/* ==========================================================================
 *  天泪纪元 · 联机后端 (Deno Deploy 版)
 *  --------------------------------------------------------------------------
 *  与 server/node/server.js 功能一致，但使用 Deno 的 WebSocketPair，
 *  可直接部署到 Deno Deploy（与 GitHub 仓库原生集成，免费、支持 WSS）。
 *
 *  本地跑：   deno run --allow-net server.ts
 *  部署：     1) 推送到 GitHub；2) 在 dash.deno.com 新建项目，指向本文件
 *            入口设为 server/deno/server.ts
 *  环境变量： PORT（本地用，默认 8787）
 *
 *  安全：本文件不含任何密钥。若启用鉴权，请用环境变量注入。
 * ========================================================================== */

const PORT = Number(Deno.env.get('PORT') || 8787);
const TICK_MS = 100;
const MONSTER_RESPAWN_MS = 8000;
const MAP_W = 3600, MAP_H = 2000;

const REGIONS = [
  { id: 'gate', name: '学院大门', x: 0, y: 0, w: 1200, h: 2000 },
  { id: 'courtyard', name: '学院庭院', x: 1200, y: 0, w: 1200, h: 2000 },
  { id: 'library', name: '图书馆', x: 2400, y: 0, w: 1200, h: 1000 },
  { id: 'corridor', name: '地下走廊', x: 2400, y: 1000, w: 1200, h: 1000 },
];

const MONSTER_SPAWNS = [
  { type: 'floater', x: 300, y: 620, region: 'gate' },
  { type: 'floater', x: 520, y: 980, region: 'gate' },
  { type: 'golem', x: 760, y: 760, region: 'gate' },
  { type: 'floater', x: 980, y: 1200, region: 'gate' },
  { type: 'wraith', x: 200, y: 1400, region: 'gate' },
  { type: 'floater', x: 1400, y: 520, region: 'courtyard' },
  { type: 'golem', x: 1650, y: 900, region: 'courtyard' },
  { type: 'floater', x: 1900, y: 640, region: 'courtyard' },
  { type: 'wraith', x: 2100, y: 1150, region: 'courtyard' },
  { type: 'golem', x: 2300, y: 1500, region: 'courtyard' },
  { type: 'floater', x: 1500, y: 1650, region: 'courtyard' },
  { type: 'wraith', x: 1250, y: 1100, region: 'courtyard' },
  { type: 'wraith', x: 2600, y: 350, region: 'library' },
  { type: 'wraith', x: 2900, y: 620, region: 'library' },
  { type: 'golem', x: 3150, y: 300, region: 'library' },
  { type: 'floater', x: 3350, y: 700, region: 'library' },
  { type: 'wraith', x: 3050, y: 880, region: 'library' },
  { type: 'golem', x: 2600, y: 1200, region: 'corridor' },
  { type: 'floater', x: 2850, y: 1500, region: 'corridor' },
  { type: 'golem', x: 3150, y: 1250, region: 'corridor' },
  { type: 'wraith', x: 3400, y: 1600, region: 'corridor' },
  { type: 'floater', x: 3250, y: 1850, region: 'corridor' },
];

const MONSTER_TYPES: Record<string, any> = {
  floater: { name: '虚空浮游魔', hp: 30, attack: 8, speed: 60, aggro: 380, attackRange: 120, cd: 2000, xp: 20, gold: 15 },
  golem: { name: '符文傀儡', hp: 80, attack: 15, speed: 80, aggro: 340, attackRange: 80, cd: 2500, xp: 40, gold: 30 },
  wraith: { name: '书页游魂', hp: 45, attack: 10, speed: 50, aggro: 420, attackRange: 280, cd: 3000, xp: 30, gold: 20 },
};

const BOSS_ZONES: Record<number, any> = {
  1: { name: '虚空行者', x: 1200, y: 1000, r: 160, maxHp: 400 },
  2: { name: '熔雷巨像', x: 2200, y: 800, r: 160, maxHp: 700 },
  3: { name: '字祸魔典', x: 2900, y: 500, r: 160, maxHp: 900 },
  4: { name: '时之眼', x: 3100, y: 1500, r: 200, maxHp: 1500 },
};

