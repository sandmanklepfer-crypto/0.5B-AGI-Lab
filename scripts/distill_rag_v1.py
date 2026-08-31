#!/usr/bin/env python3
"""distill_rag_v1 — 跨族几何蒸馏: 把 LFM2-RAG 的"基于上下文作答"技能
内化进 0.5B (qwen05b)。几何但不照搬 R1 同族路径:

  R1 同族做法        -> 跨族替代 (本脚本)
  ---------------------|---------------------------
  token id 直连 CE    -> 文本级 CE (answer 位置)
  逐 token 激活对齐   -> 句子级池化激活对齐 (同文本同句数)
  同空间 logits KL    -> 激活空间 |cos| (±方向等价)
  (无)                -> RAG 簇对比损失: query激活<->正context高, 负context低

损失: L = CE + w_align*L_align + w_sym*L_sym + w_rag*L_rag
用法: distill_rag_v1.py [--out DIR] [--epochs N] [--lr X] [--w_* W]
"""
import json, os, sys, random, argparse, re, math
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
TEACHER = '/root/lfm2-rag'

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/autodl-tmp/distill_rag_v1')
ap.add_argument('--data', default='/root/rag_data.jsonl')
ap.add_argument('--epochs', type=int, default=3)
ap.add_argument('--lr', type=float, default=5e-5)
ap.add_argument('--w_align', type=float, default=0.3)
ap.add_argument('--w_sym', type=float, default=0.5)
ap.add_argument('--w_rag', type=float, default=0.5)
ap.add_argument('--max_seq', type=int, default=1200)
ap.add_argument('--batch', type=int, default=2)
ap.add_argument('--margin', type=float, default=0.2, help='RAG 对比损失 margin')
ap.add_argument('--s_layer', type=int, default=22, help='student 激活层')
ap.add_argument('--proj_dim', type=int, default=256)
args = ap.parse_args()

S_LAYER, PROJ_DIM = args.s_layer, args.proj_dim
S_NEMBD = 896
SEED = 42
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)

def split_sentences(text: str) -> list[str]:
    """中文句切分 (。！？; ; 分段)"""
    parts = re.split(r'(?<=[。！？；;])|\n+', text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]

# ---------- 数据 ----------
def load_data(path):
    rows = []
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line: continue
        rows.append(json.loads(line))
    return rows

# ---------- 激活提取 ----------
@torch.inference_mode()
def sent_acts(model, tok, texts, layer, device):
    """编码 texts, 返回每文本的 [句子数, dim] 池化激活 (取层 hidden 均值)"""
    outs = []
    for t in texts:
        sents = split_sentences(t)
        if not sents:
            sents = [t]
        acts = []
        for s in sents:
            ids = tok(s, return_tensors='pt').to(device)
            with torch.inference_mode():
                h = model(**ids, output_hidden_states=True)
            acts.append(h.hidden_states[layer][0].mean(0))  # [dim]
        outs.append(torch.stack(acts))
    return outs  # list[Tensor [ns, dim]]

def compute_proj_from(act_list, dim_out):
    """SVD 投影矩阵: 拼接所有激活 -> [N, dim] -> V[:, :dim_out] (dim x out)"""
    A = torch.cat([a for a in act_list], dim=0).float().cpu().numpy()
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    P = Vt[:dim_out].T  # [dim, dim_out]
    return torch.tensor(P, dtype=torch.float32)

