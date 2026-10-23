/* ==========================================================================
   shooter.js —— 天泪纪元 · 3D 多人枪战（HD-2D 表现 / 沥青都市场景 / 自由视角）
   --------------------------------------------------------------------------
   场景：arena3d.js 提供的「雨夜沥青都市」（真立体高度场，可自由旋转视角）
   表现：HD-2D —— 2D 立绘角色/怪物公告板 + 泛光 Bloom + 移轴景深 Tilt-Shift + 青橙调色
   玩法：枪战手感(射线命中/后坐力/弹道/爆头/开镜/手雷/换弹) + 多人联机(公共 MQTT 房间)
   依赖：arena3d.js(ARENA) / mqtt.js(MiniMqtt)
   ========================================================================== */
(function () {
'use strict';
if (window.SHOOTER) return;
try {
if (typeof THREE === 'undefined' || !window.ARENA) {
  window.__serr = 'ARENA 未就绪：' + String(window.__aerr || '(arena3d 无错误上报)');
  try { console.error('[shooter]', window.__serr); } catch (e) {}
  return;   // ★ 不清空 body（否则 kernel.js 一起没了，无法诊断）
}
var A = window.ARENA, G = A.Ground, TILE = A.TILE;
var HOST = !!window.__HD2D_HOST;   // ★ 宿主模式：世界/循环/相机/渲染 交给 HD-2D 页，本模块只跑战斗逻辑
var actionScene = A.scene, renderer = A.renderer;
function cam() { try { var c = A.getCam(); return (c && c.isCamera) ? c : A.camera; } catch (e) { return A.camera; } }   // 兜底：永远有效                       // ★ 当前相机（HD-2D 正交 / 透视）
function billboardYaw(x, z) {                               // 立绘朝向：HD-2D 锁 45°；透视面向相机
  if (A.getCamMode() === 'hd2d') return Math.atan2(-A.CAM_DIR.x, -A.CAM_DIR.z);
  return Math.atan2(cam().position.x - x, cam().position.z - z);
}

var clamp = function (v, a, b) { return v < a ? a : (v > b ? b : v); };
var lerp = function (a, b, t) { return a + (b - a) * t; };
var rnd = function (a, b) { return a + Math.random() * (b - a); };
var norm360 = function (a) { a %= 360; return a < 0 ? a + 360 : a; };
var _dummy = { style: {}, classList: { add: function () {}, remove: function () {}, toggle: function () {} }, textContent: '', innerHTML: '', appendChild: function () {}, removeChild: function () {}, querySelector: function () { return _dummy; }, addEventListener: function () {}, children: [], value: '', display: '', getBoundingClientRect: function () { return { left: 0, top: 0, width: 0, height: 0, right: 0, bottom: 0 }; } };
var $ = function (id) { return document.getElementById(id) || _dummy; };
/* ★ 空安全 DOM 操作（元素缺失只跳过，绝不因 null.addEventListener 崩掉整脚本） */
var _on = function (id, ev, fn) { var e = $(id); if (e) e.addEventListener(ev, fn); };
var _txt = function (id, t) { var e = $(id); if (e) e.textContent = t; };
var _cls = function (id, c) { var e = $(id); if (e) e.className = c; };
var V3 = function (x, y, z) { return new THREE.Vector3(x, y, z); };
var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]; }); };
/* ★ 沙盒 / 战斗 两套玩法共存：
   sandbox=true  → 不刷怪、不出 Boss、不打玩家伤害。世界是你的，建造/探索/联机闲聊为主。
   sandbox=false → 原来的 PVE/PVP 射击场。 */
var SANDBOX = true;
var VERSION = '1.4.0';                                   // ★ 语义化版本（与 APK versionName 同步）
var BUILD = VERSION + ' · ' + Date.now().toString(36).slice(-5);   // 版本 + 构建号（界面可见）

/* ============================== 音效（纯合成） ============================== */
var Sfx = {
  ctx: null, master: null, sfxBus: null, musicBus: null, comp: null, on: true,
  vol: 1.0,   // ★ 音效音量（0~1.5）
  init: function () {
    if (this.ctx) return; var AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    try { this.ctx = new AC(); } catch (e) { return; }
    // ★ 母线：压缩器防爆音 + 总增益拉高（原来 0.5 太小）
    this.master = this.ctx.createGain(); this.master.gain.value = 1.0;
    try {
      this.comp = this.ctx.createDynamicsCompressor();
      this.comp.threshold.value = -6; this.comp.knee.value = 12; this.comp.ratio.value = 4;
      this.comp.attack.value = 0.003; this.comp.release.value = 0.25;
      this.master.connect(this.comp); this.comp.connect(this.ctx.destination);
    } catch (e) { this.master.connect(this.ctx.destination); }
    this.sfxBus = this.ctx.createGain(); this.sfxBus.gain.value = this.vol; this.sfxBus.connect(this.master);
    this.musicBus = this.ctx.createGain(); this.musicBus.gain.value = 0.85 * this.vol; this.musicBus.connect(this.master);
  },
  resume: function () { this.init(); if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); },
  _noise: function (dur) {
    var sr = this.ctx.sampleRate, n = Math.max(1, Math.floor(sr * dur)), buf = this.ctx.createBuffer(1, n, sr), d = buf.getChannelData(0);
    for (var i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    var s = this.ctx.createBufferSource(); s.buffer = buf; return s;
  },
  setVol: function (v) { this.vol = Math.max(0, Math.min(2.8, v)); if (this.sfxBus) this.sfxBus.gain.value = this.vol; if (this.musicBus) this.musicBus.gain.value = 0.85 * this.vol; },
  gun: function (kind, dist) {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, g = this.ctx.createGain(), f = this.ctx.createBiquadFilter();
    var vol = (dist === undefined ? 1 : clamp(1 - dist / 80, 0.05, 1)) * 1.0;
    var cfg = { rifle: [1100, 0.055, 190, 0.16], smg: [1500, 0.035, 320, 0.10], shotgun: [700, 0.13, 120, 0.30], sniper: [520, 0.30, 90, 0.34],
      missile: [900, 0.22, 120, 0.42], minigun: [1600, 0.03, 420, 0.09], gl: [560, 0.20, 110, 0.38] }[kind] || [1000, 0.07, 180, 0.18];
    f.type = 'lowpass'; f.frequency.setValueAtTime(cfg[0], t); f.frequency.exponentialRampToValueAtTime(cfg[2], t + cfg[1]);
    var n = this._noise(cfg[3]); n.connect(f); f.connect(g); g.connect(this.sfxBus);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + 0.004); g.gain.exponentialRampToValueAtTime(0.0001, t + cfg[3]);
    n.start(t); n.stop(t + cfg[3] + 0.02);
    var o = this.ctx.createOscillator(), og = this.ctx.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(cfg[1] > 0.1 ? 150 : 220, t); o.frequency.exponentialRampToValueAtTime(48, t + 0.12);
    og.gain.setValueAtTime(vol * 0.7, t); og.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
    o.connect(og); og.connect(this.sfxBus); o.start(t); o.stop(t + 0.16);
  },
  tick: function (freq, dur, vol, type) {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = type || 'square'; o.frequency.value = freq || 1200;
    g.gain.setValueAtTime(vol === undefined ? 0.28 : vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + (dur || 0.06));
    o.connect(g); g.connect(this.sfxBus); o.start(t); o.stop(t + (dur || 0.06) + 0.02);
  },
  hit: function (crit) { this.tick(crit ? 1900 : 1350, crit ? 0.09 : 0.055, crit ? 0.34 : 0.24, 'triangle'); },
  hurt: function () { this.tick(180, 0.22, 0.36, 'sawtooth'); },
  reload: function () { var s = this; this.tick(320, 0.05, 0.24, 'square'); setTimeout(function () { s.tick(210, 0.06, 0.22, 'square'); }, 160); },
  empty: function () { this.tick(260, 0.04, 0.18, 'square'); },
  boom: function () {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, n = this._noise(0.7), f = this.ctx.createBiquadFilter(), g = this.ctx.createGain();
    f.type = 'lowpass'; f.frequency.setValueAtTime(700, t); f.frequency.exponentialRampToValueAtTime(70, t + 0.6);
    n.connect(f); f.connect(g); g.connect(this.sfxBus);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(1.0, t + 0.01); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.7);
    n.start(t); n.stop(t + 0.72);
  },
  /* ---- ★ 新增音效（原来只有 6 种，太单调） ---- */
  step: function (run) {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, n = this._noise(0.07), f = this.ctx.createBiquadFilter(), g = this.ctx.createGain();
    f.type = 'bandpass'; f.frequency.value = run ? 1500 : 1050; f.Q.value = 1.1;
    n.connect(f); f.connect(g); g.connect(this.sfxBus);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(run ? 0.16 : 0.11, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.07);
    n.start(t); n.stop(t + 0.09);
  },
  jump: function () {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(240, t); o.frequency.exponentialRampToValueAtTime(620, t + 0.11);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.22, t + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
    o.connect(g); g.connect(this.sfxBus); o.start(t); o.stop(t + 0.15);
  },
  land: function () {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, n = this._noise(0.12), f = this.ctx.createBiquadFilter(), g = this.ctx.createGain();
    f.type = 'lowpass'; f.frequency.setValueAtTime(520, t); f.frequency.exponentialRampToValueAtTime(120, t + 0.1);
    n.connect(f); f.connect(g); g.connect(this.sfxBus);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.32, t + 0.006); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.13);
    n.start(t); n.stop(t + 0.15);
  },
  kill: function () {   // ★ 击杀确认（双音上行）
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, s = this;
    [[880, 0], [1320, 0.075]].forEach(function (p) {
      var o = s.ctx.createOscillator(), g = s.ctx.createGain();
      o.type = 'triangle'; o.frequency.value = p[0];
      g.gain.setValueAtTime(0.0001, t + p[1]); g.gain.exponentialRampToValueAtTime(0.26, t + p[1] + 0.008);
      g.gain.exponentialRampToValueAtTime(0.0001, t + p[1] + 0.16);
      o.connect(g); g.connect(s.sfxBus); o.start(t + p[1]); o.stop(t + p[1] + 0.18);
    });
  },
  waveUp: function () {  // ★ 波次提升（和弦上行）
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, s = this;
    [392, 523, 659, 784].forEach(function (fq, i) {
      var o = s.ctx.createOscillator(), g = s.ctx.createGain();
      o.type = 'sawtooth'; o.frequency.value = fq;
      var f = s.ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 2200;
      g.gain.setValueAtTime(0.0001, t + i * 0.09); g.gain.exponentialRampToValueAtTime(0.2, t + i * 0.09 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.09 + 0.45);
      o.connect(f); f.connect(g); g.connect(s.sfxBus); o.start(t + i * 0.09); o.stop(t + i * 0.09 + 0.48);
    });
  },
  ui: function () { this.tick(880, 0.035, 0.16, 'triangle'); },
  deny: function () { this.tick(160, 0.12, 0.2, 'sawtooth'); },
  pickup: function () { this.tick(1180, 0.06, 0.2, 'triangle'); setTimeout(function () { Sfx.tick(1560, 0.08, 0.18, 'triangle'); }, 70); },
  growl: function (pitch) {
    if (!this.on) return; this.init(); if (!this.ctx) return;
    var t = this.ctx.currentTime, o = this.ctx.createOscillator(), g = this.ctx.createGain(), f = this.ctx.createBiquadFilter();
    o.type = 'sawtooth'; o.frequency.setValueAtTime(pitch || 90, t); o.frequency.exponentialRampToValueAtTime((pitch || 90) * 0.6, t + 0.5);
    f.type = 'lowpass'; f.frequency.value = 500;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.34, t + 0.08); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
    o.connect(f); f.connect(g); g.connect(this.sfxBus); o.start(t); o.stop(t + 0.62);
  },
};

/* ============================== ★ 背景音乐（程序化合成 · 免外部文件） ============================== */
/* ★★ 钢琴（FL Studio Steinway 采样 → 走近可弹）★★
   4 个采样(C1~C4) + playbackRate 变调 → 整台钢琴音域；纯本地，0 流量。 */
var Piano = {
  NOTES: { C1: 32.70, C2: 65.41, C3: 130.81, C4: 261.63 },
  bufs: {}, ready: false, _load: false, playing: false, near: false,
  load: function () {
    if (this._load) return; this._load = true;
    var self = this;
    Object.keys(this.NOTES).forEach(function (k) {
      try {
        fetch('assets/audio/piano/piano_' + k + '.wav').then(function (r) { return r.arrayBuffer(); })
          .then(function (ab) { return Sfx.ctx.decodeAudioData(ab); })
          .then(function (b) { self.bufs[k] = b; self.ready = true; }).catch(function () {});
      } catch (e) {}
    });
  },
  note: function (midi, when, vol) {
    if (!Sfx.ctx || !this.ready) return;
    var f = 440 * Math.pow(2, (midi - 69) / 12), best = 'C4', bd = 1e9;
    for (var k in this.NOTES) { var d = Math.abs(Math.log2(f / this.NOTES[k])); if (d < bd) { bd = d; best = k; } }
    var buf = this.bufs[best]; if (!buf) return;
    var src = Sfx.ctx.createBufferSource(); src.buffer = buf;
    src.playbackRate.value = f / this.NOTES[best];
    var g = Sfx.ctx.createGain(); g.gain.value = vol || 0.55;
    src.connect(g); g.connect(Sfx.musicBus || Sfx.master);
    src.start(when || Sfx.ctx.currentTime);
  },
  // 一小段"雨夜圆舞曲"（自己写的，无版权）
  MEL: [[64,.0],[67,.5],[71,1.0],[72,1.5],[71,2.0],[67,2.5],[64,3.0],
        [62,3.5],[65,4.0],[69,4.5],[71,5.0],[69,5.5],[65,6.0],[62,6.5],
        [60,7.0],[64,7.5],[67,8.0],[72,8.5],[71,9.0],[67,9.5],[64,10.0]],
  play: function () {
    if (!Sfx.ctx) return;
    Sfx.resume(); this.load();
    var self = this, t0 = Sfx.ctx.currentTime + 0.06;
    this.MEL.forEach(function (n) { self.note(n[0], t0 + n[1], 0.5); });
    // 低音铺底
    [[48,0],[45,3.5],[43,7.0],[41,10.0]].forEach(function (n) { self.note(n[0], t0 + n[1], 0.3); });
    this.playing = true;
    HUD.center('🎹 琴声在雨夜里荡开', '靠近再来一曲 · 服务端零流量', 2600);
  },
};

/* ★ 音量档位：中 / 大 / 超大 / 爆表（整体增益，音乐+音效一起） */
Sfx.VOL_STEPS = [1.0, 1.4, 2.0, 2.6];
Sfx.VOL_NAMES = ['中', '大', '超大', '爆表'];
Sfx.volIdx = 1;
Sfx.applyVol = function () {
  this.setVol(this.VOL_STEPS[this.volIdx]);
  var b = document.getElementById('bVol');
  if (b) { b.textContent = '音量:' + this.VOL_NAMES[this.volIdx]; b.className = this.volIdx > 0 ? 'on' : ''; }
};

var Music = {
  on: false, timer: null, nextT: 0, bar: 0,
  // Am - F - C - G 循环，暗色调，贴合"雨夜诡都"
  prog: [[220.00, 261.63, 329.63], [174.61, 220.00, 261.63], [261.63, 329.63, 392.00], [196.00, 246.94, 293.66]],
  BAR: 2.4,
  start: function () {
    if (this.on) return; Sfx.init(); if (!Sfx.ctx) return;
    this.on = true; this.nextT = Sfx.ctx.currentTime + 0.12; this.bar = 0;
    var self = this;
    this.timer = setInterval(function () { self.schedule(); }, 200);
    this.schedule();
  },
  stop: function () { this.on = false; if (this.timer) { clearInterval(this.timer); this.timer = null; } },
  toggle: function () { if (this.on) { this.stop(); } else { Sfx.resume(); this.start(); } return this.on; },
  schedule: function () {
    if (!this.on || !Sfx.ctx) return;
    var now = Sfx.ctx.currentTime;
    while (this.nextT < now + 1.0) { this.playBar(this.nextT, this.bar); this.nextT += this.BAR; this.bar++; }
  },
  playBar: function (t0, bar) {
    var self = this, ctx = Sfx.ctx, bus = Sfx.musicBus;
    var ch = this.prog[bar % 4];
    // pad：三音铺底，慢起慢落
    ch.forEach(function (f, i) {
      var o = ctx.createOscillator(), g = ctx.createGain(), fl = ctx.createBiquadFilter();
      o.type = 'sawtooth'; o.frequency.value = f / 2; o.detune.value = (i - 1) * 6;
      fl.type = 'lowpass'; fl.frequency.setValueAtTime(420, t0); fl.frequency.linearRampToValueAtTime(760, t0 + self.BAR * 0.6);
      g.gain.setValueAtTime(0.0001, t0); g.gain.linearRampToValueAtTime(0.18, t0 + 0.7);
      g.gain.linearRampToValueAtTime(0.0001, t0 + self.BAR);
      o.connect(fl); fl.connect(g); g.connect(bus); o.start(t0); o.stop(t0 + self.BAR + 0.05);
    });
    // bass：根音
    var bo = ctx.createOscillator(), bg = ctx.createGain();
    bo.type = 'triangle'; bo.frequency.value = ch[0] / 4;
    bg.gain.setValueAtTime(0.0001, t0); bg.gain.linearRampToValueAtTime(0.30, t0 + 0.06);
    bg.gain.exponentialRampToValueAtTime(0.0001, t0 + self.BAR * 0.95);
    bo.connect(bg); bg.connect(bus); bo.start(t0); bo.stop(t0 + self.BAR);
    // 鼓：kick 1/3 拍，snare 2/4 拍，hat 8 分
    var beat = self.BAR / 4;
    for (var b = 0; b < 4; b++) {
      var tb = t0 + b * beat;
      if (b % 2 === 0) {   // kick
        var ko = ctx.createOscillator(), kg = ctx.createGain();
        ko.type = 'sine'; ko.frequency.setValueAtTime(150, tb); ko.frequency.exponentialRampToValueAtTime(42, tb + 0.11);
        kg.gain.setValueAtTime(0.50, tb); kg.gain.exponentialRampToValueAtTime(0.0001, tb + 0.16);
        ko.connect(kg); kg.connect(bus); ko.start(tb); ko.stop(tb + 0.18);
      } else {             // snare
        var sn = Sfx._noise(0.13), sf = ctx.createBiquadFilter(), sg = ctx.createGain();
        sf.type = 'highpass'; sf.frequency.value = 1400;
        sn.connect(sf); sf.connect(sg); sg.connect(bus);
        sg.gain.setValueAtTime(0.26, tb); sg.gain.exponentialRampToValueAtTime(0.0001, tb + 0.13);
        sn.start(tb); sn.stop(tb + 0.15);
      }
      for (var h = 0; h < 2; h++) {   // hat
        var ht = tb + h * beat / 2, hn = Sfx._noise(0.03), hf = ctx.createBiquadFilter(), hg = ctx.createGain();
        hf.type = 'highpass'; hf.frequency.value = 7000;
        hn.connect(hf); hf.connect(hg); hg.connect(bus);
        hg.gain.setValueAtTime(h * 0.08 + 0.05, ht); hg.gain.exponentialRampToValueAtTime(0.0001, ht + 0.03);
        hn.start(ht); hn.stop(ht + 0.04);
      }
    }
  },
};

/* ============================== ★ 语音（真麦克风 / 无权限时降级为快捷语音） ============================== */
var Voice = {
  hasMic: null, rec: null, chunks: [], t0: 0, stream: null,
  PHRASES: ['集合！', '小心 Boss！', '跟我来', '掩护我', '缺弹药', '撤！', '好球！', '救命'],
  _getMic: function (cb) {
    var self = this;
    var st = this.stream;
    if (st && st.getAudioTracks().some(function (t) { return t.readyState === 'live'; })) { cb(st); return; }
    this.stream = null;
    // ★ WebView 二次 getUserMedia 会挂起 → 一次性拿到后长期复用
    var to = setTimeout(function () { self.hasMic = false; cb(null); }, 6000);
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      clearTimeout(to); self.hasMic = true; self.stream = s; cb(s);
    }).catch(function () { clearTimeout(to); self.hasMic = false; cb(null); });
  },
  muted: false,
  init: function () {
    // ★ 绝不在这里 getUserMedia：否则一进游戏就一直占用麦克风，系统显示"录音中"、
    //   而且关不掉 → 整个手机静音失效。改为「按住说话那一刻」才申请。
    try { if (!navigator.mediaDevices || !window.MediaRecorder) this.hasMic = false; } catch (e) { this.hasMic = false; }
  },
  /* ★ 释放麦克风：松开按钮 / 关开关 / 切后台 都要调，确保不占着设备 */
  release: function () {
    try {
      if (this.rec && this.rec.state === 'recording') { try { this.rec.stop(); } catch (e) {} }
      if (this.stream) { this.stream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} }); this.stream = null; }
      var b = $('btnVoice'); if (b) b.className = b.className.replace('rec', '').trim();
    } catch (e) {}
  },
  mute: function (on) {
    this.muted = !!on;
    if (this.muted) this.release();
    try { localStorage.setItem('tl_mic', this.muted ? '0' : '1'); } catch (e) {}
  },
  start: function () {
    var self = this;
    if (this.muted) { HUD.center('麦克风已关闭', '点 ☰ → 麦克风:开', 1600); return; }
    if (this.rec && this.rec.state === 'recording') return;
    this._getMic(function (s) {
      if (!s) { self.panel(); return; }
      try {
        self.chunks = [];
        var opts = {};
        try {
          var cands = ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm'];
          for (var ci = 0; ci < cands.length; ci++) { if (MediaRecorder.isTypeSupported(cands[ci])) { opts = { mimeType: cands[ci], audioBitsPerSecond: 16000 }; break; } }
        } catch (e) {}
        var mr = new MediaRecorder(s, opts); self.rec = mr;
        mr.ondataavailable = function (e) { if (e.data && e.data.size) self.chunks.push(e.data); };
        mr.onstop = function () { self.finish(); };
        mr.start(); self.t0 = Date.now();
        var b = $('btnVoice'); if (b) b.className = 'rec';
        HUD.center('录音中…', '松手发送', 4000);
      } catch (e) { self.panel(); }
    });
  },
  stop: function () {
    if (this.rec && this.rec.state === 'recording') {
      var self = this;
      try { this.rec.onstop = function () { self.finish(); self.release(); }; this.rec.stop(); } catch (e) { this.release(); }
    } else { this.release(); }
    var b = $('btnVoice'); if (b) b.className = '';
  },
  finish: function () {
    var ms = Math.max(300, Date.now() - this.t0);
    var mime = (this.chunks[0] && this.chunks[0].type) || (this.rec && this.rec.mimeType) || 'audio/webm';
    var blob = new Blob(this.chunks, { type: mime });
    this.chunks = [];
    if (!blob.size) { HUD.center('没录到声音', '麦克风权限或按住时间太短'); return; }
    if (blob.size > 90000) { HUD.center('语音太长', '请控制在 6 秒内'); return; }
    var fr = new FileReader();
    fr.onload = function () {
      var b64 = String(fr.result).split(',')[1];
      Voice.addMsg({ name: Net.name + '（我）', data: b64, ms: ms, mime: mime, mine: true });
      if (b64) Net.voiceSend(b64, ms, null, mime);
    };
    fr.readAsDataURL(blob);
  },
  addMsg: function (o) {
    var box = $('voiceLog'); if (!box) return;
    var d = document.createElement('div'); d.className = 'vmsg';
    d.innerHTML = '<b>' + esc(o.name) + '</b>' + (o.data ? '<span class="vp">▶ 语音 ' + Math.max(1, Math.round((o.ms || 1000) / 1000)) + '″</span>' : esc(o.text || ''));
    if (o.data) d.querySelector('.vp').onclick = function () { Voice.play(o.data); };
    box.appendChild(d);
    while (box.children.length > 4) box.removeChild(box.firstChild);
    setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 22000);
  },
  play: function (b64, mime) {
    try {
      Sfx.resume();
      var bin = atob(b64), arr = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      // ★ WebView 里 data: URL 常报 NotSupportedError → 改用 Blob URL
      var blob = new Blob([arr], { type: mime || 'audio/webm' });
      var url = URL.createObjectURL(blob);
      var a = new Audio();
      a.volume = Math.min(1, 0.95 * (Sfx.vol || 1));
      a.onended = function () { try { URL.revokeObjectURL(url); } catch (e) {} };
      a.onerror = function () { try { URL.revokeObjectURL(url); } catch (e) {} Voice.fallback(b64); };
      a.src = url; a.play().catch(function () { try { URL.revokeObjectURL(url); } catch (e) {} Voice.fallback(b64); });
    } catch (e) { Voice.fallback(b64); }
  },
  _fbTried: {},
  fallback: function (b64) {          // 万一 webm 播不了 → 试 mp4（Android 原生支持）
    try {
      if (this._fbTried[b64.slice(0, 24)]) return; this._fbTried[b64.slice(0, 24)] = 1;
      var bin = atob(b64), arr = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      var url = URL.createObjectURL(new Blob([arr], { type: 'audio/mp4' }));
      var a = new Audio(); a.volume = Math.min(1, 0.95 * (Sfx.vol || 1)); a.src = url;
      a.play().then(function () {}, function () { try { URL.revokeObjectURL(url); } catch (e) {} });
    } catch (e) {}
  },
  speak: function (text) {
    try { if (!window.speechSynthesis) return; var u = new SpeechSynthesisUtterance(text); u.lang = 'zh-CN'; u.volume = Math.min(1, 0.9 * (Sfx.vol || 1)); speechSynthesis.speak(u); } catch (e) {}
  },
  panel: function () {
    var p = $('voicePanel');
    if (p) { p.style.display = (p.style.display === 'block') ? 'none' : 'block'; return; }
    p = document.createElement('div'); p.id = 'voicePanel';
    p.style.cssText = 'position:absolute;right:60px;top:96px;z-index:26;background:rgba(8,6,18,.95);border:1px solid var(--line);border-radius:12px;padding:10px;display:flex;flex-direction:column;gap:6px;min-width:132px';
    var t = document.createElement('div'); t.textContent = '快 速 语 音';
    t.style.cssText = 'font-size:11px;color:#8b7cb0;letter-spacing:2px'; p.appendChild(t);
    this.PHRASES.forEach(function (tx) {
      var b = document.createElement('button'); b.textContent = tx;
      b.style.cssText = 'background:rgba(30,20,50,.82);color:#e8e0f0;border:1px solid rgba(168,85,247,.35);border-radius:8px;padding:6px 10px;font-size:12.5px;font-family:inherit';
      b.onclick = function () { Net.voiceSend(null, 0, tx); Voice.addMsg({ name: Net.name + '（我）', text: tx, mine: true }); p.style.display = 'none'; };
      p.appendChild(b);
    });
    var hud = document.querySelector('.hud'); if (hud) hud.appendChild(p);
  },
};

/* ============================== 枪械 ============================== */
var WEAPONS = [
  { id: 'rifle',   name: '天泪突击步枪', short: '步枪', dmg: 17, rpm: 640, mag: 30, reserve: 180, reload: 1.9, spread: 0.008,  moveSpread: 0.022, auto: true,  pellets: 1, range: 150, recoil: 0.55, knock: 1.4, sfx: 'rifle',   ads: 0.55, hip: 3.6, color: 0x9aa7ff },
  { id: 'smg',     name: '虚空冲锋枪',   short: '冲锋', dmg: 12, rpm: 900, mag: 40, reserve: 240, reload: 1.6, spread: 0.013,  moveSpread: 0.030, auto: true,  pellets: 1, range: 95,  recoil: 0.38, knock: 0.6, sfx: 'smg',     ads: 0.62, hip: 3.4, color: 0x7cffd0 },
  { id: 'shotgun', name: '符文霰弹枪',   short: '霰弹', dmg: 13, rpm: 78,  mag: 7,  reserve: 48,  reload: 2.5, spread: 0.078,  moveSpread: 0.05,  auto: false, pellets: 8, range: 32,  recoil: 2.1,  knock: 6.5, sfx: 'shotgun', ads: 0.72, hip: 3.2, color: 0xffb86a },
  { id: 'sniper',  name: '时之狙击枪',   short: '狙击', dmg: 118, rpm: 42, mag: 5,  reserve: 35,  reload: 3.0, spread: 0.0013, moveSpread: 0.055, auto: false, pellets: 1, range: 340, recoil: 3.2, knock: 7.5, sfx: 'sniper',  ads: 0.14, hip: 3.9, color: 0xc084fc },
  { id: 'missile', name: '极速导弹',     short: '导弹', dmg: 130, rpm: 66, mag: 3,  reserve: 12,  reload: 3.6, spread: 0, moveSpread: 0, auto: false, pellets: 1, range: 500, recoil: 1.8, knock: 2.0, sfx: 'sniper', ads: 0.6, hip: 3.8, color: 0xff5f6d },
  { id: 'minigun', name: '重型机炮',     short: '机炮', dmg: 9,   rpm: 1150, mag: 600, reserve: 3000, reload: 5.0, spread: 0.021, moveSpread: 0.03, auto: true, pellets: 1, range: 130, recoil: 0.32, knock: 0.5, sfx: 'smg', ads: 0.85, hip: 3.6, color: 0xffd166 },
  { id: 'gl',      name: '榴弹炮',       short: '榴弹', dmg: 110, rpm: 68, mag: 6,   reserve: 30,  reload: 3.2, spread: 0.004, moveSpread: 0.02, auto: false, pellets: 1, range: 190, recoil: 2.4, knock: 1.5, sfx: 'shotgun', ads: 0.7, hip: 3.5, color: 0xff9a3d, aoe: 6.0 },
  // ★ 神器：分享 3 个好友解锁（req = 需要邀请人数）
  { id: 'relic',   name: '天泪 · 虚空之刃', short: '神器', dmg: 96, rpm: 200, mag: 24, reserve: 240, reload: 1.5, spread: 0, moveSpread: 0.01, auto: true, pellets: 1, range: 220, recoil: 0.5, knock: 3.0, sfx: 'sniper', ads: 0.30, hip: 3.4, color: 0x22d3ee, req: 3, secret: true },
];
var WMAP = {}; WEAPONS.forEach(function (w, i) { WMAP[w.id] = w; w.index = i; });

/* ============================== 魔物（原 2D 大厅怪物 → 3D 场景里的立绘） ============================== */
var MOBS = {
  floater: { key: 'floater', name: '虚空浮游魔', hp: 70,  dmg: 9,  speed: 3.6, aggro: 26, atkRange: 2.6, atkCd: 1.5, fly: 1.35, hitY: 1.5, hitR: 1.5, hitW: 1.5, mass: 0.55, score: 12, ranged: false, spr: 'assets/img/enemy_floater.png', col: '#a855f7', scale: 2.4 },
  golem:   { key: 'golem',   name: '符文傀儡',   hp: 210, dmg: 20, speed: 2.8, aggro: 24, atkRange: 2.8, atkCd: 2.1, fly: 0,    hitY: 1.25, hitR: 1.8, hitW: 1.8, mass: 2.4,  score: 26, ranged: false, spr: 'assets/img/enemy_golem.png',   col: '#f59e0b', scale: 3.0 },
  wraith:  { key: 'wraith',  name: '书页游魂',   hp: 100, dmg: 13, speed: 2.4, aggro: 34, atkRange: 24, atkCd: 2.4, fly: 1.25, hitY: 1.45, hitR: 1.6, hitW: 1.6, mass: 0.9,  score: 20, ranged: true,  spr: 'assets/img/enemy_wraith.png',  col: '#60a5fa', scale: 2.7 },
};
var MOB_KEYS = ['floater', 'golem', 'wraith'];
/* ★ 4 个 Boss = 天际巨物（14~17m，透视近大远小制造压迫感）；小怪保持正常 */
var BOSSES = [
  { id: 1, name: '虚空行者', spr: 'assets/img/boss_void.png',    scale: 14, hp: 2600, dmg: 26, spd: 2.4, x: 126, z: 24,  col: '#a855f7', tag: '空间·第一锚点' },
  { id: 2, name: '熔雷巨像', spr: 'assets/img/boss_element.png', scale: 16, hp: 3400, dmg: 32, spd: 2.1, x: 78,  z: 30,  col: '#f59e0b', tag: '元素·第二锚点' },
  { id: 3, name: '字祸魔典', spr: 'assets/img/boss_book.png',    scale: 13, hp: 3000, dmg: 24, spd: 2.6, x: 120, z: 102, col: '#60a5fa', tag: '言灵·第三锚点' },
  { id: 4, name: '时之眼',   spr: 'assets/img/boss_eye.png',     scale: 17, hp: 4200, dmg: 30, spd: 2.2, x: 36,  z: 93,  col: '#c084fc', tag: '时空·最终锚点' },
];
var BOSS_TEX = {};

/* ============================== 立绘系统（HD-2D 招牌：2D 立绘 × 3D 立体场景） ============================== */
var DIRS = ['S', 'SE', 'E', 'NE', 'N', 'NW', 'W', 'SW'];
var CH_ANG = { S: 0, SE: 45, E: 90, NE: 135, N: 180, NW: 225, W: 270, SW: 315 };
var CH = {};
(function loadDirs() {
  var tl = new THREE.TextureLoader();
  DIRS.forEach(function (d) {
    var t = tl.load('assets/ch/dir_' + d + '.png');
    t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
    if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
    CH[d] = t;
  });
})();
function dirFromAngle(a) {
  a = ((a % 360) + 360) % 360; var best = 'S', bd = 999;
  for (var i = 0; i < DIRS.length; i++) { var d = DIRS[i]; var k = Math.abs(((CH_ANG[d] - a + 540) % 360) - 180); if (k < bd) { bd = k; best = d; } }
  return best;
}
/* 敌方立绘（单张） */
var MOB_TEX = {};
(function loadMobTex() {
  var tl = new THREE.TextureLoader();
  MOB_KEYS.forEach(function (k) {
    var t = tl.load(MOBS[k].spr);
    t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter;
    if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
    MOB_TEX[k] = t;
  });
  BOSSES.forEach(function (b) { var t = tl.load(b.spr); t.minFilter = THREE.LinearMipmapLinearFilter; t.magFilter = THREE.LinearFilter; if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding; BOSS_TEX[b.id] = t; });
})();

/* 立绘材质：吃主光 + 环境，受击闪白，色相 tint（队伍色） */
var LIGHT_DIR = (function () { var d = A.moon.position.clone().normalize(); return d; })();
/* ★ 头顶名牌（画布贴图，跟随玩家） */
function makeNameTag(text, col) {
  var c = document.createElement('canvas'); c.width = 256; c.height = 64;
  var g = c.getContext('2d');
  g.clearRect(0, 0, 256, 64);
  g.font = 'bold 30px "Noto Sans SC",sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineWidth = 7; g.strokeStyle = 'rgba(0,0,0,.85)'; g.strokeText(text, 128, 32);
  g.fillStyle = '#' + ('000000' + col.toString(16)).slice(-6); g.fillText(text, 128, 32);
  var t = new THREE.CanvasTexture(c); if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;
  var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false, depthWrite: false }));
  s.scale.set(3.2, 0.8, 1); s.renderOrder = 999;
  return s;
}

