/* ==========================================================================
   arena3d.js —— 天泪纪元 · 雨夜立体竞技场（3A 质感 PBR / 探照灯 / 下雨 / 换地面）
   --------------------------------------------------------------------------
   · 立体高度场地图（街道 / 二层 / 高台 / 天台 / 地下 / 天桥 / 楼梯）
   · 地面：多套 PBR 贴图可切换（王炸雨夜沥青 / 花岗岩 / 大理石 / 钢板 / 草地 / 湿土）
   · 建筑：钢铁 + 玻璃幕墙 PBR（金属度高、反射霓虹、发光窗格）
   · 楼顶探照灯扫射 → 地面色彩溢出（SpotLight + 体积光锥）
   · 下雨 + 湿地面环境反射（CubeCamera 探针 → 地面反出霓虹）
   对外：ARENA.{scene,renderer,camera,Ground,TILE,...,setGround,grounds,setRain,update}
   ========================================================================== */
(function () {
'use strict';
if (window.ARENA) return;   // 幂等：不重复建场景
try {
if (typeof THREE === 'undefined') { document.body.innerHTML = '<pre style="color:#f88;padding:30px">three.js 未加载</pre>'; return; }

var TILE = 3.0, GW = 76, GH = 52, WALL_H = 11.5, YMIN = -6.5, WORLD = GW * TILE;
var OFF_U = 24;   // 城市整体东移（西侧 OFF_U 格 = 农村营地）
/* 离线烘焙 GI（全局光照）：把霓虹/探照灯/街灯光色烘进贴图，按世界坐标采样 → 表面被"染色" */
var GI_TEX = null, GI_EM = [];
function emAdd(x, z, y, hex, p, rad, force) {
  if (!force) {
    if (GI_EM.length > 150) return;
    for (var i = 0; i < GI_EM.length; i++) { if (Math.abs(GI_EM[i].x - x) < 5 && Math.abs(GI_EM[i].z - z) < 5) return; }   // 网格化去重
  }
  var c = new THREE.Color(hex);
  GI_EM.push({ x: x, z: z, y: y, r: c.r, g: c.g, b: c.b, p: p, rad: rad || 44 });
}
var H = new Float32Array(GW * GH);
function setH(u, v, h) { if (u >= 0 && v >= 0 && u < GW && v < GH) H[v * GW + u] = h; }
function getH(u, v) { if (u < 0 || v < 0 || u >= GW || v >= GH) return WALL_H; return H[v * GW + u]; }
function rnd(a, b) { return a + Math.random() * (b - a); }

/* ---------------- 地图（保留原布局） ---------------- */
var ATTACH = !!window.__ATTACH_CITY;   // ★ 必须最先定义（buildMap 要用）
(function buildMap() {
  var i, j, u, v;
  for (v = 0; v < GH; v++) for (u = 0; u < GW; u++) H[v * GW + u] = 0;
  for (i = 0; i < GW; i++) { setH(i, 0, WALL_H); setH(i, 1, WALL_H); setH(i, GH - 1, WALL_H); setH(i, GH - 2, WALL_H); }
  for (j = 0; j < GH; j++) { if (!ATTACH) { setH(0, j, WALL_H); setH(1, j, WALL_H); } setH(GW - 1, j, WALL_H); setH(GW - 2, j, WALL_H); }   // ★ 附加模式：西墙全开（与营地畅通）   // ★ 附加模式：西侧留一个大门与营地连通
  function rect(x0, y0, x1, y1, h) { x0 += OFF_U; x1 += OFF_U; for (var v2 = y0; v2 <= y1; v2++) for (var u2 = x0; u2 <= x1; u2++) setH(u2, v2, h); }
  function stairX(x0, y0, x1, y1, h0, h1) { var n = x1 - x0 + 1; for (var k = 0; k < n; k++) { var h = h0 + (h1 - h0) * (k / Math.max(1, n - 1)); rect(x0 + k, y0, x0 + k, y1, +h.toFixed(3)); } }
  function stairZ(x0, y0, x1, y1, h0, h1) { var n = y1 - y0 + 1; for (var k = 0; k < n; k++) { var h = h0 + (h1 - h0) * (k / Math.max(1, n - 1)); rect(x0, y0 + k, x1, y0 + k, +h.toFixed(3)); } }
  rect(5, 5, 14, 13, 3.2); rect(20, 5, 32, 15, 6.4); rect(37, 4, 47, 13, 3.2);
  rect(6, 26, 18, 37, 6.4); rect(34, 27, 46, 41, 9.6); rect(23, 21, 31, 29, 3.2);
  rect(22, 37, 33, 46, -3.2); stairZ(22, 35, 33, 36, 0, -3.2); rect(26, 35, 30, 36, 0);
  rect(27, 33, 28, 40, 3.2);
  stairX(14, 6, 18, 12, 0, 3.2); stairZ(21, 16, 31, 19, 0, 6.4); stairX(33, 6, 36, 12, 0, 3.2);
  stairX(19, 27, 22, 36, 0, 6.4); stairZ(35, 23, 45, 26, 0, 9.6); stairX(19, 22, 22, 28, 0, 3.2);
  var cov = [[8, 20], [12, 20], [24, 17], [28, 17], [40, 18], [44, 18], [15, 42], [19, 42], [40, 22], [44, 22], [10, 12], [24, 26]];
  for (var c = 0; c < cov.length; c++) { var cu = cov[c][0], cv = cov[c][1]; rect(cu, cv, cu + 1, cv, 1.1); rect(cu, cv + 1, cu + 1, cv + 1, 1.1); }
  var pil = [[17, 20], [33, 20], [17, 33], [33, 33], [3, 20], [48, 20], [20, 48], [32, 48]];
  for (var p = 0; p < pil.length; p++) rect(pil[p][0], pil[p][1], pil[p][0], pil[p][1] + 1, 6.4);
})();

var Ground = {
  GW: GW, GH: GH, TILE: TILE, H: H, WALL_H: WALL_H, YMIN: YMIN, world: WORLD,
  h: function (x, z) { return getH(Math.floor(x / TILE), Math.floor(z / TILE)); },
  canStand: function (nx, nz, y, step) {
    step = step === undefined ? 0.62 : step;
    if (nx < TILE * 1.6 || nz < TILE * 1.6 || nx > WORLD - TILE * 1.6 || nz > WORLD - TILE * 1.6) return false;
    return (this.h(nx, nz) - y) <= step;
  },
  floor: function (x, z) { return this.h(x, z); },
  ray: function (ox, oy, oz, dx, dy, dz, maxD) {
    for (var t = 0.15; t < maxD; t += 0.1) {
      var x = ox + dx * t, y = oy + dy * t, z = oz + dz * t;
      if (y < YMIN) return { dist: t, x: x, y: YMIN, z: z };
      if (y <= getH(Math.floor(x / TILE), Math.floor(z / TILE))) return { dist: t, x: x, y: y, z: z };
    }
    return { dist: maxD, x: ox + dx * maxD, y: oy + dy * maxD, z: oz + dz * maxD };
  },
  pick: function (fx, fz, minDist) {
    var best = { x: 26 * TILE, z: 20 * TILE, y: 0 }, bd = -1;
    for (var k = 0; k < 44; k++) {
      var u = 3 + Math.floor(Math.random() * (GW - 6)), v = 3 + Math.floor(Math.random() * (GH - 6));
      var h = getH(u, v); if (h > 7) continue;
      var x = (u + 0.5) * TILE, z = (v + 0.5) * TILE, d = Math.hypot(x - fx, z - fz);
      if (d >= minDist) return { x: x, z: z, y: h };
      if (d > bd) { bd = d; best = { x: x, z: z, y: h }; }
    }
    return best;
  },
};

/* ---------------- 渲染器 / 场景 / 相机 ---------------- */
var cv = ATTACH ? null : document.getElementById('cv');
var renderer = ATTACH ? window.__ATTACH_RENDERER : new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: false, preserveDrawingBuffer: true });
var LEAN = { reflect: false, spotLights: false, pointLights: false, pixel: 1.0, rain: 450 };   // ★ 移动端性能优先
if (!ATTACH) renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, LEAN.pixel));
if (!ATTACH) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }
if (!ATTACH && THREE.sRGBEncoding) renderer.outputEncoding = THREE.sRGBEncoding;
if (!ATTACH && THREE.ACESFilmicToneMapping) { renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0; }

