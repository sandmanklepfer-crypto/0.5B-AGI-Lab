/* ============================================================================
 *  sky.js —— 天泪纪元 · 真正的天空（蓝天白云 + 昼夜）
 *  --------------------------------------------------------------------------
 *  为什么单独做一个文件
 *    之前的「世界之外」(wildlands.js) 把地形/水/植被/天空 + 地面碰撞接管
 *    全塞在一起。结果：地形污染了主城逻辑（走不出去、深水挡路、只看见海），
 *    而真正想要的「天空」反而被埋在里面、还被黄昏色调压暗，等于没有。
 *
 *    这个文件只做一件事：**在天上放一个漂亮的天**。
 *      · 完全不碰地面高度与行走判定   → 绝不影响行走与碰撞
 *      · 不生成任何地形/水/植被       → 绝不影响性能与画面主体
 *      · 只加一个 Background 天空球 + 自然光，随时可一键关掉
 *
 *  效果
 *    · 蓝天渐变（天顶深蓝 → 地平线浅青白）
 *    · 程序化白云（fbm 流动，随时间飘）
 *    · 太阳/月亮（按时间走，带光晕）
 *    · 星空（夜里浮现）
 *    · 昼夜循环：清晨金 → 白天蓝 → 黄昏橙 → 夜里深蓝
 *
 *  用法
 *    Sky.init()               // 自动挂载（有 ARENA.scene 时）
 *    Sky.setEnabled(true/false)
 *    Sky.setTime(0..1)        // 0.25=正午 0.5=日落 0.75=午夜 0=日出
 *    Sky.setCycle(true/false) // 昼夜自动走
 *
 *  依赖：THREE + ARENA.scene（可选）。没有 ARENA 也能独立跑（单测用）
 * ========================================================================== */
