/* ==========================================================
   小怪 / 敌人系统
   - 三种小怪：虚空浮游魔、符文傀儡、书页游魂
   - 统一状态机：idle, chase, attack, hurt, dead
   - 死亡淡出 + 掉落
   ========================================================== */

const EnemySys = {
  types: {
    floater: {
      // 虚空浮游魔：漂浮、触须电击
      name: '虚空浮游魔',
      hp: 30,
      attack: 8,
      speed: 60,
      width: 60,
      height: 60,
      spriteUrl: 'assets/img/enemy_floater.png',
      flying: true,
      attackRange: 120,
      attackCd: 2.0,
      damageType: 'shock', // 电击
      color: '#a855f7',
      xp: 20,
      gold: 15,
    },
    golem: {
      // 符文傀儡：近战冲撞
      name: '符文傀儡',
      hp: 80,
      attack: 15,
      speed: 80,
      width: 70,
      height: 90,
      spriteUrl: 'assets/img/enemy_golem.png',
      flying: false,
      attackRange: 80,
      attackCd: 2.5,
      damageType: 'charge', // 冲撞
      color: '#f59e0b',
      xp: 40,
      gold: 30,
    },
    wraith: {
      // 书页游魂：远程符文弹
      name: '书页游魂',
      hp: 45,
      attack: 10,
      speed: 50,
      width: 55,
      height: 75,
      spriteUrl: 'assets/img/enemy_wraith.png',
      flying: true,
      attackRange: 280,
      attackCd: 3.0,
      damageType: 'ranged', // 远程
      color: '#60a5fa',
      xp: 30,
      gold: 20,
    },
  },

  createEnemy(type, x, y) {
    const def = this.types[type];
    if (!def) return null;
    return new Enemy(type, def, x, y);
  },
};

class Enemy {
  constructor(type, def, x, y) {
    this.type = type;
    this.def = def;
    this.x = x;
    this.y = y;
    this.width = def.width;
    this.height = def.height;
    this.maxHp = def.hp;
    this.hp = def.hp;
    this.attack = def.attack;
    this.speed = def.speed;
    this.flying = def.flying;
    this.attackRange = def.attackRange;
    this.attackCd = def.attackCd;
    this.attackTimer = Math.random() * 1.5;
    this.color = def.color;

    this.state = 'idle'; // idle, chase, attack, hurt, dead
    this.stateTimer = 0;
    this.facing = -1;

    // 漂浮动画（飞行怪）
    this.floatOffset = 0;
    this.floatPhase = Math.random() * Math.PI * 2;

    // 受击闪白
    this.hitFlash = 0;
    this.hurtTimer = 0;
    this.knockbackX = 0;

    // 死亡淡出
    this.deathTimer = 0;
    this.deathDuration = 0.6;

    // 精灵图（因为小怪素材可能是单帧立绘或小帧动画，兼容处理）
    this.img = new Image();
    this.img.src = def.spriteUrl;
    this.imgLoaded = false;
    this.img.onload = () => { this.imgLoaded = true; };

    // 【问题二】动画计时器（伪动画：呼吸、攻击前冲、受击挤压）
    this._animT = 0;
    this._attackAnimT = 0; // 攻击前冲动画进度 0~1
    this._hurtAnimT = 0;   // 受击动画进度 0~1
    this._walkPhase = Math.random() * Math.PI * 2;
  }

