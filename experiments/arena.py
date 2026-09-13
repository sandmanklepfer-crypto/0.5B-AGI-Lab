# -*- coding: utf-8 -*-
"""arena.py — 持续对抗循环（小模型 × 长时间思考 × 外部验证 × 权重固化）
   核心: 时间换能力 → 成功经验固化 → 下次更少时间 → 循环
   关键: 裁判必须是【外部可验证】的（防熵减）
   产出: 成功率曲线（证明是否真的在进化）
"""
import random, json, math, time, os, sys

random.seed(7)

# ==================== ① 可验证任务池（有确定答案） ====================
def gen_task(difficulty, seed=None):
    """难度 1-5: 越大越难（更深、更多步）"""
    r = random.Random(seed)
    kind = r.choice(["arith","logic","seq"])
    if kind=="arith":
        n = 2 + difficulty
        nums = [r.randint(1,9) for _ in range(n)]
        ops  = [r.choice("+-*") for _ in range(n-1)]
        expr = str(nums[0])
        for o,x in zip(ops, nums[1:]):
            expr += " %s %d"%(o,x)
        return {"kind":"arith","q":expr+" = ?","a":str(eval(expr))}
    if kind=="logic":
        # n 人的年龄传递关系
        n = 2 + difficulty
        base = [r.randint(20,40) for _ in range(n)]
        q = base[0]
        # a0 > a1 > a2 ... 差值为随机整数
        diffs=[r.randint(1,5) for _ in range(n-1)]
        target = base[0] - sum(diffs)
        desc = "A 比 B 大 %d 岁" % diffs[0]
        return {"kind":"logic","q":"已知 "+desc+"，相差关系为 %s，问 A 比最后一个大几岁？"%diffs,
                "a":str(sum(diffs))}
    # 数列
    start=r.randint(1,5); step=r.randint(2,6); n=2+difficulty
    seq=[start+i*step for i in range(n)]
    return {"kind":"seq","q":"数列 %s ... 下一项？"%seq[:-1],"a":str(seq[-1])}

def verify(task, ans):
    """外部裁判: 只比字符串数值"""
    a=str(ans).strip(); g=str(task["a"]).strip()
    try:
        return float(a)==float(g)
    except Exception:
        return a==g

# ==================== ② 小模型（模拟"弱直觉 + 可思考"） ====================
class SmallModel:
    """用规则+噪声模拟小模型: 难度越高正确率越低; 允许"多想想"(多次采样)"""
    def __init__(self, base=0.42):
        self.base = base           # 基础直觉正确率
        self.skills = {}           # 固化下来的"技能"(任务类型→加成)
    def think_once(self, task):
        """单次直觉: 正确概率 = base + 技能加成 - 难度惩罚"""
        d = len(str(task["q"]))//8
        b = self.base + self.skills.get(task["kind"],0.0) - 0.03*d
        b = max(0.02, min(0.97, b))
        if random.random() < b:
            return task["a"]            # 答对
        # 答错: 给个近似值
        try: v=float(task["a"])
        except: v=0
        return str(round(v + random.choice([-2,-1,1,2,3])))
    def think(self, task, budget):
        """花 budget 倍时间: 多次采样取多数(simulates 长思考)"""
        votes = [self.think_once(task) for _ in range(max(1,budget))]
        from collections import Counter
        return Counter(votes).most_common(1)[0][0], votes
    def solidify(self, kind, amount=0.015):
        """把成功经验固化进"权重"(技能提升)"""
        self.skills[kind] = min(0.45, self.skills.get(kind,0.0) + amount)

# ==================== ③ 对抗循环 ====================
class Arena:
    def __init__(self, big_base=0.88):
        self.small = SmallModel(0.42)
        self.big_base = big_base      # 大模型1次直觉就很强
        self.log = []
        self.success_pool = []
    def big_think(self, task):
        """大模型: 1 次直觉就够强"""
        d = len(str(task["q"]))//8
        b = max(0.05, min(0.98, self.big_base - 0.02*d))
        if random.random() < b: return task["a"]
        try: v=float(task["a"])
        except: v=0
        return str(round(v+random.choice([-1,1])))
    def round_trip(self, difficulty, small_budget):
        """一轮: 小模型花 small_budget 倍时间, 大模型 1 倍; 比谁对"""
        task = gen_task(difficulty)
        # 小模型
        sa, svotes = self.small.think(task, small_budget)
        sok = verify(task, sa)
        # 大模型(1倍预算)
        ba = self.big_think(task)
        bok = verify(task, ba)
        rec = {"difficulty":difficulty,"q":task["q"],"gold":task["a"],
               "small":sa,"small_ok":sok,"big":ba,"big_ok":bok,
               "win":(sok and not bok),"tie":(sok==bok)}
        self.log.append(rec)
        # ---- 固化: 只在"小模型对了"时学 ----
        if sok:
            self.success_pool.append(rec)
            self.small.solidify(task["kind"])
        return rec

def run(rounds=400, dump="/workspace/arena_log.json"):
    ar = Arena()
    print("="*76)
    print("  持续对抗循环: 小模型(多倍时间) vs 大模型(1倍时间)")
    print("="*76)
    print("  规则: 小模型预算 4 倍时间; 大模型 1 倍")
    print("  固化: 小模型答对 → 技能 +0.015 (模拟 LoRA 固化)")
    print()
    # 分阶段看增长
    phases = [(1,100),(101,200),(201,300),(301,400)]
    print("  %-14s %-10s %-10s %-10s %s"%("阶段","小模型胜率","平均正确率","技能积累","对比"))
    prev=None
    for (a,b) in phases:
        s_ok=0; b_ok=0; wins=0; n=0
        for i in range(a, b+1):
            diff = 1 if i<=200 else 2      # 后半段难度上升
            rec = ar.round_trip(diff, small_budget=4)
            s_ok += rec["small_ok"]; b_ok += rec["big_ok"]
            wins += rec["win"]; n += 1
        tag = "小%.0f%%/大%.0f%%"%(100*s_ok/n, 100*b_ok/n)
        print("  轮 %3d-%-4d  胜率 %5.1f%%   小模型 %5.1f%%  大模型 %5.1f%%  %s"%(
            a,b,100*wins/n,100*s_ok/n,100*b_ok/n,
            "技能:"+",".join("%s=%.2f"%(k,v) for k,v in ar.small.skills.items())))
    print()
    # 最终: 小模型能否"单次"打赢大模型
    print("="*76)
    print("  终局测试: 小模型【1 倍预算】(不思考) vs 大模型")
    print("="*76)
    for diff in (1,2,3):
        s=0; b=0; n=60
        for _ in range(n):
            t=gen_task(diff)
            sa,_=ar.small.think(t, 1)     # 1倍预算
            ba=ar.big_think(t)
            s+=verify(t,sa); b+=verify(t,ba)
        print("  难度%d: 小模型(1倍) %.0f%%  vs  大模型 %.0f%%  → %s"%(
            diff, 100*s/n, 100*b/n,
            "小胜" if s>n*0.5 and s>b else ("接近" if abs(s-b)<n*0.15 else "仍落后")))
    json.dump({"log":ar.log[-50:], "skills":ar.small.skills}, open(dump,"w"), ensure_ascii=False, indent=1)
    print("\n  日志 → %s (%d 轮记录)"%(dump, len(ar.log)))

if __name__=="__main__":
    t0=time.time()
    run(int(sys.argv[1]) if len(sys.argv)>1 else 400)
    print("  耗时 %.1fs"%(time.time()-t0))
