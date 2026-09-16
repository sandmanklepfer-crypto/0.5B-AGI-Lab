# -*- coding: utf-8 -*-
"""验证器栈 — 每层可执行判定, 返回(通过?, 理由)"""
import re, math, json

# ---- L1 可执行 (数学/逻辑: 零参数, 100%) ----
def v_arith(expr, claim):
    """验证算术断言"""
    try:
        v=eval(expr,{"__builtins__":{}},{})
        return abs(float(v)-float(claim))<1e-9, f"{expr}={v}"
    except Exception as e: return False, f"无法求值:{e}"
def v_poly_root(coef, x, val=0):
    """验证 x 是多项式(系数列表)的根"""
    r=0
    for c in reversed(coef): r=r*x+c
    return abs(r-val)<1e-9, f"p({x})={r}"
def v_prime(n, claim):
    if n<2: return claim is False, f"{n}<2 非素数"
    ok=all(n%i for i in range(2,int(n**.5)+1))
    return ok==claim, f"{n} {'是' if ok else '非'}素数"
# ---- L2 形式检查 (结构/语法: ~100%) ----
def v_format(text, rules):
    """rules: {'min_len':n,'max_len':n,'must':[..],'must_not':[..],'regex':pat}"""
    errs=[]
    if 'min_len' in rules and len(text)<rules['min_len']: errs.append('太短')
    if 'max_len' in rules and len(text)>rules['max_len']: errs.append('太长')
    for w in rules.get('must',[]):
        if w not in text: errs.append(f'缺"{w}"')
    for w in rules.get('must_not',[]):
        if w in text: errs.append(f'不该有"{w}"')
    if 'regex' in rules and not re.search(rules['regex'],text): errs.append('格式不符')
    return len(errs)==0, ';'.join(errs) if errs else 'ok'
def v_types(token_tags, gram):
    """语法检查: 用词性序列验证基本句型"""
    RULES=[('NP',['N']),('NP',['R']),('NP',['M','Q']),('NP',['A','N']),
           ('NP',['N','N']),('VP',['V']),('VP',['V','NP']),('VP',['A']),
           ('S',['NP','VP']),('S',['NP','VP','NP']),('S',['NP','A'])]
    tags=[gram.get(t,t) for t in token_tags]
    n=len(tags)
    if n<2: return False,'太短'
    ch=[[set() for _ in range(n+1)] for _ in range(n+1)]
    for i,t in enumerate(tags): ch[i][i+1].add(t)
    for i in range(n):
        for _ in range(3):
            for l,r in RULES:
                if len(r)==1 and r[0] in ch[i][i+1]: ch[i][i+1].add(l)
    for sp in range(2,n+1):
        for i in range(n-sp+1):
            j=i+sp
            for k in range(i+1,j):
                for l,r in RULES:
                    if len(r)==2 and r[0] in ch[i][k] and r[1] in ch[k][j]: ch[i][j].add(l)
            for _ in range(3):
                for l,r in RULES:
                    if len(r)==1 and r[0] in ch[i][j]: ch[i][j].add(l)
    return ('S' in ch[0][n]), ('合规' if 'S' in ch[0][n] else '不合规')
# ---- L3 检索比对 (事实验证) ----
def v_knowledge(text, kb):
    """检查文本中的断言是否与知识库一致(简化: 关键词匹配)"""
    hits=[k for k in kb if k in text]
    return len(hits)>0, f"命中知识:{hits}" if hits else "无依据"
# ---- L3.5 一致性 (矛盾检测) ----
def v_consistency(new, history):
    """新回复与历史是否矛盾: 词典分词 + 极性对比"""
    try:
        import lexicon as LX
        toks=lambda t:[w for w,_ in LX.cut(t) if len(w)>=2]
    except Exception:
        toks=lambda t:re.findall(r'[\u4e00-\u9fa5]{2,}',t)
    NEG=['不','没','无','非','别','拒绝','反对']
    def pol(t): return sum(1 for w in NEG if w in t)%2
    for h in history:
        ents=set(toks(new)) & set(toks(h))
        ents={e for e in ents if e not in ('一个','这个','那个')}
        if ents and pol(new)!=pol(h):
            return False, f"可能与历史矛盾(共享:{list(ents)[:3]})"
    return True,'ok'
# ---- L4 重复检测 ----
def v_repetition(text, n=3):
    """检查是否有 n-gram 过度重复"""
    toks=re.findall(r'[\u4e00-\u9fa5]|[a-zA-Z]+',text)
    if len(toks)<n+2: return True,'短文本'
    grams=[tuple(toks[i:i+n]) for i in range(len(toks)-n+1)]
    from collections import Counter
    c=Counter(grams)
    top=c.most_common(1)
    if top and top[0][1]>=2: return False, f"重复{top[0][1]}次:{''.join(top[0][0])}"
    return True,'ok'
# ---- L5 结构完整性 (叙事) ----
def v_narrative(text, rules=None):
    """叙事硬约束: 时间线/人称/长度"""
    rules=rules or {}
    errs=[]
    if len(text)<rules.get('min_len',20): errs.append('叙事过短')
    # 人称一致
    p1=len(re.findall(r'我',text)); p3=len(re.findall(r'他|她|它',text))
    if p1>0 and p3>0 and rules.get('strict_person'):
        errs.append('人称混用')
    return len(errs)==0, ';'.join(errs) if errs else 'ok'

STACK={1:v_arith,2:v_format,3:v_knowledge,4:v_consistency,5:v_repetition,6:v_narrative}
if __name__=='__main__':
    print("验证器栈:")
    print("  L1 算术:",v_arith("37*23",851))
    print("  L1 素数:",v_prime(97,True))
    print("  L2 格式:",v_format("这是一段测试文本",{'min_len':5,'must':['测试']}))
    print("  L2 类型:",v_types(['r','v','n'],{'r':'R','v':'V','n':'N'}))
    print("  L4 重复:",v_repetition("我我我我我我"))
    print("  L3 一致:",v_consistency("我不喜欢苹果",["我喜欢苹果"]))
