# -*- coding: utf-8 -*-
"""manifold.py — 关键: 隐状态注入, 一定要训练吗?
   区分两种注入:
     ① 随机方向 (模型没见过的"外语")  -> 应该乱码
     ② 模型自己流形上的方向 (它自己的"母语") -> 可能不用训练就能读!
"""
import numpy as np, json, time
t0=time.time()
V=np.load('/workspace/_cache_V.npy')          # 真实词嵌入 (48,896)
W2=json.load(open('/workspace/_cache_W.json'))
G=chr(0x120)
GRP={'animal':['cat','dog','bird','fish','horse','snake'],
     'food':['bread','rice','milk','meat','soup','cake'],
     'emotion':['love','fear','hope','joy','anger','sad'],
     'time':['day','week','month','year','hour','minute'],
     'place':['city','house','road','tree','field','river'],
     'body':['hand','head','eye','foot','heart','skin'],
     'color':['red','blue','green','black','white','yellow'],
     'sound':['music','song','sound','voice','noise','tone']}
y=[]
for gi,(g,ws) in enumerate(GRP.items()):
    for w in ws:
        if (G+w) in W2: y.append(gi)
y=np.array(y); X=V[:len(y)]
Xc=X-X.mean(0)
# 一个"模型": h = tanh(Wx), 读出
r=np.random.RandomState(0); H=128
W=r.randn(896,H)/np.sqrt(896)
def fwd(X, inj=None):
    h=np.tanh(X@W)
    if inj is not None: h=h+inj
    return h
# 训读出 (线性)
Htr=fwd(Xc)
Wo=np.linalg.lstsq(np.hstack([Htr,np.ones((len(Htr),1))]),np.eye(8)[y],rcond=None)[0]
def acc(inj=None):
    H2=fwd(Xc,inj)
    P=(np.hstack([H2,np.ones((len(H2),1))])@Wo).argmax(1)
    return (P==y).mean()
base=acc()
print("="*94)
print("★ 关键实验: 隐状态注入, 两种方向, 要不要训练?")
print("="*94)
print(f"  真实词嵌入 48词 x 896维, 8类.  基线准确率 = {base:.3f}")
print()
# ① 随机方向
rng=np.random.RandomState(1)
print(f"  {'注入类型':<40}{'强度':<10}{'准确率':<12}{'变化'}")
print("  "+"-"*74)
for scale in [0.5,1.0,2.0,5.0]:
    inj=np.tile(rng.randn(128)*scale,(len(Xc),1))
    a=acc(inj)
    print(f"  {'① 随机方向(模型没见过的外语)':<40}{scale:<10}{a:<12.3f}{a-base:+.3f}")
print()
# ② 模型自己流形上的方向: 用真实类均值差
cm=np.array([Htr[y==c].mean(0) for c in range(8)])
print(f"  {'② 模型自己流形上的方向(母语)':<40}{'':<10}{'':<12}{''}")
for c in [0,1,2]:
    d=cm[c]-Htr.mean(0)                          # 朝某类的方向
    for scale in [0.5,1.0,2.0]:
        inj=np.tile(d,(len(Xc),1))*scale
        a=acc(inj)
        print(f"  {f'   朝类[{c}]的激活方向':<40}{scale:<10}{a:<12.3f}{a-base:+.3f}")
print()
print("="*94)
print("★★★ 判据")
print("="*94)
print("""
  ★ 如果 ① 掉得很厉害, 而 ② 保持得好 -> 说明:
     注入【模型自己流形上的方向】, 不需要训练也能读!
     (因为那本来就是"它自己的语言")

  ★ 如果 ① 和 ② 都掉 -> 说明:
     任何注入都要训练, 没有免费午餐
""")
print(f"用时 {time.time()-t0:.2f}s")
