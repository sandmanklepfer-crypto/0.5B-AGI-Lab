# -*- coding: utf-8 -*-
"""
桥流重铸 v2 — 权重化开 -> 架桥 -> 顺桥重流
修复: torch线程数=8 (112会灾难性变慢) + 桥基维度对齐
"""
import os, json, time, math, sys
import torch
from safetensors.torch import load_file, save_file

SRC = '/root/autodl-tmp/life1/antiheb_05b'
DST = '/root/autodl-tmp/life1/bridge_05b'
LOG = '/root/autodl-tmp/life1/bridge.log'
NT  = 8            # ★ 关键: 8 线程最优 (实测 0.15s vs 112线程的 15s)
R_RATIO = 0.28
ALPHA   = 0.35

torch.set_num_threads(NT)
t0 = time.time()
def say(s):
    with open(LOG, 'a') as f: f.write(s + '\n')
    print(s, flush=True)

open(LOG, 'w').close()
say('='*76)
say('桥流重铸 v2: 权重化开 -> 架桥 -> 顺桥重流 -> 还是那些权重')
say('='*76)

sd = load_file(os.path.join(SRC, 'model.safetensors'))
say(f'权重 {len(sd)} 个, 参数 {sum(v.numel() for v in sd.values())/1e6:.0f}M, 加载 {time.time()-t0:.1f}s')

def is_t(k, v):
    if v.dim() != 2: return False
    if 'embed_tokens' in k or 'lm_head' in k or 'norm' in k: return False
    return any(p in k for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'))

keys = [k for k, v in sd.items() if is_t(k, v)]
lyr_keys = {}
for k in keys:
    L = int(k.split('.layers.')[1].split('.')[0])
    lyr_keys.setdefault(L, []).append(k)
say(f'可重铸 {len(keys)} 个权重, {len(lyr_keys)} 层')
# 打印形状, 确认
say('  形状样例: ' + ', '.join(f"{k.split('.')[-1]}={tuple(sd[k].shape)}" for k in lyr_keys[0]))

H = sd[[k for k in lyr_keys[0] if 'q_proj' in k][0]].shape[1]   # hidden=896
say(f'  hidden={H}')

bridge = None
stats = []
for L in sorted(lyr_keys):
    ks = lyr_keys[L]
    # ---- 桥基: 只看作用于残差流的权重 (输入维 = hidden) ----
    bases = []
    for k in ks:
        W = sd[k]
        U, S, Vh = torch.linalg.svd(W.float(), full_matrices=False)
        if Vh.shape[1] == H:               # 输入侧在残差空间
            bases.append(Vh)
        elif U.shape[1] == H:              # 输出侧在残差空间 (down_proj)
            bases.append(U.T)
    B = torch.cat(bases, 0)                # (M, H)
    Q, _ = torch.linalg.qr(B.T)            # (H, H)
    Rb = max(4, int(H * R_RATIO))
    Q = Q[:, :Rb]
    if bridge is None:
        bridge = Q
    else:
        m = min(bridge.shape[1], Q.shape[1])
        A_, B_ = bridge[:, :m], Q[:, :m]
        Ua, _, Vb = torch.linalg.svd(A_.T @ B_, full_matrices=False)
        bridge = B_ @ (Vb @ Ua.T)

    # ---- 顺桥重流: 只重排谱, 不动方向 ----
    moved, relmax = 0.0, 0.0
    for k in ks:
        W = sd[k].float()
        U, S, Vh = torch.linalg.svd(W, full_matrices=False)
        n = S.numel(); R = max(4, int(n * R_RATIO))
        if R >= n: continue
        head = S[:R].sum(); tail = S[R:].sum()
        boost = ALPHA * tail / (head + 1e-8)
        S2 = S.clone()
        S2[:R] = S2[:R] * (1.0 + boost)
        S2 = S2 * (S.norm() / (S2.norm() + 1e-8))     # 能量守恒
        W2 = (U * S2) @ Vh
        rel = float((W2 - W).norm() / (W.norm() + 1e-8))
        if rel > 0.5: continue                        # 安全闸门
        sd[k] = W2.to(sd[k].dtype)
        moved += float(tail / (head + tail + 1e-8)); relmax = max(relmax, rel)
    stats.append({'L': L, 'moved': moved/len(ks), 'rel': relmax, 'bridge_dim': int(bridge.shape[1])})
    say(f"  层{L:>2}: {len(ks)}权重  搬运尾部能量 {moved/len(ks):.3f}  最大偏离 {relmax:.3f}  桥维 {bridge.shape[1]}")

say(f'桥流完成 {time.time()-t0:.1f}s')

os.makedirs(DST, exist_ok=True)
save_file({k: v.contiguous() for k, v in sd.items()}, os.path.join(DST, 'model.safetensors'))
for f in ['config.json','generation_config.json','tokenizer.json','tokenizer_config.json',
          'vocab.json','merges.txt','special_tokens_map.json','added_tokens.json']:
    p = os.path.join(SRC, f)
    if os.path.exists(p): open(os.path.join(DST, f), 'wb').write(open(p, 'rb').read())
say(f'新权重 -> {DST}  ({time.time()-t0:.1f}s)')

# ---------------- 评估 ----------------
say('')
say('='*76); say('评估: 桥流后 语义/对话 有没有崩'); say('='*76)
from transformers import AutoModelForCausalLM, AutoTokenizer
tok = AutoTokenizer.from_pretrained(SRC, trust_remote_code=True)
TXT = ['人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。',
       '春天来了，树木开始发芽，小鸟在枝头歌唱。',
       '数学是研究数量关系和空间形式的科学。']
PROMPTS = ['你好，请介绍一下你自己。','中国首都是','1+1=','水的化学式是','今天天气很好，我想去']
res = {'stats': stats, 'gen': {}}
for tag, path in [('原始', SRC), ('桥流后', DST)]:
    say(f'--- 加载 {tag} ---')
    m = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32, trust_remote_code=True)
    m.eval()
    tl, tn = 0.0, 0
    for t in TXT:
        ids = tok(t, return_tensors='pt').input_ids
        with torch.no_grad(): o = m(ids, labels=ids)
        tl += float(o.loss)*(ids.shape[1]-1); tn += ids.shape[1]-1
    ppl = math.exp(tl/tn)
    say(f'  {tag} 困惑度 = {ppl:.3f}')
    res[tag+'_ppl'] = ppl
    for q in PROMPTS:
        ids = tok(q, return_tensors='pt').input_ids
        with torch.no_grad():
            o = m.generate(ids, max_new_tokens=24, do_sample=False, pad_token_id=tok.eos_token_id)
        s = tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)
        say(f'  Q {q}  ->  {s}')
        res['gen'].setdefault(q, {})[tag] = s
    del m
say('='*76); say(f'全部完成 {time.time()-t0:.1f}s')
json.dump(res, open('/root/autodl-tmp/life1/bridge_report.json','w'), ensure_ascii=False, indent=1)
say('报告 -> bridge_report.json')
