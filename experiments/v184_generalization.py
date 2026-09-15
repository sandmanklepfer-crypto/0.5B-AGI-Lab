# -*- coding: utf-8 -*-
"""
V184 判决实验: 模型的"规则外泛化" vs 验证器的"覆盖"
=================================================================
用户的批评: "验证器是面子工程, 它的泛化是假的"

V183 的问题: 训练集和测试集【同形式分布】→ 对验证器有利
            70%的形式训练都见过 → 测的是插值不是泛化

V184 设计:
  训练: 只给 封闭公式类 (n²/等比/三角/等差/多项式)   ← 7题
  测试: 全部45题, 但按【形式是否训练见过】分三组:
    G1 同形式   (n²/n³/等比/三角/等差/多项式变体)
    G2 跨形式   (递归类, 训练从没给过)
    G3 全新形式 (catalan/素数/fib, 训练从没给过)

  三方对比:
    M  模型训练后
    VA 验证器-完整   (8个形式全开)
    VB 验证器-锁定   (只开 closed_form)  ← 模拟"形式库里没有你遇到的新规律"

★ 判决标准:
   若 M 在 G2/G3 上 > VB → 模型有【验证器没有】的东西 = 规则外泛化
   若 M 在 G2/G3 上 ≈ 0 → 模型也只是模式匹配
   若 VA 在 G3 上 ≈ VB 在 G3 上 → 验证器的"能力"纯粹来自形式库覆盖面
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
import form_library as FL

LOG='/root/autodl-tmp/life1/gen.log'
open(LOG,'w').close(); t0=time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s,flush=True)

BANK=json.load(open('/root/autodl-tmp/agilab/_BANK60.json'))
# --- 形式分组 ---
def form_of(n):
    if n.startswith('n2_'): return 'sq'
    if n.startswith('n3_'): return 'cb'
    if n.startswith('g'):   return 'geo'
    if n.startswith('T'):   return 'tri'
    if n.startswith('ap'):  return 'ap'
    if n.startswith('p'):   return 'poly'
    if n.startswith('q'):   return 'poly2'
    if n.startswith('r'):   return 'rec'
    if n.startswith('cat'): return 'cat'
    if n.startswith('prime'): return 'prime'
    if n.startswith('fib'): return 'fib'
    return 'other'
CLOSED={'sq','cb','geo','tri','ap','poly','poly2'}      # 封闭公式类
RECUR={'rec','fib'}                                      # 递归类
SPECIAL={'cat','prime','other'}                          # 特殊序列

# 训练: 每类封闭公式各挑1-2题
TRAIN_N=['n2_1','n2_2','n3_1','g2','T2','ap3','p120','q2']
TRAIN={b['name']:b for b in BANK if b['name'] in TRAIN_N}

G1=[b for b in BANK if b['name'] not in TRAIN_N and form_of(b['name']) in CLOSED]
G2=[b for b in BANK if form_of(b['name']) in RECUR]
G3=[b for b in BANK if form_of(b['name']) in SPECIAL]
say('='*80)
say('V184 判决实验: 模型规则外泛化 vs 验证器覆盖')
say('='*80)
say(f'训练: {len(TRAIN)}题 (封闭公式类)')
say(f'G1 同形式(封闭,训练见过形式): {len(G1)}题')
say(f'G2 跨形式(递归,训练没给过):   {len(G2)}题')
say(f'G3 全新形式(cat/素数/fib):    {len(G3)}题')

# --- 验证器: 可控形式 ---
def verify(seq, mode):
    """mode='all' 全形式; 'closed' 只封闭公式"""
    forms = None if mode=='all' else ['closed_form']
    try:
        r=FL.search(seq, forms=forms)
        return r[2][0] if (r and len(r)>2 and r[2]) else None
    except Exception:
        return None

say('')
say('--- 先测验证器本身 (不涉及模型) ---')
for mode,label in [('all','验证器-完整(8形式)'),('closed','验证器-锁定(仅closed_form)')]:
    row=[]
    for gname,G in [('G1',G1),('G2',G2),('G3',G3)]:
        ok=sum(1 for b in G if verify(b['seq'],mode)==b['next'])
        row.append(f'{gname} {ok}/{len(G)}')
    say(f'  {label:<26} ' + '   '.join(row))

# --- 模型 ---
say('')
tok=Qwen2TokenizerFast.from_pretrained('/root/autodl-tmp/life1/antiheb_05b')
PAD=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
def q_of(s): return "问：一个数列 "+", ".join(map(str,s))+" 的下一项是多少？答："
def mb(texts):
    ids=[tok(t).input_ids for t in texts]; L=max(len(x) for x in ids)
    return torch.tensor([x+[PAD]*(L-len(x)) for x in ids]), torch.tensor([[1]*len(x)+[0]*(L-len(x)) for x in ids])
def lab(X,A):
    L=X.clone(); L[A==0]=-100; return L
TR=list(TRAIN.values())
TX,TA=mb([q_of(b['seq'])+str(b['next']) for b in TR])
ALLX={b['name']:tok(q_of(b['seq']),return_tensors='pt').input_ids for b in BANK}

m=Qwen2ForCausalLM.from_pretrained('/root/autodl-tmp/life1/antiheb_05b',dtype=torch.float32); m.eval()
for p in m.parameters(): p.requires_grad_(False)
MODS=[]
for n,mod in m.named_modules():
    mt=re.search(r'layers\.(\d+)\.',n)
    if mt and int(mt.group(1)) in range(6,14) and hasattr(mod,'weight') and mod.weight.dim()==2 \
       and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
        MODS.append((n,mod))
def gen(b):
    ids=ALLX[b['name']]
    with torch.no_grad():
        o=m.generate(ids,max_new_tokens=14,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)
def model_ok(b):
    out=gen(b); nums=re.findall(r'-?\d+',out[:50])
    return int(nums[0])==b['next'] if nums else False

say('训练 (仅封闭公式7题, 120步)...')
for st in range(1,121):
    m.zero_grad()
    loss=m(input_ids=TX,attention_mask=TA,labels=lab(TX,TA)).loss
    loss.backward()
    with torch.no_grad():
        for name,mod in MODS:
            g=mod.weight.grad
            if g is None: continue
            gn=float(g.norm())
            if gn<1e-12: continue
            mod.weight.data.add_(-(g/gn)*(8e-6*float(mod.weight.norm())))
    if st%60==0: say(f'  [{st}步] loss={float(loss):.4f}')

say('')
say('--- 模型评估 ---')
Mrow=[]
for gname,G in [('G1',G1),('G2',G2),('G3',G3)]:
    ok=sum(1 for b in G if model_ok(b))
    Mrow.append(f'{gname} {ok}/{len(G)}')
    say(f'  模型 @ {gname}: {ok}/{len(G)}')
say('')
say('='*80)
say('★ 判决表')
say('='*80)
say(f"{'':<26}{'G1同形式':>12}{'G2跨形式':>12}{'G3全新':>12}")
for label,fn in [('模型(训练后)',None)]:
    say(f"  {label:<24}" + ''.join(f"{x.split()[1]:>12}" for x in Mrow))
for mode,label in [('all','验证器-完整'),('closed','验证器-锁定')]:
    row=[]
    for G in [G1,G2,G3]:
        ok=sum(1 for b in G if verify(b['seq'],mode)==b['next'])
        row.append(f'{ok}/{len(G)}')
    say(f"  {label:<24}" + ''.join(f"{x:>12}" for x in row))
say('')
say(f'总耗时 {time.time()-t0:.0f}s')
say('DONE')
