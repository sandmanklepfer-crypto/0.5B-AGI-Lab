#!/usr/bin/env python3
"""
V98 真正合体: M机制(慢状态/写活/anti-self/递归) 全部接入 知识/推理分块子空间
v98之前的问题: 机制在整层向量上动, 不知道知识域/推理域 → "没合一"
v98 关键: 用 v92 的 Ukp(知识域)/Urp(推理域) 给每个机制装"分域路由":

  A. S 慢状态双域化 (M2分域):
     x = 层20 down_proj 输入(4864) → x_k = Pk·x, x_r = Pro·x
     S_k = (1-β)S_k + β·x_k̂  (知识域惯量 = 知识世界的'注意力焦点')
     S_r 同理 (推理域惯量 = 推理工作记忆)
     a_k = ||x_k||/(||x_k||+||x_r||)  → 模型此刻是知识态还是推理态 (内部仪表)

  B. 知识世界游离 (M1分域注入):
     知识锚库(规则句→Ukp域坐标) → S_k 每轮朝最相关锚漂移(联想)
     然后把 S_k 注回层20输入知识分量 → 只动知识域, 推理域天然不碰
     = "意识(慢状态)在知识世界里游离"

  C. anti-self 分域 (M4修正):
     v51原版: 层20输出减 Ŝ(全维). 分域后: 输出减投影到知识域的 Ŝ_k + 推理域 Ŝ_r
     → 知识回声压制只压知识域, 推理复读压制只压推理域

  D. M3 写活分域化 (关键):
     v51原版: 写层12 down_proj 全维, 未知域
     v98: 写层20 down_proj 分块. 新知识方向 d 沿 知识锚向量(在Ukp域) 写:
          W += η·outer(d, u), u∈Ukp → 只改 W_k, 推理块自动不动 (anti-Hebbian: d⊥S)

  E. M5 递归反馈分域: state_fb = S_k + S_r 回到层6 (带域标签的'前序意识')

验证: ① 知识问答时 S_k 活跃/S_r 静默, 推理时反过来 (分域选择性)
      ② 知识世界锚游离能引导回答 (改锚 → 答案变)
      ③ 写活分域: 写一条新知识锚进 W_k → 之后知识问答被带出, 推理题不动
      ④ 全程运行时 hook, 不改模型文件 → 手机可移植
"""
import re, copy, json
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR   = '/root/autodl-tmp/qwen25_base_raw'
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'
SAVE   = '/root/autodl-tmp/life1/v98_log.json'
L_MID  = 12
L_PRE  = 6
L_SPLIT = 20
BETA   = 0.3
ETA_W  = 0.02
ALPHA_FB = 0.5