# ---------- 训练 ----------
def main():
    print('[load] student + teacher...', flush=True)
    tok = AutoTokenizer.from_pretrained(STUDENT)
    tok.pad_token = tok.eos_token
    dev = 'cuda:0'
    stu = AutoModelForCausalLM.from_pretrained(STUDENT, dtype=torch.bfloat16).to(dev)
    tea = AutoModelForCausalLM.from_pretrained(TEACHER, dtype=torch.bfloat16).to(dev)
    tea.eval()
    t_layer = tea.config.num_hidden_layers - 4
    t_dim = tea.config.hidden_size
    print(f'[model] teacher LFM2 layers={tea.config.num_hidden_layers} dim={t_dim} act_layer={t_layer}', flush=True)
    print(f'[model] student layers={stu.config.num_hidden_layers} dim={S_NEMBD} act_layer={S_LAYER}', flush=True)

    rows = load_data(args.data)
    print(f'[data] {len(rows)} rows', flush=True)
    # 负样本池: 每文档选一条别的文档的 context
    by_title = {}
    for r in rows:
        by_title.setdefault(r['title'], []).append(r)
    titles = list(by_title.keys())
    for r in rows:
        others = [t for t in titles if t != r['title']]
        neg = random.choice(others)
        r['neg_context'] = random.choice(by_title[neg])['context']

    # ---- 预计算投影矩阵 (采样前 40 条) ----
    print('[proj] computing SVD projections...', flush=True)
    sample = rows[:40]
    full_texts = [r['context'] + r['query'] + r['answer'] for r in sample]
    # teacher 用自己的 tokenizer (跨族: 不能共用)
    tok_t = AutoTokenizer.from_pretrained(TEACHER)
    with torch.inference_mode():
        t_acts2 = sent_acts(tea, tok_t, full_texts, t_layer, dev)
        s_acts = sent_acts(stu, tok, full_texts, S_LAYER, dev)
    P_t = compute_proj_from(t_acts2, PROJ_DIM)  # [total_sents, 256]
    P_s = compute_proj_from(s_acts, PROJ_DIM)
    P_t = P_t.to(dev); P_s = P_s.to(dev)
    print(f'[proj] P_t={P_t.shape} P_s={P_s.shape}', flush=True)

    def project(acts, P):
        """acts: list[Tensor[ns,dim]] -> list[Tensor[ns,256]]"""
        return [a.float() @ P for a in acts]

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
            # --- CE: student 生成式 (context+query -> answer) ---
            texts_in = [r['context'] + r['query'] for r in batch]
            ans_texts = [r['answer'] for r in batch]
            enc = tok(texts_in, return_tensors='pt', padding=True, truncation=True,
                      max_length=args.max_seq).to(dev)
            ans_ids = tok(ans_texts, return_tensors='pt', padding=True, truncation=True,
                          max_length=args.max_seq // 2).to(dev)
            # 拼接 input + answer (answer 部分算 CE)
            in_len = enc['input_ids'].shape[1]
            a_ids = ans_ids['input_ids'][:, :in_len]  # 截断避免超长
            full = torch.cat([enc['input_ids'], a_ids], dim=1)
            am = torch.cat([enc['attention_mask'],
                            torch.ones_like(a_ids)], dim=1)
            labels = full.clone()
            labels[:, :in_len] = -100
            out = stu(full, attention_mask=am, labels=labels)
            loss_ce = out.loss

            # --- 激活: 整段 (context+query+answer) 句子池化 ---
            full_texts = [r['context'] + r['query'] + r['answer'] for r in batch]
            s_acts = sent_acts(stu, tok, full_texts, S_LAYER, dev)
            with torch.inference_mode():
                t_acts = sent_acts(tea, tok_t, full_texts, t_layer, dev)
            # 句子数不同则按比例池化到 min
            s_p = project(s_acts, P_s)
            t_p = project(t_acts, P_t)
            loss_align = torch.tensor(0.0, device=dev)
            n_pairs = 0
            for sa, ta in zip(s_p, t_p):
                ns, nt = sa.shape[0], ta.shape[0]
                m = min(ns, nt)
                if m == 0: continue
                sa, ta = sa[:m], ta[:m]
                cs = F.cosine_similarity(sa, ta, dim=-1)
                loss_align = loss_align + (1 - cs.abs()).mean()  # |cos| -> 1
                n_pairs += 1
            loss_align = loss_align / max(n_pairs, 1)

            # --- L_sym: query 同义变体激活不变 (纯 student) ---
            loss_sym = torch.tensor(0.0, device=dev)
            n_sym = 0
            for r in batch:
                q0 = r['query']
                for v in r.get('variants', [])[:1]:
                    a_q0 = sent_acts(stu, tok, [q0], S_LAYER, dev)[0]
                    a_q1 = sent_acts(stu, tok, [v], S_LAYER, dev)[0]
                    m = min(a_q0.shape[0], a_q1.shape[0])
                    if m == 0: continue
                    cs = F.cosine_similarity(a_q0[:m].float(), a_q1[:m].float(), dim=-1)
                    loss_sym = loss_sym + (1 - cs.abs()).mean()
                    n_sym += 1
            loss_sym = loss_sym / max(n_sym, 1)

            # --- L_rag: query <-> 正context 高, 负context 低 ---
            loss_rag = torch.tensor(0.0, device=dev)
            n_rag = 0
            for r in batch:
                a_q = sent_acts(stu, tok, [r['query']], S_LAYER, dev)[0].float().mean(0)
                a_p = sent_acts(stu, tok, [r['context']], S_LAYER, dev)[0].float().mean(0)
                a_n = sent_acts(stu, tok, [r['neg_context']], S_LAYER, dev)[0].float().mean(0)
                c_pos = F.cosine_similarity(a_q.unsqueeze(0), a_p.unsqueeze(0)).abs()
                c_neg = F.cosine_similarity(a_q.unsqueeze(0), a_n.unsqueeze(0)).abs()
                loss_rag = loss_rag + (1 - c_pos) + torch.clamp(c_neg - args.margin, min=0)
                n_rag += 1
            loss_rag = loss_rag / max(n_rag, 1)

            loss = loss_ce + args.w_align * loss_align + args.w_sym * loss_sym + args.w_rag * loss_rag
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss += loss.item()
            step += 1
            if step % 10 == 0:
                print(f'[ep{ep} s{step}] loss={loss.item():.3f} ce={loss_ce.item():.3f} '
                      f'align={loss_align.item():.3f} sym={loss_sym.item():.3f} rag={loss_rag.item():.3f}',
                      flush=True)
        print(f'[ep{ep}] avg={ep_loss / max(1, total // args.batch):.3f}', flush=True)
        # 保存
        os.makedirs(args.out, exist_ok=True)
        stu.save_pretrained(args.out)
        tok.save_pretrained(args.out)
        print(f'[save] {args.out}', flush=True)

if __name__ == '__main__':
    main()
