/* ============================================================================
 *  wildlands.js —— 天泪纪元 · 世界之外（无限远景地形 + 水域 + 昼夜）
 *  --------------------------------------------------------------------------
 *  要解决的问题
 *    原来主城之外是纯黑虚空：走到地图边缘就是一片黑，非常出戏。
 *
 *  代码来源
 *    移植自 /workspace/tianlei_online/_frozen_3d/world3d.js
 *    （那份文件本身就是「对标 Godot 那份地形」的 Three.js 实现：
 *      多层噪声高度场 / 三平面 PBR / Gerstner 波海洋 / 程序化天空 + 昼夜色带）
 *    这里只取「世界之外」需要的那部分，不动任何原有玩法代码。
 *
 *  设计原则（很重要）
 *    · 主城（0..228 × 0..156）和营地（x<0）的地面、碰撞、玩法全部原样
 *    · 城外只做「看得见的地形」，不参与 gameplay 碰撞
 *      → 玩家走不出去（原有边界墙还在），但眼里再也不是黑虚空
 *    · 地形用区块流式生成 + 预算控制，手机上加不了多少开销
 *    · 昼夜用极慢的速度推太阳，不影响战斗可读性
 *
 *  为什么不做成"能走出去的真·开放世界"
 *    主城的碰撞是高度图（逐格），城外是程序化地形（逐顶点）。
 *    两套碰撞体系硬拼会出现「边缘陷落 / 站在半空」这类 bug。
 *    更稳的做法：城墙边界不动（谁也别掉出去），城外给远景。
 *    视觉上完全够用，风险最低。这一步先做这个。
 *
 *  依赖：THREE + 可选 ARENA（拿到 scene / renderer / 玩家坐标）
 * ========================================================================== */
