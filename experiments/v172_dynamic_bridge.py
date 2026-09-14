# -*- coding: utf-8 -*-
"""
V172 动态桥 —— 每轮重建桥基再重流
=================================================================
V171 证伪: 固定桥 + 反复走 = 线性叠加, 无复利
V172 检验: 每轮重建桥 (桥建立在上一轮成果之上) 会不会产生复利?

用户 pipeline.py 的真实机制:
  跳跃 -> 形式化(找规则) -> 固化(规则写进库) -> 下一轮跳跃【在更大的库里跳】
  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ 关键: 库变大 = 桥重建

本实验:
  第1轮: 用原始权重建桥 B1 -> 重流 -> 保存
  第2轮: 用【第1轮后的新权重】重建桥 B2 -> 重流 -> 保存
  第3轮: 用【第2轮后的新权重】重建桥 B3 -> ...
  对比: 固定桥(走16轮) vs 动态桥(重建16次)

指标: 总偏移 / 桥维重叠率 / 困惑度 / 语义样例
"""
import numpy as np
for _n,_t in [('long',np.int64),('ulong',np.uint64),('uintc',np.uint32),
              ('longlong',np.int64),('ulonglong',np.uint64),('int',int),
              ('float',float),('bool',bool),('object',object),('str',str)]:
    if not hasattr(np,_n):
        try: setattr(np,_n,_t)
        except Exception: pass
import torch, math, json, time
torch.set_num_threads(8)
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
from transformers.models.qwen2.tokenization_qwen2_fast import Qwen2TokenizerFast

SRC='/root/autodl-tmp/life1/antiheb_05b'
LOG='/root/autodl-tmp/life1/dyn.log'
OUT='/root/autodl-tmp/life1/dyn_result.json'
ALPHA=0.01; R_RATIO=0.28; ROUNDS=16; H=896

open(LOG,'w').close(); t0=time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s,flush=True)

say('='*78)
say('V172 动态桥: 每轮重建桥基 (桥建立在上一轮成果之上)')
say('='*78)

tok=Qwen2TokenizerFast.from_pretrained(SRC)
TXT=["人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。",
     "春天来了，树木开始发芽，小鸟在枝头歌唱。",
     "数学是研究数量关系和空间形式的科学。",
     "深度学习模型通过反向传播算法不断调整参数，从而逐渐逼近目标函数。",
     "长江是中国最长的河流，它从青藏高原流向东海，全长六千多公里。"]
Q="你好，请介绍一下你自己。"

say('加载模型...')
m=Qwen2ForCausalLM.from_pretrained(SRC,dtype=torch.float32); m.eval()

mods=[]
for n,mod in m.named_modules():
    if hasattr(mod,'weight') and mod.weight is not None and mod.weight.dim()==2 \
       and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
        mods.append((n,mod))
say(f'目标权重 {len(mods)} 个  ({time.time()-t0:.1f}s)')

# 按层分组 (建桥要按层)
import re
layers={}
for n,mod in mods:
    mt=re.search(r'layers\.(\d+)\.',n)
    L=int(mt.group(1)) if mt else -1
    layers.setdefault(L,[]).append((n,mod))
say(f'层数 {len(layers)}')

def ppl(model):
    tl,tn=0.0,0
    for t in TXT:
        ids=tok(t,return_tensors='pt').input_ids
        with torch.no_grad(): o=model(ids,labels=ids)
        tl+=float(o.loss)*(ids.shape[1]-1); tn+=ids.shape[1]-1
    return math.exp(tl/tn)
def gen(model,q=Q,nw=26):
    ids=tok(q,return_tensors='pt').input_ids
    with torch.no_grad(): o=model.generate(ids,max_new_tokens=nw,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)

W0={n:mod.weight.data.clone() for n,mod in mods}
base_ppl=ppl(m)
say(f'基线困惑度 = {base_ppl:.4f}')
say(f'基线输出: {gen(m)[:60]}')
say('')

def build_bridge():
    """★ 用【当前权重】重建桥基 (逐层对齐)"""
    bridge=None; dims=[]
    for L in sorted(layers):
        bases=[]
        for n,mod in layers[L]:
            W=mod.weight.data.float()
            U,S,Vh=torch.linalg.svd(W,full_matrices=False)
            if Vh.shape[1]==H: bases.append(Vh)
            elif U.shape[1]==H: bases.append(U.T)
        if not bases: continue
        B=torch.cat(bases,0)
        Qq,_=torch.linalg.qr(B.T)
        Rb=max(4,int(H*R_RATIO)); Qq=Qq[:,:Rb]
        if bridge is None: bridge=Qq
        else:
            mm=min(bridge.shape[1],Qq.shape[1])
            A_,B_=bridge[:,:mm],Qq[:,:mm]
            Ua,_,Vb=torch.linalg.svd(A_.T@B_,full_matrices=False)
            bridge=B_@(Vb@Ua.T)
        dims.append(int(Qq.shape[1]))
    return bridge,dims

def reflow(bridge):
    """顺当前桥重流: 只重排 S, U/Vᵀ 不动"""
    devs=[]
    for n,mod in mods:
        W=mod.weight.data.float()
        U,S,Vh=torch.linalg.svd(W,full_matrices=False)
        k=S.numel(); R=max(4,int(k*R_RATIO))
        if R>=k: continue
        head=S[:R].sum(); tail=S[R:].sum()
        S2=S.clone(); S2[:R]=S2[:R]*(1.0+ALPHA*tail/(head+1e-8))
        S2=S2*(S.norm()/(S2.norm()+1e-8))
        W2=(U*S2)@Vh
        devs.append(float((W2-W).norm()/(W.norm()+1e-8)))
        mod.weight.data.copy_(W2.to(mod.weight.dtype))
    return max(devs) if devs else 0.0

def total_dev():
    num=den=0.0
    for n,mod in mods:
        W=mod.weight.data.float()
        num+=float((W-W0[n]).norm())**2; den+=float(W0[n].norm())**2
    return (num**0.5)/(den**0.5)

say(f"{'轮':>4}{'总偏移':>10}{'本轮最大步':>12}{'重建桥用':>10}{'困惑度':>12}{'倍数':>8}  判定")
res={'base_ppl':base_ppl,'alpha':ALPHA,'mode':'dynamic_bridge','rounds':[]}
prev_bridge=None
for rd in range(1,ROUNDS+1):
    ts=time.time()
    bridge,dims=build_bridge()             # ★ 每轮重建
    tb=time.time()-ts
    step=reflow(bridge)
    rel=total_dev(); p=ppl(m); ratio=p/base_ppl
    ok=ratio<1.25; tag='✅保' if ok else ('⚠️劣' if ratio<2 else '❌崩')
    say(f"{rd:>4}{rel*100:>9.2f}%{step*100:>11.2f}%{tb:>9.1f}s{p:>12.4f}{ratio:>7.2f}x  {tag}")
    res['rounds'].append({'r':rd,'dev':rel,'step':step,'build_s':round(tb,2),'ppl':p,'ratio':ratio})
    if rd in (1,3,5,8,12,16) and ok:
        say(f'     样例: {gen(m)[:64]}')
    if ratio>3.0:
        say('  -> 崩, 停止'); break

say('')
say(f'最终困惑度 = {ppl(m):.4f}  (基线 {base_ppl:.4f})')
say(f'最终输出: {gen(m)[:80]}')
say(f'总耗时 {time.time()-t0:.1f}s')
json.dump(res,open(OUT,'w'),ensure_ascii=False,indent=1)
say('DONE')
