#!/usr/bin/env python3
"""纯群论/对称性数据集生成器 (程序保证正确性 + 算法步骤)
类型A: 模n乘法群 (逆元/阶)
类型B: 二面体群D_n (正多边形对称)
类型C: 置换群S_n (复合/轮换分解/奇偶性)
类型D: Burnside引理 (对称染色)
输出: group_theory.txt (题面), group_theory_steps.txt (程序步骤)
"""
import random, sys

random.seed(11)
OUT_Q = '/root/autodl-tmp/group_theory.txt'
OUT_S = '/root/autodl-tmp/group_theory_steps.txt'

def egcd(a, b):
    if b == 0: return (a, 1, 0)
    g, x, y = egcd(b, a % b)
    return (g, y, x - (a // b) * y)

def mod_inv(a, n):
    g, x, _ = egcd(a % n, n)
    return x % n

def mod_order(a, n):
    a %= n; x = a; k = 1
    while x != 1:
        x = (x * a) % n; k += 1
        if k > n: return None
    return k

def gen_A():
    qs = []
    cases = [(3,7),(5,7),(4,9),(2,11),(3,11),(7,11),(4,13),(5,13),(6,13),(2,15),(7,15),(11,15),
             (3,17),(5,17),(7,17),(3,19),(5,19),(11,19),(3,23),(7,23),(5,29),(7,31),(5,41),(9,41),
             (2,25),(3,25),(4,25),(7,25),(2,27),(5,27),(11,27),(3,37),(5,37),(7,37),(2,49),(3,49)]
    for a, n in cases:
        inv = mod_inv(a, n)
        qs.append((f"在模{n}乘法群中，求元素{a}的乘法逆元。",
                   f"1. 要找 x 使得 {a}×x ≡ 1 (mod {n})\n2. 求 {a} 在模{n}下的逆元：{a}×{inv} = {a*inv} ≡ 1 (mod {n})\n3. 所以 {a} 的逆元是 {inv}",
                   f"答案：{inv}"))
    for a, n in [(2,7),(3,7),(2,9),(4,9),(2,11),(3,11),(2,13),(6,13),(2,17),(3,17),(2,19),(3,19),(2,23),(5,23),(2,29),(3,29)]:
        ord_a = mod_order(a, n)
        if ord_a is None: continue
        qs.append((f"在模{n}乘法群中，求元素{a}的阶（最小的正整数 k 使 a^k ≡ 1 mod {n}）。",
                   f"1. 阶是最小的 k 满足 {a}^k ≡ 1 (mod {n})\n2. 逐步计算幂，找到第一个为 1 的幂次\n3. {a}^{ord_a} = {pow(a,ord_a,n)} ≡ 1 (mod {n})，且更小的幂都不为 1\n4. 所以 {a} 的阶是 {ord_a}",
                   f"答案：{ord_a}"))
    return qs

def gen_B():
    qs = []
    for n in [3,4,5,6,8,10,12]:
        qs.append((f"正{n}边形的对称群（二面体群 D_{n}）一共有多少个对称操作（群的阶）？",
                   f"1. 二面体群 D_n 包含 n 个旋转和 n 个反射\n2. 旋转：0°, {360//n}°, 2×{360//n}°...共 n 个\n3. 反射：共 n 条对称轴（每条对应一个反射操作）\n4. 总数 = n + n = {2*n}",
                   f"答案：{2*n}"))
        qs.append((f"正{n}边形有多少条对称轴（反射轴）？",
                   f"1. 正{n}边形的每条对称轴对应 D_{n} 的一个反射\n2. 对称轴过顶点和对边中点（或两对顶点/两对边中点）\n3. 共 {n} 条对称轴",
                   f"答案：{n}"))
        qs.append((f"正{n}边形绕中心旋转至少多少度后与原图形重合（最小旋转对称角）？",
                   f"1. 旋转对称角 = 360° ÷ 边数\n2. 正{n}边形：360° ÷ {n} = {360//n}°\n3. 所以最小旋转角是 {360//n}°",
                   f"答案：{360//n}度"))
    return qs

def perm_mult(p, q, n):
    return tuple(p[q[i]] for i in range(n))

def perm_cycle_decomp(p):
    n = len(p); seen = [False]*n; cycles = []
    for i in range(n):
        if not seen[i]:
            c = []; j = i
            while not seen[j]:
                seen[j] = True; c.append(j); j = p[j]
            if len(c) > 1: cycles.append(c)
    return cycles

def fmt(t):
    return "(" + " ".join(str(x+1) for x in t) + ")"

def gen_C():
    qs = []
    s3_pairs = [((1,2,0),(2,0,1)), ((2,0,1),(0,2,1)), ((0,2,1),(1,2,0)), ((1,2,0),(0,1,2)), ((2,1,0),(1,0,2))]
    for p, q in s3_pairs:
        r = perm_mult(p, q, 3)
        qs.append((f"置换群 S_3 中，计算 σ∘τ，其中 σ={fmt(p)}，τ={fmt(q)}（先作用 τ 再作用 σ）。",
                   f"1. 复合 (σ∘τ)(i) = σ(τ(i))\n2. 逐元素：i=1: τ(1)={q[0]+1}→σ({q[0]+1})={p[q[0]]+1}；i=2: τ(2)={q[1]+1}→σ({q[1]+1})={p[q[1]]+1}；i=3: τ(3)={q[2]+1}→σ({q[2]+1})={p[q[2]]+1}\n3. 所以 σ∘τ = {fmt(r)}",
                   f"答案：{fmt(r)}"))
    s4_perms = [(1,3,0,2), (2,0,3,1), (0,2,1,3), (3,1,2,0)]
    for p in s4_perms:
        cycles = perm_cycle_decomp(p)
        cyc_str = " ".join(fmt(c) for c in cycles) if cycles else "恒等置换"
        n_cycles = len(cycles)
        parity = "偶" if (4 - n_cycles) % 2 == 0 else "奇"
        qs.append((f"置换 {fmt(p)} 在 S_4 中的轮换分解是什么？它是偶置换还是奇置换？",
                   f"1. 轮换分解：追踪映射得到 {cyc_str}\n2. 奇偶性 = (n - 轮换数) mod 2 = (4 - {n_cycles}) mod 2 = {(4-n_cycles)%2}\n3. 所以是{parity}置换",
                   f"答案：{cyc_str}，{parity}置换"))
    return qs

def gen_D():
    qs = [
        ("用 2 种颜色的珠子穿成 3 颗珠子的手链（可旋转），有多少种不同的手链？",
         "1. Burnside 引理：不同染色数 = (1/|G|) × Σ(每种旋转下的不动染色数)\n2. G = {旋转0°, 旋转120°, 旋转240°}\n3. 旋转0°：所有 2^3=8 种染色都不动\n4. 旋转120°：只有 3 颗同色的染色不动，共 2 种\n5. 旋转240°：同 120°，共 2 种\n6. 总数 = (8+2+2)/3 = 4",
         "答案：4"),
        ("用 2 种颜色的珠子穿成 4 颗珠子的手链（可旋转），有多少种不同的手链？",
         "1. Burnside：G = {旋转0°,90°,180°,270°}\n2. 旋转0°：2^4=16\n3. 旋转90°：全同色，2\n4. 旋转180°：两对同色，2^2=4\n5. 旋转270°：同90°，2\n6. 总数 = (16+2+4+2)/4 = 6",
         "答案：6"),
        ("用 2 种颜色的珠子穿成 5 颗珠子的手链（可旋转），有多少种不同的手链？",
         "1. Burnside：G = {旋转0°,72°,144°,216°,288°}\n2. 旋转0°：2^5=32\n3. 其余 4 个旋转：全同色才不动，各 2\n4. 总数 = (32+2+2+2+2)/5 = 8",
         "答案：8"),
        ("用 2 种颜色给正三角形的 3 个顶点染色（旋转和反射视为等价），有多少种不同染色？",
         "1. G = D_3，共 6 个元素（3 旋转 + 3 反射）\n2. 旋转0°：2^3=8\n3. 旋转120°/240°：全同色，各 2\n4. 反射×3：每条反射轴使轴两侧配对，各 2^2=4\n5. 总数 = (8+2+2+4+4+4)/6 = 24/6 = 4",
         "答案：4"),
    ]
    return qs

def main():
    all_q = []
    for gen in [gen_A, gen_B, gen_C, gen_D]:
        try:
            all_q.extend(gen())
        except Exception as e:
            print(f'[warn] {gen.__name__}: {e}', file=sys.stderr)
    random.shuffle(all_q)
    with open(OUT_Q, 'w') as fq, open(OUT_S, 'w') as fs:
        for i, (q, steps, ans) in enumerate(all_q):
            fq.write(f"{q}\n")
            fs.write(f"Q{i}: {q}\n{steps}\n{ans}\n---\n")
    print(f"生成 {len(all_q)} 道群论题")
    for q, steps, ans in all_q[:3]:
        print(f"---\n{q}\n{steps}\n{ans}")

if __name__ == '__main__':
    main()
