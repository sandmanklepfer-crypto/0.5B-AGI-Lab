#!/usr/bin/env python3
# V159 腾笼换鸟: 删70%冗余(gate行) → 腾空行重新初始化 → 只训练空行学推理(核心冻结)
# 数据: 少量推理样本(设方程/多步逻辑)
import torch, numpy as np, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
# 推理训练样本(带答案的推理链, 简短)
REASON_DATA = [
    ('小明比小红大3岁，小红比小刚大2岁，小明比小刚大几岁？', '小明比小刚大5岁。因为3+2=5。'),
    ('甲比乙高，乙比丙矮，谁最矮？', '乙最矮。因为丙比乙高。'),
    ('一个数加5等于12，这个数是多少？', '这个数是7。因为12-5=7。'),
    ('如果所有的鸟都有翅膀，企鹅是鸟，企鹅有翅膀吗？', '企鹅有翅膀。因为企鹅是鸟，所有鸟都有翅膀。'),
    ('苹果3元一斤，买4斤多少钱？', '12元。因为3×4=12。'),
]
TEST_Q = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
          '甲比乙高，乙比丙矮，谁最矮？',
          '中国的首都是哪里？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    # ---- 1. 随机删70% gate行(留空) ----
    sd = {k: v.clone() for k, v in sd0.items()}
    rng = np.random.RandomState(42)
    cut_rows = {}   # 每层被删的行号
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        n = int(4864 * 0.7)
        cut = rng.choice(4864, n, replace=False)
        cut_rows[L] = cut
        # 置零(清空旧知识)
        W = sd[WN].float().numpy()
        W[cut, :] = 0.0
        # 重新初始化空行(小随机, 给新鸟种子)
        W[cut, :] = np.random.RandomState(L).randn(len(cut), 896).astype(np.float32) * 0.02
        sd[WN] = torch.tensor(W).to(sd[WN].dtype)
    model.load_state_dict(sd, strict=True)
    print('腾笼: 70% gate行已清空并重新初始化', flush=True)

    # ---- 2. 只训练空行(核心冻结), 学推理 ----
    # 建mask: 哪些行可训练
    train_mask = {}
    for L in range(24):
        m = np.zeros(4864, dtype=bool)
        m[cut_rows[L]] = True
        train_mask[L] = torch.tensor(m, device='cuda')

    # 冻结所有参数
    for p in model.parameters():
        p.requires_grad = False
    # 只放开空行的gate权重
    opt_params = []
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        w = model.get_parameter(WN.replace('model.', '').replace('.weight', '').replace('.', '_')) if False else None
    # 更稳: 直接对gate weight做masked更新(手动SGD)
    lr = 1e-3
    lossf = torch.nn.CrossEntropyLoss()
    print('训练新鸟(空行学推理)...', flush=True)
    for ep in range(3):
        total = 0
        for q, a in REASON_DATA:
            text = '问题：%s\n推理：%s' % (q, a)
            ids = tok(text, return_tensors='pt').input_ids.to('cuda')
            x = ids[:, :-1]
            y = ids[:, 1:]
            model.zero_grad()
            out = model(input_ids=x)
            logits = out.logits  # (1,seq,V)
            loss = lossf(logits.reshape(-1, logits.size(-1)), y.reshape(-1))
            loss.backward()
            # masked更新: 只更新空行
            with torch.no_grad():
                for L in range(24):
                    WN = 'model.layers.%d.mlp.gate_proj.weight' % L
                    w = model.state_dict()[WN]
                    g = w.grad
                    if g is None: continue
                    mask = train_mask[L].unsqueeze(1).to(g.dtype)
                    upd = (g * mask)
                    w.data -= lr * upd
                    w.grad = None
            total += loss.item()
        print('  ep%d loss=%.3f' % (ep+1, total/len(REASON_DATA)), flush=True)
    print('训练完成', flush=True)

    # ---- 3. 测试 ----
    def test():
        res = []
        with torch.no_grad():
            for t in TEST_Q:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=25, do_sample=False, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                res.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:35])
        return res
    print('\n=== 腾笼换鸟后 ===', flush=True)
    for t, r in zip(TEST_Q, test()):
        print('  %s\n    → %s' % (t[:16], r), flush=True)
    # 对照: 原始0.5B
    model.load_state_dict(sd0, strict=True)
    print('\n=== 原始0.5B对照 ===', flush=True)
    for t, r in zip(TEST_Q, test()):
        print('  %s\n    → %s' % (t[:16], r), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
