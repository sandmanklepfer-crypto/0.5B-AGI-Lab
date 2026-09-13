#!/usr/bin/env python3
"""streaming_v5.py — 流式课程: 边生成边训练, 对比窗口策略
每轮: 等待新 bin -> 用最近 window 条训练 -> 快速评估 5 题 -> 记录
用法: streaming_v5.py --window N [--max-rounds R]
"""
import struct, glob, os, sys, random, argparse, time, json
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/distill_v4c'
DATA_DIR = '/root/v5_r1_hard'
OUT = '/root/distill_v5_stream'

ap = argparse.ArgumentParser()
ap.add_argument('--window', type=int, default=7, help='每轮训练窗口条数 (7/6/1)')
ap.add_argument('--max-rounds', type=int, default=8)
ap.add_argument('--epochs', type=int, default=2)
ap.add_argument('--lr', type=float, default=2e-5)
ap.add_argument('--w_align', type=float, default=0.4)
ap.add_argument('--w_denoise', type=float, default=0.5)
ap.add_argument('--s_layer', type=int, default=22)
ap.add_argument('--proj_dim', type=int, default=256)
args = ap.parse_args()

S_LAYER, PROJ_DIM = args.s_layer, args.proj_dim
T_NEMBD, S_NEMBD = 5120, 896

# 快速评估 5 题 (数学/逻辑/代码/知识/前沿)
EVAL_QS = [
    ("math", "计算：7乘以8等于多少？"),
    ("math_hard", "计算 3^100 除以 100 的余数。"),
    ("logic", "所有的A都是B，所有的B都是C，那么所有的A是什么？"),
    ("code", "执行 x=1; x=x+2; x*=3; 后 x 是多少？"),
    ("know", "光合作用光反应的产物是什么？"),
]

def load_dump(path, n_vocab=151643):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
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
    # 越界 id 过滤 (R1 vocab 152064 > student 151643)
    prompt = prompt[prompt < n_vocab]
    gen = gen[gen < n_vocab]
    acts = None
    if (len(data) - off)//4 >= ng * T_NEMBD:
        acts = np.frombuffer(data, dtype=np.float32, count=ng*T_NEMBD, offset=off).reshape(ng, T_NEMBD)
        acts = acts[:len(gen)]
    return dict(prompt=prompt, gen=gen, pieces=pieces, acts=acts)

def gen(model, tok, text, max_new=60):
    ids = tok(text, return_tensors='pt').to('cuda:0')
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()

def quick_eval(model, tok):
    """5 题快速评估 -> 每题对/错 (含数字/关键词判据)"""
    scores = {}
    ans = {}
    for tag, q in EVAL_QS:
        a = gen(model, tok, q)
        ans[tag] = a[:60]
        ok = False
        if tag == 'math': ok = ('56' in a)
        elif tag == 'math_hard': ok = ('7' in a and '1' in a and len(a) < 80)
        elif tag == 'logic': ok = ('C' in a or 'c' in a)
        elif tag == 'code': ok = ('9' in a)
        elif tag == 'know': ok = ('ATP' in a or '氧气' in a or 'O2' in a)
        scores[tag] = ok
    return scores, ans

def main():
    print(f'[stream] window={args.window} rounds<={args.max_rounds} start=v4c', flush=True)
    tok = AutoTokenizer.from_pretrained(STUDENT)
    tok.pad_token = tok.eos_token
    dev = 'cuda:0'
    stu = AutoModelForCausalLM.from_pretrained(STUDENT, dtype=torch.bfloat16).to(dev)
    n_vocab = stu.config.vocab_size

    log = []
    seen = 0
    # 初始轮: 用已存在的 bin (至少 window 条)
    bins = sorted(glob.glob(f'{DATA_DIR}/p*.bin'))
    base_scores, _ = quick_eval(stu, tok)
    log.append({"round": 0, "n_bins": len(bins), "scores": base_scores})
    print(f'[r0] base v4c: n={len(bins)} {base_scores}', flush=True)

    for rnd in range(1, args.max_rounds + 1):
        # 等待新增 window 条
        waited = 0
        while True:
            bins = sorted(glob.glob(f'{DATA_DIR}/p*.bin'))
            if len(bins) >= seen + args.window:
                break
            if waited > 2400:  # 40 分钟超时
                print('[timeout] no new bins', flush=True); return
            time.sleep(10); waited += 10
        new_bins = bins[:seen + args.window]
        seen = len(new_bins)
        # 最近 window 条 (滑动窗口)
        win_bins = new_bins[-args.window:]
        dumps = []
        for f in win_bins:
            try: dumps.append(load_dump(f))
            except Exception: pass
        print(f'[r{rnd}] window={len(dumps)} bins={seen}', flush=True)

        # 训练 1 轮
        opt = torch.optim.AdamW(stu.parameters(), lr=args.lr)
        for ep in range(args.epochs):
            random.shuffle(dumps)
            for d in dumps:
                seq = np.concatenate([d['prompt'], d['gen']])
                xs = torch.tensor(seq[:1024], dtype=torch.long).unsqueeze(0).to(dev)
                lab = torch.full_like(xs, -100)
                gen_start = min(len(d['prompt']), 1024)
                gen_end = min(len(seq), 1024)
                lab[0, gen_start:gen_end] = xs[0, gen_start:gen_end]
                if (lab != -100).sum() == 0:
                    continue  # 全 mask -> CE nan, 跳过
                # CE 用 fp32 (bf16 溢出防 nan)
                logits = stu(xs).logits.float()
                ce = F.cross_entropy(logits.view(-1, logits.shape[-1]),
                                     xs.view(-1), reduction='none')
                mask = (lab.view(-1) != -100)
                loss_ce = ce[mask].mean() if mask.any() else torch.tensor(0.0, device=dev)
                # denoise
                with torch.inference_mode():
                    a0 = stu(xs, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
                xs_n = torch.where(torch.rand(xs.shape, device=dev) < 0.15,
                                   torch.randint(0, n_vocab, xs.shape, device=dev), xs)
                a1 = stu(xs_n, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
                loss_den = 1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean()
                loss = loss_ce + args.w_denoise * loss_den
                opt.zero_grad(); loss.backward(); opt.step()
            print(f'  [ep{ep}] ce={loss_ce.item():.3f} den={loss_den.item():.3f}', flush=True)
        stu.save_pretrained(OUT); tok.save_pretrained(OUT)

        # 评估
        scores, ans = quick_eval(stu, tok)
        log.append({"round": rnd, "n_bins": seen, "scores": scores, "ans": ans})
        print(f'[r{rnd}] scores={scores}', flush=True)
        for tag, a in ans.items():
            print(f'    {tag}: {a!r}', flush=True)

    json.dump(log, open(f'{OUT}/stream_log.json', 'w'), ensure_ascii=False, indent=1)
    print('[done] stream log saved', flush=True)

if __name__ == '__main__':
    main()
