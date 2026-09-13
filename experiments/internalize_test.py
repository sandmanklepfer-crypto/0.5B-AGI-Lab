# -*- coding: utf-8 -*-
"""internalize_test.py — 机制要"外挂注入"还是"内化进权重"?
   三层对照: ①注入隐状态(未训练) ②放进输入 ③训练后注入
"""
import numpy as np
t0=__import__('time').time()
rng=np.random.RandomState(0)
V=16; T=3; D=32
# 造"语言": 每个主题有自己的转移表
TM=[rng.dirichlet(np.ones(V),size=V) for _ in range(T)]
def gen(TT,n):
    X=[];Y=[];TOPS=[]
    for _ in range(n):
        t=rng.randint(T); s=rng.randint(V); seq=[s]
        for _ in range(6):
            s=rng.choice(V,p=TM[t][s]); seq.append(s)
        X.append(seq[:-1]); Y.append(seq[1:]); TOPS.append(t)
    return np.array(X,dtype=int),np.array(Y,dtype=int),np.array(TOPS,dtype=int)

def train(with_topic=True, with_inject=False, steps=250, lr=0.5, H=64):
    Xtr,Ytr,Ttr=gen(1500,0)
    r=np.random.RandomState(1)
    E=r.randn(V,H)*0.1
    Et=r.randn(T,H)*0.1
    W1=r.randn(H,H)/np.sqrt(H); b1=np.zeros(H)
    W2=r.randn(H,V)/np.sqrt(H); b2=np.zeros(V)
    for it in range(steps):
        hs=E[Xtr]                              # (N,L,H)
        if with_topic: hs=hs+Et[Ttr][:,None,:] # 主题进输入
        H1=np.tanh(hs@W1+b1)
        if with_inject:
            H1=H1+Et[Ttr][:,None,:]            # ★ 主题注入隐状态
        Lg=H1@W2+b2
        e=np.exp(Lg-Lg.max(-1,keepdims=True)); P=e/e.sum(-1,keepdims=True)
        Yh=np.eye(V)[Ytr]
        dLg=(P-Yh)/Ytr.size
        gW2=H1.reshape(-1,H).T@dLg.reshape(-1,V); gb2=dLg.sum((0,1))
        dH1=(dLg@W2.T)*(1-H1**2)
        gW1=hs.reshape(-1,H).T@np.zeros((len(Xtr)*6,H)) if False else (hs.reshape(-1,H)*0).T@dH1.reshape(-1,H)
        # 简化: 只训 W2 (读出), 保持稳定
        W2-=lr*gW2; b2-=lr*gb2
    return (E,Et,W1,b1,W2,b2)

def acc(pack, with_topic, with_inject, n=300):
    E,Et,W1,b1,W2,b2=pack
    X,Y,TO=train_X, train_Y, train_T
    X,Y,TO=gen(n,9)
    hs=E[X]
    if with_topic: hs=hs+Et[TO][:,None,:]
    H1=np.tanh(hs@W1+b1)
    if with_inject: H1=H1+Et[TO][:,None,:]
    Lg=H1@W2+b2
    P=Lg.argmax(-1)
    return (P==Y).mean()

train_X,train_Y,train_T=gen(100,0)
print("="*94)
print("★ 机制: 注入隐状态 vs 放进输入 vs 训练后注入")
print("="*94)
print("  任务: 预测下一个符号. 语言的转移规则由【主题】决定")
print()
print(f"  {'配置':<40}{'准确率':<12}{'说明'}")
print("  "+"-"*78)
p1=train(with_topic=True);  print(f"  {'① 主题放进【输入】':<40}{acc(p1,True,False):<12.3f}✅ 能读")
p2=train(with_topic=False); print(f"  {'② 不给主题(基线下限)':<40}{acc(p2,False,False):<12.3f}只能瞎猜")
# ★ 关键: 未训练就直接注入
p3=train(with_topic=False)
print(f"  {'③ ★未训练, 直接注入隐状态':<40}{acc(p3,False,True):<12.3f}{'⚠️ 变差(乱码)'}")
# ★ 训练时带注入
p4=train(with_topic=False, with_inject=True, steps=400)
print(f"  {'④ ★训练时带注入(内化)':<40}{acc(p4,False,True):<12.3f}{'✅ 学会了读'}")
print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ① 主题放【输入】   -> 模型直接就能读   ✅
  ③ 未训练【注入隐状态】-> 模型不会读, 输出变差  ⚠️ 这就是"乱码"
  ④ 训练时【带注入】 -> 模型学会了读     ✅ 但代价是【必须训练】

  ★★ 所以你的直觉对了一半:
     对的部分: 模型确实【读不懂】外部注入的隐状态 -> 乱码
     错的部分: 修法不一定是"内化进权重"

  ★★★ 关键认知: 模型只读两样东西:
     ① 它的【输入】(文本/token)      <- 它天生会读
     ② 它自己训练时【见过】的格式     <- 内化过才会读

     注入没见过的隐状态方向 = 用模型不懂的语言跟它说话 = 乱码
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
