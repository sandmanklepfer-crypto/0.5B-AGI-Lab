# -*- coding: utf-8 -*-
"""★ 全套组装: 搜索 + 验证器 + 模型提议 + 错题本
   任务: 规律发现 (这是"像人一样"的核心动作: 提假设→验证→修正)"""
import json, urllib.request, re, itertools, math, time
import sympy as sp
from sympy import symbols, factorial, primerange, fibonacci, simplify, Symbol
n=Symbol('n', integer=True, positive=True)
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=120,t=0.2):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"

# ============ ① 搜索空间 (原子规律) ============
ATOMS={
 'n':        lambda k: k,
 'n^2':      lambda k: k**2,
 'n^3':      lambda k: k**3,
 'n^4':      lambda k: k**4,
 '2^n':      lambda k: 2**k,
 '3^n':      lambda k: 3**k,
 'n!':       lambda k: math.factorial(k),
 'fib':      lambda k: [0,1,1,2,3,5,8,13,21,34,55,89,144,233,377,610,987][k] if k<17 else 0,
 'prime':    lambda k: list(primerange(1,200))[k-1] if k>=1 else 0,
 'n(n+1)/2': lambda k: k*(k+1)//2,
 'n(n+1)(2n+1)/6': lambda k: k*(k+1)*(2*k+1)//6,
 '2n-1':     lambda k: 2*k-1,
 'n^2+n':    lambda k: k*k+k,
 'binomial': lambda k: math.comb(2*k, k),
 'catalan':  lambda k: math.comb(2*k,k)//(k+1),
}
# ============ ② 验证器 (精确) ============
def verify(fn, seq, k0=1):
    """精确验证: 数列前len项是否全部匹配"""
    try:
        for i,v in enumerate(seq):
            if fn(k0+i)!=v: return False
        return True
    except Exception: return False

def predict(fn, k0, L, cnt=2):
    try: return [fn(k0+L+i) for i in range(cnt)]
    except Exception: return None

# ============ ③ 测试集: 5个难度级别 ============
TASKS=[
 ("L1 单项 (n²)",        [1,4,9,16,25],        [36,49]),
 ("L2 线性组合 (n²+2n)",  [3,8,15,24,35],       [48,63]),
 ("L3 指数 (2^n)",       [2,4,8,16,32],        [64,128]),
 ("L4 组合 (fib+n)",     [1,2,4,7,11],         [16,22]),
 ("L5 复杂 (catalan)",   [1,2,5,14,42],        [132,429]),
]
print("="*94); print("★ 全套系统: 规律发现 (搜索+验证器+模型提议)"); print("="*94, flush=True)
for tag,seq,nxt in TASKS:
    print(f"\n{'─'*88}", flush=True)
    print(f"[{tag}]  已知: {seq}   求下两项 (真值 {nxt})", flush=True)
    # --- 路径A: 纯搜索 (穷举原子 + 线性组合) ---
    t0=time.time(); foundA=None
    for name,fn in ATOMS.items():
        if verify(fn,seq): foundA=(name,predict(fn,1,len(seq))); break
    if not foundA:   # 试二元线性组合 a*f+b*g
        for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
            for a in range(1,5):
                for b in range(-3,4):
                    if b==0: continue
                    g=lambda k,f1=f1,f2=f2,a=a,b=b: a*f1(k)+b*f2(k)
                    if verify(g,seq): foundA=(f"{a}*{n1}+{b}*{n2}",predict(g,1,len(seq))); break
                if foundA: break
            if foundA: break
    tA=time.time()-t0
    # --- 路径B: 模型提议 ---
    a=ask(f"数列: {seq}\n它的规律是什么? 下一项是什么? 用一行回答: 规律=..., 下一项=...")
    print(f"  搜索: {'✅ '+foundA[0]+' -> '+str(foundA[1]) if foundA else '❌ 未找到'}  ({tA*1000:.0f}ms)", flush=True)
    print(f"  模型: {a[:110]}", flush=True)
    ok = foundA and list(foundA[1])[:2]==list(nxt)
    print(f"  → {'✅ 搜索命中' if ok else '⚠️'}", flush=True)
print("\n"+"="*94); print("★ 对照: 纯模型 vs 人 (基准)"); print("="*94, flush=True)
print("  人: 看5项就能猜对 L1-L4, L5需要知道Catalan数", flush=True)
print("\nHUMAN_DONE")
