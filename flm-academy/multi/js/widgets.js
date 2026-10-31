/* ===========================================================
   FLM 学院 · 互动组件
   =========================================================== */
window.W = (function () {
  "use strict";
  const C = window.COURSE;
  const AE = window.AE;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  const running = new Set();

  /* ---------------- 段落 ---------------- */
  const SECTIONS = {
    intro: { drums: { kick: 1, hatc: 1, hato: 1 }, bass: 0, chords: "pad", lead: 0 },
    build: { drums: { kick: 1, hatc: 1, hato: 1 }, bass: 0, chords: "pad", lead: 0, riser: 1 },
    drop: { drums: { kick: 1, snare: 1, clap: 1, hatc: 1, hato: 1, perc: 1 }, bass: 1, chords: 1, lead: 1, impact: 1 },
    break: { drums: {}, bass: 0, chords: "pad", lead: "arp8" },
    outro: { drums: { kick: 1, hatc: 1 }, bass: 1, chords: "pad", lead: 0 }
  };

  function sectionAt(p, bar) {
    if (!p.arrangement || !p.arrangement.length) return null;
    const total = p.arrangement.reduce((a, s) => a + s.bars, 0) || 1;
    let b = bar % total, acc = 0;
    for (let i = 0; i < p.arrangement.length; i++) {
      const s = p.arrangement[i];
      if (b < acc + s.bars) return { sec: s, barIn: b - acc, index: i };
      acc += s.bars;
    }
    return { sec: p.arrangement[0], barIn: 0, index: 0 };
  }

  function totalBars(p) {
    if (p.arrangement && p.arrangement.length) return p.arrangement.reduce((a, s) => a + s.bars, 0);
    return p.bars || 4;
  }

  function chaosChord() {
    const keys = Object.keys(C.chords);
    return keys[Math.floor(Math.random() * keys.length)];
  }

  function scheduleStep(p, step, time, bar) {
    const arr = sectionAt(p, bar);
    const sec = arr ? SECTIONS[arr.sec.type] : null;
    const barDur = (60 / p.bpm) * 4;
    const chordId = p.chords.chaos ? chaosChord() : (p.chords.list[bar % p.chords.list.length] || "Am");
    const chord = C.chords[chordId] || C.chords.Am;
    const voice = C.voice[chordId] || chord.notes;

    // 鼓
    const gd = p.gain.drums;
    C.drumRows.forEach((row) => {
      const t = p.drums[row.id];
      if (!t || !t.on || !t.steps) return;
      if (sec && !sec.drums[row.id]) return;
      if (t.steps.indexOf(step) < 0) return;
      const human = row.id === "hatc" ? 1 + (Math.random() - 0.5) * 0.08 : 1;
      AE.drum(t.sample, time, clamp((t.gain || 0.8) * gd * human, 0, 1.2));
      if (row.id === "kick" && p.sidechain) AE.duck(time, 0.5, 0.17);
    });

    // 和弦
    const chordMode = sec ? (sec.chords || "none") : (p.chords.on ? p.chords.mode : "none");
    if (step === 0 && (chordMode === "pad")) {
      AE.pad(voice, time, barDur * 0.99, 0.2 * (p.chords.gain || 0.7) * p.gain.chords);
    }
    if (chordMode === "stab" && [2, 6, 10, 14].indexOf(step) >= 0) {
      AE.stab(voice, time, 0.16, 0.2 * (p.chords.gain || 0.7) * p.gain.chords);
    }

    // 贝斯
    const bassOn = sec ? sec.bass : p.bass.on;
    if (bassOn) {
      let note = null;
      if (p.bass.chaos) note = 33 + Math.floor(Math.random() * 14);
      else if (p.bass.mode === "root8" && step % 2 === 0) note = chord.bass;
      else if (p.bass.mode === "offbeat" && step % 2 === 1) note = chord.bass;
      else if (p.bass.mode === "rolling") note = chord.bass + (step % 2 ? 12 : 0);
      if (note != null) AE.bass(note, time, p.bass.mode === "rolling" ? 0.1 : 0.16, 0.9 * p.bass.gain * p.gain.bass);
    }

    // 主音
    const leadOn = sec ? !!sec.lead : p.lead.on;
    if (leadOn) {
      const mode = (sec && sec.lead === "arp8") ? "arp8" : p.lead.mode;
      const seq = [0, 1, 2, 1, 3, 2, 1, 2];
      const tone = voice[seq[step % seq.length] % voice.length] + 12;
      const lv = 0.35 * (p.lead.gain || 0.6) * p.gain.lead;
      if (p.lead.chaos) {
        if (step % 2 === 0) AE.lead(57 + Math.floor(Math.random() * 24), time, 0.12, lv);
      } else if (mode === "arp16") {
        AE.lead(tone, time, 0.11, lv);
      } else if (mode === "arp8" && step % 2 === 0) {
        AE.lead(tone, time, 0.2, lv);
      } else if (mode === "stab" && [2, 6, 10, 14].indexOf(step) >= 0) {
        AE.stab(voice.map((m) => m + 12), time, 0.14, lv * 0.8);
      }
    }

    // FX
    if (arr) {
      if (p.fx.riser && arr.sec.type === "build" && arr.barIn === 0 && step === 0) {
        AE.drum("riser1", time, 0.55);
      }
      if (p.fx.impact && arr.sec.type === "drop" && arr.barIn === 0 && step === 0) {
        AE.drum("impact1", time, 0.7);
      }
      if (p.fx.impact && arr.sec.type === "break" && arr.barIn === 0 && step === 0) {
        AE.drum("impact2", time, 0.35);
      }
    }
  }

  function stopAll() {
    AE.Transport.stop();
    running.forEach((fn) => { try { fn(); } catch (e) {} });
    running.clear();
  }

  /* =========================================================
     1. 跟拍
     ========================================================= */
  function mountTap(cfg, host, ctx) {
    const id = "tap" + Math.random().toString(36).slice(2);
    const threshold = cfg.threshold || 60;
    const beats = cfg.beats || 8;
    const bpm = cfg.bpm || 128;
    const beatDur = 60 / bpm;
    let times = [], taps = [], started = false, raf = null;

    host.innerHTML =
      '<div class="card">' +
      '<div class="row between mb16"><div><div class="h3">节拍跟拍</div>' +
      '<div class="tiny">' + bpm + ' BPM · ' + beats + ' 拍 · 目标 ' + threshold + ' 分</div></div>' +
      '<button class="btn primary" data-act="start">开始跟拍</button></div>' +
      '<div class="tap-pad" data-pad><div class="big">点这里</div><div class="sub">先听 4 拍，然后跟着「咚」每拍点一下</div></div>' +
      '<div class="tap-meta"><span>得分 <b data-score>--</b></span><span>命中 <b data-hits>0/' + beats + '</b></span>' +
      '<span data-msg class="tiny"></span></div>' +
      '<div class="tap-dots" data-dots>' + Array.from({ length: beats }).map(() => '<span class="tap-dot"></span>').join("") + '</div>' +
      '<div data-result class="mt12"></div>' +
      '</div>';

    const pad = $("[data-pad]", host);
    const dots = $$("[data-dots] .tap-dot", host);
    const scoreEl = $("[data-score]", host);
    const hitsEl = $("[data-hits]", host);
    const msgEl = $("[data-msg]", host);
    const resultEl = $("[data-result]", host);

    function start() {
      AE.unlock();
      stopAll();
      started = true;
      taps = [];
      dots.forEach((d) => { d.className = "tap-dot"; });
      resultEl.innerHTML = "";
      scoreEl.textContent = "--";
      hitsEl.textContent = "0/" + beats;
      msgEl.textContent = "听 4 拍…";
      const t0 = AE.now() + 0.35;
      for (let i = 0; i < 4; i++) AE.click(t0 + i * beatDur, i === 0);
      times = [];
      for (let i = 0; i < beats; i++) {
        const t = t0 + (4 + i) * beatDur;
        times.push(t);
        AE.click(t, i % 4 === 0);
      }
      raf = setInterval(() => {
        if (AE.now() > times[times.length - 1] + beatDur * 0.5) finish();
      }, 80);
      setTimeout(() => { msgEl.textContent = "现在！跟着点"; }, (t0 + 4 * beatDur - AE.now()) * 1000);
      running.add(() => { clearInterval(raf); });
    }

    function hit() {
      if (!started) { start(); return; }
      const t = AE.now();
      let best = -1, err = 9;
      times.forEach((bt, i) => {
        const e = Math.abs(t - bt);
        if (e < err && !taps.some((x) => x.i === i)) { err = e; best = i; }
      });
      if (best < 0) { pad.classList.add("hit"); setTimeout(() => pad.classList.remove("hit"), 90); return; }
      taps.push({ i: best, err });
      const d = dots[best];
      d.textContent = String(best + 1);
      d.className = "tap-dot " + (err < 0.09 ? "great" : err < 0.16 ? "good" : "bad");
      hitsEl.textContent = taps.length + "/" + beats;
      pad.classList.add("hit");
      setTimeout(() => pad.classList.remove("hit"), 90);
      if (taps.length >= beats) setTimeout(finish, 350);
    }

    function finish() {
      if (!started) return;
      started = false;
      clearInterval(raf);
      let score = 0;
      taps.forEach((x) => {
        score += x.err < 0.09 ? 100 : x.err < 0.16 ? 85 : x.err < 0.28 ? 60 : 30;
      });
      score = Math.round(score / beats);
      if (taps.length < beats) score = Math.round(score * (taps.length / beats));
      scoreEl.textContent = score;
      const okk = score >= threshold;
      resultEl.innerHTML = '<div class="result-bar ' + (okk ? "good" : score >= 50 ? "mid" : "bad") + '">' +
        (okk ? "✅ 拍感在线！" : "🎯 再来一次：先听 4 拍，身体先动，手再跟上。") +
        (okk ? " 得分 " + score + "，已记录。" : " 当前 " + score + " 分，需要 " + threshold + " 分。") + '</div>';
      msgEl.textContent = "";
      if (ctx.setTask) ctx.setTask("tap", okk);
      if (okk && ctx.toast) ctx.toast("跟拍通过 · " + score + " 分", "good");
    }

    $("[data-act=start]", host).addEventListener("click", start);
    pad.addEventListener("pointerdown", (e) => { e.preventDefault(); hit(); });

    return { destroy: () => { clearInterval(raf); } };
  }

  /* =========================================================
     2. 键盘
     ========================================================= */
  const BLACK = [1, 3, 6, 8, 10];
  const isBlack = (m) => BLACK.indexOf(((m % 12) + 12) % 12) >= 0;
  const KEYMAP = { a: 0, w: 1, s: 2, e: 3, d: 4, f: 5, t: 6, g: 7, y: 8, h: 9, u: 10, j: 11, k: 12, o: 13, l: 14, p: 15, ";": 16, "'": 17 };

  function mountKeyboard(cfg, host, ctx) {
    const range = cfg.range || [48, 72];
    const mode = cfg.mode || "free";
    const lo = range[0], hi = range[1];
    const whites = [];
    for (let m = lo; m <= hi; m++) if (!isBlack(m)) whites.push(m);
    const whiteW = 100 / whites.length;

    let html = '<div class="piano-wrap"><div class="piano-bar">';
    if (mode === "sequence" || mode === "chords" || mode === "progression" || mode === "dyn") {
      html += '<button class="btn sm primary" data-act="start">' + (mode === "sequence" ? "开始跟弹" : "开始") + '</button>';
      html += '<button class="btn sm ghost" data-act="hint">听提示</button>';
    }
    html += '<div class="sp"></div>';
    if (mode === "dyn" || mode === "free" || mode === "sequence") {
      html += '<div class="bpm-box">力度 <input type="range" min="10" max="127" value="' + (cfg.vel || 80) + '" data-vel style="width:80px"></div>';
    }
    if (mode === "pedal") html += '<button class="btn sm" data-act="pedal">🦶 延音踏板</button>';
    html += '<div class="pos-read" data-info></div></div>';
    html += '<div class="kb-scroll"><div class="kb" data-kb>';
    whites.forEach((m, i) => {
      const label = m % 12 === 0 ? C.noteName(m) : "";
      html += '<div class="key w" data-midi="' + m + '" style="width:' + whiteW + '%">' +
        '<span class="lab">' + label + '</span></div>';
    });
    for (let m = lo; m <= hi; m++) {
      if (!isBlack(m)) continue;
      let prev = m - 1, wi = 0;
      while (prev >= lo && isBlack(prev)) prev--;
      wi = whites.indexOf(prev);
      const left = (wi + 1) * whiteW - whiteW * 0.31;
      html += '<div class="key b" data-midi="' + m + '" style="left:' + left + '%">' +
        '<span class="lab">' + (isBlack(m) && m % 12 === 1 ? "" : "") + '</span></div>';
    }
    html += '</div></div>';
    html += '<div class="kb-legend"><span><i style="background:#7fdcff"></i>目标音</span>' +
      '<span><i style="background:#ffb75e"></i>你按下的音</span>' +
      '<span>电脑键盘：A W S E D F T G Y H U J K</span></div>';
    if (mode === "findC") html += '<div class="guide-banner" data-banner>提示：两个黑键左边紧挨着的白键就是 C。</div>';
    if (mode === "sequence") html += '<div class="guide-banner" data-banner>点「开始跟弹」，先听 4 拍，再按高亮的音。</div><div style="padding:0 14px 14px" data-dots class="seq-dots"></div>';
    if (mode === "chords" || mode === "progression") html += '<div class="guide-banner" data-banner></div><div style="padding:0 14px 14px" data-dots class="seq-dots"></div>';
    if (mode === "dyn") html += '<div class="guide-banner" data-banner>把力度滑杆调小弹前两个音，调大弹后两个音。</div><div style="padding:0 14px 14px" data-dots class="seq-dots"></div>';
    if (mode === "pedal") html += '<div class="guide-banner" data-banner>先踩下踏板，再弹 Am 的三个音（A-C-E）。</div>';
    html += '<div data-result style="padding:0 14px 14px"></div>';
    html += '</div>';
    host.innerHTML = html;

    const kb = $("[data-kb]", host);
    const info = $("[data-info]", host);
    const banner = $("[data-banner]", host);
    const dotsHost = $("[data-dots]", host);
    const resultEl = $("[data-result]", host);
    const velInput = $("[data-vel]", host);

    let hovered = false;
    let pedal = false;
    let vel = cfg.vel || 80;
    let state = { idx: 0, times: [], errs: [], started: false, pending: [], found: [], vels: [], done: false };

    const keyEls = {};
    $$(".key", kb).forEach((el) => { keyEls[+el.dataset.midi] = el; });

    function velNow() { return velInput ? +velInput.value : vel; }

    function flash(m, cls) {
      const el = keyEls[m];
      if (!el) return;
      el.classList.add(cls || "down");
      setTimeout(() => el.classList.remove(cls || "down"), 150);
    }

    function playNote(m, v) {
      AE.unlock();
      const dur = pedal ? 2.6 : 1.7;
      AE.piano(m, AE.now(), (v || velNow()) / 127, dur);
      flash(m);
    }

    function setInfo(txt) { if (info) info.textContent = txt; }
    function setBanner(txt) { if (banner) banner.innerHTML = txt; }

    /* --- 目标 --- */
    const chordList = cfg.chords || [];
    function chordPcs(id) { return (C.chords[id].notes || []).map((m) => m % 12); }

    function renderDots() {
      if (!dotsHost) return;
      if (mode === "sequence") {
        dotsHost.innerHTML = cfg.notes.map((m, i) =>
          '<span class="seq-dot ' + (i < state.idx ? "ok" : i === state.idx ? "now" : "") + '">' + C.noteName(m) + '</span>').join("");
      } else if (mode === "chords" || mode === "progression") {
        dotsHost.innerHTML = chordList.map((c, i) =>
          '<span class="seq-dot ' + (state.done && i < state.idx ? "ok" : i === state.idx ? "now" : "") + '">' + c + '</span>').join("");
      } else if (mode === "dyn") {
        dotsHost.innerHTML = cfg.notes.map((m, i) =>
          '<span class="seq-dot ' + (i < state.vels.length ? "ok" : i === state.vels.length ? "now" : "") + '">' +
          C.noteName(m) + '</span>').join("");
      }
    }

    function highlightTargets(list) {
      $$(".key", kb).forEach((el) => el.classList.remove("hl"));
      (list || []).forEach((m) => { if (keyEls[m]) keyEls[m].classList.add("hl"); });
    }

    /* --- 跟弹 --- */
    function startSeq() {
      AE.unlock();
      stopAll();
      state = { idx: 0, times: [], errs: [], started: true, pending: [], found: state.found || [], vels: [], done: false };
      renderDots();
      resultEl.innerHTML = "";
      const bpm = cfg.bpm || 70;
      const beat = 60 / bpm;
      const t0 = AE.now() + 0.3;
      for (let i = 0; i < 4; i++) AE.click(t0 + i * beat, i === 0);
      state.times = cfg.notes.map((n, i) => t0 + (4 + i) * beat);
      setBanner("跟节拍弹：<b>" + cfg.notes.map((m) => C.noteName(m)).join(" → ") + "</b>");
      const tick = setInterval(() => {
        const i = state.idx;
        if (i < cfg.notes.length) highlightTargets([cfg.notes[i]]);
        if (AE.now() > state.times[state.times.length - 1] + 0.9) { finishSeq(); }
      }, 100);
      running.add(() => clearInterval(tick));
    }

    function finishSeq() {
      if (!state.started) return;
      state.started = false;
      const n = cfg.notes.length;
      let total = 0;
      for (let i = 0; i < n; i++) {
        if (i >= state.errs.length) { total += 0; continue; }
        const e = state.errs[i];
        total += e < 0.12 ? 100 : e < 0.25 ? 85 : e < 0.5 ? 60 : e < 1.0 ? 30 : 15;
      }
      const score = Math.round(total / n);
      const okk = score >= 70 && state.errs.length === n;
      resultEl.innerHTML = '<div class="result-bar ' + (okk ? "good" : score >= 45 ? "mid" : "bad") + '">' +
        (okk ? "✅ 弹得不错！" : "🎯 慢一点，先看清下一个音。") + " 得分 " + score + " / 100</div>";
      if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, okk);
      if (okk && ctx.toast) ctx.toast("跟弹通过 · " + score + " 分", "good");
      highlightTargets([]);
    }

    /* --- 找 C --- */
    function checkFindC(m) {
      const isC = m % 12 === 0;
      if (!isC) {
        setBanner("不是这个。找<b>两个黑键左边</b>的白键。你点的这个音是 " + C.noteName(m) + "。");
        return;
      }
      const targets = cfg.targets;
      if (targets && targets.indexOf(m) < 0) {
        setBanner("这是 " + C.noteName(m) + "，但我要的是 " + targets.map((x) => C.noteName(x)).join(" 和 ") + "。");
        return;
      }
      if (state.found.indexOf(m) >= 0) { setBanner("这个 C 已经点过啦，换一个。"); return; }
      state.found.push(m);
      const need = cfg.count || (targets ? targets.length : 3);
      setBanner("找到 " + state.found.length + " / " + need + " 个 C：" + state.found.map((x) => C.noteName(x)).join("、"));
      if (state.found.length >= need) {
        setBanner("✅ 全部找到：" + state.found.map((x) => C.noteName(x)).join("、"));
        if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, true);
        if (ctx.toast) ctx.toast("找到全部 C", "good");
      }
    }

    /* --- 和弦 --- */
    function checkChord(m) {
      if (!state.started) {
        state.started = true;
        state.idx = 0;
        state.pending = [];
      }
      if (state.idx >= chordList.length) return;
      state.pending.push({ m: m, t: AE.now() });
      // 同一音重复点不算
      const now = AE.now();
      state.pending = state.pending.filter((x) => now - x.t < 2.2);
      const target = chordPcs(chordList[state.idx]);
      const uniq = [];
      state.pending.forEach((x) => { if (uniq.indexOf(x.m % 12) < 0) uniq.push(x.m % 12); });
      setInfo("已按：" + uniq.map((pc) => C.noteName(pc + 60)).join(" "));
      if (uniq.length >= target.length) {
        const same = target.length === uniq.length && target.every((pc) => uniq.indexOf(pc) >= 0);
        if (same) {
          highlightTargets(C.chords[chordList[state.idx]].notes);
          state.idx++;
          state.pending = [];
          renderDots();
          if (state.idx >= chordList.length) {
            state.started = false;
            state.done = true;
            setBanner("✅ 四个和弦全部弹对：" + chordList.join(" → "));
            resultEl.innerHTML = '<div class="result-bar good">✅ 和弦全部正确，手型记住它。</div>';
            if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, true);
            if (ctx.toast) ctx.toast("和弦全对！", "good");
          } else {
            setBanner("✅ " + chordList[state.idx - 1] + " 正确！下一个：<b>" + chordList[state.idx] + "</b>（" +
              C.chords[chordList[state.idx]].notes.map((x) => C.noteName(x)).join(" + ") + "）");
          }
        } else {
          setBanner("还不对：你按的是 " + uniq.map((pc) => C.noteName(pc + 60)).join(" ") +
            "，需要 " + C.chords[chordList[state.idx]].notes.map((x) => C.noteName(x)).join(" + ") + "。再试一次。");
          state.pending = [];
        }
      }
    }

    /* --- 力度 --- */
    function checkDyn(m) {
      const target = cfg.notes[state.vels.length];
      if (m !== target) {
        setBanner("先按高亮的那个音：" + C.noteName(target) + "。");
        return;
      }
      state.vels.push(velNow());
      renderDots();
      if (state.vels.length >= cfg.notes.length) {
        const soft = (state.vels[0] + state.vels[1]) / 2;
        const loud = (state.vels[2] + state.vels[3]) / 2;
        const okk = loud - soft >= 25;
        resultEl.innerHTML = '<div class="result-bar ' + (okk ? "good" : "mid") + '">' +
          (okk ? "✅ 动态对比 " + Math.round(loud - soft) + "（很明确）" : "🎯 对比还不够：前两个音再轻一点，后两个再重一点。") + '</div>';
        setBanner(okk ? "✅ 这就是「表情」。" : "力度差 " + Math.round(loud - soft) + "，需要 25 以上。");
        if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, okk);
        if (okk && ctx.toast) ctx.toast("力度对比通过", "good");
        state.vels = [];
      } else {
        setBanner("已弹 " + state.vels.length + " / 4 个音（力度 " + velNow() + "）");
      }
    }

    /* --- 踏板 --- */
    let pedalNotes = [];
    function checkPedal(m) {
      const pcs = [9, 0, 4]; // A C E
      if (!pedal) { setBanner("踏板还没踩。先点上面的「延音踏板」。"); return; }
      if (pcs.indexOf(m % 12) < 0) return;
      if (pedalNotes.indexOf(m % 12) < 0) pedalNotes.push(m % 12);
      setBanner("踏板踩住，已弹：" + pedalNotes.map((pc) => C.noteName(pc + 60)).join(" "));
      if (pedalNotes.length >= 3) {
        resultEl.innerHTML = '<div class="result-bar good">✅ 三个音连成一片了。换和弦时记得松一下再踩。</div>';
        if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, true);
        if (ctx.toast) ctx.toast("踏板练习完成", "good");
        pedalNotes = [];
      }
    }

    /* --- 输入 --- */
    function noteOn(m) {
      playNote(m);
      if (typeof cfg.onNote === "function") { try { cfg.onNote(m, velNow()); } catch (e) {} }
      if (mode === "findC") checkFindC(m);
      else if (mode === "sequence") {
        if (!state.started) { setBanner("先点「开始跟弹」。"); return; }
        if (state.idx >= cfg.notes.length) return;
        if (m !== cfg.notes[state.idx]) { setBanner("要按高亮的 " + C.noteName(cfg.notes[state.idx]) + "。"); return; }
        const err = Math.abs(AE.now() - state.times[state.idx]);
        state.errs.push(err);
        state.idx++;
        renderDots();
        setInfo("进度 " + state.idx + "/" + cfg.notes.length);
        if (state.idx >= cfg.notes.length) finishSeq();
        else setBanner("下一个：<b>" + C.noteName(cfg.notes[state.idx]) + "</b>");
      } else if (mode === "chords" || mode === "progression") {
        checkChord(m);
      } else if (mode === "dyn") {
        checkDyn(m);
      } else if (mode === "pedal") {
        checkPedal(m);
      }
    }

    $$(".key", kb).forEach((el) => {
      el.addEventListener("pointerdown", (e) => { e.preventDefault(); noteOn(+el.dataset.midi); });
    });

    kb.addEventListener("pointerenter", () => { hovered = true; });
    kb.addEventListener("pointerleave", () => { hovered = false; });

    const onKey = (e) => {
      if (!hovered) return;
      if (e.target && /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
      const k = e.key.toLowerCase();
      if (KEYMAP[k] == null) return;
      e.preventDefault();
      const m = 60 + KEYMAP[k];
      if (m >= lo && m <= hi) noteOn(m);
    };
    window.addEventListener("keydown", onKey);

    const startBtn = $("[data-act=start]", host);
    if (startBtn) startBtn.addEventListener("click", () => {
      if (!AE.ready) { AE.init(); AE.load(); }
      if (mode === "sequence") startSeq();
      else if (mode === "chords" || mode === "progression") {
        AE.unlock();
        state.started = true; state.idx = 0; state.pending = [];
        setBanner("开始：弹 <b>" + chordList[0] + "</b>（" + C.chords[chordList[0]].notes.map((x) => C.noteName(x)).join(" + ") + "）");
        highlightTargets(C.chords[chordList[0]].notes);
        renderDots();
      } else if (mode === "dyn") {
        state.vels = [];
        setBanner("从第一个音开始：" + C.noteName(cfg.notes[0]));
        highlightTargets([cfg.notes[0]]);
        renderDots();
      }
    });

    const hintBtn = $("[data-act=hint]", host);
    if (hintBtn) hintBtn.addEventListener("click", () => {
      AE.unlock();
      if (mode === "sequence") {
        const i = Math.min(state.idx, cfg.notes.length - 1);
        AE.piano(cfg.notes[i], AE.now(), 0.6, 0.8);
        highlightTargets([cfg.notes[i]]);
      } else if (mode === "chords" || mode === "progression") {
        const c = chordList[Math.min(state.idx, chordList.length - 1)];
        C.chords[c].notes.forEach((m, i) => AE.piano(m, AE.now() + i * 0.02, 0.6, 1.1));
        highlightTargets(C.chords[c].notes);
      } else if (mode === "dyn") {
        const m = cfg.notes[Math.min(state.vels.length, 3)];
        AE.piano(m, AE.now(), 0.5, 0.9);
      }
    });

    const pedalBtn = $("[data-act=pedal]", host);
    if (pedalBtn) pedalBtn.addEventListener("click", () => {
      pedal = !pedal;
      pedalBtn.classList.toggle("done", pedal);
      pedalBtn.textContent = pedal ? "🦶 踏板已踩下" : "🦶 延音踏板";
      setBanner(pedal ? "踏板踩住了。现在弹 A-C-E。" : "踏板松开。");
    });

    if (velInput) velInput.addEventListener("input", () => { vel = +velInput.value; });

    // 初始提示
    if (mode === "chords" || mode === "progression") {
      setBanner("点「开始」后，按提示弹出 " + chordList.join(" → ") + "。三个音要同时按（可以先摸再按）。");
    }
    if (mode === "dyn") setBanner("力度滑杆控制触键轻重。前两个音轻（30），后两个重（90+）。");
    renderDots();

    return { destroy: () => { window.removeEventListener("keydown", onKey); } };
  }

  /* =========================================================
     3. Lab：网格音序器 + 和弦/贝斯/主音
     ========================================================= */
  function mountLab(cfg, host, ctx) {
    const rows = cfg.rows || ["kick", "snare", "hatc"];
    const rowDefs = C.drumRows.filter((r) => rows.indexOf(r.id) >= 0);
    let state;
    if (cfg.preset === "empty") state = C.pattern({ bpm: cfg.bpm || 128, bars: cfg.bars || 4 });
    else if (cfg.preset) state = C.pattern(Object.assign({ bpm: cfg.bpm || 128, bars: cfg.bars || 4 }, cfg.preset));
    else state = C.pattern({ bpm: cfg.bpm || 128, bars: cfg.bars || 4 });
    if (cfg.arrangement) state.arrangement = state.arrangement || [
      { type: "intro", bars: 2 }, { type: "build", bars: 2 }, { type: "drop", bars: 4 }
    ];

    const RULER = ["1", "e", "&", "a", "2", "e", "&", "a", "3", "e", "&", "a", "4", "e", "&", "a"];
    let html = '<div class="lab"><div class="lab-bar">' +
      '<div class="transport"><button class="play-btn" data-act="play">▶</button></div>' +
      '<div class="bpm-box">BPM <input type="number" min="70" max="180" value="' + state.bpm + '" data-bpm></div>' +
      '<div class="pos-read" data-pos>1 / ' + totalBars(state) + '</div>' +
      '<div class="sp"></div>' +
      '<button class="btn sm ghost" data-act="clear">清空</button>' +
      '<button class="btn sm ghost" data-act="demo">试听示例</button>' +
      '</div>';
    html += '<div class="grid-scroll"><div class="grid">';
    html += '<div class="grid-ruler"><span>轨道</span>' + RULER.map((r, i) => '<span class="' + (i % 4 === 0 ? "b" : "") + '">' + r + '</span>').join("") + '</div>';
    rowDefs.forEach((r) => {
      html += '<div class="grid-row" data-row="' + r.id + '"><div class="grid-label ' + (state.drums[r.id].on ? "on" : "") + '" data-label="' + r.id + '" title="点击静音/取消静音，双击清空轨道">' +
        '<span class="sq">✓</span>' + r.label + ' <span class="tiny">' + r.en + '</span></div>';
      for (let s = 0; s < 16; s++) {
        html += '<button class="step-cell ' + (s % 4 === 0 ? "beat" : "") + ' ' + (state.drums[r.id].steps.indexOf(s) >= 0 ? "on" : "") +
          '" data-row="' + r.id + '" data-step="' + s + '" aria-label="' + r.label + ' 第 ' + (s + 1) + ' 格"></button>';
      }
      html += '</div>';
    });
    html += '</div></div>';

    const extras = [];
    if (cfg.chords) extras.push('<div class="field"><label>和弦进行（每小节一个）</label><div class="chord-row" style="display:grid;grid-template-columns:repeat(4,1fr);gap:5px" data-chords></div></div>');
    if (cfg.bass) extras.push('<div class="field"><label>贝斯</label><select data-bass></select></div>');
    if (cfg.lead) extras.push('<div class="field"><label>主音</label><select data-lead></select></div>');
    if (cfg.fx || cfg.arrangement) {
      extras.push('<div class="field"><label>音效 / 结构</label><div style="display:flex;gap:14px;flex-wrap:wrap">' +
        (cfg.fx ? '<label class="switch"><input type="checkbox" data-fx="riser" ' + (state.fx.riser ? "checked" : "") + '><span class="track"></span>Riser 上升</label>' +
          '<label class="switch"><input type="checkbox" data-fx="impact" ' + (state.fx.impact ? "checked" : "") + '><span class="track"></span>Impact 冲击</label>' : '') +
        (cfg.arrangement ? '<label class="switch"><input type="checkbox" data-arrmode ' + (state.arrangement ? "checked" : "") + '><span class="track"></span>编排模式</label>' : '') +
        '</div></div>');
    }
    if (cfg.chords) {
      html += '<div class="lab-extra">' + extras.join("") + '</div>';
    } else if (extras.length) {
      html += '<div class="lab-extra">' + extras.join("") + '</div>';
    }
    html += '<div class="lab-foot"><div class="lab-goals" data-goals></div><div class="sp" style="flex:1"></div><span class="tiny" data-hint></span></div>';
    html += '</div>';
    host.innerHTML = html;

    const playBtn = $("[data-act=play]", host);
    const posEl = $("[data-pos]", host);
    const goalsEl = $("[data-goals]", host);
    const bpmInput = $("[data-bpm]", host);
    let playing = false;
    let cells = {};
    $$(".step-cell", host).forEach((el) => { cells[el.dataset.row + ":" + el.dataset.step] = el; });

    if (cfg.chords) {
      const wrap = $("[data-chords]", host);
      const options = cfg.chords.options || ["Am", "F", "C", "G"];
      for (let i = 0; i < 4; i++) {
        const sel = document.createElement("select");
        sel.innerHTML = options.map((o) => '<option ' + (state.chords.list[i] === o ? "selected" : "") + '>' + o + '</option>').join("");
        sel.dataset.ci = i;
        sel.addEventListener("change", () => { state.chords.list[i] = sel.value; evaluate(); });
        wrap.appendChild(sel);
      }
    }
    const bassSel = $("[data-bass]", host);
    if (bassSel) {
      bassSel.innerHTML = (cfg.bass.modes || [["root8", "根音 8 分"]]).map((m) => '<option value="' + m[0] + '" ' + (state.bass.mode === m[0] ? "selected" : "") + '>' + m[1] + '</option>').join("");
      bassSel.addEventListener("change", () => { state.bass.mode = bassSel.value; state.bass.on = bassSel.value !== "none"; evaluate(); });
    }
    const leadSel = $("[data-lead]", host);
    if (leadSel) {
      leadSel.innerHTML = (cfg.lead.modes || [["none", "关闭"]]).map((m) => '<option value="' + m[0] + '" ' + (state.lead.mode === m[0] ? "selected" : "") + '>' + m[1] + '</option>').join("");
      leadSel.addEventListener("change", () => { state.lead.mode = leadSel.value; state.lead.on = leadSel.value !== "none"; evaluate(); });
    }
    $$("[data-fx]", host).forEach((el) => {
      el.addEventListener("change", () => { state.fx[el.dataset.fx] = el.checked; evaluate(); });
    });
    const arrChk = $("[data-arrmode]", host);
    if (arrChk) {
      arrChk.addEventListener("change", () => {
        state.arrangement = arrChk.checked ? [
          { type: "intro", bars: 2 }, { type: "build", bars: 2 }, { type: "drop", bars: 4 }
        ] : null;
        posEl.textContent = "1 / " + totalBars(state);
        evaluate();
      });
    }

    $$(".step-cell", host).forEach((el) => {
      el.addEventListener("click", () => {
        const r = el.dataset.row, s = +el.dataset.step;
        const arr = state.drums[r].steps;
        const i = arr.indexOf(s);
        if (i >= 0) arr.splice(i, 1); else arr.push(s);
        arr.sort((a, b) => a - b);
        el.classList.toggle("on", arr.indexOf(s) >= 0);
        evaluate();
      });
    });
    $$("[data-label]", host).forEach((el) => {
      el.addEventListener("click", () => {
        const r = el.dataset.label;
        state.drums[r].on = !state.drums[r].on;
        el.classList.toggle("on", state.drums[r].on);
        evaluate();
      });
      el.addEventListener("dblclick", () => {
        state.drums[el.dataset.label].steps = [];
        $$('.step-cell[data-row="' + el.dataset.label + '"]', host).forEach((c) => c.classList.remove("on"));
        evaluate();
      });
    });

    bpmInput.addEventListener("change", () => {
      state.bpm = clamp(+bpmInput.value || 128, 60, 190);
      bpmInput.value = state.bpm;
      if (playing) start();
    });

    function evaluate() {
      let all = true;
      const chips = (cfg.goals || []).map((g) => {
        let ok = false;
        try { ok = !!g.test(state); } catch (e) { ok = false; }
        if (ctx.setTask) ctx.setTask(g.id, ok);
        if (!ok) all = false;
        return '<span class="goal ' + (ok ? "ok" : "") + '"><span class="g">' + (ok ? "✓" : "○") + '</span>' + g.label + '</span>';
      });
      goalsEl.innerHTML = chips.join("");
      if (all && cfg.goals && cfg.goals.length && !state._celebrated) {
        state._celebrated = true;
        if (ctx.toast) ctx.toast("全部目标达成！点播放听听你的作品 🎧", "good");
      }
      if (!all) state._celebrated = false;
    }

    function start() {
      AE.unlock();
      stopAll();
      playing = true;
      playBtn.classList.add("playing");
      playBtn.textContent = "■";
      const steps = totalBars(state) * 16;
      AE.Transport.start({
        bpm: state.bpm, swing: state.swing, steps,
        onStep: (s, t, bar) => scheduleStep(state, s, t, bar),
        onVisual: (s, bar) => {
          Object.keys(cells).forEach((k) => cells[k].classList.remove("ph"));
          $$('.step-cell[data-step="' + s + '"]', host).forEach((c) => c.classList.add("ph"));
          posEl.textContent = (bar + 1) + " / " + totalBars(state);
        }
      });
      running.add(stop);
    }
    function stop() {
      playing = false;
      AE.Transport.stop();
      playBtn.classList.remove("playing");
      playBtn.textContent = "▶";
      $$(".step-cell", host).forEach((c) => c.classList.remove("ph"));
    }
    function toggle() { playing ? stop() : start(); }

    playBtn.addEventListener("click", toggle);
    $("[data-act=clear]", host).addEventListener("click", () => {
      rowDefs.forEach((r) => { state.drums[r.id].steps = []; });
      $$(".step-cell", host).forEach((c) => c.classList.remove("on"));
      evaluate();
    });
    $("[data-act=demo]", host).addEventListener("click", () => {
      stop();
      const demo = C.pattern({
        bpm: state.bpm, bars: 4,
        drums: {
          kick: { steps: [0, 8] }, snare: { steps: [4, 12] },
          hatc: { steps: C.even, gain: 0.32 }, hato: { steps: C.offbeat, gain: 0.4 }
        },
        chords: { list: state.chords.list.slice(), gain: 0.55 },
        bass: { mode: "root8", gain: 0.8 }
      });
      const steps = 4 * 16;
      AE.unlock();
      playBtn.classList.add("playing");
      playBtn.textContent = "■";
      playing = true;
      AE.Transport.start({
        bpm: demo.bpm, steps,
        onStep: (s, t, bar) => scheduleStep(demo, s, t, bar),
        onVisual: (s, bar) => {
          $$('.step-cell[data-step="' + s + '"]', host).forEach((c) => c.classList.add("ph"));
          posEl.textContent = (bar + 1) + " / 4";
        }
      });
      running.add(stop);
    });

    if (cfg.hint) $("[data-hint]", host).textContent = cfg.hint;
    evaluate();
    return { destroy: stop, getState: () => state };
  }

  /* =========================================================
     4. 调音台
     ========================================================= */
  function mountMixer(cfg, host, ctx) {
    const faders = cfg.faders.map((f) => Object.assign({}, f));
    const st = { faders, sidechain: !!cfg.sidechain, lowcut: cfg.lowcut ? 30 : 0, playing: false };
    let pattern = null;

    let html = '<div class="lab"><div class="lab-bar">' +
      '<div class="transport"><button class="play-btn" data-act="play">▶</button></div>' +
      '<div class="bpm-box">BPM <input type="number" value="126" data-bpm disabled></div>' +
      '<div class="sp"></div><span class="tiny">推子 = 各轨道的音量</span></div>';
    html += '<div class="mix">';
    faders.forEach((f) => {
      html += '<div class="strip"><div class="nm">' + f.label + '</div>' +
        '<div style="position:relative;height:96px;display:flex;justify-content:center">' +
        '<div style="position:absolute;width:26px;height:100%;background:linear-gradient(180deg,rgba(255,92,122,.16) 0%,rgba(74,222,128,.16) 30%,rgba(74,222,128,.16) 100%);border-radius:4px;left:50%;transform:translateX(-50%)"></div>' +
        '<input class="fader" type="range" min="0" max="100" value="' + f.value + '" data-fader="' + f.id + '" style="writing-mode:vertical-lr;direction:rtl;-webkit-appearance:slider-vertical;width:22px;height:96px">' +
        '</div>' +
        '<div class="val" data-val="' + f.id + '">' + f.value + '</div></div>';
    });
    html += '</div>';
    html += '<div class="mix-sub">' +
      '<div class="mix-opt"><div class="hd"><b>侧链 Sidechain</b><label class="switch"><input type="checkbox" data-sidechain ' + (st.sidechain ? "checked" : "") + '><span class="track"></span></label></div>' +
      '<div class="tiny">底鼓一响，贝斯和 Pad 自动让路</div></div>' +
      '<div class="mix-opt"><div class="hd"><b>低频切除 Low Cut</b><span class="v" data-lcval>' + st.lowcut + ' Hz</span></div>' +
      '<input type="range" min="0" max="120" step="5" value="' + st.lowcut + '" data-lowcut style="width:100%">' +
      '<div class="tiny">切掉贝斯 30Hz 以下的「浑浊」</div></div>' +
      '<div class="mix-opt"><div class="hd"><b>总输出</b><span class="v" data-db>-∞ dB</span></div>' +
      '<div class="master-meter" data-meter><i></i><span class="clip"></span></div>' +
      '<div class="tiny">峰值不要撞到 0 dB（红区）</div></div>' +
      '</div>';
    html += '<div class="lab-foot"><div class="lab-goals" data-goals></div></div></div>';
    host.innerHTML = html;

    const goalsEl = $("[data-goals]", host);
    const meter = $("[data-meter]", host);
    const dbEl = $("[data-db]", host);
    const playBtn = $("[data-act=play]", host);
    let raf = null;
    let lastEval = 0;

    function gainOf(id) {
      const f = st.faders.find((x) => x.id === id);
      if (!f) return 1;
      return Math.pow(clamp(f.value, 0, 100) / 78, 1.35);
    }

    function buildPattern() {
      const p = C.pattern({
        bpm: 126, bars: 4,
        drums: {
          kick: { steps: [0, 4, 8, 12], gain: 0.95 },
          snare: { steps: [4, 12], gain: 0.8 },
          hatc: { steps: [0, 4, 8, 12], gain: 0.4 },
          hato: { steps: [2, 6, 10, 14], gain: 0.5 },
          clap: { steps: [4, 12], gain: 0.5, on: true }
        },
        chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.55 },
        bass: { mode: "root8", gain: 0.9 },
        lead: { on: true, mode: "arp16", gain: 0.5 },
        sidechain: st.sidechain
      });
      p.gain.drums = 1;
      p.gain.bass = gainOf("bass");
      p.gain.chords = gainOf("pad") * 1.2;
      p.gain.lead = gainOf("lead") * 1.2;
      p.drums.kick.gain = 0.95 * gainOf("kick");
      p.drums.snare.gain = 0.8 * gainOf("snare");
      p.drums.hatc.gain = 0.4 * gainOf("hat");
      p.drums.hato.gain = 0.5 * gainOf("hat");
      p.drums.clap.gain = 0.5 * gainOf("snare");
      return p;
    }

    function evaluate() {
      const inRange = st.faders.filter((f) => f.value >= f.target[0] && f.value <= f.target[1]).length;
      const s = {
        inRange, sidechain: st.sidechain, lowcut: st.lowcut, peakDb: -100,
        faders: st.faders.reduce((a, f) => (a[f.id] = f.value, a), {})
      };
      const chips = (cfg.goals || []).map((g) => {
        let ok = false;
        try { ok = !!g.test(s); } catch (e) {}
        if (ctx.setTask) ctx.setTask(g.id, ok);
        return '<span class="goal ' + (ok ? "ok" : "") + '"><span class="g">' + (ok ? "✓" : "○") + '</span>' + g.label + '</span>';
      });
      goalsEl.innerHTML = chips.join("");
    }

    function start() {
      AE.unlock();
      stopAll();
      AE.setLowCut(st.lowcut);
      pattern = buildPattern();
      st.playing = true;
      playBtn.classList.add("playing"); playBtn.textContent = "■";
      AE.Transport.start({
        bpm: 126, steps: 64,
        onStep: (s, t, bar) => scheduleStep(pattern, s, t, bar)
      });
      raf = setInterval(() => {
        const lv = AE.getLevels();
        const pct = clamp((lv.peakDb + 48) / 48 * 100, 0, 100);
        $("i", meter).style.width = pct + "%";
        meter.classList.toggle("clipped", lv.peakDb > -0.2);
        dbEl.textContent = lv.peakDb < -60 ? "-∞ dB" : lv.peakDb.toFixed(1) + " dB";
        const now = Date.now();
        if (now - lastEval > 400) { lastEval = now; evaluate(); }
      }, 70);
      running.add(stop);
    }
    function stop() {
      st.playing = false;
      AE.Transport.stop();
      clearInterval(raf);
      playBtn.classList.remove("playing"); playBtn.textContent = "▶";
    }
    playBtn.addEventListener("click", () => st.playing ? stop() : start());

    $$("[data-fader]", host).forEach((el) => {
      el.addEventListener("input", () => {
        const f = st.faders.find((x) => x.id === el.dataset.fader);
        f.value = +el.value;
        $('[data-val="' + f.id + '"]', host).textContent = f.value;
        if (pattern) {
          const p2 = buildPattern();
          Object.assign(pattern.gain, p2.gain);
          C.drumRows.forEach((r) => { if (pattern.drums[r.id]) pattern.drums[r.id].gain = p2.drums[r.id].gain; });
        }
        evaluate();
      });
    });
    $("[data-sidechain]", host).addEventListener("change", (e) => {
      st.sidechain = e.target.checked;
      if (pattern) pattern.sidechain = st.sidechain;
      evaluate();
    });
    $("[data-lowcut]", host).addEventListener("input", (e) => {
      st.lowcut = +e.target.value;
      $("[data-lcval]", host).textContent = st.lowcut + " Hz";
      if (st.playing) AE.setLowCut(st.lowcut);
      evaluate();
    });

    evaluate();
    return { destroy: stop };
  }

  /* =========================================================
     5. 母带
     ========================================================= */
  function mountMaster(cfg, host, ctx) {
    const st = { db: 0, limiter: true, styles: [], hold: -100 };
    let pattern = null, playing = false, raf = null;

    let html = '<div class="lab"><div class="lab-bar">' +
      '<div class="transport"><button class="play-btn" data-act="play">▶</button></div>' +
      '<div class="bpm-box">增益 <input type="range" min="-6" max="14" step="1" value="0" data-gain style="width:110px"><span data-gainval style="min-width:40px;color:var(--orange2)">0 dB</span></div>' +
      '<div class="sp"></div>' +
      '<label class="switch"><input type="checkbox" data-lim checked><span class="track"></span>限幅器</label>' +
      '</div>';
    html += '<div style="padding:16px">' +
      '<div class="row between"><span class="tiny">响度（RMS）</span><span class="v" data-db style="font-size:20px;font-weight:800;font-variant-numeric:tabular-nums">-∞</span></div>' +
      '<div class="master-meter" data-meter style="height:12px"><i></i><span class="clip"></span></div>' +
      '<div class="row between mt8"><span class="tiny">目标：-9 ~ -6 dB</span><span class="tiny" data-peak>峰值 -∞</span></div>' +
      '<div class="target-strip mt12" style="height:26px;border-radius:6px;background:linear-gradient(90deg,rgba(74,222,128,.08) 0 33%,rgba(74,222,128,.25) 33% 50%,rgba(74,222,128,.08) 50%);position:relative;border:1px solid var(--line)">' +
      '<span class="tiny" style="position:absolute;left:34%;top:4px;color:#8df0b3">目标区</span></div>' +
      '</div>';
    if (cfg.styles) {
      html += '<div class="lab-extra" style="grid-template-columns:1fr"><div class="field"><label>你的风格元素（选 3 个）</label><div class="chips" data-styles>' +
        cfg.styles.map((s) => '<button class="chip" data-style="' + s + '">' + s + '</button>').join("") + '</div>' +
        '<div class="tiny mt8" data-sig>选 3 个，组成你的签名。</div></div></div>';
    }
    html += '<div class="lab-foot"><div class="lab-goals" data-goals></div></div></div>';
    host.innerHTML = html;

    const meter = $("[data-meter]", host);
    const dbEl = $("[data-db]", host);
    const peakEl = $("[data-peak]", host);
    const goalsEl = $("[data-goals]", host);
    const gain = $("[data-gain]", host);
    const playBtn = $("[data-act=play]", host);
    let lastEval = 0;

    function evaluate() {
      const s = { db: st.hold, peakDb: st.peak, limiter: st.limiter, styles: st.styles };
      const chips = cfg.goals.map((g) => {
        let ok = false;
        try { ok = !!g.test(s); } catch (e) {}
        if (ctx.setTask) ctx.setTask(g.id, ok);
        return '<span class="goal ' + (ok ? "ok" : "") + '"><span class="g">' + (ok ? "✓" : "○") + '</span>' + g.label + '</span>';
      });
      goalsEl.innerHTML = chips.join("");
    }

    function start() {
      AE.unlock();
      stopAll();
      pattern = C.pattern({
        bpm: 126, bars: 8,
        drums: {
          kick: { steps: [0, 4, 8, 12] }, snare: { steps: [4, 12] },
          clap: { on: true, steps: [4, 12], gain: 0.5 },
          hatc: { steps: [0, 4, 8, 12], gain: 0.3 }, hato: { steps: [2, 6, 10, 14], gain: 0.42 },
          perc: { on: true, steps: [3, 7, 11, 15], gain: 0.3 }
        },
        chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.55 },
        bass: { mode: "root8", gain: 0.9 },
        lead: { on: true, mode: "arp16", gain: 0.5 },
        gain: { drums: 1, bass: 1, chords: 0.65, lead: 0.85 },
        arrangement: [{ type: "build", bars: 4 }, { type: "drop", bars: 8 }]
      });
      AE.setLimiter(st.limiter);
      AE.setMasterDrive(st.db);
      playing = true;
      playBtn.classList.add("playing"); playBtn.textContent = "■";
      AE.Transport.start({ bpm: 126, steps: 192, onStep: (s, t, bar) => scheduleStep(pattern, s, t, bar) });
      let hold = -100;
      raf = setInterval(() => {
        const lv = AE.getLevels();
        const db = lv.db;
        st.peak = lv.peakDb;
        hold = Math.max(db, hold * 0.92);
        st.hold = hold;
        const pct = clamp((db + 48) / 48 * 100, 0, 100);
        $("i", meter).style.width = pct + "%";
        meter.classList.toggle("clipped", lv.peakDb > -0.2);
        dbEl.textContent = db < -60 ? "-∞" : db.toFixed(1);
        peakEl.textContent = "峰值 " + (lv.peakDb < -60 ? "-∞" : lv.peakDb.toFixed(1)) + " dB";
        const now = Date.now();
        if (now - lastEval > 350) { lastEval = now; evaluate(); }
      }, 60);
      running.add(stop);
    }
    function stop() {
      playing = false;
      AE.Transport.stop();
      clearInterval(raf);
      playBtn.classList.remove("playing"); playBtn.textContent = "▶";
      AE.setMasterDrive(0);
      AE.setLimiter(true);
    }
    playBtn.addEventListener("click", () => playing ? stop() : start());

    gain.addEventListener("input", () => {
      st.db = +gain.value;
      $("[data-gainval]", host).textContent = (st.db > 0 ? "+" : "") + st.db + " dB";
      AE.setMasterDrive(st.db);
      if (!playing) {
        st.hold = st.db - 18;
        evaluate();
      }
    });
    $("[data-lim]", host).addEventListener("change", (e) => {
      st.limiter = e.target.checked;
      AE.setLimiter(st.limiter);
      evaluate();
    });
    $$("[data-style]", host).forEach((el) => {
      el.addEventListener("click", () => {
        const s = el.dataset.style;
        const i = st.styles.indexOf(s);
        if (i >= 0) st.styles.splice(i, 1); else st.styles.push(s);
        el.classList.toggle("on", st.styles.indexOf(s) >= 0);
        const sig = $("[data-sig]", host);
        if (st.styles.length === 3) {
          sig.innerHTML = "你的签名：<b>" + st.styles.join(" + ") + "</b> —— 这三个选择就是你区别于别人的地方。";
        } else {
          sig.textContent = "再选 " + (3 - st.styles.length) + " 个（已选 " + st.styles.length + "）";
        }
        evaluate();
      });
    });

    evaluate();
    return { destroy: stop };
  }

  /* =========================================================
     6. 段落编排
     ========================================================= */
  function mountStructure(cfg, host, ctx) {
    const opts = cfg.options;
    let slots = [];
    const bars = (id) => (opts.find((o) => o.id === id) || {}).bars || 0;
    const label = (id) => (opts.find((o) => o.id === id) || {}).label || id;

    host.innerHTML = '<div class="lab"><div class="arr" style="padding:14px">' +
      '<div class="arr-slots" data-slots>' + Array.from({ length: cfg.slots }).map((_, i) =>
        '<div class="arr-slot" data-slot="' + i + '"><span>+ 第 ' + (i + 1) + ' 段</span></div>').join("") + '</div>' +
      '<div class="row between"><span class="tiny" data-total>总长 0 小节</span><button class="btn sm ghost" data-act="reset">重排</button></div>' +
      '<div class="arr-pool" data-pool>' + opts.map((o) => '<button class="arr-chip" data-opt="' + o.id + '">' + o.label + '<small>' + o.bars + ' 小节</small></button>').join("") + '</div>' +
      '</div><div class="lab-foot"><div class="lab-goals" data-goals></div></div></div>';

    const slotsEl = $("[data-slots]", host);
    const poolEl = $("[data-pool]", host);
    const totalEl = $("[data-total]", host);
    const goalsEl = $("[data-goals]", host);

    function render() {
      const cells = $$("[data-slot]", slotsEl);
      cells.forEach((c, i) => {
        if (slots[i]) {
          c.className = "arr-slot filled";
          c.innerHTML = '<span>' + label(slots[i]) + '</span><span class="bars">' + bars(slots[i]) + '′</span><span class="x" data-del="' + i + '">✕</span>';
        } else {
          c.className = "arr-slot";
          c.innerHTML = '<span>+ 第 ' + (i + 1) + ' 段</span>';
        }
      });
      $$("[data-opt]", poolEl).forEach((b) => b.classList.toggle("used", slots.indexOf(b.dataset.opt) >= 0));
      totalEl.textContent = "总长 " + slots.reduce((a, id) => a + bars(id), 0) + " 小节";
      const okk = slots.length === cfg.answer.length && slots.every((s, i) => s === cfg.answer[i]);
      goalsEl.innerHTML = '<span class="goal ' + (okk ? "ok" : "") + '"><span class="g">' + (okk ? "✓" : "○") + '</span>' +
        (okk ? "结构正确！" : "把 " + cfg.answer.length + " 个段落排成一首歌") + '</span>';
      if (ctx.setTask && cfg.task) ctx.setTask(cfg.task, okk);
      if (okk) {
        const totalBars = slots.reduce((a, id) => a + bars(id), 0);
        goalsEl.innerHTML += '<span class="goal ok"><span class="g">♪</span>总长度 ' + totalBars + ' 小节</span>';
      }
    }

    $$("[data-opt]", poolEl).forEach((b) => {
      b.addEventListener("click", () => {
        if (slots.length >= cfg.slots) { if (ctx.toast) ctx.toast("位置已经排满了，先点 ✕ 移除一个。"); return; }
        slots.push(b.dataset.opt);
        render();
      });
    });
    slotsEl.addEventListener("click", (e) => {
      const d = e.target.closest("[data-del]");
      if (!d) return;
      slots.splice(+d.dataset.del, 1);
      render();
    });
    $("[data-act=reset]", host).addEventListener("click", () => { slots = []; render(); });
    render();
    return { destroy() {} };
  }

  /* =========================================================
     7. 签名
     ========================================================= */
  function mountSign(cfg, host, ctx) {
    const saved = (ctx.getName && ctx.getName()) || "";
    host.innerHTML = '<div class="lab"><div class="panel-body">' +
      '<div class="h3">签上你的名字</div>' +
      '<p class="tiny" style="margin:6px 0 12px">这张证书会写上你的名字，代表你真的从「噪音」走到了「作品」。</p>' +
      '<div class="row"><input type="text" data-name maxlength="12" placeholder="你的名字 / 艺名" value="' + saved.replace(/"/g, "&quot;") + '" style="flex:1;background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:10px 12px;color:var(--txt);font-family:inherit;font-size:14px;outline:none">' +
      '<button class="btn primary" data-act="sign">签名</button></div>' +
      '<div class="mt12" data-msg></div></div></div>';
    const input = $("[data-name]", host);
    const msg = $("[data-msg]", host);
    $("[data-act=sign]", host).addEventListener("click", () => {
      const name = input.value.trim();
      if (name.length < 1) { msg.innerHTML = '<div class="result-bar bad">先写个名字吧。</div>'; return; }
      if (ctx.setName) ctx.setName(name);
      if (ctx.setTask) ctx.setTask(cfg.task || "name", true);
      msg.innerHTML = '<div class="result-bar good">✅ 已签名：<b>' + name + '</b>。去「毕业证书」页面领取。</div>';
      if (ctx.toast) ctx.toast("签名完成", "good");
    });
  }

  /* =========================================================
     入口
     ========================================================= */
  const MOUNTS = {
    tap: mountTap, keyboard: mountKeyboard, lab: mountLab,
    mixer: mountMixer, master: mountMaster, structure: mountStructure, sign: mountSign
  };

  function mount(kind, cfg, host, ctx) {
    if (!MOUNTS[kind]) { host.innerHTML = "<p>未知组件: " + kind + "</p>"; return null; }
    try {
      return MOUNTS[kind](cfg, host, ctx || {});
    } catch (e) {
      console.error("[W] 组件渲染失败", kind, e);
      host.innerHTML = '<div class="result-bar bad">组件加载失败：' + e.message + '</div>';
      return null;
    }
  }

  return { mount, stopAll, scheduleStep, totalBars, sectionAt };
})();
