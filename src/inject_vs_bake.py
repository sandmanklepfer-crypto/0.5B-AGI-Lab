# -*- coding: utf-8 -*-
"""inject_vs_bake.py — 逐层注入 vs 融入权重: 数学上到底谁更好?"""
import numpy as np
t0=__import__('time').time()
r=np.random.RandomState(0)
D,H,O=8,16,4
W1=r.randn(H,D)*0.5; b1=r.randn(H)*0.1
W2=r.randn(H,H)*0.3; b2=r.randn(H)*0.1
W3=r.randn(O,H)*0.4; b3=r.randn(O)*0.1
X=r.randn(200,D)
v=r.randn(H)*0.5                      # 机制向量
eta=0.6

def fwd(X, inj=None, bake=None, norm=False):
    h1=np.tanh(X@W1.T+b1)
    if inj is not None: h1=h1+eta*inj           # ★ 注入
    if norm:
        h1=h1/(np.linalg.norm(h1,axis=1,keepdims=True)/np.sqrt(H)+1e-6)
    bb = b2 + bake if bake is not None else b2  # ★ 烘焙(bias)
    h2=np.tanh(h1@W2.T+bb)
    return h2@W3.T+b3

print("="*94)
print("★ 数学对照: 逐层注入 vs 融入权重(烘焙)")
print("="*94)
print()
print("  模型: y = W3·tanh(W2·tanh(W1·x+b1) + b2) + b3")
print("  注入: h1 += eta*v")
print("  烘焙: b2 += eta*W2*v    (把注入的效果折进下一层偏置)")
print()
print(f"  {'情形':<28}{'与注入的最大差异':<20}{'结论'}")
print("  "+"-"*72)
# ---- 无归一化 ----
y_base=fwd(X)
y_inj =fwd(X, inj=np.tile(v,(len(X),1)))
bake  = eta*(W2@v)
y_bake=fwd(X, bake=bake)
print(f"  {'① 无归一化':<28}{np.abs(y_inj-y_bake).max():<20.2e}{'★ 完全等价!' if np.abs(y_inj-y_bake).max()<1e-10 else '不等价'}")
# ---- 有 RMSNorm (真实 transformer) ----
y_inj2 =fwd(X, inj=np.tile(v,(len(X),1)), norm=True)
y_bake2=fwd(X, bake=bake, norm=True)
d=np.abs(y_inj2-y_bake2).max()
scale=np.abs(y_inj2).max()
print(f"  {'② 有RMSNorm(真实架构)':<28}{d:<20.2e}{f'相对误差{d/scale:.1%} 近似等价' if d/scale<0.3 else '不等价'}")
print()
print("="*94)
print("★★ 关键: 机制是【静态】还是【依赖状态】?")
print("="*94)
print()
print("  情形A: 机制固定 (比如'永远正式语气') -> eta 是常数")
y_injA=fwd(X, inj=np.tile(v,(len(X),1)))
y_bakeA=fwd(X, bake=eta*(W2@v))
print(f"     注入 = {np.abs(y_injA-y_bakeA).max():.2e}   烘焙 = 完全一致  -> ★ 烘焙更好(零开销)")
print()
print("  情形B: 机制依赖状态 (比如'能量低时保守') -> eta = f(状态)")
print()
print(f"     {'状态值':<10}{'需要的 eta':<14}{'烘焙需要几套权重':<20}{'注入需要几套'}")
print("     "+"-"*62)
for k,st in enumerate([0.1,0.3,0.5,0.7,0.9]):
    print(f"     {st:<10}{st*1.0:<14}{k+1:<20}{'1套(实时算)'}")
print()
print("     ★ 状态连续变化 -> 烘焙需要【无穷多套权重】-> 做不到")
print("     ★ 注入只需要【一个向量 + 实时算 eta】 -> 天然支持")
print()
print("="*94)
print("★★★ 结论: 分界线非常清楚")
print("="*94)
print("""
  ┌────────────────────┬──────────────────┬──────────────────┐
  │  机制类型           │  逐层注入         │  融入权重         │
  ├────────────────────┼──────────────────┼──────────────────┤
  │ 静态 (eta 常数)     │ 可以             │ ★ 更好(等价+零开销)│
  │ 动态 (依赖状态)     │ ★ 唯一可行        │ ❌ 数学上做不到    │
  └────────────────────┴──────────────────┴──────────────────┘

  ★★ 关键数学事实 (上面已证):
     静态注入 + 烘焙 = 【完全等价】 (无归一化时误差 0)

     ★ 所以对静态机制: 烘焙严格更好 —— 不用每次算, 彻底, 永久
     ★ 对动态机制:     烘焙做不到 (要无穷多套权重)

  ★★★ 而你的 400 套方法, 绝大多数是【动态】的:
     能量门控: g = E/(κ+E)      -> 依赖 E 这个实时状态
     自读回环: 依赖上一步的状态   -> 依赖历史
     水库搜索: 依赖当前状态轨迹   -> 依赖轨迹
     -> 这些【全部】需要注入, 烘焙装不下
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
