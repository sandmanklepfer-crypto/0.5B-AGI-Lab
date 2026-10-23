#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天泪纪元 · 分享海报生成器  v2
--------------------------------------------------------------------------
输出（tianlei3d/poster/）：
  poster_v.png      1080x1920  竖版  —— 微信/QQ/朋友圈、手机分享主用
  poster_h.png      1920x1080  横版  —— 群公告、电脑看、Banner
  poster_sq.png     1080x1080  方版  —— 朋友圈九宫格、小红书
  poster_story.png  1080x1920  大二维码版 —— 面对面扫码 / 打印

关键工程点（v2 修正）：
  1) ★ 字体 fallback：网站自带的 NotoSerifSC.woff2 是"子集字体"（仅 1755 字，
     缺 雨/夜/城/筑/服/享/块/队/友/攒/脑/码 等），直接用它渲染会掉字。
     这里做逐字 fallback：Noto Serif 有的字用它（保留宋体质感），
     缺的字自动落到文泉驿正黑（42318 字，完整），保证一个都不掉。
  2) ★ 排版用 getbbox 取真实行高，不再拿 font.size 当高度（否则标题压住副标题）。
  3) ★ 胶囊/标签"先量后画"：用 dry-run 只测量不落笔，避免量的时候已经画了一个。
  4) ★ emoji 一律不用（字体里没有彩色 emoji），改用可打印的几何符号 ①②③④
     或自绘图标，保证任何设备打开都不出现口字。
