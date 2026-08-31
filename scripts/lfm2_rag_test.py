import torch, time, sys
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer
t0 = time.time()
tok = AutoTokenizer.from_pretrained("/root/lfm2-rag")
model = AutoModelForCausalLM.from_pretrained("/root/lfm2-rag", dtype=torch.bfloat16, device_map="cuda:0")
print("loaded in", round(time.time()-t0,1), "s", flush=True)
doc = "比特币是2008年由化名「中本聪」的人提出的去中心化数字货币，2009年正式运行。比特币总量被限制为2100万个，每四年区块奖励减半（从50枚开始）。截至2024年，比特币已产生约1970万个。"
q = "比特币的总量上限是多少？谁提出了比特币？"
msgs = [{"role": "user", "content": f"Use the following context to answer questions:\n{doc}\n\nQuestion: {q}"}]
text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
print("PROMPT:", text[:120].replace(chr(10)," "), flush=True)
ids = tok(text, return_tensors="pt").to("cuda:0")
with torch.inference_mode():
    out = model.generate(**ids, max_new_tokens=128, do_sample=False, pad_token_id=tok.eos_token_id)
print("ANSWER:", tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip(), flush=True)
