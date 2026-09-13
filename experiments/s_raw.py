# -*- coding: utf-8 -*-
"""看原始输出 + 测泛化(无few-shot)"""
import json, urllib.request
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(msgs, mx=250, t=0.0):
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"]
    except Exception as e: return f"ERR {str(e)[:50]}"

print("="*88); print("【A】完整原始输出 (看它怎么'说话')"); print("="*88, flush=True)
for q in ["计算：27乘以82等于多少？",
          "对 sin(theta) 平方求 theta 的导数"]:
    print(f"\n{'─'*80}\n问: {q}\n{'─'*80}", flush=True)
    print(ask([{"role":"user","content":q}]), flush=True)

print("\n"+"="*88); print("【B】无 few-shot, 直接让它翻译 (测原生性)"); print("="*88, flush=True)
SYS_MIN="把中文数学任务翻译成 sympy 代码，只输出代码。"
CROSS=[
 "求 x 的平方的导数",
 "对 sin(x) 积分",
 "解方程 x+3=10",
 "求 1/x 的导数",
 "化简 cos(x) 的平方加 sin(x) 的平方",
 "求 3x=12 中的 x",
 "对 e 的 x 次方求导",
 "求 ln(x) 的导数",
]
for q in CROSS:
    a=ask([{"role":"system","content":SYS_MIN},{"role":"user","content":q}],mx=60)
    print(f"  {q:<34} -> {a.strip().split(chr(10))[-1][:60]}", flush=True)
print("RAW_DONE")
