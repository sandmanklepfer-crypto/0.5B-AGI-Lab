/* ===========================================================
   FLM 学院 · 音频引擎
   采样来自 FL Studio Mobile 4.9.3 音色库（FLAC → WAV/MP3）
   =========================================================== */
window.AE = (function () {
  "use strict";

  const FILES = {
    kick1: "kick1.wav", kick2: "kick2.wav", kick3: "kick3.wav",
    snare1: "snare1.wav", snare2: "snare2.wav",
    clap1: "clap1.wav", clap2: "clap2.wav",
    hatc1: "hatc1.wav", hatc2: "hatc2.wav", hato1: "hato1.wav",
    ride1: "ride1.mp3", crash1: "crash1.mp3",
    perc1: "perc1.wav", perc2: "perc2.wav",
    impact1: "impact1.mp3", impact2: "impact2.mp3",
    vinyl: "vinyl.wav",
    riser1: "riser1.mp3", riser2: "riser2.mp3",
    sweep1: "sweep1.mp3", pluck1: "pluck1.mp3"
  };
  const PIANO_KEYS = [];
  for (let m = 36; m <= 84; m += 4) PIANO_KEYS.push(m);

  let ctx = null;
  let master, limiter, analyser, preAnalyser, preTap, driveGain, musicHP, dryBus, musicBus, revIn, revReturn, delIn, delReturn, delNode;
  let preData = null;
  const buf = {};
  let anData = null;
  let ready = false;
  let volume = 0.85;
  let muted = false;
  let limiterOn = true;
  const listeners = [];

  const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function init() {
    if (ctx) return ctx;
    const AC = window.AudioContext || window.webkitAudioContext;
    ctx = new AC({ latencyHint: "interactive" });

    limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -2;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.002;
    limiter.release.value = 0.12;

    master = ctx.createGain();
    master.gain.value = volume;

    analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.45;
    anData = new Float32Array(analyser.fftSize);

    // 主链路：bus → limiter(可旁通) → master → analyser → out
    dryBus = ctx.createGain();
    dryBus.gain.value = 1;
    musicBus = ctx.createGain();
    musicBus.gain.value = 1;
    // 低切（混音课用）
    musicHP = ctx.createBiquadFilter();
    musicHP.type = "highpass";
    musicHP.frequency.value = 20;
    musicHP.Q.value = 0.7;
    // 推子前监听（只看电平，不出声）
    preTap = ctx.createGain();
    preTap.gain.value = 0;
    preAnalyser = ctx.createAnalyser();
    preAnalyser.fftSize = 1024;
    preData = new Float32Array(preAnalyser.fftSize);
    dryBus.connect(limiter);
    musicBus.connect(musicHP);
    musicHP.connect(limiter);
    dryBus.connect(preTap);
    musicHP.connect(preTap);
    preTap.connect(preAnalyser);
    limiter.connect(driveGain = ctx.createGain());
    driveGain.connect(master);
    master.connect(analyser);
    analyser.connect(ctx.destination);

    // 混响
    const conv = ctx.createConvolver();
    conv.buffer = makeIR(2.1, 2.8);
    revIn = ctx.createGain();
    revReturn = ctx.createGain();
    revReturn.gain.value = 0.55;
    revIn.connect(conv);
    conv.connect(revReturn);
    revReturn.connect(limiter);

    // 延迟（附点八分，随 BPM 更新）
    delIn = ctx.createGain();
    delNode = ctx.createDelay(2.0);
    delNode.delayTime.value = 0.35;
    const fb = ctx.createGain();
    fb.gain.value = 0.32;
    const dlp = ctx.createBiquadFilter();
    dlp.type = "lowpass";
    dlp.frequency.value = 3200;
    delReturn = ctx.createGain();
    delReturn.gain.value = 0.4;
    delIn.connect(delNode);
    delNode.connect(dlp);
    dlp.connect(fb);
    fb.connect(delNode);
    delNode.connect(delReturn);
    delReturn.connect(limiter);

    return ctx;
  }

  function makeIR(dur, decay) {
    const rate = ctx.sampleRate;
    const len = Math.floor(rate * dur);
    const b = ctx.createBuffer(2, len, rate);
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c);
      for (let i = 0; i < len; i++) {
        const t = i / len;
        d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, decay) * (i < rate * 0.01 ? i / (rate * 0.01) : 1);
      }
    }
    return b;
  }

  async function load(onProgress) {
    init();
    const files = Object.keys(FILES).map((k) => FILES[k])
      .concat(PIANO_KEYS.map((m) => "piano/p" + m + ".mp3"));
    let done = 0;
    await Promise.all(files.map(async (f) => {
      try {
        const url = (window.__SAMPLES__ && window.__SAMPLES__[f]) || ("audio/" + f);
        const res = await fetch(url);
        const ab = await res.arrayBuffer();
        buf[f] = await new Promise((ok, no) => {
          const p = ctx.decodeAudioData(ab, ok, no);
          if (p && p.then) p.then(ok, no);
        });
      } catch (e) {
        console.warn("[AE] 采样加载失败", f, e);
      }
      done++;
      if (onProgress) onProgress(done / files.length);
    }));
    ready = true;
    listeners.forEach((fn) => fn());
  }

  function unlock() {
    init();
    if (ctx.state === "suspended") ctx.resume();
  }

  /* ---------------- 基础播放 ---------------- */

  function drum(name, when, vel, rate) {
    const b = buf[FILES[name] || name];
    if (!b) return;
    const src = ctx.createBufferSource();
    src.buffer = b;
    if (rate) src.playbackRate.value = rate;
    const g = ctx.createGain();
    g.gain.value = vel == null ? 0.95 : vel;
    const p = ctx.createStereoPanner();
    p.pan.value = name.startsWith("hat") ? 0.12 : (name.startsWith("perc") ? -0.18 : 0);
    src.connect(g); g.connect(p);
    p.connect(dryBus);
    // 鼓组也吃一点房间声
    const s = ctx.createGain(); s.gain.value = 0.07;
    p.connect(s); s.connect(revIn);
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    src.start(at);
  }

  function piano(midi, when, vel, dur) {
    let key = null;
    for (let i = 0; i < PIANO_KEYS.length; i++) {
      if (PIANO_KEYS[i] <= midi) key = PIANO_KEYS[i];
      if (PIANO_KEYS[i] >= midi) break;
    }
    if (key == null) key = PIANO_KEYS[0];
    const b = buf["piano/p" + key + ".mp3"];
    if (!b) return;
    const rate = Math.pow(2, (midi - key) / 12);
    const src = ctx.createBufferSource();
    src.buffer = b;
    src.playbackRate.value = rate;
    const g = ctx.createGain();
    const at = Math.max(when || ctx.currentTime, ctx.currentTime + 0.002);
    const v = clamp(vel == null ? 0.8 : vel, 0.02, 1.2);
    const hold = Math.max(0.12, (dur || 1.2));
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(Math.max(0.002, v), at + 0.006);
    g.gain.setTargetAtTime(Math.max(0.002, v * 0.86), at + 0.05, 0.4);
    g.gain.setTargetAtTime(0.0001, at + hold, 0.12);
    src.connect(g);
    const p = ctx.createStereoPanner();
    p.pan.value = clamp((midi - 60) / 90, -0.35, 0.35);
    g.connect(p);
    p.connect(dryBus);
    const s = ctx.createGain(); s.gain.value = 0.3;
    p.connect(s); s.connect(revIn);
    src.start(at);
    src.stop(at + hold + 0.9);
  }

  function bass(midi, when, dur, vel) {
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const f = mtof(midi);
    const len = dur || 0.2;
    const v = clamp(vel == null ? 0.8 : vel, 0.02, 1.2);
    const out = ctx.createGain();
    out.gain.value = 0.85;
    const filt = ctx.createBiquadFilter();
    filt.type = "lowpass";
    filt.Q.value = 6;
    filt.frequency.setValueAtTime(220, at);
    filt.frequency.linearRampToValueAtTime(980, at + 0.015);
    filt.frequency.exponentialRampToValueAtTime(190, at + len);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(v, at + 0.008);
    env.gain.setValueAtTime(v, at + Math.max(0.03, len * 0.7));
    env.gain.exponentialRampToValueAtTime(0.0001, at + len);
    const o1 = ctx.createOscillator(); o1.type = "sawtooth"; o1.frequency.value = f;
    const o2 = ctx.createOscillator(); o2.type = "sine"; o2.frequency.value = f;
    const g2 = ctx.createGain(); g2.gain.value = 0.9;
    o1.connect(filt); o2.connect(g2); g2.connect(filt);
    filt.connect(env); env.connect(out); out.connect(musicBus);
    o1.start(at); o2.start(at);
    o1.stop(at + len + 0.05); o2.stop(at + len + 0.05);
  }

  function lead(midi, when, dur, vel) {
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const f = mtof(midi);
    const len = dur || 0.14;
    const v = clamp(vel == null ? 0.4 : vel, 0.02, 1);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(v, at + 0.008);
    env.gain.setTargetAtTime(v * 0.6, at + 0.02, 0.12);
    env.gain.setValueAtTime(v * 0.6, at + len * 0.8);
    env.gain.exponentialRampToValueAtTime(0.0001, at + len);
    const filt = ctx.createBiquadFilter();
    filt.type = "lowpass"; filt.Q.value = 2.2;
    filt.frequency.setValueAtTime(5200, at);
    filt.frequency.exponentialRampToValueAtTime(1600, at + len);
    for (let i = 0; i < 3; i++) {
      const o = ctx.createOscillator();
      o.type = i === 2 ? "square" : "sawtooth";
      o.frequency.value = f;
      o.detune.value = [-9, 0, 9][i];
      const g = ctx.createGain();
      g.gain.value = i === 2 ? 0.22 : 0.5;
      o.connect(g); g.connect(filt);
      o.start(at); o.stop(at + len + 0.1);
    }
    filt.connect(env);
    const p = ctx.createStereoPanner(); p.pan.value = -0.08;
    env.connect(p); p.connect(musicBus);
    const s = ctx.createGain(); s.gain.value = 0.16; p.connect(s); s.connect(revIn);
    const d = ctx.createGain(); d.gain.value = 0.26; p.connect(d); d.connect(delIn);
  }

  function pluck(midi, when, dur, vel) {
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const f = mtof(midi);
    const len = dur || 0.4;
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(clamp(vel || 0.35, 0.01, 1), at + 0.005);
    env.gain.exponentialRampToValueAtTime(0.0001, at + len);
    const o = ctx.createOscillator(); o.type = "triangle"; o.frequency.value = f;
    const o2 = ctx.createOscillator(); o2.type = "sine"; o2.frequency.value = f * 2;
    const g2 = ctx.createGain(); g2.gain.value = 0.25;
    o.connect(env); o2.connect(g2); g2.connect(env);
    const p = ctx.createStereoPanner(); p.pan.value = 0.1;
    env.connect(p); p.connect(musicBus);
    const d = ctx.createGain(); d.gain.value = 0.3; p.connect(d); d.connect(delIn);
    o.start(at); o2.start(at);
    o.stop(at + len + 0.1); o2.stop(at + len + 0.1);
  }

  function pad(midis, when, dur, vel) {
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const len = dur || 2;
    const v = clamp(vel == null ? 0.18 : vel, 0.01, 0.8);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.linearRampToValueAtTime(v, at + 0.25);
    env.gain.setValueAtTime(v, at + Math.max(0.3, len * 0.75));
    env.gain.exponentialRampToValueAtTime(0.0001, at + len);
    const filt = ctx.createBiquadFilter();
    filt.type = "lowpass"; filt.frequency.value = 1500; filt.Q.value = 0.8;
    (midis || []).forEach((m) => {
      const f = mtof(m);
      [-7, 7].forEach((det) => {
        const o = ctx.createOscillator();
        o.type = "sawtooth"; o.frequency.value = f; o.detune.value = det;
        const g = ctx.createGain(); g.gain.value = 0.32;
        o.connect(g); g.connect(filt);
        o.start(at); o.stop(at + len + 0.15);
      });
    });
    filt.connect(env);
    const p = ctx.createStereoPanner(); p.pan.value = 0;
    env.connect(p); p.connect(musicBus);
    const s = ctx.createGain(); s.gain.value = 0.42; p.connect(s); s.connect(revIn);
  }

  function stab(midis, when, dur, vel) {
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const len = dur || 0.18;
    const v = clamp(vel == null ? 0.14 : vel, 0.01, 0.6);
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, at);
    env.gain.exponentialRampToValueAtTime(v, at + 0.005);
    env.gain.exponentialRampToValueAtTime(0.0001, at + len);
    const filt = ctx.createBiquadFilter();
    filt.type = "lowpass"; filt.Q.value = 3;
    filt.frequency.setValueAtTime(4200, at);
    filt.frequency.exponentialRampToValueAtTime(900, at + len);
    (midis || []).forEach((m) => {
      const o = ctx.createOscillator(); o.type = "sawtooth"; o.frequency.value = mtof(m);
      const g = ctx.createGain(); g.gain.value = 0.28;
      o.connect(g); g.connect(filt);
      o.start(at); o.stop(at + len + 0.05);
    });
    filt.connect(env);
    const p = ctx.createStereoPanner(); p.pan.value = 0.1;
    env.connect(p); p.connect(musicBus);
    const s = ctx.createGain(); s.gain.value = 0.2; p.connect(s); s.connect(revIn);
    const d = ctx.createGain(); d.gain.value = 0.18; p.connect(d); d.connect(delIn);
  }

  function click(when, accent) {
    if (!ctx) return;
    const at = Math.max(when || ctx.currentTime, ctx.currentTime);
    const o = ctx.createOscillator();
    o.type = "square";
    o.frequency.value = accent ? 1600 : 1050;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, at);
    g.gain.exponentialRampToValueAtTime(accent ? 0.16 : 0.09, at + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, at + 0.045);
    o.connect(g); g.connect(dryBus);
    o.start(at); o.stop(at + 0.06);
  }

  function duck(when, depth, len) {
    if (!musicBus) return;
    const at = Math.max(when, ctx.currentTime);
    const d = depth == null ? 0.45 : depth;
    const g = musicBus.gain;
    g.cancelScheduledValues(at);
    g.setValueAtTime(1, at);
    g.linearRampToValueAtTime(1 - d, at + 0.008);
    g.linearRampToValueAtTime(1, at + (len || 0.18));
  }

  /* ---------------- 走带 ---------------- */
  const Transport = {
    playing: false,
    step: 0,
    bpm: 128,
    swing: 0,
    totalSteps: 64,
    pattern: null,
    _timer: null,
    _raf: null,
    _next: 0,
    _queue: [],
    _onStep: null,
    _onBar: null,
    _onLoop: null,
    _onVisual: null,

    start(opts) {
      unlock();
      this.stop(true);
      opts = opts || {};
      this.bpm = opts.bpm || this.bpm || 128;
      this.swing = opts.swing || 0;
      this.totalSteps = opts.steps || 64;
      this._onStep = opts.onStep || null;
      this._onBar = opts.onBar || null;
      this._onLoop = opts.onLoop || null;
      this._onVisual = opts.onVisual || null;
      this.playing = true;
      this.step = 0;
      this._queue = [];
      this._next = ctx.currentTime + 0.09;
      this._timer = setInterval(() => this._tick(), 25);
      this._tick();
      this._loopVisual();
    },

    _tick() {
      const look = 0.14;
      while (this._next < ctx.currentTime + look) {
        const sd = 60 / this.bpm / 4;
        const swingOff = (this.step % 2 === 1) ? this.swing * sd * 0.5 : 0;
        const t = this._next + swingOff;
        const step = this.step;
        const bar = Math.floor(step / 16);
        if (this._onStep) this._onStep(step % 16, t, bar, step);
        this._queue.push({ step: step % 16, bar, time: t });
        this._next += sd;
        this.step++;
        if (this.step >= this.totalSteps) {
          this.step = 0;
          if (this._onLoop) this._onLoop();
        }
      }
    },

    _loopVisual() {
      const tick = () => {
        if (!this.playing) return;
        const now = ctx.currentTime;
        let cur = null;
        while (this._queue.length && this._queue[0].time <= now + 0.02) {
          cur = this._queue.shift();
        }
        if (cur && this._onVisual) this._onVisual(cur.step, cur.bar);
        this._raf = requestAnimationFrame(tick);
      };
      this._raf = requestAnimationFrame(tick);
    },

    stop(silent) {
      this.playing = false;
      if (this._timer) clearInterval(this._timer);
      if (this._raf) cancelAnimationFrame(this._raf);
      this._timer = this._raf = null;
      this._queue = [];
      if (!silent) {
        if (musicBus) musicBus.gain.cancelScheduledValues(ctx.currentTime);
        if (musicBus) musicBus.gain.setValueAtTime(1, ctx.currentTime);
      }
    }
  };

  /* ---------------- 工具 ---------------- */
  function getLevels() {
    if (!analyser) return { rms: 0, peak: 0, db: -100 };
    analyser.getFloatTimeDomainData(anData);
    let sum = 0, peak = 0;
    for (let i = 0; i < anData.length; i++) {
      const v = anData[i];
      sum += v * v;
      if (Math.abs(v) > peak) peak = Math.abs(v);
    }
    const rms = Math.sqrt(sum / anData.length);
    return { rms, peak, db: 20 * Math.log10(rms + 1e-8), peakDb: 20 * Math.log10(peak + 1e-8) };
  }

  function setVolume(v) {
    volume = clamp(v, 0, 1);
    if (master) master.gain.setTargetAtTime(muted ? 0 : volume, ctx.currentTime, 0.02);
  }
  function setMuted(m) {
    muted = m;
    setVolume(volume);
  }
  function setLimiter(on) {
    limiterOn = on;
    if (!ctx) return;
    // 关掉 limiter 时把它变成透明：阈值 0dB、压缩比 1:1
    limiter.threshold.setTargetAtTime(on ? -2 : 0, ctx.currentTime, 0.02);
    limiter.ratio.setTargetAtTime(on ? 20 : 1, ctx.currentTime, 0.02);
    limiter.release.setTargetAtTime(on ? 0.12 : 0.3, ctx.currentTime, 0.02);
  }
  function setLowCut(hz) {
    if (!musicHP) return;
    musicHP.frequency.setTargetAtTime(Math.max(20, hz || 20), ctx.currentTime, 0.05);
  }
  function setMasterDrive(db) {
    if (!driveGain) return;
    driveGain.gain.setTargetAtTime(Math.pow(10, (db || 0) / 20), ctx.currentTime, 0.04);
  }
  function getPreLevels() {
    if (!preAnalyser) return { rms: 0, peak: 0, db: -100, peakDb: -100 };
    preAnalyser.getFloatTimeDomainData(preData);
    let sum = 0, peak = 0;
    for (let i = 0; i < preData.length; i++) { const v = preData[i]; sum += v * v; if (Math.abs(v) > peak) peak = Math.abs(v); }
    const rms = Math.sqrt(sum / preData.length);
    return { rms, peak, db: 20 * Math.log10(rms + 1e-8), peakDb: 20 * Math.log10(peak + 1e-8) };
  }
  function setDelayBeat(bpm, division) {
    if (!delNode) return;
    const t = (60 / bpm) / (division || 4) * 3;
    delNode.delayTime.setTargetAtTime(clamp(t, 0.02, 1.5), ctx.currentTime, 0.05);
  }

  function playSequence(notes, bpm, opts) {
    unlock();
    opts = opts || {};
    const beat = 60 / (bpm || 120);
    const t0 = ctx.currentTime + (opts.delay == null ? 0.12 : opts.delay);
    const times = [];
    notes.forEach((n) => {
      const at = t0 + n.beat * beat;
      times.push(at);
      const dur = (n.dur == null ? 1 : n.dur) * beat;
      piano(n.midi, at, n.vel == null ? 0.75 : n.vel, dur);
      if (opts.onNote) {
        const ms = (at - ctx.currentTime) * 1000;
        setTimeout(() => opts.onNote(n, at), Math.max(0, ms));
      }
    });
    if (opts.onEnd) {
      const end = t0 + (opts.tail || 1.2);
      setTimeout(() => opts.onEnd(), Math.max(0, (end - ctx.currentTime) * 1000));
    }
    return times;
  }

  function now() { return ctx ? ctx.currentTime : 0; }

  // 预加载
  const readyPromise = { then: (fn) => { if (ready) fn(); else listeners.push(fn); } };

  return {
    init, load, unlock, readyPromise,
    get ctx() { return ctx; },
    get ready() { return ready; },
    now, mtof,
    drum, piano, bass, lead, pluck, pad, stab, click, duck,
    playSequence, getLevels, getPreLevels, setVolume, setMuted, setLimiter, setDelayBeat, setLowCut, setMasterDrive,
    Transport,
    get analyser() { return analyser; },
    PIANO_KEYS
  };
})();
