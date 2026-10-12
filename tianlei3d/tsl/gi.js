/* ==========================================================
   gi.js —— 只做一件事：色彩溢出（Color Bleeding）
   ----------------------------------------------------------
   不要雾、不要体积光、不要全局提亮。只让「邻居的固有色」
   通过反射率反弹到本格，再叠回画面。
     E[i] ← ρ[i] · Σ_neighbor E[j]      ← 这就是色彩溢出
   叠法：屏幕加法（screen），黑色=完全不改变原画面。
   ========================================================== */
(function (root) {
  'use strict';
  var TW = root.TileWorld;
  if (!TW) return;
  var MW = TW.MW, MH = TW.MH, at = TW.at, HEIGHT = TW.HEIGHT, T = TW.T;

  // 固有色（= 反弹时带出的颜色，色彩溢出的来源）
  function albedoOf(t) {
    switch (t) {
      case T.GRASS: case T.GRASS2: case T.FLOWER: return [0.16, 0.30, 0.10];   // 草：反绿
      case T.SAKURA: return [0.34, 0.16, 0.24];                                 // 樱花：反粉
      case T.PATH: case T.SAND: return [0.30, 0.26, 0.18];                      // 石路：暖
      case T.STONE: case T.MARBLE: case T.TILE_F: return [0.26, 0.26, 0.30];    // 石/大理石：中性
      case T.WATER: return [0.06, 0.14, 0.26];                                  // 水：反蓝
      case T.WOOD: case T.WALL_W: return [0.22, 0.13, 0.07];                    // 木：反棕
      case T.CARPET_R: return [0.30, 0.09, 0.11];                               // 红毯：反红
      case T.CARPET_B: return [0.09, 0.12, 0.30];                               // 蓝毯：反蓝
      default: return [0.18, 0.18, 0.22];
    }
  }
  // 真正的光源（灯笼/祭坛/火炉/喷泉）
  function emitOf(t) {
    switch (t) {
      case T.LAMP: return [1.00, 0.70, 0.30];
      case T.ALTAR: return [0.55, 0.34, 1.00];
      case T.FOUNTAIN: return [0.40, 0.62, 0.95];
      case T.CAULDRON: return [1.00, 0.40, 0.10];
      default: return null;
    }
  }

  var N = MW * MH;
  var E = new Float32Array(N * 3), E2 = new Float32Array(N * 3);
  var ALB = new Float32Array(N * 3), EM = new Float32Array(N * 3);
  var BLK = new Uint8Array(N);

  (function build() {
    for (var y = 0; y < MH; y++) for (var x = 0; x < MW; x++) {
      var i = y * MW + x, t = at(x, y), a = albedoOf(t), e = emitOf(t);
      ALB[i * 3] = a[0]; ALB[i * 3 + 1] = a[1]; ALB[i * 3 + 2] = a[2];
      EM[i * 3] = e ? e[0] : 0; EM[i * 3 + 1] = e ? e[1] : 0; EM[i * 3 + 2] = e ? e[2] : 0;
      BLK[i] = (HEIGHT[t] || 0) > 12 ? 1 : 0;
    }
  })();

  function step() {
    for (var i = 0; i < N; i++) {
      if (BLK[i]) continue;
      E[i * 3] += EM[i * 3] * 0.10; E[i * 3 + 1] += EM[i * 3 + 1] * 0.10; E[i * 3 + 2] += EM[i * 3 + 2] * 0.10;
    }
    var k = 0.86;
    for (var y = 1; y < MH - 1; y++) for (var x = 1; x < MW - 1; x++) {
      var i = y * MW + x;
      if (BLK[i]) { E2[i * 3] = E2[i * 3 + 1] = E2[i * 3 + 2] = 0; continue; }
      var r = 0, g = 0, b = 0, c = 0;
      for (var d = 0; d < 4; d++) {
        var j = (y + (d === 2 ? 1 : d === 3 ? -1 : 0)) * MW + (x + (d === 0 ? 1 : d === 1 ? -1 : 0));
        if (BLK[j]) continue;
        r += E[j * 3]; g += E[j * 3 + 1]; b += E[j * 3 + 2]; c++;
      }
      if (c) { r /= c; g /= c; b /= c; }
      E2[i * 3] = EM[i * 3] * 0.04 + r * ALB[i * 3] * k;
      E2[i * 3 + 1] = EM[i * 3 + 1] * 0.04 + g * ALB[i * 3 + 1] * k;
      E2[i * 3 + 2] = EM[i * 3 + 2] * 0.04 + b * ALB[i * 3 + 2] * k;
    }
    var t = E; E = E2; E2 = t;
  }

  var game = document.getElementById('cv');
  if (!game) return;
  var cv = document.createElement('canvas');
  cv.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:5;mix-blend-mode:plus-lighter;';
  document.body.appendChild(cv);
  var gl = cv.getContext('webgl2', { alpha: true, antialias: false, depth: false, premultipliedAlpha: false });
  if (!gl) { cv.remove(); return; }

  var VS = '#version 300 es\nin vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
  var FS = [
    '#version 300 es', 'precision highp float;',
    'uniform vec2 uRes; uniform vec2 uO; uniform float uKX,uKY;',
    'uniform sampler2D uGI; uniform float uK;',
    'out vec4 C;',
    'void main(){',
    '  vec2 sc=gl_FragCoord.xy; sc.y=uRes.y-sc.y;',   // ★ 同上：翻转 y，否则色彩溢出上下镜像
    '  float su=(sc.x-uO.x)/uKX, sv=(sc.y-uO.y)/uKY;',
    '  vec2 w=vec2((su+sv)*0.5,(sv-su)*0.5);',
    '  vec2 uv=(w+0.5)/vec2(' + MW + '.0,' + MH + '.0);',
    '  vec3 gi=vec3(0.0);',
    '  if(uv.x>=0.0&&uv.x<=1.0&&uv.y>=0.0&&uv.y<=1.0){ gi=texture(uGI,uv).rgb; }',
                       // 被实体挡住的格子不发光
    '  C=vec4(gi*uK,1.0);',
    '}'].join('\n');
  function sh(t, s) { var o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o);
    if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) { console.warn('gi:', gl.getShaderInfoLog(o)); return null; } return o; }
  var pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { cv.remove(); return; }
  gl.useProgram(pr);
  var bb = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, bb);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  var al = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(al); gl.vertexAttribPointer(al, 2, gl.FLOAT, false, 0, 0);
  var U = {};
  ['uRes','uO','uKX','uKY','uGI','uK'].forEach(function (n) { U[n] = gl.getUniformLocation(pr, n); });

  var tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  var data = new Uint8Array(N * 4);

  var DPR = Math.min(devicePixelRatio || 1, 1.5);
  function resize() { cv.width = (innerWidth * DPR * 0.75) | 0; cv.height = (innerHeight * DPR * 0.75) | 0; gl.viewport(0, 0, cv.width, cv.height); }
  addEventListener('resize', resize); resize();

  var it = 0, sc = 1;
  function frame() {
    if (root.GI_OFF === undefined) root.GI_OFF = false;
    cv.style.display = root.GI_OFF ? 'none' : 'block';
    if (!root.GI_OFF && (!root.ROOM || !root.ROOM.cur)) {
      if (it < 40) { for (var q = 0; q < 2; q++) { step(); it++; } }
      // 全局均值（本格"应有"的中性光照水平）
      var mr = 0, mg = 0, mb = 0, cnt = 0;
      for (var q = 0; q < N; q++) { if (BLK[q]) continue; mr += E[q*3]; mg += E[q*3+1]; mb += E[q*3+2]; cnt++; }
      if (cnt) { mr /= cnt; mg /= cnt; mb /= cnt; }
      // 偏离量：取「通道间差值」= 纯色相偏移（亮度变化不算溢出）
      for (var i = 0; i < N; i++) {
        if (BLK[i]) { data[i*4]=0; data[i*4+1]=0; data[i*4+2]=0; data[i*4+3]=255; continue; }
        var r = E[i*3], g = E[i*3+1], b = E[i*3+2];
        var avg = (r + g + b) / 3;
        // 相对均值的色偏（正=该通道偏强）。只留正偏移 = "被邻居染上的颜色"
        var dr = Math.max(0, (r - avg) - 0.05), dg = Math.max(0, (g - avg) - 0.05), db = Math.max(0, (b - avg) - 0.05);
        var mx = Math.max(dr, Math.max(dg, db));
        if (mx <= 0.055) { data[i*4]=0; data[i*4+1]=0; data[i*4+2]=0; data[i*4+3]=0; continue; }  // ★ 阈值：平色不出
        var amt = Math.min(1.0, (mx - 0.055) * 3.0) * 0.30;   // 弱偏移→弱显示
        data[i*4]   = Math.min(255, (dr/mx) * amt * 255);
        data[i*4+1] = Math.min(255, (dg/mx) * amt * 255);
        data[i*4+2] = Math.min(255, (db/mx) * amt * 255);
        data[i*4+3] = 0;
      }
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, MW, MH, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
      sc = cv.width / (innerWidth || 1);
      gl.uniform2f(U.uRes, cv.width, cv.height);
      gl.uniform2f(U.uO, ((innerWidth / 2) - (root.__camX || 0)) * sc, ((innerHeight / 2) - (root.__camY || 0)) * sc);
      gl.uniform1f(U.uKX, TW.TW / 2 * sc);
      gl.uniform1f(U.uKY, TW.TH / 2 * sc);
      gl.uniform1f(U.uK, 0.30);                 // 溢出强度（唯一可调）
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex); gl.uniform1i(U.uGI, 0);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  root.GI = { field: function () { return E; }, iters: function () { return it; }, reset: function () { it = 0; } };
})(window);
