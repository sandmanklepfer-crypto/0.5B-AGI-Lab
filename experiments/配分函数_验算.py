# -*- coding: utf-8 -*-
"""把 F(a)=∫0^1 x^a/(1+x)dx 读成配分函数 Z(a)，验证四件事。"""
import math, numpy as np
from scipy.integrate import quad
ln, pi = math.log, math.pi
z3 = 1.2020569031595942854

def Z(a):   return quad(lambda x: x**a/(1+x), 0, 1)[0]
def intE(a): return quad(lambda x: (-ln(x))*x**a/(1+x), 0, 1, points=[1e-12])[0]
def intE2(a):return quad(lambda x: (ln(x)**2)*x**a/(1+x), 0, 1, points=[1e-12])[0]

print("①  ⟨E⟩ = -∂lnZ/∂a   （E = -ln x，就是 L2 那一步）")
h=1e-5
for a in [0.0,1.0,5.0,20.0]:
    meanE = intE(a)/Z(a)
    dlnZ  = (math.log(Z(a+h))-math.log(Z(a-h)))/(2*h)
    print(f"   a={a:5.1f}   ⟨E⟩={meanE:.10f}   -∂lnZ/∂a={-dlnZ:.10f}   差={abs(meanE+dlnZ):.1e}")

print("\n②  热容 > 0：Var(E) = ∂²lnZ/∂a²  （方差永不小于零）")
for a in [0.0,1.0,5.0]:
    var = intE2(a)/Z(a) - (intE(a)/Z(a))**2
    d2  = (math.log(Z(a+h))-2*math.log(Z(a))+math.log(Z(a-h)))/h**2
    print(f"   a={a:4.1f}   Var(E)={var:.8f}   ∂²lnZ={d2:.8f}   ≥0 ✓")

print("\n③  低温锐化（a 大）：Z(a) → 1/[2(a+1)]  （积分塌到最低能量点 x=1）")
for a in [1,5,20,100]:
    print(f"   a={a:4d}   Z(a)={Z(a):.8f}   1/[2(a+1)]={1/(2*(a+1)):.8f}   比值={Z(a)*(2*(a+1)):.6f}")

print("\n④  离散化 = softmax：把 [0,1] 切 N 段做黎曼和（就是 L0 的动作）")
a=3.0
for N in [3,5,10,50]:
    xs = np.linspace(0.5/N, 1-0.5/N, N)          # 中点
    w  = np.ones(N)/N / (1+xs)                   # dμ = dx/(1+x)
    E  = -np.log(xs)
    ZN = np.sum(np.exp(-a*E)*w)
    p  = np.exp(-a*E)*w / ZN                     # ← 这就是 softmax 权重
    print(f"   N={N:3d}  ZN={ZN:.6f}  Z={Z(a):.6f}  |  最大权重落在 x={xs[np.argmax(p)]:.2f}")

print("\n⑤  温度 T=1/a：T 大→均匀，T 小→塌缩")
print("   （a→-1 时 x^a 在 x→0 爆掉，Z 发散，即高温端失控——对应 L1 旋钮打到底）")
