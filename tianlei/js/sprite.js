/* ==========================================================
   精灵帧动画系统
   - 精灵表加载、白底透明化、边缘羽化
   - 帧动画播放器（支持状态机驱动）
   - 6帧格式：0=idle, 1=walk1(迈右腿), 2=run(奔跑腾空), 3=walk2(迈左腿), 4=attack, 5=jump
   ========================================================== */

const SpriteSys = {
  _cache: {},

  /**
   * 加载并处理精灵表
   * 【问题1.5】加 10s 超时、失败自动重试 1 次；最终失败则回退到原始 Image 切帧
   * @param {string} url 精灵表URL
   * @param {number} frameCount 横向帧数
   * @returns {Promise<SpriteSheet>}
   */
  loadSpriteSheet(url, frameCount = 6) {
    const key = `${url}__${frameCount}`;
    if (this._cache[key]) return this._cache[key];

    const promise = this._loadWithRetry(url, frameCount, 1)
      .catch((err) => {
        console.warn('[SpriteSys] 精灵表加载失败，回退到原始切帧模式:', err && err.message);
        // 回退：加载原始图片，不做白底透明化，直接用 drawImage 切帧
        return this._loadFallback(url, frameCount);
      });

    this._cache[key] = promise;
    return promise;
  },

  /**
   * 带超时与重试的加载
   */
  _loadWithRetry(url, frameCount, retriesLeft) {
    return new Promise((resolve, reject) => {
      const TIMEOUT_MS = 10000;
      let done = false;

      const timer = setTimeout(() => {
        if (done) return;
        done = true;
        reject(new Error('sprite load timeout: ' + url));
      }, TIMEOUT_MS);

      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        try {
          const sheet = this._processSheet(img, frameCount);
          resolve(sheet);
        } catch (e) {
          // _processSheet 内部也可能因 getImageData 跨域抛出 SecurityError
          reject(e);
        }
      };
      img.onerror = () => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        reject(new Error('sprite load error: ' + url));
      };
      img.src = url;
    }).catch((err) => {
      if (retriesLeft > 0) {
        console.warn('[SpriteSys] 加载失败，重试剩余 ' + retriesLeft + ' 次:', err.message);
        return this._loadWithRetry(url, frameCount, retriesLeft - 1);
      }
      throw err;
    });
  },

  /**
   * 回退加载：只加载图片，不做透明化处理，直接用原图切帧
   * 即使跨域也能 drawImage 显示（getImageData 才需要 crossOrigin）
   */
  _loadFallback(url, frameCount) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      // 不设 crossOrigin，避免部分 CDN 对 file:// 源返回 CORS 报错
      img.onload = () => {
        const totalW = img.naturalWidth;
        const totalH = img.naturalHeight;
        const fw = Math.floor(totalW / frameCount);
        const fh = totalH;

        const frames = [];
        for (let i = 0; i < frameCount; i++) {
          // 直接创建 canvas 并 drawImage 切片（不需要 getImageData 权限）
          const canvas = document.createElement('canvas');
          canvas.width = fw;
          canvas.height = fh;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, i * fw, 0, fw, fh, 0, 0, fw, fh);
          frames.push(canvas);
        }

        resolve({
          frames,
          frameWidth: fw,
          frameHeight: fh,
          frameCount,
          srcImage: img,
          fallback: true, // 标记为回退模式
        });
      };
      img.onerror = () => reject(new Error('sprite fallback load failed: ' + url));
      img.src = url;
    });
  },

  /**
   * 处理精灵表：切帧 + 白底透明化 + 边缘羽化
   */
  _processSheet(img, frameCount) {
    const totalW = img.naturalWidth;
    const totalH = img.naturalHeight;
    const fw = Math.floor(totalW / frameCount);
    const fh = totalH;

    const frames = [];
    for (let i = 0; i < frameCount; i++) {
      const sx = i * fw;
      const canvas = document.createElement('canvas');
      canvas.width = fw;
      canvas.height = fh;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, sx, 0, fw, fh, 0, 0, fw, fh);

      // 白底透明化 + 边缘羽化
      this._makeWhiteTransparent(ctx, fw, fh);
      frames.push(canvas);
    }

    return {
      frames,
      frameWidth: fw,
      frameHeight: fh,
      frameCount,
      srcImage: img,
    };
  },

  /**
   * 近白色像素转透明，边缘半度羽化防白边
   * 使用阈值 + alpha 渐变
   */
  _makeWhiteTransparent(ctx, w, h) {
    try {
      const imgData = ctx.getImageData(0, 0, w, h);
      const data = imgData.data;

      // 亮度阈值：高于 threshold 开始透明化
      // 羽化区间：threshold ~ threshold + feather，线性渐变
      const threshold = 235;
      const feather = 25;

      for (let i = 0; i < data.length; i += 4) {
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const a = data[i + 3];

        if (a === 0) continue;

        // 亮度（感知亮度）
        const lum = 0.299 * r + 0.587 * g + 0.114 * b;

        if (lum >= threshold + feather) {
          // 纯白 → 完全透明
          data[i + 3] = 0;
        } else if (lum >= threshold) {
          // 羽化区间：alpha 线性衰减
          const t = (lum - threshold) / feather;
          data[i + 3] = Math.floor(a * (1 - t));
          // 同时把颜色往背景色相稍微偏移，减少白边
          const mix = t * 0.5;
          data[i] = Math.floor(r * (1 - mix) + 40 * mix);
          data[i + 1] = Math.floor(g * (1 - mix) + 30 * mix);
          data[i + 2] = Math.floor(b * (1 - mix) + 60 * mix);
        }
        // 低于阈值的像素保持原样
      }

      ctx.putImageData(imgData, 0, 0);
    } catch (e) {
      // 【问题1.5】getImageData 跨域 SecurityError 等异常：直接跳过透明化
      // 帧会保留原始图（白底或透明取决于源图），但至少能显示
      console.warn('[SpriteSys] 白底透明化失败（可能跨域），保留原图:', e.message);
    }
  },
};

