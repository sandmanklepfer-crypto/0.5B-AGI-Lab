/* ==========================================================================
   TileWorld —— 传奇式 / HD-2D 的 45° 斜视瓦片引擎
   --------------------------------------------------------------------------
   纯 2D：瓦片是「画出来的菱形」，不是 3D 模型，没有透视、没有体积光。
   HD-2D 只是在纯 2D 画面上叠一层光照/泛光/景深（八方旅人那套）。

   对照《学院结构设定》的地图布局：
     室外  学院正门 · 庭院 · 樱花道 · 水池 · 种植园
     一层  教室(兼实验室/演武场) · 图书馆 · 餐厅 · 后厨
     地下  仓库 · 档案室 · 锅炉房（能量核心）
   ========================================================================== */
(function (root) {
  'use strict';

  const TW = 64, TH = 32;        // 瓦片屏幕尺寸（2:1 斜视）
  const SOLID = {};              // 不可通行

  // ---------------- 瓦片定义 ----------------
  const T = {
    GRASS: 0, GRASS2: 1, PATH: 2, WATER: 3, SAND: 4, FLOWER: 5,
    STONE: 10, WOOD: 11, CARPET_R: 12, CARPET_B: 13, TILE_F: 14, DIRT: 15,
    WALL_S: 20, WALL_W: 21, ARCH: 22, WALL_TOP: 23,
    BOOK: 30, TABLE: 31, DESK: 32, STAIR_UP: 33, STAIR_DN: 34,
    FOUNTAIN: 35, TREE: 36, SAKURA: 37, LAMP: 38, BARREL: 39,
    BED: 40, CAULDRON: 41, CRATE: 42, ALTAR: 43, BUSH: 44, FENCE: 45, CROP: 46,
    ROOF_R: 50, ROOF_B: 51, ROOF_P: 52,          // 屋顶（画在最上层，走近淡出）
  };
  [T.WATER, T.WALL_S, T.WALL_W, T.ARCH, T.BOOK, T.TABLE, T.DESK, T.FOUNTAIN,
   T.TREE, T.SAKURA, T.BARREL, T.BED, T.CAULDRON, T.CRATE, T.ALTAR, T.FENCE]
    .forEach(t => SOLID[t] = 1);

  // 高度（用于排序 / 遮挡）：越高越后画
  const HEIGHT = {};
  HEIGHT[T.WALL_S] = HEIGHT[T.WALL_W] = 46;
  HEIGHT[T.ARCH] = 46;
  HEIGHT[T.TREE] = 60; HEIGHT[T.SAKURA] = 62;
  HEIGHT[T.BOOK] = 30; HEIGHT[T.TABLE] = 16; HEIGHT[T.DESK] = 16;
  HEIGHT[T.FOUNTAIN] = 22; HEIGHT[T.CAULDRON] = 20; HEIGHT[T.BARREL] = 18;
  HEIGHT[T.CRATE] = 16; HEIGHT[T.BED] = 16; HEIGHT[T.LAMP] = 40;
  HEIGHT[T.ALTAR] = 26; HEIGHT[T.BUSH] = 14; HEIGHT[T.FENCE] = 18;
  HEIGHT[T.ROOF_R] = HEIGHT[T.ROOF_B] = HEIGHT[T.ROOF_P] = 30;

  // ---------------- 配色 ----------------
  const C = {
    grass: ['#4a7a3a', '#548a42', '#3f6b31'],
    grass2: ['#548a42', '#5f9a4c', '#487a38'],
    path: ['#b09a72', '#c4ae85', '#9a8560'],
    water: ['#2f6a9c', '#3d7cb2', '#24527a'],
    sand: ['#cdb98a', '#ddcb9d', '#b5a271'],
    flower: ['#4a7a3a', '#5a8c46', '#e8a0c0'],
    stone: ['#5c5c6b', '#6b6b7c', '#4b4b58'],
    wood: ['#8a6a48', '#9c7a55', '#75583b'],
    carpetR: ['#8f3a46', '#a34852', '#7a2f3a'],
    carpetB: ['#3a4a8f', '#486ba3', '#2f3a7a'],
    tileF: ['#8a8a96', '#9a9aa6', '#767682'],
    dirt: ['#6d5a40', '#7d6950', '#5d4a33'],
    wallS: ['#6a6a7c', '#82829a', '#52526040'],
    wallW: ['#7a5c3e', '#8d6c49', '#5f4730'],
    roofR: ['#9c4a52', '#b05a62', '#7d3a42'],
    roofB: ['#4a5a9c', '#5a6cb0', '#3a487d'],
    roofP: ['#7a5aa8', '#8d6cbb', '#63478a'],
  };

  // ---------------- 瓦片绘制（程序化，保证 100% 无缝） ----------------
  const PAD = 72;                 // 画布上方预留：给"高的物体"（墙/树/书架）留空间
  const GROUND_Y = PAD + TH / 2;  // 菱形中心在画布里的 y —— 贴图时要减掉它
  const cache = {};
  function hash(seed) { let s = seed | 0 || 1; return () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; }; }

  // ================= AI 精灵瓦片层 =================
  // 把 web/assets/tiles/*.png（AI 生成）接到瓦片渲染里；
  // 精灵比单格宽，所以用「加宽画布 + 固定锚点」的方式，避免改动调用处。
  const SPRITE_W = TW * 3;                 // 精灵画布宽（3 格）
  const SPR_ANCHOR_X = SPRITE_W / 2;       // 水平锚点 = 中线
  const SPR_FOOT_Y = 236;                  // 画布内「脚底」的 y（供 drawTile 定位）
  const SPR_ANCHOR_Y = SPR_FOOT_Y - TH / 2; // 锚点 = 菱形中心（sy 是菱形下尖）
  const SPRITE_H_PX = 280;                 // 画布高（够放最高的树）
  const SPR = {};                          // 名称 -> Image
  const SPR_MAP = {                        // 瓦片类型 -> 精灵名
    [T.TREE]: 'tree_green', [T.SAKURA]: 'tree_sakura',
    [T.BUSH]: 'bush', [T.LAMP]: 'lamp', [T.FENCE]: 'fence',
    [T.CROP]: 'crop', [T.CRATE]: 'crate', [T.BARREL]: 'barrel',
    [T.ALTAR]: 'altar', [T.FOUNTAIN]: 'fountain', [T.BED]: 'desk',
    [T.STAIR_UP]: 'stairs_up', [T.STAIR_DN]: 'stairs_dn',
  };
  const SPR_H = {                           // 每个精灵在游戏里的显示高度（px）
    tree_green: 104, tree_sakura: 108, bush: 52, lamp: 92, fence: 62,
    crop: 50, crate: 54, barrel: 54, altar: 64, fountain: 72,
    desk: 54, stairs_up: 56, stairs_dn: 56,
  };
  let sprReady = 0, sprTotal = 0;
  function loadSprites(base, cb) {
    const names = Object.values(SPR_MAP).filter((v, i, a) => a.indexOf(v) === i);
    sprTotal = names.length;
    names.forEach(n => {
      const im = new Image();
      im.onload = () => { SPR[n] = im; if (++sprReady >= sprTotal && cb) cb(); };
      im.onerror = () => { if (++sprReady >= sprTotal && cb) cb(); };
      im.src = base + n + '.png';
    });
  }

  function makeSpriteTile(t) {
    const name = SPR_MAP[t];
    const im = SPR[name];
    if (!im || !im.naturalWidth) return null;
    const key = 's_' + name;
    if (cache[key]) return cache[key];
    const cv = document.createElement('canvas');
    cv.width = SPRITE_W; cv.height = SPRITE_H_PX;
    const g = cv.getContext('2d');
    const h = SPR_H[name] || 96;
    const w = h * (im.naturalWidth / im.naturalHeight);
    const footY = SPR_FOOT_Y;
    // 接地影先画
    g.save();
    g.globalAlpha = 0.16; g.fillStyle = '#2a2438';
    g.beginPath(); g.ellipse(SPR_ANCHOR_X, footY, w * 0.26, w * 0.09, 0, 0, 7); g.fill();
    g.restore();
    // 本体
    g.drawImage(im, SPR_ANCHOR_X - w / 2, footY - h, w, h);
    cache[key] = cv; return cv;
  }

  /** 统一绘制入口：自动处理普通瓦片 / 精灵瓦片的锚点差异 */
  function drawTile(g, t, sx, sy) {
    const sp = makeSpriteTile(t);
    if (sp) { g.drawImage(sp, sx - SPR_ANCHOR_X, sy - SPR_ANCHOR_Y); return; }
    g.drawImage(makeTile(t), sx - TW / 2, sy - GROUND_Y);
  }

  function makeTile(t) {
    if (cache[t]) return cache[t];
    const cv = document.createElement('canvas');
    cv.width = TW; cv.height = TH + PAD + 40;
    const g = cv.getContext('2d');
    g.translate(0, PAD);
    const dx = TW / 2, dy = TH / 2;
    const R = hash(t * 733 + 71);

    const diamond = (oy, col) => {
      g.beginPath(); g.moveTo(0, dy + oy); g.lineTo(dx, oy);
      g.lineTo(TW, dy + oy); g.lineTo(dx, TH + oy); g.closePath();
      g.fillStyle = col; g.fill();
    };
    const clipDia = (oy) => {
      g.beginPath(); g.moveTo(0, dy + oy); g.lineTo(dx, oy);
      g.lineTo(TW, dy + oy); g.lineTo(dx, TH + oy); g.closePath(); g.clip();
    };

    // ---------- 地面类 ----------
    const groundMap = {
      [T.GRASS]: C.grass, [T.GRASS2]: C.grass2, [T.PATH]: C.path,
      [T.WATER]: C.water, [T.SAND]: C.sand, [T.FLOWER]: C.flower,
      [T.STONE]: C.stone, [T.WOOD]: C.wood, [T.CARPET_R]: C.carpetR,
      [T.CARPET_B]: C.carpetB, [T.TILE_F]: C.tileF, [T.DIRT]: C.dirt,
    };
    if (groundMap[t]) {
      const p = groundMap[t];
      diamond(0, p[0]);
      g.save(); clipDia(0);
      // 纹理
      for (let i = 0; i < (t === T.WATER ? 5 : 12); i++) {
        g.globalAlpha = 0.30;
        g.fillStyle = R() < 0.5 ? p[1] : p[2];
        g.fillRect(R() * TW, R() * TH, 2 + R() * 7, 1 + R() * 2);
      }
      g.globalAlpha = 1;
      if (t === T.WATER) {
        g.globalAlpha = 0.30; g.fillStyle = '#cfe6ff';
        for (let i = 0; i < 4; i++) g.fillRect(6 + i * 15, 5 + ((i * 9) % 17), 11, 2);
        g.globalAlpha = 1;
      }
      if (t === T.STONE || t === T.TILE_F) {         // 砖缝
        g.globalAlpha = 0.22; g.strokeStyle = '#000'; g.lineWidth = 1;
        for (let i = 1; i < 3; i++) {
          g.beginPath(); g.moveTo(0, (TH / 3) * i); g.lineTo(TW, (TH / 3) * i); g.stroke();
        }
        g.globalAlpha = 1;
      }
      if (t === T.WOOD) {                            // 木纹
        g.globalAlpha = 0.20; g.strokeStyle = '#3d2c1a'; g.lineWidth = 1;
        for (let i = 1; i < 4; i++) {
          g.beginPath(); g.moveTo(0, (TH / 4) * i - 1); g.lineTo(TW, (TH / 4) * i + 1); g.stroke();
        }
        g.globalAlpha = 1;
      }
      if (t === T.CARPET_R || t === T.CARPET_B) {    // 地毯花纹
        g.globalAlpha = 0.45; g.strokeStyle = '#e8d8a0'; g.lineWidth = 2;
        g.beginPath(); g.moveTo(dx, dy - 8); g.lineTo(TW - 8, dy); g.lineTo(dx, dy + 8); g.lineTo(8, dy); g.closePath(); g.stroke();
        g.globalAlpha = 1;
      }
      if (t === T.FLOWER) {
        for (let i = 0; i < 8; i++) {
          g.fillStyle = ['#e8a0c0', '#f0d060', '#e07090', '#f0f0f0'][i % 4];
          g.fillRect(5 + R() * (TW - 12), 3 + R() * (TH - 10), 3, 3);
        }
      }
      g.restore();
      g.strokeStyle = 'rgba(0,0,0,0.26)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(0, dy); g.lineTo(dx, 0); g.lineTo(TW, dy); g.lineTo(dx, TH); g.closePath(); g.stroke();
      cache[t] = cv; return cv;
    }

    // ---------- 屋顶（画在最上层，玩家走近时整体淡出）----------
    if (t === T.ROOF_R || t === T.ROOF_B || t === T.ROOF_P) {
      const pp = t === T.ROOF_R ? C.roofR : (t === T.ROOF_B ? C.roofB : C.roofP);
      // 斜面：左暗右亮，做出屋脊感
      const topY = -H;
      g.beginPath(); g.moveTo(0, dy); g.lineTo(dx, TH); g.lineTo(dx, TH + topY); g.lineTo(0, dy + topY); g.closePath();
      g.fillStyle = pp[2]; g.fill();
      g.beginPath(); g.moveTo(dx, TH); g.lineTo(TW, dy); g.lineTo(TW, dy + topY); g.lineTo(dx, TH + topY); g.closePath();
      g.fillStyle = pp[0]; g.fill();
      // 瓦楞
      g.globalAlpha = 0.30; g.strokeStyle = '#2a1a20'; g.lineWidth = 1;
      for (let i = 1; i < 5; i++) {
        const k = i / 5;
        g.beginPath();
        g.moveTo(dx * k, dy + topY * (1 - k) + TH * 0);
        g.lineTo(0, dy + topY);
        g.stroke();
      }
      g.globalAlpha = 1;
      // 屋脊高光
      g.strokeStyle = pp[1]; g.lineWidth = 2.5;
      g.beginPath(); g.moveTo(0, dy + topY); g.lineTo(dx, topY); g.lineTo(TW, dy + topY); g.stroke();
      g.strokeStyle = 'rgba(0,0,0,0.35)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(0, dy); g.lineTo(dx, 0); g.lineTo(TW, dy); g.lineTo(dx, TH); g.closePath(); g.stroke();
      cache[t] = cv; return cv;
    }

    // ---------- 立体物：先铺地再长起来 ----------
    const base = (t === T.BOOK || t === T.TABLE || t === T.DESK || t === T.BED || t === T.BARREL || t === T.CRATE || t === T.CAULDRON || t === T.ALTAR || t === T.LAMP)
      ? (t === T.BOOK || t === T.BED || t === T.LAMP ? C.wood : C.wood)
      : C.stone;
    // 默认底面
    if (t === T.BOOK || t === T.TABLE || t === T.DESK || t === T.BED) diamond(0, C.wood[0]);
    else if (t === T.WALL_S || t === T.ARCH || t === T.FOUNTAIN || t === T.ALTAR) diamond(0, C.stone[0]);
    else if (t === T.WALL_W || t === T.BARREL || t === T.CRATE) diamond(0, C.wood[0]);
    else if (t === T.CAULDRON) diamond(0, C.stone[0]);
    else if (t === T.TREE || t === T.SAKURA || t === T.BUSH || t === T.FENCE || t === T.LAMP) diamond(0, C.grass[0]);
    else diamond(0, C.grass[0]);

    const H = HEIGHT[t] || 20;

    if (t === T.WALL_S || t === T.WALL_W || t === T.ARCH) {
      const p = t === T.WALL_W ? C.wallW : C.stone;
      // 左面 / 右面 / 顶面
      const topY = -H;
      g.beginPath(); g.moveTo(0, dy); g.lineTo(dx, TH); g.lineTo(dx, TH + topY); g.lineTo(0, dy + topY); g.closePath();
      g.fillStyle = p[2]; g.fill();
      g.beginPath(); g.moveTo(dx, TH); g.lineTo(TW, dy); g.lineTo(TW, dy + topY); g.lineTo(dx, TH + topY); g.closePath();
      g.fillStyle = p[0]; g.fill();
      g.beginPath(); g.moveTo(0, dy + topY); g.lineTo(dx, topY); g.lineTo(TW, dy + topY); g.lineTo(dx, TH + topY); g.closePath();
      g.fillStyle = p[1]; g.fill();
      g.strokeStyle = 'rgba(0,0,0,0.4)'; g.lineWidth = 1;
      g.beginPath(); g.moveTo(dx, TH); g.lineTo(dx, TH + topY); g.stroke();
      // 砖缝
      g.globalAlpha = 0.25; g.strokeStyle = '#000';
      for (let i = 1; i < 4; i++) {
        const yy = topY + (H / 4) * i;
        g.beginPath(); g.moveTo(0, dy + yy); g.lineTo(TW, dy + yy); g.stroke();
      }
      g.globalAlpha = 1;
      if (t === T.ARCH) {   // 拱门：中间挖空
        g.globalCompositeOperation = 'destination-out';
        g.beginPath(); g.ellipse(dx, TH + topY * 0.55, 20, 30, 0, 0, 7); g.fill();
        g.globalCompositeOperation = 'source-over';
      }
    } else if (t === T.BOOK) {
      const topY = -H;
      g.beginPath(); g.moveTo(0, dy); g.lineTo(dx, TH); g.lineTo(dx, TH + topY); g.lineTo(0, dy + topY); g.closePath(); g.fillStyle = C.wood[2]; g.fill();
      g.beginPath(); g.moveTo(dx, TH); g.lineTo(TW, dy); g.lineTo(TW, dy + topY); g.lineTo(dx, TH + topY); g.closePath(); g.fillStyle = C.wood[1]; g.fill();
      // 书
      for (let r = 0; r < 4; r++) {
        const yy = topY + 4 + r * 10;
        for (let i = 0; i < 6; i++) {
          g.fillStyle = ['#8f3a46', '#3a5a8f', '#3f7a4a', '#8a7a3a', '#6a3a8f', '#a06030'][(i + r) % 6];
          g.fillRect(4 + i * 9, dy + yy - 8, 7, 9);
        }
      }
    } else if (t === T.FOUNTAIN) {
      g.fillStyle = C.stone[0]; g.beginPath(); g.ellipse(dx, dy - 4, 22, 11, 0, 0, 7); g.fill();
      g.fillStyle = C.water[0]; g.beginPath(); g.ellipse(dx, dy - 6, 16, 8, 0, 0, 7); g.fill();
      g.fillStyle = C.stone[1]; g.fillRect(dx - 4, dy - 34, 8, 26);
      g.fillStyle = C.water[1]; g.beginPath(); g.ellipse(dx, dy - 34, 9, 4, 0, 0, 7); g.fill();
    } else if (t === T.TREE || t === T.SAKURA) {
      const blossom = t === T.SAKURA;
      g.fillStyle = '#4a3520'; g.fillRect(dx - 4, dy - 34, 8, 30);
      const blobs = [[0, -50, 20], [-14, -42, 13], [14, -42, 13], [0, -64, 14], [-8, -56, 12], [8, -56, 12]];
      for (const [ox, oy, r] of blobs) {
        g.beginPath(); g.arc(dx + ox, dy + oy, r, 0, 7);
        g.fillStyle = blossom ? (r > 16 ? '#f0b8d0' : '#e8a0c0') : (r > 16 ? '#3f7a34' : '#356028');
        g.fill();
      }
      if (blossom) { g.globalAlpha = 0.6;
        for (let i = 0; i < 8; i++) { g.fillStyle = '#ffd8e8'; g.fillRect(dx - 26 + R() * 52, dy - 72 + R() * 44, 3, 3); }
        g.globalAlpha = 1; }
      g.globalAlpha = 0.20; g.fillStyle = '#000';
      g.beginPath(); g.ellipse(dx, dy - 2, 18, 7, 0, 0, 7); g.fill(); g.globalAlpha = 1;
    } else if (t === T.TABLE || t === T.DESK) {
      g.fillStyle = C.wood[1];
      g.beginPath(); g.moveTo(2, dy - 4); g.lineTo(dx, TH - 10); g.lineTo(TW - 2, dy - 4); g.lineTo(dx, -10); g.closePath(); g.fill();
      g.fillStyle = C.wood[2]; g.fillRect(dx - 4, dy - 6, 8, 12);
    } else if (t === T.BED) {
      g.fillStyle = '#5c4a7a'; g.fillRect(8, dy - 12, TW - 16, 16);
      g.fillStyle = '#e8e0f0'; g.fillRect(10, dy - 22, TW - 20, 12);
      g.fillStyle = '#a090c0'; g.fillRect(12, dy - 24, 18, 14);
    } else if (t === T.BARREL || t === T.CRATE) {
      g.fillStyle = C.wood[1]; g.fillRect(dx - 12, dy - 22, 24, 22);
      g.fillStyle = C.wood[2]; g.fillRect(dx - 12, dy - 22, 24, 4);
      g.strokeStyle = '#4a3520'; g.lineWidth = 2;
      g.beginPath(); g.moveTo(dx - 12, dy - 12); g.lineTo(dx + 12, dy - 12); g.stroke();
    } else if (t === T.CAULDRON) {
      g.fillStyle = '#2a2a34'; g.beginPath(); g.ellipse(dx, dy - 12, 16, 12, 0, 0, 7); g.fill();
      g.fillStyle = '#6a4020'; g.beginPath(); g.ellipse(dx, dy - 18, 12, 6, 0, 0, 7); g.fill();
      g.fillStyle = '#c06020'; g.beginPath(); g.ellipse(dx, dy - 20, 7, 3, 0, 0, 7); g.fill();
    } else if (t === T.LAMP) {
      g.fillStyle = '#3a3a46'; g.fillRect(dx - 2, dy - 42, 4, 40);
      g.fillStyle = '#ffd88a'; g.beginPath(); g.arc(dx, dy - 46, 7, 0, 7); g.fill();
      g.globalAlpha = 0.35; g.fillStyle = '#ffe0a0';
      g.beginPath(); g.arc(dx, dy - 46, 15, 0, 7); g.fill(); g.globalAlpha = 1;
    } else if (t === T.ALTAR) {
      g.fillStyle = C.stone[1]; g.fillRect(dx - 16, dy - 26, 32, 26);
      g.fillStyle = C.stone[2]; g.fillRect(dx - 16, dy - 30, 32, 6);
      g.fillStyle = '#7a50c0'; g.beginPath(); g.arc(dx, dy - 38, 7, 0, 7); g.fill();
      g.globalAlpha = 0.5; g.fillStyle = '#b088ff';
      g.beginPath(); g.arc(dx, dy - 38, 14, 0, 7); g.fill(); g.globalAlpha = 1;
    } else if (t === T.BUSH) {
      g.fillStyle = '#3f7a34'; g.beginPath(); g.ellipse(dx, dy - 10, 20, 12, 0, 0, 7); g.fill();
      g.fillStyle = '#356028'; g.beginPath(); g.ellipse(dx, dy - 6, 16, 8, 0, 0, 7); g.fill();
    } else if (t === T.FENCE) {
      g.fillStyle = '#8a6a48';
      for (let i = 0; i < 4; i++) g.fillRect(4 + i * 16, dy - 26, 5, 24);
      g.fillStyle = '#9c7a55'; g.fillRect(0, dy - 20, TW, 4); g.fillRect(0, dy - 10, TW, 4);
    } else if (t === T.CROP) {
      for (let i = 0; i < 5; i++) {
        g.fillStyle = '#4a8a3a';
        g.fillRect(6 + i * 11, dy - 16 + (i % 2) * 3, 4, 14);
        g.fillStyle = '#6aa84a'; g.fillRect(4 + i * 11, dy - 20 + (i % 2) * 3, 8, 5);
      }
    } else if (t === T.STAIR_UP || t === T.STAIR_DN) {
      const up = t === T.STAIR_UP;
      for (let i = 0; i < 6; i++) {
        g.fillStyle = `rgb(${120 + i * 12},${110 + i * 12},${100 + i * 12})`;
        const w = 30 - i * 4, yy = dy - (up ? i : 5 - i) * 6;
        g.fillRect(dx - w / 2, yy - 6, w, 7);
      }
      g.fillStyle = up ? '#8fd0ff' : '#ffb060'; g.font = 'bold 14px sans-serif'; g.textAlign = 'center';
      g.fillText(up ? '▲' : '▼', dx, dy - 34);
    } else if (t === T.ARCH) { /* 已处理 */ }

    cache[t] = cv; return cv;
  }

  // ================= 地图 =================
  // 用《学院结构设定》的真实布局：室外 / 一层 / 地下
  const MW = 72, MH = 72;
  const map = new Uint8Array(MW * MH);
  const roof = new Uint8Array(MW * MH);        // 屋顶层（0=无）
  const roofOwner = new Int16Array(MW * MH);   // 屋顶归属哪栋楼（0=无，i+1=buildings[i]）
  const buildings = [];                        // {x,y,w,h,name} 用于"走近淡出"
  const setRoof = (x, y, v, owner) => { if (x >= 0 && y >= 0 && x < MW && y < MH) { roof[y * MW + x] = v; if (owner) roofOwner[y * MW + x] = owner; } };
  const roofAt = (x, y) => (x < 0 || y < 0 || x >= MW || y >= MH) ? 0 : roof[y * MW + x];
  const set = (x, y, v) => { if (x >= 0 && y >= 0 && x < MW && y < MH) map[y * MW + x] = v; };
  const at = (x, y) => (x < 0 || y < 0 || x >= MW || y >= MH) ? T.WALL_S : map[y * MW + x];

  (function buildAcademy() {
    const R = hash(20260);
    for (let y = 0; y < MH; y++) for (let x = 0; x < MW; x++) set(x, y, R() < 0.25 ? T.GRASS2 : T.GRASS);

    // ---- 房间工具 ----
    function room(x0, y0, w, h, floor, wallT) {
      for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) {
        const edge = (x === x0 || y === y0 || x === x0 + w - 1 || y === y0 + h - 1);
        set(x, y, edge ? (wallT || T.WALL_S) : floor);
      }
    }
    function door(x, y, vertical) {
      if (vertical) { set(x, y, T.STONE); set(x, y + 1, T.STONE); }
      else { set(x, y, T.STONE); set(x + 1, y, T.STONE); }
    }
    function fill(x0, y0, w, h, t) { for (let y = y0; y < y0 + h; y++) for (let x = x0; x < x0 + w; x++) set(x, y, t); }

    // ================= 室外：学院大门 / 庭院（简洁版）=================
    // 中轴大道（南北）
    fill(33, 4, 6, 34, T.PATH);
    // 东西横路
    fill(4, 30, 64, 5, T.PATH);
    // 石板广场
    fill(26, 24, 20, 14, T.PATH);
    // 水池（广场中央）
    fill(34, 27, 5, 5, T.WATER);
    set(36, 29, T.FOUNTAIN);
    // 樱花道（两侧对称）
    for (let y = 8; y <= 26; y += 3) { set(30, y, T.SAKURA); set(41, y, T.SAKURA); }
    for (let x = 8; x <= 62; x += 5) { set(x, 38, T.SAKURA); }
    // 灌木 / 花丛（稀疏点缀）
    for (let y = 5; y < 42; y++) for (let x = 4; x < 66; x++) {
      if (at(x, y) !== T.GRASS && at(x, y) !== T.GRASS2) continue;
      const r = R();
      if (r < 0.012) set(x, y, T.BUSH);
      else if (r < 0.03) set(x, y, T.FLOWER);
      else if (r < 0.045) set(x, y, T.TREE);
    }
    // 路灯（沿大道）
    for (let y = 10; y <= 40; y += 7) { set(32, y, T.LAMP); set(39, y, T.LAMP); }

    // ================================================================
    //  【建筑】数据驱动：整张外观图 + 菱形占地 + 门 + 房间
    //  占地内格子不可通行（碰撞），只有门洞能进。
    //  进门 → 切到「房间场景」（另一张整图 + 交互点）。
    // ================================================================
    function placeBuilding(b) {
      const rec = Object.assign({}, b);
      if (!rec.door) rec.door = { x: b.x + Math.floor(b.w / 2), y: b.y + b.h - 1 };
      buildings.push(rec);
      return rec;
    }

    placeBuilding({ id:'main', name:'学院主楼', img:'assets/obj/b_main_t.png', x:32, y:46, w:9, h:7, room:'main_1f' });
    placeBuilding({ id:'lib',  name:'图书馆',   img:'assets/obj/b_lib_t.png',  x:44, y:40, w:7, h:6,  room:'main_1f' });
    placeBuilding({ id:'dorm', name:'宿舍楼',   img:'assets/obj/b_dorm_t.png', x:53, y:43, w:7,  h:6,  room:'main_2f' });
    placeBuilding({ id:'hall', name:'大礼堂',   img:'assets/obj/b_hall_t.png', x:12, y:44, w:8, h:7,  room:'main_b1' });
  })();

  // ================= 交互系统 =================
  // 每一格都能是"交互点"。走近 → 弹提示 → 按 E 触发。
  const INTERACT = {
    [T.STAIR_DN]: { act: '下楼',   hint: '前往地下层',   key: 'down' },
    [T.STAIR_UP]: { act: '上楼',   hint: '返回地面',     key: 'up' },
    [T.BOOK]:     { act: '阅读',   hint: '翻开一本书',   key: 'read' },
    [T.BED]:      { act: '睡觉',   hint: '休息并存档',   key: 'sleep' },
    [T.CAULDRON]: { act: '烹饪',   hint: '生火做饭',     key: 'cook' },
    [T.CRATE]:    { act: '开箱',   hint: '搜刮物资',     key: 'loot' },
    [T.BARREL]:   { act: '开桶',   hint: '搜刮物资',     key: 'loot' },
    [T.ALTAR]:    { act: '触碰',   hint: '结界节点',     key: 'altar' },
    [T.WATER]:    { act: '打水',   hint: '取一桶清水',   key: 'water' },
    [T.FOUNTAIN]: { act: '许愿',   hint: '投一枚硬币',   key: 'wish' },
    [T.CROP]:     { act: '采摘',   hint: '收取作物',     key: 'pick' },
    [T.LAMP]:     { act: '点灯',   hint: '点亮灯火',     key: 'light' },
  };

  /** 玩家站立/面前的格子能不能交互 */
  function interactAt(x, y) {
    const t = at(Math.floor(x), Math.floor(y));
    return INTERACT[t] ? { t, ...INTERACT[t], x: Math.floor(x), y: Math.floor(y) } : null;
  }

  /** 建筑占地碰撞：墙走不上去，门那格例外 */
  function buildingSolid(x, y) {
    const tx = Math.floor(x), ty = Math.floor(y);
    for (const b of buildings) {
      if (tx < b.x || tx >= b.x + b.w || ty < b.y || ty >= b.y + b.h) continue;
      // 门洞（2 格宽）
      if (b.door && ty === b.y + b.h - 1 && (tx === b.door.x || tx === b.door.x + 1)) return false;
      // ★★ 建筑内部可走（只有四面外墙挡路）→ 玩家能进门、在室内走动、上楼
      const innerX = tx > b.x && tx < b.x + b.w - 1;
      const innerY = ty > b.y && ty < b.y + b.h - 1;
      if (innerX && innerY) return false;
      // 门前台阶（2 格，在建筑外南侧）
      return true;
    }
    return false;
  }

  /** 建筑渲染信息：把整张图对齐到菱形占地（底角对齐底部尖端） */
  function buildingRender(b, TW, TH) {
    const spanW = (b.w + b.h - 2) * (TW / 2) * 1.15;
    return { spanW, anchorTile: [b.x + b.w - 1, b.y + b.h - 1] };
  }

  /** 玩家是否在某个建筑内部（用于屋顶淡出） */
  function buildingAt(x, y) {
    for (const b of buildings) {
      if (x >= b.x - 0.5 && x <= b.x + b.w - 0.5 && y >= b.y - 0.5 && y <= b.y + b.h - 0.5) return b;
    }
    return null;
  }

  /** 点到建筑矩形的距离（在内部为 0）*/
  function distToBuilding(b, x, y) {
    const dx = Math.max(b.x - x, 0, x - (b.x + b.w - 1));
    const dy = Math.max(b.y - y, 0, y - (b.y + b.h - 1));
    if (dx === 0 && dy === 0) return 0;          // 在楼里
    return Math.hypot(dx, dy);
  }

  // 全局透视开关（按 T）：把所有屋顶压成半透明，方便看全城布局
  let globalXray = false;
  function setXray(v) { globalXray = !!v; }

  /**
   * 屋顶透明度 —— 按「玩家离这栋楼多远」决定：
   *   人在楼内        → 0     （完全掀开）
   *   人在门口/紧贴   → 0.30  （半透明，仍看得出"这是房子"）
   *   离得越远        → 逐渐回到 1（不透明）
   */
  function roofAlpha(bx, by, hero) {
    if (globalXray) return 0.34;
    const idx = roofOwner[by * MW + bx];
    if (!idx) return 1;
    const b = buildings[idx - 1];
    if (!b) return 1;
    const d = distToBuilding(b, hero.x, hero.y);
    const NEAR = 1.0, FAR = 5.0;
    if (d <= NEAR) return 0.30;
    if (d >= FAR) return 1;
    let t = (d - NEAR) / (FAR - NEAR);
    t = t * t * (3 - 2 * t);                     // 平滑
    return 0.30 + 0.70 * t;
  }

  // ---------------- 投影 ----------------
  const isoX = (x, y) => (x - y) * (TW / 2);
  const isoY = (x, y) => (x + y) * (TH / 2);

  function isSolid(x, y) {
    const tx = Math.floor(x), ty = Math.floor(y);
    if (SOLID[at(tx, ty)]) return true;
    return buildingSolid(x, y);
  }

  // ---------------- 渲染 ----------------
  function drawScene(g, opt) {
    const { camX, camY, W, H, hero, entities, showGrid, time } = opt;

    // 背景天空
    const bg = g.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#1a1236'); bg.addColorStop(.5, '#2a1f4e'); bg.addColorStop(1, '#120c26');
    g.fillStyle = bg; g.fillRect(0, 0, W, H);

    const ox = W / 2 - camX, oy = H / 2 - camY;
    const hx = Math.floor(hero.x), hy = Math.floor(hero.y);
    const RANGE = Math.ceil(Math.max(W, H) / TW) + 6;

    const list = [];
    for (let y = hy - RANGE; y <= hy + RANGE; y++) {
      for (let x = hx - RANGE; x <= hx + RANGE; x++) {
        if (x < 0 || y < 0 || x >= MW || y >= MH) continue;
        const sx = ox + isoX(x, y), sy = oy + isoY(x, y) + TH / 2;
        if (sx < -TW * 2 || sx > W + TW * 2 || sy < -130 || sy > H + TH * 3) continue;
        const t = at(x, y);
        // 地面先全部画（分层：地面 / 立体物）
        list.push({ d: x + y, layer: HEIGHT[t] ? 1 : 0, x, y, sx, sy, t });
      }
    }
    if (entities) for (const e of entities) {
      list.push({ d: e.x + e.y, layer: 2, ent: e, sx: ox + isoX(e.x, e.y), sy: oy + isoY(e.x, e.y) });
    }
    list.sort((a, b) => (a.layer - b.layer) || (a.d - b.d));

    for (const it of list) {
      if (it.ent) { it.ent.draw(g, it.sx, it.sy); continue; }
      drawTile(g, it.t, it.sx, it.sy);
      if (showGrid) {
        g.strokeStyle = 'rgba(255,255,255,.10)'; g.lineWidth = 1;
        g.beginPath(); g.moveTo(it.sx - TW / 2, it.sy); g.lineTo(it.sx, it.sy - TH / 2);
        g.lineTo(it.sx + TW / 2, it.sy); g.lineTo(it.sx, it.sy + TH / 2); g.closePath(); g.stroke();
      }
    }
    return { ox, oy };
  }

  // ================= 材质地面（无缝拼接） =================
  // 原理：等距变换把「单位方格」映射成菱形。
  //   所以地面瓦片 = (u,v) 空间里的单位方格；
  //   用 canvas 的 setTransform 做等距矩阵，再用 pattern 填充方格区域，
  //   相邻同材质瓦片天然共用纹理 → 完全无缝。
  const TEX = {};                       // 名称 -> Image
  const TEX_FALLBACK = {};              // 名称 -> 纯色（图没加载好时兜底）
  // 每个瓦片「脚下该铺什么地面」
  const GROUND_OF = {
    [T.TREE]: T.GRASS, [T.SAKURA]: T.GRASS, [T.BUSH]: T.GRASS, [T.FLOWER]: T.GRASS,
    [T.FENCE]: T.GRASS, [T.CROP]: T.DIRT, [T.LAMP]: T.PATH,
    [T.CRATE]: T.WOOD, [T.BARREL]: T.WOOD, [T.ALTAR]: T.MARBLE,
    [T.FOUNTAIN]: T.STONE, [T.BED]: T.WOOD, [T.BOOK]: T.WOOD,
    [T.TABLE]: T.WOOD, [T.DESK]: T.WOOD, [T.CAULDRON]: T.STONE,
    [T.STAIR_UP]: T.MARBLE, [T.STAIR_DN]: T.MARBLE,
  };

  const TEX2TILE = {                    // 地图瓦片 -> 材质名
    [T.GRASS]: 'grass', [T.GRASS2]: 'grass', [T.FLOWER]: 'grass', [T.BUSH]: 'grass',
    [T.TREE]: 'grass', [T.SAKURA]: 'grass', [T.LAMP]: 'grass', [T.FENCE]: 'grass',
    [T.CROP]: 'dirt',
    [T.PATH]: 'stone', [T.SAND]: 'dirt', [T.DIRT]: 'dirt',
    [T.WATER]: 'water',
    [T.WOOD]: 'wood', [T.STONE]: 'marble', [T.TILE_F]: 'marble',
    [T.CARPET_R]: 'marble', [T.CARPET_B]: 'marble',
    [T.WALL_S]: 'stone', [T.WALL_W]: 'wood', [T.ARCH]: 'stone',
    [T.BOOK]: 'wood', [T.TABLE]: 'wood', [T.DESK]: 'wood', [T.BED]: 'wood',
    [T.BARREL]: 'wood', [T.CRATE]: 'wood', [T.CAULDRON]: 'stone',
    [T.ALTAR]: 'marble', [T.FOUNTAIN]: 'stone',
    [T.STAIR_UP]: 'marble', [T.STAIR_DN]: 'marble',
  };
  const TEX_FILES = ['grass', 'stone', 'water', 'dirt', 'wood', 'marble'];
  const TEX_REPEAT = 6;            // 1 次纹理 = 6 格（越大越清楚）

  function loadTextures(base, cb) {
    let left = TEX_FILES.length;
    TEX_FILES.forEach(n => {
      const im = new Image();
      im.onload = () => { TEX[n] = im; if (--left <= 0 && cb) cb(); };
      im.onerror = () => { if (--left <= 0 && cb) cb(); };
      im.src = base + n + '.jpg';
    });
  }

  /** 用等距矩阵 + pattern 画地面（一次填充整个区域，天然无缝） */
  function drawGround(g, spec, DPR) {
    const { ox, oy, u0, v0, u1, v1 } = spec;
    // 按材质分组
    const groups = new Map();
    for (let v = v0; v <= v1; v++) {
      for (let u = u0; u <= u1; u++) {
        if (u < 0 || v < 0 || u >= MW || v >= MH) continue;
        const t = at(u, v);
        // ★ 立体物【也要】铺地面（否则精灵周围露出背景 = 黑方块）
        const gt = GROUND_OF[t] !== undefined ? GROUND_OF[t] : t;
        const name = TEX2TILE[gt] || 'grass';
        if (!groups.has(name)) groups.set(name, []);
        groups.get(name).push([u, v]);
      }
    }
    for (const [name, cells] of groups) {
      const im = TEX[name];
      g.save();
      // 等距矩阵： (u,v) -> (X,Y)，X=(u-v)*TW/2, Y=(u+v)*TH/2
      g.setTransform(DPR || 1, 0, 0, DPR || 1, 0, 0);
      g.translate(ox, oy);
      g.transform(TW / 2 * 1, TH / 2, -TW / 2, TH / 2, 0, 0);
      // ★ 纹理重复尺度：1 次纹理 = TEX_REPEAT 格（放大纹理，避免糊）
      const R = TEX_REPEAT;
      g.scale(R, R);
      g.beginPath();
      for (const [u, v] of cells) g.rect(u / R, v / R, 1 / R, 1 / R);
      if (im && im.naturalWidth) {
        const p = g.createPattern(im, 'repeat');
        g.fillStyle = p;
      } else {
        g.fillStyle = (C[({ grass:'grass', stone:'stone', water:'water', dirt:'dirt', wood:'wood', marble:'tileF' })[name]] || C.grass)[0];
      }
      g.fill();
      g.restore();
    }
  }

  root.TileWorld = {
    T, TW, TH, MW, MH, SOLID, HEIGHT, PAD, GROUND_Y,
    map, at, set, isSolid, isoX, isoY, makeTile, drawTile, loadSprites, drawScene,
    TEX, loadTextures, drawGround, TEX2TILE, GROUND_OF,
    roofAt, buildings, roof, INTERACT, interactAt, buildingAt, roofAlpha, setXray, distToBuilding,
    buildingSolid, buildingRender,
    worldW: MW, worldH: MH,
  };
})(typeof window !== 'undefined' ? window : this);
