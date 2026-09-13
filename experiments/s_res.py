# -*- coding: utf-8 -*-
"""测: 水库/纸带式的外部状态, 能不能延长链? (分离"计数"和"结构知识")"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=200,t=0.0):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x')
def E(code):
    try: return str(sp.simplify(eval(code.strip().strip('`'),{"__builtins__":{}},
        {"diff":diff,"simplify":simplify,"sin":sin,"cos":cos,"x":x})))
    except Exception as e: return "ERR"

print("="*94); print("【A】给显式计数器: 它能'继续'吗? (模拟纸带存了步数)"); print("="*94, flush=True)
# 不给历史, 只给"当前是第几步 + 当前表达式"
for k,cur in [(3,"-4*cos(2*x)"),(7,"-64*cos(2*x)"),(11,"-1024*cos(2*x)")]:
    q=(f"这是一次连续求导的第{k}步。当前表达式 = {cur}。"
       f"请给出第{k+1}步的结果, 只输出表达式。")
    a=ask(q)
    true_expr=str(sp.simplify(sp.diff(sp.sin(x)*sp.cos(x),x,k+1)))
    print(f"  第{k}步 ->第{k+1}步 | 模型: {a[:60]:<62} 真值: {true_expr}", flush=True)

print("\n"+"="*94); print("【B】给'结构知识': 周期4 + 系数翻倍 (模拟水库存的模式)"); print("="*94, flush=True)
base=("已知规律: 对 sin(x)*cos(x) 连续求导时,\n"
      "  · 每一步系数乘以2, 符号每4步循环 (+,+,-,-,\u2026)\n"
      "  · 函数在 sin(2x) 和 cos(2x) 之间交替\n"
      "  · 第1阶 = cos(2x), 第2阶 = -2sin(2x)\n")
for k in [5,9,12,20]:
    q=base+f"问: 第{k}阶导是什么? 只输出表达式。"
    a=ask(q)
    t=str(sp.simplify(sp.diff(sp.sin(x)*sp.cos(x),x,k)))
    print(f"  第{k:2d}阶 | 模型: {a[:58]:<60} 真值: {t}", flush=True)

print("\n"+"="*94); print("【C】水库式数值状态: 注入计数向量能帮到吗?"); print("="*94, flush=True)
# 用数字编码步数, 看模型能否用
for k in [3,7,11]:
    q=(f"[状态向量: step={k}, 上一步系数={2**(k-1)}, 函数={'cos' if k%2==1 else 'sin'}, 符号={'-' if k%4 in (2,3) else '+'}]\n"
       f"根据上面的状态向量, 第{k+1}阶导的系数和函数是什么? 只输出: 系数,函数")
    a=ask(q, 80)
    ck=2**k; fn='cos' if (k+1)%2==1 else 'sin'; sg='-' if (k+1)%4 in (2,3) else '+'
    print(f"  k={k:2d} | 模型: {a[:56]:<58} 真值: {sg}{ck},{fn}", flush=True)

print("\n"+"="*94); print("【D】对照: 同样状态, 但要求调工具"); print("="*94, flush=True)
for k,cur in [(11,"-1024*cos(2*x)")]:
    q=(f"当前表达式 = {cur}。请调用工具求它的导数, 只输出一行代码。")
    a=ask(q,80)
    m=re.findall(r'(diff\([^)]*\))',a)
    print(f"  模型原始: {a[:80]}", flush=True)
    if m: print(f"  提取调用: {m[0]} -> {E(m[0])}", flush=True)
print("RES_DONE")
