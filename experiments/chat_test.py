# -*- coding: utf-8 -*-
"""chat_test.py — 真实对话测试(numpy 版 Qwen2.5-0.5B-Instruct)"""
import numpy as np, time
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("模型就绪 %.1fs\n"%(time.time()-t0))

def chat(user, sysmsg="You are a helpful assistant.", maxn=50, temp=0.7):
    p=("<|im_start|>system\n"+sysmsg+"<|im_end|>\n"
       "<|im_start|>user\n"+user+"<|im_end|>\n<|im_start|>assistant\n")
    ids=TK.encode(p)
    t1=time.time()
    out,info=M.gen(ids,max_new=maxn,temp=temp,top_k=40,seed=123)
    dt=time.time()-t1
    txt=TK.decode(out)
    print("【问】%s"%user)
    print("【答】%s"%txt)
    print("  [%d tok, %.1fs, %.1f tok/s]\n"%(len(out),dt,len(out)/max(dt,1e-6)))
    return txt

print("="*56)
print("  对话测试 (0.5B Instruct, 端侧真实推理)")
print("="*56+"\n")
chat("你好")
chat("什么是人工智能？")
chat("帮我写一个Python函数，计算斐波那契数列")
print("="*56)
print("  测试: 中文+代码+推理, 一次跑完")
