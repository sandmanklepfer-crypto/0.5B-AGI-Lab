#!/usr/bin/env python3
"""distill_v5_fix.py — 断层补偿补训: 从 distill_v5 继续, 用分解数据
损失同 distill_v5 (CE + align + den + sym), 低 lr, 2 ep
用法: distill_v5_fix.py [--out DIR] [--epochs N] [--lr X]
"""
import struct, glob, os, sys, random, argparse, json
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

START = '/root/distill_v5'        # 上一阶段产物
DECOMP = '/root/v5_r1_decomp'     # 分解数据

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/distill_v5b')
ap.add_argument('--epochs', type=int, default=2)
ap.add_argument('--lr', type=float, default=2e-5)
ap.add_argument('--w_align', type=float, default=0.5)
ap.add_argument('--w_denoise', type=float, default=0.6)
ap.add_argument('--w_sym', type=float, default=0.5)
ap.add_argument('--max_seq', type=int, default=1024)
ap.add_argument('--batch', type=int, default=2)
ap.add_argument('--s_layer', type=int, default=22)
ap.add_argument('--proj_dim', type=int, default=256)
args = ap.parse_args()

S_LAYER, PROJ_DIM = args.s_layer, args.proj_dim
T_NEMBD, S_NEMBD = 5120, 896
SEED = 42
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)

def load_dump(path, t_nembd, n_vocab=151643):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    off += ng*k*8
    prompt = prompt[prompt < n_vocab]
    gen = gen[gen < n_vocab]
    acts = None
    if (len(data) - off)//4 >= ng * t_nembd:
        acts = np.frombuffer(data, dtype=np.float32, count=ng*t_nembd, offset=off).reshape(ng, t_nembd)
        acts = acts[:len(gen)]
    return dict(prompt=prompt, gen=gen, acts=acts)

def main():
    print(f'[load] start={START}, data={DECOMP}', flush=True)
    tok = AutoTokenizer.from_pretrained(START)
    tok.pad_token = tok.eos_token
    dev = 'cuda:0'
    stu = AutoModelForCausalLM.from_pretrained(START, dtype=torch.bfloat16).to(dev)
    n_vocab = stu.config.vocab_size

    dumps = []
    for f in sorted(glob.glob(f'{DECOMP}/p*.bin')):
        try: dumps.append(load_dump(f, T_NEMBD))
        except Exception: pass
    print(f'[data] {len(dumps)} decomp dumps', flush=True)
    random.shuffle(dumps)

    # 投影 (GPU SVD, 采样)
    t_all = np.concatenate([d['acts'] for d in dumps[:30] if d['acts'] is not None], axis=0)[:2000]
    if t_all.shape[0] > 600:
        t_all = t_all[np.random.choice(t_all.shape[0], 600, replace=False)]
    U, S, Vt = torch.linalg.svd(torch.tensor(t_all.astype(np.float32)).to(dev), full_matrices=False)
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

            with torch.inference_mode():
                logits_f = stu(xs_t).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), xs_t.view(-1), reduction='none')
            mask_all = (lab_t.view(-1) != -100)
            loss_ce = ce_all[mask_all].mean() if mask_all.any() else torch.tensor(0.0, device=dev)

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

            with torch.inference_mode():
                a0 = stu(xs_t, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            xs_n = torch.where(torch.rand(xs_t.shape, device=dev) < 0.15,
                               torch.randint(0, n_vocab, xs_t.shape, device=dev), xs_t)
            a1 = stu(xs_n, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            loss_den = 1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean()

            loss = loss_ce + args.w_align * loss_align + args.w_denoise * loss_den
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item(); step += 1
            if step % 10 == 0:
                print(f'[ep{ep} s{step}] loss={loss.item():.3f} ce={loss_ce.item():.3f} '
                      f'align={loss_align.item():.3f} den={loss_den.item():.3f}', flush=True)
        print(f'[ep{ep}] avg={ep_loss / max(1, total // args.batch):.3f}', flush=True)
        stu.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f'[save] {args.out}', flush=True)

if __name__ == '__main__':
    main()
