/* 官网 / 论坛 埋点：进一次页面就留一条【人物记录】（与游戏共用同一指纹库 fp.js）
   页面用 <body data-track="site|forum|hub"> 指定来源；官网与游戏是同一个人 → 只占一条记录，
   payload.pages 里分别记 site/game，方便看"官网曝光 → 进游戏"两层漏斗。 */
(function () {
  function go() {
    var page = (document.body && document.body.getAttribute('data-track')) || 'site';
    if (window.Fp) { try { Fp.track(page); } catch (e) {} }
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') setTimeout(go, 0);
  else document.addEventListener('DOMContentLoaded', go);
})();
