/* ==========================================================
   场景管理：开场、主菜单、剧情、Hub中枢、胜利、失败、结局
   ========================================================== */

const SceneMgr = {
  scenes: {},
  current: null,
  
  init() {
    // 缓存场景元素
    const ids = ['openingScene', 'menuScene', 'storyScene', 'hubScene', 'worldScene',
                 'battleScene', 'victoryScene', 'gameOverScene', 'endingScene'];
    for (const id of ids) {
      this.scenes[id] = document.getElementById(id);
    }
    
    // 绑定按钮事件
    this.bindEvents();
    
    // 开场符文粒子
    this.initOpeningParticles();
  },
  
  show(name) {
    // 【问题4】切换场景前，停止上一个场景的游戏循环，避免多循环同时运行
    if (this.current && this.current !== name) {
      try {
        if (this.current === 'menu') this._stopMenuVideoBg();
        if (this.current === 'hub' && window.HubMgr) HubMgr.stop();
        if ((this.current === 'battle' || this.current === 'victory' || this.current === 'gameover') && window.BattleSys) {
          BattleSys.stop();
        }
      } catch (e) {
        console.warn('[SceneMgr] 停止旧场景循环失败:', e);
      }
    }

    // 【保险】只要不是进入世界场景，就确保开放世界的循环停掉（避免和 Boss 战抢玩家）
    if (name !== 'hub' && window.WorldMgr && WorldMgr.running) {
      try { WorldMgr.stop(); } catch (e) { /* noop */ }
    }

    // 隐藏所有场景
    for (const k in this.scenes) {
      if (this.scenes[k]) this.scenes[k].classList.add('hidden');
    }
    
    const sceneMap = {
      opening: 'openingScene',
      menu: 'menuScene',
      story: 'storyScene',
      hub: 'worldScene',   // 【联机改造】中枢 → 开放世界大地图
      battle: 'battleScene',
      victory: 'victoryScene',
      gameover: 'gameOverScene',
      ending: 'endingScene',
    };
    
    const sceneId = sceneMap[name];
    if (sceneId && this.scenes[sceneId]) {
      this.scenes[sceneId].classList.remove('hidden');
      this.current = name;
      GameState.currentScene = name;
      
      // 场景进入处理
      this.onSceneEnter(name);
    }
  },
  
  onSceneEnter(name) {
    switch(name) {
      case 'menu':
        AudioMgr.playBgm('main');
        // 更新继续按钮状态
        const continueBtn = document.querySelector('[data-action="continueGame"]');
        if (continueBtn) {
          continueBtn.style.opacity = GameState.hasSave() ? '1' : '0.4';
        }
        // 启动主菜单视频背景（失败则静默回退静态背景图）
        this._playMenuVideoBg();
        break;
      case 'story':
        AudioMgr.playBgm('main');
        StoryMgr.start('prologue');
        break;
      case 'hub':
        AudioMgr.playBgm('main');
        HubMgr.start();
        break;
      case 'battle':
        // 战斗在BattleSys.start里处理音乐
        break;
      case 'victory':
        AudioMgr.playBgm('main');
        break;
      case 'gameover':
        AudioMgr.stopBgm();
        break;
      case 'ending':
        AudioMgr.playBgm('main');
        break;
    }
  },

  // 主菜单视频背景播放：成功则显示，失败/被阻止则静默回退静态背景图
  _playMenuVideoBg() {
    const videoUrl = (CONFIG.sceneVideos && CONFIG.sceneVideos.menu) || null;
    const v = document.getElementById('menuVideoBg');
    if (!v || !videoUrl) return;

    // 重置状态
    v.classList.remove('playing');
    v.src = videoUrl;

    const playPromise = v.play();
    if (playPromise && playPromise.then) {
      playPromise.then(() => {
        v.classList.add('playing');
      }).catch(() => {
        // 自动播放被阻止 → 静默回退，静态背景图继续显示
        v.classList.remove('playing');
        try { v.pause(); } catch (e) {}
      });
    }

    // 加载失败 → 静默回退
    v.onerror = () => {
      v.classList.remove('playing');
    };
  },

  _stopMenuVideoBg() {
    const v = document.getElementById('menuVideoBg');
    if (!v) return;
    v.classList.remove('playing');
    try { v.pause(); } catch (e) {}
    try { v.removeAttribute('src'); v.load(); } catch (e) {}
  },
  
  bindEvents() {
    // 开场点击进入
    const opening = document.getElementById('openingScene');
    if (opening) {
      opening.addEventListener('click', () => {
        AudioMgr.resume();
        AudioMgr.playSfx('click');
        this.show('menu');
      });
    }
    
    // 主菜单按钮
    document.querySelectorAll('#menuScene .menu-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        AudioMgr.resume();
        AudioMgr.playSfx('click');
        const action = btn.dataset.action;
        this.handleMenuAction(action);
      });
    });
    
    // 设置面板开关
    document.querySelectorAll('.toggle-switch').forEach(toggle => {
      toggle.addEventListener('click', () => {
        toggle.classList.toggle('active');
        AudioMgr.playSfx('click');
        const id = toggle.id;
        if (id === 'musicToggle') {
          GameState.settings.music = toggle.classList.contains('active');
          if (GameState.settings.music) {
            AudioMgr.playBgm(AudioMgr.currentBgm || 'main');
          } else {
            AudioMgr.stopBgm();
          }
        } else if (id === 'sfxToggle') {
          GameState.settings.sfx = toggle.classList.contains('active');
        } else if (id === 'vibrationToggle') {
          GameState.settings.vibration = toggle.classList.contains('active');
        } else if (id === 'fullscreenToggle') {
          // 全屏开关：开启时进入全屏，关闭时退出
          const active = toggle.classList.contains('active');
          if (active) {
            if (window.FullscreenMgr) FullscreenMgr.enter();
          } else {
            if (window.FullscreenMgr) FullscreenMgr.exitFullscreen();
          }
        }
        GameState.save();
      });
    });
    
    // 摇杆大小
    const joySize = document.getElementById('joystickSize');
    if (joySize) {
      joySize.addEventListener('input', () => {
        GameState.settings.joystickSize = parseInt(joySize.value);
        // 应用大小
        const base = document.getElementById('joystickBase');
        const stick = document.getElementById('joystickStick');
        const size = parseInt(joySize.value);
        if (base) {
          base.style.width = size + 'px';
          base.style.height = size + 'px';
        }
        if (stick) {
          stick.style.width = (size * 0.45) + 'px';
          stick.style.height = (size * 0.45) + 'px';
        }
        GameState.save();
      });
    }
    
    // 通用关闭按钮
    document.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        const panelId = btn.dataset.close;
        const panel = document.getElementById(panelId);
        if (panel) panel.classList.add('hidden');
      });
    });
    
    // 图鉴tab
    document.querySelectorAll('.codex-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        document.querySelectorAll('.codex-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        CodexMgr.render(tab.dataset.tab);
      });
    });
    
    // 背包tab
    document.querySelectorAll('.inv-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        document.querySelectorAll('.inv-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        InventoryMgr.render(tab.dataset.tab);
      });
    });
    
    // Hub顶部按钮
    document.querySelectorAll('.hub-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        const action = btn.dataset.action;
        if (action === 'inventory') {
          document.getElementById('inventoryPanel').classList.remove('hidden');
          InventoryMgr.render('equipment');
          document.querySelectorAll('.inv-tab').forEach(t => t.classList.remove('active'));
          document.querySelector('.inv-tab[data-tab="equipment"]').classList.add('active');
        } else if (action === 'quests') {
          document.getElementById('questPanel').classList.remove('hidden');
          QuestMgr.render();
        } else if (action === 'menuBtn') {
          document.getElementById('hubMenuPanel').classList.remove('hidden');
        }
      });
    });
    
    // Hub菜单
    document.querySelectorAll('#hubMenuPanel .menu-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        const action = btn.dataset.action;
        document.getElementById('hubMenuPanel').classList.add('hidden');
        if (action === 'saveGame') {
          GameState.save();
        } else if (action === 'hubSettings') {
          document.getElementById('settingsPanel').classList.remove('hidden');
        } else if (action === 'returnMenu') {
          HubMgr.stop();
          this.show('menu');
        }
      });
    });
    
    // 战斗暂停
    const pauseBtn = document.getElementById('battlePause');
    if (pauseBtn) {
      pauseBtn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        BattleSys.pause();
        document.getElementById('battlePausePanel').classList.remove('hidden');
      });
    }
    
    // 战斗暂停菜单
    document.querySelectorAll('#battlePausePanel .menu-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        const action = btn.dataset.action;
        document.getElementById('battlePausePanel').classList.add('hidden');
        if (action === 'resumeBattle') {
          BattleSys.resume();
        } else if (action === 'battleSettings') {
          document.getElementById('settingsPanel').classList.remove('hidden');
        } else if (action === 'retreatBattle') {
          BattleSys.stop();
          SceneMgr.show('hub');
        }
      });
    });
    
    // 胜利面板
    document.querySelector('[data-action="victoryContinue"]').addEventListener('click', () => {
      AudioMgr.playSfx('click');
      SceneMgr.show('hub');
    });
    
    // 失败面板
    document.querySelector('[data-action="retryBattle"]').addEventListener('click', () => {
      AudioMgr.playSfx('click');
      const bossId = GameState.battle.currentBossId;
      SceneMgr.show('battle');
      BattleSys.start(bossId);
    });
    
    document.querySelector('[data-action="returnHub"]').addEventListener('click', () => {
      AudioMgr.playSfx('click');
      SceneMgr.show('hub');
    });
    
    // 结局
    document.querySelector('[data-action="endingContinue"]').addEventListener('click', () => {
      AudioMgr.playSfx('click');
      SceneMgr.show('menu');
    });
    
    // 剧情对话框点击继续
    const dialogueBox = document.querySelector('.dialogue-box');
    if (dialogueBox) {
      dialogueBox.addEventListener('click', () => {
        AudioMgr.playSfx('click');
        StoryMgr.next();
      });
    }
    
    // 设置面板按钮（从主菜单打开）
    // 已通过data-action处理
  },
  
  handleMenuAction(action) {
    switch(action) {
      case 'newGame':
        // 【联机改造】「开始游戏」→ 直接进入联机 RPG 开放世界
        this.show('hub');
        break;
      case 'storyMode':
        // 原第一章剧情模式（保留）
        GameState.resetPlayer();
        GameState.save();
        this.show('story');
        break;
      case 'continueGame':
        if (GameState.load()) {
          this.show('hub');
        }
        break;
      case 'settings':
        // 同步开关状态
        document.getElementById('musicToggle').classList.toggle('active', GameState.settings.music);
        document.getElementById('sfxToggle').classList.toggle('active', GameState.settings.sfx);
        document.getElementById('vibrationToggle').classList.toggle('active', GameState.settings.vibration);
        document.getElementById('joystickSize').value = GameState.settings.joystickSize;
        // 全屏开关：同步当前真实全屏状态
        const fsToggle = document.getElementById('fullscreenToggle');
        if (fsToggle && window.FullscreenMgr) {
          fsToggle.classList.toggle('active', FullscreenMgr.isFullscreen);
        }
        document.getElementById('settingsPanel').classList.remove('hidden');
        break;
      case 'codex':
        document.getElementById('codexPanel').classList.remove('hidden');
        CodexMgr.render('characters');
        document.querySelectorAll('.codex-tab').forEach(t => t.classList.remove('active'));
        document.querySelector('.codex-tab[data-tab="characters"]').classList.add('active');
        break;
    }
  },
  
  initOpeningParticles() {
    const container = document.getElementById('openingParticles');
    if (!container) return;
    
    for (let i = 0; i < 30; i++) {
      const p = document.createElement('div');
      p.className = 'rune-particle';
      p.style.left = Math.random() * 100 + '%';
      p.style.animationDuration = (4 + Math.random() * 6) + 's';
      p.style.animationDelay = (Math.random() * 8) + 's';
      p.style.width = (4 + Math.random() * 8) + 'px';
      p.style.height = p.style.width;
      p.style.opacity = (0.3 + Math.random() * 0.5).toFixed(2);
      container.appendChild(p);
    }
  },
};

