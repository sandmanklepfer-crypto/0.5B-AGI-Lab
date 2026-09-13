# -*- coding: utf-8 -*-
"""why_zero.py — 为什么"检索命中118次却零引用"?"""
import numpy as np, json, time
t0=time.time()
V=np.load('/workspace/_cache_V.npy'); W2=json.load(open('/workspace/_cache_W.json'))
G=chr(0x120)
GRP={'animal':['cat','dog','bird','fish','horse','snake'],'food':['bread','rice','milk','meat','soup','cake'],
     'emotion':['love','fear','hope','joy','anger','sad'],'time':['day','week','month','year','hour','minute'],
     'place':['city','house','road','tree','field','river'],'body':['hand','head','eye','foot','heart','skin'],
     'color':['red','blue','green','black','white','yellow'],'sound':['music','song','sound','voice','noise','tone']}
y=[]
for gi,(g,ws) in enumerate(GRP.items()):
    for w in ws:
        if (G+w) in W2: y.append(gi)
y=np.array(y); Xc=V[:len(y)]-V[:len(y)].mean(0)
r=np.random.RandomState(0); H=128
W=r.randn(896,H)/np.sqrt(896)
h=np.tanh(Xc@W)
Wo=np.linalg.lstsq(h,np.eye(8)[y],rcond=None)[0]
def acc(hm): return ((hm@Wo).argmax(1)==y).mean()

print("="*92)
print("★ 你的公式: h + eta*(h·v)*v   在什么情况下【注入无效】?")
print("="*92)
print()
print("  数学: 加进去的量 = eta * (h·v) * v")
print("        而 (h·v) = h 和 v 的余弦相似度 x 模长")
print()
print(f"  {'v 与 h 的关系':<26}{'h·v':<12}{'实际注入量 ||Δh||':<20}{'有效吗'}")
print("  "+"-"*74)
h0=h[0]
for nm,vv in [("★ v 就是 h 自己(完全同向)",h0.copy()),
              ("v 与 h 同向 70%", h0*0.7+np.random.RandomState(1).randn(H)*np.linalg.norm(h0)*0.5),
              ("v 与 h 无关(正交)", None),
              ("v = h + 大噪声", h0+np.random.RandomState(2).randn(H)*np.linalg.norm(h0)*3)]:
    if vv is None:
        # 构造正交向量
        vv=np.random.RandomState(3).randn(H)
        vv=vv-(vv@h0)/(h0@h0)*h0
    v=vv/(np.linalg.norm(vv)+1e-9)
    dot=float(h0@v)
    d=0.5*dot*v
    print(f"  {nm:<26}{dot:<12.3f}{np.linalg.norm(d):<20.4f}{'✅ 有效' if np.linalg.norm(d)>0.01 else '❌ 几乎为0'}")
print()
print("="*92)
print("★★★ 这就是「命中118次却零引用」的原因")
print("="*92)
print("""
  ★ 你的检索确实命中了 (cosv 高, 118次)
  ★ 但你注入的是 eta*(h·v)*v

  ★★ 当检索到的知识方向 v, 和当前隐状态 h 【接近正交】时:
       h·v ≈ 0  ->  注入量 ≈ 0  ->  【什么都没加进去】

  ★★★ 所以"命中"了, 但注入量极小 -> 文本里就"零引用"

  ★ 这正是 v122 记录的现象:
     "生成文本里没有一句引用检索到的真知识
      (函数方程被挣118次但文本零出现)"
     -> 不是检索没用, 是【注入公式把命中丢掉了】
""")
print()
print("="*92)
print("★★ 正确做法: 加性注入 (不是投影)")
print("="*92)
print()
print(f"  {'注入方式':<30}{'公式':<24}{'注入量':<12}{'能操控输出吗'}")
print("  "+"-"*80)
for nm,formula in [("① 你的(投影式)","eta*(h·v)*v"),("② 加性(直接加)","eta*v")]:
    for eta in [0.3,1.0]:
        # 用类别均值方向做 v
        cm=np.array([h[y==c].mean(0) for c in range(8)])
        tot=0;ok=0
        for c in range(8):
            v=cm[c]-h.mean(0); v/=np.linalg.norm(v)+1e-9
            if '投影' in nm or '①' in nm:
                inj=eta*((h@v)[:,None]*v)
            else:
                inj=eta*np.outer(np.ones(len(h)),v)
            p=((h+inj)@Wo).argmax(1)
            m=y!=c
            tot+=m.sum(); ok+=(p[m]==c).sum()
        print(f"  {nm:<30}{formula:<24}{eta:<12}{ok/tot:.3f}")
print()
print(f"用时 {time.time()-t0:.2f}s")
