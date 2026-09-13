# -*- coding: utf-8 -*-
"""evolve.py — 「可验证领域自进化」最小完整实现（真实验证器，不依赖大模型）
   核心机制（对应 CPU 的三大加速）:
     ① 验证器     = 真执行代码，跑测试用例判对错   ← 外部裁判，防熵减
     ② 记忆库     = 解过的题存起来，下次直接复用    ← 缓存
     ③ 技能权重   = 有效的构造块概率上升            ← 学习/进化
   度量: 每轮「平均尝试次数」「解决率」「记忆命中原语」—— 应逐轮改善
"""
import random, time, math

random.seed(2026)

# ==================== ① 可验证任务池 ====================
# 每题: 名字, 签名(用于检索), 测试用例列表, 参数字典
TASKS = [
    # 数值表达式
    ("arith_aplusb", "num2", [((3,4),7), ((10,2),12), ((0,5),5)], {"a":1,"b":1}),
    ("arith_amulb",  "num2", [((3,4),12), ((5,2),10), ((7,3),21)], {"a":1,"b":1}),
    ("arith_a2b",    "num2", [((3,4),9),  ((5,2),7),  ((1,1),3)],  {"a":1,"b":2}),
    ("arith_ab_diff","num2", [((9,4),5),  ((3,10),7), ((5,5),0)],  {"a":1,"b":1}),
    # 列表
    ("list_sum",     "listi",[([1,2,3],6), ([5,5],10), ([-1,1],0)], {"L":1}),
    ("list_max",     "listi",[([1,2,3],3), ([5,5],5), ([-1,1],1)], {"L":1}),
    ("list_min",     "listi",[([1,2,3],1), ([5,5],5), ([-1,1],-1)],{"L":1}),
    ("list_len",     "listi",[([1,2,3],3), ([5,5],2), ([],0)],     {"L":1}),
    ("list_sumsq",   "listi",[([1,2,3],14),([5],25), ([2,2],8)],   {"L":1}),
    # 字符串
    ("str_upper",    "str",  [("ab","AB"),("Hi","HI"),("x","X")],  {"s":1}),
    ("str_rev",      "str",  [("ab","ba"),("abc","cba"),("x","x")],{"s":1}),
    ("str_len2",     "str",  [("ab",2),("abc",3),("",0)],          {"s":1}),
]

def verify(code, cases):
    """真实执行验证 —— 唯一裁判"""
    ns = {}
    try:
        exec(code, ns)
        f = ns.get("f")
        if f is None: return False
        for arg, want in cases:
            got = f(arg) if isinstance(arg, (list,)) else f(*arg) if isinstance(arg, tuple) else f(arg)
            if got != want: return False
        return True
    except Exception:
        return False

# ==================== ② 弱求解器(模拟"弱直觉") ====================
# 用随机组合 "构造块" 生成候选代码; 有效构造块概率会随进化上升
BLOCKS = {
    "num2": ["a","b","a+b","a*b","a-b","b-a","a*a","b*b","a+b+b","a*a+b","(a+b)*2",
             "a*b+a","b*b-a","abs(a-b)","a//b if b else 0","a+b-a","a*2+b"],
    "listi":["sum(L)","max(L) if L else 0","min(L) if L else 0","len(L)",
             "sum(x*x for x in L)","sum(L)-len(L)","max(L)*min(L) if L else 0",
             "sorted(L)[-1] if L else 0","sum(L)+1","len(L)*max(L) if L else 0"],
    "str":  ['s.upper()','s[::-1]','str(len(s))','s.lower()','s+"!"','s.replace("a","A")',
             's.strip()','s*1','s.title()','str(len(s)*2)'],
}
BODY = {
    "num2": lambda e: "def f(a, b):\n    return %s" % e,
    "listi":lambda e: "def f(L):\n    return %s" % e,
    "str":  lambda e: "def f(s):\n    return %s" % e,
}

