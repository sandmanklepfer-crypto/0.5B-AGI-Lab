p = "/root/fix_template.py"
s = open(p).read()
old = 'MODEL = "/root/autodl-tmp/distill_out_15b"'
new = 'MODEL = "/root/autodl-tmp/distill_out_3b"'
if old not in s:
    # 可能带单引号
    old = "MODEL = '/root/autodl-tmp/distill_out_15b'"
    new = "MODEL = '/root/autodl-tmp/distill_out_3b'"
assert old in s, f"NOT FOUND: {old}"
s = s.replace(old, new)
open(p, "w").write(s)
print("PATCH_FIX3B_OK")
