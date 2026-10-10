/* ==========================================================
   玩家系统
   ========================================================== */

const Player = {
  x: 600,
  y: 400,
  width: 80,
  height: 120,
  facing: 1, // 1右 -1左
  velocityY: 0,
  onGround: true,
  groundY: 480, // 地面Y坐标
  
  // 状态
  hp: 100,
  mp: 50,
  maxHp: 100,
  maxMp: 50,
  attack: 12,
  defense: 3,
  speed: 220,
  
  // 技能冷却
  skillCd: { 1: 0, 2: 0, 3: 0, ult: 0, attack: 0, dodge: 0 },
  
  // 状态标记
  state: 'idle', // idle, walk, attack, cast, hit, dead, invincible, ult
  worldMode: false, // 【联机世界模式】true 时不走战斗场地边界（由 WorldMgr 接管）
  stateTimer: 0,
  
  // 攻击连击
  comboIndex: 0,
  comboTimer: 0,
  attackCooldown: 0,
  
  // 闪避
  dodging: false,
  dodgeTimer: 0,
  dodgeDir: 1,
  
  // 无敌
  invincible: false,
  invincibleTimer: 0,
  hitInvincibleCd: 0,
  
  // 闪现代理残影
  afterimages: [],
  
  // 虚空禁锢技能的区域
  voidPrisons: [],
  
  // 空间切割效果
  spaceSlashes: [],
  
  // 大招领域
  ultimateField: null,
  
  // 受击闪白
  hitFlash: 0,
  
  // 暗影斗篷暴击标记
  dodgeCritReady: false,
  dodgeCritTimer: 0,
  
  // 图片资源（旧的立绘保留用于菜单/图鉴）
  imgIdle: null,
  imgBattle: null,

  // 精灵表动画（HD-2D）
  spriteSheet: null,
  animPlayer: null,
  spriteLoaded: false,

  // 渲染：角色脚底 Y（用于排序和阴影）
  // 跳跃高度（正 = 跳起）
  jumpY: 0, // 0 = 在地面
  jumpVy: 0,
  isJumping: false,

  init() {
    this.imgIdle = new Image();
    this.imgIdle.src = 'assets/img/heyun_idle.png';
    this.imgBattle = new Image();
    this.imgBattle.src = 'assets/img/heyun_fight.png';

    // 加载精灵表
    if (window.SpriteSys) {
      SpriteSys.loadSpriteSheet('assets/img/player_sheet.jpg', 6).then(sheet => {
        this.spriteSheet = sheet;
        this.animPlayer = new AnimPlayer(sheet);
        this.spriteLoaded = true;
        this._playIdle();
      }).catch(e => console.warn('player sprite load failed:', e));
    }

    this.reset();
  },

  // ---- 动画状态机 ----
  _playIdle() {
    if (!this.animPlayer) return;
    // idle：帧0呼吸循环（轻微缩放感觉）
    this.animPlayer.play([0, 0, 0, 0], { loop: true, fps: 2 });
  },

  _playRun() {
    if (!this.animPlayer) return;
    // 奔跑：帧1-2-3循环（迈右腿、腾空、迈左腿）
    this.animPlayer.play([1, 2, 3, 2], { loop: true, fps: 8, speedScale: 1 });
  },

  _playAttack(onComplete) {
    if (!this.animPlayer) { if (onComplete) onComplete(); return; }
    this.animPlayer.play([4], { loop: false, fps: 10, onComplete });
  },

  _playJump() {
    if (!this.animPlayer) return;
    this.animPlayer.play([5], { loop: false, fps: 8 });
  },

  _playHurt() {
    if (!this.animPlayer) return;
    this.animPlayer.play([0], { loop: false, fps: 4 });
  },
  
  reset() {
    const p = GameState.player;
    this.maxHp = p.maxHp;
    this.maxMp = p.maxMp;
    this.hp = this.maxHp;
    this.mp = this.maxMp;
    this.attack = p.attack;
    this.defense = p.defense;
    this.speed = p.speed;
    this.x = 200;
    this.y = this.groundY;
    this.facing = 1;
    this.state = 'idle';
    this.stateTimer = 0;
    this.skillCd = { 1: 0, 2: 0, 3: 0, ult: 0, attack: 0, dodge: 0 };
    this.comboIndex = 0;
    this.comboTimer = 0;
    this.attackCooldown = 0;
    this.dodging = false;
    this.invincible = false;
    this.invincibleTimer = 0;
    this.hitInvincibleCd = 0;
    this.afterimages = [];
    this.voidPrisons = [];
    this.spaceSlashes = [];
    this.ultimateField = null;
    this.hitFlash = 0;
    this.dodgeCritReady = false;
    this.dodgeCritTimer = 0;

    // 渲染状态
    this.jumpY = 0;
    this._animState = null;
  },
  
  // 获取技能实际冷却（考虑遗物）
  getSkillCd(skillId) {
    let cd = CONFIG.skills[skillId].cooldown;
    const lv = GameState.player.skillLevels[skillId] || 1;
    
    // 技能升级效果
    if (skillId === 1) cd -= (lv - 1) * 0.3;
    if (skillId === 2) {
      // 2技能升级主要加伤害，冷却不变
    }
    if (skillId === 3) {
      // 3技能升级加伤害和段数
    }
    if (skillId === 'ult') {
      // 大招升级加伤害和持续
    }
    
    // 遗物效果
    if (skillId === 1) {
      const mul = GameState.getRelicEffect('skill1CdMul');
      if (mul) cd *= mul;
    }
    
    return Math.max(0.5, cd);
  },
  
  // 获取技能伤害倍率
  getSkillDamageMul(skillId) {
    const lv = GameState.player.skillLevels[skillId] || 1;
    let mul = 1;
    
    switch(skillId) {
      case 'attack':
        if (lv >= 2) mul += 0.15;
        if (lv >= 3) mul += 0.15;
        if (lv >= 4) mul += 0.2;
        if (lv >= 5) mul += 0.2;
        if (lv >= 6) mul += 0.3;
        break;
      case 2:
        if (lv >= 2) mul += 0.2;
        if (lv >= 3) mul += 0.2;
        if (lv >= 5) mul += 0.3;
        break;
      case 3:
        if (lv >= 2) mul += 0.2;
        if (lv >= 4) mul += 0.2;
        if (lv >= 6) mul += 0.4;
        break;
      case 'ult':
        if (lv >= 2) mul += 0.25;
        if (lv >= 4) mul += 0.25;
        if (lv >= 6) mul += 0.5;
        break;
    }
    
    // 遗物
    if (skillId === 1) {
      const mul1 = GameState.getRelicEffect('skill1DmgMul');
      if (mul1) mul *= mul1;
    }
    
    return mul;
  },
  
  update(dt) {
    // 更新冷却
    for (const k in this.skillCd) {
      if (this.skillCd[k] > 0) this.skillCd[k] -= dt;
    }
    
    // MP恢复
    this.mp = Math.min(this.maxMp, this.mp + CONFIG.playerBase.mpRegen * dt);
    
    // 状态计时器
    if (this.stateTimer > 0) {
      this.stateTimer -= dt;
      if (this.stateTimer <= 0 && this.state !== 'idle' && this.state !== 'walk' && this.state !== 'dead') {
        this.state = 'idle';
      }
    }
    
    // 攻击冷却
    if (this.attackCooldown > 0) this.attackCooldown -= dt;
    if (this.comboTimer > 0) {
      this.comboTimer -= dt;
      if (this.comboTimer <= 0) this.comboIndex = 0;
    }
    
    // 无敌计时
    if (this.invincibleTimer > 0) {
      this.invincibleTimer -= dt;
      if (this.invincibleTimer <= 0) {
        this.invincible = false;
      }
    }
    
    // 受击无敌冷却
    if (this.hitInvincibleCd > 0) this.hitInvincibleCd -= dt;
    
    // 闪白
    if (this.hitFlash > 0) this.hitFlash -= dt;
    
    // 闪避
    if (this.dodging) {
      this.dodgeTimer -= dt;
      this.x += this.dodgeDir * 500 * dt;
      // 生成残影
      if (Math.random() < 0.5) {
        this.afterimages.push({
          x: this.x,
          y: this.y,
          facing: this.facing,
          life: 0.3,
          maxLife: 0.3,
        });
      }
      if (this.dodgeTimer <= 0) {
        this.dodging = false;
        this.invincible = false;
      }
    }
    
    // 暗影斗篷暴击计时
    if (this.dodgeCritTimer > 0) {
      this.dodgeCritTimer -= dt;
      if (this.dodgeCritTimer <= 0) this.dodgeCritReady = false;
    }
    
    // 移动速度倍率（减速/时滞等）
    let speedMul = 1;
    if (this.slowTimer && this.slowTimer > 0) {
      this.slowTimer -= dt;
      speedMul *= (this.slowAmount || 0.5);
    }
    if (this.timeSlowMul !== undefined) {
      speedMul *= this.timeSlowMul;
    }
    
    // 移动
    let moving = false;
    let moveSpeedRatio = 0;
    if (!this.dodging && this.state !== 'dead' && this.state !== 'attack' && this.state !== 'cast' && this.state !== 'ult' && this.state !== 'hit') {
      const moveX = InputMgr.joystick.x;
      const moveY = InputMgr.joystick.y;
      moveSpeedRatio = Math.hypot(moveX, moveY);

      if (moveX !== 0 || moveY !== 0) {
        moving = true;
        // 横版移动：左右为主，上下小幅度
        // 【联机世界模式】位移交由 WorldMgr 处理（世界尺寸远大于战斗场地）
        if (!this.worldMode) {
          const moveSpeed = this.speed * speedMul;
          this.x += moveX * moveSpeed * dt;
          this.y += moveY * moveSpeed * 0.5 * dt;
        }

        if (moveX > 0.1) this.facing = 1;
        else if (moveX < -0.1) this.facing = -1;

        if (this.state === 'idle') this.state = 'walk';
      } else {
        if (this.state === 'walk') this.state = 'idle';
      }
    }

    // 动画更新（状态机）
    if (this.animPlayer) {
      // 奔跑速度随移动速度变化
      if (this.state === 'walk' && moveSpeedRatio > 0) {
        this.animPlayer.speedScale = 0.6 + moveSpeedRatio * 0.8;
      } else {
        this.animPlayer.speedScale = 1;
      }

      // 状态切换时播放对应动画（避免每帧重复触发）
      if (this._animState !== this.state) {
        this._animState = this.state;
        switch (this.state) {
          case 'idle':
          case 'walk':
            if (moving || this.state === 'walk') this._playRun();
            else this._playIdle();
            break;
          case 'attack':
            this._playAttack(() => {
              // 攻击动画结束后自动回 idle/walk
              if (this.state === 'attack') this.state = 'idle';
            });
            break;
          case 'cast':
          case 'ult':
            this._playAttack(() => {
              if (this.state === 'cast' || this.state === 'ult') this.state = 'idle';
            });
            break;
          case 'hit':
            this._playHurt();
            break;
          case 'dead':
            this.animPlayer.stop();
            break;
        }
      }

      // 保持 run 动画在移动状态下
      if ((this.state === 'walk' || this.state === 'idle') && moving && !this.animPlayer.playing) {
        this._playRun();
      } else if (this.state === 'idle' && !moving && this._animState === 'idle' && !this.animPlayer.playing) {
        this._playIdle();
      }

      this.animPlayer.update(dt);
    }

    // 跳跃高度模拟（奔跑时微小上下起伏）
    if (this.state === 'walk' && moving) {
      // 奔跑时身体起伏 + 腾空帧时跳得更高
      const frame = this.animPlayer ? this.animPlayer.frameIndex : 0;
      const isAirFrame = frame === 1 || frame === 3; // 迈腿帧有轻微离地
      this.jumpY = isAirFrame ? 6 : 2;
    } else {
      this.jumpY = 0;
    }
    
    // 边界限制（优先使用 BattleSys 的动态边界，适配超宽屏）
    // 【联机世界模式】边界由 WorldMgr 按世界尺寸处理
    if (!this.worldMode) {
      const left = (window.BattleSys && BattleSys.leftBound !== undefined) ? BattleSys.leftBound : 50;
      const right = (window.BattleSys && BattleSys.rightBound !== undefined) ? BattleSys.rightBound : CONFIG.canvasWidth - 50;
      this.x = Utils.clamp(this.x, left, right);
      this.y = Utils.clamp(this.y, this.groundY - 120, this.groundY + 20);
    }
    
    // 更新残影
    this.afterimages = this.afterimages.filter(a => {
      a.life -= dt;
      return a.life > 0;
    });
    
    // 更新虚空禁锢
    this.voidPrisons = this.voidPrisons.filter(p => {
      p.life -= dt;
      p.tickTimer -= dt;
      if (p.tickTimer <= 0) {
        p.tickTimer = 0.3;
        // 造成持续伤害
        const dmg = Math.floor(CONFIG.skills[2].damage * 0.25 * this.getSkillDamageMul(2));
        if (BattleSys.boss && Utils.circleCollide(p.x, p.y, p.radius, BattleSys.boss.x, BattleSys.boss.y, BattleSys.boss.width/2)) {
          BattleSys.damageBoss(dmg, false, p.x, p.y - 20);
        }
      }
      return p.life > 0;
    });
    
    // 更新空间切割
    this.spaceSlashes = this.spaceSlashes.filter(s => {
      s.life -= dt;
      return s.life > 0;
    });
    
    // 更新大招领域
    if (this.ultimateField) {
      this.ultimateField.life -= dt;
      this.ultimateField.tickTimer -= dt;
      if (this.ultimateField.tickTimer <= 0) {
        this.ultimateField.tickTimer = 0.4;
        const dmg = Math.floor(CONFIG.skills.ult.damage * this.getSkillDamageMul('ult'));
        if (BattleSys.boss && Utils.circleCollide(
          this.ultimateField.x, this.ultimateField.y, this.ultimateField.radius,
          BattleSys.boss.x, BattleSys.boss.y, BattleSys.boss.width/2
        )) {
          BattleSys.damageBoss(dmg, false, this.ultimateField.x, BattleSys.boss.y - 30);
          // 烛九阴鳞片灼烧
          if (GameState.getRelicEffect('ultBurn')) {
            BattleSys.boss.burning = true;
            BattleSys.boss.burnTimer = GameState.getRelicEffect('burnDuration') || 3;
          }
        }
        // 粒子
        ParticleSys.emit(
          this.ultimateField.x + Utils.rand(-this.ultimateField.radius, this.ultimateField.radius),
          this.ultimateField.y + Utils.rand(-this.ultimateField.radius, this.ultimateField.radius),
          3,
          { color: '#7c3aed', size: Utils.rand(3, 8), life: 0.5 }
        );
      }
      if (this.ultimateField.life <= 0) {
        this.ultimateField = null;
        // 震屏结束
        ScreenShake.shake(10, 0.3);
      }
    }
    
    // 处理技能输入
    this.handleInput(dt);

    // 坐标自愈：任何原因产生的 NaN/Infinity 都立即修正，避免"角色卡死"
    if (!isFinite(this.x)) this.x = (window.CONFIG ? CONFIG.canvasWidth / 2 : 640);
    if (!isFinite(this.y)) this.y = isFinite(this.groundY) ? this.groundY : 480;
  },
  
  handleInput(dt) {
    if (this.state === 'dead') return;
    
    // 普攻
    if (InputMgr.consumeSkill('attack') && this.attackCooldown <= 0) {
      this.doAttack();
    }
    
    // 技能1：虚空闪现
    if (InputMgr.consumeSkill(1) && this.skillCd[1] <= 0 && this.mp >= CONFIG.skills[1].mpCost) {
      this.doVoidDash();
    }
    
    // 技能2：虚空禁锢
    if (InputMgr.consumeSkill(2) && this.skillCd[2] <= 0 && this.mp >= CONFIG.skills[2].mpCost) {
      this.doVoidPrison();
    }
    
    // 技能3：空间切割
    if (InputMgr.consumeSkill(3) && this.skillCd[3] <= 0 && this.mp >= CONFIG.skills[3].mpCost) {
      this.doSpaceSlash();
    }
    
    // 大招
    if (InputMgr.consumeSkill('ult') && this.skillCd['ult'] <= 0 && this.mp >= CONFIG.skills.ult.mpCost) {
      this.doUltimate();
    }
    
    // 闪避
    if (InputMgr.consumeSkill('dodge') && this.skillCd['dodge'] <= 0) {
      this.doDodge();
    }
  },
  
  doAttack() {
    this.mp = Math.max(0, this.mp - CONFIG.skills.attack.mpCost);
    this.attackCooldown = 0.35;
    this.state = 'attack';
    this.stateTimer = 0.25;
    this.comboIndex = (this.comboIndex % 3) + 1;
    this.comboTimer = 0.8;
    
    const baseDmg = Math.floor(CONFIG.skills.attack.damage * (1 + this.comboIndex * 0.2) * this.getSkillDamageMul('attack'));
    const range = CONFIG.skills.attack.range;
    const hitX = this.x + this.facing * range / 2;
    const isCrit = this.dodgeCritReady || Math.random() < CONFIG.playerBase.critRate;
    if (this.dodgeCritReady && isCrit) this.dodgeCritReady = false;
    const dmg = isCrit ? Math.floor(baseDmg * CONFIG.playerBase.critDamage) : baseDmg;

    let hit = false;

    // 检测命中Boss
    if (BattleSys.boss) {
      const boss = BattleSys.boss;
      const inRange = Math.abs(boss.x - hitX) < range / 2 + boss.width / 2 &&
                      Math.abs(boss.y - this.y) < 80;
      if (inRange) {
        BattleSys.damageBoss(dmg, isCrit, boss.x, boss.y - boss.height / 2);
        hit = true;

        // 言灵残页追击
        const runeChance = GameState.getRelicEffect('attackRuneChance');
        if (runeChance && Math.random() < runeChance) {
          const runeDmg = Math.floor(dmg * (GameState.getRelicEffect('attackRuneDamage') || 0.5));
          setTimeout(() => {
            if (BattleSys.boss) BattleSys.damageBoss(runeDmg, false, boss.x + 20, boss.y - boss.height/2 - 10);
          }, 150);
        }
      }
    }

    // 检测命中小怪（范围攻击）
    if (BattleSys.mode === 'wave' && BattleSys.enemies.length > 0) {
      const hits = BattleSys.damageEnemiesInArea(hitX, this.y - 40, range / 2 + 20, dmg, isCrit, true);
      if (hits > 0) hit = true;
    }

    if (hit) {
      AudioMgr.playRealSfx('hit');
    } else {
      // 挥空也有轻量音效
      AudioMgr.playSfx('dodge');
    }
    ParticleSys.burst(this.x + this.facing * 40, this.y - 40, this.facing > 0 ? 0 : Math.PI, 0.5, 5, {
      color: '#a855f7', size: 3, life: 0.3, speed: 100,
    });
  },
  
  doVoidDash() {
    this.skillCd[1] = this.getSkillCd(1);
    this.mp -= CONFIG.skills[1].mpCost;
    this.state = 'cast';
    this.stateTimer = 0.2;
    this.invincible = true;
    this.invincibleTimer = 0.3;
    
    // 位移
    const dashDist = CONFIG.skills[1].range;
    let dx = InputMgr.joystick.x;
    let dy = InputMgr.joystick.y;
    if (dx === 0 && dy === 0) { dx = this.facing; dy = 0; }
    
    // 【问题二】位移后更新朝向：位移方向就是新的 facing
    if (dx > 0.1) this.facing = 1;
    else if (dx < -0.1) this.facing = -1;
    
    const startX = this.x;
    const startY = this.y;
    this.x += dx * dashDist;
    this.y += dy * dashDist * 0.5;
    
    // 生成残影与空间裂痕粒子
    for (let i = 0; i < 5; i++) {
      const t = i / 5;
      this.afterimages.push({
        x: startX + (this.x - startX) * t,
        y: startY + (this.y - startY) * t,
        facing: this.facing,
        life: 0.4 - t * 0.2,
        maxLife: 0.4,
      });
    }
    
    ParticleSys.emit(startX, startY, 15, {
      color: '#a855f7', size: Utils.rand(2, 6), life: 0.6,
      vx: Utils.rand(-80, 80), vy: Utils.rand(-40, 40),
    });
    
    AudioMgr.playSfx('dash');
  },
  
  doVoidPrison() {
    this.skillCd[2] = this.getSkillCd(2);
    this.mp -= CONFIG.skills[2].mpCost;
    this.state = 'cast';
    this.stateTimer = 0.35;
    
    // 在目标位置展开（摇杆方向前方，无摇杆则朝当前facing）
    const range = 180;
    let dirX = InputMgr.joystick.x;
    let dirY = InputMgr.joystick.y;
    if (dirX === 0 && dirY === 0) { dirX = this.facing; dirY = 0; }
    
    // 【问题二】释放技能时同步更新朝向（有水平输入就按输入方向，无则保持facing）
    if (dirX > 0.1) this.facing = 1;
    else if (dirX < -0.1) this.facing = -1;
    
    const targetX = this.x + dirX * range;
    const targetY = this.y + dirY * range * 0.3;
    
    const lv = GameState.player.skillLevels[2] || 1;
    let duration = CONFIG.skills[2].duration;
    let radius = CONFIG.skills[2].radius;
    if (lv >= 4) duration += 0.5;
    if (lv >= 6) radius *= 1.3;
    
    this.voidPrisons.push({
      x: targetX,
      y: targetY,
      radius: radius,
      life: duration,
      maxLife: duration,
      tickTimer: 0.3,
    });
    
    // 初始伤害（Boss）
    const dmg = Math.floor(CONFIG.skills[2].damage * this.getSkillDamageMul(2));
    if (BattleSys.boss && Utils.circleCollide(targetX, targetY, radius, BattleSys.boss.x, BattleSys.boss.y, BattleSys.boss.width/2)) {
      BattleSys.damageBoss(dmg, false, BattleSys.boss.x, BattleSys.boss.y - BattleSys.boss.height/2);
      // 定身效果
      BattleSys.boss.stunned = true;
      BattleSys.boss.stunTimer = duration;
    }

    // 初始伤害（小怪）
    if (BattleSys.mode === 'wave') {
      BattleSys.damageEnemiesInArea(targetX, targetY, radius, dmg, false);
    }
    
    AudioMgr.playSfx('skill');
    ParticleSys.emit(targetX, targetY, 20, {
      color: '#7c3aed', size: Utils.rand(3, 8), life: 0.8,
      vx: Utils.rand(-60, 60), vy: Utils.rand(-60, 60), gravity: 0,
    });
    
    ScreenShake.shake(4, 0.2);
  },
  
  doSpaceSlash() {
    this.skillCd[3] = this.getSkillCd(3);
    this.mp -= CONFIG.skills[3].mpCost;
    this.state = 'cast';
    this.stateTimer = 0.4;
    
    const lv = GameState.player.skillLevels[3] || 1;
    let hits = CONFIG.skills[3].hits;
    if (lv >= 3) hits += 1;
    if (lv >= 5) hits += 1;
    
    const angle = this.facing > 0 ? 0 : Math.PI;
    const range = CONFIG.skills[3].range;
    const dmgPerHit = Math.floor(CONFIG.skills[3].damage / CONFIG.skills[3].hits * this.getSkillDamageMul(3));
    
    // 创建多道斩击效果
    for (let i = 0; i < hits; i++) {
      setTimeout(() => {
        if (GameState.currentScene !== 'battle') return;
        const offsetAngle = angle + Utils.rand(-0.3, 0.3);
        const dist = Utils.rand(60, range);
        const slashX = this.x + Math.cos(offsetAngle) * dist;
        const slashY = this.y - 40 + Math.sin(offsetAngle) * dist * 0.3;
        
        this.spaceSlashes.push({
          x: slashX,
          y: slashY,
          angle: offsetAngle,
          life: 0.25,
          maxLife: 0.25,
          length: 80,
        });
        
        // 伤害检测（Boss）
        if (BattleSys.boss) {
          const boss = BattleSys.boss;
          const hitAngle = Utils.angleBetween(this.x, this.y - 40, boss.x, boss.y);
          let angDiff = hitAngle - angle;
          while (angDiff > Math.PI) angDiff -= Math.PI * 2;
          while (angDiff < -Math.PI) angDiff += Math.PI * 2;
          const dist2 = Utils.dist(this.x, this.y - 40, boss.x, boss.y);
          if (dist2 < range && Math.abs(angDiff) < CONFIG.skills[3].angle * Math.PI / 180 / 2) {
            BattleSys.damageBoss(dmgPerHit, false, boss.x + Utils.rand(-20, 20), boss.y - boss.height/2);
          }
        }

        // 伤害检测（小怪）
        if (BattleSys.mode === 'wave') {
          BattleSys.damageEnemiesInArea(slashX, slashY, 40, dmgPerHit, false);
        }
        
        ParticleSys.burst(slashX, slashY, offsetAngle, 1, 6, {
          color: '#ec4899', size: 3, life: 0.3, speed: 150,
        });
      }, i * 100);
    }
    
    AudioMgr.playSfx('skill');
    ScreenShake.shake(3, 0.15);
  },
  
  doUltimate() {
    this.skillCd['ult'] = this.getSkillCd('ult');
    this.mp -= CONFIG.skills.ult.mpCost;
    this.state = 'ult';
    this.stateTimer = 1;
    
    const lv = GameState.player.skillLevels['ult'] || 1;
    let duration = CONFIG.skills.ult.duration;
    let radius = CONFIG.skills.ult.radius;
    if (lv >= 3) duration += 1;
    if (lv >= 5) radius *= 1.3;
    
    this.ultimateField = {
      x: this.x,
      y: this.y - 40,
      radius: radius,
      life: duration,
      maxLife: duration,
      tickTimer: 0.4,
    };
    
    AudioMgr.playRealSfx('explosion', { volume: 0.8 });
    ScreenShake.shake(8, duration);
    
    // 初始大爆发粒子
    ParticleSys.emit(this.x, this.y - 40, 50, {
      color: '#7c3aed', size: Utils.rand(4, 12), life: 1,
      vx: Utils.rand(-200, 200), vy: Utils.rand(-200, 200),
    });
  },
  
  doDodge() {
    this.skillCd['dodge'] = CONFIG.skills.dodge.cooldown;
    this.dodging = true;
    this.dodgeTimer = CONFIG.skills.dodge.duration;
    this.invincible = true;
    // 【问题二】闪避方向：优先用摇杆水平方向，否则用当前facing；闪避后同步更新朝向
    const jx = InputMgr.joystick.x;
    this.dodgeDir = jx > 0.1 ? 1 : (jx < -0.1 ? -1 : this.facing);
    if (jx > 0.1) this.facing = 1;
    else if (jx < -0.1) this.facing = -1;
    
    // 暗影斗篷：闪避后暴击
    if (GameState.getRelicEffect('dodgeCrit')) {
      this.dodgeCritReady = true;
      this.dodgeCritTimer = GameState.getRelicEffect('dodgeCritDuration') || 3;
    }
    
    AudioMgr.playSfx('dash');
  },
  
  takeDamage(dmg) {
    if (this.invincible || this.state === 'dead') return false;
    
    const actualDmg = Math.max(1, dmg - this.defense);
    this.hp -= actualDmg;
    this.hitFlash = 0.15;
    this.state = 'hit';
    this.stateTimer = 0.2;
    
    DamageNumberSys.show(this.x, this.y - this.height, actualDmg, 'normal');
    AudioMgr.playSfx('hurt');
    ScreenShake.shake(5, 0.2);
    
    // 巫贤护符：受击后无敌
    if (this.hitInvincibleCd <= 0) {
      const invincibleDur = GameState.getRelicEffect('hitInvincible');
      if (invincibleDur) {
        this.invincible = true;
        this.invincibleTimer = invincibleDur;
        this.hitInvincibleCd = GameState.getRelicEffect('hitInvincibleCd') || 10;
      }
    }
    
    if (this.hp <= 0) {
      this.hp = 0;
      this.state = 'dead';
      BattleSys.onPlayerDeath();
    }
    
    return true;
  },
  
  // 击杀回复（Boss死亡时调用）
  onKillEnemy() {
    const restore = GameState.getRelicEffect('killMpRestore');
    if (restore) {
      this.mp = Math.min(this.maxMp, this.mp + this.maxMp * restore);
    }
  },
  
  draw(ctx) {
    // 画残影
    for (const a of this.afterimages) {
      const alpha = a.life / a.maxLife * 0.6;
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(a.x, a.y);
      ctx.scale(a.facing, 1);

      if (this.spriteLoaded && this.animPlayer) {
        const frame = this.animPlayer.getCurrentFrame();
        if (frame) {
          ctx.drawImage(frame, -this.width/2, -this.height, this.width, this.height);
        }
      } else {
        const img = this.state === 'attack' || this.state === 'cast' ? this.imgBattle : this.imgIdle;
        if (img && img.complete) {
          const iw = this.width;
          const ih = this.height * 1.3;
          ctx.drawImage(img, -iw/2, -ih, iw, ih);
        }
      }
      ctx.restore();
    }
    
    // 画虚空禁锢
    for (const p of this.voidPrisons) {
      const alpha = p.life / p.maxLife;
      ctx.save();
      ctx.globalAlpha = alpha * 0.6;
      // 外圈
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 3;
      ctx.shadowColor = '#c084fc';
      ctx.shadowBlur = 15;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.stroke();
      // 内部网格
      ctx.globalAlpha = alpha * 0.2;
      ctx.fillStyle = '#7c3aed';
      ctx.fill();
      // 符文
      ctx.globalAlpha = alpha * 0.8;
      ctx.strokeStyle = '#c084fc';
      ctx.lineWidth = 1;
      for (let i = 0; i < 6; i++) {
        const angle = (i / 6) * Math.PI * 2 + performance.now() / 1000;
        const r = p.radius * 0.7;
        ctx.beginPath();
        ctx.moveTo(p.x + Math.cos(angle) * r, p.y + Math.sin(angle) * r);
        ctx.lineTo(p.x + Math.cos(angle + Math.PI) * r, p.y + Math.sin(angle + Math.PI) * r);
        ctx.stroke();
      }
      ctx.restore();
    }
    
    // 画空间斩击
    for (const s of this.spaceSlashes) {
      const alpha = s.life / s.maxLife;
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.translate(s.x, s.y);
      ctx.rotate(s.angle);
      ctx.strokeStyle = '#ec4899';
      ctx.lineWidth = 4;
      ctx.shadowColor = '#f472b6';
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.moveTo(-s.length/2, -20);
      ctx.lineTo(s.length/2, 20);
      ctx.stroke();
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(-s.length/2 + 10, 0);
      ctx.lineTo(s.length/2 - 10, 40);
      ctx.stroke();
      ctx.restore();
    }
    
    // 画大招领域
    if (this.ultimateField) {
      const f = this.ultimateField;
      const alpha = Math.min(1, f.life / 0.5) * Math.min(1, (f.maxLife - f.life) / 0.5 + 0.3);
      ctx.save();
      ctx.globalAlpha = alpha * 0.5;
      // 外圈
      const grad = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, f.radius);
      grad.addColorStop(0, 'rgba(76, 29, 149, 0.8)');
      grad.addColorStop(0.7, 'rgba(49, 46, 129, 0.5)');
      grad.addColorStop(1, 'rgba(30, 27, 75, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.radius, 0, Math.PI * 2);
      ctx.fill();
      // 边缘
      ctx.globalAlpha = alpha * 0.8;
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 3;
      ctx.shadowColor = '#c084fc';
      ctx.shadowBlur = 20;
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    
    // 画玩家（精灵帧优先，加载失败则回退到立绘）
    if (this.state === 'dead') {
      ctx.save();
      ctx.globalAlpha = 0.5;
      ctx.translate(this.x, this.y);
      ctx.rotate(this.facing > 0 ? Math.PI / 2 : -Math.PI / 2);
      const img = this.imgBattle;
      if (img && img.complete) {
        const iw = this.width;
        const ih = this.height * 1.3;
        ctx.drawImage(img, -iw/2, -ih, iw, ih);
      }
      ctx.restore();
      return;
    }

    // ---- 脚底阴影（在角色之前绘制，产生接地感） ----
    this._drawShadow(ctx);

    ctx.save();
    // 角色 y 减去跳跃高度（正 = 上升）
    const drawY = this.y - this.jumpY;
    ctx.translate(this.x, drawY);
    ctx.scale(this.facing, 1);

    // 无敌闪烁
    if (this.invincible && Math.floor(performance.now() / 80) % 2 === 0) {
      ctx.globalAlpha = 0.5;
    }

    // 环境光：脚底轻微染色
    // （通过叠加一层底部颜色实现）

    if (this.spriteLoaded && this.animPlayer) {
      // 精灵帧绘制
      const frame = this.animPlayer.getCurrentFrame();
      if (frame) {
        const fw = this.width;
        const fh = this.height;

        if (this.hitFlash > 0) {
          // 闪白效果
          ctx.globalCompositeOperation = 'source-over';
          ctx.drawImage(frame, -fw/2, -fh, fw, fh);
          ctx.globalCompositeOperation = 'lighter';
          ctx.globalAlpha = Math.min(1, this.hitFlash / 0.15) * 0.8;
          ctx.filter = 'brightness(3)';
          ctx.drawImage(frame, -fw/2, -fh, fw, fh);
          ctx.filter = 'none';
          ctx.globalCompositeOperation = 'source-over';
        } else {
          ctx.drawImage(frame, -fw/2, -fh, fw, fh);
        }
      }
    } else {
      // 回退到立绘
      let bobY = 0;
      if (this.state === 'walk') {
        bobY = Math.sin(performance.now() / 150) * 3;
      }
      ctx.translate(0, bobY);

      const img = (this.state === 'attack' || this.state === 'cast' || this.state === 'ult') ? this.imgBattle : this.imgIdle;
      if (img && img.complete) {
        const iw = this.width;
        const ih = this.height * 1.3;

        if (this.hitFlash > 0) {
          ctx.globalCompositeOperation = 'source-over';
          ctx.drawImage(img, -iw/2, -ih, iw, ih);
          ctx.globalCompositeOperation = 'lighter';
          ctx.globalAlpha = this.hitFlash / 0.15 * 0.8;
          ctx.filter = 'brightness(3)';
          ctx.drawImage(img, -iw/2, -ih, iw, ih);
          ctx.filter = 'none';
          ctx.globalCompositeOperation = 'source-over';
        } else {
          ctx.drawImage(img, -iw/2, -ih, iw, ih);
        }
      }
    }

    ctx.restore();

    // 暗影斗篷暴击标记
    if (this.dodgeCritReady) {
      ctx.save();
      ctx.fillStyle = '#fbbf24';
      ctx.shadowColor = '#fbbf24';
      ctx.shadowBlur = 10;
      ctx.font = 'bold 14px serif';
      ctx.textAlign = 'center';
      ctx.fillText('暴击', this.x, this.y - this.height - 10 - this.jumpY);
      ctx.restore();
    }
  },

  /**
   * 绘制脚底动态椭圆阴影
   * 站立时大而深，跳起时缩小变淡
   */
  _drawShadow(ctx) {
    const shadowScale = Math.max(0.3, 1 - this.jumpY / 60);
    const shadowAlpha = 0.4 * shadowScale;
    const shadowW = this.width * 0.7 * shadowScale;
    const shadowH = 8 * shadowScale;

    ctx.save();
    ctx.translate(this.x, this.y + 2);
    ctx.globalAlpha = shadowAlpha;

    const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, shadowW / 2);
    grad.addColorStop(0, 'rgba(0, 0, 0, 0.6)');
    grad.addColorStop(0.7, 'rgba(0, 0, 0, 0.3)');
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(0, 0, shadowW / 2, shadowH, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  },
};
