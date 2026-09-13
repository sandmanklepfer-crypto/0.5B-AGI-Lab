# -*- coding: utf-8 -*-
"""分离三件事: 知道步骤 / 记忆状态 / 计划能力"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=260,t=0.0,sys=None):
    ms=[]
    if sys: ms.append({"role":"system","content":sys})
    ms.append({"role":"user","content":q})
    b=json.dumps({"messages":ms,"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x')

print("="*92); print("【T1】知道步骤吗? (知识, 不需要记忆)"); print("="*92, flush=True)
Q1=["要计算 sin(x)*cos(x) 的12阶导数, 一共需要几步? 每一步做什么? 只列步骤, 不要计算。",
    "sin(x) 求导4次会回到自己吗? 导数有什么周期性规律?",
    "一个导数链有12步, 如果第3步算错了, 后面9步会怎样?"]
for q in Q1:
    print(f"\n  Q: {q}\n  A: {ask(q)[:280]}", flush=True)

print("\n"+"="*92); print("【T2】记忆状态吗? (给完整状态, 只做最后一步)"); print("="*92, flush=True)
# 给完整推导历史, 要求做下一步
HIST="""已知推导历史:
sin(x)*cos(x) 的1阶导 = cos(2*x)
2阶导 = -2*sin(2*x)
3阶导 = -4*cos(2*x)
4阶导 = 8*sin(2*x)
5阶导 = 16*cos(2*x)
6阶导 = -32*sin(2*x)
7阶导 = -64*cos(2*x)
8阶导 = 128*sin(2*x)
9阶导 = 256*cos(2*x)
10阶导 = -512*sin(2*x)
11阶导 = -1024*cos(2*x)
请给出第12阶导。只回答表达式。"""
print(f"\n  Q: (给完整历史, 求第12阶导)", flush=True)
print(f"  A: {ask(HIST)[:200]}", flush=True)
print(f"  真值: 12阶导 = 2048*sin(2*x)", flush=True)

print("\n"+"="*92); print("【T3】计划能力? (能否自己说出'下一步该调什么')"); print("="*92, flush=True)
S="""多步推导器。可用: diff(f,x) 求导, simplify(e) 化简, trigsimp(e) 三角化简
目标: 求 sin(x)**2 的导数并化简到最简形式
当前状态: 未开始
请只回答: 总共几步? 每步调用什么? 格式: 步数|第1步|第2步|..."""
print(f"\n  Q: {S[60:]}", flush=True)
print(f"  A: {ask(S)[:280]}", flush=True)

print("\n"+"="*92); print("【T4】记忆衰减? (同样状态, 放在开头 vs 结尾)"); print("="*92, flush=True)
STATE="当前表达式是 1024*cos(2*x) "
TASK="请对它求导, 输出结果表达式。"
# 结尾放状态
a1=ask(f"背景信息: 这是一次连续求导推导的第11步。\n{TASK}\n{STATE}")
# 开头放状态 + 长干扰
noise="无关内容。"*40
a2=ask(f"{STATE}\n{noise}\n{TASK}")
print(f"\n  状态在结尾: {a1[:120]}", flush=True)
print(f"  状态+长干扰后: {a2[:120]}", flush=True)
print(f"  真值: diff(1024*cos(2*x),x) = -2048*sin(2*x)", flush=True)

print("\n"+"="*92); print("【T5】它知道'周期4'这个结构吗? (纯知识, 零记忆)"); print("="*92, flush=True)
for q in ["sin(x) 的100阶导数是什么? (提示: 导数4次一循环)",
          "cos(x) 的导数4次一循环, 第4阶导等于?",
          "如果导数周期是4, 第13阶导等于第几阶导?"]:
    print(f"\n  Q: {q}\n  A: {ask(q)[:150]}", flush=True)
print("MEM_DONE")
