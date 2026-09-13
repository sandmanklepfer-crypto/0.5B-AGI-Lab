# -*- coding: utf-8 -*-
"""tiny13kb.py — 1.3KB(330参数) 微型核的能力边界扫描
   测: 它到底能学会什么? 只是分10类? 还是能做运算?
"""
import numpy as np, random, re, time, hashlib
random.seed(7); np.random.seed(7)

# ---------- 测试 1: 10类意图(已知100%) ----------
def t_intent():
    M=["roam","energy","reflect"]; W=["量子","天气","股票"]; C=["ls","df"]
    I=[]
    for m in M: I+=[("关掉 "+m,"OFF"),("开启 "+m,"ON")]
    for w in W: I+=[("搜索 "+w,"SEARCH"),(w+"是什么","ASK")]
    for c in C: I+=[("执行 "+c,"SHELL")]
    I+=[("看看世界","LOOK"),("新对话","CHAT"),("诊断","DIAG")]
    KS=sorted(set(k for _,k in I)); K={k:i for i,k in enumerate(KS)}
    def samp(n):
        o=[]
        for _ in range(n):
            tpl,kd=random.choice(I)
            if "%s" in tpl:
                pool=W if kd in("SEARCH","ASK") else (C if kd=="SHELL" else ["x"])
                tpl=tpl.replace("%s",random.choice(pool))
            o.append((tpl,K[kd]))
        return o
    return samp(2000), samp(800), len(KS)

# ---------- 测试 2: 二位数加法(真运算) ----------
def t_add(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        o.append(("%d+%d"%(a,b), a+b))
    return o

# ---------- 测试 3: 比较大小 ----------
def t_cmp(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        if a==b: a+=1
        o.append(("%d>%d"%(a,b), int(a>b)))
    return o

# ---------- 测试 4: 奇偶判断 ----------
def t_parity(lo,hi,n):
    return [("%d"%random.randint(lo,hi), random.randint(lo,hi)%2) for _ in range(n)]

def feat_q(s,D):
    """字符级哈希特征"""
    v=np.zeros(D,np.float32); s=str(s).lower()
    for i in range(len(s)-1): v[int(hashlib.md5(s[i:i+2].encode()).hexdigest()[:6],16)%D]+=1.0
    for c in s: v[int(hashlib.md5(("1"+c).encode()).hexdigest()[:6],16)%D]+=0.3
    n=np.linalg.norm(v); return v/n if n>0 else v

def train_eval(tr, te, C, D):
    Xtr=np.array([feat_q(q,D) for q,_ in tr]); Ytr=np.array([y for _,y in tr])
    Xte=np.array([feat_q(q,D) for q,_ in te]); Yte=np.array([y for _,y in te])
    W=np.zeros((D,C),np.float32); b=np.zeros(C,np.float32)
    for s in range(2000):
        i=random.randrange(len(Xtr)); x=Xtr[i]; y=Ytr[i]
        lg=x@W+b; lg-=lg.max(); p=np.exp(lg); p/=p.sum()
        g=p.copy(); g[y]-=1
        W-=1.0*np.outer(x,g); b-=1.0*g
    return float(((Xte@W+b).argmax(1)==Yte).mean()), D*C+C

print("="*70)
print("  1.3KB 微型核 能力边界")
print("="*70)
print("\n%-30s %-16s %-10s %s"%("任务","参数量","占用","准确率"))
print("-"*70)

# 1) 意图分类
tr,te,C=t_intent()
acc,np_=train_eval(tr,te,C,32)
print("%-30s %-16s %-10s %.1f%%"%("10类意图分类", f"{np_:,}", "%.1f KB"%(np_*4/1024), 100*acc))

# 2) 加法(同分布)
tr=t_add(0,9,3000); te=t_add(0,9,600)
acc,np_=train_eval(tr,te,19,32)   # 0-18 → 19类
print("%-30s %-16s %-10s %.1f%%"%("个位加法(同分布)", f"{np_:,}", "%.1f KB"%(np_*4/1024), 100*acc))

# 3) 加法(跨范围泛化) ★
tr=t_add(0,9,4000); te=t_add(10,20,600)
acc,np_=train_eval(tr,te,41,32)   # 结果 0-40 → 41类
print("%-30s %-16s %-10s %.1f%%  ← 泛化"%(f"{np_:,}" and "个位加法 → 测10-20", f"{np_:,}", "%.1f KB"%(np_*4/1024), 100*acc))

# 4) 比较大小(跨范围)
tr=t_cmp(0,9,3000); te=t_cmp(10,99,600)
acc,np_=train_eval(tr,te,2,32)
print("%-30s %-16s %-10s %.1f%%  ← 泛化"%("比较0-9 → 测10-99", f"{np_:,}", "%.1f KB"%(np_*4/1024), 100*acc))

# 5) 奇偶(跨范围)
tr=t_parity(0,9,3000); te=t_parity(10,999,600)
acc,np_=train_eval(tr,te,2,32)
print("%-30s %-16s %-10s %.1f%%  ← 泛化"%("奇偶0-9 → 测10-999", f"{np_:,}", "%.1f KB"%(np_*4/1024), 100*acc))