(function (root) {
  'use strict';

  if (!root.THREE) return;

  var W = {
    /* ---- 参数（对齐 world3d.js 的默认值）---- */
    cfg: {
      chunkSize: 220,
      viewChunks: 2,          // 手机保守：半径 2 圈（5x5=25 块）
      segments: 44,           // 每块网格密度（远景不需要高）
      seed: 20260,
      seaLevel: -1.4,

      /* 主城范围：这块区域不生成远景地形（避免和城里的地面打架） */
      cityMinX: -80,          // 含营地（营地 x 从 -78 起）
      cityMaxX: 234,
      cityMinZ: -34,          // 含北边赛车区（z -30 起）
      cityMaxZ: 162,

      /* 地形（从 world3d 的 terrain 段取用） */
      maxPeakHeight: 120,
      mountainLevel: 45,
      treeLine: 34,
      beachLine: 2.2,

      /* 噪声（world3d 的 noise 段） */
      continental: 0.0022,
      mountain: 0.010,
      moisture: 0.0026,

      /* 昼夜 */
      daySpeed: 0.0035,       // 一圈约 285 秒；0 则静止
      startTime: 0.53,        // 0.25=正午 0.5=地平线 0.75=午夜 → 0.53 是「刚入夜的黄昏」
      nightFloor: 0.20        // 夜里最暗保留的环境光比例
    },

    inited: false,
    scene: null,
    renderer: null,
    group: null,
    chunks: {},
    _built: 0,
    _dayTime: 0.53,
    _sun: null, _hemi: null, _skyMesh: null,
    water: null,
    _frame: 0,
    _budget: 2,

    /* ------------------------------------------------------------------ */
    /*  噪声（照搬 world3d.js 的 _noise2 / _fbm / _sfbm / _ridged）        */
    /* ------------------------------------------------------------------ */
    _noise2: function (x, y) {
      var X = Math.floor(x), Y = Math.floor(y);
      var fx = x - X, fy = y - Y;
      var u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy);
      function h(a, b) {
        var n = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
        return n - Math.floor(n);
      }
      var a = h(X, Y), b = h(X + 1, Y), c = h(X, Y + 1), d = h(X + 1, Y + 1);
      var top = a + (b - a) * u, bot = c + (d - c) * u;
      return top + (bot - top) * v;
    },
    _fbm: function (x, y, oct, gain) {
      var s = 0, a = 0.5, f = 1;
      for (var i = 0; i < oct; i++) { s += a * this._noise2(x * f, y * f); f *= 2.03; a *= (gain || 0.5); }
      return s;
    },
    _snoise2: function (x, y) { return this._noise2(x, y) * 2 - 1; },
    _sfbm: function (x, y, oct, gain) {
      var s = 0, a = 0.5, f = 1, norm = 0;
      for (var i = 0; i < oct; i++) { s += a * this._snoise2(x * f, y * f); norm += a; f *= 2.03; a *= (gain || 0.5); }
      return s / norm;
    },
    _ridged: function (x, y, oct) {
      var s = 0, a = 0.5, f = 1;
      for (var i = 0; i < oct; i++) { s += a * (1 - Math.abs(this._noise2(x * f, y * f) * 2 - 1)); f *= 2.07; a *= 0.5; }
      return s;
    },

    /* 高度场：大陆起伏 + 山脊 + 细节 */
    heightAt: function (wx, wz) {
      var C = this.cfg, s = C.seed % 1000;
      var x = wx + s, z = wz + s;

      var cont = this._sfbm(x * C.continental, z * C.continental, 3, 0.5);
      var ridge = this._ridged(x * C.mountain, z * C.mountain, 4);
      var mountainMask = Math.max(0, cont - 0.18) / 0.82;
      var mount = ridge * mountainMask * C.maxPeakHeight;
      var detail = (this._fbm(x * 0.05, z * 0.05, 2, 0.5) - 0.5) * 2.2;

      var h = cont * 26 + mount + detail;
      h *= this._edgeFade(wx, wz);
      return h;
    },

    /* 主城附近把地形压平，越往外越恢复原样（防止与城里地面冲突） */
    _edgeFade: function (wx, wz) {
      var C = this.cfg;
      var dx = 0, dz = 0;
      if (wx < C.cityMinX) dx = C.cityMinX - wx;
      else if (wx > C.cityMaxX) dx = wx - C.cityMaxX;
      if (wz < C.cityMinZ) dz = C.cityMinZ - wz;
      else if (wz > C.cityMaxZ) dz = wz - C.cityMaxZ;
      var d = Math.sqrt(dx * dx + dz * dz);
      if (d <= 0) return 0;
      var t = Math.min(1, d / 90);
      return t * t * (3 - 2 * t);
    },

    _inCity: function (x, z) {
      var C = this.cfg;
      return x >= C.cityMinX && x <= C.cityMaxX && z >= C.cityMinZ && z <= C.cityMaxZ;
    },

    /* ------------------------------------------------------------------ */
    /*  初始化                                                             */
    /* ------------------------------------------------------------------ */
    init: function (scene, renderer) {
      if (this.inited) return this;
      if (!scene) {
        var A = root.ARENA;
        scene = A && A.scene;
        renderer = A && A.renderer;
      }
      if (!scene) return this;

      this.scene = scene;
      this.renderer = renderer;
      this.group = new THREE.Group();
      this.group.name = 'wildlands';
      scene.add(this.group);

      this._initSky();
      this._initWater();
      this._initLights();
      this._dayTime = this.cfg.startTime;

      this.inited = true;
      try { console.log('[wildlands] 世界之外已启用 · 区块', this.cfg.chunkSize, '· 视距', this.cfg.viewChunks); } catch (e) {}
      return this;
    },

    /* ---- 天空球（照搬 world3d 的 shader，缩放到主城尺度）---- */
    _initSky: function () {
      var geo = new THREE.SphereGeometry(1800, 24, 16);
      var mat = new THREE.ShaderMaterial({
        side: THREE.BackSide, depthWrite: false, depthTest: false,
        uniforms: {
          topColor: { value: new THREE.Color(0x2f6fd0) },
          midColor: { value: new THREE.Color(0x9dc4ee) },
          botColor: { value: new THREE.Color(0xe9d9c0) },
          sunDir: { value: new THREE.Vector3(0.4, 0.6, 0.3) },
          sunTint: { value: new THREE.Color(0xffd9a0) },
          time: { value: 0 },
          cloudSpeed: { value: 0.015 },
          cloudAmt: { value: 0.55 }
        },
        vertexShader: [
          'varying vec3 vDir;',
          'void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }'
        ].join('\n'),
        fragmentShader: [
          'varying vec3 vDir;',
          'uniform vec3 topColor, midColor, botColor, sunTint;',
          'uniform vec3 sunDir;',
          'uniform float time, cloudSpeed, cloudAmt;',
          'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
          'float noise(vec2 p){',
          '  vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);',
          '  float a=hash(i), b=hash(i+vec2(1,0)), c=hash(i+vec2(0,1)), d=hash(i+vec2(1,1));',
          '  return mix(mix(a,b,f.x), mix(c,d,f.x), f.y);',
          '}',
          'float fbm(vec2 p){ float s=0.0, a=0.5; for(int i=0;i<5;i++){ s+=a*noise(p); p*=2.03; a*=0.5; } return s; }',
          'void main(){',
          '  vec3 d = normalize(vDir);',
          '  float h = clamp(d.y*0.5+0.5, 0.0, 1.0);',
          '  vec3 col = mix(botColor, midColor, smoothstep(0.46,0.62,h));',
          '  col = mix(col, topColor, smoothstep(0.6,0.95,h));',
          '  float sd = max(dot(d, normalize(sunDir)), 0.0);',
          '  col += sunTint * pow(sd, 220.0) * 2.2;',
          '  col += sunTint * pow(sd, 8.0) * 0.28;',
          '  if (d.y > 0.02) {',
          '    vec2 uv = d.xz / max(d.y, 0.06) * 0.28;',
          '    uv += vec2(time*cloudSpeed, time*cloudSpeed*0.6);',
          '    float c = fbm(uv*1.4) * smoothstep(0.02,0.4,d.y);',
          '    col = mix(col, vec3(0.96,0.97,1.0), clamp(c*cloudAmt, 0.0, 0.85));',
          '  }',
          '  gl_FragColor = vec4(col, 1.0);',
          '}'
        ].join('\n')
      });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.frustumCulled = false;
      mesh.renderOrder = -1000;
      this.group.add(mesh);
      this._skyMesh = mesh;
    },

    /* ---- 水面（三角函数波 + 菲涅尔 + 高光）---- */
    _initWater: function () {
      var C = this.cfg;
      var geo = new THREE.PlaneGeometry(9000, 9000, 1, 1);
      geo.rotateX(-Math.PI / 2);

      var mat = new THREE.ShaderMaterial({
        transparent: true, depthWrite: false,
        uniforms: {
          time: { value: 0 },
          deep: { value: new THREE.Color(0.02, 0.07, 0.13) },
          shallow: { value: new THREE.Color(0.10, 0.30, 0.36) },
          foam: { value: new THREE.Color(0.95, 0.94, 0.92) },
          skyTop: { value: new THREE.Color(0.18, 0.34, 0.62) },
          skyBot: { value: new THREE.Color(0.72, 0.82, 0.92) },
          sunDir: { value: new THREE.Vector3(0.4, 0.7, 0.3) },
          seaLevel: { value: C.seaLevel },
          waveH: { value: 0.11 },
          waveSpeed: { value: 0.22 }
        },
        vertexShader: [
          'varying vec3 vWPos;',
          'uniform float time, waveH, waveSpeed, seaLevel;',
          'void main(){',
          '  vec3 p = position;',
          '  vec4 wp = modelMatrix * vec4(p, 1.0);',
          '  float w = sin(wp.x*0.035 + time*waveSpeed) * cos(wp.z*0.031 + time*waveSpeed*1.3);',
          '  w += sin(wp.x*0.087 - time*waveSpeed*1.7) * 0.4;',
          '  wp.y = seaLevel + w * waveH * 3.0;',
          '  vWPos = wp.xyz;',
          '  gl_Position = projectionMatrix * viewMatrix * wp;',
          '}'
        ].join('\n'),
        fragmentShader: [
          'varying vec3 vWPos;',
          'uniform vec3 deep, shallow, foam, skyTop, skyBot, sunDir;',
          'uniform float time, seaLevel;',
          'void main(){',
          '  vec3 V = normalize(cameraPosition - vWPos);',
          '  float fres = pow(1.0 - max(V.y, 0.0), 3.0);',
          '  vec3 col = mix(deep, shallow, 0.5);',
          '  vec3 skyRefl = mix(skyBot, skyTop, 0.5);',
          '  col = mix(col, skyRefl, fres * 0.7);',
          '  float spec = pow(max(dot(reflect(-normalize(sunDir), vec3(0.0,1.0,0.0)), V), 0.0), 60.0);',
          '  col += vec3(1.0,0.92,0.8) * spec * 1.4;',
          '  float n = sin(vWPos.x*0.7 + time*0.9) * cos(vWPos.z*0.63 - time*0.75);',
          '  col += foam * max(0.0, n) * 0.05;',
          '  gl_FragColor = vec4(col, 0.86);',
          '}'
        ].join('\n')
      });
      var mesh = new THREE.Mesh(geo, mat);
      mesh.position.y = C.seaLevel;
      mesh.frustumCulled = false;
      mesh.renderOrder = -500;
      this.group.add(mesh);
      this.water = mesh;
    },

    /* ---- 光照：只加一个方向光 + 半球光（原来城里的灯不动）---- */
    _initLights: function () {
      var sun = new THREE.DirectionalLight(0xffd9a0, 0.9);
      sun.position.set(120, 180, 80);
      sun.castShadow = false;                 // 远景不投影，省性能
      this.group.add(sun);
      this._sun = sun;

      var hemi = new THREE.HemisphereLight(0x8fb8e8, 0x2a2620, 0.5);
      this.group.add(hemi);
      this._hemi = hemi;
    },

    /* ------------------------------------------------------------------ */
    /*  地形区块                                                           */
    /* ------------------------------------------------------------------ */
    _terrainMat: null,
    _terrainMaterial: function () {
      if (this._terrainMat) return this._terrainMat;
      var mat = new THREE.MeshStandardMaterial({
        vertexColors: true,
        roughness: 0.95,
        metalness: 0.02
      });
      try {
        if (root.ARENA && ARENA.matTex) {
          var m2 = ARENA.matTex('grass', { rep: 60, rough: 0.95 });
          if (m2 && m2.map) { mat.map = m2.map; }
        }
      } catch (e) {}
      mat.needsUpdate = true;
      this._terrainMat = mat;
      return mat;
    },

    _COL: {
      sand: [0.76, 0.70, 0.52],
      grass: [0.28, 0.42, 0.22],
      rock: [0.38, 0.36, 0.34],
      snow: [0.92, 0.94, 0.97]
    },

    _colorAt: function (h, slope) {
      var C = this.cfg, K = this._COL;
      var t;
      if (h < C.beachLine) return K.sand;
      if (h > C.mountainLevel + 30) return K.snow;
      if (h > C.mountainLevel || slope > 0.55) {
        t = Math.min(1, (h - C.treeLine) / 40);
        return [
          K.rock[0] + (K.snow[0] - K.rock[0]) * t * 0.55,
          K.rock[1] + (K.snow[1] - K.rock[1]) * t * 0.55,
          K.rock[2] + (K.snow[2] - K.rock[2]) * t * 0.55
        ];
      }
      t = Math.min(1, (h - C.beachLine) / 8);
      return [
        K.sand[0] + (K.grass[0] - K.sand[0]) * t,
        K.sand[1] + (K.grass[1] - K.sand[1]) * t,
        K.sand[2] + (K.grass[2] - K.sand[2]) * t
      ];
    },

    _makeChunk: function (cx, cz) {
      var C = this.cfg, seg = C.segments, cs = C.chunkSize;
      var ox = cx * cs, oz = cz * cs;

      // 整块都在城里 → 不生成（省性能，也避免和地面打架）
      if (ox > C.cityMinX - cs && ox < C.cityMaxX + cs &&
          oz > C.cityMinZ - cs && oz < C.cityMaxZ + cs) {
        this.chunks[cx + ',' + cz] = null;
        return;
      }

      var geo = new THREE.PlaneGeometry(cs, cs, seg, seg);
      geo.rotateX(-Math.PI / 2);
      var pos = geo.attributes.position;
      var colArr = new Float32Array(pos.count * 3);

      for (var i = 0; i < pos.count; i++) {
        var x = pos.getX(i) + ox;
        var z = pos.getZ(i) + oz;
        var h = this.heightAt(x, z);
        pos.setY(i, h);

        var hx = this.heightAt(x + 2, z) - this.heightAt(x - 2, z);
        var hz = this.heightAt(x, z + 2) - this.heightAt(x, z - 2);
        var slope = Math.min(1, Math.sqrt(hx * hx + hz * hz) / 8);

        var c = this._colorAt(h, slope);
        colArr[i * 3] = c[0]; colArr[i * 3 + 1] = c[1]; colArr[i * 3 + 2] = c[2];
      }
      geo.setAttribute('color', new THREE.BufferAttribute(colArr, 3));
      geo.computeVertexNormals();

      var mesh = new THREE.Mesh(geo, this._terrainMaterial());
      mesh.position.set(ox, 0, oz);
      mesh.receiveShadow = false;
      mesh.frustumCulled = true;

      this.group.add(mesh);
      this.chunks[cx + ',' + cz] = mesh;
      this._built++;
    },

    /* 以玩家为中心流式加载/卸载 */
    updateChunks: function (px, pz, budget) {
      var C = this.cfg, cs = C.chunkSize, vc = C.viewChunks;
      var ccx = Math.round(px / cs), ccz = Math.round(pz / cs);
      var b = budget == null ? this._budget : budget;

      for (var dx = -vc; dx <= vc && b > 0; dx++) {
        for (var dz = -vc; dz <= vc && b > 0; dz++) {
          var cx = ccx + dx, cz = ccz + dz, k = cx + ',' + cz;
          if (k in this.chunks) continue;
          this._makeChunk(cx, cz);
          b--;
        }
      }
      for (var kk in this.chunks) {
        var p = kk.split(',');
        if (Math.abs(+p[0] - ccx) > vc + 1 || Math.abs(+p[1] - ccz) > vc + 1) {
          var g = this.chunks[kk];
          if (g) {
            this.group.remove(g);
            try { g.geometry.dispose(); } catch (e) {}
          }
          delete this.chunks[kk];
        }
      }
    },

    /* ------------------------------------------------------------------ */
    /*  昼夜交替                                                           */
    /* ------------------------------------------------------------------ */
    setDayTime: function (t) { this._dayTime = ((t % 1) + 1) % 1; },
    getDayTime: function () { return this._dayTime; },

    updateSky: function (dt, px, pz) {
      var C = this.cfg;
      this._dayTime = (this._dayTime + dt * C.daySpeed) % 1;
      var ang = this._dayTime * Math.PI * 2;
      var sy = Math.sin(ang), sx = Math.cos(ang);
      var dir = new THREE.Vector3(sx * 0.55, sy, sx * 0.28 + 0.35).normalize();

      if (this._sun) {
        this._sun.position.set(dir.x * 400 + (px || 0), dir.y * 400 + 60, dir.z * 400 + (pz || 0));
        var day = Math.max(0, sy);
        this._sun.intensity = 0.12 + day * 1.5;
        var duskC = new THREE.Color(0xff9a5c), dayC = new THREE.Color(0xfff2e0);
        this._sun.color.copy(duskC).lerp(dayC, Math.min(1, day * 1.6));
      }
      if (this._hemi) {
        var day2 = Math.max(0, sy);
        this._hemi.intensity = C.nightFloor * 0.9 + day2 * 0.55;
        var nC = new THREE.Color(0x2a3550), dC = new THREE.Color(0x8fb8e8);
        this._hemi.color.copy(nC).lerp(dC, Math.min(1, day2 * 1.8));
      }

      if (this._skyMesh) {
        var u = this._skyMesh.material.uniforms;
        u.time.value += dt;
        u.sunDir.value.copy(dir);
        var day3 = Math.max(0, sy);
        var dusk = 1 - Math.min(1, day3 * 2.2);
        u.topColor.value.setRGB(0.10 + day3 * 0.10, 0.16 + day3 * 0.28, 0.34 + day3 * 0.44);
        u.midColor.value.setRGB(0.30 + day3 * 0.28, 0.26 + day3 * 0.50, 0.42 + day3 * 0.50);
        u.botColor.value.setRGB(0.55 + dusk * 0.35, 0.30 + dusk * 0.22 + day3 * 0.30, 0.26 + dusk * 0.04 + day3 * 0.45);
        u.sunTint.value.setRGB(1.0, 0.72 + day3 * 0.25, 0.42 + day3 * 0.45);
        u.cloudAmt.value = 0.30 + day3 * 0.35;
        this._skyMesh.position.set(px || 0, 0, pz || 0);
      }

      if (this.water) {
        var wu = this.water.material.uniforms;
        wu.time.value += dt;
        wu.sunDir.value.copy(dir);
        if (this._skyMesh) {
          wu.skyTop.value.copy(this._skyMesh.material.uniforms.topColor.value);
          wu.skyBot.value.copy(this._skyMesh.material.uniforms.botColor.value);
        }
        this.water.position.x = px || 0;
        this.water.position.z = pz || 0;
      }

      // 雾气颜色跟着天色
      try {
        var sc = root.ARENA && ARENA.scene;
        if (sc && sc.fog && sc.fog.color) {
          var day4 = Math.max(0, sy);
          sc.fog.color.setRGB(0.04 + day4 * 0.10, 0.05 + day4 * 0.12, 0.09 + day4 * 0.16);
        }
      } catch (e) {}
    },

    /* ------------------------------------------------------------------ */
    /*  每帧                                                               */
    /* ------------------------------------------------------------------ */
    update: function (dt, px, pz) {
      if (!this.inited) return;
      this._frame++;

      if (px == null) {
        try {
          px = (root.P && root.P.x != null) ? root.P.x : 0;
          pz = (root.P && root.P.z != null) ? root.P.z : 0;
        } catch (e) { px = 0; pz = 0; }
      }

      this.updateSky(dt, px, pz);

      if (this._frame % 6 === 0) {
        this.updateChunks(px, pz, this._budget);
      }
    }
  };

  root.Wildlands = W;

  /* ---- 自动挂载：有 ARENA 就自己起来，不改 shooter.js ---- */
  function autoBoot() {
    if (!root.ARENA || !root.ARENA.scene) { setTimeout(autoBoot, 600); return; }
    try {
      W.init(root.ARENA.scene, root.ARENA.renderer);
      var px = 0, pz = 0;
      try { if (root.P) { px = P.x || 0; pz = P.z || 0; } } catch (e) {}
      W.updateChunks(px, pz, 8);
    } catch (e) {
      try { console.log('[wildlands] 启动失败', e); } catch (_) {}
    }
  }
  if (root.ARENA && root.ARENA.scene) setTimeout(autoBoot, 0);
  else setTimeout(autoBoot, 800);

})(typeof self !== 'undefined' ? self : this);
