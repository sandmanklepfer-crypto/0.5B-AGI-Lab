/* ==========================================================
   Boss系统 - 四个Boss各有独特机制
   ========================================================== */

const BossSys = {
  // Boss实例由BattleSys管理
  createBoss(id) {
    const data = CONFIG.bosses[id];
    if (!data) return null;
    
    return {
      id: id,
      name: data.name,
      title: data.title,
      maxHp: data.maxHp,
      hp: data.maxHp,
      attack: data.attack,
      speed: data.speed,
      width: 130,
      height: 170,
      x: 900,
      y: 480,
      facing: -1,
      state: 'idle', // idle, attack, hit, stunned, dead
      stateTimer: 0,
      phase: 1,
      maxPhase: data.phases,
      sprite: data.sprite,
      img: null,
      
      // 通用技能计时
      attackCooldown: 2,
      specialCd: 5,
      
      // 受击闪白
      hitFlash: 0,

      // 【问题二】动画计时（伪动画：呼吸缩放、攻击前冲、受击挤压）
      _animT: 0,
      _attackAnimT: 0,
      _hurtAnimT: 0,
      
      // 定身
      stunned: false,
      stunTimer: 0,
      
      // 灼烧
      burning: false,
      burnTimer: 0,
      burnTick: 0,
      
      // 登场动画
      introTimer: 1.5,
      
      // Boss特有数据
      data: {},
      
      // 初始化Boss特有数据
      init() {
        this.img = new Image();
        this.img.src = data.sprite;
        
        switch(id) {
          case 1: // 虚空行者
            this.data = {
              clones: [], // 镜像分身
              blackHole: null, // 虚空黑洞
              teleportCd: 4,
              cloneCd: 8,
              blackHoleCd: 6,
            };
            break;
          case 2: // 熔雷巨像
            this.data = {
              slamCd: 4,
              slamWarn: 0, // 预警时间
              slamPos: { x: 0, y: 0 },
              projectileCd: 2.5,
              shockwaveCd: 6,
              shockwaveActive: false,
              shockwaveTimer: 0,
            };
            break;
          case 3: // 字祸魔典
            this.data = {
              runeVolleyCd: 3,
              sealThrowCd: 5,
              pageCyclone: false,
              cycloneCd: 8,
              cycloneTimer: 0,
            };
            break;
          case 4: // 时之眼
            this.data = {
              // 一阶段
              chainSweepCd: 4,
              runeRingCd: 3,
              // 二阶段
              timeSlowCd: 20,
              timeSlowTimer: 0,
              timeSlowActive: false,
              timeRewindActive: false,
              // 三阶段
              laserCd: 5,
              laserActive: false,
              laserAngle: 0,
              laserTimer: 0,
              arenaShrink: 0,
            };
            break;
        }
      },
      
      update(dt) {
        if (this.state === 'dead') return;
        
        // 登场动画
        if (this.introTimer > 0) {
          this.introTimer -= dt;
          return;
        }
        
        // 闪白
        if (this.hitFlash > 0) this.hitFlash -= dt;

        // 【问题二】动画计时
        this._animT += dt;
        if (this.state === 'attack' && this._attackAnimT < 0.9) {
          // 刚进入攻击态时激活动画峰值
          this._attackAnimT = 1;
        } else if (this._attackAnimT > 0) {
          this._attackAnimT = Math.max(0, this._attackAnimT - dt * 2.5);
        }
        if (this._hurtAnimT > 0) this._hurtAnimT = Math.max(0, this._hurtAnimT - dt * 4);
        
        // 灼烧
        if (this.burning) {
          this.burnTimer -= dt;
          this.burnTick -= dt;
          if (this.burnTick <= 0) {
            this.burnTick = 0.5;
            const burnDmg = Math.floor(Player.attack * (GameState.getRelicEffect('burnDmgPerTick') || 0.05));
            this.hp -= burnDmg;
            DamageNumberSys.show(this.x, this.y - this.height, burnDmg, 'boss');
          }
          if (this.burnTimer <= 0) this.burning = false;
        }
        
        // 定身
        if (this.stunned) {
          this.stunTimer -= dt;
          if (this.stunTimer <= 0) this.stunned = false;
          this.state = 'stunned';
          return;
        }
        
        // 阶段检测
        this.checkPhase();
        
        // 更新Boss特有AI
        switch(id) {
          case 1: this.updateVoidWalker(dt); break;
          case 2: this.updateMagmaThunder(dt); break;
          case 3: this.updateGrimoire(dt); break;
          case 4: this.updateTimeEye(dt); break;
        }
        
        // 朝玩家
        if (this.state === 'idle') {
          this.facing = Player.x < this.x ? -1 : 1;
        }
        
        // 状态计时
        if (this.stateTimer > 0) {
          this.stateTimer -= dt;
          if (this.stateTimer <= 0 && this.state !== 'idle' && this.state !== 'dead') {
            this.state = 'idle';
          }
        }
      },
      
      checkPhase() {
        const hpRatio = this.hp / this.maxHp;
        let newPhase = 1;
        if (this.maxPhase >= 2 && hpRatio < 0.5) newPhase = 2;
        if (this.maxPhase >= 3 && hpRatio < 0.25) newPhase = 3;
        
        if (newPhase > this.phase) {
          this.phase = newPhase;
          this.onPhaseChange();
        }
      },
      
      onPhaseChange() {
        // 阶段转换特效
        ScreenShake.shake(8, 0.5);
        ParticleSys.emit(this.x, this.y - this.height / 2, 30, {
          color: '#f87171', size: Utils.rand(3, 8), life: 1,
          vx: Utils.rand(-150, 150), vy: Utils.rand(-150, 150),
        });
        
        // 时之眼阶段转换特殊处理
        if (id === 4) {
          if (this.phase === 2) {
            this.data.timeSlowCd = 12;
          } else if (this.phase === 3) {
            this.data.arenaShrink = 150;
            this.data.laserCd = 3;
          }
        }
      },
      
      takeDamage(dmg, isCrit) {
        if (this.state === 'dead' || this.introTimer > 0) return 0;
        this.hp -= dmg;
        this.hitFlash = 0.1;
        this.state = 'hit';
        this.stateTimer = 0.15;
        this._hurtAnimT = 1; // 【问题二】受击挤压动画
        
        DamageNumberSys.show(
          this.x + Utils.rand(-20, 20),
          this.y - this.height + Utils.rand(0, 30),
          dmg,
          isCrit ? 'crit' : 'boss'
        );
        
        ParticleSys.emit(this.x, this.y - this.height / 2, 5, {
          color: isCrit ? '#fbbf24' : '#f87171',
          size: Utils.rand(2, 5), life: 0.4,
          vx: Utils.rand(-80, 80), vy: Utils.rand(-80, 0),
        });
        
        if (this.hp <= 0) {
          this.hp = 0;
          this.state = 'dead';
          BattleSys.onBossDeath();
        }
        return dmg;
      },
      
      // ====== Boss 1: 虚空行者 ======
      updateVoidWalker(dt) {
        const d = this.data;
        
        // 闪现CD
        d.teleportCd -= dt;
        d.cloneCd -= dt;
        d.blackHoleCd -= dt;
        
        // 与玩家保持距离
        if (this.state === 'idle') {
          const dist = Math.abs(Player.x - this.x);
          if (dist < 200) {
            // 太远时偶尔闪现到玩家背后
            if (d.teleportCd <= 0 && Math.random() < 0.02) {
              this.voidWalkerTeleport();
            }
            // 贴近时普通攻击
            if (this.attackCooldown <= 0) {
              this.voidWalkerAttack();
            }
          }
          
          this.attackCooldown -= dt;
        }
        
        // 释放分身
        if (d.cloneCd <= 0 && this.state === 'idle') {
          this.voidWalkerSummonClones();
          d.cloneCd = 12;
        }
        
        // 释放黑洞
        if (d.blackHoleCd <= 0 && this.state === 'idle') {
          this.voidWalkerBlackHole();
          d.blackHoleCd = 8;
        }
        
        // 更新分身
        if (d.clones) {
          d.clones = d.clones.filter(c => {
            c.life -= dt;
            c.attackCd -= dt;
            // 分身缓慢跟随玩家
            if (Math.abs(c.x - Player.x) > 100) {
              c.x += (Player.x < c.x ? -1 : 1) * 50 * dt;
            }
            // 分身攻击
            if (c.attackCd <= 0 && Math.abs(c.x - Player.x) < 150) {
              c.attackCd = 2;
              if (Utils.circleCollide(c.x, c.y, 60, Player.x, Player.y, 40)) {
                Player.takeDamage(Math.floor(this.attack * 0.5));
              }
            }
            return c.life > 0;
          });
        }
        
        // 更新黑洞
        if (d.blackHole) {
          d.blackHole.life -= dt;
          // 吸引玩家
          const dx = d.blackHole.x - Player.x;
          const dy = d.blackHole.y - Player.y;
          const dist = Math.hypot(dx, dy);
          if (dist < d.blackHole.radius * 2 && dist > 10) {
            const pullForce = 80 * (1 - dist / (d.blackHole.radius * 2));
            Player.x += (dx / dist) * pullForce * dt;
            Player.y += (dy / dist) * pullForce * 0.3 * dt;
          }
          // 持续伤害
          d.blackHole.dmgCd -= dt;
          if (d.blackHole.dmgCd <= 0 && dist < d.blackHole.radius) {
            d.blackHole.dmgCd = 0.5;
            Player.takeDamage(Math.floor(this.attack * 0.3));
          }
          // 粒子
          ParticleSys.emit(d.blackHole.x, d.blackHole.y, 2, {
            color: '#7c3aed', size: Utils.rand(2, 5), life: 0.5,
            vx: Utils.rand(-30, 30), vy: Utils.rand(-30, 30),
          });
          if (d.blackHole.life <= 0) d.blackHole = null;
        }
      },
      
      voidWalkerTeleport() {
        this.data.teleportCd = 5;
        // 闪现到玩家背后
        const behindX = Player.x - Player.facing * 150;
        ParticleSys.emit(this.x, this.y - this.height/2, 15, {
          color: '#a855f7', size: 4, life: 0.5,
        });
        this.x = Utils.clamp(behindX, 100, CONFIG.canvasWidth - 100);
        ParticleSys.emit(this.x, this.y - this.height/2, 15, {
          color: '#a855f7', size: 4, life: 0.5,
        });
        this.facing = Player.facing * -1;
        this.state = 'attack';
        this.stateTimer = 0.3;
        
        // 背刺伤害
        setTimeout(() => {
          if (Math.abs(this.x - Player.x) < 120 && Math.abs(this.y - Player.y) < 60) {
            Player.takeDamage(Math.floor(this.attack * 1.2));
          }
        }, 200);
        
        AudioMgr.playSfx('skill');
      },
      
      voidWalkerAttack() {
        this.attackCooldown = 1.5;
        this.state = 'attack';
        this.stateTimer = 0.4;
        
        if (Math.abs(this.x - Player.x) < this.width / 2 + 60 &&
            Math.abs(this.y - Player.y) < 80) {
          Player.takeDamage(this.attack);
        }
        AudioMgr.playSfx('hit');
      },
      
      voidWalkerSummonClones() {
        // 生成2个镜像分身
        for (let i = 0; i < 2; i++) {
          this.data.clones.push({
            x: this.x + (i === 0 ? -100 : 100),
            y: this.y,
            life: 8,
            attackCd: 2,
          });
        }
        ParticleSys.emit(this.x, this.y - this.height/2, 20, {
          color: '#7c3aed', size: 4, life: 0.8,
        });
        AudioMgr.playSfx('skill');
      },
      
      voidWalkerBlackHole() {
        this.data.blackHole = {
          x: Player.x + (Math.random() - 0.5) * 100,
          y: Player.y - 40,
          radius: 80,
          life: 4,
          dmgCd: 0.5,
        };
        this.state = 'cast';
        this.stateTimer = 0.5;
        AudioMgr.playSfx('skill');
      },
      
      // ====== Boss 2: 熔雷巨像 ======
      updateMagmaThunder(dt) {
        const d = this.data;
        
        if (this.state === 'idle') {
          d.slamCd -= dt;
          d.projectileCd -= dt;
          d.shockwaveCd -= dt;
          this.attackCooldown -= dt;
          
          // 砸地
          if (d.slamCd <= 0) {
            this.magmaSlamWarn();
            d.slamCd = this.phase === 2 ? 3.5 : 5;
          }
          
          // 远程弹幕
          if (d.projectileCd <= 0 && Math.abs(this.x - Player.x) > 200) {
            this.magmaProjectile();
            d.projectileCd = this.phase === 2 ? 2 : 3;
          }
          
          // 冲击波（二阶段）
          if (this.phase >= 2 && d.shockwaveCd <= 0 && Math.abs(this.x - Player.x) < 300) {
            this.magmaShockwave();
            d.shockwaveCd = 8;
          }
          
          // 近战
          if (this.attackCooldown <= 0 && Math.abs(this.x - Player.x) < 130) {
            this.state = 'attack';
            this.stateTimer = 0.5;
            this.attackCooldown = 1.8;
            setTimeout(() => {
              if (Math.abs(this.x - Player.x) < this.width/2 + 50 &&
                  Math.abs(this.y - Player.y) < 80) {
                Player.takeDamage(this.attack);
              }
            }, 300);
          }
        }
        
        // 砸地预警
        if (d.slamWarn > 0) {
          d.slamWarn -= dt;
          if (d.slamWarn <= 0) {
            this.magmaSlam();
          }
        }
        
        // 冲击波
        if (d.shockwaveActive) {
          d.shockwaveTimer -= dt;
          // 检测玩家是否在地面
          if (d.shockwaveTimer < 0.3 && Player.y >= Player.groundY - 10) {
            Player.takeDamage(Math.floor(this.attack * 0.7));
            d.shockwaveActive = false;
          }
          if (d.shockwaveTimer <= 0) d.shockwaveActive = false;
        }
        
        // 更新弹幕
        if (!this.projectiles) this.projectiles = [];
        this.projectiles = this.projectiles.filter(p => {
          p.x += p.vx * dt;
          p.y += p.vy * dt;
          p.vy += 100 * dt; // 轻微重力
          p.life -= dt;
          
          // 碰撞玩家
          if (Utils.circleCollide(p.x, p.y, p.radius, Player.x, Player.y - 40, 30)) {
            Player.takeDamage(p.damage);
            return false;
          }
          
          return p.life > 0 && p.x > -50 && p.x < CONFIG.canvasWidth + 50 && p.y < CONFIG.canvasHeight;
        });
      },
      
      magmaSlamWarn() {
        this.data.slamWarn = 1.2;
        this.data.slamPos = { x: Player.x, y: Player.groundY };
        this.state = 'cast';
        this.stateTimer = 1.2;
        AudioMgr.playSfx('skill');
      },
      
      magmaSlam() {
        // 砸地伤害
        const pos = this.data.slamPos;
        const slamRadius = 120;
        if (Math.abs(Player.x - pos.x) < slamRadius && Math.abs(Player.y - Player.groundY) < 50) {
          Player.takeDamage(Math.floor(this.attack * 1.5));
        }
        
        ParticleSys.emit(pos.x, pos.y, 25, {
          color: '#f97316', size: Utils.rand(3, 8), life: 0.6,
          vx: Utils.rand(-200, 200), vy: Utils.rand(-200, -50),
          gravity: 300,
        });
        
        ScreenShake.shake(10, 0.4);
      },
      
      magmaProjectile() {
        if (!this.projectiles) this.projectiles = [];
        const angle = Utils.angleBetween(this.x, this.y - 60, Player.x, Player.y - 40);
        const count = this.phase === 2 ? 3 : 1;
        
        for (let i = 0; i < count; i++) {
          const spread = (i - (count-1)/2) * 0.2;
          this.projectiles.push({
            x: this.x,
            y: this.y - 60,
            vx: Math.cos(angle + spread) * 300,
            vy: Math.sin(angle + spread) * 300 - 50,
            radius: 12,
            damage: Math.floor(this.attack * 0.6),
            life: 4,
            color: i % 2 === 0 ? '#f97316' : '#60a5fa',
          });
        }
        
        this.state = 'attack';
        this.stateTimer = 0.3;
        AudioMgr.playSfx('skill');
      },
      
      magmaShockwave() {
        this.data.shockwaveActive = true;
        this.data.shockwaveTimer = 0.5;
        this.state = 'attack';
        this.stateTimer = 0.5;
        ScreenShake.shake(6, 0.3);
        AudioMgr.playSfx('skill');
      },
      
      // ====== Boss 3: 字祸魔典 ======
      updateGrimoire(dt) {
        const d = this.data;
        
        if (this.state === 'idle') {
          d.runeVolleyCd -= dt;
          d.sealThrowCd -= dt;
          d.cycloneCd -= dt;
          
          // 符文弹幕
          if (d.runeVolleyCd <= 0) {
            this.grimoireRuneVolley();
            d.runeVolleyCd = this.phase === 2 ? 2 : 3;
          }
          
          // 汉字封印
          if (d.sealThrowCd <= 0) {
            this.grimoireSealThrow();
            d.sealThrowCd = this.phase === 2 ? 4 : 6;
          }
          
          // 书页旋风（二阶段强化）
          if (d.cycloneCd <= 0) {
            this.grimoirePageCyclone();
            d.cycloneCd = this.phase === 2 ? 10 : 15;
          }
        }
        
        // 书页旋风持续
        if (d.pageCyclone) {
          d.cycloneTimer -= dt;
          d.cycloneAngle = (d.cycloneAngle || 0) + dt * 3;
          
          // 旋风伤害
          const dist = Utils.dist(this.x, this.y - 60, Player.x, Player.y - 40);
          if (dist < 130 && dist > 50) {
            d.cycloneDmgCd = (d.cycloneDmgCd || 0) - dt;
            if (d.cycloneDmgCd <= 0) {
              d.cycloneDmgCd = 0.5;
              Player.takeDamage(Math.floor(this.attack * 0.4));
            }
          }
          
          if (d.cycloneTimer <= 0) d.pageCyclone = false;
        }
        
        // 更新弹幕
        if (!this.projectiles) this.projectiles = [];
        this.projectiles = this.projectiles.filter(p => {
          p.x += p.vx * dt;
          p.y += p.vy * dt;
          p.life -= dt;
          
          if (p.type === 'seal') {
            // 封印弹：减速效果
            if (Utils.circleCollide(p.x, p.y, p.radius, Player.x, Player.y - 40, 30)) {
              Player.takeDamage(p.damage);
              // 减速：通过临时降低移动速度实现
              Player.slowTimer = 2;
              Player.slowAmount = 0.5;
              return false;
            }
          } else {
            if (Utils.circleCollide(p.x, p.y, p.radius, Player.x, Player.y - 40, 30)) {
              Player.takeDamage(p.damage);
              return false;
            }
          }
          
          return p.life > 0 && p.x > -50 && p.x < CONFIG.canvasWidth + 50 &&
                 p.y > -50 && p.y < CONFIG.canvasHeight + 50;
        });
      },
      
      grimoireRuneVolley() {
        if (!this.projectiles) this.projectiles = [];
        const angle = Utils.angleBetween(this.x, this.y - 60, Player.x, Player.y - 40);
        const count = this.phase === 2 ? 9 : 6;
        
        for (let i = 0; i < count; i++) {
          const spread = (i - (count-1)/2) * 0.15;
          this.projectiles.push({
            x: this.x,
            y: this.y - 60,
            vx: Math.cos(angle + spread) * 250,
            vy: Math.sin(angle + spread) * 250,
            radius: 10,
            damage: Math.floor(this.attack * 0.4),
            life: 3,
            color: '#c084fc',
            type: 'rune',
          });
        }
        
        this.state = 'cast';
        this.stateTimer = 0.3;
        AudioMgr.playSfx('skill');
      },
      
      grimoireSealThrow() {
        if (!this.projectiles) this.projectiles = [];
        const angle = Utils.angleBetween(this.x, this.y - 60, Player.x, Player.y - 40);
        // 发射3个汉字封印
        for (let i = 0; i < 3; i++) {
          setTimeout(() => {
            if (GameState.currentScene !== 'battle' || this.state === 'dead') return;
            const a = Utils.angleBetween(this.x, this.y - 60, Player.x, Player.y - 40);
            this.projectiles.push({
              x: this.x,
              y: this.y - 60,
              vx: Math.cos(a) * 200,
              vy: Math.sin(a) * 200,
              radius: 20,
              damage: Math.floor(this.attack * 0.5),
              life: 4,
              color: '#fbbf24',
              type: 'seal',
              char: ['禁', '封', '缚'][i % 3],
            });
          }, i * 200);
        }
        
        this.state = 'cast';
        this.stateTimer = 0.5;
        AudioMgr.playSfx('skill');
      },
      
      grimoirePageCyclone() {
        this.data.pageCyclone = true;
        this.data.cycloneTimer = this.phase === 2 ? 5 : 4;
        this.data.cycloneAngle = 0;
        this.data.cycloneDmgCd = 0;
        this.state = 'cast';
        this.stateTimer = 0.5;
        AudioMgr.playSfx('skill');
      },
      
      // ====== Boss 4: 时之眼 (最终Boss, 三阶段) ======
      updateTimeEye(dt) {
        const d = this.data;
        
        // 时滞效果影响玩家
        if (d.timeSlowActive) {
          d.timeSlowTimer -= dt;
          if (d.timeSlowTimer <= 0) {
            d.timeSlowActive = false;
            Player.timeSlowMul = 1;
          } else {
            Player.timeSlowMul = 0.4;
          }
        } else {
          Player.timeSlowMul = 1;
        }
        
        if (this.state === 'idle') {
          d.chainSweepCd -= dt;
          d.runeRingCd -= dt;
          
          if (this.phase >= 2) d.timeSlowCd -= dt;
          
          if (this.phase >= 3) {
            d.laserCd -= dt;
          }
          
          // 一阶段：锁链横扫 + 九环符文
          if (d.chainSweepCd <= 0 && this.phase <= 2) {
            this.timeEyeChainSweep();
            d.chainSweepCd = 4;
          }
          
          if (d.runeRingCd <= 0) {
            this.timeEyeRuneRing();
            d.runeRingCd = this.phase === 2 ? 2.5 : 3.5;
          }
          
          // 二阶段：时滞 + 血量回溯
          if (this.phase >= 2 && d.timeSlowCd <= 0) {
            this.timeEyeTimeSlow();
            d.timeSlowCd = 18;
          }
          
          // 三阶段：激光扫射
          if (this.phase >= 3 && d.laserCd <= 0 && !d.laserActive) {
            this.timeEyeLaser();
            d.laserCd = 6;
          }
        }
        
        // 激光持续
        if (d.laserActive) {
          d.laserTimer -= dt;
          d.laserAngle += d.laserDir * dt * 1.5;
          
          // 检测玩家是否被激光扫中
          const laserLen = 600;
          const laserX = this.x + Math.cos(d.laserAngle) * laserLen;
          const laserY = this.y - 60 + Math.sin(d.laserAngle) * laserLen;
          
          // 点到线段距离
          const A = Player.x - this.x;
          const B = Player.y - 60 - (this.y - 60);
          const C = laserX - this.x;
          const D = laserY - (this.y - 60);
          const dot = A * C + B * D;
          const lenSq = C * C + D * D;
          const t = Math.max(0, Math.min(1, dot / lenSq));
          const closestX = this.x + t * C;
          const closestY = (this.y - 60) + t * D;
          const dist = Math.hypot(Player.x - closestX, Player.y - 60 - closestY);
          
          if (dist < 25) {
            d.laserDmgCd = (d.laserDmgCd || 0) - dt;
            if (d.laserDmgCd <= 0) {
              d.laserDmgCd = 0.3;
              Player.takeDamage(Math.floor(this.attack * 0.5));
            }
          }
          
          if (d.laserTimer <= 0) {
            d.laserActive = false;
          }
        }
        
        // 锁链
        if (this.chains) {
          this.chains = this.chains.filter(c => {
            c.life -= dt;
            c.x += c.vx * dt;
            
            if (c.active && Utils.circleCollide(c.x, c.y, 15, Player.x, Player.y - 40, 30)) {
              Player.takeDamage(c.damage);
              c.active = false;
            }
            
            return c.life > 0;
          });
        }
        
        // 弹幕
        if (!this.projectiles) this.projectiles = [];
        this.projectiles = this.projectiles.filter(p => {
          p.x += p.vx * dt;
          p.y += p.vy * dt;
          p.life -= dt;
          
          if (Utils.circleCollide(p.x, p.y, p.radius, Player.x, Player.y - 40, 30)) {
            Player.takeDamage(p.damage);
            return false;
          }
          
          return p.life > 0 && p.x > -50 && p.x < CONFIG.canvasWidth + 50 &&
                 p.y > -50 && p.y < CONFIG.canvasHeight + 50;
        });
      },
      
      timeEyeChainSweep() {
        if (!this.chains) this.chains = [];
        // 两条锁链横扫
        const dir = Player.x < this.x ? -1 : 1;
        for (let i = 0; i < 2; i++) {
          this.chains.push({
            x: this.x,
            y: this.y - 60 + (i === 0 ? -40 : 40),
            vx: dir * 400,
            damage: Math.floor(this.attack * 0.6),
            life: 2,
            active: true,
          });
        }
        this.state = 'attack';
        this.stateTimer = 0.4;
        AudioMgr.playSfx('skill');
      },
      
      timeEyeRuneRing() {
        if (!this.projectiles) this.projectiles = [];
        const count = this.phase === 3 ? 12 : 9;
        
        for (let i = 0; i < count; i++) {
          const angle = (i / count) * Math.PI * 2;
          setTimeout(() => {
            if (GameState.currentScene !== 'battle' || this.state === 'dead') return;
            this.projectiles.push({
              x: this.x,
              y: this.y - 60,
              vx: Math.cos(angle) * 180,
              vy: Math.sin(angle) * 180,
              radius: 10,
              damage: Math.floor(this.attack * 0.4),
              life: 4,
              color: '#fbbf24',
              type: 'rune',
            });
          }, i * 50);
        }
        this.state = 'cast';
        this.stateTimer = 0.3;
        AudioMgr.playSfx('skill');
      },
      
      timeEyeTimeSlow() {
        this.data.timeSlowActive = true;
        this.data.timeSlowTimer = 5;
        this.state = 'cast';
        this.stateTimer = 0.8;
        
        // 回溯血量
        const rewindHp = this.maxHp * 0.1;
        this.hp = Math.min(this.maxHp, this.hp + rewindHp);
        
        ScreenShake.shake(5, 0.5);
        ParticleSys.emit(this.x, this.y - this.height/2, 30, {
          color: '#fbbf24', size: Utils.rand(3, 6), life: 1,
        });
        AudioMgr.playSfx('skill');
      },
      
      timeEyeLaser() {
        this.data.laserActive = true;
        this.data.laserTimer = 3;
        this.data.laserAngle = -Math.PI; // 从左扫到右
        this.data.laserDir = 1;
        this.data.laserDmgCd = 0;
        this.state = 'cast';
        this.stateTimer = 1;
        AudioMgr.playSfx('skill');
        ScreenShake.shake(4, 3);
      },
      
      draw(ctx) {
        // 登场动画
        if (this.introTimer > 0) {
          const t = 1 - this.introTimer / 1.5;
          ctx.save();
          ctx.globalAlpha = t;
          ctx.translate(this.x, this.y);
          if (this.img && this.img.complete) {
            const iw = this.width * (0.5 + t * 0.5);
            const ih = this.height * (0.5 + t * 0.5);
            ctx.drawImage(this.img, -iw/2, -ih, iw, ih);
          }
          ctx.restore();
          return;
        }
        
        // 画分身（虚空行者）
        if (id === 1 && this.data.clones) {
          for (const c of this.data.clones) {
            ctx.save();
            ctx.globalAlpha = 0.6;
            ctx.translate(c.x, c.y);
            if (this.img && this.img.complete) {
              const iw = this.width * 0.7;
              const ih = this.height * 0.7;
              ctx.drawImage(this.img, -iw/2, -ih, iw, ih);
            }
            ctx.restore();
          }
        }
        
        // 画黑洞
        if (id === 1 && this.data.blackHole) {
          const bh = this.data.blackHole;
          ctx.save();
          const grad = ctx.createRadialGradient(bh.x, bh.y, 0, bh.x, bh.y, bh.radius);
          grad.addColorStop(0, 'rgba(0,0,0,0.9)');
          grad.addColorStop(0.5, 'rgba(76,29,149,0.7)');
          grad.addColorStop(1, 'rgba(124,58,237,0)');
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(bh.x, bh.y, bh.radius, 0, Math.PI * 2);
          ctx.fill();
          // 旋转光环
          ctx.strokeStyle = '#a855f7';
          ctx.lineWidth = 2;
          ctx.shadowColor = '#c084fc';
          ctx.shadowBlur = 10;
          const rot = performance.now() / 500;
          for (let i = 0; i < 3; i++) {
            ctx.beginPath();
            const a = rot + i * Math.PI * 2 / 3;
            ctx.ellipse(bh.x, bh.y, bh.radius * 0.8, bh.radius * 0.3, a, 0, Math.PI * 2);
            ctx.stroke();
          }
          ctx.restore();
        }
        
        // 画砸地预警（熔雷巨像）
        if (id === 2 && this.data.slamWarn > 0) {
          const pos = this.data.slamPos;
          const warnProgress = 1 - this.data.slamWarn / 1.2;
          ctx.save();
          ctx.strokeStyle = `rgba(239, 68, 68, ${0.5 + 0.5 * warnProgress})`;
          ctx.lineWidth = 3;
          ctx.setLineDash([10, 10]);
          ctx.beginPath();
          ctx.ellipse(pos.x, pos.y, 120 * warnProgress, 40 * warnProgress, 0, 0, Math.PI * 2);
          ctx.stroke();
          // 红色闪烁填充
          ctx.fillStyle = `rgba(239, 68, 68, ${0.15 + 0.15 * Math.sin(performance.now() / 100)})`;
          ctx.beginPath();
          ctx.ellipse(pos.x, pos.y, 120 * warnProgress, 40 * warnProgress, 0, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
        
        // 画弹幕
        if (this.projectiles) {
          for (const p of this.projectiles) {
            ctx.save();
            ctx.fillStyle = p.color || '#f87171';
            ctx.shadowColor = p.color || '#f87171';
            ctx.shadowBlur = 8;
            
            if (p.type === 'seal') {
              // 汉字封印
              ctx.font = `bold ${p.radius * 2}px serif`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = '#fbbf24';
              ctx.strokeStyle = '#92400e';
              ctx.lineWidth = 2;
              ctx.strokeText(p.char || '禁', p.x, p.y);
              ctx.fillText(p.char || '禁', p.x, p.y);
            } else {
              ctx.beginPath();
              ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
              ctx.fill();
            }
            ctx.restore();
          }
        }
        
        // 画锁链（时之眼）
        if (id === 4 && this.chains) {
          for (const c of this.chains) {
            ctx.save();
            ctx.strokeStyle = '#94a3b8';
            ctx.lineWidth = 6;
            ctx.shadowColor = '#cbd5e1';
            ctx.shadowBlur = 5;
            ctx.beginPath();
            ctx.moveTo(this.x, this.y - 60);
            ctx.lineTo(c.x, c.y);
            ctx.stroke();
            // 链球
            ctx.fillStyle = '#64748b';
            ctx.beginPath();
            ctx.arc(c.x, c.y, 15, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }
        
        // 画激光（时之眼三阶段）
        if (id === 4 && this.data.laserActive) {
          const d = this.data;
          const laserLen = 600;
          const endX = this.x + Math.cos(d.laserAngle) * laserLen;
          const endY = this.y - 60 + Math.sin(d.laserAngle) * laserLen;
          
          ctx.save();
          // 外发光
          ctx.strokeStyle = 'rgba(251, 191, 36, 0.3)';
          ctx.lineWidth = 50;
          ctx.shadowColor = '#fbbf24';
          ctx.shadowBlur = 20;
          ctx.beginPath();
          ctx.moveTo(this.x, this.y - 60);
          ctx.lineTo(endX, endY);
          ctx.stroke();
          // 核心
          ctx.strokeStyle = '#fef3c7';
          ctx.lineWidth = 10;
          ctx.shadowBlur = 15;
          ctx.beginPath();
          ctx.moveTo(this.x, this.y - 60);
          ctx.lineTo(endX, endY);
          ctx.stroke();
          ctx.restore();
        }
        
        // 画Boss本体
        ctx.save();
        ctx.translate(this.x, this.y);
        ctx.scale(this.facing > 0 ? -1 : 1, 1); // 默认朝左

        // 【问题二】基于状态的动态缩放（避免静态立绘漂移感）
        let bsx = 1, bsy = 1, boy = 0;
        if (this.state === 'idle' || this.state === 'stunned') {
          // 呼吸缩放
          const breath = 1 + Math.sin(this._animT * 1.5) * 0.025;
          bsx = breath;
          bsy = 2 - breath;
        } else if (this.state === 'attack' || this._attackAnimT > 0) {
          // 攻击前冲
          const t = this._attackAnimT;
          bsx = 1 + t * 0.2;
          bsy = 1 - t * 0.1;
        }
        if (this._hurtAnimT > 0) {
          const t = this._hurtAnimT;
          bsx *= 1 + t * 0.15;
          bsy *= 1 - t * 0.2;
        }
        ctx.scale(bsx, bsy);
        ctx.translate(0, boy);
        
        // 受击闪白
        if (this.hitFlash > 0) {
          ctx.globalAlpha = 0.8;
        }
        
        if (this.state === 'dead') {
          const t = Math.max(0, this.stateTimer / 1);
          ctx.globalAlpha *= t;
          ctx.rotate((1 - t) * 0.3);
          ctx.scale(1 + (1 - t) * 0.2, 1 - (1 - t) * 0.1);
        }
        
        // 定身效果
        if (this.stunned) {
          ctx.shadowColor = '#7c3aed';
          ctx.shadowBlur = 20;
        }
        
        // 真身微光（虚空行者）
        if (id === 1) {
          ctx.shadowColor = '#c084fc';
          ctx.shadowBlur = 15;
        }
        
        if (this.img && this.img.complete) {
          const iw = this.width;
          const ih = this.height * 1.2;
          
          if (this.hitFlash > 0) {
            ctx.drawImage(this.img, -iw/2, -ih, iw, ih);
            ctx.globalCompositeOperation = 'lighter';
            ctx.globalAlpha = this.hitFlash / 0.1 * 0.6;
            ctx.filter = 'brightness(3)';
            ctx.drawImage(this.img, -iw/2, -ih, iw, ih);
            ctx.filter = 'none';
            ctx.globalCompositeOperation = 'source-over';
          } else {
            ctx.drawImage(this.img, -iw/2, -ih, iw, ih);
          }
        }
        ctx.restore();
        
        // 书页旋风（字祸魔典）
        if (id === 3 && this.data.pageCyclone) {
          const d = this.data;
          ctx.save();
          ctx.translate(this.x, this.y - 60);
          ctx.rotate(d.cycloneAngle);
          ctx.fillStyle = '#f5f5dc';
          ctx.strokeStyle = '#8b7355';
          ctx.lineWidth = 1;
          for (let i = 0; i < 12; i++) {
            const a = (i / 12) * Math.PI * 2;
            const r = 90 + Math.sin(performance.now() / 200 + i) * 10;
            const px = Math.cos(a) * r;
            const py = Math.sin(a) * r * 0.6;
            ctx.save();
            ctx.translate(px, py);
            ctx.rotate(a);
            ctx.fillRect(-15, -5, 30, 10);
            ctx.strokeRect(-15, -5, 30, 10);
            ctx.restore();
          }
          ctx.restore();
        }
      },
    };
  },
};
