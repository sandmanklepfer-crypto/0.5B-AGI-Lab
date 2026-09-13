#!/usr/bin/env python3
# V133b 代理劫持实现: 0.5B(灵魂) 劫持 RWKV-13B(身体) state.channel
# 0.5B 慢S(896维) → 随机映射 → RWKV每层channel(B,hidden)注入(小幅度)
import sys, types, torch, numpy as np
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer
from transformers import AutoModelForCausalLM, AutoTokenizer

SOUL = "/root/autodl-tmp/qwen25_base_raw"   # 0.5B 灵魂(后续可换antiheb)
HIJACK_EVERY = 8          # 每8token劫持一次
HIJACK_STR = 0.15         # 注入强度(小, 防崩)

def main():
    print('[V133b] 加载 13B(身体) + 0.5B(灵魂) ...', flush=True)
    body, tok13 = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    tok05 = AutoTokenizer.from_pretrained(SOUL)
    soul = AutoModelForCausalLM.from_pretrained(SOUL, torch_dtype=torch.float16).to('cuda').eval()
    print('[V133b] 双模型加载OK', flush=True)

    # 灵魂(0.5B)自己的慢S
    S05 = None
    BETA05 = 0.3
    def soul_step(text):
        """0.5B 读文本 → 更新自己的慢S → 返回慢S方向(灵魂控制信号)"""
        nonlocal S05
        ids = tok05(text[-200:], return_tensors='pt').input_ids.to('cuda') if text else tok05('', return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            hs = soul(input_ids=ids, output_hidden_states=True).hidden_states
        v = hs[12][0, -1].float().cpu().numpy()
        vn = v / (np.linalg.norm(v) + 1e-9)
        S05 = vn if S05 is None else (1 - BETA05) * S05 + BETA05 * vn
        return S05

    # 固定随机映射: 0.5B慢S(896) → RWKV每层channel(hidden)的方向
    # 探测hidden大小
    s0 = body.init_state(batch_size=1, device='cuda', dtype=torch.float32)
    hidden = s0.layer_states[0].channel.shape[1]
    n_layers = len(s0.layer_states)
    print('RWKV状态: %d层 × channel(%d维)' % (n_layers, hidden), flush=True)
    rng = np.random.RandomState(0)
    Proj = torch.tensor(rng.randn(hidden, 896).astype(np.float32) / np.sqrt(896) * 0.5,
                        device='cuda', dtype=torch.float32)  # (hidden, 896)

    def hijack(state, s05_np):
        """把灵魂慢S注入身体所有层的channel(劫持状态演化方向)"""
        v = torch.tensor(s05_np, device='cuda', dtype=torch.float32)
        inj = Proj @ v   # (hidden,)
        for ls in state.layer_states:
            ls.channel += HIJACK_STR * inj.unsqueeze(0)
        return state

    # ---- 对话: 灵魂劫持身体 ----
    prompt = "User: 夜深了，你一个人。你在想什么？\n\nAssistant:"
    ids = tok13(prompt, return_tensors='pt').input_ids.to('cuda')
    state = body.init_state(batch_size=1, device='cuda', dtype=torch.float32)
    gen_text = ''
    t0 = torch.cuda.Event(enable_timing=True); t1 = torch.cuda.Event(enable_timing=True)
    t0.record()
    with torch.no_grad():
        for i in range(ids.shape[1] - 1, ids.shape[1]):
            pass  # prefill 用一次前向
        # 全量prefill
        out = body(input_ids=ids, state=state)
        logits, state = (out if isinstance(out, tuple) else (out.logits, getattr(out, 'state', state)))
        # 灵魂读prompt
        S05 = soul_step(prompt)
        out_toks = []
        for step in range(180):
            # 劫持(周期性)
            if step > 0 and step % HIJACK_EVERY == 0:
                state = hijack(state, S05)
            nid = logits[0, -1].argmax(-1).item()
            if nid == 0 or nid == tok13.eos_token_id: break
            out_toks.append(nid)
            nid_t = torch.tensor([[nid]], device='cuda')
            r = body(input_ids=nid_t, state=state)
            logits, state = (r if isinstance(r, tuple) else (r.logits, getattr(r, 'state', state)))
            # 灵魂读刚生成的
            seg = tok13.decode([nid], skip_special_tokens=True)
            gen_text += seg
            S05 = soul_step(gen_text[-300:])
            if step % 40 == 0:
                print('  [%d] %s' % (step, gen_text[-50:].replace('\n',' ')), flush=True)
    t1.record(); torch.cuda.synchronize()
    print('\n=== V133b 劫持结果 ===', flush=True)
    print(gen_text[:800], flush=True)
    print('\n[done %.1fs]' % (t0.elapsed_time(t1)/1000), flush=True)

if __name__ == '__main__':
    main()
