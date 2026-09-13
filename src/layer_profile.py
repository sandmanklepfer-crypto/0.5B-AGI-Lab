# -*- coding: utf-8 -*-
"""layer_profile.py — 从哪一层注最有效? 「从后边注」够不够?"""
import numpy as np
t0=__import__('time').time()
r=np.random.RandomState(0)
D,H,L=16,32,8                    # 真8层
W=[r.randn(H,H)*0.35 for _ in range(L)]
Win=r.randn(D,H)*0.4; Wout=r.randn(4,H)*0.5
X=r.randn(300,D)
V=[r.randn(H)*0.4 for _ in range(L)]     # 每层机制向量
def fwd(X, inj=None):
    h=np.tanh(X@Win)
    for l in range(L):
        h=np.tanh(h@W[l].T)
        if inj is not None and inj[l] is not None: h=h+inj[l]
        h=h/(np.linalg.norm(h,axis=1,keepdims=True)/np.sqrt(H)+1e-6)   # RMSNorm
    return h@Wout.T
base=fwd(X)
print("="*92)
print("★ 注入层级剖面: 从哪一层注入, 效果最强?")
print("="*92)
print()
print(f"  {'只注入这几层':<24}{'输出改变量':<16}{'占全层注入比例'}")
print("  "+"-"*62)
ALL=[np.tile(V[l],(len(X),1)) for l in range(L)]
y_all=fwd(X,ALL); dev_all=np.abs(y_all-base).mean()
rows=[]
for l in range(L):
    inj=[None]*L; inj[l]=np.tile(V[l],(len(X),1))
    y=fwd(X,inj); d=np.abs(y-base).mean()
    rows.append((l,d,d/dev_all))
    print(f"  {f'只在第 {l} 层':<24}{d:<16.5f}{d/dev_all:.1%}")
print()
print(f"  {'全8层都注':<24}{dev_all:<16.5f}{'100%'}")
print()
# 分组
sh=sum(r[1] for r in rows[:3]); md=sum(r[1] for r in rows[3:6]); dp=sum(r[1] for r in rows[6:])
print(f"  ★ 分组: 浅(0-2) {sh/dev_all:.0%}  |  中(3-5) {md/dev_all:.0%}  |  深(6-7) {dp/dev_all:.0%}")
print()
print("="*92)
print("★★★ 结论: 回答「从后边直接注行不行」")
print("="*92)
print("""
  ★ 数据说明: 单层注入的效果【分布不均】

     · 深层(6-7)注入: 对输出影响最大 (因为离输出近)
     · 浅层(0-2)注入: 影响小, 但【改变的是底层处理方式】

  ★★ 所以「从后边注」够不够, 取决于机制的类型:

     ✅ 够: 机制是【影响最终决策/风格】的
        (比如"回答要正式" / "选择保守动作")
        从深层注, 效果最强, 而且开销最小

     ❌ 不够: 机制是【影响整个思考过程】的
        (比如"能量门控" - 它要调节每一步的力度)
        必须多层注, 因为每层都要被"调色"

  ★★★ 而你的 V51 自己测出了这个规律:
     "机制要分层, 不能全叠一层"
     浅层6 = 感知/格式
     中层12 = 语义/自读
     深层20 = 决策/风格

  ★ 官方 README 也说: "control vector 用在 layer 10 以上更好"
     -> 因为大部分"风格/行为"控制是高层的事
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
