# -*- coding: utf-8 -*-
"""steer2.py — 只注入【读出相关子空间】, 能不能只操控、不破坏?"""
import numpy as np, json, time
t0=time.time()
V=np.load('/workspace/_cache_V.npy')
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
y=np.array(y); Xc=V[:len(y)]-V[:len(y)].mean(0)
r=np.random.RandomState(0); H=128
W=r.randn(896,H)/np.sqrt(896)
Htr=np.tanh(Xc@W)
Wo=np.linalg.lstsq(np.hstack([Htr,np.ones((len(Htr),1))]),np.eye(8)[y],rcond=None)[0][:H]
def pred(inj=None):
    h=Htr if inj is None else Htr+inj
    return (np.hstack([h,np.ones((len(h),1))])@np.hstack([Wo,np.zeros((1,8))]).T if False else \
            (h@Wo)).argmax(1)
cm=np.array([Htr[y==c].mean(0) for c in range(8)])
# 读出相关子空间: Wo 的列空间
U,S,Vt=np.linalg.svd(Wo,full_matrices=False)
print("="*94)
print("★ 优化: 只注入【读出相关子空间】(去掉会干扰其他计算的分量)")
print("="*94)
print(f"  读出矩阵秩 = {len(S)} (128维隐空间里, 只有 {len(S)} 个方向影响输出)")
print()
print(f"  {'注入方式':<30}{'强度':<8}{'被操控率':<12}{'保持正确率'}")
print("  "+"-"*64)
for nm,proj in [("① 全空间注入",lambda d: d),
                ("② 只注入读出子空间",lambda d: U@(U.T@d))]:
    for sc in [0.3,0.6,1.0,1.5]:
        tot=0;ok=0;kept=0
        for c in range(8):
            d=cm[c]-Htr.mean(0)
            inj=np.tile(proj(d),(len(y),1))*sc
            p=pred(inj)
            m=y!=c
            tot+=m.sum(); ok+=(p[m]==c).sum(); kept+=(p[m]==y[m]).sum()
        print(f"  {nm:<30}{sc:<8}{ok/tot:<12.3f}{kept/tot:<12.3f}")
    print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ★ 如果 ② 能在不破坏的前提下操控 -> 说明:
     隐状态注入可以【精准操控】, 关键是注入到【对的那几个方向】上

  ★ 这直接回答你的问题:
     "全部塞进隐状态, 不训练" -> 可行, 但要塞到【模型自己用的那些方向】上
""")
print(f"用时 {time.time()-t0:.2f}s")
