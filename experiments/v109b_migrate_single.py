#!/usr/bin/env python3
# V109b 单源小步迁移: 只迁 v70逻辑 到 antiheb_05b, SCALE=0.02 (v81安全幅度低端)
# 逐步: 迁移→验证不崩→(可再加幅度或加源)
import os, shutil, copy
import numpy as np
import torch
from safetensors.torch import load_file, save_file
from transformers import AutoModelForCausalLM, AutoTokenizer

FUSION = '/root/autodl-tmp/life1/antiheb_05b'
SRC    = '/root/autodl-tmp/life1/v70_logic_05b'
OUT    = '/root/autodl-tmp/life1/antiheb_v70_05b'
SCALE  = 0.02

def gen(model, tok, q, max_new=60):
    ids = tok(q, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode():
        o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                           repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()

def main():
    print('[V109b] 单源小步迁移: v70逻辑 -> antiheb (SCALE=0.02)', flush=True)
    fusion = load_file(FUSION + '/model.safetensors', device='cpu')
    src = load_file(SRC + '/model.safetensors', device='cpu')
    tok = AutoTokenizer.from_pretrained(FUSION)

    # 基线: 迁移前 回答(不崩参照)
    model0 = AutoModelForCausalLM.from_pretrained(FUSION, torch_dtype=torch.bfloat16).to('cuda').eval()
    print('\n=== 迁移前 (antiheb_05b) ===', flush=True)
    for tag, q in [('逻辑', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
                   ('常识', '中国的首都是哪里？'),
                   ('正常', '你好，请介绍一下自己')]:
        print('【%s】%s\n  -> %s' % (tag, q, gen(model0, tok, q)[:120]), flush=True)
    del model0; torch.cuda.empty_cache()

    # 计算 delta, 只取 src 明显不同于 fusion 的层, 小步叠加
    W = {k: v.float().clone() for k, v in fusion.items()}
    n = 0; total_dn = 0.0
    for k in fusion.keys():
        if k in src and fusion[k].shape == src[k].shape:
            d = (src[k].float() - fusion[k].float())
            dn = d.norm().item()
            if dn < 1e-5: continue
            wnorm = W[k].norm().item() + 1e-9
            scale = min(SCALE * wnorm / dn, 0.2)   # 受控: 至多该层范数2%
            W[k] = W[k] + d * scale
            n += 1; total_dn += dn * scale
    print('\n迁移 %d 权重, 总移动范数=%.1f' % (n, total_dn), flush=True)
    os.makedirs(OUT, exist_ok=True)
    save_file({k: v.to(torch.bfloat16) for k, v in W.items()}, OUT + '/model.safetensors')
    for f in ['config.json', 'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt',
              'special_tokens_map.json', 'added_tokens.json', 'generation_config.json']:
        p = os.path.join(FUSION, f)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(OUT, f))
    print('已存: %s' % OUT, flush=True)

    # 迁移后测试
    model1 = AutoModelForCausalLM.from_pretrained(OUT, torch_dtype=torch.bfloat16).to('cuda').eval()
    print('\n=== 迁移后 (antiheb_v70_05b) ===', flush=True)
    for tag, q in [('逻辑', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
                   ('常识', '中国的首都是哪里？'),
                   ('正常', '你好，请介绍一下自己')]:
        print('【%s】%s\n  -> %s' % (tag, q, gen(model1, tok, q)[:140]), flush=True)
    print('\n[V109b] 完成 (若迁移后逻辑更好且常识/正常不崩 = 小步单源迁移成功)', flush=True)

if __name__ == '__main__':
    main()
