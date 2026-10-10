/* ==========================================================
   游戏主入口
   ========================================================== */

window.addEventListener('DOMContentLoaded', () => {
  // 初始化布局管理器（最先运行，统一处理尺寸重算）
  if (window.LayoutMgr) LayoutMgr.init();

  // 初始化全屏管理器（处理方向与全屏）
  FullscreenMgr.init();

  // 初始化游戏系统
  AudioMgr.init();
  Player.init();
  BattleSys.init();
  SceneMgr.init();
  InputMgr.init();

  // 尝试加载存档
  GameState.load();

  // 检测缩略图模式
  const isThumbnail = new URLSearchParams(window.location.search).has('thumbnail');

  if (isThumbnail) {
    // 缩略图模式：直接定格在主菜单，不走全屏启动
    document.getElementById('fsOverlay').style.display = 'none';
    SceneMgr.show('menu');
  } else {
    // 正常模式：显示全屏启动遮罩，等待用户点击进入
    const fsBtn = document.getElementById('fsEnterBtn');
    const fsOverlay = document.getElementById('fsOverlay');

    const startGame = () => {
      // 【问题1.2】整体 try/catch：任何一步抛错都要保证遮罩消失、进入游戏
      try {
        // 【问题2】全屏请求后台异步执行，成功与否都不阻塞进入游戏
        // 防止某些安卓 WebView 中 requestFullscreen 永久挂起导致卡死
        FullscreenMgr.enter().catch(e => console.warn('FullscreenMgr.enter error:', e));

        // 立即淡出遮罩、进入开场过场，不等全屏结果
        fsOverlay.classList.add('fade-out');
        setTimeout(() => {
          fsOverlay.style.display = 'none';
        }, 500);

        // 从开场过场开始
        SceneMgr.show('opening');

        // 音频恢复（移动端需要用户手势后才能播放）
        AudioMgr.resume();

        // 初始化章节进度管理
        if (window.ChapterMgr) ChapterMgr.init();

        // 开场过场点击后进入剧情/第一章（只绑定一次）
        const openingScene = document.getElementById('openingScene');
        if (openingScene && !openingScene._chapterBound) {
          openingScene._chapterBound = true;
          openingScene.addEventListener('click', () => {
            try {
              // 【联机改造】开场点击后直接进入"联机 RPG 开放世界"
              // （原第一章剧情仍保留，可从主菜单「开始游戏」进入）
              SceneMgr.show('hub');
            } catch (e) {
              console.error('开场点击出错，兜底进入菜单:', e);
              SceneMgr.show('menu');
            }
          });
        }
      } catch (e) {
        console.error('startGame 异常，兜底进入游戏:', e);
        // 强行移除遮罩，进入菜单作为最后兜底
        fsOverlay.classList.add('fade-out');
        fsOverlay.style.display = 'none';
        try { SceneMgr.show('menu'); } catch (e2) { /* noop */ }
      }
    };

    fsBtn.addEventListener('click', startGame);

    // 键盘回车也可进入
    document.addEventListener('keydown', function onKey(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        document.removeEventListener('keydown', onKey);
        startGame();
      }
    });
  }
  
  // 页面可见性变化 - 自动暂停
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (GameState.currentScene === 'battle' && !GameState.battle.paused) {
        BattleSys.pause();
        document.getElementById('battlePausePanel').classList.remove('hidden');
      }
    }
  });
  
  // 防止长按选中和手势缩放
  document.addEventListener('gesturestart', e => e.preventDefault());
  document.addEventListener('contextmenu', e => e.preventDefault());
  
  console.log('天泪纪元：学院篇 - 游戏初始化完成');
  console.log('操作说明：');
  console.log('  移动：WASD / 方向键 / 左下虚拟摇杆');
  console.log('  普攻：J');
  console.log('  虚空闪现（位移）：U');
  console.log('  虚空禁锢：K');
  console.log('  空间切割：L');
  console.log('  大招·虚空领域：I');
  console.log('  闪避：O');
});
