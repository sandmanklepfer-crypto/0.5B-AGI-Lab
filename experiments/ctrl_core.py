# -*- coding: utf-8 -*-
"""ctrl_core.py — v146/v147 的 numpy 重做 + 非线性分析
   ① 找「通用控制核」: 跨任务稳定激活的 gate 神经元 (v146 思路)
   ② 分析这些核的动力学: 混沌? 分形? 能用公式描述? (新增)
   ③ 量化: 这些核到底占多少、多重要
"""
import numpy as np, time, warnings, json
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪"%(time.time()-t0),flush=True)

# v146 的多任务集(原样)
TASKS=[
 '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
 '中国的首都是哪里？',
 '一只蜗牛白天爬3米晚上滑下2米，井深10米几天爬出？',
 '请写一段关于秋天的文字',
 '如果人可以删除记忆该不该有这能力？',
 '1+1等于几？',
 '鲸鱼属于什么动物？',
]

def gate_of(ids):
    """返回每层 gate_proj 输出(最后token): {L: (4864,)}"""
    w=M.w; out={L:None for L in range(24)}
    kv=[{"k":[],"v":[]} for _ in range(24)]
    x=None
    for pos,t in enumerate(ids):
        x=M.tok_emb[t].copy()
        for L in range(24):
            p="blk.%d."%L
            h=M.rms(x,w[p+"attn_norm.weight"])
            q=w[p+"attn_q.weight"]@h; k=w[p+"attn_k.weight"]@h; v=w[p+"attn_v.weight"]@h
            if p+"attn_q.bias" in w: q=q+w[p+"attn_q.bias"]
            if p+"attn_k.bias" in w: k=k+w[p+"attn_k.bias"]
            if p+"attn_v.bias" in w: v=v+w[p+"attn_v.bias"]
            q=M.rope(q.reshape(14,64),pos); k=M.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(w[p+"attn_output.weight"]@att)
            h2=M.rms(x,w[p+"ffn_norm.weight"])
            gpre=w[p+"ffn_gate.weight"]@h2          # ← gate 输出(非线性前)
            out[L]=gpre                              # 只留最后token
            u=w[p+"ffn_up.weight"]@h2
            x=x+(w[p+"ffn_down.weight"]@(M.silu(gpre)*u))
    return out

print("扫描 %d 个任务的 gate 激活..."%len(TASKS),flush=True)
G={L:[] for L in range(24)}
t0=time.time()
for ti,qt in enumerate(TASKS):
    ids=TK.encode(qt)
    g=gate_of(ids)
    for L in range(24): G[L].append(g[L])
    print("  任务%d (%d tok) 完成 %.0fs"%(ti+1,len(ids),time.time()-t0),flush=True)

# ============ ① 找通用控制核 (v146核心) ============
print("\n"+"="*66)
print("  ① 通用控制核扫描 (跨任务稳定激活的 gate 神经元)")
print("="*66)
report={}
for L in [0,6,12,18,23]:
    A=np.stack(G[L])                    # (7, 4864)
    mean=A.mean(0); std=A.std(0)
    absmean=np.abs(mean)
    # 通用控制核: 激活强 + 跨任务稳定
    ctrl = (absmean > np.percentile(absmean,90)) & (std < np.percentile(std,50))
    spec = (std > np.percentile(std,90))
    print("  第%2d层: 控制核 %4d个(%.1f%%) 特异单元 %4d个(%.1f%%) | 激活均值%.3f"%(
        L, ctrl.sum(), 100*ctrl.mean(), spec.sum(), 100*spec.mean(), absmean.mean()))
    report[L]={"ctrl":int(ctrl.sum()),"spec":int(spec.sum()),
               "ctrl_ratio":float(ctrl.mean())}

# ============ ② 控制核的动力学分析 ============
print("\n"+"="*66)
print("  ② 控制核的动力学 (非线性分析)")
print("="*66)
import nolds
L=12
A=np.stack(G[L])
mean=A.mean(0); std=A.std(0)
ctrl_idx=np.where((np.abs(mean)>np.percentile(np.abs(mean),90)) &
                  (std<np.percentile(std,50)))[0]
print("  第12层控制核: %d 个神经元"%len(ctrl_idx))
# 用控制核的激活序列(7个任务)做动力学分析
traj=A[:,ctrl_idx].mean(1)        # 控制核平均激活随任务变化
print("  控制核平均激活(7任务):", " ".join("%.2f"%v for v in traj))
print("  变异系数 = %.3f  (<0.3 说明真的稳定)"%(std[ctrl_idx].mean()/(np.abs(mean[ctrl_idx]).mean()+1e-9)))
# 全层控制核占比随层变化(深度剖面)
ratios=[report[L]["ctrl_ratio"] for L in [0,6,12,18,23]]
print("  控制核占比(层0→23):", " ".join("%.0f%%"%(100*r) for r in ratios))

# ============ ③ 门控的统计性质 ============
print("\n"+"="*66)
print("  ③ 门控(SiLU前)的统计性质 — 它是不是'非线性核心'?")
print("="*66)
for L in [0,12,23]:
    Z=A.reshape(-1)
    kurt=float(((Z-Z.mean())**4).mean()/(Z.std()**4+1e-12))
    neg=float((Z<0).mean()*100)
    # 幂律: 看大激活的分布
    s=np.sort(np.abs(Z))[::-1]
    top1=s[:len(s)//100].mean()/(np.abs(Z).mean()+1e-9)
    print("  第%2d层: 峰度%.2f 关断率%.0f%% 前1%%均值/整体=%.1f"%(L,kurt,neg,top1))
    report.setdefault("stats",{})[L]={"kurt":kurt,"neg":neg,"top1_ratio":float(top1)}

json.dump(report,open("/workspace/ctrl_report.json","w"),ensure_ascii=False,indent=1)
print("\n报告 → /workspace/ctrl_report.json")
print("总耗时 %.0fs"%(time.time()-t0))
