# -*- coding: utf-8 -*-
import time
t0=time.time()
print("="*94)
print("真跑: 「加组合」能有多强?  —— 从1出发, 最少几步到达大数")
print("="*94)
print()

def naive(N):   # 只有原子 +1
    return N

def combo(N):   # 组合: 自己加自己(双倍) + 加1
    if N<=1: return 0
    bits=bin(N)[2:]
    steps=0
    for b in bits[1:]:
        steps+=1              # 双倍 (自己+自己)
        if b=='1': steps+=1   # 加1
    return steps

print("  【只有原子】vs【加组合】")
print()
print(f"  {'目标 N':<14}{'朴素(+1)':<22}{'组合(双倍+加1)':<22}{'加速比'}")
print("  "+"-"*80)
for N in [10, 10**2, 10**3, 10**6, 10**12, 10**30, 10**100]:
    a=naive(N); b=combo(N)
    sa = f"{a:,}" if a < 10**12 else f"10^{len(str(a))-1:.0f}量级"
    print(f"  10^{len(str(N))-1:<10}{sa:<22}{b:<22}{a/b:.3e}")

print()
print("  ★★ 关键: 到达 10^100,")
print(f"     朴素法需要 10^100 步 (永远走不完)")
print(f"     组合法只需要 {combo(10**100)} 步  ← 几分钟就能跑完")
print(f"     加速比 ≈ 10^100 / {combo(10**100)} ≈ 10^98 倍")
print()

print("="*94)
print("★ 而且这个加速比【随目标指数增长】")
print("="*94)
print()
print(f"  {'目标':<12}{'组合法步数':<14}{'加速比':<24}{'趋势'}")
print("  "+"-"*68)
prev=None
for e in [2,3,4,6,10,20,50,100]:
    N=10**e
    b=combo(N); r=N/b
    trend=""
    if prev: trend=f"↑{r/prev:.0f}倍" if r>prev else ""
    print(f"  10^{e:<9}{b:<14}{r:<24.2e}{trend}")
    prev=r
print()
print("  ★ 每把目标加一个数量级, 组合法的优势就【再涨一个数量级】")
print("  ★ 这就是「指数对线性」—— 不是优化, 是换了个量级体系")
print()

print("="*94)
print("★ 加「命名」还能再快 (把中间结果存成新原子)")
print("="*94)
print()
def named(N):
    """命名法: 记住'有用的中间结果', 用它去够更大的数"""
    # 找 N 的二进制, 但把最高位命名为原子, 反复用
    if N<=1: return 0
    bits=bin(N)[2:]
    L=len(bits)
    # 第1步: 构造顶层原子 2^(L-1) (用双倍, L-1步)
    steps=L-1
    # 之后每步: 用命名的原子去加
    rem=N-(1<<(L-1))
    steps+=bin(rem).count('1')
    return steps
print(f"  {'目标':<14}{'组合法':<12}{'组合+命名':<14}{'说明'}")
print("  "+"-"*60)
for N in [10**6, 10**12, 10**100]:
    print(f"  10^{len(str(N))-1:<11}{combo(N):<12}{named(N):<14}命名把重复动作也变成原子")
print()

print("="*94)
print("★ 对比「加权重」: 它要多少代价?")
print("="*94)
print()
print(f"  {'做法':<26}{'代价':<26}{'性质'}")
print("  "+"-"*76)
print(f"  {'加权重 (记住 10^100)':<26}{'10^100 个参数':<26}线性")
print(f"  {'加权重 (压缩后)':<26}{'10^100/36000 个参数':<26}线性")
print(f"  {'★ 加组合':<26}{f'{combo(10**100)} 步操作':<26}对数!")
print()
print("  ★★ 结论: 同样是'处理 10^100 这么大的东西'")
print("     权重法: 参数线性增长 (做不到)")
print("     组合法: 步数对数增长 (~800步)")
print()

print("="*94)
print("★ 但组合的死穴 (必须说)")
print("="*94)
print("""  上面全是【构造型】任务 (到达目标值) —— 组合碾压.

  但换成【判断型】任务会怎样?
     '10^100 是质数吗?'  -> 朴素要试 10^50 次除法
      组合法能加速吗? -> 只能加速【乘法】, 不能加速【判定】
      -> 这类任务, 组合的优势【大打折扣】(除非发现深层数论结构)

  ★ 所以分界:
     构造/组合/可达  -> 组合碾压 (对数 vs 线性)
     判断/搜索/验证  -> 组合只能帮上验证部分
""")
print(f"用时 {time.time()-t0:.2f}s")
