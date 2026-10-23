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

      /* 画质档：low / mid / high（植被密度与网格密度随之切换） */
      quality: 'mid',

      /* 植被密度（0 = 关，手机卡就调低） */
      vegDensity: 0.45,
      treeDensity: 0.12,

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

    /* ---- 水面：3 波 + 海床深度感知 + 岸边泡沫 + SSS（移植 world3d）---- */
    _initWater: function () {
      var C = this.cfg;
      var sb = this._buildSeabed();

      var geo = new THREE.PlaneGeometry(9000, 9000, 48, 48);
      geo.rotateX(-Math.PI / 2);

      var mat = new THREE.ShaderMaterial({
        transparent: true,
        uniforms: {
          time: { value: 0 },
          deep: { value: new THREE.Color(0.012, 0.055, 0.115) },
          shallow: { value: new THREE.Color(0.06, 0.34, 0.40) },
          foam: { value: new THREE.Color(0.95, 0.94, 0.92) },
          sss: { value: new THREE.Color(0.10, 0.78, 0.68) },
          skyTop: { value: new THREE.Color(0.18, 0.34, 0.62) },
          skyBot: { value: new THREE.Color(0.72, 0.82, 0.92) },
          sunDir: { value: new THREE.Vector3(0.4, 0.7, 0.3) },
          camPos: { value: new THREE.Vector3() },
          dayFactor: { value: 0.8 },
          seabedTex: { value: sb.tex },
          seaParams: { value: new THREE.Vector4(sb.R, sb.minH, sb.maxH, C.seaLevel) },
          waveH: { value: 0.34 },
          waveS: { value: 0.28 }
        },
        vertexShader: [
          'uniform float time, waveH, waveS;',
          'varying vec3 vWPos; varying vec3 vNrm; varying float vWave;',
          'float wave(vec2 q, float t){',
          '  return sin(q.x*0.055 + t)*0.5 + sin(q.y*0.047 - t*0.8)*0.5 + sin((q.x+q.y)*0.11 + t*1.3)*0.45;',
          '}',
          'void main(){',
          '  vec3 p = position;',
          '  float t = time * waveS;',
          '  float h = wave(p.xz, t) * waveH;',
          '  float hx = wave(p.xz + vec2(1.4, 0.0), t) * waveH;',
          '  float hz = wave(p.xz + vec2(0.0, 1.4), t) * waveH;',
          '  vNrm = normalize(vec3(-(hx - h)*0.55, 1.0, -(hz - h)*0.55));',
          '  vWave = h;',
          '  p.y += h;',
          '  vec4 wp = modelMatrix * vec4(p, 1.0);',
          '  vWPos = wp.xyz;',
          '  gl_Position = projectionMatrix * viewMatrix * wp;',
          '}'
        ].join('\n'),
        fragmentShader: [
          'precision highp float;',
          'varying vec3 vWPos; varying vec3 vNrm; varying float vWave;',
          'uniform vec3 deep, shallow, foam, sss, skyTop, skyBot, sunDir, camPos;',
          'uniform float time, dayFactor;',
          'uniform sampler2D seabedTex;',
          'uniform vec4 seaParams;',
          'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
          'float noise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);',
          '  return mix(mix(hash(i),hash(i+vec2(1.0,0.0)),f.x), mix(hash(i+vec2(0.0,1.0)),hash(i+vec2(1.0,1.0)),f.x), f.y); }',
          'float waterDepth(vec2 wxz){',
          '  vec2 uv = (wxz + seaParams.x) / (2.0 * seaParams.x);',
          '  uv = clamp(uv, 0.0, 1.0);',
          '  float t = texture2D(seabedTex, uv).r;',
          '  float hb = seaParams.y + t * (seaParams.z - seaParams.y);',
          '  return seaParams.w - hb;',
          '}',
          'void main(){',
          '  vec3 n = normalize(vNrm);',
          '  vec3 V = normalize(camPos - vWPos);',
          '  vec3 L = normalize(sunDir);',
          '  float wd = max(waterDepth(vWPos.xz), 0.0);',
          '  float depthF = clamp(wd / 16.0, 0.0, 1.0);',
          '  vec3 col = mix(shallow, deep, depthF);',
          '  float sssF = (1.0 - depthF) * max(dot(n, L), 0.0);',
          '  col += sss * sssF * 0.55 * dayFactor;',
          '  float fres = pow(1.0 - clamp(dot(n, V), 0.0, 1.0), 4.0);',
          '  vec3 skyRefl = mix(skyBot, skyTop, 0.5);',
          '  col = mix(col, skyRefl, fres * 0.75);',
          '  float spec = pow(max(dot(reflect(-L, n), V), 0.0), 160.0);',
          '  col += vec3(1.0, 0.97, 0.90) * spec * 2.2 * dayFactor;',
          '  float shore = 1.0 - smoothstep(0.0, 0.9, wd);',
          '  float fnoise = noise(vWPos.xz * 0.35 + vec2(time*0.5, -time*0.35));',
          '  float foamF = clamp(shore * (0.35 + fnoise * 0.65), 0.0, 1.0);',
          '  col = mix(col, foam, foamF * 0.85);',
          '  float alpha = mix(0.22, 0.96, depthF);',
          '  gl_FragColor = vec4(col, clamp(alpha, 0.05, 0.98));',
          '}'
        ].join('\n')
      });

      var mesh = new THREE.Mesh(geo, mat);
      mesh.position.y = C.seaLevel;
      mesh.frustumCulled = false;
      mesh.renderOrder = 2;
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

    /* 画质档：low 关植被省性能，mid/high 按密度开 */
    setQuality: function (q) {
      this.cfg.quality = q;
      if (q === 'low') {
        this.cfg.vegDensity = 0;
        this.cfg.treeDensity = 0;
        this.cfg.segments = 32;
      } else if (q === 'high') {
        this.cfg.vegDensity = 0.75;
        this.cfg.treeDensity = 0.22;
        this.cfg.segments = 56;
      } else {
        this.cfg.vegDensity = 0.45;
        this.cfg.treeDensity = 0.12;
        this.cfg.segments = 44;
      }
      // 重建已有区块（尺寸变了）
      var keys = Object.keys(this.chunks);
      for (var i = 0; i < keys.length; i++) {
        var g = this.chunks[keys[i]];
        if (g) {
          try {
            var veg = g.userData && g.userData.veg;
            if (veg) { veg.traverse(function (o) { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); this.group.remove(veg); }
            this.group.remove(g); g.geometry.dispose();
          } catch (e) {}
        }
        delete this.chunks[keys[i]];
      }
      this._budget = 4;
      return q;
    },

    /* ------------------------------------------------------------------ */
    /*  地形材质：真 GLSL（多尺度噪声分色 + 高度/坡度混合 + 距离雾）      */
    /*  移植自 world3d.js 的 _terrainMaterial，替换掉原来的顶点色方案     */
    /* ------------------------------------------------------------------ */
    _terrainMat: null,
    _terrainMaterial: function () {
      if (this._terrainMat) return this._terrainMat;
      var C = this.cfg;

      var mat = new THREE.ShaderMaterial({
        uniforms: {
          sunDir: { value: new THREE.Vector3(0.4, 0.7, 0.3) },
          snowLine: { value: C.mountainLevel + 30 },
          treeLine: { value: C.treeLine },
          beachLine: { value: C.beachLine },
          dayFactor: { value: 0.8 },
          fogColor: { value: new THREE.Color(0.16, 0.18, 0.24) },
          time: { value: 0 }
        },
        vertexShader: [
          'varying vec3 vWPos; varying vec3 vWNor; varying float vHeight;',
          'void main(){',
          '  vec4 wp = modelMatrix * vec4(position, 1.0);',
          '  vWPos = wp.xyz; vHeight = position.y;',
          '  vWNor = normalize(mat3(modelMatrix) * normal);',
          '  gl_Position = projectionMatrix * viewMatrix * wp;',
          '}'
        ].join('\n'),
        fragmentShader: [
          'precision highp float;',
          'varying vec3 vWPos; varying vec3 vWNor; varying float vHeight;',
          'uniform vec3 sunDir; uniform float snowLine, treeLine, beachLine, dayFactor, time;',
          'uniform vec3 fogColor;',
          'float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453); }',
          'float noise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);',
          '  float a=hash(i),b=hash(i+vec2(1.0,0.0)),c=hash(i+vec2(0.0,1.0)),d=hash(i+vec2(1.0,1.0));',
          '  return mix(mix(a,b,f.x),mix(c,d,f.x),f.y); }',
          'float fbm(vec2 p){ float s=0.0,a=0.5; for(int i=0;i<5;i++){ s+=a*noise(p); p*=2.03; a*=0.5;} return s; }',
          'void main(){',
          '  vec3 n = normalize(vWNor);',
          '  float sl = 1.0 - clamp(n.y, 0.0, 1.0);',
          '  float macro = fbm(vWPos.xz*0.0026);',
          '  float mid   = fbm(vWPos.xz*0.011 + 31.7);',
          '  float fine  = fbm(vWPos.xz*0.085);',
          '  vec3 cSand  = vec3(0.72, 0.66, 0.48);',
          '  vec3 cGreen = vec3(0.17, 0.30, 0.12);',
          '  vec3 cStraw = vec3(0.45, 0.40, 0.20);',
          '  vec3 cDry   = vec3(0.36, 0.31, 0.17);',
          '  vec3 cRock  = vec3(0.30, 0.27, 0.25);',
          '  vec3 cRockD = vec3(0.18, 0.16, 0.15);',
          '  vec3 cSnow  = vec3(0.92, 0.94, 0.98);',
          '  vec3 grass = mix(cGreen, cStraw, smoothstep(0.34, 0.72, mid));',
          '  grass = mix(grass, cDry, smoothstep(0.52, 0.86, macro));',
          '  grass *= mix(0.82, 1.18, fine);',
          '  vec3 rock = mix(cRock, cRockD, smoothstep(0.3, 0.9, fine));',
          '  float rockW = smoothstep(0.34, 0.62, sl + (fine-0.5)*0.25);',
          '  vec3 albedo = mix(grass, rock, rockW);',
          '  float snowW = smoothstep(snowLine, snowLine + 34.0, vHeight) * (1.0 - sl*0.55);',
          '  albedo = mix(albedo, cSnow, snowW);',
          '  float beachW = smoothstep(beachLine + 1.6, beachLine - 0.6, vHeight);',
          '  albedo = mix(albedo, cSand, beachW * (1.0 - rockW*0.6));',
          '  float wet = smoothstep(0.8, -1.8, vHeight);',
          '  albedo = mix(albedo, vec3(0.30, 0.34, 0.37), wet * 0.42);',
          '  vec3 L = normalize(sunDir);',
          '  float ndl = max(dot(n, L), 0.0);',
          '  float sky = clamp(n.y*0.5+0.5, 0.0, 1.0);',
          '  vec3 col = albedo * (ndl*1.25*dayFactor + sky*(0.35+0.35*dayFactor) + 0.06);',
          '  col = mix(col, col * vec3(1.22, 1.00, 0.74), ndl * 0.55 * (1.0-dayFactor*0.5));',
          '  float dist = length(cameraPosition - vWPos);',
          '  float fog = 1.0 - exp(-dist*0.0011);',
          '  col = mix(col, fogColor, clamp(fog, 0.0, 0.9));',
          '  gl_FragColor = vec4(col, 1.0);',
          '}'
        ].join('\n')
      });
      this._terrainMat = mat;
      return mat;
    },

    /* 海床高度图：给水面做"水深感知"（不用深度纹理，手机上便宜得多） */
    _buildSeabed: function () {
      if (this.seabed) return this.seabed;
      var N = 128, R = 2600, minH = -30, maxH = 40;
      var data = new Uint8Array(N * N * 4);
      for (var iz = 0; iz < N; iz++) {
        for (var ix = 0; ix < N; ix++) {
          var wx = -R + (ix + 0.5) / N * 2 * R;
          var wz = -R + (iz + 0.5) / N * 2 * R;
          var h = this.heightAt(wx, wz);
          var v = Math.max(0, Math.min(255, Math.round((h - minH) / (maxH - minH) * 255)));
          var i = (iz * N + ix) * 4;
          data[i] = v; data[i + 1] = v; data[i + 2] = v; data[i + 3] = 255;
        }
      }
      var tex = new THREE.DataTexture(data, N, N, THREE.RGBAFormat);
      tex.minFilter = THREE.LinearFilter; tex.magFilter = THREE.LinearFilter;
      tex.needsUpdate = true;
      this.seabed = { tex: tex, R: R, minH: minH, maxH: maxH };
      return this.seabed;
    },

    _makeChunk: function (cx, cz) {
      var C = this.cfg, seg = C.segments, cs = C.chunkSize;
      var ox = cx * cs, oz = cz * cs;

      if (ox > C.cityMinX - cs && ox < C.cityMaxX + cs &&
          oz > C.cityMinZ - cs && oz < C.cityMaxZ + cs) {
        this.chunks[cx + ',' + cz] = null;
        return;
      }

      var geo = new THREE.PlaneGeometry(cs, cs, seg, seg);
      geo.rotateX(-Math.PI / 2);
      var pos = geo.attributes.position;
      for (var i = 0; i < pos.count; i++) {
        var x = pos.getX(i) + ox;
        var z = pos.getZ(i) + oz;
        pos.setY(i, this.heightAt(x, z));
      }
      geo.computeVertexNormals();

      var mesh = new THREE.Mesh(geo, this._terrainMaterial());
      mesh.position.set(ox, 0, oz);
      mesh.frustumCulled = true;
      this.group.add(mesh);
      this.chunks[cx + ',' + cz] = mesh;
      this._built++;

      /* 植被：InstancedMesh，一次 draw call 出上千棵 */
      var veg = this._makeVegetation(ox, oz, cs);
      if (veg) {
        if (!mesh.userData) mesh.userData = {};
        mesh.userData.veg = veg;
      }
    },

    /* 植被：草丛 + 树（照搬 world3d 的做法） */
    _makeVegetation: function (ox, oz, cs) {
      if (this.cfg.vegDensity <= 0) return null;
      var C = this.cfg, TH = root.THREE;

      var spots = [], N = 12;
      for (var i = 0; i < N; i++) {
        for (var j = 0; j < N; j++) {
          var lx = (i / N) * cs + (Math.random() - 0.5) * (cs / N);
          var lz = (j / N) * cs + (Math.random() - 0.5) * (cs / N);
          var wx = ox + lx, wz = oz + lz;
          var h = this.heightAt(wx, wz);
          if (h < C.beachLine + 1 || h > C.treeLine) continue;
          var moist = this._fbm(wx * C.moisture, wz * C.moisture, 2);
          if (moist < 0.30) continue;
          spots.push([lx, h, lz, moist]);
        }
      }
      if (!spots.length) return null;

      var group = new TH.Group();

      var grassGeo = new TH.ConeGeometry(0.07, 0.55, 3, 1, true);
      grassGeo.translate(0, 0.5, 0);
      var grassMat = new TH.MeshStandardMaterial({ color: 0x4d7c2a, roughness: 1.0, side: TH.DoubleSide });
      var gn = Math.min(spots.length, Math.floor(spots.length * C.vegDensity));
      if (gn > 0) {
        var grass = new TH.InstancedMesh(grassGeo, grassMat, gn);
        var m4 = new TH.Matrix4(), q = new TH.Quaternion(), sc = new TH.Vector3(), tp = new TH.Vector3();
        for (var k = 0; k < gn; k++) {
          var s = spots[k % spots.length];
          var sz = 0.7 + Math.random() * 1.1;
          tp.set(s[0], s[1], s[2]);
          q.setFromEuler(new TH.Euler(0, Math.random() * Math.PI * 2, (Math.random() - 0.5) * 0.25));
          sc.set(sz, sz * (0.9 + Math.random() * 0.6), sz);
          m4.compose(tp, q, sc);
          grass.setMatrixAt(k, m4);
        }
        grass.frustumCulled = false;
        group.add(grass);
      }

      var treeN = Math.min(Math.floor(spots.length * C.treeDensity), 20);
      if (treeN > 0) {
        var trunkGeo = new TH.CylinderGeometry(0.17, 0.26, 3.4, 6);
        trunkGeo.translate(0, 1.7, 0);
        var crownGeo = new TH.ConeGeometry(1.7, 5.2, 8);
        crownGeo.translate(0, 5.2, 0);
        var trunkMat = new TH.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 1 });
        var crownMat = new TH.MeshStandardMaterial({ color: 0x2f5c22, roughness: 1 });
        var trunks = new TH.InstancedMesh(trunkGeo, trunkMat, treeN);
        var crowns = new TH.InstancedMesh(crownGeo, crownMat, treeN);
        var m42 = new TH.Matrix4(), q2 = new TH.Quaternion(), sc2 = new TH.Vector3(), tp2 = new TH.Vector3();
        for (var t = 0; t < treeN; t++) {
          var sp = spots[Math.floor(Math.random() * spots.length)];
          var s2 = 0.75 + Math.random() * 0.8;
          tp2.set(sp[0], sp[1], sp[2]);
          q2.setFromEuler(new TH.Euler(0, Math.random() * Math.PI * 2, 0));
          sc2.set(s2, s2, s2);
          m42.compose(tp2, q2, sc2);
          trunks.setMatrixAt(t, m42);
          crowns.setMatrixAt(t, m42);
        }
        trunks.frustumCulled = false; crowns.frustumCulled = false;
        group.add(trunks); group.add(crowns);
      }

      this.group.add(group);
      return group;
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
            // 先拆植被子组（InstancedMesh 也要 dispose，否则显存泄漏）
            try {
              var veg = g.userData && g.userData.veg;
              if (veg) {
                veg.traverse(function (o) {
                  if (o.geometry) o.geometry.dispose();
                  if (o.material) o.material.dispose();
                });
                this.group.remove(veg);
              }
            } catch (e) {}
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

      /* ★ 把昼夜参数同步给地形材质（日落镀金 / 岩石明暗） */
      try {
        if (this._terrainMat && this._terrainMat.uniforms) {
          var tu = this._terrainMat.uniforms;
          tu.sunDir.value.copy(dir);
          tu.time.value += dt;
          var dayT = Math.max(0, sy);
          tu.dayFactor.value = 0.10 + dayT * 0.90;
          // 雾色跟着天色：夜偏蓝黑，黄昏偏暖
          var duskT = 1 - Math.min(1, dayT * 2.2);
          tu.fogColor.value.setRGB(
            0.05 + dayT * 0.12 + duskT * 0.09,
            0.06 + dayT * 0.14 + duskT * 0.04,
            0.11 + dayT * 0.17 - duskT * 0.02
          );
        }
      } catch (e) {}

      if (this.water) {
        var wu = this.water.material.uniforms;
        wu.time.value += dt;
        wu.sunDir.value.copy(dir);
        var dayW = Math.max(0, sy);
        wu.dayFactor.value = 0.12 + dayW * 0.88;
        // 相机位置：水的菲涅尔/高光需要
        try {
          var cam = root.ARENA && ARENA.camera;
          if (cam && cam.position) wu.camPos.value.copy(cam.position);
        } catch (e) {}
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