/* ----------------------------- 状态 ----------------------------- */

interface Player {
  id: number; name: string; x: number; y: number; dir: number; state: string;
  hp: number; maxHp: number; level: number; scene: string; pvp: boolean; gold: number;
  lastSeen: number; lastAttack: number; socket: WebSocket;
}

let nextPlayerId = 1;
const players = new Map<number, Player>();

const monsters = MONSTER_SPAWNS.map((s, i) => {
  const def = MONSTER_TYPES[s.type];
  return {
    id: 'm' + i, type: s.type, homeX: s.x, homeY: s.y, x: s.x, y: s.y,
    hp: def.hp, maxHp: def.hp, alive: true, respawnAt: 0, attackAt: 0,
    wanderT: Math.random() * 6, wanderA: Math.random() * Math.PI * 2, region: s.region,
  };
});

const bosses: Record<number, any> = {};
for (const k of Object.keys(BOSS_ZONES)) {
  const id = Number(k);
  bosses[id] = { id, ...BOSS_ZONES[id], hp: BOSS_ZONES[id].maxHp, alive: true, fighters: new Set<number>(), respawnAt: 0 };
}

/* ----------------------------- 工具 ----------------------------- */

const dist = (ax: number, ay: number, bx: number, by: number) => Math.hypot(ax - bx, ay - by);
const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);

function playerSnapshot() {
  return [...players.values()].map(p => ({
    id: p.id, name: p.name, x: Math.round(p.x), y: Math.round(p.y), dir: p.dir,
    state: p.state, hp: p.hp, maxHp: p.maxHp, level: p.level, scene: p.scene, pvp: p.pvp,
  }));
}
function monsterSnapshot() {
  return monsters.filter(m => m.alive).map(m => ({ id: m.id, type: m.type, x: Math.round(m.x), y: Math.round(m.y), hp: m.hp, maxHp: m.maxHp }));
}
function bossSnapshot() {
  const out: any = {};
  for (const k of Object.keys(bosses)) {
    const b = bosses[Number(k)];
    out[b.id] = { hp: b.hp, maxHp: b.maxHp, alive: b.alive, fighters: b.fighters.size };
  }
  return out;
}

function send(id: number, obj: any) {
  const p = players.get(id);
  if (p) { try { p.socket.send(JSON.stringify(obj)); } catch (_) { /* ignore */ } }
}
function broadcast(obj: any) {
  const s = JSON.stringify(obj);
  for (const p of players.values()) { try { p.socket.send(s); } catch (_) { /* ignore */ } }
}

/* ----------------------------- 世界模拟 ----------------------------- */

