# 生成 3B 蒸馏训练脚本 (基于 1.5B 版)
src = "/root/autodl-tmp/distill_train_15b.py"
dst = "/root/autodl-tmp/distill_train_3b.py"
s = open(src).read()
old_new = [
    ("STUDENT = '/root/qwen15b'", "STUDENT = '/root/autodl-tmp/qwen3b'"),
    ("OUT_DIR = '/root/autodl-tmp/distill_out_15b'", "OUT_DIR = '/root/autodl-tmp/distill_out_3b'"),
]
for o, n in old_new:
    assert o in s, f"NOT FOUND: {o}"
    s = s.replace(o, n)
open(dst, "w").write(s)
print("PATCH_3B_OK")
