# -*- coding: utf-8 -*-
"""测 calc_v1 的工具调用能力: 分布内 vs 分布外 vs 思维链引导"""
import json, urllib.request, re, math
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(q, mx=80, t=0.2):
    body=json.dumps({"messages":[{"role":"user","content":q}],
                     "max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:60]}"

def evalc(txt):
    """提取 <calc>expr</calc> 并 eval"""
    m=re.findall(r'⟨calc⟩(.+?)⟨/calc⟩', txt, re.S)
    if not m:
        m=re.findall(r'⟨calc⟩([^⟨]+)', txt, re.S)
    if not m: return None,None
    e=m[0].strip().replace('×','*').replace('^','**')
    try: return e, eval(e, {"__builtins__":{}}, {"math":math})
    except Exception as ex: return e, f"EVAL_ERR {str(ex)[:40]}"

print("="*80); print("测试1: 训练分布内 (算术) —— 工具调用能力"); print("="*80, flush=True)
import random
random.seed(1)
ok=0; N=10
for i in range(N):
    a,b=random.randint(10,99),random.randint(10,99)
    q=f"计算：{a}乘以{b}等于多少？"
    a1=ask(q,40)
    e,v=evalc(a1)
    good = (v==a*b)
    ok+=good
    print(f"  [{i+1}] {a}x{b}={a*b}  |  模型: {a1[:55]}  |  提取: {e} -> {v}  {'✅' if good else '❌'}", flush=True)
print(f"\n  分布内准确率: {ok}/{N} = {100*ok/N:.0f}%", flush=True)

print("\n"+"="*80); print("测试2: 分布外 (符号/微积分/黎曼几何)"); print("="*80, flush=True)
OOD=[
 "求 f(x)=x^3 的导数。",
 "计算定积分 ∫_0^1 x^2 dx。",
 "平面上的圆，曲率是多少？",
 "二维球面度规 g=diag(1,sin^2θ)，Christoffel 符号 Γ^θ_φφ 等于多少？",
 "黎曼曲率张量 R_abcd 关于 a,b 是对称还是反对称？",
 "单位球面的标量曲率 R 等于多少？",
]
for q in OOD:
    print(f"\n  Q: {q}\n     A: {ask(q,80)[:130]}", flush=True)

print("\n"+"="*80); print("测试3: 思维链引导 (把难题拆成可工具化的步骤)"); print("="*80, flush=True)
COT=[
 ("第1步:写出度规分量",
  "二维球面，坐标(θ,φ)，度规 g_θθ 和 g_φφ 分别等于多少？用表达式回答。"),
 ("第2步:写Christoffel公式",
  "Christoffel 符号 Γ^a_bc = 1/2 g^ad (∂_b g_dc + ∂_c g_db - ∂_d g_bc)。"
  "对二维球面，请写出 Γ^θ_φφ 的表达式。"),
 ("第3步:算Γ^θ_φφ",
  "对 g_φφ=sin²θ，计算 Γ^θ_φφ = -(1/2)(∂_θ g_φφ)/g_θθ。结果表达式？"),
 ("第4步:算R^φ_θφθ",
  "已知 Γ^θ_φφ=-sinθcosθ, Γ^φ_θφ=cotθ。计算 R^φ_θφθ = ∂_θΓ^φ_φθ - ∂_φΓ^φ_θθ + ...，最终值？"),
 ("第5步:标量曲率",
  "二维球面，R_θθ=1, R_φφ=sin²θ, g^θθ=1, g^φφ=1/sin²θ。"
  "R = g^ab R_ab = ? 用表达式回答。"),
]
for tag,q in COT:
    r=ask(q,90)
    e,v=evalc(r)
    print(f"\n  [{tag}]\n     Q: {q[:70]}\n     A: {r[:120]}", flush=True)
    if e: print(f"     ★ 提取表达式: {e} -> {v}", flush=True)
print("\nTOOL_DONE")
