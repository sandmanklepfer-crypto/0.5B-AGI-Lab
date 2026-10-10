/* ==========================================================
   核心系统：工具函数、输入、音频、存档、粒子、游戏状态
   ========================================================== */

// ---------- 工具函数 ----------
const Utils = {
  // NaN 安全：任何残缺/越界输入都不会产生 NaN 坐标（NaN 会传染导致"角色卡死"）
  clamp(v, min, max) {
    if (!isFinite(v)) v = isFinite(min) ? min : 0;
    if (!isFinite(min)) min = -1e6;
    if (!isFinite(max)) max = 1e6;
    return Math.max(min, Math.min(max, v));
  },
  safeNum(v, fallback) { return (typeof v === 'number' && isFinite(v)) ? v : fallback; },
  lerp(a, b, t) { return a + (b - a) * t; },
  dist(x1, y1, x2, y2) { return Math.hypot(x2 - x1, y2 - y1); },
  rand(min, max) { return min + Math.random() * (max - min); },
  randInt(min, max) { return Math.floor(min + Math.random() * (max - min + 1)); },
  angleBetween(x1, y1, x2, y2) { return Math.atan2(y2 - y1, x2 - x1); },
  
  // 圆形碰撞
  circleCollide(x1, y1, r1, x2, y2, r2) {
    return Math.hypot(x2 - x1, y2 - y1) < r1 + r2;
  },
  
  // 扇形碰撞
  fanCollide(cx, cy, radius, angle, spread, tx, ty) {
    const d = Math.hypot(tx - cx, ty - cy);
    if (d > radius) return false;
    const a = Math.atan2(ty - cy, tx - cx);
    let diff = a - angle;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    return Math.abs(diff) < spread / 2;
  },
};

