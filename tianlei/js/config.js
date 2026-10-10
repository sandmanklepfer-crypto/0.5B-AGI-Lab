/* ==========================================================
   游戏配置与数据
   ========================================================== */

const CONFIG = {
  // 画布
  canvasWidth: 1280,
  canvasHeight: 720,

  // 【问题三】各场景视频背景（URL 后续提供，null 则用静态背景图）
  sceneVideos: {
    menu: 'assets/img/menu.mp4',    // 主菜单
    hub: null,     // 中枢Hub大厅
    courtyard: null, // 学院庭院
    corridor: null,  // 地下走廊
    boss1: null,     // Boss房·虚空行者
    boss2: null,     // Boss房·熔雷巨像
    boss3: null,     // Boss房·字祸魔典
    boss4: null,     // Boss房·时之眼
  },
  
  // 玩家基础属性
  playerBase: {
    maxHp: 100,
    maxMp: 50,
    attack: 12,
    defense: 3,
    speed: 220,
    critRate: 0.1,
    critDamage: 1.8,
    mpRegen: 2, // 每秒
  },
  
  // 经验升级
  expPerLevel: [0, 100, 250, 500, 900, 1500, 2400, 3800, 6000, 9000],
  
  // 技能配置
  skills: {
    1: { // 虚空闪现
      name: '虚空闪现',
      key: 'U',
      cooldown: 3.0,
      mpCost: 8,
      damage: 0,
      range: 180,
      description: '瞬移到摇杆方向，原地留下残影与空间裂痕',
      upgradeCost: [100, 250, 500, 1000, 2000],
      upgradeEffect: ['冷却-0.3s', '冷却-0.3s', '冷却-0.3s', '冷却-0.3s', '距离+50'],
    },
    2: { // 虚空禁锢
      name: '虚空禁锢',
      key: 'K',
      cooldown: 6.0,
      mpCost: 15,
      damage: 25,
      duration: 2.5,
      radius: 80,
      description: '在目标位置展开空间牢笼，敌人持续受伤并被定身',
      upgradeCost: [150, 350, 700, 1400, 2800],
      upgradeEffect: ['伤害+20%', '伤害+20%', '持续+0.5s', '伤害+30%', '范围+30%'],
    },
    3: { // 空间切割
      name: '空间切割',
      key: 'L',
      cooldown: 5.0,
      mpCost: 12,
      damage: 40,
      hits: 4,
      range: 200,
      angle: 60,
      description: '前方扇形区域召唤多道空间裂缝连续斩击',
      upgradeCost: [150, 350, 700, 1400, 2800],
      upgradeEffect: ['伤害+20%', '段数+1', '伤害+20%', '段数+1', '伤害+40%'],
    },
    ult: { // 虚空领域
      name: '虚空领域',
      key: 'I',
      cooldown: 30.0,
      mpCost: 30,
      damage: 15,
      duration: 4,
      radius: 250,
      description: '大范围空间坍缩，紫黑色领域持续爆发',
      upgradeCost: [300, 700, 1500, 3000, 6000],
      upgradeEffect: ['伤害+25%', '持续+1s', '伤害+25%', '范围+30%', '伤害+50%'],
    },
    dodge: { // 闪避
      name: '闪避',
      key: 'O',
      cooldown: 2.0,
      mpCost: 0,
      duration: 0.4,
      description: '短暂无敌并向摇杆方向冲刺',
      upgradeCost: [0, 0, 0, 0, 0],
      upgradeEffect: [],
    },
    attack: { // 普攻
      name: '普攻',
      key: 'J',
      cooldown: 0,
      mpCost: 0,
      damage: 10,
      range: 90,
      comboCount: 3,
      description: '普通攻击，三段连击',
      upgradeCost: [80, 200, 450, 900, 1800],
      upgradeEffect: ['伤害+15%', '伤害+15%', '伤害+20%', '伤害+20%', '伤害+30%'],
    },
  },
  
  // 遗物（改变玩法）
  relics: [
    {
      id: 'broken_watch',
      name: '断裂的怀表',
      description: '虚空闪现冷却减半，但伤害降低30%',
      icon: '⏱',
      rarity: 'rare',
      effect: { skill1CdMul: 0.5, skill1DmgMul: 0.7 },
    },
    {
      id: 'spirit_page',
      name: '言灵残页',
      description: '普攻有30%概率追加符文追击，造成额外伤害',
      icon: '📜',
      rarity: 'uncommon',
      effect: { attackRuneChance: 0.3, attackRuneDamage: 0.5 },
    },
    {
      id: 'witch_amulet',
      name: '巫贤护符',
      description: '受击后获得1.5秒无敌，冷却10秒',
      icon: '🔮',
      rarity: 'rare',
      effect: { hitInvincible: 1.5, hitInvincibleCd: 10 },
    },
    {
      id: 'candle_scale',
      name: '烛九阴鳞片',
      description: '大招附带持续灼烧，每0.5秒造成5%攻击力伤害',
      icon: '🔥',
      rarity: 'epic',
      effect: { ultBurn: true, burnDmgPerTick: 0.05, burnDuration: 3 },
    },
    {
      id: 'void_crystal',
      name: '虚空晶石',
      description: '击杀敌人回复20%最大法力值',
      icon: '💎',
      rarity: 'uncommon',
      effect: { killMpRestore: 0.2 },
    },
    {
      id: 'shadow_cloak',
      name: '暗影斗篷',
      description: '闪避后3秒内下次攻击必定暴击',
      icon: '🌑',
      rarity: 'epic',
      effect: { dodgeCrit: true, dodgeCritDuration: 3 },
    },
  ],
  
  // Boss数据
  bosses: {
    1: {
      id: 1,
      name: '虚空行者',
      title: '空间系·第一锚点',
      maxHp: 400,
      attack: 8,
      speed: 120,
      sprite: 'assets/img/boss_void.png',
      bg: 'assets/img/bg_bossroom.jpg',
      videoUrl: null, // 虚空行者场景动态视频背景
      phases: 1,
      rewards: { gold: 300, star: 2, exp: 150, relic: 'spirit_page' },
      description: '能操控空间的结界守卫，擅长分身与黑洞牵引。',
    },
    2: {
      id: 2,
      name: '熔雷巨像',
      title: '元素系·第二锚点',
      maxHp: 700,
      attack: 12,
      speed: 80,
      sprite: 'assets/img/boss_element.png',
      bg: 'assets/img/bg_bossroom.jpg',
      videoUrl: null, // 熔雷巨像场景动态视频背景
      phases: 2,
      rewards: { gold: 500, star: 3, exp: 300, relic: 'candle_scale' },
      description: '熔岩与雷电交织的巨像，擅长大范围AOE与远程弹幕。',
    },
    3: {
      id: 3,
      name: '字祸魔典',
      title: '言灵系·第三锚点',
      maxHp: 900,
      attack: 10,
      speed: 60,
      sprite: 'assets/img/boss_book.png',
      bg: 'assets/img/bg_bossroom.jpg',
      videoUrl: null, // 字祸魔典场景动态视频背景
      phases: 2,
      rewards: { gold: 700, star: 4, exp: 500, relic: 'witch_amulet' },
      description: '由禁忌文字组成的魔典，发射密集符文弹幕与汉字封印。',
    },
    4: {
      id: 4,
      name: '时之眼·结界核心',
      title: '最终Boss·时之锚点',
      maxHp: 1500,
      attack: 15,
      speed: 100,
      sprite: 'assets/img/boss_eye.png',
      bg: 'assets/img/bg_bossroom.jpg',
      videoUrl: null, // 时之眼场景动态视频背景
      phases: 3,
      rewards: { gold: 1500, star: 10, exp: 1200, relic: 'shadow_cloak' },
      description: '结界的核心，操控时间之力的最终守护者。',
    },
  },
  
  // 剧情对话
  storyPrologue: [
    { speaker: 'narrator', text: '现代魔法学院，被一层神秘的时之结界笼罩。', char: null },
    { speaker: 'narrator', text: '结界内部的时间流速与外界截然不同，学院陷入了永恒的黄昏之中。', char: null },
    { speaker: 'heyun', text: '又是这个梦...不，这不是梦。', char: 'heyun_idle' },
    { speaker: 'narrator', text: '鹤允——空间与言灵双轨天才，称号"虚空禁锢者"。', char: 'heyun_idle' },
    { speaker: 'heyun', text: '结界已经持续了整整三个月，必须找到出口。', char: 'heyun_idle' },
    { speaker: 'heyun', text: '传说地下深处有八个结界锚点...只要全部摧毁，就能撕裂结界。', char: 'heyun_idle' },
    { speaker: 'narrator', text: '带着这样的决心，鹤允潜入了学院地下的结界中枢。', char: 'heyun_battle' },
    { speaker: 'narrator', text: '在黑暗的地下通道中，她遇到了一个同样在寻找出路的少年。', char: null },
    { speaker: 'zhuyang', text: '你也是被那只眼睛困在这里的人吗？', char: 'zhuyang_idle' },
    { speaker: 'heyun', text: '你是谁？身上有股...不祥的气息。', char: 'heyun_idle' },
    { speaker: 'zhuyang', text: '竹阳。从龙渊帝国逃出来的。被某种叫"烛九阴"的东西缠上了。', char: 'zhuyang_idle' },
    { speaker: 'zhuyang', text: '你要去打那些锚点？正好，我也需要出去。一起？', char: 'zhuyang_battle' },
    { speaker: 'heyun', text: '...哼，别拖后腿就行。', char: 'heyun_idle' },
    { speaker: 'narrator', text: '就这样，虚空禁锢者与黑火少年的冒险，正式开始了。', char: null },
  ],
  
  // 章节与关卡（按原著顺序）
  chapters: [
    {
      id: 1,
      name: '第一章·学院日常',
      description: '时之结界笼罩下的魔法学院，鹤允的日常被一场意外打破。',
      bg: 'assets/img/bg_courtyard.jpg', // 庭院
      videoUrl: null, // 【问题三】动态视频背景（稍后提供URL，null则用静态bg）
      scenes: [
        {
          id: 'ch1_intro',
          type: 'story',
          title: '结界笼罩',
          bg: 'assets/img/bg_corridor_dl.jpg', // 教学区走廊
          videoUrl: null, // 动态视频背景
          dialogues: [
            { speaker: 'narrator', text: '现代魔法学院，被一层神秘的时之结界笼罩。' },
            { speaker: 'narrator', text: '结界内部的时间流速与外界截然不同，学院陷入了永恒的黄昏之中。' },
            { speaker: 'narrator', text: '结界已经持续了整整三个月。没有人知道它从何而来，也没有人知道如何破解。' },
            { speaker: 'heyun', text: '又是这个梦...不，这不是梦。' },
            { speaker: 'narrator', text: '鹤允——空间与言灵双轨天才，称号「虚空禁锢者」。现代魔法学院最年轻的特级生。' },
            { speaker: 'heyun', text: '第三节课...算了，反正去不去都一样。时间在这里毫无意义。' },
            { speaker: 'narrator', text: '她从教学区走廊的窗台上跳下，用空间能力直接绕过了结界守卫。' },
            { speaker: 'heyun', text: '反正有结界在，出不去。逃课也没人管。' },
          ],
        },
        {
          id: 'ch1_courtyard',
          type: 'battle',
          title: '庭院·时空裂隙',
          bg: 'assets/img/bg_courtyard.jpg',
          videoUrl: null, // 庭院动态视频背景
          waves: [
            [
              { type: 'floater', x: 900, y: 480 },
              { type: 'floater', x: 1050, y: 440 },
            ],
            [
              { type: 'golem', x: 1000, y: 480 },
              { type: 'floater', x: 1100, y: 420 },
            ],
          ],
          dialogueBefore: [
            { speaker: 'heyun', text: '——什么东西？' },
            { speaker: 'narrator', text: '庭院上空裂开了一道黑色缝隙，扭曲的魔物从中涌出。' },
            { speaker: 'narrator', text: '时空裂隙——结界正在从内部被侵蚀。' },
          ],
          dialogueAfter: [
            { speaker: 'heyun', text: '这些东西...是从哪里来的？' },
            { speaker: 'narrator', text: '裂隙还在扩大。必须搞清楚发生了什么。' },
          ],
        },
        {
          id: 'ch1_meet',
          type: 'story',
          title: '相遇',
          bg: 'assets/img/bg_courtyard.jpg',
          videoUrl: null,
          dialogues: [
            { speaker: 'narrator', text: '在通往地下的走廊尽头，她遇到了一个同样在寻找出路的少年。' },
            { speaker: 'zhuyang', text: '你也是被那只眼睛困在这里的人吗？' },
            { speaker: 'heyun', text: '你是谁？身上有股...不祥的气息。' },
            { speaker: 'zhuyang', text: '竹阳。从龙渊帝国逃出来的。被某种叫「烛九阴」的东西缠上了。' },
            { speaker: 'heyun', text: '龙渊帝国？休战期还没过，你怎么潜入学院的？' },
            { speaker: 'zhuyang', text: '潜入？我是被当作活体武器送过来的。失控了才逃出来。' },
            { speaker: 'zhuyang', text: '你要去打那些锚点？正好，我也需要出去。一起？' },
            { speaker: 'heyun', text: '...哼，别拖后腿就行。' },
            { speaker: 'narrator', text: '就这样，虚空禁锢者与黑火少年的冒险，正式开始了。' },
          ],
        },
      ],
    },
  ],

  // 图鉴数据
  codex: {
    characters: [
      {
        name: '鹤允',
        title: '虚空禁锢者',
        img: 'assets/img/heyun_idle.png',
        desc: '空间-言灵双轨天才少女，现代魔法学院最年轻的特级生。性格冷静孤傲，但内心深处有着不为人知的温柔。',
      },
      {
        name: '竹阳',
        title: '黑火少年',
        img: 'assets/img/zhuyang_idle.png',
        desc: '从遥远的龙渊帝国逃亡而来的少年，被邪神烛九阴的力量所束缚。表面玩世不恭，实则背负着沉重的命运。',
      },
    ],
    bosses: [
      { name: '虚空行者', img: 'assets/img/boss_void.png', desc: '第一个结界锚点的守卫者，能够操控空间进行瞬移与分身。真身散发微光，假身则没有。' },
      { name: '熔雷巨像', img: 'assets/img/boss_element.png', desc: '第二个结界锚点，熔岩与雷电的混合体。砸地前会有红色预警圈，需要及时走位躲避。' },
      { name: '字祸魔典', img: 'assets/img/boss_book.png', desc: '第三个结界锚点，由禁忌文字凝聚而成的魔典。发射密集符文弹幕，被汉字封印击中会减速。' },
      { name: '时之眼', img: 'assets/img/boss_eye.png', desc: '最终Boss，时之结界的核心。拥有三个阶段的战斗形态，操控时间之力极其危险。' },
    ],
    music: [
      { name: '主题曲·天泪纪元', desc: '主菜单/中枢/剧情BGM', src: 'main' },
      { name: '战歌·结界之战', desc: 'Boss战BGM', src: 'boss' },
    ],
  },
  
  // 初始任务
  initialQuests: [
    { id: 'q1', type: 'main', name: '撕裂结界', desc: '击败四个结界锚点，打破时之结界', reward: '结局剧情', completed: false },
    { id: 'q2', type: 'bounty', name: '悬赏：虚空行者', desc: '击败虚空行者', reward: '300金币·2星砾', completed: false, bossId: 1 },
    { id: 'q3', type: 'bounty', name: '悬赏：熔雷巨像', desc: '击败熔雷巨像', reward: '500金币·3星砾', completed: false, bossId: 2 },
    { id: 'q4', type: 'bounty', name: '悬赏：字祸魔典', desc: '击败字祸魔典', reward: '700金币·4星砾', completed: false, bossId: 3 },
    { id: 'q5', type: 'bounty', name: '悬赏：时之眼', desc: '击败时之眼·结界核心', reward: '1500金币·10星砾', completed: false, bossId: 4 },
  ],
};

