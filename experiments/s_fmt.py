# -*- coding: utf-8 -*-
"""★ 验证: 失败原因是"多做一步", 不是"算不出来" """
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=120,t=0.0):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
CUR="-1024*cos(2*x)"; TRUE="2048*sin(2*x)"
TESTS=[
 ("① 自由回答",              f"当前表达式 = {CUR}。请给出它的导数。"),
 ("② +只输出一行",           f"当前表达式 = {CUR}。求它的导数。只输出一行, 不要解释, 不要化简。"),
 ("③ +禁止化简",             f"当前表达式 = {CUR}。求导。直接输出结果, 禁止做任何化简或进一步运算。"),
 ("④ +固定格式(如few-shot)", f"示例: 已知 x**3, 输出 3*x**2\n已知 {CUR}, 输出"),
 ("⑤ +只报系数",             f"当前表达式 = {CUR} 是连续求导第11步。第12步的系数是多少? 只输出数字。"),
]
print("="*90); print(f"★ 格式纪律测试  (当前={CUR}, 真值={TRUE})"); print("="*90, flush=True)
for tag,q in TESTS:
    a=ask(q)
    print(f"\n  {tag}", flush=True)
    print(f"    {a[:150]}", flush=True)
print("\nFMT_DONE")