var scene = ATTACH ? (function () { var g = new THREE.Group(); g.position.x = 72; g.userData.attachCity = true; window.__ATTACH_SCENE.add(g); return g; })() : new THREE.Scene();
if (THREE.FogExp2) scene.fog = new THREE.FogExp2(0x0a0d18, 0.0038);
scene.background = (function () {
  var c = document.createElement('canvas'); c.width = 64; c.height = 512; var g = c.getContext('2d');
  var gr = g.createLinearGradient(0, 0, 0, 512);
  gr.addColorStop(0, '#05070f'); gr.addColorStop(0.42, '#0d1220'); gr.addColorStop(0.72, '#22242e'); gr.addColorStop(0.88, '#453b3a'); gr.addColorStop(1, '#6a5346');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 512);
  for (var i = 0; i < 190; i++) { g.fillStyle = 'rgba(200,215,240,' + (Math.random() * 0.4) + ')'; g.fillRect(Math.random() * 64, Math.random() * 260, 1, 1); }
  var t = new THREE.CanvasTexture(c); t.mapping = THREE.EquirectangularReflectionMapping; return t;
})();
var camera = new THREE.PerspectiveCamera(74, 1, 0.08, 700); camera.rotation.order = 'YXZ';
/* ★ 同一世界 · 双视角相机：HD-2D（正交45°锁死） ↔ 透视（自由旋转） */
var CAM_DIR = new THREE.Vector3(Math.cos(Math.PI / 6) * Math.cos(Math.PI / 4), Math.sin(Math.PI / 6), Math.cos(Math.PI / 6) * Math.sin(Math.PI / 4)).normalize();
var orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 900);
var camMode = 'persp';
var orthoVH = 9, orthoHW = 0;
function getCam() { return camMode === 'hd2d' ? orthoCam : camera; }
function setOrthoVH(v) { orthoVH = Math.max(2, Math.min(60, v || 9)); resize(); }
function setOrthoHW(v) { orthoHW = (v > 0) ? Math.max(2, Math.min(120, v)) : 0; resize(); }
function getOrthoHW() { return orthoHW; }
function setCamMode(m) { camMode = (m === 'hd2d') ? 'hd2d' : 'persp'; return camMode; }
function getCamMode() { return camMode; }
function resize() {
  if (ATTACH) return;
  var W = window.innerWidth, Hh = window.innerHeight;
  renderer.setSize(W, Hh, false); cv.style.width = W + 'px'; cv.style.height = Hh + 'px';
  camera.aspect = W / Math.max(1, Hh); camera.updateProjectionMatrix();
  var _vh = orthoVH, _asp = W / Math.max(1, Hh), _hw = orthoHW > 0 ? orthoHW : _vh * _asp;
  orthoCam.left = -_hw; orthoCam.right = _hw; orthoCam.top = _vh; orthoCam.bottom = -_vh;
  orthoCam.updateProjectionMatrix();
}
if (!ATTACH) window.addEventListener('resize', resize);

