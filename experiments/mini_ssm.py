# -*- coding: utf-8 -*-
"""mini_ssm.py — 微型 SSM 学「指令解析」实验
   问题: 一个几十万参数的小核, 能不能学会把自然语言 → 结构化指令?
   意义: 若能, agent 的 80% 请求不用惊动 4B → 秒回 + 省电
   架构: 对角 SSM (Mamba 简化版) —— 状态恒定, 手机友好
   数据: 程序化生成(有确定真值, 不用大模型)
"""
import numpy as np, random, time, re

random.seed(7); np.random.seed(7)

# ============ ① 指令集 + 自然语言变体(程序化生成真值) ============
MECHS = ["roam","energy","reflect","attractor","ignite","consolidate","self_loop","meta_box","reflect_up"]
THETAS = ["energy.metabolism","inject.eta","life.temp","gate.cos_threshold","retrieval.topk",
          "reservoir.rho","self_edit.eta_min","reflect.mirror_weight","novelty.low"]
TOOLS = ["search","shell","fetch"]
WORDS = ["量子计算","天气预报","股票价格","机器学习","北京","历史","python","算法","数学"]
CMDS  = ["ls /sdcard","getprop","df -h","ps -A","date","uptime"]

# 意图 → (模板列表, 目标指令)
def build_intents():
    intents=[]; kinds=[]
    for m in MECHS:
        intents.append((["关掉 %s","禁用 %s","关闭 %s","%s 关掉"][0:4], "M:%s=0"%m, "MECH_OFF"))
        intents.append((["开启 %s","启用 %s","打开 %s"], "M:%s=1"%m, "MECH_ON"))
    for t in THETAS:
        v = "0.0002" if "metab" in t else "0.6"
        intents.append((["把 %s 设为 %s","%s 改成 %s","调 %s 到 %s"], "T:%s=%s"%(t,v), "THETA"))
    for w in WORDS:
        intents.append((["搜索 %s","搜一下 %s","查 %s","帮我查 %s"], "X:search:%s"%w, "SEARCH"))
        intents.append((["%s 是什么","介绍一下 %s","什么是 %s"], "R:recall:%s"%w, "RECALL"))
    for c in CMDS:
        intents.append((["执行 %s","运行 %s","终端：%s"], "X:shell:%s"%c, "SHELL"))
    intents.append((["看看世界","观察场景","看世界"], "W:look", "WORLD"))
    intents.append((["演化 5 步","前进 3 步","走 10 步"], "W:step:5", "WORLD_STEP"))
    intents.append((["新对话","重新开始"], "C:new", "CHAT"))
    intents.append((["总结一下","压缩上下文"], "C:sum", "CHAT"))
    intents.append((["保存","存档"], "C:save", "CHAT"))
    intents.append((["自我诊断","体检","检查自己"], "A:diag", "MACRO"))
    intents.append((["一键修复","优化一下","修一下"], "A:fix", "MACRO"))
    intents.append((["用大模型","换个聪明的"], "G:switch:4b", "MODEL"))
    return intents

INTENTS = build_intents()
KIND_SET = sorted(set(k for _,_,k in INTENTS))
KIND2ID = {k:i for i,k in enumerate(KIND_SET)}
print("意图池: %d 条, %d 类"%(len(INTENTS), len(KIND_SET)))
print("类别:", KIND_SET)

# ============ ② 字符级编码 ============
CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:=/ -_：中文"
VOCAB = list("abcdefghijklmnopqrstuvwxyz0123456789.:=/ -_") + ["<unk>","<pad>"]
C2I = {c:i for i,c in enumerate(VOCAB)}
PAD = C2I["<pad>"]; UNK = C2I["<unk>"]
MAXLEN = 40

def encode(s):
    ids=[C2I.get(c, UNK) for c in s[:MAXLEN]]
    while len(ids)<MAXLEN: ids.append(PAD)
    return np.array(ids, np.int32)

def make_batch(n):
    X=[]; Y=[]; 
    for _ in range(n):
        tpl, target, kind = random.choice(INTENTS)
        s = random.choice(tpl).replace("：",":")
        if "%s" in s and s.count("%s")==2:
            s = s.replace("%s", random.choice(WORDS) if "search" in target else "0.6", 1)
        X.append(encode(s)); Y.append(KIND2ID[kind])
    return np.array(X, np.int32), np.array(Y, np.int64)