function spriteMat(tex, opt) {
  opt = opt || {};
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: true, side: THREE.DoubleSide,
    uniforms: {
      uMap: { value: tex }, uAmb: { value: opt.amb === undefined ? 0.62 : opt.amb },
      uLightDir: { value: LIGHT_DIR }, uLightC: { value: new THREE.Color(0.85, 0.9, 1.0) },
      uTint: { value: new THREE.Color(opt.tint === undefined ? 0xffffff : opt.tint) },
      uFlash: { value: 0 }, uOpacity: { value: 1 },
      uOutline: { value: new THREE.Color(0x000000) }, uOutlineW: { value: 0 },
      uGI: { value: (window.ARENA && window.ARENA.GI) ? window.ARENA.GI() : null },
      uWld: { value: (window.ARENA && window.ARENA.world) || 156 }, uGIA: { value: 0.55 },
    },
    vertexShader: 'varying vec2 vUv; varying vec3 vN; varying vec3 vWP;\n' +
      'void main(){ vUv=uv; vN=normalize(mat3(modelMatrix)*vec3(0.0,0.0,1.0));' +
      ' vWP=(modelMatrix*vec4(0.0,0.0,0.0,1.0)).xyz;' +
      ' gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
    fragmentShader: 'uniform sampler2D uMap; uniform sampler2D uGI; uniform vec3 uLightDir,uLightC,uTint,uOutline; uniform float uAmb,uFlash,uOpacity,uWld,uGIA,uOutlineW;\n' +
      'varying vec2 vUv; varying vec3 vN; varying vec3 vWP;\n' +
      'void main(){ vec4 t=texture2D(uMap,vUv);\n' +
      '  if(t.a<0.45){\n' +
      '    if(uOutlineW>0.0){\n' +
      '      vec2 q=vec2(uOutlineW/230.0,uOutlineW/310.0); float a=0.0;\n' +
      '      a=max(a,texture2D(uMap,vUv+vec2(q.x,0.0)).a); a=max(a,texture2D(uMap,vUv-vec2(q.x,0.0)).a);\n' +
      '      a=max(a,texture2D(uMap,vUv+vec2(0.0,q.y)).a); a=max(a,texture2D(uMap,vUv-vec2(0.0,q.y)).a);\n' +
      '      a=max(a,texture2D(uMap,vUv+q).a); a=max(a,texture2D(uMap,vUv-q).a);\n' +
      '      a=max(a,texture2D(uMap,vUv+vec2(q.x,-q.y)).a); a=max(a,texture2D(uMap,vUv+vec2(-q.x,q.y)).a);\n' +
      '      if(a>0.45){ gl_FragColor=vec4(uOutline.rgb*uOpacity,uOpacity); return; }\n' +
      '    }\n' +
      '    discard;\n' +
      '  }\n' +
      '  float ndl=max(dot(vN,uLightDir),0.0);\n' +
      '  vec3 gi = texture2D(uGI, vWP.xz/uWld).rgb;\n' +
      '  vec3 c=t.rgb*uTint*(uAmb+ndl*0.6)*uLightC*(1.0+gi*uGIA);\n' +
      '  c=mix(c, vec3(1.0), uFlash);\n' +
      '  gl_FragColor=vec4(c, t.a*uOpacity); }',
  });
}
/* 通用立绘实体：绕 Y 面向相机的公告板 + 接地影 + 头顶血条 */
function makeBillboard(hWorld, mat) {
  var img = mat.uniforms.uMap.value.image;
  var ar = (img && img.width) ? img.width / img.height : 0.6;
  var g = new THREE.PlaneGeometry(hWorld * ar, hWorld); g.translate(0, hWorld / 2, 0);
  var m = new THREE.Mesh(g, mat);
  return m;
}
function addShadow(r) {
  var m = new THREE.Mesh(new THREE.PlaneGeometry(r, r * 0.7),
    new THREE.MeshBasicMaterial({ map: shadowTex(), color: 0x000000, transparent: true, opacity: 0.5, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; return m;
}
var _shTex = null;
function shadowTex() {
  if (_shTex) return _shTex;
  var c = document.createElement('canvas'); c.width = c.height = 128; var g = c.getContext('2d');
  var gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.55, 'rgba(255,255,255,.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); _shTex = new THREE.CanvasTexture(c); return _shTex;
}
var HP_TEX = null;
function hpTex() {                       // ★ 共享血条贴图（MobRender 池用）
  if (HP_TEX) return HP_TEX;
  var c = document.createElement('canvas'); c.width = 64; c.height = 12; var g = c.getContext('2d');
  g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(0, 0, 64, 12);
  g.fillStyle = '#ff4d6d'; g.fillRect(1, 1, 62, 10);
  g.fillStyle = 'rgba(255,255,255,.4)'; g.fillRect(1, 1, 62, 3);
  HP_TEX = new THREE.CanvasTexture(c); return HP_TEX;
}
function makeHpBar(width) {
  var c = document.createElement('canvas'); c.width = 128; c.height = 34;
  var t = new THREE.CanvasTexture(c);
  var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false, depthWrite: false }));
  s.scale.set(width || 2.0, (width || 2.0) * 0.27, 1); s.renderOrder = 999; s.userData = { c: c, t: t };
  return s;
}
function drawHp(s, ratio, name, color) {
  var c = s.userData.c, g = c.getContext('2d');
  g.clearRect(0, 0, 128, 34);
  g.fillStyle = 'rgba(0,0,0,.55)'; g.fillRect(6, 15, 116, 9);
  g.fillStyle = color || '#ff4d6d'; g.fillRect(6, 15, 116 * clamp(ratio, 0, 1), 9);
  g.strokeStyle = 'rgba(255,255,255,.4)'; g.lineWidth = 1; g.strokeRect(6.5, 15.5, 115, 8);
  if (name) { g.font = 'bold 13px sans-serif'; g.fillStyle = '#fff'; g.textAlign = 'center'; g.fillText(name, 64, 12); }
  s.userData.t.needsUpdate = true;
}

/* ============================== ★ 3D 准星（世界空间标记，而非屏幕贴片） ============================== */
var Aim = { type: 'air', crit: false, point: null, dist: 30, group: null, mat: null, mode3d: true };
function buildAim() {
  if (Aim.group) return;
  var g = new THREE.Group(); g.renderOrder = 999; g.frustumCulled = false;
  Aim.mat = new THREE.LineBasicMaterial({ color: 0x9ff0ff, transparent: true, opacity: 0.95, depthTest: false, blending: THREE.AdditiveBlending });
  var geo = new THREE.BufferGeometry();
  var sz = 0.5, o = 0.16;
  geo.setAttribute('position', new THREE.Float32BufferAttribute([
    -sz, 0, 0, -o, 0, 0, sz, 0, 0, o, 0, 0,
    0, -sz, 0, 0, -o, 0, 0, sz, 0, 0, o, 0,
  ], 3));
  var line = new THREE.LineSegments(geo, Aim.mat); line.frustumCulled = false; g.add(line);
  var dot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 6, 4), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.95 }));
  g.add(dot); Aim.dot = dot;
  g.visible = false; actionScene.add(g); Aim.group = g;
}
function setAimVisible(v) { if (Aim.group) Aim.group.visible = !!v; }
function updateAim() {
  if (!Aim.group) return;
  var w = WMAP[P.weapon];
  var eye, hit;
  var eye = V3(P.x, P.y + (P.crouch ? 1.15 : 1.4), P.z), dir = null;
  if (A.getCamMode() === 'hd2d') {
    if (!Combat._hdrc) Combat._hdrc = new THREE.Raycaster();
    Combat._hdrc.setFromCamera({ x: Input.aimX || 0, y: Input.aimY || 0 }, A.orthoCam);
    var rr = Combat._hdrc.ray;
    hit = Combat.cast(rr.origin.x, rr.origin.y, rr.origin.z, rr.direction.x, rr.direction.y, rr.direction.z, 500);
    dir = (hit && hit.p) ? hit.p.clone().sub(eye).normalize() : rr.direction.clone();
  } else {
    dir = camDir(V3(0, 0, 0)).clone();
    hit = Combat.cast(eye.x, eye.y, eye.z, dir.x, dir.y, dir.z, w.range);
  }
  if (!dir || !isFinite(dir.x)) dir = V3(0, 0, 1);
  Aim.type = hit.type; Aim.crit = !!hit.crit;
  Aim.point = hit.p.clone(); Aim.dist = eye.distanceTo(hit.p);
  var dist = Math.min(Aim.dist, 40);
  if (hit.type === 'wall') dist = Math.max(0.5, Aim.dist - 0.06);
  Aim.group.position.copy(eye).addScaledVector(dir, dist);
  Aim.group.lookAt(cam().position);
  Aim.group.scale.setScalar(clamp(dist * 0.034, 0.18, 4.0));
  Aim.group.visible = P.alive && Aim.mode3d;
  var col = hit.type === 'mob' ? (hit.crit ? 0xffd166 : 0xff4d5e) : (hit.type === 'player' ? 0xff4d5e : 0x9ff0ff);
  Aim.mat.color.setHex(col);
}

/* ============================== 特效池 ============================== */
var FX = {
  tracer: [], impact: [], shell: [], flash: [], beam: [], glow: [], decal: [],
  bt: 0, gt: 0, dt: 0, it: 0, st: 0, ft: 0, tt: 0,
  init: function () {
    // 冲击火花
    var imp = (function () {
      var c = document.createElement('canvas'); c.width = c.height = 64; var g = c.getContext('2d');
      var gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      gr.addColorStop(0, 'rgba(255,255,225,1)'); gr.addColorStop(0.4, 'rgba(255,190,90,.8)'); gr.addColorStop(1, 'rgba(255,140,40,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
    })();
    for (var j = 0; j < 20; j++) { var s1 = new THREE.Sprite(new THREE.SpriteMaterial({ map: imp, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); s1.visible = false; actionScene.add(s1); this.impact.push({ o: s1, life: 0 }); }
    // 弹壳
    for (var k = 0; k < 26; k++) { var sh = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.09), new THREE.MeshStandardMaterial({ color: 0xd9b26a, roughness: 0.4, metalness: 0.6 })); sh.visible = false; actionScene.add(sh); this.shell.push({ o: sh, life: 0, v: V3(0, 0, 0) }); }
    // 枪口焰
    var ft = (function () {
      var c = document.createElement('canvas'); c.width = c.height = 64; var g = c.getContext('2d');
      var gr = g.createRadialGradient(32, 32, 0, 32, 32, 30);
      gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.3, 'rgba(255,235,150,.95)'); gr.addColorStop(0.65, 'rgba(255,150,40,.5)'); gr.addColorStop(1, 'rgba(255,90,0,0)');
      g.fillStyle = gr; g.beginPath(); g.moveTo(32, 2); g.lineTo(58, 56); g.lineTo(6, 56); g.closePath(); g.fill();
      return new THREE.CanvasTexture(c);
    })();
    for (var q = 0; q < 6; q++) { var sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: ft, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); sp.visible = false; actionScene.add(sp);
      var _pl = new THREE.PointLight(0xffd9a0, 0, 14, 2); _pl.visible = false; actionScene.add(_pl);
      this.flash.push({ o: sp, l: _pl, life: 0 }); }
    // ★ 火线（发光长条：从枪口到命中点）
    var beamGeo = new THREE.BoxGeometry(1, 1, 1);
    for (var b2 = 0; b2 < 26; b2++) {
      var bm = new THREE.MeshBasicMaterial({ color: 0xfff2b0, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, depthWrite: false });
      var bo = new THREE.Mesh(beamGeo, bm); bo.visible = false; bo.frustumCulled = false; actionScene.add(bo);
      this.beam.push({ o: bo, life: 0 });
    }
    // ★ 通用光晕（弹道带光 / 命中 / 能量球拖尾）
    var gl = (function () {
      var c = document.createElement('canvas'); c.width = c.height = 64; var g = c.getContext('2d');
      var gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      gr.addColorStop(0, 'rgba(255,255,255,.95)'); gr.addColorStop(0.35, 'rgba(255,255,255,.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
    })();
    for (var g2 = 0; g2 < 80; g2++) { var gs = new THREE.Sprite(new THREE.SpriteMaterial({ map: gl, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })); gs.visible = false; actionScene.add(gs); this.glow.push({ o: gs, life: 0, lifeMax: 1 }); }
    // ★ 地面染色光斑（打过的地方留光）
    var dgeo = new THREE.PlaneGeometry(1, 1); dgeo.rotateX(-Math.PI / 2);
    for (var d2 = 0; d2 < 30; d2++) { var dm = new THREE.MeshBasicMaterial({ map: gl, color: 0x66d0ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }); var dobj = new THREE.Mesh(dgeo, dm); dobj.visible = false; actionScene.add(dobj); this.decal.push({ o: dobj, life: 0, lifeMax: 1 }); }
    // ★ 枪口点光（照亮周围）
    this.gunL = null;
  },
  tracerA: function (a, b) {                      // ★ 火线：一条发光光束
    if (!this.beam.length) return;
    var t = this.beam[this.bt++ % this.beam.length];
    var dir = b.clone().sub(a), len = dir.length() || 1; dir.multiplyScalar(1 / len);
    t.o.position.copy(a).addScaledVector(dir, len * 0.5);
    t.o.quaternion.setFromUnitVectors(V3(0, 0, 1), dir);
    t.o.scale.set(0.085, 0.085, len);
    t.o.visible = true; t.o.material.opacity = 0.95; t.life = 0.09;
  },
  _fT: 0, _fN: 0,
  glowAt: function (p, size, life, color) {       // ★ 追加光晕（带每帧配额，防池子被刷爆残留）
    var now = performance.now(); if (now - this._fT > 16) { this._fT = now; this._fN = 0; }
    if (this._fN > 14) return; this._fN++;
    if (!this.glow.length) return;
    var g = this.glow[this.gt++ % this.glow.length];
    g.o.position.copy(p); g.o.material.color.setHex(color === undefined ? 0xffd9a0 : color);
    g.o.scale.set(size, size, 1); g.o.visible = true; g.o.material.opacity = 1; g.life = g.lifeMax = (life || 0.2);
  },
  decalAt: function (x, y, z, size, color, life) { // ★ 地面染色光斑（长时间淡出）
    if (!this.decal.length) return;
    var d = this.decal[this.dt++ % this.decal.length];
    d.o.position.set(x, y, z); d.o.material.color.setHex(color === undefined ? 0x66d0ff : color);
    d.o.scale.set(size, 1, size); d.o.visible = true; d.o.material.opacity = 0.9; d.life = d.lifeMax = (life || 2.0);
  },
  ballistic: function (a, b) {                     // ★ 整条弹道的光效

    var dist = a.distanceTo(b), steps = Math.min(6, Math.max(1, Math.floor(dist / 4)));
    for (var i = 1; i <= steps; i++) { var p = a.clone().lerp(b, i / (steps + 1)); this.glowAt(p, 0.5, 0.13, 0xffe0a0); }
    var cols = [0xff5fb0, 0x39e0ff, 0xffcc55, 0x8affc0, 0x9fc4ff];
    var gy = window.ARENA ? window.ARENA.Ground.h(b.x, b.z) : 0;
    // ★ 地面光斑已移除（密集射击时会在地面残留一片，很诡异）
    this.glowAt(b, 1.15, 0.2, 0xfff0c0);
  },
  imp: function (p, big) { if (!this.impact.length) return; var i = this.impact[this.it++ % this.impact.length]; i.o.position.copy(p); i.o.visible = true; i.o.material.opacity = 1; var s = big ? 1.6 : 0.6; i.o.scale.set(s, s, 1); i.life = 0.14; },
  muzzle: function (p) { if (!this.flash.length) return; var f = this.flash[this.ft++ % this.flash.length]; f.o.position.copy(p); f.o.visible = true; f.o.material.opacity = 1; f.o.material.rotation = Math.random() * 6.28; if (f.l) { f.l.position.copy(p); f.l.visible = true; f.l.intensity = 6; } f.life = 0.05; },
  blast: function (x, y, z, size, inten, life) { if (!this.flash.length) return; var f = this.flash[this.ft++ % this.flash.length]; f.o.position.set(x, y, z); f.o.visible = true; f.o.scale.set(size, size, 1); f.o.material.opacity = 1; if (f.l) { f.l.position.set(x, y, z); f.l.visible = true; f.l.intensity = inten; } f.life = life || 0.3; },
  shellOut: function (p, right) { if (!this.shell.length) return; var s = this.shell[this.st++ % this.shell.length]; s.o.position.copy(p); s.o.visible = true; s.v.set(right.x * 2.4 + rnd(-1, 1), 3.4 + rnd(0, 1.4), right.z * 2.4 + rnd(-1, 1)); s.life = 1.1; },
  knock: function (b, dir, force) {
    if (!b || !b.alive) return;
    var L = Math.hypot(dir.x, dir.z) || 1;
    var imp = (force || 1) / 14;                          // 巨物质量 14 → 几乎推不动
    b.kx = (b.kx || 0) + (dir.x / L) * imp * 4.0; b.kz = (b.kz || 0) + (dir.z / L) * imp * 4.0;
  },
  update: function (dt) {
    var i, t;
    for (i = 0; i < this.beam.length; i++) { t = this.beam[i]; if (t.life > 0) { t.life -= dt; t.o.material.opacity = Math.max(0, t.life / 0.09) * 0.95; if (t.life <= 0) t.o.visible = false; } }
    for (i = 0; i < this.glow.length; i++) { t = this.glow[i]; if (t.life > 0) { t.life -= dt; t.o.material.opacity = Math.max(0, t.life / t.lifeMax); t.o.scale.multiplyScalar(1 + dt * 1.6); if (t.life <= 0) t.o.visible = false; } }
    for (i = 0; i < this.decal.length; i++) { t = this.decal[i]; if (t.life > 0) { t.life -= dt; t.o.material.opacity = Math.max(0, t.life / t.lifeMax) * 0.9; if (t.life <= 0) t.o.visible = false; } }
    for (i = 0; i < this.impact.length; i++) { t = this.impact[i]; if (t.life > 0) { t.life -= dt; t.o.material.opacity = Math.max(0, t.life / 0.14); t.o.scale.multiplyScalar(1 + dt * 7); if (t.life <= 0) t.o.visible = false; } }
    for (i = 0; i < this.flash.length; i++) { t = this.flash[i]; if (t.life > 0) { t.life -= dt; if (t.life <= 0) { t.o.visible = false; if (t.l) { t.l.intensity = 0; t.l.visible = false; } } } }
    for (i = 0; i < this.shell.length; i++) { t = this.shell[i]; if (t.life > 0) { t.life -= dt; t.v.y -= 22 * dt; t.o.position.addScaledVector(t.v, dt); var gh = G.h(t.o.position.x, t.o.position.z) + 0.03; if (t.o.position.y < gh) { t.o.position.y = gh; t.v.set(0, 0, 0); } t.o.rotation.x += dt * 12; t.o.rotation.z += dt * 9; if (t.life <= 0) t.o.visible = false; } }

  },
};

var ScreenShake = { amt: 0, add: function (a) { this.amt = Math.min(1.2, this.amt + a); }, update: function (dt) { this.amt = Math.max(0, this.amt - dt * 2.6); return this.amt; } };

