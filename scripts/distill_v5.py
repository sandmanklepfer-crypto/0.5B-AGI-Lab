#!/usr/bin/env python3
"""distill_v5.py — 前沿难题 × 主动蒸馏 (断层检测 + 动态补偿入口)
损失: CE(id直连) + L_align(层58→256 |cos|) + L_denoise(输入加噪激活不变) + L_sym/iso(变体不变)
断层检测: 每 step 记录每样本 loss -> 周期输出断层样本(学不动的) 供合成数据补偿
用法: distill_v5.py [--out DIR] [--epochs N] [--w_* W] [--detect-every S]
"""
import struct, glob, os, sys, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/distill_v4c'   # 从 v4c 起步
R1_DATA = '/root/v5_r1_hard'    # 前沿难题 dump

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/distill_v5')
ap.add_argument('--epochs', type=int, default=4)
ap.add_argument('--lr', type=float, default=4e-5)
ap.add_argument('--w_align', type=float, default=0.4)
ap.add_argument('--w_denoise', type=float, default=0.6)
ap.add_argument('--w_sym', type=float, default=0.5)
ap.add_argument('--denoise_sigma', type=float, default=0.15)
ap.add_argument('--max_seq', type=int, default=1024)
ap.add_argument('--batch', type=int, default=2)
ap.add_argument('--s_layer', type=int, default=22)
ap.add_argument('--proj_dim', type=int, default=256)
ap.add_argument('--detect-every', type=int, default=8)
ap.add_argument('--fault-thresh', type=float, default=1.5, help='断层阈值: 样本CE loss超过则标记')
args = ap.parse_args()

S_LAYER, PROJ_DIM = args.s_layer, args.proj_dim
S_NEMBD = 896
T_NEMBD = 5120
T_LAYER = 58
SEED = 42
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)

SYN_PAIRS = [('计算','求'),('写出','给出'),('具体','详细'),('步骤','过程'),
             ('推导','证明'),('过程','步骤'),('结果','答案'),('使用','利用'),
             ('计算过程','计算'),('完整','完整地')]

def load_dump(path, t_nembd, n_vocab=151643):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    assert magic == 0x54444344
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    top_ids = np.frombuffer(data, dtype=np.uint32, count=ng*k, offset=off); off += ng*k*4
    top_logits = np.frombuffer(data, dtype=np.float32, count=ng*k, offset=off); off += ng*k*4
    pieces = []
    if off < len(data):
        try:
            for j in range(ng):
                (pl,) = struct.unpack_from('<I', data, off); off += 4
                pieces.append(data[off:off+pl].decode('utf-8', 'replace')); off += pl
        except Exception:
            pieces = []
    # 越界 id 过滤 (R1 152064 > student 151643)
    prompt = prompt[prompt < n_vocab]
    gen = gen[gen < n_vocab]
    acts = None
    if (len(data) - off)//4 >= ng * t_nembd:
        acts = np.frombuffer(data, dtype=np.float32, count=ng*t_nembd, offset=off).reshape(ng, t_nembd)
        acts = acts[:len(gen)]
    return dict(prompt=prompt, gen=gen, pieces=pieces, acts=acts, ce=0.0)

def syn_variant(text):
    t = text
    for a, b in random.sample(SYN_PAIRS, k=2):
        if a in t: t = t.replace(a, b)
    return t

def iso_variant(text):
    """数字替换变体 (结构同构)"""
    nums = re.findall(r'\d+', text)
    if nums:
        n0 = nums[0]
        n1 = str(int(n0) + 7) if int(n0) < 90 else str(int(n0) - 7)
        return text.replace(n0, n1, 1)
    return text

def add_noise_ids(ids, sigma, n_vocab):
    noise = torch.rand(ids.shape, device=ids.device)
    mask = noise < sigma
    rand_ids = torch.randint(0, n_vocab, ids.shape, device=ids.device)
    return torch.where(mask, rand_ids, ids)

