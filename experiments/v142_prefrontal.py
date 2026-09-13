#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V142 前额叶控制器 — 架构创新: 0.5B执行脑 + 元认知控制层
不训练任何权重。纯运行时架构:
  0.5B = 系统1(快糙): 生成候选步骤
  控制器 = 系统2(元认知): 观察0.5B状态, 决策:
    - 继续: 这步合理, 推进
    - 重想: 这步可疑(自评低/自相矛盾), 换角度重生成
    - 查证: 需要外部记忆(规则池检索)
    - 完成: 自评通过, 输出
控制器决策信号(全来自0.5B自身状态, 无外部裁判):
  ① 自评: 让0.5B给自己的步骤打分("这步对吗 0-10") = 内部校验
  ② 矛盾检测: 新步骤与历史步骤的激活cos (低=可能跑题/矛盾)
  ③ 完成检测: 自评≥阈且包含答案特征
对照: 无控制器(0.5B直答) vs 有控制器(元认知循环)
验证: 多步题正确率是否提升(0.5B原来必错的那种)
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
QS = [
    ('年龄', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？', '5'),
    ('蜗牛', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？', '8'),
    ('和尚', '有100个和尚吃100个馒头，大和尚每人吃3个，小和尚每3人吃1个，大小和尚各几人？', '25,75'),
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    print('[V142] 前额叶控制器 | 0.5B执行脑 + 元认知层 | 不训练纯架构', flush=True)

    def gen(prompt, max_new=40):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    # 无控制器基线
    def baseline(q):
        return gen('请解答：%s\n答案：' % q, 80)

    # 控制器循环
    def controlled(q, max_steps=4):
        history = []
        for step in range(max_steps):
            # 执行脑生成一步
            ctx = '\n'.join('第%d步:%s' % (i+1, h) for i, h in enumerate(history))
            step_txt = gen('题目：%s\n%s\n下一步推理(只写一句，具体数字)：' % (q, ctx or '（还没开始）'), 45)
            history.append(step_txt)
            # 控制器: 自评(0.5B当judge)
            judge = gen('检查这步推理对不对："%s"\n这步对吗？只答：对/不对/不确定' % step_txt, 10)
            # 控制器: 完成检测(有答案数字?)
            import re
            nums = re.findall(r'\d+', step_txt)
            if ('对' in judge or '正确' in judge) and len(nums) >= 1 and step >= 1:
                # 再验证一次整体
                final_check = gen('完整过程：%s\n最终答案是多少？只给数字：' % (' '.join(history)), 20)
                return final_check, history, step+1
            # 若自评不对 → 重想(下轮自动换角度)
            if '不对' in judge or '错误' in judge:
                history = history[:-1]  # 丢弃错步(控制器剪枝)
                history.append('（重新想）')
        return gen('完整过程：%s\n最终答案：' % (' '.join(history)), 30), history, max_steps

    print('\n=== 无控制器(基线) ===', flush=True)
    for tag, q, gold in QS:
        a = baseline(q)
        print('[%s] 标准=%s | 直答=%s' % (tag, gold, a[:70].replace('\n',' ')), flush=True)
    print('\n=== 有控制器(元认知循环) ===', flush=True)
    for tag, q, gold in QS:
        ans, hist, n = controlled(q)
        print('[%s] 标准=%s | 控制器输出=%s | 用了%d步' % (tag, gold, ans[:70].replace('\n',' '), n), flush=True)
        print('   步骤: %s' % ' | '.join(h[:25] for h in hist[:3]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
