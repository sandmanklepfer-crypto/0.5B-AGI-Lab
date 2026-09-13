# -*- coding: utf-8 -*-
"""直接压制拒绝话术的token: 让模型物理上无法输出'对不起...没学会'"""
import sys
sys.path.insert(0,'/root/autodl-tmp/llama.cpp/gguf-py')
import numpy as np
from gguf import GGUFReader
r=GGUFReader('/root/autodl-tmp/calc_v1.gguf')
# 读词表
toks=None
for k,v in r.kv.items():
    if k=='tokenizer.ggml.tokens':
        toks=v; break
print("词表大小", len(toks) if toks else 0)
if toks is None:
    # 从 fields 读
    f=r.fields.get('tokenizer.ggml.tokens')
    if f is not None:
        toks=[str(x) for x in f.contents()]
print("词表(2)", len(toks) if toks else 0)
print("示例 token:", [toks[i] for i in [0,100,1000,8000,10000] ] if toks else "无")
# 找拒绝相关 token
REJ_CHARS="对不起无法不能抱歉学会回答这个问题"
BAN=[-1.0]*(len(toks) if toks else 0)
hit=0
if toks:
    for i,t in enumerate(toks):
        s=t.replace('▁',' ').replace('Ġ',' ').strip()
        if not s: continue
        # 单字或短词命中
        if any(ch in s for ch in "对不起无法不能抱歉学会拒不") and len(s)<=3:
            BAN[i]=-1.0; hit+=1
print(f"命中拒绝相关token: {hit}")
# 生成 bias
b=np.zeros(len(toks),np.float32)
STR=30.0
for i,v in enumerate(BAN):
    if v<0: b[i]=-STR
b.tofile('/root/autodl-tmp/bias_ban100.bin')
print(f"bias_ban100 写入: 压制 {hit} 个token, 强度 -{STR}")
print("BAN_DONE")
