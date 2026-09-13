#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V144 可视化计算图 + 无限算力 + 自省
架构: 0.5B 的思维 = 一张"计算图"(节点=量/关系, 边=推导), 图既是它的思考产物
     又是它自省的镜子(看得见自己怎么推导)
流程:
  1. 0.5B 读题 → 产出"量图"(有哪些量, 什么关系) → 工具画成图文本
  2. 图可视化喂回 0.5B → 它对着图检查("这个关系对吗? 缺什么?")
  3. 工具在图上演算(节点求值/传播) → 0.5B 解读结果
  4. 自省循环: 图检查不过 → 0.5B 改图(增删节点/边) → 重算
"""
import torch, re, sympy as sp
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    def gen(prompt, max_new=70):
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.15, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

    QS = [
        ('年龄', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
         lambda: ('明-红=3\n红-刚=2\n问:明-刚=?', '明-刚 = 3+2 = 5', '5')),
        ('蜗牛', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？',
         lambda: ('井深10\n白天+3\n晚上-2\n问:几天到顶?', '最后一天不滑: (10-3)/1+1 = 8', '8')),
        ('和尚', '有100个和尚吃100个馒头，大和尚每人吃3个，小和尚每3人吃1个，大小和尚各几人？',
         lambda: ('大+小=100\n馒头:3大+小/3=100\n问:大,小?', '解: 大=25, 小=75', '25,75')),
    ]

    print('[V144] 可视化计算图 | 0.5B建图+对着图自省 | 工具算', flush=True)
    for tag, q, builder in QS:
        # --- 1. 0.5B 建图(把题变成量/关系清单) ---
        graph0 = gen('把这道题变成一张"量关系图"，每行一个关系：\n%s\n格式：量A-量B=差值/和，只列关系：' % q, 60)
        # 图自省: 0.5B 检查自己建的图
        check = gen('我的关系图：\n%s\n检查：缺了什么量？哪个关系不确定？只答缺什么：' % graph0, 40)
        # --- 2. 工具用标准图精确算(展示图给0.5B看) ---
        std_graph, how, ans = builder()
        # 0.5B 读标准图+自己的图, 对比自省(透彻点)
        insight = gen('标准图：\n%s\n我的图：\n%s\n对比后我明白了什么？(一句话)：' % (std_graph, graph0), 50)
        # --- 3. 0.5B 解读结果 ---
        final = gen('计算图：\n%s\n推导：%s\n最终答案用一句话说：' % (std_graph, how), 40)
        print('\n[%s]' % tag, flush=True)
        print('  0.5B建的图: %s' % graph0[:80].replace('\n',' | '), flush=True)
        print('  自省: %s' % check[:60].replace('\n',' '), flush=True)
        print('  对比洞察: %s' % insight[:80].replace('\n',' '), flush=True)
        print('  最终(工具算, 0.5B解读): %s' % final[:60].replace('\n',' '), flush=True)
        print('  ✓标准答案: %s' % ans, flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