// ---------- 游戏状态 ----------
const GameState = {
  currentScene: 'opening', // opening, menu, story, hub, battle, victory, gameover, ending
  settings: {
    music: true,
    sfx: true,
    vibration: true,
    joystickSize: 90,
  },
  
  // 玩家数据
  player: {
    level: 1,
    exp: 0,
    gold: 0,
    star: 0,
    maxHp: 100,
    maxMp: 50,
    hp: 100,
    mp: 50,
    attack: 12,
    defense: 3,
    speed: 220,
    skillLevels: { 1: 1, 2: 1, 3: 1, ult: 1, attack: 1, dodge: 1 },
    relics: [], // 拥有的遗物id
    equippedRelics: [], // 装备的遗物id (最多3个)
    unlockedBosses: [1], // 已解锁的Boss
    defeatedBosses: [], // 已击败的Boss
    quests: JSON.parse(JSON.stringify(CONFIG.initialQuests)),
  },
  
  // 战斗状态
  battle: {
    currentBossId: 1,
    paused: false,
    combo: 0,
    comboTimer: 0,
  },
  
  // 存档
  save() {
    try {
      const data = {
        settings: this.settings,
        player: this.player,
      };
      localStorage.setItem('tianlei_save', JSON.stringify(data));
      return true;
    } catch (e) {
      console.warn('保存失败:', e);
      return false;
    }
  },
  
  load() {
    try {
      const raw = localStorage.getItem('tianlei_save');
      if (!raw) return false;
      const data = JSON.parse(raw);
      if (data.settings) Object.assign(this.settings, data.settings);
      if (data.player) {
        Object.assign(this.player, data.player);
        // 确保技能等级都有
        if (!this.player.skillLevels) {
          this.player.skillLevels = { 1: 1, 2: 1, 3: 1, ult: 1, attack: 1, dodge: 1 };
        }
        if (!this.player.relics) this.player.relics = [];
        if (!this.player.equippedRelics) this.player.equippedRelics = [];
        if (!this.player.unlockedBosses) this.player.unlockedBosses = [1];
        if (!this.player.defeatedBosses) this.player.defeatedBosses = [];
        if (!this.player.quests) this.player.quests = JSON.parse(JSON.stringify(CONFIG.initialQuests));
      }
      return true;
    } catch (e) {
      console.warn('读取存档失败:', e);
      return false;
    }
  },
  
  hasSave() {
    try {
      return !!localStorage.getItem('tianlei_save');
    } catch { return false; }
  },
  
  resetPlayer() {
    this.player.level = 1;
    this.player.exp = 0;
    this.player.gold = 0;
    this.player.star = 0;
    this.player.maxHp = CONFIG.playerBase.maxHp;
    this.player.maxMp = CONFIG.playerBase.maxMp;
    this.player.hp = this.player.maxHp;
    this.player.mp = this.player.maxMp;
    this.player.attack = CONFIG.playerBase.attack;
    this.player.defense = CONFIG.playerBase.defense;
    this.player.speed = CONFIG.playerBase.speed;
    this.player.skillLevels = { 1: 1, 2: 1, 3: 1, ult: 1, attack: 1, dodge: 1 };
    this.player.relics = [];
    this.player.equippedRelics = [];
    this.player.unlockedBosses = [1];
    this.player.defeatedBosses = [];
    this.player.quests = JSON.parse(JSON.stringify(CONFIG.initialQuests));
  },
  
  // 获取升级所需经验
  getExpToNextLevel() {
    const lv = this.player.level;
    if (lv >= CONFIG.expPerLevel.length) return 99999;
    return CONFIG.expPerLevel[lv];
  },
  
  // 添加经验
  addExp(amount) {
    this.player.exp += amount;
    let leveledUp = false;
    while (this.player.exp >= this.getExpToNextLevel() && this.player.level < CONFIG.expPerLevel.length) {
      this.player.exp -= this.getExpToNextLevel();
      this.player.level++;
      // 属性提升
      this.player.maxHp += 15;
      this.player.maxMp += 5;
      this.player.attack += 2;
      this.player.defense += 1;
      this.player.hp = this.player.maxHp;
      this.player.mp = this.player.maxMp;
      leveledUp = true;
    }
    return leveledUp;
  },
  
  // 获取遗物效果叠加
  getRelicEffect(key) {
    let value = null;
    for (const id of this.player.equippedRelics) {
      const relic = CONFIG.relics.find(r => r.id === id);
      if (relic && relic.effect[key] !== undefined) {
        if (value === null) value = relic.effect[key];
        else if (typeof value === 'number') value += relic.effect[key];
        else if (typeof value === 'boolean') value = value || relic.effect[key];
      }
    }
    return value;
  },
};

