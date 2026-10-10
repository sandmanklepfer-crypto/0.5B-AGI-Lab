/* ==========================================================
   布局管理器（统一处理尺寸重算的防抖与稳定化）
   - 监听 resize / orientationchange / fullscreenchange / visualViewport.resize
   - 所有尺寸重算统一走 requestAnimationFrame + 防抖(150ms)
   - 事件触发后连续重算直到两次结果完全一致，确保取到最终稳定尺寸
   ========================================================== */

const LayoutMgr = {
  _timer: null,
  _rafId: null,
  _lastW: 0,
  _lastH: 0,
  _stableCount: 0,
  _callbacks: [],
  _debounceMs: 150,
  _maxRetries: 10,
  _retryCount: 0,

  init() {
    // 主 resize 监听
    window.addEventListener('resize', () => this._schedule());

    // 方向变化
    window.addEventListener('orientationchange', () => {
      this._schedule(200); // 方向切换后延迟更久
    });
    if (screen.orientation && screen.orientation.addEventListener) {
      screen.orientation.addEventListener('change', () => this._schedule(200));
    }

    // 全屏变化
    const fsHandler = () => this._schedule(200);
    document.addEventListener('fullscreenchange', fsHandler);
    document.addEventListener('webkitfullscreenchange', fsHandler);
    document.addEventListener('msfullscreenchange', fsHandler);

    // visualViewport（地址栏收起/展开、虚拟键盘）
    if (window.visualViewport && window.visualViewport.addEventListener) {
      window.visualViewport.addEventListener('resize', () => this._schedule());
      window.visualViewport.addEventListener('scroll', () => this._schedule());
    }

    // matchMedia 方向变化
    if (window.matchMedia) {
      const mql = window.matchMedia('(orientation: landscape)');
      const handler = () => this._schedule(200);
      if (mql.addEventListener) mql.addEventListener('change', handler);
      else if (mql.addListener) mql.addListener(handler);
    }
  },

  /**
   * 注册重算回调，尺寸稳定后触发
   * @param {Function} cb 回调函数
   */
  onResize(cb) {
    if (typeof cb === 'function' && this._callbacks.indexOf(cb) === -1) {
      this._callbacks.push(cb);
    }
  },

  /**
   * 立即触发一次重算（不防抖），用于初始化
   */
  triggerNow() {
    this._fire();
  },

  _schedule(delay) {
    const ms = typeof delay === 'number' ? delay : this._debounceMs;
    if (this._timer) clearTimeout(this._timer);
    this._timer = setTimeout(() => {
      this._retryCount = 0;
      this._stableCount = 0;
      this._lastW = 0;
      this._lastH = 0;
      this._tick();
    }, ms);
  },

  _tick() {
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = requestAnimationFrame(() => {
      const dims = this._getDims();
      const w = dims.w;
      const h = dims.h;

      if (w === this._lastW && h === this._lastH) {
        this._stableCount++;
      } else {
        this._stableCount = 0;
        this._lastW = w;
        this._lastH = h;
      }

      // 先执行一次（快速响应）
      this._fire();

      // 需要稳定：连续两次相同，或达到最大重试次数
      if (this._stableCount < 1 && this._retryCount < this._maxRetries) {
        this._retryCount++;
        // 间隔 80ms 再测一次
        this._timer = setTimeout(() => this._tick(), 80);
      }
    });
  },

  _getDims() {
    // 优先用 gameContainer 的实际尺寸（受旋转模式影响）
    const gc = document.getElementById('gameContainer');
    if (gc) {
      return { w: gc.offsetWidth, h: gc.offsetHeight };
    }
    return { w: window.innerWidth, h: window.innerHeight };
  },

  _fire() {
    for (let i = 0; i < this._callbacks.length; i++) {
      try {
        this._callbacks[i]();
      } catch (e) {
        console.warn('LayoutMgr callback error:', e);
      }
    }
  },
};
