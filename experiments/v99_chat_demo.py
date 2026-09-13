#!/usr/bin/env python3
"""
V99 合体引擎对话演示: 机制分域 + 知识锚游离注入 实际对话
底子: qwen25_base_raw + 层12 antiheb机制痕迹 + 层20 知识/推理分块(v92)
运行时: 双慢状态 S_k/S_r + 每问先做知识域游离(联想)再生成
显示: a_k 知识活跃度 (观察知识态/推理态切换)
题目: 知识题/推理题/发散题混合
"""
import numpy as np, torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR   = '/root/autodl-tmp/life1/antiheb_05b'   # base+层12机制
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'
L_SPLIT = 20
BETA = 0.3; ALPHA = 0.35; STEPS = 6

# 知识世界(锚)
ANCHORS = [
    "中国的首都是北京。", "水在标准大气压下100摄氏度沸腾。",
    "光速约为每秒30万公里。", "珠穆朗玛峰海拔约8848米。",
    "年龄差在两人都活着时永远不变。", "十年后每个人都长十岁。",
    "长江是中国最长的河流。", "地球绕太阳公转一圈是一年。",
]
DIALOG = [
    ("知识", "中国的首都是哪里？"),
    ("推理", "小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？"),
    ("发散", "如果一个人能同时看到过去和未来，他最困惑的事情会是什么？"),
    ("知识", "水的沸点是多少度？"),
    ("推理", "一个盒子里有红球和蓝球，红球是蓝球的2倍，拿走3个蓝球后红球是蓝球的3倍，原来各有多少个？"),
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Ukp = b['Ukp'].float().cuda(); m = Ukp.shape[1]
    Pk  = Ukp @ Ukp.T
    xbuf = {}
    S_k = torch.zeros(m, device='cuda'); S_r = torch.zeros(m, device='cuda')
    inj_vec = None
    ALPHA_FB = 0.5

    def hook_in(mod, inp, out):
        x = inp[0][0, -1].float()
        xbuf['x'] = x.detach().cpu().numpy()
        xk = Pk @ x
        ak = xk.norm() / (xk.norm() + 1e-9)
        xbuf['a_k'] = ak.item()
        S_k[:] = (1-BETA)*S_k + BETA*(Ukp.T@xk)/((Ukp.T@xk).norm()+1e-9)
        S_r[:] = (1-BETA)*S_r + BETA*((b['Urp'].float().cuda().T)@(b['Urp'].float().cuda()@b['Urp'].float().cuda().T@x))/((b['Urp'].float().cuda().T@x).norm()+1e-9)
        return out
    h_in = model.model.layers[L_SPLIT].mlp.down_proj.register_forward_hook(hook_in)

    def hook_inj(mod, inp):
        if inj_vec is not None:
            x = inp[0]
            return (x + (inj_vec.unsqueeze(0)*ALPHA_FB).to(x.dtype),)
    h_inj = model.model.layers[L_SPLIT].mlp.down_proj.register_forward_pre_hook(hook_inj)

    def embed_4864(texts):
        vecs = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode(): model(input_ids=ids)
            vecs.append(xbuf['x'].copy())
        return np.array(vecs)

    def free_shift(q):
        x0 = embed_4864([q])[0]
        A = embed_4864(ANCHORS) @ Ukp.cpu().numpy()
        p = x0 @ Ukp.cpu().numpy()
        for _ in range(STEPS):
            d = A - p; dist = np.linalg.norm(d, axis=1)
            w = np.exp(-6*dist); w = w/(w.sum()+1e-9)
            p = p + ALPHA*(d*w[:,None]).sum(0)
        return (p - x0 @ Ukp.cpu().numpy()), p

    def chat(q, tag):
        nonlocal inj_vec
        S_k.zero_(); S_r.zero_()
        shift, p_end = free_shift(q)
        inj_vec = torch.tensor((Ukp.cpu().numpy() @ (shift if np.linalg.norm(shift)>1e-6 else np.zeros(m)))).float().cuda()
        # 只注入显著游离
        inj_vec = inj_vec if np.linalg.norm(shift) > 0.02 else None
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=130, do_sample=True, temperature=0.8,
                               top_p=0.9, repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        ans = tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()
        inj_vec = None
        state = '知识态' if xbuf.get('a_k',0) > 0.6 else ('推理态' if xbuf.get('a_k',0) < 0.4 else '混合')
        print('\n【%s/%s】\n  游离牵引=%.3f' % (tag, q, np.linalg.norm(shift) if shift is not None else 0), flush=True)
        print('  [域:%s a_k=%.2f]' % (state, xbuf.get('a_k',0)), flush=True)
        print('  → %s' % ans[:400], flush=True)

    print('[V99] 合体引擎对话演示 (antiheb底子+分块+双慢状态+知识游离)', flush=True)
    for tag, q in DIALOG:
        chat(q, tag)
    h_in.remove(); h_inj.remove()
    print('\n[V99] 完成', flush=True)

if __name__ == '__main__':
    main()