/* ---------------- PBR 贴图集（assets/tex：albedo + normal + roughness） ---------------- */
var TL = new THREE.TextureLoader();
function tex(url, srgb, repeat) {
  var t = TL.load(url);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  if (srgb && THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
  t.anisotropy = Math.min(8, renderer.capabilities && renderer.capabilities.getMaxAnisotropy ? renderer.capabilities.getMaxAnisotropy() : 8);
  if (repeat) t.repeat.set(repeat, repeat);
  return t;
}
/* 地面可选材质（名称 → 贴图 + 物理参数）；沥青 = 之前那张「王炸雨夜沥青」 */
var GROUNDS = [
  { id: 'asphalt', name: '瑞丽沥青', base: 'city',   metal: 0.18, rough: 0.72, tint: 0xe6ebf5, refl: 0.85, uvRep: 0.7 },
  { id: 'granite', name: '花岗岩',   base: 'stone',  metal: 0.10, rough: 0.88, tint: 0xd2cdc4, refl: 0.45, uvRep: 0.8 },
  { id: 'marble',  name: '大理石',   base: 'marble', metal: 0.12, rough: 0.62, tint: 0xdcd8ce, refl: 0.7, uvRep: 0.9 },
  { id: 'steel',   name: '钢板',     base: 'city',   metal: 0.80, rough: 0.30, tint: 0xaebfd4, refl: 1.2, uvRep: 0.6 },
  { id: 'grass',   name: '草地',     base: 'grass',  metal: 0.02, rough: 1.0,  tint: 0xa6bf8e, refl: 0.06, uvRep: 1.2 },
  { id: 'dirt',    name: '湿土',     base: 'dirt',   metal: 0.05, rough: 0.95, tint: 0xad967c, refl: 0.18, uvRep: 0.8 },
  { id: 'wood',    name: '木栈道',   base: 'wood',   metal: 0.04, rough: 0.82, tint: 0xc8b090, refl: 0.22, uvRep: 0.9 },
];
var GROUNDSETS = {};
GROUNDS.forEach(function (g) {
  var rep2 = g.uvRep || 3;                       // 一张贴图铺几格（越大越细密）
  var set = { map: tex('assets/tex/' + g.base + '.jpg', true, rep2) };
  var hasN = (g.base !== 'dirt' && g.base !== 'marble');
  if (hasN) set.normalMap = tex('assets/tex/' + g.base + '_n.png', false, rep2);
  set.roughnessMap = tex('assets/tex/' + g.base + '_r.png', false, rep2);
  GROUNDSETS[g.id] = set;
});

/* ---------------- 钢铁楼 / 玻璃幕墙（程序化 PBR 贴图） ---------------- */
function makeSteel() {
  var c = document.createElement('canvas'); c.width = c.height = 256; var g = c.getContext('2d');
  g.fillStyle = '#7b8493'; g.fillRect(0, 0, 256, 256);
  for (var y = 0; y < 256; y += 2) {            // 竖向拉丝金属
    g.fillStyle = 'rgba(' + (150 + Math.random() * 60 | 0) + ',' + (160 + Math.random() * 60 | 0) + ',' + (175 + Math.random() * 60 | 0) + ',.16)';
    g.fillRect(0, y, 256, 1);
  }
  g.strokeStyle = 'rgba(40,46,58,.9)'; g.lineWidth = 4;
  for (var x = 0; x <= 256; x += 128) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, 256); g.stroke(); }  // 竖向幕墙分割
  for (var y2 = 0; y2 <= 256; y2 += 64) { g.beginPath(); g.moveTo(0, y2); g.lineTo(256, y2); g.stroke(); } // 楼层线
  g.fillStyle = 'rgba(210,220,235,.55)';        // 铆钉
  for (var i = 0; i < 16; i++) for (var j = 0; j < 8; j++) { g.beginPath(); g.arc(10 + i * 16, 22 + j * 32, 1.3, 0, 6.3); g.fill(); }
  var t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding; return t;
}
function makeGlassEmis() {
  var c = document.createElement('canvas'); c.width = c.height = 256; var g = c.getContext('2d');
  g.fillStyle = '#020308'; g.fillRect(0, 0, 256, 256);
  var cols = ['#ffd9a0', '#ffc070', '#bfe0ff', '#8fd0ff', '#ffffff', '#ffe9c0'];
  for (var y = 8; y < 248; y += 30) for (var x = 8; x < 248; x += 22) {   // 稀疏小窗（写实：多数暗、少数亮）
    if (Math.random() < 0.80) continue;
    g.fillStyle = cols[(Math.random() * cols.length) | 0];
    g.globalAlpha = 0.25 + Math.random() * 0.55;
    g.fillRect(x, y, 13, 18); g.globalAlpha = 1;
  }
  var t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding; return t;
}
var TEX_STEEL = makeSteel(), TEX_GLASS = makeGlassEmis();

