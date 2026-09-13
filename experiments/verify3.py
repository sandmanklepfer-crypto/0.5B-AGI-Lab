import numpy as np, math
from scipy.integrate import quad
pi=math.pi; ln=math.log
s2=math.sqrt(2); z3=1.2020569031595942853997381615

# check d/dx of x^4+4 antiderivative
def F(x): return (1/8)*(math.atan(x-1)+math.atan(x+1))+(1/16)*math.log((x*x+2*x+2)/(x*x-2*x+2))
for x in [-1.7,0.3,1.4,2.6]:
    h=1e-5; d=(F(x+h)-F(x-h))/(2*h)
    print(f"x={x:5.2f} F'={d:.10f}  1/(x^4+4)={1/(x**4+4):.10f}")

print()
def show(n,num,cl,s): print(f"{n:44s} num={num:+.12f} closed={cl:+.12f} diff={abs(num-cl):.2e} [{s}]")
show("int_0^1 ln x ln(1-x)/x dx", quad(lambda x: np.log(x)*np.log(1-x)/x,0,1)[0], z3,"zeta(3)")
show("int_0^1 sqrt(1-x^2)/(1+x^2) dx", quad(lambda x: np.sqrt(1-x**2)/(1+x**2),0,1)[0], pi/2*(s2-1),"(pi/2)(sqrt2-1)")
show("int_0^{pi/2} dx/(1+tan^a x) a=2.7", quad(lambda x:1/(1+np.tan(x)**2.7),0,pi/2)[0], pi/4,"pi/4")
show("int_0^{pi/2} x cot x dx", quad(lambda x: x/np.tan(x),0,pi/2)[0], pi/2*ln(2),"(pi/2)ln2")
show("int_0^{pi/2} sqrt(tan x)dx", quad(lambda x: np.sqrt(np.tan(x)),0,pi/2)[0], pi/s2,"pi/sqrt2")
show("int_0^inf ln x/(1+x^4)dx", quad(lambda x: np.log(x)/(1+x**4),0,np.inf)[0], -pi**2*s2/16,"-pi^2 sqrt2/16")
show("int_0^inf (arctan x)^2/x^2 dx", quad(lambda x: np.arctan(x)**2/x**2,0,np.inf)[0], pi*ln(2),"pi ln2")
show("int_0^1 ln(1+x)ln(1-x)/x dx", quad(lambda x: np.log(1+x)*np.log(1-x)/x,0,1)[0], -5/8*z3,"-(5/8)z3")
show("int_0^1 x ln x/(1+x^2)dx", quad(lambda x: x*np.log(x)/(1+x**2),0,1)[0], -pi**2/48,"-pi^2/48")
show("int_0^1 ln(1+x^2)/x dx", quad(lambda x: np.log(1+x*x)/x,0,1)[0], pi**2/24,"pi^2/24")
show("int_0^{pi/2} x ln sin x dx", quad(lambda x: x*np.log(np.sin(x)),0,pi/2)[0], 7/16*z3-pi**2/8*ln(2),"(7/16)zeta3-(pi^2/8)ln2")
