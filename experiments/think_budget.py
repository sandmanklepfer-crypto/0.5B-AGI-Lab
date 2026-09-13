# -*- coding: utf-8 -*-
"""think_budget.py — 「思考预算」真实实验
   对比 4 种模式在同一批题上的表现:
     A. 直接答            (无思考)
     B. 先想再答          (CoT)
     C. 想+自检+重答      (3轮)
     D. 多候选投票        (3路采样选一致)
   目标: 量化"用满思考预算"到底能提升多少
"""
import numpy as np, time, warnings, re
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪"%(time.time()-t0),flush=True)

def gen(user, maxn=60, temp=0.7, seed=0, stop_ids=(151645,)):
    ids=TK.encode("<|im_start|>user\n"+user+"<|im_end|>\n<|im_start|>assistant\n")
    out,_=M.gen(ids,max_new=maxn,temp=temp,top_k=40,seed=seed)
    # 截断到停止符
    res=[]
    for t in out:
        if t in stop_ids: break
        res.append(t)
    return TK.decode(res).strip()

# ---------- 测试题(有确定答案) ----------
CASES=[
 ("小明比小红大3岁，小红比小刚大2岁，那么小明比小刚大几岁？只回答数字。","5"),
 ("一只蜗牛白天爬3米，晚上滑下2米，井深10米。几天能爬出去？只回答数字。","8"),
 ("1+2+3+4+5等于多少？只回答数字。","15"),
 ("笼子里有鸡和兔共10只，共有28条腿，兔子有几只？只回答数字。","4"),
 ("一个数是另一个数的3倍，两数之和是20，较小的数是多少？只回答数字。","5"),
 ("100减37等于多少？只回答数字。","63"),
]

def extract_num(s):
    m=re.findall(r"-?\d+", s)
    return m[-1] if m else ""

print("\n"+"="*70)
print("  测试: 0.5B 在 6 道题上的表现 (四种思考预算)")
print("="*70)

# ---------- A. 直接答 ----------
print("\n[A] 直接答", flush=True)
resA=[]
for q,g in CASES:
    t1=time.time()
    a=gen(q, maxn=12, temp=0.3, seed=1)
    ok = (extract_num(a)==g)
    resA.append(ok)
    print("   %-32s → %-8s gold=%s %s [%.0fs]"%(q[:30], a[:12].replace("\n"," "), g,
          "✅" if ok else "❌", time.time()-t1), flush=True)
accA=100*sum(resA)/len(resA)

# ---------- B. 先想再答 (CoT) ----------
print("\n[B] 先想再答(CoT)", flush=True)
resB=[]
for q,g in CASES:
    t1=time.time()
    cot = gen("请一步一步思考，然后回答。\n问题："+q, maxn=90, temp=0.7, seed=2)
    a=gen("根据你的思考，最终答案是什么？只回答数字。", maxn=10, temp=0.3, seed=3)
    ok = (extract_num(a)==g) or (g in extract_num(cot))
    resB.append(ok)
    print("   → %-8s gold=%s %s [%.0fs]"%(a[:10].replace("\n"," "),g,"✅" if ok else "❌",time.time()-t1),flush=True)
accB=100*sum(resB)/len(resB)

# ---------- C. 想+自检+重答 ----------
print("\n[C] 想+自检+重答(最多3轮)", flush=True)
resC=[]
for q,g in CASES:
    t1=time.time(); ok=False; logs=[]
    draft=gen(q, maxn=60, temp=0.7, seed=4)
    for rnd in range(3):
        chk=gen("请检查下面这个回答是否正确，如果有错请指出正确值和理由。\n问题："+q[:60]+"\n回答："+draft[:150]+"\n你的检查：",
                maxn=70, temp=0.7, seed=10+rnd)
        logs.append(len(chk))
        newa=gen("基于你的检查，最终答案是什么？只回答数字。", maxn=10, temp=0.3, seed=20+rnd)
        v=extract_num(newa)
        if v==g: ok=True
        draft = draft+" [修正]" + v
        if ok: break
    resC.append(ok)
    print("   → %s (检查%d轮) %s [%.0fs]"%(g, len(logs), "✅" if ok else "❌", time.time()-t1),flush=True)
accC=100*sum(resC)/len(resC)

# ---------- D. 多候选投票 ----------
print("\n[D] 多候选投票(3路)", flush=True)
resD=[]
for q,g in CASES:
    t1=time.time(); votes=[]
    for s in range(3):
        a=gen(q, maxn=14, temp=0.9, seed=100+s)
        votes.append(extract_num(a))
    from collections import Counter
    c=Counter(votes); best=c.most_common(1)[0][0]
    ok=(best==g)
    resD.append(ok)
    print("   → 票:%s 选=%s gold=%s %s [%.0fs]"%(votes,best,g,"✅" if ok else "❌",time.time()-t1),flush=True)
accD=100*sum(resD)/len(resD)

print("\n"+"="*70)
print("  结果汇总")
print("="*70)
print("  A 直接答        : %5.1f%%  (%d/%d)"%(accA,sum(resA),len(resA)))
print("  B 先想再答      : %5.1f%%  (%d/%d)  Δ%+.0f"%(accB,sum(resB),len(resB),accB-accA))
print("  C 想+自检+重答  : %5.1f%%  (%d/%d)  Δ%+.0f"%(accC,sum(resC),len(resC),accC-accA))
print("  D 多候选投票    : %5.1f%%  (%d/%d)  Δ%+.0f"%(accD,sum(resD),len(resD),accD-accA))
print("\n总耗时 %.0fs"%(time.time()-t0))