/* ---------------- ★ 农村营地（西侧 OFF_U 格，与城市连成一片） ---------------- */
(function buildCamp() {
  var campW = OFF_U + 2;                     // 营地宽度（格）
  // 草地地面
  var gg = new THREE.PlaneGeometry(campW * TILE, GH * TILE); gg.rotateX(-Math.PI / 2);
  var gt = (function () { var c = document.createElement('canvas'); c.width = c.height = 256; var g = c.getContext('2d');
    g.fillStyle = '#3f5a34'; g.fillRect(0, 0, 256, 256);
    for (var i = 0; i < 2600; i++) { g.fillStyle = 'rgba(' + (60 + Math.random() * 50 | 0) + ',' + (95 + Math.random() * 60 | 0) + ',' + (48 + Math.random() * 40 | 0) + ',' + (Math.random() * 0.5) + ')'; g.fillRect(Math.random() * 256, Math.random() * 256, 1 + Math.random() * 2, 1 + Math.random() * 3); }
    var t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(campW * TILE / 3, GH * TILE / 3);
    if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding; return t; })();
  var gm = new THREE.Mesh(gg, new THREE.MeshStandardMaterial({ map: gt, roughness: 1, metalness: 0.02 }));
  gm.position.set(campW * TILE / 2, 0.04, GH * TILE / 2); gm.receiveShadow = true;
  injectGI ? null : null; scene.add(gm);
  // 泥土路（营地→城市）
  var rg = new THREE.PlaneGeometry(OFF_U * TILE, 4.2 * TILE); rg.rotateX(-Math.PI / 2);
  var rm = new THREE.Mesh(rg, new THREE.MeshStandardMaterial({ color: 0x6b5a42, roughness: 1 }));
  rm.position.set(OFF_U * TILE * 0.5 + 3, 0.06, GH * TILE * 0.5); scene.add(rm);
  // 树（低多边形，InstancedMesh）
  var trunkG = new THREE.CylinderGeometry(0.16, 0.22, 1.6, 5), leafG = new THREE.ConeGeometry(1.5, 3.4, 7);
  var trunkM = new THREE.MeshStandardMaterial({ color: 0x4a3320, roughness: 1 });
  var leafM = new THREE.MeshStandardMaterial({ color: 0x2f6b2a, roughness: 1 });
  var tr = [], lf = [], d = new THREE.Object3D();
  for (var i = 0; i < 90; i++) {
    var u = 2 + Math.random() * (campW - 4), v = 2 + Math.random() * (GH - 4);
    if (Math.abs(v - GH / 2) < 3) continue;                  // 让开中间的路
    tr.push([u * TILE, v * TILE]); lf.push([u * TILE, v * TILE]);
  }
  var tim = new THREE.InstancedMesh(trunkG, trunkM, tr.length), lim = new THREE.InstancedMesh(leafG, leafM, tr.length);
  for (var j = 0; j < tr.length; j++) {
    d.position.set(tr[j][0], 0.8, tr[j][1]); d.rotation.set(0, Math.random() * 6.28, 0); d.scale.set(1, 1, 1); d.updateMatrix(); tim.setMatrixAt(j, d.matrix);
    d.position.set(tr[j][0], 3.3, tr[j][1]); d.updateMatrix(); lim.setMatrixAt(j, d.matrix);
  }
  tim.castShadow = lim.castShadow = true; scene.add(tim); scene.add(lim);
  // 木屋（方块体块 + 屋顶）
  var wallM = new THREE.MeshStandardMaterial({ color: 0x8a6a48, roughness: 0.9 });
  var roofM = new THREE.MeshStandardMaterial({ color: 0x7d3a2a, roughness: 0.85 });
  var houses = [[7, 10], [14, 38], [4, 30], [17, 16], [10, 44]];
  for (var h = 0; h < houses.length; h++) {
    var hx = houses[h][0] * TILE, hz = houses[h][1] * TILE;
    var b = new THREE.Mesh(new THREE.BoxGeometry(3.4, 2.6, 3.0), wallM); b.position.set(hx, 1.3, hz); b.castShadow = b.receiveShadow = true; scene.add(b);
    var r = new THREE.Mesh(new THREE.ConeGeometry(3.0, 1.8, 4), roofM); r.position.set(hx, 3.5, hz); r.rotation.y = Math.PI / 4; r.castShadow = true; scene.add(r);
    emAdd(hx, hz, 2.4, 0xffc07a, 0.7, 22, true);             // 屋里暖光（进 GI）
  }
  // 营地入口 · 告示牌（指引箭头）
  var sx = (campW - 1) * TILE, sz = GH * TILE * 0.5;
  var post = new THREE.Mesh(new THREE.BoxGeometry(0.22, 2.4, 0.22), new THREE.MeshStandardMaterial({ color: 0x5a4228, roughness: 1 }));
  post.position.set(sx, 1.2, sz); scene.add(post);
  var signCv = document.createElement('canvas'); signCv.width = 256; signCv.height = 128; var sg = signCv.getContext('2d');
  sg.fillStyle = '#c9a266'; sg.fillRect(0, 0, 256, 128); sg.fillStyle = '#3a2a18'; sg.font = 'bold 34px sans-serif'; sg.textAlign = 'center';
  sg.fillText('← 农村营地', 128, 52); sg.fillText('CAMP', 128, 96);
  var st = new THREE.CanvasTexture(signCv); if (THREE.sRGBEncoding) st.encoding = THREE.sRGBEncoding;
  var board = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.3), new THREE.MeshStandardMaterial({ map: st, roughness: 0.8 }));
  board.position.set(sx, 2.6, sz); board.rotation.y = Math.PI; scene.add(board);
  window.__campReady = true;
})();

/* ---------------- 环境反射探针（CubeCamera → 地面/楼体反出霓虹） ---------------- */
var cubeRT = new THREE.WebGLCubeRenderTarget(256, { generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter });
var cubeCam = new THREE.CubeCamera(0.5, 400, cubeRT);

