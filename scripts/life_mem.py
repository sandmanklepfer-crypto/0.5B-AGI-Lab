#!/usr/bin/env python3
"""人生档案库 — 四维时空记忆的人生粒度版 (2026-08-28)
每个人 = 一条世界线: 轨迹(年份, 状态5维, 决策, 结果分数, 下一状态)
检索: 生活状态 → 最相似人生时刻 → 那人的决策+结果 (人生顾问)
"""
import numpy as np
import json, os, random, sys

# 生活状态维度
LIFE_DIMS = ['事业', '健康', '关系', '知识', '自由']

DECISIONS = ['进取', '稳健', '冒险', '学习', '投资', '助人', '休养', '创业', '结婚', '远行']
DEC_REASON = {
    '进取': '全力拼搏事业', '稳健': '守住现状稳步前进', '冒险': '押上一切赌一把',
    '学习': '投入时间学习提升', '投资': '把资源投向未来', '助人': '帮助他人建立联结',
    '休养': '停下休整恢复', '创业': '开创自己的事业', '结婚': '建立家庭', '远行': '离开熟悉的地方探索',
}

class LifeMemory:
    def __init__(self, path=None):
        self.path = path
        self.people = {}   # person_id -> {name, birth, trajectory: [{y, state, dec, score, next}], summary}
        if path and os.path.exists(path):
            self.load()

    def add_person(self, pid, name, birth, traj, summary=''):
        self.people[pid] = {'name': name, 'birth': birth, 'trajectory': traj, 'summary': summary}
        if self.path:
            self.save()

    def generate_person(self, pid, name, years=70, seed=None):
        """程序生成一个人生轨迹 (状态随机游走 + 决策)"""
        rng = random.Random(seed if seed is not None else pid * 7919)
        state = np.array([rng.uniform(0.2, 0.8) for _ in range(5)], dtype=np.float32)  # 出生状态
        traj = []
        score = 50.0
        for age in range(0, years, 5):
            y = age
            # 决策: 与状态相关的选择 (状态差→更可能进取/冒险, 状态好→稳健/休养)
            p = state.mean()
            if p < 0.35:
                dec = rng.choices(DECISIONS[:3], weights=[4, 2, 3])[0]
            elif p > 0.7:
                dec = rng.choices(['稳健', '休养', '助人', '学习'], weights=[3, 2, 2, 2])[0]
            else:
                dec = rng.choice(DECISIONS)
            # 决策效果 (带随机性 + 决策类型偏置)
            eff = np.zeros(5)
            if dec == '进取': eff[0] += 0.12
            elif dec == '稳健': eff[0] += 0.03; eff[1] += 0.03; eff[4] += 0.02
            elif dec == '冒险': eff[0] += rng.uniform(-0.15, 0.35)
            elif dec == '学习': eff[3] += 0.12; eff[0] += 0.04
            elif dec == '投资': eff[0] += rng.uniform(-0.05, 0.2); eff[3] += 0.02
            elif dec == '助人': eff[2] += 0.12; eff[1] += 0.03
            elif dec == '休养': eff[1] += 0.12; eff[0] -= 0.02
            elif dec == '创业': eff[0] += rng.uniform(-0.2, 0.4); eff[4] += 0.05
            elif dec == '结婚': eff[2] += 0.15; eff[0] -= 0.03
            elif dec == '远行': eff[4] += 0.12; eff[3] += 0.06; eff[2] -= 0.03
            noise = np.array([rng.uniform(-0.04, 0.04) for _ in range(5)])
            next_state = np.clip(state + eff + noise, 0.05, 0.95)
            # 分数: 状态均衡度 + 事业 + 关系 - 波动惩罚
            score = 0.5 * next_state.mean() + 0.2 * next_state[0] + 0.2 * next_state[2] - 0.1 * next_state.std()
            traj.append({
                'y': y, 'state': state.tolist(), 'dec': dec, 'dec_reason': DEC_REASON[dec],
                'score': round(float(score) * 100, 1), 'next': next_state.tolist()
            })
            state = next_state
        # 人生总结
        summary = f"{name}的一生: 从{traj[0]['state'][0]:.0%}事业起点开始,经历{', '.join(set(t['dec'] for t in traj))}等关键选择,最终人生满意度{traj[-1]['score']:.0f}/100。"
        self.add_person(pid, name, 0, traj, summary)
        return traj

    def generate_batch(self, n, prefix='人'):
        """批量生成 n 个人生"""
        for i in range(n):
            self.generate_person(i, f"{prefix}{i+1}", seed=i * 131 + 7)
        if self.path:
            self.save()
        return n

    def recall_similar(self, life_state, topk=3, min_cos=0.3):
        """生活状态联想: 返回最相似的人生时刻 [(cos, person, 年份, 决策, 分数), ...]"""
        q = np.asarray(life_state, dtype=np.float32)
        nq = np.linalg.norm(q)
        if nq < 1e-9:
            return []
        q = q / nq
        cands = []
        for pid, p in self.people.items():
            for t in p['trajectory']:
                s = np.asarray(t['state'], dtype=np.float32)
                c = float(s @ q) / (np.linalg.norm(s) + 1e-9)
                if c >= min_cos:
                    cands.append((c, p['name'], t['y'], t['dec'], t['dec_reason'], t['score']))
        cands.sort(key=lambda x: -x[0])
        return cands[:topk]

    def best_advice(self, life_state, topk=5):
        """人生顾问: 相似状态下的最优决策"""
        hits = self.recall_similar(life_state, topk=topk, min_cos=0.2)
        if not hits:
            return None
        best = max(hits, key=lambda h: h[5])
        return {'cos': best[0], 'person': best[1], 'year': best[2],
                'decision': best[3], 'reason': best[4], 'score': best[5]}

    def life_patterns(self):
        """人生模式提炼: 状态区域 → 最优决策 (皮层)"""
        from collections import defaultdict
        regions = defaultdict(list)
        for p in self.people.values():
            for t in p['trajectory']:
                s = np.asarray(t['state'], dtype=np.float32)
                # 区域: 按平均状态分 低/中/高 3 档
                r = '低' if s.mean() < 0.35 else '高' if s.mean() > 0.7 else '中'
                regions[r].append((t['dec'], t['score']))
        pat = {}
        for r, items in regions.items():
            if not items: continue
            by_dec = defaultdict(list)
            for dec, sc in items:
                by_dec[dec].append(sc)
            best_dec = max(by_dec, key=lambda d: np.mean(by_dec[d]))
            pat[r] = {'best_dec': best_dec, 'avg_score': round(float(np.mean([s for _, s in items])), 1),
                      'n': len(items)}
        return pat

    def stats(self):
        n_traj = sum(len(p['trajectory']) for p in self.people.values())
        return {'people': len(self.people), 'traj_entries': n_traj}

    def save(self):
        if not self.path: return
        with open(self.path, 'w') as f:
            json.dump(self.people, f, default=str)

    def load(self):
        with open(self.path) as f:
            self.people = json.load(f)


if __name__ == '__main__':
    lm = LifeMemory('/root/autodl-tmp/life_mem.json')
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    lm.generate_batch(n)
    print('生成:', lm.stats())
    # 测试检索
    probe = [0.3, 0.5, 0.4, 0.6, 0.5]  # 某人的生活状态
    print('相似时刻:', [(h[0], h[1], h[2], h[3], h[5]) for h in lm.recall_similar(probe, topk=3)])
    print('最佳建议:', lm.best_advice(probe))
    print('人生模式:', lm.life_patterns())
