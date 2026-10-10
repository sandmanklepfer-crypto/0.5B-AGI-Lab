/* ==========================================================
   WorldMgr —— 联机 RPG 开放世界（取代原来的"大厅 Hub"）
   ----------------------------------------------------------
   · 大世界 3600x2000，相机跟随
   · 小怪分散在地图各区域巡游（不再是死板的大厅传送门）
   · 原来 4 个 Boss 的"关卡入口"→ 地图上的"锚点"，走到就触发
   · 玩家之间通过 MQTT 实时同步（位置/血条/名字），可交互、可 PVP
   · 世界怪物由"主机"模拟并广播（单人时本地模拟，离线也能玩）
   复用：Player / Enemy / BattleSys（Boss 战仍是原系统）
   ========================================================== */

const WorldMgr = {
  canvas: null,
  ctx: null,
  running: false,
  animFrame: null,
  lastTime: 0,

  scale: 1,
  viewW: 1280,
  viewH: 720,
  cssW: 0,
  cssH: 0,
  cam: { x: 0, y: 0 },

  enemies: [],
  enemyById: new Map(),
  floatTexts: [],
  bgImages: {},
  playerImg: null,

  _lastBossZone: null,
  _bossCooldown: 0,
  _hint: '',
  _drawErr: '',

  /* ---------------- 生命周期 ---------------- */

  start() {
    if (this.running) this.stop();

    this.canvas = document.getElementById('worldCanvas');
    if (!this.canvas) { console.warn('[WorldMgr] 找不到 worldCanvas'); return; }
    this.ctx = this.canvas.getContext('2d');

    if (window.Player) {
      const sp = (CONFIG.world && CONFIG.world.spawnPoint) || { x: 320, y: 900 };
      if (Player.hp <= 0 || Player.state === 'dead') Player.reset();
      // 状态复位（从 Boss 战撤退回来时最容易残留，导致"动不了"）
      Player.dodging = false;
      Player.invincible = false;
      Player.timeSlowMul = 1;
      Player.slowTimer = 0;
      Player.state = 'idle';
      Player.worldMode = false;   // 由 update 内部按需临时开启
      // 坐标自愈 + 位置恢复（从 Boss 回来时回到进入前的位置）
      if (!isFinite(Player.x) || !isFinite(Player.y)) { Player.x = sp.x; Player.y = sp.y; }
      else if (this._returnPos) { Player.x = this._returnPos.x; Player.y = this._returnPos.y; }
      this._returnPos = null;
      if (Player.facing !== 1 && Player.facing !== -1) Player.facing = 1;
      // 摇杆复位，防止残留方向把人"顶住"
      if (window.InputMgr) { InputMgr.joystick.x = 0; InputMgr.joystick.y = 0; InputMgr.joystick.active = false; }
      // 相机立即归位，避免拖影
      this.cam.x = Player.x - (this.viewW || 1280) / 2;
      this.cam.y = Player.y - (this.viewH || 720) / 2;
    }

    // 预载分区背景
    this.bgImages = {};
    for (const r of CONFIG.world.regions) {
      const img = new Image();
      img.src = r.bg;
      this.bgImages[r.id] = img;
    }
    this.playerImg = new Image();
    this.playerImg.src = 'assets/img/heyun_idle.png';

    // 世界怪物模拟
    if (window.WorldSim) {
      WorldSim.init();
      WorldSim.onEnemyAttack = (targetId, dmg, m) => this._onEnemyAttack(targetId, dmg, m);
    }

    this.resize();
    if (window.LayoutMgr) {
      this._layoutCb = () => this.resize();
      LayoutMgr.onResize(this._layoutCb);
    }

    this._bindJoystick();
    this._bindChat();
    this._bindPanels();
    this._bindCanvasClick();
    this.renderChat();
    this.updateObjective();

    if (window.NetMgr) {
      NetMgr.loadSettings();
      this._hookNet();
      if (!NetMgr.connected) NetMgr.connect();
    }

    this.updateHUDRow();
    this.running = true;
    this.lastTime = performance.now();
    this.gameLoop();

    if (typeof AudioMgr !== 'undefined' && AudioMgr.playBgm) AudioMgr.playBgm('main');
  },

  stop() {
    this.running = false;
    if (this.animFrame) { cancelAnimationFrame(this.animFrame); this.animFrame = null; }
  },

  _hookNet() {
    NetMgr.onStatus = (text, ok) => {
      const el = document.getElementById('worldNetStatus');
      if (el) {
        el.textContent = (ok ? '● ' : '○ ') + text;
        el.className = 'world-net-status' + (ok ? ' online' : ' offline');
      }
      this.updateHUDRow();
    };
    NetMgr.onChat = () => this.renderChat();
    NetMgr.onAlert = (text, kind) => this.pushAlert(text, kind);
    NetMgr.onPvpHit = (msg) => this._onPvpHit(msg);
    NetMgr.onHurt = (msg) => {
      this.spawnFloatText(Player.x, Player.y - Player.height, '-' + msg.dmg, '#f87171');
      ScreenShake.shake(4, 0.2);
      if (Player.hp <= 0) this._playerDeath();
    };
    NetMgr.onPlayers = () => this.updateHUDRow();
  },

  /* ---------------- 尺寸 ---------------- */

  resize() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    let cw = parent ? parent.offsetWidth : 0;
    let ch = parent ? parent.offsetHeight : 0;
    if (!cw || !ch) { cw = window.innerWidth || 1280; ch = window.innerHeight || 720; }

    this.cssW = cw;
    this.cssH = ch;

    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.floor(cw * dpr));
    this.canvas.height = Math.max(1, Math.floor(ch * dpr));
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this.scale = ch / CONFIG.canvasHeight || 1;
    this.viewW = cw / this.scale;
    this.viewH = CONFIG.canvasHeight;
  },

  /* ---------------- 主循环 ---------------- */

  gameLoop() {
    if (!this.running) return;
    // 停止只由场景切换显式触发（SceneMgr.show -> HubMgr.stop -> WorldMgr.stop），
    // 这里不再按 currentScene 自动停机，否则会出现"撤退后世界起不来、人动不了"。
    try {
      const now = performance.now();
      const dt = Math.min((now - this.lastTime) / 1000, 0.05);
      this.lastTime = now;
      this.update(dt);
      this.draw();
    } catch (e) {
      this._drawErr = (e && e.message) || String(e);
      console.error('[WorldMgr] 帧错误:', e);
    } finally {
      this.animFrame = requestAnimationFrame(() => this.gameLoop());
    }
  },

  /* ---------------- 逻辑 ---------------- */

  update(dt) {
    const W = CONFIG.world;
    const p = Player;

    // 坐标自愈：绝不把 NaN 带进后续运算
    if (!isFinite(p.x) || !isFinite(p.y)) {
      const sp = W.spawnPoint || { x: 320, y: 900 };
      p.x = sp.x; p.y = sp.y;
    }

    // 移动
    let dx = 0, dy = 0;
    if (InputMgr.keys['a'] || InputMgr.keys['arrowleft']) dx -= 1;
    if (InputMgr.keys['d'] || InputMgr.keys['arrowright']) dx += 1;
    if (InputMgr.keys['w'] || InputMgr.keys['arrowup']) dy -= 1;
    if (InputMgr.keys['s'] || InputMgr.keys['arrowdown']) dy += 1;
    if (InputMgr.joystick.active) { dx = InputMgr.joystick.x; dy = InputMgr.joystick.y; }
    dx = Utils.safeNum(dx, 0); dy = Utils.safeNum(dy, 0);   // 输入自愈
    if (this.chatOpen) { dx = 0; dy = 0; }

    const moving = (dx !== 0 || dy !== 0) && p.state !== 'dead';
    if (moving) {
      const len = Math.hypot(dx, dy) || 1;
      const speed = 300;
      p.x += (dx / len) * speed * dt;
      p.y += (dy / len) * speed * dt;
      if (dx > 0.15) p.facing = 1; else if (dx < -0.15) p.facing = -1;
      if (p.state === 'idle' || p.state === 'walk') p.state = 'walk';
    } else if (p.state === 'walk') {
      p.state = 'idle';
    }

    // 只在世界场景设置 worldMode，绝不污染 Boss 战
    p.worldMode = true;
    p.update(dt);
    p.worldMode = false;

    p.x = Utils.clamp(p.x, 40, W.width - 40);
    p.y = Utils.clamp(p.y, 60, W.height - 40);

    // 让原战斗系统把"世界怪物"当可攻击目标（不改 Player 攻击代码）
    if (window.BattleSys) { BattleSys.mode = 'wave'; BattleSys.enemies = this.enemies; BattleSys.boss = null; }
    p.handleInput(dt);

    // 相机
    const camX = Utils.clamp(p.x - this.viewW / 2, 0, Math.max(0, W.width - this.viewW));
    const camY = Utils.clamp(p.y - this.viewH / 2, 0, Math.max(0, W.height - this.viewH));
    this.cam.x += (camX - this.cam.x) * Math.min(1, dt * 8);
    this.cam.y += (camY - this.cam.y) * Math.min(1, dt * 8);

    // 世界怪物
    this._updateMonsters(dt);

    // Boss 锚点
    this._updateBossZones(dt);

    // 特效
    ParticleSys.update(dt);
    ScreenShake.update(dt);
    this.floatTexts = this.floatTexts.filter(t => { t.life -= dt; t.y -= 40 * dt; return t.life > 0; });

    // 同步状态
    if (window.NetMgr && NetMgr.sendState) NetMgr.sendState(p, 'world');

    this.updateHUDRow();
  },

  /** 判断当前谁是世界权威：单人/主机=本地模拟，否则用 MQTT 快照 */
  _isAuthority() {
    return !window.NetMgr || !NetMgr.connected || NetMgr.isHost;
  },

  _updateMonsters(dt) {
    const W = CONFIG.world;

    // 1) 权威：本地模拟 + （主机时）广播
    if (this._isAuthority() && window.WorldSim) {
      const list = [{ id: NetMgr.myId, x: Player.x, y: Player.y, scene: 'world' }];
      if (window.NetMgr) for (const [id, rp] of NetMgr.remotePlayers) list.push({ id, x: rp.x, y: rp.y, scene: rp.scene });
      WorldSim.update(dt, list);
      if (window.NetMgr && NetMgr.isHost) {
        WorldSim._pubAcc = (WorldSim._pubAcc || 0) + dt;
        if (WorldSim._pubAcc >= 0.1) {
          WorldSim._pubAcc = 0;
          NetMgr.publishWorld(WorldSim.snapshot(), {});
        }
      }
    }

    // 2) 取权威怪物列表
    let auth = [];
    if (this._isAuthority()) {
      auth = WorldSim.monsters.map(m => ({ id: m.id, type: m.type, x: m.x, y: m.y, hp: Math.max(0, m.hp), maxHp: m.maxHp, alive: m.alive }));
    } else {
      for (const [id, m] of NetMgr.monsters) auth.push({ id, type: m.type, x: m.x, y: m.y, hp: m.hp, maxHp: m.maxHp, alive: true });
    }

    // 3) 同步到绘制实体
    const seen = new Set();
    for (const am of auth) {
      if (!am.alive || am.hp <= 0) continue;
      seen.add(am.id);
      let e = this.enemyById.get(am.id);
      if (!e) {
        e = EnemySys.createEnemy(am.type, am.x, am.y);
        if (!e) continue;
        e.simId = am.id;
        this._wrapEnemy(e);
        this.enemies.push(e);
        this.enemyById.set(am.id, e);
      }
      e.hp = am.hp; e.maxHp = am.maxHp;
      // 让原 Enemy 跑一次动画/朝向
      e.update(dt, Player.x, Player.y);
      // 位置以权威为准（平滑逼近，覆盖本地 AI 位移）
      e.x += (am.x - e.x) * Math.min(1, dt * 12);
      e.y += (am.y - e.y) * Math.min(1, dt * 12);
      const moved = (Math.abs(am.x - (e._px || am.x)) + Math.abs(am.y - (e._py || am.y))) > 1.5;
      e.state = moved ? 'chase' : 'idle';
      if (am.x > e.x + 2) e.facing = 1; else if (am.x < e.x - 2) e.facing = -1;
      e._px = am.x; e._py = am.y;
    }

    // 4) 移除已消失
    for (const [id, e] of [...this.enemyById]) {
      if (!seen.has(id)) {
        this.enemies = this.enemies.filter(x => x !== e);
        this.enemyById.delete(id);
      }
    }
  },

  /** 给 Enemy 包装 takeDamage：本地表现 + 上报/结算 */
  _wrapEnemy(e) {
    const orig = e.takeDamage.bind(e);
    e.takeDamage = (dmg, fromX) => {
      orig(dmg, fromX);                       // 本地表现（闪白/击退/粒子）
      this.spawnFloatText(e.x, e.y - e.height, '-' + Math.round(dmg), '#fbbf24');
      if (this._isAuthority()) {
        if (window.WorldSim) WorldSim.damageFrom(e.simId, dmg, (window.NetMgr && NetMgr.name) || '你');
      } else if (window.NetMgr) {
        NetMgr.hitEnemy(e.simId, dmg);
      }
      // 死亡以权威为准，这里不回传"已死"
      e.hp = Math.max(1, e.hp);
      return false;
    };
  },

  _onEnemyAttack(targetId, dmg, m) {
    const mname = (EnemySys.types[m.type] || {}).name || '魔物';
    if (targetId === (window.NetMgr && NetMgr.myId)) {
      // 打的是我
      if (Player.state === 'dead' || Player.invincible) return;
      Player.takeDamage(dmg);
      this.spawnFloatText(Player.x, Player.y - Player.height, '-' + dmg, '#f87171');
      ScreenShake.shake(4, 0.2);
      if (Player.hp <= 0) this._playerDeath();
    } else if (window.NetMgr && NetMgr.isHost) {
      // 主机告诉别人他被打了
      NetMgr.event({ k: 'enemyHit', to: targetId, dmg, mname });
    }
  },

  /* ---------------- Boss 锚点 ---------------- */

  _updateBossZones(dt) {
    this._bossCooldown = Math.max(0, this._bossCooldown - dt);
    let near = null, bestD = Infinity;
    for (const z of CONFIG.world.bossZones) {
      const d = Utils.dist(Player.x, Player.y, z.x, z.y);
      if (d < z.r && d < bestD) { bestD = d; near = z; }
    }
    const hintEl = document.getElementById('worldHint');
    if (near) {
      if (hintEl) { hintEl.textContent = `⚔ ${near.name} · ${near.hint}（走近自动触发）`; hintEl.style.display = 'block'; }
      if (this._bossCooldown <= 0 && this._lastBossZone !== near.id) {
        this._bossCooldown = 3;
        this._lastBossZone = near.id;
        this.triggerBoss(near.id);
      }
    } else {
      if (hintEl) hintEl.style.display = 'none';
      if (this._lastBossZone !== null) this._lastBossZone = null;
    }
  },

  triggerBoss(bossId) {
    // 记住进入 Boss 前的位置，撤退/胜利后原样返回
    this._returnPos = { x: Player.x, y: Player.y };
    AudioMgr.playSfx('levelup');
    ScreenShake.shake(6, 0.4);
    ParticleSys.emit(Player.x, Player.y - 40, 30, { color: '#38e0a2', size: 4, life: 0.8, speed: 140 });
    this.stop();
    setTimeout(() => { SceneMgr.show('battle'); BattleSys.start(bossId); }, 420);
  },

  /* ---------------- 玩家死亡 ---------------- */

  _playerDeath() {
    Player.state = 'dead';
    this.pushAlert('你被击倒了，3 秒后在学院大门复活', 'pvp');
    setTimeout(() => {
      const sp = CONFIG.world.spawnPoint;
      Player.reset();
      Player.x = sp.x; Player.y = sp.y;
    }, 3000);
  },

  _onPvpHit(msg) {
    this.spawnFloatText(Player.x, Player.y - Player.height, '-' + msg.dmg + ' PVP', '#f472b6');
    ScreenShake.shake(5, 0.3);
    this.pushAlert(`${msg.name} 攻击了你！`, 'pvp');
    if (Player.hp <= 0) this._playerDeath();
  },

  /* ---------------- 飘字 / 公告 ---------------- */

  spawnFloatText(x, y, text, color) {
    this.floatTexts.push({ x, y, text, color: color || '#fff', life: 0.9, maxLife: 0.9 });
  },

  pushAlert(text, kind) {
    const host = document.getElementById('worldAlerts');
    if (!host) return;
    const el = document.createElement('div');
    el.className = 'world-alert' + (kind ? ' ' + kind : '');
    el.textContent = text;
    host.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 400); }, 3600);
    while (host.children.length > 5) host.removeChild(host.firstChild);
  },

  /* ---------------- 点击其他玩家 → PVP ---------------- */

  _bindCanvasClick() {
    if (this._clickBound) return;
    this._clickBound = true;
    this.canvas.addEventListener('click', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const s = this.scale || 1;
      let sx = e.clientX - rect.left, sy = e.clientY - rect.top;
      if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
        const pt = FullscreenMgr.screenToContainer(e.clientX, e.clientY);
        sx = pt.x; sy = pt.y;
      }
      const wx = sx / s + this.cam.x;
      const wy = sy / s + this.cam.y;
      const now = performance.now();
      for (const [id, rp] of NetMgr.remotePlayers) {
        const pos = NetMgr.playerPos(rp, now);
        if (Utils.dist(wx, wy, pos.x, pos.y - 60) < 90) { this.attackPlayer(id); return; }
      }
    });
  },

  attackPlayer(id) {
    if (!window.NetMgr || !NetMgr.connected) { this.pushAlert('未联网，无法 PVP', 'pvp'); return; }
    const t = NetMgr.remotePlayers.get(id);
    if (!t) return;
    if (!t.pvp) { this.pushAlert(`${t.name} 未开启 PVP`, 'pvp'); return; }
    const dmg = Math.max(5, Math.round(Player.attack * (1 + Math.random() * 0.5)));
    NetMgr.pvpAttack(id, dmg);
    this.spawnFloatText(t.x, t.y - 90, '-' + dmg, '#f472b6');
    Player.facing = t.x > Player.x ? 1 : -1;
    AudioMgr.playSfx('hit');
    ParticleSys.burst(Player.x + Player.facing * 40, Player.y - 40, Player.facing > 0 ? 0 : Math.PI, 0.6, 6, { color: '#f472b6', size: 3, life: 0.3, speed: 140 });
  },

  /* ---------------- 输入 ---------------- */

  _bindJoystick() {
    const container = document.getElementById('worldJoystick');
    const stick = document.getElementById('worldJoystickStick');
    if (!container || container._bound) return;
    container._bound = true;

    const centerOf = () => { const r = container.getBoundingClientRect(); return { cx: r.left + r.width / 2, cy: r.top + r.height / 2 }; };

    const move = (e) => {
      if (!InputMgr.joystick.active || e.pointerId !== InputMgr.joystick.pointerId) return;
      e.preventDefault();
      const { cx, cy } = centerOf();
      let dx = e.clientX - cx, dy = e.clientY - cy;
      if (window.FullscreenMgr && FullscreenMgr.forceRotate) { const a = dx, b = dy; dx = b; dy = -a; }
      const maxDist = 42, len = Math.hypot(dx, dy);
      let vx = dx, vy = dy;
      if (len > maxDist) { vx = dx / len * maxDist; vy = dy / len * maxDist; }
      InputMgr.joystick.x = Utils.clamp(dx / maxDist, -1, 1);
      InputMgr.joystick.y = Utils.clamp(dy / maxDist, -1, 1);
      const jl = Math.hypot(InputMgr.joystick.x, InputMgr.joystick.y);
      if (jl > 1) { InputMgr.joystick.x /= jl; InputMgr.joystick.y /= jl; }
      let px = vx, py = vy;
      if (window.FullscreenMgr && FullscreenMgr.forceRotate) { const a = px; px = -py; py = a; }
      if (stick) stick.style.transform = `translate(calc(-50% + ${px}px), calc(-50% + ${py}px))`;
    };

    container.addEventListener('pointerdown', (e) => {
      e.preventDefault(); AudioMgr.resume();
      InputMgr.joystick.active = true; InputMgr.joystick.pointerId = e.pointerId; move(e);
    });
    window.addEventListener('pointermove', move);
    const end = (e) => {
      if (e.pointerId !== InputMgr.joystick.pointerId) return;
      InputMgr.joystick.active = false; InputMgr.joystick.x = 0; InputMgr.joystick.y = 0; InputMgr.joystick.pointerId = null;
      if (stick) stick.style.transform = 'translate(-50%, -50%)';
    };
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  },

  _bindChat() {
    const input = document.getElementById('worldChatInput');
    if (!input || input._bound) return;
    input._bound = true;
    input.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') {
        const text = input.value.trim();
        if (text) { if (window.NetMgr && NetMgr.connected) NetMgr.chat(text, 'world'); else this.pushAlert('未联网，消息未发送', 'sys'); }
        input.value = ''; input.blur(); this.chatOpen = false;
      } else if (e.key === 'Escape') { input.value = ''; input.blur(); this.chatOpen = false; }
    });
    input.addEventListener('focus', () => { this.chatOpen = true; });
    input.addEventListener('blur', () => { this.chatOpen = false; });
  },

  _bindPanels() {
    document.querySelectorAll('.hub-btn[data-action="multiplayer"]').forEach(btn => {
      if (btn._mpBound) return;
      btn._mpBound = true;
      btn.addEventListener('click', () => { AudioMgr.playSfx('click'); this.openMultiPanel(); });
    });

    const nameEl = document.getElementById('mpName');
    const roomEl = document.getElementById('mpRoom');
    const statusEl = document.getElementById('mpStatus');
    const connectBtn = document.getElementById('mpConnectBtn');
    const pvpBtn = document.getElementById('mpPvpBtn');

    this._syncMp = () => {
      if (nameEl) nameEl.value = NetMgr.name;
      if (roomEl) roomEl.value = NetMgr.room;
      if (statusEl) statusEl.textContent = NetMgr.connected
        ? `已连接 · 在线 ${NetMgr.remotePlayers.size + 1} 人` : (NetMgr.connecting ? '连接中…' : '未连接');
      if (pvpBtn) pvpBtn.textContent = 'PVP：' + (this.pvpOn === false ? '关闭' : '开启');
    };

    if (connectBtn && !connectBtn._b) {
      connectBtn._b = true;
      connectBtn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        NetMgr.name = (nameEl.value || '').trim() || NetMgr.name;
        NetMgr.room = ((roomEl.value || 'main').trim() || 'main').replace(/[^a-zA-Z0-9_-]/g, '');
        NetMgr.saveSettings();
        NetMgr.connect();
        this.pushAlert('正在连接联机频道…', 'sys');
      });
    }
    if (pvpBtn && !pvpBtn._b) {
      pvpBtn._b = true;
      pvpBtn.addEventListener('click', () => {
        this.pvpOn = this.pvpOn === false ? true : false;
        if (window.NetMgr && NetMgr.connected) NetMgr.setPvp(this.pvpOn);
        pvpBtn.textContent = 'PVP：' + (this.pvpOn ? '开启' : '关闭');
      });
    }
  },

  openMultiPanel() {
    if (window.NetMgr) NetMgr.loadSettings();
    if (this._syncMp) this._syncMp();
    const p = document.getElementById('multiplayerPanel');
    if (p) p.classList.remove('hidden');
  },

  sendChatFromBox() {
    const input = document.getElementById('worldChatInput');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    if (window.NetMgr && NetMgr.connected) NetMgr.chat(text, 'world'); else this.pushAlert('未联网', 'sys');
    input.value = ''; this.chatOpen = false;
  },

  renderChat() {
    const box = document.getElementById('worldChatLog');
    if (!box || !window.NetMgr) return;
    box.innerHTML = NetMgr.chatLog.slice(-6).map(c =>
      `<div class="chat-line${c.self ? ' self' : ''}"><b>${this._esc(c.name)}</b>：${this._esc(c.text)}</div>`
    ).join('');
  },

  _esc(s) { return String(s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m])); },

  /* ---------------- HUD ---------------- */

  updateHUDRow() {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('worldGold', GameState.player.gold);
    set('worldStar', GameState.player.star);
    set('worldLevel', GameState.player.level);
    const hp = document.getElementById('worldHpFill');
    const mp = document.getElementById('worldMpFill');
    if (hp) hp.style.width = Math.max(0, (Player.hp / Player.maxHp) * 100) + '%';
    if (mp) mp.style.width = Math.max(0, (Player.mp / Player.maxMp) * 100) + '%';
    const rn = document.getElementById('worldRegion');
    if (rn) {
      const r = CONFIG.world.regions.find(rg => Player.x >= rg.x && Player.x < rg.x + rg.w && Player.y >= rg.y && Player.y < rg.y + rg.h);
      rn.textContent = r ? r.name : '未知区域';
    }
    const st = document.getElementById('worldNetStatus');
    if (st && window.NetMgr) {
      const n = NetMgr.connected ? NetMgr.remotePlayers.size + 1 : 0;
      st.textContent = NetMgr.connected ? `● 在线 ${n}人${NetMgr.isHost ? '·房主' : ''}` : (NetMgr.connecting ? '○ 连接中…' : '○ 未连接');
      st.className = 'world-net-status' + (NetMgr.connected ? ' online' : ' offline');
    }
  },

  updateObjective() {
    const el = document.getElementById('worldObjective');
    if (el) el.textContent = `锚点 ${GameState.player.defeatedBosses.length}/4`;
  },

  /* ---------------- 绘制 ---------------- */

  draw() {
    const ctx = this.ctx;
    const W = CONFIG.world;
    const s = this.scale || 1;

    ctx.setTransform(window.devicePixelRatio || 1, 0, 0, window.devicePixelRatio || 1, 0, 0);
    ctx.clearRect(0, 0, this.cssW, this.cssH);
    ctx.fillStyle = '#141026';
    ctx.fillRect(0, 0, this.cssW, this.cssH);

    ctx.save();
    ctx.scale(s, s);
    ctx.translate(-this.cam.x, -this.cam.y);

    // 分区背景
    for (const r of W.regions) {
      const img = this.bgImages[r.id];
      if (img && img.complete && img.naturalWidth) {
        ctx.globalAlpha = 0.9;
        ctx.drawImage(img, r.x, r.y, r.w, r.h);
        ctx.globalAlpha = 1;
      } else {
        // 兜底：不同分区不同底色，保证不是纯黑
        const g = ctx.createLinearGradient(r.x, r.y, r.x, r.y + r.h);
        const pal = { gate: ['#1b1440', '#0e0a20'], courtyard: ['#132a3a', '#0a1622'], library: ['#2a1b3a', '#140a20'], corridor: ['#0e1a2a', '#060a12'] };
        const c = pal[r.id] || ['#1a1030', '#0b0718'];
        g.addColorStop(0, c[0]); g.addColorStop(1, c[1]);
        ctx.fillStyle = g;
        ctx.fillRect(r.x, r.y, r.w, r.h);
      }
      ctx.fillStyle = 'rgba(8,4,20,0.25)';
      ctx.fillRect(r.x, r.y, r.w, r.h);
      ctx.strokeStyle = 'rgba(168,85,247,0.28)';
      ctx.lineWidth = 3;
      ctx.strokeRect(r.x, r.y, r.w, r.h);
      ctx.save();
      ctx.fillStyle = 'rgba(196,181,253,0.25)';
      ctx.font = 'bold 44px "Noto Serif SC", serif';
      ctx.textAlign = 'center';
      ctx.fillText(r.name, r.x + r.w / 2, r.y + 84);
      ctx.restore();
    }

    // Boss 锚点
    for (const z of W.bossZones) this._drawBossZone(ctx, z);

    // 实体（按 y 排序）
    const now = performance.now();
    const ents = [];
    for (const e of this.enemies) if (e.state !== 'dead') ents.push({ y: e.getSortY ? e.getSortY() : e.y, draw: () => e.draw(ctx) });
    if (window.NetMgr) for (const [id, rp] of NetMgr.remotePlayers) {
      const pos = NetMgr.playerPos(rp, now);
      ents.push({ y: pos.y, draw: () => this._drawRemote(ctx, rp, pos) });
    }
    ents.push({ y: Player.y, draw: () => Player.draw(ctx) });
    ents.sort((a, b) => a.y - b.y);
    for (const e of ents) e.draw();

    ParticleSys.draw(ctx);

    for (const t of this.floatTexts) {
      ctx.save();
      ctx.globalAlpha = Math.max(0, t.life / t.maxLife);
      ctx.fillStyle = t.color;
      ctx.font = 'bold 22px "Noto Serif SC", serif';
      ctx.textAlign = 'center';
      ctx.shadowColor = '#000'; ctx.shadowBlur = 6;
      ctx.fillText(t.text, t.x, t.y);
      ctx.restore();
    }

    ctx.restore();

    // 调试：把绘制错误显示出来（有错才显示）
    if (this._drawErr) {
      ctx.save();
      ctx.fillStyle = 'rgba(120,0,0,0.85)';
      ctx.fillRect(0, this.cssH - 40, this.cssW, 40);
      ctx.fillStyle = '#fff'; ctx.font = '16px monospace'; ctx.textAlign = 'left';
      ctx.fillText('绘制错误: ' + this._drawErr, 20, this.cssH - 14);
      ctx.restore();
    }

    this._drawBossBar();

    // 调试行（默认关闭；需要时用命令行开：dbg overlay on）
    if (window.__TL_DEBUG === true) {
      const dpr = window.devicePixelRatio || 1;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = 'rgba(0,0,0,0.55)';
      ctx.fillRect(0, 0, this.cssW, 22);
      ctx.fillStyle = '#7CFC00';
      ctx.font = '13px monospace';
      ctx.textAlign = 'left';
      const loaded = Object.values(this.bgImages).filter(i => i.complete && i.naturalWidth).length;
      ctx.fillText(`dbg ${Math.round(this.cssW)}x${Math.round(this.cssH)} s=${this.scale.toFixed(2)} cam=${Math.round(this.cam.x)},${Math.round(this.cam.y)} p=${Math.round(Player.x)},${Math.round(Player.y)} e=${this.enemies.length} bg=${loaded}/${Object.keys(this.bgImages).length} net=${window.NetMgr && NetMgr.connected ? 'on' : 'off'}${window.NetMgr && NetMgr.isHost ? '/host' : ''}`, 12, 15);
      ctx.restore();
    }
  },

  _drawBossZone(ctx, z) {
    const t = performance.now() / 1000;
    const dead = GameState.player.defeatedBosses.includes(z.id);
    const col = dead ? '#6ee7b7' : '#f87171';
    const pulse = 1 + Math.sin(t * 2 + z.id) * 0.06;
    ctx.save();
    ctx.translate(z.x, z.y);
    ctx.scale(pulse, pulse);
    const g = ctx.createRadialGradient(0, 0, 10, 0, 0, z.r);
    g.addColorStop(0, dead ? 'rgba(110,231,183,0.30)' : 'rgba(248,113,113,0.32)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.ellipse(0, 0, z.r, z.r * 0.45, 0, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = col; ctx.globalAlpha = 0.8; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.ellipse(0, 0, z.r * 0.8, z.r * 0.36, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.ellipse(0, 0, z.r * 0.5, z.r * 0.22, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.textAlign = 'center';
    ctx.shadowColor = col; ctx.shadowBlur = 12;
    ctx.fillStyle = dead ? '#a7f3d0' : '#fecaca';
    ctx.font = 'bold 22px "Noto Serif SC", serif';
    ctx.fillText(z.name, 0, -z.r * 0.5 - 14);
    ctx.font = '13px "Noto Serif SC", serif';
    ctx.fillStyle = 'rgba(226,232,240,0.85)';
    ctx.fillText(dead ? '✓ 已击破' : z.hint, 0, -z.r * 0.5 + 8);
    ctx.restore();
  },

  _drawRemote(ctx, rp, pos) {
    ctx.save();
    ctx.translate(pos.x, pos.y);
    ctx.scale((rp.dir || 1) * 0.6, 0.6);
    const img = this.playerImg;
    if (img && img.complete && img.naturalWidth) {
      ctx.shadowColor = rp.pvp ? '#f472b6' : '#38bdf8';
      ctx.shadowBlur = 14;
      ctx.drawImage(img, -50, -140, 100, 140);
    } else {
      ctx.fillStyle = rp.pvp ? '#f472b6' : '#38bdf8';
      ctx.beginPath(); ctx.arc(0, -60, 26, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();

    ctx.save();
    ctx.textAlign = 'center';
    ctx.font = 'bold 14px "Noto Serif SC", serif';
    ctx.fillStyle = rp.pvp ? '#f9a8d4' : '#bae6fd';
    ctx.shadowColor = '#000'; ctx.shadowBlur = 4;
    ctx.fillText(`${rp.name} Lv.${rp.level}`, pos.x, pos.y - 150);
    const w = 60, h = 5;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    ctx.fillRect(pos.x - w / 2, pos.y - 144, w, h);
    ctx.fillStyle = '#34d399';
    ctx.fillRect(pos.x - w / 2, pos.y - 144, w * Math.max(0, Math.min(1, (rp.hp || 0) / (rp.maxHp || 1))), h);
    ctx.restore();
  },

  _drawBossBar() {
    const bar = document.getElementById('worldBossBar');
    if (!bar || !window.NetMgr) return;
    let active = null;
    for (const id of Object.keys(NetMgr.bosses || {})) {
      const b = NetMgr.bosses[id];
      if (b && b.hp !== undefined && b.hp < b.maxHp) { active = { id, ...b }; break; }
    }
    if (active) {
      const z = CONFIG.world.bossZones.find(z => z.id === Number(active.id));
      bar.style.display = 'block';
      bar.innerHTML = `<span>${z ? z.name : 'Boss'} · 全服共享</span>` +
        `<div class="wbb-track"><div class="wbb-fill" style="width:${Math.max(0, active.hp / active.maxHp * 100)}%"></div></div>`;
    } else {
      bar.style.display = 'none';
    }
  },
};
