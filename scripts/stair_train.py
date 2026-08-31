#!/usr/bin/env python3
"""stair_train.py — 阶梯式断层补训 (渐进课程)
阶梯1: start+decomp[:20] 1ep -> eval -> stair1
阶梯2: stair1+decomp[20:42] 1ep -> eval -> stair2
阶梯3: stair2+decomp[:42] 1ep -> eval -> stair3
理解力测试: 断层题变体 (换数值/结构, 测泛化)
用法: stair_train.py [--out-prefix DIR]
"""
import struct, glob, os, sys, random, argparse, json
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

START = '/root/distill_v5'
DECOMP = '/root/v5_r1_decomp'

UNDERSTAND_QS = [
    ("错排数变体", "求错排数 D(6) 的值，用递推 D(n)=(n-1)(D(n-1)+D(n-2))。"),
    ("LRU变体", "页面访问序列 1,2,3,4,1,2,5 用 LRU（3帧），缺页多少次？"),
    ("快速幂变体", "用快速幂计算 2^50 mod 1000。"),
    ("TCP变体", "TCP 慢启动 ssthresh=8，cwnd 前4个RTT分别是多少？"),
    ("圆排列变体", "5 个人围圆桌有多少种不同坐法？"),
    ("RSA变体", "RSA: p=11, q=7, e=13，求 n 和 φ(n)。"),
    ("B+树变体", "B+树（阶数3）插入 3,1,2：何时分裂？"),
    ("谓词逻辑变体", "把'每个学生都喜欢某本书'翻译成一阶逻辑。"),
]

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

def gen(model, tok, text, max_new=90):
    ids = tok(text, return_tensors='pt').to('cuda:0')
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()

def understand_eval(model, tok):
    """理解力测试: 断层题变体, 关键词判据"""
    res = {}
    for tag, q in UNDERSTAND_QS:
        a = gen(model, tok, q)
        ok = False
        if tag == '错排数变体': ok = ('265' in a or '44' in a)  # D(6)=265, D(5)=44
        elif tag == 'LRU变体': ok = ('5' in a and '缺页' in a)
        elif tag == '快速幂变体': ok = ('776' in a or '824' in a)  # 2^50 mod 1000=824
        elif tag == 'TCP变体': ok = ('1' in a and '2' in a and '4' in a)
        elif tag == '圆排列变体': ok = ('24' in a or '120' in a)  # (5-1)!=24, 5!=120
        elif tag == 'RSA变体': ok = ('77' in a and ('60' in a or '72' in a))
        elif tag == 'B+树变体': ok = ('3' in a and '分裂' in a)
        elif tag == '谓词逻辑变体': ok = ('∀' in a or '∃' in a or '所有' in a)
        res[tag] = ok
    return res

def train_round(model, tok, dumps, out_dir, lr=2e-5, epochs=1):
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    n_vocab = model.config.vocab_size
    for ep in range(epochs):
        random.shuffle(dumps)
        tot = 0.0; n = 0
        for i in range(0, len(dumps), 2):
            batch = dumps[i:i+2]
            maxlen = min(1024, max(len(d['prompt'])+len(d['gen']) for d in batch))
            xs_pad = np.zeros((len(batch), maxlen), dtype=np.int64)
            lab_pad = np.full((len(batch), maxlen), -100, dtype=np.int64)
            for bi, d in enumerate(batch):
                seq = np.concatenate([d['prompt'], d['gen']])[:maxlen]
                xs_pad[bi, :len(seq)] = seq
                lab_pad[bi, len(d['prompt']):min(len(d['prompt'])+len(d['gen']), maxlen)] = seq[len(d['prompt']):maxlen]
            xs_t = torch.tensor(xs_pad, dtype=torch.long).to('cuda:0')
            lab_t = torch.tensor(lab_pad, dtype=torch.long).to('cuda:0')
            with torch.inference_mode():
                logits_f = model(xs_t).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), xs_t.view(-1), reduction='none')
            mask = (lab_t.view(-1) != -100)
            loss_ce = ce_all[mask].mean() if mask.any() else torch.tensor(0.0, device='cuda:0')
            with torch.inference_mode():
                a0 = model(xs_t, output_hidden_states=True).hidden_states[22][:, -8:].float()
            xs_n = torch.where(torch.rand(xs_t.shape, device='cuda:0') < 0.15,
                               torch.randint(0, n_vocab, xs_t.shape, device='cuda:0'), xs_t)
            a1 = model(xs_n, output_hidden_states=True).hidden_states[22][:, -8:].float()
            loss_den = 1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean()
            loss = loss_ce + 0.6 * loss_den
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f'  [round] ce={loss_ce.item():.3f} den={loss_den.item():.3f}', flush=True)
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir); tok.save_pretrained(out_dir)
    return tot / max(n, 1)

def main():
    tok = AutoTokenizer.from_pretrained(START)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(START, dtype=torch.bfloat16).to('cuda:0')
    dumps = []
    for f in sorted(glob.glob(f'{DECOMP}/p*.bin')):
        try: dumps.append(load_dump(f, 5120))
        except Exception: pass
    print(f'[data] {len(dumps)} decomp dumps', flush=True)
    random.shuffle(dumps)
    report = {}
    # 阶梯 1
    print('== stair1: first 20 ==', flush=True)
    train_round(model, tok, dumps[:20], '/root/distill_v5b_s1')
    s1 = understand_eval(model, tok)
    report['stair1'] = s1
    print(f'  understand: {sum(s1.values())}/{len(s1)}', flush=True)
    # 阶梯 2
    print('== stair2: +next 22 ==', flush=True)
    train_round(model, tok, dumps[20:42], '/root/distill_v5b_s2')
    s2 = understand_eval(model, tok)
    report['stair2'] = s2
    print(f'  understand: {sum(s2.values())}/{len(s2)}', flush=True)
    # 阶梯 3
    print('== stair3: all 42 ==', flush=True)
    train_round(model, tok, dumps[:42], '/root/distill_v5b_s3')
    s3 = understand_eval(model, tok)
    report['stair3'] = s3
    print(f'  understand: {sum(s3.values())}/{len(s3)}', flush=True)
    json.dump(report, open('/root/stair_report.json', 'w'), ensure_ascii=False, indent=1)
    print('[done] stair report saved', flush=True)
    for k, v in report.items():
        print(f'  {k}: {sum(v.values())}/{len(v)} {v}', flush=True)

if __name__ == '__main__':
    main()
