/* ==========================================================
   视差与背景渲染系统（HD-2D 立体感）
   - 多层视差图层（远景/中景/近景/前景）
   - 透视网格地面、体积光束、漂浮微尘
   - 所有场景统一接口
   ========================================================== */

const ParallaxSys = {
  _bgCache: {},

  /**
   * 创建视差场景
   * @param {object} layers 图层配置
   * @returns {ParallaxScene}
   */
  createScene(layers) {
    return new ParallaxScene(layers);
  },
};

class ParallaxScene {
  constructor(layers) {
    this.layers = layers.map(l => ({
      image: null,
      speed: l.speed || 0.5, // 相对于镜头移动速度的比例
      y: l.y || 0, // 垂直位置（0=顶部，1=底部）
      tint: l.tint || null, // 叠加色调
      alpha: l.alpha !== undefined ? l.alpha : 1,
      blur: l.blur || 0,
      loaded: false,
      _img: null,
    }));

    // 加载图片
    for (const layer of layers) {
      if (layer.url) {
        const img = new Image();
        img.onload = () => {
          const l = this.layers.find(ll => ll._img === img);
          if (l) l.loaded = true;
        };
        img.src = layer.url;
        const l = this.layers[layers.indexOf(layer)];
        l._img = img;
      }
    }

    // 微尘粒子
    this.dustParticles = [];
    for (let i = 0; i < 30; i++) {
      this.dustParticles.push({
        x: Math.random() * 1280,
        y: Math.random() * 720,
        size: Math.random() * 2 + 1,
        speed: Math.random() * 20 + 10,
        alpha: Math.random() * 0.4 + 0.1,
        drift: Math.random() * 0.5 - 0.25,
      });
    }

    // 光束（体积光）
    this.lightBeams = [
      { x: 200, width: 80, alpha: 0.08 },
      { x: 600, width: 120, alpha: 0.05 },
      { x: 1000, width: 60, alpha: 0.07 },
    ];

    this.cameraX = 0;
    this.cameraY = 0;
  }

  update(dt, camX, camY) {
    this.cameraX = camX || 0;
    this.cameraY = camY || 0;

    // 微尘飘动
    for (const p of this.dustParticles) {
      p.x += p.drift * dt * 10;
      p.y -= p.speed * dt;
      if (p.y < -10) {
        p.y = 730;
        p.x = Math.random() * 1280;
      }
      if (p.x < -10) p.x = 1290;
      if (p.x > 1290) p.x = -10;
    }
  }

  /**
   * 绘制整个视差场景（背景层 + 网格地面 + 微尘 + 光束）
   * 角色和其他前景由调用方在中间绘制
   */
  drawBackground(ctx, cw, ch) {
    // 场景暗底色
    ctx.fillStyle = '#0a0615';
    ctx.fillRect(0, 0, cw, ch);

    // 各层视差
    for (let i = 0; i < this.layers.length; i++) {
      const layer = this.layers[i];
      if (!layer._img || !layer.loaded) continue;

      const img = layer._img;
      const imgRatio = img.width / img.height;
      const canvasRatio = cw / ch;

      // 每层都 cover 铺满，但位置随镜头移动
      let bw, bh;
      if (imgRatio > canvasRatio) {
        bh = ch;
        bw = ch * imgRatio;
      } else {
        bw = cw;
        bh = cw / imgRatio;
      }

      // 视差偏移：镜头移动 * speed
      // 越远的层 speed 越小
      const offsetX = -this.cameraX * layer.speed;
      const offsetY = -this.cameraY * layer.speed * 0.3;

      // 居中偏移 + 视差偏移
      const bx = (cw - bw) / 2 + offsetX;
      const by = (ch - bh) / 2 + offsetY;

      ctx.save();
      ctx.globalAlpha = layer.alpha;
      if (layer.blur > 0) {
        ctx.filter = `blur(${layer.blur}px)`;
      }
      ctx.drawImage(img, bx, by, bw, bh);
      ctx.filter = 'none';

      // 色调叠加
      if (layer.tint) {
        ctx.globalCompositeOperation = 'multiply';
        ctx.fillStyle = layer.tint;
        ctx.fillRect(0, 0, cw, ch);
        ctx.globalCompositeOperation = 'source-over';
      }
      ctx.restore();
    }

    // 体积光束（自上而下的斜射光）
    this._drawLightBeams(ctx, cw, ch);

    // 漂浮微尘
    this._drawDust(ctx, cw, ch);
  }

  _drawLightBeams(ctx, cw, ch) {
    ctx.save();
    for (const beam of this.lightBeams) {
      const x = beam.x - this.cameraX * 0.3;
      const grad = ctx.createLinearGradient(x, 0, x + beam.width, ch);
      grad.addColorStop(0, `rgba(200, 180, 255, ${beam.alpha})`);
      grad.addColorStop(0.5, `rgba(180, 160, 255, ${beam.alpha * 0.5})`);
      grad.addColorStop(1, 'rgba(180, 160, 255, 0)');

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.moveTo(x - beam.width / 2, 0);
      ctx.lineTo(x + beam.width / 2, 0);
      ctx.lineTo(x + beam.width, ch);
      ctx.lineTo(x - beam.width, ch);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  _drawDust(ctx, cw, ch) {
    ctx.save();
    for (const p of this.dustParticles) {
      // 简单视差：靠近镜头的微尘移动更快
      const px = p.x - this.cameraX * 0.1;
      const py = p.y - this.cameraY * 0.05;

      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = '#c4b5fd';
      ctx.shadowColor = '#a855f7';
      ctx.shadowBlur = 4;
      ctx.beginPath();
      ctx.arc(px, py, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    ctx.restore();
  }

  /**
   * 绘制透视网格地面（营造 HD-2D 纵深）
   * @param {number} groundY 地面 y 坐标（逻辑坐标）
   */
  drawGround(ctx, groundY, cw, ch) {
    ctx.save();

    // 地面渐变（近深远淡）
    const grad = ctx.createLinearGradient(0, groundY, 0, ch);
    grad.addColorStop(0, 'rgba(30, 27, 75, 0.3)');
    grad.addColorStop(1, 'rgba(15, 10, 35, 0.6)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, groundY, cw, ch - groundY);

    // 透视网格
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.1)';
    ctx.lineWidth = 1;

    // 水平线（向地平线汇聚）
    const horizonY = groundY - 20;
    const gridBottom = ch;
    const rows = 8;
    for (let i = 1; i <= rows; i++) {
      const t = i / rows;
      // 透视位置：非线性靠近地平线
      const y = groundY + Math.pow(t, 1.5) * (gridBottom - groundY);
      ctx.globalAlpha = 0.1 + t * 0.2;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(cw, y);
      ctx.stroke();
    }

    // 垂直线（向消失点汇聚）
    const vanishX = cw / 2;
    const cols = 12;
    ctx.globalAlpha = 0.15;
    for (let i = 0; i <= cols; i++) {
      const t = (i / cols - 0.5) * 2; // -1 ~ 1
      const bottomX = cw / 2 + t * cw * 0.8;
      ctx.beginPath();
      ctx.moveTo(vanishX, horizonY);
      ctx.lineTo(bottomX, gridBottom);
      ctx.stroke();
    }

    ctx.restore();
  }
}