/* ============================== 联机层（公共 MQTT · 房间） ============================== */
var GLOBAL_ROOM = 'world';     // ★ 全服统一世界：所有玩家默认自动进这一个房间
// ★ 公网分发入口（用户点链接直接玩网页版；APK 里 file:// 时用它拼邀请链接）
var PUBLIC_BASE = window.TL_PUBLIC_BASE || 'https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/tianlei3d/';
function publicEntry() {
  var h = location.href.split('?')[0].split('#')[0];
  if (/^file:/i.test(h) || /^https?:\/\/(localhost|127\.|\d+\.\d+\.\d+\.\d+:)/i.test(location.origin + '/')) {
    return PUBLIC_BASE + (/\/$/.test(PUBLIC_BASE) ? '' : '/') + (/index\.html$/.test(h) ? '' : 'index.html');
  }
  return h;
}
var Net = {
  NS: 'zhz/tianlei/fps/', room: GLOBAL_ROOM, name: '旅人', id: '', inv: '', fromLink: false,
  mq: null, connected: false, connecting: false, enabled: true,
  isHost: false, hostId: '', hostAt: 0, rtt: 0, peers: 1,
  players: new Map(),          // id -> 远端玩家状态
  chat: [], feed: [], hist: [],   // hist = 历史事件大厅（broker retain → 跨设备、离线也在）
  onStatus: null, onChat: null, onFeed: null, onEvent: null, onPlayers: null, onHist: null,
  _st: 0, _hostTimer: null, _cleanTimer: null, _pingAt: 0, _seen: {}, _histN: 0, _joinLogged: 0,
  /* ★★ 去中心化权威（无房主）★★
     以前是"房主权威"：一台机器模拟全部 Boss/小怪，别人复现。
     问题：公网延迟 4~5s 时，房主一抖 / 两端对"谁是房主"判断不一致（split-brain），
           就会出现"两边都以为对方是房主 → 谁都不模拟 → 谁都看不到 Boss"。
     现在：按实体拆分权威，确定性归属，无需协商：
       · 小怪：id 自带归属者 → "<ownerId>-M<n>"，前缀是谁的就是谁的。
       · Boss：4 个固定，按「最近活跃玩家名单」（按 id 字典序）轮流分配。
     任何一端掉线/卡住，名单里自动剔除 → 别人立刻接手（从上一帧状态续上）。
     → 没有单点，谁都在"共同维持"这个世界。 */
  roster: function () {
    var now = performance.now();
    if (this._rosterT && now - this._rosterT < 300) return this._rosterCache;   // ★ 300ms 缓存（热循环里频繁调用）
    var ids = [];
    // ★ 判"对方还在"的阈值放宽到 12s：公网延迟常达 4~5s，阈值太紧会误判掉线→归属乱跳→两端各模拟一份而分叉
    this.players.forEach(function (p, id) { if (now - (p._t || 0) < 12000) ids.push(id); });
    ids.push(this.id);
    ids.sort();
    this._rosterCache = ids; this._rosterT = now;
    return ids;
  },
  isScribe: function () { return this.roster()[0] === this.id; },     // 历史大厅的单一写入者（避免重复记录）
  mobOwner: function (id) { return String(id).split('-M')[0]; },
  mineMob: function (id) { return !this.connected || this.mobOwner(id) === this.id; },
  bossIdx: function (id) { var n = parseInt(String(id).replace(/[^0-9]/g, ''), 10); return (isFinite(n) && n > 0) ? n : 1; },
  mineBoss: function (id) { if (!this.connected) return true; var r = this.roster(); return r[this.bossIdx(id) % r.length] === this.id; },
  base: function () { return this.NS + this.room + '/'; },
  tP: function (id) { return this.base() + 'p/' + id; },
  tMob: function () { return this.base() + 'mob'; },
  tEv: function () { return this.base() + 'ev'; },
  tHost: function () { return this.base() + 'host'; },
  tBoss: function () { return this.base() + 'boss'; },      // ★ Boss 权威快照（房主广播）
  tHist: function (k) { return this.base() + 'hist/' + k; },
  tHistAll: function () { return this.base() + 'hist/#'; },

  load: function () {
    try {
      var s = JSON.parse(localStorage.getItem('tianlei_fps') || '{}');
      if (s.name) this.name = s.name;
      if (s.id) this.id = s.id;
    } catch (e) {}
    // ★ 链接即进服：URL 参数优先（?room=xxx&n=昵称&inv=邀请人）——玩家完全无感
    try {
      var q = new URLSearchParams(location.search);
      var r = (q.get('room') || q.get('r') || '').trim();
      var n = (q.get('n') || q.get('name') || '').trim();
      if (r) this.room = r.replace(/[^0-9A-Za-z_\u4e00-\u9fa5-]/g, '').slice(0, 24) || GLOBAL_ROOM;
      if (n) this.name = n.slice(0, 16);
      this.inv = (q.get('inv') || q.get('from') || '').trim().slice(0, 24);   // 邀请人的 id
      if (q.has('room') || q.has('r') || q.has('auto')) this.fromLink = true;   // 点了分发链接 → 直接进
    } catch (e) {}
    // ★ 稳定身份：用设备指纹派生 id（换了浏览器/清了缓存也认得出是同一个人）
    if (window.Fp) { try { this.id = Fp.uid(); } catch (e) {} }
    if (!this.id) this.id = 'f' + Math.random().toString(36).slice(2, 8);
    if (!this.name || this.name === '旅人') this.name = '旅人' + Math.floor(100 + Math.random() * 900);
    this.save();
  },
  // 生成分发链接：任何人拿到都能点开直接进同一个世界
  inviteLink: function () {
    // ★ 用 id（稳定）而不是名字来标记"是谁邀请的"，否则改名就断链
    var u = publicEntry() + '?room=' + encodeURIComponent(this.room) + '&inv=' + encodeURIComponent(this.id);
    if (this.name) u += '&n=' + encodeURIComponent(this.name);
    return u;
  },
  save: function () { try { localStorage.setItem('tianlei_fps', JSON.stringify({ name: this.name, room: this.room, id: this.id })); } catch (e) {} },

  connect: function () {
    if (typeof MiniMqtt === 'undefined') { this.status('缺少 mqtt.js · 单机模式'); return; }
    this.disconnect();
    this.connecting = true; this.status('连接中…');
    var mq = MiniMqtt.createClient({ clientId: 'tlfps' + this.id });
    this.mq = mq; var self = this;
    mq.on('connect', function (b) {
      self.connected = true; self.connecting = false;
      self.status('在线 · ' + String(b || '').replace(/^wss:\/\//, '').split(':')[0]); self._downAt = 0;
      mq.subscribe(self.tMob()); mq.subscribe(self.tEv()); mq.subscribe(self.tHost()); mq.subscribe(self.base() + 'p/+');
      mq.subscribe(self.tBoss());                          // ★ Boss 权威快照
      mq.subscribe(self.tHistAll());                       // ★ 历史事件大厅：一进来就补齐全部历史
      mq.subscribe(self.base() + 'blk/#');                 // ★ 共享建造：一进来就拿到全服已建好的所有方块
      mq.subscribe(self.base() + 'ref/' + self.id + '/+');  // ★ 我的邀请记录（分享领神器）
      mq.subscribe(Stats.V + '+');                          // ★ 访客足迹（每个访客一条保留消息）
      self.broadcast({ k: 'join', name: self.name, inv: self.inv });
      Ref.report();                                        // ★ 记一次邀请（谁带我来的）
      Stats.mark();                                        // ★ 留痕：写下我自己的访客记录
      Stats.render();
      self.startHost();
      if (!self._cleanTimer) self._cleanTimer = setInterval(function () { self.clean(); }, 1500);
      if (!self._pingAt) self._pingAt = performance.now();
    });
    mq.on('message', function (t, p) { self.onMsg(t, p); });
    mq.on('close', function () { self.connected = false; self.isHost = false; self._downAt = performance.now(); self.status('网络抖动 · 重连中…'); });
    mq.on('error', function () { self.status('连接出错'); });
  },
  disconnect: function () {
    if (this._hostTimer) { clearInterval(this._hostTimer); this._hostTimer = null; }
    if (this.mq) { try { this.pub(this.tP(this.id), JSON.stringify({ id: this.id, bye: 1 }), false); } catch (e) {} try { this.mq.end(); } catch (e) {} this.mq = null; }
    this.connected = false; this.connecting = false; this.isHost = false;
    this.players.clear();
  },
  status: function (t) { if (this.onStatus) this.onStatus(t, this.connected); },
  pub: function (t, s, r) { if (this.mq && this.connected) { try { this.mq.publish(t, s, !!r); } catch (e) {} } },
  broadcast: function (o) { this.pub(this.tEv(), JSON.stringify(o)); },
  mobs: function (list) { if (this.connected && list && list.length) this.pub(this.tMob(), JSON.stringify({ id: this.id, at: Date.now(), h: (Host._hash | 0), m: list })); },

  sendState: function (p, extra) {
    if (!this.connected) return;
    var now = performance.now(); if (now - this._st < 120) return; this._st = now;
    var o = { id: this.id, name: this.name, x: +p.x.toFixed(2), z: +p.z.toFixed(2), y: +p.y.toFixed(2),
      yaw: +p.yaw.toFixed(1), hp: Math.round(p.hp), mx: Math.round(p.maxHp), wp: p.weapon,
      sc: p.score, kl: p.kills, dt: p.deaths, al: p.alive ? 1 : 0, tm: p.team, at: Date.now() };
    if (extra) for (var k in extra) o[k] = extra[k];
    this.pub(this.tP(this.id), JSON.stringify(o), false);
  },
  chatSend: function (text) { this.broadcast({ k: 'chat', name: this.name, text: text }); },
  voiceSend: function (b64, ms, text, mime) { if (!this.connected) return; this.broadcast({ k: 'voice', name: this.name, data: b64 || null, ms: ms || 0, text: text || null, mime: mime || null }); },

  startHost: function () {
    // ★ 去中心化后不再选"房主"。保留此函数：启动一个轻量"名单心跳"定时器，
    //   顺便记录一次"进入世界"（由 isScribe 派发，避免多端重复）。
    var self = this;
    if (this._hostTimer) clearInterval(this._hostTimer);
    this._hostTimer = setInterval(function () {
      if (!self.connected) return;
      if (!self._joinLogged && self.isScribe()) {
        self._joinLogged = 1;
        self.histPub({ k: 'join', name: self.name, text: self.name + ' 进入了世界' + (self.inv ? '（来自 ' + self.inv + ' 的邀请）' : '') });
      }
    }, 1600);
  },
  becomeHost: function () { /* 去中心化：无房主概念，保留空实现以兼容旧调用 */ },

  clean: function () {
    var now = performance.now(), ch = false;
    // ★ 保留 12s（与 roster 阈值一致；公网 4~5s 延迟 + 抖动下，太快删人会导致归属乱跳）
    this.players.forEach(function (p, id) { if (now - (p._t || 0) > 12000) { Net.players.delete(id); ch = true; } });
    if (ch) Net._rosterT = 0;
    this.peers = this.players.size + 1;
    if (ch && this.onPlayers) this.onPlayers();
    if (now - this._pingAt > 2500) { this._pingAt = now; this.broadcast({ k: 'ping', t: Date.now() }); }
  },

  onMsg: function (topic, payload) {
    var o = null; try { o = payload ? JSON.parse(payload) : null; } catch (e) { o = null; }
    // ★ 建造主题允许"空载荷"（= 拆除），不能像其它主题那样直接 return
    if (!o && topic.indexOf(this.base() + 'blk/') !== 0) return;
    var now = performance.now(), self = this;
    if (topic === this.tHost()) {
      // ★ 保留读取：有旧客户端（老版本）在广播房主时，我们记录下来仅供 UI 显示，不参与权威判定
      if (o && o.id && o.id !== this.id) { this.hostId = o.id; this.hostAt = Date.now(); }
      return;
    }
    if (topic === this.tMob()) {
      if (o.id === this.id) return;
      this.snap = o; this.snapAt = now; this.snapHost = o.id;
      if (this.onMobs) this.onMobs(o.m || []);
      // ★ 状态校验：我们展开出来的怪和房主发来的对不上 → 记下来（用于发现不同步）
      if (o.h !== undefined && Host.mobs.length) {
        var mine = 0;
        for (var _i = 0; _i < Host.mobs.length; _i++) { var _m = Host.mobs[_i]; if (_m.alive && !_m.remote) continue; }
        this._lastHash = o.h;
      }
      return;
    }
    if (topic.indexOf(this.base() + 'p/') === 0) {
      if (o.id === this.id) return;
      if (o.bye) { this.players.delete(o.id); this.peers = this.players.size + 1; if (this.onPlayers) this.onPlayers(); return; }
      if (!o.id || !isFinite(o.x) || !isFinite(o.z)) return;
      var prev = this.players.get(o.id);
      if (prev) { prev.tx = o.x; prev.tz = o.z; prev.ty = o.y; prev.yaw = o.yaw; prev.hp = o.hp; prev.maxHp = o.mx;
        prev.wp = o.wp; prev.score = o.sc; prev.kills = o.kl; prev.deaths = o.dt; prev.alive = o.al; prev.name = o.name; prev.team = o.tm; prev._t = now; }
      else { this.players.set(o.id, { id: o.id, name: o.name, x: o.x, z: o.z, y: o.y, tx: o.x, tz: o.z, ty: o.y,
        yaw: o.yaw, hp: o.hp, maxHp: o.mx, wp: o.wp, score: o.sc, kills: o.kl, deaths: o.dt, alive: o.al, team: o.tm, _t: now, _rx: o.x, _rz: o.z }); }
      this.peers = this.players.size + 1;
      if (this.onPlayers) this.onPlayers();
      return;
    }
    if (topic === this.tBoss()) {                                        // ★ Boss 权威快照（归属者广播，其余人复现）
      if (typeof BossSys !== 'undefined') BossSys.applySnap(o && o.m ? o.m : []);
      return;
    }
    if (topic.indexOf(this.base() + 'ref/') === 0) {                     // ★ 邀请记录
      Ref.add(topic.slice((this.base() + 'ref/').length));
      return;
    }
    if (topic.indexOf(this.base() + 'blk/') === 0) {                     // ★ 共享建造同步
      var bk = topic.slice((this.base() + 'blk/').length);
      Build.apply(bk, o);
      return;
    }
    if (topic.indexOf(this.base() + 'hist/') === 0) { this.onHistMsg(topic, o); return; }
    if (topic.indexOf(Stats.V) === 0) { Stats.on(topic, payload); return; }   // ★ 访客足迹
    if (topic === this.tEv()) this.onEv(o, now);
  },

  /* ---------- 历史事件大厅（broker retain 当"服务器"：跨设备、离线也在） ---------- */
  onHistMsg: function (topic, o) {
    var hid = topic.slice((this.base() + 'hist/').length);
    if (!hid || this._seen[hid]) return;
    this._seen[hid] = 1;
    o.hid = hid; o.room = this.room;
    this.hist.push(o);
    this.hist.sort(function (a, b) { return (a.at || 0) - (b.at || 0); });
    while (this.hist.length > 800) { delete this._seen[this.hist.shift().hid]; }
    if (this.onHist) this.onHist();
  },
  // 记一条历史（去中心化后由「名单第一个」写，避免多端重复；retain=true → broker 永久保存）
  histPub: function (o) {
    if (!this.connected || !this.isScribe()) return;
    try {
      var at = o.at || Date.now();
      var hid = o.hid || (at.toString(36) + Math.random().toString(36).slice(2, 6));
      delete o.hid;
      o.at = at;
      this.pub(this.tHist(hid), JSON.stringify(o), true);
      this._histN++;
      if (this._histN % 12 === 0) this.trimHist();
    } catch (e) {}
  },
  // broker 上的历史不会自己消失 → 定期清理。
  // ★ 关键：先淘汰「进入了世界」这类噪音，把击杀/Boss/波次/建房这些真正的事件留住，
  //    否则人一多，大厅会被"XXX 进入了世界"刷屏，重要记录全被挤掉。
  trimHist: function () {
    if (!this.connected) return;
    var KEEP = 400;
    if (this.hist.length <= KEEP) return;
    var noise = [], keep = [];
    for (var i = 0; i < this.hist.length; i++) {
      var h = this.hist[i];
      (h.k === 'join' ? noise : keep).push(h);
    }
    var over = this.hist.length - KEEP;
    var drop = noise.slice(0, Math.min(over, noise.length));       // 先删噪音
    if (drop.length < over) drop = drop.concat(keep.slice(0, over - drop.length));   // 不够再删老的正常记录
    var dropSet = {};
    for (var j = 0; j < drop.length; j++) { dropSet[drop[j].hid] = 1; if (drop[j].hid) { try { this.pub(this.tHist(drop[j].hid), '', true); delete this._seen[drop[j].hid]; } catch (e) {} } }
    this.hist = this.hist.filter(function (h) { return !dropSet[h.hid]; });
    if (this.onHist) this.onHist();
  },

  onEv: function (o, now) {
    if (o.id === this.id && o.k !== 'pong') return;
    switch (o.k) {
      case 'join': if (o.id !== this.id) { this.feed && this.feed('sys: ' + (o.name || '旅人') + ' 进入战场'); this.broadcast({ k: 'hi', name: this.name }); this.histPub({ k: 'join', name: o.name || '旅人', text: (o.name || '旅人') + ' 进入了世界' + (o.inv ? '（来自 ' + o.inv + ' 的邀请）' : '') }); } break;
      case 'hi': break;
      case 'ping': this.broadcast({ k: 'pong', to: o.id, t: o.t }); break;
      case 'pong': if (o.to === this.id) this.rtt = Math.max(1, Date.now() - o.t); break;
      case 'chat': this.chat.push({ name: o.name, text: o.text }); if (this.chat.length > 40) this.chat.shift(); if (this.onChat) this.onChat(); break;
      case 'hit': if (o.by !== Net.id && Net.mineMob(o.mid)) Host.damage(o.mid, o.dmg, o.by, o.byName, o.crit); break;
      case 'bosshit': if (o.by !== Net.id && Net.mineBoss(o.bid)) BossSys.damage(o.bid, o.dmg, o.by, o.byName); break;
      case 'mhit': if (o.to === Net.id) Combat.takeDamage(o.dmg, o.name, 'mob'); break;
      case 'die': this.pushFeed((o.byName || '?') + ' 击倒 ' + (o.mname || '魔物')); this.histPub({ k: 'kill', text: (o.byName || '?') + ' 击倒 ' + (o.mname || '魔物') }); if (this.onEvent) this.onEvent('die', o); break;
      case 'phit': if (o.to === this.id) Combat.takeDamage(o.dmg, o.name, 'player'); break;
      case 'pdie': this.pushFeed((o.byName || '?') + ' 击杀 ' + (o.victim || '?')); this.pushFeed2(o); this.histPub({ k: 'pkill', text: (o.byName || '?') + ' 击杀了 ' + (o.victim || '?') }); if (this.onEvent) this.onEvent('pdie', o); break;
      // ★ 房主裁决的 Boss 伤害 → 只打指定玩家
      case 'batk': if (o.to === this.id) { if (P.alive) Combat.takeDamage(o.dmg, o.name || 'Boss', 'boss'); } break;
      // ★ Boss 技能特效（各端播同一套）
      case 'bskill': {
        var _b = null; for (var _i = 0; _i < BossSys.list.length; _i++) if (BossSys.list[_i].id === o.bid) { _b = BossSys.list[_i]; break; }
        if (_b) {
          if (o.kind === 'wave') { FX.blast(_b.x, _b.y + 2, _b.z, 14, 28, 0.5); Sfx.boom(); ScreenShake.add(0.9); HUD.feed(_b.name + ' 释放 冲击波'); }
          else if (o.kind === 'summon') { HUD.feed(_b.name + ' 召唤 爪牙 x3'); Sfx.growl(110); }
        }
        break;
      }
      // ★ 弹幕出生（只同步"出生"，飞行各端自己算 → 流量≈0，视觉完全一致）
      case 'pspawn': Proj.fireDir(o.x, o.y, o.z, o.dx, o.dy, o.dz, o.sp, o.dmg, true, null, o.by); break;
      // ★ 玩家弹道（别人也能看到你开火）
      case 'pshot': FX.tracerA(V3(o.x, o.y, o.z), V3(o.tx, o.ty, o.tz)); FX.muzzle(V3(o.x, o.y, o.z)); break;
      case 'voice': Voice.addMsg({ name: o.name || '旅人', data: o.data, ms: o.ms, text: o.text, mime: o.mime }); if (o.text) Voice.speak(o.text); else if (o.data) Voice.play(o.data, o.mime); break;
      case 'nade': if (o.to) { Grenade.spawnRemote(o.x, o.y, o.z); } break;
      case 'boom': Grenade.explodeRemote(o.x, o.y, o.z, o.r); break;
    }
  },
  pushFeed: function (t) { this.feed.push(t); if (this.feed.length > 6) this.feed.shift(); if (this.onFeed) this.onFeed(); },
  pushFeed2: function (o) {},

  /* ★★ 远端玩家平滑插值 ★★
     根因修复：收到别人状态时只写了 tx/tz（目标），而渲染/小地图读的是 x/z ——
     x/z 除了第一次以外永不更新 → 别人看起来"冻在第一次那个坐标上"。
     这里每帧把 x/z 朝 tx/tz 推进，因此位置真的会变、且平滑。 */
  interp: function (dt) {
    var k = Math.min(1, dt * 12);
    this.players.forEach(function (p) {
      if (p.tx === undefined) return;
      p.x += (p.tx - p.x) * k;
      p.z += (p.tz - p.z) * k;
      if (p.ty !== undefined) p.y += (p.ty - p.y) * k;
      // 兜底：万一误差极小，直接吸附，避免长期微小漂移
      if (Math.abs(p.tx - p.x) < 0.002) p.x = p.tx;
      if (Math.abs(p.tz - p.z) < 0.002) p.z = p.tz;
    });
  },
};

/* ★★ 访客足迹（留痕）★★
   每个客户端进服时，往 broker 写一条【保留消息】`zhz/tianlei/stats/v/<唯一id>`。
   · 保留消息 = broker 永久保存 → 跨设备、离线也在、谁都能读
   · 每个访客只占一条（重复进服会覆盖自己那条，不膨胀）
   · 直接数条数 = 累计来访人数；按 at 过滤 = 今日人数
   不依赖任何服务器，保持"免登录即玩"。
   ============================================================================ */
var Stats = {
  V: 'zhz/tianlei/stats/v/',
  visits: new Map(),          // id -> {name, at, room, page, ip, pages, ...}
  mark: function () {
    // ★ 统一走指纹库留痕：名字/房间变化时补一条（不重复计 visits，不用随机 Net.id）
    if (window.Fp) { try { Fp.track(null, { name: Net.name, room: Net.room }, { nofcount: true }); return; } catch (e) {} }
    if (!Net.connected) return;
    try {
      Net.pub(this.V + Net.id, JSON.stringify({
        id: Net.id, name: Net.name, room: Net.room, at: Date.now(),
        dt: (typeof devicePixelRatio !== 'undefined' ? devicePixelRatio : 1),
        ua: (navigator.userAgent || '').slice(0, 64)
      }), true);
    } catch (e) {}
  },
  on: function (topic, payload) {
    var id = topic.slice(this.V.length); if (!id) return;
    try {
      var o = JSON.parse(payload || '{}');
      this.visits.set(id, {
        name: o.name, at: o.at || 0, room: o.room, page: o.page || '',
        ip: o.ip || '', ipMode: o.ipMode || '', geo: o.geo || '', org: o.org || '',
        plat: o.plat || '', tz: o.tz || '', scr: o.scr || '', mobile: o.mobile,
        pages: o.pages || {}, v: o.visits || 0, fp: o.fp || ''
      });
    } catch (e) {}
    this.render();
  },
  count: function () { return this.visits.size; },
  today: function () {
    var d0 = new Date(); d0.setHours(0, 0, 0, 0); var n = 0;
    this.visits.forEach(function (v) { if ((v.at || 0) >= d0.getTime()) n++; });
    return n;
  },
  list: function () { var a = []; this.visits.forEach(function (v, id) { a.push({ id: id, name: v.name, at: v.at, room: v.room, page: v.page, ip: v.ip, geo: v.geo, plat: v.plat, tz: v.tz, scr: v.scr, mobile: v.mobile, pages: v.pages, v: v.v, fp: v.fp }); }); return a.sort(function (x, y) { return (y.at || 0) - (x.at || 0); }); },
  siteCount: function () { var n = 0; this.visits.forEach(function (v) { if (v.pages && v.pages.site) n++; }); return n; },
  gameCount: function () { var n = 0; this.visits.forEach(function (v) { if (v.pages && v.pages.game) n++; }); return n; },
  render: function () {
    var t = $('visitChip');
    if (t) t.textContent = '👣 访客 ' + this.count() + (this.today() ? ' · 今日 ' + this.today() : '');
  },
  show: function () {
    var el = document.getElementById('visitPanel');
    if (!el) {
      el = document.createElement('div'); el.id = 'visitPanel';
      el.style.cssText = 'position:fixed;right:12px;top:104px;z-index:40;width:min(52vw,460px);max-height:62vh;overflow:auto;' +
        'background:rgba(10,8,22,.95);border:1px solid rgba(168,85,247,.45);border-radius:12px;padding:12px 14px;color:#e8e0ff;' +
        'font:13px/1.65 system-ui,sans-serif;box-shadow:0 10px 34px rgba(0,0,0,.6)';
      document.body.appendChild(el);
    }
    var rows = this.list();
    var h = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">' +
      '<b>👣 累计访客 ' + rows.length + '</b>' +
      '<span style="opacity:.8">今日 ' + this.today() + '</span>' +
      '<span id="vpClose" style="cursor:pointer;padding:0 6px">✕</span></div>' +
      '<div style="opacity:.7;font-size:11.5px;margin-bottom:8px">官网 ' + this.siteCount() + ' 人 · 游戏 ' + this.gameCount() + ' 人 · ' +
      '指纹去重（换浏览器/清缓存仍是同一人）· 人物记录与游戏存档分开，清档不影响</div>';
    if (!rows.length) h += '<div style="opacity:.6">暂无记录（你自己这条要先连上才有）</div>';
    rows.slice(0, 300).forEach(function (v) {
      var t = v.at ? new Date(v.at).toLocaleString('zh-CN') : '';
      var tags = []; if (v.pages && v.pages.site) tags.push('官网'); if (v.pages && v.pages.game) tags.push('游戏');
      var dev = [v.plat || '', v.scr || '', v.tz || '', (v.mobile ? '手机' : '电脑')].filter(Boolean).join(' · ');
      h += '<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,.06)">' +
        '<div>' + (v.name || '（无名）') +
        ' <span style="opacity:.5;font-size:11.5px">' + t + (v.room ? ' · ' + v.room : '') + '</span>' +
        (tags.length ? ' <span style="font-size:11px;color:#a7f">[' + tags.join('/') + ']</span>' : '') + '</div>' +
        '<div style="opacity:.5;font-size:11px">' + (v.ip ? ('IP ' + v.ip + (v.geo ? ' · ' + v.geo : '')) : 'IP 未取到') +
        (dev ? ' · ' + dev : '') + '</div></div>';
    });
    el.innerHTML = h; el.style.display = 'block';
    var c = document.getElementById('vpClose'); if (c) c.onclick = function () { el.style.display = 'none'; };
  },
  // ★ 只清游戏数据（战绩/建造/时长），人物记录一律不动
  wipeGame: function () {
    var rm = (window.Fp ? Fp.wipeGame() : []);
    HUD.center('🗑 已清理本地游戏战绩', '人物记录(访客/指纹)完整保留 —— ' + (rm.length ? rm.join(',') : '本来就空'), 2600);
  },
};

/* ★★ 存档（本地持久：战绩 / 建造 / 游玩时长 / 回归欢迎）★★
   为什么需要：玩家"来一次就走"的最大原因是没有舍不得走的理由。
   这里把跨局累计的战绩留在本地，回来就能看到"我上次砍了多少只 / 建了多少块"。
   （建造方块本身是 MQTT 保留消息 → 全服持久；这里存的是"个人累计"数字。）
   ============================================================================ */
var Save = {
  K: 'tianlei_save', d: null, _b: {},
  load: function () {
    var o = null; try { o = JSON.parse(localStorage.getItem(this.K) || 'null'); } catch (e) {}
    this.d = o || { totalKills: 0, totalDeaths: 0, totalScore: 0, bestWave: 1, bestScore: 0, totalBuilds: 0, playSec: 0, sessions: 0, firstAt: Date.now(), lastAt: 0 };
    return this.d;
  },
  begin: function () {
    this._b = { k: P.kills, d: P.deaths, s: P.score, b: Build.list.size, t: performance.now() };
    this.d.sessions = (this.d.sessions || 0) + 1; this.d.lastAt = Date.now();
    this.chip(); this.welcome();
  },
  flush: function () {
    if (!this.d || !this._b.t) return;
    var d = this.d, k = P.kills - this._b.k, dd = P.deaths - this._b.d, s = P.score - this._b.s, b = Build.list.size;
    if (k > 0) d.totalKills += k;
    if (dd > 0) d.totalDeaths += dd;
    if (s > 0) d.totalScore += s;
    if (b > this._b.b) d.totalBuilds += (b - this._b.b);
    this._b.k = P.kills; this._b.d = P.deaths; this._b.s = P.score; this._b.b = b;
    if (Host.wave > (d.bestWave || 1)) d.bestWave = Host.wave;
    if (P.score > (d.bestScore || 0)) d.bestScore = P.score;
    var now = performance.now(); d.playSec = (d.playSec || 0) + Math.round((now - this._b.t) / 1000); this._b.t = now;
    try { localStorage.setItem(this.K, JSON.stringify(d)); } catch (e) {}
    this.chip();
  },
  chip: function () { var c = $('saveChip'); if (c && this.d) c.textContent = '🏆 累计击杀 ' + this.d.totalKills + ' · 建造 ' + this.d.totalBuilds; },
  welcome: function () {
    var d = this.d;
    if (!d || (d.sessions <= 1 && !d.totalKills)) { this.chip(); return; }   // 首次进入不弹
    HUD.center('🏆 欢迎回来', '累计击杀 ' + d.totalKills + ' · 最高波次 ' + (d.bestWave || 1) + ' · 共建造 ' + d.totalBuilds + ' 块 · 第 ' + d.sessions + ' 次进入', 3800);
  },
  line: function () {
    var d = this.d; if (!d) return '';
    return '🏆 累计击杀 ' + d.totalKills + ' · 累计积分 ' + d.totalScore + ' · 最高波次 ' + (d.bestWave || 1) +
      ' · 建造 ' + d.totalBuilds + ' 块 · 游玩 ' + Math.floor((d.playSec || 0) / 60) + ' 分钟 · 共进入 ' + d.sessions + ' 次';
  },
};

var TEAM_COLS = [0xff6b6b, 0x4ecdc4, 0xffd166, 0x9b5de5, 0x00bbf9, 0xf15bb5, 0x7bed9f, 0xff9f1c];
Net.teamColor = function (id) {
  var h = 0; for (var i = 0; i < (id || '').length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return TEAM_COLS[h % TEAM_COLS.length];
};
Net.teamColorHex = function (id) { return '#' + ('000000' + Net.teamColor(id).toString(16)).slice(-6); };
Net.nameOf = function (id) { var p = this.players.get(id); return (p && p.name) || id; };


/* ============================== 玩家 + 第三人称可旋转相机 ============================== */
var P = {
  x: 78, z: 78, y: 0, yaw: 0, vy: 0, onGround: true,
  hp: 100, maxHp: 100, armor: 40, alive: true, respawnAt: 0,
  weapon: 'rifle', ammo: {}, reserve: {}, reloading: 0, fireCd: 0, ads: false, crouch: false,
  score: 0, kills: 0, deaths: 0, nade: 3, nadeCd: 0, walk: 0, moving: false, team: 0,
  lastHurt: 0, lastAttacker: '', spawn: { x: 78, z: 78 },
};
function resetAmmo() { P.ammo = {}; P.reserve = {}; WEAPONS.forEach(function (w) { P.ammo[w.id] = w.mag; P.reserve[w.id] = w.reserve; }); }

var Cam = { yaw: 0, pitch: -0.30, dist: 4.9, adsDist: 2.6, mode: 'center', autoAim: false, shake: V3(0, 0, 0),
  fp: false, fpEye: 1.62, _bob: 0 };        // ★ 第一人称：相机直接贴在眼睛上（点 1P 按钮切换）
function pitchLim() { return Cam.fp ? [-1.30, 1.30] : [-1.15, 0.75]; }   // ★ 第一人称允许抬头看天
function clampPitch(v) { var l = pitchLim(); return clamp(v, l[0], l[1]); }
var Recoil = { p: 0, y: 0 };   // ★ 后坐力偏移（独立于玩家俯仰 → 瞄准辅助无法抵消它）
function camDir(out) {
  out = out || V3(0, 0, 0);
  if (A.getCamMode() === 'hd2d') { out.copy(A.CAM_DIR).negate(); return out.normalize(); }   // HD-2D：固定 45°
  var yaw = Cam.yaw + Recoil.y, pitch = clamp(Cam.pitch + Recoil.p, -1.34, Cam.fp ? 1.34 : 1.0);
  var cp = Math.cos(pitch);
  out.set(Math.sin(yaw) * cp, Math.sin(pitch), Math.cos(yaw) * cp);
  return out.normalize();
}
var _cd = V3(0, 0, 0), _cp = V3(0, 0, 0);
function updateCamera(dt) {
  if (A.getCamMode() === 'hd2d') {                          // ★ HD-2D：正交 45° 锁死，跟随玩家
    var oc = A.orthoCam, D = A.CAM_DIR;
    oc.position.set(P.x + D.x * 220, P.y + D.y * 220 + 1.0, P.z + D.z * 220);
    oc.lookAt(P.x, P.y + 1.0, P.z);
    return;
  }
  /* ★★★ 第一人称：相机 = 眼睛（点 1P 切换）。第三人称那条路径一行不动 ★★★ */
  if (Cam.fp) {
    Cam._bob += dt;
    var eyeY = P.y + (P.crouch ? 1.04 : Cam.fpEye);
    if (P.alive) eyeY += P.moving ? Math.abs(Math.sin(Cam._bob * 9)) * 0.035 : Math.sin(Cam._bob * 2.2) * 0.012;   // 走路微晃
    camDir(_cd);                                           // 含后坐力 → 枪口上抬时画面真的会抬
    var shf = ScreenShake.amt;
    var fx0 = P.x + rnd(-shf, shf) * 0.06, fy0 = eyeY + rnd(-shf, shf) * 0.06, fz0 = P.z + rnd(-shf, shf) * 0.06;
    // ★ 头别埋进墙里：眼睛朝后 0.5m 就撞墙（贴着墙站）时把相机往身体里收一点
    var hb = G.ray(fx0, fy0, fz0, -_cd.x, -_cd.y, -_cd.z, 0.5);
    if (hb.dist < 0.32) { var kb = 0.32 - hb.dist; fx0 -= _cd.x * kb; fy0 -= _cd.y * kb; fz0 -= _cd.z * kb; }
    cam().position.set(fx0, fy0, fz0);
    _cp.set(fx0 + _cd.x, fy0 + _cd.y, fz0 + _cd.z);
    cam().lookAt(_cp);
    var fovF = P.ads ? 55 : 78;                            // 第一人称视野略大一点（默认比过肩宽）
    cam().fov += (fovF - cam().fov) * Math.min(1, dt * 10); cam().updateProjectionMatrix();
    return;
  }
  // ★ 附近有巨物 Boss → 相机自动拉远，保证「巨物 + 渺小玩家」同框（透视压迫感）
  var _bn = null, _bd = 1e9;
  for (var _i = 0; _i < BossSys.list.length; _i++) { var _b = BossSys.list[_i]; if (_b.spawned && _b.alive) { var _d = Math.hypot(P.x - _b.x, P.z - _b.z); if (_d < _bd) { _bd = _d; _bn = _b; } } }
  var _base = clamp(Cam.distV !== undefined ? (Cam.distV * 0.40 + 1.5) : 4.9, 2.5, 30);   // ★ 滑条值
  Cam.dist = _bn ? clamp(Math.max(_base, 6) + _bn.def.scale * 0.45, 6, 34) : _base;   // 有巨物 Boss 时至少 6m 才装得下
  var tx = P.x, ty = P.y + (P.crouch ? 1.1 : 1.5), tz = P.z;
  camDir(_cd);
  var dist = P.ads ? Cam.adsDist : Cam.dist;
  // ★ 过肩视角：相机偏到角色右肩外侧 → 角色落在屏幕左下，屏幕中心准星指向远方（不再"压在头上"）
  var shoulder = (Cam.mode === 'shoulder' && !P.ads) ? 0.95 : 0.0;
  var rise = P.ads ? 0.10 : (Cam.mode === 'center' ? 1.15 : 0.28);   // 居中模式：相机抬高 → 角色落到屏幕中下，准星在头顶远方
  var rx = -Math.cos(Cam.yaw), rz = Math.sin(Cam.yaw);               // 屏幕右方向（世界）
  var cx = tx - _cd.x * dist + rx * shoulder, cz = tz - _cd.z * dist + rz * shoulder, cy = ty - _cd.y * dist + rise;
  // 相机防穿墙/穿地
  var dx = cx - tx, dy = cy - ty, dz = cz - tz, L = Math.hypot(dx, dy, dz) || 1;
  var hit = G.ray(tx, ty, tz, dx / L, dy / L, dz / L, L + 0.25);
  if (hit.dist < L + 0.05) { var k = Math.max(0.7, hit.dist - 0.35); cx = tx + dx / L * k; cy = ty + dy / L * k; cz = tz + dz / L * k; }
  var sh = ScreenShake.amt;
  cam().position.set(cx + rnd(-sh, sh) * 0.14, cy + rnd(-sh, sh) * 0.14, cz + rnd(-sh, sh) * 0.14);
  _cp.set(cam().position.x + _cd.x, cam().position.y + _cd.y, cam().position.z + _cd.z);
  cam().lookAt(_cp);
  var fov = P.ads ? 52 : 74; cam().fov += (fov - cam().fov) * Math.min(1, dt * 10); cam().updateProjectionMatrix();
}
/* 玩家立绘 */
var heroMat = null, heroMesh = null, heroShadow = null, heroBar = null;
function buildHero() {
  heroMat = spriteMat(CH.S, { amb: 0.7, tint: 0xffffff });
  heroMesh = makeBillboard(2.05, heroMat); actionScene.add(heroMesh);
  heroShadow = addShadow(1.5); actionScene.add(heroShadow);
  heroBar = makeHpBar(1.6); actionScene.add(heroBar);
}
var _F = V3(0, 0, 0);
/* 把「世界朝向 yaw」换算成「屏幕方向」再取立绘（相机在动，必须投影到相机坐标系） */
function facingDir(x, z, yaw, camPos) {
  var fx = x - camPos.x, fz = z - camPos.z, fl = Math.hypot(fx, fz) || 1;
  fx /= fl; fz /= fl;                       // 相机 → 目标 的水平朝向（F）
  var vx = Math.sin(yaw), vz = Math.cos(yaw);   // 角色朝向（世界）
  var sx = vx * fz - vz * fx;               // 屏幕右分量（sprite 局部 +X 的世界朝向 = (fz,-fx)）
  var sy = vx * fx + vz * fz;               // 屏幕「远离」分量（sprite 局部 +Z 的世界朝向 = (fx,fz)）
  return dirFromAngle(norm360(Math.atan2(sx, -sy) * 180 / Math.PI));
}
function updateHero(dt, t, camYawAz) {
  if (!heroMesh) return;
  heroMesh.visible = !Cam.fp;                 // ★ 第一人称：把自己藏掉（影子留着，低头有影子才不假）
  heroMesh.position.set(P.x, P.y, P.z);
  heroMesh.rotation.y = billboardYaw(P.x, P.z);
  var d = facingDir(P.x, P.z, P.yaw, cam().position);
  if (CH[d] && heroMat.uniforms.uMap.value !== CH[d]) heroMat.uniforms.uMap.value = CH[d];
  var bob = P.moving ? Math.abs(Math.sin(t * 9)) * 0.06 : Math.sin(t * 2.2) * 0.02;
  heroMesh.scale.set(1, 1 + bob, 1);
  heroShadow.position.set(P.x, G.h(P.x, P.z) + 0.04, P.z);
  heroShadow.scale.setScalar(P.moving ? 1.05 : 1.0);
  heroBar.position.set(P.x, P.y + 2.35, P.z);
  heroBar.visible = false;
}

/* ============================== 刷怪 / 魔物模拟（Host） ============================== */
var Host = {
  mobs: [], nextId: 1, wave: 1, waveKills: 0, waveNeed: 12, maxAlive: 20, snapAcc: 0,
  SNAP_HZ: 5,          // ★ 快照降频 10Hz→5Hz（客户端有插值，看不出来，流量减半）
  CULL_R: 90,          // ★ 只同步「任何玩家 90 格内」的怪
  HARD_CAP: 40,        // ★ 同屏存活硬上限（防止刷爆把房间拖死）
  init: function () { if (SANDBOX) return; for (var i = 0; i < 9; i++) this.spawnAuto(true); },
  spawn: function (kind, x, z) {
    var def = MOBS[kind];
    // ★ 去中心化：id 里带归属者前缀 → 谁生成的就是谁的（前缀即所有权，无需协商）
    var m = { id: Net.id + '-M' + (this.nextId++), kind: kind, def: def, x: x, z: z, y: def.fly, hp: 0, maxHp: 0, alive: true,
      homeX: x, homeZ: z, yaw: 0, atkAt: 0, respawnAt: 0, moving: false, kx: 0, kz: 0, slow: 0, seed: Math.random() * 10, obj: null, mat: null, hpS: null, flash: 0 };
    m.maxHp = m.hp = def.hp * (1 + (this.wave - 1) * 0.16);
    this.mobs.push(m); return m;
  },
  spawnAuto: function () { if (SANDBOX) return; var k = MOB_KEYS[Math.floor(Math.random() * 3)]; var s = G.pick(P.x, P.z, 18); return this.spawn(k, s.x, s.z); },
  damage: function (mid, dmg, by, byName, crit) {
    var m = null; for (var i = 0; i < this.mobs.length; i++) if (this.mobs[i].id === mid) { m = this.mobs[i]; break; }
    if (!m || !m.alive) return;
    m.hp -= dmg; m.flash = 0.1;
    if (m.hp <= 0) {
      m.hp = 0; m.alive = false;
      m.respawnAt = Date.now() + 9000;
      FX.imp(V3(m.x, m.y + m.def.hitY, m.z), true);
      Sfx.growl(m.kind === 'golem' ? 70 : 130);
      Net.broadcast({ k: 'die', mid: m.id, mname: m.def.name, by: by, byName: byName });
      Net.histPub({ k: 'kill', text: (byName || '?') + ' 击倒 ' + m.def.name });
      if (by === Net.id) { P.score += m.def.score; P.kills++; HUD.feed('击杀 ' + m.def.name + '  +' + m.def.score); Sfx.kill(); }
      this.waveKills++;
      if (this.waveKills >= this.waveNeed) { this.waveKills = 0; this.wave++; this.waveNeed = 12 + this.wave * 4; this.maxAlive = Math.min(this.HARD_CAP, 12 + this.wave); HUD.center('第 ' + this.wave + ' 波', '魔物变强了'); Sfx.waveUp(); Net.histPub({ k: 'wave', text: '全服进入第 ' + this.wave + ' 波（魔物变强）' }); }
    }
  },
  update: function (dt, targets) {
    if (SANDBOX) return;
    var now = Date.now();
    for (var i = 0; i < this.mobs.length; i++) {
      var m = this.mobs[i];
      /* ★ 去中心化：只模拟「我名下」的怪；别人名下的做插值复现（不跑 AI，避免各算各的） */
      if (m.remote) {
        if (!m.alive) continue;
        m.x = lerp(m.x, m._rx !== undefined ? m._rx : m.x, Math.min(1, dt * 9));
        m.z = lerp(m.z, m._rz !== undefined ? m._rz : m.z, Math.min(1, dt * 9));
        var fY = G.h(m.x, m.z);
        m.y = m.def.fly > 0 ? fY + m.def.fly + Math.sin(now / 620 + m.seed) * 0.18 : fY;
        continue;
      }
      if (!m.alive) {
        if (now >= m.respawnAt && this.mobs.length <= this.maxAlive + 6 && this.aliveCount() < this.HARD_CAP) {
          var s = G.pick(P.x, P.z, 20);
          m.x = s.x; m.z = s.z; m.homeX = s.x; m.homeZ = s.z; m.maxHp = m.hp = m.def.hp * (1 + (this.wave - 1) * 0.16);
          m.alive = true;
        }
        continue;
      }
      var def = m.def, tgt = null, bd = def.aggro;
      for (var t = 0; t < targets.length; t++) { var tg = targets[t]; if (!tg || tg.hp <= 0) continue; var d = Math.hypot(tg.x - m.x, tg.z - m.z); if (d < bd) { bd = d; tgt = tg; } }
      m.moving = false;
      if (m.kx || m.kz) {                                  // ★ 击退惯性（先被推，再执行 AI）
        var kxn = m.x + m.kx * dt, kzn = m.z + m.kz * dt;
        if (G.canStand(kxn, m.z, m.y, 1.0)) m.x = kxn; else m.kx = 0;
        if (G.canStand(m.x, kzn, m.y, 1.0)) m.z = kzn; else m.kz = 0;
        var dk = Math.exp(-dt * 5.5); m.kx *= dk; m.kz *= dk;
        if (Math.abs(m.kx) < 0.06) m.kx = 0; if (Math.abs(m.kz) < 0.06) m.kz = 0;
        m.moving = true;
      }
      if (m.slow > 0) m.slow -= dt;
      var spMul = m.slow > 0 ? 0.38 : 1;
      if (tgt) {
        var dx = tgt.x - m.x, dz = tgt.z - m.z, dl = Math.hypot(dx, dz) || 1;
        m.yaw = Math.atan2(dx, dz);
        if (dl > def.atkRange) {
          var sp = def.speed * (1 + (this.wave - 1) * 0.03) * spMul, nx = m.x + dx / dl * sp * dt, nz = m.z + dz / dl * sp * dt;
          if (G.canStand(nx, m.z, def.fly > 0 ? 99 : m.y, 0.7)) m.x = nx;
          if (G.canStand(m.x, nz, def.fly > 0 ? 99 : m.y, 0.7)) m.z = nz;
          m.moving = true;
        } else if (now - m.atkAt > def.atkCd * 1000) {
          m.atkAt = now;
          if (def.ranged) Proj.fire(m, tgt);
          else {
            if (tgt.id === Net.id) Combat.takeDamage(def.dmg, def.name, 'mob');
            else Net.broadcast({ k: 'mhit', to: tgt.id, dmg: def.dmg, name: def.name });
            FX.imp(V3(tgt.x, tgt.y + 1.0, tgt.z), false); Sfx.growl(m.kind === 'golem' ? 80 : 150);
          }
        }
      } else {
        var w = Math.sin(now / 1400 + m.seed) * 6.28;
        var wx = Math.cos(w) * def.speed * 0.4 * dt, wz = Math.sin(w) * def.speed * 0.4 * dt;
        var hx = Math.hypot(m.x - m.homeX, m.z - m.homeZ);
        if (hx > 14) { wx += (m.homeX - m.x) / hx * def.speed * dt; wz += (m.homeZ - m.z) / hx * def.speed * dt; }
        if (G.canStand(m.x + wx, m.z + wz, def.fly > 0 ? 99 : m.y, 0.7)) { m.x += wx; m.z += wz; m.moving = true; }
        m.yaw += Math.sin(now / 900 + m.seed) * 0.2 * dt;
      }
      var floorY = G.h(m.x, m.z);
      var ty2 = def.fly > 0 ? floorY + def.fly + Math.sin(now / 620 + m.seed) * 0.18 : floorY;
      m.y += (ty2 - m.y) * Math.min(1, dt * 6);
      if (m.flash > 0) m.flash -= dt;
    }
  },
  knock: function (m, dir, force) {
    if (!m || !m.alive) return;
    var hx = dir.x, hz = dir.z, L = Math.hypot(hx, hz) || 1; hx /= L; hz /= L;
    var imp = (force || 1) / (m.def.mass || 1);
    m.kx = (m.kx || 0) + hx * imp * 5.2; m.kz = (m.kz || 0) + hz * imp * 5.2;
    m.slow = 0.35;
  },
  aliveCount: function () { var n = 0; for (var i = 0; i < this.mobs.length; i++) if (this.mobs[i].alive) n++; return n; },
  // ★ 只同步"任何玩家附近"的怪（远处的不发），并带一个校验和用于发现不同步
  snapshot: function () {
    var pts = [{ x: P.x, z: P.z }];
    Net.players.forEach(function (rp) { if (rp.alive) pts.push({ x: rp.x, z: rp.z }); });
    var o = [], sum = 0, R = this.CULL_R * this.CULL_R;
    for (var i = 0; i < this.mobs.length; i++) {
      var m = this.mobs[i];
      if (!m.alive || m.remote) continue;                              // ★ 只广播自己名下的怪
      var near = false;
      for (var j = 0; j < pts.length; j++) { var ddx = m.x - pts[j].x, ddz = m.z - pts[j].z; if (ddx * ddx + ddz * ddz < R) { near = true; break; } }
      if (!near) continue;
      var a = [m.id, MOB_KEYS.indexOf(m.kind), +m.x.toFixed(1), +m.z.toFixed(1), Math.round(m.hp), Math.round(m.maxHp)];
      o.push(a);
      sum = (sum + a[2] * 31 + a[3] * 17 + a[4]) | 0;                 // ★ 状态哈希（校验用）
    }
    this._hash = sum;
    return o;
  },
  applySnapshot: function (list) {
    var now = performance.now();
    for (var i = 0; i < list.length; i++) {
      var a = list[i], id = a[0], kind = MOB_KEYS[a[1]] || 'floater';
      if (Net.mobOwner(id) === Net.id) continue;                       // ★ 我名下的怪以我为准，忽略别人的副本
      var m = null; for (var j = 0; j < this.mobs.length; j++) if (this.mobs[j].id === id) { m = this.mobs[j]; break; }
      if (!m) {
        var def = MOBS[kind];
        m = { id: id, kind: kind, def: def, x: a[2], z: a[3], y: def.fly, hp: a[4], maxHp: a[5], alive: true, obj: null, mat: null, hpS: null, seed: Math.random() * 10, remote: true, _rx: a[2], _rz: a[3], moving: false, flash: 0 };
        this.mobs.push(m);
      }
      m._t = now; m._rx = a[2]; m._rz = a[3];
      var wasAlive = m.alive;
      m.alive = true;
      if (m.hp !== a[4]) { m.hp = a[4]; m.maxHp = a[5]; }
      if (!wasAlive) { m.x = a[2]; m.z = a[3]; m.kx = 0; m.kz = 0; }
    }
    // ★ 超时清理：某个归属者 3.5s 没再发它的怪 → 移除此副本（掉线/走远）
    for (var k = this.mobs.length - 1; k >= 0; k--) {
      var mm = this.mobs[k];
      if (mm.remote && now - (mm._t || 0) > 3500) this.mobs.splice(k, 1);
    }
  },
  interp: function (dt) {
    var now = Date.now();
    for (var i = 0; i < this.mobs.length; i++) {
      var m = this.mobs[i]; if (!m.remote || !m.alive) continue;
      m.x = lerp(m.x, m._rx !== undefined ? m._rx : m.x, Math.min(1, dt * 9));
      m.z = lerp(m.z, m._rz !== undefined ? m._rz : m.z, Math.min(1, dt * 9));
      var floorY = G.h(m.x, m.z);
      m.y = m.def.fly > 0 ? floorY + m.def.fly + Math.sin(now / 620 + m.seed) * 0.18 : floorY;
      /* 位置由 MobRender 池统一写 */
    }
  },
  each: function (fn) { for (var i = 0; i < this.mobs.length; i++) if (this.mobs[i].alive) fn(this.mobs[i]); },
};

/* ============================== 星 Boss 系统（4 个巨物，透视压迫感） ============================== */
var BossSys = {
  list: [], active: null, nextId: 1,
  init: function () {
    var self = this; this.list = []; this.nextId = 1;      // ★ 每次重建都复位 id，避免 B1..B4/B5..B8 叠代错位
    var ring = [[1, 1], [1, -1], [-1, 1], [-1, -1]];      // 四个方向
    BOSSES.forEach(function (b, bi) {
      var def = { key: 'boss', name: b.name, hp: b.hp, dmg: b.dmg, speed: b.spd, aggro: 60,
        atkRange: b.scale * 0.40, atkCd: 2.4, fly: 0, hitY: b.scale * 0.45, hitR: b.scale * 0.40, hitW: b.scale * 0.40, scale: b.scale, score: 500 };
      var mat = spriteMat(BOSS_TEX[b.id], { amb: 0.65 });
      var obj = makeBillboard(b.scale, mat); obj.visible = false;
      var hpS = makeHpBar(b.scale * 0.42); obj.add(hpS); hpS.position.y = b.scale * 0.98;
      var sh = addShadow(b.scale * 0.6); actionScene.add(sh); obj.userData.sh = sh;
      actionScene.add(obj);
      // ★ 测试期：直接放在玩家出生点四周 26~36m，进游戏即可见（不再需要走近激活）
      var a = ring[bi % 4];
      var bx = clamp(P.x + a[0] * rnd(26, 36), 14, G.GW * G.TILE - 14);
      var bz = clamp(P.z + a[1] * rnd(26, 36), 14, G.GH * G.TILE - 14);
      obj.visible = !SANDBOX; sh.visible = !SANDBOX;      // ★ 沙盒模式：Boss 不出现
      self.list.push({ id: 'B' + (self.nextId++), def: def, name: b.name, tag: b.tag,
        x: bx, z: bz, kx: 0, kz: 0, y: G.h(bx, bz), hp: b.hp, maxHp: b.hp, alive: !SANDBOX, spawned: !SANDBOX,
        obj: obj, mat: mat, hpS: hpS, sh: sh, atkAt: 0, skillAt: 0, flash: 0, phase: 1 });
    });
  },
  activate: function (b) {
    b.spawned = true; b.alive = true; b.hp = b.maxHp;
    b.obj.visible = true; b.sh.visible = true; drawHp(b.hpS, 1, b.name, '#ffd166');
    HUD.center('锚点觉醒 · ' + b.name, b.tag, 2200);
    Sfx.growl(60); ScreenShake.add(1.0);
    for (var i = 0; i < 10; i++) FX.imp(V3(b.x + rnd(-4, 4), G.h(b.x, b.z) + rnd(0.5, 4), b.z + rnd(-4, 4)), true);
  },
  damage: function (bid, dmg, by, byName) {
    var b = null; for (var i = 0; i < this.list.length; i++) if (this.list[i].id === bid) { b = this.list[i]; break; }
    if (!b || !b.alive) return;
    b.hp -= dmg; b.flash = 0.1;
    drawHp(b.hpS, b.hp / b.maxHp, b.name, '#ffd166');
    var ph = b.hp / b.maxHp > 0.66 ? 1 : (b.hp / b.maxHp > 0.33 ? 2 : 3);
    if (ph > b.phase) { b.phase = ph; HUD.center(b.name + ' · 第 ' + b.phase + ' 阶段', '攻势更猛', 1600); Sfx.growl(50); }
    if (b.hp <= 0) {
      b.hp = 0; b.alive = false; b.spawned = false; b.obj.visible = false; b.sh.visible = false;
      FX.blast(b.x, b.y + 3, b.z, 16, 34, 0.7); Sfx.boom(); ScreenShake.add(1.2);
      for (var k = 0; k < 12; k++) FX.imp(V3(b.x + rnd(-5, 5), b.y + rnd(0.5, 5), b.z + rnd(-5, 5)), true);
      HUD.feed('★ 击破锚点 · ' + b.name + '  +500'); HUD.center('锚点已破 · ' + b.name, '+500 分', 2600);
      Net.histPub({ k: 'boss', boss: b.name, text: '【全服】' + (byName || '?') + ' 击破了结界锚点 · ' + b.name + '！' });
      if (by === Net.id) { P.score += 500; P.kills++; }
      if (this.active === b) this.active = null;
    }
  },
  /* ★★ 权威分离 ★★
     以前：每台设备各自跑 Boss 的 AI（技能还用 Math.random 抽），
           结果"我这躲开了、他那边判定打中"——各看各的，根本不是一个 Boss。
     现在：只有房主模拟；其他人收 10Hz 快照做插值 + 收事件播同一套特效。 */
  /* ★ 去中心化权威：不再有"房主"，谁归属谁模拟 ★★ */
  isAuth: function (b) { return !Net.connected || Net.mineBoss(b && (b.id || b)); },

  // ★ 修复：此前 Combat.fire 调用了从未定义的 BossSys.knock → 打 Boss 时抛异常中断开火（老 bug）
  knock: function (b, dir, force) { if (b && b.alive) FX.knock(b, dir, force); },

  // 归属者裁决伤害：自己吃 / 广播给指定玩家
  hurtPlayer: function (pid, dmg, name) {
    if (!pid) return;
    if (pid === Net.id || !Net.connected) { if (P.alive) Combat.takeDamage(dmg, name || 'Boss', 'boss'); return; }
    Net.broadcast({ k: 'batk', to: pid, dmg: dmg, name: name || 'Boss' });
  },

  pushSnap: function () {
    if (!Net.connected) return;
    var a = [];
    for (var i = 0; i < this.list.length; i++) {
      var b = this.list[i];
      if (!Net.mineBoss(b.id)) continue;                 // ★ 只广播我名下这个 Boss
      a.push([b.id, +b.x.toFixed(1), +b.z.toFixed(1), Math.round(b.hp), b.phase,
              b.alive ? 1 : 0, b.spawned ? 1 : 0, (b.flash > 0) ? 1 : 0]);
    }
    if (!a.length) return;
    Net.pub(Net.tBoss(), JSON.stringify({ m: a }), false);
  },

  applySnap: function (list) {
    for (var i = 0; i < list.length; i++) {
      var a = list[i], b = null;
      if (Net.mineBoss(a[0])) continue;                  // ★ 我名下这个 Boss 以我为准，忽略别人的副本
      for (var j = 0; j < this.list.length; j++) if (this.list[j].id === a[0]) { b = this.list[j]; break; }
      if (!b) continue;
      b.tx = a[1]; b.tz = a[2];
      b.hp = a[3]; b.phase = a[4];
      var was = b.alive;
      b.alive = !!a[5]; b.spawned = !!a[6];
      if (a[7]) b.flash = 0.1;
      if (was && !b.alive) { FX.blast(b.x, b.y + 3, b.z, 16, 34, 0.7); Sfx.boom(); ScreenShake.add(1.0); }
      if (!was && b.alive) { /* 归属者激活了它 */ }
    }
  },

  update: function (dt) {
    if (SANDBOX) return;
    if (Net.connected) { this.simLocal(dt); this.simRemote(dt); } else this.simLocal(dt);
    var act = this.active, bar = $('bossBar');
    if (act && act.alive && act.spawned && Math.hypot(P.x - act.x, P.z - act.z) < 70) {
      bar.style.display = 'block';
      $('bossName').textContent = act.name;
      $('bossTag').textContent = act.tag + ' · ' + Math.ceil(act.hp) + ' / ' + act.maxHp;
      $('bossHpFill').style.width = clamp(act.hp / act.maxHp, 0, 1) * 100 + '%';
    } else bar.style.display = 'none';
  },

  // ---- 我名下：完整模拟 ----
  simLocal: function (dt) {
    var now = performance.now();
    for (var i = 0; i < this.list.length; i++) {
      var b = this.list[i];
      if (!Net.mineBoss(b.id)) continue;
      var d = Math.hypot(P.x - b.x, P.z - b.z);
      if (!b.spawned && b.alive && d < 30 && P.alive) this.activate(b);
      if (!b.spawned || !b.alive) continue;
      var def = b.def;
      // ★ 追最近的玩家（不只自己）
      var tgt = { x: P.x, z: P.z, id: Net.id }, bd = d;
      Net.players.forEach(function (rp) {
        if (!rp.alive) return;
        var dd = Math.hypot(rp.x - b.x, rp.z - b.z);
        if (dd < bd) { bd = dd; tgt = { x: rp.x, z: rp.z, id: rp.id }; }
      });
      if (bd > def.atkRange && bd < 24) {
        var sp2 = def.speed * (1 + (b.phase - 1) * 0.25);
        var nx = b.x + (tgt.x - b.x) / bd * sp2 * dt, nz = b.z + (tgt.z - b.z) / bd * sp2 * dt;
        if (G.canStand(nx, b.z, b.y, 2.0)) b.x = nx;
        if (G.canStand(b.x, nz, b.y, 2.0)) b.z = nz;
      }
      if (b.kx || b.kz) { var kx2 = b.x + b.kx * dt, kz2 = b.z + b.kz * dt; if (G.canStand(kx2, b.z, b.y, 2.0)) b.x = kx2; if (G.canStand(b.x, kz2, b.y, 2.0)) b.z = kz2; var dk2 = Math.exp(-dt * 6); b.kx *= dk2; b.kz *= dk2; }
      b.y += (G.h(b.x, b.z) - b.y) * Math.min(1, dt * 5);
      b.obj.position.set(b.x, b.y, b.z);
      b.obj.rotation.y = billboardYaw(b.x, b.z);
      b.sh.position.set(b.x, G.h(b.x, b.z) + 0.06, b.z);
      if (b.flash > 0) { b.flash -= dt; b.mat.uniforms.uFlash.value = Math.max(0, b.flash / 0.1); }
      if (bd < def.atkRange + 1.5 && now - b.atkAt > def.atkCd * 1000) {
        b.atkAt = now;
        this.hurtPlayer(tgt.id, def.dmg, b.name);
        FX.imp(V3(tgt.x, 1, tgt.z), true); Sfx.growl(60);
      }
      var cd = 5200 - (b.phase - 1) * 1200;
      if (now - b.skillAt > cd) { b.skillAt = now; this.skill(b, tgt); }
      if (this.active !== b && d < 50) this.active = b;
    }
    // ★ 无论是否激活，都按 10Hz 广播我名下的 Boss（未激活也会发 → 各端位置/血量始终一致）
    this._sa = (this._sa || 0) + dt; if (this._sa > 0.1) { this._sa = 0; this.pushSnap(); }
  },

  // ---- 别人名下：只插值 + 复现 ----
  simRemote: function (dt) {
    var k = Math.min(1, dt * 10);
    for (var i = 0; i < this.list.length; i++) {
      var b = this.list[i];
      if (Net.mineBoss(b.id)) continue;
      if (b.tx !== undefined) { b.x += (b.tx - b.x) * k; b.z += (b.tz - b.z) * k; }
      var vis = b.spawned && b.alive;
      if (b.obj) b.obj.visible = vis;
      if (b.sh) b.sh.visible = vis;
      if (!vis) continue;
      // 兜底：没收到快照前，先按本地地形放好
      b.y += (G.h(b.x, b.z) - b.y) * Math.min(1, dt * 5);
      b.obj.position.set(b.x, b.y, b.z);
      b.obj.rotation.y = billboardYaw(b.x, b.z);
      b.sh.position.set(b.x, G.h(b.x, b.z) + 0.06, b.z);
      if (b.flash > 0) { b.flash -= dt; b.mat.uniforms.uFlash.value = Math.max(0, b.flash / 0.1); }
      drawHp(b.hpS, clamp(b.hp / b.maxHp, 0, 1), b.name, '#ffd166');
      var d = Math.hypot(P.x - b.x, P.z - b.z);
      if (this.active !== b && d < 50) this.active = b;
    }
  },

  skill: function (b, tgt) {
    tgt = tgt || { x: P.x, z: P.z, id: Net.id };
    var roll = Math.random(), R = b.def.atkRange + 4, self = this;
    if (roll < 0.34) {
      // 冲击波：房主逐个裁决范围内玩家
      FX.blast(b.x, b.y + 2, b.z, 14, 28, 0.5); Sfx.boom(); ScreenShake.add(0.9);
      if (Math.hypot(P.x - b.x, P.z - b.z) < R) this.hurtPlayer(Net.id, b.def.dmg * 0.8, b.name);
      Net.players.forEach(function (rp) {
        if (rp.alive && Math.hypot(rp.x - b.x, rp.z - b.z) < R) self.hurtPlayer(rp.id, b.def.dmg * 0.8, b.name);
      });
      HUD.feed(b.name + ' 释放 冲击波');
      if (Net.connected) Net.broadcast({ k: 'bskill', bid: b.id, kind: 'wave' });
    } else if (roll < 0.68) {
      for (var i = 0; i < 3; i++) Host.spawn(MOB_KEYS[i % 3], b.x + rnd(-5, 5), b.z + rnd(-5, 5));
      HUD.feed(b.name + ' 召唤 爪牙 x3'); Sfx.growl(110);
      if (Net.connected) Net.broadcast({ k: 'bskill', bid: b.id, kind: 'summon' });
    } else {
      var n = 3 + (b.phase - 1) * 2;
      var a0 = Math.atan2(tgt.x - b.x, tgt.z - b.z);
      for (var k = 0; k < n; k++) {
        var a = a0 + (k - (n - 1) / 2) * 0.16;
        // ★ 朝"被锁定的那个玩家"打；fireDir 会自动广播出生给所有人
        Proj.fireDir(b.x, b.y + b.scale * 0.5, b.z, Math.sin(a), -0.08, Math.cos(a), 22,
                     b.def.dmg * 0.5, false, tgt.id);
      }
      HUD.feed(b.name + ' 发射 能量弹幕'); Sfx.tick(880, 0.09, 0.1, 'sine');
    }
  },
};


/* ============================== 远程弹 ============================== */
var Proj = {
  list: [], tex: null,
  mk: function () {
    if (!this.tex) { var c = document.createElement('canvas'); c.width = c.height = 32; var g = c.getContext('2d');
      var gr = g.createRadialGradient(16, 16, 0, 16, 16, 16); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.4, 'rgba(120,200,255,.9)'); gr.addColorStop(1, 'rgba(40,120,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, 32, 32); this.tex = new THREE.CanvasTexture(c); }
    var s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.tex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    s.scale.set(0.7, 0.7, 1); actionScene.add(s);
    return s;   // ★ 不再建动态点光（弹幕一多会让所有 PBR 材质每帧循环几十盏灯 → 掉到 1fps）
  },
  // ★ 只同步"出生"（起点/方向/速度），飞行各端自己算 → 视觉一致、流量≈0
  fireDir: function (x, y, z, dx, dy, dz, sp, dmg, noSync, aimId, owner) {
    sp = sp || 22;
    var dd = Math.hypot(dx, dy, dz) || 1;
    this.list.push({ x: x, y: y, z: z, vx: dx / dd * sp, vy: dy / dd * sp, vz: dz / dd * sp,
                     life: 3.5, o: this.mk(), dmg: dmg || MOBS.wraith.dmg, toId: aimId || null, owner: owner || Net.id });
    if (!noSync && Net.connected) {
      Net.broadcast({ k: 'pspawn', x: +x.toFixed(1), y: +y.toFixed(1), z: +z.toFixed(1),
        dx: +(dx / dd).toFixed(3), dy: +(dy / dd).toFixed(3), dz: +(dz / dd).toFixed(3),
        sp: sp, dmg: Math.round(dmg || MOBS.wraith.dmg), by: Net.id });
    }
  },
  fire: function (m, tgt) {
    var sx = m.x, sy = m.y + 0.5, sz = m.z, tx = tgt.x, ty = tgt.y + 1.1, tz = tgt.z;
    var dx = tx - sx, dy = ty - sy, dz = tz - sz, d = Math.hypot(dx, dy, dz) || 1, sp = 22;
    this.list.push({ x: sx, y: sy, z: sz, vx: dx / d * sp, vy: dy / d * sp, vz: dz / d * sp, life: 3, o: this.mk(), toId: tgt.id, owner: Net.id });
    Sfx.tick(880, 0.08, 0.08, 'sine');
    // ★ 怪物的远程弹也要同步出生，否则别人只挨打、看不到子弹
    if (Net.connected) {
      Net.broadcast({ k: 'pspawn', x: +sx.toFixed(1), y: +sy.toFixed(1), z: +sz.toFixed(1),
        dx: +(dx / d).toFixed(3), dy: +(dy / d).toFixed(3), dz: +(dz / d).toFixed(3), sp: sp, dmg: Math.round(MOBS.wraith.dmg) });
    }
  },
  update: function (dt) {
    for (var i = this.list.length - 1; i >= 0; i--) {
      var p = this.list[i]; p.life -= dt; p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt; p.o.position.set(p.x, p.y, p.z);
      if (Math.random() < 0.15) FX.glowAt(p.o.position, 0.6, 0.18, 0x8fd8ff);   // 能量球拖尾
      var dead = p.life <= 0;
      if (!dead && p.y <= G.h(p.x, p.z) + 0.05) { FX.imp(V3(p.x, p.y, p.z), false); dead = true; }
      var auth = (!Net.connected || p.owner === Net.id);      // ★ 由「发射者归属」裁决命中（无房主）
      if (auth) {
        if (!dead && p.toId === Net.id && P.alive && Math.hypot(p.x - P.x, p.y - (P.y + 1.0), p.z - P.z) < 1.25) { Combat.takeDamage(p.dmg || MOBS.wraith.dmg, MOBS.wraith.name, 'mob'); FX.imp(V3(p.x, p.y, p.z), false); dead = true; }
        if (!dead && Net.connected) Net.players.forEach(function (rp) { if (dead || !rp.alive) return; if (Math.hypot(p.x - rp.x, p.y - (rp.y + 1.0), p.z - rp.z) < 1.25) { Net.broadcast({ k: 'mhit', to: rp.id, dmg: p.dmg || MOBS.wraith.dmg, name: MOBS.wraith.name }); FX.imp(V3(p.x, p.y, p.z), false); dead = true; } });
      }
      if (dead) { try { actionScene.remove(p.o); } catch (e) {} this.list.splice(i, 1); }
    }
    if (this.list.length > 120) { while (this.list.length > 100) { var _q = this.list.shift(); try { actionScene.remove(_q.o); } catch (e) {} } }   // ★ 超量强制回收
  },
};

/* ============================== 战斗 ============================== */
var Combat = {
  rayAABB: function (ox, oy, oz, dx, dy, dz, x0, y0, z0, x1, y1, z1) {
    var tmin = 0.0, tmax = 1e9;
    var o = [ox, oy, oz], d = [dx, dy, dz], mn = [x0, y0, z0], mx = [x1, y1, z1];
    for (var i = 0; i < 3; i++) {
      if (Math.abs(d[i]) < 1e-8) { if (o[i] < mn[i] || o[i] > mx[i]) return -1; continue; }
      var t1 = (mn[i] - o[i]) / d[i], t2 = (mx[i] - o[i]) / d[i], lo = Math.min(t1, t2), hi = Math.max(t1, t2);
      if (lo > tmin) tmin = lo; if (hi < tmax) tmax = hi;
      if (tmin > tmax) return -1;
    }
    return tmin < 0 ? 0 : tmin;
  },
  raySphere: function (ox, oy, oz, dx, dy, dz, cx, cy, cz, r) {
    var ex = ox - cx, ey = oy - cy, ez = oz - cz, b = ex * dx + ey * dy + ez * dz, c = ex * ex + ey * ey + ez * ez - r * r;
    if (c > 0 && b > 0) return -1; var disc = b * b - c; if (disc < 0) return -1; var t = -b - Math.sqrt(disc); return t < 0 ? 0 : t;
  },
  _hp: V3(0, 0, 0),
  cast: function (ox, oy, oz, dx, dy, dz, maxD) {
    var hr = G.ray(ox, oy, oz, dx, dy, dz, maxD);
    this._hp.set(hr.x, hr.y, hr.z);
    var best = { type: 'wall', dist: hr.dist, p: this._hp };
    Host.each(function (m) {
      // ★ 贴合立绘的 AABB（原来只有一个小球，比立绘小 → 打身体边缘全穿过去）
      var hgt = m.def.scale || 2.2, hw = (m.def.hitW || 1.0);
      var cy = m.y + hgt * 0.5;
      var t = Combat.rayAABB(ox, oy, oz, dx, dy, dz, m.x - hw, cy - hgt * 0.5, m.z - hw, m.x + hw, cy + hgt * 0.5, m.z + hw);
      if (t >= 0 && t < best.dist) {
        var hy = oy + dy * t;
        Combat._hp.set(ox + dx * t, oy + dy * t, oz + dz * t);
        best = { type: 'mob', dist: t, mob: m, crit: hy > cy + hgt * 0.14, p: Combat._hp };   // 上部 36% = 爆头
      }
    });
    BossSys.list.forEach(function (b) {
      if (!b.spawned || !b.alive) return;
      var hgt = b.def.scale, hw = b.def.hitW, cy = b.y + hgt * 0.5;
      var t = Combat.rayAABB(ox, oy, oz, dx, dy, dz, b.x - hw, cy - hgt * 0.5, b.z - hw, b.x + hw, cy + hgt * 0.5, b.z + hw);
      if (t >= 0 && t < best.dist) { var hy = oy + dy * t; Combat._hp.set(ox + dx * t, oy + dy * t, oz + dz * t);
        best = { type: 'boss', dist: t, boss: b, crit: hy > cy + hgt * 0.18, p: Combat._hp }; }
    });
    // ★ 修复：只有真的命中（t>=0）才允许覆盖 best —— 原来无条件覆盖，
    //   导致"枪口对着任意方向都会判定为打中玩家"，PVP 完全不可用
    Net.players.forEach(function (rp) {
      if (!rp.alive || SANDBOX) return;                 // ★ 沙盒模式：子弹不伤玩家
      var t = Combat.raySphere(ox, oy, oz, dx, dy, dz, rp.x, rp.y + 1.0, rp.z, 0.9);
      if (t >= 0 && t < best.dist) {
        Combat._hp.set(ox + dx * t, oy + dy * t, oz + dz * t);
        best = { type: 'player', dist: t, rp: rp, crit: false, p: Combat._hp };
      }
      var t2 = Combat.raySphere(ox, oy, oz, dx, dy, dz, rp.x, rp.y + 1.9, rp.z, 0.55);
      if (t2 >= 0 && t2 < best.dist) {
        Combat._hp.set(ox + dx * t2, oy + dy * t2, oz + dz * t2);
        best = { type: 'player', dist: t2, rp: rp, crit: true, p: Combat._hp };
      }
    });
    return best;
  },
  fire: function () {
    var w = WMAP[P.weapon];
    if (!P.alive || P.reloading > 0 || P.fireCd > 0) return;
    if (P.ammo[w.id] <= 0) { Sfx.empty(); P.reloading = w.reload; Sfx.reload(); HUD.ammo(); return; }
    P.fireCd = 60 / w.rpm; P.ammo[w.id]--;
    if (w.id === 'gl') {                                 // ★ 榴弹炮：命中点范围爆炸
      var ge = V3(P.x, P.y + (P.crouch ? 1.15 : 1.5), P.z), gd = camDir(V3(0, 0, 0)).clone();
      var gh = this.cast(ge.x, ge.y, ge.z, gd.x, gd.y, gd.z, w.range);
      var gp = gh.p, gm = V3(P.x, P.y + 1.4, P.z).addScaledVector(gd, 0.8);
      FX.tracerA(gm, gp); FX.ballistic(gm, gp);
      FX.blast(gp.x, gp.y, gp.z, 9, 28, 0.45);
      Sfx.boom(); ScreenShake.add(0.7); Recoil.p += w.recoil * 0.0062;
      Grenade.damage(gp.x, gp.y, gp.z, w.aoe, w.dmg, true);
      Net.broadcast({ k: 'boom', x: +gp.x.toFixed(1), y: +gp.y.toFixed(1), z: +gp.z.toFixed(1), r: w.aoe });
      if (P.ammo[w.id] === 0) { P.reloading = w.reload; Sfx.reload(); }
      HUD.ammo(); return;
    }
    if (w.id === 'missile') {
      Homing.launchCluster(w);
      Recoil.p += w.recoil * 0.0062; ScreenShake.add(w.recoil * 0.1);
      if (P.ammo[w.id] === 0) { P.reloading = w.reload; Sfx.reload(); }
      HUD.ammo(); return;
    }
    var eye = V3(P.x, P.y + (Cam.fp ? (P.crouch ? 1.04 : Cam.fpEye) : (P.crouch ? 1.15 : 1.5)), P.z);
    var dir;
    if (A.getCamMode() === 'hd2d') {
      // ★ HD-2D：从「屏幕准星」发射正交射线，穿过 3D 空间 → 高度自动命中（不用控俯仰）
      if (!this._hdrc) this._hdrc = new THREE.Raycaster();
      this._hdrc.setFromCamera({ x: Input.aimX || 0, y: Input.aimY || 0 }, A.orthoCam);
      var rr = this._hdrc.ray;
      var ri = this.cast(rr.origin.x, rr.origin.y, rr.origin.z, rr.direction.x, rr.direction.y, rr.direction.z, 500);
      dir = ri.p.clone().sub(eye).normalize();
    } else {
      dir = camDir(V3(0, 0, 0)).clone();          // 透视：玩家头部 + 视线（含俯仰）
    }
    // ★ 瞄准辅助：只在开火瞬间把弹道朝准心锥内的怪轻偏一点（绝不改动玩家视角）
    if (IS_TOUCH) {
      var _best = null, _bd = 0.962;
      Host.each(function (m) {
        var v = V3(m.x - eye.x, m.y + m.def.hitY - eye.y, m.z - eye.z), L = v.length() || 1; v.multiplyScalar(1 / L);
        var dot = v.dot(dir);
        if (dot > _bd && (!_best || dot > _best.dot)) _best = { dot: dot, v: v };
      });
      if (_best) dir.lerp(_best.v, 0.18).normalize();   // 只轻修弹道，绝不改相机
    }
    // ★ 第一人称：枪口就是从眼睛往前一点（弹道/枪口焰都在视线正前方，不偏不低）
    var muzzle = Cam.fp ? eye.clone().addScaledVector(dir, 0.45)
      : V3(P.x, P.y + (P.crouch ? 1.05 : 1.4), P.z).addScaledVector(dir, 0.75);
    var spread = w.spread + w.moveSpread * (P.moving ? 1 : 0) + (P.onGround ? 0 : 0.02);
    if (P.ads) spread *= 0.5;
    var right = V3(Math.cos(Cam.yaw), 0, -Math.sin(Cam.yaw));
    for (var p = 0; p < w.pellets; p++) {
      var d = dir.clone(); if (spread > 0) { d.x += rnd(-spread, spread); d.y += rnd(-spread, spread); d.z += rnd(-spread, spread); d.normalize(); }
      var hit = this.cast(eye.x, eye.y, eye.z, d.x, d.y, d.z, w.range);
      var hp = V3(eye.x + d.x * hit.dist, eye.y + d.y * hit.dist, eye.z + d.z * hit.dist);
      FX.tracerA(muzzle, hp);
      if (p === 0) FX.ballistic(muzzle, hp);
      if (hit.type === 'mob') {
        var dmg = w.dmg * (hit.crit ? 2 : 1);
        FX.imp(hp, hit.crit); HUD.hitmark(hit.crit, dmg, hp);
        Net.broadcast({ k: 'hit', mid: hit.mob.id, dmg: dmg, by: Net.id, byName: Net.name, crit: hit.crit });
        if (Net.mineMob(hit.mob.id) || !Net.connected) { Host.damage(hit.mob.id, dmg, Net.id, Net.name, hit.crit); Host.knock(hit.mob, dir, w.knock); }
      } else if (hit.type === 'boss') {
        var dmg3 = w.dmg * (hit.crit ? 2 : 1);
        FX.imp(hp, hit.crit); HUD.hitmark(hit.crit, dmg3, hp);
        Net.broadcast({ k: 'bosshit', bid: hit.boss.id, dmg: dmg3, by: Net.id, byName: Net.name });
        if (Net.mineBoss(hit.boss.id) || !Net.connected) { BossSys.damage(hit.boss.id, dmg3, Net.id, Net.name); BossSys.knock(hit.boss, dir, w.knock); }
      } else if (hit.type === 'player') {
        var dmg2 = w.dmg * (hit.crit ? 2 : 1);
        Net.broadcast({ k: 'phit', to: hit.rp.id, dmg: dmg2, name: Net.name, crit: hit.crit });
        FX.imp(hp, true); HUD.hitmark(hit.crit, dmg2, hp);
      } else FX.imp(hp, false);
    }
    FX.muzzle(muzzle); FX.shellOut(muzzle, right);
    if (Net.connected) Net.broadcast({ k: 'pshot', x: +muzzle.x.toFixed(1), y: +muzzle.y.toFixed(1), z: +muzzle.z.toFixed(1),
      tx: +hp.x.toFixed(1), ty: +hp.y.toFixed(1), tz: +hp.z.toFixed(1) });
    Recoil.p += w.recoil * 0.0062;                       // ★ 后坐力：枪口上抬（打巨物时视觉上相对小）
    Recoil.y += rnd(-1, 1) * w.recoil * 0.0026;
    Recoil.p = Math.min(Recoil.p, 0.42); Recoil.y = clamp(Recoil.y, -0.26, 0.26);
    Cam.pitch = clampPitch(Cam.pitch);
    ScreenShake.add(w.recoil * 0.1); Sfx.gun(w.sfx, 0);
    if (P.ammo[w.id] === 0) { P.reloading = w.reload; Sfx.reload(); }
    HUD.ammo();
  },
  reload: function () { var w = WMAP[P.weapon]; if (P.reloading > 0 || P.ammo[w.id] >= w.mag || P.reserve[w.id] <= 0 || !P.alive) return; P.reloading = w.reload; Sfx.reload(); HUD.ammo(); },
  finishReload: function () { var w = WMAP[P.weapon], need = w.mag - P.ammo[w.id], got = Math.min(need, P.reserve[w.id]); P.ammo[w.id] += got; P.reserve[w.id] -= got; HUD.ammo(); },
  canUse: function (w) {
    if (!w || !w.req) return true;
    if (Ref.count() >= w.req) return true;                       // 邀请人数达标
    // ★ 两条路都能拿：① 直接邀请够人数 ② 积分攒到 100（官网/论坛/游玩都在攒）
    try { if (window.TLReward && TLReward.pts() >= 100) return true; } catch (e) {}
    // ★ 新邀请系统也计数（旧版 ref/ + 新版 inv/ 都算，避免老玩家的邀请白拉）
    try { if (window.TLReward && TLReward.invite && TLReward.invite.count() >= w.req) return true; } catch (e) {}
    return false;
  },
  switchTo: function (i) {
    var w = WEAPONS[i];
    if (!w || w.id === P.weapon) return;
    if (!this.canUse(w)) {                                    // ★ 未解锁 → 提示怎么拿
      var pts = 0, inv = 0;
      try { pts = (window.TLReward ? TLReward.pts() : 0); } catch (e) {}
      try { inv = (window.TLReward && TLReward.invite) ? TLReward.invite.count() : 0; } catch (e) {}
      var n = Math.max(Ref.count(), inv);
      HUD.center('🔒 ' + w.name,
        '两条路任选：邀请 ' + w.req + ' 位好友（' + n + '/' + w.req + '）　或　积分攒满 100（当前 ' + pts + '/100）',
        3000);
      Sfx.deny(); return;
    }
    P.weapon = w.id; P.reloading = 0; P.fireCd = Math.max(P.fireCd, 0.25); P.ads = false; HUD.weapon(); Sfx.tick(600, 0.04, 0.1);
  },
  next: function () {
    var i = WMAP[P.weapon].index, n = WEAPONS.length;
    for (var k = 1; k <= n; k++) {
      var j = (i + k) % n;
      if (this.canUse(WEAPONS[j])) { this.switchTo(j); return; }
    }
  },
  takeDamage: function (dmg, fromName, kind) {
    if (!P.alive) return;
    if (P.armor > 0) { var a = Math.min(P.armor, dmg * 0.6); P.armor -= a; dmg -= a; }
    P.hp -= dmg; P.lastHurt = performance.now(); P.lastAttacker = fromName || '?';
    HUD.vitals(); HUD.selfDmg(dmg); HUD.vignette(); Sfx.hurt(); ScreenShake.add(0.35);
    if (P.hp <= 0) this.die(fromName);
  },
  die: function (byName) {
    P.hp = 0; P.alive = false; P.deaths++; P.respawnAt = performance.now() + 3200;
    HUD.center('你被击倒了', (byName ? '凶手：' + byName + ' · ' : '') + '3 秒后复活');
    $('respBar').style.display = 'block'; Net.broadcast({ k: 'pdie', victim: Net.name, byName: byName || '魔物' }); HUD.board();
  },
  respawn: function () {
    P.alive = true; P.hp = P.maxHp || 100; P.armor = 40; P.vy = 0; P.reloading = 0; P.fireCd = 0; P.ads = false;   // ★ 先活过来
    try {
      // ★ 复活回"统一出生点"（避免被随机丢到大图另一头，和队友失联）
      placeAtSpawn();
      if (typeof resetAmmo === 'function') resetAmmo();
      var rb = $('respBar'); if (rb) rb.style.display = 'none';
      var dv = $('dmgVig'); if (dv) dv.style.opacity = 0;
      HUD.center('已复活', '', 900); HUD.vitals(); HUD.ammo();
      if (window.__OCTO) { window.__OCTO.hero.x = P.x; window.__OCTO.hero.y = P.z; }   // 同步到 HD-2D 世界
    } catch (e) { window.__respawnErr = String((e && e.message) || e); }
  },
};

/* 事件补充 */
var _onEv = Net.onEv;
Net.onEv = function (o, now) {
  if (o.k === 'mhit') { if (o.to === Net.id) Combat.takeDamage(o.dmg, o.name, 'mob'); return; }
  if (o.k === 'pdie') {
    if (o.byName === Net.name && o.victim !== Net.name) { P.kills++; P.score += 50; HUD.center('击杀 ' + o.victim, '+50'); HUD.board(); }
    return _onEv.call(Net, o, now);
  }
  if (o.k === 'phit') { if (o.to === Net.id) Combat.takeDamage(o.dmg, o.name, 'player'); return; }
  return _onEv.call(Net, o, now);
};

/* ============================== ★ 怪物渲染池（复用 Sprite 对象 + 共享材质 + 视距剔除 → 几百只也不卡） ============================== */
var MobRender = {
  MAX: 220, sprites: [], hps: [], mats: {}, hpMat: null, used: 0, range: 46,
  init: function () {
    MOB_KEYS.forEach(function (k) {
      MobRender.mats[k] = new THREE.SpriteMaterial({ map: MOB_TEX[k], transparent: true, depthWrite: true });
    });
    MobRender.hpMat = new THREE.SpriteMaterial({ map: hpTex(), transparent: true, depthTest: false, depthWrite: false });
    for (var i = 0; i < this.MAX; i++) {
      var s = new THREE.Sprite(this.mats.floater); s.center.set(0.5, 0); s.visible = false; s.frustumCulled = true;
      actionScene.add(s); this.sprites.push(s);
      var h = new THREE.Sprite(this.hpMat); h.visible = false; h.renderOrder = 998;
      actionScene.add(h); this.hps.push(h);
    }
  },
  sync: function () {
    if (!this.sprites.length) return;
    var cp = cam().position, n = 0, hpN = 0;
    for (var i = 0; i < Host.mobs.length; i++) {
      var m = Host.mobs[i];
      if (!m.alive) continue;
      var d = Math.hypot(m.x - cp.x, m.z - cp.z);
      if (d > MobRender.range) continue;                     // ★ 视距剔除（性能调速器会动态调整）
      if (n >= this.MAX) break;
      var sp = this.sprites[n];
      var mt = this.mats[m.kind] || this.mats.floater;
      if (sp.material !== mt) sp.material = mt;
      var hgt = m.def.scale;
      sp.position.set(m.x, m.y, m.z);
      sp.scale.set(hgt * 0.62, hgt, 1);
      sp.visible = true;
      n++;
      if (d < 22 && hpN < this.MAX) {                        // 血条：只近处显示
        var hb = this.hps[hpN];
        hb.position.set(m.x, m.y + hgt * 0.92, m.z);
        hb.scale.set(1.6 * clamp(m.hp / m.maxHp, 0.02, 1), 0.26, 1);
        hb.visible = true; hpN++;
      }
    }
    for (var k = n; k < this.used; k++) this.sprites[k].visible = false;
    for (var q = hpN; q < this.used; q++) this.hps[q].visible = false;
    this.used = Math.max(n, hpN);
  },
};

/* ============================== ★ 集束追踪导弹（清场终极武器） ============================== */
var Homing = {
  MAX: 120, list: [], geo: null, pts: null, pos: null,
  init: function () {
    var c = document.createElement('canvas'); c.width = c.height = 32; var g = c.getContext('2d');
    var gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,180,90,.9)'); gr.addColorStop(1, 'rgba(255,90,40,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
    var tex = new THREE.CanvasTexture(c);
    this.geo = new THREE.BufferGeometry();
    this.pos = new Float32Array(this.MAX * 3);
    for (var i = 0; i < this.MAX; i++) this.pos[i * 3 + 1] = -9999;
    this.geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    var m = new THREE.PointsMaterial({ map: tex, size: 1.15, sizeAttenuation: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
    this.pts = new THREE.Points(this.geo, m); this.pts.frustumCulled = false; actionScene.add(this.pts);
  },
  launch: function (x, y, z, tx, ty, tz, mob, dmg) {
    if (this.list.length >= this.MAX) this.list.shift();
    var dx = tx - x, dy = ty - y, dz = tz - z, d = Math.hypot(dx, dy, dz) || 1, sp = 42;
    this.list.push({ x: x, y: y, z: z, vx: dx / d * sp + rnd(-6, 6), vy: dy / d * sp + rnd(0, 6), vz: dz / d * sp + rnd(-6, 6), mob: mob, dmg: dmg, life: 4.5 });
  },
  launchCluster: function (w) {
    var eye = V3(P.x, P.y + 1.6, P.z), tg = [];
    Host.each(function (m) { if (Math.hypot(m.x - P.x, m.z - P.z) < 65 && tg.length < 18) tg.push(m); });
    BossSys.list.forEach(function (b) { if (b.spawned && b.alive && Math.hypot(b.x - P.x, b.z - P.z) < 80 && tg.length < 22) tg.push(b); });
    if (!tg.length) { this.launch(eye.x, eye.y, eye.z, P.x + Math.sin(Cam.yaw) * 40, eye.y, P.z + Math.cos(Cam.yaw) * 40, null, w.dmg); return 0; }
    var n = 0;
    for (var i = 0; i < tg.length; i++) { var t = tg[i], ty = t.y + (t.def.hitY || 1.2);
      for (var k = 0; k < 4; k++) { this.launch(eye.x + rnd(-0.6, 0.6), eye.y + rnd(-0.4, 0.8), eye.z + rnd(-0.6, 0.6), t.x, ty, t.z, t, w.dmg); n++; } }
    HUD.center('集束导弹 · 锁定 ' + tg.length + ' 个目标', '追踪弹 x' + n, 1200);
    Sfx.boom(); ScreenShake.add(0.5);
    return n;
  },
  update: function (dt) {
    if (!this.list.length) return;
    var alive = 0;
    for (var i = 0; i < this.list.length; i++) {
      var p = this.list[i]; p.life -= dt;
      var t = p.mob;
      if (t && t.alive) {
        var tx = t.x, ty = t.y + (t.def.hitY || 1.2), tz = t.z;
        var dx = tx - p.x, dy = ty - p.y, dz = tz - p.z, d = Math.hypot(dx, dy, dz) || 1, sp2 = 46, k = Math.min(1, dt * 7);
        p.vx = lerp(p.vx, dx / d * sp2, k); p.vy = lerp(p.vy, dy / d * sp2, k); p.vz = lerp(p.vz, dz / d * sp2, k);
        var vl = Math.hypot(p.vx, p.vy, p.vz) || 1; p.vx = p.vx / vl * sp2; p.vy = p.vy / vl * sp2; p.vz = p.vz / vl * sp2;
        if (d < (t.def.hitR || 1.5) + 0.9) {
          FX.imp(V3(p.x, p.y, p.z), true);
          if (t.id && t.id.charAt(0) === 'B') BossSys.damage(t.id, p.dmg, Net.id, Net.name);
          else if (Net.mineMob(t.id) || !Net.connected) { Host.damage(t.id, p.dmg, Net.id, Net.name); Host.knock(t, V3(p.vx, 0, p.vz), 0.8); }
          p.life = 0;
        }
      } else p.vy -= 6 * dt;
      p.x += p.vx * dt; p.y += p.vy * dt; p.z += p.vz * dt;
      if (p.y < G.h(p.x, p.z) + 0.1) { FX.imp(V3(p.x, G.h(p.x, p.z) + 0.2, p.z), false); p.life = 0; }
      if (p.life <= 0) { this.pos[i * 3 + 1] = -9999; continue; }
      this.pos[i * 3] = p.x; this.pos[i * 3 + 1] = p.y; this.pos[i * 3 + 2] = p.z;
      if (Math.random() < 0.08) FX.glowAt(V3(p.x, p.y, p.z), 0.45, 0.14, 0xffa050);
      alive++;
    }
    this.geo.attributes.position.needsUpdate = true;
    if (!alive) { this.list.length = 0; return; }
    var w2 = 0;
    for (var j = 0; j < this.list.length; j++) if (this.list[j].life > 0) { this.list[w2] = this.list[j]; if (w2 !== j) { this.pos[w2 * 3] = this.pos[j * 3]; this.pos[w2 * 3 + 1] = this.pos[j * 3 + 1]; this.pos[w2 * 3 + 2] = this.pos[j * 3 + 2]; } w2++; }
    this.list.length = w2;
  },
};

/* ============================== 手雷 ============================== */
var Grenade = {
  list: [],
  throwFrom: function () {
    if (P.nade <= 0 || P.nadeCd > 0 || !P.alive) return;
    P.nade--; P.nadeCd = 1.2; HUD.nade();
    var d = camDir(V3(0, 0, 0));
    var g = { x: P.x + d.x * 0.7, y: P.y + 1.5, z: P.z + d.z * 0.7, vx: d.x * 17, vy: d.y * 17 + 4.5, vz: d.z * 17, t: 0, mine: true };
    var mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(0.16, 1), new THREE.MeshStandardMaterial({ color: 0x2f3542, emissive: 0xff6a00, emissiveIntensity: 1.2 }));
    actionScene.add(mesh); g.mesh = mesh; this.list.push(g);
    Net.broadcast({ k: 'nade', x: +g.x.toFixed(1), y: +g.y.toFixed(1), z: +g.z.toFixed(1) }); Sfx.tick(500, 0.06, 0.1, 'sine');
  },
  spawnRemote: function (x, y, z) {
    var g = { x: x, y: y, z: z, vx: 0, vy: 0, vz: 0, t: 0, mine: false };
    var mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(0.16, 1), new THREE.MeshStandardMaterial({ color: 0x2f3542, emissive: 0xff6a00, emissiveIntensity: 1.2 }));
    actionScene.add(mesh); g.mesh = mesh; g.t = 1.6; this.list.push(g);
  },
  update: function (dt) {
    for (var i = this.list.length - 1; i >= 0; i--) {
      var g = this.list[i]; g.t += dt; g.vy -= 24 * dt;
      var nx = g.x + g.vx * dt, ny = g.y + g.vy * dt, nz = g.z + g.vz * dt;
      var fl = G.h(nx, nz) + 0.16;
      if (ny <= fl) { ny = fl; g.vy *= -0.42; g.vx *= 0.6; g.vz *= 0.6; if (Math.abs(g.vy) > 0.6) Sfx.tick(240, 0.04, 0.06); }
      if (ny < G.h(nx, nz) + 2 && (G.h(nx, g.z + 0.6) > ny - 0.5)) { g.vx *= -0.5; nx = g.x; }
      g.x = nx; g.y = ny; g.z = nz; if (g.mesh) g.mesh.position.set(g.x, g.y, g.z);
      if (g.t > 2.4) { this.boom(g); this.list.splice(i, 1); }
    }
  },
  boom: function (g) {
    var R = 7.5, D = 140;
    FX.imp(V3(g.x, g.y, g.z), true); FX.blast(g.x, g.y, g.z, 4.5, 24, 0.34);
    for (var i = 0; i < 5; i++) FX.imp(V3(g.x + rnd(-2, 2), G.h(g.x, g.z) + rnd(0.3, 2), g.z + rnd(-2, 2)), true);
    Sfx.boom(); ScreenShake.add(0.9);
    if (g.mesh) actionScene.remove(g.mesh);
    Net.broadcast({ k: 'boom', x: +g.x.toFixed(1), y: +g.y.toFixed(1), z: +g.z.toFixed(1), r: R });
    this.damage(g.x, g.y, g.z, R, D, g.mine);
  },
  explodeRemote: function (x, y, z, r) {
    FX.blast(x, y, z, 4.5, 20, 0.34);
    Sfx.boom(); var d = Math.hypot(x - P.x, y - P.y, z - P.z); if (d < r) ScreenShake.add(0.7 * (1 - d / r));
    this.damage(x, y, z, r, 90, false, true);
  },
  damage: function (x, y, z, R, D, mine, remote) {
    Host.each(function (m) { var d = Math.hypot(m.x - x, m.y - y, m.z - z); if (d < R) { var dmg = D * (1 - d / R * 0.6); Net.broadcast({ k: 'hit', mid: m.id, dmg: dmg, by: Net.id, byName: Net.name }); if (Net.mineMob(m.id) || !Net.connected) Host.damage(m.id, dmg, Net.id, Net.name, false); } });
    if (!remote) Net.players.forEach(function (rp) { if (!rp.alive) return; var d = Math.hypot(rp.x - x, rp.y - y, rp.z - z); if (d < R) Net.broadcast({ k: 'phit', to: rp.id, dmg: D * (1 - d / R * 0.6), name: Net.name }); });
  },
};

/* ============================== 输入 ============================== */
var Camera = { yawKick: 0 };                 // 兼容占位
var Input = { keys: {}, mx: 0, my: 0, fire: false, fireOnce: false, ads: false, jump: false, reload: false, swap: false, nade: false };
var IS_TOUCH = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0) || /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
var locked = false;
function bindInput() {
  try { window.focus && window.focus(); } catch (e) {}
  var CODE = { keyw: 'w', keya: 'a', keys: 's', keyd: 'd', arrowup: 'w', arrowleft: 'a', arrowdown: 's', arrowright: 'd',
    space: ' ', shiftleft: 'shift', shiftright: 'shift', keyr: 'r', keyg: 'g', keyq: 'q', keye: 'e',
    digit1: '1', digit2: '2', digit3: '3', digit4: '4' };
  window.addEventListener('keydown', function (e) {
    var code = (e.code || '').toLowerCase(), k = (e.key || '').toLowerCase();
    if (CODE[code]) k = CODE[code];
    Input.keys[k] = 1;
    if (k === 'r') Input.reload = true;
    if (k === 'g') Input.nade = true;
    if (k === ' ') Input.jump = true;
    if (k === 'e') Input.ads = !Input.ads;
    if (k >= '1' && k <= '8') Combat.switchTo(parseInt(k, 10) - 1);
    if (k === 'q') Combat.next();
    if (k === 'v') cycleCam();
    if (k === 'f') toggleFP();          // ★ F = 第一人称
    if (k === 'x') toggleAim();
    if (k === 'y') toggleAssist();
    if (k === 'c') cycleView();
    if ('wasd '.indexOf(k) >= 0) e.preventDefault();
  }, { passive: false });
  window.addEventListener('keyup', function (e) {
    var code = (e.code || '').toLowerCase(), k = (e.key || '').toLowerCase();
    if (CODE[code]) k = CODE[code];
    Input.keys[k] = 0;
  });
  var cvEl = $('cv');
  cvEl.addEventListener('click', function () { if (!locked) cvEl.requestPointerLock && cvEl.requestPointerLock(); });
  document.addEventListener('pointerlockchange', function () { locked = (document.pointerLockElement === cvEl); });
  var dragging = false;
  document.addEventListener('mousemove', function (e) {
    if (locked) { Cam.yaw -= e.movementX * 0.0022; Cam.pitch -= e.movementY * 0.0022; Cam.pitch = clampPitch(Cam.pitch); return; }
    if (dragging) { Cam.yaw -= e.movementX * 0.004; Cam.pitch -= e.movementY * 0.004; Cam.pitch = clampPitch(Cam.pitch); Input.lookDrag = performance.now(); }
  });
  cvEl.addEventListener('mousedown', function (e) { if (e.button === 0) dragging = true; });
  window.addEventListener('mouseup', function () { dragging = false; });
  document.addEventListener('mousedown', function (e) {
    var el = e.target;
    if (el && el.closest && el.closest('.hrbtns,#chatWrap,#board,#startPanel,.modal-panel,#joy,.tbtn')) return;   // ★ 点 UI 不开火
    if (e.button === 0) { Input.fire = true; Input.fireOnce = true; }
    if (e.button === 2) Input.ads = true;
  }, true);
  document.addEventListener('mouseup', function (e) { if (e.button === 0) Input.fire = false; if (e.button === 2) Input.ads = false; });
  document.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  document.addEventListener('mousedown', function (e) { if (e.button === 0) { dragging = true; } }, true);

  // ★ 无条件显示并绑定触控 UI（不再依赖 UA 判断 —— WebView 里常判断失败导致"完全动不了"）
  $('touchpad').style.display = 'block';
  $('joy').style.display = 'block'; $('lookZone').style.display = 'block';
  // ★ 优先用「全局 pointer 事件 + 手工命中检测」：完全绕开 CSS 层级/pointer-events 的坑
  if (window.PointerEvent) bindPointer(); else { bindJoy(); bindLook(); bindBtns(); }   // PointerEvent 优先（touch 版不启用，避免打架）
  $('tipTxt').textContent = '左摇杆移动 · 右半屏拖动转视角 · PC：WASD + 鼠标拖转视角 + 左键开火';
}
/* ★ 全局 pointer 输入：不依赖元素是否可点，自己算命中 → 真机"点不到"的终极解法 */
function bindPointer() {
  // ★ 双指捏合缩放（单指仍是 转视角/移准星）
  var pts = {}, pinching = false, d0 = 0, v0 = 24;
  function pdist() { var a = Object.keys(pts); if (a.length < 2) return 0; var p1 = pts[a[0]], p2 = pts[a[1]]; return Math.hypot(p1.clientX - p2.clientX, p1.clientY - p2.clientY); }
  window.addEventListener('pointerdown', function (e) { pts[e.pointerId] = e; if (Object.keys(pts).length === 2) { pinching = true; d0 = pdist() || 1; v0 = Cam.distV || 24; } });
  window.addEventListener('pointermove', function (e) {
    if (pts[e.pointerId]) pts[e.pointerId] = e;
    if (pinching && d0 > 0) { var d = pdist(); if (d > 0) setCamDist(clamp(v0 * (d0 / d), 8, 70)); }   // 只缩放（准星已移除，以滑动为主）
  }, { passive: false });
  function pend(e) { delete pts[e.pointerId]; if (Object.keys(pts).length < 2) pinching = false; }
  window.addEventListener('pointerup', pend); window.addEventListener('pointercancel', pend);

  var BTN = ['btnFire', 'btnJump', 'btnReload', 'btnSwap', 'btnGrenade', 'btnAds', 'joy'];
  var joyId = null, lookId = null, lookLast = null, fireId = null;
  function hit(x, y) {
    for (var i = 0; i < BTN.length; i++) {
      var el = $(BTN[i]); if (!el) continue;
      var r = el.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return BTN[i];
    }
    return null;
  }
  function joySet(x, y) {
    var el = $('joy'), r = el.getBoundingClientRect();
    var cx = r.left + r.width / 2, cy = r.top + r.height / 2, dx = x - cx, dy = y - cy;
    var L = Math.hypot(dx, dy) || 1, m = Math.min(L, 46); dx = dx / L * m; dy = dy / L * m;
    Input.mx = dx / 46; Input.my = -dy / 46;
    var st = el.querySelector('.k'); if (st) st.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
  }
  window.addEventListener('pointerdown', function (e) {
    // ★ 任何 UI 浮层/控件都不抢手势：按钮/链接/表单/各面板。
    //   （原来只排除表单，导致点菜单按钮被当"转视角"并 preventDefault，click 被吞 → 点了没反应 / ✕关不掉 / 滑动被吃）
    if (e.target && e.target.closest && e.target.closest(
      'button,a,input,select,textarea,#treePanel,#qrPanel,#histPanel,#board,#mapWrap,#chatWrap,#visitPanel,.hrbtns,#distBox,.thead,.chip')) return;
    var t = hit(e.clientX, e.clientY);
    if (t === 'joy') { joyId = e.pointerId; joySet(e.clientX, e.clientY); }
    else if (t === 'btnFire') { fireId = e.pointerId; Input.fire = true; Input.fireOnce = true; $('btnFire').classList.add('on'); }
    else if (t === 'btnJump') { Input.jump = true; }
    else if (t === 'btnReload') { Input.reload = true; }
    else if (t === 'btnSwap') { Input.swap = true; }
    else if (t === 'btnGrenade') { Input.nade = true; }
    else if (t === 'btnAds') { Input.ads = !Input.ads; }
    else { lookId = e.pointerId; lookLast = { x: e.clientX, y: e.clientY }; }   // ★ 除控件外「全屏任意处」都能转视角
    if (t || lookId === e.pointerId) e.preventDefault();
  }, { passive: false });
  window.addEventListener('pointermove', function (e) {
    if (e.pointerId === joyId) { joySet(e.clientX, e.clientY); e.preventDefault(); }
    else if (e.pointerId === lookId && lookLast) {
      var dx = e.clientX - lookLast.x, dy = e.clientY - lookLast.y;
      if (A.look) { A.look(dx * 0.005, dy * 0.005); }               // ★ 单指拖 = 转视角（HD-2D 也能转）
      else { Cam.yaw -= dx * 0.005; Cam.pitch -= dy * 0.005; Cam.pitch = clampPitch(Cam.pitch); }
      Input.lookDrag = performance.now();
      lookLast = { x: e.clientX, y: e.clientY }; e.preventDefault();
    }
  }, { passive: false });
  function up(e) {
    if (e.pointerId === joyId) { joyId = null; Input.mx = Input.my = 0; var st = $('joy').querySelector('.k'); if (st) st.style.transform = ''; }
    if (e.pointerId === lookId) lookId = null;
    if (e.pointerId === fireId) { fireId = null; Input.fire = false; $('btnFire').classList.remove('on'); }
  }
  window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up);
}
function bindJoy() {
  var el = $('joy'), stick = el.querySelector('.k'), id = null;
  function move(t) {
    var r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    var dx = t.clientX - cx, dy = t.clientY - cy, L = Math.hypot(dx, dy) || 1, m = Math.min(L, 46);
    dx = dx / L * m; dy = dy / L * m; Input.mx = dx / 46; Input.my = -dy / 46;
    stick.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
  }
  el.addEventListener('touchstart', function (e) { id = e.changedTouches[0].identifier; move(e.changedTouches[0]); e.preventDefault(); }, { passive: false });
  el.addEventListener('touchmove', function (e) { if (id === null) return; var t = [].slice.call(e.changedTouches).filter(function (x) { return x.identifier === id; })[0]; if (t) { move(t); e.preventDefault(); } }, { passive: false });
  el.addEventListener('touchend', function () { id = null; Input.mx = Input.my = 0; stick.style.transform = ''; });
  var md = false;
  el.addEventListener('mousedown', function (e) { md = true; move(e); e.preventDefault(); });
  window.addEventListener('mousemove', function (e) { if (md) move(e); });
  window.addEventListener('mouseup', function () { if (md) { md = false; Input.mx = Input.my = 0; stick.style.transform = ''; } });
  el.addEventListener('touchcancel', function () { id = null; Input.mx = Input.my = 0; stick.style.transform = ''; });
}
function bindLook() {
  var el = $('lookZone'), ids = {}, last = {};
  var t0 = 0, mvd = 0;
  el.addEventListener('touchstart', function (e) {
    t0 = performance.now(); mvd = 0;
    for (var i = 0; i < e.changedTouches.length; i++) { var t = e.changedTouches[i]; ids[t.identifier] = 1; last[t.identifier] = { x: t.clientX, y: t.clientY }; }
    e.preventDefault();
  }, { passive: false });
  el.addEventListener('touchmove', function (e) {
    for (var i = 0; i < e.changedTouches.length; i++) {
      var t = e.changedTouches[i], pr = last[t.identifier]; if (!pr) continue;
      var dx = t.clientX - pr.x, dy = t.clientY - pr.y;
      if (A.getCamMode() === 'hd2d') {
        Input.aimX = clamp((Input.aimX || 0) + dx / 300, -1, 1);     // ★ HD-2D：拖动移动屏幕准星
        Input.aimY = clamp((Input.aimY || 0) - dy / 300, -1, 1);
      } else {
        Cam.yaw -= dx * 0.005; Cam.pitch -= dy * 0.005; Cam.pitch = clampPitch(Cam.pitch);
      }
      Input.lookDrag = performance.now();
      mvd += Math.abs(dx) + Math.abs(dy);
      last[t.identifier] = { x: t.clientX, y: t.clientY }; e.preventDefault();
    }
  }, { passive: false });
  el.addEventListener('touchend', function (e) {
    for (var i = 0; i < e.changedTouches.length; i++) delete ids[e.changedTouches[i].identifier];
    // ★ 右侧轻点 = 开火（拖动转视角不算）
    if (performance.now() - t0 < 240 && mvd < 16) { try { Combat.fire(); } catch (err) {} }
  });
}
function holdBtn(id, on, off) {
  var b = $(id); if (!b) return;
  b.addEventListener('touchstart', function (e) { b.classList.add('on'); on(); e.preventDefault(); }, { passive: false });
  b.addEventListener('touchend', function (e) { b.classList.remove('on'); if (off) off(); e.preventDefault(); }, { passive: false });
  b.addEventListener('mousedown', function (e) { b.classList.add('on'); on(); e.preventDefault(); });
  b.addEventListener('mouseup', function () { b.classList.remove('on'); if (off) off(); });
}
function bindBtns() {
  holdBtn('btnFire', function () { Input.fire = true; Input.fireOnce = true; }, function () { Input.fire = false; });
  holdBtn('btnAds', function () { Input.ads = true; }, function () { Input.ads = false; });
  holdBtn('btnJump', function () { Input.jump = true; });
  holdBtn('btnReload', function () { Input.reload = true; });
  holdBtn('btnSwap', function () { Input.swap = true; });
  holdBtn('btnGrenade', function () { Input.nade = true; });
}

/* 移动 + 重力 */
var GRAV = 20, JUMPV = 9.2;   // 跳跃高度 ≈2.1m
function movePlayer(dt) {
  // ★ 用「当前相机的水平朝向」算移动方向（HD-2D 是固定 45°，透视是 Cam.yaw）——之前固定用 Cam.yaw → HD-2D 方向错位
  var camYaw = (A.getCamMode() === 'hd2d') ? Math.atan2(-A.CAM_DIR.x, -A.CAM_DIR.z) : Cam.yaw;
  var fwd = V3(Math.sin(camYaw), 0, Math.cos(camYaw)), right = V3(-Math.cos(camYaw), 0, Math.sin(camYaw));
  var ix = 0, iz = 0;
  if (Input.keys['w'] || Input.keys['arrowup']) iz += 1; if (Input.keys['s'] || Input.keys['arrowdown']) iz -= 1;
  if (Input.keys['d'] || Input.keys['arrowright']) ix += 1; if (Input.keys['a'] || Input.keys['arrowleft']) ix -= 1;
  ix += Input.mx; iz += Input.my;
  if (!isFinite(ix)) ix = 0; if (!isFinite(iz)) iz = 0;
  var run = Input.keys['shift'] ? 1.45 : 1, spd = 5.6 * run * (P.crouch ? 0.5 : 1) * (P.ads ? 0.75 : 1);
  var mvx = fwd.x * iz + right.x * ix, mvz = fwd.z * iz + right.z * ix;
  var ml = Math.hypot(mvx, mvz);
  P.moving = ml > 0.05 && P.alive;
  if (P.moving) {
    mvx /= ml; mvz /= ml;
    var nx = P.x + mvx * spd * dt, nz = P.z + mvz * spd * dt;
    var _step = P.onGround ? 0.66 : 1.75;          // ★ 空中可"攀爬"1.75m 台阶（跳起来能爬出浅坑）
    if (G.canStand(nx, P.z, P.y, _step)) P.x = nx;
    if (G.canStand(P.x, nz, P.y, _step)) P.z = nz;
    P.yaw = Math.atan2(mvx, mvz);
    var _pw = P.walk; P.walk += dt * (6 + 4 * run);
    if (P.onGround && Math.floor(_pw / Math.PI) !== Math.floor(P.walk / Math.PI)) Sfx.step(run > 1.2);   // ★ 脚步音
  } else P.yaw = Cam.yaw;
  var floor = G.h(P.x, P.z);
  if (Input.jump && P.onGround && P.alive) { P.vy = JUMPV; P.onGround = false; Input.jump = false; Sfx.jump(); }
  if (!P.onGround) {
    P.vy -= GRAV * dt; P.y += P.vy * dt;
    if (P.y <= floor) { P.y = floor; P.vy = 0; P.onGround = true; Sfx.land(); }
  } else {
    P.y += (floor - P.y) * Math.min(1, dt * 14);
    if (floor - P.y < -0.05) { } else P.y = lerp(P.y, floor, Math.min(1, dt * 14));
    if (Math.abs(floor - P.y) < 0.02) P.y = floor;
  }
  Input.jump = false;
  // ★ 卡住自救：想动却几乎没动（被四面墙围住/掉坑）→ 找最近可站立点脱困，永不困死
  if (P.alive) {
    var want = Math.abs(ix) > 0.05 || Math.abs(iz) > 0.05;
    if (want) {
      var moved = Math.hypot(P.x - (P._lx === undefined ? P.x : P._lx), P.z - (P._lz === undefined ? P.z : P._lz));
      P._stuck = moved < 0.015 ? (P._stuck || 0) + dt : 0;
      if (P._stuck > 1.0) {
        P._stuck = 0;
        var best = null, bs = 1e9;
        for (var rr = 2; rr <= 8; rr++) for (var aa = 0; aa < 16; aa++) {
          var an = aa / 16 * Math.PI * 2, tx2 = P.x + Math.cos(an) * rr, tz2 = P.z + Math.sin(an) * rr;
          if (tx2 < 8 || tz2 < 8 || tx2 > G.GW * G.TILE - 8 || tz2 > G.GH * G.TILE - 8) continue;
          var th = G.h(tx2, tz2);
          if (th - P.y > 3.6) continue;                       // 太高爬不上
          var score = rr + Math.abs(th - P.y) * 0.6;
          if (score < bs) { bs = score; best = { x: tx2, z: tz2, y: th }; }
        }
        if (best) { P.x = best.x; P.z = best.z; P.y = best.y + 0.06; P.vy = 0; P.onGround = true; HUD.center('已脱困', '', 600); }
      }
    } else P._stuck = 0;
    P._lx = P.x; P._lz = P.z;
  }
  // 越界兜底
  P.x = clamp(P.x, 6, G.GW * TILE - 6); P.z = clamp(P.z, 6, G.GH * TILE - 6);
}

/* 瞄准辅助（触屏）：把准心轻推最近的敌人 */
function aimAssist() {
  // ★ 自动瞄准：正在拖动视角时不抢（保护操作），停手后才温和吸附到准心锥内的怪
  if (!P.alive) return;
  if (performance.now() - (Input.lookDrag || 0) < 260) return;
  var dir = camDir(V3(0, 0, 0)), best = null, bd = 0.90;
  var ex = P.x, ey = P.y + (P.crouch ? 1.15 : 1.5), ez = P.z;
  Host.each(function (m) {
    var v = V3(m.x - ex, m.y + m.def.hitY - ey, m.z - ez);
    var d = v.length(); if (d < 1.2 || d > 70) return; v.multiplyScalar(1 / d);
    var dot = v.dot(dir); if (dot > bd && (!best || dot > best.dot)) best = { dot: dot, m: m };
  });
  if (best) {
    var target = V3(best.m.x, best.m.y + best.m.def.hitY, best.m.z).sub(V3(ex, ey, ez)).normalize();
    var yawT = Math.atan2(target.x, target.z), pitchT = Math.asin(target.y);
    Cam.yaw += (yawT - Cam.yaw) * 0.25;
    Cam.pitch += (pitchT - Cam.pitch) * 0.25;
    Cam.pitch = clampPitch(Cam.pitch);
  }
}

/* ============================== HUD ============================== */
var HUD = {
  feedT: [], hitT: 0, msgT: 0,
  ammo: function () {
    var w = WMAP[P.weapon];
    var el = $('gunAmmo'); el.className = P.reloading > 0 ? 'reloading' : '';
    el.innerHTML = P.reloading > 0 ? '换弹' : (P.ammo[w.id] + '<small> / ' + P.reserve[w.id] + '</small>');
    $('gunName').textContent = w.name;
    var wl = $('wlist'); wl.innerHTML = '';
    var shown = 0;
    WEAPONS.forEach(function (ww, i) {
      if (!Combat.canUse(ww)) return;                            // ★ 未解锁的不显示
      var d = document.createElement('div'); d.className = 'w' + (ww.id === P.weapon ? ' on' : '');
      d.textContent = (i + 1) + ' ' + ww.short; wl.appendChild(d); shown++;
    });
  },
  weapon: function () { this.ammo(); },
  nade: function () { },
  _hv: '', _av: '', _num: '',
  vitals: function () {
    var hv = Math.round(clamp(P.hp / P.maxHp, 0, 1) * 100), av = Math.round(clamp(P.armor / 100, 0, 1) * 100);
    if (hv !== this._hv) { this._hv = hv; $('hpFill').style.width = hv + '%'; }
    var num = Math.max(0, Math.round(P.hp)) + ' / ' + P.maxHp;
    if (num !== this._num) { this._num = num; $('hpNum').textContent = num; }
    if (av !== this._av) { this._av = av; $('arFill').style.width = av + '%'; }
  },
  _sv: '',
  score: function () { var v = P.kills + '/' + P.deaths + '/' + P.score + '/' + Host.wave; if (v === this._sv) return; this._sv = v; $('kKill').textContent = P.kills; $('kDeath').textContent = P.deaths; $('kScore').textContent = P.score; $('kWave').textContent = Host.wave; },
  feed: function (t) {
    var d = document.createElement('div'); d.textContent = t; var kf = $('killfeed'); kf.appendChild(d);
    while (kf.children.length > 6) kf.removeChild(kf.firstChild);
    setTimeout(function () { d.style.transition = 'opacity .4s'; d.style.opacity = 0; setTimeout(function () { d.parentNode && d.parentNode.removeChild(d); }, 420); }, 3400);
  },
  hitmark: function (crit, dmg, worldPos) {
    var hm = $('hitmark'); hm.style.opacity = 1; hm.style.color = crit ? '#ffd166' : '#ff5f6d';
    clearTimeout(this.hitT); this.hitT = setTimeout(function () { hm.style.opacity = 0; }, 110);
    var x = $('xhair'); x.className = crit ? 'kill' : 'hit'; clearTimeout(this.xT); this.xT = setTimeout(function () { x.className = ''; }, 130);
    if (worldPos) this.dmgNum(dmg, crit, worldPos);
  },
  dmgNum: function (v, crit, wp) {
    var p = wp.clone().project(cam());
    if (p.z > 1) return;
    var el = document.createElement('div'); el.className = 'dmg' + (crit ? ' crit' : '');
    el.textContent = (crit ? '暴击 ' : '') + Math.round(v);
    el.style.left = ((p.x * 0.5 + 0.5) * window.innerWidth) + 'px';
    el.style.top = ((-p.y * 0.5 + 0.5) * window.innerHeight) + 'px';
    $('dmgLayer').appendChild(el); var t0 = performance.now();
    (function anim() {
      var k = (performance.now() - t0) / 800; if (k > 1) { el.remove(); return; }
      el.style.transform = 'translate(' + (1.2 * k * (Math.random() < .5 ? 1 : -1) * 10) + 'px,' + (-40 * k) + 'px) scale(' + (1 + (1 - k) * 0.2) + ')';
      el.style.opacity = 1 - k; requestAnimationFrame(anim);
    })();
  },
  selfDmg: function (v) { var d = document.createElement('div'); d.className = 'dmg self'; d.textContent = '-' + Math.round(v); d.style.left = (window.innerWidth / 2 + 40) + 'px'; d.style.top = (window.innerHeight / 2 + 60) + 'px'; $('dmgLayer').appendChild(d); var t0 = performance.now(); (function a() { var k = (performance.now() - t0) / 600; if (k > 1) { d.remove(); return; } d.style.opacity = 1 - k; d.style.transform = 'translateY(' + (-30 * k) + 'px)'; requestAnimationFrame(a); })(); },
  vignette: function () { var v = $('dmgVig'); v.style.opacity = 1; clearTimeout(this.vT); this.vT = setTimeout(function () { v.style.opacity = 0; }, 260); },
  center: function (t, sub, ms) {
    var c = $('centerMsg'); c.innerHTML = t + (sub ? '<small>' + sub + '</small>' : ''); c.className = 'on';
    clearTimeout(this.msgT); this.msgT = setTimeout(function () { c.className = ''; }, ms || 1900);
  },
  net: function (t, ok) { $('netText').textContent = t; $('netChip').className = 'chip' + (ok ? ' on' : ''); },
  board: function () {
    var body = $('boardBody'); body.innerHTML = '';
    var sl = Save.line();
    if (sl) { var sp = document.createElement('div'); sp.style.cssText = 'margin-bottom:8px;padding:7px 9px;border-radius:8px;background:rgba(155,93,229,.16);border:1px solid rgba(168,85,247,.35);font-size:12.5px'; sp.textContent = sl; body.appendChild(sp); }
    var rows = [{ name: Net.name + '（你）', k: P.kills, d: P.deaths, s: P.score, me: true, ping: Net.rtt }];
    Net.players.forEach(function (p) { rows.push({ name: p.name || '旅人', k: p.kills || 0, d: p.deaths || 0, s: p.score || 0, me: false, ping: Net.rtt }); });
    rows.sort(function (a, b) { return b.s - a.s; });
    rows.forEach(function (r, i) { var tr = document.createElement('tr'); if (r.me) tr.className = 'me'; tr.innerHTML = '<td>' + (i + 1) + '</td><td>' + r.name + '</td><td>' + r.k + '</td><td>' + r.d + '</td><td>' + r.s + '</td><td>' + (r.ping | 0) + 'ms</td>'; body.appendChild(tr); });
  },
  chat: function () {
    var log = $('chatLog'); log.innerHTML = '';
    Net.chat.slice(-7).forEach(function (c) { var d = document.createElement('div'); d.innerHTML = '<span>' + c.name + '</span> ' + c.text; log.appendChild(d); });
  },
  hist: function () {
    var box = $('histBody'); if (!box) return;
    var arr = Net.hist.slice(-200);
    if (!arr.length) { box.innerHTML = '<div class="hev"><i>--:--</i> 暂无记录 · 勇士的传说等你书写</div>'; return; }
    var p2 = function (n) { return ('0' + n).slice(-2); };
    var html = '';
    for (var i = arr.length - 1; i >= 0; i--) {
      var e = arr[i], t = new Date(e.at || Date.now());
      html += '<div class="hev"><i>' + p2(t.getHours()) + ':' + p2(t.getMinutes()) + ':' + p2(t.getSeconds()) + '</i> ' + esc(e.text || e.k || '') + '</div>';
    }
    box.innerHTML = html;
  },
  invite: function () {
    var u = Net.inviteLink();
    HUD.qr(u);                                   // ★ 先弹二维码（更好扩散）
    var ok = function () { HUD.center('邀请链接已复制', '也可以让朋友直接扫码', 2400); };
    try { if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(u).then(ok, function () {}); return; } } catch (e) {}
  },
  /* ★ 二维码弹窗：链接转二维码，可长按保存 / 截图发群（微信里发链接会被折叠，发图不会） */
  qr: function (url) {
    var p = $('qrPanel'); if (!p) return;
    $('qrUrl').textContent = url;
    var box = $('qrImg');
    try {
      if (typeof qrcode !== 'undefined') {
        var q = qrcode(0, 'M');               // 0 = 自动选版本，M = 15% 纠错
        q.addData(url); q.make();
        box.innerHTML = '<img src="' + q.createDataURL(7, 2) + '" style="width:min(56vw,220px);image-rendering:pixelated;background:#fff;padding:9px;border-radius:10px">';
      } else {
        box.textContent = '二维码库未加载，请复制下面的链接';
      }
    } catch (e) { box.textContent = '生成失败：' + (e.message || e); }
    p.style.display = 'flex';
  },
  qrHide: function () { var p = $('qrPanel'); if (p) p.style.display = 'none'; },
  promptLink: function (u) { try { window.prompt('邀请链接（复制发给好友，点开直接进服）', u); } catch (e) {} },
  tip3D: function () {
    if (load('tl_3d_tip', '') === '1') return;      // 点过就永不再提示
    var c = $('coach3d'); if (!c) return;
    c.style.display = 'flex';
    clearTimeout(this._tipT);
    this._tipT = setTimeout(function () { HUD.tip3DHide(); }, 60000);   // 60 秒自己消失
  },
  tip3DHide: function () { var c = $('coach3d'); if (c) c.style.display = 'none'; save('tl_3d_tip', '1'); clearTimeout(this._tipT); },
  minimap: function () {
    var c = $('minimap'); if (!c || !c.getContext) return;
    var g = c.getContext('2d'), W = c.width, Hh = c.height;
    var C = (window.__CITY3D && window.__CITY3D.Ground) ? window.__CITY3D : null;
    var GWW = G.GW, GHH = G.GH, CW = C ? C.GW : 0, CH = C ? C.GH : 0;
    var TOTW = GWW + (CW || 40), TOTH = Math.max(GHH, CH);
    var sc = Math.min(W / TOTW, Hh / TOTH), ox = (W - TOTW * sc) / 2, oy = (Hh - TOTH * sc) / 2;
    g.clearRect(0, 0, W, Hh); g.fillStyle = 'rgba(6,6,14,.94)'; g.fillRect(0, 0, W, Hh);
    function hm(h, base) {   // 高度 → 颜色
      var t = clamp(h / (C ? 11.5 : 1.6), 0, 1);
      return 'rgba(' + (base[0] + t * 90 | 0) + ',' + (base[1] + t * 96 | 0) + ',' + (base[2] + t * 120 | 0) + ',.95)';
    }
    // 营地（左）
    for (var v = 0; v < GHH; v++) for (var u = 0; u < GWW; u++) {
      var h = (G.H && G.H[v * GWW + u]) || 0;
      g.fillStyle = h > 1 ? 'rgba(150,154,176,.9)' : 'rgba(40,74,52,.95)';
      g.fillRect(ox + u * sc, oy + v * sc, sc + 0.5, sc + 0.5);
    }
    // ★ 城市（右，结构完整：街/墙/楼）
    if (C) for (var cv2 = 0; cv2 < CH; cv2++) for (var cu = 0; cu < CW; cu++) {
      var ch2 = (C.H && C.H[cv2 * CW + cu]) || 0;
      g.fillStyle = ch2 > 1 ? 'rgba(176,182,204,.95)' : 'rgba(30,34,52,.95)';
      g.fillRect(ox + (GWW + cu) * sc, oy + cv2 * sc, sc + 0.5, sc + 0.5);
    } else { g.fillStyle = 'rgba(30,34,52,.95)'; g.fillRect(ox + GWW * sc, oy, 40 * sc, TOTH * sc); }
    // 实体
    Host.each(function (m) { g.fillStyle = m.kind === 'golem' ? '#f59e0b' : (m.kind === 'wraith' ? '#60a5fa' : '#a855f7'); g.beginPath(); g.arc(ox + m.x * sc, oy + m.z * sc, 1.8, 0, 6.28); g.fill(); });
    Net.players.forEach(function (rp) { g.fillStyle = '#ff7a7a'; g.beginPath(); g.arc(ox + rp.x * sc, oy + rp.z * sc, 2.4, 0, 6.28); g.fill(); });
    g.fillStyle = '#7cffd0'; g.beginPath(); g.arc(ox + P.x * sc, oy + P.z * sc, 3, 0, 6.28); g.fill();
    // 玩家在城里的位置（hero.x 可能 > GWW）
    if (window.__OCTO) { var hx = window.__OCTO.hero.x, hy = window.__OCTO.hero.y; g.fillStyle = '#ffffff'; g.beginPath(); g.arc(ox + hx * sc, oy + hy * sc, 2.2, 0, 6.28); g.fill(); }
  },
};

/* ============================== HD-2D 后期：泛光 + 移轴景深 + 调色 ============================== */
var FXp = { on: true, fog: false };   // ★ 后处理管线保留（默认开）
function initFXpass() {
  var opt = { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter };
  FXp.rtScene = new THREE.WebGLRenderTarget(1, 1, opt);
  FXp.rtBright = new THREE.WebGLRenderTarget(1, 1, opt);
  FXp.rtBlur = new THREE.WebGLRenderTarget(1, 1, opt);
  FXp.quadScene = new THREE.Scene();
  FXp.quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  FXp.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), null); FXp.quadScene.add(FXp.quad);
  var VS = 'varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}';
  var BRIGHT = 'uniform sampler2D tDiffuse;uniform float uThr;varying vec2 vUv;void main(){vec3 c=texture2D(tDiffuse,vUv).rgb;float l=dot(c,vec3(0.299,0.587,0.114));float k=max(0.0,l-uThr)/max(0.001,1.0-uThr);gl_FragColor=vec4(c*k,1.0);}';
  var BLUR = 'uniform sampler2D tDiffuse;uniform vec2 uDir;varying vec2 vUv;void main(){vec3 s=vec3(0.0);float w[5];w[0]=0.227;w[1]=0.194;w[2]=0.121;w[3]=0.054;w[4]=0.016;s+=texture2D(tDiffuse,vUv).rgb*w[0];for(int i=1;i<5;i++){s+=texture2D(tDiffuse,vUv+uDir*float(i)).rgb*w[i];s+=texture2D(tDiffuse,vUv-uDir*float(i)).rgb*w[i];}gl_FragColor=vec4(s,1.0);}';
  var COMP = 'uniform sampler2D tScene,tBloom;uniform vec2 uTexel;uniform float uHaze;varying vec2 vUv;void main(){float d=abs(vUv.y-0.5);float r=clamp((d-0.16)/0.30,0.0,1.0);r=r*r*7.0;vec3 col=vec3(0.0);float tot=0.0;for(int i=-1;i<=1;i++){for(int j=-1;j<=1;j++){vec2 o=vec2(float(i),float(j))*uTexel*r*1.9;float w=1.0/(1.0+float(i*i+j*j));col+=texture2D(tScene,vUv+o).rgb*w;tot+=w;}}col/=tot;vec3 bl=texture2D(tBloom,vUv).rgb;col+=bl*0.34;float l=dot(col,vec3(0.299,0.587,0.114));col=mix(col*vec3(0.92,0.96,1.14),col*vec3(1.12,1.02,0.90),smoothstep(0.12,0.85,l));col=mix(vec3(l),col,1.16);col=mix(vec3(0.5),col,0.96);col=(col*(2.51*col+0.03))/(col*(2.43*col+0.59)+0.14);float hz=smoothstep(0.34,1.0,length((vUv-0.5)*vec2(1.1,1.0))*1.5);vec3 glow=vec3(0.06,0.06,0.10);col+=glow*hz*uHaze*0.26;col=mix(col,col*1.06+vec3(0.03,0.028,0.045),uHaze*hz*0.5);gl_FragColor=vec4(clamp(col,0.0,1.0),1.0);}';
  var mk = function (fs, u) { return new THREE.ShaderMaterial({ uniforms: u, vertexShader: VS, fragmentShader: fs, depthTest: false, depthWrite: false }); };
  FXp.mBright = mk(BRIGHT, { tDiffuse: { value: null }, uThr: { value: 0.80 } });
  FXp.mBlurX = mk(BLUR, { tDiffuse: { value: null }, uDir: { value: new THREE.Vector2() } });
  FXp.mBlurY = mk(BLUR, { tDiffuse: { value: null }, uDir: { value: new THREE.Vector2() } });
  FXp.mComp = mk(COMP, { tScene: { value: null }, tBloom: { value: null }, uTexel: { value: new THREE.Vector2() }, uHaze: { value: 0 } });
  resizeFX();
}
function resizeFX() {
  if (!FXp.rtScene) return;
  var dpr = renderer.getPixelRatio(), W = window.innerWidth, Hh = window.innerHeight;
  FXp.rtScene.setSize(W * dpr, Hh * dpr);
  var bw = Math.max(2, (W * dpr * 0.16) | 0), bh = Math.max(2, (Hh * dpr * 0.16) | 0);
  FXp.rtBright.setSize(bw, bh); FXp.rtBlur.setSize(bw, bh);
  FXp.mBlurX.uniforms.uDir.value.set(1.6 / bw, 0);
  FXp.mBlurY.uniforms.uDir.value.set(0, 1.6 / bh);
  FXp.mComp.uniforms.uTexel.value.set(1 / (W * dpr), 1 / (Hh * dpr));
}
function blit(mat) { FXp.quad.material = mat; renderer.render(FXp.quadScene, FXp.quadCam); }
function renderFrame() {
  try {
    if (FXp.on) renderPost();
    else { renderer.setRenderTarget(null); renderer.render(actionScene, cam()); }
  } catch (e) {
    window.__renderErr = (e && (e.stack || e.message)) || String(e);
    showFatal('渲染: ' + (e && e.message || e));
    try { FXp.on = false; renderer.setRenderTarget(null); renderer.render(actionScene, cam()); }
    catch (e2) { showFatal('渲染兜底失败: ' + e2.message); }
  }
}
function renderPost() {
  renderer.setRenderTarget(FXp.rtScene); renderer.clear(); renderer.render(actionScene, cam());
  FXp.mBright.uniforms.tDiffuse.value = FXp.rtScene.texture;
  renderer.setRenderTarget(FXp.rtBright); blit(FXp.mBright);
  FXp.mBlurX.uniforms.tDiffuse.value = FXp.rtBright.texture; renderer.setRenderTarget(FXp.rtBlur); blit(FXp.mBlurX);
  FXp.mBlurY.uniforms.tDiffuse.value = FXp.rtBlur.texture; renderer.setRenderTarget(FXp.rtBright); blit(FXp.mBlurY);
  FXp.mComp.uniforms.tScene.value = FXp.rtScene.texture; FXp.mComp.uniforms.tBloom.value = FXp.rtBright.texture;
  FXp.mComp.uniforms.uHaze.value = FXp.fog ? 1 : 0;
  renderer.setRenderTarget(null); blit(FXp.mComp);
}
function showFatal(msg) {
  try {
    var el = document.getElementById('fatalBox');
    if (!el) {
      el = document.createElement('div'); el.id = 'fatalBox';
      el.style.cssText = 'position:fixed;left:6px;bottom:6px;right:6px;max-height:38%;overflow:auto;z-index:99999;background:rgba(40,0,0,.92);color:#ff8080;font:11px/1.45 monospace;padding:6px 8px;border:1px solid #f66;border-radius:6px;white-space:pre-wrap';
      (document.body || document.documentElement).appendChild(el);
    }
    el.textContent = '\u26a0 ' + msg;
    el.style.display = 'block';
  } catch (_) {}
}
window.addEventListener('error', function (ev) { showFatal('JS: ' + (ev.message || (ev.error && ev.error.message) || '?')); });

