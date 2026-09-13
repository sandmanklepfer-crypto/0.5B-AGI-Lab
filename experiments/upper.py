# -*- coding: utf-8 -*-
"""upper.py — 上界测试: 到底缺什么?
   任务: (a%10 + b%10) % 10
   四组特征 × 训练0-9 → 测50-99
     F1 字符哈希         (现状)
     F2 个位 one-hot     (给了"个位"信息)
     F3 个位交叉 one-hot (给了"组合"信息)
     F4 直接给答案       (理论上界)
"""
import numpy as np, random, hashlib
random.seed(7); np.random.seed(7)
def t_add(lo,hi,n):
    return [(random.randint(lo,hi),random.randint(lo,hi)) for _ in range(n)]
def lab(a,b): return (a+b)%10

# ---------- 特征 ----------
def F1(a,b):   # 字符哈希
    s="%d+%d"%(a,b); D=64; v=np.zeros(D,np.float32)
    for i in range(len(s)-1): v[int(hashlib.md5(s[i:i+2].encode()).hexdigest()[:6],16)%D]+=1.0
    n=np.linalg.norm(v); return v/n if n>0 else v
def F2(a,b):   # 个位 one-hot (20维)
    v=np.zeros(20,np.float32); v[a%10]=1; v[10+b%10]=1; return v
def F3(a,b):   # 交叉 one-hot (100维)
    v=np.zeros(100,np.float32); v[(a%10)*10+(b%10)]=1; return v
def F4(a,b):   # 含答案
    v=np.zeros(11,np.float32); v[a%10]=1; v[(a+b)%10]=1; return v

def run(feat, name, D):
    tr=[(a,b,lab(a,b)) for a,b in t_add(0,9,2000)]
    te=[(a,b,lab(a,b)) for a,b in t_add(50,99,800)]
    Xtr=np.array([feat(a,b) for a,b,_ in tr]); Ytr=np.array([y for _,_,y in tr])
    Xte=np.array([feat(a,b) for a,b,_ in te]); Yte=np.array([y for _,_,y in te])
    Yh=np.zeros((len(Ytr),10),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    W=np.linalg.solve(Xtr.T@Xtr+1e-3*np.eye(D), Xtr.T@Yh)
    acc=float(((Xte@W).argmax(1)==Yte).mean())
    tag="✅ 泛化成功" if acc>0.7 else ("⚠️ 略高于瞎猜" if acc>0.15 else "❌ 瞎猜")
    print("  %-22s 特征%3d维  测试准确率 %5.1f%%   %s"%(name, D, 100*acc, tag))
    return acc

print("="*68)
print("  上界测试: 训练 0-9 → 测试 50-99 (基线=10%)")
print("="*68)
run(F1, "F1 字符哈希(现状)", 64)
run(F2, "F2 个位 one-hot", 20)
run(F3, "F3 交叉 one-hot", 100)
run(F4, "F4 含答案(理论上界)", 11)
print()
print("解读: 若 F3≈100% 而 F1≈10%, 说明「缺的是特征, 不是容量」")