// ---------- 剧情系统 ----------
const StoryMgr = {
  dialogues: [],
  index: 0,
  typing: false,
  typeText: '',
  typeTimer: null,
  currentChar: null,
  
  start(storyId) {
    if (storyId === 'prologue') {
      this.dialogues = CONFIG.storyPrologue;
    }
    this.index = 0;
    this._onComplete = null;
    this.showLine();
  },

  /**
   * 播放一段自定义对话（用于章节剧情）
   * @param {Array} dialogues 对话数组
   * @param {Function} onComplete 结束回调
   */
  play(dialogues, onComplete) {
    this.dialogues = dialogues || [];
    this.index = 0;
    this._onComplete = onComplete || null;
    this.showLine();
  },
  
  showLine() {
    if (this.index >= this.dialogues.length) {
      // 剧情结束
      if (this._onComplete) {
        const cb = this._onComplete;
        this._onComplete = null;
        cb();
      } else {
        // 默认行为：进入Hub
        SceneMgr.show('hub');
      }
      return;
    }
    
    const line = this.dialogues[this.index];
    const nameEl = document.getElementById('dialogueName');
    const textEl = document.getElementById('dialogueText');
    const charImg = document.getElementById('storyCharImg');
    
    // 名字
    if (line.speaker === 'narrator') {
      nameEl.textContent = '旁白';
      nameEl.style.background = 'rgba(100,100,140,0.7)';
    } else if (line.speaker === 'heyun') {
      nameEl.textContent = '鹤允 · 虚空禁锢者';
      nameEl.style.background = 'rgba(147,51,234,0.7)';
    } else if (line.speaker === 'zhuyang') {
      nameEl.textContent = '竹阳';
      nameEl.style.background = 'rgba(239,68,68,0.7)';
    }
    
    // 立绘
    let imgSrc = '';
    if (line.char === 'heyun_idle') imgSrc = 'assets/img/heyun_idle.png';
    else if (line.char === 'heyun_battle') imgSrc = 'assets/img/heyun_fight.png';
    else if (line.char === 'zhuyang_idle') imgSrc = 'assets/img/zhuyang_idle.png';
    else if (line.char === 'zhuyang_battle') imgSrc = 'assets/img/zhuyang_fight.png';
    
    if (imgSrc && this.currentChar !== line.char) {
      charImg.style.animation = 'none';
      charImg.offsetHeight; // reflow
      charImg.style.animation = '';
      charImg.src = imgSrc;
      charImg.style.display = 'block';
      this.currentChar = line.char;
    } else if (!imgSrc) {
      charImg.style.display = 'none';
      this.currentChar = null;
    }
    
    // 打字机效果
    this.typing = true;
    this.typeText = '';
    const fullText = line.text;
    let i = 0;
    clearInterval(this.typeTimer);
    
    this.typeTimer = setInterval(() => {
      if (i < fullText.length) {
        this.typeText += fullText[i];
        textEl.textContent = this.typeText;
        i++;
      } else {
        clearInterval(this.typeTimer);
        this.typing = false;
      }
    }, 40);
  },
  
  next() {
    if (this.typing) {
      // 跳过打字机
      clearInterval(this.typeTimer);
      const line = this.dialogues[this.index];
      document.getElementById('dialogueText').textContent = line.text;
      this.typing = false;
      return;
    }
    
    this.index++;
    this.showLine();
  },
};

