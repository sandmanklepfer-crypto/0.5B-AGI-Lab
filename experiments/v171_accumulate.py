# -*- coding: utf-8 -*-
"""
V171 累积桥流 —— 单步 1% × 流水线反复走
=================================================================
用户机制: 小步(1%) -> 验证语义没崩 -> 固化 -> 再走一小步 -> 循环

★ 关键优化: 因为只动 S 不动 U/Vᵀ, 反复重流【不需要重新 SVD】
   一次 SVD -> 对 S 反复谱整形 -> 秒级迭代

问题:
  ① 累积 N 步, 总偏移怎么涨? (线性? 收敛?)
  ② 第几步崩? (安全线在哪)
  ③ 收敛后模型还剩什么能力?
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

SRC = '/root/autodl-tmp/life1/antiheb_05b'
LOG = '/root/autodl-tmp/life1/acc.log'
OUT = '/root/autodl-tmp/life1/acc_result.json'
ALPHA = 0.01          # ★ 已验证安全的单步预算
R_RATIO = 0.28
ROUNDS = 40

open(LOG,'w').close()
t0 = time.time()
def say(s):
    with open(LOG,'a') as f: f.write(s+'\n')
    print(s, flush=True)

say('='*76)
say('V171 累积桥流: 单步 1% × 流水线反复走')
say('='*76)

tok = Qwen2TokenizerFast.from_pretrained(SRC)
TXT = ["人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。",
       "春天来了，树木开始发芽，小鸟在枝头歌唱。",
       "数学是研究数量关系和空间形式的科学。",
       "深度学习模型通过反向传播算法不断调整参数，从而逐渐逼近目标函数。",
       "长江是中国最长的河流，它从青藏高原流向东海，全长六千多公里。"]
Q = "你好，请介绍一下你自己。"

say('加载模型...')
m = Qwen2ForCausalLM.from_pretrained(SRC, dtype=torch.float32); m.eval()

mods = []
for n, mod in m.named_modules():
    if hasattr(mod,'weight') and mod.weight is not None and mod.weight.dim()==2 \
       and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
        mods.append((n, mod))
say(f'目标权重 {len(mods)} 个  ({time.time()-t0:.1f}s)')

def ppl(model):
    tl, tn = 0.0, 0
    for t in TXT:
        ids = tok(t, return_tensors='pt').input_ids
        with torch.no_grad(): o = model(ids, labels=ids)
        tl += float(o.loss)*(ids.shape[1]-1); tn += ids.shape[1]-1
    return math.exp(tl/tn)

def gen(model, q=Q, n=26):
    ids = tok(q, return_tensors='pt').input_ids
    with torch.no_grad():
        o = model.generate(ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)

# ---------- ★ 一次 SVD, 永久缓存 ----------
say('一次 SVD 分解 (缓存 U/S/Vᵀ, 之后反复重流不再分解)...')
cache = []
for n, mod in mods:
    W = mod.weight.data.float()
    U, S, Vh = torch.linalg.svd(W, full_matrices=False)
    k = S.numel(); R = max(4, int(k*R_RATIO))
    cache.append({'n':n,'mod':mod,'U':U,'S':S,'Vh':Vh,
                  'W0':W.clone(),'R':R,'n0':float(W.norm())})
say(f'缓存完成 {len(cache)} 组  ({time.time()-t0:.1f}s)')

base_ppl = ppl(m)
say(f'基线困惑度 = {base_ppl:.4f}')
say(f'基线输出: {gen(m)[:60]}')
say('')
say(f"{'轮':>4}{'总偏移':>10}{'谱集中度':>11}{'困惑度':>12}{'倍数':>8}  判定")

def spectrum_step(S, R, alpha):
    """谱整形: 尾部能量搬进前 R 个桥通道 + 能量守恒"""
    head = S[:R].sum(); tail = S[R:].sum()
    S2 = S.clone()
    S2[:R] = S2[:R] * (1.0 + alpha * tail/(head+1e-8))
    return S2 * (S.norm()/(S2.norm()+1e-8))

def apply_all(step_fn):
    for c in cache:
        S2 = step_fn(c['S'], c['R'], ALPHA)
        c['S'] = S2                                    # ★ 固化: S 就地更新
        c['mod'].weight.data.copy_((c['U']*S2) @ c['Vh'])

def total_dev():
    """总偏移 (相对初始权重) + 谱集中度"""
    num = 0.0; den = 0.0; conc = 0.0
    for c in cache:
        W = (c['U']*c['S']) @ c['Vh']
        num += float((W-c['W0']).norm())**2
        den += c['n0']**2
        conc += float(c['S'][:c['R']].sum() / (c['S'].sum()+1e-8))
    return (num**0.5)/ (den**0.5), conc/len(cache)

res = {'base_ppl':base_ppl,'alpha':ALPHA,'rounds':[]}
history = []
for rd in range(1, ROUNDS+1):
    apply_all(spectrum_step)                            # 走一小步 + 固化
    rel, conc = total_dev()
    p = ppl(m)
    ratio = p/base_ppl
    ok = ratio < 1.25
    tag = '✅保' if ok else ('⚠️劣' if ratio<2 else '❌崩')
    say(f"{rd:>4}{rel*100:>9.2f}%{conc*100:>10.1f}%{p:>12.4f}{ratio:>7.2f}x  {tag}")
    res['rounds'].append({'r':rd,'dev':rel,'conc':conc,'ppl':p,'ratio':ratio})
    history.append((rd,rel,p,ratio))
    if ratio > 3.0:
        say('  -> 已崩塌, 停止'); break
    if rd in (1,5,10,20,30,40) and ok:
        say(f'     样例: {gen(m)[:64]}')

say('')
say(f'最终困惑度 = {ppl(m):.4f}  (基线 {base_ppl:.4f})')
say(f'最终输出: {gen(m)[:80]}')
say(f'总耗时 {time.time()-t0:.1f}s')
json.dump(res, open(OUT,'w'), ensure_ascii=False, indent=1)
say('DONE')
