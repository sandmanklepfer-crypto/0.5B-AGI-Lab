# -*- coding: utf-8 -*-
"""
V173 离散增量流水线 —— 每轮【新增一个方向】, 不微调旧的
=================================================================
V171/V172 证伪:
  连续微调(搬谱能量) → 线性叠加, 无复利
  连续微调 + 重建桥  → 退化成固定桥 (1%扰动不足以旋转250维子空间)

V173 检验用户 pipeline.py 的真实形式:
  跳跃(探索新方向) → 验证(语义/效果) → 固化(写进权重) → 库里多一个方向
  ★ 关键: 每轮【加一个新维度】, 不是微调旧维度

对比: 同样 1% 预算/轮
  A 连续微调 (V170/V171 路线)  : W' = 谱整形
  B 离散增量 (本实验)          : W' = W + α·(u vᵀ),  v ⊥ 已有桥

指标: 总偏移 / 新增方向的正交性 / 困惑度
"""
import numpy as np
for _n,_t in [('long',np.int64),('ulong',np.uint64),('uintc',np.uint32),
              ('longlong',np.int64),('ulonglong',np.uint64),('int',int),
              ('float',float),('bool',bool),('object',object),('str',str)]:
    if not hasattr(np,_n):
        try: setattr(np,_n,_t)
        except Exception: pass
import torch, math, json, time, re
torch.set_num_threads(8)
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
from transformers.models.qwen2.tokenization_qwen2_fast import Qwen2TokenizerFast

SRC='/root/autodl-tmp/life1/antiheb_05b'
LOG='/root/autodl-tmp/life1/disc.log'
OUT='/root/autodl-tmp/life1/disc_result.json'
BUDGET=0.01          # 每轮 1% 预算 (与 V170/V171 对齐)
ROUNDS=20; H=896
torch.manual_seed(20260915)

open(LOG,'w').close(); t0=time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s,flush=True)

say('='*78)
say('V173 离散增量流水线: 每轮新增一个正交方向 (不微调旧的)')
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
say(f'目标权重 {len(mods)} 个')

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
base=ppl(m)
say(f'基线困惑度 = {base:.4f}')
say(f'基线输出: {gen(m)[:60]}')
say('')

# ---------- ★ 每个权重建"方向库": 存已用过的方向, 保证新方向与其正交 ----------
lib={}
for n,mod in mods:
    W=mod.weight.data.float()
    U,S,Vh=torch.linalg.svd(W,full_matrices=False)
    # 方向库初始 = 权重自己的主方向 (前 R 个) → 新方向必须避开这些
    R=max(4,int(S.numel()*0.28))
    lib[n]={'U':U,'S':S,'Vh':Vh,'used':Vh[:R].clone(),'R':R,'W0':W.clone(),
            'n0':float(W.norm()),'u_used':U[:,:R].clone()}
say(f'方向库建立: {len(lib)} 组  ({time.time()-t0:.1f}s)')
say('')

def orth_project(v, used):
    """把 v 投影到 used 的正交补 (Gram-Schmidt)"""
    if used.shape[0]==0: return v
    G=used@v
    return v - used.T@G

def total_dev():
    num=den=0.0
    for n,mod in mods:
        W=mod.weight.data.float()
        num+=float((W-W0[n]).norm())**2; den+=float(W0[n].norm())**2
    return (num**0.5)/(den**0.5)

say(f"{'轮':>4}{'总偏移':>10}{'新增方向正交度':>16}{'库大小':>8}{'困惑度':>12}{'倍数':>8}  判定")
res={'base_ppl':base,'budget':BUDGET,'mode':'discrete_add','rounds':[]}

for rd in range(1,ROUNDS+1):
    orthos=[]
    for n,mod in mods:
        d=lib[n]
        # ★ 跳跃: 采样一个新方向, 投影到已有方向的正交补
        din=W0[n].shape[1]                     # ★ 按实际输入维 (down_proj 是 4864)
        raw=torch.randn(din)
        v=orth_project(raw, d['used'])
        nv=float(v.norm())
        if nv<1e-6: continue
        v=v/nv
        orthos.append(nv)                      # 正交度 = 剩余分量长度 (1=完全正交)
        # ★ 验证+固化: 写成秩-1 补丁, 幅度受控 (与连续微调同样 1% 预算)
        u=torch.randn(W0[n].shape[0]); u=u/u.norm()
        patch=torch.outer(u, v.to(W0[n].dtype))
        patch=patch*(d['n0']*BUDGET/ (float(patch.norm())+1e-8))
        mod.weight.data.add_(patch.to(mod.weight.dtype))
        # ★ 库增长: 把这方向标为"已用"
        d['used']=torch.cat([d['used'], v.unsqueeze(0)],0)
    rel=total_dev(); p=ppl(m); ratio=p/base
    ok=ratio<1.25; tag='✅保' if ok else ('⚠️劣' if ratio<2 else '❌崩')
    mol=sum(orthos)/len(orthos) if orthos else 0
    libsz=sum(d['used'].shape[0] for d in lib.values())//len(lib)
    say(f"{rd:>4}{rel*100:>9.2f}%{mol:>15.3f}{libsz:>8}{p:>12.4f}{ratio:>7.2f}x  {tag}")
    res['rounds'].append({'r':rd,'dev':rel,'orth':mol,'lib':libsz,'ppl':p,'ratio':ratio})
    if rd in (1,3,5,10,15,20) and ok:
        say(f'     样例: {gen(m)[:64]}')
    if ratio>3.0:
        say('  -> 崩, 停止'); break

say('')
say(f'最终困惑度 = {ppl(m):.4f}  (基线 {base:.4f})')
say(f'最终输出: {gen(m)[:80]}')
say(f'总耗时 {time.time()-t0:.1f}s')
json.dump(res,open(OUT,'w'),ensure_ascii=False,indent=1)
say('DONE')