/* ---------------- 地形网格（顶面=地面材质，侧面=钢铁+玻璃楼） ---------------- */
var matTop, matSide, matGlass, topMesh = null, GROUNDMATS = {};
var terrain = (function buildTerrain() {
  var top = { pos: [], uv: [], col: [], idx: [], b: 0 };
  var side = { pos: [], uv: [], col: [], idx: [], b: 0 };
  var glass = { pos: [], uv: [], idx: [], b: 0 };
  function shade(h) { var t = (h - YMIN) / (WALL_H - YMIN); var b = 0.68 + 0.5 * t; return [b * 1.0, b * 1.0, b * 1.0]; }
  function quadTop(x, z, h, col) {
    var y = h, o = top.b;
    top.pos.push(x, y, z, x + TILE, y, z, x + TILE, y, z + TILE, x, y, z + TILE);
    top.uv.push(x / 4.2, z / 4.2, (x + TILE) / 4.2, z / 4.2, (x + TILE) / 4.2, (z + TILE) / 4.2, x / 4.2, (z + TILE) / 4.2);
    for (var i = 0; i < 4; i++) top.col.push(col[0], col[1], col[2]);
    top.idx.push(o, o + 1, o + 2, o, o + 2, o + 3); top.b += 4;
  }
  function quadWall(ax, ay, az, bx, by, bz, cx, cy, cz, dx2, dy2, dz2, ox, oz) {
    var o = side.b, c = shade(Math.max(ay, cy));
    side.pos.push(ax, ay, az, bx, by, bz, cx, cy, cz, dx2, dy2, dz2);
    var w = Math.hypot(bx - ax, bz - az), hh = Math.hypot(dx2 - ax, dy2 - ay, dz2 - az);
    side.uv.push(w / 5, 0, 0, 0, 0, hh / 5, w / 5, hh / 5);
    for (var i = 0; i < 4; i++) side.col.push(c[0] * 0.95, c[1] * 0.97, c[2] * 1.0);
    side.idx.push(o, o + 1, o + 2, o, o + 2, o + 3); side.b += 4;
    // 幕墙玻璃（楼体上部 62% 挂深色玻璃，强反射霓虹）
    if (hh > 1.3) {
      var gy1 = Math.max(ay, by) - 0.10, gy0 = gy1 - 0.62 * hh, g = glass.b;
      glass.pos.push(ax + ox, gy1, az + oz, bx + ox, gy1, bz + oz, cx + ox, gy0, cz + oz, dx2 + ox, gy0, dz2 + oz);
      var gu = w / 3.4, gv = (gy1 - gy0) / 3.4;
      glass.uv.push(gu, 1, 0, 1, 0, 1 - gv, gu, 1 - gv);
      glass.idx.push(g, g + 1, g + 2, g, g + 2, g + 3); glass.b += 4;
    }
  }
  for (var v = 0; v < GH; v++) for (var u = 0; u < GW; u++) {
    var h = H[v * GW + u], x = u * TILE, z = v * TILE, col = shade(h);
    quadTop(x, z, h, col);
    var nR = getH(u + 1, v), nL = getH(u - 1, v), nD = getH(u, v + 1), nU = getH(u, v - 1);
    if (nR < h) quadWall(x + TILE, h, z, x + TILE, h, z + TILE, x + TILE, nR, z + TILE, x + TILE, nR, z, 0.05, 0);
    if (nL < h) quadWall(x, h, z + TILE, x, h, z, x, nL, z, x, nL, z + TILE, -0.05, 0);
    if (nD < h) quadWall(x + TILE, h, z + TILE, x, h, z + TILE, x, nD, z + TILE, x + TILE, nD, z + TILE, 0, 0.05);
    if (nU < h) quadWall(x, h, z, x + TILE, h, z, x + TILE, nU, z, x, nU, z, 0, -0.05);
  }
  function mk(d, mat, idx) {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(d.pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(d.uv, 2));
    if (d.col && d.col.length) g.setAttribute('color', new THREE.Float32BufferAttribute(d.col, 3));
    g.setIndex(d.idx); g.computeVertexNormals();
    var m = new THREE.Mesh(g, mat); scene.add(m); return m;
  }
  matTop = new THREE.MeshStandardMaterial({ map: GROUNDSETS.asphalt.map, normalMap: GROUNDSETS.asphalt.normalMap,
    roughnessMap: GROUNDSETS.asphalt.roughnessMap, vertexColors: true, roughness: 0.72, metalness: 0.18,
    color: new THREE.Color(0xe6ebf5), envMap: cubeRT.texture, envMapIntensity: 0.85 });
  // ★ 真实石材/混凝土墙（写实 PBR：albedo + normal + roughness）
  matSide = new THREE.MeshStandardMaterial({ map: tex('assets/tex/stone.jpg', true), normalMap: tex('assets/tex/stone_n.png'),
    roughnessMap: tex('assets/tex/stone_r.png'), color: 0x8f949c, vertexColors: true,
    roughness: 0.93, metalness: 0.12, envMap: cubeRT.texture, envMapIntensity: 0.7, side: THREE.DoubleSide });
  // ★ 玻璃幕墙（深色高反射 + 稀疏亮窗）
  matGlass = new THREE.MeshStandardMaterial({ color: 0x243d5e, metalness: 1.0, roughness: 0.05,
    envMap: cubeRT.texture, envMapIntensity: 2.6, emissiveMap: TEX_GLASS, emissive: 0xffffff, emissiveIntensity: 1.1,
    transparent: true, opacity: 0.62, side: THREE.DoubleSide, depthWrite: false });
  var mt = mk(top, matTop); mt.receiveShadow = true;
  var ms = mk(side, matSide); ms.castShadow = true; ms.receiveShadow = true;
  if (glass.b) { var mg = mk(glass, matGlass); mg.renderOrder = 1; }
  topMesh = mt; return { top: mt, side: ms };
})();

/* ---------------- 楼顶写实细节：女儿墙 / 通风管 / 空调外机 ---------------- */
(function buildRoofDetail() {
  var dummy = new THREE.Object3D(), parts = [], pipes = [], acs = [];
  for (var v = 2; v < GH - 2; v++) for (var u = 2; u < GW - 2; u++) {
    var h = H[v * GW + u]; if (h < 3.0) continue;
    var ex = getH(u + 1, v) < h - 0.5, ez = getH(u, v + 1) < h - 0.5;
    if (ex && ((u * 3 + v) % 3 === 0)) parts.push([(u + 1) * TILE, h + 0.42, (v + 0.5) * TILE, 0.20, 0.84, TILE]);
    if (ez && ((u + v * 3) % 3 === 0)) parts.push([(u + 0.5) * TILE, h + 0.42, (v + 1) * TILE, TILE, 0.84, 0.20]);
    if (!ex && !ez) {
      var r = (u * 7 + v * 11) % 100;
      if (r < 5) pipes.push([(u + 0.5) * TILE, h, (v + 0.5) * TILE]);
      else if (r < 8) acs.push([(u + 0.5) * TILE, h, (v + 0.5) * TILE, (u * v) % 2]);
    }
  }
  var mConc = new THREE.MeshStandardMaterial({ map: tex('assets/tex/stone.jpg', true), normalMap: tex('assets/tex/stone_n.png'),
    color: 0x8b9098, roughness: 0.95, metalness: 0.10, envMap: cubeRT.texture, envMapIntensity: 0.45 });
  var mMetal = new THREE.MeshStandardMaterial({ color: 0x6d747e, roughness: 0.35, metalness: 0.9, envMap: cubeRT.texture, envMapIntensity: 1.1 });
  var boxG = new THREE.BoxGeometry(1, 1, 1);
  function inst(geo, mat, list, apply) {
    if (!list.length) return;
    var im = new THREE.InstancedMesh(geo, mat, list.length);
    for (var i = 0; i < list.length; i++) { apply(dummy, list[i], i); dummy.updateMatrix(); im.setMatrixAt(i, dummy.matrix); }
    im.castShadow = true; im.receiveShadow = true; scene.add(im);
  }
  inst(boxG, mConc, parts, function (d, p) { d.position.set(p[0], p[1], p[2]); d.scale.set(p[3], p[4], p[5]); d.rotation.set(0, 0, 0); });
  inst(new THREE.CylinderGeometry(0.42, 0.42, 1.3, 12), mMetal, pipes, function (d, p) { d.position.set(p[0], p[1] + 0.65, p[2]); d.scale.set(1, 1, 1); d.rotation.set(0, 0, 0); });
  inst(new THREE.BoxGeometry(1.7, 1.1, 1.1), mMetal, acs, function (d, p) { d.position.set(p[0], p[1] + 0.55, p[2]); d.scale.set(1, 1, 1); d.rotation.set(0, p[3] * Math.PI / 2, 0); });
})();

/* ★ 地面切换（可切换 + 外部保存） */
function setGround(id) {
  var m = GROUNDMATS[id]; if (!m) return false;
  if (topMesh) topMesh.material = m;            // ★ 换材质对象 → THREE 必定重新编译，一定生效
  matTop = m; currentGround = id;
  return true;
}
var currentGround = 'asphalt';