def main():
    print('[load] student=v4c, data=frontier hard dumps', flush=True)
    tok = AutoTokenizer.from_pretrained(STUDENT)
    tok.pad_token = tok.eos_token
    dev = 'cuda:0'
    stu = AutoModelForCausalLM.from_pretrained(STUDENT, dtype=torch.bfloat16).to(dev)
    n_vocab = stu.config.vocab_size

    dumps = []
    for f in sorted(glob.glob(f'{R1_DATA}/p*.bin')):
        try:
            dumps.append(load_dump(f, T_NEMBD))
        except Exception:
            pass
    print(f'[data] {len(dumps)} dumps', flush=True)
    random.shuffle(dumps)

    # 投影矩阵
    print('[proj] SVD...', flush=True)
    t_acts = np.concatenate([d['acts'] for d in dumps[:30] if d['acts'] is not None], axis=0)
    t_acts = t_acts[:2000]
    if t_acts.shape[0] > 600:
        t_acts = t_acts[np.random.choice(t_acts.shape[0], 600, replace=False)]
    U, S, Vt = torch.linalg.svd(torch.tensor(t_acts.astype(np.float32)).to(dev), full_matrices=False)
    P_t = Vt[:PROJ_DIM].T.to(dev).float()
    s_acts_all = []
    with torch.inference_mode():
        for d in dumps[:30]:
            full = torch.tensor(np.concatenate([d['prompt'], d['gen']])[:args.max_seq],
                                dtype=torch.long).unsqueeze(0).to(dev)
            h = stu(full, output_hidden_states=True)
            s_acts_all.append(h.hidden_states[S_LAYER][0].mean(0).float().cpu().numpy())
    A = np.stack(s_acts_all)
    U2, S2, Vt2 = torch.linalg.svd(torch.tensor(A, device=dev).float(), full_matrices=False)
    P_s = Vt2[:PROJ_DIM].T.to(dev).float()
    print(f'[proj] P_t={P_t.shape} P_s={P_s.shape}', flush=True)

    opt = torch.optim.AdamW(stu.parameters(), lr=args.lr)
    os.makedirs(args.out, exist_ok=True)
    total = len(dumps)
    step = 0
    fault_log = []
    for ep in range(1, args.epochs + 1):
        random.shuffle(dumps)
        ep_loss = 0.0
        for i in range(0, total, args.batch):
            batch = dumps[i:i + args.batch]
            maxlen = min(args.max_seq, max(len(d['prompt']) + len(d['gen']) for d in batch))
            xs_pad = np.zeros((len(batch), maxlen), dtype=np.int64)
            lab_pad = np.full((len(batch), maxlen), -100, dtype=np.int64)
            for bi, d in enumerate(batch):
                seq = np.concatenate([d['prompt'], d['gen']])[:maxlen]
                xs_pad[bi, :len(seq)] = seq
                lab_pad[bi, len(d['prompt']):min(len(d['prompt']) + len(d['gen']), maxlen)] = \
                    seq[len(d['prompt']):maxlen]
            xs_t = torch.tensor(xs_pad, dtype=torch.long).to(dev)
            lab_t = torch.tensor(lab_pad, dtype=torch.long).to(dev)

            # CE (per-sample loss for fault detection) fp32
            with torch.inference_mode():
                logits_f = stu(xs_t).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]),
                                     xs_t.view(-1), reduction='none')
            mask_all = (lab_t.view(-1) != -100)
            loss_ce = ce_all[mask_all].mean() if mask_all.any() else torch.tensor(0.0, device=dev)
            # 每样本断层分数
            for bi, d in enumerate(batch):
                m = (lab_t[bi] != -100)
                if m.sum() > 0:
                    ce_b = F.cross_entropy(logits_f[bi][m], xs_t[bi][m], reduction='mean').item()
                    d['ce'] = 0.9 * d['ce'] + 0.1 * ce_b

            # L_align
            with torch.inference_mode():
                h = stu(xs_t, output_hidden_states=True)
            s_acts = h.hidden_states[S_LAYER]
            loss_align = torch.tensor(0.0, device=dev); n = 0
            for bi, d in enumerate(batch):
                if d['acts'] is None: continue
                t_a = torch.tensor(d['acts'], dtype=torch.float32, device=dev)
                m = min(t_a.shape[0], s_acts.shape[1] - 1)
                if m <= 0: continue
                pt = t_a[:m] @ P_t
                ps = s_acts[bi, -m:].float() @ P_s
                d2 = min(ps.shape[1], pt.shape[1])
                ps, pt = ps[:, :d2], pt[:, :d2]
                cs = F.cosine_similarity(ps, pt, dim=-1)
                loss_align = loss_align + (1 - cs.abs()).mean(); n += 1
            loss_align = loss_align / max(n, 1)

            # L_denoise
            with torch.inference_mode():
                a0 = stu(xs_t, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            xs_noisy = add_noise_ids(xs_t, args.denoise_sigma, n_vocab)
            a1 = stu(xs_noisy, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            loss_den = (1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean())

            # L_sym/iso
            loss_sym = torch.tensor(0.0, device=dev); n = 0
            for d in batch:
                base_txt = ''.join(d['pieces'])[:300] if d['pieces'] else ''
                if not base_txt: continue
                v = syn_variant(base_txt) if random.random() < 0.5 else iso_variant(base_txt)
                if v == base_txt: continue
                with torch.inference_mode():
                    h0 = stu(tok(base_txt, return_tensors='pt').to(dev)['input_ids'], output_hidden_states=True)
                    h1 = stu(tok(v, return_tensors='pt').to(dev)['input_ids'], output_hidden_states=True)
                a0 = h0.hidden_states[S_LAYER][0].mean(0).float()
                a1 = h1.hidden_states[S_LAYER][0].mean(0).float()
                cs = F.cosine_similarity(a0.unsqueeze(0), a1.unsqueeze(0)).abs()
                loss_sym = loss_sym + (1 - cs); n += 1
            loss_sym = loss_sym / max(n, 1)

            loss = loss_ce + args.w_align * loss_align + args.w_denoise * loss_den + args.w_sym * loss_sym
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item(); step += 1

            # 断层检测
            if step % args.detect_every == 0:
                faults = [d for d in dumps if d['ce'] > args.fault_thresh]
                fault_log.append((step, len(faults)))
                top_idx = sorted(range(len(dumps)), key=lambda i: -dumps[i]['ce'])[:3]
                top_info = [(i, round(dumps[i]['ce'], 2),
                             ''.join(dumps[i]['pieces'])[:40] or '') for i in top_idx]
                print(f'[ep{ep} s{step}] loss={loss.item():.3f} ce={loss_ce.item():.3f} '
                      f'align={loss_align.item():.3f} den={loss_den.item():.3f} sym={loss_sym.item():.3f} '
                      f'faults={len(faults)}/{len(dumps)} top={top_info}', flush=True)
        print(f'[ep{ep}] avg={ep_loss / max(1, total // args.batch):.3f}', flush=True)
        stu.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f'[save] {args.out}', flush=True)

    # 断层报告 (供合成数据补偿)
    with open(f'{args.out}/fault_report.json', 'w') as f:
        json.dump({"fault_track": fault_log,
                   "worst": [{"idx": i, "ce": d['ce'], "prompt": ''.join(d['pieces'])[:200]}
                             for i, d in sorted(enumerate(dumps), key=lambda x: -x[1]['ce'])[:10]]}, f, ensure_ascii=False)
    print('[done] fault report saved', flush=True)

if __name__ == '__main__':
    main()
