# -*- coding: utf-8 -*-
"""
V180b 分层配比训练(快速版) —— 50步/组, 分步进度
=================================================================
A 纯SGD | B +幅度控制 | C +antiHeb | D +分层轮换 | E +验证器
优化: 模型只加载一次, 每组用 state_dict 恢复 (省 15秒×5)
"""
import numpy as np, sys, os, re, json, time, copy
for _n,_t in [('long',np.int64),('ulong',np.uint64),('uintc',np.uint32),
              ('longlong',np.int64),('ulonglong',np.uint64),('int',int),
              ('float',float),('bool',bool),('object',object),('str',str)]:
    if not hasattr(np,_n):
        try: setattr(np,_n,_t)
        except Exception: pass
import torch
torch.set_num_threads(8)
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
from transformers.models.qwen2.tokenization_qwen2_fast import Qwen2TokenizerFast
sys.path.insert(0,'/root/autodl-tmp/agilab/src')
from form_library import search

LOG='/root/autodl-tmp/life1/tier2.log'
open(LOG,'w').close(); t0=time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s,flush=True)

BANK=[([1,4,9,16,25],36),([3,8,15,24,35],48),([2,4,8,16,32],64),
 ([1,2,5,14,42],132),([2,7,20,57,166],491),([1,3,6,10,15],21),
 ([1,1,2,3,5,8],13),([2,3,5,7,11],13),([1,8,27,64,125],216),
 ([1,2,4,8,16,32],64),([5,10,20,40,80],160),([1,4,10,22,46],94)]
TRAIN=[([1,4,9,16,25],36),([2,4,8,16,32],64),([1,1,2,3,5,8],13),([5,10,20,40,80],160)]
KEEP=["人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。",
 "春天来了，树木开始发芽，小鸟在枝头歌唱。",
 "长江是中国最长的河流，它从青藏高原流向东海，全长六千多公里。",
 "深度学习模型通过反向传播算法不断调整参数，从而逐渐逼近目标函数。"]
HOLD=["量子力学描述了微观粒子的运动规律，与经典力学有本质区别。",
 "中国古代四大发明包括造纸术、印刷术、火药和指南针。",
 "人体由数十万亿个细胞构成，每个细胞都包含完整的遗传信息。"]
STEPS=50; LR=2e-5; SCALE=8e-6; LAYERS=list(range(6,14))

say('='*78)
say('V180b 分层配比(快速版): 50步/组, 逐机制叠加')
say('='*78)
tok=Qwen2TokenizerFast.from_pretrained('/root/autodl-tmp/life1/antiheb_05b')
PAD=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
def q_of(s): return "问：一个数列 "+", ".join(map(str,s))+" 的下一项是多少？答："
def txt(s):
    a=next((b for x,b in BANK if x==s),'')
    return q_of(s)+str(a)
def mb(texts):
    ids=[tok(t).input_ids for t in texts]; L=max(len(x) for x in ids)
    return torch.tensor([x+[PAD]*(L-len(x)) for x in ids]), torch.tensor([[1]*len(x)+[0]*(L-len(x)) for x in ids])
def lab(X,A):
    L=X.clone(); L[A==0]=-100; return L
TX,TA=mb([txt(s) for s,_ in TRAIN])
KX,KA=mb(KEEP); HX,HA=mb(HOLD)
ALLX=[tok(q_of(s),return_tensors='pt').input_ids for s,_ in BANK]

say('加载模型(一次)...')
m=Qwen2ForCausalLM.from_pretrained('/root/autodl-tmp/life1/antiheb_05b',dtype=torch.float32); m.eval()
INIT={k:v.clone() for k,v in m.state_dict().items()}
say(f'  加载完成 {time.time()-t0:.0f}s')

def mods_of():
    out=[]
    for n,mod in m.named_modules():
        mt=re.search(r'layers\.(\d+)\.',n)
        if mt and int(mt.group(1)) in LAYERS and hasattr(mod,'weight') and mod.weight.dim()==2 \
           and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
            out.append((n,mod))
    return out
