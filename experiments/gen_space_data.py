# -*- coding: utf-8 -*-
"""gen_space_data.py — 空间能力训练数据生成器(L1: ASCII 伪3D)
   老师 = 几何规则本身(确定性, 完美标注, 可无限生成)
   产出三类样本:
     ① 场景 → ASCII画面       (学会画)
     ② 画面 → 空间问答        (学会看)
     ③ 场景 → 空间推理        (学会推: 会不会撞/去哪了)
"""
import numpy as np, json, random, sys

W, H = 44, 16
FOCAL = 30.0
CAM = (0.0, 2.0, -8.0)

def project(x, y, z, cam=CAM):
    dx, dy, dz = x-cam[0], y-cam[1], z-cam[2]
    if dz <= 0.35: return None
    sx = int(round(W/2 + FOCAL*dx/dz))
    sy = int(round(H/2 - FOCAL*dy/dz))
    if 0 <= sx < W and 0 <= sy < H: return (sx, sy)
    return None

def render(balls, ground=0.0):
    buf = [[" "]*W for _ in range(H)]
    zb  = [[1e9]*W for _ in range(H)]
    def put(x,y,z,ch):
        p = project(x,y,z)
        if not p: return
        sx,sy = p
        dz = z - CAM[2]
        if dz < zb[sy][sx]:
            zb[sy][sx] = dz; buf[sy][sx] = ch
    for gx in range(-4,5):
        for gz in range(-4,5):
            put(gx, ground, gz, "+" if (gx==0 and gz==0) else ".")
    for i,b in enumerate(balls):
        cx,cy,cz,r = b
        K = 20
        for k in range(K):
            a = k/K*2*np.pi
            put(cx+np.cos(a)*r, cy+np.sin(a)*r*0.5, cz, str(i))
            put(cx, cy+r, cz+np.cos(a)*r, str(i))
        put(cx,cy,cz,str(i))
    return "\n".join("".join(row).rstrip() for row in buf)

def rand_scene(rng, n=None):
    n = n or rng.randint(1,4)
    balls=[]
    for _ in range(n):
        balls.append(( rng.uniform(-3.5,3.5), rng.uniform(0.3,4.0), rng.uniform(-3.5,3.5),
                       rng.uniform(0.18,0.35) ))
    return balls

# ---------- 问答模板 ----------
def qa_count(balls):   return "画面里有几个球？", str(len(balls))
def qa_where(balls, i): 
    b=balls[i]
    return "第%d个球在什么位置？"%i, "(%.1f, %.1f, %.1f)"%b[:3]
def qa_left(balls):
    i=min(range(len(balls)), key=lambda k: balls[k][0])
    return "哪个球在最左边？", "第%d个"%i
def qa_high(balls):
    i=max(range(len(balls)), key=lambda k: balls[k][1])
    return "哪个球最高？", "第%d个"%i
def qa_near(balls):
    i=min(range(len(balls)), key=lambda k: balls[k][2])
    return "哪个球离镜头最近？", "第%d个"%i
def qa_dist(balls, i, j):
    a,b=balls[i],balls[j]
    d=np.sqrt(sum((a[k]-b[k])**2 for k in range(3)))
    return "第%d个球和第%d个球相距多远？"%(i,j), "%.1f"%d

def make_sample(rng):
    balls = rand_scene(rng)
    art = render(balls)
    typ = rng.randint(0,3)
    if typ==0:
        # 场景 → 画面 (学会画)
        scene = "；".join("球%d(%.1f,%.1f,%.1f)"%(i,b[0],b[1],b[2]) for i,b in enumerate(balls))
        q = "用ASCII画出这个场景：%s"%scene
        a = "```\n%s\n```"%art
    elif typ==1:
        # 画面 → 问答 (学会看)
        fns = [qa_count, qa_left, qa_high, qa_near]
        f = rng.choice(fns)
        q0,a0 = f(balls)
        if rng.random()<0.5:
            i = rng.randrange(len(balls)); q0,a0 = qa_where(balls,i)
        q = "这是ASCII场景：\n```\n%s\n```\n问：%s"%(art,q0)
        a = a0
    else:
        # 场景 → 空间推理
        i = rng.randrange(len(balls)); j = rng.randrange(len(balls))
        if i==j: j=(j+1)%len(balls)
        if i==j: continue
        q0,a0 = qa_dist(balls,i,j)
        scene = "；".join("球%d(%.1f,%.1f,%.1f)"%(k,b[0],b[1],b[2]) for k,b in enumerate(balls))
        q = "场景：%s\n问：%s"%(scene,q0)
        a = a0
    return {"q":q, "a":a}

def main():
    n = int(sys.argv[1]) if len(sys.argv)>1 else 3000
    out = sys.argv[2] if len(sys.argv)>2 else "/workspace/space_train.jsonl"
    rng = random.Random(2026)
    with open(out,"w",encoding="utf-8") as f:
        for k in range(n):
            s = make_sample(rng)
            f.write(json.dumps(s,ensure_ascii=False)+"\n")
    print("生成 %d 条 → %s"%(n,out))
    # 展示样例
    rng2 = random.Random(7)
    for k in range(2):
        s = make_sample(rng2)
        print("\n"+"="*50)
        print("[问]", s["q"][:400])
        print("[答]", s["a"][:300])

if __name__=="__main__":
    main()
