# -*- coding: utf-8 -*-
"""一条线:迭代 x_{n+1}=f(x_n) 的阶梯。每级只验上一级的一个点。"""
import math
print("级0  √2 迭代 x=(x+2/x)/2, x0=1:")
x=1.0
for i in range(5):
    x=(x+2/x)/2; print(f"   x{i+1}={x:.12f}")
print("级1  终点=方程解: L=(L+2/L)/2 -> L^2=2 -> L=sqrt2 =", math.sqrt(2))

print("\n级2  误差乘法: f'(sqrt2)=", abs(1-2/ (math.sqrt(2)**2)), " (f'(x)=1-2/x^2, 在 sqrt2 处 =0)")
xc=0.5
for i in range(6): xc=math.cos(xc)
print("级2  x=cos(x) 迭代 ->", round(xc,9), "   f'(L)=-sin(L)=", round(-math.sin(xc),6))

print("\n级5  logistic f=rx(1-x), 周期2 公式 (1+r±sqrt((r-3)(r+1)))/(2r):")
r=3.2; d=math.sqrt((r-3)*(r+1)); print(f"   r={r} -> 周期2 = { (1+r-d)/(2*r):.6f} 与 {(1+r+d)/(2*r):.6f}")
y=0.4
for i in range(200): y=r*y*(1-y)
p=[y]
for i in range(3): y=r*y*(1-y); p.append(y)
print("   数值迭代(r=3.2)末几步:", [round(v,5) for v in p[1:]], "-> 在两值间跳")

print("\n级6  倍周期点:3, 3.44949, 3.54409, 3.5644 ...  比值->Feigenbaum")
pts=[3.0,3.449489743,3.544090360,3.564407266,3.568759420]
for i in range(1,len(pts)-1):
    a,b,c=pts[i-1],pts[i],pts[i+1]; print(f"   delta_{i} = {(b-a)/(c-b):.6f}   (真值 4.669201...)")

print("\n级7  r=4 的 Lyapunov 指数 = ln2 ?")
r=4.0; x=0.1234567; s=0
N=400000
for i in range(1000): x=r*x*(1-x)
for i in range(N):
    x=r*x*(1-x); s+=math.log(abs(r*(1-2*x)))
print(f"   lambda 数值 = {s/N:.6f}   ln2 = {math.log(2):.6f}")

print("\n级8  竞赛壳: sqrt(2+sqrt(2+...)) 与 连分数 [1;1,1,...]")
x=math.sqrt(2)
for i in range(40): x=math.sqrt(2+x)
print(f"   sqrt(2+sqrt(2+...)) -> {x:.12f}   (就是 2, 因 L=sqrt(2+L)->L=2)")
c=1.0
for i in range(40): c=1+1/c
print(f"   连分数[1;1,1,...] -> {c:.12f}   (黄金比 phi={(1+math.sqrt(5))/2:.12f})")