setInterval(() => {
  const now = Date.now();
  for (const [id, p] of players) {
    if (now - p.lastSeen > 30000) { players.delete(id); broadcast({ t: 'playerLeave', id }); }
  }
  const list = [...players.values()];
  const dt = TICK_MS / 1000;

  for (const m of monsters) {
    if (!m.alive) { if (now >= m.respawnAt) { m.alive = true; m.hp = m.maxHp; m.x = m.homeX; m.y = m.homeY; } continue; }
    const def = MONSTER_TYPES[m.type];
    let target: Player | null = null, best = def.aggro;
    for (const p of list) { if (p.scene !== 'world') continue; const d = dist(p.x, p.y, m.x, m.y); if (d < best) { best = d; target = p; } }

    if (target) {
      if (best > def.attackRange) {
        m.x += (target.x - m.x) / best * def.speed * dt;
        m.y += (target.y - m.y) / best * def.speed * dt * 0.7;
      } else if (now - m.attackAt > def.cd) {
        m.attackAt = now;
        target.hp = Math.max(0, target.hp - def.attack);
        send(target.id, { t: 'hurt', by: m.id, dmg: def.attack, hp: target.hp });
      }
    } else {
      m.wanderT -= dt;
      if (m.wanderT <= 0) { m.wanderT = 2 + Math.random() * 4; m.wanderA = Math.random() * Math.PI * 2; }
      m.x += Math.cos(m.wanderA) * def.speed * 0.35 * dt;
      m.y += Math.sin(m.wanderA) * def.speed * 0.25 * dt;
      if (dist(m.x, m.y, m.homeX, m.homeY) > 260) {
        const d2 = dist(m.x, m.y, m.homeX, m.homeY);
        m.x += (m.homeX - m.x) / d2 * def.speed * dt;
        m.y += (m.homeY - m.y) / d2 * def.speed * dt;
      }
    }
    m.x = clamp(m.x, 40, MAP_W - 40); m.y = clamp(m.y, 40, MAP_H - 40);
  }

  for (const k of Object.keys(bosses)) {
    const b = bosses[Number(k)];
    if (!b.alive && now >= b.respawnAt) { b.alive = true; b.hp = b.maxHp; broadcast({ t: 'bossUpdate', bossId: b.id, hp: b.hp, maxHp: b.maxHp, alive: true, fighters: 0 }); }
    if (b.alive && b.fighters.size === 0 && b.hp < b.maxHp) b.hp = Math.min(b.maxHp, b.hp + b.maxHp * 0.02 * dt);
  }

  broadcast({ t: 'players', list: playerSnapshot() });
  broadcast({ t: 'monsters', list: monsterSnapshot() });
}, TICK_MS);

/* ----------------------------- 消息处理 ----------------------------- */

function handle(player: Player, msg: any) {
  player.lastSeen = Date.now();
  switch (msg.t) {
    case 'state':
      player.x = clamp(+msg.x || 0, 0, MAP_W);
      player.y = clamp(+msg.y || 0, 0, MAP_H);
      player.dir = msg.dir === -1 ? -1 : 1;
      player.state = String(msg.state || 'idle').slice(0, 12);
      player.hp = Math.max(0, Math.min(player.maxHp, +msg.hp || 0));
      player.maxHp = Math.max(1, +msg.maxHp || 100);
      player.level = Math.max(1, +msg.level || 1);
      player.scene = String(msg.scene || 'world').slice(0, 16);
      break;
    case 'chat': {
      const text = String(msg.text || '').slice(0, 120).trim();
      if (!text) return;
      broadcast({ t: 'chat', from: player.id, name: player.name, text, scope: msg.scope || 'world', at: Date.now() });
      break;
    }
    case 'hitEnemy': {
      const m = monsters.find(x => x.id === msg.id);
      if (!m || !m.alive) return;
      const dmg = clamp(+msg.dmg || 0, 0, 5000);
      m.hp -= dmg;
      broadcast({ t: 'dmg', kind: 'enemy', id: m.id, dmg: Math.round(dmg), by: player.id });
      if (m.hp <= 0) {
        m.alive = false; m.respawnAt = Date.now() + MONSTER_RESPAWN_MS;
        player.gold += MONSTER_TYPES[m.type].gold;
        broadcast({ t: 'monsterDead', id: m.id, by: player.id, name: player.name });
        broadcast({ t: 'worldMsg', text: `${player.name} 击败了 ${MONSTER_TYPES[m.type].name}`, kind: 'kill' });
      }
      break;
    }
    case 'bossEngage': {
      const b = bosses[msg.bossId]; if (!b || !b.alive) return;
      b.fighters.add(player.id);
      broadcast({ t: 'worldMsg', text: `${player.name} 进入了「${b.name}」锚点`, kind: 'boss' });
      broadcast({ t: 'bossUpdate', bossId: b.id, hp: b.hp, maxHp: b.maxHp, alive: b.alive, fighters: b.fighters.size });
      break;
    }
    case 'bossLeave': {
      const b = bosses[msg.bossId]; if (!b) return;
      b.fighters.delete(player.id);
      broadcast({ t: 'bossUpdate', bossId: b.id, hp: b.hp, maxHp: b.maxHp, alive: b.alive, fighters: b.fighters.size });
      break;
    }
    case 'hitBoss': {
      const b = bosses[msg.bossId]; if (!b || !b.alive) return;
      const dmg = clamp(+msg.dmg || 0, 0, 20000);
      b.hp -= dmg; b.fighters.add(player.id);
      broadcast({ t: 'dmg', kind: 'boss', id: b.id, dmg: Math.round(dmg), by: player.id });
      if (b.hp <= 0) {
        b.hp = 0; b.alive = false; b.respawnAt = Date.now() + 30000;
        broadcast({ t: 'bossDown', bossId: b.id, by: player.id, name: player.name });
        broadcast({ t: 'worldMsg', text: `【全服公告】${player.name} 击破了结界锚点 · ${b.name}！`, kind: 'boss' });
      }
      broadcast({ t: 'bossUpdate', bossId: b.id, hp: Math.max(0, b.hp), maxHp: b.maxHp, alive: b.alive, fighters: b.fighters.size });
      break;
    }
    case 'pvp': {
      const target = players.get(msg.targetId);
      if (!target || !player.pvp || !target.pvp) return;
      if (Date.now() - player.lastAttack < 250) return;
      player.lastAttack = Date.now();
      const dmg = clamp(+msg.dmg || 0, 0, 2000);
      target.hp = Math.max(0, target.hp - dmg);
      send(target.id, { t: 'pvpHit', from: player.id, name: player.name, dmg: Math.round(dmg), hp: target.hp });
      break;
    }
    case 'pvpToggle':
      player.pvp = !!msg.on;
      broadcast({ t: 'worldMsg', text: `${player.name} ${player.pvp ? '开启了' : '关闭了'} PVP`, kind: 'pvp' });
      break;
    case 'ping':
      send(player.id, { t: 'pong', at: msg.at });
      break;
  }
}