/**
 * 动画播放器
 * 由状态机驱动播放不同的帧序列
 */
class AnimPlayer {
  constructor(sheet) {
    this.sheet = sheet;
    this.frameIndex = 0;
    this.timer = 0;
    this.frameDuration = 0.12; // 每帧秒数
    this.sequence = [0]; // 当前播放的帧序列
    this.loop = true;
    this.onComplete = null;
    this.playing = false;
    this.speedScale = 1;
  }

  /**
   * 播放一个动作序列
   * @param {number[]} frames 帧索引数组
   * @param {object} opts { loop, fps, onComplete, speedScale }
   */
  play(frames, opts = {}) {
    this.sequence = frames;
    this.frameIndex = 0;
    this.timer = 0;
    this.loop = opts.loop !== false;
    this.frameDuration = opts.fps ? 1 / opts.fps : 0.12;
    this.onComplete = opts.onComplete || null;
    this.speedScale = opts.speedScale || 1;
    this.playing = true;
  }

  stop() {
    this.playing = false;
  }

  update(dt) {
    if (!this.playing || this.sequence.length <= 1) return;

    this.timer += dt * this.speedScale;
    if (this.timer >= this.frameDuration) {
      this.timer -= this.frameDuration;
      this.frameIndex++;
      if (this.frameIndex >= this.sequence.length) {
        if (this.loop) {
          this.frameIndex = 0;
        } else {
          this.frameIndex = this.sequence.length - 1;
          this.playing = false;
          if (this.onComplete) {
            const cb = this.onComplete;
            this.onComplete = null;
            cb();
          }
        }
      }
    }
  }

  /**
   * 获取当前帧 canvas
   */
  getCurrentFrame() {
    if (!this.sheet || !this.sheet.frames.length) return null;
    const idx = this.sequence[Math.min(this.frameIndex, this.sequence.length - 1)] || 0;
    return this.sheet.frames[idx];
  }

  /**
   * 绘制到 ctx
   */
  draw(ctx, x, y, opts = {}) {
    const frame = this.getCurrentFrame();
    if (!frame) return;

    const w = opts.width || this.sheet.frameWidth;
    const h = opts.height || this.sheet.frameHeight;
    const flip = opts.flip || 1; // 1 或 -1
    const alpha = opts.alpha !== undefined ? opts.alpha : 1;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(x, y);
    ctx.scale(flip, 1);
    ctx.drawImage(frame, -w / 2, -h, w, h);
    ctx.restore();
  }
}