/* ---------------- 楼顶霓虹边缘 + 街灯（保留并强化） ---------------- */
(function buildNeon() {
  var box = new THREE.BoxGeometry(1, 1, 1);
  var cols = [0x39e0ff, 0xff3d8b, 0xffb43d, 0x7cff6a, 0xa855f7, 0x7aa8ff];
  var ci = 0, items = [];
  for (var v = 2; v < GH - 2; v++) for (var u = 2; u < GW - 2; u++) {
    var h = H[v * GW + u];
    if (h < 3.0 || h > 10.5) continue;
    if (!((getH(u + 1, v) < h - 0.1) || (getH(u, v + 1) < h - 0.1) || (getH(u - 1, v) < h - 0.1) || (getH(u, v - 1) < h - 0.1))) continue;
    if (((u * 7 + v * 13) % 3) !== 0) continue;
    var c = cols[(ci++) % cols.length];
    items.push({ x: (u + 0.5) * TILE, y: h + 0.09, z: (v + 0.5) * TILE, c: c });
    emAdd((u + 0.5) * TILE, (v + 0.5) * TILE, h + 0.6, c, 1.35, 30);
  }
  if (items.length) {                                  // ★ InstancedMesh：一次 draw call
    var im = new THREE.InstancedMesh(box, new THREE.MeshBasicMaterial(), items.length);
    var d = new THREE.Object3D(), col = new THREE.Color();
    for (var i = 0; i < items.length; i++) {
      d.position.set(items[i].x, items[i].y, items[i].z); d.scale.set(TILE * 0.96, 0.16, TILE * 0.96);
      d.updateMatrix(); im.setMatrixAt(i, d.matrix); im.setColorAt(i, col.setHex(items[i].c));
    }
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    im.frustumCulled = false; scene.add(im);
  }
  // 路灯：柱+头也用 InstancedMesh
  var lamps = [[16, 9], [35, 20], [9, 30], [40, 30], [26, 44], [44, 8], [6, 16], [30, 49]];
  var poleG = new THREE.CylinderGeometry(0.07, 0.09, 5.2, 6), headG = new THREE.SphereGeometry(0.26, 10, 8);
  var poleM = new THREE.MeshStandardMaterial({ color: 0x2a2e38, roughness: 0.4, metalness: 0.85 });
  var headM = new THREE.MeshBasicMaterial({ color: 0xffd9a0 });
  var poles = new THREE.InstancedMesh(poleG, poleM, lamps.length);
  var heads = new THREE.InstancedMesh(headG, headM, lamps.length);
  var dd = new THREE.Object3D();
  for (var j = 0; j < lamps.length; j++) {
    var u2 = lamps[j][0], v2 = lamps[j][1], hh = getH(u2, v2);
    dd.position.set((u2 + 0.5) * TILE, hh + 2.6, (v2 + 0.5) * TILE); dd.updateMatrix(); poles.setMatrixAt(j, dd.matrix);
    dd.position.set((u2 + 0.5) * TILE, hh + 5.2, (v2 + 0.5) * TILE); dd.updateMatrix(); heads.setMatrixAt(j, dd.matrix);
    emAdd((u2 + 0.5) * TILE, (v2 + 0.5) * TILE, hh + 5.2, 0xffc07a, 1.9, 50, true);
  }
  scene.add(poles); scene.add(heads);
})();

(function buildSkyline() {
  var mat = new THREE.MeshStandardMaterial({ color: 0x232a3e, roughness: 0.45, metalness: 0.85, emissive: 0x0a0e1c });
  var Cx = ATTACH ? 78 : WORLD / 2, Cz = ATTACH ? 78 : WORLD / 2, R = ATTACH ? 215 : 165, N = 40;   // ★ 附加模式围住「营地+城市」
  var im = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), mat, N);
  var d = new THREE.Object3D();
  for (var i = 0; i < N; i++) {
    var a = (i / N) * Math.PI * 2 + Math.random() * 0.09, dist = R + rnd(-20, 50);
    var w = rnd(11, 28), hgt = rnd(30, 100);
    d.position.set(Math.cos(a) * dist + Cx, hgt / 2 - 4, Math.sin(a) * dist + Cz);
    d.rotation.set(0, Math.random() * 1.57, 0); d.scale.set(w, hgt, w); d.updateMatrix(); im.setMatrixAt(i, d.matrix);
  }
  im.frustumCulled = false; scene.add(im);
})();

/* ---------------- 楼顶探照灯（扫射 → 地面色彩溢出 + 体积光锥） ---------------- */
var SEARCH = [];
var SPOT_ON = true;
var DECAL_TEX = (function () {
  var c = document.createElement('canvas'); c.width = c.height = 128; var g = c.getContext('2d');
  var gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,.95)'); gr.addColorStop(0.35, 'rgba(255,255,255,.5)'); gr.addColorStop(0.75, 'rgba(255,255,255,.16)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
})();
(function buildSearchlights() {
  var spots = [
    { x: 26, z: 10, c: 0x39e0ff }, { x: 12, z: 31, c: 0xff3d8b },
    { x: 40, z: 34, c: 0xffb43d }, { x: 34, z: 9, c: 0x8affc0 },
  ];
  for (var i = 0; i < spots.length; i++) {
    var s = spots[i], bx = (s.x + 0.5) * TILE, bz = (s.z + 0.5) * TILE, by = getH(s.x, s.z) + 4.2;
    var sp = new THREE.SpotLight(s.c, 0, 100, 0.30, 0.55, 1.5);
    sp.position.set(bx, by, bz); sp.castShadow = false;
    var tg = new THREE.Object3D(); tg.position.set(bx, 0, bz + 12);
    if (LEAN.spotLights) { tg.position.set(bx, 0, bz + 12); scene.add(tg); sp.target = tg; scene.add(sp); }
    emAdd(bx, bz, by, s.c, 3.2, 80, true);
    var hgt = by, cone = new THREE.Mesh(new THREE.ConeGeometry(Math.tan(0.30) * hgt * 1.25, hgt, 22, 1, true),
      new THREE.MeshBasicMaterial({ color: s.c, transparent: true, opacity: 0.026, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
    cone.rotation.x = Math.PI; scene.add(cone);
    var bulb = new THREE.Mesh(new THREE.SphereGeometry(0.4, 10, 8), new THREE.MeshBasicMaterial({ color: s.c }));
    bulb.position.set(bx, by, bz); scene.add(bulb);
    var decal = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: DECAL_TEX, color: s.c, transparent: true, opacity: 0.15, blending: THREE.AdditiveBlending, depthWrite: false }));
    decal.rotation.x = -Math.PI / 2; decal.scale.set(11, 11, 1); scene.add(decal);
    SEARCH.push({ sp: sp, tg: tg, cone: cone, decal: decal, bx: bx, by: by, bz: bz, phase: Math.random() * 6.28, spd: rnd(0.25, 0.5) });
  }
})();

