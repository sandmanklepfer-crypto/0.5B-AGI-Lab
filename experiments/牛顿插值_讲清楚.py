# -*- coding: utf-8 -*-
from fractions import Fraction as F
import math

def C(m, k):            # 广义组合数 C(m,k)=m(m-1)...(m-k+1)/k!
    r = F(1)
    for j in range(k):
        r *= (F(m) - j)
    for j in range(1, k+1):
        r /= j
    return r

print("【表】f(n)=2^n, n=0,1,2,3,4  →  1, 2, 4, 8, 16")
print("【差分表】（下一行 = 上一行相邻两项相减）")
rows = [[1,2,4,8,16]]
while len(rows[-1]) > 1:
    prev = rows[-1]
    rows.append([prev[i+1]-prev[i] for i in range(len(prev)-1)])
for i,r in enumerate(rows):
    print("   " + "Δ"*i + f"^?.  {r}")

print("\n【牛顿公式】 f(m) = 1 + C(m,1)*1 + C(m,2)*1 + C(m,3)*1 + ...")
print("   因为这张表的每一行第一个数都是 1\n")

print("① 整数 m 会自动截断（C(m,k)=0 当 k>m）:")
for m in [2,3,4]:
    s = sum(C(m,k) for k in range(m+1))
    print(f"   m={m}: 1+{m}+...+1 = {s}   而真实 2^{m}={2**m}   {'OK' if s==2**m else 'XX'}")

print("\n② 非整数 m=1/2（表里没有的点！）逐项加，看逼近谁:")
s = F(0)
for k in range(9):
    s += C(F(1,2), k)
    print(f"   加第{k}项后 = {float(s):.8f}")
print(f"   真实 sqrt(2) = {math.sqrt(2):.8f}")

print("\n③ 换个函数：f(x)=x^2（差分很快归零 → 精确）")
rows2=[[0,1,4,9,16]]
while len(rows2[-1])>1:
    p=rows2[-1]; rows2.append([p[i+1]-p[i] for i in range(len(p)-1)])
for i,r in enumerate(rows2): print("   "+"Δ"*i+f"  {r}")
m=F(5,2)
val=sum(C(m,k)*rows2[k][0] for k in range(len(rows2)))
print(f"   牛顿公式算 f(2.5) = {val}  真实 2.5^2 = {F(5,2)**2}   {'OK' if val==F(25,4) else 'XX'}")
