# -*- coding: utf-8 -*-
"""steering.py — 真测试: 注入隐状态, 能不能【操控】模型的输出?"""
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
Wo=np.linalg.lstsq(np.hstack([Htr,np.ones((len(Htr),1))]),np.eye(8)[y],rcond=None)[0]
def pred(inj=None):
    h=Htr if inj is None else Htr+inj
    return (np.hstack([h,np.ones((len(h),1))])@Wo).argmax(1)
base=pred()
cm=np.array([Htr[y==c].mean(0) for c in range(8)])
print("="*94)
print("★ 真测试: 注入隐状态方向, 能不能把输出【操控】到指定类别?")
print("="*94)
print(f"  基线准确率 {np.mean(base==y):.3f}   每类 {sum(y==0)} 个词")
print()
# 目标: 对每个词, 注入"类c"的方向, 看输出变成c的比例
print(f"  {'注入方向':<26}{'强度':<8}{'被操控率':<12}{'保持正确率':<12}{'说明'}")
print("  "+"-"*76)
for nm,dirfn in [("① 随机方向",lambda c: np.tile(np.random.RandomState(100+c).randn(H),(len(y),1))),
                 ("② 自己流形方向",lambda c: np.tile(cm[c]-Htr.mean(0),(len(y),1)))]:
    for sc in [0.1,0.3,0.5,1.0]:
        tot=0;ok=0;kept=0
        for c in range(8):
            p=pred(dirfn(c)*sc)
            # 只看"原本不是c"的词
            m=y!=c
            tot+=m.sum()
            ok+=(p[m]==c).sum()
            kept+=(p[m]==y[m]).sum()
        print(f"  {nm:<26}{sc:<8}{ok/tot:<12.3f}{kept/tot:<12.3f}")
    print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ★ 判据:
     · "被操控率"高 + "保持正确率"高  -> ✅ 注入能操控, 且不破坏模型
     · 两个都低                      -> ❌ 注入只是噪声
     · 操控率高但保持率低             -> ⚠️ 破坏了模型 (乱码)

  ★ 这个测试直接回答了你的问题:
     "全部塞进隐状态, 不训练, 能不能让模型按你说的做?"
""")
print(f"用时 {time.time()-t0:.2f}s")