/* ---------------- 下雨（雨丝） ---------------- */
var RAIN = { on: true };
var RAIN_N = 450, rainMesh = null, rainPos = null, rainSpd = null;
(function buildRain() {
  rainPos = new Float32Array(RAIN_N * 6); rainSpd = new Float32Array(RAIN_N);
  for (var i = 0; i < RAIN_N; i++) {
    var x = rnd(-60, 60), y = rnd(0, 45), z = rnd(-60, 60), sp = rnd(26, 40);
    rainPos[i * 6] = x; rainPos[i * 6 + 1] = y; rainPos[i * 6 + 2] = z;
    rainPos[i * 6 + 3] = x + 0.06; rainPos[i * 6 + 4] = y - 0.75; rainPos[i * 6 + 5] = z;
    rainSpd[i] = sp;
  }
  var g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(rainPos, 3));
  var m = new THREE.LineBasicMaterial({ color: 0xbcd6ff, transparent: true, opacity: 0.45, blending: THREE.AdditiveBlending, depthWrite: false });
  rainMesh = new THREE.LineSegments(g, m); rainMesh.frustumCulled = false; scene.add(rainMesh);
})();

/* ---------------- ★ 离线烘焙 GI（全局光照贴图） ---------------- */
function bakeGI() {
  var R = 256, data = new Uint8Array(R * R * 4);
  for (var gy = 0; gy < R; gy++) for (var gx = 0; gx < R; gx++) {
    var wx = (gx + 0.5) / R * WORLD, wz = (gy + 0.5) / R * WORLD;
    var r = 0, g = 0, b = 0;
    for (var i = 0; i < GI_EM.length; i++) {
      var e = GI_EM[i], d = Math.hypot(e.x - wx, e.z - wz);
      if (d > e.rad) continue;
      var vis = 1, K = 9;
      for (var k = 1; k <= K; k++) {
        var f = k / (K + 1), sx = wx + (e.x - wx) * f, sz = wz + (e.z - wz) * f;
        var hh = getH(Math.floor(sx / TILE), Math.floor(sz / TILE));
        if (hh > Math.max(0.6, e.y * 0.55)) { vis = 0.12; break; }
      }
      var att = vis * e.p / (1 + d * d * 0.032);
      r += e.r * att; g += e.g * att; b += e.b * att;
    }
    var o = (gy * R + gx) * 4;
    data[o] = Math.min(255, r * 200); data[o + 1] = Math.min(255, g * 200); data[o + 2] = Math.min(255, b * 200); data[o + 3] = 255;
  }
  var t = new THREE.DataTexture(data, R, R, THREE.RGBAFormat);
  t.needsUpdate = true; t.minFilter = THREE.LinearFilter; t.magFilter = THREE.LinearFilter;
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  return t;
}
/* 把 GI 注入任意标准材质：按世界坐标采样 → 表面被霓虹/探照灯染色（色彩溢出） */
function injectGI(mat, amt) {
  if (!mat) return mat;
  mat.onBeforeCompile = function (sh) {
    sh.uniforms.uGI = { value: GI_TEX };
    sh.uniforms.uGIA = { value: amt === undefined ? 1.2 : amt };
    sh.uniforms.uWld = { value: WORLD };
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec2 vWPx;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWPx=(modelMatrix*vec4(transformed,1.0)).xz;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nuniform sampler2D uGI;uniform float uGIA,uWld;varying vec2 vWPx;')
      .replace('#include <dithering_fragment>', '#include <dithering_fragment>\n  vec3 _gi=texture2D(uGI, vWPx/uWld).rgb;\n  gl_FragColor.rgb *= (1.0 + _gi*uGIA);');
  };
  mat.needsUpdate = true;
  return mat;
}

/* ---------------- 光照 ---------------- */
var hemi = new THREE.HemisphereLight(0x33436a, 0x0c0c14, 0.40); scene.add(hemi);
var moon = new THREE.DirectionalLight(0x9fb4e8, 0.58);
moon.position.set(70, 96, 34); moon.castShadow = true;
moon.shadow.mapSize.set(512, 512);
var SC = 118;
moon.shadow.camera.left = -SC; moon.shadow.camera.right = SC; moon.shadow.camera.top = SC; moon.shadow.camera.bottom = -SC;
moon.shadow.camera.near = 1; moon.shadow.camera.far = 340; moon.shadow.bias = -0.0014;
scene.add(moon); scene.add(moon.target);
var warm = new THREE.DirectionalLight(0xff9a5a, 0.16); warm.position.set(-60, 40, -50); scene.add(warm);

/* ---------------- 每帧更新（探照灯 / 雨 / 反射探针） ---------------- */
/* ★ 烘焙一次并注入：地面/墙/玻璃 都会被霓虹与探照灯"染色"（离线 GI） */
GI_TEX = bakeGI();
(function buildGroundMats() {
  for (var i = 0; i < GROUNDS.length; i++) {
    var g = GROUNDS[i], s2 = GROUNDSETS[g.id];
    var mm = new THREE.MeshStandardMaterial({
      map: s2.map, normalMap: s2.normalMap || null, roughnessMap: s2.roughnessMap || null,
      vertexColors: true, color: new THREE.Color(g.tint),
      roughness: g.rough, metalness: g.metal, envMap: cubeRT.texture, envMapIntensity: g.refl,
    });
    injectGI(mm, g.id === 'asphalt' ? 1.15 : 0.95);
    GROUNDMATS[g.id] = mm;
  }
})();
if (topMesh && GROUNDMATS.asphalt) { matTop = GROUNDMATS.asphalt; topMesh.material = matTop; }
injectGI(matSide, 0.75);
injectGI(matGlass, 1.0);

