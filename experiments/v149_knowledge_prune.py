#!/usr/bin/env python3
# V149 知识剪除 — 尽量删知识(允许伤一点骨架), 只留控制核+结构
# 剪法: 用激活定位"知识单元"(题库/事实强激活, 流程弱) vs "控制单元"(跨任务稳定)
#       gate权重行置零 = 剪掉该神经元
# 指标: 剪除后 ①知识题还答得出吗(应下降=知识删了) ②控制/流程还在吗(多步组织能力)
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
KNOW_TASKS = ['中国的首都是哪里？','水的沸点是多少？','鲸鱼属于什么动物？','光速大约多少？','一年几个月？']
CTRL_TASKS = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
              '甲比乙高乙比丙矮谁最矮？','如果P则Q，P真Q怎样？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    # 收集 层12 gate 激活
    buf = {}
    h = model.model.layers[12].mlp.gate_proj.register_forward_hook(
        lambda m, i, o: buf.__setitem__('g', o[0].float().cpu()))
    def gate_act(texts):
        acts = []
        with torch.no_grad():
            for t in texts:
                buf.clear()
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                model(input_ids=ids)
                if 'g' in buf:
                    # 所有token的gate激活均值(该任务下)
                    acts.append(buf['g'].mean(0).numpy())
        return np.array(acts) if acts else np.zeros((0, 4864))
    A_know = gate_act(KNOW_TASKS)   # (5,4864)
    A_ctrl = gate_act(CTRL_TASKS)   # (3,4864)
    h.remove()
    # 知识单元: 知识任务激活强 且 控制任务激活弱(只在知识时开=知识专用)
    know_str = A_know.mean(0)
    ctrl_str = A_ctrl.mean(0)
    # 知识专用度 = 知识激活 - 控制激活
    spec_know = know_str - ctrl_str
    th = np.percentile(spec_know, 80)   # 顶20%=知识单元
    know_units = np.where(spec_know > th)[0]
    print('知识专用单元: %d/4864 (顶20%%)' % len(know_units), flush=True)
    # 剪除: gate行置零(该神经元永久关闭)
    sd = model.state_dict()
    WN = 'model.layers.12.mlp.gate_proj.weight'
    W0 = sd[WN].float().cpu().numpy().copy()
    W_new = W0.copy()
    W_new[know_units, :] = 0.0
    sd[WN] = torch.tensor(W_new).to(sd[WN].dtype)
    model.load_state_dict(sd, strict=True)
    print('已剪除 %d 个知识单元 (层12 gate)' % len(know_units), flush=True)
    # 测试: 知识题 vs 控制题 剪除前后
    def test(texts):
        res = []
        with torch.no_grad():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=25, do_sample=False,
                                   repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
                res.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:30])
        return res
    print('\n=== 剪除后 ===', flush=True)
    print('知识题:', flush=True)
    for q, a in zip(KNOW_TASKS, test(KNOW_TASKS)):
        print('  %s → %s' % (q[:12], a[:25]), flush=True)
    print('控制/流程题:', flush=True)
    for q, a in zip(CTRL_TASKS, test(CTRL_TASKS)):
        print('  %s → %s' % (q[:14], a[:25]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
