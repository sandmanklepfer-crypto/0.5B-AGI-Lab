import numpy as np
from scipy.integrate import quad
import math

def show(name, num, closed, closedstr):
    print(f"{name:52s} num={num:+.12f}  closed={closed:+.12f}  diff={abs(num-closed):.2e}   [{closedstr}]")

pi=math.pi; ln=math.log

# 1 indefinite check: derivative of candidate antiderivatives
def dcheck(name, F, x0):
    h=1e-5
    d=(F(x0+h)-F(x0-h))/(2*h)
    print(f"  deriv check {name} at x={x0}: F'={d:+.10f}")

# F1 = (1/(2*sqrt2))[atan(sqrt2 x+1)+atan(sqrt2 x-1)] + (1/(4 sqrt2)) ln((x^2+sqrt2 x+1)/(x^2-sqrt2 x+1))
s2=math.sqrt(2)
def F1(x): return (1/(2*s2))*(math.atan(s2*x+1)+math.atan(s2*x-1))+(1/(4*s2))*math.log((x*x+s2*x+1)/(x*x-s2*x+1))
for x in [-2.3,0.7,1.9]: dcheck("d/dx [x^4+1 antideriv]", F1, x)

# 2 sin^6+cos^6
def F2(x): return math.atan(math.tan(x)-1/math.tan(x))
for x in [0.4,1.1,2.0]: dcheck("d/dx arctan(tanx-cotx)", F2, x)

# 3 sqrt(tan x)
def F3(x):
    t=math.tan(x)
    return (1/s2)*math.atan((t-1)/(s2*math.sqrt(t)))+(1/(2*s2))*math.log(abs((t+s2*math.sqrt(t)+1)/(t-s2*math.sqrt(t)+1)))
for x in [0.3,0.8,1.2]: dcheck("d/dx sqrt(tan) antideriv", F3, x)

print()
# definite integrals
show("int_0^{pi/2} dx/(1+tan^{sqrt2}x)", quad(lambda x:1/(1+math.tan(x)**s2),0,pi/2-1e-12)[0], pi/4,"pi/4")
show("int_0^{pi/2} sqrt(tan x)dx", quad(lambda x: math.sqrt(math.tan(x)),0,pi/2)[0], pi/s2,"pi/sqrt2")
show("int_0^1 ln(1+x)/(1+x^2)dx", quad(lambda x: math.log(1+x)/(1+x*x),0,1)[0], (pi/8)*ln(2),"(pi/8)ln2")
G=0.91596559417721901505460351493238411077414937428167
show("int_0^1 arctan x/x dx", quad(lambda x: math.atan(x)/x,0,1)[0], G,"Catalan G")
show("int_0^1 ln x ln(1-x)dx", quad(lambda x: math.log(x)*math.log(1-x),0,1)[0], 2-pi**2/6,"2-pi^2/6")
show("int_0^1 ln x ln(1+x)dx", quad(lambda x: math.log(x)*math.log(1+x),0,1)[0], 2-pi**2/12-2*ln(2),"2-pi^2/12-2ln2")
show("int_0^{pi/2} x ln sin x dx", quad(lambda x: x*math.log(math.sin(x)),0,pi/2)[0], -(pi**2/8)*ln(2),"-(pi^2/8)ln2")
show("int_0^{pi/2} x cot x dx", quad(lambda x: x/math.tan(x),0,pi/2)[0], (pi/2)*ln(2),"(pi/2)ln2")
show("int_0^1 ln x/(x^2-1)dx", quad(lambda x: math.log(x)/(x*x-1),0,1)[0], pi**2/8,"pi^2/8")
show("int_0^1 ln^2 x/(1+x^2)dx", quad(lambda x: math.log(x)**2/(1+x*x),0,1)[0], pi**3/16,"pi^3/16")
show("int_0^inf x/(e^x+1)dx", quad(lambda x: x/(math.exp(x)+1),0,np.inf)[0], pi**2/12,"pi^2/12")
show("int_0^inf ln x/(1+x^4)dx", quad(lambda x: math.log(x)/(1+x**4),0,np.inf)[0], -pi**2*s2/16,"-pi^2 sqrt2/16")
show("int_0^inf (arctan x)^2/x^2 dx", quad(lambda x: math.atan(x)**2/x**2,0,np.inf)[0], pi*ln(2),"pi ln2")
show("int_0^{pi/2} ln sin x dx", quad(lambda x: math.log(math.sin(x)),0,pi/2)[0], -(pi/2)*ln(2),"-(pi/2)ln2")
show("int_0^1 ln x/(1-x) dx", quad(lambda x: math.log(x)/(1-x),0,1)[0], -pi**2/6,"-pi^2/6")
