#!/usr/bin/env python3
# V138 动力学级猎取: 猎"通路"不猎"答案"
# 知识(13B解释)作为刺激 → 0.5B自己处理(深层激活=它的理解痕迹)
# → anti-Hebbian 干净写活(把"通往概念的路径"凿进权重, 非内容)
# → 多轮多角度累积 → 脱离上下文测试: 能否自己走到那条通路
import sys, types, torch, numpy as np, re
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer
from transformers import AutoModelForCausalLM, AutoTokenizer

HUNTER = "/root/autodl-tmp/qwen25_base_raw"
N_ROUNDS = 10
SCALE = 0.04
WRITE_LAYERS = [12, 16, 20]    # 层轮换(防漂移累积)
ANGLES = [
    '为什么在地球表面(弯曲的)上, 两点间最短路径不是直线? 这跟度量有什么关系?',
    '黎曼度量到底是什么? 它和普通距离有什么区别? 为什么说它定义在"每一点"?',
    '什么是曲率? 怎么感觉一个面是弯的? 弯曲的程度怎么数学化?',
    '爱因斯坦说物质让时空弯曲, 这个"弯曲"在几何上到底指什么?',
    '如果我在一个曲面上走, 平行线会相交吗? 这和曲率什么关系?',
    '高斯说曲率是"内蕴"的, 什么意思? 蚂蚁在球面上能发现球是弯的吗?',
]

def main():
    torch.manual_seed(0)
    print('[V138] 加载 13B猎物 + 0.5B猎人(可写活) ...', flush=True)
    prey, tok13 = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    tok = AutoTokenizer.from_pretrained(HUNTER)
    hunter = AutoModelForCausalLM.from_pretrained(HUNTER, torch_dtype=torch.float16).to('cuda').eval()
    sd = hunter.state_dict()
    print('[V138] 加载OK | 目标: 黎曼曲率(动力学级) | %d轮 写活层=%s' % (N_ROUNDS, WRITE_LAYERS), flush=True)

    # 已写方向(anti-Hebbian 记忆)
    written_dirs = []
    def clean_write(layer, act_in_4864, act_out_896):
        """干净写活: 把'处理该知识时的激活方向'凿进down_proj"""
        WN = 'model.layers.%d.mlp.down_proj.weight' % layer
        W = sd[WN].float().cpu().numpy()
        avec = act_in_4864.astype(np.float64)
        avec = avec / (np.linalg.norm(avec) + 1e-9)
        # anti-Hebbian: 避开已写方向(输入侧)
        for wd in written_dirs:
            avec = avec - (avec @ wd) * wd
        avec = avec / (np.linalg.norm(avec) + 1e-9)
        # 输出侧方向 = 激活本身的方向(它"走向"哪里)
        d = act_out_896.astype(np.float64)
        d = d / (np.linalg.norm(d) + 1e-9)
        P = np.outer(d, avec)
        P = P / np.linalg.norm(P) * (np.linalg.norm(W) * SCALE)
        sd[WN] = torch.tensor(W + P).to(sd[WN].dtype)
        written_dirs.append(avec)
        hunter.load_state_dict(sd, strict=True)

    def gen_hunter(text, max_new=40):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = hunter.generate(ids, max_new_tokens=max_new, do_sample=True,
                                temperature=0.85, top_p=0.9, repetition_penalty=1.15,
                                pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def capture(layer, text):
        """取 层layer 处理text时的 down_proj输入(4864) 和 层输出(896)"""
        buf = {}
        h_in = hunter.model.layers[layer].mlp.down_proj.register_forward_hook(
            lambda m, i, o: buf.__setitem__('in', i[0][0, -1].float().cpu().numpy()))
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            hs = hunter(input_ids=ids, output_hidden_states=True).hidden_states
        h_in.remove()
        return buf['in'], hs[layer+1][0, -1].float().cpu().numpy()

    def prey_answer(angle, seed):
        torch.manual_seed(seed)
        prompt = f"User: {angle}\n\nAssistant: 让我从直觉讲起:"
        ids = tok13(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = prey.generate(input_ids=ids, max_new_tokens=100, do_sample=True,
                                temperature=0.85, top_p=0.92, pad_token_id=0)
        return tok13.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    # ---- 猎取主循环 ----
    print('\n=== 动力学猎取开始 ===', flush=True)
    for r in range(N_ROUNDS):
        angle = ANGLES[r % len(ANGLES)]
        layer = WRITE_LAYERS[r % len(WRITE_LAYERS)]
        # 1. 猎物给解释
        exp = prey_answer(angle, 700 + r * 7)
        # 2. 猎人消化(带自我锚:"我学过距离...")
        dig = gen_hunter('我以前知道距离是两点之差。现在看到一段关于曲率/度量的解释：\n%s\n我现在的理解是：' % exp[:350])
        # 3. 捕获猎人处理知识时的激活(凿通路素材)
        probe_text = '黎曼曲率 弯曲空间 度量 ' + dig[-120:]
        act_in, act_out = capture(layer, probe_text)
        # 4. 干净写活
        clean_write(layer, act_in, act_out)
        print('  轮%d [层%d] 猎物: %s...' % (r+1, layer, exp[:45].replace('\n',' ')), flush=True)
        print('          猎人消化: %s...' % dig[:60].replace('\n',' '), flush=True)
        # 5. 崩检测
        if r % 3 == 2:
            chk = gen_hunter('你好', 15)
            if len(set(chk[-6:])) == 1:
                print('  ⚠ 崩溃前兆, 停', flush=True); break
    print('\n=== 猎取完成, 权重已凿通路 ===', flush=True)

    # ---- 脱离上下文测试(不给任何知识, 只给词) ----
    print('\n=== 测试: 通路是否可走 ===', flush=True)
    tests = [
        ('联想', '弯曲的空间 距离'),
        ('直问', '曲率是什么意思？'),
        ('应用', '为什么地球表面最短路径不是直线？'),
    ]
    for tag, q in tests:
        a = gen_hunter(q, 60)
        print('\n【%s】%s\n  → %s' % (tag, q, a[:250]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
