# -*- coding: utf-8 -*-
"""gen_short.py — 短样本空间数据(为端侧训练效率优化: 每条 ≤40 token)"""
import random, json, sys
import numpy as np

TASKS = ["right","left","high","low","near","far","dist","count","axis_x","axis_y","axis_z"]

def gen(rng):
    n = rng.randint(2,4)
    balls=[(rng.uniform(-4,4), rng.uniform(0.2,4.0), rng.uniform(-4,4)) for _ in range(n)]
    def scene(): return " ".join("球%d(%.1f,%.1f,%.1f)"%(i,b[0],b[1],b[2]) for i,b in enumerate(balls))
    t = rng.choice(TASKS)
    if t=="right":
        i = max(range(n), key=lambda k: balls[k][0])
        return scene(), "谁最靠右？", "球%d"%i
    if t=="left":
        i = min(range(n), key=lambda k: balls[k][0])
        return scene(), "谁最靠左？", "球%d"%i
    if t=="high":
        i = max(range(n), key=lambda k: balls[k][1])
        return scene(), "谁最高？", "球%d"%i
    if t=="low":
        i = min(range(n), key=lambda k: balls[k][1])
        return scene(), "谁最低？", "球%d"%i
    if t=="near":
        i = min(range(n), key=lambda k: balls[k][2])
        return scene(), "谁离镜头最近？", "球%d"%i
    if t=="far":
        i = max(range(n), key=lambda k: balls[k][2])
        return scene(), "谁离镜头最远？", "球%d"%i
    if t=="dist":
        if n<2: return gen(rng)
        i,j = rng.sample(range(n),2)
        d = float(np.sqrt(sum((balls[i][k]-balls[j][k])**2 for k in range(3))))
        return scene(), "球%d和球%d相距多远？"%(i,j), "%.1f"%d
    if t=="count":
        return scene(), "一共有几个球？", "球%d个"%n if False else "%d"%n
    if t in ("axis_x","axis_y","axis_z"):
        i = rng.randrange(n); ax = {"axis_x":0,"axis_y":1,"axis_z":2}[t]
        return scene(), "球%d的%s坐标是多少？"%(i,{"axis_x":"x","axis_y":"y","axis_z":"z"}[t]), "%.1f"%balls[i][ax]
    return gen(rng)

def build(n, seed=1):
    rng = random.Random(seed)
    out=[]
    for _ in range(n):
        s,q,a = gen(rng)
        out.append({"q":s+"\n问："+q, "a":a})
    return out

if __name__=="__main__":
    n = int(sys.argv[1]) if len(sys.argv)>1 else 400
    dst = sys.argv[2] if len(sys.argv)>2 else "/workspace/space_short.jsonl"
    data = build(n)
    with open(dst,"w",encoding="utf-8") as f:
        for d in data: f.write(json.dumps(d,ensure_ascii=False)+"\n")
    print("生成 %d 条 → %s"%(n,dst))
    for d in data[:6]:
        print("\nQ:", d["q"])
        print("A:", d["a"])