  update(dt, playerX, playerY) {
    if (this.state === 'dead') {
      this.deathTimer += dt;
      return this.deathTimer >= this.deathDuration;
    }

    // 受击恢复
    if (this.hurtTimer > 0) {
      this.hurtTimer -= dt;
    }
    if (this.hitFlash > 0) this.hitFlash -= dt;
    if (this.knockbackX !== 0) {
      this.x += this.knockbackX * dt;
      this.knockbackX *= 0.9;
      if (Math.abs(this.knockbackX) < 5) this.knockbackX = 0;
    }

    // 漂浮动画
    if (this.flying) {
      this.floatPhase += dt * 2;
      this.floatOffset = Math.sin(this.floatPhase) * 8;
    }

    // 状态机
    const dist = Math.hypot(playerX - this.x, playerY - this.y);

    // 【问题二】动画计时更新
    this._animT += dt;
    if (this.state === 'chase') {
      this._walkPhase += dt * (3 + Math.min(2, this.speed / 50));
    }
    if (this._attackAnimT > 0) this._attackAnimT = Math.max(0, this._attackAnimT - dt * 3);
    if (this._hurtAnimT > 0) this._hurtAnimT = Math.max(0, this._hurtAnimT - dt * 5);

    if (this.state === 'attack') {
      this.stateTimer -= dt;
      if (this.stateTimer <= 0) {
        // 攻击完成，回到追击
        this.state = 'chase';
      }
    } else if (this.state === 'hurt') {
      this.stateTimer -= dt;
      if (this.stateTimer <= 0) {
        this.state = 'chase';
      }
    } else {
      // 朝向玩家
      if (playerX > this.x) this.facing = 1;
      else this.facing = -1;

      if (dist < this.attackRange) {
        // 攻击冷却
        this.attackTimer -= dt;
        if (this.attackTimer <= 0) {
          this._doAttack(playerX, playerY);
        }
        // 远程怪保持距离，近战怪继续靠近
        if (this.def.damageType === 'ranged') {
          if (dist < this.attackRange * 0.6) {
            // 后退
            this.x -= this.facing * this.speed * 0.5 * dt;
          }
        } else {
          this._moveToward(playerX, playerY, dt * 0.3);
        }
        this.state = 'chase';
      } else if (dist < 500) {
        // 追击
        this._moveToward(playerX, playerY, dt);
        this.state = 'chase';
      } else {
        this.state = 'idle';
      }
    }

    return false; // 未死亡
  }