(function (root) {
  'use strict';
  if (!root.THREE) return;

  var S = {
    cfg: {
      radius: 1600,          // 天空球半径（比地形远，比相机远裁略小）
      time: 0.25,            // 0.25 = 正午（默认给白天，别一进来就黄昏）
      cycleSpeed: 0.0016,    // 一圈约 10 分钟；0 = 静止
      cycle: true,
      clouds: 0.75,          // 云量 0~1
      stars: 1.0,            // 星空强度
      sunSize: 220.0         // 太阳光斑锐度（越大越小）
    },

    inited: false,
    enabled: true,
    scene: null,
    group: null,
    mesh: null,
    mat: null,
    sunLight: null,
    hemi: null,
    _t: 0.25,
    _accum: 0,

    /* ------------------------------------------------------------------ */
    /*  天空球 shader                                                     */
    /* ------------------------------------------------------------------ */
    _buildMaterial: function () {
      return new THREE.ShaderMaterial({
        side: THREE.BackSide,
        depthWrite: false,
        depthTest: false,
        fog: false,
        uniforms: {
          uTime: { value: 0 },
          uDay: { value: 1.0 },              // 0=夜 1=正午
          uSunDir: { value: new THREE.Vector3(0.3, 0.9, 0.2) },
          uCloud: { value: 0.75 },
          uStars: { value: 1.0 },
          uSunSize: { value: 220.0 },
          // 三个色带会随昼夜插值
          uZenith: { value: new THREE.Color(0x2f6fd0) },   // 天顶
          uMid: { value: new THREE.Color(0x87b7e8) },      // 中天
          uHorizon: { value: new THREE.Color(0xd9e9f7) },  // 地平线
          uSunTint: { value: new THREE.Color(0xfff6e0) }
        },
        vertexShader: [
          'varying vec3 vDir;',
          'void main(){',
          '  vDir = normalize(position);',
          '  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);',
          '}'
        ].join('\n'),
        fragmentShader: [
          'precision highp float;',
          'varying vec3 vDir;',
          'uniform float uTime, uDay, uCloud, uStars, uSunSize;',
          'uniform vec3 uSunDir, uZenith, uMid, uHorizon, uSunTint;',

          'float hash21(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }',
          'float vnoise(vec2 p){',
          '  vec2 i = floor(p), f = fract(p);',
          '  f = f * f * (3.0 - 2.0 * f);',
          '  float a = hash21(i);',
          '  float b = hash21(i + vec2(1.0, 0.0));',
          '  float c = hash21(i + vec2(0.0, 1.0));',
          '  float d = hash21(i + vec2(1.0, 1.0));',
          '  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);',
          '}',
          'float fbm(vec2 p){',
          '  float s = 0.0, a = 0.5;',
          '  for (int i = 0; i < 5; i++) { s += a * vnoise(p); p *= 2.03; a *= 0.5; }',
          '  return s;',
          '}',

          'void main(){',
          '  vec3 d = normalize(vDir);',
          '  float h = clamp(d.y, -0.15, 1.0);',           // -1..1 → 用地平线附近做过渡

          /* ---- 天空渐变：地平线 → 中天 → 天顶 ---- */
          '  float t1 = smoothstep(-0.05, 0.30, h);',
          '  float t2 = smoothstep(0.25, 0.85, h);',
          '  vec3 col = mix(uHorizon, uMid, t1);',
          '  col = mix(col, uZenith, t2);',

          /* ---- 太阳 / 月亮 ---- */
          '  vec3 L = normalize(uSunDir);',
          '  float sd = max(dot(d, L), 0.0);',
          '  float disc = pow(sd, uSunSize);',              // 日面（锐）
          '  float halo = pow(sd, 8.0);',                   // 光晕（柔）
          '  col += uSunTint * disc * 3.0;',
          '  col += uSunTint * halo * 0.35;',

          /* ---- 星空：只在上半球，夜里才亮 ---- */
          '  float night = clamp(1.0 - uDay * 1.6, 0.0, 1.0);',
          '  if (night > 0.01 && d.y > 0.02) {',
          '    vec2 sp = d.xz / max(d.y, 0.08) * 24.0;',
          '    float st = hash21(floor(sp));',
          '    float twinkle = 0.75 + 0.25 * sin(uTime * 2.5 + st * 40.0);',
          '    float star = smoothstep(0.995, 1.0, st) * twinkle;',
          '    col += vec3(1.0, 0.98, 0.92) * star * night * uStars * 1.6;',
          '  }',

          /* ---- 云：两层 fbm 叠加 + 随时间飘 ---- */
          '  if (d.y > 0.015) {',
          '    vec2 uv = d.xz / max(d.y, 0.10) * 0.55;',
          '    vec2 drift = vec2(uTime * 0.010, uTime * 0.004);',
          '    float c1 = fbm(uv * 1.0 + drift);',
          '    float c2 = fbm(uv * 2.4 - drift * 1.7 + 11.3);',
          '    float c = c1 * 0.68 + c2 * 0.32;',
          '    float mask = smoothstep(0.015, 0.30, d.y);',   // 地平线附近淡出
          '    float cover = smoothstep(0.46, 0.86, c) * mask * uCloud;',
          // 云的颜色：白天纯白偏暖，夜里变暗灰蓝
          '    vec3 cloudLit = mix(vec3(0.30, 0.34, 0.42), vec3(1.0, 0.99, 0.97), uDay);',
          '    vec3 cloudShade = mix(vec3(0.16, 0.19, 0.28), vec3(0.72, 0.77, 0.86), uDay);',
          '    vec3 cloudCol = mix(cloudShade, cloudLit, smoothstep(0.35, 0.95, c));',
          // 云被夕阳染暖
          '    float warm = (1.0 - uDay) * halo;',
          '    cloudCol = mix(cloudCol, vec3(1.0, 0.72, 0.48), warm * 0.55);',
          '    col = mix(col, cloudCol, cover * 0.90);',
          '  }',

          /* ---- 地平线以下：压暗，避免"球底露馅" ---- */
          '  float below = smoothstep(0.0, -0.16, h);',
          '  col = mix(col, col * 0.35, below);',

          '  gl_FragColor = vec4(col, 1.0);',
          '}'
        ].join('\n')
      });
    },

    /* ------------------------------------------------------------------ */
    /*  昼夜曲线：返回该时刻的天色                               */
    /* ------------------------------------------------------------------ */
    _palette: function (t) {
      // t: 0=日出 0.25=正午 0.5=日落 0.75=午夜
      /* ★ 必须保留负值：Math.max(0,sin) 会让黄昏(0.5)与午夜(0.75)都变成 0，
         两者天空一模一样，夜里根本不黑。 */
      var day = Math.sin(t * Math.PI * 2);        // -1=午夜 0=地平线 +1=正午
      var dayPos = Math.max(0, day);              // 亮度只用正值

      // 白天 ↔ 夜里的三个色带
      var zenithDay = [0x2f6fd0, 0x87b7e8, 0xd9e9f7];     // 天顶/中天/地平（白天）
      var zenithNight = [0x02030a, 0x03060f, 0x0a1120];   // 夜里（压得更暗）
      var zenithDusk = [0x27407a, 0x8a5f7a, 0xf0a06a];    // 黄昏

      // 权重：白天日高时偏白蓝，地平线附近偏橙
      var duskW = Math.max(0, 1 - Math.abs(day) * 3.2);        // 只在日出/日落附近有
      var dayW = Math.pow(dayPos, 1.35);   // 指数>1 → 地平线附近过渡更缓，日出日落有层次
      var nightW = Math.pow(Math.max(0, -day), 1.2) * 1.0;     // 权重归一到 0~1，避免压过 dayW
      var ambientW = dayPos < 0.02 ? 0.35 : 0;                 // 夜里留一点环境光，不至于全黑

      function mix3(a, b, c, wa, wb, wc) {
        var s = wa + wb + wc || 1;
        return [
          (a[0] * wa + b[0] * wb + c[0] * wc) / s,
          (a[1] * wa + b[1] * wb + c[1] * wc) / s,
          (a[2] * wa + b[2] * wb + c[2] * wc) / s
        ];
      }
      function hex2rgb(h) {
        return [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255];
      }

      var zN = hex2rgb(zenithNight[0]), zD = hex2rgb(zenithDay[0]), zK = hex2rgb(zenithDusk[0]);
      var mN = hex2rgb(zenithNight[1]), mD = hex2rgb(zenithDay[1]), mK = hex2rgb(zenithDusk[1]);
      // 夜里给中天一点点蓝，避免死黑
      mN = [mN[0] + ambientW * 0.06, mN[1] + ambientW * 0.10, mN[2] + ambientW * 0.22];
      var hN = hex2rgb(zenithNight[2]), hD = hex2rgb(zenithDay[2]), hK = hex2rgb(zenithDusk[2]);

      return {
        day: dayPos,
        rawDay: day,
        zenith: mix3(zN, zD, zK, nightW, dayW, duskW),
        mid: mix3(mN, mD, mK, nightW, dayW, duskW),
        horizon: mix3(hN, hD, hK, nightW, dayW, duskW)
      };
    },

    /* 太阳方向：绕一圈 */
    _sunDir: function (t) {
      var ang = t * Math.PI * 2;
      var y = Math.sin(ang);
      var x = Math.cos(ang) * 0.55;
      var z = Math.cos(ang) * 0.30 + 0.25;
      var v = new THREE.Vector3(x, y, z);
      return v.normalize();
    },

    /* ------------------------------------------------------------------ */
    /*  初始化                                                           */
    /* ------------------------------------------------------------------ */
    init: function (scene) {
      if (this.inited) return this;
      scene = scene || (root.ARENA && root.ARENA.scene);
      if (!scene) return this;

      this.scene = scene;
      this.group = new THREE.Group();
      this.group.name = 'tlsky';
      scene.add(this.group);

      this.mat = this._buildMaterial();
      var geo = new THREE.SphereGeometry(this.cfg.radius, 32, 20);
      this.mesh = new THREE.Mesh(geo, this.mat);
      this.mesh.frustumCulled = false;
      this.mesh.renderOrder = -10000;         // 永远最先画
      this.group.add(this.mesh);

      // 光：一个方向光（太阳）+ 半球光（天光），只做视觉，不影响玩法碰撞
      this.sunLight = new THREE.DirectionalLight(0xfff3e0, 1.0);
      this.sunLight.castShadow = false;       // 主城原有阴影系统不动
      this.group.add(this.sunLight);

      this.hemi = new THREE.HemisphereLight(0xa8c8ee, 0x2a2b30, 0.55);
      this.group.add(this.hemi);

      this._t = this.cfg.time;
      this.inited = true;
      this.apply();
      try { console.log('[sky] 天空已启用（纯视觉，不接触任何玩法逻辑）'); } catch (e) {}
      return this;
    },

    /* ------------------------------------------------------------------ */
    /*  应用参数                                                         */
    /* ------------------------------------------------------------------ */
    apply: function () {
      if (!this.inited) return;
      var u = this.mat.uniforms;
      var t = this._t;
      var dir = this._sunDir(t);
      var pal = this._palette(t);

      u.uSunDir.value.copy(dir);
      u.uDay.value = Math.max(0.02, Math.min(1, pal.day * 1.15));
      u.uZenith.value.setRGB(pal.zenith[0], pal.zenith[1], pal.zenith[2]);
      u.uMid.value.setRGB(pal.mid[0], pal.mid[1], pal.mid[2]);
      u.uHorizon.value.setRGB(pal.horizon[0], pal.horizon[1], pal.horizon[2]);
      u.uCloud.value = this.cfg.clouds;
      u.uStars.value = this.cfg.stars;
      u.uSunSize.value = this.cfg.sunSize;

      // 太阳颜色：正午白 → 地平线橙
      var warm = Math.max(0, 1 - Math.abs(pal.day) * 2.6);
      u.uSunTint.value.setRGB(1.0, 0.98 - warm * 0.30, 0.92 - warm * 0.55);

      if (this.sunLight) {
        this.sunLight.position.copy(dir).multiplyScalar(600);
        this.sunLight.intensity = 0.08 + Math.max(0, pal.day) * 1.15;
        this.sunLight.color.setRGB(1.0, 0.97 - warm * 0.22, 0.92 - warm * 0.42);
      }
      if (this.hemi) {
        this.hemi.intensity = 0.16 + Math.max(0, pal.day) * 0.62;
        this.hemi.color.setRGB(
          0.30 + pal.day * 0.42,
          0.36 + pal.day * 0.42,
          0.48 + pal.day * 0.36
        );
      }
    },

    /* ------------------------------------------------------------------ */
    /*  每帧                                                             */
    /* ------------------------------------------------------------------ */
    update: function (dt, px, pz) {
      if (!this.inited || !this.enabled) return;
      this._accum += dt;

      if (this.cfg.cycle) {
        this._t = (this._t + dt * this.cfg.cycleSpeed) % 1;
        this.apply();
      }
      this.mat.uniforms.uTime.value = this._accum;

      // 跟随玩家：天空球永远在"最远处"
      if (this.mesh) {
        this.mesh.position.set(px || 0, 0, pz || 0);
      }
    },

    /* ------------------------------------------------------------------ */
    /*  对外控制                                                         */
    /* ------------------------------------------------------------------ */
    setEnabled: function (on) {
      this.enabled = !!on;
      if (this.group) this.group.visible = this.enabled;
      return this.enabled;
    },
    setTime: function (t) {
      this._t = ((t % 1) + 1) % 1;
      this.apply();
      return this._t;
    },
    getTime: function () { return this._t; },
    setCycle: function (on) {
      this.cfg.cycle = !!on;
      return this.cfg.cycle;
    },
    setClouds: function (v) {
      this.cfg.clouds = Math.max(0, Math.min(1, v));
      this.apply();
      return this.cfg.clouds;
    },
    /* 给 UI 一个"几点"的可读文本 */
    clock: function () {
      var hh = (this._t * 24 + 6) % 24;      // t=0 → 6:00（日出）
      var h = Math.floor(hh), m = Math.floor((hh - h) * 60);
      return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
    },
    phaseName: function () {
      var t = this._t, d = Math.sin(t * Math.PI * 2);
      if (d > 0.75) return '正午';
      if (d > 0.25) return '白天';
      if (d > 0.02) return '清晨 / 黄昏';
      if (d > -0.25) return '黄昏';
      return '夜';
    }
  };

  root.Sky = S;

  /* ---- 自动挂载 ---- */
  function boot() {
    if (!root.ARENA || !root.ARENA.scene) { setTimeout(boot, 500); return; }
    try { S.init(); } catch (e) { try { console.log('[sky] 启动失败', e); } catch (_) {} }
  }
  if (root.ARENA && root.ARENA.scene) setTimeout(boot, 0);
  else setTimeout(boot, 600);

})(typeof self !== 'undefined' ? self : this);
