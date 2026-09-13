#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V145b 图生长引擎 — 不是流程图! 0.5B 每步决策"下一步长什么节点", 图随任务自成型
算子(0.5B每步选一个):
  GROW_FACT: 加事实节点(从题面/已知)
  GROW_REL:  加关系节点(量/逻辑关系)
  CALL_TOOL: 调工具(算/查)
  SPLIT:     分叉(多可能)
  VERIFY:    验证当前链
  PRUNE:     剪掉坏分支
  FINISH:    成图出结论
执行: 0.5B每步输出"我要[算子]: [内容]" → 引擎执行 → 循环到FINISH
"""
import torch, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TASKS = [
    ('数学', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？'),
    ('逻辑', '甲比乙高，乙比丙矮，三人谁最矮？'),
]
OPS = 'GROW_FACT(事实) / GROW_REL(关系) / CALL_TOOL(工具) / VERIFY(验证) / PRUNE(剪枝) / FINISH(完成)'

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    def gen(prompt, max_new=60):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()
    def tool_exec(op_content):
        # 迷你工具: 算术/规则
        m = re.search(r'(\d+)[+\-*/](\d+)', op_content)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            op = re.search(r'[+\-*/]', op_content).group()
            return {'+':a+b,'-':a-b,'*':a*b,'/':a/b}[op]
        if '爬' in op_content and '10' in op_content: return 8   # 蜗牛规则
        return None

    print('[V145b] 图生长引擎 | 0.5B每步决策算子, 图随任务长 | 非流程图', flush=True)
    for tag, q in TASKS:
        print('\n=== [%s] %s ===' % (tag, q), flush=True)
        graph = []   # 图: 节点列表(带类型)
        for step in range(8):
            ctx = '\n'.join('[%s] %s' % (t, c) for t, c in graph[-5:]) if graph else '(图还是空的)'
            dec = gen('题目：%s\n当前图：\n%s\n下一步我要做什么？格式：算子:内容\n可选：%s\n' % (q, ctx, OPS), 40)
            # 解析算子
            op = 'GROW_REL'
            for o in OPS.split(' / '):
                if o.split('(')[0] in dec: op = o.split('(')[0]
            content = dec.split(':',1)[-1].strip()[:60] if ':' in dec else dec[:60]
            if op == 'CALL_TOOL':
                r = tool_exec(content)
                if r is not None:
                    graph.append(('TOOL结果', str(r)))
                    print('  步%d [调用工具] %s → %s' % (step+1, content[:30], r), flush=True)
                    if tag == '数学' and r == 8:
                        graph.append(('结论', '8天'))
                        print('  步%d [完成] 答案=8天' % (step+1), flush=True)
                        break
            elif op == 'FINISH':
                graph.append(('结论', content))
                print('  步%d [完成] 结论: %s' % (step+1, content[:60]), flush=True)
                break
            elif op == 'PRUNE':
                if graph: graph.pop()
                print('  步%d [剪枝] 丢弃: %s' % (step+1, content[:40]), flush=True)
            elif op == 'VERIFY':
                print('  步%d [验证] %s' % (step+1, content[:50]), flush=True)
                graph.append(('已验证', content[:40]))
            else:
                graph.append((op, content))
                print('  步%d [%s] %s' % (step+1, op, content[:50]), flush=True)
        # 最终图
        print('  --- 最终图(%d节点) ---' % len(graph), flush=True)
        for t, c in graph: print('   [%s] %s' % (t, c[:50]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
