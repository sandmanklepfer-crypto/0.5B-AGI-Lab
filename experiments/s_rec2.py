# -*- coding: utf-8 -*-
"""★ 验证: 把"递归形式"加进搜索空间, 能不能命中?"""
import numpy as np, itertools
SEQ=[2,7,20,57,166]; TRUE=[491,1464]
print("="*92); print("★ 加入【递归形式】后的搜索"); print("="*92, flush=True)
print(f"  数列: {SEQ}   真值: {TRUE}", flush=True)

# 形式扩展: a_n = c*a_{n-1} + d*n + e
print("\n  搜索形式: a_n = c·a_(n-1) + d·n + e", flush=True)
best=None
for c in range(1,6):
    for d in range(-20,21):
        for e in range(-20,21):
            def recc(k, c=c, d=d, e=e):
                v=SEQ[0]
                for i in range(2,k+1):
                    v=c*v + d*i + e
                return v
            ok=all(recc(k)==SEQ[k-1] for k in range(1,6))
            if ok:
                pred=[recc(6),recc(7)]
                if pred==TRUE: best=(c,d,e,pred)
                break
        if best: break
    if best: break
print(f"  {'✅ 命中: a_n = %d·a_(n-1) + %d·n + %d -> 预测 %s' % best if best else '❌'}",
      flush=True)

# 对照: 不加递归形式时(封闭公式搜索)的结果
print("\n  对照: 【没有】递归形式时 -> 前面已验证: ❌ 搜不到", flush=True)

print("\n"+"="*92); print("★ 关键对比: 三种'形式'的覆盖范围"); print("="*92, flush=True)
CASES=[
 ("封闭公式 (多项式/指数)", [1,4,9,16,25], [36,49], "n^2", "✅ 能"),
 ("封闭公式+组合",         [3,8,15,24,35], [48,63], "n^2+2n", "✅ 能"),
 ("递归形式",              [2,7,20,57,166], [491,1464], "3a_(n-1)-(2n-5)", "✅ 加进去就能"),
 ("不动点/隐式",           [1,1,2,3,5,8], [13,21], "fib: a_n=a_(n-1)+a_(n-2)", "⚠️ 需专门形式"),
]
print(f"  {'形式':<24}{'例子':<22}{'结果'}", flush=True)
print("  "+"-"*74, flush=True)
for form,seq,nxt,note,ok in CASES:
    print(f"  {form:<24}{note:<22}{ok}", flush=True)
print("\n"+"="*92); print("★ 结论: '像人一样' = 需要多少种'形式'?"); print("="*92, flush=True)
print("""  人类解题时, 会自然地尝试不同【形式】:
     多项式? 指数? 递归? 差分方程? 隐式? 集合? 图论? 拓扑?

  ★ 每加一种形式, 能解决的问题域就扩大一圈
  ★ 而"发明新形式" (如微积分/群论) 才是真正的原创
  ★ 系统能"在给定形式内搜到极致", 但"新形式"要靠人给
""", flush=True)
print("REC2_DONE")
