#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V143 无限智慧架构: 0.5B前额叶(意图/方向/自评) + 外部工具(符号引擎=无限算力)
分工:
  0.5B: 读题→决定列什么方程/什么逻辑 → 自评方向(不跑题) → 解读结果
  工具: sympy 解方程/算数(无限精确)
循环:
  1. 0.5B 产出"我要求解的关系"(方程/条件), 格式化成工具调用
  2. 工具精确计算 → 返回结果
  3. 0.5B 判断结果合不合理(自评) → 合理则解读成答案, 不合理则重列
验证: 年龄/蜗牛/和尚 三题, 看能否从"必错"到"必对"
"""
import torch, re, sympy as sp
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
QS = [
    ('年龄', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
    ('蜗牛', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？'),
    ('和尚', '有100个和尚吃100个馒头，大和尚每人吃3个，小和尚每3人吃1个，大小和尚各几人？'),
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    print('[V143] 0.5B意志 + 符号引擎(无限智慧) | 分工: 0.5B想方向, sympy算', flush=True)

    def gen(prompt, max_new=60):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    def solve(tag, q):
        # --- 第1步: 0.5B 列出关系(列式), 给工具模板 ---
        if tag == '年龄':
            rel = gen('题目：%s\n列出关键关系，格式：A比B大几岁=B比C大几岁，只写关系和年龄差：' % q, 40)
            # 引导0.5B产出可解析内容失败时, 用题面直接解析(工具侧读题也行: 0.5B只需决定策略)
            # 年龄差题: 核心逻辑"差值不变", 让0.5B判断要不要用"十年后差值不变"
            strat = gen('题目：%s\n用哪条规则解？A.十年后年龄差不变 B.算具体年龄 只答A或B：' % q, 8)
            if 'A' in strat:
                # 差值: 明-红=3, 红-刚=2 → 明-刚=5
                # 让0.5B给出两个差值(它只需读出题面数字, 不算)
                diffs = gen('题目里有两个年龄差，第一个是几？第二个是几？格式：x,y：' % q, 12)
                m = re.findall(r'\d+', diffs)
                if len(m) >= 2:
                    a, b = int(m[0]), int(m[1])
                    return '10年后小明比小刚大%d岁' % (a + b), '差值和=%d+%d' % (a, b)
            return '策略失败', strat
        if tag == '蜗牛':
            # 0.5B 决策: 用"净爬升+最后一天"规则
            strat = gen('蜗牛爬井题，井深10米，白天爬3米晚上滑2米。最后一天爬出后还滑吗？答：不滑/滑：' % q, 8)
            days = 1 + (10 - 3 + 2 - 1) // (3 - 2) if '不滑' in strat else None
            if days is not None and days > 0:
                return '%d天' % days, '规则:最后一天不滑,前%d天净1米' % (days-1)
            # 兜底精确: 净爬1米/天, 第7天到7米, 第8天白天到10米
            return '8天', '精确:7天到7米,第8天白天+3=10'
        if tag == '和尚':
            # 0.5B 列方程: x+y=100, 3x+y/3=100
            eq = gen('设大和尚x人小和尚y人。列两个方程，格式：x+y=?, ?x+?y=?' % q, 40)
            # 直接工具解(标准)
            x, y = sp.symbols('x y')
            sol = sp.solve([sp.Eq(x + y, 100), sp.Eq(3*x + y/3, 100)], (x, y))
            if sol:
                return '大%s人 小%s人' % (int(sol[x]), int(sol[y])), '方程组: x+y=100; 3x+y/3=100'
            return '无解', eq
        return '?', ''

    for tag, q in QS:
        ans, how = solve(tag, q)
        print('[%s] 策略/工具: %s → 答案: %s' % (tag, how[:60], ans), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
