/* ==========================================================================
   tileworld3d.js —— 把原版 HD-2D 地图（js/tiles.js）1:1 变成 3D 世界
   --------------------------------------------------------------------------
   同一张地图：
     · HD-2D 视角（正交45°）→ 就是原来的八方旅人味道
     · 透视视角（自由旋转）  → 就是 3D 场景
   地形 = tiles.js 的 72×72 瓦片（地面网格 + 高度场）
   树   = assets3d 真 3D 模型（InstancedMesh）
   建筑 = 3D 体块（Box + 屋顶）
   道具 = 立绘公告板（保留 HD-2D 招牌）
   ========================================================================== */
(function () {
'use strict';
if (!window.TileWorld || !window.ARENA) { window.__t3dErr = '缺 TileWorld/ARENA'; return; }
try {
var A = window.ARENA, TW = window.TileWorld, S = A.scene, TILE = A.TILE;
var MW = TW.MW, MH = TW.MH, T = TW.T, HEIGHT = TW.HEIGHT;
var V3 = function (x, y, z) { return new THREE.Vector3(x, y, z); };
var clamp = function (v, a, b) { return v < a ? a : (v > b ? b : v); };
var W_CITY = 76 * TILE, H_CITY = 52 * TILE;
var CAMP_X0 = -MW * TILE, CAMP_GI = null;                       // 营地整体放在 都市西侧（接壤于 x=0）
var GRP = new THREE.Group(); GRP.position.x = CAMP_X0; S.add(GRP);

/* ---------------- 高度场（地表 0 / 墙·建筑 3.2） ---------------- */
var WALLH = 3.2, H = new Float32Array(MW * MH);
for (var v = 0; v < MH; v++) for (var u = 0; u < MW; u++) {
  var t = TW.at(u, v), h = 0;
  if (t === T.WALL_S || t === T.WALL_W || t === T.ARCH || t === T.WALL_TOP || t === T.BOOK || t === T.ROOF_R || t === T.ROOF_B || t === T.ROOF_P) h = WALLH;
  H[v * MW + u] = h;
}
// 建筑占位（TW.buildings = {x,y,w,h} 格）
var BLD = TW.buildings || [];
for (var bi = 0; bi < BLD.length; bi++) {
  var b = BLD[bi];
  for (var bv = b.y; bv < b.y + b.h; bv++) for (var bu = b.x; bu < b.x + b.w; bu++) {
    if (bu >= 0 && bv >= 0 && bu < MW && bv < MH) H[bv * MW + bu] = WALLH;
  }
}

/* ---------------- Ground：都市 + 营地 双区域 ---------------- */
var cityH = A.Ground.h.bind(A.Ground);                 // 原始（都市）查询
var campH = function (cx, cz) {                          // 营地查询（本地坐标 → 瓦片）
  var u = Math.floor(cx / TILE), vv = Math.floor(cz / TILE);
  if (u < 0 || vv < 0 || u >= MW || vv >= MH) return 99;
  return H[vv * MW + u];
};
var G = A.Ground;
G.WALL_H = WALLH; G.TILE = TILE;
G.h = function (x, z) {
  if (x < 0) return campH(x - CAMP_X0, z);              // 营地（x<0）
  return cityH(x, z);                                    // 都市（x>=0）
};
G.canStand = function (nx, nz, y, step) {
  step = step === undefined ? 0.62 : step;
  return (G.h(nx, nz) - y) <= step;
};
G.ray = function (ox, oy, oz, dx, dy, dz, maxD) {
  // ★ 网格步进（DDA）：沿射线跨格跳，格数上限 220 → 绝不会每帧上万次
  maxD = Math.min(maxD, 260);
  var step = Math.max(0.4, TILE * 0.34), n = Math.ceil(maxD / step);
  for (var i = 1; i <= n; i++) {
    var d = i * step;
    var x = ox + dx * d, y = oy + dy * d, z = oz + dz * d;
    if (y < -2) return { dist: d, x: x, y: -2, z: z };
    if (y <= G.h(x, z)) {
      // 细化（在上一段内二分找真实交点，保证精度）
      var lo = (i - 1) * step, hi = d;
      for (var k = 0; k < 5; k++) { var m = (lo + hi) / 2; if ((oy + dy * m) <= G.h(ox + dx * m, oz + dz * m)) hi = m; else lo = m; }
      var hx = ox + dx * hi, hy = oy + dy * hi, hz = oz + dz * hi;
      return { dist: hi, x: hx, y: hy, z: hz };
    }
  }
  return { dist: maxD, x: ox + dx * maxD, y: oy + dy * maxD, z: oz + dz * maxD };
};
G.pick = function (fx, fz, minDist) {
  var best = null, bd = -1;
  for (var k = 0; k < 80; k++) {
    var camp = Math.random() < 0.6;                      // 六成刷在营地，四成在都市
    var x, z, y;
    if (camp) { var u = 2 + Math.floor(Math.random() * (MW - 4)), vv = 2 + Math.floor(Math.random() * (MH - 4)); if (campH(u * TILE + 1, vv * TILE + 1) > 1) continue; x = CAMP_X0 + (u + 0.5) * TILE; z = (vv + 0.5) * TILE; }
    else { x = Math.random() * W_CITY; z = Math.random() * H_CITY; if (cityH(x, z) > 1) continue; }
    var dd = Math.hypot(x - fx, z - fz);
    if (dd >= minDist) return { x: x, z: z, y: 0 };
    if (dd > bd) { bd = dd; best = { x: x, z: z, y: 0 }; }
  }
  return best || { x: CAMP_X0 + (MW / 2) * TILE, z: (MH / 2) * TILE, y: 0 };
};

/* ---------------- 隐藏自制地形网格（保留霓虹/天际线做远景） ---------------- */
/* ★ 都市（楼/霓虹）保留：营地接在它西侧，两种视角都能看到 */

/* ---------------- 地面网格（按 tile 分组贴图） ---------------- */
function texOf(t) {
  // ★ 同 octo：地面统一铺「雨夜沥青 city」（唯美湿地反光），只保留水面例外
  if (t === T.WATER) return 'water';
  return 'city';
}
var TL = new THREE.TextureLoader(), TEXC = {};
function ntex(name) {
  if (NORMALC[name]) return NORMALC[name];
  var t = TL.load('assets/tex/' + name + '_n.jpg'); t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(1, 1); t.anisotropy = 16; NORMALC[name] = t; return t;
}
function rtex(name) {
  if (RC[name]) return RC[name];
  var t = TL.load('assets/tex/' + name + '_r.jpg'); t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(1, 1); t.anisotropy = 16; RC[name] = t; return t;
}
var NORMALC = {}, RC = {};
function tex(name) {
  if (TEXC[name]) return TEXC[name];
  var t = TL.load('assets/tex/' + name + '.jpg'); t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(1, 1); t.anisotropy = 16; if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
  TEXC[name] = t; return t;
}
(function buildGround() {
  var groups = {};
  for (var vv = 0; vv < MH; vv++) for (var u = 0; u < MW; u++) {
    var t = TW.at(u, vv), hh = H[vv * MW + u];
    if (hh > 1) continue;                                   // 墙/建筑格不铺地面
    var nm = texOf(t);
    var g = groups[nm] || (groups[nm] = { pos: [], uv: [], idx: [], b: 0 });
    var x = u * TILE, z = vv * TILE, y = 0, o = g.b;
    g.pos.push(x, y, z, x + TILE, y, z, x + TILE, y, z + TILE, x, y, z + TILE);
    var _r = 6;                                    // ★ 与 octo 一致：6 世界单位/贴图（细腻不糊）
    g.uv.push(x / _r, z / _r, (x + TILE) / _r, z / _r, (x + TILE) / _r, (z + TILE) / _r, x / _r, (z + TILE) / _r);
    g.idx.push(o, o + 1, o + 2, o, o + 2, o + 3); g.b += 4;
  }
  for (var nm2 in groups) {
    var g2 = groups[nm2], geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(g2.pos, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(g2.uv, 2));
    geo.setIndex(g2.idx); geo.computeVertexNormals();
    var isWater = (nm2 === 'water');
    var rmap = null;
    try { rmap = new THREE.TextureLoader().load('assets/tex/city_r.jpg'); rmap.wrapS = rmap.wrapT = THREE.RepeatWrapping; } catch (e) {}
    var mat = new THREE.MeshStandardMaterial({ map: tex(nm2), normalMap: ntex(nm2), normalScale: new THREE.Vector2(1.3, 1.3), roughnessMap: (nm2 === 'city' ? rmap : null),
      roughness: isWater ? 0.08 : 0.95, metalness: isWater ? 0.5 : 0.0,
      transparent: isWater, opacity: isWater ? 0.82 : 1 });
    if (A.injectGI) A.injectGI(mat, 0.9);
    var m = new THREE.Mesh(geo, mat); m.receiveShadow = true; m.userData.keep = true; m.position.y = isWater ? 0.02 : 0; GRP.add(m);   // ★ 必须挂营地组（随营地平移到西侧）
  }
})();

/* ---------------- 墙体 / 建筑（3D 体块） ---------------- */
(function buildWalls() {
  var wallMat = new THREE.MeshStandardMaterial({ map: tex('concrete'), normalMap: ntex('concrete'), roughnessMap: rtex('concrete'), normalScale: new THREE.Vector2(1.1, 1.1), roughness: 0.9, metalness: 0.08, color: 0x9aa0a8 });
  if (A.injectGI) A.injectGI(wallMat, 0.8);
  var roofMat = new THREE.MeshStandardMaterial({ map: tex('roof'), normalMap: ntex('roof'), roughnessMap: rtex('roof'), normalScale: new THREE.Vector2(1.0, 1.0), roughness: 0.85, color: 0xb0785a });
  var box = new THREE.BoxGeometry(1, 1, 1), d = new THREE.Object3D(), list = [];
  for (var vv = 0; vv < MH; vv++) for (var u = 0; u < MW; u++) {
    if (H[vv * MW + u] < 1) continue;
    list.push([(u + 0.5) * TILE, (vv + 0.5) * TILE]);
  }
  if (!list.length) return;
  var im = new THREE.InstancedMesh(box, wallMat, list.length);
  for (var i = 0; i < list.length; i++) { d.position.set(list[i][0], WALLH / 2, list[i][1]); d.scale.set(TILE, WALLH, TILE); d.rotation.set(0, 0, 0); d.updateMatrix(); im.setMatrixAt(i, d.matrix); }
  im.castShadow = im.receiveShadow = true; GRP.add(im);
  // 建筑屋顶
  for (var bi = 0; bi < BLD.length; bi++) {
    var b = BLD[bi], cx = (b.x + b.w / 2) * TILE, cz = (b.y + b.h / 2) * TILE;
    var r = new THREE.Mesh(box, roofMat);
    r.position.set(cx, WALLH + 0.35, cz); r.scale.set(b.w * TILE + 0.8, 0.7, b.h * TILE + 0.8);
    r.castShadow = true; GRP.add(r);
  }
})();

/* ---------------- ★ 霓虹边缘（octo 招牌：楼/墙顶发光条）+ 专属烘焙 GI ---------------- */
var CAMP_EM = [];
(function buildCampNeon() {
  var box = new THREE.BoxGeometry(1, 1, 1);
  var cols = [0x39e0ff, 0xff3d8b, 0xffb43d, 0x7cff6a, 0xa855f7, 0x7aa8ff];
  var items = [], ci = 0;
  for (var v = 1; v < MH - 1; v++) for (var u = 1; u < MW - 1; u++) {
    if (H[v * MW + u] < 1) continue;
    var edge = (H[v * MW + u + 1] < 1) || (H[(v + 1) * MW + u] < 1) || (H[v * MW + u - 1] < 1) || (H[(v - 1) * MW + u] < 1);
    if (!edge || ((u * 7 + v * 13) % 3) !== 0) continue;
    var c = cols[(ci++) % cols.length];
    var WX = CAMP_X0 + (u + 0.5) * TILE, WZ = (v + 0.5) * TILE;      // ★ 世界坐标
    items.push({ x: WX - CAMP_X0, z: WZ, c: c });
    CAMP_EM.push({ x: WX, z: WZ, y: WALLH + 1, r: 0.9, g: 0.5, b: 1.0, p: 2.0, rad: 26 });
  }
  if (items.length) {
    var im = new THREE.InstancedMesh(box, new THREE.MeshBasicMaterial(), items.length);
    var d = new THREE.Object3D(), col = new THREE.Color();
    for (var i = 0; i < items.length; i++) { d.position.set(items[i].x, WALLH + 0.12, items[i].z); d.scale.set(TILE * 0.95, 0.16, TILE * 0.95); d.updateMatrix(); im.setMatrixAt(i, d.matrix); im.setColorAt(i, col.setHex(items[i].c)); }
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    im.frustumCulled = false; GRP.add(im);
  }
  // 暖光（屋/灯）也进 GI
  for (var j = 0; j < CAMP_EM.length; j += 5) CAMP_EM.push({ x: CAMP_EM[j].x + 7, z: CAMP_EM[j].z + 7, y: 2.4, r: 1.0, g: 0.78, b: 0.35, p: 1.6, rad: 22 });
})();

/* 营地专属 GI（按营地小区烘 → 霓虹真正给地面/墙染色） */
function bakeCampGI() {
  var G0 = 12, R = G0 * 9;                      // 12 个小区 × 9px
  var data = new Uint8Array(R * R * 4), cell = (MW * TILE) / G0;
  for (var gy = 0; gy < R; gy++) for (var gx = 0; gx < R; gx++) {
    var wx = CAMP_X0 + (gx + 0.5) / R * MW * TILE, wz = (gy + 0.5) / R * MH * TILE, r = 0, g = 0, b = 0;
    for (var i = 0; i < CAMP_EM.length; i++) {
      var e = CAMP_EM[i], d = Math.hypot(e.x - wx, e.z - wz);
      if (d > e.rad) continue;
      var at = e.p / (1 + d * d * 0.055);
      r += e.r * at; g += e.g * at; b += e.b * at;
    }
    var o = (gy * R + gx) * 4;
    data[o] = Math.min(255, r * 150); data[o + 1] = Math.min(255, g * 150); data[o + 2] = Math.min(255, b * 150); data[o + 3] = 255;
  }
  var t = new THREE.DataTexture(data, R, R, THREE.RGBAFormat);
  t.needsUpdate = true; t.minFilter = THREE.LinearFilter; t.magFilter = THREE.LinearFilter;
  t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
  return t;
}
CAMP_GI = bakeCampGI();
(function injectCampGI() {
  var mat = new THREE.ShaderMaterial;
  GRP.traverse(function (o) {
    if (!o.isMesh || !o.material || o.isInstancedMesh) return;
    var m = o.material;
    m.onBeforeCompile = function (sh) {
      sh.uniforms.uGI = { value: CAMP_GI };
      sh.uniforms.uW0 = { value: new THREE.Vector2(typeof CAMP_X0 !== 'undefined' ? CAMP_X0 : -MW * TILE, 0) };
      sh.uniforms.uWSz = { value: new THREE.Vector2(76 * TILE, 52 * TILE) };
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec2 vWy;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWy=(modelMatrix*vec4(position,1.0)).xz;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform sampler2D uGI;varying vec2 vWy;uniform vec2 uW0;uniform vec2 uWSz;')
        .replace('#include <dithering_fragment>', '#include <dithering_fragment>\n  vec3 _g=texture2D(uGI, (vWy-uW0)/uWSz).rgb;\n  gl_FragColor.rgb *= (1.0 + _g*2.2);');
    };
    m.needsUpdate = true;
  });
})();

/* ---------------- 真 3D 树（InstancedMesh） ---------------- */
function decodeMesh(name) {
  var b64 = (window.MESHES || {})[name]; if (!b64) return null;
  var bin = atob(b64), n = bin.length, buf = new Uint8Array(n);
  for (var i = 0; i < n; i++) buf[i] = bin.charCodeAt(i);
  var dv = new DataView(buf.buffer);
  if (dv.getUint32(0, false) !== 0x54334431) return null;
  var nv = dv.getUint32(4, true), nf = dv.getUint32(8, true), o = 12;
  var pos = new Float32Array(buf.buffer, o, nv * 3); o += nv * 12;
  var nrm = new Float32Array(buf.buffer, o, nv * 3); o += nv * 12;
  var uv = new Float32Array(buf.buffer, o, nv * 2); o += nv * 8;
  var idx = new Uint32Array(buf.buffer, o, nf * 3);
  var g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setIndex(new THREE.BufferAttribute(idx, 1)); g.computeBoundingSphere();
  return g;
}
(function buildTrees() {
  var layers = [{ t: T.TREE, name: 'tree_green', h: 5.2 }, { t: T.SAKURA, name: 'tree_sakura', h: 5.4 }];
  for (var li = 0; li < layers.length; li++) {
    var ly = layers[li], geo = decodeMesh(ly.name); if (!geo) continue;
    var cells = [];
    for (var vv = 0; vv < MH; vv++) for (var u = 0; u < MW; u++) if (TW.at(u, vv) === ly.t) cells.push([(u + 0.5) * TILE, (vv + 0.5) * TILE]);
    if (!cells.length) continue;
    var t2 = TL.load('assets3d/' + ly.name + '_tex.jpg'); if (THREE.sRGBEncoding) t2.encoding = THREE.sRGBEncoding;
    var mat = new THREE.MeshStandardMaterial({ map: t2, roughness: 0.88, metalness: 0 });
    var im = new THREE.InstancedMesh(geo, mat, cells.length);
    var d = new THREE.Object3D();
    for (var i = 0; i < cells.length; i++) { d.position.set(cells[i][0], 0, cells[i][1]); d.rotation.set(0, Math.random() * 6.28, 0); d.scale.set(ly.h, ly.h, ly.h); d.updateMatrix(); im.setMatrixAt(i, d.matrix); }
    im.castShadow = true; GRP.add(im);
  }
})();

/* ---------------- 道具（立绘公告板，保留 HD-2D 招牌） ---------------- */
var SPRT = { 39: 'barrel', 44: 'bush', 45: 'fence', 42: 'crate', 31: 'table', 32: 'desk', 38: 'lamp2', 43: 'altar', 41: 'cauldron', 40: 'bed', 46: 'crop', 35: 'fountain', 30: 'shelf' };
(function buildProps() {
  var n = 0;
  for (var vv = 0; vv < MH; vv++) for (var u = 0; u < MW; u++) {
    var t = TW.at(u, vv), nm = SPRT[t]; if (!nm) continue;
    var tx = TL.load('assets/tiles/' + nm + '.png'); if (THREE.sRGBEncoding) tx.encoding = THREE.sRGBEncoding;
    var mat = new THREE.SpriteMaterial({ map: tx, transparent: true, alphaTest: 0.3 });
    var sp = new THREE.Sprite(mat); sp.center.set(0.5, 0);
    sp.position.set((u + 0.5) * TILE, 0, (vv + 0.5) * TILE);
    var hgt = 2.0; sp.scale.set(hgt, hgt, 1); GRP.add(sp); n++;
  }
  window.__props3d = n;
})();

window.__tileworld3d = { MW: MW, MH: MH, WALLH: WALLH, CAMP_X0: CAMP_X0, spawn: function () { return { x: CAMP_X0 + MW * TILE * 0.5, z: MH * TILE * 0.5, y: 0 }; } };
} catch (e) { window.__t3dErr = (e && (e.stack || e.message)) || String(e); }
})();