/* ============================== 小地图底图 ============================== */
var mmBase = null;
function buildMmBase() {
  var N = G.GW; mmBase = document.createElement('canvas'); mmBase.width = mmBase.height = N;
  var g = mmBase.getContext('2d');
  for (var v = 0; v < N; v++) for (var u = 0; u < N; u++) {
    var h = G.H[v * N + u], sh = clamp((h - G.YMIN) / (G.WALL_H - G.YMIN), 0, 1);
    g.fillStyle = h >= G.WALL_H - 0.1 ? 'rgba(150,150,180,1)' : 'rgba(' + (22 + sh * 96 | 0) + ',' + (26 + sh * 102 | 0) + ',' + (44 + sh * 130 | 0) + ',1)';
    g.fillRect(u, v, 1, 1);
  }
}

/* ============================== 主循环 ============================== */
/* ============================== ★ 性能调速器（保 60 帧：低了自动降画质，够了自动恢复） ============================== */
var Perf = {
  fps: 60, lo: 0, hi: 0, level: 0,   // ★ 默认最低档(0)，交给自适应往上加；不再一进来就 3A
  cap60: true, _skip: 0, _acc: 0,
  // 自适应=原版三档(0.55/0.75/1.0)；手动=5 档像素比
  PR: null, MANUAL: 0,                        // MANUAL>0 时手动锁定档位，不再自动调
  apply: function () {
    var U = !!window.__ULTRA;
    if (this.MANUAL) {
      /* ★ 手动 5 档（APP 高 / 网页保守） */
      if (!this.PR) this.PR = U ? [0.75, 1.2, 1.7, 2.3, 3.25] : [0.55, 0.75, 1.0, 1.3, 1.5];
      var pr = this.PR[this.level];
      try { A.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, pr)); A.resize(); } catch (e) {}
      MobRender.range = (U ? [28, 34, 46, 58, 72] : [22, 34, 46, 58, 72])[this.level];
      try { A.setLean && A.setLean({ rain: [180, 320, 450, 520, 600][this.level], reflect: false, spotLights: false, pointLights: false }); } catch (e) {}
      if (FXp) FXp.on = true;
      try { if (A.scene && A.scene.fog) A.scene.fog.density = [0.016, 0.013, 0.010, 0.0082, 0.0068][this.level]; } catch (e) {}
    } else {
      /* ★★ 自适应 = 原版限流器，一模一样（0.55/0.75/1.0，三档，会掉到模糊） */
      var lv = Math.min(this.level, 2);
      try { A.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, [0.55, 0.75, 1.0][lv] * (A.LEAN ? A.LEAN.pixel : 1))); A.resize(); } catch (e) {}
      MobRender.range = [22, 34, 46][lv];
      try { A.setLean && A.setLean({ rain: [180, 320, 450][lv], reflect: false, spotLights: false, pointLights: false }); } catch (e) {}
      if (FXp) FXp.on = lv >= 1;
      try { if (A.scene && A.scene.fog) A.scene.fog.density = [0.014, 0.010, 0.0082][lv]; } catch (e) {}
    }
    window.__perfLevel = this.level;
    // ★ 阴影也跟档位：最低档直接关（手机上最吃性能的就是这个），中档以上才开
    this.shadow(this.MANUAL ? this.level : Math.min(this.level, 2));
  },
  shadow: function (lv) {
    var on = lv >= 1;
    if (this._sh === on) return;
    this._sh = on;
    try {
      A.renderer.shadowMap.enabled = on;
      A.renderer.shadowMap.needsUpdate = true;
      A.scene.traverse(function (o) {
        if (!o.material) return;
        var ms = Array.isArray(o.material) ? o.material : [o.material];
        for (var i = 0; i < ms.length; i++) if (ms[i]) ms[i].needsUpdate = true;
      });
    } catch (e) {}
  },
  tick: function (f) {                       // 每秒调用一次
    this.fps = f;
    if (this.MANUAL) return;                  // 用户手动锁档 → 不自动调
    // ★ 自适应（像网页版）：掉帧快降、流畅慢升，5 档全覆盖
    var loAt = 52, hiAt = 58;      // ★ 与网页版完全一致（真的会升会降）
    if (f < loAt && this.level > 0) { this.lo++; this.hi = 0; if (this.lo >= 2) { this.level--; this.lo = 0; this.apply(); } }
    else if (f > hiAt && this.level < 2) { this.hi++; this.lo = 0; if (this.hi >= 5) { this.level++; this.hi = 0; this.apply(); } }   // ★ 自适应上限=2（原版三档）
    else { this.lo = 0; this.hi = 0; }
  },
  // ★ 手动档位：0标清 1高清 2超清 3极高 4顶级3A
  setLevel: function (lv) { this.level = Math.max(0, Math.min(4, lv)); this.MANUAL = 1; this.apply(); return this.level; },
  // ★ 自适应：永远从最低档起步（首帧最省），帧率够就自己往上爬
  auto: function () { this.MANUAL = 0; this.level = 0; this.apply(); return '自适应'; },
  name: function () { return this.MANUAL ? ['标清', '高清', '超清', '极高', '顶级3A'][this.level] : '自适应'; },
  tips: ['最省电 · 老机型', '清晰与流畅平衡', '高画质', '很高画质 · 旗舰', '顶级3A · 拉满'],
  // 60 帧上限（显示刷新率 >60 时省电/省热；掉帧时不限，保证能跑到 60）
  limit: function (now) { if (!this.cap60) return false; this._acc += (now - (this._last || now)); this._last = now; return false; },
  // ★ 帧率上限：hz=60 稳（省电省热）/ hz=120 跟手（高刷屏满帧）
  hz: 60,
  minGap: function () { return (this.hz >= 120 ? 7.4 : 15.2) - 0.1; },
  setHz: function (h) {
    this.hz = (h >= 120 ? 120 : 60);
    this.cap60 = true;
    try { localStorage.setItem('tl_hz', String(this.hz)); } catch (e) {}
    return this.hz;
  },
};

