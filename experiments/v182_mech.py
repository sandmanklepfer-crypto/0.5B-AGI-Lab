# -*- coding: utf-8 -*-
"""
V182 种子/影子/自持环/相位通道... 正确实现版
=================================================================
V180 教训: 机制"用崩了"和"真没用"必须分清
   → 每臂都记录 train_loss 曲线 (用崩了 = loss 不降)

全部以【幅度控制】为底座 (V180唯一验证有效的), 逐个叠加真机制:

  B   幅度控制(基准)        V80/V81
  S1  种子 (慢参照系)        b03/b04: S=EMA(W,λ), 弱引力 + 漂移门控
  S2  影子 (低秩更新)        shadow_ray: 更新限制在权重前 k 个主方向
  S3  自持环 (能量飞轮)      V142: 学习率由"进步"驱动的能量信号调制
  S4  相位通道 (正交历史)    V163/V165: 更新垂直于最近 N 个更新
  S5  配额记忆 (方向字典)    V166: 固定容量方向表, 重复利用
  S6  全局回看 (rehearsal)   V11: 每 K 步回放通用样本防遗忘
  S7  火种 (点火逃逸)        V12a: 卡住时沿高梯度方向点火
  S8  组合(最优几个一起)

指标: 12题严格判答 + train_loss + 通用/遗忘loss
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

LOG='/root/autodl-tmp/life1/mech.log'
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
STEPS=100; SCALE=8e-6; LAYERS=list(range(6,14))

say('='*80)
say('V182 种子/影子/自持环/相位通道 —— 正确实现版 (带 train_loss 诊断)')
say('='*80)
tok=Qwen2TokenizerFast.from_pretrained('/root/autodl-tmp/life1/antiheb_05b')
PAD=tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
def q_of(s): return "问：一个数列 "+", ".join(map(str,s))+" 的下一项是多少？答："
def mb(texts):
    ids=[tok(t).input_ids for t in texts]; L=max(len(x) for x in ids)
    return torch.tensor([x+[PAD]*(L-len(x)) for x in ids]), torch.tensor([[1]*len(x)+[0]*(L-len(x)) for x in ids])
def lab(X,A):
    L=X.clone(); L[A==0]=-100; return L
TX,TA=mb([q_of(s)+str(a) for s,a in TRAIN])
KX,KA=mb(KEEP); HX,HA=mb(HOLD)
ALLX=[tok(q_of(s),return_tensors='pt').input_ids for s,_ in BANK]

say('加载模型...')
m=Qwen2ForCausalLM.from_pretrained('/root/autodl-tmp/life1/antiheb_05b',dtype=torch.float32); m.eval()
INIT={k:v.clone() for k,v in m.state_dict().items()}
MODS=[]
for n,mod in m.named_modules():
    mt=re.search(r'layers\.(\d+)\.',n)
    if mt and int(mt.group(1)) in LAYERS and hasattr(mod,'weight') and mod.weight.dim()==2 \
       and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
        MODS.append((n,mod,int(mt.group(1))))
say(f'可训练权重 {len(MODS)} 个')
say('预计算影子参照系(低秩k=4)...')
SHADOW={}
for name,mod,L in MODS:
    U,Sv,Vh=torch.linalg.svd(mod.weight.data.float(),full_matrices=False)
    SHADOW[name]=(U[:,:4].contiguous(), Vh[:4,:].contiguous())
say(f'  完成 {len(SHADOW)} 组')

def loss_of(X,A):
    with torch.no_grad(): return float(m(input_ids=X,attention_mask=A,labels=lab(X,A)).loss)
def gen(ids,nw=14):
    with torch.no_grad():
        o=m.generate(ids,max_new_tokens=nw,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)
def score():
    ok=0
    for i,(s,ans) in enumerate(BANK):
        out=gen(ALLX[i]); nums=re.findall(r'-?\d+',out[:50])
        ok += (str(ans) in nums)
    return ok

# ---------- 机制需要的常驻状态 ----------
def reset():
    m.load_state_dict(INIT)
    for p in m.parameters(): p.requires_grad_(False)
    for _,mod,_ in MODS: mod.weight.requires_grad_(True)
    st={'seed':{n:mod.weight.data.clone() for n,mod,_ in MODS},   # 种子: 慢参照系
        'dirs':{},                                                 # 相位通道/配额: 历史方向
        'energy':1.0,                                              # 自持环能量
        'prev_loss':None, 'stuck':0, 'lr_mult':1.0}
    return st

def train(arm, steps=STEPS):
    reset(); st_=None
    st=reset()
    hist=[]
    for it in range(1,steps+1):
        m.zero_grad()
        loss=m(input_ids=TX,attention_mask=TA,labels=lab(TX,TA)).loss
        lv=float(loss)
        if arm in ('S6',) and it%10==0:                 # 全局回看: 回放通用样本
            loss2=m(input_ids=KX,attention_mask=KA,labels=lab(KX,KA)).loss
            (loss+0.3*loss2).backward()
        else:
            loss.backward()
        # ---------- 自持环: 能量飞轮 ----------
        if arm in ('S3','S8','S9'):
            if st['prev_loss'] is not None:
                imp=st['prev_loss']-lv
                st['energy']=min(2.0,max(0.3,st['energy']+ (0.05 if imp>0.002 else -0.03)))
            st['lr_mult']=st['energy']
            st['prev_loss']=lv
        # ---------- 火种: 卡住检测 ----------
        if arm in ('S7','S8'):
            if st['prev_loss'] is not None and abs(st['prev_loss']-lv)<1e-4:
                st['stuck']+=1
            else: st['stuck']=0
            st['prev_loss']=lv
        with torch.no_grad():
            for name,mod,L in MODS:
                gr=mod.weight.grad
                if gr is None: continue
                gn=float(gr.norm())
                if gn<1e-12: continue
                patch=gr/gn                                    # 幅度控制(底座)
                # ---------- 影子: 低秩约束 (只在前k个主方向更新) ----------
                if arm in ('S2','S8'):
                    Uc,Vc=SHADOW[name]                         # 影子参照系(预先算好, 固定)
                    patch=(Uc@(Uc.T@patch))+ (patch@Vc.T)@Vc   # 投影到低秩子空间
                    pn=float(patch.norm())
                    if pn<1e-12: continue
                    patch=patch/pn
                # ---------- 相位通道: 垂直于最近N个更新 ----------
                if arm in ('S4','S8','S9'):
                    for ud in st['dirs'].get(name,[])[-6:]:
                        patch=patch-(patch*ud).sum()*ud
                    pn=float(patch.norm())
                    if pn<1e-12: continue
                    patch=patch/pn
                    dl=st['dirs'].setdefault(name,[]); dl.append(patch.clone())
                    if len(dl)>6: del dl[:-6]          # ★ 只保留最近6个 (防内存爆炸)
                # ---------- 配额记忆: 方向字典, 复用它 ----------
                if arm=='S5':
                    d=st['dirs'].setdefault(name,[])
                    if len(d)<4:
                        d.append(patch.clone())
                    else:
                        # 在记忆里找最接近的, 用它(复用)
                        sims=torch.stack([ (patch*u).sum() for u in d])
                        patch=d[int(sims.argmax())]
                # ---------- 火种: 卡住时点火(混入高梯度方向) ----------
                if arm in ('S7','S8') and st['stuck']>=5:
                    noise=torch.randn_like(patch); noise=noise/(noise.norm()+1e-8)
                    patch=0.7*patch+0.3*noise
                    st['stuck']=0
                sz=SCALE*float(mod.weight.norm())*st.get('lr_mult',1.0)
                mod.weight.data.add_(-patch*sz)
            # ---------- 种子: 慢参照系 + 漂移门控 ----------
            if arm in ('S1','S8','S9'):
                LAM=0.05; ALPHA=0.15
                for name,mod,L in MODS:
                    sd=st['seed'][name]
                    sd.mul_(1-LAM).add_(mod.weight.data,alpha=LAM)   # 种子缓慢吸收历史
                    drift=float((mod.weight.data-sd).norm())/(float(sd.norm())+1e-8)
                    if drift>0.02:                                    # 漂移过大 → 拉回一点
                        mod.weight.data.add_(sd-mod.weight.data, alpha=ALPHA)
        if it%50==0: hist.append((it,lv))
    return hist

say('')
say(f"基线: {score()}/12   通用{loss_of(KX,KA):.4f}  遗忘{loss_of(HX,HA):.4f}")
say('')
say(f"{'臂':<28}{'机制':<22}{'12题':>7}{'末loss':>9}{'通用':>9}{'遗忘':>9}{'秒':>6}")
ARMS=[('S4','相位通道(正交历史)'),('S5','配额记忆(方向字典)'),
      ('S6','全局回看(rehearsal)'),('S7','火种(点火逃逸)'),
      ('S9','组合(强种子+S4)')]
res={}
for a,nm in ARMS:
    ts=time.time(); hist=train(a)
    ok=score(); lk,lh=loss_of(KX,KA),loss_of(HX,HA)
    last=hist[-1][1] if hist else float('nan')
    say(f"{a:<4}{nm:<24}{ok:>5}/12{last:>9.4f}{lk:>9.4f}{lh:>9.4f}{time.time()-ts:>6.0f}")
    res[a]={'name':nm,'ok':ok,'last_loss':last,'lk':lk,'lh':lh,'hist':hist}
    for it,lv in hist: say(f'        [{it}步] loss={lv:.4f}')
say('')
say('='*80)
base=[k for k,v in res.items() if v['ok']>=8]
say(f"达标(>=8/12): {[res[k]['name'] for k in base]}")
say(f"总耗时 {time.time()-t0:.0f}s")
json.dump(res,open('/root/autodl-tmp/life1/mech.json','w'),ensure_ascii=False,indent=1)
say('DONE')
