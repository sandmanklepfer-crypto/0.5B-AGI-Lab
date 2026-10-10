/* ==========================================================
   音效 / 背景音乐管理（纯 Web Audio 合成版 · 零外部文件依赖）
   - BGM：lookahead 调度器程序化生成（main 悠远氛围 / boss 紧张战歌）
   - SFX：全部同步即时合成，确定可响，带随机音高变化
   - 注意：core.js 中已声明 AudioMgr，这里用 Object.assign 覆盖扩展，
     避免顶层 const 重复声明导致整个脚本 SyntaxError 失效。
   ========================================================== */

(function () {
  const impl = {
    ctx: null,
    masterGain: null,
    bgmGain: null,
    sfxGain: null,

    currentBgm: null,      // 当前 BGM 类型（保留，便于设置面板恢复）
    _schedOn: false,       // 调度器是否在跑
    _schedTimer: null,
    _nextNoteTime: 0,
    _noteStep: 0,

    bgmVolume: 0.4,
    sfxVolume: 0.7,

    _noiseBuffer: null,

    // ---------------- 初始化 ----------------
    init() {
      if (this.ctx) return;
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        this.ctx = new AudioCtx();

        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.value = 1;
        this.masterGain.connect(this.ctx.destination);

        this.bgmGain = this.ctx.createGain();
        this.bgmGain.gain.value = this.bgmVolume;
        this.bgmGain.connect(this.masterGain);

        this.sfxGain = this.ctx.createGain();
        this.sfxGain.gain.value = this.sfxVolume;
        this.sfxGain.connect(this.masterGain);

        // 回声（空间感）：bgm 同时送入 delay
        const delay = this.ctx.createDelay(1);
        delay.delayTime.value = 0.32;
        const fb = this.ctx.createGain();
        fb.gain.value = 0.3;
        const wet = this.ctx.createGain();
        wet.gain.value = 0.22;
        this.bgmGain.connect(delay);
        delay.connect(fb);
        fb.connect(delay);
        delay.connect(wet);
        wet.connect(this.masterGain);

        this._buildNoise();
      } catch (e) {
        console.warn('Audio init failed:', e);
      }
    },

    _buildNoise() {
      const len = this.ctx.sampleRate * 2;
      const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
      const d = buf.getChannelData(0);
      for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
      this._noiseBuffer = buf;
    },

    // 用户手势后恢复
    resume() {
      if (this.ctx && this.ctx.state === 'suspended') {
        this.ctx.resume().catch(() => {});
      }
    },

    // ---------------- BGM ----------------
    playBgm(type) {
      if (!this.ctx) this.init();
      if (!this.ctx) return;

      // 记录期望类型（即使音乐开关关闭也记录，开启时可恢复）
      if (type !== this.currentBgm) this.currentBgm = type;

      const musicOn = !(window.GameState) || GameState.settings.music !== false;
      if (!musicOn) return;
      if (this._schedOn && type === this._bgmType) return;

      this._bgmType = type;
      this._startScheduler();
    },

    stopBgm() {
      this._stopScheduler();
    },

    _startScheduler() {
      this._stopScheduler();
      this._noteStep = 0;
      this._nextNoteTime = this.ctx.currentTime + 0.06;
      this._schedOn = true;
      this._schedTimer = setInterval(() => this._scheduler(), 80);
    },

    _stopScheduler() {
      this._schedOn = false;
      if (this._schedTimer) {
        clearInterval(this._schedTimer);
        this._schedTimer = null;
      }
    },

    _scheduler() {
      if (!this.ctx || !this._schedOn) return;
      const stepDur = this._bgmType === 'boss' ? 0.3 : 0.75;
      while (this._nextNoteTime < this.ctx.currentTime + 0.22) {
        this._scheduleStep(this._noteStep, this._nextNoteTime, stepDur);
        this._nextNoteTime += stepDur;
        this._noteStep++;
      }
    },

    // 五声音阶（宫商角徵羽）
    _PENTA: [261.63, 293.66, 329.63, 392.0, 440.0, 523.25, 587.33, 659.25, 783.99, 880.0],
    // boss 用小调音（带半音，紧张）
    _MINOR: [261.63, 311.13, 349.23, 392.0, 466.16, 523.25, 622.25, 698.46],

    _scheduleStep(step, time, stepDur) {
      if (this._bgmType === 'boss') {
        // 不协和低音 drone
        if (step % 16 === 0) {
          this._tone(65.41, time, 4.6, { wave: 'sawtooth', vol: 0.09, cutoff: 500 });
          this._tone(77.78, time, 4.6, { wave: 'sawtooth', vol: 0.07, cutoff: 500 });
        }
        // bass line
        if (step % 4 === 0) {
          const b = [65.41, 77.78, 87.31, 77.78][(step / 4) % 4];
          this._tone(b, time, 0.26, { wave: 'square', vol: 0.16, cutoff: 900 });
        }
        // 连续紧迫琶音
        if (Math.random() < 0.72) {
          const f = this._MINOR[Math.floor(Math.random() * this._MINOR.length)];
          this._tone(f, time, 0.26, { wave: 'sawtooth', vol: 0.12, cutoff: 1900 });
        }
        // kick
        if (step % 2 === 0) this._kick(time);
        // hat
        if (step % 4 === 2) this._hat(time);
      } else {
        // main：悠远氛围
        if (step % 8 === 0) {
          const drone = (step / 8) % 2 === 0 ? 65.41 : 98.0;
          this._tone(drone, time, 6.2, { wave: 'triangle', vol: 0.12 });
          this._tone(drone * 2, time, 6.2, { wave: 'sine', vol: 0.05 });
        }
        // 五声音阶缓慢琶音
        if (Math.random() < 0.62) {
          const hi = Math.random() < 0.28 ? 5 : 0;
          const f = this._PENTA[hi + Math.floor(Math.random() * 5)];
          this._tone(f, time, 1.4, { wave: 'triangle', vol: 0.15, attack: 0.03 });
        }
        if (Math.random() < 0.18) {
          const f = this._PENTA[Math.floor(Math.random() * this._PENTA.length)];
          this._tone(f, time, 1.2, { wave: 'sine', vol: 0.1 });
        }
      }
    },

    // 基础乐音
    _tone(freq, start, dur, opts = {}) {
      const ctx = this.ctx;
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = opts.wave || 'triangle';
      osc.frequency.setValueAtTime(freq, start);
      if (opts.glideTo) osc.frequency.exponentialRampToValueAtTime(opts.glideTo, start + dur);

      const vol = opts.vol !== undefined ? opts.vol : 0.14;
      const atk = opts.attack || 0.012;
      g.gain.setValueAtTime(0, start);
      g.gain.linearRampToValueAtTime(vol, start + atk);
      g.gain.setValueAtTime(vol, start + Math.max(atk, dur - dur * 0.5));
      g.gain.exponentialRampToValueAtTime(0.0008, start + dur);

      let node = osc;
      if (opts.cutoff) {
        const flt = ctx.createBiquadFilter();
        flt.type = 'lowpass';
        flt.frequency.value = opts.cutoff;
        osc.connect(flt);
        node = flt;
      }
      node.connect(g);
      g.connect(this.bgmGain);
      osc.start(start);
      osc.stop(start + dur + 0.05);
    },

    _kick(time) {
      const ctx = this.ctx;
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(150, time);
      osc.frequency.exponentialRampToValueAtTime(48, time + 0.14);
      g.gain.setValueAtTime(0.55, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + 0.18);
      osc.connect(g); g.connect(this.bgmGain);
      osc.start(time); osc.stop(time + 0.2);
    },

    _hat(time) {
      const ctx = this.ctx;
      const src = ctx.createBufferSource();
      src.buffer = this._noiseBuffer;
      const flt = ctx.createBiquadFilter();
      flt.type = 'highpass';
      flt.frequency.value = 7000;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.12, time);
      g.gain.exponentialRampToValueAtTime(0.001, time + 0.04);
      src.connect(flt); flt.connect(g); g.connect(this.bgmGain);
      src.start(time); src.stop(time + 0.05);
    },

    // ---------------- SFX ----------------
    playSfx(type) {
      if (!this.ctx) this.init();
      if (!this.ctx) return;
      const sfxOn = !(window.GameState) || GameState.settings.sfx !== false;
      if (!sfxOn) return;
      this.resume();
      this._synth(type);
    },

    // 兼容旧调用：真实音效 → 直接合成（opts.volume 生效）
    playRealSfx(key, opts = {}) {
      if (!this.ctx) this.init();
      if (!this.ctx) return;
      const sfxOn = !(window.GameState) || GameState.settings.sfx !== false;
      if (!sfxOn) return;
      this.resume();
      this._synth(key, opts);
    },

    // 一个合成音（osc 可选滑音）
    _blip(wave, freq, dur, vol, glideTo, startOffset = 0) {
      const ctx = this.ctx;
      const t = ctx.currentTime + startOffset;
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = wave;
      osc.frequency.setValueAtTime(freq, t);
      if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t + dur);
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(vol, t + 0.008);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      osc.connect(g); g.connect(this.sfxGain);
      osc.start(t); osc.stop(t + dur + 0.02);
    },

    // 一段噪声（可选滤波扫频）
    _noiseHit(dur, vol, filterType, freqFrom, freqTo, startOffset = 0) {
      const ctx = this.ctx;
      const t = ctx.currentTime + startOffset;
      const src = ctx.createBufferSource();
      src.buffer = this._noiseBuffer;
      const flt = ctx.createBiquadFilter();
      flt.type = filterType;
      flt.frequency.setValueAtTime(freqFrom, t);
      if (freqTo) flt.frequency.exponentialRampToValueAtTime(freqTo, t + dur);
      const g = ctx.createGain();
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      src.connect(flt); flt.connect(g); g.connect(this.sfxGain);
      src.start(t); src.stop(t + dur + 0.02);
    },

    _synth(type, opts = {}) {
      const v = opts.volume !== undefined ? opts.volume : 1;
      // 随机音高 ±6%
      const p = 1 + (Math.random() * 2 - 1) * 0.06;
      const P = (f) => f * p;

      switch (type) {
        case 'hit':
        case 'attack':
          // 低频砰 + 高频噪声啪
          this._blip('sine', P(185), 0.1, 0.5 * v, P(62));
          this._noiseHit(0.07, 0.28 * v, 'highpass', 1200);
          break;
        case 'explosion':
        case 'skillHit':
        case 'ult':
          this._noiseHit(0.5, 0.42 * v, 'lowpass', 3200, 200);
          this._blip('sine', P(120), 0.45, 0.4 * v, P(40));
          break;
        case 'hurt':
        case 'playerHit':
          this._blip('sawtooth', P(300), 0.18, 0.34 * v, P(120));
          this._noiseHit(0.08, 0.18 * v, 'bandpass', 900);
          break;
        case 'skill':
          this._blip('sawtooth', P(320), 0.18, 0.24 * v, P(900));
          break;
        case 'dash':
          this._blip('sine', P(520), 0.1, 0.16 * v, P(1300));
          break;
        case 'dodge':
          this._blip('sine', P(620), 0.11, 0.18 * v, P(1450));
          break;
        case 'click':
          this._blip('sine', P(880), 0.06, 0.2 * v);
          break;
        case 'enemyDeath':
          this._blip('square', P(220), 0.18, 0.26 * v, P(70));
          this._noiseHit(0.14, 0.2 * v, 'lowpass', 1600, 300);
          break;
        case 'bossAppear':
          this._blip('sawtooth', P(120), 0.9, 0.34 * v, P(45));
          this._noiseHit(0.9, 0.12 * v, 'lowpass', 800, 120);
          break;
        case 'relic':
          this._blip('triangle', P(440), 0.35, 0.26 * v, P(880));
          break;
        case 'levelUp':
          this._blip('sine', P(523), 0.14, 0.28 * v);
          this._blip('sine', P(659), 0.16, 0.28 * v, null, 0.09);
          this._blip('sine', P(784), 0.28, 0.28 * v, P(1047), 0.18);
          break;
        case 'victory':
          this._blip('sine', P(523), 0.18, 0.28 * v);
          this._blip('sine', P(659), 0.18, 0.28 * v, null, 0.15);
          this._blip('sine', P(784), 0.2, 0.28 * v, null, 0.3);
          this._blip('sine', P(1047), 0.5, 0.3 * v, null, 0.45);
          break;
        case 'gameOver':
          this._blip('sawtooth', P(300), 1.1, 0.3 * v, P(70));
          this._noiseHit(1.0, 0.14 * v, 'lowpass', 1000, 100);
          break;
        default:
          this._blip('sine', P(440), 0.1, 0.16 * v);
      }
    },

    // ---------------- 音量 / 开关 ----------------
    toggle() {
      // 兼容：总开关（与设置 sfx 联动）
      const on = window.GameState ? GameState.settings.sfx !== false : true;
      if (window.GameState) GameState.settings.sfx = !on;
      return !on;
    },

    setBgmVolume(vol) {
      this.bgmVolume = vol;
      if (this.bgmGain) this.bgmGain.gain.value = vol;
    },

    setSfxVolume(vol) {
      this.sfxVolume = vol;
      if (this.sfxGain) this.sfxGain.gain.value = vol;
    },
  };

  // 覆盖扩展 core.js 中已声明的 AudioMgr；若不存在则直接挂到 window
  if (typeof AudioMgr !== 'undefined') {
    Object.assign(AudioMgr, impl);
  } else {
    window.AudioMgr = impl;
  }
})();
