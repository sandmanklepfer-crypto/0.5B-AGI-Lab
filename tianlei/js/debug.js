/* ==========================================================
   调试命令通道 DebugConsole
   ----------------------------------------------------------
   极简但够用的"命令行"：外部（沙箱里的 tools/tldbg.js）通过
   MQTT 主题   zhz/tianlei/v1/<频道>/debug   发命令，
   本文件执行后把结果发到
              zhz/tianlei/v1/<频道>/debug/result
   完全不在画面上显示任何东西（除你自己用 overlay on 打开）。

   命令一览：见 help
   ========================================================== */

const DebugConsole = {
  god: false,

  handle(cmd) {
    cmd = String(cmd || '').trim();
    if (!cmd) return;
    const parts = cmd.split(/\s+/);
    const c = parts[0].toLowerCase();
    const a = parts.slice(1);

    try {
      switch (c) {
        case 'help': return this.reply(
          '命令: state | ping | who | tp <x> <y> | boss <1-4> | spawn <type> [n] | ' +
          'killall | walk <dir> [sec] | hp <n> | mp <n> | level <n> | ' +
          'gold <n> | overlay on|off | god on|off | pvp on|off | chat <text> | hide | show');

        case 'ping':
          return this.reply('pong', { room: NetMgr.room, name: NetMgr.name, at: Date.now() });

        case 'state': {
          const r = CONFIG.world.regions.find(rg => Player.x >= rg.x && Player.x < rg.x + rg.w && Player.y >= rg.y && Player.y < rg.y + rg.h);
          return this.reply('state', {
            me: { id: NetMgr.myId, name: NetMgr.name, x: Math.round(Player.x), y: Math.round(Player.y), hp: Math.round(Player.hp) + '/' + Player.maxHp, mp: Math.round(Player.mp) + '/' + Player.maxMp, level: GameState.player.level, gold: GameState.player.gold, region: r ? r.name : '未知', state: Player.state },
            net: { connected: NetMgr.connected, host: NetMgr.isHost, hostId: NetMgr.hostId, peers: NetMgr.remotePlayers.size, latency: NetMgr.latency, room: NetMgr.room },
            world: { enemies: WorldMgr.enemies.length, sim: (window.WorldSim ? WorldSim.monsters.filter(m => m.alive).length : 0), size: CONFIG.world.width + 'x' + CONFIG.world.height },
            scene: GameState.currentScene,
            defeated: GameState.player.defeatedBosses,
            god: this.god,
          });
        }

        case 'who': {
          const list = [{ id: NetMgr.myId, name: NetMgr.name, me: true }];
          for (const [id, p] of NetMgr.remotePlayers) list.push({ id, name: p.name, x: Math.round(p.x), y: Math.round(p.y), hp: p.hp + '/' + p.maxHp, lv: p.level, pvp: p.pvp });
          return this.reply(`${list.length} 人在线`, list);
        }

        case 'tp': {
          const x = Number(a[0]), y = Number(a[1]);
          if (!isFinite(x) || !isFinite(y)) return this.reply('tp 用法: tp <x> <y>', null, false, false);
          Player.x = x; Player.y = y;
          if (WorldMgr.running) { WorldMgr.cam.x = x; WorldMgr.cam.y = y; }
          return this.reply(`已传送到 ${x},${y}`);
        }

        case 'boss': {
          const id = parseInt(a[0], 10);
          const z = CONFIG.world.bossZones.find(z => z.id === id);
          if (!z) return this.reply('boss 用法: boss <1-4>', null, false, false);
          Player.x = z.x; Player.y = z.y;
          this.reply(`已到达锚点 ${z.name}，触发战斗`);
          if (WorldMgr.running) WorldMgr.triggerBoss(id);
          return;
        }

        case 'spawn': {
          const type = a[0] || 'floater';
          const n = Math.max(1, Math.min(20, parseInt(a[1] || '1', 10)));
          if (!EnemySys.types[type]) return this.reply('spawn 用法: spawn <floater|golem|wraith> [n]', null, false, false);
          if (!window.WorldSim) return this.reply('世界未就绪', null, false, false);
          for (let i = 0; i < n; i++) {
            const def = EnemySys.types[type];
            const ang = Math.random() * Math.PI * 2, d = 120 + Math.random() * 160;
            WorldSim.monsters.push({
              id: 'x' + Date.now() + '_' + i, type,
              homeX: Player.x + Math.cos(ang) * d, homeY: Player.y + Math.sin(ang) * d,
              x: Player.x + Math.cos(ang) * d, y: Player.y + Math.sin(ang) * d,
              hp: def.hp, maxHp: def.hp, alive: true, respawnAt: 0, attackAt: 0, wanderT: 2, wanderA: ang,
            });
          }
          return this.reply(`已在附近生成 ${n} 只 ${type}`);
        }

        case 'killall': {
          if (!window.WorldSim) return this.reply('世界未就绪', null, false, false);
          let k = 0;
          for (const m of WorldSim.monsters) if (m.alive && Math.hypot(m.x - Player.x, m.y - Player.y) < 1200) { m.alive = false; m.hp = 0; k++; }
          return this.reply(`清除了附近 ${k} 只怪`);
        }

        case 'walk': {
          const dir = (a[0] || 'd').toLowerCase();
          const sec = Math.min(5, Number(a[1] || 1));
          const v = { d: [1, 0], a: [-1, 0], w: [0, -1], s: [0, 1] }[dir] || [1, 0];
          const t0 = performance.now();
          const step = () => {
            const dt = Math.min(0.05, (performance.now() - t0) / 1000);
            Player.x += v[0] * 300 * 0.02; Player.y += v[1] * 300 * 0.02;
            if (performance.now() - t0 < sec * 1000) requestAnimationFrame(step);
          };
          step();
          return this.reply(`向 ${dir} 走 ${sec}s`);
        }

        case 'hp': { Player.hp = Math.max(0, Math.min(Player.maxHp, Number(a[0]))); return this.reply('HP=' + Player.hp); }
        case 'mp': { Player.mp = Math.max(0, Math.min(Player.maxMp, Number(a[0]))); return this.reply('MP=' + Player.mp); }
        case 'level': { GameState.player.level = Math.max(1, parseInt(a[0], 10) || 1); GameState.save(); return this.reply('Lv=' + GameState.player.level); }
        case 'gold': { GameState.player.gold = Math.max(0, parseInt(a[0], 10) || 0); GameState.save(); return this.reply('金币=' + GameState.player.gold); }

        case 'overlay': {
          window.__TL_DEBUG = (a[0] !== 'off');
          return this.reply('overlay ' + (window.__TL_DEBUG ? 'on' : 'off'));
        }
        case 'god': { this.god = (a[0] !== 'off'); Player.invincible = this.god; return this.reply('god ' + (this.god ? 'on' : 'off')); }
        case 'pvp': {
          const on = (a[0] !== 'off');
          if (WorldMgr) WorldMgr.pvpOn = on;
          if (NetMgr.connected) NetMgr.setPvp(on);
          return this.reply('pvp ' + (on ? 'on' : 'off'));
        }
        case 'chat': case 'say': {
          const text = a.join(' ');
          if (!NetMgr.connected) return this.reply('未联网');
          NetMgr.chat(text, 'world');
          return this.reply('已发送: ' + text);
        }
        case 'hide': { const s = document.getElementById('worldScene'); if (s) s.classList.add('hidden'); return this.reply('world 隐藏'); }
        case 'show': { const s = document.getElementById('worldScene'); if (s) s.classList.remove('hidden'); return this.reply('world 显示'); }

        default:
          return this.reply('未知命令: ' + c + '（用 help 查看）', null, false, false);
      }
    } catch (e) {
      return this.reply('执行出错: ' + (e && e.message), null, false, false);
    }
  },

  reply(text, data, ok, rtt) {
    if (window.NetMgr && NetMgr.mq && NetMgr.connected) {
      NetMgr.mq.publish(NetMgr._base() + 'debug/result', JSON.stringify({
        ok: ok !== false, text: text || '', data: data || null, noRtt: rtt === false, at: Date.now(),
      }));
    }
  },
};