class Solver:
    """弱求解器: 从构造块里随机组候选; 用权重体现'学到的偏好'"""
    def __init__(self):
        # 每个构造块一个权重(初始1.0) → 进化中有效块权重上升
        self.w = {k: [1.0]*len(v) for k,v in BLOCKS.items()}
        self.tried = {k: [0]*len(v) for k,v in BLOCKS.items()}

    def propose(self, sig):
        """按权重采样一个候选代码"""
        ws = self.w[sig]
        tot = sum(ws)
        r = random.random()*tot
        acc = 0
        for i,w in enumerate(ws):
            acc += w
            if r <= acc:
                self.tried[sig][i] += 1
                return BODY[sig](BLOCKS[sig][i]), i
        i = len(ws)-1
        return BODY[sig](BLOCKS[sig][i]), i

    def reward(self, sig, idx, ok):
        """验证结果 → 调权重(这就是'进化')"""
        if ok: self.w[sig][idx] *= 1.6          # 有效的块概率上升
        else:  self.w[sig][idx] *= 0.97         # 无效的略降
        return

# ==================== ③ 记忆库(缓存复用) ====================
class Memory:
    def __init__(self): self.store={}; self.hit=0; self.miss=0
    def get(self, key):
        if key in self.store: self.hit+=1; return self.store[key]
        self.miss+=1; return None
    def put(self, key, val): self.store[key]=val

# ==================== ④ 进化循环 ====================
def run_round(solver, mem, tasks, max_try=300, reuse=True):
    solved=0; total_try=0; reused=0; detail=[]
    for tname, sig, cases, params in tasks:
        key = tname
        code = None
        # —— 复用: 记忆命中直接拿 ——
        if reuse:
            code = mem.get(key)
            if code is not None:
                reused += 1
                if verify(code, cases):
                    solved += 1; total_try += 1
                    detail.append((tname, 1, "记忆命中"))
                    continue
        # —— 搜索: 反复尝试 + 每次真实验证 ——
        n = 0; got=None
        for _ in range(max_try):
            n += 1
            cand, idx = solver.propose(sig)
            ok = verify(cand, cases)
            solver.reward(sig, idx, ok)
            if ok:
                got = cand; break
        total_try += n
        if got:
            solved += 1
            mem.put(key, got)
            detail.append((tname, n, "搜索成功"))
        else:
            detail.append((tname, n, "失败"))
    return solved, total_try, reused, detail

def main():
    t0=time.time()
    solver = Solver()
    mem = Memory()
    print("="*74)
    print("  「可验证领域自进化」实验 —— 真实验证器(exec) + 记忆复用 + 权重进化")
    print("="*74)
    print("  任务池: %d 道 (数值/列表/字符串)\n" % len(TASKS))

    hist=[]
    for rnd in range(1,6):
        solved, tries, reused, detail = run_round(solver, mem, TASKS)
        avg = tries/len(TASKS)
        hist.append((rnd, solved, avg, reused))
        print("  第%d轮: 解决 %2d/%d (%.0f%%)  平均尝试 %6.1f 次  记忆命中 %2d 题  [剩余记忆 %d]"
              % (rnd, solved, len(TASKS), 100*solved/len(TASKS), avg, reused, len(mem.store)))
    print("\n" + "="*74)
    print("  逐轮明细(看尝试次数是否下降)")
    print("="*74)
    # 重点是第1轮 vs 第2轮(去掉记忆后重解, 看权重进化的效果)
    solver2 = Solver()
    mem2 = Memory()
    s1, t1, _, _ = run_round(solver2, mem2, TASKS, reuse=False)
    a1 = t1/len(TASKS)
    s2, t2, _, _ = run_round(solver2, mem2, TASKS, reuse=False)   # 不用记忆, 纯权重进化
    a2 = t2/len(TASKS)
    s3, t3, _, _ = run_round(solver2, mem2, TASKS, reuse=False)
    a3 = t3/len(TASKS)
    print("  【纯权重进化】(禁用记忆, 只靠构造块权重学习)")
    print("     第1轮 平均尝试 %6.1f 次" % a1)
    print("     第2轮 平均尝试 %6.1f 次   (变化 %+.1f%%)" % (a2, 100*(a2-a1)/a1))
    print("     第3轮 平均尝试 %6.1f 次   (变化 %+.1f%%)" % (a3, 100*(a3-a1)/a1))

    print("\n  【构造块权重进化】(哪些块被学出来了)")
    for sig, ws in solver2.w.items():
        tops = sorted(range(len(ws)), key=lambda i:-ws[i])[:2]
        print("     %-6s 最优块: %s" % (sig, " | ".join("%s(w=%.1f)"%(BLOCKS[sig][i], ws[i]) for i in tops)))

    print("\n  总耗时 %.1fs" % (time.time()-t0))
    print("="*74)

if __name__=="__main__":
    main()
