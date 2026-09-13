import numpy as np, math
from scipy.integrate import quad
pi=math.pi; ln=math.log
def show(name,num,closed,s):
    print(f"{name:46s} num={num:+.12f} closed={closed:+.12f} diff={abs(num-closed):.2e} [{s}]")
z3=1.2020569031595942853997381615
show("int_0^inf x/(e^x+1)dx", quad(lambda x: x/(np.exp(x)+1),0,60)[0], pi**2/12,"pi^2/12")
show("int_0^inf ln x/(1+x^4)dx", quad(lambda x: np.log(x)/(1+x**4),0,np.inf)[0], -pi**2*math.sqrt(2)/16,"-pi^2 sqrt2/16")
show("int_0^inf (arctan x)^2/x^2 dx", quad(lambda x: np.arctan(x)**2/x**2,0,np.inf)[0], pi*ln(2),"pi ln2")
show("int_0^{pi/2} ln sin x dx", quad(lambda x: np.log(np.sin(x)),0,pi/2)[0], -(pi/2)*ln(2),"-(pi/2)ln2")
show("int_0^1 ln x/(1-x)dx", quad(lambda x: np.log(x)/(1-x),0,1)[0], -pi**2/6,"-pi^2/6")
show("int_0^{pi/2} x ln sin x dx", quad(lambda x: x*np.log(np.sin(x)),0,pi/2)[0], (7/16)*z3-(pi**2/8)*ln(2),"(7/16)z3-(pi^2/8)ln2")
show("int_0^{pi/2} sqrt(tan x) dx", quad(lambda x: np.sqrt(np.tan(x)),0,pi/2)[0], pi/math.sqrt(2),"pi/sqrt2")
show("int_0^{inf} (e^-x^2)?? skip", 0,0,"")
show("int_0^1 arctan x/(x) dx", quad(lambda x: np.arctan(x)/x,0,1)[0], 0.915965594177219,"G")
# extra candidates
show("int_0^1 ln(1+x)ln(1-x)/x dx", quad(lambda x: np.log(1+x)*np.log(1-x)/x,0,1)[0], -(5/8)*z3,"-(5/8)z3")
show("int_0^{pi/2} ln(cos x) dx", quad(lambda x: np.log(np.cos(x)),0,pi/2)[0], -(pi/2)*ln(2),"-(pi/2)ln2")
show("int_0^1 x ln x/(1+x^2) dx", quad(lambda x: x*np.log(x)/(1+x**2),0,1)[0], -(pi**2/96),"-pi^2/96")
show("int_0^1 ln(1+x^2)/x dx", quad(lambda x: np.log(1+x*x)/x,0,1)[0], pi**2/48,"pi^2/48")
show("int_0^inf dx/(1+x^3)", quad(lambda x: 1/(1+x**3),0,np.inf)[0], 2*pi/(3*math.sqrt(3)),"2pi/(3sqrt3)")
show("int_0^1 sqrt(1-x^2)/(1+x^2) dx", quad(lambda x: np.sqrt(1-x*x)/(1+x*x),0,1)[0], (pi/2)*(math.sqrt(2)-1),"pi/2(sqrt2-1)")
