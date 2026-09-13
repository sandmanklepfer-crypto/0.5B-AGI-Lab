p = "/root/autodl-tmp/distill_train_15b.py"
s = open(p).read()
old_new = [
    ("STUDENT = '/root/autodl-tmp/qwen05b'", "STUDENT = '/root/qwen15b'"),
    ("DATA_DIRS = ['/root/autodl-tmp/distill_data_a', '/root/autodl-tmp/distill_data_b']",
     "DATA_DIRS = ['/root/autodl-tmp/distill_data_full_a', '/root/autodl-tmp/distill_data_full_b']"),
    ("OUT_DIR = '/root/autodl-tmp/distill_out'", "OUT_DIR = '/root/autodl-tmp/distill_out_15b'"),
]
for o, n in old_new:
    assert o in s, f"NOT FOUND: {o}"
    s = s.replace(o, n)
open(p, "w").write(s)
print("PATCH_OK")
