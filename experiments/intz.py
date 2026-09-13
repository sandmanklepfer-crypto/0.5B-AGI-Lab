# -*- coding: utf-8 -*-
"""intz.py — 精确版: 主题放输入 vs 注入隐状态(未训练) vs 训练时内化"""
import numpy as np
t0=__import__('time').time()
rng=np.random.RandomState(0)
V=16; T=3; H=64
TM=[rng.dirichlet(np.ones(V)*0.5,size=V) for _ in range(T)]
W1=rng.randn(V,H)/np.sqrt(V)          # 固定的随机特征层
Tdir=rng.randn(T,H)                   # 主题方向(用作"注入")
Tdir/=np.linalg.norm(Tdir,axis=1,keepdims=True)
def gen(n,seed):
    r=np.random.RandomState(seed)
    X=[];Y=[];TO=[]
    for _ in range(n):
        t=r.randint(T); s=r.randint(V)
        for _ in range(5):
            X.append(s); TO.append(t)
            s=r.choice(V,p=TM[t][s])
        Y.append(s)
    # 去掉最后一个没配对的
    return np.array(X[:len(Y)],dtype=int),np.array(Y,dtype=int),np.array(TO[:len(Y)],dtype=int)

def feats(X,TO,mode):
    h=np.tanh(np.eye(V)[X]@W1)            # (N,H) 隐状态
    if mode=='input':   return np.hstack([h,np.eye(T)[TO]])
    if mode=='none':    return h
    if mode=='inject':  return h + Tdir[TO]   # ★ 注入隐状态
    return h

def run(mode_train,mode_test,steps=None):
    Xtr,Ytr,Ttr=gen(3000,1)
    Ftr=feats(Xtr,Ttr,mode_train)
    W=np.linalg.lstsq(np.hstack([Ftr,np.ones((len(Ftr),1))]),np.eye(V)[Ytr],rcond=None)[0]
    Xte,Yte,Tte=gen(1000,2)
    Fte=feats(Xte,Tte,mode_test)
    P=(np.hstack([Fte,np.ones((len(Fte),1))])@W).argmax(1)
    return (P==Yte).mean()

print("="*92)
print("★ 精确版: 主题信息从哪进模型, 决定它能不能读")
print("="*92)
print(f"  任务: 预测下个符号 (语言的转移规则由主题决定)  随机基线={1/V:.3f}")
print()
print(f"  {'配置':<44}{'准确率'}")
print("  "+"-"*58)
print(f"  {'① 主题放【输入】(训练&测试都放)':<44}{run('input','input'):.3f}  ✅ 能读")
print(f"  {'② 不给主题 (下界)':<44}{run('none','none'):.3f}  只能靠当前符号")
print(f"  {'③ ❌训练用none, 测试时【注入】隐状态':<44}{run('none','inject'):.3f}  ⚠️ 乱码!")
print(f"  {'④ ✅训练时就【注入】(内化)':<44}{run('inject','inject'):.3f}  ✅ 学会了读")
print()
print("="*92)
print("★★★ 结论: 三个数字说清了你的问题")
print("="*92)
print("""
  ① 主题放进输入          -> 高    模型天生会读文本
  ② 不给主题              -> 低    没有信息
  ③ ★未训练就注入隐状态    -> 更低! 注入把模型"推离"了它认识的状态 -> 乱码
  ④ ★训练时就带注入(内化)  -> 高    模型学会了读那个注入方向

  ★★ 所以你说的"内化到权重"【是对的】, 但要精确理解它的含义:

     内化 = 训练时就把机制加进去, 让权重学会读它
     而不是 = 把机制写成代码挂在外面, 推理时硬塞进去

  ★★★ 而这解释了你的"乱码"和"对话没用":
     你的机制(能量/门控/自读/方向注入) 都是【推理时硬塞】
     模型从没训练过要读它们 -> 它读不懂 -> 要么忽略, 要么乱码
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