# ============ ③ 微型 SSM (对角线性 + 门控, numpy) ============
class MiniSSM:
    """h_t = a⊙h_{t-1} + b⊙x_t ;  y = mean(h) → 分类
       a 用 sigmoid 保证稳定, b 用输入投影"""
    def __init__(self, vocab=len(VOCAB), d=32, H=64, ncls=len(KIND_SET), seed=0):
        r=np.random.RandomState(seed)
        self.d, self.H, self.V, self.C = d, H, vocab, ncls
        self.E  = r.randn(vocab, d)*0.3                       # 嵌入
        self.Wb = r.randn(H, d)/np.sqrt(d)                    # b = tanh(Wb x)
        self.ba = r.randn(H)*0.1                              # a = sigmoid(ba + ...)
        self.Wa = r.randn(H, d)/np.sqrt(d)
        self.Wo = r.randn(ncls, H)/np.sqrt(H)
        self.bo = np.zeros(ncls)
        self.nparam = sum(p.size for p in [self.E,self.Wb,self.ba,self.Wa,self.Wo,self.bo])
    def forward(self, X, cache=False):
        B,T = X.shape; H=self.H
        x = self.E[X]                                          # (B,T,d)
        b = np.tanh(x @ self.Wb.T)                             # (B,T,H)
        a = 1/(1+np.exp(-(self.Wa @ x.transpose(0,2,1)).transpose(0,2,1) - self.ba))  # (B,T,H)
        h = np.zeros((B,H), np.float32); hs=[]
        for t in range(T):
            h = a[:,t,:]*h + (1-a[:,t,:])*b[:,t,:]
            hs.append(h.copy())
        HS = np.stack(hs, 1)                                   # (B,T,H)
        pool = HS.mean(1)                                       # 平均池化
        logits = pool @ self.Wo.T + self.bo
        if cache: return logits, dict(HS=HS, a=a, b=b, x=x, pool=pool)
        return logits
    def loss_grad(self, X, Y, lr=0.01):
        B,T = X.shape; H=self.H
        logits, c = self.forward(X, cache=True)
        lg = logits - logits.max(1, keepdims=True)
        p = np.exp(lg); p /= p.sum(1, keepdims=True)
        loss = -np.log(p[np.arange(B), Y] + 1e-12).mean()
        dlog = p.copy(); dlog[np.arange(B), Y] -= 1; dlog /= B
        gWo = dlog.T @ c["pool"]; gbo = dlog.sum(0)
        dpool = dlog @ self.Wo                                  # (B,H)
        dHS = np.repeat((dpool/T)[:,None,:], T, axis=1)         # 均分到每步
        # 反向穿过 SSM (简化: 只回传 b 和 a 的直接影响, 不做完整 BPTT)
        gWb=np.zeros_like(self.Wb); gWa=np.zeros_like(self.Wa); gba=np.zeros_like(self.ba); gE=np.zeros_like(self.E)
        dh_next = np.zeros((B,H), np.float32)
        for t in range(T-1,-1,-1):
            dh = dHS[:,t,:] + dh_next
            da = dh*(c["b"][:,t,:]-db_prev if False else 0)      # 占位
            # 真正的 ∂h_t/∂a = (h_{t-1} - b_t), ∂h_t/∂b = (1-a_t)
            hprev = c["HS"][:,t-1,:] if t>0 else np.zeros((B,H),np.float32)
            da = dh*(hprev - c["b"][:,t,:])
            db = dh*(1-c["a"][:,t,:])
            x_t = c["x"][:,t,:]                                  # (B,d)
            gWb += db.T @ x_t
            gWa += da.T @ x_t
            gba += da.sum(0)
            gE[X[:,t]] += db @ self.Wb + da @ self.Wa
            dh_next = dh*c["a"][:,t,:]
        # 更新
        for P,G in ((self.Wo,gWo),(self.bo,gbo),(self.Wb,gWb),(self.Wa,gWa),(self.ba,gba),(self.E,gE)):
            np.clip(G,-1,1,out=G); P -= lr*G
        return loss
    def acc(self, X, Y):
        return float((self.forward(X).argmax(1)==Y).mean())

# ============ ④ 训练 + 评估 ============
def main():
    t0=time.time()
    m = MiniSSM()
    print("\n微型SSM 参数量: %s (%.2f MB fp32)"%(f"{m.nparam:,}", m.nparam*4/1048576))
    Xte, Yte = make_batch(600)
    print("训练前准确率: %.1f%%"%(100*m.acc(Xte,Yte)))
    print("\n训练中...")
    lr=0.05
    for step in range(1, 901):
        Xb, Yb = make_batch(64)
        loss = m.loss_grad(Xb, Yb, lr)
        if step % 150 == 0:
            a = m.acc(Xte, Yte)
            print("  step %4d  loss=%.4f  测试准确率=%.1f%%  (%.0fs)"%(step, loss, 100*a, time.time()-t0), flush=True)
    print("\n最终: %.1f%%"%(100*m.acc(Xte,Yte)))
    # 逐类准确率
    pred = m.forward(Xte).argmax(1)
    print("\n各类准确率:")
    for k,i in KIND2ID.items():
        mask = Yte==i
        if mask.sum(): print("   %-12s %5.1f%% (%d样本)"%(k, 100*(pred[mask]==i).mean(), mask.sum()))
    print("\n耗时 %.0fs"%(time.time()-t0))

if __name__=="__main__":
    main()
