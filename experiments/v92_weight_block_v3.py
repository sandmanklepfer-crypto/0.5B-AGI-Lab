#!/usr/bin/env python3
"""
V92 权重分块 v3 — 类特有流形分块 (补空间法)
v90发现: PCA类内子空间分块 能量隔离弱(score~0.1, KL隔离比2.37x)
v91诊断: 知识/推理激活能量高度重叠(共享成分主导), 判别结构真实存在(LDA 5折0.9+)
         → 描述子空间≠特有子空间, PCA分块原理上失败

V92 正确思路 (类特有流形):
  知识特有子空间 = [推理训练流形(行空间)的正交补] ∩ [知识激活高能量区]
                 = 把知识激活投影到推理流形补空间后 PCA top-m
  推理特有子空间 = 对称 (知识流形补空间内 PCA 推理)
  原理: 训练集上 知识输入 ⊥ 推理特有通道, 推理输入 ⊥ 知识特有通道 → 修改天然隔离
        测试隔离度 = 流形外推稳健性 (40条/类是否足够覆盖真实流形)
步骤:
 1 采 down_proj 输入(4864) 末token激活 (层18/20/21/22)
 2 每层: 推理训练流形 U_rspan(行空间) → 知识补空间投影 PCA → U_kpure
        知识训练流形 U_kspan → 推理补空间投影 PCA → U_rpure
 3 指标(未见测试集): 通道强度 知识入U_kpure / 推理入U_kpure(=泄漏),
       响应隔离比 = 通道强度/泄漏; 对称推理通道
 4 恒等分块: W_k = W·P_kpure, W_r = W·P_rpure, W_rest = W-W_k-W_r
 5 整模型KL注入: Δk沿U_kpure第1方向注入W_k / Δr沿U_rpure第1方向注入W_r
       → 隔离比 = 本类KL/异类KL (期望 >>10, v90仅2.37)
"""
import copy
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
LAYERS = [18, 20, 21, 22]
M_SCAN = [4, 8, 16]

import importlib.util
spec = importlib.util.spec_from_file_location('v90', '/root/autodl-tmp/v90_weight_block_v2.py')
v90 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v90)
KT, RT, KTe, RTe = v90.KNOW_TRAIN, v90.REASON_TRAIN, v90.KNOW_TEST, v90.REASON_TEST

def collect(model, tok, texts, layers):
    bufs = {L: [] for L in layers}
    handles = []
    for L in layers:
        handles.append(model.model.layers[L].mlp.down_proj.register_forward_hook(
            lambda mod, inp, out, L=L: bufs[L].append(inp[0][0, -1].float().cpu())))
    with torch.inference_mode():
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            model(input_ids=ids)
    for h in handles:
        h.remove()
    return {L: torch.stack(bufs[L]).numpy().astype(np.float64) for L in layers}

def span_basis(Xc):
    """行空间正交基: Xc (n,d) 中心化 → (d,r) 正交列"""
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    r = min(Xc.shape[0] - 1, Xc.shape[1])
    return Vt[:r].T

def proj_out(X, U):
    """X 去掉 U 张成子空间的分量: X - (X U) U^T, 分步避免构造大矩阵"""
    return X - (X @ U) @ U.T

def pca_top(Xc, m):
    m = min(m, min(Xc.shape) - 1)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    return Vt[:m].T

