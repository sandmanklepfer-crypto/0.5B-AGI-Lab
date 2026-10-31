/* ===========================================================
   FLM 学院 · 应用主逻辑
   =========================================================== */
(function () {
  "use strict";
  const C = window.COURSE;
  const AE = window.AE;
  const W = window.W;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.prototype.slice.call((r || document).querySelectorAll(s));
  const KEY = "flm-academy-v1";

  /* ---------------- 状态 ---------------- */
  const DEFAULT = { xp: 0, done: {}, tasks: {}, name: "", tour: false, unlockAll: false, works: [], seen: {} };
  let S = load();

  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return Object.assign({}, DEFAULT);
      return Object.assign({}, DEFAULT, JSON.parse(raw));
    } catch (e) { return Object.assign({}, DEFAULT); }
  }
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {}
  }

  const LESSONS = C.allLessons();
  const TOTAL = LESSONS.length;
  const TOTAL_XP = LESSONS.reduce((a, l) => a + l.xp, 0);

  function levelOf(id) { return C.levels.find((l) => l.id === id); }
  function levelLessons(lv) { return lv.lessons; }
  function levelDoneCount(lv) { return lv.lessons.filter((l) => S.done[l.id]).length; }
  function levelComplete(lv) { return lv.lessons.every((l) => S.done[l.id]); }
  function doneCount() { return LESSONS.filter((l) => S.done[l.id]).length; }

  function levelUnlocked(id) {
    if (S.unlockAll) return true;
    if (id === 0) return true;
    return levelComplete(levelOf(id - 1));
  }
  function lessonUnlocked(lv, idx) {
    if (S.unlockAll) return true;
    if (!levelUnlocked(lv.id)) return false;
    if (idx === 0) return true;
    return !!S.done[lv.lessons[idx - 1].id];
  }
  function nextLesson() {
    for (const lv of C.levels) {
      for (let i = 0; i < lv.lessons.length; i++) {
        const l = lv.lessons[i];
        if (!S.done[l.id] && lessonUnlocked(lv, i)) return l;
      }
    }
    return null;
  }
  function rank() {
    let n = 0;
    for (const lv of C.levels) { if (levelComplete(lv)) n++; else break; }
    return n; // 0..6
  }

  /* ---------------- 通用 UI ---------------- */
  let toastTimer = null;
  function toast(msg, type) {
    const el = $("#toast");
    el.className = "toast show " + (type || "");
    el.innerHTML = msg;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = "toast " + (type || ""); }, 2600);
  }

  function modal(html, onMount) {
    const m = $("#modal");
    m.innerHTML = '<div class="modal-box">' + html + "</div>";
    m.classList.add("show");
    m.onclick = (e) => {
      if (e.target === m || (e.target.closest && e.target.closest("[data-close]"))) closeModal();
    };
    if (onMount) onMount(m);
  }
  function closeModal() { const m = $("#modal"); m.classList.remove("show"); m.innerHTML = ""; }

  function fmtDate(ts) {
    const d = new Date(ts);
    return d.getFullYear() + " 年 " + (d.getMonth() + 1) + " 月 " + d.getDate() + " 日";
  }

  /* ---------------- 顶部 / 侧栏 ---------------- */
  function updateChrome() {
    const r = rank();
    const lv = C.levels[Math.min(r, 5)];
    $("#rankName").textContent = r >= 6 ? "Lv.5 大师 · 毕业" : "Lv." + r + " " + lv.name;
    $("#xpFill").style.width = Math.min(100, (S.xp / TOTAL_XP) * 100) + "%";
    $("#xpTxt").textContent = S.xp + " XP";
    const pct = Math.round((doneCount() / TOTAL) * 100);
    $("#mpPct").textContent = pct + "%";
    $("#mpFill").style.width = pct + "%";
    $("#mpSub").textContent = doneCount() + " / " + TOTAL + " 课 · " + S.xp + " XP";

    $("#railLevels").innerHTML = '<div class="rl-title">学习路线</div>' + C.levels.map((l) => {
      const done = levelComplete(l);
      const unlocked = levelUnlocked(l.id);
      return '<div class="rl-item ' + (done ? "done" : "") + " " + (unlocked ? "" : "locked") + '" data-go="' + l.id + '">' +
        '<span class="rl-dot"></span><span>' + l.tag + " " + l.name + '</span></div>';
    }).join("");
    $$("#railLevels [data-go]").forEach((el) => {
      el.addEventListener("click", () => { location.hash = "#/level/" + el.dataset.go; closeRail(); });
    });
    highlightNav();
  }

  function highlightNav() {
    const h = location.hash || "#/home";
    const key = h.indexOf("studio") >= 0 ? "studio" : h.indexOf("piano") >= 0 ? "piano" : h.indexOf("cert") >= 0 ? "cert" : "home";
    $$(".rail-nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === key));
  }

  function closeRail() { $("#rail").classList.remove("open"); $("#railScrim").classList.remove("show"); }

  /* ---------------- 首页 ---------------- */
  function viewHome() {
    const r = rank();
    const nl = nextLesson();
    const pct = Math.round((doneCount() / TOTAL) * 100);
    const lv = C.levels[Math.min(r, 5)];
    const ring = 2 * Math.PI * 26;
    const dash = ring * (pct / 100);

    const ach = achievements();
    const html =
      '<div class="page">' +
      '<section class="hero">' +
      '<div>' +
      '<div class="pill" style="margin-bottom:14px">🎓 互动教程 · 零基础到大师</div>' +
      '<h1>从<em>噪音</em>，到<em>作品</em>。</h1>' +
      '<p>6 个等级、18 节课，全部用 FL Studio Mobile 的真实采样。每一课都先听、再懂、再动手——耳朵、手指、软件，三条线一起长。</p>' +
      '<div class="hero-actions">' +
      (nl ? '<a class="btn primary lg" href="#/lesson/' + nl.id + '">' + (doneCount() ? "继续学习" : "开始第一课") + ' · ' + nl.title + ' →</a>'
        : '<a class="btn primary lg" href="#/cert">领取毕业证书 →</a>') +
      '<a class="btn lg" href="#/studio">进工作台随便玩</a>' +
      '</div>' +
      '<div class="row mt16" style="gap:18px;font-size:12px;color:var(--dim2);flex-wrap:wrap">' +
      '<span>✓ 真实采样</span><span>✓ 自动判定</span><span>✓ 进度保存</span><span>✓ 手机可用</span></div>' +
      '</div>' +
      '<div class="hero-side">' +
      '<div class="hero-badge">' +
      '<div class="ring"><svg width="64" height="64"><circle cx="32" cy="32" r="26" fill="none" stroke="#242c3d" stroke-width="5"/>' +
      '<circle cx="32" cy="32" r="26" fill="none" stroke="url(#gg)" stroke-width="5" stroke-linecap="round" stroke-dasharray="' + dash + ' ' + ring + '"/></svg>' +
      '<defs><linearGradient id="gg"><stop offset="0" stop-color="#ff9e2c"/><stop offset="1" stop-color="#3ee0ff"/></linearGradient></defs>' +
      '<div class="rv">' + pct + '%<small>总进度</small></div></div>' +
      '<div><div style="font-size:13px;font-weight:700">' + (r >= 6 ? "毕业 · 大师" : lv.tag + " " + lv.name) + '</div>' +
      '<div class="tiny">' + (r >= 6 ? "你已经走完了整条路。" : "下一段位：" + C.levels[Math.min(r + 1, 5)].name) + '</div></div>' +
      '</div>' +
      '<div class="hero-stat">' +
      '<div class="stat"><b>' + doneCount() + '<span style="font-size:12px;color:var(--dim2)">/' + TOTAL + '</span></b><span>完成课时</span></div>' +
      '<div class="stat"><b>' + S.xp + '</b><span>经验值 XP</span></div>' +
      '<div class="stat"><b>' + ach.filter((a) => a.on).length + '<span style="font-size:12px;color:var(--dim2)">/' + ach.length + '</span></b><span>成就</span></div>' +
      '<div class="stat"><b>' + (S.unlockAll ? "∞" : "6") + '</b><span>等级</span></div>' +
      '</div>' +
      '</div>' +
      '</section>' +

      '<div class="section-head"><div><div class="h2">学习路线</div><div class="sub">点击进入关卡 · 每关 2 节课 + 1 个考核</div></div>' +
      '<div class="tiny">' + doneCount() + " / " + TOTAL + ' 课已完成</div></div>' +
      '<div class="path">' + C.levels.map((l) => {
        const done = levelComplete(l);
        const unlocked = levelUnlocked(l.id);
        const cur = unlocked && !done;
        const dc = levelDoneCount(l);
        return '<div class="lvl ' + (done ? "done" : "") + " " + (cur ? "cur" : "") + " " + (unlocked ? "" : "locked") + '" data-level="' + l.id + '">' +
          '<div class="lvl-dot">' + (done ? "✓" : l.id) + '</div>' +
          '<div class="lvl-main"><h3>' + l.tag + " · " + l.name +
          (cur ? ' <span class="pill warn">进行中</span>' : "") +
          (done ? ' <span class="pill ok">已通关</span>' : "") +
          (!unlocked ? ' <span class="pill">🔒 未解锁</span>' : "") + '</h3>' +
          '<p>' + l.desc + '</p>' +
          '<div class="lvl-tags">' + l.lessons.map((x) => '<span class="pill" style="font-size:10.5px">' +
            (x.track === "edm" ? "🎛 EDM" : x.track === "piano" ? "🎹 钢琴" : "🏁 考核") + " · " + x.title + '</span>').join("") + '</div></div>' +
          '<div class="lvl-side"><div><div class="lvl-bar"><i style="width:' + (dc / l.lessons.length * 100) + '%"></i></div></div>' +
          '<span class="lvl-pct">' + dc + "/" + l.lessons.length + '</span></div></div>';
      }).join("") + '</div>' +

      '<div class="section-head"><div><div class="h2">成就墙</div><div class="sub">每一关都会留下痕迹</div></div></div>' +
      '<div class="ach-grid">' + ach.map((a) => '<div class="ach ' + (a.on ? "on" : "") + '"><div class="ach-ico">' + a.ico + '</div>' +
        '<div><b>' + a.name + '</b><span>' + a.desc + '</span></div></div>').join("") + '</div>' +

      '<div class="card mt32" style="display:flex;gap:18px;align-items:center;flex-wrap:wrap">' +
      '<div style="font-size:34px">💡</div><div style="flex:1;min-width:240px">' +
      '<div class="h3">完全的新手？先看这 3 句话</div>' +
      '<div class="tiny" style="margin-top:4px">① 先有拍子再加音色；② 每个轨道都要有自己的位置；③ 做完一段先循环听 10 遍再往下走。</div></div>' +
      '<button class="btn" id="homeTour">重新看新手引导</button></div>' +
      '</div>';

    $("#view").innerHTML = html;
    $$(".lvl").forEach((el) => {
      el.addEventListener("click", () => {
        const id = +el.dataset.level;
        if (!levelUnlocked(id)) { toast("先通过上一关的考核才能解锁 🔒"); return; }
        location.hash = "#/level/" + id;
      });
    });
    $("#homeTour").addEventListener("click", () => startTour(true));
    highlightNav();
  }

  function achievements() {
    const pianoDone = LESSONS.filter((l) => l.track === "piano" && S.done[l.id]).length;
    return [
      { ico: "🌱", name: "初来乍到", desc: "打开学院，迈出第一步", on: doneCount() > 0 || S.tour },
      { ico: "🥁", name: "拍感在线", desc: "通过 Lv.0 节奏门", on: !!S.done["l0-exam"] },
      { ico: "🔁", name: "第一个循环", desc: "做出完整的 4 小节鼓组", on: !!S.done["l1-exam"] },
      { ico: "🪄", name: "会跳的 Loop", desc: "掌握反拍与贝斯", on: !!S.done["l2-exam"] },
      { ico: "🎛", name: "编曲人", desc: "完成 8 小节 Drop", on: !!S.done["l3-exam"] },
      { ico: "🎚", name: "混音师", desc: "所有轨道各就各位", on: !!S.done["l4-exam"] },
      { ico: "🏆", name: "大师", desc: "完成毕业作品", on: !!S.done["l5-exam"] },
      { ico: "🎹", name: "键盘手", desc: "完成 3 节钢琴课", on: pianoDone >= 3 },
      { ico: "✨", name: "完美主义", desc: "18 节课全部完成", on: doneCount() >= TOTAL }
    ];
  }

  /* ---------------- 关卡页 ---------------- */
  function viewLevel(id) {
    const lv = levelOf(id);
    if (!lv) { location.hash = "#/home"; return; }
    if (!levelUnlocked(id)) {
      toast("这一关还没解锁，先完成 " + C.levels[id - 1].tag + " 的考核。");
      location.hash = "#/level/" + (id - 1);
      return;
    }
    const dc = levelDoneCount(lv);
    const html = '<div class="page">' +
      '<div class="crumbs"><a href="#/home">首页</a><span class="sep">/</span><span>' + lv.tag + '</span></div>' +
      '<div class="lvl-hero"><div><div class="pill" style="margin-bottom:10px">' + lv.icon + " " + lv.en + '</div>' +
      '<h1 class="h1">' + lv.tag + " · " + lv.name + '</h1><p>' + lv.desc + '</p></div>' +
      '<div style="text-align:right"><div class="tiny">本关进度</div><div style="font-size:28px;font-weight:800;color:' + lv.color + '">' + Math.round(dc / lv.lessons.length * 100) + '%</div></div></div>' +
      '<div class="lesson-list">' + lv.lessons.map((l, i) => {
        const done = !!S.done[l.id];
        const unlocked = lessonUnlocked(lv, i);
        return '<div class="lesson-row ' + (done ? "done" : "") + " " + (unlocked ? "" : "locked") + '" data-lesson="' + l.id + '">' +
          '<div class="lr-ico">' + (done ? "✓" : l.track === "edm" ? "🎛" : l.track === "piano" ? "🎹" : "🏁") + '</div>' +
          '<div><div class="tag">' + (l.track === "edm" ? "EDM 电子" : l.track === "piano" ? "PIANO 钢琴" : "CHECKPOINT 考核") + " · " + l.time + '</div>' +
          '<h4>' + l.title + '</h4><p>' + l.sub + '</p></div>' +
          '<div class="lr-right"><span class="lr-xp">+' + l.xp + ' XP</span>' +
          '<span>' + (done ? "已完成" : unlocked ? "开始 →" : "🔒") + '</span></div></div>';
      }).join("") + '</div>' +

      '<div class="card mt24" style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">' +
      '<div style="font-size:28px">' + lv.icon + '</div><div style="flex:1;min-width:220px">' +
      '<div class="h3">这一关的目标</div><div class="tiny">' + lv.desc + '</div></div>' +
      '<button class="btn primary" id="startLevel">' + (dc ? "继续本关" : "开始本关") + ' →</button></div>' +
      '</div>';
    $("#view").innerHTML = html;
    $$(".lesson-row").forEach((el) => {
      el.addEventListener("click", () => {
        const l = C.getLesson(el.dataset.lesson);
        const i = lv.lessons.findIndex((x) => x.id === l.id);
        if (!lessonUnlocked(lv, i)) { toast("先完成上一节课。"); return; }
        location.hash = "#/lesson/" + l.id;
      });
    });
    $("#startLevel").addEventListener("click", () => {
      const i = lv.lessons.findIndex((l) => !S.done[l.id]);
      const l = lv.lessons[i < 0 ? lv.lessons.length - 1 : i];
      location.hash = "#/lesson/" + l.id;
    });
    highlightNav();
  }

  /* ---------------- 课程页 ---------------- */
  let currentLessonId = null;
  let activeWidgets = [];

  function viewLesson(id) {
    const lesson = C.getLesson(id);
    if (!lesson) { location.hash = "#/home"; return; }
    const lv = levelOf(lesson.level);
    const idx = lv.lessons.findIndex((x) => x.id === id);
    if (!lessonUnlocked(lv, idx)) {
      toast("这一节课还没解锁。");
      location.hash = "#/level/" + lv.id;
      return;
    }
    W.stopAll();
    currentLessonId = id;
    S.tasks[id] = {};
    save();

    const prev = LESSONS[LESSONS.findIndex((l) => l.id === id) - 1];
    const next = LESSONS[LESSONS.findIndex((l) => l.id === id) + 1];
    const done = !!S.done[id];

    const html = '<div class="page">' +
      '<div class="crumbs"><a href="#/home">首页</a><span class="sep">/</span>' +
      '<a href="#/level/' + lv.id + '">' + lv.tag + " " + lv.name + '</a><span class="sep">/</span><span>' + lesson.title + '</span></div>' +
      '<div class="lesson-wrap">' +
      '<div><div class="lesson-head">' +
      '<div class="kicker">' + (lesson.track === "edm" ? "🎛 EDM 线" : lesson.track === "piano" ? "🎹 钢琴线" : "🏁 考核") + " · " + lesson.time + " · +" + lesson.xp + " XP</div>" +
      '<h1>' + lesson.title + '</h1><div class="lead">' + lesson.lead + '</div>' +
      '<div class="steps">' +
      (lesson.blocks.filter((b) => b.type === "demo").length ? '<span class="step-chip"><b>1</b>先听</span>' : "") +
      (lesson.blocks.filter((b) => b.type === "p" || b.type === "h" || b.type === "tip" || b.type === "terms").length ? '<span class="step-chip"><b>2</b>搞懂</span>' : "") +
      (lesson.blocks.filter((b) => b.type === "widget").length ? '<span class="step-chip"><b>3</b>动手</span>' : "") +
      '<span class="step-chip"><b>4</b>通关</span>' +
      '</div></div>' +
      '<div class="lesson-progress"><i id="lessonProg" style="width:0%"></i></div>' +
      '<div class="blocks" id="blocks">' + lesson.blocks.map((b, i) => blockHTML(b, i)).join("") + '</div>' +
      '<div id="lessonEnd"></div>' +
      '<div class="lesson-nav mt24">' +
      (prev ? '<a class="btn" href="#/lesson/' + prev.id + '" id="prevBtn">← ' + prev.title + '</a>' : '<span></span>') +
      (next ? '<a class="btn primary" href="#/lesson/' + next.id + '" id="nextBtn">' + next.title + ' →</a>' : '<a class="btn primary" href="#/cert">领取证书 →</a>') +
      '</div></div>' +

      '<aside class="side-sticky"><div class="task-card">' +
      '<div class="task-head"><b>本课任务</b><span class="cnt" id="taskCnt">0 / ' + lesson.tasks.length + '</span></div>' +
      '<ul class="task-list" id="taskList">' + lesson.tasks.map((t) => '<li data-task="' + t.id + '"><span class="box">✓</span><span>' + t.label + '</span></li>').join("") + '</ul>' +
      '<div class="task-foot"><div class="tiny" id="taskHint">完成全部任务即可通关</div>' +
      '<button class="btn sm" id="btnReset" style="width:100%">重置本课</button></div>' +
      '</div>' +
      '<div class="card" style="padding:14px"><div class="tiny" style="letter-spacing:1px;color:var(--dim2)">本关进度</div>' +
      '<div class="row between mt8"><span style="font-size:13px">' + lv.tag + " " + lv.name + '</span><b>' + levelDoneCount(lv) + "/" + lv.lessons.length + '</b></div>' +
      '<div class="mp-bar mt8"><i style="width:' + (levelDoneCount(lv) / lv.lessons.length * 100) + '%"></i></div></div>' +
      '</aside></div></div>';

    $("#view").innerHTML = html;
    activeWidgets = [];

    // 挂载组件
    $$("[data-widget]").forEach((host) => {
      const i = +host.dataset.widget;
      const b = lesson.blocks[i];
      const inst = W.mount(b.w, b.cfg, host, {
        setTask: (tid, ok) => setTask(lesson, tid, ok),
        toast,
        getName: () => S.name,
        setName: (n) => { S.name = n; save(); }
      });
      if (inst) activeWidgets.push(inst);
    });

    bindQuizzes(lesson);
    bindDemos(lesson);
    renderTasks(lesson);

    $("#btnReset").addEventListener("click", () => {
      S.tasks[id] = {};
      save();
      viewLesson(id);
    });

    if (done) {
      $("#taskHint").innerHTML = '<span style="color:var(--green)">✅ 本课已完成，可以随时复习</span>';
    }
    updateChrome();
  }

  function blockHTML(b, i) {
    switch (b.type) {
      case "p": return '<div class="block"><p class="b-p">' + b.html + '</p></div>';
      case "h": return '<div class="block"><div class="b-h">' + b.text + '</div></div>';
      case "tip": case "warn": case "note": case "ok":
        return '<div class="block"><div class="b-box ' + b.type + '">' + b.html + '</div></div>';
      case "quote": return '<div class="block"><div class="b-quote">' + b.html + '</div></div>';
      case "terms":
        return '<div class="block"><div class="terms">' + b.items.map((t) => '<div class="term"><b>' + t[0] + '</b><span>' + t[1] + '</span></div>').join("") + '</div></div>';
      case "demo": return demoHTML(b, i);
      case "widget":
        return '<div class="block"><div data-widget="' + i + '"></div>' + (b.cap ? '<div class="tiny mt8">' + b.cap + '</div>' : "") + '</div>';
      case "quiz": return quizHTML(b, i);
      default: return "";
    }
  }

  function demoHTML(b, i) {
    return '<div class="block"><div class="demo"><div class="demo-head"><div class="t"><span class="k">试听</span>' + b.title + '</div>' +
      '<span class="tiny">戴上耳机 🎧</span></div><div class="demo-body"><div class="demo-items">' +
      b.items.map((it, j) => '<button class="demo-btn" data-demo="' + it.demo + '" data-di="' + i + "-" + j + '">' +
        '<span class="play">▶</span><span style="flex:1"><span class="lbl">' + it.label + '</span>' +
        '<span class="sub">' + (it.sub || it.tag || "") + '</span></span>' +
        '<span class="eq" style="color:var(--orange2)"><i></i><i></i><i></i><i></i></span></button>').join("") +
      '</div>' + (b.foot ? '<div class="demo-note">' + b.foot + '</div>' : "") + '</div></div></div>';
  }

  function quizHTML(b, i) {
    return '<div class="block"><div class="quiz" data-quiz="' + i + '"><div class="quiz-head"><span>小测</span>' + b.q + '</div>' +
      '<div class="quiz-opts">' + b.options.map((o, j) => '<button class="quiz-opt" data-opt="' + j + '"><span class="k">' + "ABCD"[j] + '</span><span>' + o.text + '</span></button>').join("") + '</div>' +
      '<div class="quiz-explain">' + b.explain + '</div></div></div>';
  }

  function bindQuizzes(lesson) {
    $$("[data-quiz]").forEach((qz) => {
      const b = lesson.blocks[+qz.dataset.quiz];
      $$("[data-opt]", qz).forEach((btn) => {
        btn.addEventListener("click", () => {
          if (qz.dataset.answered) return;
          const j = +btn.dataset.opt;
          if (j === b.answer) {
            qz.dataset.answered = "1";
            btn.classList.add("correct");
            $(".quiz-explain", qz).classList.add("show");
            setTask(lesson, "quiz", true);
          } else {
            btn.classList.add("wrong");
            setTimeout(() => btn.classList.remove("wrong"), 700);
            $(".quiz-explain", qz).classList.add("show");
          }
        });
      });
    });
  }

  function bindDemos(lesson) {
    let cur = null;
    $$(".demo-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        AE.unlock();
        if (btn.classList.contains("on")) {
          W.stopAll();
          btn.classList.remove("on");
          btn.querySelector(".play").textContent = "▶";
          cur = null;
          return;
        }
        W.stopAll();
        $$(".demo-btn").forEach((x) => { x.classList.remove("on"); x.querySelector(".play").textContent = "▶"; });
        btn.classList.add("on");
        btn.querySelector(".play").textContent = "■";
        const p = (C.demos[btn.dataset.demo] || C.demos["l0-groove"])();
        const bars = W.totalBars(p);
        AE.Transport.start({
          bpm: p.bpm, steps: bars * 16,
          onStep: (s, t, bar) => W.scheduleStep(p, s, t, bar)
        });
        cur = btn;
        btn.dataset.timer = "";
        clearTimeout(btn._t);
        btn._t = setTimeout(() => {
          if (cur === btn) {
            btn.classList.remove("on");
            btn.querySelector(".play").textContent = "▶";
            W.stopAll();
          }
        }, bars * (60 / p.bpm) * 4 * 1000 + 500);
      });
    });
  }

  function setTask(lesson, id, ok) {
    if (!S.tasks[lesson.id]) S.tasks[lesson.id] = {};
    const before = !!S.tasks[lesson.id][id];
    S.tasks[lesson.id][id] = !!ok;
    save();
    if (before !== !!ok) renderTasks(lesson);
    checkComplete(lesson);
  }

  function renderTasks(lesson) {
    const st = S.tasks[lesson.id] || {};
    let n = 0;
    lesson.tasks.forEach((t) => {
      const li = $('[data-task="' + t.id + '"]');
      const ok = !!st[t.id];
      if (ok) n++;
      if (li) li.classList.toggle("ok", ok);
    });
    const cnt = $("#taskCnt");
    if (cnt) cnt.textContent = n + " / " + lesson.tasks.length;
    const prog = $("#lessonProg");
    if (prog) prog.style.width = (n / lesson.tasks.length * 100) + "%";
    if (n === lesson.tasks.length && $("#taskHint") && !S.done[lesson.id]) {
      $("#taskHint").innerHTML = '<span style="color:var(--green)">✅ 全部完成，正在记录…</span>';
    }
  }

  function checkComplete(lesson) {
    const st = S.tasks[lesson.id] || {};
    const all = lesson.tasks.every((t) => st[t.id]);
    if (!all) return;
    const first = !S.done[lesson.id];
    if (first) {
      S.done[lesson.id] = true;
      S.xp += lesson.xp;
      S.seen[lesson.id] = Date.now();
      save();
      updateChrome();
      toast("✅ 通关 · " + lesson.title + "　+" + lesson.xp + " XP", "good");
      setTimeout(() => showComplete(lesson), 500);
      if (lesson.kind === "exam") setTimeout(() => showLevelClear(lesson), 1000);
    }
    if ($("#taskHint")) $("#taskHint").innerHTML = '<span style="color:var(--green)">✅ 本课已完成</span>';
  }

  function showComplete(lesson) {
    const next = LESSONS[LESSONS.findIndex((l) => l.id === lesson.id) + 1];
    const el = $("#lessonEnd");
    if (!el) return;
    el.innerHTML = '<div class="card mt24" style="border-color:rgba(74,222,128,.35);background:linear-gradient(140deg,rgba(74,222,128,.08),var(--panel))">' +
      '<div class="row between wrap"><div><div class="h3">🎉 通关：' + lesson.title + '</div>' +
      '<div class="tiny mt8">+' + lesson.xp + ' XP　·　' + (rank() >= 6 ? "全部完成" : "继续下一课") + '</div></div>' +
      (next ? '<a class="btn primary" href="#/lesson/' + next.id + '">下一课：' + next.title + ' →</a>' : '<a class="btn primary" href="#/cert">领取证书 →</a>') +
      '</div></div>';
    if (el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function showLevelClear(lesson) {
    const lv = levelOf(lesson.level);
    const nextLv = C.levels[lv.id + 1];
    modal('<div class="modal-head"><h3>' + lv.icon + " " + lv.tag + ' 通关！</h3><button class="icon-btn" data-close="1">✕</button></div>' +
      '<div class="modal-body center"><div style="font-size:56px">' + lv.icon + '</div>' +
      '<div class="h2 mt8">' + lv.name + '</div>' +
      '<p class="muted" style="font-size:13px">你已经完成这一关的全部内容。</p>' +
      '<div class="row mt16" style="justify-content:center;gap:20px">' +
      '<div class="stat"><b>' + S.xp + '</b><span>总 XP</span></div>' +
      '<div class="stat"><b>' + doneCount() + '/' + TOTAL + '</b><span>课时</span></div></div></div>' +
      '<div class="modal-foot">' + (nextLv ? '<a class="btn primary" href="#/level/' + nextLv.id + '" data-close="1">进入 ' + nextLv.tag + " " + nextLv.name + ' →</a>' : '<a class="btn primary" href="#/cert" data-close="1">领取证书 →</a>') +
      '</div>');
  }

  /* ---------------- 工作台 ---------------- */
  const PRESETS = {
    melodic: {
      name: "Melodic EDM", desc: "Am–F–C–G · 琶音主音 · 大混响",
      p: () => C.pattern({
        bpm: 126, bars: 4,
        drums: {
          kick: { steps: [0, 4, 8, 12] }, snare: { steps: [4, 12] },
          clap: { on: true, steps: [4, 12], gain: 0.45 },
          hatc: { steps: [0, 4, 8, 12], gain: 0.28 }, hato: { steps: [2, 6, 10, 14], gain: 0.4 }
        },
        chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.6 },
        bass: { mode: "root8", gain: 0.9 },
        lead: { on: true, mode: "arp16", gain: 0.45 },
        gain: { drums: 1, bass: 1, chords: 0.7, lead: 0.8 }
      })
    },
    prog: {
      name: "Progressive House", desc: "四踩 · 滚动贝斯 · 慢展开",
      p: () => C.pattern({
        bpm: 124, bars: 4,
        drums: {
          kick: { steps: [0, 4, 8, 12] }, snare: { steps: [4, 12], gain: 0.6 },
          hatc: { steps: [0, 2, 4, 6, 8, 10, 12, 14], gain: 0.26 }, hato: { steps: [2, 6, 10, 14], gain: 0.36 },
          perc: { on: true, steps: [7, 15], gain: 0.28 }
        },
        chords: { list: ["Am", "F", "C", "G"], mode: "stab", gain: 0.5 },
        bass: { mode: "rolling", gain: 0.75 },
        lead: { on: true, mode: "arp8", gain: 0.35 },
        gain: { drums: 1, bass: 1, chords: 0.6, lead: 0.7 }
      })
    },
    future: {
      name: "Future Bass", desc: "半速鼓 · 宽和弦 · 留白",
      p: () => C.pattern({
        bpm: 150, bars: 4,
        drums: {
          kick: { steps: [0, 10] }, snare: { steps: [8], gain: 0.9 },
          clap: { on: true, steps: [8], gain: 0.6 },
          hatc: { steps: [0, 2, 4, 6, 8, 10, 12, 14], gain: 0.22 },
          perc: { on: true, steps: [6, 14], gain: 0.3 }
        },
        chords: { list: ["Cadd9", "Gsus4", "Am7", "Fmaj7"], mode: "pad", gain: 0.7 },
        bass: { mode: "root8", gain: 1 },
        lead: { on: true, mode: "stab", gain: 0.4 },
        gain: { drums: 1, bass: 1, chords: 0.8, lead: 0.7 }
      })
    },
    piano: {
      name: "Piano × Electronic", desc: "真钢琴 · 电子鼓 · 侧链",
      p: () => C.pattern({
        bpm: 100, bars: 4,
        drums: {
          kick: { steps: [0, 8], gain: 0.85 }, snare: { steps: [4, 12], gain: 0.6 },
          hatc: { steps: [2, 6, 10, 14], gain: 0.25 }
        },
        chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.35 },
        bass: { mode: "root8", gain: 0.75 },
        lead: { on: false, mode: "arp8", gain: 0.4 },
        gain: { drums: 1, bass: 0.9, chords: 0.5, lead: 0.6 }
      })
    }
  };

  function viewStudio(q) {
    const presetKey = q || S.studioPreset || "melodic";
    S.studioPreset = presetKey;
    const preset = PRESETS[presetKey] || PRESETS.melodic;
    const p = preset.p();
    const html = '<div class="page">' +
      '<div class="studio-head"><div><div class="kicker" style="color:var(--orange);font-size:11px;letter-spacing:2px;font-weight:700">PLAYGROUND</div>' +
      '<h1 class="h1">工作台</h1><p class="muted" style="margin:6px 0 0">这里是你的练习场：没有判定，随便改。做完可以存下来，去证书页看看自己的作品。</p></div>' +
      '<div class="row"><button class="btn sm" id="btnSaveWork">💾 保存作品</button><button class="btn sm" id="btnLoadWork">📂 我的作品</button></div></div>' +
      '<div class="preset-row">' + Object.keys(PRESETS).map((k) => '<button class="preset ' + (k === presetKey ? "on" : "") + '" data-preset="' + k + '">' + PRESETS[k].name +
        '<span class="tiny" style="display:block;font-size:10px;color:var(--dim2)">' + PRESETS[k].desc + '</span></button>').join("") + '</div>' +
      '<div id="studioLab"></div>' +
      '<div class="card mt24"><div class="h3">工作台小抄</div><div class="terms mt12">' +
      '<div class="term"><b>空格</b><span>播放 / 停止</span></div>' +
      '<div class="term"><b>点击格子</b><span>加入或移除一个音</span></div>' +
      '<div class="term"><b>点轨道名</b><span>静音 / 取消静音</span></div>' +
      '<div class="term"><b>双击轨道名</b><span>清空这条轨道</span></div>' +
      '<div class="term"><b>编排模式</b><span>自动分成 Intro/Build/Drop</span></div>' +
      '<div class="term"><b>BPM</b><span>70–180，改完自动重播</span></div>' +
      '</div></div></div>';

    $("#view").innerHTML = html;

    const cfg = {
      rows: ["kick", "snare", "clap", "hatc", "hato", "perc"],
      bpm: p.bpm, bars: 4, preset: p,
      chords: { editable: true, options: Object.keys(C.chords) },
      bass: { modes: [["none", "关闭"], ["root8", "根音 8 分"], ["offbeat", "反拍"], ["rolling", "滚动 16 分"]] },
      lead: { modes: [["none", "关闭"], ["arp8", "琶音 8 分"], ["arp16", "琶音 16 分"], ["stab", "和弦切音"]] },
      fx: true, arrangement: true,
      hint: "空格键播放/停止"
    };
    const host = $("#studioLab");
    const inst = W.mount("lab", cfg, host, {
      setTask: () => {}, toast, getName: () => S.name, setName: (n) => { S.name = n; save(); }
    });

    $$("[data-preset]").forEach((b) => {
      b.addEventListener("click", () => {
        W.stopAll();
        location.hash = "#/studio/" + b.dataset.preset;
      });
    });

    $("#btnSaveWork").addEventListener("click", () => {
      if (!inst) return;
      const st = inst.getState();
      S.works = S.works || [];
      S.works.unshift({ name: S.name || "无名作品", ts: Date.now(), pattern: JSON.parse(JSON.stringify(st)) });
      S.works = S.works.slice(0, 8);
      save();
      toast("已保存到「我的作品」", "good");
    });
    $("#btnLoadWork").addEventListener("click", () => {
      const works = S.works || [];
      if (!works.length) { toast("还没有保存过作品。"); return; }
      modal('<div class="modal-head"><h3>我的作品</h3><button class="icon-btn" data-close="1">✕</button></div>' +
        '<div class="modal-body">' + works.map((w, i) => '<div class="lesson-row" style="margin-bottom:8px" data-work="' + i + '">' +
          '<div class="lr-ico">🎵</div><div><h4>' + w.name + '</h4><p>' + fmtDate(w.ts) + " · " + (w.pattern.bpm || 126) + ' BPM</p></div>' +
          '<div class="lr-right"><span>载入 →</span></div></div>').join("") + '</div>' +
        '<div class="modal-foot"><button class="btn" data-close="1">关闭</button></div>');
      $$("[data-work]").forEach((el) => {
        el.addEventListener("click", () => {
          const w = works[+el.dataset.work];
          closeModal();
          W.stopAll();
          const cfg2 = Object.assign({}, cfg, { preset: w.pattern, bpm: w.pattern.bpm, bars: w.pattern.bars });
          W.mount("lab", cfg2, host, { setTask: () => {}, toast, getName: () => S.name, setName: (n) => { S.name = n; save(); } });
          toast("已载入：" + w.name, "good");
        });
      });
    });

    highlightNav();
  }

  /* ---------------- 钢琴房 ---------------- */
  function viewPiano() {
    const html = '<div class="page">' +
      '<div class="studio-head"><div><div class="kicker" style="color:var(--cyan);font-size:11px;letter-spacing:2px;font-weight:700">PIANO ROOM</div>' +
      '<h1 class="h1">钢琴房</h1><p class="muted" style="margin:6px 0 0">真实施坦威采样（FL Studio Mobile Essential Pianos）。弹吧，这里没有评分。</p></div>' +
      '<div class="row"><button class="btn sm" id="btnRec">● 录音</button><button class="btn sm" id="btnPlayRec" disabled>▶ 回放</button></div></div>' +
      '<div class="card mb16"><div class="row between wrap"><div><div class="h3">和弦速查</div>' +
      '<div class="tiny">点一个和弦，听它的声音，再看看是哪三个音</div></div>' +
      '<div class="tiny" id="chordInfo">—</div></div>' +
      '<div class="chips mt12" id="chordBtns">' + ["Am", "F", "C", "G", "Dm", "Em", "Cadd9", "Fmaj7", "Gsus4", "Am7"].map((c) => '<button class="chip" data-chord="' + c + '">' + c + '</button>').join("") + '</div></div>' +
      '<div id="pianoKb"></div>' +
      '<div class="grid mt24" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">' +
      '<div class="card"><div class="h3">四个万能进行</div><div class="tiny mb8">点一下，整段播放</div>' +
      ["Am,F,C,G", "C,G,Am,F", "Cadd9,Gsus4,Am7,Fmaj7", "Am7,Dm7,G,Cmaj7"].map((x) => '<button class="btn sm" style="margin:4px 4px 0 0" data-prog="' + x + '">' + x.replace(/,/g, " – ") + '</button>').join("") + '</div>' +
      '<div class="card"><div class="h3">电脑键盘</div><div class="tiny">把鼠标放到键盘上，然后用电脑键盘弹：</div>' +
      '<div class="terms mt8" style="grid-template-columns:1fr"><div class="term"><b>A W S E D F T G Y H U J K</b><span>白键 A S D F G H J K · 黑键 W E T Y U</span></div></div></div>' +
      '</div></div>';
    $("#view").innerHTML = html;

    W.mount("keyboard", {
      mode: "free", range: [48, 84], vel: 82,
      onNote: (m, v) => {
        if (recording) rec.push({ midi: m, t: AE.now(), vel: v });
      }
    }, $("#pianoKb"), { setTask: () => {}, toast });

    let recording = false;
    let rec = [];
    let recStart = 0;

    $("#btnRec").addEventListener("click", (e) => {
      if (!recording) {
        AE.unlock();
        recording = true; rec = []; recStart = AE.now();
        e.target.classList.add("done");
        e.target.textContent = "■ 停止";
        toast("开始录音，弹点什么吧");
      } else {
        recording = false;
        e.target.classList.remove("done");
        e.target.textContent = "● 录音";
        $("#btnPlayRec").disabled = rec.length === 0;
        toast("录下了 " + rec.length + " 个音", "good");
      }
    });
    $("#btnPlayRec").addEventListener("click", () => {
      if (!rec.length) return;
      AE.unlock();
      const t0 = AE.now() + 0.1;
      rec.forEach((n) => AE.piano(n.midi, t0 + (n.t - recStart), (n.vel || 80) / 127, 1.4));
    });

    $("#chordBtns").addEventListener("click", (e) => {
      const b = e.target.closest("[data-chord]");
      if (!b) return;
      const id = b.dataset.chord;
      const ch = C.chords[id];
      AE.unlock();
      ch.notes.forEach((m, i) => AE.piano(m, AE.now() + i * 0.015, 0.72, 1.8));
      $("#chordInfo").innerHTML = '<b style="color:var(--cyan)">' + id + '</b> · ' + ch.cn + ' · ' + ch.notes.map((m) => C.noteName(m)).join(" + ");
    });

    $$("[data-prog]").forEach((b) => {
      b.addEventListener("click", () => {
        AE.unlock();
        W.stopAll();
        const list = b.dataset.prog.split(",");
        const bpm = 72, beat = 60 / bpm;
        const t0 = AE.now() + 0.15;
        list.forEach((id, i) => {
          const ch = C.chords[id];
          const voice = C.voice[id] || ch.notes;
          voice.forEach((m) => AE.piano(m, t0 + i * beat * 2, 0.55, beat * 1.9));
          AE.pad(voice, t0 + i * beat * 2, beat * 1.9, 0.1);
        });
      });
    });

    highlightNav();
  }

  /* ---------------- 证书 ---------------- */
  function viewCert() {
    const done = doneCount();
    const complete = done >= TOTAL;
    const r = rank();
    const name = S.name || "（未签名）";
    const date = fmtDate(S.seen["l5-exam"] || Date.now());
    const html = '<div class="page cert-wrap"><div class="studio-head" style="width:100%"><div>' +
      '<div class="kicker" style="color:#ffd166;font-size:11px;letter-spacing:2px;font-weight:700">CERTIFICATE</div>' +
      '<h1 class="h1">毕业证书</h1><p class="muted" style="margin:6px 0 0">' +
      (complete ? "你已经走完整条路。打印它，贴在墙上。" : "完成全部 18 节课后解锁。目前完成 " + done + "/" + TOTAL + "。") + '</p></div>' +
      '<div class="row">' + (complete ? '<button class="btn primary" id="btnPrint">🖨 打印 / 存为 PDF</button>' : '<a class="btn" href="#/lesson/' + (nextLesson() ? nextLesson().id : "l0-edm") + '">继续学习 →</a>') + '</div></div>' +

      '<div class="cert ' + (complete ? "" : "cert-locked") + '">' +
      '<div class="brandline"><span>FLM ACADEMY</span><span>NO. ' + String(1000 + done * 37 + r * 11) + '</span></div>' +
      '<h2>结 业 证 书</h2><div class="sub">CERTIFICATE OF COMPLETION</div>' +
      '<div class="center"><div class="name">' + name + '</div></div>' +
      '<div class="body">兹证明该同学已完成《FLM 学院 · 从噪音到大师》全部课程，<br>' +
      '涵盖电子音乐制作（EDM）与钢琴演奏两条主线，<br>' +
      '从节拍、编曲、混音、母带到钢琴句法，共 6 个等级 · 18 节课。</div>' +
      '<div class="body" style="margin-top:2%">评定：' + (r >= 6 ? "大师 MASTER" : "学习中 IN PROGRESS") + '　·　总经验 ' + S.xp + ' XP</div>' +
      '<div class="sign"><b>FLM 学院</b>' + date + '</div>' +
      '<div class="seal">FLM<br>ACADEMY<br>' + new Date().getFullYear() + '</div>' +
      '</div>' +

      '<div class="card" style="width:100%;max-width:820px"><div class="h3">成绩单</div><div class="terms mt12">' +
      C.levels.map((lv) => '<div class="term"><b>' + lv.tag + " " + lv.name + '</b><span>' +
        levelDoneCount(lv) + "/" + lv.lessons.length + " 课 · " + (levelComplete(lv) ? "✅ 已通关" : "进行中") + '</span></div>').join("") +
      '</div></div></div>';

    $("#view").innerHTML = html;
    if (complete) $("#btnPrint").addEventListener("click", () => window.print());
    highlightNav();
  }

  /* ---------------- 新手引导 ---------------- */
  const TOUR = [
    { el: "#rankChip", title: "这是你的段位", text: "从 Lv.0 噪音制造者开始，每通一关就升一级。经验值会显示在旁边。" },
    { el: ".hero-actions", title: "从第一课开始", text: "不用自己找课。点这个按钮，系统永远带你去「下一节该学的」。", fallback: true },
    { el: ".path", title: "6 个等级 · 18 节课", text: "每一关都是「EDM 课 + 钢琴课 + 考核」。灰色的还没解锁，先过上一关。", fallback: true },
    { el: ".rail-nav a[data-nav=studio]", title: "工作台", text: "学完随时来玩：16 格音序器、贝斯、和弦、编排，全都能改。" },
    { el: ".rail-nav a[data-nav=piano]", title: "钢琴房", text: "真实施坦威采样。鼠标点，或用电脑键盘 A W S E D 弹。" }
  ];
  let ti = 0;

  function startTour(force) {
    if (!force && S.tour) return;
    ti = 0;
    $("#tour").classList.add("show");
    $("#tour").innerHTML = '<div class="tour-spot"></div><div class="tour-tip"></div>';
    drawTour();
  }
  function endTour() {
    $("#tour").classList.remove("show");
    $("#tour").innerHTML = "";
    S.tour = true;
    save();
  }
  function drawTour() {
    if (ti >= TOUR.length) { endTour(); return; }
    const step = TOUR[ti];
    let el = document.querySelector(step.el);
    if (!el || !el.offsetParent) { ti++; return drawTour(); }
    const r = el.getBoundingClientRect();
    const spot = $(".tour-spot"), tip = $(".tour-tip");
    spot.style.cssText = "left:" + (r.left - 8) + "px;top:" + (r.top - 8) + "px;width:" + (r.width + 16) + "px;height:" + (r.height + 16) + "px";
    const w = 300;
    let left, top;
    if (r.right + w + 30 < window.innerWidth) { left = r.right + 20; top = Math.max(16, Math.min(r.top, window.innerHeight - 220)); }
    else { left = Math.max(16, Math.min(r.left, window.innerWidth - w - 16)); top = r.bottom + 16; }
    if (top + 200 > window.innerHeight) top = Math.max(16, r.top - 190);
    tip.style.cssText = "left:" + left + "px;top:" + top + "px";
    tip.innerHTML = '<div class="num">STEP ' + (ti + 1) + " / " + TOUR.length + '</div><h4>' + step.title + '</h4><p>' + step.text + '</p>' +
      '<div class="acts"><button class="skip">跳过引导</button><div class="row" style="gap:6px">' +
      (ti > 0 ? '<button class="btn sm ghost" data-t="prev">上一步</button>' : "") +
      '<button class="btn sm primary" data-t="next">' + (ti === TOUR.length - 1 ? "开始学习" : "下一步") + '</button></div></div>';
    $(".skip", tip).onclick = endTour;
    const nb = $('[data-t="next"]', tip);
    if (nb) nb.onclick = () => { ti++; drawTour(); };
    const pb = $('[data-t="prev"]', tip);
    if (pb) pb.onclick = () => { ti--; drawTour(); };
  }

  /* ---------------- 设置 ---------------- */
  function openSettings() {
    modal('<div class="modal-head"><h3>设置</h3><button class="icon-btn" data-close="1">✕</button></div>' +
      '<div class="modal-body">' +
      '<div class="setting-row"><div class="lab"><b>总音量</b><span>影响所有声音</span></div>' +
      '<input type="range" id="setVol" min="0" max="100" value="' + Math.round((+localStorage.getItem("flm-vol") || 0.85) * 100) + '" style="width:120px"></div>' +
      '<div class="setting-row"><div class="lab"><b>解锁全部关卡</b><span>预览用，不影响成就</span></div>' +
      '<label class="switch"><input type="checkbox" id="setUnlock" ' + (S.unlockAll ? "checked" : "") + '><span class="track"></span></label></div>' +
      '<div class="setting-row"><div class="lab"><b>新手引导</b><span>重新看一遍界面介绍</span></div>' +
      '<button class="btn sm" id="setTour">重新播放</button></div>' +
      '<div class="setting-row"><div class="lab"><b>清空进度</b><span>所有课程、XP、成就都会重置</span></div>' +
      '<button class="btn sm" id="setReset" style="border-color:rgba(255,92,122,.4);color:#ffb3c1">清空</button></div>' +
      '<div class="setting-row"><div class="lab"><b>音频引擎</b><span id="audioState">' + (AE.ready ? "采样已加载" : "加载中…") + '</span></div>' +
      '<span class="pill">' + (AE.ready ? "READY" : "LOADING") + '</span></div>' +
      '</div><div class="modal-foot"><button class="btn primary" data-close="1">完成</button></div>');

    $("#setVol").addEventListener("input", (e) => {
      const v = +e.target.value / 100;
      localStorage.setItem("flm-vol", v);
      AE.setVolume(v);
      $("#volSlider").value = e.target.value;
    });
    $("#setUnlock").addEventListener("change", (e) => {
      S.unlockAll = e.target.checked;
      save(); updateChrome();
      toast(S.unlockAll ? "已解锁全部关卡（预览模式）" : "恢复按进度解锁");
      route();
    });
    $("#setTour").addEventListener("click", () => { closeModal(); location.hash = "#/home"; setTimeout(() => startTour(true), 300); });
    $("#setReset").addEventListener("click", () => {
      if (!confirm("确定清空所有学习进度？")) return;
      S = Object.assign({}, DEFAULT);
      save(); closeModal(); updateChrome();
      location.hash = "#/home"; route();
      toast("进度已清空");
    });
  }

  /* ---------------- 路由 ---------------- */
  function route() {
    W.stopAll();
    activeWidgets.forEach((w) => { try { w.destroy && w.destroy(); } catch (e) {} });
    activeWidgets = [];
    AE.setMasterDrive(0);
    AE.setLimiter(true);
    AE.setLowCut(20);

    const h = (location.hash || "#/home").replace(/^#\/?/, "");
    const parts = h.split("/");
    const page = parts[0] || "home";
    const arg = parts[1];

    if (page === "home") viewHome();
    else if (page === "level") viewLevel(+arg);
    else if (page === "lesson") viewLesson(arg);
    else if (page === "studio") viewStudio(arg);
    else if (page === "piano") viewPiano();
    else if (page === "cert") viewCert();
    else { location.hash = "#/home"; return; }

    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
    updateChrome();
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    // 音量
    const v = +(localStorage.getItem("flm-vol") || 0.85);
    $("#volSlider").value = Math.round(v * 100);
    AE.setVolume(v);
    $("#volSlider").addEventListener("input", (e) => {
      const val = +e.target.value / 100;
      localStorage.setItem("flm-vol", val);
      AE.setVolume(val);
      $("#btnMute").textContent = val === 0 ? "🔇" : "🔊";
    });
    $("#btnMute").addEventListener("click", () => {
      const cur = +$("#volSlider").value;
      if (cur > 0) {
        $("#volSlider").dataset.prev = cur;
        $("#volSlider").value = 0;
        AE.setVolume(0);
        $("#btnMute").textContent = "🔇";
      } else {
        const p = +($("#volSlider").dataset.prev || 85);
        $("#volSlider").value = p;
        AE.setVolume(p / 100);
        $("#btnMute").textContent = "🔊";
      }
    });

    $("#btnSettings").addEventListener("click", openSettings);
    $("#btnHelp").addEventListener("click", () => { location.hash = "#/home"; setTimeout(() => startTour(true), 250); });
    $("#btnMenu").addEventListener("click", () => {
      $("#rail").classList.toggle("open");
      $("#railScrim").classList.toggle("show");
    });
    $("#railScrim").addEventListener("click", closeRail);

    window.addEventListener("hashchange", () => { closeRail(); route(); });
    document.addEventListener("keydown", (e) => {
      if (e.code === "Space" && location.hash.indexOf("studio") >= 0) {
        if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
        e.preventDefault();
        const btn = $(".play-btn");
        if (btn) btn.click();
      }
      if (e.key === "Escape") { closeModal(); endTour(); }
    });

    // 先把界面渲染出来（不等音频）
    if (!location.hash) location.hash = "#/home";
    route();

    // 启动遮罩
    const splash = $("#splash");
    const fill = $("#splashFill");
    const pctEl = $("#splashPct");
    let splashDone = false;
    function hideSplash() {
      if (splashDone || !splash) return;
      splashDone = true;
      splash.classList.add("hide");
      setTimeout(() => { if (splash.parentNode) splash.parentNode.removeChild(splash); }, 480);
      if (!S.tour) setTimeout(() => startTour(false), 700);
    }

    // 后台加载采样；遮罩最多挡 4 秒，之后照样能用（音频继续加载）
    function whenSamples(cb) {
      if (window.__SAMPLES__) return cb();
      setTimeout(() => whenSamples(cb), 40);
    }
    whenSamples(() => AE.load((p) => {
      const n = Math.round(p * 100);
      if (fill) fill.style.width = n + "%";
      if (pctEl) pctEl.textContent = n + "%";
      const el = $("#audioState");
      if (el) el.textContent = "加载中 " + n + "%";
    })).then(() => {
      const el = $("#audioState");
      if (el) el.textContent = "采样已加载（FL Studio Mobile 音色库）";
      hideSplash();
    }).catch((e) => {
      console.warn(e);
      hideSplash();
      toast("音频加载失败，请刷新重试", "bad");
    });
    setTimeout(hideSplash, 2500);

    // 兜底：DOM 都就绪了还黑着，就直接撤遮罩
    setTimeout(() => { if (document.getElementById("view").children.length) hideSplash(); }, 900);
    // 调试/测试入口
    window.__FLM = {
      state: () => S,
      unlock: () => { S.unlockAll = true; save(); updateChrome(); route(); },
      go: (h) => { location.hash = h; },
      completeTask: (lid, tid) => { const l = C.getLesson(lid); if (l) setTask(l, tid, true); }
    };
    window.addEventListener("resize", () => { if ($("#tour").classList.contains("show")) drawTour(); });
  }

  // 脚本位于 body 末尾，DOM 已就绪 → 立刻渲染界面，
  // 这样即使后面还有大段音频数据要解析，用户也不会看到空白屏。
  if (document.readyState === "loading") {
    if (document.getElementById("view")) boot();
    else document.addEventListener("DOMContentLoaded", boot);
  } else boot();
})();
