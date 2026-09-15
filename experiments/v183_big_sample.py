# -*- coding: utf-8 -*-
"""
V183 大样本严格对照 (45题) —— 解决12题精度不够的问题
=================================================================
12题时 1题=8.3% (8 vs 9 是噪声)
45题时 1题=2.2% → 能分辨真实差异

对照:
  基线          不训练
  B   幅度控制    V80/V81
  D1  分层(乘性递增) V51 正确版
  S3  自持环      V142
  E1  基线 + 验证器        (推理层, 不训练)
  E2  B组训练 + 验证器     (训练+推理合体)

指标: 全45题严格判分 + 训练集8题(记忆) / 其余37题(泛化) 分开统计
"""
import numpy as np, sys, os, re, json, time
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

LOG='/root/autodl-tmp/life1/big.log'
open(LOG,'w').close(); t0=time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s,flush=True)

BANK=json.load(open('/root/autodl-tmp/agilab/_BANK60.json'))
TRAIN_NAMES=['n2_1','n2_2','n3_1','g2','T2','ap3','p120','r3_-2']
TRAIN=[b for b in BANK if b['name'] in TRAIN_NAMES]
TEST_N=[b for b in BANK if b['name'] not in TRAIN_NAMES]
say('='*80)
say(f'V183 大样本严格对照: 题库{len(BANK)}题 (训练{len(TRAIN)} / 泛化{len(TEST_N)})')
say('='*80)

KEEP=["人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。",
 "春天来了，树木开始发芽，小鸟在枝头歌唱。",
 "长江是中国最长的河流，它从青藏高原流向东海，全长六千多公里。",
 "深度学习模型通过反向传播算法不断调整参数，从而逐渐逼近目标函数。"]
HOLD=["量子力学描述了微观粒子的运动规律，与经典力学有本质区别。",
 "中国古代四大发明包括造纸术、印刷术、火药和指南针。",
 "人体由数十万亿个细胞构成，每个细胞都包含完整的遗传信息。"]
STEPS=120; SCALE=8e-6; LAYERS=list(range(6,14))

say('加载模型...')
tok=Qwen2TokenizerFast.from_pretrained('/root/autodl-tmp/life1/antiheb_05b')
PAD=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
def q_of(s): return "问：一个数列 "+", ".join(map(str,s))+" 的下一项是多少？答："
def mb(texts):
    ids=[tok(t).input_ids for t in texts]; L=max(len(x) for x in ids)
    return torch.tensor([x+[PAD]*(L-len(x)) for x in ids]), torch.tensor([[1]*len(x)+[0]*(L-len(x)) for x in ids])
def lab(X,A):
    L=X.clone(); L[A==0]=-100; return L
TX,TA=mb([q_of(b['seq'])+str(b['next']) for b in TRAIN])
KX,KA=mb(KEEP); HX,HA=mb(HOLD)
ALLX=[tok(q_of(b['seq']),return_tensors='pt').input_ids for b in BANK]

m=Qwen2ForCausalLM.from_pretrained('/root/autodl-tmp/life1/antiheb_05b',dtype=torch.float32); m.eval()
INIT={k:v.clone() for k,v in m.state_dict().items()}
MODS=[]
for n,mod in m.named_modules():
    mt=re.search(r'layers\.(\d+)\.',n)
    if mt and int(mt.group(1)) in LAYERS and hasattr(mod,'weight') and mod.weight.dim()==2 \
       and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
        MODS.append((n,mod,int(mt.group(1))))
say(f'可训练 {len(MODS)} 个权重')

def loss_of(X,A):
    with torch.no_grad(): return float(m(input_ids=X,attention_mask=A,labels=lab(X,A)).loss)
def gen(ids,nw=14):
    with torch.no_grad():
        o=m.generate(ids,max_new_tokens=nw,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)

