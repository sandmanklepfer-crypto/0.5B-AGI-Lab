/* ==========================================================
   全屏与方向适配管理器
   - 启动全屏遮罩 + 进入全屏
   - 横屏锁定（不支持则静默跳过）
   - 竖屏自动旋转90度适配（标准方案：transform-origin 0 0 + rotate(90deg) translateY(-100vw)）
   - 动态视口与安全区域适配
   - 监听 fullscreenchange / orientationchange 自动重适配
   - 旋转模式下触摸坐标正确换算
   - 尺寸重算统一走 LayoutMgr（防抖 + 稳定化）
   ========================================================== */

const FullscreenMgr = {
  isFullscreen: false,
  isPortrait: false,
  forceRotate: false, // 是否启用强制旋转模式（竖屏且无法锁定时）
  orientationLocked: false,

  init() {
    this.detectOrientation();
    this.bindEvents();
    this.updateDeviceTip();
    this.applyLayout();
  },

  // 检测当前方向（优先 matchMedia + 视口尺寸双保险）
  detectOrientation() {
    let landscape = false;

    // 方法1: matchMedia（最准确，反映CSS媒体查询方向）
    if (window.matchMedia && window.matchMedia('(orientation: landscape)').matches) {
      landscape = true;
    }

    // 方法2: 视口尺寸对比（最终兜底）
    const w = window.innerWidth;
    const h = window.innerHeight;
    if (w > h) landscape = true;
    else if (w < h) landscape = false;
    // w == h 时以 matchMedia 为准

    this.isPortrait = !landscape;
    return this.isPortrait;
  },

  // 绑定事件
  bindEvents() {
    // 全屏变化
    const fsChange = () => {
      this.isFullscreen = !!(document.fullscreenElement ||
                             document.webkitFullscreenElement ||
                             document.msFullscreenElement);
      this.syncToggleUI();
      // 全屏切换后方向可能变化，重新检测并应用
      this.detectOrientation();
      this.applyLayout();
      // 交给 LayoutMgr 做防抖稳定化重算
      if (window.LayoutMgr) LayoutMgr._schedule(250);
    };
    document.addEventListener('fullscreenchange', fsChange);
    document.addEventListener('webkitfullscreenchange', fsChange);
    document.addEventListener('msfullscreenchange', fsChange);

    // 方向变化（由 LayoutMgr 统一监听并调度，这里只负责状态更新）
    const orientChange = () => {
      this.detectOrientation();
      this.applyLayout();
      this.updateDeviceTip();
    };
    window.addEventListener('orientationchange', () => {
      // orientationchange 后尺寸可能还没更新，先标记，LayoutMgr 会稳定化
      setTimeout(() => {
        this.detectOrientation();
        this.applyLayout();
        this.updateDeviceTip();
      }, 150);
    });

    if (screen.orientation && screen.orientation.addEventListener) {
      screen.orientation.addEventListener('change', orientChange);
    }

    // matchMedia 方向变化（兼容性最好）
    if (window.matchMedia) {
      const mql = window.matchMedia('(orientation: landscape)');
      if (mql.addEventListener) {
        mql.addEventListener('change', orientChange);
      } else if (mql.addListener) {
        mql.addListener(orientChange);
      }
    }
  },

  // 请求进入全屏 + 横屏锁定
  async enter() {
    // 【问题2】所有异步操作用 800ms 超时保护，防止安卓 WebView 中 Promise 挂起
    let fsOk = false;

    const timeout = (ms) => new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms));

    try {
      const el = document.documentElement;
      if (el.requestFullscreen) {
        // 用 Promise.race 加超时保护
        await Promise.race([
          el.requestFullscreen(),
          timeout(800),
        ]);
        fsOk = true;
      } else if (el.webkitRequestFullscreen) {
        el.webkitRequestFullscreen();
        fsOk = true;
      } else if (el.msRequestFullscreen) {
        el.msRequestFullscreen();
        fsOk = true;
      }
    } catch (e) {
      console.warn('全屏请求失败或超时:', e.message);
    }

    // 尝试锁定横屏（也加超时保护）
    try {
      await Promise.race([
        this.tryLockLandscape(),
        timeout(800),
      ]);
    } catch (e) {
      console.warn('横屏锁定超时或失败:', e.message);
    }

    // 计算方向并应用布局（等一下让浏览器完成全屏+方向切换）
    setTimeout(() => {
      this.detectOrientation();
      this.applyLayout();
      if (window.LayoutMgr) LayoutMgr._schedule(300);
    }, 250);

    return fsOk;
  },

  // 尝试锁定横屏
  async tryLockLandscape() {
    try {
      if (screen.orientation && screen.orientation.lock) {
        await screen.orientation.lock('landscape');
        this.orientationLocked = true;
      }
    } catch (e) {
      // 不支持或被拒绝，静默。改用CSS旋转方案兜底
      this.orientationLocked = false;
    }
  },

  // 应用布局（根据方向决定是否强制旋转）
  applyLayout() {
    const body = document.body;

    // 方向锁已成功 → 不用旋转
    // 方向锁失败 且 是竖屏 → 启用CSS强制旋转
    if (this.isPortrait && !this.orientationLocked) {
      body.classList.add('portrait-forced');
      this.forceRotate = true;
      this.showPortraitTip();
    } else {
      body.classList.remove('portrait-forced');
      this.forceRotate = false;
      this.hidePortraitTip();
    }

    // 通知游戏核心重新计算画布尺寸
    // （由 LayoutMgr 统一防抖调度，这里只做必要的立即响应）
    if (typeof HubMgr !== 'undefined' && HubMgr.resize) {
      HubMgr.resize();
    }
    if (typeof BattleSys !== 'undefined' && BattleSys.resize) {
      BattleSys.resize();
    }
  },

  /**
   * 将屏幕坐标（clientX/clientY）转换为游戏容器内的逻辑坐标
   * 在强制旋转模式下需要反向换算
   */
  screenToContainer(clientX, clientY) {
    if (!this.forceRotate) {
      // 正常横屏：直接相对于 gameContainer
      const container = document.getElementById('gameContainer');
      const rect = container.getBoundingClientRect();
      return { x: clientX - rect.left, y: clientY - rect.top };
    }

    // 竖屏强制横屏模式：
    // 容器 width=100vh, height=100vw
    // transform-origin: 0 0
    // transform: rotate(90deg) translateY(-100vw)
    //
    // 旋转前（屏幕坐标下容器的左上角）在 (0, 100vw)
    // 容器 X 轴正向 = 屏幕 Y 轴正向
    // 容器 Y 轴正向 = 屏幕 X 轴负向
    //
    // 设容器内点 (cx, cy)，对应屏幕点 (sx, sy)：
    //   sx = 容器宽 - cy   （Y反向，从容器顶到容器底 = 屏幕右到左）
    //   sy = cx            （X正向 = 屏幕Y正向）
    // 反向：
    //   cx = sy
    //   cy = 容器宽 - sx

    const containerW = window.innerHeight; // 容器宽 = 视口高（100dvh）
    return {
      x: clientY,
      y: containerW - clientX,
    };
  },

  // 竖屏旋转提示
  showPortraitTip() {
    let tip = document.getElementById('portraitTip');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'portraitTip';
      tip.className = 'portrait-tip';
      tip.innerHTML = '<div class="rotate-icon">📱</div><div>请将手机横屏<br>获得最佳体验</div>';
      document.body.appendChild(tip);
    }
    tip.classList.add('show');
    clearTimeout(this._tipTimer);
    this._tipTimer = setTimeout(() => {
      tip.classList.remove('show');
    }, 5000);
  },

  hidePortraitTip() {
    const tip = document.getElementById('portraitTip');
    if (tip) tip.classList.remove('show');
  },

  // 启动页设备提示文字
  updateDeviceTip() {
    const tip = document.getElementById('fsDeviceTip');
    if (!tip) return;
    const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    if (isMobile) {
      tip.textContent = '点击后自动适配横屏';
    } else {
      tip.textContent = '推荐使用手机浏览器访问';
    }
  },

  // 同步设置面板的全屏开关UI
  syncToggleUI() {
    const toggle = document.getElementById('fullscreenToggle');
    if (!toggle) return;
    toggle.classList.toggle('active', this.isFullscreen);
  },

  // 设置面板开关切换全屏
  toggleFullscreen() {
    if (this.isFullscreen) {
      this.exitFullscreen();
    } else {
      this.enter();
    }
  },

  exitFullscreen() {
    try {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
      }
    } catch (e) {
      // 静默
    }
  },
};
