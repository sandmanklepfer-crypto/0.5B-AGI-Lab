# -*- coding: utf-8 -*-
import math
s2 = math.sqrt(2)
# 上一版给的公式（错）  vs  重新推导的公式（正）
def F_wrong(x):
    t = math.tan(x)
    return (1/s2)*math.atan((t-1)/(s2*math.sqrt(t))) + (1/(2*s2))*math.log(abs((t+s2*math.sqrt(t)+1)/(t-s2*math.sqrt(t)+1)))
def F_right(x):
    t = math.tan(x)
    return (1/s2)*math.atan((t-1)/(s2*math.sqrt(t))) - (1/(2*s2))*math.log(abs((t+s2*math.sqrt(t)+1)/(t-s2*math.sqrt(t)+1)))

h=1e-5
print("  x     被积 sqrt(tanx)   旧公式F'     新公式F'")
for x in [0.3,0.8,1.2,1.5]:
    dw=(F_wrong(x+h)-F_wrong(x-h))/(2*h)
    dr=(F_right(x+h)-F_right(x-h))/(2*h)
    print(f"{x:5.2f}   {math.sqrt(math.tan(x)):.9f}   {dw:.9f}   {dr:.9f}")