// ---------- 音频系统 ----------
const AudioMgr = {
  bgmMain: null,
  bgmBoss: null,
  currentBgm: null,
  volume: 0.5,
  
  init() {
    this.bgmMain = document.getElementById('bgmMain');
    this.bgmBoss = document.getElementById('bgmBoss');
    if (this.bgmMain) this.bgmMain.volume = this.volume;
    if (this.bgmBoss) this.bgmBoss.volume = this.volume;
  },
  
  playBgm(type) {
    if (!GameState.settings.music) return;
    if (type === this.currentBgm) return;
    
    // 淡出现有
    this.fadeOut(this.currentBgm === 'main' ? this.bgmMain : this.bgmBoss, 0.8);
    
    // 淡入新的
    const target = type === 'main' ? this.bgmMain : this.bgmBoss;
    if (target) {
      target.volume = 0;
      target.play().catch(() => {});
      this.fadeIn(target, 0.8);
    }
    this.currentBgm = type;
  },
  
  stopBgm() {
    this.fadeOut(this.bgmMain, 0.5);
    this.fadeOut(this.bgmBoss, 0.5);
    this.currentBgm = null;
  },
  
  fadeIn(audio, duration) {
    if (!audio) return;
    const startVol = audio.volume;
    const targetVol = this.volume;
    const startTime = performance.now();
    const step = () => {
      const t = (performance.now() - startTime) / (duration * 1000);
      if (t >= 1) { audio.volume = targetVol; return; }
      audio.volume = startVol + (targetVol - startVol) * t;
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  },
  
  fadeOut(audio, duration) {
    if (!audio || audio.paused) return;
    const startVol = audio.volume;
    const startTime = performance.now();
    const step = () => {
      const t = (performance.now() - startTime) / (duration * 1000);
      if (t >= 1) {
        audio.volume = 0;
        audio.pause();
        return;
      }
      audio.volume = startVol * (1 - t);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  },
  
  // 使用Web Audio简单合成音效
  sfxContext: null,
  
  playSfx(type) {
    if (!GameState.settings.sfx) return;
    try {
      if (!this.sfxContext) {
        this.sfxContext = new (window.AudioContext || window.webkitAudioContext)();
      }
      const ctx = this.sfxContext;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      
      switch(type) {
        case 'hit':
          osc.type = 'square';
          osc.frequency.setValueAtTime(200, now);
          osc.frequency.exponentialRampToValueAtTime(80, now + 0.1);
          gain.gain.setValueAtTime(0.15, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
          osc.start(now); osc.stop(now + 0.1);
          break;
        case 'skill':
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(400, now);
          osc.frequency.exponentialRampToValueAtTime(800, now + 0.15);
          gain.gain.setValueAtTime(0.1, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
          osc.start(now); osc.stop(now + 0.15);
          break;
        case 'dash':
          osc.type = 'sine';
          osc.frequency.setValueAtTime(600, now);
          osc.frequency.exponentialRampToValueAtTime(1200, now + 0.1);
          gain.gain.setValueAtTime(0.08, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
          osc.start(now); osc.stop(now + 0.1);
          break;
        case 'hurt':
          osc.type = 'triangle';
          osc.frequency.setValueAtTime(150, now);
          osc.frequency.exponentialRampToValueAtTime(50, now + 0.2);
          gain.gain.setValueAtTime(0.2, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
          osc.start(now); osc.stop(now + 0.2);
          break;
        case 'levelup':
          osc.type = 'sine';
          osc.frequency.setValueAtTime(400, now);
          osc.frequency.setValueAtTime(600, now + 0.1);
          osc.frequency.setValueAtTime(800, now + 0.2);
          gain.gain.setValueAtTime(0.15, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
          osc.start(now); osc.stop(now + 0.4);
          break;
        case 'victory':
          osc.type = 'sine';
          osc.frequency.setValueAtTime(523, now);
          osc.frequency.setValueAtTime(659, now + 0.15);
          osc.frequency.setValueAtTime(784, now + 0.3);
          osc.frequency.setValueAtTime(1047, now + 0.45);
          gain.gain.setValueAtTime(0.15, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
          osc.start(now); osc.stop(now + 0.8);
          break;
        case 'click':
          osc.type = 'sine';
          osc.frequency.setValueAtTime(800, now);
          gain.gain.setValueAtTime(0.08, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
          osc.start(now); osc.stop(now + 0.05);
          break;
      }
    } catch (e) {
      // 静默失败
    }
  },
  
  resume() {
    if (this.sfxContext && this.sfxContext.state === 'suspended') {
      this.sfxContext.resume();
    }
  },
};

// ---------- 输入系统 ----------
const InputMgr = {
  // 键盘
  keys: {},
  
  // 摇杆
  joystick: {
    active: false,
    x: 0, // -1 ~ 1
    y: 0,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    pointerId: null,
  },
  
  // 技能按钮按下状态
  skillPressed: { 1: false, 2: false, 3: false, ult: false, attack: false, dodge: false },
  skillHeld: {}, // 按住的技能（用于显示范围指示）
  
  init() {
    // 键盘
    window.addEventListener('keydown', (e) => {
      this.keys[e.key.toLowerCase()] = true;
      // WASD 移动
      const key = e.key.toLowerCase();
      if (['a', 'd', 'w', 's'].includes(key)) {
        this.updateJoystickFromKeys();
      }
      // 技能键
      if (key === 'j') this.triggerSkill('attack');
      if (key === 'k') this.triggerSkill(2);
      if (key === 'l') this.triggerSkill(3);
      if (key === 'u') this.triggerSkill(1);
      if (key === 'i') this.triggerSkill('ult');
      if (key === 'o') this.triggerSkill('dodge');
    });
    
    window.addEventListener('keyup', (e) => {
      this.keys[e.key.toLowerCase()] = false;
      const key = e.key.toLowerCase();
      if (['a', 'd', 'w', 's'].includes(key)) {
        this.updateJoystickFromKeys();
      }
    });
    
    // 摇杆触控
    this.initJoystick();
    
    // 技能按钮
    this.initSkillButtons();
  },
  
  updateJoystickFromKeys() {
    let dx = 0, dy = 0;
    if (this.keys['a']) dx -= 1;
    if (this.keys['d']) dx += 1;
    if (this.keys['w']) dy -= 1;
    if (this.keys['s']) dy += 1;
    
    if (dx !== 0 || dy !== 0) {
      const len = Math.hypot(dx, dy);
      this.joystick.x = dx / len;
      this.joystick.y = dy / len;
      this.joystick.active = true;
    } else {
      this.joystick.x = 0;
      this.joystick.y = 0;
      this.joystick.active = false;
    }
  },
  
  initJoystick() {
    const container = document.getElementById('joystickContainer');
    const base = document.getElementById('joystickBase');
    const stick = document.getElementById('joystickStick');
    if (!container) return;
    
    // 辅助：根据当前是否强制旋转，获取容器在"逻辑坐标"中的中心位置
    // 强制旋转模式下，rect给出的是屏幕外接矩形，需要换算回容器逻辑坐标
    const getCenter = (e) => {
      const rect = container.getBoundingClientRect();
      // 容器DOM本身的逻辑宽高（CSS声明值，不受旋转影响）
      const cw = container.offsetWidth;
      const ch = container.offsetHeight;

      if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
        // 强制旋转模式：屏幕rect的宽高是反向的
        // 容器逻辑中心 (cx_logical, cy_logical) = (cw/2, ch/2)
        // 映射到屏幕坐标：
        //   sx = 容器宽(屏幕方向下的容器高=ch) - cy_logical
        //   sy = cx_logical
        // 但我们需要的是反过来——把屏幕rect映射到逻辑中心
        // 更简单：直接用 offsetLeft/offsetTop + 自身中心 在容器坐标系里
        // 由于摇杆容器在 #gameContainer 内，且 gameContainer 被旋转了，
        // 实际触摸与摇杆的相对关系会随旋转而变。
        // 解决：把触摸点 clientX/Y 转成容器内逻辑坐标，再与摇杆逻辑中心比较。
        const p = FullscreenMgr.screenToContainer(
          rect.left + rect.width / 2,
          rect.top + rect.height / 2
        );
        // 注意：p 是屏幕中心在容器坐标系里的坐标，但摇杆"中心"本身也在容器坐标系里。
        // 摇杆在容器内通过 bottom/left 定位，其逻辑中心坐标为 (left + cw/2, container_h - bottom - ch/2)
        // 更直接的做法——用 clientX/Y 的触摸点算出摇杆逻辑坐标。
        // 但摇杆的 UI 位置是 CSS 定位的，在强制旋转模式下视觉位置也被旋转了。
        // 正确做法：摇杆UI在旋转后的视觉位置 = 屏幕上看到的位置。
        // 用户触摸的就是屏幕上的摇杆，所以 dx/dy 直接用屏幕坐标差是对的！
        // 但摇杆的方向值 (x, y) 需要反向换算到游戏逻辑坐标。
        return { cx: rect.left + rect.width / 2, cy: rect.top + rect.height / 2 };
      } else {
        return { cx: rect.left + rect.width / 2, cy: rect.top + rect.height / 2 };
      }
    };

    const handleStart = (e) => {
      e.preventDefault();
      const { cx, cy } = getCenter(e);
      this.joystick.active = true;
      this.joystick.pointerId = e.pointerId;
      this.joystick.startX = cx;
      this.joystick.startY = cy;
      handleMove(e);
    };
    
    const handleMove = (e) => {
      // 注意：battle 摇杆用的是自己的容器(joystickContainer)，与世界摇杆(worldJoystick)互不干扰，
      // 不要按场景 return，否则 pointerup 收不到会"摇杆卡死"。
      if (!this.joystick.active || e.pointerId !== this.joystick.pointerId) return;
      e.preventDefault();
      const { cx, cy } = getCenter(e);
      let dx = e.clientX - cx;
      let dy = e.clientY - cy;

      // 强制旋转模式下：摇杆偏移方向要映射回游戏逻辑方向
      // 屏幕向右(dx>0) = 游戏向下(cy>0, 逻辑y+)
      // 屏幕向下(dy>0) = 游戏向左(逻辑x-)
      if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
        const oldDx = dx, oldDy = dy;
        dx = oldDy;     // 屏幕Y方向 → 游戏X方向
        dy = -oldDx;    // 屏幕X正向 → 游戏Y负向
      }

      const maxDist = 45;
      const dist = Math.hypot(dx, dy);
      
      if (dist > maxDist) {
        const ratio = maxDist / dist;
        this.joystick.currentX = dx * ratio;
        this.joystick.currentY = dy * ratio;
      } else {
        this.joystick.currentX = dx;
        this.joystick.currentY = dy;
      }
      
      this.joystick.x = Utils.clamp(dx / maxDist, -1, 1);
      this.joystick.y = Utils.clamp(dy / maxDist, -1, 1);
      
      // 限制长度为1
      const jlen = Math.hypot(this.joystick.x, this.joystick.y);
      if (jlen > 1) {
        this.joystick.x /= jlen;
        this.joystick.y /= jlen;
      }
      
      // 摇杆视觉位移：在强制旋转模式下视觉偏移也需要反向计算回屏幕方向
      let visX = this.joystick.currentX;
      let visY = this.joystick.currentY;
      if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
        // 游戏逻辑偏移 → 屏幕偏移（反向换算）
        const ox = visX, oy = visY;
        visX = -oy;   // 游戏Y负 = 屏幕X正
        visY = ox;    // 游戏X正 = 屏幕Y正
      }
      stick.style.transform = `translate(calc(-50% + ${visX}px), calc(-50% + ${visY}px))`;
    };
    
    const handleEnd = (e) => {
      // 无条件复位：只要指针抬起就清掉摇杆，避免残留方向把角色"顶住"
      if (this.joystick.pointerId !== null && e.pointerId !== this.joystick.pointerId) return;
      this.joystick.active = false;
      this.joystick.x = 0;
      this.joystick.y = 0;
      this.joystick.currentX = 0;
      this.joystick.currentY = 0;
      this.joystick.pointerId = null;
      stick.style.transform = 'translate(-50%, -50%)';
    };
    
    container.addEventListener('pointerdown', handleStart);
    window.addEventListener('pointermove', handleMove);
    window.addEventListener('pointerup', handleEnd);
    window.addEventListener('pointercancel', handleEnd);
  },
  
  initSkillButtons() {
    const buttons = document.querySelectorAll('.skill-btn');
    buttons.forEach(btn => {
      const skill = btn.dataset.skill;
      
      const handleDown = (e) => {
        e.preventDefault();
        e.stopPropagation();
        AudioMgr.resume();
        // 立即触发技能
        this.triggerSkill(skill);
        
        this.skillHeld[skill] = true;
        // 对于需要方向指示的技能，显示指示器
        if ((skill === '2' || skill === '3') && typeof BattleSys !== 'undefined' && BattleSys.showSkillIndicator) {
          BattleSys.showSkillIndicator(skill);
        }
      };
      
      const handleUp = (e) => {
        e.preventDefault();
        this.skillHeld[skill] = false;
        if (typeof BattleSys !== 'undefined' && BattleSys.hideSkillIndicator) {
          BattleSys.hideSkillIndicator();
        }
      };
      
      btn.addEventListener('pointerdown', handleDown);
      btn.addEventListener('pointerup', handleUp);
      btn.addEventListener('pointercancel', handleUp);
      btn.addEventListener('pointerleave', handleUp);
    });
  },
  
  triggerSkill(skill) {
    this.skillPressed[skill] = true;
  },
  
  // 消费一次按键事件
  consumeSkill(skill) {
    if (this.skillPressed[skill]) {
      this.skillPressed[skill] = false;
      return true;
    }
    return false;
  },
  
  resetSkillPresses() {
    this.skillPressed = { 1: false, 2: false, 3: false, ult: false, attack: false, dodge: false };
  },
};

// ---------- 粒子系统 ----------
class Particle {
  constructor(x, y, opts = {}) {
    this.x = x;
    this.y = y;
    this.vx = opts.vx || Utils.rand(-50, 50);
    this.vy = opts.vy || Utils.rand(-50, 50);
    this.life = opts.life || 1;
    this.maxLife = this.life;
    this.size = opts.size || 4;
    this.color = opts.color || '#a855f7';
    this.gravity = opts.gravity || 0;
    this.shrink = opts.shrink !== false;
    this.glow = opts.glow !== false;
  }
  
  update(dt) {
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.vy += this.gravity * dt;
    this.life -= dt;
    return this.life > 0;
  }
  
  draw(ctx) {
    const alpha = this.life / this.maxLife;
    const size = this.shrink ? this.size * alpha : this.size;
    ctx.save();
    ctx.globalAlpha = alpha;
    if (this.glow) {
      ctx.shadowColor = this.color;
      ctx.shadowBlur = 10;
    }
    ctx.fillStyle = this.color;
    ctx.beginPath();
    ctx.arc(this.x, this.y, size, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

const ParticleSys = {
  particles: [],
  
  emit(x, y, count, opts = {}) {
    // 【问题1.6】同屏粒子上限 220，超出丢弃最旧的，防止长时间战斗内存累积
    const MAX = 220;
    for (let i = 0; i < count; i++) {
      this.particles.push(new Particle(x, y, {
        vx: opts.vx !== undefined ? opts.vx : Utils.rand(-100, 100),
        vy: opts.vy !== undefined ? opts.vy : Utils.rand(-100, 100),
        life: opts.life || Utils.rand(0.3, 0.8),
        size: opts.size || Utils.rand(2, 6),
        color: opts.color || '#a855f7',
        gravity: opts.gravity || 0,
        glow: opts.glow !== false,
      }));
    }
    if (this.particles.length > MAX) {
      this.particles.splice(0, this.particles.length - MAX);
    }
  },
  
  // 定向喷射
  burst(x, y, angle, spread, count, opts = {}) {
    const MAX = 220;
    for (let i = 0; i < count; i++) {
      const a = angle + Utils.rand(-spread / 2, spread / 2);
      const speed = opts.speed || Utils.rand(80, 200);
      this.particles.push(new Particle(x, y, {
        vx: Math.cos(a) * speed,
        vy: Math.sin(a) * speed,
        life: opts.life || Utils.rand(0.3, 0.7),
        size: opts.size || Utils.rand(2, 5),
        color: opts.color || '#a855f7',
        gravity: opts.gravity || 0,
      }));
    }
    if (this.particles.length > MAX) {
      this.particles.splice(0, this.particles.length - MAX);
    }
  },
  
  update(dt) {
    this.particles = this.particles.filter(p => p.update(dt));
  },
  
  draw(ctx) {
    for (const p of this.particles) p.draw(ctx);
  },
  
  clear() { this.particles = []; },
};

// ---------- 伤害飘字 ----------
const DamageNumberSys = {
  show(x, y, value, type = 'normal') {
    const container = document.getElementById('damageNumbers');
    if (!container) return;

    // 【问题一】正确的坐标换算：游戏逻辑坐标(1280x720设计基准) → DOM容器像素
    // BattleSys.scale = 容器高度 / 720；canvas 按 scale 等比缩放，上下无黑边
    const s = (window.BattleSys && BattleSys.scale) ? BattleSys.scale : 1;
    // 水平方向：逻辑x * scale = 容器内像素x（canvas从左到右铺满）
    const px = x * s;
    // 垂直方向：逻辑y * scale = 容器内像素y
    const py = y * s;

    const el = document.createElement('div');
    el.className = `dmg-number ${type}`;
    el.textContent = value;

    // 以左下角为基准，居中对齐飘字（用 transform 做水平居中，避免 left 偏移半个字宽）
    el.style.left = `${px}px`;
    el.style.top = `${py}px`;
    el.style.transform = 'translateX(-50%)';

    container.appendChild(el);
    setTimeout(() => el.remove(), 1100);
  },
};

// ---------- 屏幕震动 ----------
const ScreenShake = {
  intensity: 0,
  duration: 0,
  time: 0,
  
  shake(intensity, duration) {
    if (!GameState.settings.vibration) return;
    this.intensity = Math.max(this.intensity, intensity);
    this.duration = Math.max(this.duration, duration);
    this.time = 0;
  },
  
  update(dt) {
    if (this.duration <= 0) return { x: 0, y: 0 };
    this.time += dt;
    if (this.time >= this.duration) {
      this.duration = 0;
      this.intensity = 0;
      return { x: 0, y: 0 };
    }
    const t = 1 - this.time / this.duration;
    return {
      x: Utils.rand(-1, 1) * this.intensity * t,
      y: Utils.rand(-1, 1) * this.intensity * t,
    };
  },
};

// ---------- 全局错误兜底（看门狗） ----------
// 【问题1.4】捕获所有未处理错误，记录日志但不让页面崩溃
// 若游戏循环 running=true 但 animFrame 已停，自动重启循环
(function installGlobalErrorGuard() {
  function report(type, detail) {
    try {
      console.warn('[GlobalGuard] ' + type + ':', detail);
    } catch (e) { /* noop */ }
  }

  window.addEventListener('error', (e) => {
    report('error', e.message || e.error);
    // 阻止默认行为（避免部分WebView直接弹出错误对话框卡死）
    e.preventDefault && e.preventDefault();
  }, true);

  window.addEventListener('unhandledrejection', (e) => {
    report('unhandledrejection', e.reason && e.reason.message ? e.reason.message : e.reason);
    e.preventDefault && e.preventDefault();
  });

  // 看门狗：每 2s 检查主循环是否活着，若 running 但无动画帧则重启
  let _lastHubFrame = -1;
  let _lastBattleFrame = -1;
  setInterval(() => {
    try {
      // Hub 场景看门狗
      if (window.HubMgr && HubMgr.running) {
        if (HubMgr.animFrame === _lastHubFrame) {
          console.warn('[GlobalGuard] Hub loop appears stuck, restarting...');
          HubMgr.lastTime = performance.now();
          HubMgr.gameLoop();
        }
        _lastHubFrame = HubMgr.animFrame;
      }
      // Battle 场景看门狗
      if (window.BattleSys && BattleSys.running) {
        if (BattleSys.animFrame === _lastBattleFrame) {
          console.warn('[GlobalGuard] Battle loop appears stuck, restarting...');
          BattleSys.lastTime = performance.now();
          BattleSys.gameLoop();
        }
        _lastBattleFrame = BattleSys.animFrame;
      }
    } catch (e) {
      // 看门狗自身不能抛错
    }
  }, 2000);
})();