var running = false, lastT = performance.now(), frames = 0, lastF = lastT, fps = 0, elapsed = 0, mmT = 0;
function loop(now) {
  requestAnimationFrame(loop);
  // ★ 60 帧上限：显示刷新率 >60 时主动跳帧（省一半 GPU 时间 → 更稳、更省电/热）
  var now = performance.now();
  if (Perf.cap60 && now - (loop._t || 0) < Perf.minGap()) return;
  loop._t = now;
  var dt = Math.min((now - lastT) / 1000, 0.05); lastT = now;
  if (!running) return;
  try { loopBody(dt, now); }
  catch (e) { window.__loopErr = (e && (e.stack || e.message)) || String(e); try { $('perf').textContent = 'LOOPERR ' + String(e.message || e); } catch (_) {} }
}
function loopBody(dt, now) {
  try {
  if (HOST && window.__OCTO) { var _hh = window.__OCTO.hero; P.x = _hh.x; P.z = _hh.y; P.y = 0; if (window.__OCTO.yaw) P.yaw = window.__OCTO.yaw(); }
  elapsed += dt; ScreenShake.update(dt);

  P.ads = Input.ads && P.alive;
  if (!HOST) movePlayer(dt);

  if (P.fireCd > 0) P.fireCd -= dt;
  if (P.reloading > 0) { P.reloading -= dt; if (P.reloading <= 0) Combat.finishReload(); }
  if (P.nadeCd > 0) P.nadeCd -= dt;
  var w = WMAP[P.weapon];
  if (Input.fireOnce) { Input.fireOnce = false; Combat.fire(); }        // ★ 轻点=立即开一枪（不再被帧间隔吞掉）
  if (Input.fire) { if (w.auto) Combat.fire(); else if (!Input._fired) { Combat.fire(); Input._fired = true; } } else Input._fired = false;
  if (Input.reload) { Input.reload = false; Combat.reload(); }
  if (Input.swap) { Input.swap = false; Combat.next(); }
  if (Input.nade) { Input.nade = false; Grenade.throwFrom(); }
  if (!P.alive && now >= P.respawnAt) Combat.respawn();

  Recoil.p = lerp(Recoil.p, 0, Math.min(1, dt * 7.5));    // 后坐力自动回落
  Recoil.y = lerp(Recoil.y, 0, Math.min(1, dt * 6.5));
  if (P.alive && Cam.autoAim) aimAssist();   // ★ 默认不自动转视角（会抢走你正在瞄的目标）
  try { Build.rescue(dt, !!(Input.mx || Input.my || Input.keys['w'] || Input.keys['a'] || Input.keys['s'] || Input.keys['d'])); } catch (e) {}
  CamIntro.update();
  if (!HOST) updateCamera(dt);
  if (!HOST) updateHero(dt, elapsed);

  var targets = [{ id: Net.id, x: P.x, z: P.z, y: P.y, hp: P.alive ? P.hp : 0 }];
  Net.players.forEach(function (rp) { if (rp.alive) targets.push({ id: rp.id, x: rp.x, z: rp.z, y: rp.y, hp: rp.hp }); });
  if (Net.connected) {
    Host.update(dt, targets);                                  // ★ 内部按归属模拟：自己的算 AI，别人的只插值
    Host.snapAcc = (Host.snapAcc || 0) + dt;
    if (Host.snapAcc > 1 / Host.SNAP_HZ) { Host.snapAcc = 0; Net.mobs(Host.snapshot()); }
  } else Host.update(dt, targets);

  A.update(dt, cam().position);
  BossSys.update(dt);
  MobRender.sync();
  Homing.update(dt);
  Proj.update(dt); Grenade.update(dt); FX.update(dt);
  MotionDir.update(dt);
  Net.interp(dt);                    // ★ 让远端玩家真的动起来
  Net.sendState(P);
  } catch (e) { window.__logicErr = (e && (e.stack || e.message)) || String(e); }

  updateAim();                       // ★ 3D 准星（世界标记）
  var _xh = $('xhair');
  if (_xh) {
    if (A.getCamMode() === 'hd2d') {            // ★ HD-2D：屏幕准星（可拖动）
      _xh.style.display = 'block'; _xh.style.margin = '0';
      _xh.style.left = (((Input.aimX || 0) * 0.5 + 0.5) * 100).toFixed(1) + '%';
      _xh.style.top = (((-(Input.aimY || 0)) * 0.5 + 0.5) * 100).toFixed(1) + '%';
      _xh.style.transform = 'translate(-50%,-50%)';
    } else { _xh.style.display = 'none'; }
  }
  HUD.score(); HUD.vitals();
  mmT += dt; if (mmT > 0.5) { mmT = 0; if (!mmBase) buildMmBase(); HUD.minimap(); }

  if (!HOST) try { renderFrame(); } catch (e) { window.__renderErr = (e && (e.stack || e.message)) || String(e); try { renderer.setRenderTarget(null); renderer.render(actionScene, cam()); } catch (_) {} }
  frames++; if (now - lastF > 1000) {
    fps = frames * 1000 / (now - lastF); frames = 0; lastF = now;
    Perf.tick(fps);
    $('perf').textContent = window.innerWidth + 'x' + window.innerHeight + '  ' + fps.toFixed(0) + ' fps' +
      (window.__houseDraws ? ' · 房子 ' + window.__houseDraws + ' dc' : '') +
      '\n怪物 ' + Host.mobs.filter(function (m) { return m.alive; }).length + ' · 玩家 ' + Net.peers;
  }
}

