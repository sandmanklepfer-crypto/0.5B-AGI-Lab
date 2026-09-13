#!/usr/bin/env python3
"""probe_topo.py — 几何形状探测: 流形拓扑(非指标)
A. 概念簇的树拓扑: 距离矩阵->层次聚类->分支结构(合并模式)
B. 生成轨迹拓扑: 30步轨迹的3D形状(位移/曲率/方向变化) v4b vs v4c
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

V4B = "/workspace/backups_a800/distill_mix_v4b"
V4C = "/workspace/backups_a800/distill_v4c"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "老虎", "苹果", "香蕉", "数学", "物理", "化学",
            "太阳", "月亮", "星星", "医生", "老师", "学生", "汽车", "火车", "飞机", "米饭", "面条",
            "电脑", "手机", "音乐", "电影", "足球", "游泳", "跑步", "北京", "上海", "广州", "战争",
            "和平", "经济", "历史", "科技", "艺术", "睡眠", "吃饭", "旅行", "学习", "工作", "爱情",
            "友谊", "春天", "冬天", "量子", "基因"]
Q = "你好"

def concept_acts(model, tok, layer=22):
    U = []
    for c in CONCEPTS:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        U.append(u / (u.norm() + 1e-12))
    return torch.stack(U)

def cluster_tree(U, thresh=0.15):
    """层次聚类树拓扑: 距离<thresh的连边, 统计簇数/合并模式"""
    N = U.shape[0]
    D = 1 - (U @ U.T).abs()
    # 阈值图: 连边数/分量数 (简单并查集)
    parent = list(range(N))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    edges = 0
    for i in range(N):
        for j in range(i+1, N):
            if D[i, j] < thresh:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj; edges += 1
    comps = len(set(find(i) for i in range(N)))
    return comps, edges, D.mean().item()

def trajectory_topo(model, tok, q, steps=25, layer=22):
    ids = tok(q, return_tensors="pt")
    gen = ids["input_ids"]
    traj = []
    for _ in range(steps):
        with torch.inference_mode():
            lg = model(gen).logits[:, -1]
        nxt = torch.argmax(lg, dim=-1).unsqueeze(0)
        gen = torch.cat([gen, nxt], dim=1)
        with torch.inference_mode():
            h = model(gen, output_hidden_states=True)
        a = h.hidden_states[layer][0, -1].float()
        traj.append(a / (a.norm() + 1e-12))
    A = torch.stack(traj)
    U, S, V = torch.pca_lowrank(A, q=3)
    P = (A @ V).cpu().numpy()
    disp = np.linalg.norm(P[-1] - P[0])          # 位移(轨迹伸展)
    dirs = P[1:] - P[:-1]
    dirs = dirs / (np.linalg.norm(dirs, axis=1, keepdims=True) + 1e-12)
    curv = np.mean([np.linalg.norm(dirs[i] - dirs[i+1]) for i in range(len(dirs)-1)])  # 曲率(方向变化)
    return disp, curv

if __name__ == "__main__":
    print("=== 几何形状(流形拓扑) v4b vs v4c ===")
    for name, path in [("v4b", V4B), ("v4c", V4C)]:
        tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
        m = AutoModelForCausalLM.from_pretrained(path)
        m.eval()
        U = concept_acts(m, tok)
        comps, edges, dmean = cluster_tree(U, 0.15)
        disp, curv = trajectory_topo(m, tok, Q)
        print(f"{name}: 簇拓扑[分量数={comps}, 连边={edges}, 平均距离={dmean:.3f}] "
              f"| 轨迹拓扑[位移={disp:.3f}, 曲率={curv:.4f}]")
        del m
