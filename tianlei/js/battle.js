/* ==========================================================
   战斗系统
   ========================================================== */

const BattleSys = {
  canvas: null,
  ctx: null,
  boss: null,
  bgImage: null,
  running: false,
  lastTime: 0,
  animFrame: null,

  // 缩放与安全区（运行时计算）
  scale: 1,        // 统一缩放比（基于高度等比，保证不变形）
  offsetX: 0,      // 玩法区域在画布上的水平偏移（居中/贴边）
  safeTop: 0,      // 安全区顶部（逻辑坐标）
  safeBottom: 0,   // 安全区底部预留（逻辑坐标）
  cssW: 0,         // 画布 CSS 宽度
  cssH: 0,         // 画布 CSS 高度

  // 场地边界（逻辑坐标系，1280x720 设计基准）
  groundY: 480,
  leftBound: 60,
  rightBound: 1220,

  // 小怪战斗模式
  mode: 'boss', // 'boss' or 'wave'
  enemies: [],
  enemyProjectiles: [],
  currentWave: 0,
  waveData: null,
  onWaveComplete: null,
  waveBannerTimer: 0,
  waveBannerText: '',

  // 视差场景
  parallaxScene: null,

  init() {
    this.canvas = document.getElementById('battleCanvas');
    this.ctx = this.canvas.getContext('2d');
    this.resize();
    // 接入 LayoutMgr 统一防抖重算
    if (window.LayoutMgr) {
      LayoutMgr.onResize(() => this.resize());
    }
  },

  /**
   * 计算安全区像素值（CSS 像素）
   * 注意：在强制旋转模式下，安全区方向需要重新映射：
   *   竖屏左边（刘海）→ 横屏顶部
   *   竖屏右边 → 横屏底部
   *   竖屏顶部 → 横屏右边
   *   竖屏底部（home 指示条）→ 横屏左边
   */
  _getSafeAreaPx() {
    const styles = getComputedStyle(document.documentElement);
    const parsePx = (v) => {
      const m = (v || '0px').match(/([\d.]+)px/);
      return m ? parseFloat(m[1]) : 0;
    };
    const sat = parsePx(styles.getPropertyValue('--sat').trim());
    const sab = parsePx(styles.getPropertyValue('--sab').trim());
    const sal = parsePx(styles.getPropertyValue('--sal').trim());
    const sar = parsePx(styles.getPropertyValue('--sar').trim());

    let top, bottom, left, right;
    if (window.FullscreenMgr && FullscreenMgr.forceRotate) {
      // 强制旋转模式（竖屏→横屏）：
      // 容器顶部 ← 屏幕右侧 safe-area-inset-right
      // 容器底部 ← 屏幕左侧 safe-area-inset-left
      // 容器左侧 ← 屏幕顶部 safe-area-inset-top（刘海）
      // 容器右侧 ← 屏幕底部 safe-area-inset-bottom（home 条）
      top = sar;
      bottom = sal;
      left = sat;
      right = sab;
    } else {
      top = sat;
      bottom = sab;
      left = sal;
      right = sar;
    }

    // 额外底部预留：避开宿主"豆包工作生成"水印浮层（约 40-50px 高）
    bottom += 50;

    // 顶部额外预留：至少 8px 呼吸空间
    top = Math.max(top, 8);

    return { top, bottom, left, right };
  },

  resize() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    let cw = parent.offsetWidth;
    let ch = parent.offsetHeight;
    // 容器可能还没完成布局（尺寸为 0）→ 兜底，否则 scale=0 会让边界算成 NaN
    if (!cw || !ch) { cw = window.innerWidth || 1280; ch = window.innerHeight || 720; }

    this.cssW = cw;
    this.cssH = ch;

    // 画布物理像素 = CSS 尺寸 × devicePixelRatio
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.floor(cw * dpr));
    this.canvas.height = Math.max(1, Math.floor(ch * dpr));
    // ctx 按 dpr 缩放，这样绘制时仍用 CSS 像素坐标
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // 统一缩放比：按高度等比缩放，保证游戏画面不变形
    // 设计基准：1280 x 720
    this.scale = (ch / CONFIG.canvasHeight) || 1;

    // 逻辑宽度（按等比缩放后的水平游戏区域）
    // 超宽屏：逻辑宽度 > 1280，可以看到更多左右场景
    // 窄屏：逻辑宽度 < 1280，左右被裁切
    const logicalW = cw / this.scale;

    // 安全区（CSS 像素 → 逻辑像素）
    const safe = this._getSafeAreaPx();
    this.safeTop = safe.top / this.scale;
    this.safeBottom = safe.bottom / this.scale;

    // 玩法边界：基于安全可视区重新计算
    // 左/右边界：留出边距，保证角色不贴边
    const sideMargin = 60;
    this.leftBound = sideMargin;
    this.rightBound = Math.max(logicalW - sideMargin, CONFIG.canvasWidth - sideMargin);

    // 地面位置：在逻辑坐标系中保持 480（按高度等比缩放后，
    // 距底部 240 逻辑像素的比例与设计稿一致）
    this.groundY = 480;

    // offsetX：玩法区域在画布上的水平偏移（超宽屏时始终为 0，画面从左到右铺满）
    this.offsetX = 0;
  },
  
  start(bossId) {
    // 【问题4】切换场景前确保旧循环清理干净
    this.stop();

    // 【联机改造】回到战斗场地边界规则
    if (window.Player) Player.worldMode = false;

    GameState.battle.currentBossId = bossId;
    GameState.battle.paused = false;
    GameState.battle.combo = 0;
    GameState.battle.comboTimer = 0;

    this.mode = 'boss';
    this.enemies = [];
    this.enemyProjectiles = [];
    this.boss = null;
    this.parallaxScene = null;

    // 确保画布大小正确
    this.resize();
    
    // 重置玩家
    Player.reset();
    Player.groundY = this.groundY;
    Player.y = this.groundY;
    
    // 创建Boss
    this.boss = BossSys.createBoss(bossId);
    if (this.boss) this.boss.init();
    
    // 加载背景
    const bossData = CONFIG.bosses[bossId];
    this.bgImage = new Image();
    this.bgImage.src = bossData.bg;

    // 【问题三】启动视频背景（Boss房）
    this._tryPlayVideoBg(bossData.videoUrl || (CONFIG.sceneVideos && CONFIG.sceneVideos['boss' + bossId]));
    
    // UI
    document.getElementById('bossName').textContent = bossData.name;
    document.getElementById('bossStage').textContent = bossData.title;
    const bossHp = document.querySelector('.boss-hp-container');
    if (bossHp) bossHp.style.display = 'block';
    
    // 切换音乐
    AudioMgr.playBgm('boss');
    
    this.running = true;
    this.lastTime = performance.now();
    this.gameLoop();
    
    InputMgr.resetSkillPresses();
  },
  
  stop() {
    this.running = false;
    if (this.animFrame) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
    // 【问题三】退出战斗时停止视频背景
    if (window.VideoBgMgr) VideoBgMgr.stop();
    ParticleSys.clear();
  },
  
  gameLoop() {
    if (!this.running) return;

    try {
      const now = performance.now();
      let dt = (now - this.lastTime) / 1000;
      this.lastTime = now;

      // 限制dt防止跳帧
      dt = Math.min(dt, 0.05);

      if (!GameState.battle.paused) {
        this.update(dt);
      }

      this.draw();
    } catch (e) {
      console.error('[BattleSys] 帧错误，已跳过:', e);
    } finally {
      this.animFrame = requestAnimationFrame(() => this.gameLoop());
    }
  },
  
  update(dt) {
    // 时之眼时滞效果
    let timeMul = 1;
    if (Player.timeSlowMul !== undefined) {
      timeMul = Player.timeSlowMul;
    }
    const adt = dt * timeMul;
    
    // 减速效果（字祸魔典封印）
    if (Player.slowTimer && Player.slowTimer > 0) {
      Player.slowTimer -= dt;
    }
    
    // 震屏
    const shake = ScreenShake.update(dt);
    
    // 更新玩家
    Player.update(adt);
    
    // 应用减速
    if (Player.slowTimer && Player.slowTimer > 0) {
      // 减速通过在update中乘以系数实现，这里补充处理
    }
    
    // 边界
    Player.x = Utils.clamp(Player.x, this.leftBound, this.rightBound);
    
    // 更新Boss
    if (this.boss) {
      this.boss.update(dt);
      // 限制Boss位置
      this.boss.x = Utils.clamp(this.boss.x, this.leftBound + 50, this.rightBound - 50);
    }

    // 小怪战斗：更新敌人
    if (this.mode === 'wave') {
      for (const e of this.enemies) {
        e.update(dt, Player.x, Player.y);

        // 近战/冲撞伤害检测
        if (e.state !== 'dead' && e.def.damageType !== 'ranged') {
          const dist = Math.hypot(e.x - Player.x, (e.y - e.height / 2) - (Player.y - Player.height / 2));
          if (dist < e.width / 2 + Player.width / 2 && e.state === 'attack') {
            // 每0.5秒才扣一次血的简单处理（用hitFlash作为冷却）
            if (Player.hitFlash <= 0) {
              Player.takeDamage(e.attack);
            }
          }
        }
      }

      // 敌方弹幕更新
      this.enemyProjectiles = this.enemyProjectiles.filter(p => {
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.life -= dt;

        // 碰撞玩家
        const dist = Math.hypot(p.x - Player.x, p.y - (Player.y - Player.height / 2));
        if (dist < p.size + Player.width / 2) {
          Player.takeDamage(p.damage);
          if (window.ParticleSys) {
            ParticleSys.emit(p.x, p.y, 8, { color: p.color, size: 3, life: 0.3 });
          }
          return false;
        }

        return p.life > 0 && p.x > -100 && p.x < 2000 && p.y > -100 && p.y < 1000;
      });

      // 波次横幅计时
      if (this.waveBannerTimer > 0) this.waveBannerTimer -= dt;

      // 检测波次完成
      this._checkWaveComplete();
    }

    // 视差场景更新
    if (this.parallaxScene) {
      // 镜头轻微跟随玩家（更有 HD-2D 纵深感）
      const targetCamX = (Player.x - CONFIG.canvasWidth / 2) * 0.1;
      this.parallaxScene.update(dt, targetCamX, 0);
    }
    
    // 更新粒子
    ParticleSys.update(dt);
    
    // 连击计时
    if (GameState.battle.comboTimer > 0) {
      GameState.battle.comboTimer -= dt;
      if (GameState.battle.comboTimer <= 0) {
        GameState.battle.combo = 0;
        const comboEl = document.getElementById('comboDisplay');
        comboEl.classList.remove('active');
      }
    }
    
    // 更新UI
    this.updateHUD();
    this.updateSkillCD();
    
    // 更新技能范围指示器
    this.updateSkillIndicator();
  },
  
  draw() {
    const ctx = this.ctx;
    const cw = this.cssW;
    const ch = this.cssH;
    const s = this.scale;

    const shake = ScreenShake.update(0); // 取当前值

    ctx.save();
    ctx.clearRect(0, 0, cw, ch);

    // ===== 背景层：视差或 cover 铺满 =====
    if (this.parallaxScene) {
      this.parallaxScene.drawBackground(ctx, cw, ch);
    } else if (this.bgImage && this.bgImage.complete) {
      const imgRatio = this.bgImage.width / this.bgImage.height;
      const canvasRatio = cw / ch;
      let bw, bh, bx, by;
      if (imgRatio > canvasRatio) {
        bh = ch;
        bw = ch * imgRatio;
        bx = (cw - bw) / 2;
        by = 0;
      } else {
        bw = cw;
        bh = cw / imgRatio;
        bx = 0;
        by = (ch - bh) / 2;
      }
      ctx.globalAlpha = 0.9;
      ctx.drawImage(this.bgImage, bx, by, bw, bh);
      ctx.globalAlpha = 1;

      // 叠加暗化
      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
      ctx.fillRect(0, 0, cw, ch);
    } else {
      ctx.fillStyle = '#1a1030';
      ctx.fillRect(0, 0, cw, ch);
    }

    // ===== 游戏内容层：统一缩放，不变形 =====
    ctx.save();
    // 震屏偏移
    ctx.translate(shake.x * s, shake.y * s);
    // 缩放到游戏坐标（统一比例，按高度等比）
    ctx.scale(s, s);

    // 透视网格地面（HD-2D 纵深）
    this._drawGroundGrid(ctx);

    // 收集所有要绘制的实体，按 y 排序（前后遮挡）
    const entities = [];
    if (this.boss && this.boss.y < Player.y) {
      entities.push({ kind: 'boss', obj: this.boss, y: this.boss.y });
    }
    // 小怪
    if (this.mode === 'wave') {
      for (const e of this.enemies) {
        entities.push({ kind: 'enemy', obj: e, y: e.getSortY() });
      }
    }
    // 玩家
    entities.push({ kind: 'player', obj: Player, y: Player.y });
    // Boss 后半
    if (this.boss && this.boss.y >= Player.y) {
      entities.push({ kind: 'boss', obj: this.boss, y: this.boss.y });
    }

    // 按 y 从低到高排序（y 小的先画 = 在后面）
    entities.sort((a, b) => a.y - b.y);

    for (const ent of entities) {
      if (ent.kind === 'boss') ent.obj.draw(ctx);
      else if (ent.kind === 'enemy') ent.obj.draw(ctx);
      else if (ent.kind === 'player') ent.obj.draw(ctx);
    }

    // 敌方弹幕（小怪战）
    if (this.mode === 'wave') {
      for (const p of this.enemyProjectiles) {
        ctx.save();
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }

    // 粒子
    ParticleSys.draw(ctx);

    ctx.restore(); // 游戏内容层（scale + 震屏）

    // ===== 波次横幅（UI 层，不缩放） =====
    if (this.mode === 'wave' && this.waveBannerTimer > 0) {
      const alpha = Math.min(1, this.waveBannerTimer / 0.3);
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = 'bold 28px "Noto Serif SC", serif';
      ctx.shadowColor = '#000';
      ctx.shadowBlur = 10;
      ctx.fillStyle = '#fecaca';
      ctx.fillText(this.waveBannerText, cw / 2, ch / 3);
      ctx.restore();
    }

    ctx.restore(); // 最外层
  },

  /**
   * 绘制透视网格地面 + 地面暗化
   */
  _drawGroundGrid(ctx) {
    // 地面渐变暗化
    const grad = ctx.createLinearGradient(0, this.groundY + 10, 0, CONFIG.canvasHeight);
    grad.addColorStop(0, 'rgba(30, 27, 75, 0.3)');
    grad.addColorStop(1, 'rgba(10, 6, 21, 0.6)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, this.groundY + 10, this.rightBound + 100, CONFIG.canvasHeight - this.groundY - 10);

    // 透视网格
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.08)';
    ctx.lineWidth = 1;
    const horizonY = this.groundY - 50;
    const gridBottom = CONFIG.canvasHeight;
    const rows = 6;
    for (let i = 1; i <= rows; i++) {
      const t = i / rows;
      const y = this.groundY + Math.pow(t, 1.5) * (gridBottom - this.groundY);
      ctx.globalAlpha = 0.05 + t * 0.1;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.rightBound + 100, y);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  },
  
  updateHUD() {
    // 玩家血蓝
    const hpPct = (Player.hp / Player.maxHp) * 100;
    const mpPct = (Player.mp / Player.maxMp) * 100;
    
    document.getElementById('playerHpFill').style.width = `${hpPct}%`;
    document.getElementById('playerMpFill').style.width = `${mpPct}%`;
    document.getElementById('playerHpText').textContent = `${Math.ceil(Player.hp)}/${Player.maxHp}`;
    document.getElementById('playerMpText').textContent = `${Math.ceil(Player.mp)}/${Player.maxMp}`;
    
    // 经验
    const expNeed = GameState.getExpToNextLevel();
    const expPct = (GameState.player.exp / expNeed) * 100;
    document.getElementById('playerExpFill').style.width = `${expPct}%`;
    document.getElementById('playerExpText').textContent = `EXP ${GameState.player.exp}/${expNeed}`;
    
    // Boss血条
    if (this.boss) {
      const hpPct = Math.max(0, (this.boss.hp / this.boss.maxHp) * 100);
      document.getElementById('bossHpFill').style.width = `${hpPct}%`;
      
      // 阶段指示
      const phaseIndicator = document.getElementById('bossPhaseIndicator');
      if (this.boss.maxPhase > 1) {
        phaseIndicator.style.display = 'block';
        // 更新分段数
        phaseIndicator.style.background = `repeating-linear-gradient(
          90deg,
          transparent,
          transparent calc(${100/this.boss.maxPhase}% - 1px),
          rgba(0,0,0,0.5) calc(${100/this.boss.maxPhase}% - 1px),
          rgba(0,0,0,0.5) ${100/this.boss.maxPhase}%
        )`;
      } else {
        phaseIndicator.style.display = 'none';
      }
      
      document.getElementById('bossStage').textContent = 
        this.boss.maxPhase > 1 ? `第 ${this.boss.phase} 阶段 · ${this.boss.title}` : this.boss.title;
    }
    
    // 连击
    const comboEl = document.getElementById('comboDisplay');
    if (GameState.battle.combo > 2) {
      comboEl.classList.add('active');
      comboEl.innerHTML = `${GameState.battle.combo}<span class="combo-label">COMBO</span>`;
    }
  },
  
  updateSkillCD() {
    const skills = ['1', '2', '3', 'ult', 'dodge'];
    for (const s of skills) {
      const cdEl = document.getElementById(`skillCd${s === 'dodge' ? 'Dodge' : s === 'ult' ? 'Ult' : s}`);
      if (!cdEl) continue;
      const cd = Player.skillCd[s];
      if (cd > 0) {
        cdEl.style.display = 'flex';
        cdEl.textContent = cd.toFixed(1);
        // 顺时针遮罩效果（用conic-gradient模拟）
        const total = s === 'dodge' ? CONFIG.skills.dodge.cooldown : Player.getSkillCd(s);
        const progress = (total - cd) / total;
        cdEl.style.background = `conic-gradient(rgba(0,0,0,0.7) ${progress * 360}deg, rgba(0,0,0,0.3) 0deg)`;
      } else {
        cdEl.style.display = 'none';
      }
    }
  },
  
  damageBoss(dmg, isCrit = false, x = 0, y = 0) {
    if (!this.boss || this.boss.state === 'dead') return;
    
    // 虚空行者：假身不扣血
    // （简化：当前只有真身有boss实例，分身在data.clones里不扣血）
    
    this.boss.takeDamage(dmg, isCrit);

    // 打击音效
    AudioMgr.playRealSfx('hit');

    // 连击
    GameState.battle.combo++;
    GameState.battle.comboTimer = 2;
  },
  
  onPlayerDeath() {
    GameState.battle.combo = 0;
    setTimeout(() => {
      this.stop();
      SceneMgr.show('gameover');
    }, 1500);
  },
  
  onBossDeath() {
    AudioMgr.playSfx('victory');
    ScreenShake.shake(15, 0.8);
    
    // 击杀回蓝遗物
    Player.onKillEnemy();
    
    // 大量粒子
    ParticleSys.emit(this.boss.x, this.boss.y - this.boss.height/2, 50, {
      color: '#fbbf24', size: Utils.rand(4, 10), life: 1.5,
      vx: Utils.rand(-200, 200), vy: Utils.rand(-300, -50), gravity: 200,
    });
    
    setTimeout(() => {
      this.handleVictory();
    }, 2000);
  },
  
  handleVictory() {
    const bossId = GameState.battle.currentBossId;
    const bossData = CONFIG.bosses[bossId];
    const rewards = bossData.rewards;
    
    // 发放奖励
    GameState.player.gold += rewards.gold;
    GameState.player.star += rewards.star;
    const leveledUp = GameState.addExp(rewards.exp);
    
    // 获得遗物
    let droppedRelic = null;
    if (rewards.relic) {
      if (!GameState.player.relics.includes(rewards.relic)) {
        GameState.player.relics.push(rewards.relic);
        // 自动装备（如果有空位）
        if (GameState.player.equippedRelics.length < 3) {
          GameState.player.equippedRelics.push(rewards.relic);
        }
        droppedRelic = CONFIG.relics.find(r => r.id === rewards.relic);
      }
    }
    
    // 标记击败
    if (!GameState.player.defeatedBosses.includes(bossId)) {
      GameState.player.defeatedBosses.push(bossId);
    }
    
    // 解锁下一个Boss
    const nextBossId = bossId + 1;
    if (nextBossId <= 4 && !GameState.player.unlockedBosses.includes(nextBossId)) {
      GameState.player.unlockedBosses.push(nextBossId);
    }
    
    // 更新任务
    for (const q of GameState.player.quests) {
      if (q.bossId === bossId && !q.completed) {
        q.completed = true;
      }
    }
    
    // 保存
    GameState.save();
    
    // 更新胜利面板
    document.getElementById('victoryBoss').textContent = `击败 ${bossData.name}`;
    document.getElementById('rewardGold').textContent = `+${rewards.gold}`;
    document.getElementById('rewardStar').textContent = `+${rewards.star}`;
    document.getElementById('rewardExp').textContent = `+${rewards.exp}`;
    
    const dropEl = document.getElementById('rewardDrop');
    if (droppedRelic) {
      dropEl.classList.remove('hidden');
      document.getElementById('rewardItemName').textContent = droppedRelic.name;
    } else {
      dropEl.classList.add('hidden');
    }
    
    const levelUpEl = document.getElementById('levelUpNotice');
    if (leveledUp) {
      levelUpEl.classList.remove('hidden');
      document.getElementById('newLevel').textContent = GameState.player.level;
      AudioMgr.playSfx('levelup');
    } else {
      levelUpEl.classList.add('hidden');
    }
    
    this.stop();
    
    // 最终Boss：进入结局
    if (bossId === 4) {
      setTimeout(() => {
        SceneMgr.show('ending');
      }, 100);
    } else {
      SceneMgr.show('victory');
    }
  },
  
  showSkillIndicator(skillId) {
    const indicator = document.getElementById('skillIndicator');
    if (!indicator) return;
    indicator.classList.remove('hidden');
    indicator.dataset.skill = skillId;
    this.updateSkillIndicator();
  },
  
  updateSkillIndicator() {
    const indicator = document.getElementById('skillIndicator');
    if (!indicator || indicator.classList.contains('hidden')) return;

    const s = this.scale; // 统一缩放比
    const skillId = indicator.dataset.skill;

    if (skillId === '2') {
      // 虚空禁锢 - 圆形范围
      const radius = CONFIG.skills[2].radius * s;
      indicator.style.width = `${radius * 2}px`;
      indicator.style.height = `${radius * 2}px`;
      indicator.style.borderRadius = '50%';
      indicator.style.borderStyle = 'dashed';
      indicator.style.borderColor = 'rgba(168,85,247,0.6)';
      indicator.style.background = 'rgba(168,85,247,0.1)';

      let tx = Player.x + (InputMgr.joystick.x || Player.facing) * 180;
      let ty = Player.y + InputMgr.joystick.y * 60 - 40;

      indicator.style.left = `${tx * s - radius}px`;
      indicator.style.top = `${ty * s - radius}px`;
    } else if (skillId === '3') {
      // 空间切割 - 扇形（用圆形近似）
      const range = CONFIG.skills[3].range * s;
      indicator.style.width = `${range * 2}px`;
      indicator.style.height = `${range * 2}px`;
      indicator.style.borderRadius = '50%';
      indicator.style.borderStyle = 'dashed';
      indicator.style.borderColor = 'rgba(236,72,153,0.6)';
      indicator.style.background = 'rgba(236,72,153,0.1)';

      indicator.style.left = `${Player.x * s - range}px`;
      indicator.style.top = `${(Player.y - 40) * s - range}px`;
    }
  },
  
  hideSkillIndicator() {
    const indicator = document.getElementById('skillIndicator');
    if (indicator) indicator.classList.add('hidden');
  },
  
  pause() {
    GameState.battle.paused = true;
  },
  
  resume() {
    GameState.battle.paused = false;
    this.lastTime = performance.now();
  },

  // ---- 小怪战斗模式 ----

  startWaveBattle(scene, onComplete) {
    // 【问题4】切换前先清理旧循环
    this.stop();

    // 【联机改造】回到战斗场地边界规则
    if (window.Player) Player.worldMode = false;

    GameState.battle.paused = false;
    GameState.battle.combo = 0;
    GameState.battle.comboTimer = 0;

    this.mode = 'wave';
    this.boss = null;
    this.enemies = [];
    this.enemyProjectiles = [];
    this.currentWave = 0;
    this.waveData = scene.waves || [];
    this.onWaveComplete = onComplete;
    this.waveBannerTimer = 1.5;
    this.waveBannerText = scene.title || '遭遇战';

    // 确保画布大小正确
    this.resize();

    // 重置玩家
    Player.reset();
    Player.groundY = this.groundY;
    Player.y = this.groundY;

    // 加载背景（视差）
    this._initParallax(scene.bg);

    // 【问题三】启动视频背景（波次战场景）
    this._tryPlayVideoBg(scene.videoUrl || (CONFIG.sceneVideos && CONFIG.sceneVideos.courtyard));

    // 隐藏Boss血条UI
    const bossHp = document.getElementById('bossHpContainer') || document.querySelector('.boss-hp-container');
    if (bossHp) bossHp.style.display = 'none';

    // 切换音乐（波次战可由 scene.bgm 指定，默认主题曲 main）
    AudioMgr.playBgm(scene.bgm || 'main');

    // 先生成第一波，再启动主循环（否则首帧会在空数组时误判“波次已清空”，
    // 提前 1 秒把下一波叠加上来）
    this._wavePending = false;
    this._spawnWave(0);

    this.running = true;
    this.lastTime = performance.now();
    this.gameLoop();
  },

  _initParallax(bgUrl) {
    if (!window.ParallaxSys) return;
    this.parallaxScene = ParallaxSys.createScene([
      { url: bgUrl, speed: 0.1, alpha: 1 },
    ]);
    // 同时保留旧的 bgImage 作为 fallback
    this.bgImage = new Image();
    this.bgImage.src = bgUrl;
  },

  /**
   * 【问题三】尝试播放视频背景
   * 视频播放成功则 canvas 透出视频；失败/无URL则走原有静态背景
   */
  _tryPlayVideoBg(videoUrl) {
    if (!window.VideoBgMgr) return;
    const canvas = this.canvas || document.getElementById('battleCanvas');
    VideoBgMgr.play(videoUrl, () => {
      // 回退：恢复 canvas 原有背景绘制
      if (canvas) canvas.style.background = '';
    });
    if (videoUrl && canvas) {
      canvas.style.background = 'transparent';
    }
  },

  _spawnWave(waveIndex) {
    if (!this.waveData || waveIndex >= this.waveData.length) return;
    const wave = this.waveData[waveIndex];
    this.currentWave = waveIndex;
    this.waveBannerTimer = 1.2;
    this.waveBannerText = `第 ${waveIndex + 1} 波`;

    for (const def of wave) {
      const enemy = EnemySys.createEnemy(def.type, def.x, def.y || this.groundY);
      if (enemy) this.enemies.push(enemy);
    }
  },

  _checkWaveComplete() {
    if (this.mode !== 'wave') return;

    // 过滤掉已死亡且消失的敌人
    this.enemies = this.enemies.filter(e => !(e.state === 'dead' && e.deathTimer >= e.deathDuration));

    if (this.enemies.length !== 0) return;
    // 已在等待下一波/结算时直接返回，避免空窗期每帧重复调度、导致同波刷多次
    if (this._wavePending) return;
    this._wavePending = true;

    // 波次清空
    const next = this.currentWave + 1;
    if (next < this.waveData.length) {
      // 下一波
      setTimeout(() => {
        if (this.mode !== 'wave') return;
        this._wavePending = false;
        this._spawnWave(next);
      }, 1000);
    } else {
      // 全部完成
      this.waveBannerTimer = 2;
      this.waveBannerText = '战斗胜利！';
      setTimeout(() => {
        if (this.mode !== 'wave') return;
        this._wavePending = false;
        this.stop();
        if (this.onWaveComplete) {
          const cb = this.onWaveComplete;
          this.onWaveComplete = null;
          cb();
        }
      }, 1500);
    }
  },

  /**
   * 对小怪造成范围伤害（玩家技能调用）
   * 返回命中数
   */
  damageEnemiesInArea(x, y, radius, dmg, isCrit, hitFx) {
    let hits = 0;
    for (const e of this.enemies) {
      if (e.state === 'dead') continue;
      const dist = Math.hypot(e.x - x, (e.y - e.height / 2) - y);
      if (dist < radius + e.width / 2) {
        const killed = e.takeDamage(dmg, Player.x);
        const showDmg = isCrit ? Math.floor(dmg * CONFIG.playerBase.critDamage) : dmg;
        DamageNumberSys.show(e.x, e.y - e.height, showDmg, isCrit ? 'crit' : 'normal');
        hits++;
        if (killed) {
          // 掉落经验金币
          GameState.player.gold += e.def.gold || 0;
          GameState.addExp(e.def.xp || 10);
          Player.onKillEnemy();
          AudioMgr.playRealSfx('explosion', { volume: 0.4 });
        } else {
          AudioMgr.playRealSfx('hit', { volume: 0.6 });
        }
      }
    }
    return hits;
  },
};
