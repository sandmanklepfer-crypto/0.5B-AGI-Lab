import torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
torch.set_num_threads(8)
t0=time.time()
print("="*76); print("用 transformers 直接跑 (CPU)"); print("="*76, flush=True)

TCS=[
 ("7乘以8","计算：7乘以8等于多少？"),
 ("3x=21","解方程：3x=21，求x。"),
 ("2的10次方","计算 2 的 10 次方。"),
 ("12+34","12加34等于多少？"),
 ("25乘4","计算：25乘以4等于多少？"),
 ("逻辑","如果A大于B，B大于C，那么A和C谁大？"),
]
for path,name in [("/root/distill_calc_v1","计算蒸馏 calc_v1"),
                  ("/root/qwen25_base_raw","BASE 原始模型")]:
    print(f"\n{'#'*70}\n##### {name} #####", flush=True)
    try:
        tok=AutoTokenizer.from_pretrained(path, trust_remote_code=True)
        md=AutoModelForCausalLM.from_pretrained(path, torch_dtype=torch.float32)
        md.eval()
        print(f"  加载完成 {time.time()-t0:.0f}s", flush=True)
        for tag,q in TCS:
            try:
                msgs=[{"role":"user","content":q}]
                txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
            except Exception:
                txt=q+"\n"
            ids=tok(txt,return_tensors="pt").input_ids
            with torch.no_grad():
                o=md.generate(ids,max_new_tokens=25,do_sample=False,
                              pad_token_id=tok.eos_token_id or 0)
            a=tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True).strip().replace("\n"," ")
            print(f"  [{tag}] {q}\n      -> {a[:110]}", flush=True)
        del md
    except Exception as e:
        print(f"  ❌ {str(e)[:130]}", flush=True)
print("\nPY_DONE")
