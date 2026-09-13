# -*- coding: utf-8 -*-
"""
一元积分 12 题 的自动化验算脚本
思路：凡是不定积分 -> 用中心差分验"导数等于被积函数"；
      凡是定积分     -> 用 scipy.quad 高精度数值积分，和闭式答案对比。
"""
import numpy as np, math
from scipy.integrate import quad
pi, ln, s2 = math.pi, math.log, math.sqrt(2)
Z3 = 1.2020569031595942853997381615          # ζ(3)
G  = 0.915965594177219015054603514932384110774  # Catalan 常数

# ---------- 第一档：不定积分，验导数 ----------
def F1(x): return (1/(2*s2))*(math.atan(s2*x+1)+math.atan(s2*x-1)) + (1/(4*s2))*math.log((x*x+s2*x+1)/(x*x-s2*x+1))
def F2(x): return (1/8)*(math.atan(x-1)+math.atan(x+1)) + (1/16)*math.log((x*x+2*x+2)/(x*x-2*x+2))
def F3(x): return math.atan(math.tan(x)-1/math.tan(x))
def F4(x):
    t = math.tan(x)
    return (1/s2)*math.atan((t-1)/(s2*math.sqrt(t))) - (1/(2*s2))*math.log(abs((t+s2*math.sqrt(t)+1)/(t-s2*math.sqrt(t)+1)))

def dcheck(tag, F, integrand, xs):
    h = 1e-5
    for x in xs:
        d = (F(x+h)-F(x-h))/(2*h)            # 中心差分，误差 O(h^2)
        t = integrand(x)
        ok = "OK" if abs(d-t) < 1e-4 else "XX"
        print(f"  [{ok}] {tag:22s} x={x:5.2f}  F'(x)={d: .9f}  被积={t: .9f}")

print("=== 第一档：不定积分（验证 F'(x) = 被积函数）===")
dcheck("1/(x^4+1)",  F1, lambda x: 1/(x**4+1),            [-1.7, 0.7, 1.9])
dcheck("1/(x^4+4)",  F2, lambda x: 1/(x**4+4),            [-1.7, 0.3, 1.4, 2.6])
dcheck("1/(sin^6+cos^6)", F3, lambda x: 1/(math.sin(x)**6+math.cos(x)**6), [0.4,1.1,2.0])
dcheck("sqrt(tan x)", F4, lambda x: math.sqrt(math.tan(x)), [0.3,0.8,1.2])

# ---------- 第二、三档：定积分，数值 vs 闭式 ----------
def show(n, num, cl, s):
    ok = "OK" if abs(num-cl) < 1e-8 else "XX"
    print(f"  [{ok}] {n:34s} 数值={num:+.12f}  闭式={cl:+.12f}  [{s}]")

print("\n=== 第二档 / 第三档：定积分（数值 vs 闭式）===")
show("5) ∫0^{pi/2} 1/(1+tan^a), a=2.7", quad(lambda x:1/(1+np.tan(x)**2.7),0,pi/2)[0], pi/4, "pi/4")
show("5) 同上, a=0.3",                  quad(lambda x:1/(1+np.tan(x)**0.3),0,pi/2)[0], pi/4, "pi/4")
show("6) ∫0^{pi/2} sqrt(tan x)",        quad(lambda x:np.sqrt(np.tan(x)),0,pi/2)[0], pi/s2, "pi/sqrt2")
show("7) ∫0^1 ln(1+x)/(1+x^2)",         quad(lambda x:np.log(1+x)/(1+x*x),0,1)[0], pi/8*ln(2), "(pi/8)ln2")
show("8) ∫0^1 sqrt(1-x^2)/(1+x^2)",     quad(lambda x:np.sqrt(1-x*x)/(1+x*x),0,1)[0], pi/2*(s2-1), "(pi/2)(sqrt2-1)")
show("9) ∫0^{pi/2} x cot x",            quad(lambda x:x/np.tan(x),0,pi/2)[0], pi/2*ln(2), "(pi/2)ln2")
show("10) ∫0^{pi/2} x ln sin x",        quad(lambda x:x*np.log(np.sin(x)),0,pi/2)[0], 7/16*Z3-pi**2/8*ln(2), "(7/16)ζ3-(pi^2/8)ln2")
show("11) ∫0^1 ln(1+x)ln(1-x)/x",       quad(lambda x:np.log(1+x)*np.log(1-x)/x,0,1)[0], -5/8*Z3, "-(5/8)ζ3")
show("12) ∫0^inf (arctan x)^2/x^2",     quad(lambda x:np.arctan(x)**2/x**2,0,np.inf)[0], pi*ln(2), "pi ln2")
print("  --- 附四道 ---")
show("附1) ∫0^{pi/2} ln sin x",         quad(lambda x:np.log(np.sin(x)),0,pi/2)[0], -pi/2*ln(2), "-(pi/2)ln2")
show("附2) ∫0^1 ln x ln(1-x)",          quad(lambda x:np.log(x)*np.log(1-x),0,1)[0], 2-pi**2/6, "2-pi^2/6")
show("附3) ∫0^1 ln x/(x^2-1)",          quad(lambda x:np.log(x)/(x*x-1),0,1)[0], pi**2/8, "pi^2/8")
show("附4) ∫0^inf ln x/(1+x^4)",        quad(lambda x:np.log(x)/(1+x**4),0,np.inf)[0], -pi**2*s2/16, "-pi^2 sqrt2/16")
show("7b) ∫0^1 arctan x/x",             quad(lambda x:np.arctan(x)/x,0,1)[0], G, "Catalan G")
