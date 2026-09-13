# -*- coding: utf-8 -*-
import math
from fractions import Fraction as F
def C(m,k):
    r=F(1)
    for j in range(k): r*= (F(m)-j)
    for j in range(1,k+1): r/= j
    return r

s2=math.sqrt(2)
print("本线的真值：S = Σ_k C(1/2,k)·1 = (1+1)^(1/2) = sqrt(2) =", round(s2,12))
print("（上一轮我文字里误写成 m=1.5。m=1/2 才收敛到 sqrt2，数字表用的是 1/2。）\n")

m=F(1,2)
print(" n    第n项 C(1/2,n)     部分和 S_n          S_n - sqrt2")
S=F(0)
Sn=[]
for n in range(0,21):
    t=C(m,n); S+=t; Sn.append(float(S))
    print(f"{n:3d}   {float(t):+.10f}    {float(S):.10f}   {float(S-s2):+.10f}")

print("\n【关键】项越加越小，正负交替；和永远在 sqrt2 两侧抖，永不往下越界：")
print("  偶数项部分和 (从下往上趋近):", [f"{Sn[n]:.6f}" for n in range(0,12,2)])
print("  奇数项部分和 (从上往下趋近):", [f"{Sn[n]:.6f}" for n in range(1,12,2)])
print(f"  sqrt2 = {s2:.6f}  ← 两条线夹着它，谁都别想过去")
