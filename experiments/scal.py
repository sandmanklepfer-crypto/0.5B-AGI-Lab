# -*- coding: utf-8 -*-
"""scal.py — 参数量极限扫描: 到底多小才够?
   任务: 自然语言 → 指令(11类)
   模型: 字符n-gram哈希 → 线性softmax (最简单的可用模型)
   扫描: 从 0.0000001B(100参数) 到 0.002B(200万参数)
"""
import numpy as np, random, time, re
random.seed(7); np.random.seed(7)

# ---------- 数据 ----------
MECHS=["roam","energy","reflect","attractor","ignite","consolidate","self_loop","meta_box","reflect_up","gate","reservoir"]
THETAS=["energy.metabolism","inject.eta","life.temp","gate.cos_threshold","retrieval.topk",
        "reservoir.rho","self_edit.eta_min","reflect.mirror_weight","novelty.low","energy.cap"]
WORDS=["量子计算","天气预报","股票价格","机器学习","北京","历史","python","算法","数学","物理"]
CMDS=["ls /sdcard","getprop","df -h","ps -A","date","uptime","id","pwd"]
def build():
    I=[]
    for m in MECHS:
        for t in ["关掉 %s","禁用 %s","关闭 %s","停止 %s"]: I.append((t,"MECH_OFF"))
        for t in ["开启 %s","启用 %s","打开 %s","恢复 %s"]: I.append((t,"MECH_ON"))
    for th in THETAS:
        for t in ["把 %s 设为 0.6","%s 改成 0.6","调 %s 到 0.6"]: I.append((t,"THETA"))
    for w in WORDS:
        for t in ["搜索 %s","搜一下 %s","查 %s","帮我查 %s"]: I.append((t,"SEARCH"))
        for t in ["%s 是什么","介绍一下 %s","什么是 %s","讲讲 %s"]: I.append((t,"RECALL"))
    for c in CMDS:
        for t in ["执行 %s","运行 %s","终端：%s","shell %s"]: I.append((t,"SHELL"))
    for t in ["看看世界","观察场景","看世界","世界什么样"]: I.append((t,"WORLD"))
    for t in ["新对话","重新开始","开个新会话","总结一下","压缩上下文","保存","存档"]: I.append((t,"CHAT"))
    for t in ["自我诊断","体检","检查自己","诊断","一键修复","优化一下","修复"]: I.append((t,"MACRO"))
    for t in ["用大模型","换个聪明的","切到4b"]: I.append((t,"MODEL"))
    return I
INTENTS=build(); KS=sorted(set(k for _,k in INTENTS)); K2I={k:i for i,k in enumerate(KS)}
print("意图模板 %d 条 | 类别 %d 个"%(len(INTENTS),len(KS)))

def sample(n):
    out=[]
    for _ in range(n):
        tpl,kind=random.choice(INTENTS)
        if "%s" in tpl:
            pool = WORDS if kind in ("SEARCH","RECALL") else (CMDS if kind=="SHELL" else (MECHS if kind.startswith("MECH") else ["0.6"]))
            tpl=tpl.replace("%s", random.choice(pool))
        out.append((tpl, K2I[kind]))
    return out

# ---------- 特征: 字符2gram 哈希 ----------
def feats(s, D):
    v=np.zeros(D, np.float32)
    s=s.lower()
    for i in range(len(s)-1):
        h=hash(s[i:i+2])%D; v[h]+=1
    for c in s: v[hash(c+"1")%D]+=0.3
    n=np.linalg.norm(v)
    return v/n if n>0 else v
def make(data, D):
    X=np.array([feats(s,D) for s,_ in data]); Y=np.array([y for _,y in data])
    return X,Y

# ---------- 训练 ----------
def train(D, tr, te, steps=600, lr=0.5):
    Xtr,Ytr=make(tr,D); Xte,Yte=make(te,D)
    C=len(KS); W=np.zeros((D,C),np.float32); b=np.zeros(C,np.float32)
    nparam=D*C+C
    for s in range(steps):
        i=random.randrange(len(Xtr)); x=Xtr[i]; y=Ytr[i]
        lg=x@W+b; lg-=lg.max(); p=np.exp(lg); p/=p.sum()
        g=(p.copy()); g[y]-=1
        W-=lr*np.outer(x,g); b-=lr*g
    pred=(Xte@W+b).argmax(1)
    return float((pred==Yte).mean()), nparam

# ---------- 规则基线(0 参数) ----------
RULES=[("搜索|搜一下|帮我查|查 ","SEARCH"),("是什么|介绍一下|什么是|讲讲","RECALL"),
       ("执行|运行|终端|shell","SHELL"),("关掉|禁用|关闭|停止","MECH_OFF"),("开启|启用|打开|恢复","MECH_ON"),
       ("设为|改成|调到","THETA"),("看看世界|观察场景|看世界","WORLD"),("新对话|重新开始|总结|保存|存档","CHAT"),
       ("诊断|体检|修复|优化","MACRO"),("大模型|换个聪明|切到","MODEL")]
def rule_acc(te):
    ok=0
    for s,y in te:
        for pat,k in RULES:
            if re.search(pat,s): ok += (K2I[k]==y); break
        else: ok += (K2I["CHAT"]==y)
    return ok/len(te)

tr=sample(3000); te=sample(1000)
print("\n规则基线(0参数): %.1f%%"% (100*rule_acc(te)))
print("\n%-22s %-10s %-8s %s"%("设定位宽 D","参数量","占用","测试准确率"))
print("-"*62)
for D in [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]:
    t0=time.time()
    acc,nparam=train(D,tr,te,steps=800)
    size = nparam*4/1024
    unit = "%.0f 字节"%(nparam*4) if nparam*4<1024 else ("%.1f KB"%size if size<1024 else "%.1f MB"%(size/1024))
    tag = " ← 0.0000001B" if nparam<=1100 and nparam>=80 else ""
    print("%-22s %-12s %-8s %.1f%%  (%.0fs)%s"%(f"D={D}", f"{nparam:,}", unit, 100*acc, time.time()-t0, tag))