/* 远端玩家立绘 */
var MotionDir = {
  avatars: {},
  update: function (dt) {
    var alive = {};
    Net.players.forEach(function (rp, id) {
      alive[id] = 1;
      var a = this.avatars[id];
      if (!a) {
        // ★ 用原色（和自己同款画风），靠"队伍色描边 + 名字"区分，而不是把整张画染脏
        var teamCol = Net.teamColor(id);
        var mat = spriteMat(CH.S, { amb: 0.7, tint: 0xffffff });     // 原色，画风与本人一致
        mat.uniforms.uOutline = { value: new THREE.Color(teamCol) };  // 队伍色描边
        mat.uniforms.uOutlineW = { value: 0.30 };
        var mesh = makeBillboard(2.05, mat); actionScene.add(mesh);
        var sh = addShadow(1.5); actionScene.add(sh);
        var bar = makeHpBar(1.6); actionScene.add(bar);
        var nm = makeNameTag(rp.name || '旅人', teamCol); actionScene.add(nm);
        a = this.avatars[id] = { mesh: mesh, mat: mat, sh: sh, bar: bar, nm: nm, walk: 0, name: rp.name };
      }
      // ★ x/z 已在 Net.interp 里平滑过了，这里直接用，不要再插值一次（会二次拖慢）
      var tx = rp.x, tz = rp.z;
      var floorY = G.h(rp.x, rp.z);
      a.mesh.position.set(tx, floorY, tz);
      a.mesh.rotation.y = billboardYaw(tx, tz);
      var d = facingDir(tx, tz, rp.yaw || 0, cam().position); if (CH[d] && a.mat.uniforms.uMap.value !== CH[d]) a.mat.uniforms.uMap.value = CH[d];
      a.mat.uniforms.uTint.value.setHex(rp.alive ? 0xffffff : 0x666677);
      a.mat.uniforms.uOpacity.value = rp.alive ? 1 : 0.45;
      a.sh.position.set(tx, floorY + 0.04, tz);
      a.bar.position.set(tx, floorY + 2.35, tz);
      drawHp(a.bar, (rp.hp || 0) / (rp.maxHp || 100), rp.name || '旅人', Net.teamColorHex(id));
      if (a.nm) { a.nm.position.set(tx, floorY + 3.0, tz); }
    }, this);
    for (var id in this.avatars) if (!alive[id]) { var a = this.avatars[id]; actionScene.remove(a.mesh); actionScene.remove(a.sh); actionScene.remove(a.bar); if (a.nm) actionScene.remove(a.nm); delete this.avatars[id]; }
  },
};

/* 切换沙盒/战斗：立刻让世界安静下来 / 恢复刷怪 */
function applySandbox() {
  try {
    if (SANDBOX) {
      Host.mobs.forEach(function (m) { m.alive = false; });
      Host.mobs.length = 0;
      BossSys.list.forEach(function (b) {
        b.alive = false; b.spawned = false;
        if (b.obj) b.obj.visible = false;
        if (b.sh) b.sh.visible = false;
      });
      BossSys.active = null;
      var bb = $('bossBar'); if (bb) bb.style.display = 'none';
    } else {
      Host.init();
      BossSys.init();
      BossSys.activate(BossSys.list[0]);
    }
  } catch (e) { window.__sbErr = String((e && e.message) || e); }
}

/* ============================== ★ 分享领神器（邀请追踪） ==============================
   原理：我生成邀请链接 → 好友点开进来 → 我用 retain 记一条 ref/<我的id>/<好友id>。
        retain 天然去重（同一好友重复点不重复计数），换设备也还在。
   里程碑：3 人 → 解锁神器「天泪·虚空之刃」。
   ⚠️ 诚实说明：全部在客户端，认真的人用无痕窗口也能刷。但刷的成本 ≈ 真分享的成本，
      对小规模游戏够用；真要防刷需要服务端账号体系。
   ============================================================================ */
var Ref = {
  invited: {},              // 好友id -> 1
  need: 3,
  count: function () { var n = 0; for (var k in this.invited) n++; return n; },
  add: function (k) {
    if (!k) return;
    var parts = k.split('/'), who = parts[parts.length - 1];
    if (!who || who === Net.id) return;                    // 不能自己邀请自己
    if (this.invited[who]) return;
    var before = this.count();
    this.invited[who] = 1;
    if (this.count() > before) this.refresh(true);
  },
  report: function () {
    var inv = Net.inv;
    if (!inv || inv === Net.id) return;                    // 没邀请人 / 自己点自己 → 不记
    if (!Net.connected) return;
    try {
      Net.pub(Net.base() + 'ref/' + inv + '/' + Net.id, JSON.stringify({ name: Net.name, at: Date.now() }), true);
    } catch (e) {}
  },
  refresh: function (silent) {
    var n = this.count(), need = this.need;
    var el = $('bShare'); if (el) el.textContent = '分享(' + n + ')';
    if (!silent) return;
    if (n >= need) {
      HUD.center('🎉 神器已解锁！', '按 8 或滚轮切出「天泪·虚空之刃」', 4200);
      Sfx.waveUp(); Net.histPub({ k: 'relic', text: Net.name + ' 集齐 ' + need + ' 位好友，唤醒了虚空之刃！' });
    } else {
      HUD.center('好友 +1（' + n + '/' + need + '）', '再来 ' + (need - n) + ' 位就能解锁神器', 2600);
      Sfx.kill();
    }
  },
};

/* ============================== ★ 共享建造（沙盒核心玩法） ==============================
   设计：一格建筑 = 一条 retained 消息，主题 base()+'blk/<x>_<y>'。
        · retain=true → broker 替你永久存着，任何人进来订阅 blk/# 就拿到"全服已建好的一切"
        · 拆 = 向同主题发空载荷 + retain → broker 清掉（和 luhuo 的历史清理同一套）
   → 不需要服务器、不需要账号，所有人的建筑天然共享、天然持久、离线也在。
   ============================================================================ */
/* ★★ 建筑块材质工厂：全部走 assets/tex 的扫描 PBR（albedo+法线+粗糙）★★ */
var BM = (function () {
  var tc = {}, ldr = new THREE.TextureLoader();
  function tex(n) {
    var k = 't' + n; if (tc[k]) return tc[k];
    var t = ldr.load('assets/tex/' + n + '.jpg'); t.wrapS = t.wrapT = THREE.RepeatWrapping;
    if (THREE.sRGBEncoding) t.encoding = THREE.sRGBEncoding;         // ★ 修：颜色空间
    try { t.anisotropy = 4; } catch (e) {}
    tc[k] = t; return t;
  }
  function mat(name, o) {
    o = o || {}; var rep = o.rep || 1;
    // ★ 建筑块默认带一点自发光（夜景里绝不发黑）；显式传 emissive 则用它
    var em = (o.emissive != null) ? o.emissive : 0x241a10;
    var emI = (o.emInt != null) ? o.emInt : 0.55;
    var key = ['m', name, rep, o.color || '', o.rough, o.metal, em, emI].join('|');
    if (tc[key]) return tc[key];
    var map = tex(name).clone(); map.needsUpdate = true; map.repeat.set(rep, rep);
    var m = new THREE.MeshStandardMaterial({ map: map, roughness: o.rough != null ? o.rough : 0.9, metalness: o.metal != null ? o.metal : 0.06 });
    try {
      var nt = ldr.load('assets/tex/' + name + '_n.jpg'); nt.wrapS = nt.wrapT = THREE.RepeatWrapping; nt.repeat.set(rep, rep); m.normalMap = nt;
      var rt = ldr.load('assets/tex/' + name + '_r.jpg'); rt.wrapS = rt.wrapT = THREE.RepeatWrapping; rt.repeat.set(rep, rep); m.roughnessMap = rt;
    } catch (e) {}
    if (o.color) m.color.setHex(o.color);
    m.emissive.setHex(em); m.emissiveIntensity = emI;              // ★ 自发光
    try { var envT = (window.ARENA && ARENA.cubeRT) ? ARENA.cubeRT.texture : (window.__CITY3D && __CITY3D.cubeRT ? __CITY3D.cubeRT.texture : null);
      if (envT) { m.envMap = envT; m.envMapIntensity = 0.6; } } catch (e) {}   // ★ 环境反射（反出城市霓虹）
    m.side = THREE.DoubleSide; tc[key] = m; return m;
  }
  function bx(grp, mm, w, h, d, x, y, z, rz) {
    var e = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mm); e.position.set(x || 0, y || 0, z || 0);
    if (rz) e.rotation.z = rz; e.castShadow = e.receiveShadow = true; grp.add(e); return e;
  }
  return { tex: tex, mat: mat, box: bx };
})();

