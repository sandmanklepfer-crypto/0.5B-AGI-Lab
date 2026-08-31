#!/usr/bin/env python3
"""皮层 (Cortex) — 从四维时空记忆提炼规律的语义层 (2026-08-28)
人脑类比: 海马(四维)记录具体事件 → 重放 → 皮层提炼抽象规律
实现: 状态空间聚类 → 每簇统计最佳行动 → 决策时按当前状态给规律建议
"""
import numpy as np
import json, os

class Cortex:
    def __init__(self, k=8, path=None):
        self.k = k
        self.path = path
        self.centers = None       # (k, state_dim)
        self.region_best = {}     # cluster_idx -> {action, avg_score, n}
        self.region_all = {}      # cluster_idx -> [(action, score)]
        if path and os.path.exists(path):
            self.load()

    def distill(self, mem):
        """从四维记忆提炼规律: 聚类状态 → 每簇最佳行动"""
        ms = mem.memories
        if len(ms) < self.k * 2:
            return False
        S = np.array([m['state'] for m in ms], dtype=np.float32)
        sc = np.array([m['score'] for m in ms], dtype=np.float32)
        # 简单 kMeans (numpy, 无 sklearn 依赖)
        k = min(self.k, len(S))
        idx = np.random.choice(len(S), k, replace=False)
        centers = S[idx].copy()
        labels = np.zeros(len(S), dtype=int)
        for _ in range(20):
            d = ((S[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
            new_labels = d.argmin(1)
            if (new_labels == labels).all():
                break
            labels = new_labels
            for c in range(k):
                m = S[labels == c]
                if len(m):
                    centers[c] = m.mean(0)
        self.centers = centers
        # 每簇统计
        self.region_best = {}
        self.region_all = {}
        for c in range(k):
            idxs = np.where(labels == c)[0]
            acts = [ms[i]['action'] for i in idxs]
            scs = [float(sc[i]) for i in idxs]
            self.region_all[c] = list(zip(acts, scs))
            if acts:
                bi = int(np.argmax(scs))
                self.region_best[c] = {'action': acts[bi], 'avg_score': float(np.mean(scs)), 'n': len(acts), 'best': float(scs[bi])}
        if self.path:
            self.save()
        return True

    def advise(self, state_vec):
        """给当前状态的规律建议: 最近区域的最佳行动"""
        if self.centers is None or len(self.centers) == 0:
            return None
        q = np.asarray(state_vec, dtype=np.float32)
        d = ((self.centers - q[None, :]) ** 2).sum(-1)
        c = int(d.argmin())
        rb = self.region_best.get(c)
        if not rb:
            return None
        return {'cluster': c, 'action': rb['action'], 'avg_score': rb['avg_score'],
                'n': rb['n'], 'best': rb['best'], 'center': self.centers[c].tolist()}

    def summary(self):
        if self.centers is None or len(self.centers) == 0:
            return '皮层: 尚未提炼(轨迹不足)'
        parts = []
        for c in sorted(self.region_best.keys()):
            rb = self.region_best[c]
            parts.append(f"区域{c}:{rb['action'].get('dir')}/{rb['avg_score']:.0f}分(n={rb['n']})")
        return '皮层规律: ' + '; '.join(parts)

    def save(self):
        if not self.path:
            return
        data = {
            'centers': [c.tolist() for c in self.centers] if self.centers is not None else None,
            'region_best': {str(k): {**v, 'action': v['action']} for k, v in self.region_best.items()},
        }
        with open(self.path, 'w') as f:
            json.dump(data, f, default=str)

    def load(self):
        with open(self.path) as f:
            data = json.load(f)
        if data.get('centers'):
            self.centers = np.array(data['centers'], dtype=np.float32)
        self.region_best = {int(k): v for k, v in (data.get('region_best') or {}).items()}