/* ==========================================================
   【联机 RPG 世界】配置（新增，不影响原有章节/战斗配置）
   - 用一张开放大地图取代原来"死板的大厅"
   - 小怪分散在地图各区域巡游
   - Boss 不再是关卡入口，而是地图上的"锚点"，走进去触发
   ========================================================== */
CONFIG.world = {
  // 世界尺寸（逻辑坐标）
  width: 3600,
  height: 2000,
  // 出生点
  spawnPoint: { x: 320, y: 900 },

  // 分区（每区一张背景图）
  regions: [
    { id: 'gate',      name: '学院大门', x: 0,    y: 0,    w: 1200, h: 2000, bg: 'assets/img/bg_academy.jpg' },
    { id: 'courtyard', name: '学院庭院', x: 1200, y: 0,    w: 1200, h: 2000, bg: 'assets/img/bg_courtyard.jpg' },
    { id: 'library',   name: '图书回廊', x: 2400, y: 0,    w: 1200, h: 1000, bg: 'assets/img/bg_corridor.jpg' },
    { id: 'corridor',  name: '地下走廊', x: 2400, y: 1000, w: 1200, h: 1000, bg: 'assets/img/bg_corridor_dl.jpg' },
  ],

  // Boss 锚点：走到附近（r 半径内）自动触发原来的 Boss 战
  bossZones: [
    { id: 1, name: '虚空行者',  x: 1200, y: 1000, r: 150, hint: '空间·第一锚点' },
    { id: 2, name: '熔雷巨像',  x: 2200, y: 800,  r: 150, hint: '元素·第二锚点' },
    { id: 3, name: '字祸魔典',  x: 2900, y: 500,  r: 150, hint: '言灵·第三锚点' },
    { id: 4, name: '时之眼',    x: 3100, y: 1500, r: 190, hint: '时空·最终锚点' },
  ],

  // 小怪刷新点（与服务器 server.js 的 MONSTER_SPAWNS 对齐）
  spawns: [
    { type: 'floater', x: 300,  y: 620  },
    { type: 'floater', x: 520,  y: 980  },
    { type: 'golem',   x: 760,  y: 760  },
    { type: 'floater', x: 980,  y: 1200 },
    { type: 'wraith',  x: 200,  y: 1400 },
    { type: 'floater', x: 1400, y: 520  },
    { type: 'golem',   x: 1650, y: 900  },
    { type: 'floater', x: 1900, y: 640  },
    { type: 'wraith',  x: 2100, y: 1150 },
    { type: 'golem',   x: 2300, y: 1500 },
    { type: 'floater', x: 1500, y: 1650 },
    { type: 'wraith',  x: 1250, y: 1100 },
    { type: 'wraith',  x: 2600, y: 350  },
    { type: 'wraith',  x: 2900, y: 620  },
    { type: 'golem',   x: 3150, y: 300  },
    { type: 'floater', x: 3350, y: 700  },
    { type: 'wraith',  x: 3050, y: 880  },
    { type: 'golem',   x: 2600, y: 1200 },
    { type: 'floater', x: 2850, y: 1500 },
    { type: 'golem',   x: 3150, y: 1250 },
    { type: 'wraith',  x: 3400, y: 1600 },
    { type: 'floater', x: 3250, y: 1850 },
  ],

  // 联机后端默认地址（可在游戏内"联机设置"里修改）
  defaultServer: 'ws://127.0.0.1:8787/ws',
};
