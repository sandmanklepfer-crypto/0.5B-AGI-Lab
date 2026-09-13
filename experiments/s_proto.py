# -*- coding: utf-8 -*-
"""测: few-shot 能否引导出「先形式验证 → 不行再自推」的协议"""
import json, urllib.request
def ask(port,msgs,mx=110):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":0.2}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=90).read())["choices"][0]["message"]["content"].strip().replace("\n"," ")[:170]
    except Exception as e: return f"ERR {str(e)[:30]}"
# few-shot 教"先验证再自推"
FS=[
 {"role":"user","content":"计算：12+34等于多少？"},
 {"role":"assistant","content":"我先尝试形式验证。这可以形式化。答案 = ⟨calc⟩12+34⟨/calc⟩"},
 {"role":"user","content":"为什么天是蓝色的？"},
 {"role":"assistant","content":"我先尝试形式验证。这个问题无法用形式工具验证。那么我尝试自己推理：太阳光被大气分子散射，蓝光波长短散射强，所以天空呈蓝色。"},
]
QS=["计算：56乘以7等于多少？","求 cos(x) 对 x 的导数。","为什么水会结冰？","黎曼猜想是什么？"]
print("="*92); print("行为协议测试 (few-shot, neg100模型)"); print("="*92, flush=True)
for q in QS:
    a=ask(8093, FS+[{"role":"user","content":q}])
    print(f"\n  Q: {q}\n     A: {a}", flush=True)
print("\nPROTO_DONE")
