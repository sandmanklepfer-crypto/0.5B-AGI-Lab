# -*- coding: utf-8 -*-
"""验证 d_refusal 方向的含义: 拒绝样本 vs 正常样本的激活投影"""
import sys
sys.path.insert(0,"/root/venv_lfm2/lib/python3.12/site-packages")
import numpy as np, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tok=AutoTokenizer.from_pretrained("/root/distill_calc_v1")
md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1",dtype=torch.float32)
md.eval()
d=torch.tensor(np.fromfile('/root/autodl-tmp/l23/d_refusal.bin',np.float32))
d=d/d.norm()
# 拒绝型 prompt  vs  正常型 prompt
REJ=["求 sin(x) 对 x 的导数。","对 x 的平方求导。","黎曼张量的对称性是什么？",
     "解微分方程 dy/dx=y。","证明费马大定理。"]
NOR=["计算：347乘以28等于多少？","介绍一下你自己。","什么是人工智能？",
     "为什么天是蓝色的？","1+1等于多少？"]
def proj(lst):
    out=[]
    for q in lst:
        txt=tok.apply_chat_template([{"role":"user","content":q}],tokenize=False,add_generation_prompt=True)
        ids=tok(txt,return_tensors="pt").input_ids
        with torch.no_grad():
            hs=md(ids,output_hidden_states=True).hidden_states
        h=hs[-1][0,-1].float()      # 最后一层最后位置
        out.append(float(h@d))
    return out
a=proj(REJ); b=proj(NOR)
print("拒绝型 prompt 投影:", [f"{v:+.3f}" for v in a], flush=True)
print("  均值 %.3f" % np.mean(a), flush=True)
print("正常型 prompt 投影:", [f"{v:+.3f}" for v in b], flush=True)
print("  均值 %.3f" % np.mean(b), flush=True)
print(f"分离度: {abs(np.mean(a)-np.mean(b))/((np.std(a)+np.std(b))/2+1e-9):.2f} σ", flush=True)
print(f"结论: d 指向 {'拒绝' if np.mean(a)>np.mean(b) else '正常'}", flush=True)
print("DIR_DONE")
