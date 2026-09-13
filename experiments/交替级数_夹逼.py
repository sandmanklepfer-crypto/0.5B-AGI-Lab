# -*- coding: utf-8 -*-
import math
from fractions import Fraction as F

def C(m,k):
    r=F(1)
    for j in range(k): r*= (F(m)-j)
    for j in range(1,k+1): r/= j
    return r

m=F(3,2)          # 1.5
print("真值 sqrt(2) =", round(math.sqrt(2),12))
print("\n n   第n项C(1.5,n)      部分和S_n          和 sqrt2 的差")
S=F(0)
for n in range(0,21):
    t=C(m,n)                    # 差分列全是1，所以项=C(m,n)
    S+=t
    print(f"{n:3d}  {float(t):+.12f}   {float(S):.12f}   {float(S-math.sqrt(2)):+.12f}")

print("\n【分开看奇偶】收敛方式：偶数项从下往上，奇数项从上往下，夹住 sqrt2")
S=F(0); even=[]; odd=[]
for n in range(0,25):
    S+=C(m,n)
    (even if n%2==0 else odd).append((n,float(S)))
print("  偶数部分和 S0,S2,S4,...:", [f"{v:.6f}" for n,v in even[:7]])
print("  奇数部分和 S1,S3,S5,...:", [f"{v:.6f}" for n,v in odd[:7]])
print("  两者都往 1.414213562 挤 → 谁也过不去")
