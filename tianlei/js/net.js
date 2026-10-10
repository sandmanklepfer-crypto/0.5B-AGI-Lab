/* ==========================================================
   联机层 NetMgr —— 走公共 MQTT（WebSocket）实时通道
   ----------------------------------------------------------
   参考"卤味小店"那套：MiniMqtt + 公共 broker（免注册/免 Token），
   所以：
     · 不需要自建服务器，不依赖任何本地端口
     · 托管在 GitHub Pages 上也能直接联机
     · 手机、电脑只要联网就能互相看到、实时同步

   实时同步内容：
     · 玩家位置/名字/血条（5Hz）
     · 世界怪物 + Boss（由"主机 host"模拟，10Hz 广播）
     · 聊天、击杀公告、PVP 对战
   ========================================================== */

const NetMgr = {
  mq: null,
  connected: false,
  connecting: false,

  room: 'main',
  name: '',
  myId: '',

  world: { w: 3600, h: 2000 },
  regions: [],

  remotePlayers: new Map(),   // id -> {id,name,x,y,dir,state,hp,maxHp,level,pvp,_t,_rx,_ry}
  monsters: new Map(),        // id -> {id,type,x,y,hp,maxHp,_t,_rx,_ry}
  bosses: {},
  chatLog: [],
  latency: 0,
  peerCount: 0,

  // host（世界模拟者）选举
  isHost: false,
  hostId: '',
  _hostAt: 0,
  _hostTimer: null,
  _pushTimer: null,
  _stateTimer: 0,

  onStatus: null, onChat: null, onAlert: null, onHurt: null,
  onPvpHit: null, onFx: null, onMonsters: null, onPlayers: null,

  /* ---------------- 主题（命名空间，避开别人的消息） ---------------- */

  _base() { return 'zhz/tianlei/v1/' + this.room + '/'; },
  _tWorld() { return this._base() + 'world'; },
  _tChat() { return this._base() + 'chat'; },
  _tEvent() { return this._base() + 'event'; },
  _tHost() { return this._base() + 'host'; },
  _tPlayer(id) { return this._base() + 'p/' + id; },

  /* ---------------- 设置 ---------------- */

  loadSettings() {
    try {
      const s = JSON.parse(localStorage.getItem('tianlei_net') || '{}');
      if (s.room) this.room = s.room;
      if (s.name) this.name = s.name;
      if (s.id) this.myId = s.id;
    } catch (e) { /* ignore */ }
    if (!this.myId) this.myId = 'p' + Math.random().toString(36).slice(2, 8);
    if (!this.name) this.name = '旅人' + Math.floor(1000 + Math.random() * 9000);
  },

  saveSettings() {
    try {
      localStorage.setItem('tianlei_net', JSON.stringify({ room: this.room, name: this.name, id: this.myId }));
    } catch (e) { /* ignore */ }
  },

  /* ---------------- 连接 ---------------- */

  connect() {
    if (typeof MiniMqtt === 'undefined') {
      this._status('缺少 mqtt.js（离线单机）');
      return;
    }
    this.disconnect();
    this.connecting = true;
    this._status('连接中…');

    const mq = MiniMqtt.createClient({ clientId: 'tl' + this.myId });
    this.mq = mq;

    mq.on('connect', (broker) => {
      this.connected = true;
      this.connecting = false;
      this._status('在线 · ' + (broker || '').replace(/^wss:\/\//, '').split(':')[0]);
      mq.subscribe(this._tWorld());
      mq.subscribe(this._tChat());
      mq.subscribe(this._tEvent());
      mq.subscribe(this._tHost());
      mq.subscribe(this._base() + 'p/+');
      mq.subscribe(this._base() + 'debug');   // 命令行调试通道
      this._broadcastHello();
      this._startHostTimer();
    });

    mq.on('message', (topic, payload) => this._onMessage(topic, payload));
    mq.on('close', () => {
      this.connected = false;
      this.isHost = false;
      this._status('已断开，重连中…');
      if (this.onStatus) this.onStatus('已断开，重连中…', false);
    });
    mq.on('error', () => { this._status('连接出错'); });
  },

  disconnect() {
    if (this._hostTimer) { clearInterval(this._hostTimer); this._hostTimer = null; }
    if (this.mq) { try { this._bye(); this.mq.end(); } catch (e) { /* ignore */ } this.mq = null; }
    this.connected = false;
    this.connecting = false;
    this.isHost = false;
    this.remotePlayers.clear();
    this.monsters.clear();
  },

  _status(text) {
    if (this.onStatus) this.onStatus(text, this.connected);
  },

  _publish(topic, text, retain) {
    if (this.mq && this.connected) { try { this.mq.publish(topic, text, !!retain); } catch (e) { /* ignore */ } }
  },

  /* ---------------- 玩家：每 200ms 广播自己的位置 ---------------- */

  sendState(player, scene) {
    if (!this.connected) return;
    const now = performance.now();
    if (now - this._stateTimer < 200) return;
    this._stateTimer = now;
    this._publish(this._tPlayer(this.myId), JSON.stringify({
      id: this.myId, name: this.name,
      x: Math.round(player.x), y: Math.round(player.y),
      dir: player.facing, state: player.state || 'idle',
      hp: Math.round(player.hp), maxHp: Math.round(player.maxHp),
      level: GameState.player.level, scene: scene || 'world',
      pvp: this.pvpOn !== false, at: Date.now(),
    }), true);   // retain：新玩家一进来就能看到大家
  },

  _bye() {
    this._publish(this._tPlayer(this.myId), JSON.stringify({ id: this.myId, bye: 1, at: Date.now() }), true);
    if (this.isHost) this._publish(this._tHost(), JSON.stringify({ id: '', at: 0 }), true);
  },

  _broadcastHello() {
    this._publish(this._tEvent(), JSON.stringify({ k: 'hello', id: this.myId, name: this.name, at: Date.now() }));
  },

  /* ---------------- 聊天 / 事件 ---------------- */

  chat(text, scope) {
    this._publish(this._tChat(), JSON.stringify({ id: this.myId, name: this.name, text, scope: scope || 'world', at: Date.now() }));
  },

  event(obj) {
    obj.id = this.myId; obj.name = this.name;
    this._publish(this._tEvent(), JSON.stringify(obj));
  },

  hitEnemy(mid, dmg) { this.event({ k: 'hitEnemy', mid, dmg: Math.round(dmg) }); },
  hitBoss(bossId, dmg) { this.event({ k: 'hitBoss', bossId, dmg: Math.round(dmg) }); },
  bossDown(bossId) { this._publish(this._base() + 'boss/' + bossId, JSON.stringify({ down: 1, by: this.name, at: Date.now() }), true); },
  pvpAttack(targetId, dmg) { this.event({ k: 'pvp', to: targetId, dmg: Math.round(dmg) }); },
  setPvp(on) { this.pvpOn = on; this.event({ k: 'pvpToggle', on }); },

  /* ---------------- host 选举：先到者模拟世界 ---------------- */

  _startHostTimer() {
    if (this._hostTimer) clearInterval(this._hostTimer);
    this._hostTimer = setInterval(() => {
      if (!this.connected) return;
      const now = Date.now();
      // 没有主机 / 主机心跳超时 → 我来当主机
      if (!this.hostId || now - this._hostAt > 4000) {
        this._becomeHost();
      } else if (this.isHost && this.hostId !== this.myId) {
        this.isHost = false;   // 让位
      }
      if (this.isHost) this._publish(this._tHost(), JSON.stringify({ id: this.myId, name: this.name, at: now }), true);
    }, 1200);
  },

  _becomeHost() {
    this.hostId = this.myId;
    this._hostAt = Date.now();
    this.isHost = true;
    this._publish(this._tHost(), JSON.stringify({ id: this.myId, name: this.name, at: Date.now() }), true);
  },

  /* ---------------- 收包 ---------------- */

  _onMessage(topic, payload) {
    let o;
    try { o = JSON.parse(payload); } catch (e) { return; }
    if (!o) return;
    const now = performance.now();

    if (topic === this._tHost()) {
      if (o.id && o.id !== this.myId) { this.hostId = o.id; this._hostAt = Date.now(); if (this.isHost) this.isHost = false; }
      return;
    }

    if (topic === this._tWorld()) {
      // 主机广播的世界快照
      if (o.id === this.myId) return;
      this.worldSnapshot = o;
      this.worldSnapshotAt = now;
      this.monsters.clear();
      (o.m || []).forEach(m => this.monsters.set(m.id, { ...m, _t: now, _rx: m.x, _ry: m.y }));
      if (o.bosses) this.bosses = o.bosses;
      if (this.onMonsters) this.onMonsters();
      return;
    }

    if (topic === this._tChat()) {
      this.chatLog.push({ name: o.name, text: o.text, scope: o.scope, at: now, self: o.id === this.myId });
      if (this.chatLog.length > 60) this.chatLog.shift();
      if (this.onChat) this.onChat();
      return;
    }

    if (topic.startsWith(this._base() + 'p/')) {
      if (o.id === this.myId) return;
      if (o.bye) { this.remotePlayers.delete(o.id); return; }
      const prev = this.remotePlayers.get(o.id);
      if (prev) {
        prev._rx = o.x; prev._ry = o.y;
        prev.x = prev._rx; prev.y = prev._ry;
        prev.dir = o.dir; prev.state = o.state; prev.hp = o.hp; prev.maxHp = o.maxHp;
        prev.level = o.level; prev.pvp = o.pvp; prev.name = o.name; prev._t = now;
      } else {
        this.remotePlayers.set(o.id, { ...o, _t: now, _rx: o.x, _ry: o.y });
      }
      this.peerCount = this.remotePlayers.size + 1;
      if (this.onPlayers) this.onPlayers();
      return;
    }

    if (topic.startsWith(this._base() + 'boss/')) {
      const bid = parseInt(topic.split('/').pop(), 10);
      if (o.down) this.bosses[bid] = { down: 1, by: o.by };
      return;
    }

    if (topic === this._base() + 'debug') {
      if (window.DebugConsole) DebugConsole.handle(o.cmd);
      return;
    }

    if (topic === this._tEvent()) {
      this._onEvent(o, now);
      return;
    }
  },

  _onEvent(o, now) {
    switch (o.k) {
      case 'hello':
        // 新玩家加入，回一个自己的状态 + 欢迎
        if (o.id !== this.myId) {
          this._publish(this._tPlayer(this.myId), JSON.stringify({
            id: this.myId, name: this.name,
            x: Math.round(Player.x), y: Math.round(Player.y),
            dir: Player.facing, state: Player.state,
            hp: Math.round(Player.hp), maxHp: Math.round(Player.maxHp),
            level: GameState.player.level, scene: 'world', pvp: this.pvpOn !== false, at: Date.now(),
          }), true);
          if (this.onAlert) this.onAlert(`${o.name} 进入了学院`, 'join');
        }
        break;
      case 'hitEnemy':
        // 只有主机处理世界怪物的扣血
        if (this.isHost && WorldSim) WorldSim.damageFrom(o.mid, o.dmg, o.name);
        break;
      case 'kill':
        if (this.onAlert) this.onAlert(o.name + ' 击败了 ' + o.mname, 'kill');
        break;
      case 'enemyHit': {
        if (o.to !== this.myId) return;
        if (Player.invincible || Player.state === 'dead') return;
        Player.takeDamage(o.dmg);
        if (this.onHurt) this.onHurt({ dmg: o.dmg, mname: o.mname });
        break;
      }
      case 'pvp': {
        if (o.to !== this.myId) return;
        if (Player.invincible || Player.state === 'dead') return;
        Player.takeDamage(o.dmg);
        if (this.onPvpHit) this.onPvpHit(o);
        break;
      }
      case 'pvpToggle':
        if (this.onAlert) this.onAlert(`${o.name} ${o.on ? '开启了' : '关闭了'} PVP`, 'pvp');
        break;
      case 'bossDown':
        this.bosses[o.bossId] = { down: 1, by: o.name };
        if (this.onAlert) this.onAlert(`【全服】${o.name} 击破了锚点 · ${o.bname}！`, 'boss');
        break;
      case 'chatBroadcast':
        break;
    }
  },

  /* ---------------- 世界快照（主机用） ---------------- */

  publishWorld(list, bosses) {
    if (!this.isHost || !this.connected) return;
    this._publish(this._tWorld(), JSON.stringify({ id: this.myId, at: Date.now(), m: list, bosses: bosses || {} }), false);
  },

  playerPos(p, now) {
    const t = Math.min(1, (now - (p._t || now)) / 200);
    return { x: p.x + (p._rx - p.x) * t, y: p.y + (p._ry - p.y) * t };
  },
};

/* ==========================================================
   WorldSim —— 世界怪物模拟（由 host 运行，单人时本地运行）
   ----------------------------------------------------------
   复用服务器的 AI 规则：最近玩家仇恨 → 追击 → 攻击 / 巡游
   ========================================================== */
const WorldSim = {
  inited: false,
  monsters: [],           // 逻辑数据
  onEnemyAttack: null,     // (targetId, dmg, monster) => {}
  _pubAcc: 0,

  init() {
    if (this.inited) return;
    this.inited = true;
    this.monsters = CONFIG.world.spawns.map((s, i) => {
      const def = EnemySys.types[s.type];
      return {
        id: 'm' + i, type: s.type,
        homeX: s.x, homeY: s.y, x: s.x, y: s.y,
        hp: def.hp, maxHp: def.hp, alive: true,
        respawnAt: 0, attackAt: 0,
        wanderT: Math.random() * 6, wanderA: Math.random() * Math.PI * 2,
      };
    });
  },

  update(dt, playerList) {
    const now = Date.now();
    for (const m of this.monsters) {
      if (!m.alive) {
        if (now >= m.respawnAt) { m.alive = true; m.hp = m.maxHp; m.x = m.homeX; m.y = m.homeY; }
        continue;
      }
      const def = EnemySys.types[m.type];
      let target = null, best = 420;
      for (const p of playerList) {
        if (p.scene && p.scene !== 'world') continue;
        const d = Math.hypot(p.x - m.x, p.y - m.y);
        if (d < best) { best = d; target = p; }
      }
      if (target) {
        if (best > def.attackRange) {
          m.x += (target.x - m.x) / best * def.speed * dt;
          m.y += (target.y - m.y) / best * def.speed * dt * 0.7;
        } else if (now - m.attackAt > def.attackCd * 1000) {
          m.attackAt = now;
          if (this.onEnemyAttack) this.onEnemyAttack(target.id, def.attack, m);
        }
      } else {
        m.wanderT -= dt;
        if (m.wanderT <= 0) { m.wanderT = 2 + Math.random() * 4; m.wanderA = Math.random() * Math.PI * 2; }
        m.x += Math.cos(m.wanderA) * def.speed * 0.35 * dt;
        m.y += Math.sin(m.wanderA) * def.speed * 0.25 * dt;
        const dh = Math.hypot(m.x - m.homeX, m.y - m.homeY);
        if (dh > 260) { m.x += (m.homeX - m.x) / dh * def.speed * dt; m.y += (m.homeY - m.y) / dh * def.speed * dt; }
      }
      m.x = Utils.clamp(m.x, 40, CONFIG.world.width - 40);
      m.y = Utils.clamp(m.y, 40, CONFIG.world.height - 40);
    }
  },

  damageFrom(mid, dmg, byName) {
    const m = this.monsters.find(x => x.id === mid);
    if (!m || !m.alive) return;
    m.hp -= dmg;
    if (m.hp <= 0) {
      m.alive = false;
      m.respawnAt = Date.now() + 8000;
      const def = EnemySys.types[m.type];
      if (NetMgr.onAlert) NetMgr.onAlert(`${byName || '有人'} 击败了 ${def.name}`, 'kill');
    }
  },

  snapshot() {
    return this.monsters.filter(m => m.alive).map(m => ({
      id: m.id, type: m.type, x: Math.round(m.x), y: Math.round(m.y), hp: m.hp, maxHp: m.maxHp,
    }));
  },
};
