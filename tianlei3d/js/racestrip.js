/* ==========================================================================
   racestrip.js —— ★把《极限刹车》的「公路 + 车 + 路灯 + 护栏」放进天泪场景
   --------------------------------------------------------------------------
   复用刹车那套「城市材质体系」：湿沥青路面(车道线) + 金属车漆 + 暖色路灯，
   和天泪的沥青/木屋顶/大理石在同一套 PBR 光照下 → 天然同源。
   位置：营地北侧一块"跑道区"（x 10..70 / z -30..-14），并把它设为可走。
   ========================================================================== */
(function () {
'use strict';
if (window.__RACE_STRIP) return;
if (!window.ARENA || !window.THREE) { setTimeout(arguments.callee, 400); return; }
var A = window.ARENA, T = window.THREE;
try {
  var scene = A.scene;
  var X0 = 10, X1 = 70, Z0 = -30, Z1 = -14;             // 跑道区
  var CX = (X0 + X1) / 2, CZ = (Z0 + Z1) / 2, LEN = X1 - X0, WID = Z1 - Z0;

  /* ① 把跑道区设为"可走平地"（否则在地图外会被当墙） */
  var oldH = A.Ground.h, oldStand = A.Ground.canStand;
  function inStrip(x, z) { return x >= X0 - 3 && x <= X1 + 3 && z >= Z0 - 3 && z <= Z1 + 3; }
  A.Ground.h = function (x, z) { return inStrip(x, z) ? 0 : oldH(x, z); };
  A.Ground.canStand = function (x, z, y, step) { return inStrip(x, z) ? true : oldStand(x, z, y, step); };

  var G = new T.Group(); scene.add(G);

  /* ② 底地 */
  var base = new T.Mesh(new T.PlaneGeometry(LEN + 46, WID + 30),
    new T.MeshStandardMaterial({ color: 0x0c0d10, roughness: 0.96, metalness: 0.02 }));
  base.rotation.x = -Math.PI / 2; base.position.set(CX, -0.02, CZ); base.receiveShadow = true; G.add(base);

  /* ③ 路面（湿沥青，带金属感 → 和"刹车"一样会反光） */
  var roadM = new T.MeshStandardMaterial({ color: 0x24242a, roughness: 0.40, metalness: 0.18 });
  var road = new T.Mesh(new T.PlaneGeometry(LEN, WID), roadM);
  road.rotation.x = -Math.PI / 2; road.position.set(CX, 0.02, CZ); road.receiveShadow = true; G.add(road);

  /* 车道线：白边 + 黄边 + 中间白虚线（细长条，方向不会错） */
  function line(w, l, x, z, col, emis) {
    var m = new T.Mesh(new T.PlaneGeometry(w, l),
      new T.MeshStandardMaterial({ color: col, emissive: emis || 0x000000, emissiveIntensity: emis ? 1.2 : 0, roughness: 0.6 }));
    m.rotation.x = -Math.PI / 2; m.position.set(x, 0.035, z); G.add(m);
  }
  line(LEN, 0.16, CX, CZ - WID / 2 + 1.0, 0xe9e6dc);
  line(LEN, 0.16, CX, CZ + WID / 2 - 1.0, 0xe9e6dc);
  line(LEN, 0.16, CX, CZ - WID / 2 + 2.2, 0xf2c94c);
  line(LEN, 0.16, CX, CZ + WID / 2 - 2.2, 0xf2c94c);
  for (var dx = 0; dx < LEN - 3; dx += 6) line(3.0, 0.16, X0 + 1.5 + dx, CZ, 0xe9e6dc);

  /* ④ 护栏 */
  var railM = new T.MeshStandardMaterial({ color: 0xb8bcc2, roughness: 0.34, metalness: 0.78 });
  for (var s2 = -1; s2 <= 1; s2 += 2) {
    var rail = new T.Mesh(new T.BoxGeometry(LEN, 0.24, 0.14), railM);
    rail.position.set(CX, 0.62, CZ + s2 * (WID / 2 + 0.9)); rail.castShadow = true; G.add(rail);
    var posts = new T.InstancedMesh(new T.BoxGeometry(0.14, 0.9, 0.14), railM, 13), d = new T.Object3D();
    for (var i = 0; i < 13; i++) { d.position.set(X0 + 3 + i * (LEN - 6) / 12, 0.45, CZ + s2 * (WID / 2 + 0.9)); d.updateMatrix(); posts.setMatrixAt(i, d.matrix); }
    posts.castShadow = true; G.add(posts);
  }

  /* ⑤ 路灯（杆 + 自发光灯头） */
  var poleM = new T.MeshStandardMaterial({ color: 0x1c2026, roughness: 0.5, metalness: 0.6 });
  var lampM = new T.MeshStandardMaterial({ color: 0xffdca8, emissive: 0xffc27a, emissiveIntensity: 3.2, roughness: 0.4 });
  var poleGeo = new T.CylinderGeometry(0.09, 0.12, 6.2, 8);
  for (var k = 0; k < 6; k++) {
    var lx = X0 + 7 + k * (LEN - 14) / 5, side = (k % 2) ? 1 : -1;
    var lz = CZ + side * (WID / 2 + 2.6);
    var pole = new T.Mesh(poleGeo, poleM); pole.position.set(lx, 3.1, lz); pole.castShadow = true; G.add(pole);
    var head = new T.Mesh(new T.BoxGeometry(0.5, 0.28, 1.5), lampM); head.position.set(lx, 6.15, lz - side * 0.7); G.add(head);
  }

  /* ⑥ 车（复刻刹车那台白色 SUV：车漆PBR + 贯穿式红色尾灯） */
  function buildCar(px, pz, yaw) {
    var car = new T.Group(); car.position.set(px, 0, pz); car.rotation.y = yaw || 0;
    var paint = new T.MeshStandardMaterial({ color: 0xeef1f2, roughness: 0.26, metalness: 0.62 });
    var dark = new T.MeshStandardMaterial({ color: 0x15171b, roughness: 0.5, metalness: 0.4 });
    var glass = new T.MeshStandardMaterial({ color: 0x0a0d11, roughness: 0.08, metalness: 0.9 });
    var body = new T.Mesh(new T.BoxGeometry(4.7, 1.05, 2.0), paint); body.position.y = 1.02; body.castShadow = true; car.add(body);
    var skirt = new T.Mesh(new T.BoxGeometry(4.72, 0.36, 2.02), dark); skirt.position.y = 0.55; car.add(skirt);
    var cabin = new T.Mesh(new T.BoxGeometry(2.5, 0.82, 1.86), glass); cabin.position.set(-0.15, 1.9, 0); car.add(cabin);
    var roof = new T.Mesh(new T.BoxGeometry(2.6, 0.12, 1.9), paint); roof.position.set(-0.15, 2.34, 0); car.add(roof);
    var wg = new T.CylinderGeometry(0.44, 0.44, 0.36, 16), wm = new T.MeshStandardMaterial({ color: 0x0b0c0e, roughness: 0.85, metalness: 0.2 });
    [[1.45, -1.0], [1.45, 1.0], [-1.5, -1.0], [-1.5, 1.0]].forEach(function (p) {
      var w = new T.Mesh(wg, wm); w.rotation.x = Math.PI / 2; w.position.set(p[0], 0.44, p[1]); w.castShadow = true; car.add(w);
    });
    var tl = new T.Mesh(new T.BoxGeometry(0.06, 0.14, 1.86), new T.MeshStandardMaterial({ color: 0xff2a1a, emissive: 0xff1a10, emissiveIntensity: 4.0 }));
    tl.position.set(2.36, 1.16, 0); car.add(tl);
    var hl = new T.Mesh(new T.BoxGeometry(0.06, 0.12, 1.7), new T.MeshStandardMaterial({ color: 0xfff2d0, emissive: 0xffe6b0, emissiveIntensity: 3.2 }));
    hl.position.set(-2.36, 1.16, 0); car.add(hl);
    G.add(car); return car;
  }
  buildCar(CX, CZ - 4.4, 0);            // 一台（车头朝 +x）
  buildCar(CX - 18, CZ + 4.4, Math.PI); // 对向一台

  window.__RACE_STRIP = { X0: X0, X1: X1, Z0: Z0, Z1: Z1, spawn: { x: CX + 9, z: CZ - 4.4 } };
  window.__raceReady = true;
  try { console.log('[racestrip] 就绪', CX, CZ); } catch (e) {}
} catch (e) { window.__raceErr = (e && (e.stack || e.message)) || String(e); }
})();
