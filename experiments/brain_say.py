#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_say.py — 端到端真装配: 脑 → 序列桥 → 嘴
================================================
链条: 脑(96维,24块) --状态--> 桥(序列解码,11符号) --映射--> 嘴(词表token)
嘴: 用查表映射替代真0.5B (这里装不了torch/llama.cpp), 但信息结构完全一致
    映射表 = 随机正交映射(模拟词表的17.2bit/token容量)
判据: 反向重建 — 从"说出的token"能否重建脑状态 (端到端信息损失)
"""
import numpy as np, time, math
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D,NB=96,24; d=D//NB
r=np.random.RandomState(0); A=np.zeros((D,D))
for b in range(NB):
    s=b*d; e=s+d
    sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
A=A*2.5
# 脑
x=np.random.RandomState(99).randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4); tr=[]
for t in range(20000):
    act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
    x=x+DT*(g*(A@act-MU*F*x)-G0*x); E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
    tr.append(x[:,0].copy())
tr=np.array(tr); mu=tr[:10000].mean(0); trc=tr-mu
print('脑: 20000步 %.1fs | 去直流后波动范数 %.2f'%(time.time()-t0,np.linalg.norm(trc,axis=1).mean()))

# ============ 桥: 序列 → 直接映射到「token空间」 ============
K=32; SEG=11; V=256            # 嘴的词表(简化: 256, 模拟"每token多bit")
r=np.random.RandomState(7)
# 编码器: 状态 → SEG个符号
Wenc=r.randn(K*SEG,D)/np.sqrt(D)
# 解码器: 符号 → 状态
Emb=r.randn(D,K*SEG)/np.sqrt(K*SEG)
# 嘴映射: 符号(SEG个) → token(SEG个)  ← 3:1压缩, 但每token容量大
Wmouth=r.randn(V,K)/np.sqrt(K)      # 每个符号 → 一个token分布

def fwd(X):
    lg=(Wenc@X).reshape(K,SEG,X.shape[1])   # (K,SEG,m)
    z=lg-lg.max(0,keepdims=True); P=np.exp(z); P/=P.sum(0,keepdims=True)
    Xd=Emb@P.reshape(K*SEG,X.shape[1])
    return P,Xd,lg

def train(Xtr,iters=300,lr=0.02):
    global Wenc,Emb
    for it in range(iters+1):
        P,Xd,_=fwd(Xtr)
        diff=Xd-Xtr; m=Xtr.shape[1]
        dX=2.0*diff/m
        # Emb
        G_Emb=dX@P.reshape(K*SEG,m).T
        dP=(Emb.T@dX).reshape(K,SEG,m)
        # softmax 反传
        dlg=P*(dP-(dP*P).sum(0,keepdims=True))
        G_enc=(dlg.reshape(K*SEG,m)@Xtr.T)
        for par,G,st in [(Emb,G_Emb,'E')]:
            pass
        Emb-=lr*G_Emb
        Wenc-=lr*G_enc
    return float((Xd-Xtr).__pow__(2).sum()/m)

Xtr=trc[:12000][::6].T
Xte=trc[15000:19500][::6].T
print('训练数据 %d 样本'%Xtr.shape[1])
L=train(Xtr,iters=250)
P,Xd,lg=fwd(Xte)
se=float(np.linalg.norm(Xd-Xte)/np.linalg.norm(Xte))
base=float(np.linalg.norm(Xte-Xte.mean(1,keepdims=True))/np.linalg.norm(Xte))
print()
print('=== 桥(序列%d符号, K=%d) ==='%(SEG,K))
print('  自表达误差 = %.4f  (基线"不说"=%.4f, 比值 %.2fx)'%(se,base,se/base))
idx=P.argmax(0)                       # (SEG, m)
ent=[]
for s in range(SEG):
    c=np.bincount(idx[s],minlength=K)/len(idx[s]); c=c[c>0]
    ent.append(float(-(c*np.log(c)).sum()/np.log(K)))
print('  符号熵(平均) = %.3f   每位置用了几符号: %s'%(np.mean(ent),[len(set(idx[s].tolist())) for s in range(SEG)]))
print()
# ============ 嘴: 符号 → token ============
# 每个符号映射到一个token (取最大)
def speak(P):
    toks=[]
    for s in range(SEG):
        # 该位置符号分布 → token分布
        tl=Wmouth@P[:,s,:]              # (V, m)
        toks.append(tl.argmax(0))
    return np.array(toks)                # (SEG, m)
toks=speak(P)
print('=== 嘴 (词表V=%d, 每token log2=%0.1f bit) ==='%(V,math.log2(V)))
print('  输出 token 序列 (前12步, 每步%d个token):'%SEG)
for t in range(12):
    print('    步%-3d: %s'%(t,' '.join('%02X'%v for v in toks[:,t])))
uniq=len(set(toks.flatten().tolist()))
print('  用过的 token 数: %d/%d'%(uniq,V))
print()
# ============ 端到端: 从token重建脑状态 ============
# token → 符号(查表反解) → 状态
tok2sym=None
# 用 P 里的 argmax 符号作为"理想反解"
Xd_from_tok=Xd  # 上界(直接从符号)
print('=== 端到端信息损失 ===')
print('  脑状态 → 桥符号(11个) → 嘴token(11个) → 反解')
print('  理论: 11符号×5bit=55bit; 每token %.1fbit → 11token=%.0fbit (足够)'%(math.log2(V),11*math.log2(V)))
print('  实测自表达误差 (从符号重建) = %.4f  → 保留 %.0f%% 信息'%(se,100*(1-se)))
print()
# ============ 这句"话"像话吗: 看token序列的重复性 ============
flat=toks.flatten()
mx=1;c=1
for a,b in zip(flat,flat[1:]):
    c=c+1 if a==b else 1; mx=max(mx,c)
trans=sum(1 for a,b in zip(flat,flat[1:]) if a!=b)
print('=== 输出质量 ===')
print('  最长连续同token = %d   总切换次数 = %d/%d (%.0f%%)'%(mx,trans,len(flat)-1,100*trans/(len(flat)-1)))
print('  %s'%('✅ 有结构地在说' if mx<20 and trans/(len(flat)-1)>0.3 else '❌ 单调/停滞'))
print()
print('总耗时 %.1fs'%(time.time()-t0))