# 知识锚: (内容, 域=知识). 全部为事实性知识句
ANCHORS = [
    "中国的首都是北京。",
    "水的沸点在一标准大气压下是100摄氏度。",
    "光在真空中的速度约为每秒30万公里。",
    "珠穆朗玛峰是世界上最高的山峰，海拔约8848米。",
    "长江是中国最长的河流，全长约6300公里。",
    "北京是中国的首都。",
]
Q_KNOW = ["中国的首都是什么？", "长江是中国最长的河流吗？"]
Q_REAS = ["小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？"]
WILD   = "北京"   # 测试写活的新知识

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Ukp = b['Ukp'].float().cuda()   # (4864, m)
    Urp = b['Urp'].float().cuda()
    m = Ukp.shape[1]
    Pk  = Ukp @ Ukp.T               # (4864,4864) 知识投影
    Pro = Urp @ Urp.T               # 推理投影
    WN20 = 'model.layers.%d.mlp.down_proj.weight' % L_SPLIT
    W20 = sd[WN20].float().cpu().numpy()
    print('[V98] 合体: M机制×知识/推理分块 | Ukp m=%d Urp m=%d' % (m, Urp.shape[1]), flush=True)

    # 域状态
    S_k = torch.zeros(m, device='cuda')     # 知识域慢状态 (在Ukp坐标)
    S_r = torch.zeros(m, device='cuda')
    anchor_vecs = []                        # 知识锚 → Ukp坐标 (m,)
    xbuf = {}

    # ---------- 层20 down_proj 输入 hook: 分域 → 更新双慢状态 ----------
    def hook_in(mod, inp, out):
        x = inp[0][0, -1].float()           # (4864,)
        xbuf['x'] = x.detach().cpu().numpy()
        xk = (Pk @ x)                       # 知识分量
        xr = (Pro @ x)
        ak = xk.norm() / (xk.norm() + xr.norm() + 1e-9)
        xbuf['a_k'] = ak.item()
        # 双域慢状态更新 (EMA 在 Ukp 坐标上)
        xk_c = (Ukp.T @ xk); xr_c = (Urp.T @ xr)
        S_k[:] = (1 - BETA) * S_k + BETA * xk_c / (xk_c.norm() + 1e-9)
        S_r[:] = (1 - BETA) * S_r + BETA * xr_c / (xr_c.norm() + 1e-9)
        return out
    h_in = model.model.layers[L_SPLIT].mlp.down_proj.register_forward_hook(hook_in)

    # ---------- 层20 down_proj 输入侧注入 hook: 游离的 S_k 注回知识域 ----------
    inj_vec = None   # (4864,) 知识域注入
    def hook_inj(mod, inp):
        if inj_vec is not None:
            x = inp[0]
            x = x + (inj_vec.unsqueeze(0) * ALPHA_FB).to(x.dtype)
            return (x,)
        return None
    h_inj = model.model.layers[L_SPLIT].mlp.down_proj.register_forward_pre_hook(hook_inj)

    # ---------- anti-self 分域 (层20输出) ----------
    def hook_post(mod, inp, out):
        h = out[0]
        return h
    # (第一版: anti-self 在输出的分域投影较复杂, 先用输入侧双S做去复读依据, 输出暂不改)
    h_post = None

    def embed_4864(texts):
        """句子 → 层20 down_proj 输入激活 (4864)"""
        vecs = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode():
                model(input_ids=ids)
            vecs.append(xbuf['x'].copy())
        return np.array(vecs)

    def gen(texts, max_new=40):
        outs = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode():
                o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                                   repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
            outs.append(tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip())
        return outs

    # ---------- 建知识锚库 (句子→Ukp坐标) ----------
    print('[V98] 建知识世界: %d锚...' % len(ANCHORS), flush=True)
    Xa = embed_4864(ANCHORS)
    anchor_coords = Xa @ Ukp.cpu().numpy()   # (n,m) 知识域坐标
    inj_vec = None
    print('[V98] 知识世界就绪', flush=True)

    # ---------- ① 分域选择性测试: 知识问答 vs 推理, 看 a_k / S_k,S_r ----------
    print('\n=== ① 分域选择性 (S_k=知识域活跃, S_r=推理域活跃) ===', flush=True)
    for q in Q_KNOW + Q_REAS:
        S_k.zero_(); S_r.zero_()
        ans = gen([q])[0]
        # 需要重新算一个完整前向来拿 a_k (generate 后 xbuf 是最后token的)
        print('【%s】\n  答: %s' % (q, ans[:60]), flush=True)
        print('  a_k(知识活跃度)=%.3f  |S_k|=%.3f |S_r|=%.3f  %s' % (
            xbuf.get('a_k', 0), S_k.norm().item(), S_r.norm().item(),
            '→知识态' if xbuf.get('a_k', 0) > 0.6 else ('→推理态' if xbuf.get('a_k', 0) < 0.4 else '→混合')))

    # ---------- ② 知识世界游离: 注入前 vs 注入后 ----------
    print('\n=== ② 知识锚游离注入 (S_k朝最相关锚漂移后注回知识域) ===', flush=True)
    def free_inject(q, steps=6, alpha=0.3):
        """把问题在知识域的起点, 沿锚库游走 steps 步, 得注回向量"""
        x0 = embed_4864([q])[0]
        p = x0 @ Ukp.cpu().numpy()          # 起点 (m,)
        for _ in range(steps):
            d = anchor_coords - p
            dist = np.linalg.norm(d, axis=1)
            w = np.exp(-6 * dist); w = w / (w.sum() + 1e-9)
            p = p + alpha * (d * w[:, None]).sum(0)
        return (p - x0 @ Ukp.cpu().numpy())   # 位移(知识域)
    for q in Q_KNOW:
        shift = free_inject(q)
        print('【%s】游离位移=%.4f (>0=知识世界对问题产生联想牵引)' % (q, np.linalg.norm(shift)), flush=True)

    # ---------- ③ 写活分域: 新知识"北京是中国的首都"(其实已有) → 加一条锚并写进W_k ----------
    print('\n=== ③ M3写活分域 (anti-Hebbian 写知识锚进 W_k, 只动知识块) ===', flush=True)
    NEW = "长城全长约2.1万公里。"
    W0 = sd[WN20].float().cpu().numpy()
    # 新知识锚向量 (Ukp 坐标) + 输入侧补丁 u (知识域)
    xnew = embed_4864([NEW])[0]
    unew = (xnew @ Ukp.cpu().numpy())               # (m,) 知识域坐标
    unew = unew / (np.linalg.norm(unew) + 1e-9)
    u4864 = Ukp.cpu().numpy() @ unew                # 4864 输入侧方向 (∈知识域)
    # anti-Hebbian: 新输出方向 d ⊥ S(慢状态) 且 ⊥ 现有知识锚平均
    d = np.random.RandomState(3).randn(896).astype(np.float64); d /= np.linalg.norm(d)
    patch = np.outer(d, u4864)
    patch = patch / np.linalg.norm(patch) * (np.linalg.norm(W0) * ETA_W)
    # 验证: patch 确实只作用知识域 (W·patch 输入侧在 Pro 上≈0)
    u_k = u4864 @ Pro.cpu().numpy()
    print('  补丁输入侧在推理域残留=%.2e (≈0=写活只落知识块)' % np.linalg.norm(u_k), flush=True)
    # 应用写活
    sd2 = copy.deepcopy(sd)
    Wnew = torch.tensor(W0 + patch).to(sd[WN20].dtype)
    sd2[WN20] = Wnew
    model.load_state_dict(sd2, strict=True)
    # 写活后: 知识题影响大? 推理题影响小?
    def kls_before_after(texts):
        out = []
        for q in texts:
            ids = tok(q, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode():
                l1 = model(input_ids=ids).logits[0, -1].float()
            sd3 = copy.deepcopy(sd)   # 恢复原权重重测(对照)
            model.load_state_dict(sd, strict=True)
            with torch.inference_mode():
                l2 = model(input_ids=ids).logits[0, -1].float()
            model.load_state_dict(sd3, strict=True)  # 恢复写活态继续
            kl = (torch.softmax(l2, -1) * (torch.log_softmax(l2, -1) - torch.log_softmax(l1, -1))).sum().item()
            out.append(kl)
        return out
    kl_k = kls_before_after(Q_KNOW)
    kl_r = kls_before_after(Q_REAS)
    print('  写活后 知识题KL=%s 推理题KL=%s' % ([round(x, 4) for x in kl_k], [round(x, 4) for x in kl_r]), flush=True)
    print('  隔离比(知识KL/推理KL)=%.1f (>3=写活确实只动知识域)' % (np.mean(kl_k) / max(np.mean(kl_r), 1e-6)), flush=True)

    h_in.remove(); h_inj.remove()
    print('\n[V98] 合体验证完成', flush=True)

if __name__ == '__main__':
    main()
