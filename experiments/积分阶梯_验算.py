# -*- coding: utf-8 -*-
"""一元积分阶梯：一条主线 F(a)=∫0^1 x^a/(1+x)dx，层层剥。全部数值核验。"""
import numpy as np, math
from scipy.integrate import quad
pi, ln = math.pi, math.log
z3 = 1.2020569031595942853997      # ζ(3)
G  = 0.9159655941772190150546      # Catalan

def chk(tag, num, cl):
    ok = "OK" if abs(num-cl) < 1e-8 else "XX"
    print(f"  [{ok}] {tag:38s} 数值={num:+.10f}  闭式={cl:+.10f}")

print("=== 一条线：F(a)=∫0^1 x^a/(1+x)dx ===")
chk("L0 ∫0^1 x^2 dx",            quad(lambda x:x**2,0,1)[0], 1/3)
chk("L1 ∫0^1 x^a dx (a=1.5)",    quad(lambda x:x**1.5,0,1)[0], 1/(2.5))
chk("L2 ∫0^1 x^a ln x dx (a=1)", quad(lambda x:x*math.log(x),0,1)[0], -1/(2**2))
chk("L3 ∫0^1 ln x/(1+x) dx",     quad(lambda x:math.log(x)/(1+x),0,1)[0], -pi**2/12)
chk("L4 ∫0^1 ln^2 x/(1+x) dx",   quad(lambda x:math.log(x)**2/(1+x),0,1)[0], 1.5*z3)
chk("L5 ∫0^1 ln x/(1+x^2) dx",   quad(lambda x:math.log(x)/(1+x**2),0,1)[0], -G)
chk("L6 ∫0^1 ln^2 x/(1+x^2) dx", quad(lambda x:math.log(x)**2/(1+x**2),0,1)[0], pi**3/16)
chk("L7 ∫0^1 ln x ln(1-x) dx",   quad(lambda x:math.log(x)*math.log(1-x),0,1)[0], 2-pi**2/6)
chk("L8 ∫0^1 ln(1+x)ln(1-x)/x",  quad(lambda x:math.log(1+x)*math.log(1-x)/x,0,1)[0], -5/8*z3)
chk("L9 ∫0^1 ln^2 x ln(1-x) dx", quad(lambda x:math.log(x)**2*math.log(1-x),0,1)[0], 2*z3+pi**2/3-6)

print("\n=== 金线：递推 F(a)+F(a-1)=1/a ===")
def F(a): return quad(lambda x:x**a/(1+x),0,1)[0]
for a in [0.7, 1.4, 2.3]:
    print(f"  a={a}:  F(a)+F(a-1)={F(a)+F(a-1):.10f}   1/a={1/a:.10f}")

print("\n=== 旋钮打到头就崩：a→-1+ ===")
for a in [-0.9, -0.99, -0.999]:
    print(f"  a={a}:  F(a)={F(a):.6f}   (a→-1 时发散)")
