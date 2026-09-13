# -*- coding: utf-8 -*-
"""diag_repr.py — 决定性诊断: 泛化的瓶颈是「表示」还是「纠缠」?
   同一个水库, 只换输入表示:
     A. 字符特征(现状)          → 泛化 ?
     B. 数值特征(解析出数)       → 泛化 ?
   若 B 远好于 A → 瓶颈是"表示", 不是"纠缠"
"""
import numpy as np, random, hashlib
random.seed(7); np.random.seed(7)

def t_add(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        o.append((a,b,(a+b)%10))
    return o

# ---- 特征A: 字符哈希(原版) ----
CH=list("0123456789+=")
def featA(a,b, D=64):
    s="%d+%d"%(a,b); v=np.zeros(D,np.float32)
    for i in range(len(s)-1): v[int(hashlib.md5(s[i:i+2].encode()).hexdigest()[:6],16)%D]+=1.0
    for c in s: v[int(hashlib.md5(("1"+c).encode()).hexdigest()[:6],16)%D]+=0.3
    n=np.linalg.norm(v); return v/n if n>0 else v

# ---- 特征B: 数值特征(告诉它"个位是多少") ----
def featB(a,b, D=64):
    v=np.zeros(D,np.float32)
    v[0]=a/100.0; v[1]=b/100.0            # 原值
    v[2]=(a%10)/10.0; v[3]=(b%10)/10.0     # 个位 ← 关键
    v[4]=((a+b)%10)/10.0                   # 答案(用于验证特征有效性)
    v[5]=a%10; v[6]=b%10
    v[7]=(a%10+b%10)/18.0
    return v

def ev(feat, tr, te, C=10, D=64):
    Xtr=np.array([feat(a,b) for a,b,_ in tr]); Ytr=np.array([y for _,_,y in tr])
    Xte=np.array([feat(a,b) for a,b,_ in te]); Yte=np.array([y for _,_,y in te])
    Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    W=np.linalg.solve(Xtr.T@Xtr+1e-3*np.eye(D), Xtr.T@Yh)
    return float(((Xte@W).argmax(1)==Yte).mean())

print("="*66)
print("  诊断: 泛化瓶颈 = 表示 还是 纠缠?")
print("="*66)
print("\n%-26s %-14s %s"%("配置","训练范围","测试范围 → 准确率"))
print("-"*66)
for name, feat in (("A 字符特征", featA), ("B 数值特征", featB)):
    for (trlo,trhi),(telo,tehi) in [((0,9),(0,9)), ((0,9),(10,30)), ((0,9),(50,99))]:
        tr=t_add(trlo,trhi,1500); te=t_add(telo,tehi,600)
        acc=ev(feat,tr,te)
        tag = "★泛化" if telo>9 else "同分布"
        print("%-26s %-14s %s → %.1f%%"%(name, "%d-%d"%(trlo,trhi), "%d-%d"%(telo,tehi), 100*acc), end="")
        print("  %s"%("✅ 泛化成功!" if (telo>9 and acc>0.7) else ("(瞎猜=10%)" if telo>9 else "")),flush=True)
    print()