MODS=mods_of()
say(f'  可训练权重 {len(MODS)} 个')
def loss_of(X,A):
    with torch.no_grad(): return float(m(input_ids=X,attention_mask=A,labels=lab(X,A)).loss)
def gen(ids,nw=14):
    with torch.no_grad():
        o=m.generate(ids,max_new_tokens=nw,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)
def score(verifier=False):
    ok=0; det=[]
    for i,(s,ans) in enumerate(BANK):
        out=gen(ALLX[i]); nums=re.findall(r'-?\d+',out[:50])
        cand=int(nums[0]) if nums else None; final=cand
        if verifier:
            try:
                r=search(s); fp=r[2][0] if (r and len(r)>2 and r[2]) else None
            except Exception: fp=None
            if fp is not None and cand!=ans: final=fp
        g=(final==ans); ok+=g; det.append((s,ans,cand,final,g))
    return ok,det

def reset():
    m.load_state_dict(INIT)
    for p in m.parameters(): p.requires_grad_(False)
    for _,mod in MODS: mod.weight.requires_grad_(True)

def train(mode,steps=STEPS):
    reset(); dirs={}
    for st in range(1,steps+1):
        m.zero_grad()
        loss=m(input_ids=TX,attention_mask=TA,labels=lab(TX,TA)).loss
        loss.backward()
        act=set()
        if mode>=4:
            g=(st//10)%3
            act=set([6,7,8,9]) if g==0 else (set([10,11]) if g==1 else set([12,13]))
        with torch.no_grad():
            for name,mod in MODS:
                gr=mod.weight.grad
                if gr is None: continue
                if mode>=4:
                    L=int(re.search(r'layers\.(\d+)\.',name).group(1))
                    if L not in act: continue
                if mode>=2:
                    gn=float(gr.norm())
                    if gn<1e-12: continue
                    patch=gr/gn
                else: patch=gr
                if mode>=3:
                    for ud in dirs.get(name,[])[-8:]:
                        patch=patch-(patch*ud).sum()*ud
                    pn=float(patch.norm())
                    if pn<1e-12: continue
                    patch=patch/pn
                    dirs.setdefault(name,[]).append(patch.clone())
                sz = SCALE*float(mod.weight.norm()) if mode>=2 else LR
                mod.weight.data.add_(-patch*sz)
        if st%25==0: say(f'    [{st}步] train_loss={float(loss):.4f}')
    return m

ok0,det0=score()
say(f'基线: 12题严格 {ok0}/12   通用{loss_of(KX,KA):.4f}  遗忘{loss_of(HX,HA):.4f}')
ok0v,_=score(True)
say(f'基线+验证器: {ok0v}/12')
say('')
say(f"{'组':<22}{'12题':>8}{'通用':>10}{'遗忘':>10}{'耗时':>8}")
res={}
for mode,name in [(1,'A 纯SGD'),(2,'B +幅度控制'),(3,'C +antiHeb'),(4,'D +分层轮换')]:
    ts=time.time(); train(mode)
    ok,_=score(); lk,lh=loss_of(KX,KA),loss_of(HX,HA)
    say(f"{name:<22}{ok:>6}/12{lk:>10.4f}{lh:>10.4f}{time.time()-ts:>7.0f}s")
    res[name]={'ok':ok,'lk':lk,'lh':lh}
say('')
say('--- E: D组训练 + 形式库验证器 ---')
train(4)
ok_e,det=score(True)
say(f"{'E D组+验证器':<22}{ok_e:>6}/12")
for s,ans,cand,final,g in det:
    say(f"    {str(s):<22} 真值{ans:<6} 模型{str(cand):<6} 采纳{str(final):<6} {'✅' if g else '❌'}")
say('')
say('='*78)
say(f"总结: 基线{ok0}/12 | 基线+验证器{ok0v}/12 | E合体{ok_e}/12 | 形式库单独12/12")
say(f"总耗时 {time.time()-t0:.0f}s")
say('DONE')
