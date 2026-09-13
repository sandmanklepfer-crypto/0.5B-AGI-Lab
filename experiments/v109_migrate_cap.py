#!/usr/bin/env python3
# V109 能力迁移: king(叙事)+v70(逻辑)+distill05(答题) → antiheb融合体
# 方法: 每源模型与融合体同架构(896/24), 计算 delta=src-fusion, 按层受控比例叠加(干净配方)
import os, shutil
import torch
from safetensors.torch import load_file, save_file
from transformers import AutoModelForCausalLM, AutoTokenizer

FUSION = '/root/autodl-tmp/life1/antiheb_05b'
SOURCES = [('king', '/root/autodl-tmp/king_narr_ft'),
           ('v70', '/root/autodl-tmp/life1/v70_logic_05b'),
           ('distill05', '/root/autodl-tmp/distill_05b_unified_v2')]
OUT = '/root/autodl-tmp/life1/antiheb_super_05b'
SCALE = 0.08

def main():
    print('[V109] 迁移: king+v70+distill05 -> antiheb_super', flush=True)
    fusion = load_file(FUSION + '/model.safetensors', device='cpu')
    W = {k: v.float().clone() for k, v in fusion.items()}
    for name, src_dir in SOURCES:
        print('处理 %s ...' % name, flush=True)
        src = load_file(src_dir + '/model.safetensors', device='cpu')
        n = 0
        for k in fusion.keys():
            if k in src and fusion[k].shape == src[k].shape:
                d = (src[k].float() - W[k])
                dn = d.norm().item()
                if dn < 1e-6:
                    continue
                wnorm = W[k].norm().item() + 1e-9
                scale = min(SCALE * wnorm / dn, 0.5)
                W[k] = W[k] + d * scale
                n += 1
        print('  已迁移 %d 个权重 (比例<=%.3f)' % (n, SCALE), flush=True)
    os.makedirs(OUT, exist_ok=True)
    save_file({k: v.to(torch.bfloat16) for k, v in W.items()}, OUT + '/model.safetensors')
    for f in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt',
              'special_tokens_map.json', 'added_tokens.json', 'generation_config.json']:
        p = os.path.join(FUSION, f)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(OUT, f))
    print('[V109] 融合体已存: %s' % OUT, flush=True)
    # 测试
    tok = AutoTokenizer.from_pretrained(OUT)
    model = AutoModelForCausalLM.from_pretrained(OUT, torch_dtype=torch.bfloat16).to('cuda').eval()
    tests = [('逻辑', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
             ('叙事', '在深秋的傍晚，一个老人在湖边点了一支烟，想起了'),
             ('知识', '中国的首都是哪里？')]
    for tag, q in tests:
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            o = model.generate(ids, max_new_tokens=60, do_sample=False,
                               repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        a = tok.decode(o[0][len(ids[0]):], skip_special_tokens=True)
        print('【%s】%s\n  -> %s' % (tag, q, a[:140]), flush=True)
    print('[V109] 完成', flush=True)

if __name__ == '__main__':
    main()
