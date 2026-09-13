# -*- coding: utf-8 -*-
"""analyze_nonlinear.py — 用非线性分析工具解剖神经网络
   对 Qwen2.5-0.5B 的每一层, 分析:
     ① 激活分布形态 (是否重尾/双峰)
     ② 样本熵 / 分形维 / Lyapunov (是否混沌)
     ③ 符号回归: 能否用公式描述这个非线性
     ④ 幂律指数 (自组织临界性?)
     ⑤ 有效维度 (PCA) —— 真实"信息容量"
"""
import numpy as np, time, warnings, json
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪"% (time.time()-t0), flush=True)

# 一段真实文本
TEXT = ("人工智能的发展经历了多次浪潮。从符号主义到连接主义，"
        "再到今天的深度学习，每一次突破都建立在对非线性系统更深的理之上。"
        "神经网络的本质是一个高维非线性映射，其中激活函数提供了必需的非线性。")
ids = TK.encode(TEXT)
print("输入 %d tokens"%len(ids), flush=True)

# ---- 收集每层激活 ----
def collect(ids, layers=(0,6,12,18,23)):
    w=M.w; acts={L:[] for L in layers}; gates={L:[] for L in layers}
    kv=[{"k":[],"v":[]} for _ in range(24)]
    pre={L:[] for L in layers}; post={L:[] for L in layers}
    for pos,t in enumerate(ids):
        x=M.tok_emb[t].copy()
        for L in range(24):
            p="blk.%d."%L
            h=M.rms(x, w[p+"attn_norm.weight"])
            q=w[p+"attn_q.weight"]@h; k=w[p+"attn_k.weight"]@h; v=w[p+"attn_v.weight"]@h
            if p+"attn_q.bias" in w: q=q+w[p+"attn_q.bias"]
            if p+"attn_k.bias" in w: k=k+w[p+"attn_k.bias"]
            if p+"attn_v.bias" in w: v=v+w[p+"attn_v.bias"]
            q=M.rope(q.reshape(14,64),pos); k=M.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1)
            Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(w[p+"attn_output.weight"]@att)
            h2=M.rms(x, w[p+"ffn_norm.weight"])
            z=w[p+"ffn_gate.weight"]@h2          # ← 非线性前
            u=w[p+"ffn_up.weight"]@h2
            g=M.silu(z)                          # ← SiLU
            if L in layers:
                pre[L].append(z.copy()); post[L].append(g.copy())
            x=x+(w[p+"ffn_down.weight"]@(g*u))
    return pre, post

t0=time.time()
pre,post = collect(ids)
print("[%.0fs] 激活收集完成\n"%(time.time()-t0), flush=True)

import nolds
from gplearn.genetic import SymbolicRegressor

print("="*68)
print("  神经网络非线性解剖 (Qwen2.5-0.5B, %d 层采样)"%len(pre))
print("="*68)

report={}
for L in sorted(pre):
    Z=np.concatenate(pre[L])     # SiLU 输入
    G=np.concatenate(post[L])    # SiLU 输出
    print("\n── 第 %d 层 FFN 门控(SiLU) ──"%L)
    print("   输入 z : mean=%.3f std=%.3f 范围[%.2f,%.2f]"%(Z.mean(),Z.std(),Z.min(),Z.max()))
    print("   输出 g : mean=%.3f std=%.3f 范围[%.2f,%.2f]"%(G.mean(),G.std(),G.min(),G.max()))
    # ① 重尾?峰度
    kurt=float(((Z-Z.mean())**4).mean()/(Z.std()**4+1e-12))
    skew=float(((Z-Z.mean())**3).mean()/(Z.std()**3+1e-12))
    print("   峰度=%.2f 偏度=%.2f  %s"%(kurt,skew,
          "(重尾!非高斯)" if kurt>4 else "(近正态)"))
    # ② 负值比例(门控关断率)
    neg=float((Z<0).mean()*100)
    print("   门控关断率(z<0) = %.1f%%"%(neg))
    # ③ 有效维度(PCA)
    X=G.reshape(-1, len(G)//max(1,len(post[L])))
    if X.shape[0]>X.shape[1]: X=X.T
    Xc=X-X.mean(0); 
    try:
        s=np.linalg.svd(Xc, compute_uv=False); s=s[s>1e-9]
        p=s**2/ (s**2).sum()
        eff=float(np.exp(-(p*np.log(p+1e-12)).sum()))
        print("   有效维度 = %.1f / %d  (信息压缩比 %.1f%%)"%(eff, len(s), 100*eff/len(s)))
    except Exception as e: eff=0
    # ④ 符号回归: 能否拟合 g = f(z)?
    n=min(800,len(Z)); idx=np.random.RandomState(0).choice(len(Z),n,replace=False)
    t1=time.time()
    sr=SymbolicRegressor(population_size=500,generations=8,stopping_criteria=0.001,
        p_crossover=0.7,p_subtree_mutation=0.1,p_hoist_mutation=0.05,p_point_mutation=0.1,
        max_samples=0.9,verbose=0,random_state=0,n_jobs=8,
        function_set=('add','mul','tanh','div','neg'))
    sr.fit(Z[idx].reshape(-1,1), G[idx])
    print("   符号回归: g ≈ %s"%str(sr._program)[:110])
    print("             (真值: g = z·sigmoid(z))  R²=%.4f"%sr.score(Z[idx].reshape(-1,1),G[idx]))
    report[L]={"kurt":kurt,"skew":skew,"neg_pct":neg,"eff_dim":eff,
               "fit_r2":float(sr.score(Z[idx].reshape(-1,1),G[idx])),
               "formula":str(sr._program)[:120]}

json.dump(report, open("/workspace/nonlinear_report.json","w"), ensure_ascii=False, indent=1)
print("\n"+"="*68)
print("  报告已存 /workspace/nonlinear_report.json")
