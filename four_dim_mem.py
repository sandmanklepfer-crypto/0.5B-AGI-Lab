#!/usr/bin/env python3
"""四维时空记忆 (2026-08-28) — 自进化系统的轨迹记忆
维度: 空间(状态向量) × 时间(轮次) × 行动(决策) × 价值(分数)
每条记忆: (timeline_id, t, state_vec, action, score, next_state)
检索: 状态空间 kNN + 时间线过滤 + 分数排序
"""
import numpy as np
import json, os

class FourDimMemory:
    def __init__(self, state_dim, path=None):
        self.state_dim = state_dim
        self.path = path
        self.memories = []   # dict: {tl, t, state, action, score, next_state}
        if path and os.path.exists(path):
            self.load()

    def record(self, tl, t, state_vec, action, score, next_state=None):
        """记录一条时空记忆"""
        self.memories.append({
            'tl': tl, 't': t,
            'state': np.asarray(state_vec, dtype=np.float32).tolist(),
            'action': action,
            'score': float(score),
            'next_state': np.asarray(next_state, dtype=np.float32).tolist() if next_state is not None else None,
        })
        if len(self.memories) > 500:  # 容量: 保留每个时间线最新的
            keep = []
            seen = {}
            for m in reversed(self.memories):
                k = (m['tl'], m['t'])
                if k not in seen and len(keep) < 500:
                    keep.append(m); seen[k] = True
            self.memories = list(reversed(keep))
        if self.path:
            self.save()

    def recall(self, state_vec, tl=None, topk=3, min_cos=0.3, prefer_recent=True):
        """状态空间联想: 返回与当前状态最相似的历史记忆 [(cos, mem), ...]"""
        if not self.memories:
            return []
        q = np.asarray(state_vec, dtype=np.float32).flatten()
        nq = np.linalg.norm(q)
        if nq < 1e-9:
            return []
        q = q / nq
        cands = [m for m in self.memories if (tl is None or m['tl'] == tl)]
        if not cands:
            return []
        S = np.array([m['state'] for m in cands])
        cos = (S @ q) / (np.linalg.norm(S, axis=1) + 1e-9)
        order = np.argsort(cos)[::-1][:topk * 3]
        out = []
        for i in order:
            if cos[i] >= min_cos:
                out.append((float(cos[i]), cands[i]))
        out.sort(key=lambda x: (-x[0], x[1]['score']))
        return out[:topk]

    def trajectory(self, tl):
        """整条时间线轨迹 (按时间排序)"""
        tr = [m for m in self.memories if m['tl'] == tl]
        tr.sort(key=lambda m: m['t'])
        return tr

    def best_action_in_region(self, state_vec, topk=5):
        """状态邻域内最高分的历史行动 (空间联想的核心)"""
        hits = self.recall(state_vec, topk=topk, min_cos=0.2)
        if not hits:
            return None
        best = max(hits, key=lambda h: h[1]['score'])
        return best[1]['action'], best[1]['score'], best[0]

    def state_transition_stats(self, action_key):
        """统计某行动的状态转移效果: 平均分数 + 状态变化方向"""
        ms = [m for m in self.memories if m.get('action', {}).get('dir') == action_key and m['next_state'] is not None]
        if not ms:
            return None
        avg_score = np.mean([m['score'] for m in ms])
        # 平均状态位移
        moves = np.array([np.array(m['next_state']) - np.array(m['state']) for m in ms])
        avg_move = moves.mean(0)
        return {'n': len(ms), 'avg_score': float(avg_score), 'avg_move': avg_move.tolist()}

    def stats(self):
        n_tl = len(set(m['tl'] for m in self.memories))
        return {'n': len(self.memories), 'timelines': n_tl,
                'best_score': max((m['score'] for m in self.memories), default=None)}

    def save(self):
        if not self.path:
            return
        data = {'memories': [{**m, 'state': m['state'], 'next_state': m['next_state']} for m in self.memories]}
        with open(self.path, 'w') as f:
            json.dump(data, f, default=str)

    def load(self):
        with open(self.path) as f:
            data = json.load(f)
        self.memories = data['memories']


if __name__ == '__main__':
    m = FourDimMemory(5)
    m.record(0, 1, [0.01, 0.02, 0.03, 0.04, 0.05], {'dir': '攻击', 'strength': 80}, 85.0, [0.02, 0.05, 0.01, 0.03, 0.02])
    m.record(1, 1, [0.9, 0.8, 0.1, 0.05, 0.01], {'dir': '身份', 'strength': 30}, 60.0, [0.85, 0.82, 0.12, 0.04, 0.02])
    hits = m.recall([0.015, 0.025, 0.03, 0.045, 0.05])
    print('recall:', [(h[0], h[1]['action'], h[1]['score']) for h in hits])
    print('traj0:', m.trajectory(0))
    print('best_in_region:', m.best_action_in_region([0.012, 0.022, 0.031, 0.042, 0.051]))
    print('stats:', m.stats())