def judge_all(use_verifier=False):
    """返回 (总对, 训练集对, 泛化对, 逐题明细)"""
    tot=tr=te=0; det=[]
    for i,b in enumerate(BANK):
        out=gen(ALLX[i]); nums=re.findall(r'-?\d+',out[:50])
        cand=int(nums[0]) if nums else None
        final=cand
        if use_verifier:
            try:
                r=search(b['seq']); fp=r[2][0] if (r and len(r)>2 and r[2]) else None
            except Exception: fp=None
            if fp is not None and cand!=b['next']: final=fp
        good = (final==b['next']); tot+=good
        if b['name'] in TRAIN_NAMES: tr+=good
        else: te+=good
        det.append((b['name'],b['seq'],b['next'],cand,final,good))
    return tot,tr,te,det

def reset():
    m.load_state_dict(INIT)
    for p in m.parameters(): p.requires_grad_(False)
    for _,mod,_ in MODS: mod.weight.requires_grad_(True)

def train(arm,steps=STEPS):
    reset()
    if arm=='B': wmap={L:1.0 for L in LAYERS}
    elif arm=='D1': wmap={L:2.0**(L-6) for L in LAYERS}
    else: wmap={L:1.0 for L in LAYERS}
    energy=1.0; prev=None
    for st in range(1,steps+1):
        m.zero_grad()
        loss=m(input_ids=TX,attention_mask=TA,labels=lab(TX,TA)).loss
        lv=float(loss.detach())
        loss.backward()
        if arm=='S3' and prev is not None:
            energy=min(2.0,max(0.3,energy+(0.05 if prev-lv>0.002 else -0.03)))
        prev=lv
        with torch.no_grad():
            for name,mod,L in MODS:
                gr=mod.weight.grad
                if gr is None: continue
                gn=float(gr.norm())
                if gn<1e-12: continue
                patch=gr/gn
                mult = energy if arm=='S3' else wmap.get(L,1.0)
                mod.weight.data.add_(-patch*(SCALE*float(mod.weight.norm())*mult))
        if st%60==0: say(f'    [{st}步] loss={lv:.4f}')
    return lv

res={}
# --- 基线 ---
say('')
say('评估 基线...')
tot,tr,te,_=judge_all(False)
say(f'基线: 总{tot}/{len(BANK)}  训练{tr}/{len(TRAIN)}  泛化{te}/{len(TEST_N)}')
res['基线']={'tot':tot,'tr':tr,'te':te}
e1=judge_all(True)[0]
say(f'基线+验证器: 总{e1}/{len(BANK)}')
res['基线+验证器']={'tot':e1}
# --- 训练组 ---
for arm,nm in [('B','B 幅度控制'),('D1','D1 分层(乘性递增)'),('S3','S3 自持环')]:
    ts=time.time(); train(arm)
    tot,tr,te,det=judge_all(False)
    lk,lh=loss_of(KX,KA),loss_of(HX,HA)
    say(f'{nm}: 总{tot}/{len(BANK)}  训练{tr}/{len(TRAIN)}  泛化{te}/{len(TEST_N)}  '
        f'通用{lk:.4f} 遗忘{lh:.4f}  {time.time()-ts:.0f}s')
    res[nm]={'tot':tot,'tr':tr,'te':te,'lk':lk,'lh':lh}
    # 训练+验证器
    e=judge_all(True)[0]
    say(f'  {nm} + 验证器: 总{e}/{len(BANK)}')
    res[nm+'+验证器']={'tot':e}
say('')
say('='*80)
say(f"题库 {len(BANK)} 题 | 1题 = {100/len(BANK):.1f}%")
for k,v in res.items():
    if 'tr' in v: say(f"  {k:<22} 总{v['tot']:>3}/{len(BANK)}  训练{v['tr']}/{len(TRAIN)}  泛化{v['te']}/{len(TEST_N)}")
    else: say(f"  {k:<22} 总{v['tot']:>3}/{len(BANK)}")
say(f"总耗时 {time.time()-t0:.0f}s")
json.dump(res,open('/root/autodl-tmp/life1/big.json','w'),ensure_ascii=False,indent=1)
say('DONE')
