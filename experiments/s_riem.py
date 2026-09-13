# -*- coding: utf-8 -*-
"""黎曼曲率张量: 用外部工具(符号计算)做真实验算
   架构: 生成器(提候选) + 验证器(符号计算精确判) + 记忆
"""
import sympy as sp
from sympy import symbols, Function, sqrt, simplify, diff, cos, sin, Matrix, zeros, Rational
import time, itertools, json
t0=time.time()
print("="*84); print("黎曼曲率张量: 对称性发现 (真符号计算)"); print("="*84, flush=True)

# ---- 设定: 2维球面度规 g = diag(1, sin^2 θ) ----
th, ph = symbols('theta phi', real=True)
g = Matrix([[1,0],[0,sin(th)**2]])
n=2
g_inv = g.inv()
print(f"\n[1] 度规 g = diag(1, sin^2(theta))  行列式={sp.simplify(g.det())}")

# ---- 计算 Christoffel 符号 ----
Gam = [[[sp.Integer(0) for _ in range(n)] for _ in range(n)] for _ in range(n)]
for a in range(n):
    for b in range(n):
        for c in range(n):
            e = sum(g_inv[a,m]*(diff(g[m,b], [th,ph][c]) + diff(g[m,c],[th,ph][b]) - diff(g[b,c],[th,ph][m]))
                    for m in range(n))
            Gam[a][b][c]=sp.simplify(e/2)
print("[2] Christoffel 非零分量:")
for a in range(n):
    for b in range(n):
        for c in range(n):
            if Gam[a][b][c]!=0:
                print(f"    Gamma^{a}_{b}{c} = {Gam[a][b][c]}")

# ---- 计算黎曼张量 R^a_{bcd} ----
def R(a,b,c,d):
    e = diff(Gam[a][b][d],[th,ph][c]) - diff(Gam[a][b][c],[th,ph][d])
    e += sum(Gam[a][c][m]*Gam[m][b][d] - Gam[a][d][m]*Gam[m][b][c] for m in range(n))
    return sp.simplify(e)
print("[3] 黎曼张量非零分量:")
Rnz=[]
for a in range(n):
    for b in range(n):
        for c in range(n):
            for d in range(n):
                v=R(a,b,c,d)
                if v!=0:
                    Rnz.append((a,b,c,d,v)); print(f"    R^{a}_{b}{c}{d} = {v}")

# ---- 降指标 R_{abcd} = g_{ae} R^e_{bcd} ----
def Rabcd(a,b,c,d):
    return sp.simplify(sum(g[a,e]*R(e,b,c,d) for e in range(n)))
Rlow={(a,b,c,d):Rabcd(a,b,c,d) for a in range(n) for b in range(n) for c in range(n) for d in range(n)}

print("\n" + "="*84)
print("[4] ★ 生成器: 提出候选对称性, 验证器精确判定")
print("="*84)
CANDS=[
 ("反对称: R_abcd = -R_bacd",      lambda: all(sp.simplify(Rlow[(a,b,c,d)]+Rlow[(b,a,c,d)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("反对称: R_abcd = -R_abdc",      lambda: all(sp.simplify(Rlow[(a,b,c,d)]+Rlow[(a,b,d,c)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("交换对: R_abcd = R_cdab",       lambda: all(sp.simplify(Rlow[(a,b,c,d)]-Rlow[(c,d,a,b)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("第一比安基: 三者轮换和 = 0",      lambda: all(sp.simplify(Rlow[(a,b,c,d)]+Rlow[(a,c,d,b)]+Rlow[(a,d,b,c)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("对称: R_abcd = R_bacd",         lambda: all(sp.simplify(Rlow[(a,b,c,d)]-Rlow[(b,a,c,d)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("R_abcd = -R_adcb",             lambda: all(sp.simplify(Rlow[(a,b,c,d)]+Rlow[(a,d,c,b)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
 ("R_abcd = R_acbd",              lambda: all(sp.simplify(Rlow[(a,b,c,d)]-Rlow[(a,c,b,d)])==0 for a in range(n) for b in range(n) for c in range(n) for d in range(n))),
]
OK=0
for nm,fn in CANDS:
    r=fn(); OK+=r
    print(f"   {'✅ 成立' if r else '❌ 不成立'}  {nm}", flush=True)
print(f"\n[5] 结果: {OK}/{len(CANDS)} 条候选成立")

# ---- 里奇张量 / 标量曲率 (真实的几何量) ----
print("\n" + "="*84); print("[6] 推导里奇张量 R_bd = R^a_bad 与标量曲率"); print("="*84)
Ric=[[sp.simplify(sum(R(a,b,a,d) for a in range(n))) for d in range(n)] for b in range(n)]
print("  里奇张量:")
for b in range(n):
    for d in range(n):
        if Ric[b][d]!=0: print(f"    R_{b}{d} = {Ric[b][d]}")
Rs=sp.simplify(sum(g_inv[b,d]*Ric[b][d] for b in range(n) for d in range(n)))
print(f"  标量曲率 R = {Rs}")
print(f"  验算: 单位球 r=1 的标量曲率应为 2 -> 实得 {Rs}  {'✅ 正确!' if Rs==2 else '❌'}")

print("\n" + "="*84)
print("★★★ 结论 [黎曼]")
print("="*84)
print(f"""
  用【符号计算】这个外部工具, 完成了:
    · Christoffel 符号推导     (精确)
    · 黎曼张量 4 阶分量计算    (精确)
    · 7 条对称性候选的判定      ({OK}/{len(CANDS)} 条成立)
    · 里奇张量 + 标量曲率 R=2   ✅ 与已知结果一致

  ★ 全程【零模型】参与 —— 纯工具推导
  ★ 这就是"外部工具让系统做难题"的可行证明
""")
print(f"用时 {time.time()-t0:.2f}s")
