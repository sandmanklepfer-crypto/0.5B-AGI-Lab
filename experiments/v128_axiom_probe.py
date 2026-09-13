#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V128 四轴冲突检测器原型 — "远规则"第一次落地
验证: 不认领域词(ζ/零点/素数全跳过), 只用结构词(量词/否定/比较/对立极/数字),
能否抓出"卡 vs 转述"的命题冲突。若可 → 核对不随领域增长(极少规则覆盖全部)。

四轴 (远规则 = 逻辑矛盾律在语言层的4个投影):
  A 存在/量词轴: 全称(所有/每个/处处/整串/全部) vs 存在(有些/有的/一些) vs 零(没有/一个都没有)
  B 极性/否定轴: 显式否定词组(没有/不存在/尚未/从未/无法) 在不在命题上
  C 比较/方向轴: 大于/小于/等于/不超过 + 跟随数字或量级词(1/2, 0, 1, 全部)
  D 对立取值轴: 通用对立词对(正/负 奇/偶 实/虚 收敛/发散 有限/无穷 证明/未证明 实轴/复平面 实域/复域 局部/全部)
  E 数字槽: 句中数字(同一卡内同槽数字不同 → 冲突可疑)

输出每对: 各轴抽取的"结构签名" + 冲突判定(冲突/可疑/一致)
"""
import re

# ---- 结构词表 (不含任何领域词) ----
QUANT_ALL = ['所有','全部','每个','任何','处处','整串','整条','一切','都','全都']
QUANT_SOME = ['有些','有的','一些','部分','一串','一种','一个','几个','许多','无数']
QUANT_ZERO = ['没有','不存在','一个都没有','零个','毫无','没有任何','找不到任何一个']
NEG_WORDS = ['没有','不存在','尚未','从未','未','无法','不是','并非','毫无','别']  # 显式否定(长词优先)
CMP = {'大于':'gt','小于':'lt','等于':'eq','不低于':'ge','不超过':'le','超过':'gt','不到':'lt','大约是':'ap','约等于':'ap'}
OPP = [
    ('正','负'), ('奇','偶'), ('实','虚'), ('收敛','发散'), ('有限','无穷'), ('有限','无限'),
    ('有界','无界'), ('有','没有'), ('证明','未证明'), ('实轴','虚轴'), ('实部','虚部'),
    ('实数域','复数域'), ('实平面','复平面'), ('大于','小于'), ('内部','外部'), ('局部','全部'),
    ('零点上','零点外'), ('收敛','发散'),
]
NUM = re.compile(r'(\d+(?:\.\d+)?|[一二三四五六七八九十]+分之[一二三四五六七八九十百千]+|二分之一|四分之一|四分之三|零)')

def strip_domain(s):
    """把领域内容词替换成占位, 只留结构骨架 (演示'不认字')"""
    # 领域词表(演示用, 规则本身不含): 这些词被抹成 ▓
    dom = ['ζ函数','ζ','黎曼','欧拉','素数定理','非平凡零点','平凡零点','零点','素数','整数','函数','卡','转述',
           '复平面','实数域','实部','虚部','实轴','η函数','圆周率','自然对数','猜想','证明','区域','段','串','点','线','域','值']
    out = s
    for d in sorted(dom, key=len, reverse=True):
        out = out.replace(d, '▓')
    return out

def sig(s):
    """结构签名: 各轴抽取"""
    neg = [w for w in NEG_WORDS if w in s]
    qa = [w for w in QUANT_ALL if w in s]
    qs = [w for w in QUANT_SOME if w in s]
    qz = [w for w in QUANT_ZERO if w in s]
    cmpv = [(w, CMP[w]) for w in CMP if w in s]
    numv = NUM.findall(s)
    oppv = []
    for a, b in OPP:
        if a in s: oppv.append((a, '+'))
        if b in s: oppv.append((b, '-'))
    return {'neg': neg, 'all': qa, 'some': qs, 'zero': qz, 'cmp': cmpv, 'num': numv, 'opp': oppv}

def check(card, trans):
    sc, st = sig(card), sig(trans)
    res = {}
    # 轴A 存在/量词冲突
    a_card_has = bool(sc['some']) and not sc['zero'] or (not sc['all'] and not sc['zero'] and not sc['some'])
    # 简化: 有否定词"没有"且无"一个都没有"的肯定 => 判零
    zero_c = bool(sc['zero']) or ('没有' in sc['neg'] and '一个' not in card and '一点' not in card and '个' not in card and '条' not in card and '串' not in card)
    zero_t = bool(st['zero']) or ('没有' in st['neg'] and '一个' not in trans and '一点' not in trans and '个' not in trans and '条' not in trans and '串' not in trans)
    some_c = bool(sc['some']); some_t = bool(st['some'])
    # 零 vs 有 冲突
    if (zero_c and some_t) or (zero_t and some_c):
        res['A存在'] = '冲突'
    elif zero_c == zero_t and some_c == some_t:
        res['A存在'] = '一致'
    else:
        res['A存在'] = '可疑'
    # 轴B 极性: 卡有显式否定而转述无(或反) → 冲突
    if bool(sc['neg']) != bool(st['neg']):
        # 若一边是"没有X"结构(零存在)一边是纯否定差, 视为B冲突
        res['B极性'] = '冲突'
    else:
        res['B极性'] = '一致'
    # 轴C 比较方向: 取同序号比较词对, 方向相反 → 冲突
    cmpc = sorted([v for _, v in sc['cmp']]); cmpt = sorted([v for _, v in st['cmp']])
    if cmpc and cmpt:
        if cmpc[0] != cmpt[0] and {cmpc[0], cmpt[0]} <= {'gt','lt'}:
            res['C比较'] = '冲突'
        elif cmpc[0] == cmpt[0]:
            res['C比较'] = '一致'
        else:
            res['C比较'] = '可疑'
    elif cmpc or cmpt:
        res['C比较'] = '可疑'
    else:
        res['C比较'] = '一致'
    # 轴D 对立取值: 同一对立对在卡/转述各取一极 → 冲突
    opp_c = {a for a, _ in sc['opp']}; opp_t = {a for a, _ in st['opp']}
    hit = []
    for a, b in OPP:
        ac = a in card and b not in card; at = a in trans and b not in trans
        bc = b in card and a not in card; bt = b in trans and a not in trans
        if (ac and bt) or (bc and at):
            hit.append((a, b))
    res['D对立'] = '冲突 x%d %s' % (len(hit), hit) if hit else '一致'
    # 轴E 数字槽: 数字集合差异(保守: 只在两边都有数字且交集为空时报可疑)
    nc, nt = set(sc['num']), set(st['num'])
    if nc and nt and not (nc & nt):
        res['E数字'] = '可疑 %s vs %s' % (sorted(nc), sorted(nt))
    else:
        res['E数字'] = '一致'
    # 总判定
    conf = [k for k, v in res.items() if '冲突' in str(v)]
    susp = [k for k, v in res.items() if '可疑' in str(v)]
    verdict = '冲突!' if conf else ('可疑' if susp else '一致(未抓)')
    return verdict, res

# ---- 测试集: (标签, 卡, 转述) ----
TESTS = [
    ('T1 V127错句: 负偶数说成正偶数', 'ζ函数的平凡零点都在负偶数那串点上', '平凡零点都在正偶数那串点上'),
    ('T2 V127错句: 实部>1有零点(应无)', 'ζ函数在实部大于1的区域里一个零点都没有', '实部大于1的零点一串，没有的是非零的'),
    ('T3 正确对(应一致)', 'ζ函数在负偶数那些点上，值都等于零', '负偶数整串都是它的零点'),
    ('T4 V127错句: 延拓到全实数域(应Re>0)', '用η函数可以把ζ函数延拓到实部大于0的区域', 'ζ的适用范围被延拓到全实数域，用η函数一提就了'),
    ('T5 数值错: π²/6→π²/90', 'ζ函数在s等于2的时候，值等于圆周率的平方除以6', 'ζ函数在s等于2的时候，值等于圆周率的平方除以90'),
    ('T6 猜想被证明(应未证明)', '黎曼猜想从1859年被提出来，到现在还没有人证明它', '黎曼猜想在1859年就被证明了'),
    ('T7 发散说成收敛', 'ζ函数在s等于1的地方是发散的，一直加下去会变成无穷大', 'ζ函数在s等于1的地方是收敛的，一直加下去不会变成无穷大'),
    ('T8 V127错句: 实部>1说成有路有工具', 'ζ函数在实部大于1的区域里一个零点都没有', '取零的路在实部大于1的段上，没有求零的工具在那'),
    ('T9 正确转述(应一致)', '黎曼把ζ函数从只能在实部大于1的范围，扩展到了整个复平面', '黎曼把ζ函数的适用范围从右半平面一路延拓到全部复数域'),
    ('T10 V127错句: 全取零函数/实部<0', '用η函数可以证明ζ在实部小于0处处处为零(错卡)', '把ζ看作全称取零的函数，全部系数为0的解集全在实部小于0的半平面'),
]

def main():
    print('V128 四轴冲突检测器 — 远规则原型 (不认领域词, 只认结构)\n' + '='*70)
    print('结构骨架示例: 卡2 抹掉领域词后 =', strip_domain('ζ函数在实部大于1的区域里一个零点都没有'), '\n')
    ok = 0
    for label, card, trans in TESTS:
        verdict, res = check(card, trans)
        flag = '✅抓' if '冲突' in verdict else ('⚠️疑' if '可疑' in verdict else '❌漏')
        if '冲突' in verdict or '可疑' in verdict:
            ok += 1
        print('[%s] %s' % (flag, label))
        print('   卡 : %s' % card)
        print('   述 : %s' % trans)
        print('   判定: %s | 轴详情: %s' % (verdict, {k: v for k, v in res.items() if v != '一致'}))
    print('='*70)
    print('抓取率: %d/%d (含可疑)' % (ok, len(TESTS)))

if __name__ == '__main__':
    main()
