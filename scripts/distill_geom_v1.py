#!/usr/bin/env python3
"""distill_geom_v1 — 泛化/涌现几何蒸馏: 学生激活距离矩阵 -> 匹配 R1-32B 的 D_t
在 distill_rag_v1 基础上叠加 L_geom = ||D_s - D_t||_F (Frobenius)
从 distill_rag_v1 模型继续训练 (RAG 技能保底, 几何校准叠加)
用法: distill_geom_v1.py [--out DIR] [--epochs N] [--w_geom W]
"""
import json, os, sys, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/distill_rag_v1'
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/autodl-tmp/distill_geom_v1')
ap.add_argument('--data', default='/root/rag_data.jsonl')
ap.add_argument('--geom', default='/root/probe_geom_t.npz')
ap.add_argument('--probes', default='/root/probes.txt')
ap.add_argument('--epochs', type=int, default=2)
ap.add_argument('--lr', type=float, default=3e-5)
ap.add_argument('--w_geom', type=float, default=0.4)
ap.add_argument('--w_align', type=float, default=0.3)
ap.add_argument('--w_sym', type=float, default=0.5)
ap.add_argument('--w_rag', type=float, default=0.5)
ap.add_argument('--max_seq', type=int, default=1200)
ap.add_argument('--batch', type=int, default=2)
ap.add_argument('--s_layer', type=int, default=22)
ap.add_argument('--proj_dim', type=int, default=256)
args = ap.parse_args()

S_LAYER, PROJ_DIM = args.s_layer, args.proj_dim
SEED = 42
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)

def split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[。！？；;])|\n+', text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]

def load_rows(path):
    return [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]

@torch.inference_mode()
def sent_acts(model, tok, texts, layer, device):
    outs = []
    for t in texts:
        sents = split_sentences(t)
        if not sents: sents = [t]
        acts = []
        for s in sents:
            ids = tok(s, return_tensors='pt').to(device)
            h = model(**ids, output_hidden_states=True)
            acts.append(h.hidden_states[layer][0].mean(0))
        outs.append(torch.stack(acts))
    return outs

def main():
    print('[load] student = distill_rag_v1...', flush=True)
    tok = AutoTokenizer.from_pretrained(STUDENT)
    tok.pad_token = tok.eos_token
    dev = 'cuda:0'
    stu = AutoModelForCausalLM.from_pretrained(STUDENT, dtype=torch.bfloat16).to(dev)

    rows = load_rows(args.data)
    probes = [l.strip() for l in open(args.probes, encoding='utf-8') if l.strip()]
    G = np.load(args.geom)
    D_t = torch.tensor(G['D'], dtype=torch.float32).to(dev)  # [96,96]
    print(f'[data] rows={len(rows)} probes={len(probes)} D_t={D_t.shape} mean={D_t.mean():.3f}', flush=True)

    by_title = {}
    for r in rows: by_title.setdefault(r['title'], []).append(r)
    titles = list(by_title.keys())
    for r in rows:
        others = [t for t in titles if t != r['title']]
        r['neg_context'] = random.choice(by_title[random.choice(others)])['context']

    # ---- 学生 probe 投影矩阵 (SVD, 与 teacher 同维度空间) ----
    print('[proj] student probe SVD...', flush=True)
    with torch.inference_mode():
        s_probe_acts = sent_acts(stu, tok, probes, S_LAYER, dev)
    A = torch.cat([a for a in s_probe_acts], dim=0).float().cpu().numpy()
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    P_s = torch.tensor(Vt[:PROJ_DIM].T, dtype=torch.float32).to(dev)  # [896,256]
    print(f'[proj] P_s={P_s.shape}', flush=True)

    def probe_Ds():
        """学生 96 个 probe 激活 -> 距离矩阵 [96,96]"""
        with torch.inference_mode():
            acts = sent_acts(stu, tok, probes, S_LAYER, dev)
        vecs = torch.stack([a.mean(0).float() @ P_s for a in acts])  # [96,256]
        vecs = vecs / (vecs.norm(dim=1, keepdim=True) + 1e-12)
        C = (vecs @ vecs.T).abs()
        return 1.0 - C

    # ---- 优化器 ----
    opt = torch.optim.AdamW(stu.parameters(), lr=args.lr)
    os.makedirs(args.out, exist_ok=True)
    total = len(rows)
    step = 0
    for ep in range(1, args.epochs + 1):
        random.shuffle(rows)
        ep_loss = 0.0
        for i in range(0, total, args.batch):
            batch = rows[i:i + args.batch]
            # CE
            texts_in = [r['context'] + r['query'] for r in batch]
            enc = tok(texts_in, return_tensors='pt', padding=True, truncation=True,
                      max_length=args.max_seq).to(dev)
            ans_ids = tok([r['answer'] for r in batch], return_tensors='pt', padding=True,
                          truncation=True, max_length=args.max_seq // 2).to(dev)
            in_len = enc['input_ids'].shape[1]
            a_ids = ans_ids['input_ids'][:, :in_len]
            full = torch.cat([enc['input_ids'], a_ids], dim=1)
            am = torch.cat([enc['attention_mask'], torch.ones_like(a_ids)], dim=1)
            labels = full.clone(); labels[:, :in_len] = -100
            loss_ce = stu(full, attention_mask=am, labels=labels).loss

            # L_geom: 距离矩阵匹配 (核心)
            D_s = probe_Ds()
            loss_geom = ((D_s - D_t) ** 2).mean().sqrt()  # Frobenius/规模归一

            # L_rag (保底): query <-> 正/负 context
            loss_rag = torch.tensor(0.0, device=dev); n = 0
            for r in batch:
                with torch.inference_mode():
                    a_q = sent_acts(stu, tok, [r['query']], S_LAYER, dev)[0].float().mean(0)
                    a_p = sent_acts(stu, tok, [r['context']], S_LAYER, dev)[0].float().mean(0)
                    a_n = sent_acts(stu, tok, [r['neg_context']], S_LAYER, dev)[0].float().mean(0)
                c_pos = F.cosine_similarity(a_q.unsqueeze(0), a_p.unsqueeze(0)).abs()
                c_neg = F.cosine_similarity(a_q.unsqueeze(0), a_n.unsqueeze(0)).abs()
                loss_rag = loss_rag + (1 - c_pos) + torch.clamp(c_neg - 0.2, min=0)
                n += 1
            loss_rag = loss_rag / max(n, 1)

            loss = loss_ce + args.w_geom * loss_geom + args.w_rag * loss_rag
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item(); step += 1
            if step % 8 == 0:
                print(f'[ep{ep} s{step}] loss={loss.item():.3f} ce={loss_ce.item():.3f} '
                      f'geom={loss_geom.item():.3f} rag={loss_rag.item():.3f}', flush=True)
        print(f'[ep{ep}] avg={ep_loss / max(1, total // args.batch):.3f}', flush=True)
        stu.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f'[save] {args.out}', flush=True)

if __name__ == '__main__':
    main()
