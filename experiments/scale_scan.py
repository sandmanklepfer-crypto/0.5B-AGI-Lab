# -*- coding: utf-8 -*-
"""scale_scan.py — 「多小才够」参数扫描
   任务: 中文自然语言 → 11 类指令
   对照: ① 纯规则(0参数) ② 极小线性模型(几十~几千参数) ③ 更大
"""
import numpy as np, random, re, time, hashlib
random.seed(7); np.random.seed(7)

MECHS=["roam","energy","reflect","consolidate","self_loop","meta_box"]
THETAS=["inject.eta","life.temp","energy.cap"]
WORDS=["量子计算","天气预报","股票","机器学习","北京","历史","算法"]
CMDS=["ls /sdcard","getprop","df -h","date"]
def build():
    I=[]
    for m in MECHS:
        I.append(("关掉 %s","OFF")); I.append(("禁用 %s","OFF"))
        I.append(("开启 %s","ON"));  I.append(("打开 %s","ON"))
    for th in THETAS:
        I.append(("把 %s 设为 0.6","SET")); I.append(("调 %s 到 0.6","SET"))
    for w in WORDS:
        I.append(("搜索 %s","SEARCH")); I.append(("查 %s","SEARCH"))
        I.append(("%s 是什么","ASK")); I.append(("讲讲 %s","ASK"))
    for c in CMDS:
        I.append(("执行 %s","SHELL")); I.append(("运行 %s","SHELL"))
    I+=[("看看世界","LOOK"),("新对话","CHAT"),("总结一下","CHAT"),("保存","CHAT"),
        ("自我诊断","DIAG"),("一键修复","DIAG"),("用大模型","MODEL")]
    return I
INTENTS=build(); KS=sorted(set(k for _,k in INTENTS)); K2I={k:i for i,k in enumerate(KS)}
def sample(n):
    out=[]
    for _ in range(n):
        tpl,kind=random.choice(INTENTS)
        if "%s" in tpl:
            pool = WORDS if kind in("SEARCH","ASK") else (CMDS if kind=="SHELL" else (MECHS if kind in("ON","OFF") else ["0.6"]))
            tpl=tpl.replace("%s", random.choice(pool))
        out.append((tpl,K2I[kind]))
    return out
tr=sample(2000); te=sample(800); C=len(KS)
print("类别 %d: %s"%(C,KS))

# ---- 特征: 字符 bigram 哈希到 D 维 ----
def feats(s,D):
    v=np.zeros(D,np.float32); s=s.lower()
    for i in range(len(s)-1):
        v[int(hashlib.md5(s[i:i+2].encode()).hexdigest()[:6],16)%D]+=1.0
    for c in s: v[int(hashlib.md5(("1"+c).encode()).hexdigest()[:6],16)%D]+=0.3
    n=np.linalg.norm(v); return v/n if n>0 else v
def mat(data,D): return np.array([feats(s,D) for s,_ in data]),np.array([y for _,y in data])

# ---- 0 参数: 纯规则 ----
RULES=[("搜索|搜一下|查 ","SEARCH"),("是什么|讲讲","ASK"),("执行|运行|shell","SHELL"),
       ("关掉|禁用|关闭","OFF"),("开启|启用|打开","ON"),("设为|改成|调到","SET"),
       ("世界","LOOK"),("新对话|总结|保存|存档","CHAT"),("诊断|体检|修复|优化","DIAG"),("大模型|切到","MODEL")]
def rule_acc():
    ok=0
    for s,y in te:
        for p,k in RULES:
            if re.search(p,s): ok+=(K2I[k]==y); break
        else: ok+=(K2I["CHAT"]==y)
    return ok/len(te)

# ---- 训练线性 ----
def train(D,steps=1500,lr=1.0):
    Xtr,Ytr=mat(tr,D); Xte,Yte=mat(te,D)
    W=np.zeros((D,C),np.float32); b=np.zeros(C,np.float32)
    for s in range(steps):
        i=random.randrange(len(Xtr)); x=Xtr[i]; y=Ytr[i]
        lg=x@W+b; lg-=lg.max(); p=np.exp(lg); p/=p.sum()
        g=p.copy(); g[y]-=1
        W-=lr*np.outer(x,g); b-=lr*g
    return float(((Xte@W+b).argmax(1)==Yte).mean()), D*C+C

print("\n%-24s %-14s %-10s %s"%("配置","参数量","占用","准确率"))
print("-"*66)
print("%-24s %-14s %-10s %.1f%%" % ("纯规则(if-else)", "0", "0 字节", 100*rule_acc()))
for D in [2, 4, 8, 16, 32, 64, 128, 256]:
    t0=time.time()
    acc,np_=train(D, steps=1200)
    by=np_*4
    u = "%d 字节"%by if by<1024 else ("%.1f KB"%(by/1024) if by<1048576 else "%.1f MB"%(by/1048576))
    print("%-24s %-14s %-10s %.1f%%  (%.0fs)"%(f"线性 D={D}", f"{np_:,}", u, 100*acc, time.time()-t0))
