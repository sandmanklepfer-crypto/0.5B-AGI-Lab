#!/usr/bin/env python3
# V147b 控制核深挖: 逐token单前向记录gate, 分析控制动力学
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    L = 12
    buf = {}
    h = model.model.layers[L].mlp.gate_proj.register_forward_hook(
        lambda mod, i, o: buf.__setitem__('gate', o[0, -1].float().cpu()))
    q = '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'
    ids = tok(q, return_tensors='pt').input_ids.to('cuda')
    gate_traj = []
    with torch.no_grad():
        # 逐token: 每步前向整个前缀, 只记末token的gate
        n = ids.shape[1]
        for i in range(1, n):
            buf.clear()
            model(input_ids=ids[:, :i])
            if 'gate' in buf:
                gate_traj.append(buf['gate'].numpy().copy())
    h.remove()
    G = np.array(gate_traj)
    print('gate轨迹: %s' % (G.shape,), flush=True)
    if G.ndim != 2 or G.shape[1] < 100:
        print('异常退出'); return
    mean = G.mean(0); std = G.std(0)
    stable_idx = np.where((std < np.median(std)) & (mean > np.median(mean)))[0]
    spec_idx = np.where(std > np.median(std) * 1.5)[0]
    print('稳定(控制)单元: %d, 特异单元: %d' % (len(stable_idx), len(spec_idx)), flush=True)
    ctrl_traj = G[:, stable_idx].mean(1) if len(stable_idx) else np.zeros(G.shape[0])
    spec_traj = G[:, spec_idx].mean(1) if len(spec_idx) else np.zeros(G.shape[0])
    print('\n① 阶段节拍(逐token):', flush=True)
    for t in range(0, len(ctrl_traj), max(1, len(ctrl_traj)//8)):
        print('  tok%2d: 控制核=%.3f 内容核=%.3f' % (t, ctrl_traj[t], spec_traj[t]), flush=True)
    if len(stable_idx) >= 10:
        samp = stable_idx[np.random.RandomState(0).choice(len(stable_idx), min(50, len(stable_idx)), replace=False)]
        sub = G[:, samp]
        corr = np.corrcoef(sub.T)
        sync = (np.abs(corr) - np.eye(len(samp))).mean()
        print('\n② 控制核内部同步: %.4f' % sync, flush=True)
    from numpy.fft import rfft
    def peakf(traj):
        sp = np.abs(rfft(traj - traj.mean()))
        return float(sp[1:].argmax()/len(sp)) if len(sp) > 2 else 0
    print('③ 控制核主频: %.3f | 内容核主频: %.3f' % (peakf(ctrl_traj), peakf(spec_traj)), flush=True)
    print('④ 控制核开关性: %.4f | 内容核: %.4f' % (
        (np.median(ctrl_traj) - np.mean(ctrl_traj[ctrl_traj<np.median(ctrl_traj)]))**2,
        (np.median(spec_traj) - np.mean(spec_traj[spec_traj<np.median(spec_traj)]))**2), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
