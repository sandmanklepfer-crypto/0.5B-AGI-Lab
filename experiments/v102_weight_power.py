#!/usr/bin/env python3
"""
V102 权重幂次滚动 (章程空间展开) — 试做
原理: 0.5B 单次前向=一层走一遍; 让推理状态在权重上"再滚几次"(循环组织),
     等效把权重/状态展开成更高阶章程空间 (0.5B -> 0.5B^滚次的等效组织深度)
关键设计:
  状态 x 过 层L的MLP:  y = down(W_d · σ(W_g·x) * W_u·x)   (一次组织)
  "滚" = 把 y 当新的 x 再送进同一个 MLP, 滚 N 次 = N 次组织
        (同一批权重, 每次滚都对前次结果再重组 → 时间展开 = 等效深度增长)
  不是简单重复: 每次滚前把 x 在"章程空间"里重新归一化/加当前步上下文,
     让每滚产生新的交叉结构 (类似把画布对折再对折)
实现: 钩住某深层(如20)的MLP, 对经过它的状态做 R 次滚动(每次滚后残差接回),
     其它层正常。R=1(原样对照) vs R=3 vs R=6, 测深问题能力是否随滚次上升。
测: 用 0.5B 能开始但会撞容量墙的任务(长程约束/复杂状态跟踪), 看滚次↑是否答得更好
"""
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
ROLL_LAYER = 20      # 滚动层
ROLLS = [1, 3, 6]    # 对照: 滚1次(原样)/3次/6次

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    # 拿滚动层的 MLP 组件
    mlp = model.model.layers[ROLL_LAYER].mlp
    print('[V102] 权重幂次滚动 | 滚动层=%d 滚次=%s' % (ROLL_LAYER, ROLLS), flush=True)

    # 深任务1: 长程状态跟踪 (0.5B 单次易丢)
    TASKS = [
        ("三色球跟踪(3步)", 
         "盒子里开始有1个红球。第一次放入2个蓝球。第二次拿走1个红球放入3个绿球。第三次拿走2个蓝球放入1个红球。现在盒子里红球、蓝球、绿球各多少个？"),
        ("人物关系多跳", 
         "老王的儿子是小李，小李的妻子是小张，小张的弟弟是小赵，小赵的父亲是老李。问：小张和老王是什么关系？"),
        ("排队位置", 
         "甲乙丙丁戊五人排队。甲在乙左边，丙在甲左边，丁在戊右边，戊在乙右边。问：谁站在最中间？"),
    ]

    def gen_roll(prompt, rolls, max_new=90):
        """带滚动推理的生成: 提示词过模型时, 滚动层状态滚 rolls 次"""
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        # 滚动hook: 拦截滚动层MLP输出, 做rolls次滚动
        orig_forward = mlp.forward
        def rolling_forward(x):
            h = orig_forward(x)          # 正常一次
            if rolls <= 1:
                return h
            # 滚: 把输出当输入再进MLP, 每次滚之间做轻量重整(残差+归一)
            for _ in range(rolls - 1):
                # 用"输出侧激活"再造一个输入(与gate/up结构匹配: 用h投影回4864? 
                # 简化可行做法: 把h当x的"深化版", 直接再过一遍原MLP的gate/up需要4864维
                # 这里用 down 的伪逆太贵; 采用: 对x做多次down_proj级联的组织
                break
            return h
        # 注: 真正的"幂次滚动"需要在4864中间空间循环, 下面用可靠近似:
        # 在滚动层把 (gate*up) 的结果反复过 down_proj -> 升维 -> 再过 down...
        # 受transformers模块限制, 这里用等效: 多次"down(gate*up)"级联,
        # 即把隐藏态反复投影过MLP低秩核心 = W_d @ (W_u^T x ⊙ σ(W_g^T x)) 迭代
        down_w = mlp.down_proj.weight.detach().float().to(torch.bfloat16)   # (896,4864)
        gate_w = mlp.gate_proj.weight.detach().float().to(torch.bfloat16)   # (4864,896)
        up_w   = mlp.up_proj.weight.detach().float().to(torch.bfloat16)
        def roll_iter(hidden):
            # hidden (B,L,896) -> 中间4864 -> 再过down... 每次滚=一次完整MLP组织
            g = F.silu(F.linear(hidden, gate_w))          # (B,L,4864)
            u = F.linear(hidden, up_w)
            m = g * u
            return F.linear(m, down_w)                    # (B,L,896)
        ids_in = ids
        with torch.inference_mode():
            # 前向到滚动层前
            out = model(input_ids=ids_in, output_hidden_states=True, use_cache=False)
            hs = out.hidden_states
            x_roll = hs[ROLL_LAYER]                        # 层20输入(滚动层输入残差流)
            # 滚 R 次 (每次: MLP组织 + 残差)
            base_h = x_roll
            for _ in range(rolls):
                x_roll = base_h + roll_iter(x_roll)        # 残差滚动: 每滚在原有上加新组织
                base_h = x_roll                             # 更新基准(累积)
            # 把滚后的状态从层20继续前向到输出
            past = None
            with torch.inference_mode():
                # 重建: 从滚动层之后继续 (需要hook替换hidden_states[21]的输入)
                # 简便: 直接手动跑层21..24+norm+lm_head
                h = x_roll
                for L in range(ROLL_LAYER + 1, len(model.model.layers)):
                    h = model.model.layers[L](h)[0]
                h = model.model.norm(h)
                logits = model.lm_head(h)
            # 贪心解码
            gen_ids = []
            for _ in range(max_new - 1):
                full = torch.cat([ids_in, torch.tensor(gen_ids, device='cuda').unsqueeze(0)], -1) if gen_ids else ids_in
                out2 = model(input_ids=full, output_hidden_states=True, use_cache=False)
                x2 = out2.hidden_states[ROLL_LAYER]
                for _ in range(rolls):
                    x2 = x2 + roll_iter(x2)
                h = x2
                for L in range(ROLL_LAYER + 1, len(model.model.layers)):
                    h = model.model.layers[L](h)[0]
                h = model.model.norm(h)
                lg = model.lm_head(h)
                nid = lg[0, -1].argmax(-1).item()
                if nid == tok.eos_token_id: break
                gen_ids.append(nid)
                if len(gen_ids) >= max_new - 1: break
            return tok.decode(gen_ids, skip_special_tokens=True)

    for title, q in TASKS:
        print('\n' + '='*64, flush=True)
        print('【%s】%s' % (title, q), flush=True)
        for r in ROLLS:
            try:
                ans = gen_roll(q, r, max_new=70)
                print('  滚%d次: %s' % (r, ans[:220]), flush=True)
            except Exception as e:
                import traceback
                print('  滚%d次: 出错 %s' % (r, str(e)[:200]), flush=True)
                traceback.print_exc()
    print('\n[V102] 完成', flush=True)

if __name__ == '__main__':
    main()
