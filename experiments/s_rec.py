# -*- coding: utf-8 -*-
"""★ 真测水库设想: 数值递推 (状态是数字, 水库存得下)"""
import json, urllib.request, re
import numpy as np
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=60,t=0.0):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"

# 递推: x_{k+1} = 2*x_k + 1,  x_0=1
def rec(k):
    v=1
    for _ in range(k): v=2*v+1
    return v
print("="*90); print("★ 数值递推测试: x_{k+1}=2x_k+1, x_0=1  (水库能存的状态)"); print("="*90, flush=True)

print("\n【A】只给初值+规则, 要第k项 (模型自己迭代)", flush=True)
for k in [3,5,8,10]:
    a=ask(f"数列: x0=1, x(n+1)=2*x(n)+1。请问 x({k}) = ? 只输出数字。")
    m=re.findall(r'-?\d+', a)
    got=int(m[0]) if m else None
    print(f"  x({k:2d}) | 模型: {a[:50]:<52} 真值: {rec(k):<8} {'✅' if got==rec(k) else '❌'}", flush=True)

print("\n【B】给当前值+规则, 要下一项 (模拟水库提供状态)", flush=True)
print("    ★ 这就是'每步只走一步'的模式", flush=True)
cur=1; ok=0; tot=0
for k in range(1,11):
    a=ask(f"已知 x = {cur}, 规则 x(next) = 2*x + 1。求 x(next)。只输出数字。", mx=40)
    m=re.findall(r'-?\d+', a)
    got=int(m[0]) if m else None
    tot+=1
    good = (got==2*cur+1)
    ok+=good
    print(f"  第{k:2d}步: {cur:>6} -> 模型 {str(got):<8} 真值 {2*cur+1:<8} {'✅' if good else '❌'}", flush=True)
    cur=2*cur+1 if good else (got if got else cur*2+1)
print(f"  → 逐步模式: {ok}/{tot}", flush=True)

print("\n【C】★ 接'水库'式外部状态: 模型只做单步, 状态由外部(水库)保持", flush=True)
print("    (水库的作用: 替我记住 cur, 不用我复述历史)", flush=True)
cur=1; ok=0
for k in range(1,11):
    # 只给当前值, 不给任何历史
    a=ask(f"x = {cur}\nx_next = 2 * x + 1\n只输出 x_next 的数字:", mx=30)
    m=re.findall(r'-?\d+', a)
    got=int(m[0]) if m else None
    good=(got==2*cur+1); ok+=good
    print(f"  步{k:2d}: 水库给 {cur:>6}, 模型出 {str(got):<8} {'✅' if good else '❌'}", flush=True)
    cur=2*cur+1
print(f"  → {ok}/10", flush=True)

print("\n【D】对照: 不给外部状态(要模型自己从头算到第k项)", flush=True)
for k in [5,8,12]:
    a=ask(f"从 x0=1 开始, 反复做 x -> 2x+1, 做 {k} 次后 x 是多少? 只输出数字。", mx=60)
    m=re.findall(r'-?\d+', a)
    got=int(m[0]) if m else None
    print(f"  {k}次 | 模型 {str(got):<10} 真值 {rec(k):<8} {'✅' if got==rec(k) else '❌'}", flush=True)
print("REC_DONE")