var Build = {
  on: false, kind: 'wall_stone', mode: 'place', ghost: null, list: new Map(), meshes: {},
  /* ★ 20 种建筑块：材质全部扫描 PBR；形状 7 类（方块/薄板/台阶/斜坡/圆柱/拱/组合） */
  BLOCKS: [
    { id: 'wall_stone', n: '石墙',   g: 'box',       m: 'stone',     rep: 1, cat: '墙 体' },
    { id: 'wall_brick', n: '砖墙',   g: 'box',       m: 'brick',     rep: 1, cat: '墙 体' },
    { id: 'wall_conc',  n: '混凝土', g: 'box',       m: 'concrete',  rep: 1, cat: '墙 体' },
    { id: 'wall_wood',  n: '木墙板', g: 'box',       m: 'planks',    rep: 1, cat: '墙 体' },
    { id: 'wall_metal', n: '金属板', g: 'box',       m: 'metal',     rep: 1, metal: 0.85, rough: 0.35, cat: '墙 体' },
    { id: 'glass',      n: '玻璃幕', g: 'box_glass', cat: '墙 体' },
    { id: 'floor',  n: '地板',   g: 'floor',  m: 'planks',   rep: 1, rough: 0.8, cat: '结 构' },
    { id: 'slab',   n: '平台板', g: 'slab',   m: 'concrete', rep: 1, cat: '结 构' },
    { id: 'step',   n: '台阶',   g: 'step',   m: 'stone',    rep: 1, cat: '结 构' },
    { id: 'ramp',   n: '斜坡',   g: 'ramp',   m: 'concrete', rep: 1, cat: '结 构' },
    { id: 'pillar', n: '圆柱',   g: 'pillar', m: 'marble',   rep: 1, cat: '结 构' },
    { id: 'column', n: '方柱',   g: 'column', m: 'concrete', rep: 1, cat: '结 构' },
    { id: 'arch',   n: '拱门',   g: 'arch',   m: 'stone',    rep: 1, cat: '结 构' },
    { id: 'fence',  n: '栏杆',   g: 'fence',  m: 'metal',    rep: 1, metal: 0.85, rough: 0.4, cat: '结 构' },
    { id: 'roof',   n: '坡屋顶', g: 'roof',   m: 'roof',     rep: 1, cat: '结 构' },
    { id: 'crate',  n: '木箱',   g: 'crate',  m: 'planks',   rep: 1, rough: 0.85, cat: '道 具' },
    { id: 'barrel', n: '油桶',   g: 'barrel', m: 'rustmetal',rep: 1, metal: 0.6, rough: 0.5, cat: '道 具' },
    { id: 'lamp',   n: '路灯',   g: 'lamp',   cat: '道 具' },
    { id: 'crystal',n: '晶石',   g: 'crystal',cat: '道 具' },
    { id: 'planter',n: '花坛',   g: 'planter',m: 'stone',    rep: 1, cat: '道 具' },
  ],
  def: function (id) { for (var i = 0; i < this.BLOCKS.length; i++) if (this.BLOCKS[i].id === id) return this.BLOCKS[i]; return this.BLOCKS[0]; },
  name: function (id) { return this.def(id).n; },
  /* ★ 按定义造出几何（底部对齐 y=0，占 1 格） */
  build: function (id) {
    var d = this.def(id), grp = new THREE.Group(), M = d.m ? BM.mat(d.m, d) : null, g = d.g;
    if (g === 'box') BM.box(grp, M, 0.96, 1.55, 0.96, 0, 0.775, 0);
    else if (g === 'box_glass') {
      var gm = new THREE.MeshStandardMaterial({ color: 0x2b4a6e, metalness: 1, roughness: 0.06, transparent: true, opacity: 0.58, side: THREE.DoubleSide });
      var envT = (window.ARENA && ARENA.cubeRT) ? ARENA.cubeRT.texture : null; if (envT) { gm.envMap = envT; gm.envMapIntensity = 2.4; }
      BM.box(grp, gm, 0.96, 1.55, 0.96, 0, 0.775, 0);
    }
    else if (g === 'floor') BM.box(grp, M, 0.98, 0.14, 0.98, 0, 0.07, 0);
    else if (g === 'slab') BM.box(grp, M, 0.98, 0.2, 0.98, 0, 0.62, 0);
    else if (g === 'step') { BM.box(grp, M, 0.96, 0.78, 0.96, 0, 0.39, 0); BM.box(grp, M, 0.96, 0.77, 0.46, 0, 1.165, -0.25); }
    else if (g === 'ramp') {
      var sh = new THREE.Shape(); sh.moveTo(-0.48, 0); sh.lineTo(0.48, 0); sh.lineTo(0.48, 1.55); sh.lineTo(-0.48, 0);
      var rg = new THREE.ExtrudeGeometry(sh, { depth: 0.96, bevelEnabled: false }); rg.translate(0, 0, -0.48);
      var rmp = new THREE.Mesh(rg, M); rmp.castShadow = rmp.receiveShadow = true; grp.add(rmp);
    }
    else if (g === 'pillar') { var cy = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.30, 1.55, 16), M); cy.position.y = 0.775; cy.castShadow = cy.receiveShadow = true; grp.add(cy); }
    else if (g === 'column') BM.box(grp, M, 0.52, 1.55, 0.52, 0, 0.775, 0);
    else if (g === 'arch') { BM.box(grp, M, 0.28, 1.0, 0.5, -0.34, 0.5, 0); BM.box(grp, M, 0.28, 1.0, 0.5, 0.34, 0.5, 0); var tq = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.14, 8, 16, Math.PI), M); tq.position.y = 1.0; tq.castShadow = true; grp.add(tq); }
    else if (g === 'fence') { BM.box(grp, M, 0.06, 1.0, 0.06, -0.44, 0.5, 0); BM.box(grp, M, 0.06, 1.0, 0.06, 0.44, 0.5, 0); BM.box(grp, M, 0.94, 0.05, 0.05, 0, 0.92, 0); BM.box(grp, M, 0.94, 0.05, 0.05, 0, 0.55, 0); }
    else if (g === 'roof') { BM.box(grp, M, 0.76, 0.1, 1.06, -0.26, 0.9, 0, 0.72); BM.box(grp, M, 0.76, 0.1, 1.06, 0.26, 0.9, 0, -0.72); }
    else if (g === 'crate') {
      BM.box(grp, M, 0.84, 0.84, 0.84, 0, 0.42, 0);
      var fm = BM.mat('planks', { rep: 1, rough: 0.72, color: 0x7a5535 });
      BM.box(grp, fm, 0.9, 0.09, 0.9, 0, 0.06, 0); BM.box(grp, fm, 0.9, 0.09, 0.9, 0, 0.79, 0);
      [[-0.43, 0], [0.43, 0], [0, -0.43], [0, 0.43]].forEach(function (p) { BM.box(grp, fm, p[0] ? 0.07 : 0.9, 0.84, p[0] ? 0.9 : 0.07, p[0], 0.42, p[1]); });
    }
    else if (g === 'barrel') { var by = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.9, 16), M); by.position.y = 0.45; by.castShadow = by.receiveShadow = true; grp.add(by); }
    else if (g === 'lamp') {
      var pM = BM.mat('metal', { rep: 1, metal: 0.85, rough: 0.4 });
      BM.box(grp, pM, 0.1, 2.7, 0.1, 0, 1.35, 0);
      var hd = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.24, 0.36), new THREE.MeshBasicMaterial({ color: 0xffd9a0 })); hd.position.y = 2.78; grp.add(hd);
      var pl = new THREE.PointLight(0xffc07a, 0.85, 13, 2); pl.position.y = 2.6; grp.add(pl);
    }
    else if (g === 'crystal') {
      var cm = new THREE.MeshStandardMaterial({ color: 0x9b5de5, emissive: 0x7c3aed, emissiveIntensity: 1.7, transparent: true, opacity: 0.78, roughness: 0.1, metalness: 0.2 });
      var oc = new THREE.Mesh(new THREE.OctahedronGeometry(0.48, 0), cm); oc.position.y = 0.85; oc.scale.y = 1.7; grp.add(oc);
      var pl2 = new THREE.PointLight(0xa855f7, 0.7, 9, 2); pl2.position.y = 1.2; grp.add(pl2);
    }
    else if (g === 'planter') {
      BM.box(grp, M, 0.96, 0.46, 0.96, 0, 0.23, 0);
      BM.box(grp, BM.mat('dirt', { rep: 1 }), 0.8, 0.1, 0.8, 0, 0.48, 0);
      var lf = BM.mat('foliage', { rep: 1 }); var lc = new THREE.MeshStandardMaterial({ map: BM.tex('foliage'), roughness: 0.9, metalness: 0, side: THREE.DoubleSide });
      [[-0.2, 0], [0.2, 0], [0, -0.2]].forEach(function (p, i) { var bush = new THREE.Mesh(new THREE.SphereGeometry(0.26, 8, 6), lc); bush.position.set(p[0], 0.68 + i * 0.06, p[1]); bush.castShadow = true; grp.add(bush); });
    }
    return grp;
  },
  key: function (x, z) { return Math.floor(x) + ',' + Math.floor(z); },
  solidAt: function (x, z) { return this.list.has(this.key(x, z)); },

  init: function () {
    this._ghostMat = new THREE.MeshStandardMaterial({ color: 0x9b5de5, transparent: true, opacity: 0.45, depthWrite: false, side: THREE.DoubleSide });
    this._mkGhost();
    this._buildBar();
    // 建造出来的方块要能挡路：接进地形碰撞
    var g = G, _cs = g.canStand;
    g.canStand = function (nx, nz, y, step) {
      if (Build.list.size && Build.solidAt(nx, nz)) return false;
      return _cs.call(g, nx, nz, y, step);
    };
  },
  _mkGhost: function () {
    if (this.ghost) { actionScene.remove(this.ghost); }
    var g = this.build(this.kind);
    g.traverse(function (o) { if (o.isMesh) { o.material = Build._ghostMat; o.castShadow = false; o.receiveShadow = false; } });
    this.ghost = g; g.visible = false; actionScene.add(g);
    this._ghostBad = false;
  },
  _buildBar: function () {
    var bar = $('buildBar'); if (!bar) return;
    var h = '', last = '';
    this.BLOCKS.forEach(function (b) {
      if (b.cat !== last) { last = b.cat; if (b.cat) h += '<span class="catlabel">' + b.cat + '</span>'; }
      h += '<button class="bk" data-bk="' + b.id + '">' + b.n + '</button>';
    });
    h += '<span class="sep"></span><button class="bk del" id="bk_del">拆除</button><button class="bk" id="bk_close">✕</button>';
    bar.innerHTML = h;
    var self = this;
    Array.prototype.forEach.call(bar.querySelectorAll('[data-bk]'), function (b) {
      b.addEventListener('click', function () { self.setKind(b.getAttribute('data-bk')); });
    });
    var dl = $('bk_del'); if (dl) dl.addEventListener('click', function () { self.setMode(self.mode === 'del' ? 'place' : 'del'); });
    var cl = $('bk_close'); if (cl) cl.addEventListener('click', function () { if (self.on) self.toggle(); });
  },
  mkMesh: function (k, o) {
    if (this.meshes[k]) return;
    var p = k.split(','), x = +p[0], z = +p[1];
    var m = this.build(o.t);                       // ★ 按种类造真实形状 + 扫描 PBR 材质
    m.position.set(x + 0.5, G.h(x + 0.5, z + 0.5), z + 0.5);
    actionScene.add(m); this.meshes[k] = m;
  },
  rmMesh: function (k) {
    var m = this.meshes[k]; if (!m) return;
    actionScene.remove(m);
    try { m.geometry.dispose(); m.material.dispose(); } catch (e) {}
    delete this.meshes[k];
  },
  // 收到（本地/远端/历史）的一格
  apply: function (k, o) {
    if (!k) return;
    if (o && o.t) { this.list.set(k, o); this.mkMesh(k, o); }
    else { this.list.delete(k); this.rmMesh(k); }
  },
  place: function (x, z) {
    // ★ 禁止把方块放在玩家自己（或别人）身上 → 从源头杜绝"把自己埋住/围死"
    if (Math.floor(x) === Math.floor(P.x) && Math.floor(z) === Math.floor(P.z)) {
      HUD.center('不能放在自己脚下', '离开一格再放', 1400); Sfx.deny(); return;
    }
    if (Math.hypot(x - P.x, z - P.z) < 1.2) {
      HUD.center('离自己太近', '站远一点再放', 1400); Sfx.deny(); return;
    }
    var k = this.key(x, z), o = { t: this.kind, by: Net.name, at: Date.now() };
    Net.pub(Net.base() + 'blk/' + k, JSON.stringify(o), true);   // 先广播（retain 当存储）
    this.apply(k, o);                                            // 本地立刻可见
    Sfx.pickup(); HUD.center('已放置 · ' + this.name(this.kind), '', 900);
  },
  remove: function (x, z) {
    var k = this.key(x, z);
    Net.pub(Net.base() + 'blk/' + k, '', true);
    this.apply(k, null);
    Sfx.deny(); HUD.center('已拆除', '', 900);
  },
  // 屏幕坐标 → 地面 → 放置/拆除
  _stuck: 0,
  rescue: function (dt, wantMove) {
    if (!this.list.size) { this._stuck = 0; return; }
    var h = window.__OCTO && window.__OCTO.hero;
    if (!h) return;
    if (!wantMove) { this._stuck = 0; this._lx = h.x; this._lz = h.y; return; }
    var m = Math.hypot(h.x - (this._lx === undefined ? h.x : this._lx), h.y - (this._lz === undefined ? h.y : this._lz));
    this._lx = h.x; this._lz = h.y;
    this._stuck = (m < 0.008) ? this._stuck + dt : 0;
    if (this._stuck < 0.7) return;
    this._stuck = 0;
    // 找离玩家最近的一格拆掉（只拆"挡住去路"的那一格）
    var best = null, bd = 1e9;
    this.list.forEach(function (v, k) {
      var px = k.split(','), cx = +px[0] + 0.5, cz = +px[1] + 0.5;
      var d = Math.hypot(cx - h.x, cz - h.y);
      if (d < bd) { bd = d; best = k; }
    });
    if (best) {
      var q = best.split(',');
      this.remove(+q[0], +q[1]);
      HUD.center('自动脱困', '已拆掉挡路的方块', 1600);
    }
  },
  tap: function (nx, ny) {
    if (!this.on) return false;
    try {
      var rc = new THREE.Raycaster();
      rc.setFromCamera({ x: nx, y: ny }, cam());
      var hit = new THREE.Vector3();
      if (!rc.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hit)) return false;
      var x = hit.x, z = hit.z, d = Math.hypot(x - P.x, z - P.z);
      if (d > 16) { HUD.center('太远了', '走近一点再放', 1200); return false; }
      if (G.h(x, z) > 0.35) { HUD.center('这里放不了', '找一块平地', 1200); return false; }
      if (this.mode === 'del') {
        if (this.solidAt(x, z)) this.remove(x, z); else HUD.center('这里没有方块', '', 900);
      } else if (this.solidAt(x, z)) this.remove(x, z); else this.place(x, z);
      return true;
    } catch (e) { window.__buildErr = String((e && e.message) || e); return false; }
  },
  follow: function (nx, ny) {
    if (!this.on || !this.ghost) { if (this.ghost) this.ghost.visible = false; return; }
    try {
      var rc = new THREE.Raycaster(); rc.setFromCamera({ x: nx, y: ny }, cam());
      var hit = new THREE.Vector3();
      if (!rc.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hit)) { this.ghost.visible = false; return; }
      var gx = Math.floor(hit.x) + 0.5, gz = Math.floor(hit.z) + 0.5;
      var bad = (Math.hypot(gx - P.x, gz - P.z) > 16) || (G.h(hit.x, hit.z) > 0.35);
      this.ghost.position.set(gx, G.h(gx, gz), gz);
      this.ghost.visible = true;
      this._ghostMat.color.setHex(bad ? 0xff5f6d : (this.solidAt(gx, gz) ? 0xffd166 : 0x9b5de5));
    } catch (e) { this.ghost.visible = false; }
  },
  cycleKind: function () {
    var i = 0; for (var j = 0; j < this.BLOCKS.length; j++) if (this.BLOCKS[j].id === this.kind) i = j;
    this.setKind(this.BLOCKS[(i + 1) % this.BLOCKS.length].id);
  },
  mode: 'place',                                  // place=放置 / del=拆除
  toggle: function () {
    this.on = !this.on;
    if (!this.on && this.ghost) this.ghost.visible = false;
    this.bar();
    HUD.center(this.on ? '建造模式 · 开' : '建造模式 · 关',
      this.on ? '点地面放置 · 点已有方块即拆除' : '', 2200);
    Sfx.ui();
  },
  setKind: function (k) { this.kind = k; this.mode = 'place'; this._mkGhost(); this.bar(); Sfx.ui(); HUD.center('方块 · ' + this.name(k), '', 900); },
  setMode: function (m) { this.mode = m; this.bar(); Sfx.ui(); HUD.center(m === 'del' ? '拆除模式' : '放置模式', '', 900); },
  bar: function () {
    var el = $('buildBar'); if (!el) return;
    el.style.display = this.on ? 'flex' : 'none';
    var b = $('bBuild'); if (b) b.className = this.on ? 'on' : '';
    var self = this;
    Array.prototype.forEach.call(el.querySelectorAll('[data-bk]'), function (x) { x.className = (self.kind === x.getAttribute('data-bk')) ? 'on' : ''; });
    var pd = $('bk_del'); if (pd) pd.className = (this.mode === 'del') ? 'on' : '';
  },
};

/* ============================== ★ 全服统一出生点 ============================== */
//  规则：所有玩家（含从分发链接进来的）都生在同一个世界固定点，
//        只在 ±3 格内按 id 做「确定性」散布 —— 同一玩家永远同一偏移，
//        既不完全重叠，又保证一定互相看得见。
//  ⚠️ 宿主模式（index.html）下 P 每帧从 __OCTO.hero 同步 → 必须改 hero 才真正生效。
var SPAWN_PT = { x: 36.5, y: 21.5 };        // 与 index.html 里 hero 的初值一致
function placeAtSpawn() {
  var h = 0;
  for (var i = 0; i < Net.id.length; i++) h = (h * 31 + Net.id.charCodeAt(i)) | 0;
  var sx = SPAWN_PT.x + ((h % 7) - 3), sz = SPAWN_PT.y + (((h >> 3) % 7) - 3);
  if (!G.canStand(sx, sz, 0, 1.0)) { sx = SPAWN_PT.x; sz = SPAWN_PT.y; }
  if (!G.canStand(sx, sz, 0, 1.0)) { var p = G.pick(SPAWN_PT.x, SPAWN_PT.y, 0); sx = p.x; sz = p.z; }
  var O = window.__OCTO;
  if (O && O.hero) { O.hero.x = sx; O.hero.y = sz; if (O.hero.vx !== undefined) { O.hero.vx = 0; O.hero.vy = 0; } }
  P.x = sx; P.z = sz; P.y = G.h(sx, sz);
  P.spawn = { x: sx, z: sz };
}

/* ============================== 启动 ============================== */
function startGame() {
  var _pn = (($('inName') && $('inName').value) || '').trim();
  var _pr = (($('inRoom') && $('inRoom').value) || '').trim();
  Net.name = _pn || Net.name || ('旅人' + Math.floor(100 + Math.random() * 900));
  if (Net.name === '旅人') Net.name = '旅人' + Math.floor(100 + Math.random() * 900);   // ★ 空昵称自动加尾号，避免全场重名
  if ($('inName')) $('inName').value = Net.name;
  Net.room = _pr || Net.room || GLOBAL_ROOM;
  Net.save();
  $('startPanel').style.display = 'none';
  Sfx.resume();
  resetAmmo();
  placeAtSpawn();
  window.__spawnInfo = 'spawn 来自=' + ((window.__tileworld3d && window.__tileworld3d.spawn) ? '营地' : '城市pick') +
    ' x=' + Math.round(P.x) + ' z=' + Math.round(P.z) + ' CAMP_X0=' + (window.__tileworld3d ? window.__tileworld3d.CAMP_X0 : '-');
  P.y = G.h(P.x, P.z);
  buildHero();
  FX.init();
  buildAim();
  Perf.apply();
  Homing.init();
  MobRender.init();
  BossSys.init();
  HUD.vitals(); HUD.ammo(); HUD.score(); HUD.chat();
  Host.init();
  if ($('inMode').value !== 'solo') {
    Net.onStatus = function (t, ok) { HUD.net(t, ok); };
    Net.onChat = function () { HUD.chat(); };
    Net.onFeed = function () { HUD.feed(Net.feed[Net.feed.length - 1]); };
    Net.onMobs = function (list) { Host.applySnapshot(list); };
    Net.onPlayers = function () { HUD.board(); };
    Net.onHist = function () { HUD.hist(); };
    Net.connect();
  } else HUD.net('单机模式', false);
  running = true; lastT = performance.now();
  bindInput();
  sync3DBtn();
  try { Save.begin(); } catch (e) {}                       // ★ 存档：开局记一笔（并弹"欢迎回来"）
  setTimeout(function () { CamIntro.play(); }, 600);      // ★ 开局 3 秒镜头引导
}
/* ============================== ★ 影院模式（隐藏全部界面） ==============================
   用途：截图 / 录视频 / 纯观赏。隐藏 HUD、摇杆、按钮、聊天，只留画面。
   进入后右下角有个很淡的提示，点一下或按 H 退出。
   ============================================================================ */
var Cine = {
  on: false,
  toggle: function () {
    this.on = !this.on;
    var b = document.body;
    if (this.on) {
      b.classList.add('cine');
      if (!document.getElementById('cineTip')) {
        var t = document.createElement('div');
        t.id = 'cineTip';
        t.textContent = '影院模式 · 点此或按 H 退出';
        t.onclick = function () { Cine.toggle(); };
        document.body.appendChild(t);
      }
      var tip = document.getElementById('cineTip'); tip.style.display = 'block';
      clearTimeout(this._h); this._h = setTimeout(function () { tip.style.opacity = '0.12'; }, 2600);
    } else {
      b.classList.remove('cine');
      var tip2 = document.getElementById('cineTip'); if (tip2) tip2.style.display = 'none';
    }
    var bt = $('bCine'); if (bt) bt.className = this.on ? 'on' : '';
    Sfx.ui();
  },
};

/* ============================== ★ 3D 引导（3 秒镜头 + 一次性箭头） ============================== */
var CamIntro = {
  on: false, t0: 0, dur: 3.0, y0: 0, took: false, _cancel: null,
  play: function () {
    var O = window.__OCTO;
    if (!O || !O.camPS || !O.setMode) return;
    if (load('tl_intro3d', '') === '1') { HUD.tip3D(); return; }   // 看过就不再放
    if (A.getCamMode() !== 'hd2d') { HUD.tip3D(); return; }        // 玩家已在透视，不打扰
    this.on = true; this.t0 = performance.now(); this.y0 = O.camPS.yaw;
    O.setMode('persp'); O.camPS.pitch = -0.36; O.camPS.dist = 12.5;
    HUD.center('3 D 世 界', '拖动屏幕 · 自由转视角', 3000);
    var self = this, cv = document.getElementById('cv');
    this._cancel = function () { self.on = false; };               // 玩家接管 → 保持透视，不抢回
    if (cv) cv.addEventListener('pointerdown', this._cancel, { once: true });
    save('tl_intro3d', '1');
  },
  update: function () {
    if (!this.on) return;
    var O = window.__OCTO;
    if (!O || !O.camPS) { this.on = false; return; }
    var k = (performance.now() - this.t0) / 1000 / this.dur;
    if (k >= 1) {
      this.on = false;
      O.setMode('hd2d');
      if (this._cancel) { try { var cv = document.getElementById('cv'); cv && cv.removeEventListener('pointerdown', this._cancel); } catch (e) {} this._cancel = null; }
      HUD.tip3D();                                                 // 放完 → 亮出一次性箭头
      sync3DBtn();
      return;
    }
    var e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;  // easeInOutQuad
    O.camPS.yaw = this.y0 + e * Math.PI * 1.12;
  },
};

/* ★ 统一切换玩法：沙盒（安心建造）/ 战斗（刷怪 · Boss · 可 PVP） */
function setMode(sandbox) {
  SANDBOX = !!sandbox;
  save('tl_sandbox', SANDBOX ? '1' : '0');
  applySandbox();
  var bs = $('bSandbox'), bf = $('bFight'), mc = $('modeChip');
  if (bs) bs.className = SANDBOX ? 'on' : '';
  if (bf) bf.className = SANDBOX ? '' : 'on';
  if (mc) { mc.textContent = SANDBOX ? '🧱 沙盒' : '⚔ 战斗'; mc.className = 'chip' + (SANDBOX ? '' : ' on'); }
  HUD.center(SANDBOX ? '🧱 沙盒模式' : '⚔ 战斗模式',
    SANDBOX ? '不刷怪 · 不互伤 · 安心探索建造' : '刷怪 · Boss · 可 PVP', 2200);
  Sfx.ui();
}
function sync3DBtn() {
  var n = (A.getCamMode() === 'persp') ? 'on' : '';
  var b = $('b3D'); if (b) b.className = n;
  var bf = $('bFP'); if (bf) bf.className = Cam.fp ? 'on' : '';          // ★ 1P 按钮跟着相机状态亮
  var vb = $('bView'); if (vb) vb.textContent = '视角:' + (A.getCamMode() === 'hd2d' ? 'HD-2D' : '透视');
}
/* ★★★ 第一人称开关（点右上角 1P / 按 V）★★★
   只动相机这一层：相机贴到眼睛、藏掉自己的立绘、弹道从视线出。
   第三人称（居中/过肩）和 HD-2D 全部原样保留，随时切回。 */
function setFP(on) {
  on = !!on;
  var was = Cam.fp;
  Cam.fp = on;
  save('tl_fp', on ? '1' : '0');
  if (on) {
    CamIntro.on = false;                                  // 开局运镜会抢相机，先掐掉
    if (A.getCamMode() === 'hd2d') {                      // 正交 45° 没有"眼"，第一人称必须透视
      A.setCamMode('persp'); save('tl_view', 'persp');
      setCamDist(Cam.distV || 9); setCamHW(Cam.hwV || 0); sync3DBtn();
      var b3 = $('b3D'); if (b3) b3.className = 'on';
      HUD.tip3DHide();
    }
    Cam.pitch = clamp(Cam.pitch, -0.45, 0.45);            // 从俯视切过来别一头栽到地上
    Input.aimX = 0; Input.aimY = 0;
  }
  if (heroMesh) heroMesh.visible = !on;
  var bf = $('bFP'); if (bf) { bf.className = on ? 'on' : ''; bf.textContent = on ? '1P' : '1P'; }
  var bf2 = $('bFP2'); if (bf2) { bf2.className = on ? 'on' : ''; bf2.textContent = on ? '👁 第一人称:开' : '👁 第一人称'; }
  sync3DBtn();
  if (was !== on) {
    HUD.center(on ? '👁 第一人称' : '🎥 第三人称',
      on ? '拖动/移动鼠标转视角 · 点 1P 或按 V 切回' : '回到居中/过肩机位', 1600);
    Sfx.ui();
  }
}
function toggleFP() { setFP(!Cam.fp); }

function toggle3D() {
  Sfx.resume();
  var n = (A.getCamMode() === 'hd2d') ? 'persp' : 'hd2d';
  if (n === 'hd2d' && Cam.fp) setFP(false);      // ★ 正交 45° 没有第一人称 → 切回 HD-2D 时自动退出 1P
  CamIntro.on = false;
  A.setCamMode(n); save('tl_view', n);
  setCamDist(Cam.distV || 9); setCamHW(Cam.hwV || 0);
  sync3DBtn();
  var b = $('b3D'); if (b) b.className = n === 'persp' ? 'on' : '';
  HUD.tip3DHide();
  HUD.center(n === 'persp' ? '3D 透视视角' : 'HD-2D 视角',
    n === 'persp' ? '拖动屏幕自由转视角' : '经典斜 45° 正交', 1500);
  Sfx.ui();
}