/* ----------------------------- HTTP / WS ----------------------------- */

Deno.serve({ port: PORT }, (req: Request) => {
  const url = new URL(req.url);

  if (url.pathname === '/health') {
    return Response.json({ ok: true, online: players.size, monsters: monsters.filter(m => m.alive).length });
  }

  if (url.pathname === '/ws') {
    const upgrade = req.headers.get('upgrade') || '';
    if (upgrade.toLowerCase() !== 'websocket') return new Response('expected websocket', { status: 426 });

    const { socket, response } = Deno.upgradeWebSocket(req);
    const id = nextPlayerId++;
    const name = url.searchParams.get('name') || ('旅人' + id);

    socket.onopen = () => {
      const player: Player = {
        id, name: name.slice(0, 16), x: 600, y: 900, dir: 1, state: 'idle',
        hp: 100, maxHp: 100, level: 1, scene: 'world', pvp: true, gold: 0,
        lastSeen: Date.now(), lastAttack: 0, socket,
      };
      players.set(id, player);
      send(id, {
        t: 'welcome', id, name: player.name, map: { w: MAP_W, h: MAP_H }, regions: REGIONS,
        players: playerSnapshot(), monsters: monsterSnapshot(), bosses: bossSnapshot(),
      });
      broadcast({ t: 'playerJoin', player: { id, name: player.name } });
    };
    socket.onmessage = (e) => {
      const p = players.get(id);
      if (!p) return;
      try { handle(p, JSON.parse(e.data)); } catch (_) { /* ignore */ }
    };
    socket.onclose = () => { if (players.delete(id)) broadcast({ t: 'playerLeave', id }); };
    socket.onerror = () => { if (players.delete(id)) broadcast({ t: 'playerLeave', id }); };
    return response;
  }

  return new Response('天泪纪元 · 联机后端运行中\n', { headers: { 'content-type': 'text/plain; charset=utf-8' } });
});

console.log(`[天泪纪元·联机后端/Deno] listening on :${PORT}`);
