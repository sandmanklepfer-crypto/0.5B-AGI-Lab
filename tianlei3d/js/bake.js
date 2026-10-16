/* ============================================================================
   bake.js —— 把"代码实时拼出来的一堆 Mesh"固化（合并）成极少数 Draw Call
   ----------------------------------------------------------------------------
   原理：一栋和风町屋 = ~87 个独立 Mesh（每个都有自己的几何 + 一次 draw call）。
        按【材质】分桶合并 → 每栋从 87 次 draw call → 3~8 次。视觉零变化。
   注意：
     · 会动/会淡出的（屋顶淡出组 rg、门 gd、飘烟、幌子旗）不能合并 → 用 userData.noBake 标掉
     · 这里不做 FBX/GLB —— 网页上"合并几何"是唯一无副作用、无需构建步骤的做法
   ========================================================================== */
(function () {
  'use strict';

  /* 合并若干 BufferGeometry（要求属性一致：position/normal/uv，indexed 或都非 indexed） */
  function mergeGeos(geos) {
    var vtx = 0, idx = 0, hasUV = true, hasN = true, i, g;
    for (i = 0; i < geos.length; i++) {
      g = geos[i];
      var p = g.attributes.position;
      if (!p) return null;
      vtx += p.count;
      idx += g.index ? g.index.count : p.count;
      if (!g.attributes.uv) hasUV = false;
      if (!g.attributes.normal) hasN = false;
    }
    if (!hasN) return null;                       // 没法线 → 光照会错，宁可不合并

    var pos = new Float32Array(vtx * 3);
    var nrm = new Float32Array(vtx * 3);
    var uv = hasUV ? new Float32Array(vtx * 2) : null;
    var I = vtx > 65535 ? new Uint32Array(idx) : new Uint16Array(idx);

    var vo = 0, io = 0;
    for (i = 0; i < geos.length; i++) {
      g = geos[i];
      var pp = g.attributes.position;
      pos.set(pp.array, vo * 3);
      nrm.set(g.attributes.normal.array, vo * 3);
      if (uv) uv.set(g.attributes.uv.array, vo * 2);
      if (g.index) {
        var a = g.index.array;
        for (var k = 0; k < a.length; k++) I[io + k] = a[k] + vo;
        io += a.length;
      } else {
        for (var k2 = 0; k2 < pp.count; k2++) I[io + k2] = k2 + vo;
        io += pp.count;
      }
      vo += pp.count;
    }

    var out = new THREE.BufferGeometry();
    out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    out.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
    if (uv) out.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    out.setIndex(new THREE.BufferAttribute(I, 1));
    return out;
  }

  /* 合并一个 Group 的【直接 Mesh 子节点】，按材质分桶。
     子 Group（如 rg / gd）不动；标了 userData.noBake 的不动；ShaderMaterial 不动。 */
  function bakeGroup(group) {
    if (!group) return { before: 0, after: 0 };
    var buckets = new Map();
    var kids = group.children.slice();
    var before = 0, moved = 0;
    for (var i = 0; i < kids.length; i++) {
      var ch = kids[i];
      if (!ch.isMesh || ch.userData.noBake) continue;
      var mat = ch.material;
      if (!mat || mat.isShaderMaterial) continue;      // 幌子旗这类别动
      before++;
      var key = mat.uuid;
      if (!buckets.has(key)) buckets.set(key, { mat: mat, geos: [] });
      ch.updateMatrix();
      var gg = ch.geometry.clone();
      gg.applyMatrix4(ch.matrix);
      buckets.get(key).geos.push(gg);
      group.remove(ch);
      moved++;
    }
    var after = 0;
    buckets.forEach(function (b) {
      if (!b.geos.length) return;
      var merged = b.geos.length === 1 ? b.geos[0] : mergeGeos(b.geos);
      if (!merged) { after++; return; }               // 合并失败 → 保持原样（先不回填，安全）
      var m = new THREE.Mesh(merged, b.mat);
      m.castShadow = true; m.receiveShadow = true;
      m.userData.baked = true;
      group.add(m);
      after++;
    });
    return { before: moved, after: after };
  }

  /* 递归合并：跳过 noBake 子树 */
  function bakeTree(root) {
    var stat = { before: 0, after: 0, groups: 0 };
    (function walk(node) {
      var r = bakeGroup(node);
      stat.before += r.before; stat.after += r.after; stat.groups++;
      node.children.slice().forEach(function (c) {
        if (c.isGroup && !c.userData.noBake) walk(c);
      });
    })(root);
    return stat;
  }

  /* ==========================================================================
     灯光池 LightPool —— 把 ~18 个点光源压成恒定 3 个
     --------------------------------------------------------------------------
     为什么不能靠"调暗"：Three.js 前向渲染里，光的【数量】决定每个像素的
       光照循环次数。intensity=0 的光照样进入循环，照样费。必须"真的少"。
     做法：场景里只放【固定 MAX 个】真 PointLight；把 ~18 盏灯登记成"候选点"；
       每帧把这固定几个光【搬到】离玩家最近的几个候选位置并换色。
       → 光对象数量恒定 ⇒ 不会触发着色器重编译 ⇒ 无卡顿、真省性能。
     ========================================================================== */
  function LightPool(max) {
    this.max = max || 3;
    this.cands = [];                 // {x,z,color,intensity,dist}
    this.lights = [];
    var self = this;
    (function init() {
      if (typeof THREE === 'undefined') return;
      for (var i = 0; i < self.max; i++) {
        var L = new THREE.PointLight(0xffffff, 0, 12, 2);
        L.visible = false;           // 数量恒定但默认不亮
        self.lights.push(L);
      }
    })();
  }
  LightPool.prototype.attach = function (scene) {
    this.lights.forEach(function (L) { scene.add(L); });
  };
  /* 登记一盏"虚拟灯"（不进场景，只记位置/颜色/强度） */
  LightPool.prototype.add = function (x, z, color, intensity, dist) {
    this.cands.push({ x: x, z: z, color: color || 0xffb060,
                      intensity: intensity == null ? 0.9 : intensity,
                      dist: dist || 12, _d: 0 });
  };
  /* 每帧调用：把固定几个光搬到最近的候选点 */
  LightPool.prototype.update = function (px, pz) {
    var cands = this.cands;
    if (!cands.length) return;
    for (var i = 0; i < cands.length; i++) {
      var dx = cands[i].x - px, dz = cands[i].z - pz;
      cands[i]._d = dx * dx + dz * dz;
    }
    cands.sort(function (a, b) { return a._d - b._d; });
    for (var k = 0; k < this.lights.length; k++) {
      var L = this.lights[k], c = cands[k];
      if (c) {
        L.position.set(c.x, 2.2, c.z);
        L.color.setHex(c.color);
        L.intensity = c.intensity;
        L.distance = c.dist;
        L.visible = true;
      } else {
        L.visible = false; L.intensity = 0;
      }
    }
  };

  window.Bake = { mergeGeos: mergeGeos, bakeGroup: bakeGroup, bakeTree: bakeTree };
  window.LightPool = LightPool;
})();
