#!/usr/bin/env python3
"""
V103 真正的章程空间展开 (权重×权重 / 特征交互) — 验证"容量随滚次增长"
修正 v102b 失败根因: 反复套同一 MLP (W(W(Wx))) = 线性幂次化, 不产生新结构, 只会转圈退化
V103 数学: Kronecker 特征交互展开 — 每滚引入 x_r ⊙ x0 二阶(高次)交叉项
          函数类随"阶数"严格变大 (depth-separation): 滚N次 ≈ N阶多项式章程空间
          0.5B滚1次=二阶空间(≈0.5B²的特征组合), 滚N次=N阶
实现:
  滚动层=20. forward替换: 
    m1 = silu(gate(x))·up(x)            # 一阶组织 (原MLP)
    m2 = R(x ⊙ x0)                       # 二阶交叉: 与原始输入交互, R固定随机896→4864
    h  = down(m1 + λ·m2)                 # 每滚都与x0交互 → 累积 r 阶项, 不转圈
  验证(不生成文本, 绕开base答题退化):
    8类约束句子 × 每类多句 → 前向拿层20末token激活
    → 线性探针(岭回归)预测类别
    → 滚1/3/6 的探针acc = 章程空间里类别是否线性可分的直接度量
"""
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
ROLL_LAYER = 20
LAM = 0.25
N_TRAIN = 24   # 每类训练句数
N_TEST = 8     # 每类测试句数

def make_sentences(cls_id):
    """8类 = 甲乙丙 各自在一队/二队 的 2^3 组合; 每句多种措辞"""
    a = (cls_id >> 2) & 1
    b = (cls_id >> 1) & 1
    c = cls_id & 1
    ta, tb, tc = ('一队' if a else '二队'), ('一队' if b else '二队'), ('一队' if c else '二队')
    variants = [
        f"甲在{ta}，乙在{tb}，丙在{tc}。",
        f"队伍分配：甲→{ta}，乙→{tb}，丙→{tc}。",
        f"甲属于{ta}，乙属于{tb}，丙属于{tc}。",
        f"甲:{ta} 乙:{tb} 丙:{tc}",
        f"把甲编入{ta}、乙编入{tb}、丙编入{tc}。",
    ]
    return variants

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    mlp = model.model.layers[ROLL_LAYER].mlp
    orig_fwd = mlp.forward
    # 固定随机升维映射 (二阶交叉): 896 -> 4864 (与MLP中间同维, 之后down)
    rng = np.random.RandomState(42)
    Rmat = torch.tensor(rng.randn(4864, 896).astype(np.float32) / np.sqrt(896)).to(torch.bfloat16).cuda() * 0.5
    cur_rolls = 1

    def rolling_forward(x):
        h = orig_fwd(x)
        if cur_rolls <= 1:
            return h
        gw, uw, dw = mlp.gate_proj.weight, mlp.up_proj.weight, mlp.down_proj.weight
        x0 = x.detach()                 # 原始输入 (本token)
        acc = h
        cur = h
        for _ in range(cur_rolls - 1):
            m1 = F.silu(F.linear(cur, gw)) * F.linear(cur, uw)      # 一阶组织
            m2 = F.linear(cur * x0, Rmat)                            # 二阶交叉: cur ⊙ x0
            m = m1 + LAM * m2
            cur = cur + F.linear(m, dw)                              # 残差滚动(累积新阶)
            acc = cur
        return acc
    mlp.forward = rolling_forward

    def get_act(texts, rolls):
        cur_rolls = rolls
        vecs = []
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                out = model(input_ids=ids, output_hidden_states=True)
                v = out.hidden_states[ROLL_LAYER + 1][0, -1].float().cpu().numpy()  # 层20输出
                vecs.append(v)
        return np.array(vecs)

    def linprobe(Xtr, ytr, Xte, yte):
        """岭回归 one-hot 线性探针: 返回 top-1 acc"""
        ncls = ytr.max() + 1
        Y = np.zeros((len(ytr), ncls)); Y[np.arange(len(ytr)), ytr] = 1
        Xtr = Xtr - Xtr.mean(0, keepdims=True)
        Xte = Xte - Xte.mean(0, keepdims=True)
        lam = 1.0
        Wp = np.linalg.solve(Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1]), Xtr.T @ Y)
        pred = Xte @ Wp
        return (pred.argmax(1) == yte).mean()

    # 数据: 8类 × 每类句子(训练+测试, 用不同措辞循环)
    all_tr, all_te = [], []
    y_tr, y_te = [], []
    for cid in range(8):
        sents = make_sentences(cid)
        for i in range(N_TRAIN):
            all_tr.append(sents[i % len(sents)] + f"（第{i}号记录）")
            y_tr.append(cid)
        for i in range(N_TEST):
            all_te.append(sents[(i + 3) % len(sents)] + f"（备注{i}）")
            y_te.append(cid)
    y_tr = np.array(y_tr); y_te = np.array(y_te)

    print('[V103] 章程空间(特征交互滚动) | 滚动层%d λ=%.2f | 训练%d句 测试%d句 8类' % (
        ROLL_LAYER, LAM, len(all_tr), len(all_te)), flush=True)
    for r in [1, 3, 6]:
        print('  采集 滚%d 激活...' % r, flush=True)
        Xtr = get_act(all_tr, r)
        Xte = get_act(all_te, r)
        acc = linprobe(Xtr, y_tr, Xte, y_te)
        # 基准: 输入embedding可线性分吗(看是不是模型哪都行)
        print('  [滚%d次] 层20激活 线性探针acc=%.3f' % (r, acc), flush=True)
    mlp.forward = orig_fwd
    print('\n[V103] 完成 (若acc随滚次上升 = 章程空间容量随阶数增长的直接证据)', flush=True)

if __name__ == '__main__':
    main()