def energy_ratio(X, U):
    p = (X @ U) @ U.T
    return np.mean(np.linalg.norm(p, axis=1) / np.maximum(np.linalg.norm(X, axis=1), 1e-9))

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    print('[V92] 类特有流形分块(补空间法) 层=%s m=%s' % (LAYERS, M_SCAN), flush=True)
    print('[V92] 采集激活...', flush=True)
    Ak = collect(model, tok, KT, LAYERS); Ar = collect(model, tok, RT, LAYERS)
    Tk = collect(model, tok, KTe, LAYERS); Tr = collect(model, tok, RTe, LAYERS)
    print('[V92] 采集完成', flush=True)

    rows = []
    best = None
    for L in LAYERS:
        Akc = Ak[L] - Ak[L].mean(0, keepdims=True)
        Arc = Ar[L] - Ar[L].mean(0, keepdims=True)
        Tkc = Tk[L] - Tk[L].mean(0, keepdims=True)
        Trc = Tr[L] - Tr[L].mean(0, keepdims=True)
        # 训练流形 (行空间基)
        U_kspan = span_basis(Akc)
        U_rspan = span_basis(Arc)
        # 类特有: 剔除对方流形后在补空间PCA
        Ak_pure = proj_out(Akc, U_rspan)
        Ar_pure = proj_out(Arc, U_kspan)
        for m in M_SCAN:
            Ukp = pca_top(Ak_pure, m)     # 知识特有 (⊥推理训练流形)
            Urp = pca_top(Ar_pure, m)     # 推理特有 (⊥知识训练流形)
            # 测试集: 通道强度/泄漏
            c_kk = energy_ratio(Tkc, Ukp)   # 知识测试入知识特有通道
            c_rk = energy_ratio(Trc, Ukp)   # 推理测试泄漏进知识通道
            c_rr = energy_ratio(Trc, Urp)
            c_kr = energy_ratio(Tkc, Urp)
            ratio_k = c_kk / max(c_rk, 1e-9)
            ratio_r = c_rr / max(c_kr, 1e-9)
            rows.append(dict(L=L, m=m, c_kk=c_kk, c_rk=c_rk, c_rr=c_rr, c_kr=c_kr,
                             ratio_k=ratio_k, ratio_r=ratio_r))
            print('L%2d m%2d  知识入U_kpure=%.3f 推理泄漏入=%.3f (比%.1f) | 推理入U_rpure=%.3f 知识泄漏入=%.3f (比%.1f)' % (
                L, m, c_kk, c_rk, ratio_k, c_rr, c_kr, ratio_r), flush=True)
            if best is None or (ratio_k * ratio_r) > (best['ratio_k'] * best['ratio_r']):
                best = dict(L=L, m=m, ratio_k=ratio_k, ratio_r=ratio_r,
                            Ukp=Ukp, Urp=Urp, Tkc=Tkc, Trc=Trc)
    Lb, mb = best['L'], best['m']
    print('\n[V92] 最优: 层%d m=%d 知识通道比=%.1f 推理通道比=%.1f' % (Lb, mb, best['ratio_k'], best['ratio_r']), flush=True)

    # ---- 恒等分块 + 存产物 ----
    WN = 'model.layers.%d.mlp.down_proj.weight' % Lb
    W = sd[WN].float().cpu().numpy().astype(np.float64)
    Ukp, Urp = best['Ukp'], best['Urp']
    # W_k = W @ Ukp @ Ukp.T (分步)
    Wk = ((W @ Ukp) @ Ukp.T)
    Wr = ((W @ Urp) @ Urp.T)
    Wrest = W - Wk - Wr
    err = np.abs(W - (Wk + Wr + Wrest)).max()
    print('[V92] 恒等分解误差 max=%.2e' % err, flush=True)
    torch.save({
        'layer': Lb, 'm': mb, 'Ukp': torch.tensor(Ukp), 'Urp': torch.tensor(Urp),
        'Wk': torch.tensor(Wk).half(), 'Wr': torch.tensor(Wr).half(),
        'Wrest': torch.tensor(Wrest).half(),
        'ratio_k': best['ratio_k'], 'ratio_r': best['ratio_r'],
        'rows': rows,
    }, '%s/v92_blocks.pt' % SAVE)
    print('[V92] 产物: %s/v92_blocks.pt' % SAVE, flush=True)

    # ---- 整模型 KL 注入 (最优层) ----
    print('\n[V92] KL注入验证 (层%d, 幅度0.12x||W||_F):' % Lb, flush=True)
    def last_logits(texts):
        out = []
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                out.append(model(input_ids=ids).logits[0, -1].float())
        return out
    def kl(p, q):
        lp = torch.log_softmax(p, -1); lq = torch.log_softmax(q, -1)
        return (torch.softmax(p, -1) * (lp - lq)).sum().item()
    def clean_patch(u_dir, seed=1):
        d = np.random.RandomState(seed).randn(896).astype(np.float64)
        d /= np.linalg.norm(d)
        u = u_dir.astype(np.float64); u /= np.linalg.norm(u)
        P = np.outer(d, u)
        return P / np.linalg.norm(P) * (np.linalg.norm(W) * 0.12)
    print('  基线...', flush=True)
    base_k = last_logits(KTe); base_r = last_logits(RTe)
    def inject(D, name):
        sd2 = copy.deepcopy(sd)
        sd2[WN] = torch.tensor(W + D).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)
        dk = np.mean([kl(base_k[i], last_logits([t])[0]) for i, t in enumerate(KTe)])
        dr = np.mean([kl(base_r[i], last_logits([t])[0]) for i, t in enumerate(RTe)])
        model.load_state_dict(sd, strict=True)
        print('  注入%s → 知识题KL=%.4f 推理题KL=%.4f  隔离比=%s' % (
            name, dk, dr, ('%.1f' % (dk/dr)) if dr > 1e-6 else 'inf'), flush=True)
        return dk, dr
    kl_kk, kl_kr = inject(clean_patch(Ukp[:, 0], 1), 'Δk→知识特有块')
    kl_rk, kl_rr = inject(clean_patch(Urp[:, 0], 2), 'Δr→推理特有块')
    ok_k = kl_kk > kl_kr * 5
    ok_r = kl_rr > kl_rk * 5
    print('\n[V92] 结论: 知识块隔离%s (比=%.1f) | 推理块隔离%s (比=%.1f)  [阈: >5x]' % (
        '✅' if ok_k else '❌', kl_kk/max(kl_kr,1e-9), '✅' if ok_r else '❌', kl_rr/max(kl_rk,1e-9)), flush=True)

if __name__ == '__main__':
    main()
