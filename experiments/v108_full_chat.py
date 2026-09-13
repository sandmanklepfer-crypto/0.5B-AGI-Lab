#!/usr/bin/env python3
"""
V108 合体终极对话: 0.5B 上把全套合体 + 对话效果
= base + 层12 antiheb(活权重) + 层20 知识/推理分块(Ukp/Urp 双慢状态)
  + 反刍思考 + 冲击式知识写活(v81干净配方: 归一化单方向+幅度0.06)
流程: 问一个问题 → 若需要新知识则"冲击写活"一条(沿知识块) → 分域对话生成
"""
import copy, re
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR   = '/root/autodl-tmp/life1/antiheb_05b'
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'
L12, L20 = 12, 20
BETA = 0.3
SCALE = 0.06   # v81安全幅度

DIALOG = [
    # (类型, 问题)
    ("推理", "三个朋友分苹果，甲拿的是乙的两倍，乙拿的比丙多1个，一共17个，三人各拿多少？"),
    ("发散", "如果记忆可以像文件一样删除和恢复，人应该拥有这个能力吗？"),
    ("知识+冲击", "鲸鱼属于什么动物类别？"),
    ("自指", "你正在思考这个问题本身，这个'思考'发生在哪里？"),
]

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Ukp = b['Ukp'].float().cuda(); Urp = b['Urp'].float().cuda()
    m = Ukp.shape[1]
    Pk = Ukp @ Ukp.T
    print('[V108] 合体对话 | 层12活权重+层20分块 | 分域慢状态+干净写活', flush=True)

    # ---- 分域慢状态 (层20 down_proj 输入) ----
    S_k = torch.zeros(m, device='cuda'); S_r = torch.zeros(m, device='cuda')
    a_k = 0.5
    xbuf = {}
    def hook_in(mod, inp, out):
        nonlocal S_k, S_r, a_k
        x = inp[0][:, -1].float()[0]
        xk = Pk @ x
        xk_c = Ukp.T @ xk
        nk = xk_c.norm() + 1e-9
        S_k = (1-BETA)*S_k + BETA*xk_c/nk
        xbuf['a_k'] = (nk/(nk + 1e-9)).item()
        a_k = xbuf['a_k']
        return out
    h_in = model.model.layers[L20].mlp.down_proj.register_forward_hook(hook_in)

    WN20 = 'model.layers.%d.mlp.down_proj.weight' % L20
    W20 = sd[WN20].float().cpu().numpy()

    def gen(prompt, max_new=110):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=True, temperature=0.85,
                               top_p=0.92, repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def embed_x(texts):
        """层20 down_proj 输入 (4864)"""
        vecs = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode(): model(input_ids=ids)
            vecs.append(xbuf.get('x0', np.zeros(4864)))
        return np.array(vecs) if vecs else np.zeros((0, 4864))

    # 修正: hook里存4864输入
    def hook_in2(mod, inp, out):
        nonlocal S_k, S_r, a_k
        x = inp[0][:, -1].float()[0]
        xbuf['x0'] = x.detach().cpu().numpy()
        xk = Pk @ x
        xk_c = Ukp.T @ xk
        nk = xk_c.norm() + 1e-9
        S_k = (1-BETA)*S_k + BETA*xk_c/nk
        a_k = (nk/(nk + 1e-9)).item()
        xbuf['a_k'] = a_k
        return out
    h_in.remove()
    h_in = model.model.layers[L20].mlp.down_proj.register_forward_hook(hook_in2)

    # ---- 干净写活 (v81配方: 单方向归一化+幅度0.06, 沿知识块方向 Ukp) ----
    def clean_write_knowledge(sentence):
        """把一句知识 干净写进层20知识块 (只动知识域)"""
        # 取该句在层20 down_proj输入的激活方向 (知识域)
        _ = embed_x([sentence])
        u4864 = xbuf['x0'].copy()
        u4864 = u4864 / (np.linalg.norm(u4864) + 1e-9)
        # 只留知识域分量 (投影到 Ukp)
        u_k = (Ukp.cpu().numpy() @ (Ukp.cpu().numpy().T @ u4864))
        u_k = u_k / (np.linalg.norm(u_k) + 1e-9)
        # 输出方向: 随机单位 (干净, 不依赖旧方向)
        d = np.random.RandomState(7).randn(896).astype(np.float64)
        d = d / np.linalg.norm(d)
        patch = np.outer(d, u_k)
        patch = patch / np.linalg.norm(patch) * (np.linalg.norm(W20) * SCALE)
        # 应用
        sd2 = copy.deepcopy(sd)
        sd2[WN20] = torch.tensor(W20 + patch).to(sd[WN20].dtype)
        model.load_state_dict(sd2, strict=True)
        return np.linalg.norm(patch)

    def chat(q, tag):
        print('\n' + '='*66, flush=True)
        print('【%s】%s' % (tag, q), flush=True)
        if tag == '知识+冲击':
            # 演示: 冲击写活一条相关知识 (模型已知道, 但展示机制在真实对话中生效)
            written = clean_write_knowledge("鲸鱼是哺乳动物，不是鱼类。")
            print('  [冲击写活] 知识块写入幅度=%.4f (只动知识域, 推理域不动)' % written, flush=True)
        # 反刍: 先想一轮再答
        ans1 = gen('下面问题需要认真思考，请先拆解再回答。\n问题：%s\n\n思考：' % q)
        print('  [第一轮思考] %s' % ans1[:220], flush=True)
        ans2 = gen('问题：%s\n你刚才的想法：%s\n请再深入一层，给出更完整的最终回答：\n'
                   % (q, ans1[:300]))
        print('  [最终回答] %s' % ans2[:300], flush=True)
        print('  [域] a_k=%.2f %s' % (a_k, '知识态' if a_k > 0.6 else ('推理态' if a_k < 0.4 else '混合')), flush=True)

    for tag, q in DIALOG:
        chat(q, tag)
    h_in.remove()
    print('\n[V108] 完成', flush=True)

if __name__ == '__main__':
    main()
