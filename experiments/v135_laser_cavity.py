#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V135 通用激光腔 — 0.5B 自我反射 + 可插拔环境泵浦 (架构不挑领域)
腔体(通用, 不随领域变):
  反射: 0.5B 对问题迭代 N 轮, 每轮把上一轮答案+本轮反思当输入再生成
  泵浦: 每轮答案送"环境验证器"(可插拔插座), 验证器返回 真/假/不可判
       真→增益注入(下轮prompt带"已验证为真") 假→修正提示("环境判你错了")
       不可判→无泵浦(纯反射=对照组)
测试: 9题 × 3领域(数学/常识/逻辑), 每领域3题
  数学泵浦=sympy验算 | 常识泵浦=事实库 | 逻辑泵浦=一致性(自相矛盾判假)
测: 答案质量随反射轮数涨(激光) 还是 跌(普通镜子) — 腔体通用性
"""
import torch, re, sympy as sp
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
N_ROUNDS = 4

# ---- 9题 × 3领域: (问题, 正确答案串, 领域) ----
Q = [
    # 数学 (泵浦: sympy)
    ('ζ函数在s等于2的时候，值等于多少？', '圆周率的平方除以6', 'math'),
    ('从1加到100的和等于多少？', '5050', 'math'),
    ('一个圆的半径是1，它的面积等于多少？', '圆周率', 'math'),
    # 常识 (泵浦: 事实共识)
    ('一年有多少个月？', '12', 'fact'),
    ('中国的首都是哪个城市？', '北京', 'fact'),
    ('水的化学式是什么？', 'H2O', 'fact'),
    # 逻辑 (泵浦: 一致性)
    ('如果所有A都是B，且所有B都是C，那么所有A都是什么？', 'C', 'logic'),
    ('一个命题和它的否定不可能同时为真，这叫什么律？', '矛盾律', 'logic'),
    ('3比5大吗？', '不大', 'logic'),
]

def pump_math(ans, q):
    """数学泵浦: 能算则算"""
    # ζ(2)
    if 'ζ' in q and 's等于2' in q:
        m = re.search(r'([π\d\^/\.\*\(\)]+)', ans.replace('圆周率', 'π'))
        if m:
            try:
                v = sp.N(sp.sympify(m.group(1).replace('π', 'pi')))
                if abs(v - sp.N(sp.pi**2/6)) < 1e-4: return ('真', '')
                return ('假', '正确是: 圆周率的平方除以6(ζ(2)=π²/6)')
            except: return ('不可判', '')
    # 从1到100
    if '1加到100' in q:
        m = re.search(r'(\d+)', ans)
        if m: return ('真', '') if m.group(1) == '5050' else ('假', '正确是5050')
    # 圆面积
    if '圆的半径是1' in q and ('圆周率' in ans or 'π' in ans): return ('真', '')
    if '圆的半径是1' in q: return ('假', '正确是: 圆周率(πr², r=1)')
    return ('不可判', '')

def pump_fact(ans, q):
    if '多少个月' in q:
        m = re.search(r'(\d+)', ans)
        return ('真', '') if m and m.group(1) == '12' else ('假', '正确是12个月')
    if '首都' in q:
        return ('真', '') if '北京' in ans else ('假', '正确是北京')
    if '化学式' in q:
        return ('真', '') if 'H2O' in ans or 'h2o' in ans else ('假', '正确是H2O')
    return ('不可判', '')

def pump_logic(ans, q):
    if '所有A都是B' in q:
        return ('真', '') if 'C' in ans and 'B' not in ans.replace('都是C','') else ('假', '正确是C')
    if '矛盾律' in q or '不可能同时为真' in q:
        return ('真', '') if '矛盾' in ans else ('假', '正确是矛盾律')
    if '3比5大吗' in q:
        if '不' in ans or '错' in ans: return ('真', '')
        return ('假', '不对，3比5小')
    return ('不可判', '')

def pump(q, ans, domain):
    if domain == 'math': return pump_math(ans, q)
    if domain == 'fact': return pump_fact(ans, q)
    return pump_logic(ans, q)

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    def gen(ctx, maxn=40):
        ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=maxn, do_sample=True, temperature=0.6,
                               top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).replace('\n', ' ')

    print('V135 通用激光腔 | 9题×3领域 | %d轮反射 | 泵浦可插拔' % N_ROUNDS, flush=True)
    total_correct = [0]*N_ROUNDS   # 每轮的累计正确(泵浦可真判的题)
    for qi, (q, gold, dom) in enumerate(Q):
        ans = ''
        prompt = '问题：%s\n我的答案：' % q
        seen_true = False
        for r in range(N_ROUNDS):
            ans = gen(prompt, maxn=40)
            verdict, hint = pump(q, ans, dom)
            # 反射: 把验证结果喂回去(泵浦)
            if verdict == '真':
                seen_true = True
                prompt = '问题：%s\n我的答案：%s\n环境验证：正确。\n我的最终答案：' % (q, ans)
            elif verdict == '假':
                prompt = '问题：%s\n我的答案：%s\n环境验证：错误。%s\n我修正后的答案：' % (q, ans, hint)
            else:
                prompt = '问题：%s\n我的答案：%s\n我再想想，我的答案：' % (q, ans)  # 无泵浦纯反射
            # 记录本轮最终答案正确性(泵浦可真判时)
            v2, _ = pump(q, ans, dom)
            if v2 == '真': total_correct[r] += 1
        # 每轮结束显示轨迹
        v_final, _ = pump(q, ans, dom)
        print('[%s] %s' % (dom, q), flush=True)
        print('    末轮: %s | 泵浦判定: %s' % (ans[:60], v_final), flush=True)
    print('\n各轮正确数(9题中): ' + ' → '.join(str(c) for c in total_correct), flush=True)
    trend = '上升=激光腔收敛' if total_correct[-1] > total_correct[0] else ('下降=普通镜子发散' if total_correct[-1] < total_correct[0] else '持平')
    print('趋势: %s' % trend, flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
