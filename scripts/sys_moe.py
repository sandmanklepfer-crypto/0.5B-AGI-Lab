#!/usr/bin/env python3
"""sys_moe.py — 系统级 MoE: 路由器 + 专家模型分工
专家: calc_v1(数学) / v4c(推理+通用) / qwen05b(兜底)
路由: 规则检测题类型 -> 选专家 -> 生成 -> 后处理验证
用法: sys_moe.py [--interactive]
"""
import sys, re, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

EXPERTS = {
    "math": "/root/distill_calc_v1",
    "reason": "/root/distill_v4c",
    "general": "/root/autodl-tmp/qwen05b",
}

class ExpertRouter:
    def __init__(self):
        self.models = {}
        self.toks = {}
        for name, path in EXPERTS.items():
            t = AutoTokenizer.from_pretrained(path); t.pad_token = t.eos_token
            m = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16).to("cuda:0")
            m.eval()
            self.models[name] = m
            self.toks[name] = t
        print(f"[router] experts: {list(EXPERTS.keys())}", flush=True)

    def route(self, q):
        """路由规则: 数学/计算 -> math; 推理/逻辑 -> reason; 否则 general"""
        if re.search(r'[0-9]|计算|等于|解方程|多少|几|圆周|面积|次方|%', q):
            return "math"
        if re.search(r'推理|逻辑|如果|那么|所有|因为|所以|A是|B是|要么|判断', q):
            return "reason"
        return "general"

    def gen(self, name, q, max_new=60):
        t, m = self.toks[name], self.models[name]
        ids = t(q, return_tensors="pt").to("cuda:0")
        with torch.inference_mode():
            out = m.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=t.eos_token_id)
        return t.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

    def resolve_calc(self, text):
        for _ in range(4):
            m = re.search(r'⟨calc⟩(.+?)⟨/calc⟩', text)
            if not m: break
            try:
                v = eval(m.group(1), {"__builtins__": {}}, {"math": __import__("math")})
                v = round(v, 4) if isinstance(v, float) else v
            except Exception:
                v = "?"
            text = text[:m.start()] + str(v) + text[m.end():]
        return text

    def answer(self, q):
        expert = self.route(q)
        ans = self.gen(expert, q)
        # 数学专家: calc 后处理; 其他: 形式检查(重复/模板)
        if expert == "math":
            ans = self.resolve_calc(ans)
        else:
            if len(set(ans)) < len(ans) * 0.3 or len(ans) < 4:
                # 专家输出崩坏 -> 换专家兜底
                backup = "general" if expert != "general" else "reason"
                ans = self.gen(backup, q)
        return expert, ans

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qs", nargs="*", default=[
        "7乘以8等于多少？", "17+25等于多少？", "半径为5的圆周长（π=3.14）？",
        "所有的A都是B，所有的B都是C，那么A是什么？",
        "如果下雨路会湿，路没湿，今天下雨了吗？",
        "太阳从哪边升起？", "水的沸点是多少度？",
    ])
    args = ap.parse_args()
    router = ExpertRouter()
    print("=== 系统级 MoE 测试 ===", flush=True)
    for q in args.qs:
        expert, ans = router.answer(q)
        ok = "✅" if (expert == "math" and any(c.isdigit() for c in ans)) or \
                    (expert == "reason" and len(ans) > 6 and len(set(ans)) > len(ans) * 0.5) else "❌"
        print(f"  {ok} [{expert}] {q[:24]} -> {ans[:80]}", flush=True)

if __name__ == "__main__":
    main()
