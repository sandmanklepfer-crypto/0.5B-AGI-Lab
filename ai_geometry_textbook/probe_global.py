#!/usr/bin/env python3
"""probe_global.py — 全层轨迹全局几何: 概念/题目的25层激活轨迹
探测: ①轨迹整体形状(PCA 3D) ②三段论轨迹 vs 纯推理/纯数学 的汇合点
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
TEXTS = {
    "三段论(推理×数学)": "所有的A都是B，所有的B都是C，那么A是什么？",
    "纯推理": "如果下雨路会湿，路没湿，今天下雨了吗？",
    "纯数学": "1+1等于几？",
    "代码": "写一个Python函数计算两个数的和",
    "普通": "你好",
}

def trajectory(model, tok, text):
    """概念过全层的激活轨迹 [25, 896]"""
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
    trajs = {name: trajectory(m, tok, t) for name, t in TEXTS.items()}
    names = list(trajs)
    print("=== 全层轨迹全局几何 ===")
    # 1. 轨迹间距 (同层位置的距离): 三段论 vs 其他
    syl = trajs["三段论(推理×数学)"]
    print("\n--- 轨迹间距 (1-cos, 每层) 三段论 vs 各题 ---")
    for name in names:
        if name == "三段论(推理×数学)": continue
        d = [1 - F.cosine_similarity(syl[li].unsqueeze(0), trajs[name][li].unsqueeze(0)).item() for li in range(0, 25, 4)]
        print(f"  三段论vs{name}: 间距(层0,4,8,12,16,20,24)={[round(x,3) for x in d]}")
    # 2. 全局PCA 3D: 所有轨迹的点投影
    A = torch.cat([trajs[n] for n in names], dim=0)  # [125, 896]
    U, S, V = torch.pca_lowrank(A, q=3)
    P = (A @ V).cpu().numpy()  # [125, 3]
    print("\n--- 全局PCA 3D (125点: 5题×25层) ---")
    for i, name in enumerate(names):
        seg = P[i*25:(i+1)*25]
        print(f"  {name}: 起点({seg[0,0]:.3f},{seg[0,1]:.3f},{seg[0,2]:.3f}) "
              f"终点({seg[-1,0]:.3f},{seg[-1,1]:.3f},{seg[-1,2]:.3f}) "
              f"轨迹长度={np.linalg.norm(seg[-1]-seg[0]):.3f}")
    # 3. 汇合检测: 轨迹是否在某层后"合并"(间距骤降)
    print("\n--- 汇合检测 (轨迹间距是否在某层后骤降) ---")
    for name in ["纯推理", "纯数学"]:
        d_all = [1 - F.cosine_similarity(syl[li].unsqueeze(0), trajs[name][li].unsqueeze(0)).item() for li in range(25)]
        drop = [i for i in range(1, 25) if d_all[i] < d_all[i-1] * 0.7]
        print(f"  三段论vs{name}: 起始间距={d_all[0]:.3f} 末端间距={d_all[-1]:.3f} 骤降层={drop[:5]}")