  _moveToward(px, py, dt) {
    const dx = px - this.x;
    const dy = py - this.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 1) return;
    const nx = dx / dist;
    const ny = dy / dist;
    this.x += nx * this.speed * dt;
    // 飞行怪可以上下移动，地面怪只能左右
    if (this.flying) {
      this.y += ny * this.speed * 0.5 * dt;
    }
  }

  _doAttack(px, py) {
    this.attackTimer = this.attackCd;
    this.state = 'attack';
    this.stateTimer = 0.4;
    this._attackAnimT = 1; // 【问题二】触发攻击前冲动画

    if (this.def.damageType === 'ranged') {
      // 发射符文弹
      const angle = Math.atan2(py - this.y, px - this.x);
      if (window.BattleSys && BattleSys.enemyProjectiles) {
        BattleSys.enemyProjectiles.push({
          x: this.x,
          y: this.y - this.height / 2,
          vx: Math.cos(angle) * 200,
          vy: Math.sin(angle) * 200,
          damage: this.attack,
          color: this.color,
          size: 10,
          life: 3,
        });
      }
    } else if (this.def.damageType === 'charge') {
      // 冲撞：短距离快速扑向玩家
      this.knockbackX = this.facing * -30; // 反冲
      // 伤害检测在 BattleSys.update 里做
    } else {
      // 电击 / 近战：直接伤害检测在 BattleSys 里做
    }

    // 攻击特效
    if (window.ParticleSys) {
      ParticleSys.emit(this.x, this.y - this.height / 2, 8, {
        color: this.color, size: 3, life: 0.3, speed: 80,
      });
    }
  }

  takeDamage(dmg, fromX) {
    if (this.state === 'dead') return false;
    this.hp -= dmg;
    this.hitFlash = 0.1;
    this.hurtTimer = 0.2;
    this._hurtAnimT = 1; // 【问题二】触发受击挤压动画
    this.state = 'hurt';
    this.stateTimer = 0.2;

    // 击退
    if (fromX !== undefined) {
      const dir = this.x > fromX ? 1 : -1;
      this.knockbackX = dir * 100;
    }

    if (this.hp <= 0) {
      this.hp = 0;
      this.state = 'dead';
      this.deathTimer = 0;
      // 死亡粒子
      if (window.ParticleSys) {
        ParticleSys.emit(this.x, this.y - this.height / 2, 20, {
          color: this.color, size: Utils.rand(3, 6), life: 0.6,
          vx: Utils.rand(-80, 80), vy: Utils.rand(-80, 40),
          gravity: 200,
        });
      }
      if (window.AudioMgr) AudioMgr.playSfx('enemyDeath');
      return true; // 击杀
    }
    return false;
  }

  draw(ctx) {
    const drawY = this.flying ? this.y + this.floatOffset : this.y;

    // 脚底阴影（地面怪才有，飞行怪阴影淡且小）
    this._drawShadow(ctx, drawY);

    ctx.save();
    ctx.translate(this.x, drawY - this.height / 2); // 中心点在胸部
    ctx.scale(this.facing, 1);

    // 死亡淡出
    if (this.state === 'dead') {
      const t = this.deathTimer / this.deathDuration;
      ctx.globalAlpha = 1 - t;
      ctx.translate(0, -t * 30); // 上升消失
      ctx.rotate(t * Math.PI * 0.5); // 旋转消散
      ctx.scale(1 - t * 0.5, 1 + t * 0.3);
    }

    // 受击闪白 + 无敌
    if (this.hurtTimer > 0 && Math.floor(performance.now() / 60) % 2 === 0) {
      ctx.globalAlpha *= 0.7;
    }

    // 【问题二】基于状态的动态缩放（伪动画，避免静态漂移感）
    // idle：呼吸缩放；chase：上下小幅弹跳；attack：前冲挤压；hurt：受击压扁
    let scaleX = 1, scaleY = 1, offsetY = 0;
    if (this.state === 'idle') {
      const breath = 1 + Math.sin(this._animT * 2) * 0.03;
      scaleX = breath;
      scaleY = 2 - breath;
    } else if (this.state === 'chase') {
      // 行走弹跳
      const bounce = Math.abs(Math.sin(this._walkPhase)) * 0.08;
      scaleY = 1 - bounce * 0.3;
      offsetY = -bounce * this.height * 0.1;
    } else if (this.state === 'attack' || this._attackAnimT > 0) {
      // 攻击前冲：横向拉伸
      const t = this._attackAnimT;
      scaleX = 1 + t * 0.3;
      scaleY = 1 - t * 0.15;
    }
    if (this._hurtAnimT > 0) {
      // 受击压扁叠加
      const t = this._hurtAnimT;
      scaleX *= 1 + t * 0.2;
      scaleY *= 1 - t * 0.25;
    }
    ctx.scale(scaleX, scaleY);
    ctx.translate(0, offsetY);

    if (this.imgLoaded) {
      const iw = this.width;
      const ih = this.height;

      if (this.hitFlash > 0) {
        ctx.globalCompositeOperation = 'source-over';
        ctx.drawImage(this.img, -iw/2, -ih/2, iw, ih);
        ctx.globalCompositeOperation = 'lighter';
        ctx.globalAlpha = Math.min(1, this.hitFlash / 0.1) * 0.7;
        ctx.filter = 'brightness(3)';
        ctx.drawImage(this.img, -iw/2, -ih/2, iw, ih);
        ctx.filter = 'none';
        ctx.globalCompositeOperation = 'source-over';
      } else {
        ctx.drawImage(this.img, -iw/2, -ih/2, iw, ih);
      }
    } else {
      // 加载前的占位：发光圆
      ctx.fillStyle = this.color;
      ctx.globalAlpha = 0.5;
      ctx.shadowColor = this.color;
      ctx.shadowBlur = 20;
      ctx.beginPath();
      ctx.arc(0, 0, this.width / 2, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }

  _drawShadow(ctx, groundY) {
    const isAir = this.flying;
    const shadowAlpha = isAir ? 0.2 : 0.4;
    const shadowW = this.width * 0.6 * (isAir ? 0.7 : 1);
    const shadowH = 6 * (isAir ? 0.5 : 1);
    const shadowY = groundY + this.height / 2 + (isAir ? 10 : 2);

    ctx.save();
    ctx.globalAlpha = shadowAlpha;
    const grad = ctx.createRadialGradient(this.x, shadowY, 0, this.x, shadowY, shadowW / 2);
    grad.addColorStop(0, 'rgba(0, 0, 0, 0.5)');
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(this.x, shadowY, shadowW / 2, shadowH, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  getSortY() {
    return this.y + (this.flying ? this.floatOffset : 0);
  }
}
