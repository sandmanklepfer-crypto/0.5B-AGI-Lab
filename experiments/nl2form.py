# -*- coding: utf-8 -*-
"""NL->形式 翻译的覆盖率分析 (纯本地, 零成本)"""
import re, itertools, math

# ========== 同一个形式任务的多种自然语言说法 ==========
# 形式目标: calc(a*b), calc(a+b), solve(a*x=b), diff(f,x)
def T(expr): return f"<calc>{expr}</calc>"

# 一个任务("求 a 乘 b")的自然语言变体 —— 真实语料里的说法
PHRASINGS_MUL = [
 "计算：{a}乘以{b}等于多少？", "计算 {a}乘以{b}等于多少",
 "{a}乘{b}等于几", "{a}乘上{b}是多少", "{a}×{b}=?", 
 "求{a}和{b}的乘积", "帮我算{a}乘以{b}", "{a}乘以{b}等于多少",
 "{a} * {b} 等于几", "请计算{a}×{b}", "算一下{a}乘{b}",
 "{a}与{b}相乘是多少", "what is {a} times {b}", "compute {a}*{b}",
 "{a}倍的{b}是多少", "{a}个{b}相加是多少",   # ★ 语义等价但形式不同!
 "把{a}重复加{b}次",                        # ★ 需要转化
 "如果每份{b}个, 共{a}份, 总共多少",         # ★ 应用题
]
PHRASINGS_ADD = [
 "计算 {a}+{b} 等于多少", "计算：{a}加{b}等于多少？",
 "{a}加上{b}是多少", "{a}+{b}=?", "求{a}与{b}的和",
 "把{a}和{b}加起来", "{a} plus {b}", "sum of {a} and {b}",
 "从{a}开始数{b}个是多少",                   # ★ 需要转化
]

print("="*94); print("★ 自然语言 → 形式任务 的覆盖率分析"); print("="*94, flush=True)
print("  形式目标:  计算 a*b  →  <calc>a*b</calc>", flush=True)

# ========== 方法1: 逐字模板匹配 (最朴素, 就是模型在做的事) ==========
def translator_templates(text, tmpls):
    for t in tmpls:
        # 模板里 {a}{b} 是槽位
        pat = re.escape(t).replace(r'\{a\}', r'(\d+)').replace(r'\{b\}', r'(\d+)')
        m = re.match('^'+pat+'$', text.strip())
        if m: return T(f"{m.group(1)}*{m.group(2)}")
    return None

print("\n" + "─"*90, flush=True)
print("【方法1】逐字模板匹配 (模型实际在做的事: 记住每个问法)", flush=True)
print("─"*90, flush=True)
for n in [1,3,5,10,15,len(PHRASINGS_MUL)]:
    tmpls = PHRASINGS_MUL[:n]
    hits=0
    for p in PHRASINGS_MUL:
        if translator_templates(p.format(a=37,b=23), tmpls): hits+=1
    print(f"  记住 {n:2d} 个模板 -> 覆盖 {hits}/{len(PHRASINGS_MUL)} = {100*hits/len(PHRASINGS_MUL):3.0f}%", flush=True)

# ========== 方法2: 关键词+槽位 (稍有泛化) ==========
def translator_kw(text):
    t=text.strip()
    m=re.search(r'(\d+)\s*(?:乘以|乘上|乘|×|\*|times|倍的|个)', t)
    n=re.search(r'(?:乘|×|\*|times)\s*(\d+)|(\d+)\s*(?:相加|重复)', t)
    if m:
        a=m.group(1)
        # 找第二个数
        nums=re.findall(r'\d+', t)
        if len(nums)>=2:
            a,b=[x for x in nums[:2]]
            return T(f"{a}*{b}")
    return None

print("\n" + "─"*90, flush=True)
print("【方法2】关键词+槽位 (更泛化, 但仍靠词表)", flush=True)
print("─"*90, flush=True)
hit=0; missed=[]
for p in PHRASINGS_MUL:
    t=p.format(a=37,b=23)
    r=translator_kw(t)
    if r and r==T("37*23"): hit+=1
    else: missed.append(p)
print(f"  覆盖 {hit}/{len(PHRASINGS_MUL)} = {100*hit/len(PHRASINGS_MUL):.0f}%", flush=True)
print(f"  漏掉的问法:", flush=True)
for p in missed[:8]: print(f"     {p}", flush=True)

print("\n" + "─"*90, flush=True)
print("【关键: 组合爆炸】一个任务有多少种说法?", flush=True)
print("─"*90, flush=True)
V=dict(
 动词=["计算","求","算","帮我算","算一下","求值","evaluate","compute","what is",""],
 连词=["乘以","乘上","乘","×","*","times","乘以...的",""],
 询问=["等于多少","等于几","是多少","是几","=?","",  "为多少","结果是什么"],
 语序=["AB","BA"],
 括号=["","（","请","麻烦"],
)
c=1
for k,v in V.items(): c*=len(v)
print(f"  动词{len(V['动词'])} × 连词{len(V['连词'])} × 询问{len(V['询问'])} × 语序{len(V['语序'])} × 语气{len(V['括号'])}", flush=True)
print(f"  = {c:,} 种说法 (还没算'应用题'这种语义转化)", flush=True)
print(f"\n  ★ 模型要100%覆盖, 需要记 {c:,} 个模板", flush=True)
print(f"  ★ 而 calc_v1 的400条训练数据, 最多覆盖几十种", flush=True)
print(f"  ★ 所以覆盖率 ≈ 训练样本数 / 说法总数 = 极低", flush=True)

print("\n" + "─"*90, flush=True)
print("【最后一层: 语义转化 (不是换说法, 是要懂意思)】", flush=True)
print("─"*90, flush=True)
SEM=[
 ("如果每份23个, 共37份, 总共多少", "37*23", "数量×单价 → 乘法"),
 ("把37重复加23次",              "37*23", "'重复加n次' → 乘法"),
 ("37个23相加",                  "37*23", "'n个m相加' → 乘法"),
 ("一个长方形长37宽23, 面积",     "37*23", "几何 → 乘法"),
 ("每秒钟37米, 走23秒, 距离",     "37*23", "物理 → 乘法"),
]
print(f"  {'自然语言':<32}{'正确形式':<12}{'需要的知识'}", flush=True)
print("  "+"-"*76, flush=True)
for nl,form,know in SEM:
    print(f"  {nl:<32}{form:<12}{know}", flush=True)
print(f"\n  ★ 这些【不是换说法】, 是【换语义】——必须懂'面积/距离/重复'都是乘法", flush=True)
print(f"  ★ 模板匹配完全失效; 这需要【世界知识 + 概念映射】", flush=True)
print("\nDONE")
