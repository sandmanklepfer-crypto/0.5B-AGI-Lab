# -*- coding: utf-8 -*-
"""手动LoRA训练: 去拒绝 + 「先形式验证→不行再自推」行为"""
import sys, types, importlib.machinery as _m, time, random, json
import torch, torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
from sympy import symbols, sin, cos, tan, diff, integrate, solve, simplify

t0=time.time()
MODE=sys.argv[1] if len(sys.argv)>1 else "speed"   # speed | train
OUT="/root/distill_agent_v1"
BASE="/root/distill_calc_v1"

# ============ 训练数据: 行为协议 ============
def make_data(n=500):
    D=[]
    # ① 算术 (先验证 → 调用工具)
    for _ in range(n//5):
        a,b=random.randint(11,99),random.randint(2,12)
        D.append((f"计算：{a}乘以{b}等于多少？",
                  f"我先尝试形式验证。这可以形式化。答案 = ⟨calc⟩{a}*{b}⟨/calc⟩"))
    for _ in range(n//8):
        a,b=random.randint(20,99),random.randint(2,40)
        D.append((f"计算 {a}+{b} 等于多少？",
                  f"我先尝试形式验证。这可以形式化。答案 = ⟨calc⟩{a}+{b}⟨/calc⟩"))
    # ② 代数
    for _ in range(n//8):
        a=random.randint(2,9); x=random.randint(2,20)
        D.append((f"解方程 {a}x={a*x}，求x。",
                  f"我先尝试形式验证。这可以形式化。答案 = ⟨calc⟩{a*x}/{a}⟨/calc⟩"))
    # ③ 求导 (形式化 → 输出 sympy 调用)
    for _ in range(n//6):
        k=random.randint(2,5); f=f"x**{k}"
        D.append((f"求 {f} 对 x 的导数。",
                  f"我先尝试形式验证。求导可以形式化：diff({f}, x)"))
    for _ in range(n//10):
        D.append((f"求 sin(x) 对 x 的导数。","我先尝试形式验证。求导可以形式化：diff(sin(x), x)"))
        D.append((f"求 cos(x) 对 x 的导数。","我先尝试形式验证。求导可以形式化：diff(cos(x), x)"))
    # ④ 无法形式化 → 自己推理
    QUAL=[
     ("为什么天是蓝色的？","太阳光穿过大气时被空气分子散射，蓝光波长短散射更强，所以天空呈蓝色。"),
     ("为什么会有白天和黑夜？","地球自转使不同区域轮流朝向太阳，朝向太阳处是白天，背向处是黑夜。"),
     ("水为什么会结冰？","温度降到冰点时水分子运动减慢，有序排列成晶格，就从液态变成固态冰。"),
     ("介绍一下你自己。","我是一个小型语言模型，擅长把问题转成形式化工具调用，也能做简单的定性推理。"),
     ("什么是人工智能？","人工智能是用计算机模拟人类智能的技术，包括学习、推理、感知等方面。"),
     ("为什么需要睡觉？","睡眠能修复身体、巩固记忆、清理代谢废物，是维持正常生理功能的必要条件。"),
    ]
    for _ in range(n//10):
        for q,a in QUAL:
            D.append((q, f"我先尝试形式验证。这个问题无法用形式工具验证。那么我尝试自己推理：{a}"))
    random.shuffle(D); return D

# ============ 模型 + 手动 LoRA ============
tok=AutoTokenizer.from_pretrained(BASE); tok.pad_token=tok.eos_token
md=AutoModelForCausalLM.from_pretrained(BASE,dtype=torch.float32)
print(f"[{time.time()-t0:.0f}s] 模型就绪 层数={len(md.model.layers)}",flush=True)
R=8
class LoRALin(nn.Module):
    def __init__(s,base,r=R,alpha=16):
        super().__init__(); s.base=base; s.scale=alpha/r
        for p in base.parameters(): p.requires_grad=False
        s.A=nn.Parameter(torch.randn(r,base.in_features)*0.01)
        s.B=nn.Parameter(torch.zeros(base.out_features,r))
    def forward(s,x): return s.base(x)+(x@s.A.T@s.B.T)*s.scale
for l in md.model.layers:
    l.self_attn.q_proj=LoRALin(l.self_attn.q_proj)
    l.self_attn.v_proj=LoRALin(l.self_attn.v_proj)
P=[p for p in md.parameters() if p.requires_grad]
print(f"[{time.time()-t0:.0f}s] LoRA 可训练 {sum(p.numel() for p in P):,} 参数",flush=True)

def batch_loss(bs):
    ins=[q for q,_ in bs]; outs=[a for _,a in bs]
    ti=tok(ins,return_tensors="pt",padding=True,truncation=True,max_length=96)
    ta=tok(outs,return_tensors="pt",padding=True,truncation=True,max_length=96)
    full=torch.cat([ti["input_ids"],ta["input_ids"]],dim=1)
    am=torch.cat([ti["attention_mask"],ta["attention_mask"]],dim=1)
    lab=full.clone(); lab[:,:ti["input_ids"].shape[1]]=-100
    return md(full,attention_mask=am,labels=lab).loss

if MODE=="speed":
    md.train(); opt=torch.optim.AdamW(P,lr=2e-4)
    D=make_data(200)[:4]
    t1=time.time(); loss=batch_loss(D); loss.backward(); opt.step(); opt.zero_grad()
    dt=time.time()-t1
    print(f"单步 {dt:.2f}s  loss={loss.item():.3f}",flush=True)
    print(f"→ 500样本/bs4=125步 x2轮 = 250步 → {dt*250/60:.1f}分钟",flush=True)
else:
    D=make_data(500)
    print(f"[{time.time()-t0:.0f}s] 数据 {len(D)} 条",flush=True)
    opt=torch.optim.AdamW(P,lr=3e-4)
    md.train()
    for ep in range(1,3):
        random.shuffle(D); tot=0
        for i in range(0,len(D),4):
            loss=batch_loss(D[i:i+4]); opt.zero_grad(); loss.backward(); opt.step()
            tot+=loss.item()
        print(f"[ep{ep}] loss={tot/(len(D)//4):.4f}  {time.time()-t0:.0f}s",flush=True)
    md.save_pretrained(OUT); tok.save_pretrained(OUT)
    print(f"[save] {OUT}",flush=True)
print(f"总 {time.time()-t0:.0f}s",flush=True)
print("TRAIN_DONE")
