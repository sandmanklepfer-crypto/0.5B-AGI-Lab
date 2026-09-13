#!/usr/bin/env python3
# V141 底层动力学找核心: 不按架构名, 按动力学剖面找 RWKV 的"核心区"
# 指标(每层/每状态分量):
#   1. 状态跃迁量 |Δchannel|: 该层每token状态变多大 = 信息吞吐
#   2. 雅可比敏感度: 输出对状态的导数 = 该层"加工强度"
#   3. 时间常数: channel 自相关衰减 = 该层记多久(慢=记忆/快=加工)
#   4. 非线性激活度: 门控输出饱和程度
# 找到: 哪些层是"加工核心"(快变/高敏), 哪些是"记忆核心"(慢变/长时)
import sys, types, torch, numpy as np
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

TEXT = '山腰的老屋空了七年，我推开门，灰尘里有一行新的脚印，通向堂屋。我跟着脚印走，听见屋后有声音。' * 3

def main():
    print('[V141] 加载 RWKV-7 ...', flush=True)
    model, tok = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    ids = tok(TEXT, return_tensors='pt').input_ids.to('cuda')
    state = model.init_state(batch_size=1, device='cuda', dtype=torch.float32)
    n_layers = len(state.layer_states)
    # 记录每层 channel 轨迹
    traj = [[] for _ in range(n_layers)]
    with torch.no_grad():
        for i in range(ids.shape[1]):
            r = model(input_ids=ids[:, i:i+1], state=state)
            logits, state = r if isinstance(r, tuple) else (r.logits, getattr(r, 'state', state))
            for L, ls in enumerate(state.layer_states):
                traj[L].append(ls.channel[0].float().cpu().numpy().copy())
    print('逐token完成 (%d token × %d层)' % (ids.shape[1], n_layers), flush=True)
    # 分析
    print('\n=== 动力学剖面 ===', flush=True)
    print('层  平均跃迁|Δc|  自相关τ(记多久)  范数  判定', flush=True)
    for L in range(n_layers):
        arr = np.array(traj[L])          # (T, H)
        if arr.shape[0] < 5: continue
        jumps = np.abs(np.diff(arr, axis=0)).mean()      # 每步变化
        # 时间常数: 相邻cos(层状态稳定性)
        cos_adj = [float(arr[t]@arr[t+1]/(np.linalg.norm(arr[t])*np.linalg.norm(arr[t+1])+1e-9)) for t in range(min(len(arr)-1, 60))]
        tau = float(np.mean(cos_adj)) if cos_adj else 0   # 高=慢变(记忆), 低=快变(加工)
        norm = float(np.linalg.norm(arr[-1]))
        role = '记忆核心(慢变)' if tau > 0.999 else ('加工核心(快变)' if jumps > np.median([np.abs(np.diff(np.array(traj[L2]),axis=0)).mean() for L2 in range(n_layers) if np.array(traj[L2]).shape[0]>5])*1.2 else '中继')
        if L % 5 == 0 or role != '中继':
            print('层%2d  %.5f  τ=%.5f  |c|=%.1f  %s' % (L, jumps, tau, norm, role), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
