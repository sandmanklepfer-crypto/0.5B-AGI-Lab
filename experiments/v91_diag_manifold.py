#!/usr/bin/env python3
"""
V91 诊断 — 知识/推理流形分块可行性定位 (v90隔离弱之后, 先诊断再定v92)
v90发现: down_proj输入(4864)上 PCA top-24 子空间能量隔离弱(score~0.1, 交叉20-30%),
        KL注入隔离比仅2.37x → 通道不够"干净"
V91 问题:
 Q1 哪个空间?  A. 层输出残差流(896, v85 LDA在此成功)  B. down_proj输入(4864)
 Q2 哪些层?    {12,18,20,21,22,23}
 Q3 m多大?     {8,16,24,32}
 Q4 真实判别上限? LDA 5折交叉验证(压缩空间), 防v85式训练集过拟合
指标(全部用未见测试集):
  A 类内捕获: 知识测试激活在 U_k(top-m) 的能量占比 (高=描述力强)
  B 交叉泄漏: 知识测试激活在 U_r 的能量占比 (低=好)
  C 特异性:   对U_k每个方向 v: spec = E_k(v)/(E_k(v)+E_r(v)) 平均 (0.5=无区分,1=纯知识)
  D 判别上限: 两类PCA子空间(64维联合)内 LDA 5折×3次 平均acc
"""
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYERS = [12, 18, 20, 21, 22, 23]
M_SCAN = [8, 16, 24, 32]

# 复用 v90 任务集 (通过 import 或内嵌? 服务器v90已上传, 直接 import 它的数据部分)
import importlib.util, sys
spec = importlib.util.spec_from_file_location('v90', '/root/autodl-tmp/v90_weight_block_v2.py')
v90 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v90)   # 只取 KNOW_TRAIN 等常量(不执行main)
KT, RT, KTe, RTe = v90.KNOW_TRAIN, v90.REASON_TRAIN, v90.KNOW_TEST, v90.REASON_TEST

def collect(model, tok, texts):
    """返回 dict: L -> {hs: (n,896), mlp_in: (n,4864)}"""
    bufs = {L: {'hs': [], 'mlp_in': []} for L in LAYERS}
    handles = []
    def fac(L):
        def h(mod, inp, out):
            bufs[L]['mlp_in'].append(inp[0][0, -1].float().cpu())
        return h
    for L in LAYERS:
        handles.append(model.model.layers[L].mlp.down_proj.register_forward_hook(fac(L)))
    with torch.inference_mode():
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            out = model(input_ids=ids, output_hidden_states=True)
            for L in LAYERS:
                bufs[L]['hs'].append(out.hidden_states[L + 1][0, -1].float().cpu())  # 层L输出 896
    for h in handles:
        h.remove()
    return {L: {k: torch.stack(v).numpy().astype(np.float64) for k, v in bufs[L].items()} for L in LAYERS}

def pca_top(Xc, m):
    m = min(m, min(Xc.shape) - 1)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    return Vt[:m].T

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    print('[V91] 采集: 训练%d+%d 测试%d+%d × 层%s × 2空间...' % (len(KT), len(RT), len(KTe), len(RTe), LAYERS), flush=True)
    Dk_tr = collect(model, tok, KT); Dr_tr = collect(model, tok, RT)
    Dk_te = collect(model, tok, KTe); Dr_te = collect(model, tok, RTe)
    print('[V91] 采集完成', flush=True)

    SPACES = [('层输出896', 'hs'), ('mlp输入4864', 'mlp_in')]
    print('\n=== 测试集能量捕获/泄漏表 ===', flush=True)
    print('空间      层  m  知识入U_k 知识入U_r 推理入U_r 推理入U_k  特异度_k 特异度_r  判别acc(5折)', flush=True)
    summary = []
    for sname, skey in SPACES:
        for L in LAYERS:
            Ak = Dk_tr[L][skey]; Ar = Dr_tr[L][skey]   # (40,d)
            Tk = Dk_te[L][skey]; Tr = Dr_te[L][skey]   # (20,d)
            d = Ak.shape[1]
            mu = np.concatenate([Ak, Ar], 0).mean(0, keepdims=True)
            Akc, Arc = Ak - mu, Ar - mu
            Tkc, Trc = Tk - mu, Tr - mu
            for m in M_SCAN:
                Uk = pca_top(Akc, m); Ur = pca_top(Arc, m)
                # A/B: 能量占比
                def eratio(Xc, U):
                    p = Xc @ (U @ U.T)
                    return np.mean(np.linalg.norm(p, axis=1) / np.maximum(np.linalg.norm(Xc, axis=1), 1e-9))
                e_kk, e_kr = eratio(Tkc, Uk), eratio(Tkc, Ur)
                e_rr, e_rk = eratio(Trc, Ur), eratio(Trc, Uk)
                # C: 特异性 (方向级: 知识能量份额)
                def spec(U):
                    ek = np.linalg.norm(Tkc @ U, axis=0) ** 2
                    er = np.linalg.norm(Trc @ U, axis=0) ** 2
                    return float(np.mean(ek / (ek + er + 1e-9)))
                sk, sr = spec(Uk), spec(Ur)
                # D: 联合64维空间内 LDA 5折×3
                Fk = np.hstack([Tkc @ Uk, Tkc @ Ur]); Fr = np.hstack([Trc @ Ur, Trc @ Uk])
                accs = []
                for rep in range(3):
                    idx = np.random.RandomState(rep).permutation(20)
                    for f in range(5):
                        va = idx[f::5]
                        tr = np.setdiff1d(np.arange(20), va)
                        Xk_tr, Xk_va = Fk[tr], Fk[va]
                        Xr_tr, Xr_va = Fr[tr], Fr[va]
                        mk, mr = Xk_tr.mean(0), Xr_tr.mean(0)
                        Sw = np.cov(Xk_tr.T) + np.cov(Xr_tr.T) + 1e-6 * np.eye(Fk.shape[1])
                        try:
                            w = np.linalg.solve(Sw, mk - mr)
                        except np.linalg.LinAlgError:
                            w = mk - mr
                        pk, pr = Xk_va @ w, Xr_va @ w
                        ck = np.mean(pk > np.mean([pk.mean(), pr.mean()]))
                        # 简化: 最近质心分类
                        c = 0
                        for x in Xk_va:
                            if abs(x @ w - mk @ w) < abs(x @ w - mr @ w): c += 1
                        for x in Xr_va:
                            if abs(x @ w - mr @ w) < abs(x @ w - mk @ w): c += 1
                        accs.append(c / (2 * len(va)))
                dacc = float(np.mean(accs))
                flag = '←候选' if (e_kk - e_kr + e_rr - e_rk) > 0.6 and dacc > 0.9 else ''
                print('%s L%2d %2d  %.2f    %.2f    %.2f    %.2f    %.2f    %.2f    %.2f   %s' % (
                    sname, L, m, e_kk, e_kr, e_rr, e_rk, sk, sr, dacc, flag), flush=True)
                summary.append(dict(space=sname, L=L, m=m, score=e_kk - e_kr + e_rr - e_rk, dacc=dacc))
    summary.sort(key=lambda r: -r['score'])
    print('\n[V91] 能量隔离score TOP5:', flush=True)
    for r in summary[:5]:
        print('  %s L%d m=%d score=%.2f 判别acc=%.2f' % (r['space'], r['L'], r['m'], r['score'], r['dacc']), flush=True)

if __name__ == '__main__':
    main()