"""
import os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IMG  = os.path.join(ROOT, 'site', 'img')
OUT  = os.path.join(ROOT, 'poster')
FONTDIR = os.path.join(ROOT, 'assets', 'fonts')
os.makedirs(OUT, exist_ok=True)

URL = 'https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/tianlei3d/'
URL_SHOW = 'sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/tianlei3d'

SERIF_SRC = os.path.join(FONTDIR, 'NotoSerifSC-Bold.woff2')
SERIF_TTF = '/tmp/NotoSerifSC-Bold.ttf'
HEI = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'      # 完整字集兜底

NEON  = (192, 132, 252)
CYAN  = (34, 211, 238)
GOLD  = (255, 209, 102)
WHITE = (255, 255, 255)
MUTED = (169, 159, 196)

# ---------------------------------------------------------------- 字体
_cmap = None
def serif_cmap():
    """Noto Serif 子集实际覆盖了哪些字"""
    global _cmap
    if _cmap is None:
        f = TTFont(SERIF_TTF, fontNumber=0)
        s = set()
        for t in f['cmap'].tables:
            s |= set(t.cmap.keys())
        _cmap = s
    return _cmap

_fcache = {}
def getfont(path, size):
    k = (path, size)
    if k not in _fcache:
        _fcache[k] = ImageFont.truetype(path, size, index=0) if path.endswith('.ttc') \
                     else ImageFont.truetype(path, size)
    return _fcache[k]

def F(size):
    """正文黑体（完整字集）"""
    return getfont(HEI, size)

def FS(size):
    """标题宋体（可能缺字，必须配合 draw_text 的 fallback）"""
    return getfont(SERIF_TTF, size)


# ---------------------------------------------------------------- 文本绘制（带 fallback）
def _runs(text, size, use_serif):
    """把字符串切成 [(片段, 字体), ...]，Serif 缺的字落到黑体"""
    if not use_serif:
        return [(text, F(size))]
    cm = serif_cmap()
    out, buf, cur = [], '', None
    for ch in text:
        serif_ok = (ord(ch) in cm) and not ch.isspace()
        # 空格/标点统一走黑体更稳
        if ch.isspace() or (ord(ch) not in cm):
            serif_ok = False
        want = 's' if serif_ok else 'h'
        if cur is None:
            cur, buf = want, ch
        elif want == cur:
            buf += ch
        else:
            out.append((buf, FS(size) if cur == 's' else F(size)))
            cur, buf = want, ch
    if buf:
        out.append((buf, FS(size) if cur == 's' else F(size)))
    return out


def text_width(draw, text, size, use_serif=False):
    w = 0
    for seg, f in _runs(text, size, use_serif):
        bb = draw.textbbox((0, 0), seg, font=f)
        w += bb[2] - bb[0]
    return w


def draw_text(base, xy, text, size, fill, use_serif=False, anchor='la', glow=None,
              glow_px=26, stroke=0, stroke_fill=None, alpha=255):
    """
    逐段渲染（支持 fallback）。anchor: 'la' 左对齐 / 'ma' 居中。
    glow=(r,g,b) 时先画一层模糊发光。
    """
    W, H = base.size
    total = text_width(ImageDraw.Draw(base), text, size, use_serif)
    x = xy[0] - (total / 2 if anchor == 'ma' else 0)
    y = xy[1]

    # 基线对齐：取最大 ascent，让不同字体的字落在同一条线上
    fonts = [f for _, f in _runs(text, size, use_serif)]
    asc = max((f.getmetrics()[0] for f in fonts), default=size)

    def paint(target_draw, col, sw=0, sf=None):
        cx = x
        for seg, f in _runs(text, size, use_serif):
            bb = target_draw.textbbox((0, 0), seg, font=f)
            dy = asc - f.getmetrics()[0]          # 对齐基线
            target_draw.text((cx - bb[0], y + dy), seg, font=f, fill=col,
                             stroke_width=sw, stroke_fill=sf)
            cx += bb[2] - bb[0]

    if glow:
        gl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        paint(ImageDraw.Draw(gl), tuple(list(glow) + [255]))
        for _ in range(2):
            gl = gl.filter(ImageFilter.GaussianBlur(glow_px))
        a = gl.split()[3].point(lambda v: min(255, int(v * 2.0)))
        gl.putalpha(a)
        base.alpha_composite(gl)

    d = ImageDraw.Draw(base)
    paint(d, tuple(list(fill) + [alpha]), stroke, stroke_fill)
    return total, asc


def text_height(draw, size, use_serif=False):
    f = FS(size) if use_serif else F(size)
    asc, desc = f.getmetrics()
    return asc + desc


# ---------------------------------------------------------------- 图像工具
def cover(im, W, H, fx=0.5, fy=0.45):
    sw, sh = im.size
    s = max(W / sw, H / sh)
    nw, nh = int(sw * s + 0.5), int(sh * s + 0.5)
    im2 = im.resize((nw, nh), Image.LANCZOS)
    x = int((nw - W) * fx); y = int((nh - H) * fy)
    return im2.crop((x, y, x + W, y + H))


def vgrad(W, H, stops):
    g = Image.new('RGBA', (1, H)); px = g.load()
    for y in range(H):
        t = y / max(1, H - 1)
        col = stops[-1][1]
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]; p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                k = (t - p0) / max(1e-6, p1 - p0)
                col = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(4))
                break
        px[0, y] = col
    return g.resize((W, H), Image.BILINEAR)


def vignette(W, H, strength=0.85):
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).ellipse([-W * 0.3, -H * 0.3, W * 1.3, H * 1.3], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(min(W, H) * 0.18))
    dark = Image.new('RGBA', (W, H), (4, 3, 10, 255))
    dark.putalpha(Image.eval(m, lambda v: int((255 - v) * strength)))
    return dark


def rrect(base, xy, r, fill=None, outline=None, width=2):
    layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)
    base.alpha_composite(layer)


def pill_size(draw, text, size, pad_x=24, pad_y=13):
    bb = draw.textbbox((0, 0), text, font=F(size))
    return (bb[2] - bb[0] + pad_x * 2, bb[3] - bb[1] + pad_y * 2, bb, pad_x, pad_y)


def pill(base, xy, text, size, bg=(255, 209, 102, 34), bd=(255, 209, 102, 150), fg=GOLD):
    d = ImageDraw.Draw(base)
    w, h, bb, px, py = pill_size(d, text, size)
    rrect(base, [xy[0], xy[1], xy[0] + w, xy[1] + h], h // 2, fill=bg, outline=bd, width=2)
    d = ImageDraw.Draw(base)
    d.text((xy[0] + px - bb[0], xy[1] + py - bb[1]), text, font=F(size), fill=tuple(list(fg) + [255]))
    return w, h


def qr_card(url, box, radius=34, pad=26):
    q = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=12, border=0)
    q.add_data(url); q.make(fit=True)
    qi = q.make_image(fill_color=(10, 8, 22), back_color=(255, 255, 255)).convert('RGB')
    inner = box - pad * 2
    qi = qi.resize((inner, inner), Image.NEAREST)
    card = Image.new('RGBA', (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle([0, 0, box - 1, box - 1], radius=radius, fill=(255, 255, 255, 255))
    card.paste(qi, (pad, pad))
    return card


def place_qr(base, url, box, x, y, glow_col=(168, 85, 247, 130), glow_px=32):
    gl = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle([x - 8, y - 8, x + box + 8, y + box + 8],
                                         radius=42, fill=glow_col)
    gl = gl.filter(ImageFilter.GaussianBlur(glow_px))
    base.alpha_composite(gl)
    base.alpha_composite(qr_card(url, box), (x, y))


# ---------------------------------------------------------------- 内容
TITLE  = '天泪纪元'
EN     = 'T I A N L E I   C H R O N I C L E'
SLOGAN = '雨夜之城 · 与人共建'
TAG    = '免费 · 免注册 · 手机电脑都能玩'
POINTS = [
    ('①', '点链接就进',   '不用注册，不用输房间号'),
    ('②', '建筑全服共享', '你放的方块，全世界都看得见'),
    ('③', '多人同屏',     '队友就站在你旁边'),
    ('④', '玩就有积分',   '攒满 100 分解锁神器'),
]


def build_portrait(size=(1080, 1920), big_qr=False, name='poster_v.png'):
    W, H = size
    base = Image.new('RGBA', (W, H), (6, 5, 13, 255))
    bg = cover(Image.open(os.path.join(IMG, 'hero.jpg')).convert('RGB'), W, H, 0.56, 0.26).convert('RGBA')
    bg = Image.blend(bg, Image.new('RGBA', (W, H), (16, 9, 34, 255)), 0.20)
    base.alpha_composite(bg)
    base.alpha_composite(vgrad(W, H, [
        (0.00, (6, 5, 13, 236)),
        (0.13, (6, 5, 13, 165)),
        (0.30, (6, 5, 13, 55)),
        (0.46, (6, 5, 13, 40)),
        (0.62, (7, 5, 14, 130)),
        (0.78, (7, 5, 14, 226)),
        (0.90, (6, 5, 13, 250)),
        (1.00, (6, 5, 13, 255)),
    ]))
    base.alpha_composite(vignette(W, H, 0.92))

    d = ImageDraw.Draw(base)

    # 顶部品牌小字
    draw_text(base, (W // 2, 78), 'T I A N L E I   S T U D I O', 24, (198, 184, 231),
              anchor='ma', alpha=150)

    # 主标题（宋体 + 紫光）
    y = 128
    t_size = 172
    while text_width(d, TITLE, t_size, True) > W - 170 and t_size > 60:
        t_size -= 4
    hh = text_height(d, t_size, True)
    draw_text(base, (W // 2, y), TITLE, t_size, WHITE, use_serif=True, anchor='ma',
              glow=NEON, glow_px=34)
    y += hh + 6

    draw_text(base, (W // 2, y), EN, 24, (188, 168, 228), anchor='ma', alpha=185)
    y += 60

    draw_text(base, (W // 2, y), SLOGAN, 46, (238, 232, 252), use_serif=True, anchor='ma')
    y += text_height(d, 46, True) + 22

    # 标签
    d = ImageDraw.Draw(base)
    tw, th = pill_size(d, TAG, 26)[:2]
    pill(base, ((W - tw) // 2, y), TAG, 26)
    y += th + 40

    # 四宫格
    cw, ch = (W - 148 - 24) // 2, 148
    gx, gy = 74, y
    for i, (num, t1, t2) in enumerate(POINTS):
        cx = gx + (i % 2) * (cw + 24)
        cy = gy + (i // 2) * (ch + 18)
        rrect(base, [cx, cy, cx + cw, cy + ch], 24,
              fill=(15, 11, 30, 200), outline=(168, 85, 247, 90), width=2)
        # 序号圆点
        rrect(base, [cx + 24, cy + 26, cx + 24 + 42, cy + 26 + 42], 21,
              fill=(168, 85, 247, 70), outline=(192, 132, 252, 170), width=2)
        d = ImageDraw.Draw(base)
        bb = d.textbbox((0, 0), num, font=F(24))
        d.text((cx + 24 + 21 - (bb[2] - bb[0]) / 2 - bb[0], cy + 26 + 21 - (bb[3] - bb[1]) / 2 - bb[1]),
               num, font=F(24), fill=(226, 214, 255, 255))
        maxw = cw - 82 - 22                       # 卡片内可用的文字宽度
        s1, s2 = 31, 22
        while text_width(d, t1, s1) > maxw and s1 > 18: s1 -= 1
        while text_width(d, t2, s2) > maxw and s2 > 14: s2 -= 1
        draw_text(base, (cx + 82, cy + 24), t1, s1, WHITE, alpha=250)
        draw_text(base, (cx + 82, cy + 76), t2, s2, MUTED, alpha=235)

    # 二维码（底部）
    box = 404 if big_qr else 366
    qy = H - box - (250 if not big_qr else 210)
    qx = (W - box) // 2

    # 箭头
    d = ImageDraw.Draw(base)
    d.polygon([(W // 2, qy - 26), (W // 2 - 16, qy - 46), (W // 2 + 16, qy - 46)],
              fill=(255, 209, 102, 235))

    place_qr(base, URL, box, qx, qy)

    ty = qy + box + 30
    draw_text(base, (W // 2, ty), '扫码 3 秒进服', 54, WHITE, use_serif=True, anchor='ma',
              glow=(120, 60, 210), glow_px=22)
    ty += text_height(d, 54, True) + 10
    draw_text(base, (W // 2, ty), '免费 · 免注册 · 手机上就能玩', 27, GOLD, anchor='ma', alpha=238)
    ty += 46
    draw_text(base, (W // 2, ty), URL_SHOW, 20, (138, 128, 168), anchor='ma', alpha=205)

    out = os.path.join(OUT, name)
    base.convert('RGB').save(out, 'PNG', optimize=True)
    print(f'  ✅ {name}  {W}x{H}  {os.path.getsize(out) / 1024:.0f} KB')


def build_landscape(size=(1920, 1080), name='poster_h.png'):
    W, H = size
    base = cover(Image.open(os.path.join(IMG, 'hero.jpg')).convert('RGBA'), W, H, 0.66, 0.32)
    base = Image.blend(base, Image.new('RGBA', (W, H), (16, 9, 34, 255)), 0.18)

    left = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(left).rectangle([0, 0, int(W * 0.56), H], fill=(5, 4, 11, 222))
    left = left.filter(ImageFilter.GaussianBlur(72))
    base.alpha_composite(left)
    base.alpha_composite(vgrad(W, H, [(0, (6, 5, 13, 40)), (1, (6, 5, 13, 120))]))
    base.alpha_composite(vignette(W, H, 0.82))

    d = ImageDraw.Draw(base)
    x, y = 104, 112
    draw_text(base, (x, y), 'T I A N L E I   S T U D I O', 21, (198, 184, 231), alpha=145)
    y += 58

    t_size = 118
    while text_width(d, TITLE, t_size, True) > W * 0.44 and t_size > 50:
        t_size -= 3
    draw_text(base, (x, y), TITLE, t_size, WHITE, use_serif=True, glow=NEON, glow_px=26)
    y += text_height(d, t_size, True) + 2

    draw_text(base, (x, y), EN, 21, (188, 168, 228), alpha=180)
    y += 54
    draw_text(base, (x, y), SLOGAN, 40, (238, 232, 252), use_serif=True)
    y += text_height(d, 40, True) + 24

    d = ImageDraw.Draw(base)
    tw, th = pill_size(d, TAG, 23)[:2]
    pill(base, (x, y), TAG, 23)
    y += th + 42

    for num, t1, t2 in POINTS:
        rrect(base, [x, y + 4, x + 30, y + 34], 15, fill=(168, 85, 247, 60),
              outline=(192, 132, 252, 150), width=1)
        d = ImageDraw.Draw(base)
        bb = d.textbbox((0, 0), num, font=F(18))
        d.text((x + 15 - (bb[2] - bb[0]) / 2 - bb[0], y + 19 - (bb[3] - bb[1]) / 2 - bb[1]),
               num, font=F(18), fill=(226, 214, 255, 255))
        maxw = int(W * 0.56) - x - 46 - 40
        s1, s2 = 27, 21
        while text_width(d, t1 + '  · ' + t2, s1, False) > maxw and s1 > 17:
            s1 -= 1; s2 = max(14, s2 - 1)
        wt1, _ = draw_text(base, (x + 46, y), t1, s1, WHITE, alpha=250)
        draw_text(base, (x + 46 + wt1 + 14, y + 5), '· ' + t2, s2, MUTED, alpha=228)
        y += 52

    box = 296
    qx, qy = W - box - 104, H - box - 96
    place_qr(base, URL, box, qx, qy, glow_px=30)
    draw_text(base, (qx + box // 2, qy - 48), '扫码 3 秒进服', 34, WHITE,
              use_serif=True, anchor='ma', glow=(120, 60, 210), glow_px=16)

    out = os.path.join(OUT, name)
    base.convert('RGB').save(out, 'PNG', optimize=True)
    print(f'  ✅ {name}  {W}x{H}  {os.path.getsize(out) / 1024:.0f} KB')


def build_square(size=(1080, 1080), name='poster_sq.png'):
    """方版：左上标题 / 右下二维码 的对角构图 —— 不压角色脸"""
    W, H = size
    base = cover(Image.open(os.path.join(IMG, 'hero.jpg')).convert('RGBA'), W, H, 0.72, 0.20)
    base = Image.blend(base, Image.new('RGBA', (W, H), (16, 9, 34, 255)), 0.16)
    base.alpha_composite(vgrad(W, H, [
        (0.00, (6, 5, 13, 205)), (0.20, (6, 5, 13, 90)),
        (0.42, (6, 5, 13, 30)), (0.66, (6, 5, 13, 95)),
        (0.86, (6, 5, 13, 214)), (1.00, (6, 5, 13, 250)),
    ]))
    base.alpha_composite(vignette(W, H, 0.86))

    # ★ 左上角局部压暗：原图左上有一行残留字迹，盖掉它
    corner = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(corner)
    cd.ellipse([-int(W * 0.30), -int(H * 0.30), int(W * 0.72), int(H * 0.52)],
               fill=(6, 5, 13, 205))
    corner = corner.filter(ImageFilter.GaussianBlur(int(W * 0.075)))
    base.alpha_composite(corner)

    d = ImageDraw.Draw(base)

    # ---- 左上：标题 ----
    x, y = 72, 66
    draw_text(base, (x, y), 'T I A N L E I', 20, (198, 184, 231), alpha=140)
    y += 44
    t_size = 104
    while text_width(d, TITLE, t_size, True) > W * 0.60 and t_size > 44:
        t_size -= 3
    draw_text(base, (x, y), TITLE, t_size, WHITE, use_serif=True, glow=NEON, glow_px=26)
    y += text_height(d, t_size, True) + 4
    draw_text(base, (x, y), SLOGAN, 30, (238, 232, 252), use_serif=True)
    y += text_height(d, 30, True) + 18
    d = ImageDraw.Draw(base)
    tw, th = pill_size(d, '免费 · 免注册', 22)[:2]
    pill(base, (x, y), '免费 · 免注册', 22)

    # ---- 右下：二维码 ----
    box = 300
    qx, qy = W - box - 66, H - box - 104
    place_qr(base, URL, box, qx, qy, glow_px=28)
    draw_text(base, (qx + box // 2, qy - 40), '扫码 3 秒进服', 30, WHITE,
              use_serif=True, anchor='ma', glow=(120, 60, 210), glow_px=14)

    # ---- 左下：一行卖点（贴着二维码左边，不压角色） ----
    lines = ['建筑全服共享 · 多人同屏', '玩就送积分 · 攒满解锁神器']
    ly = H - 138
    for ln in lines:
        draw_text(base, (72, ly), ln, 22, (214, 203, 240), alpha=232)
        ly += 36

    out = os.path.join(OUT, name)
    base.convert('RGB').save(out, 'PNG', optimize=True)
    print(f'  ✅ {name}  {W}x{H}  {os.path.getsize(out) / 1024:.0f} KB')


if __name__ == '__main__':
    if not os.path.exists(SERIF_TTF):
        f = TTFont(SERIF_SRC); f.flavor = None; f.save(SERIF_TTF)
    print('生成海报 …')
    build_portrait()
    build_landscape()
    build_square()
    build_portrait((1080, 1920), big_qr=True, name='poster_story.png')
    print('完成 →', OUT)
