/* ===========================================================
   FLM 学院 · 课程内容 + 乐理数据
   =========================================================== */
(function () {
  "use strict";

  /* ---------------- 乐理 ---------------- */
  const QUAL = {
    maj: [0, 4, 7],
    min: [0, 3, 7],
    maj7: [0, 4, 7, 11],
    min7: [0, 3, 7, 10],
    sus4: [0, 5, 7],
    sus2: [0, 2, 7],
    add9: [0, 4, 7, 14]
  };

  const CHORDS = {
    Am: { root: 57, q: "min", bass: 33, cn: "A 小三和弦", notes: [57, 60, 64] },
    F: { root: 53, q: "maj", bass: 29, cn: "F 大三和弦", notes: [53, 57, 60] },
    C: { root: 48, q: "maj", bass: 36, cn: "C 大三和弦", notes: [48, 52, 55] },
    G: { root: 55, q: "maj", bass: 31, cn: "G 大三和弦", notes: [55, 59, 62] },
    Dm: { root: 50, q: "min", bass: 38, cn: "D 小三和弦", notes: [50, 53, 57] },
    Em: { root: 52, q: "min", bass: 40, cn: "E 小三和弦", notes: [52, 55, 59] },
    E: { root: 52, q: "maj", bass: 28, cn: "E 大三和弦", notes: [52, 56, 59] },
    D: { root: 50, q: "maj", bass: 38, cn: "D 大三和弦", notes: [50, 54, 57] },
    Bm: { root: 59, q: "min", bass: 35, cn: "B 小三和弦", notes: [59, 62, 66] },
    Cadd9: { root: 48, q: "add9", bass: 36, cn: "C 加九和弦", notes: [48, 52, 55, 62] },
    Fmaj7: { root: 53, q: "maj7", bass: 29, cn: "F 大七和弦", notes: [53, 57, 60, 64] },
    Gsus4: { root: 55, q: "sus4", bass: 31, cn: "G 挂四和弦", notes: [55, 60, 62] },
    Am7: { root: 57, q: "min7", bass: 33, cn: "A 小七和弦", notes: [57, 60, 64, 67] }
  };

  // 平滑声部连接用的四声部排列（pad 用）
  const VOICE = {
    Am: [57, 60, 64, 69],
    F: [57, 60, 65, 69],
    C: [55, 60, 64, 67],
    G: [55, 59, 62, 67],
    Dm: [57, 62, 65, 69],
    Em: [55, 59, 64, 67],
    Cadd9: [55, 60, 62, 64],
    Fmaj7: [57, 60, 64, 65],
    Gsus4: [55, 60, 62, 67],
    Am7: [55, 60, 64, 67]
  };

  const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const noteName = (m) => NOTE_NAMES[m % 12] + (Math.floor(m / 12) - 1);

  const DRUM_ROWS = [
    { id: "kick", label: "底鼓", en: "Kick", sample: "kick1", key: "K" },
    { id: "snare", label: "军鼓", en: "Snare", sample: "snare1", key: "S" },
    { id: "clap", label: "拍手", en: "Clap", sample: "clap1", key: "C" },
    { id: "hatc", label: "闭镲", en: "Closed Hat", sample: "hatc1", key: "H" },
    { id: "hato", label: "开镲", en: "Open Hat", sample: "hato1", key: "O" },
    { id: "perc", label: "打击", en: "Perc", sample: "perc1", key: "P" },
    { id: "ride", label: "叮叮镲", en: "Ride", sample: "ride1", key: "R" },
    { id: "crash", label: "强音镲", en: "Crash", sample: "crash1", key: "X" }
  ];

  /* ---------------- Pattern ---------------- */
  function pattern(o) {
    const base = {
      bpm: 128, swing: 0, bars: 4,
      drums: {
        kick: { on: true, steps: [], gain: 0.95, sample: "kick1" },
        snare: { on: true, steps: [], gain: 0.85, sample: "snare1" },
        clap: { on: false, steps: [], gain: 0.7, sample: "clap1" },
        hatc: { on: true, steps: [], gain: 0.45, sample: "hatc1" },
        hato: { on: false, steps: [], gain: 0.5, sample: "hato1" },
        perc: { on: false, steps: [], gain: 0.6, sample: "perc1" },
        ride: { on: false, steps: [], gain: 0.35, sample: "ride1" },
        crash: { on: false, steps: [], gain: 0.45, sample: "crash1" }
      },
      chords: { on: true, list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.75, octave: 0, chaos: false },
      bass: { on: true, mode: "root8", gain: 0.9, chaos: false },
      lead: { on: false, mode: "arp8", gain: 0.6, chaos: false },
      fx: { riser: false, impact: false },
      gain: { drums: 1, bass: 1, chords: 1, lead: 1 },
      sidechain: true,
      arrangement: null
    };
    const out = Object.assign({}, base, o || {});
    out.drums = Object.assign({}, base.drums);
    if (o && o.drums) Object.keys(o.drums).forEach((k) => { out.drums[k] = Object.assign({}, base.drums[k], o.drums[k]); });
    out.chords = Object.assign({}, base.chords, (o && o.chords) || {});
    out.bass = Object.assign({}, base.bass, (o && o.bass) || {});
    out.lead = Object.assign({}, base.lead, (o && o.lead) || {});
    out.fx = Object.assign({}, base.fx, (o && o.fx) || {});
    out.gain = Object.assign({}, base.gain, (o && o.gain) || {});
    return out;
  }

  const range = (a, b, step) => { const r = []; for (let i = a; i < b; i += (step || 1)) r.push(i); return r; };
  const even = range(0, 16, 2);
  const offbeat = [2, 6, 10, 14];
  const quarters = [0, 4, 8, 12];

  function chaos() {
    const p = pattern({ bpm: 128 });
    const rnd = (n) => { const a = []; for (let i = 0; i < n; i++) a.push(Math.floor(Math.random() * 16)); return a; };
    p.drums.kick.steps = rnd(7);
    p.drums.snare.steps = rnd(6);
    p.drums.hatc.steps = rnd(12);
    p.drums.perc.on = true; p.drums.perc.steps = rnd(5);
    p.drums.clap.on = true; p.drums.clap.steps = rnd(4);
    p.chords.chaos = true;
    p.bass.chaos = true;
    p.lead.on = true; p.lead.chaos = true;
    p.sidechain = false;
    return p;
  }

  const DEMOS = {
    chaos: () => chaos(),

    "l0-groove": () => pattern({
      drums: {
        kick: { steps: [0, 8] }, snare: { steps: [4, 12] },
        hatc: { steps: even, gain: 0.3 }
      },
      chords: { list: ["Am", "F", "C", "G"], gain: 0.55 },
      bass: { mode: "root8", gain: 0.8 }
    }),

    "l1-kick": () => pattern({
      drums: { kick: { steps: [0, 8] } },
      chords: { on: false }, bass: { on: false }
    }),

    "l1-kicksnare": () => pattern({
      drums: { kick: { steps: [0, 8] }, snare: { steps: [4, 12] } },
      chords: { on: false }, bass: { on: false }
    }),

    "l1-full": () => pattern({
      drums: {
        kick: { steps: [0, 8] }, snare: { steps: [4, 12] },
        hatc: { steps: even, gain: 0.32 }
      },
      chords: { on: false }, bass: { on: false }
    }),

    "l2-straight": () => pattern({
      drums: {
        kick: { steps: quarters }, snare: { steps: [4, 12] },
        hatc: { steps: even, gain: 0.42 }
      },
      chords: { on: false }, bass: { on: false }
    }),

    "l2-offbeat": () => pattern({
      drums: {
        kick: { steps: quarters }, snare: { steps: [4, 12] },
        hatc: { steps: quarters, gain: 0.35 },
        hato: { steps: offbeat, gain: 0.5 }
      },
      chords: { on: false }, bass: { on: false }
    }),

    "l2-loop": () => pattern({
      drums: {
        kick: { steps: [0, 8] }, snare: { steps: [4, 12] },
        hatc: { steps: quarters, gain: 0.35 }, hato: { steps: offbeat, gain: 0.5 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.55 },
      bass: { mode: "root8", gain: 0.85 }
    }),

    "l3-loop": () => pattern({
      bpm: 126, bars: 4,
      drums: {
        kick: { steps: quarters }, snare: { steps: [4, 12] },
        clap: { on: true, steps: [4, 12], gain: 0.5 },
        hatc: { steps: quarters, gain: 0.3 }, hato: { steps: offbeat, gain: 0.42 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.6 },
      bass: { mode: "root8", gain: 0.9 },
      lead: { on: true, mode: "arp16", gain: 0.45 }
    }),

    "l3-build": () => pattern({
      bpm: 126, bars: 8,
      drums: {
        kick: { steps: quarters }, snare: { steps: [4, 12] },
        hatc: { steps: quarters, gain: 0.3 }, hato: { steps: offbeat, gain: 0.42 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.6 },
      bass: { mode: "root8", gain: 0.9 },
      lead: { on: true, mode: "arp16", gain: 0.45 },
      arrangement: [
        { type: "intro", bars: 2 }, { type: "build", bars: 2 },
        { type: "drop", bars: 4 }
      ]
    }),

    "l4-bad": () => pattern({
      bpm: 126,
      drums: {
        kick: { steps: quarters, gain: 0.7 }, snare: { steps: [4, 12], gain: 0.5 },
        hatc: { steps: quarters, gain: 0.25 }, hato: { steps: offbeat, gain: 0.3 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 1.5 },
      bass: { mode: "root8", gain: 1.25 },
      lead: { on: true, mode: "arp16", gain: 0.3 },
      gain: { drums: 0.7, bass: 1.35, chords: 1.45, lead: 0.6 },
      sidechain: false
    }),

    "l4-good": () => pattern({
      bpm: 126,
      drums: {
        kick: { steps: quarters, gain: 1 }, snare: { steps: [4, 12], gain: 0.85 },
        hatc: { steps: quarters, gain: 0.3 }, hato: { steps: offbeat, gain: 0.42 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.5 },
      bass: { mode: "root8", gain: 0.9 },
      lead: { on: true, mode: "arp16", gain: 0.6 },
      gain: { drums: 1, bass: 1, chords: 0.6, lead: 0.95 },
      sidechain: true
    }),

    "l5-full": () => pattern({
      bpm: 126, bars: 16,
      drums: {
        kick: { steps: quarters }, snare: { steps: [4, 12] },
        clap: { on: true, steps: [4, 12], gain: 0.55 },
        hatc: { steps: quarters, gain: 0.32 }, hato: { steps: offbeat, gain: 0.45 },
        perc: { on: true, steps: [3, 7, 11, 15], gain: 0.35 }
      },
      chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.55 },
      bass: { mode: "root8", gain: 0.95 },
      lead: { on: true, mode: "arp16", gain: 0.5 },
      gain: { drums: 1, bass: 1, chords: 0.65, lead: 0.85 },
      arrangement: [
        { type: "intro", bars: 4 }, { type: "build", bars: 4 },
        { type: "drop", bars: 8 }, { type: "break", bars: 4 },
        { type: "build", bars: 4 }, { type: "drop", bars: 8 }, { type: "outro", bars: 4 }
      ]
    })
  };

  /* ---------------- 课程 ---------------- */
  const Q = (q, options, answer, explain) => ({ type: "quiz", q, options, answer, explain });
  const p = (html) => ({ type: "p", html });
  const h = (text) => ({ type: "h", text });
  const tip = (html) => ({ type: "tip", html });
  const warn = (html) => ({ type: "warn", html });
  const note = (html) => ({ type: "note", html });
  const ok = (html) => ({ type: "ok", html });
  const demo = (title, items, foot) => ({ type: "demo", title, items, foot });
  const widget = (w, cfg, cap) => ({ type: "widget", w, cfg, cap });
  const terms = (items) => ({ type: "terms", items });

  const LEVELS = [
    /* ================= Lv.0 ================= */
    {
      id: 0, tag: "Lv.0", name: "噪音制造者", en: "NOISE MAKER", color: "#8c96ac", icon: "🎧",
      desc: "你刚打开软件，做出来的东西自己都不想听第二遍。没关系——这一关只解决一件事：听懂「拍子」。",
      lessons: [
        {
          id: "l0-edm", track: "edm", kind: "lesson", xp: 80, time: "6 分钟",
          title: "为什么你的作品听起来像噪音",
          sub: "3 个新手通病 + 你的第一次跟拍",
          lead: "几乎所有人在 FL Studio 里的第一首歌，都是「所有音色一起响」。这不是你笨，是没人告诉你音乐的第一性原理：声音要在时间上排整齐。",
          tasks: [
            { id: "tap", label: "跟拍 8 拍，拿到 60 分以上" },
            { id: "quiz", label: "答对：哪一段才是 4/4 循环" }
          ],
          blocks: [
            note("本课你会得到：① 能听出「有拍子」和「没拍子」的区别 ② 身体能跟上 120 BPM ③ 第一次明白 4/4 是什么意思。"),
            h("先听：新手第一天 vs 同一套音色的正确打开方式"),
            p("下面两段用的是<strong>完全一样的音色</strong>——同一个底鼓、同一个军鼓、同一把合成器。区别只有一件事：<b>声音出现的位置</b>。先听第一段，再听第二段。"),
            demo("A/B 对比 · 同一套音色，两种命运", [
              { label: "新手第一天", sub: "随机乱点 · 全部堆在一起", demo: "chaos", tag: "BAD" },
              { label: "四条轨道的循环", sub: "底鼓、军鼓、镲、贝斯各就各位", demo: "l0-groove", tag: "GOOD" }
            ], "听的时候不要只听「好不好听」，听：底鼓是不是每隔一样的时间响一次？"),
            p("第一段不是「音色差」，而是<b>时间上失控</b>：底鼓没有规律、贝斯乱走、所有东西同时挤在一起。第二段之所以像音乐，是因为每个声音都在一个固定的格子里。"),
            h("4/4 拍：把时间切成格子"),
            p("绝大多数电子音乐和流行歌都是 <b>4/4 拍</b>：每小节 4 拍，数出来是 <b>1 · 2 · 3 · 4</b>。每一拍再切成 4 份，就是 <b>16 分音符</b>——也就是 FL Studio 里那 <b>16 个格子</b>。"),
            tip("一小节 = 4 拍 = 16 格。第 1 拍在格子 1，第 2 拍在格子 5，第 3 拍在格子 9，第 4 拍在格子 13。这个换算你以后每天都会用到。"),
            terms([
              ["BPM", "每分钟多少拍。128 BPM 是 EDM 最常用的速度。"],
              ["4/4 拍", "每小节四拍，流行/电子乐的默认设置。"],
              ["16 分音符", "把一拍切成 4 份，一小节共 16 个格子。"],
              ["小节 Bar", "一次 1-2-3-4 循环，就是一个「格子框」，也是编排的最小单位。"]
            ]),
            h("动手：跟上拍子"),
            p("戴上耳机（或用外放），点下面的方块，跟着「咚·哒·咚·哒」每拍点一下。先别管准不准，先让身体记住 128 BPM 的速度。"),
            widget("tap", { threshold: 60, beats: 8, bpm: 128 }),
            tip("如果手忙脚乱，先听 4 拍再开始点。专业制作人不是手快，是「提前」——在拍子到之前就准备按下去了。"),
            h("检查一下你真的听懂了吗"),
            Q("下面哪一段才是真正的 4/4 循环？", [
              { text: "第一段：底鼓、军鼓、贝斯各在不同的时间出现，有规律地重复" },
              { text: "第二段：所有乐器同时响，音量很大" },
              { text: "哪段音色更贵，哪段就是 4/4" }
            ], 0, "4/4 的关键不是音量、不是音色，而是「规律」。每 4 拍一个循环，循环里每个声音都有自己的位置。"),
            warn("新手最容易犯的错：一上来就加 10 个音色。先用 4 个轨道把 4 小节做顺，再加东西。限制，是新手最好的老师。")
          ]
        },
        {
          id: "l0-piano", track: "piano", kind: "lesson", xp: 80, time: "7 分钟",
          title: "键盘第一课：找到中央 C",
          sub: "黑白键规律、手指编号、第一次弹出 C-D-E",
          lead: "钢琴有 88 个键，但你只需要先认识 1 个音：中央 C。找到它，整张键盘就都有了坐标。",
          tasks: [
            { id: "findc", label: "在键盘上找出 3 个 C" },
            { id: "cde", label: "用 3 指依次弹出 C-D-E" }
          ],
          blocks: [
            note("本课你会得到：① 一眼认出任意一个 C ② 知道 1-5 指怎么编号 ③ 用正确的手指弹出人生第一个三音动机。"),
            h("黑键的密码：2 个一组、3 个一组"),
            p("看键盘上的黑键：它们不是均匀排列的，而是 <b>2 个一组、3 个一组</b>交替出现。这个规律就是你的地图：<b>两个黑键左边紧挨着的白键，永远是 C</b>。"),
            p("继续数：C 右边的白键是 D、E、F、G、A、B，然后又回到 C。所以钢琴其实是「C-D-E-F-G-A-B」这 7 个名字，不停地循环。"),
            tip("两个黑键 = C 的定位器。三个黑键左边的白键是 F（记住「F 左边有 3 个黑键」）。你现在只需要 C。"),
            h("中央 C 在哪里？"),
            p("钢琴中间的 C 叫 <b>中央 C（C4）</b>，MIDI 编号 <b>60</b>。它是所有教材的第一课，也是你右手最舒服的位置。"),
            widget("keyboard", {
              mode: "findC", count: 3, range: [48, 84],
              task: "findc", hint: "点亮 3 个不同的 C（C3、C4、C5 都可以）"
            }),
            h("手指编号：1 到 5"),
            p("弹琴不用「食指中指」这种叫法，用编号：<b>1 = 拇指，2 = 食指，3 = 中指，4 = 无名指，5 = 小指</b>。右手和左手都是这样数。"),
            terms([
              ["1 指", "拇指。弹 C 时最自然。"],
              ["3 指", "中指。最长、最有力量，常用来弹旋律的中心音。"],
              ["5 指", "小指。力量最弱，需要特意「立起来」。"],
              ["手型", "像握着一个苹果：手指弯曲、指尖触键、手腕放松不塌。"]
            ]),
            h("动手：C-D-E"),
            p("现在把右手 1、2、3 指分别放在 C、D、E 上。跟着下面的提示，依次按下 <b>C → D → E</b>。不用管速度，先让每个音都干净、不碰到旁边的键。"),
            widget("keyboard", {
              mode: "sequence", notes: [60, 62, 64], bpm: 70, tolerance: 420,
              task: "cde", fingers: [1, 2, 3], guide: true, hint: "1 指 C → 2 指 D → 3 指 E"
            }),
            ok("当你按下 C-D-E 的时候，你已经在「作曲」了：这是最小的旋律动机。后面所有复杂的曲子，都是这样的三个音长大后的样子。"),
            Q("「中央 C」是哪两个黑键左边的白键？", [
              { text: "两个黑键的左边" },
              { text: "三个黑键的左边" },
              { text: "随便哪个白键都可以" }
            ], 0, "两个黑键左边的白键是 C；三个黑键左边的白键是 F。这是最快的定位方法。")
          ]
        },
        {
          id: "l0-exam", track: "exam", kind: "exam", xp: 120, time: "4 分钟",
          title: "通关考核 · 节奏门",
          sub: "证明你已经有拍感、也认识键盘了",
          lead: "这一关不考操作，只考两件事：身体能不能跟上拍子，眼睛能不能认出 C。两样都过，才进入 Lv.1。",
          tasks: [
            { id: "tap", label: "跟拍 8 拍，70 分以上" },
            { id: "findc", label: "找出指定的 2 个 C" },
            { id: "quiz", label: "答对：16 格里第 3 拍在第几格" }
          ],
          blocks: [
            p("放松，先听 4 拍再开始。跟拍不需要「打得响」，只需要「打得准」。"),
            widget("tap", { threshold: 70, beats: 8, bpm: 128 }),
            p("接下来是键盘：请点亮 <b>C4（中央 C）</b> 和 <b>C5</b>。点错会提示你往哪边走。"),
            widget("keyboard", { mode: "findC", count: 2, targets: [60, 72], range: [48, 84], task: "findc" }),
            Q("一小节 16 个格子里，第 3 拍在第几格？", [
              { text: "第 5 格" }, { text: "第 9 格" }, { text: "第 13 格" }, { text: "第 3 格" }
            ], 1, "第 1 拍在第 1 格，之后每隔 4 格一拍：1、5、9、13。所以第 3 拍是第 9 格。"),
            ok("Lv.0 通关。你已经比 90% 刚打开软件的人强了——因为你知道「先有拍子，再有音乐」。")
          ]
        }
      ]
    },

    /* ================= Lv.1 ================= */
    {
      id: 1, tag: "Lv.1", name: "节拍学徒", en: "BEAT APPRENTICE", color: "#3ee0ff", icon: "🥁",
      desc: "你开始能做出「像歌」的东西了。这一关把底鼓、军鼓、镲片排成一条能让人点头的鼓组。",
      lessons: [
        {
          id: "l1-edm", track: "edm", kind: "lesson", xp: 80, time: "8 分钟",
          title: "底鼓与军鼓：搭起第一根骨架",
          sub: "1、3 拍底鼓，2、4 拍军鼓——最万能的鼓组公式",
          lead: "如果把一首 EDM 比作一个人，底鼓是心跳，军鼓是呼吸。先把这两样放对位置，你的循环就活了。",
          tasks: [
            { id: "kick13", label: "底鼓放在第 1、3 拍（第 1、9 格）" },
            { id: "snare24", label: "军鼓放在第 2、4 拍（第 5、13 格）" }
          ],
          blocks: [
            note("本课你会得到：① 底鼓/军鼓的分工 ② 在 16 格网格上准确落点 ③ 一个能循环听的 4 小节鼓组。"),
            h("先听：骨架是一层一层长出来的"),
            demo("逐层叠加 · 听骨架怎么成型", [
              { label: "只有底鼓", sub: "1、3 拍，像心跳", demo: "l1-kick" },
              { label: "加军鼓", sub: "2、4 拍，像回答", demo: "l1-kicksnare" },
              { label: "加 8 分闭镲", sub: "把空隙填满，律动出现", demo: "l1-full" }
            ], "注意：每一层都没有改变前面的东西，只是「加」上去。这就是编曲。"),
            p("底鼓在 <b>第 1 拍和第 3 拍</b>，军鼓在 <b>第 2 拍和第 4 拍</b>——这个「咚 · 哒 · 咚 · 哒」是流行音乐一百年没变过的骨架。换成 16 格：底鼓在 <code>1、9</code>，军鼓在 <code>5、13</code>。"),
            h("动手：把两个鼓放对位置"),
            p("点亮下面的格子。点击已经亮的格子可以取消。先只放底鼓，播放听一遍，再放军鼓。"),
            widget("lab", {
              rows: ["kick", "snare"], bpm: 128, bars: 4, preset: "empty",
              goals: [
                { id: "kick13", label: "底鼓 = 第 1、9 格", test: (pt) => eq(pt.drums.kick.steps, [0, 8]) },
                { id: "snare24", label: "军鼓 = 第 5、13 格", test: (pt) => eq(pt.drums.snare.steps, [4, 12]) }
              ],
              hint: "先点第 1 格和第 9 格放底鼓；再点第 5 格和第 13 格放军鼓。"
            }),
            tip("不确定位置？看格子上面那行小字：<b>1 e &amp; a · 2 e &amp; a</b>。数字是拍，e/&amp;/a 是每拍里的四份。底鼓在「1」和「3」，军鼓在「2」和「4」。"),
            h("为什么不是底鼓 4 拍全放？"),
            p("可以放。这叫 <b>Four on the Floor（四踩）</b>，House / Techno / Trance 全都这么干，第 3 关你就会用到。但先学会「1、3」的呼吸感，你才知道四踩是在加强什么。"),
            Q("军鼓落在第 2 拍和第 4 拍，是为了什么？", [
              { text: "填满低频" },
              { text: "和底鼓形成「呼叫—回应」，让人能数清小节" },
              { text: "让音量更大" }
            ], 1, "底鼓给重拍，军鼓给「回答」。一呼一应，耳朵才能确认「一小节结束了」。"),
            warn("如果军鼓和底鼓同时落在第 1 拍，鼓组会变得很笨重。除非你明确要「大鼓点」，否则让它们错开。")
          ]
        },
        {
          id: "l1-piano", track: "piano", kind: "lesson", xp: 80, time: "8 分钟",
          title: "五个音，一只右手",
          sub: "C 大调五指位 + 你的第一条完整旋律",
          lead: "不用学和弦，先把右手五个手指管好。C-D-E-F-G 这五个音，能弹出无数条你听过的旋律。",
          tasks: [
            { id: "scale", label: "跟节拍弹完 C-D-E-F-G-F-E-D-C，70 分以上" }
          ],
          blocks: [
            note("本课你会得到：① C 大调五指位 ② 1-5 指的落键顺序 ③ 一条能反复练习的上下行音阶。"),
            h("先听：五指位长什么样"),
            p("把右手 1、2、3、4、5 指分别放在 <b>C、D、E、F、G</b> 五个白键上。这五个音都属于 C 大调，所以随便按都不会「难听」——这是新手最安全的自留地。"),
            widget("keyboard", {
              mode: "free", range: [60, 67], highlight: [60, 62, 64, 65, 67],
              hint: "高亮的 5 个键就是 C 大调五指位"
            }),
            h("手指要立起来"),
            p("很多人弹琴像在「拍键盘」。正确的手型是：手指弯曲、<b>指尖</b>触键、手腕略高于琴键、肩膀放松。声音会更干净，速度也上得去。"),
            tip("一个检查方法：把手背放在桌上，手指自然弯曲成拱形——这就是弹琴的手型。手腕不要塌下去。"),
            h("动手：上下行音阶"),
            p("跟着节拍器，用 <b>1-2-3-4-5-4-3-2-1</b> 指依次弹 <b>C-D-E-F-G-F-E-D-C</b>。速度 70 BPM，每拍一个音。弹错音会标红，但可以继续。"),
            widget("keyboard", {
              mode: "sequence", notes: [60, 62, 64, 65, 67, 65, 64, 62, 60], bpm: 70, tolerance: 420,
              task: "scale", fingers: [1, 2, 3, 4, 5, 4, 3, 2, 1], guide: true,
              hint: "1 指 C · 2 指 D · 3 指 E · 4 指 F · 5 指 G，再原路回来"
            }),
            p("如果你觉得 4 指（无名指）特别不听使唤——恭喜，所有人都是。4 指和 5 指共用一条肌腱，天生不灵活，只能靠慢练。"),
            Q("C 大调五指位是哪五个音？", [
              { text: "C D E F G" }, { text: "C D E F G A" }, { text: "C E G B D" }
            ], 0, "五指位就是五个手指各自负责一个音：C D E F G。第六个音开始就要换把位了，那是下一关的事。"),
            ok("你已经能弹出完整的上下行了。把它当热身，每次打开键盘先弹两遍。")
          ]
        },
        {
          id: "l1-exam", track: "exam", kind: "exam", xp: 120, time: "6 分钟",
          title: "通关考核 · 第一个鼓循环",
          sub: "底鼓、军鼓、8 分闭镲，一个都不能少",
          lead: "这次没有提示格子，自己排。三个轨道都正确，你就是个合格的节拍学徒了。",
          tasks: [
            { id: "kick13", label: "底鼓在第 1、9 格" },
            { id: "snare24", label: "军鼓在第 5、13 格" },
            { id: "hat8", label: "闭镲铺满 8 分音符（每 2 格一个）" }
          ],
          blocks: [
            p("要求：底鼓 1、3 拍；军鼓 2、4 拍；闭镲每 2 格一个（8 分音符）。播放 4 小节，听起来应该像一首歌的开头。"),
            widget("lab", {
              rows: ["kick", "snare", "hatc"], bpm: 128, bars: 4, preset: "empty",
              goals: [
                { id: "kick13", label: "底鼓 = 第 1、9 格", test: (pt) => eq(pt.drums.kick.steps, [0, 8]) },
                { id: "snare24", label: "军鼓 = 第 5、13 格", test: (pt) => eq(pt.drums.snare.steps, [4, 12]) },
                { id: "hat8", label: "闭镲 = 每 2 格一个", test: (pt) => eq(pt.drums.hatc.steps, even) }
              ],
              hint: "闭镲一共 8 个：1、3、5、7、9、11、13、15 格。"
            }),
            tip("做完了别急着走，把 BPM 从 128 拉到 100，再拉到 150，听听同一个循环在不同速度下的性格。"),
            ok("恭喜，你已经能独立做出一个能循环播放的鼓组了。Lv.2 我们要让它「会跳」。")
          ]
        }
      ]
    },

    /* ================= Lv.2 ================= */
    {
      id: 2, tag: "Lv.2", name: "循环制造者", en: "LOOP MAKER", color: "#4ade80", icon: "🔁",
      desc: "鼓组稳了，现在加反拍、贝斯、和弦。你的 4 小节不再是节拍器，而是一个能让人抖腿的 Loop。",
      lessons: [
        {
          id: "l2-edm", track: "edm", kind: "lesson", xp: 80, time: "8 分钟",
          title: "反拍 hi-hat：让循环「会跳」",
          sub: "开镲落在 2、6、10、14 格，律动立刻前进",
          lead: "同样一个鼓组，只要把开镲从正拍挪到反拍，感觉就从「走」变成了「跳」。这是 EDM 最便宜也最有效的魔法。",
          tasks: [
            { id: "offhat", label: "开镲落在 4 个反拍（第 3、7、11、15 格）" },
            { id: "notfull", label: "闭镲只放正拍，没有把 16 格全填满" }
          ],
          blocks: [
            note("本课你会得到：① 正拍/反拍的区别 ② offbeat open hat 的写法 ③ 一条「留白」的审美原则。"),
            demo("A/B 对比 · 正拍 vs 反拍", [
              { label: "正拍 8 分闭镲", sub: "稳，但有点平", demo: "l2-straight", tag: "A" },
              { label: "反拍开镲", sub: "会跳了", demo: "l2-offbeat", tag: "B" }
            ], "注意第二段里每一次「嚓——」都落在底鼓的缝隙里。"),
            p("第 1 拍是 <b>正拍</b>（Downbeat）。两拍之间的那一半叫 <b>反拍</b>（Offbeat）。在 16 格网格上，反拍 8 分音符就是 <b>第 3、7、11、15 格</b>——也就是每拍的后半拍。"),
            tip("口诀：底鼓踩 1、3；开镲踩「和」；军鼓踩 2、4。三个东西互相错开，循环才有空间。"),
            h("动手：把开镲放上去"),
            p("先把底鼓（1、9）和军鼓（5、13）放好——这次直接给你预设。你只需要把开镲放在 4 个反拍上，再听听有什么变化。"),
            widget("lab", {
              rows: ["kick", "snare", "hatc", "hato"], bpm: 128, bars: 4,
              preset: { drums: { kick: { steps: [0, 8] }, snare: { steps: [4, 12] }, hatc: { steps: quarters, gain: 0.32 } } },
              goals: [
                { id: "offhat", label: "开镲 = 第 3、7、11、15 格", test: (pt) => eq(pt.drums.hato.steps, offbeat) },
                { id: "notfull", label: "没有把所有格子填满（≤ 6 个闭镲）", test: (pt) => pt.drums.hatc.steps.length <= 6 }
              ],
              hint: "开镲放在 3、7、11、15 格；闭镲留在 1、5、9、13 格（正拍）。"
            }),
            h("为什么「留白」这么重要"),
            p("把 16 格全填满，听起来不是更满，而是更糊——因为每个声音都在抢同一块时间。专业鼓组永远在<b>互相让路</b>：底鼓响的时候开镲不响，开镲响的时候底鼓歇着。"),
            warn("注意：本课说的「反拍」是 8 分反拍。<code>第 3、7、11、15 格</code> 数的是格子序号，从 1 开始。别和「第 3 拍」搞混。"),
            Q("开镲放在 3、7、11、15 格，它听起来会是什么感觉？", [
              { text: "每拍的正拍都有一个重音" },
              { text: "每拍的后半拍有一个「推」的力量，让人想动" },
              { text: "完全没有节奏" }
            ], 1, "反拍是「推」的力量。正拍让人站稳，反拍让人想跳。"),
            ok("现在你的循环有骨架、有呼吸、有推力了。下一课给它加和声。")
          ]
        },
        {
          id: "l2-piano", track: "piano", kind: "lesson", xp: 90, time: "10 分钟",
          title: "三和弦：三个音撑起一片天",
          sub: "C、Am、F、G —— 四和弦万能进行",
          lead: "你不需要会看五线谱，也能弹和弦。三和弦的构造只有一条数学：大三 = 4+3，小三 = 3+4。",
          tasks: [
            { id: "chords", label: "依次弹出 C、Am、F、G 四个和弦" },
            { id: "quiz", label: "答对：小三和弦的半音结构" }
          ],
          blocks: [
            note("本课你会得到：① 三和弦的构造公式 ② 四个万能和弦的手型 ③ 一条能弹一辈子的进行：C–Am–F–G。"),
            h("三个音，隔一个键按一个"),
            p("<b>C 大三和弦</b> = C + E + G。看键盘：C 到 E 中间隔了 C#、D 两个键（4 个半音），E 到 G 隔了 F、F#（3 个半音）。所以 <b>大三 = 4 + 3</b>。"),
            p("<b>A 小三和弦</b> = A + C + E。A 到 C 是 3 个半音，C 到 E 是 4 个半音。所以 <b>小三 = 3 + 4</b>。就这一个数字换了位置，情绪就从「亮」变成「暗」。"),
            terms([
              ["大三和弦", "根音 + 4 半音 + 3 半音。明亮、稳定。例：C E G。"],
              ["小三和弦", "根音 + 3 半音 + 4 半音。柔和、忧郁。例：A C E。"],
              ["根音 Root", "和弦的名字来源，也是最低、最稳的那个音。"],
              ["转位", "同样的三个音，换一个当最低音。C/E 就是把 E 放最下面。"]
            ]),
            h("动手：四个和弦，四种颜色"),
            p("按顺序弹出 <b>C → Am → F → G</b>。不用管节奏，三个音要同时按下（先后差几十毫秒没关系）。提示会告诉你差哪个音。"),
            widget("keyboard", {
              mode: "chords", chords: ["C", "Am", "F", "G"], octave: 4,
              task: "chords", hint: "每个和弦三个音同时按：C(C-E-G)、Am(A-C-E)、F(F-A-C)、G(G-B-D)"
            }),
            tip("按不准？先把三个音「摸」一遍再同时按。手指记住位置比眼睛看更快。"),
            h("为什么这四个和弦这么万能"),
            p("在 C 大调里，它们是 <b>I – vi – IV – V</b>。全世界一半的流行歌都用这个循环：它从「家」出发，去一点「忧伤」，再走到「远方」，最后用「悬念」把你带回开头。"),
            demo("听：C–Am–F–G 的四种用法", [
              { label: "柱式和弦", sub: "一拍一下，最直接", demo: "l2-loop" },
              { label: "加贝斯与鼓", sub: "这就是一首歌的雏形", demo: "l2-loop" }
            ], "同一个进行，换伴奏型态就是另一种风格。"),
            Q("小三和弦的半音结构是？", [
              { text: "4 + 3" }, { text: "3 + 4" }, { text: "3 + 3" }
            ], 1, "小三 = 根音往上 3 个半音，再往上 4 个半音。大三正好相反：4 + 3。"),
            ok("四个和弦到手。下一关你会把它们放进 8 小节里，做成真正的 Drop。")
          ]
        },
        {
          id: "l2-exam", track: "exam", kind: "exam", xp: 130, time: "8 分钟",
          title: "通关考核 · 鼓 + 贝斯 + 和弦",
          sub: "把三样东西合在一起，做成能循环的 Loop",
          lead: "这次你要同时管三层：鼓组、贝斯、和弦。它们要各就各位，谁也不抢谁。",
          tasks: [
            { id: "kick4", label: "底鼓变成四踩（1、5、9、13 格）" },
            { id: "hats", label: "开镲在 4 个反拍" },
            { id: "bass", label: "贝斯选择「根音 8 分」" },
            { id: "prog", label: "和弦进行 = Am–F–C–G" }
          ],
          blocks: [
            p("这次底鼓升级成 <b>Four on the Floor（四踩）</b>：每拍都有底鼓，共 4 个（第 1、5、9、13 格）。同时把开镲放在反拍，贝斯选「根音 8 分」，和弦用 Am–F–C–G。"),
            widget("lab", {
              rows: ["kick", "snare", "hatc", "hato"], bpm: 126, bars: 4, preset: "empty",
              chords: { editable: true, options: ["Am", "F", "C", "G", "Dm", "Em"] },
              bass: { modes: [["none", "关闭"], ["root8", "根音 8 分"], ["offbeat", "反拍"], ["rolling", "滚动 16 分"]] },
              goals: [
                { id: "kick4", label: "底鼓 = 四踩（1、5、9、13）", test: (pt) => eq(pt.drums.kick.steps, quarters) },
                { id: "hats", label: "开镲 = 3、7、11、15", test: (pt) => eq(pt.drums.hato.steps, offbeat) },
                { id: "bass", label: "贝斯模式 = 根音 8 分", test: (pt) => pt.bass.mode === "root8" && pt.bass.on },
                { id: "prog", label: "和弦 = Am F C G", test: (pt) => pt.chords.list.join(",") === "Am,F,C,G" }
              ],
              hint: "底鼓四踩 + 开镲反拍 + 贝斯 root8 + 和弦 Am F C G。"
            }),
            tip("贝斯不要弹太高。根音在低音区才有「推背感」；跳到中音区会和和弦打架。"),
            ok("这就是一个完整的 EDM Loop 了。下一关，我们把它变成一首歌。")
          ]
        }
      ]
    },

    /* ================= Lv.3 ================= */
    {
      id: 3, tag: "Lv.3", name: "编曲人", en: "ARRANGER", color: "#a78bfa", icon: "🎛",
      desc: "Loop 只是素材。真正的区别在于：什么时候进、什么时候退、什么时候炸。这一关学结构。",
      lessons: [
        {
          id: "l3-edm", track: "edm", kind: "lesson", xp: 90, time: "9 分钟",
          title: "和弦进行与 Drop 结构",
          sub: "Intro → Build → Drop，让 4 小节变成 32 小节",
          lead: "为什么别人的 EDM 听得人起鸡皮疙瘩，你的循环听两遍就腻？因为没有「期待」和「释放」。结构就是制造期待的技术。",
          tasks: [
            { id: "order", label: "把 6 个段落排成正确的顺序" },
            { id: "prog", label: "和弦进行设为 Am–F–C–G" },
            { id: "fx", label: "打开 Risers 和 Impact" }
          ],
          blocks: [
            note("本课你会得到：① EDM 标准段落结构 ② Build 的作用 ③ 用 riser + impact 制造「炸点」。"),
            h("先听：没有 Build 的 Drop 有多平"),
            demo("A/B 对比 · 直接 Drop vs 有 Build 的 Drop", [
              { label: "直接进 Drop", sub: "从第 1 秒就全开", demo: "l3-loop", tag: "A" },
              { label: "Intro → Build → Drop", sub: "先收，再放", demo: "l3-build", tag: "B" }
            ], "第二段前面 4 小节是「憋着」的，所以 Drop 一进来才有力量。"),
            p("音乐的能量来自<b>对比</b>，不是来自音量。如果从头到尾都很大声，耳朵 30 秒就疲劳了。专业做法是：<b>先拿走一些东西，再一次性还给你</b>。"),
            h("EDM 的标准结构"),
            terms([
              ["Intro 前奏", "8–16 小节。只有鼓和 Pad，给 DJ 对拍用。"],
              ["Build 上升", "8 小节。拿走底鼓、加 riser、军鼓加速，制造紧张。"],
              ["Drop 高潮", "16–32 小节。全部乐器进来，低音最重，这就是「炸」。"],
              ["Breakdown 间奏", "8 小节。撤掉鼓，只留和弦/人声，让耳朵休息。"],
              ["Outro 尾奏", "8 小节。逐层退出，方便接下一首。"]
            ]),
            h("动手：排段落"),
            p("把下面的段落卡片按顺序放进 6 个位置。正确顺序是：前奏 → 上升 → 高潮 → 间奏 → 再上升 → 最后高潮。"),
            widget("structure", {
              slots: 6,
              options: [
                { id: "intro", label: "Intro 前奏", bars: 8 },
                { id: "build", label: "Build 上升", bars: 8 },
                { id: "drop", label: "Drop 高潮", bars: 16 },
                { id: "break", label: "Breakdown 间奏", bars: 8 },
                { id: "build2", label: "Build 2 再上升", bars: 8 },
                { id: "drop2", label: "Drop 2 最后高潮", bars: 16 }
              ],
              answer: ["intro", "build", "drop", "break", "build2", "drop2"],
              task: "order", hint: "记住：收 → 憋 → 放 → 歇 → 再憋 → 再放"
            }),
            h("动手：把和弦和 FX 打开"),
            p("现在在下面这个 Lab 里，把和弦改成 <b>Am–F–C–G</b>，并打开 <b>Riser</b>（上升音效）和 <b>Impact</b>（冲击音效）。然后播放——你会听到 Build 段结束时有一条上升音，Drop 第一拍有一个「轰」。"),
            widget("lab", {
              rows: ["kick", "snare", "hatc", "hato"], bpm: 126, bars: 8,
              preset: {
                drums: {
                  kick: { steps: quarters }, snare: { steps: [4, 12] },
                  hatc: { steps: quarters, gain: 0.3 }, hato: { steps: offbeat, gain: 0.42 }
                },
                chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.6 },
                bass: { mode: "root8", gain: 0.9 },
                lead: { on: true, mode: "arp16", gain: 0.45 }
              },
              chords: { editable: true, options: ["Am", "F", "C", "G", "Dm", "Em", "Cadd9", "Fmaj7"] },
              bass: { modes: [["none", "关闭"], ["root8", "根音 8 分"], ["offbeat", "反拍"]] },
              lead: { modes: [["none", "关闭"], ["arp8", "琶音 8 分"], ["arp16", "琶音 16 分"], ["stab", "和弦切音"]] },
              fx: true, arrangement: true,
              goals: [
                { id: "prog", label: "和弦 = Am F C G", test: (pt) => pt.chords.list.join(",") === "Am,F,C,G" },
                { id: "fx", label: "Riser 与 Impact 都打开", test: (pt) => pt.fx.riser && pt.fx.impact }
              ],
              hint: "和弦下拉框选 Am/F/C/G；Riser 与 Impact 两个开关都打开。"
            }),
            Q("Build 段最重要的工作是什么？", [
              { text: "把音量开到最大" },
              { text: "制造紧张感，让 Drop 的到来显得「必须发生」" },
              { text: "把所有乐器都加进来" }
            ], 1, "Build 是「憋气」。去掉底鼓、加 riser、加密军鼓，都是为了让 Drop 的「呼气」更爽。"),
            warn("Riser 不要从头放到尾。它只属于 Build 的最后 2–4 小节。放太久会变成噪音。")
          ]
        },
        {
          id: "l3-piano", track: "piano", kind: "lesson", xp: 90, time: "9 分钟",
          title: "左手：根音 + 五度，稳住低音",
          sub: "A–E–A–E 分解，让右手可以放心飞",
          lead: "左手不需要炫技。它只要做一件事：把和弦的根音和五度扎稳，右手就有地面可以起跳。",
          tasks: [
            { id: "lh", label: "左手弹完 A–E–A–E 分解，70 分以上" }
          ],
          blocks: [
            note("本课你会得到：① 左手根音-五度-八度的手型 ② 「分解和弦」伴奏 ③ 一个能套进任何歌的低音型。"),
            h("左手只做三件事"),
            p("流行/电子钢琴的左手，90% 的时间在做：<b>根音 → 五度 → 八度 → 五度</b>。以 Am 为例，就是 <b>A → E → A → E</b>。听上去很简单，但它是整首歌的地基。"),
            p("为什么是五度？因为根音+五度是最「空」也最稳的音程，不会和右手打架。它像水泥，不抢戏，但少了它整栋楼会晃。"),
            widget("keyboard", {
              mode: "free", range: [33, 60], highlight: [45, 52, 57, 52],
              hint: "A2(45) · E3(52) · A3(57) · E3(52) —— 这就是 Am 的左手分解"
            }),
            h("动手：跟着拍子弹"),
            p("用左手 5-2-1-2 指弹 <b>A2 → E3 → A3 → E3</b>，每拍一个音，70 BPM。先慢，再加速。"),
            widget("keyboard", {
              mode: "sequence", notes: [45, 52, 57, 52, 45, 52, 57, 52], bpm: 70, tolerance: 450,
              task: "lh", fingers: [5, 2, 1, 2, 5, 2, 1, 2], guide: true, startOct: 2,
              hint: "5 指 A2 · 2 指 E3 · 1 指 A3 · 2 指 E3"
            }),
            tip("左手容易越弹越快。把节拍器开大声，让「哒」的声音盖过你的琴声，你会自动跟回去。"),
            h("踏板：一小节一换"),
            p("弹分解和弦时踩住延音踏板，声音会连成一片。但<b>换和弦的瞬间必须松一下再踩</b>，否则前一个和弦的残响会和新的和弦糊在一起。"),
            Q("左手分解 A–E–A–E 里，E 是 A 的什么音？", [
              { text: "三度" }, { text: "五度" }, { text: "八度" }
            ], 1, "A 到 E 是纯五度。根音 + 五度是伴奏里最稳的搭配。"),
            ok("左手稳了，右手才敢做旋律。Lv.4 我们开始处理「声音的质感」。")
          ]
        },
        {
          id: "l3-exam", track: "exam", kind: "exam", xp: 140, time: "10 分钟",
          title: "通关考核 · 8 小节 Drop",
          sub: "鼓、贝斯、和弦、琶音、FX，全部到位",
          lead: "这是你第一首「能放给别人听」的东西。要求只有一个：每个元素都有存在的理由。",
          tasks: [
            { id: "arr", label: "编排 = Intro → Build → Drop" },
            { id: "kick", label: "底鼓四踩" },
            { id: "hats", label: "开镲反拍" },
            { id: "prog", label: "和弦 Am–F–C–G" },
            { id: "lead", label: "主音打开（琶音）" },
            { id: "fx", label: "Riser + Impact 打开" }
          ],
          blocks: [
            p("把下面每一层都打开，然后点播放。8 小节里，前 4 小节应该「憋着」，第 5 小节 Drop 全部炸开。"),
            widget("lab", {
              rows: ["kick", "snare", "hatc", "hato"], bpm: 126, bars: 8,
              preset: {
                drums: {
                  kick: { steps: quarters }, snare: { steps: [4, 12] },
                  hatc: { steps: quarters, gain: 0.3 }, hato: { steps: offbeat, gain: 0.42 }
                },
                chords: { list: ["Am", "F", "C", "G"], mode: "pad", gain: 0.58 },
                bass: { mode: "root8", gain: 0.9 },
                lead: { on: false, mode: "arp16", gain: 0.45 }
              },
              chords: { editable: true, options: ["Am", "F", "C", "G", "Dm", "Em"] },
              bass: { modes: [["none", "关闭"], ["root8", "根音 8 分"], ["offbeat", "反拍"]] },
              lead: { modes: [["none", "关闭"], ["arp8", "琶音 8 分"], ["arp16", "琶音 16 分"], ["stab", "和弦切音"]] },
              fx: true, arrangement: true,
              goals: [
                { id: "arr", label: "编排开启（Intro → Build → Drop）", test: (pt) => !!pt.arrangement && pt.arrangement.length >= 3 },
                { id: "kick", label: "底鼓 = 四踩", test: (pt) => eq(pt.drums.kick.steps, quarters) },
                { id: "hats", label: "开镲 = 反拍", test: (pt) => eq(pt.drums.hato.steps, offbeat) },
                { id: "prog", label: "和弦 = Am F C G", test: (pt) => pt.chords.list.join(",") === "Am,F,C,G" },
                { id: "lead", label: "主音打开", test: (pt) => pt.lead.on && pt.lead.mode !== "none" },
                { id: "fx", label: "Riser 与 Impact 打开", test: (pt) => pt.fx.riser && pt.fx.impact }
              ],
              hint: "六项全绿就通关。先把 drums 和 chords 确认好，再开 lead 和 FX。"
            }),
            ok("你已经能做出一个完整的 Drop 了。接下来是让它在任何设备上都好听——混音。")
          ]
        }
      ]
    },

    /* ================= Lv.4 ================= */
    {
      id: 4, tag: "Lv.4", name: "制作人", en: "PRODUCER", color: "#ff9e2c", icon: "🎚",
      desc: "同样的音符，为什么别人的作品听起来「贵」？这一关学频率分工、侧链、动态——把 demo 变成成品。",
      lessons: [
        {
          id: "l4-edm", track: "edm", kind: "lesson", xp: 100, time: "11 分钟",
          title: "混音：让每个声音有位置",
          sub: "音量平衡、低频分工、侧链、不爆红",
          lead: "混音不是「让每个声音都变大」，而是「让每个声音都有自己的地盘」。地盘靠两样东西划分：频率和音量。",
          tasks: [
            { id: "balance", label: "把 6 条轨道的音量调进目标区" },
            { id: "sidechain", label: "打开侧链 Sidechain" },
            { id: "lowcut", label: "低频切除打开（≥ 30 Hz）" }
          ],
          blocks: [
            note("本课你会得到：① 每个音色的频率地盘 ② 侧链到底在做什么 ③ 一个可以反复用的混音检查流程。"),
            h("先听：没混音 vs 混音后"),
            demo("A/B 对比 · 同一首歌的两种命", [
              { label: "没混音", sub: "Pad 糊住一切，底鼓被埋", demo: "l4-bad", tag: "MUD" },
              { label: "混音后", sub: "低频干净，每个声音都能听见", demo: "l4-good", tag: "CLEAN" }
            ], "第一段不是音色差，是「所有东西都挤在低频」。"),
            h("频率的地盘"),
            terms([
              ["Sub 20–60 Hz", "超低音，身体感受得到，耳朵听不清。太多会糊。"],
              ["Kick 50–100 Hz", "底鼓的「拳頭」。和贝斯共享这段，必须分工。"],
              ["Bass 60–250 Hz", "贝斯的基频。和底鼓错开时间（侧链）。"],
              ["Pad 200–2k Hz", "和声铺底。要让路给主音，通常 -6dB 以上。"],
              ["Hi-hat 8k+ Hz", "空气感。太多会刺耳，太少会闷。"]
            ]),
            p("最重要的规则：<b>同一时间，同一个频段，只能有一个主角</b>。底鼓响的时候，贝斯要让开——这就是 <b>侧链（Sidechain）</b>。"),
            h("侧链在做什么？"),
            p("每次底鼓一响，就把贝斯和 Pad 的音量瞬间压下去一点，0.15 秒后再恢复。听起来像「泵动」（pumping），是 EDM 最有辨识度的呼吸感。"),
            demo("听：侧链开 / 关", [
              { label: "侧链关", sub: "低音糊成一团", demo: "l4-bad" },
              { label: "侧链开", sub: "底鼓一拳一拳打出来", demo: "l4-good" }
            ]),
            h("动手：调你的第一个混音"),
            p("把 5 条轨道的推子调到目标范围（绿色区间），打开侧链，看总输出的峰值表——推到红区就是削波，会爆音。"),
            widget("mixer", {
              faders: [
                { id: "kick", label: "底鼓", value: 98, target: [74, 90] },
                { id: "snare", label: "军鼓", value: 52, target: [62, 78] },
                { id: "hat", label: "镲片", value: 62, target: [32, 50] },
                { id: "bass", label: "贝斯", value: 48, target: [64, 80] },
                { id: "pad", label: "Pad", value: 66, target: [18, 38] },
                { id: "lead", label: "主音", value: 44, target: [52, 68] }
              ],
              sidechain: false, lowcut: false,
              goals: [
                { id: "balance", label: "6 条轨道都在目标区", test: (s) => s.inRange >= 6 },
                { id: "sidechain", label: "侧链已打开", test: (s) => s.sidechain },
                { id: "lowcut", label: "低频切除 ≥ 30 Hz", test: (s) => s.lowcut >= 30 }
              ],
              hint: "Pad 是最容易过大的：把它拉到 30 以下。低切打开，底鼓和贝斯才不打架。"
            }),
            tip("混音顺序：先调鼓 → 再调贝斯 → 再调和弦 → 最后调主音。每次都从「最响的那个」往下减，不要一直加。"),
            Q("侧链压缩的主要作用是？", [
              { text: "让贝斯更响" },
              { text: "底鼓响的时候自动把贝斯/Pad 压下去，腾出低频空间" },
              { text: "给声音加混响" }
            ], 1, "侧链让底鼓和贝斯「轮流说话」。低频只有一个位置，谁响谁占。"),
            warn("总输出不是越大越好。母带阶段才是提响度的地方；混音阶段把峰值控制在 -6 dB 左右，留出余量。")
          ]
        },
        {
          id: "l4-piano", track: "piano", kind: "lesson", xp: 100, time: "9 分钟",
          title: "力度与踏板：让钢琴会呼吸",
          sub: "pp 到 ff 的距离，就是业余和专业的分界线",
          lead: "同样的音符，用不同的力度弹，是两种情绪。钢琴不是「按键发声器」，它是 88 个可以推拉的音量旋钮。",
          tasks: [
            { id: "dyn", label: "弹出「弱—弱—强—强」的力度对比" },
            { id: "pedal", label: "用延音踏板让和弦连成一片" }
          ],
          blocks: [
            note("本课你会得到：① 力度层（velocity）的概念 ② 强弱对比的练习 ③ 踏板什么时候踩、什么时候松。"),
            h("同一句旋律，两种命运"),
            p("下面这条 C-E-G-E 的旋律，第一遍全部用很轻的力度（pp），第二遍用很强的力度（ff）。注意不是音量旋钮在变，是「触键」在变。"),
            demo("听：力度就是表情", [
              { label: "pp 很弱", sub: "像自言自语", demo: "l1-kick" },
              { label: "ff 很强", sub: "像在宣告", demo: "l1-full" }
            ], "（示例为节奏对比，请到键盘上亲手体会真正的力度差别。）"),
            p("钢琴采样是按力度分层的：你按得越重，触发的是越「亮」、越有攻击性的那一层采样。这就是为什么 MIDI 键盘要支持 <b>velocity（力度）</b>。"),
            h("动手：弱—弱—强—强"),
            p("用键盘下方的力度滑杆控制触键轻重。弹 <b>C（弱）、D（弱）、E（强）、G（强）</b>。程序会检查你后两个音的力度是否明显大于前两个。"),
            widget("keyboard", {
              mode: "dyn", notes: [60, 62, 64, 67], bpm: 80,
              task: "dyn", hint: "前两个音力度拉到 30 左右，后两个拉到 85 以上"
            }),
            h("踏板：和声的胶水"),
            p("延音踏板（Sustain）踩下去，琴弦会一直振动。用法只有一条铁律：<b>换和弦就换踏板</b>。如果和弦变了还踩着，两个和弦会糊在一起，听起来像「脏」。"),
            widget("keyboard", {
              mode: "pedal", chord: "Am", task: "pedal",
              hint: "踩住踏板（或点「踏板」按钮），依次弹 A-C-E，听听声音是否连起来"
            }),
            Q("什么时候应该松踏板？", [
              { text: "每弹一个音就松" },
              { text: "和声变化的那一瞬间" },
              { text: "整首曲子都不松" }
            ], 1, "踏板的单位是「和声」，不是「音符」。一个和弦一踩，换和弦时快速松开再踩。"),
            ok("力度 + 踏板 = 钢琴的呼吸。下一关我们学大师怎么「说话」。")
          ]
        },
        {
          id: "l4-exam", track: "exam", kind: "exam", xp: 150, time: "8 分钟",
          title: "通关考核 · 混音检查",
          sub: "六条轨道，一个都不能错",
          lead: "这次没有「差不多」。六条轨道全部进目标区、侧链打开、峰值不爆红，才算过。",
          tasks: [
            { id: "balance", label: "所有轨道都在目标区" },
            { id: "sidechain", label: "侧链打开" },
            { id: "lowcut", label: "低频切除打开（≥ 30 Hz）" },
            { id: "space", label: "Pad 音量 < 主音" }
          ],
          blocks: [
            p("这一关的目标区更窄，推子要更精确。先看电平表，再动推子。"),
            widget("mixer", {
              faders: [
                { id: "kick", label: "底鼓", value: 99, target: [80, 92] },
                { id: "snare", label: "军鼓", value: 55, target: [66, 80] },
                { id: "clap", label: "拍手", value: 65, target: [38, 58] },
                { id: "hat", label: "镲片", value: 55, target: [30, 48] },
                { id: "bass", label: "贝斯", value: 90, target: [70, 86] },
                { id: "pad", label: "Pad", value: 55, target: [20, 40] },
                { id: "lead", label: "主音", value: 42, target: [54, 70] }
              ],
              sidechain: false, lowcut: false, strict: true,
              goals: [
                { id: "balance", label: "全部轨道都在目标区", test: (s) => s.inRange >= 7 },
                { id: "sidechain", label: "侧链已打开", test: (s) => s.sidechain },
                { id: "lowcut", label: "低切 ≥ 30 Hz", test: (s) => s.lowcut >= 30 },
                { id: "space", label: "Pad 音量 < 主音", test: (s) => s.faders.pad < s.faders.lead }
              ],
              hint: "先把所有推子拉到目标区，再打开侧链和低切，最后看峰值。"
            }),
            ok("过了这一关，你的作品在手机、耳机、车里都不会「糊」。只剩最后一步：母带。")
          ]
        }
      ]
    },

    /* ================= Lv.5 ================= */
    {
      id: 5, tag: "Lv.5", name: "大师", en: "MASTER", color: "#ffd166", icon: "🏆",
      desc: "最后一个 10%，决定别人把你的作品当「练习」还是「作品」。母带、风格、句子，以及你自己的签名。",
      lessons: [
        {
          id: "l5-edm", track: "edm", kind: "lesson", xp: 110, time: "10 分钟",
          title: "母带与风格：最后 10%",
          sub: "响度、限幅、参考曲，和你的个人签名",
          lead: "母带不是「把音量拉大」。它是让作品在任何设备上都有同样的冲击力，同时不刺耳、不削波。",
          tasks: [
            { id: "loud", label: "响度进入目标区（-9 ~ -6 dB）" },
            { id: "noclip", label: "没有削波，限幅器打开" },
            { id: "style", label: "选择 3 个风格元素" }
          ],
          blocks: [
            note("本课你会得到：① 响度与削波的关系 ② 限幅器怎么用 ③ 风格不是标签，是三个具体的选择。"),
            h("为什么「更响」不等于「更好」"),
            p("把音量推大，波形上下就会撞到天花板被「削平」——这叫 <b>削波（Clipping）</b>，听起来是刺耳的失真。母带的工作是：在不削波的前提下，尽量把平均响度推高。"),
            p("工具是 <b>限幅器（Limiter）</b>：它会在峰值超过阈值时瞬间压住，像一只很快的手。但压太多会把鼓的「拳頭」压扁，所以阈值要一点点推。"),
            h("动手：推响度"),
            p("拖动增益，让响度进入 <b>-9 ~ -6 dB</b>。超过 0 dB 就会爆红。打开限幅器后再推，看看能推多高而不失真。"),
            widget("master", {
              goals: [
                { id: "loud", label: "响度 -9 ~ -6 dB", test: (s) => s.db >= -9 && s.db <= -6 },
                { id: "noclip", label: "峰值 < 0 dB 且限幅器开启", test: (s) => s.peakDb < -0.2 && s.limiter }
              ],
              styles: ["Melodic EDM", "Progressive House", "Future Bass", "Piano × Electronic"]
            }),
            h("风格 = 三个具体选择"),
            p("「我做 Melodic EDM」不是风格，是标签。真正的风格是：<b>音色 + 节奏 + 和声</b> 的具体选择。比如："),
            terms([
              ["Melodic EDM", "长音色 Pad + 6/8 感琶音 + 小调进行（Am–F–C–G）"],
              ["Progressive House", "四踩 + 滚动贝斯 + 大混响军鼓 + 慢展开"],
              ["Future Bass", "半速鼓 + 宽 Supersaw 和弦 + 大量 pitch bend"],
              ["Piano × Electronic", "真钢琴 + 电子鼓 + 侧链 Pad，动态优先"]
            ]),
            Q("母带限幅器的正确用法是？", [
              { text: "阈值直接拉到 -20 dB，越响越好" },
              { text: "一点点推阈值，让峰值刚好被压住但不压扁鼓" },
              { text: "关掉它，响度才会自然" }
            ], 1, "限幅是「刚好接住」而不是「死死按住」。压太多会让音乐失去呼吸。"),
            tip("找一首你喜欢的歌当参考曲（Reference），在同样的音量下 A/B。你的低频比它多还是少？高频够不够亮？这比任何教程都准。")
          ]
        },
        {
          id: "l5-piano", track: "piano", kind: "lesson", xp: 110, time: "12 分钟",
          title: "大师句法：挂留、加九、留白",
          sub: "从「弹对」到「弹得像在说话」",
          lead: "业余弹音，专业弹句子。句子需要呼吸、需要悬念、需要在最后一刻解决。这一课学三个让和弦「有话说」的工具。",
          tasks: [
            { id: "voicing", label: "依次弹出 Cadd9 → Gsus4 → Am7 → Fmaj7" },
            { id: "quiz", label: "答对：sus4 要怎么解决" }
          ],
          blocks: [
            note("本课你会得到：① add9 / sus4 / maj7 的色彩 ② 声部连接（voice leading） ③ 什么时候「不弹」比弹更重要。"),
            h("三个让和弦变高级的工具"),
            p("<b>add9（加九）</b>：在三和弦上再加一个高八度的二度音。Cadd9 = C E G <b>D</b>。它让和弦变「宽」，像打开一扇窗。"),
            p("<b>sus4（挂四）</b>：把三音换成四音。Gsus4 = G <b>C</b> D。三音被「挂」起来，产生悬念，必须解决回三音（G 大三 = G B D）。"),
            p("<b>maj7（大七）</b>：加一个七音。Fmaj7 = F A C <b>E</b>。温柔、城市感、有一点想哭。"),
            terms([
              ["Cadd9", "C E G D。比 C 更开阔，不改变和弦性质。"],
              ["Gsus4", "G C D。悬念，通常解决到 G。"],
              ["Am7", "A C E G。比 Am 更柔，常用于流行/R&B。"],
              ["Fmaj7", "F A C E。梦幻、怀旧。"],
              ["Voice Leading", "声部连接：让相邻和弦的共同音尽量保持不动，听起来更平滑。"]
            ]),
            h("动手：弹一条「会说话」的进行"),
            p("按提示依次弹出四个和弦。注意每个和弦的<b>最高音</b>：D → D → G → E，这条隐形的旋律线就是「句子」。"),
            widget("keyboard", {
              mode: "progression",
              chords: ["Cadd9", "Gsus4", "Am7", "Fmaj7"],
              task: "voicing", slow: true,
              hint: "Cadd9(C-E-G-D) → Gsus4(G-C-D) → Am7(A-C-E-G) → Fmaj7(F-A-C-E)"
            }),
            h("留白：最后一个音之后的那一秒"),
            p("大师和学生的区别，常常不在弹了什么，而在<b>敢不敢停下来</b>。一个和弦解决之后，让它响完，再进下一个——这就是「呼吸」。"),
            demo("听：密集 vs 有呼吸", [
              { label: "每个音都塞满", sub: "听起来很忙，但没有重点", demo: "l2-loop" },
              { label: "留白 + 长音", sub: "每个音都有空间", demo: "l5-full" }
            ], "（示例为编曲对比：真正的留白要靠你的手，不是靠软件。）"),
            Q("Gsus4 之后通常要解决到哪里？", [
              { text: "回到 G 大三和弦（三音 B 出现）" },
              { text: "直接跳到 C" },
              { text: "停在 sus4 不解决" }
            ], 0, "sus4 的「挂起」需要一个答案：四音 C 下行半音到三音 B，回到 G。这是最经典的解决。"),
            ok("你现在拥有的是「句法」，不是「技巧」。技巧会过时，句法不会。")
          ]
        },
        {
          id: "l5-exam", track: "exam", kind: "exam", xp: 180, time: "12 分钟",
          title: "毕业作品 · 从噪音到大师",
          sub: "编排、混音、母带、签名，全部自己来",
          lead: "最后一关没有标准答案，只有你的选择。把它们拼成一首 32 小节的作品，然后签上你的名字。",
          tasks: [
            { id: "arr", label: "完成 7 段编排" },
            { id: "mix", label: "混音通过（侧链 + 低切）" },
            { id: "master", label: "母带响度达标且不削波" },
            { id: "name", label: "签上你的名字" }
          ],
          blocks: [
            p("这是你的毕业作品。四个步骤，按顺序来：① 排好 7 个段落 ② 确认鼓组与和弦 ③ 打开侧链和低切 ④ 把响度推到 -8 dB 左右。"),
            widget("structure", {
              slots: 7,
              options: [
                { id: "intro", label: "Intro 前奏", bars: 4 },
                { id: "build", label: "Build 上升", bars: 4 },
                { id: "drop", label: "Drop 高潮", bars: 8 },
                { id: "break", label: "Breakdown 间奏", bars: 4 },
                { id: "build2", label: "Build 2 再上升", bars: 4 },
                { id: "drop2", label: "Drop 2 最后高潮", bars: 8 },
                { id: "outro", label: "Outro 尾奏", bars: 4 }
              ],
              answer: ["intro", "build", "drop", "break", "build2", "drop2", "outro"],
              task: "arr", hint: "Intro → Build → Drop → Break → Build → Drop → Outro"
            }),
            widget("mixer", {
              faders: [
                { id: "kick", label: "底鼓", value: 97, target: [78, 92] },
                { id: "snare", label: "军鼓", value: 56, target: [64, 80] },
                { id: "hat", label: "镲片", value: 30, target: [32, 50] },
                { id: "bass", label: "贝斯", value: 86, target: [68, 84] },
                { id: "pad", label: "Pad", value: 52, target: [20, 40] },
                { id: "lead", label: "主音", value: 44, target: [54, 70] }
              ],
              sidechain: false, lowcut: false,
              goals: [
                { id: "mix", label: "侧链与低切都打开", test: (s) => s.sidechain && s.lowcut >= 30 }
              ],
              hint: "六条轨道先摆好，再打开侧链和低切。"
            }),
            widget("master", {
              goals: [
                { id: "master", label: "响度 -9 ~ -6 dB 且不削波", test: (s) => s.db >= -9 && s.db <= -6 && s.peakDb < -0.2 && s.limiter }
              ],
              styles: ["Melodic EDM", "Progressive House", "Future Bass", "Piano × Electronic"]
            }),
            widget("sign", { task: "name" }),
            ok("通关之后，你会拿到一张写着自己名字的证书。但更重要的是：你现在知道每一步为什么这么做。")
          ]
        }
      ]
    }
  ];

  function eq(a, b) {
    if (!a || !b) return false;
    const x = a.slice().sort((m, n) => m - n);
    const y = b.slice().sort((m, n) => m - n);
    return x.length === y.length && x.every((v, i) => v === y[i]);
  }

  window.COURSE = {
    levels: LEVELS,
    chords: CHORDS,
    voice: VOICE,
    drumRows: DRUM_ROWS,
    noteName,
    pattern,
    demos: DEMOS,
    eq,
    range,
    even,
    offbeat,
    quarters,
    allLessons() {
      const out = [];
      LEVELS.forEach((lv) => lv.lessons.forEach((ls) => out.push(Object.assign({ level: lv.id, levelName: lv.name }, ls))));
      return out;
    },
    getLesson(id) {
      for (const lv of LEVELS) for (const ls of lv.lessons) if (ls.id === id) return Object.assign({ level: lv.id, levelName: lv.name }, ls);
      return null;
    }
  };
})();
