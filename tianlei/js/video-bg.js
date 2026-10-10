/* ==========================================================
   动态视频背景管理器
   - 为横版场景提供可选的视频背景层
   - 视频优先级 > 静态背景图；视频加载失败/不支持自动回退到静态图
   - 支持 muted loop autoplay playsinline，兼容移动端 WebView
   - 与多层视差、Y轴排序、动态阴影共存（视频在最底层）
   ========================================================== */

const VideoBgMgr = {
  _videoEl: null,
  _currentUrl: null,
  _playing: false,
  _fallbackCallback: null,

  /**
   * 初始化（在 DOM ready 后调用一次）
   */
  init() {
    // 创建 video 元素，默认隐藏
    const v = document.createElement('video');
    v.id = 'videoBg';
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.setAttribute('webkit-playsinline', 'true');
    v.setAttribute('playsinline', 'true');
    v.autoplay = true;
    v.preload = 'auto';
    v.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
      z-index: 0;
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.5s ease;
      display: none;
    `;
    // 插入到 body 最前面（canvas 之上、UI 之下——但 canvas 透明时能透出视频）
    // 实际由各场景决定插入位置；这里统一管理但默认隐藏
    document.body.insertBefore(v, document.body.firstChild);
    this._videoEl = v;

    // 错误处理：加载失败则回退
    v.addEventListener('error', () => {
      console.warn('[VideoBgMgr] 视频加载失败，回退到静态背景:', this._currentUrl);
      this._doFallback();
    });

    // 无法自动播放时回退
    v.addEventListener('play', () => {
      this._playing = true;
      v.style.opacity = '1';
    });
  },

  /**
   * 播放指定视频作为背景
   * @param {string} url 视频URL，为 null/空则停止并显示静态背景
   * @param {Function} fallbackCb 回退时调用（用于触发静态背景显示）
   */
  play(url, fallbackCb) {
    if (!this._videoEl) this.init();
    const v = this._videoEl;

    this._fallbackCallback = fallbackCb || null;

    // url 为空 → 停止视频，走静态背景
    if (!url) {
      this.stop();
      if (fallbackCb) fallbackCb();
      return;
    }

    // 同 URL 不重复加载
    if (this._currentUrl === url && this._playing) {
      v.style.display = 'block';
      v.style.opacity = '1';
      return;
    }

    this._currentUrl = url;
    v.style.display = 'block';
    v.style.opacity = '0';
    v.src = url;

    // 8 秒超时仍未开始播放 → 回退
    this._timeoutId = setTimeout(() => {
      if (!this._playing) {
        console.warn('[VideoBgMgr] 视频加载超时，回退到静态背景');
        this._doFallback();
      }
    }, 8000);

    // 尝试播放（移动端需要用户手势，但我们是在用户点击进入后启动）
    const playPromise = v.play();
    if (playPromise && playPromise.catch) {
      playPromise.catch((e) => {
        console.warn('[VideoBgMgr] 视频自动播放被阻止，回退:', e.message);
        this._doFallback();
      });
    }
  },

  /**
   * 停止视频背景，隐藏元素
   */
  stop() {
    if (!this._videoEl) return;
    const v = this._videoEl;
    try { v.pause(); } catch (e) {}
    v.style.opacity = '0';
    v.style.display = 'none';
    this._playing = false;
    this._currentUrl = null;
    if (this._timeoutId) {
      clearTimeout(this._timeoutId);
      this._timeoutId = null;
    }
  },

  _doFallback() {
    if (this._fallbackCallback) {
      const cb = this._fallbackCallback;
      this._fallbackCallback = null;
      try { cb(); } catch (e) { console.warn('[VideoBgMgr] fallback error:', e); }
    }
    this.stop();
  },
};
