#!/usr/bin/env python3
"""probe_funnel.py — 沙漏窄颈细节几何
①汇合微观过程(层0-6逐层间距: 渐入/骤变) ②公共带束宽 ③窄颈维度 ④3D形状
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
TEXTS = {
    "三段论": "所有的A都是B，所有的B都是C，那么A是什么？",
    "纯推理": "如果下雨路会湿，路没湿，今天下雨了吗？",
    "纯数学": "1+1等于几？",
    "代码": "写一个Python函数计算两个数的和",
    "普通": "你好",
}

def trajectory(model, tok, text):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    traj = []
    for li in range(len(h.hidden_states)):
        a = h.hidden_states[li][0].mean(0).float()
        traj.append(a / (a.norm() + 1e-12))
    return torch.stack(traj)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    trajs = {n: trajectory(m, tok, t) for n, t in TEXTS.items()}
    names = list(trajs)
    syl = trajs["三段论"]

    print("=== ① 汇合微观过程 (层0-6, 三段论vs各题间距) ===")
    for li in range(7):
        ds = [1 - F.cosine_similarity(syl[li].unsqueeze(0), trajs[n][li].unsqueeze(0)).item() for n in names if n != "三段论"]
        print(f"  层{li}: 间距={[round(d,4) for d in ds]} 均值={sum(ds)/len(ds):.4f}")

    print("\n=== ② 公共带束宽 (层4-20, 5轨迹两两最大间距) ===")
    for li in [4, 8, 12, 16, 20]:
        dmax = 0
        for i in range(len(names)):
            for j in range(i+1, len(names)):
                d = 1 - F.cosine_similarity(trajs[names[i]][li].unsqueeze(0), trajs[names[j]][li].unsqueeze(0)).item()
                dmax = max(dmax, d)
        print(f"  层{li}: 束宽(最大间距)={dmax:.4f}")

    print("\n=== ③ 公共带维度 (层8激活PCA: 窄颈是低维?) ===")
    A8 = torch.stack([trajs[n][8] for n in names])
    U, S, V = torch.pca_lowrank(A8, q=5)
    print(f"  层8 5轨迹前5奇异值: {[round(x.item(),3) for x in S]}")

    print("\n=== ④ 公共带3D形状 (层4-20 全部轨迹点) ===")
    A = torch.cat([trajs[n][4:21] for n in names], dim=0)
    U, S, V = torch.pca_lowrank(A, q=3)
    P = (A @ V).cpu().numpy()
    # 束的3D范围
    span = P.max(0) - P.min(0)
    print(f"  公共带3D跨度: x={span[0]:.3f} y={span[1]:.3f} z={span[2]:.3f} (小=窄束)")
    # 每轨迹在公共带的位移
    for i, n in enumerate(names):
        seg = P[i*17:(i+1)*17]
        move = np.linalg.norm(seg[-1]-seg[0])
        print(f"  {n}: 公共带内位移={move:.4f}")
