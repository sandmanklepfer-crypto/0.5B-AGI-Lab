/* ==========================================================================
   hd2d_arena.js —— 适配层：把 octo 的 HD-2D 世界包装成战斗模块要的 ARENA 接口
   --------------------------------------------------------------------------
   这样联机/战斗/建造 等模块（shooter.js 那套）可以直接跑在 **HD-2D 世界**里，
   而不是另开一个 3D 场景。坐标：1 格 = 1 世界单位（与 octo 的 hero.x/y 一致）。
   ========================================================================== */
(function () {
'use strict';
function ready() {
  var O = window.__OCTO, TW = window.TileWorld;
  if (!O || !TW) { window.__hdErr = '缺 __OCTO 或 TileWorld'; return; }
  if (window.ARENA) return;
  var MW = TW.MW, MH = TW.MH;
  var H = new Float32Array(MW * MH);
  for (var v = 0; v < MH; v++) for (var u = 0; u < MW; u++) H[v * MW + u] = TW.isSolid(u + 0.5, v + 0.5) ? 1.6 : 0;
  var CITY0 = MW, CITYW = 90;                 // ★ 东侧城市：x ∈ [MW, MW+90]
  function hh(x, z) {
    if (x >= CITY0) { if (x > CITY0 + CITYW || z < 0 || z > MH) return 1.6; return 0; }   // 城市 = 平地
    var u = Math.floor(x), v = Math.floor(z); if (u < 0 || v < 0 || u >= MW || v >= MH) return 1.6; return H[v * MW + u];
  }
  var Ground = {
    GW: MW, GH: MH, TILE: 1, H: H, WALL_H: 1.6, YMIN: -2, world: MW,
    h: hh, floor: hh,
    canStand: function (nx, nz, y, step) { step = step === undefined ? 0.62 : step; if (nx < 1 || nz < 1 || nx > MW - 1 || nz > MH - 1) return false; return (hh(nx, nz) - y) <= step; },
    ray: function (ox, oy, oz, dx, dy, dz, maxD) {
      maxD = Math.min(maxD, 200);
      for (var d = 0.12; d < maxD; d += 0.12) { var x = ox + dx * d, y = oy + dy * d, z = oz + dz * d; if (y <= hh(x, z)) return { dist: d, x: x, y: y, z: z }; }
      return { dist: maxD, x: ox + dx * maxD, y: oy + dy * maxD, z: oz + dz * maxD };
    },
    pick: function (fx, fz, minD) {
      var best = null, bd = -1;
      for (var k = 0; k < 80; k++) {
        var u = 2 + Math.floor(Math.random() * (MW - 4)), v = 2 + Math.floor(Math.random() * (MH - 4));
        if (H[v * MW + u] > 0.1) continue;
        var x = u + 0.5, z = v + 0.5, dd = Math.hypot(x - fx, z - fz);
        if (dd >= (minD || 0)) return { x: x, z: z, y: 0 };
        if (dd > bd) { bd = dd; best = { x: x, z: z, y: 0 }; }
      }
      return best || { x: TW.MW / 2 + 0.5, z: TW.MH / 2 + 0.5, y: 0 };
    },
  };
  window.ARENA = {
    TILE: 1, GW: MW, GH: MH, H: H, world: MW, LEAN: { pixel: 1, rain: 0 },
    Ground: Ground, scene: O.scene, renderer: O.renderer, camera: O.camP, orthoCam: O.cam, CAM_DIR: O.CAM_DIR,
    getCam: function () { return O.mode === 'persp' ? O.camP : O.cam; },
    setCamMode: function (m) { O.setMode(m); return O.mode; },
    getCamMode: function () { return O.mode; },
    setOrthoVH: function (v) { if (O.setZoom) O.setZoom(Math.max(0.12, Math.min(4, 11.25 / Math.max(2, v))), 0); },   // v=45→视野~96格(看得到城市)
    getOrthoVH: function () { return 24; },
    setOrthoHW: function (w) { if (O.setZoom) O.setZoom(1, w); },
    getOrthoHW: function () { return 0; },
    update: function () {}, setLean: function () {}, injectGI: function () {},
    grounds: [], getGround: function () { return 'asphalt'; }, setGround: function () { return true; },
    getRain: function () { return true; }, setRain: function () { return true; },
    getSpot: function () { return false; }, setSpot: function () { return true; },
    resize: function () {}, moon: { position: (window.THREE ? new THREE.Vector3(0.6, 0.9, 0.5) : { x: 0.6, y: 0.9, z: 0.5 }) }, matSide: null, matGlass: null,
    topMesh: function () { return null; }, GI: function () { return null; },
  };
  /* 东侧城市由 arena3d.js（附加模式）提供，这里不再自建 */

  window.__hdArenaReady = true;
  try { console.log('[hd2d_arena] 就绪：HD-2D 世界已适配为 ARENA'); } catch (e) {}
}
if (window.__OCTO) ready(); else setTimeout(ready, 300);
})();