// ---------- Hub中枢系统 ----------
const HubMgr = {
  canvas: null,
  ctx: null,
  running: false,
  animFrame: null,
  lastTime: 0,
  
  // 玩家在Hub里的状态
  player: { x: 640, y: 500, facing: 1, vx: 0, vy: 0 },
  
  // Boss入口（靠左第一个更显眼，方便找到）
  entrances: [
    { id: 1, x: 280, y: 430, name: '虚空行者', unlocked: true },
    { id: 2, x: 500, y: 360, name: '熔雷巨像', unlocked: false },
    { id: 3, x: 780, y: 360, name: '字祸魔典', unlocked: false },
    { id: 4, x: 1000, y: 430, name: '时之眼', unlocked: false },
  ],
  
  // NPC竹阳
  npc: { x: 640, y: 500 },
  
  // 新手引导
  guide: {
    showFinger: true,  // 显示手指指引动画
    shownOnce: false,
  },
  
  // 背景
  bgImage: null,
  playerImg: null,
  npcImg: null,
  platformImage: null,
  
  start() {
    // 【联机改造】中枢大厅已被"开放世界大地图"取代：
    // 统一交给 WorldMgr（RPG 大地图 + 地图小怪 + Boss 锚点 + 联机）
    if (window.WorldMgr) return WorldMgr.start();

    // 【问题4】确保旧循环清理干净，避免多个循环同时运行
    if (this.running) this.stop();

    this.canvas = document.getElementById('hubCanvas');
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    
    // Hub 背景为程序化深紫空间（不使用石台图）
    this.bgImage = null;
    this.playerImg = new Image();
    this.playerImg.src = 'assets/img/heyun_idle.png';
    this.npcImg = new Image();
    this.npcImg.src = 'assets/img/zhuyang_idle.png';
    
    // 更新解锁状态
    for (const e of this.entrances) {
      e.unlocked = GameState.player.unlockedBosses.includes(e.id);
      e.defeated = GameState.player.defeatedBosses.includes(e.id);
    }

    // 新手引导：裂隙未通关或第一个 Boss 未击败时显示手指
    const firstDefeated = GameState.player.defeatedBosses.includes(1);
    this.guide.showFinger = !GameState.player.riftCleared || !firstDefeated;

    // 点击画布直接进入传送门（兜底方式）
    this._canvasClickHandler = (e) => this.handleCanvasClick(e);
    this.canvas.addEventListener('click', this._canvasClickHandler);

    // 【问题三】启动视频背景（有则播放，无则静默回退静态图）
    if (window.VideoBgMgr) {
      const videoUrl = (CONFIG.sceneVideos && CONFIG.sceneVideos.hub) || null;
      VideoBgMgr.play(videoUrl, () => {
        // 回退：canvas 照常绘制静态背景图
      });
      // 视频在 canvas 下层，canvas 背景设为透明以透出视频
      if (videoUrl) {
        this.canvas.style.background = 'transparent';
      }
    }
    
    this.running = true;
    this.lastTime = performance.now();
    this.gameLoop();

    // 接入 LayoutMgr 统一防抖重算
    if (window.LayoutMgr) {
      this._layoutCb = () => this.resize();
      LayoutMgr.onResize(this._layoutCb);
    }
  },
  
  stop() {
    // 【联机改造】同步停掉开放世界循环
    if (window.WorldMgr && WorldMgr.running) WorldMgr.stop();

    this.running = false;
    if (this.animFrame) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
    // 【问题三】离开 Hub 时停止视频背景
    if (window.VideoBgMgr) VideoBgMgr.stop();
    if (this.canvas) this.canvas.style.background = '';
    if (this._canvasClickHandler && this.canvas) {
      this.canvas.removeEventListener('click', this._canvasClickHandler);
      this._canvasClickHandler = null;
    }
  },
  
  resize() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    const cw = parent.offsetWidth;
    const ch = parent.offsetHeight;
    this.cssW = cw;
    this.cssH = ch;

    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.floor(cw * dpr);
    this.canvas.height = Math.floor(ch * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // 统一缩放比：按高度等比，保证不变形
    this.scale = ch / CONFIG.canvasHeight;
    const logicalW = cw / this.scale;

    // 安全区（底部留足空间避让水印和导航栏）
    const styles = getComputedStyle(document.documentElement);
    const parsePx = (v) => {
      const m = (v || '0px').match(/([\d.]+)px/);
      return m ? parseFloat(m[1]) : 0;
    };
    const sab = parsePx(styles.getPropertyValue('--sab').trim());
    const sal = parsePx(styles.getPropertyValue('--sal').trim());
    // 强制旋转模式下：容器底部 ← 屏幕左侧 safe-area-inset-left
    let bottomPx = (window.FullscreenMgr && FullscreenMgr.forceRotate) ? sal : sab;
    bottomPx += 50; // 避让水印
    this.safeBottom = bottomPx / this.scale;

    // 左右边界随逻辑宽度扩展
    this.leftBound = 60;
    this.rightBound = Math.max(logicalW - 60, CONFIG.canvasWidth - 60);
  },
  
  gameLoop() {
    if (!this.running) return;

    try {
      const now = performance.now();
      const dt = Math.min((now - this.lastTime) / 1000, 0.05);
      this.lastTime = now;

      this.update(dt);
      this.draw();
    } catch (e) {
      console.error('[HubMgr] 帧错误，已跳过:', e);
    } finally {
      this.animFrame = requestAnimationFrame(() => this.gameLoop());
    }
  },
  
  update(dt) {
    const p = this.player;
    const speed = 180;
    
    // 键盘移动
    let dx = 0, dy = 0;
    if (InputMgr.keys['a'] || InputMgr.keys['arrowleft']) dx -= 1;
    if (InputMgr.keys['d'] || InputMgr.keys['arrowright']) dx += 1;
    if (InputMgr.keys['w'] || InputMgr.keys['arrowup']) dy -= 1;
    if (InputMgr.keys['s'] || InputMgr.keys['arrowdown']) dy += 1;
    
    // 摇杆
    if (InputMgr.joystick.active) {
      dx = InputMgr.joystick.x;
      dy = InputMgr.joystick.y;
    }
    
    const moving = dx !== 0 || dy !== 0;
    if (moving) {
      const len = Math.hypot(dx, dy);
      dx /= len; dy /= len;
      p.x += dx * speed * dt;
      p.y += dy * speed * dt * 0.6;
      if (dx > 0) p.facing = 1;
      else if (dx < 0) p.facing = -1;
    }

    // 【问题二】Hub 玩家动画状态机
    if (window.Player && Player.animPlayer) {
      // 确保 idle/run 状态正确切换
      if (moving) {
        if (this._hubAnimState !== 'run') {
          this._hubAnimState = 'run';
          Player.animPlayer.play([1, 2, 3, 2], { loop: true, fps: 8 });
        }
      } else {
        if (this._hubAnimState !== 'idle') {
          this._hubAnimState = 'idle';
          Player.animPlayer.play([0, 0, 0, 0], { loop: true, fps: 2 });
        }
      }
      Player.animPlayer.update(dt);
    }
    
    // 边界
    p.x = Utils.clamp(p.x, 80, 1200);
    p.y = Utils.clamp(p.y, 320, 580);
    
    // 检测靠近入口（触发半径扩大，方便找到）
    let nearestEntrance = null;
    let nearestDist = Infinity;
    for (const e of this.entrances) {
      const d = Utils.dist(p.x, p.y, e.x, e.y);
      if (d < 80 && d < nearestDist && e.unlocked) {
        nearestDist = d;
        nearestEntrance = e;
      }
    }
    
    // NPC对话
    const npcDist = Utils.dist(p.x, p.y, this.npc.x, this.npc.y);
    // 第5裂隙（小怪连战）距离
    const riftDist = Utils.dist(p.x, p.y, this.RIFT_POS.x, this.RIFT_POS.y);

    const hintEl = document.getElementById('hubHint');
    if (nearestEntrance) {
      // 靠近入口了，隐藏手指引导
      if (this.guide.showFinger) this.guide.showFinger = false;

      hintEl.textContent = nearestEntrance.defeated
        ? `再次挑战 ${nearestEntrance.name}（点击进入）`
        : `进入 ${nearestEntrance.name} 关卡（点击进入）`;
      hintEl.classList.add('clickable');
      hintEl.style.cursor = 'pointer';
      hintEl.onclick = () => {
        this.enterBattle(nearestEntrance.id);
      };

      // 空格/回车进入
      if (InputMgr.keys[' '] || InputMgr.keys['enter']) {
        InputMgr.keys[' '] = false;
        InputMgr.keys['enter'] = false;
        this.enterBattle(nearestEntrance.id);
      }
    } else if (riftDist < 74) {
      // 靠近裂隙领域（小怪连战）——开局玩家即在附近，优先引导刷小怪
      if (this.guide.showFinger) this.guide.showFinger = false;

      hintEl.textContent = '进入「裂隙领域」刷小怪（升级·攒金币）· 点击进入';
      hintEl.classList.add('clickable');
      hintEl.style.cursor = 'pointer';
      hintEl.onclick = () => this.enterRift();
      if (InputMgr.keys[' '] || InputMgr.keys['enter']) {
        InputMgr.keys[' '] = false;
        InputMgr.keys['enter'] = false;
        this.enterRift();
      }
    } else if (npcDist < 60) {
      hintEl.textContent = '与竹阳对话';
      hintEl.classList.remove('clickable');
      hintEl.style.cursor = 'pointer';
      hintEl.onclick = () => this.talkToNPC();
    } else {
      // 引导目标：未通关裂隙 → 先去刷小怪；否则前往下一个 Boss
      let target;
      if (!GameState.player.riftCleared) target = { name: '裂隙领域', isRift: true };
      else target = this.entrances.find(e => e.unlocked && !e.defeated)
                  || this.entrances.find(e => e.unlocked);

      if (target) {
        hintEl.textContent = target.isRift
          ? '先前往「裂隙领域」刷小怪升级 · 点击直接进入'
          : `前往「${target.name}」入口 · 点击或靠近传送门进入`;
      } else {
        hintEl.textContent = '移动到关卡入口进入战斗';
      }
      hintEl.classList.add('clickable');
      hintEl.style.cursor = 'pointer';
      // 点击底部提示直接进入目标（兜底）
      hintEl.onclick = () => {
        if (target && target.isRift) { this.enterRift(); return; }
        const t = this.entrances.find(e => e.unlocked && !e.defeated)
                || this.entrances.find(e => e.unlocked);
        if (t) this.enterBattle(t.id);
      };
    }
  },

  // 画布点击：点到传送门直接进入（兜底）
  handleCanvasClick(e) {
    const rect = this.canvas.getBoundingClientRect();
    const s = this.scale || 1;
    // 强制旋转模式下坐标换算
    let sx = e.clientX - rect.left;
    let sy = e.clientY - rect.top;
    if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
      const p = FullscreenMgr.screenToContainer(e.clientX, e.clientY);
      sx = p.x;
      sy = p.y;
    }
    const worldX = sx / s;
    const worldY = sy / s;

    // 检查是否点在第5裂隙（小怪连战）上
    const rp = this.RIFT_POS;
    if (Utils.dist(worldX, worldY, rp.x, rp.y) < 54) {
      AudioMgr.playSfx('click');
      this.enterRift();
      return;
    }

    // 检查是否点在某个Boss入口上（半径 50）
    for (const ent of this.entrances) {
      if (!ent.unlocked) continue;
      const d = Utils.dist(worldX, worldY, ent.x, ent.y);
      if (d < 55) {
        AudioMgr.playSfx('click');
        this.enterBattle(ent.id);
        return;
      }
    }
  },

  enterBattle(bossId) {
    this.stop();
    SceneMgr.show('battle');
    BattleSys.start(bossId);
  },

  // 进入第5裂隙·小怪连战（初始开放，先刷小怪升级、攒金币，再去打 Boss）
  enterRift() {
    this.stop();
    SceneMgr.show('battle');
    const riftScene = {
      title: '裂隙领域',
      bg: 'assets/img/bg_corridor_dl.jpg',
      bgm: 'boss',
      waves: [
        [
          { type: 'floater', x: 900, y: 470 },
          { type: 'floater', x: 1040, y: 430 },
          { type: 'floater', x: 1150, y: 470 },
        ],
        [
          { type: 'wraith', x: 960, y: 470 },
          { type: 'floater', x: 1090, y: 430 },
          { type: 'wraith', x: 1180, y: 470 },
        ],
        [
          { type: 'golem', x: 1000, y: 480 },
          { type: 'wraith', x: 1120, y: 440 },
          { type: 'floater', x: 1180, y: 470 },
          { type: 'floater', x: 900, y: 450 },
        ],
      ],
    };
    BattleSys.startWaveBattle(riftScene, () => {
      // 通关奖励（可重复进入刷取）
      const gold = 120, exp = 100;
      GameState.player.gold += gold;
      const leveled = GameState.addExp(exp);
      GameState.player.riftCleared = true;
      GameState.save();
      SceneMgr.show('hub');
      HubMgr.start();
      HubMgr._toast(`裂隙领域净化完成！获得 ${gold} 金币、${exp} 经验`);
      if (leveled) AudioMgr.playSfx('levelup');
    });
  },

  // 轻量临时提示（不依赖每帧 update 的 hint）
  _toast(text) {
    const host = document.getElementById('hubScene') || document.body;
    const el = document.createElement('div');
    el.textContent = text;
    el.style.cssText =
      'position:absolute;top:16%;left:50%;transform:translateX(-50%);' +
      'background:rgba(8,35,58,0.9);color:#bae6fd;padding:10px 22px;border-radius:10px;' +
      'border:1px solid rgba(125,211,252,0.55);z-index:60;font-size:16px;' +
      'pointer-events:none;white-space:nowrap;box-shadow:0 0 18px rgba(56,189,248,0.35);';
    host.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 520);
    }, 2600);
  },
  
  talkToNPC() {
    // 简单对话
    const dialogues = [
      { speaker: 'zhuyang', text: '嘿，鹤允。准备好挑战下一个锚点了吗？' },
      { speaker: 'heyun', text: '...还用你说。' },
      { speaker: 'zhuyang', text: '哈哈，那就加油吧。需要帮忙随时叫我。' },
      { speaker: 'zhuyang', text: '（这丫头...嘴上不说，其实挺可靠的。）' },
    ];
    
    // 临时用story场景
    StoryMgr.dialogues = dialogues;
    StoryMgr.index = 0;
    // 直接显示第一个对话
    // 简化：用alert的替代方案——弹窗
    // 实际应该用对话系统，这里简化处理
    let i = 0;
    const showNext = () => {
      if (i >= dialogues.length) {
        document.getElementById('storyScene').classList.add('hidden');
        SceneMgr.show('hub');
        return;
      }
      const d = dialogues[i];
      const nameEl = document.getElementById('dialogueName');
      const textEl = document.getElementById('dialogueText');
      const charImg = document.getElementById('storyCharImg');
      
      nameEl.textContent = d.speaker === 'zhuyang' ? '竹阳' : '鹤允';
      nameEl.style.background = d.speaker === 'zhuyang' ? 'rgba(239,68,68,0.7)' : 'rgba(147,51,234,0.7)';
      
      charImg.src = d.speaker === 'zhuyang' 
        ? 'assets/img/zhuyang_idle.png'
        : 'assets/img/heyun_idle.png';
      charImg.style.display = 'block';
      
      // 打字机
      let j = 0;
      textEl.textContent = '';
      const timer = setInterval(() => {
        if (j < d.text.length) {
          textEl.textContent += d.text[j];
          j++;
        } else {
          clearInterval(timer);
        }
      }, 40);
      
      i++;
    };
    
    document.getElementById('storyScene').classList.remove('hidden');
    SceneMgr.current = 'story'; // 临时
    
    const box = document.querySelector('.dialogue-box');
    const handler = () => {
      if (i >= dialogues.length) {
        box.removeEventListener('click', handler);
        document.getElementById('storyScene').classList.add('hidden');
        SceneMgr.current = 'hub';
      } else {
        showNext();
      }
    };
    box.addEventListener('click', handler, { once: false });
    
    showNext();
  },
  
  updateHubUI() {
    document.getElementById('hubGold').textContent = GameState.player.gold;
    document.getElementById('hubStar').textContent = GameState.player.star;
    document.getElementById('hubLevel').textContent = GameState.player.level;
  },

  updateObjective() {
    const objEl = document.getElementById('hubObjective');
    if (!objEl) return;
    const defeated = GameState.player.defeatedBosses.length;
    const total = 4;
    if (defeated >= total) {
      objEl.textContent = '所有锚点已击破 · 前往最终决战';
    } else {
      objEl.textContent = `当前目标：击败结界锚点 ${defeated}/${total}`;
    }
  },
  
  draw() {
    const ctx = this.ctx;
    const cw = this.cssW;
    const ch = this.cssH;
    const s = this.scale || 1;

    ctx.clearRect(0, 0, cw, ch);

    // 背景：深紫虚空径向渐变
    {
      const bg = ctx.createRadialGradient(cw * 0.5, ch * 0.42, 80, cw * 0.5, ch * 0.5, Math.max(cw, ch) * 0.75);
      bg.addColorStop(0, '#241542');
      bg.addColorStop(0.55, '#160d2c');
      bg.addColorStop(1, '#0b0718');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, cw, ch);
    }

    ctx.save();
    ctx.scale(s, s);

    // 画符文平台
    this.drawRunePlatform(ctx, 640, 450, 500);

    // 第5入口·裂隙领域（锁定态）
    this.drawRiftEntrance(ctx);

    // 画Boss入口
    for (const e of this.entrances) {
      this.drawEntrance(ctx, e);
    }

    // 新手引导：未通关裂隙先指向裂隙（刷小怪），否则指向下一个 Boss
    if (this.guide.showFinger) {
      let target;
      if (!GameState.player.riftCleared) target = this.RIFT_POS;
      else target = this.entrances.find(e => e.unlocked && !e.defeated);
      if (target) {
        this.drawGuide(ctx, target);
      }
    }
    
    // 竹阳通过底部固定按钮交互，场景内不再绘制其立绘与名字

    // 画玩家
    {
      const p = this.player;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.scale(p.facing * 0.6, 0.6);

      // 【问题二】优先用精灵帧动画；精灵未加载时回退到静态立绘+浮动
      const useAnim = window.Player && Player.spriteLoaded && Player.animPlayer;
      if (useAnim) {
        const frame = Player.animPlayer.getCurrentFrame();
        if (frame) {
          const fw = Player.width || 100;
          const fh = Player.height || 140;
          ctx.shadowColor = '#a855f7';
          ctx.shadowBlur = 15;
          ctx.drawImage(frame, -fw/2, -fh, fw, fh);
        }
      } else if (this.playerImg && this.playerImg.complete) {
        const bob = Math.sin(performance.now() / 200) * 2;
        ctx.translate(0, bob);
        ctx.shadowColor = '#a855f7';
        ctx.shadowBlur = 15;
        ctx.drawImage(this.playerImg, -50, -140, 100, 140);
      }
      ctx.restore();
    }
    
    ctx.restore();
  },
  
  // 中枢大厅中央·发光魔法阵（多层、高对比、持续旋转）
  drawRunePlatform(ctx, cx, cy, size) {
    const t = performance.now() / 1000;
    const R = size * 0.42;          // 水平半径
    const flat = 0.42;              // 透视压扁
    // 透视椭圆上的点（a 为阵平面内角度）
    const pt = (a, r) => [
      cx + Math.cos(a) * r,
      cy + Math.sin(a) * r * flat,
    ];

    const C_MAIN = '#7dd3fc';       // 青
    const C_ALT = '#c084fc';        // 紫
    const FONT = '"Noto Serif SC", "Songti SC", serif';

    ctx.save();

    // ---- 地面辉光底盘 ----
    const ground = ctx.createRadialGradient(cx, cy, 10, cx, cy, R * 1.25);
    ground.addColorStop(0, 'rgba(125,211,252,0.16)');
    ground.addColorStop(0.6, 'rgba(124,58,237,0.10)');
    ground.addColorStop(1, 'rgba(124,58,237,0)');
    ctx.fillStyle = ground;
    ctx.beginPath();
    ctx.ellipse(cx, cy, R * 1.25, R * 1.25 * flat, 0, 0, Math.PI * 2);
    ctx.fill();

    // ---- 最外环（亮、发光）----
    ctx.save();
    ctx.shadowColor = C_MAIN; ctx.shadowBlur = 18;
    ctx.strokeStyle = 'rgba(125,211,252,0.9)';
    ctx.lineWidth = 2.6;
    ctx.beginPath();
    ctx.ellipse(cx, cy, R, R * flat, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // ---- 外环刻度（48 格，缓慢正转）----
    const rotTicks = t / 12;
    ctx.strokeStyle = 'rgba(125,211,252,0.55)';
    ctx.lineWidth = 1.4;
    for (let k = 0; k < 48; k++) {
      const a = (k / 48) * Math.PI * 2 + rotTicks;
      const long = k % 4 === 0;
      const [x1, y1] = pt(a, long ? R - 12 : R - 6);
      const [x2, y2] = pt(a, R);
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }

    // ---- 第二环（紫）----
    ctx.save();
    ctx.shadowColor = C_ALT; ctx.shadowBlur = 12;
    ctx.strokeStyle = 'rgba(192,132,252,0.8)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(cx, cy, R * 0.78, R * 0.78 * flat, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // ---- 六芒星（两个叠加三角，缓慢正转）----
    const rotStar = t / 9;
    ctx.save();
    ctx.shadowColor = C_MAIN; ctx.shadowBlur = 10;
    ctx.strokeStyle = 'rgba(165,224,255,0.85)';
    ctx.lineWidth = 1.8;
    for (const off of [0, Math.PI / 3]) {
      ctx.beginPath();
      for (let k = 0; k < 3; k++) {
        const [x, y] = pt(k * (Math.PI * 2 / 3) + off + rotStar, R * 0.62);
        if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }
    ctx.restore();

    // ---- 内符文环（8 节点，反向旋转）----
    const rotRune = -t / 11;
    ctx.strokeStyle = 'rgba(192,132,252,0.6)';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.ellipse(cx, cy, R * 0.42, R * 0.42 * flat, 0, 0, Math.PI * 2);
    ctx.stroke();
    const runeChars = ['虚', '空', '禁', '锢', '裂', '时', '言', '灵'];
    for (let k = 0; k < 8; k++) {
      const a = (k / 8) * Math.PI * 2 + rotRune;
      const [x, y] = pt(a, R * 0.42);
      ctx.save();
      ctx.shadowColor = C_ALT; ctx.shadowBlur = 8;
      ctx.fillStyle = 'rgba(221,214,254,0.92)';
      ctx.font = 'bold 15px ' + FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(runeChars[k], x, y);
      ctx.restore();
    }

    // ---- 轨道光点（两圈，不同速）----
    for (const [rr, sp, col] of [[R * 0.9, t / 6, C_MAIN], [R * 0.55, -t / 4, C_ALT]]) {
      for (let k = 0; k < 3; k++) {
        const a = (k / 3) * Math.PI * 2 + sp;
        const [x, y] = pt(a, rr);
        ctx.save();
        ctx.shadowColor = col; ctx.shadowBlur = 12;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(x, y, 3.2, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
    }

    // ---- 中心核心（脉动发光）----
    const pulse = 1 + Math.sin(t * 2.4) * 0.18;
    const cr = 26 * pulse;
    const core = ctx.createRadialGradient(cx, cy, 1, cx, cy, cr);
    core.addColorStop(0, 'rgba(255,255,255,0.95)');
    core.addColorStop(0.4, 'rgba(165,224,255,0.7)');
    core.addColorStop(1, 'rgba(125,211,252,0)');
    ctx.save();
    ctx.shadowColor = C_MAIN; ctx.shadowBlur = 20;
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(cx, cy, cr, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    ctx.restore();
  },

  // 第5入口·裂隙领域（小怪连战，初始即解锁，先刷小怪再打 Boss）
  RIFT_POS: { x: 580, y: 465 },
  drawRiftEntrance(ctx) {
    const t = performance.now() / 1000;
    const { x, y } = this.RIFT_POS;
    const c = '#38bdf8';
    const FONT = '"Noto Serif SC", "Songti SC", serif';
    const pulse = 1 + Math.sin(t * 2.2) * 0.06;

    ctx.save();
    ctx.translate(x, y);
    ctx.scale(pulse, pulse);

    // 外椭圆环（发光）
    ctx.save();
    ctx.shadowColor = c; ctx.shadowBlur = 20;
    ctx.strokeStyle = 'rgba(125,211,252,0.95)'; ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.ellipse(0, 0, 36, 48, 0, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();

    // 内部空间辉光（扭动的裂隙感）
    const g = ctx.createRadialGradient(0, -4, 3, 0, 0, 46);
    g.addColorStop(0, 'rgba(186,230,253,0.75)');
    g.addColorStop(0.5, 'rgba(56,189,248,0.35)');
    g.addColorStop(1, 'rgba(56,189,248,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.ellipse(0, 0, 33, 45, 0, 0, Math.PI * 2); ctx.fill();

    // 内部闪电状裂纹
    ctx.strokeStyle = 'rgba(224,242,254,0.8)'; ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(-6, -30); ctx.lineTo(4, -12); ctx.lineTo(-4, 4); ctx.lineTo(8, 26);
    ctx.stroke();

    // 编号徽章（青色）
    ctx.save();
    ctx.shadowColor = c; ctx.shadowBlur = 12;
    ctx.fillStyle = c;
    ctx.beginPath(); ctx.arc(0, -64, 15, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#08233a';
    ctx.font = 'bold 17px ' + FONT;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('5', 0, -64);
    ctx.restore();

    // 名称 + 小怪标注
    ctx.textBaseline = 'alphabetic';
    ctx.save();
    ctx.shadowColor = c; ctx.shadowBlur = 12;
    ctx.fillStyle = '#bae6fd';
    ctx.font = 'bold 20px ' + FONT;
    ctx.textAlign = 'center';
    ctx.fillText('裂隙领域', 0, 82);
    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(147,197,253,0.92)';
    ctx.font = '13px ' + FONT;
    const blip = Math.sin(t * 5) > 0;
    ctx.fillText('小怪连战 · 刷级刷金币' + (blip ? ' ▼' : ''), 0, 102);
    ctx.restore();

    ctx.restore();
  },
  
  drawEntrance(ctx, e) {
    const t = performance.now() / 1000;
    const pulse = 1 + Math.sin(t * 1.6 + e.id * 1.3) * 0.035;
    const runes = { 1: '虚', 2: '熔', 3: '字', 4: '时' };
    const FONT = '"Noto Serif SC", "Songti SC", "STSong", serif';

    ctx.save();
    ctx.translate(e.x, e.y);

    if (e.unlocked) {
      const defeated = e.defeated;
      const main = '#38e0a2';
      const light = defeated ? '#6ee7b7' : '#8af5c4';
      const dim = defeated ? 0.82 : 1;       // 已击破整体略柔
      const glow = defeated ? 14 : 24;

      ctx.scale(pulse, pulse);

      // 外椭圆环（暗淡、最外）
      ctx.save();
      ctx.shadowColor = main; ctx.shadowBlur = 10;
      ctx.strokeStyle = 'rgba(52,211,153,' + (0.30 * dim) + ')';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(0, 0, 52, 70, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // 内部径向辉光
      const g = ctx.createRadialGradient(0, -6, 4, 0, 0, 60);
      g.addColorStop(0, 'rgba(52,211,153,' + (0.32 * dim) + ')');
      g.addColorStop(0.6, 'rgba(16,185,129,' + (0.14 * dim) + ')');
      g.addColorStop(1, 'rgba(16,185,129,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(0, 0, 50, 68, 0, 0, Math.PI * 2);
      ctx.fill();

      // 内椭圆环（亮、发光）
      ctx.save();
      ctx.shadowColor = main; ctx.shadowBlur = glow;
      ctx.strokeStyle = 'rgba(74,226,170,' + (0.92 * dim) + ')';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.ellipse(0, 0, 42, 57, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // Boss 几何线稿
      ctx.save();
      ctx.translate(0, -4);
      ctx.shadowColor = main; ctx.shadowBlur = 8;
      ctx.strokeStyle = 'rgba(110,231,183,' + (0.55 * dim) + ')';
      ctx.lineWidth = 1.6;
      this.drawBossGlyph(ctx, e.id);
      ctx.restore();

      // 符文大字
      ctx.save();
      ctx.shadowColor = main; ctx.shadowBlur = 12;
      ctx.fillStyle = 'rgba(138,245,196,' + (0.62 * dim) + ')';
      ctx.font = '34px ' + FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(runes[e.id] || '', 0, -8);
      ctx.restore();

      // 编号徽章
      ctx.save();
      ctx.shadowColor = main; ctx.shadowBlur = 14;
      ctx.fillStyle = main;
      ctx.beginPath();
      ctx.arc(0, -66, 15, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = '#06281c';
      ctx.font = 'bold 17px ' + FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(e.id), 0, -66);
      ctx.restore();

      // 名字
      ctx.save();
      ctx.shadowColor = main; ctx.shadowBlur = 12;
      ctx.fillStyle = light;
      ctx.font = 'bold 21px ' + FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(e.name, 0, 84);
      ctx.restore();

      // 状态
      ctx.textAlign = 'center';
      if (defeated) {
        ctx.fillStyle = 'rgba(110,231,183,0.72)';
        ctx.font = '14px ' + FONT;
        ctx.fillText('✓ 已击破', 0, 106);
      } else {
        const blip = Math.sin(t * 5) > 0;
        ctx.fillStyle = 'rgba(138,245,196,0.92)';
        ctx.font = '13px ' + FONT;
        ctx.fillText((blip ? '▼' : '▽') + ' 点击挑战 ' + (blip ? '▼' : '▽'), 0, 106);
      }
    } else {
      // 锁定：灰色虚线门
      ctx.strokeStyle = 'rgba(110,120,130,0.5)';
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.ellipse(0, 0, 42, 57, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = 'rgba(90,96,110,0.9)';
      ctx.beginPath();
      ctx.arc(0, -66, 15, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#c7ccd4';
      ctx.font = 'bold 17px ' + FONT;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(String(e.id), 0, -66);

      ctx.fillStyle = '#7d8590';
      ctx.font = '18px serif';
      ctx.fillText('🔒', 0, 0);

      ctx.textBaseline = 'alphabetic';
      ctx.font = '13px ' + FONT;
      ctx.fillStyle = '#8b939e';
      ctx.fillText(e.name + ' · 未解锁', 0, 84);
    }

    ctx.restore();
  },

  // Boss 几何线稿（符文阵中心图案）
  drawBossGlyph(ctx, id) {
    ctx.beginPath();
    switch (id) {
      case 1: // 虚空行者：多面水晶 + 切面
        ctx.moveTo(0, -26);
        ctx.lineTo(17, -8);
        ctx.lineTo(13, 16);
        ctx.lineTo(0, 27);
        ctx.lineTo(-14, 16);
        ctx.lineTo(-16, -8);
        ctx.closePath();
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, -26); ctx.lineTo(0, 27);
        ctx.moveTo(-16, -8); ctx.lineTo(17, -8);
        ctx.moveTo(-14, 16); ctx.lineTo(13, 16);
        ctx.stroke();
        break;
      case 2: // 熔雷巨像：横向六边形祭坛 + 中心菱形
        ctx.moveTo(-27, -5);
        ctx.lineTo(-14, -14);
        ctx.lineTo(14, -14);
        ctx.lineTo(27, -5);
        ctx.lineTo(14, 7);
        ctx.lineTo(-14, 7);
        ctx.closePath();
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, -8);
        ctx.lineTo(8, 0);
        ctx.lineTo(0, 8);
        ctx.lineTo(-8, 0);
        ctx.closePath();
        ctx.stroke();
        break;
      case 3: // 字祸魔典：挂环 + 盾形吊坠
        ctx.moveTo(4, -22);
        ctx.arc(0, -22, 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, -16);
        ctx.lineTo(15, -2);
        ctx.lineTo(9, 17);
        ctx.lineTo(0, 27);
        ctx.lineTo(-9, 17);
        ctx.lineTo(-15, -2);
        ctx.closePath();
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, -16); ctx.lineTo(0, 27);
        ctx.moveTo(-9, 4); ctx.lineTo(9, 4);
        ctx.stroke();
        break;
      case 4: // 时之眼：杏仁眼 + 菱形瞳孔
        ctx.moveTo(-26, 0);
        ctx.quadraticCurveTo(0, -20, 26, 0);
        ctx.quadraticCurveTo(0, 18, -26, 0);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, -9);
        ctx.lineTo(9, 0);
        ctx.lineTo(0, 9);
        ctx.lineTo(-9, 0);
        ctx.closePath();
        ctx.stroke();
        break;
    }
  },

  // 新手引导：手指动画 + 从玩家指向目标入口的箭头路径提示
  drawGuide(ctx, target) {
    const p = this.player;
    const t = performance.now() / 1000;

    // 地面移动箭头（从玩家指向目标入口，一排沿路径的箭头）
    const dx = target.x - p.x;
    const dy = target.y - p.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 80) return; // 靠近了就不显示了

    const dirX = dx / dist;
    const dirY = dy / dist;
    const arrowCount = Math.min(6, Math.floor(dist / 60));
    ctx.save();
    ctx.fillStyle = 'rgba(251,191,36,0.7)';
    ctx.shadowColor = '#fbbf24';
    ctx.shadowBlur = 8;
    for (let i = 1; i <= arrowCount; i++) {
      const frac = i / (arrowCount + 1);
      const ax = p.x + dx * frac;
      const ay = p.y + dy * frac;
      const offset = (t * 30 + i * 20) % 30 - 15; // 流动效果
      const aax = ax + dirX * offset * 0.5;
      const aay = ay + dirY * offset * 0.5;
      ctx.save();
      ctx.translate(aax, aay);
      ctx.rotate(Math.atan2(dy, dx));
      ctx.beginPath();
      ctx.moveTo(10, 0);
      ctx.lineTo(-6, -6);
      ctx.lineTo(-6, 6);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();

    // 手指图标：在目标入口上方浮动 + 点击动效
    const fingerY = target.y - 90 + Math.sin(t * 3) * 8;
    const fingerX = target.x;
    ctx.save();
    ctx.translate(fingerX, fingerY);
    ctx.font = '32px serif';
    ctx.textAlign = 'center';
    ctx.shadowColor = '#fbbf24';
    ctx.shadowBlur = 12;
    // 按压缩放效果
    const press = (Math.sin(t * 4) + 1) / 2; // 0~1
    const sy = 1 - press * 0.15;
    ctx.scale(1, sy);
    ctx.fillText('👆', 0, 0);
    ctx.restore();
  },
};

// ---------- 图鉴系统 ----------
const CodexMgr = {
  render(tab) {
    const body = document.getElementById('codexBody');
    if (!body) return;
    
    if (tab === 'characters') {
      body.innerHTML = CONFIG.codex.characters.map(c => `
        <div class="codex-entry">
          <img src="${c.img}" alt="${c.name}">
          <div>
            <h4>${c.name} · ${c.title}</h4>
            <p>${c.desc}</p>
          </div>
        </div>
      `).join('');
    } else if (tab === 'bosses') {
      body.innerHTML = CONFIG.codex.bosses.map((b, idx) => {
        const bossId = idx + 1;
        const unlocked = GameState.player.defeatedBosses.includes(bossId);
        return `
        <div class="codex-entry">
          <img src="${b.img}" alt="${b.name}" style="${unlocked ? '' : 'filter: brightness(0.3) grayscale(1)'}">
          <div>
            <h4>${unlocked ? b.name : '???'}</h4>
            <p>${unlocked ? b.desc : '击败后解锁资料'}</p>
          </div>
        </div>
      `}).join('');
    } else if (tab === 'music') {
      body.innerHTML = CONFIG.codex.music.map((m, i) => `
        <div class="music-entry">
          <div>
            <h4 style="color:#c4b5fd; font-weight:500; margin-bottom:2px;">${m.name}</h4>
            <p style="font-size:12px; color:#888;">${m.desc}</p>
          </div>
          <button onclick="CodexMgr.playMusic(${i})">▶ 播放</button>
        </div>
      `).join('');
    }
  },
  
  playMusic(index) {
    const m = CONFIG.codex.music[index];
    if (!m) return;
    AudioMgr.playBgm(m.src);
  },
};

// ---------- 背包/装备/技能 ----------
const InventoryMgr = {
  currentTab: 'equipment',
  selectedItem: null,
  
  render(tab) {
    this.currentTab = tab;
    const body = document.getElementById('invBody');
    if (!body) return;
    
    if (tab === 'equipment') {
      // 装备栏（3个遗物槽）
      const equipped = GameState.player.equippedRelics;
      let slotsHtml = '';
      for (let i = 0; i < 3; i++) {
        const relicId = equipped[i];
        const relic = relicId ? CONFIG.relics.find(r => r.id === relicId) : null;
        slotsHtml += `
          <div class="inv-slot ${relic ? 'has-item equipped' : ''}" 
               onclick="InventoryMgr.selectSlot(${i})">
            ${relic ? `
              <div class="slot-icon">${relic.icon}</div>
              <div class="slot-name">${relic.name}</div>
            ` : `
              <div class="slot-icon">+</div>
              <div class="slot-name">空槽</div>
            `}
          </div>
        `;
      }
      
      body.innerHTML = `
        <p style="color:#a0a0c0; font-size:13px; margin-bottom:10px;">装备中的遗物（最多3个）</p>
        <div class="inv-grid">${slotsHtml}</div>
        ${this.selectedItem !== null ? this.renderDetail() : ''}
      `;
    } else if (tab === 'relics') {
      // 所有拥有的遗物
      const relics = GameState.player.relics;
      if (relics.length === 0) {
        body.innerHTML = '<p style="color:#666; text-align:center; padding:40px 0;">尚未获得任何遗物</p>';
        return;
      }
      
      let html = '<p style="color:#a0a0c0; font-size:13px; margin-bottom:10px;">已获得的遗物（点击装备/卸下）</p>';
      html += '<div class="inv-grid">';
      for (const id of relics) {
        const relic = CONFIG.relics.find(r => r.id === id);
        if (!relic) continue;
        const isEquipped = GameState.player.equippedRelics.includes(id);
        html += `
          <div class="inv-slot has-item ${isEquipped ? 'equipped' : ''}" 
               onclick="InventoryMgr.toggleRelic('${id}')">
            <div class="slot-icon">${relic.icon}</div>
            <div class="slot-name">${relic.name}</div>
          </div>
        `;
      }
      html += '</div>';
      
      // 未获得的
      const unowned = CONFIG.relics.filter(r => !relics.includes(r.id));
      if (unowned.length > 0) {
        html += '<p style="color:#666; font-size:12px; margin:16px 0 8px;">未获得</p>';
        html += '<div class="inv-grid">';
        for (const relic of unowned) {
          html += `
            <div class="inv-slot" style="opacity:0.4;">
              <div class="slot-icon">?</div>
              <div class="slot-name">???</div>
            </div>
          `;
        }
        html += '</div>';
      }
      
      body.innerHTML = html;
    } else if (tab === 'skills') {
      // 技能升级
      const skills = ['attack', '1', '2', '3', 'ult'];
      let html = '';
      for (const s of skills) {
        const skill = CONFIG.skills[s];
        const lv = GameState.player.skillLevels[s] || 1;
        const maxLv = skill.upgradeCost.length + 1;
        const cost = lv < maxLv ? skill.upgradeCost[lv - 1] : null;
        const canUpgrade = cost !== null && GameState.player.gold >= cost;
        
        html += `
          <div class="skill-upgrade-row">
            <div class="skill-upgrade-info">
              <h4>${skill.name} <span style="color:#fbbf24; font-size:12px;">Lv.${lv}${lv >= maxLv ? ' (满级)' : ''}</span></h4>
              <p>${skill.description}</p>
              ${lv < maxLv ? `<p style="color:#10b981; font-size:11px;">下级效果：${skill.upgradeEffect[lv - 1]}</p>` : ''}
            </div>
            <button class="skill-upgrade-btn" 
                    ${canUpgrade ? '' : 'disabled'}
                    onclick="InventoryMgr.upgradeSkill('${s}')">
              ${cost !== null ? `${cost}金币` : '已满级'}
            </button>
          </div>
        `;
      }
      body.innerHTML = html;
    }
  },
  
  selectSlot(index) {
    const equipped = GameState.player.equippedRelics;
    const relicId = equipped[index];
    if (relicId) {
      // 卸下
      equipped.splice(index, 1);
      GameState.save();
      this.render('equipment');
      AudioMgr.playSfx('click');
    }
  },
  
  toggleRelic(id) {
    const equipped = GameState.player.equippedRelics;
    const idx = equipped.indexOf(id);
    if (idx >= 0) {
      // 卸下
      equipped.splice(idx, 1);
    } else {
      // 装备
      if (equipped.length >= 3) {
        // 满了，替换第一个
        equipped.shift();
      }
      equipped.push(id);
    }
    GameState.save();
    this.render('relics');
    AudioMgr.playSfx('click');
  },
  
  upgradeSkill(skillId) {
    const skill = CONFIG.skills[skillId];
    const lv = GameState.player.skillLevels[skillId] || 1;
    const maxLv = skill.upgradeCost.length + 1;
    if (lv >= maxLv) return;
    
    const cost = skill.upgradeCost[lv - 1];
    if (GameState.player.gold < cost) return;
    
    GameState.player.gold -= cost;
    GameState.player.skillLevels[skillId] = lv + 1;
    GameState.save();
    
    AudioMgr.playSfx('levelup');
    this.render('skills');
    
    // 更新Hub UI
    if (document.getElementById('hubGold')) {
      document.getElementById('hubGold').textContent = GameState.player.gold;
    }
  },
  
  renderDetail() {
    // 简化处理
    return '';
  },
};

// ---------- 任务系统 ----------
const QuestMgr = {
  render() {
    const list = document.getElementById('questList');
    if (!list) return;
    
    const quests = GameState.player.quests;
    list.innerHTML = quests.map(q => `
      <div class="quest-item ${q.completed ? 'completed' : ''}">
        <h4>${q.type === 'main' ? '【主线】' : '【悬赏】'}${q.name}</h4>
        <p>${q.desc}</p>
        <span class="quest-reward">${q.completed ? '✓ 已完成' : '奖励：' + q.reward}</span>
      </div>
    `).join('');
  },
};