var T = 0, envAcc = 0, lastEnvX = 0, lastEnvZ = 0;
function update(dt, camPos) {
  T += dt;
  // 探照灯扫射
  for (var i = 0; i < SEARCH.length; i++) {
    var s = SEARCH[i], a = Math.sin(T * s.spd + s.phase) * 0.85, pw = Math.cos(T * s.spd * 0.7 + s.phase) * 0.25;
    var len = s.by;
    var tx = s.bx + Math.sin(a) * len * 1.15, tz = s.bz + Math.cos(a) * len * 0.7;
    s.tg.position.set(tx, Math.max(0, s.by - len - pw * 12), tz);
    s.cone.position.set(s.bx, s.by / 2, s.bz);
    s.cone.rotation.set(Math.PI, 0, 0);
    s.cone.lookAt(tx, 0, tz); s.cone.rotateX(Math.PI / 2);
    s.cone.position.set((s.bx + tx) / 2, s.by / 2, (s.bz + tz) / 2);
    if (s.decal) { s.decal.position.set(tx, getH(Math.floor(tx / TILE), Math.floor(tz / TILE)) + 0.04, tz); }
  }
  // 雨
  if (RAIN.on && rainMesh && camPos) {
    var arr = rainPos, N = Math.min(RAIN_N, LEAN.rain || RAIN_N);
    if (rainMesh.geometry.setDrawRange) rainMesh.geometry.setDrawRange(0, N * 2);
    for (var k = 0; k < N; k++) {
      var o = k * 6, dy = rainSpd[k] * dt;
      arr[o + 1] -= dy; arr[o + 4] -= dy;
      if (arr[o + 1] < camPos.y - 16) {
        var nx = camPos.x + rnd(-40, 40), nz = camPos.z + rnd(-40, 40), ny = camPos.y + rnd(14, 34);
        arr[o] = nx; arr[o + 1] = ny; arr[o + 2] = nz;
        arr[o + 3] = nx + 0.06; arr[o + 4] = ny - 0.75; arr[o + 5] = nz;
      }
    }
    rainMesh.geometry.attributes.position.needsUpdate = true;
    rainMesh.visible = true;
  } else if (rainMesh) rainMesh.visible = false;
  // 环境反射探针（低频重建 → 地面反出霓虹/探照灯）
  envAcc += dt;
  var _moved = camPos ? Math.hypot(camPos.x - (lastEnvX || 1e9), camPos.z - (lastEnvZ || 1e9)) : 0;
  if (LEAN.reflect && envAcc > 4.0 && camPos && _moved > 6.0) {      // ★ 降频 1.6s 且相机移动>2 才重建（原本 0.35s → 周期性爆帧）
    envAcc = 0; lastEnvX = camPos.x; lastEnvZ = camPos.z;
    cubeCam.position.set(camPos.x, camPos.y + 1.5, camPos.z);
    if (rainMesh) rainMesh.visible = false;
    cubeCam.update(renderer, scene);
    if (rainMesh && RAIN.on) rainMesh.visible = true;
  }
}

function setSpot(on) {
  SPOT_ON = !!on;
  for (var i = 0; i < SEARCH.length; i++) { SEARCH[i].sp.visible = SPOT_ON && LEAN.spotLights; SEARCH[i].sp.intensity = (SPOT_ON && LEAN.spotLights) ? 0.62 : 0; SEARCH[i].cone.visible = SPOT_ON; }
}
function getSpot() { return SPOT_ON; }
// ★ 标记「自制都市内容」→ 外部（tileworld3d）可整体隐藏，只留环境（天/雨/雾/光/GI）
scene.traverse(function (o) { if ((o.isMesh || o.isSprite || o.isInstancedMesh) && o !== rainMesh && !o.userData.keep) o.userData.city = true; });

resize();
var _API = {
  TILE: TILE, GW: GW, GH: GH, H: H, Ground: Ground, scene: scene, renderer: renderer, camera: camera,
  moon: moon, resize: resize, update: update, grounds: GROUNDS, CAM_DIR: CAM_DIR, getCam: getCam, setCamMode: setCamMode, getCamMode: getCamMode, orthoCam: orthoCam, setOrthoVH: setOrthoVH, getOrthoVH: function () { return orthoVH; }, setOrthoHW: setOrthoHW, getOrthoHW: getOrthoHW, setOrthoHW2: setOrthoHW,
  cubeRT: cubeRT, setSpot: setSpot, getSpot: getSpot, LEAN: LEAN, setLean: function (o) { for (var k in o) LEAN[k] = o[k]; }, matSide: matSide, matGlass: matGlass, topMesh: function () { return topMesh; }, GI: function () { return GI_TEX; }, world: WORLD, injectGI: injectGI, setGround: setGround, getGround: function () { return currentGround; }, setRain: function (on) { RAIN.on = !!on; }, getRain: function () { return RAIN.on; },
};
if (ATTACH) window.__CITY3D = _API; else window.__CITY3D = _API;
window.ARENA_UNUSED = {
  TILE: TILE, GW: GW, GH: GH, H: H, Ground: Ground, scene: scene, renderer: renderer, camera: camera,
  moon: moon, resize: resize, update: update, grounds: GROUNDS, CAM_DIR: CAM_DIR, getCam: getCam, setCamMode: setCamMode, getCamMode: getCamMode, orthoCam: orthoCam, setOrthoVH: setOrthoVH, getOrthoVH: function () { return orthoVH; }, setOrthoHW: setOrthoHW, getOrthoHW: getOrthoHW,
  setGround: setGround, getGround: function () { return currentGround; },
  setRain: function (on) { RAIN.on = !!on; }, getRain: function () { return RAIN.on; },
  cubeRT: cubeRT, setSpot: setSpot, getSpot: getSpot, LEAN: LEAN, setLean: function (o) { for (var k in o) LEAN[k] = o[k]; }, matSide: matSide, matGlass: matGlass, topMesh: function () { return topMesh; }, GI: function () { return GI_TEX; }, world: WORLD, injectGI: injectGI,
};
} catch (e) { window.__aerr = (e.stack || e.message); }
})();
