#!/usr/bin/env python3
"""
V106 终极挑战 — 全部部件装上, 挑战自指级难题
部件:
  1. 合体底子: life1/antiheb_05b (=qwen25_base_raw + 层12 anti-Hebbian 动态机制)
  2. 分域慢状态: 层20 down_proj 输入 → S_k(知识域/Ukp) + S_r(推理域/Urp) EMA
     (状态层仪表: a_k = 此刻在知识域还是推理域)
  3. 反刍循环: 生成一段思考 → 接回上下文 → 再深入 (时间拼完整度, 无外接笔记本)
  4. 自发打转检测(状态层, 非文本正则): 每轮 ΔS 塌缩=卡死
     → 注入"换角度重审"扰动(anti-Hebbian式换路), 模型自己重新组织
题: 自指级发散难题 (无标准答案, 探"活的思考"深度)
"""
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR   = '/root/autodl-tmp/life1/antiheb_05b'
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'
L20    = 20
BETA   = 0.3
D_ROT  = 0.10        # 打转判定阈值 (ΔS)
MAX_R  = 5           # 每题最多思考轮
GEN    = dict(max_new_tokens=95, do_sample=True, temperature=0.85,
              top_p=0.92, repetition_penalty=1.2, pad_token_id=None)

QUESTIONS = [
    ("自指·自我修改",
     "假设你是一个能修改自己权重的模型。为了让自己更有智慧，你会先修改哪一部分？"
     "修改之后，你还是原来的你吗？什么才算'你'？"),
    ("发散·深度",
     "一个拥有无限知识却从不反思的系统，和一个知识有限但会不断推翻自己结论的系统，"
     "哪一个更可能做出真正重大的发现？为什么？"),
]

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Ukp = b['Ukp'].float().cuda(); Urp = b['Urp'].float().cuda()
    m = Ukp.shape[1]
    Pk = Ukp @ Ukp.T
    Pro = Urp @ Urp.T
    print('[V106] 终极挑战 | 底子=antiheb_05b(活权重) + 分域慢状态 + 反刍循环 + 自发换路', flush=True)

    S_k = torch.zeros(m, device='cuda', dtype=torch.float32)
    S_r = torch.zeros(m, device='cuda', dtype=torch.float32)
    deltaS = 0.0          # 最近一次 hook 的 S 更新量 (活性)
    a_k = 0.5
    xbuf = {}

    def hook_in(mod, inp, out):
        nonlocal deltaS, a_k
        x = inp[0][:, -1].float()          # (B,4864) 最后token
        x = x[0]
        xk = Pk @ x; xr = Pro @ x
        xk_c = Ukp.T @ xk; xr_c = Urp.T @ xr
        nk = xk_c.norm() + 1e-9; nr = xr_c.norm() + 1e-9
        new_k = (1-BETA)*S_k + BETA*xk_c/nk
        new_r = (1-BETA)*S_r + BETA*xr_c/nr
        deltaS = (new_k-S_k).norm().item() + (new_r-S_r).norm().item()
        S_k.copy_(new_k); S_r.copy_(new_r)
        xbuf['a_k'] = (nk/(nk+nr)).item()
        a_k = xbuf['a_k']
        return out
    h_in = model.model.layers[L20].mlp.down_proj.register_forward_hook(hook_in)

    def generate(prompt, max_new=95):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=True,
                               temperature=0.85, top_p=0.92, repetition_penalty=1.2,
                               pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def think(q, tag):
        print('\n' + '='*70, flush=True)
        print('【%s】%s' % (tag, q), flush=True)
        history = ''
        turns = []
        prev_S = (S_k.clone(), S_r.clone())
        rotate = 0
        for r in range(1, MAX_R+1):
            if r == 1:
                prompt = ('下面是一道需要深度思考的问题。请把它拆成子问题，逐步想清楚，'
                          '不要急着下结论，允许推翻自己。\n问题：%s\n\n思考：' % q)
            elif r == MAX_R:
                prompt = ('%s\n以上是你前面的思考。现在综合所有角度，'
                          '给出你最完整、最坦诚的最终回答：\n' % (q + '\n' + history[-1500:]))
            elif rotate >= 1 and r % 2 == 0:
                prompt = ('%s\n你刚才的思路可能走进了死胡同。'
                          '换一个完全不同的角度重新审视这个问题，找出前面没想到的层面：\n'
                          % (q + '\n' + history[-1400:]))
            else:
                prompt = ('%s\n继续深入：上一个子问题想清楚后，'
                          '再往深一层想，或者检查前面的推理有没有漏洞：\n'
                          % (q + '\n' + history[-1400:]))
            seg = generate(prompt)
            history += seg + '\n'
            cur_S = (S_k.clone(), S_r.clone())
            ds = (cur_S[0]-prev_S[0]).norm().item() + (cur_S[1]-prev_S[1]).norm().item()
            prev_S = cur_S
            # 状态层打转检测: ds 小 = 这轮没产生新状态结构 = 卡死
            stalled = ds < D_ROT
            if stalled:
                rotate += 1
                mark = '⚠状态塌缩→自发换路'
            else:
                mark = 'ΔS=%.3f' % ds
            turns.append((r, seg, a_k, ds, stalled))
            print('\n── 思考第%d轮 [域a_k=%.2f %s] ──' % (r, a_k, mark), flush=True)
            print(seg[:400], flush=True)
            if r == MAX_R:
                break
        final = history.strip().split('\n')[-1] if history.strip() else ''
        print('\n[终] 总轮数=%d 自发换路=%d 最后回答: %s' % (len(turns), rotate, final[:200]), flush=True)

    for tag, q in QUESTIONS:
        think(q, tag)
    h_in.remove()
    print('\n[V106] 完成', flush=True)

if __name__ == '__main__':
    main()
