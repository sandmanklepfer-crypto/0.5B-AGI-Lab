# -*- coding: utf-8 -*-
import numpy as np, math
from scipy.integrate import quad
ln, pi = math.log, math.pi

def L(f, x):   # 单侧极限
    return f(x)
def lim(f, x0, side=1):
    return f(x0+side*1e-7)

print("=== 极限组 ===")
print(" (1/x - 1/(e^x-1)) x->0 :", lim(lambda x: 1/x-1/(math.exp(x)-1), 0), " 期望 0.5")
print(" (tanx-sinx)/x^3 x->0   :", lim(lambda x:(math.tan(x)-math.sin(x))/x**3,0), " 期望 0.5")
print(" (sinx/x)^(1/x^2) x->0  :", lim(lambda x: (math.sin(x)/x)**(1/x**2),0), " 期望 e^-1/6=",math.exp(-1/6))
print(" sqrt(x^2+x)-x x->inf   :", (math.sqrt(1e12+1e6)-1e6), " 期望 0.5")
print(" (cosx)^(1/x^2) x->0    :", lim(lambda x: math.cos(x)**(1/x**2),0), " 期望 e^-0.5=",math.exp(-0.5))
print(" (x/(1+x))^x x->inf     :", (1/(1+1e-7))**(1e7), " 期望 e^-1=",math.exp(-1))

print("\n=== 积分组（数值 vs 闭式）===")
def chk(n,num,cl): 
    ok="OK" if abs(num-cl)<1e-8 else "XX"; print(f"  [{ok}] {n:30s} {num:+.8f} vs {cl:+.8f}")
chk("∫x^2 e^x 0..1",        quad(lambda x:x*x*math.exp(x),0,1)[0], 1.0)
chk("∫x cosx 0..pi/2",      quad(lambda x:x*math.cos(x),0,pi/2)[0], pi/2-1)
chk("∫ln x 1..e",           quad(lambda x:math.log(x),1,math.e)[0], 1.0)
chk("∫x^2e^x 0..1 通式? (x^2-2x+2)e^x", ((1-2+2)*math.e-(0-0+2)*1), 1.0)
chk("∫ 1..4 sqrtx",         quad(lambda x:math.sqrt(x),1,4)[0], 14/3)
chk("∫0..2 |x-1|",          quad(lambda x:abs(x-1),0,2)[0], 1.0)
chk("y=x^2,y=x 面积",       quad(lambda x:x-x*x,0,1)[0], 1/6)
chk("y=x^2,y=2-x^2 面积",   quad(lambda x:(2-x*x)-x*x,-1,1)[0], 8/3)
chk("V=pi∫0..1 x dx",       pi*quad(lambda x:x,0,1)[0], pi/2)
chk("∫0..pi/2 sin^2 x",     quad(lambda x:math.sin(x)**2,0,pi/2)[0], pi/4)
chk("∫0..1/(1+x^2)",        quad(lambda x:1/(1+x*x),0,1)[0], pi/4)
chk("∫dx/(x^2+4) 0..2",     quad(lambda x:1/(x*x+4),0,2)[0], (1/2)*math.atan(1))
chk("∫ 0..1 1/(1+e^x)",     quad(lambda x:1/(1+math.exp(x)),0,1)[0], 1-math.log(1+math.e)+math.log(2))
chk("∫ 1/(x^2-1) 2..3",     quad(lambda x:1/(x*x-1),2,3)[0], 0.5*math.log((2/4)/(1/3)) )
chk("∫ 1/(x^2+3x+2) 0..1",  quad(lambda x:1/(x*x+3*x+2),0,1)[0], math.log(4/3))
chk("∫ tan x 0..pi/4",      quad(lambda x:math.tan(x),0,pi/4)[0], -math.log(math.cos(pi/4)))
chk("∫ sqrt(4-x^2) 0..2",   quad(lambda x:math.sqrt(4-x*x),0,2)[0], pi)