function bindUI() {
  /* ★★ 手机 HUD：状态栏折叠 + 横屏提示（解决"挡住 3D 切换"）★★ */
  (function () {
    var tb = document.querySelector('.topbar'), mini = $('chipMini');
    if (mini) mini.addEventListener('click', function () {
      tb.classList.toggle('open');
      Sfx.ui();
    });
    // 折叠时给个一眼能看懂的小结
    var mt = $('miniTxt');
    setInterval(function () {
      if (!mt) return;
      var k = $('kKill') ? $('kKill').textContent : '0';
      var p = 0; try { p = TLReward ? TLReward.pts() : 0; } catch (e) {}
      mt.textContent = '击杀 ' + k + ' · 积分 ' + p;
    }, 1500);

    /* 竖屏提示：只在"手机上 + 竖屏 + 没点过先这样玩"时出现 */
    var hint = $('rotateHint');
    var isTouch = /Mobi|Android|iPhone|iPad|HarmonyOS|MiuiBrowser|XiaoMi/i.test(navigator.userAgent) || (navigator.maxTouchPoints || 0) > 1;
    function portrait() { return window.innerHeight > window.innerWidth; }
    function upd() {
      if (!hint || !isTouch) return;
      var skipped = false;
      try { skipped = localStorage.getItem('tl_rotate_skip') === '1'; } catch (e) {}
      hint.classList.toggle('on', portrait() && !skipped);
    }
    upd();
    addEventListener('resize', upd);
    addEventListener('orientationchange', function () { setTimeout(upd, 260); });

    /* 一键横屏：全屏 + 尝试锁横屏（浏览器允许就生效，不允许就只全屏） */
    var go = $('rhGo');
    if (go) go.addEventListener('click', function () {
      var el = document.documentElement;
      try {
        var p = el.requestFullscreen ? el.requestFullscreen() : (el.webkitRequestFullscreen && el.webkitRequestFullscreen());
        if (p && p.then) p.then(lockLandscape, lockLandscape);
        else setTimeout(lockLandscape, 200);
      } catch (e) { lockLandscape(); }
      hint.classList.remove('on');
      Sfx.ui();
    });
    function lockLandscape() {
      try {
        if (screen.orientation && screen.orientation.lock) {
          screen.orientation.lock('landscape').catch(function () { });
        }
      } catch (e) {}
      setTimeout(function () { try { A.resize(); resizeFX(); } catch (e) {} }, 320);
    }
    var skip = $('rhSkip');
    if (skip) skip.addEventListener('click', function () {
      try { localStorage.setItem('tl_rotate_skip', '1'); } catch (e) {}
      hint.classList.remove('on');
    });

    /* 全屏切换后重新算尺寸（解决"全屏后格式乱"） */
    ['fullscreenchange', 'webkitfullscreenchange'].forEach(function (ev) {
      document.addEventListener(ev, function () {
        setTimeout(function () { try { A.resize(); resizeFX(); } catch (e) {} upd(); }, 260);
      });
    });
  })();

  // ★ 兜底：这些层绝不拦截触摸（即便 CSS 被缓存）
  try {
    ['dmgLayer', 'perf', 'tipTxt', 'chatLog'].forEach(function (id) { var e = $(id); if (e) e.style.pointerEvents = 'none'; });
    // ★ 顶栏所有按钮 + 聊天 + 开始面板：强制可点（.hud>* 的 pointer-events:none 特异性更高，会把它们全吃掉）
    var clickable = document.querySelectorAll('.hrbtns button, #chatSend, #chatInput, #goBtn, #board button, .modeSel .m');
    for (var ci = 0; ci < clickable.length; ci++) clickable[ci].style.pointerEvents = 'auto';
    // ★ 强制触控元素可点（CSS 里 .hud>*{none} 会覆盖 #joy 等，这里内联兜底，杜绝"点不到"）
    ['joy', 'lookZone', 'btnFire', 'btnAds', 'btnJump', 'btnReload', 'btnSwap', 'btnGrenade'].forEach(function (id) { var e = $(id); if (e) e.style.pointerEvents = 'auto'; });
    var tp = $('touchpad'); if (tp) tp.style.pointerEvents = 'none';
    // 让开火按钮浮到最上层，任何情况下都点得到
    ['btnFire', 'btnAds', 'btnJump', 'btnReload', 'btnSwap', 'btnGrenade'].forEach(function (id) { var e = $(id); if (e) e.style.zIndex = '9'; });
  } catch (e) {}
  document.querySelectorAll('.modeSel .m').forEach(function (m) {
    m.addEventListener('click', function () {
      document.querySelectorAll('.modeSel .m').forEach(function (x) { x.className = 'm'; });
      m.className = 'm on';
    });
  });
  _on('goBtn', 'click', startGame);
  _on('chatSend', 'click', sendChat);
  _on('chatInput', 'keydown', function (e) { if (e.key === 'Enter') { sendChat(); e.stopPropagation(); } });
  _on('bFx', 'click', function () {
    if (HOST && window.__OCTO && window.__OCTO.setFx) { var v = !window.__OCTO.getFx(); window.__OCTO.setFx(v); this.textContent = '后处理' + (v ? '' : '(关)'); this.className = v ? 'on' : ''; return; }
    FXp.on = !FXp.on; this.textContent = '后处理' + (FXp.on ? '' : '(关)'); this.className = FXp.on ? 'on' : '';
  });
  _on('bFog', 'click', function () {
    if (HOST && window.__OCTO && window.__OCTO.setFog) { var f = !window.__OCTO.getFog(); window.__OCTO.setFog(f); this.textContent = '薄雾' + (f ? '(开)' : ''); this.className = f ? 'on' : ''; return; }
    FXp.fog = !FXp.fog; if (FXp.fog && !FXp.on) { FXp.on = true; _cls('bFx','on'); _txt('bFx','后处理'); } this.textContent = '薄雾' + (FXp.fog ? '(开)' : ''); this.className = FXp.fog ? 'on' : '';
  });
  (function bindVoice() {
    var b = $('btnVoice'); if (!b) return;
    var dn = function (e) { e.preventDefault(); Voice.start(); };
    var up = function (e) { e.preventDefault(); Voice.stop(); };
    b.addEventListener('touchstart', dn, { passive: false });
    b.addEventListener('touchend', up, { passive: false });
    b.addEventListener('touchcancel', up, { passive: false });
    b.addEventListener('mousedown', dn);
    b.addEventListener('mouseup', up);
    b.addEventListener('mouseleave', function () { if (Voice.rec && Voice.rec.state === 'recording') Voice.stop(); });
  })();
  _on('bBuild', 'click', function () { openTree(false); Build.toggle(); });
  _on('bCine', 'click', function () { openTree(false); Cine.toggle(); });
  /* ★ 赛道：传送到城市旁的「公路 + 车」区（复用刹车材质，在同一套 PBR 光照下） */
  function gotoRace() {
    var R = window.__RACE_STRIP; if (!R) { HUD.center('赛道未就绪', 'racestrip.js 未加载', 1500); return; }
    openTree(false);
    var sx = R.spawn.x, sz = R.spawn.z;
    var O = window.__OCTO; if (O && O.hero) { O.hero.x = sx; O.hero.y = sz; }
    try { P.x = sx; P.z = sz; P.y = 0; P.vy = 0; } catch (e) {}
    try { if (typeof Cam !== 'undefined') { Cam.yaw = Math.PI; } } catch (e) {}
    HUD.center('🏁 极速公路', '按住"开火"或踩着油门', 2000);
    try { Sfx.ui(); } catch (e) {}
  }
  /* 原版《极限刹车》全屏入口（保留） */
  (function () {
    function openRace(on) {
      var w = $('raceWrap'), f = $('raceFrame'); if (!w) return;
      if (on) { if (f && !f.getAttribute('src')) f.setAttribute('src', 'brake/index.html'); w.style.display = 'block'; try { Sfx.ui(); } catch (e) {} }
      else { w.style.display = 'none'; if (f) { try { f.setAttribute('src', 'about:blank'); } catch (e) {} } }
    }
    _on('bRace', 'click', function () { gotoRace(); });
    _on('bRace2', 'click', function () { gotoRace(); });
    _on('bRace3', 'click', function () { openTree(false); openRace(true); });
    _on('raceClose', 'click', function () { openRace(false); });
    window.__openRace = openRace; window.__gotoRace = gotoRace;
  })();
  window.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    if (k === 'h' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
      e.preventDefault(); Cine.toggle();
    }
  });
  _on('bKind', 'click', function () { Build.cycleKind(); });
  _on('bSandbox', 'click', function () { setMode(true); });
  _on('bFight', 'click', function () { setMode(false); });
  _on('modeChip', 'click', function () { setMode(!SANDBOX); });
  (function bindBuild() {
    var cv = document.getElementById('cv'); if (!cv) return;
    var dn = null;
    cv.addEventListener('pointerdown', function (e) { dn = { x: e.clientX, y: e.clientY }; });
    cv.addEventListener('pointermove', function (e) {
      if (!Build.on) return;
      Build.follow((e.clientX / window.innerWidth) * 2 - 1, -((e.clientY / window.innerHeight) * 2 - 1));
    });
    cv.addEventListener('pointerup', function (e) {
      if (!Build.on) return;
      if (dn && Math.hypot(e.clientX - dn.x, e.clientY - dn.y) > 14) return;   // 拖动视角 → 不算点击
      Build.tap((e.clientX / window.innerWidth) * 2 - 1, -((e.clientY / window.innerHeight) * 2 - 1));
    });
  })();
  _on('bVer', 'click', function () {
    var v = '构建 ' + BUILD + ' · 房间 ' + Net.room + ' · ' + (Net.connected ? '在线' : '离线') + ' · ' + Net.peers + ' 人';
    HUD.center('版本', v, 4000);
    try { if (navigator.clipboard) navigator.clipboard.writeText('天泪 ' + BUILD + ' ' + location.href); } catch (e) {}
    this.textContent = BUILD;
  });
  _on('b3D', 'click', toggle3D);
  _on('bFP', 'click', toggleFP);
  if ($('bFP2')) _on('bFP2', 'click', toggleFP);
  // ★ 关键修复：面板必须开在 ☰ 按钮"下方"，而不是写死 top:52px。
  //   顶栏按钮一多就会换行，☰ 掉到第二行时，写死的面板正好盖住它 → 展开后关不掉。
  // ★ 统一关闭所有「右上浮层」（菜单 + 子面板），避免"菜单关了子面板还留着"
  function hideSubPanels() {
    ['qrPanel', 'histPanel', 'board'].forEach(function (id) { var e = $(id); if (e) e.style.display = 'none'; });
    var vp = document.getElementById('visitPanel'); if (vp) vp.style.display = 'none';
  }
  function openTree(on) {
    var p = $('treePanel'), b = $('bRoot');
    if (!p) return;
    if (!on) { p.style.display = 'none'; hideSubPanels(); return; }   // ★ 关菜单顺手清干净子面板
    hideSubPanels();                                                  // ★ 开菜单先收掉子面板，不叠在一起
    p.style.display = 'block';
    if (b) {
      var r = b.getBoundingClientRect();
      p.style.top = Math.round(r.bottom + 6) + 'px';
      p.style.maxHeight = Math.max(120, window.innerHeight - r.bottom - 18) + 'px';
    }
    Sfx.ui();
  }
  _on('bRoot', 'click', function (e) {
    if (e) e.stopPropagation();
    var p = $('treePanel'); if (!p) return;
    openTree(p.style.display !== 'block');
  });
  _on('treeClose', 'click', function () { openTree(false); });          // 明确的关闭键
  // 点面板外面 → 关掉（点里面不关）
  document.addEventListener('pointerdown', function (e) {
    var p = $('treePanel'); if (!p || p.style.display !== 'block') return;
    var t = e.target;
    if (p.contains(t)) return;                                   // 菜单内部不关
    var b = $('bRoot'); if (b && b.contains(t)) return;          // ☰ 自己处理开关
    if (t && t.closest && t.closest('button,a,input,.chip,.hrbtns')) return;   // 其它 UI 也不关
    openTree(false);
  }, true);
  window.addEventListener('resize', function () {
    var p = $('treePanel'); if (p && p.style.display === 'block') openTree(true);
  });
  _on('bVol', 'click', function () {
    Sfx.volIdx = (Sfx.volIdx + 1) % Sfx.VOL_STEPS.length;
    Sfx.applyVol(); save('tl_vol', String(Sfx.volIdx));
    HUD.center('音量 · ' + Sfx.VOL_NAMES[Sfx.volIdx], Sfx.volIdx >= 2 ? '再往上可能破音，觉得吵就往下调' : '', 1400);
    Sfx.ui();
  });
  _on('bMusic', 'click', function () { Sfx.resume(); var on = Music.toggle(); this.textContent = '音乐' + (on ? ':开' : ':关'); this.className = on ? 'on' : ''; save('tl_music', on ? '1' : '0'); });
  _on('bSfx', 'click', function () { Sfx.on = !Sfx.on; this.textContent = '音效' + (Sfx.on ? ':开' : ':关'); this.className = Sfx.on ? 'on' : ''; save('tl_sfx', Sfx.on ? '1' : '0'); if (Sfx.on) Sfx.ui(); });
  _on('bMic', 'click', function () {
    Voice.mute(!Voice.muted);
    this.textContent = '麦克风:' + (Voice.muted ? '关' : '开');
    this.className = Voice.muted ? '' : 'on';
    HUD.center(Voice.muted ? '麦克风已关闭' : '麦克风已开启',
      Voice.muted ? '已释放占用 · 可正常静音' : '按住 🎤 说话', 1600);
    Sfx.ui();
  });
  _on('bMic', 'click', function () {
    Voice.mute(!Voice.muted);                    // 关→开 / 开→关
    this.textContent = '麦克风:' + (Voice.muted ? '关' : '开');
    this.className = Voice.muted ? '' : 'on';
    HUD.center(Voice.muted ? '麦克风已关闭' : '麦克风已开启',
      Voice.muted ? '已释放麦克风占用 · 可静音' : '按住 🎤 说话', 1600);
    Sfx.ui();
  });
  _on('bMap', 'click', function () { var m = $('mapWrap'); if (!m) return; var on = m.style.display !== 'block'; m.style.display = on ? 'block' : 'none'; this.className = on ? 'on' : ''; });
  _on('bVisitors', 'click', function () { openTree(false); Stats.show(); });   // ★ 访客名单
  _on('bChat', 'click', function () { var c = $('chatWrap'); if (!c) return; var on = !c.classList.contains('on'); c.classList.toggle('on', on); this.className = on ? 'on' : ''; if (on) { var ci = $('chatInput'); if (ci) try { ci.focus(); } catch (e) {} } });
  _on('bBoard', 'click', function () { openTree(false); var b = $('board'); HUD.board(); b.style.display = 'block'; });
  _on('bHist', 'click', function () { openTree(false); var p = $('histPanel'); if (!p) return; HUD.hist(); p.style.display = 'block'; });
  _on('histClose', 'click', function () { var p = $('histPanel'); if (p) p.style.display = 'none'; });
  _on('bInv', 'click', function () { openTree(false); HUD.invite(); });
  _on('bShare', 'click', function () {
    openTree(false);
    var n = Ref.count(), ni = 0, bonus = 0;
    try {
      if (window.TLReward && TLReward.invite) {
        ni = TLReward.invite.count();
        bonus = ni * TLReward.invite.rules.perFriend;
      }
    } catch (e) {}
    n = Math.max(n, ni);
    HUD.qr(Net.inviteLink());
    HUD.center('拉好友 · 已来 ' + n + ' 人' + (bonus ? '（+' + bonus + ' 分）' : ''),
      n >= Ref.need
        ? '神器已解锁！按 8 切出虚空之刃 · 继续拉还有称号和分'
        : ('再来 ' + (Ref.need - n) + ' 人开神器 · 每拉 1 人 +' +
           (window.TLReward && TLReward.invite ? TLReward.invite.rules.perFriend : 30) +
           ' 分，对方 +' + (window.TLReward && TLReward.invite ? TLReward.invite.rules.newbieGift : 50) + ' 分'),
      4200);
    Sfx.ui();
  });
  _on('qrCopy', 'click', function () {
    var u = $('qrUrl').textContent;
    try { if (navigator.clipboard) navigator.clipboard.writeText(u); } catch (e) {}
    this.textContent = '✅ 已复制';
  });
  _on('qrClose', 'click', function () { HUD.qrHide(); });
  /* ★ 钢琴交互：走近提示，按 E / 点按钮弹奏 */
  setInterval(function () {
    var pi = window.__PIANO; if (!pi) return;
    var d = Math.hypot(P.x - pi.x, P.z - pi.z);
    var near = d < 4.2; Piano.near = near;
    var el = $('interactTip');
    if (el) { el.style.display = near ? 'block' : 'none'; if (near) el.textContent = '🎹 按 E 弹奏钢琴'; }
  }, 300);
  window.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    if (k === 'e' && Piano.near) {
      if (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
      e.preventDefault(); Piano.play();
    }
  });
  _on('interactTip', 'click', function () { if (Piano.near) Piano.play(); });
  _on('bHz', 'click', function () {
    var h = Perf.setHz(Perf.hz >= 120 ? 60 : 120);
    this.textContent = '帧率:' + h;
    this.className = h >= 120 ? 'on' : '';
    HUD.center('帧率上限 ' + h + ' fps',
      h >= 120 ? '高刷屏满帧跟手（更费电、发热略高）' : '稳定 60，省电省热（推荐手机）', 2200);
    Sfx.ui();
  });
  _on('bHouse', 'click', function () {
    var on = !window.__houseFancy;
    try { if (window.setHouseFancy) window.setHouseFancy(on); } catch (e) {}
    this.textContent = '房子:' + (on ? '精' : '简');
    this.className = on ? 'on' : '';
    save('tl_house', on ? 'fancy' : 'simple');
    HUD.center('房子 · ' + (on ? '精致版' : '火柴盒'),
      on ? '扫描材质 + 发光窗 + 暖光（更好看，更吃性能）' : '纯色方块 + 尖顶，最省性能 · 不卡', 2200);
    Sfx.ui();
  });
  _on('bQual', 'click', function () {
    var order = ['auto', 0, 1, 2, 3, 4], cur = (Perf.MANUAL ? Perf.level : 'auto');
    var i = order.indexOf(cur); var nx = order[(i + 1) % order.length];
    if (nx === 'auto') Perf.auto(); else Perf.setLevel(nx);
    this.textContent = '画质:' + Perf.name();
    this.className = Perf.MANUAL ? 'on' : '';
    save('tl_qual', Perf.MANUAL ? ('m' + Perf.level) : 'auto');
    HUD.center('画质 · ' + Perf.name(), Perf.MANUAL ? Perf.tips[Perf.level] : '按帧率自动升降档（当前 ' + ['标清', '高清', '超清', '极高', '顶级3A'][Perf.level] + '）', 1800);
    Sfx.ui();
  });
  /* ★ 积分 chip：点一下看进度（神器解锁还差多少） */
  _on('ptsChip', 'click', function () {
    var p = 0, t = 0, g = null;
    try { p = TLReward.pts(); t = TLReward.todayGain(); g = TLReward.nextGoal(); } catch (e) {}
    HUD.center('🎁 我的积分 ' + p + ' · 今日 +' + t,
      g ? ('再攒 ' + (g.at - p) + ' 分解锁「' + g.name + '」（' + g.desc + '）')
        : '全部奖励已解锁 —— 谢谢你在玩！', 3200);
    Sfx.ui();
  });
  /* ★★ 开车：靠近车 → 按 E / 点提示 上车；再按 E 下车 ★★ */
  (function bindDrive() {
    var D = null;
    function refresh() {
      var DD = window.__DRIVE, cars = window.__CARS; if (!DD || !cars || !cars.length) return;
      D = DD;
      var el = $('driveTip');
      if (DD.on) { if (el) { el.style.display = 'block'; el.textContent = '🚗 按 E 下车'; } return; }
      var best = null, bd = 4.5;
      cars.forEach(function (c) {
        var cx = c.mesh ? c.mesh.position.x : c.x, cz = c.mesh ? c.mesh.position.z : c.z;
        var d = Math.hypot(cx - P.x, cz - P.z); if (d < bd) { bd = d; best = c; }
      });
      DD.near = best;
      if (el) { el.style.display = best ? 'block' : 'none'; if (best) el.textContent = '🚗 按 E 上车'; }
    }
    setInterval(refresh, 300); refresh();
    function toggleDrive() {
      var DD = window.__DRIVE; if (!DD) return;
      if (DD.on) { DD.on = false; DD.car = null; HUD.center('下车', '', 1200); }
      else if (DD.near) { DD.on = true; DD.car = DD.near; HUD.center('🚗 上车', 'WASD/摇杆 开车 · 再按 E 下车', 2600); }
      Sfx.ui();
    }
    window.addEventListener('keydown', function (e) {
      if ((e.key || '').toLowerCase() !== 'e') return;
      if (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
      var DD = window.__DRIVE; if (!DD || (!DD.on && !DD.near)) return;
      e.preventDefault(); toggleDrive();
    });
    _on('driveTip', 'click', function () { toggleDrive(); });
  })();
  _on('bGround', 'click', cycleGround);
  _on('bCam', 'click', cycleCam);
  if ($('bAim')) _on('bAim', 'click', toggleAssist);
  if ($('bView')) _on('bView', 'click', cycleView);
  if ($('camDist')) _on('camDist', 'input', function () { setCamDist(+this.value); });
  if ($('camHW')) _on('camHW', 'input', function () { setCamHW(+this.value); });
  _on('bRain', 'click', function () { var on = !A.getRain(); A.setRain(on); save('tl_rain', on ? '1' : '0'); this.textContent = '下雨' + (on ? '' : '(关)'); this.className = on ? 'on' : ''; });
  _on('bSL', 'click', function () { var on = !A.getSpot(); A.setSpot(on); save('tl_spot', on ? '1' : '0'); this.textContent = '探照灯' + (on ? '' : '(关)'); this.className = on ? 'on' : ''; });
  _on('bHelp', 'click', function () { HUD.center('WASD 移动 · 鼠标转视角 · 左键开火', 'R 换弹 · 1/2/3/4 切枪 · Shift 疾跑 · 空格 跳 · G 手雷 · 右键开镜', 4200); });
  _on('bBack', 'click', function () { running = false; Net.disconnect(); location.href = 'index.html'; });
  $('inName').value = Net.name; $('inRoom').value = Net.room;
}
function save(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function load(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }
function setCamDist(v) {
  Cam.distV = v;
  if (A.getCamMode() === 'hd2d') A.setOrthoVH(v);                 // HD-2D：正交视野大小（越大越远）
  else Cam.dist = clamp(v * 0.40 + 1.5, 2.5, 30);                 // 透视：第三人称距离（范围拉大）
  save('tl_camdist', v);
}
function setCamHW(v) { Cam.hwV = v; if (A.getCamMode() === 'hd2d' && A.setOrthoHW) A.setOrthoHW(v); save('tl_camhw', v); }
function cycleView() { toggle3D(); }
function toggleAssist() {
  Cam.autoAim = !Cam.autoAim; save('tl_assist', Cam.autoAim ? '1' : '0');
  var b = $('bAim'); if (b) { b.textContent = '辅助:' + (Cam.autoAim ? '开' : '关'); b.className = Cam.autoAim ? 'on' : ''; }
  HUD.center('瞄准辅助 · ' + (Cam.autoAim ? '开（会自动转视角）' : '关（只修弹道）'), Cam.autoAim ? '可能抢走目标' : '推荐：视角 100% 归你', 1400);
}
function toggleAim() {
  Aim.mode3d = !Aim.mode3d; save('tl_aim', Aim.mode3d ? '3d' : '2d');
  setAimVisible(Aim.mode3d);
  if ($('xhair')) $('xhair').style.display = Aim.mode3d ? 'none' : 'block';
  HUD.center('准星 · ' + (Aim.mode3d ? '3D 世界标记' : '2D 屏幕'), Aim.mode3d ? '打在哪就留在哪' : '固定屏幕中心', 1100);
}
function cycleCam() {
  Cam.mode = (Cam.mode === 'center') ? 'shoulder' : 'center';
  save('tl_cam', Cam.mode);
  var t = Cam.mode === 'center' ? '视角 · 居中' : '视角 · 过肩';
  HUD.center(t, Cam.mode === 'center' ? '角色居中偏下 · 准星指远方' : '角色偏肩 · 视野更开阔', 1200);
  $('bCam').textContent = '视角:' + (Cam.mode === 'center' ? '居中' : '过肩');
}
function cycleGround() {
  var gs = A.grounds, cur = A.getGround(), i = 0;
  for (var k = 0; k < gs.length; k++) if (gs[k].id === cur) { i = k; break; }
  var nx = gs[(i + 1) % gs.length];
  A.setGround(nx.id); save('tl_ground', nx.id);
  HUD.center('地面 · ' + nx.name, '共 ' + gs.length + ' 种 · 已保存', 1300);
  $('bGround').textContent = '地面:' + nx.name;
}
function restorePrefs() {
  var g = load('tl_ground', 'asphalt'); if (A.grounds.some(function (x) { return x.id === g; })) A.setGround(g);
  else g = 'asphalt';
  var nm = '路面'; A.grounds.forEach(function (x) { if (x.id === g) nm = x.name; });
  $('bGround').textContent = '地面:' + nm;
  var r = load('tl_rain', '1') === '1'; A.setRain(r); $('bRain').textContent = '下雨' + (r ? '' : '(关)'); $('bRain').className = r ? 'on' : '';
  var sp = load('tl_spot', '1') === '1'; A.setSpot(sp); $('bSL').textContent = '探照灯' + (sp ? '' : '(关)'); $('bSL').className = sp ? 'on' : '';
  Cam.mode = load('tl_cam', 'center'); $('bCam').textContent = '机位:' + (Cam.mode === 'center' ? '居中' : '过肩');
  // ★ 第一人称偏好：上次开着就继续开（?fp=1 强制开 / ?fp=0 强制关）
  var _fpQ = (location.search.match(/[?&]fp=([01])/) || [])[1];
  var _fp = (_fpQ !== undefined) ? (_fpQ === '1') : (load('tl_fp', '0') === '1');
  if (_fp) setTimeout(function () { try { setFP(true); } catch (e) {} }, 60);
  var _cd = +load('tl_camdist', '9'); if (window.__zoomQ) _cd = +window.__zoomQ; if ($('camDist')) $('camDist').value = _cd; setCamDist(_cd);
  var _hwx = +load('tl_camhw', '0'); Cam.hwV = _hwx; if ($('camHW')) $('camHW').value = _hwx; setCamHW(_hwx);
  var _vm = load('tl_view', 'hd2d');
  var _q = (location.search.match(/[?&]view=([a-z0-9]+)/i) || [])[1];   // ?view=hd2d|persp 强制
  if (_q) _vm = _q;
  var _q2 = (location.search.match(/[?&]zoom=([0-9.]+)/) || [])[1];   // ?zoom=9 强制 A.setCamMode(_vm); if ($('bView')) { $('bView').textContent = '视角:' + (_vm === 'hd2d' ? 'HD-2D' : '透视'); $('bView').className = _vm === 'hd2d' ? 'on' : ''; }
  Aim.mode3d = load('tl_aim', '3d') !== '2d';
  Cam.autoAim = load('tl_assist', '0') === '1';
  SANDBOX = load('tl_sandbox', '1') !== '0';
  if ($('bSandbox')) $('bSandbox').className = SANDBOX ? 'on' : '';
  if ($('bFight')) $('bFight').className = SANDBOX ? '' : 'on';
  if ($('modeChip')) { $('modeChip').textContent = SANDBOX ? '🧱 沙盒' : '⚔ 战斗'; $('modeChip').className = 'chip' + (SANDBOX ? '' : ' on'); }
  // ★ 恢复画质选择（auto / m0~m4）
  (function () {
    var q = load('tl_qual', 'auto');
    if (q === 'auto') Perf.auto();
    else if (/^m[0-4]$/.test(q)) Perf.setLevel(parseInt(q.slice(1), 10));
    var b = $('bQual'); if (b) b.textContent = '画质:' + Perf.name();
    // ★ 房子细节档（默认火柴盒）
    var bh = $('bHouse');
    if (bh) { bh.textContent = '房子:' + (window.__houseFancy ? '精' : '简'); bh.className = window.__houseFancy ? 'on' : ''; }
    // ★ 帧率上限（60 稳 / 120 跟手）
    Perf.setHz(parseInt(load('tl_hz', '60'), 10) || 60);
    var bz = $('bHz'); if (bz) bz.textContent = '帧率:' + Perf.hz;
  })();
  Sfx.on = load('tl_sfx', '1') !== '0';
  Sfx.volIdx = Math.max(0, Math.min(3, parseInt(load('tl_vol', '1'), 10) || 0));
  Sfx.applyVol();
  Voice.muted = load('tl_mic', '1') === '0';
  if ($('bMic')) { $('bMic').textContent = '麦克风:' + (Voice.muted ? '关' : '开'); $('bMic').className = Voice.muted ? '' : 'on'; }
  Voice.muted = load('tl_mic', '1') === '0';
  if ($('bMic')) { $('bMic').textContent = '麦克风:' + (Voice.muted ? '关' : '开'); $('bMic').className = Voice.muted ? '' : 'on'; }
  if ($('bSfx')) { $('bSfx').textContent = '音效' + (Sfx.on ? ':开' : ':关'); $('bSfx').className = Sfx.on ? 'on' : ''; }
  if (load('tl_music', '1') !== '0') setTimeout(function () { Sfx.resume(); if (Sfx.ctx && !Music.on) { Music.start(); if ($('bMusic')) { $('bMusic').textContent = '音乐:开'; $('bMusic').className = 'on'; } } }, 400);
  if ($('bAim')) { $('bAim').textContent = '辅助:' + (Cam.autoAim ? '开' : '关'); $('bAim').className = Cam.autoAim ? 'on' : ''; }
}
function sendChat() {
  var v = $('chatInput').value.trim(); if (!v) return;
  Net.chat.push({ name: Net.name + '（我）', text: v }); HUD.chat();
  if (Net.connected) Net.chatSend(v);
  $('chatInput').value = '';
}

/* 初始化 */
Net.load();
Voice.init();
Build.init();
/* ★ 存档：载入 + 定时落盘 + 切后台/关页落盘 */
Save.load();
setInterval(function () { try { Save.flush(); } catch (e) {} }, 5000);
window.addEventListener('pagehide', function () { try { Save.flush(); } catch (e) {} });
document.addEventListener('visibilitychange', function () { if (document.hidden) { try { Save.flush(); } catch (e) {} } });
document.addEventListener('visibilitychange', function () { if (document.hidden) Voice.release(); });
window.addEventListener('pagehide', function () { Voice.release(); });
/* ★ 链接即进服：URL 带 room/n → 无感直接进入（不显示开始面板） */
if (!HOST && Net.fromLink) setTimeout(function () { try { if (!running) startGame(); } catch (e) { window.__autoJoinErr = String((e && e.message) || e); } }, 90);
initFXpass();
window.addEventListener('resize', function () { A.resize(); resizeFX(); });
A.resize(); resizeFX(); buildMmBase(); restorePrefs();
bindUI();
if (!HOST) requestAnimationFrame(loop);
else {   // ★ 宿主模式：暴露给 HD-2D 页每帧调用；并自动初始化战斗
  window.Shooter = { tick: function (dt) { loopBody(dt, performance.now()); }, Combat: Combat,
    Host: Host, Net: Net, Boss: BossSys, Homing: Homing, Mob: MobRender, Perf: Perf, P: P, FX: FX, Aim: Aim, Grenade: Grenade,
    start: function () { if (!running) { running = true; lastT = performance.now(); } } };
  (function boot() {
    if (!window.__hdArenaReady || !window.ARENA) { setTimeout(boot, 300); return; }
    try {
      resetAmmo(); FX.init(); buildAim(); Homing.init(); MobRender.init(); BossSys.init();
      P.x = window.__OCTO.hero.x; P.z = window.__OCTO.hero.y;
      bindInput();                                   // ★ 显示并绑定触屏按钮（摇杆/开火/换弹/切枪/跳跃/手雷/机瞄）
      Net.onStatus = function (t, ok) { HUD.net(t, ok); };
      Net.onChat = function () { HUD.chat(); };
      Net.onFeed = function () { HUD.feed(Net.feed[Net.feed.length - 1]); };
      Net.onMobs = function (list) { Host.applySnapshot(list); };
      Net.onPlayers = function () { HUD.board(); };
      Net.onHist = function () { HUD.hist(); };
      placeAtSpawn();                                // ★ 统一出生点（宿主模式也必须调）
      try { Save.begin(); } catch (e) {}             // ★ 存档：开局记一笔
      try { Build.bar(); } catch (e) {}
      try { Ref.refresh(false); } catch (e) {}
      try { HUD.vitals(); HUD.ammo(); HUD.score(); HUD.chat(); } catch (e) {}
      Net.connect();                                 // ★ HD-2D 主场景也自动进全服 */
      HUD.net('连接中…', false);
      var _tp = $('touchpad'); if (_tp) _tp.style.display = 'block';
      var _jy = $('joy'); if (_jy) _jy.style.display = 'block';
      var _lz = $('lookZone'); if (_lz) _lz.style.display = 'block';
      running = true; lastT = performance.now();
      sync3DBtn();
      setTimeout(function () { CamIntro.play(); }, 700);   // ★ 开局 3 秒镜头引导
      console.log('[shooter] 宿主模式启动：HD-2D 世界 + 战斗');
    } catch (e) { window.__initErr = String((e && e.message) || e); }
  })();
}

/* 调试接口（可被 tl eval 调用） */
/* ★★ 视觉小说对话（照搬原版 StoryMgr：立绘 + 打字机 + 点击推进；背景透明可见 3D 环境）★★ */
var StoryMgr = {
  dialogues: [], index: 0, typing: false, typeTimer: null, currentChar: null, onDone: null,
  on: function () { var w = $('storySceneWrap'); return !!(w && w.style.display === 'block'); },
  play: function (lines, onDone) {
    this.dialogues = lines || []; this.index = 0; this.onDone = onDone || null;
    var w = $('storySceneWrap'); if (w) w.style.display = 'block';
    this.currentChar = null; this.showLine();
  },
  hide: function () {
    var w = $('storySceneWrap'); if (w) w.style.display = 'none';
    if (this.typeTimer) { clearInterval(this.typeTimer); this.typeTimer = null; }
    this.typing = false; this.onDone = null; this.dialogues = []; this.index = 0;
  },
  showLine: function () {
    if (this.index >= this.dialogues.length) { var f = this.onDone; this.onDone = null; this.hide(); if (f) try { f(); } catch (e) {} return; }
    var line = this.dialogues[this.index] || {};
    var nEl = $('dialogueName'), tEl = $('dialogueText'), img = $('storyCharImg'), ch = $('storyCharacter');
    if (nEl) { nEl.textContent = line.speaker || '旅人'; nEl.style.background = line.color || 'rgba(147,51,234,.75)'; }
    var src = line.char || 'assets/ch/dir_S.png';
    if (img && this.currentChar !== src) {
      img.src = src; img.style.display = 'block'; this.currentChar = src;
      if (ch) { ch.style.animation = 'none'; try { ch.offsetHeight; } catch (e) {} ch.style.animation = ''; }
    }
    this.typing = true;
    var self = this, full = String(line.text || ''), i = 0;
    clearInterval(this.typeTimer); if (tEl) tEl.textContent = '';
    this.typeTimer = setInterval(function () {
      if (i < full.length) { if (tEl) tEl.textContent = full.slice(0, ++i); }
      else { clearInterval(self.typeTimer); self.typeTimer = null; self.typing = false; }
    }, 38);
  },
  next: function () {
    if (!this.on()) return;
    if (this.typing) {
      clearInterval(this.typeTimer); this.typeTimer = null; this.typing = false;
      var line = this.dialogues[this.index]; if (line && $('dialogueText')) $('dialogueText').textContent = line.text; return;
    }
    this.index++; this.showLine();
  },
};
/* 昭和屋台：老板对话（统一用同一个角色立绘） */
var STORY_CHEF = [
  [{ speaker: '鱼板烧屋', color: 'rgba(220,120,60,.85)', text: 'いらっしゃい！刚烤好的鱼板烧～' },
   { speaker: '鱼板烧屋', color: 'rgba(220,120,60,.85)', text: '雨天路滑，小心脚下啊。' },
   { speaker: '旅人', text: '……这味道，像是回到了昭和的横丁。' },
   { speaker: '鱼板烧屋', color: 'rgba(220,120,60,.85)', text: '要来一串吗？趁热吃最香。' }],
  [{ speaker: '关东煮屋', color: 'rgba(90,170,220,.85)', text: '姑娘，来碗关东煮暖暖身子？' },
   { speaker: '关东煮屋', color: 'rgba(90,170,220,.85)', text: '这汤头，熬了一整天了。' },
   { speaker: '旅人', text: '好香。这雨夜，确实该吃点热的。' }],
  [{ speaker: '团子屋', color: 'rgba(220,150,190,.85)', text: '三色团子，甜的咸的都有。' },
   { speaker: '团子屋', color: 'rgba(220,150,190,.85)', text: '看你这身打扮，不像是本地人？' },
   { speaker: '旅人', text: '路过。这里的灯，比城里暖。' }]
];
(function bindStory() {
  var near = null;
  setInterval(function () {
    if (StoryMgr.on()) return;
    var C = window.__CHEFS; var el = $('vnTip');
    if (!C || !C.length) { if (el) el.style.display = 'none'; return; }
    var bd = 3.8; near = null;
    for (var i = 0; i < C.length; i++) { var d = Math.hypot(C[i].x - P.x, C[i].z - P.z); if (d < bd) { bd = d; near = C[i]; } }
    if (el) { el.style.display = near ? 'block' : 'none'; if (near) el.textContent = '💬 按 E 和「' + near.name + '」交谈'; }
  }, 300);
  function talk() { if (!near) return; StoryMgr.play(STORY_CHEF[near.kind] || STORY_CHEF[0]); try { Sfx.ui(); } catch (e) {} }
  window.addEventListener('keydown', function (e) {
    if ((e.key || '').toLowerCase() !== 'e') return;
    if (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
    if (StoryMgr.on()) { e.preventDefault(); StoryMgr.next(); return; }
    if (near) { e.preventDefault(); talk(); }
  });
  _on('vnTip', 'click', function () { talk(); });
  _on('dialogueBox', 'click', function () { StoryMgr.next(); });
})();
window.SHOOTER = { P: P, Net: Net, Host: Host, Combat: Combat, Cam: Cam, Input: Input, Aim: Aim, Boss: BossSys, Homing: Homing, Perf: Perf, start: startGame, Sfx: Sfx, Music: Music, Voice: Voice, CamIntro: CamIntro, toggle3D: toggle3D, sync3DBtn: sync3DBtn, Build: Build,
  build: function () { return BUILD; }, Ref: Ref, Cine: Cine, Stats: Stats, Save: Save,
  Fp: (typeof Fp !== 'undefined' ? Fp : null), Story: StoryMgr,
  /* ★ 演示工具（拍宣传素材用，本地生成，不占网络） */
  demo: function (n, cx, cz, R) {
    n = n || 3; cx = cx || P.x + 5; cz = cz || P.z; R = R || 4;
    var names = ['云中客', '夜行车', '青枫', '白鸦', '无想', '归舟', '空山', '拾光'];
    Net.players.clear();
    var list = [];
    for (var i = 0; i < n; i++) list.push({ id: 'fk' + i, ang: i * Math.PI * 2 / n, r: R * (0.55 + 0.45 * Math.random()) });
    if (window.__fRAF) cancelAnimationFrame(window.__fRAF);
    (function step() {
      var t = performance.now() / 1000;
      for (var i = 0; i < list.length; i++) {
        var f = list[i], a = f.ang + t * 0.30;
        var x = cx + Math.cos(a) * f.r, z = cz + Math.sin(a) * f.r;
        Net.players.set(f.id, { id: f.id, name: names[i % names.length], x: x, z: z, y: 0,
          tx: x, tz: z, ty: 0, yaw: a * 57, hp: 100, maxHp: 100, alive: 1, team: i, _t: performance.now() });
      }
      Net.peers = list.length + 1;
      window.__fRAF = requestAnimationFrame(step);
    })();
    return list.length;
  },
  sweep: function (dur, y0, y1, d0, d1, p0, p1) {
    var O = window.__OCTO; if (!O) return 'no octo';
    O.setMode('persp');
    var t0 = performance.now(); dur = (dur || 10) * 1000;
    (function st() {
      var k = Math.min(1, (performance.now() - t0) / dur);
      var e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      O.camPS.yaw = y0 + (y1 - y0) * e; O.camPS.pitch = p0 + (p1 - p0) * e; O.camPS.dist = d0 + (d1 - d0) * e;
      if (k < 1) requestAnimationFrame(st);
    })();
    return 'sweep ' + dur / 1000 + 's';
  },
  hd: function (v) { var O = window.__OCTO; if (!O) return 'no octo'; O.setMode('hd2d'); if (O.setZoom) O.setZoom(v || 9, 0); return 'hd ' + v; },
  sandbox: function () { return SANDBOX; }, setSandbox: function (v) { SANDBOX = !!v; applySandbox(); },
  running: function () { return running; }, facing: function (y) { return facingDir(P.x, P.z, y === undefined ? P.yaw : y, cam().position); },
  dbg: function () {
    var az = Math.atan2(cam().position.x - P.x, cam().position.z - P.z);
    var rel = norm360(P.yaw - az);
    return { yaw: +P.yaw.toFixed(1), camYaw: +Cam.yaw.toFixed(1), az: +az.toFixed(1), rel: +rel.toFixed(1),
      dir: facingDir(P.x, P.z, P.yaw, cam().position), rel: +rel.toFixed(1), spr: (heroMat && heroMat.uniforms.uMap.value.image) ? heroMat.uniforms.uMap.value.image.src.split('/').pop() : '?',
      camX: +cam().position.x.toFixed(1), camZ: +cam().position.z.toFixed(1), px: +P.x.toFixed(1), pz: +P.z.toFixed(1), hp: Math.round(P.hp), alive: P.alive };
  } };

} catch (e) { window.__serr = (e.stack || e.message); }
})();
