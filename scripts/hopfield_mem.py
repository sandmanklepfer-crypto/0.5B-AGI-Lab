#!/usr/bin/env python3
"""Hopfield 能量景观记忆 (0.5B hopfield_mem 移植到进化系统, 2026-08-28)
内容寻址联想记忆: 存 (特征向量 → 记忆内容), 检索用 cos 相似度
进化系统用途: 有效的参数组合存为记忆, 相似情况自动联想最优解
"""
import numpy as np
import json, os

class HopfieldMemory:
    def __init__(self, dim, path=None):
        self.dim = dim
        self.path = path
        self.keys = []     # 特征向量列表
        self.vals = []     # 记忆内容(JSON 可序列化)
        self.scores = []   # 记忆的质量分
        if path and os.path.exists(path):
            self.load()

    def store(self, key_vec, val, score=0.0):
        """存储: key_vec 归一化, val 任意 JSON 对象"""
        k = np.asarray(key_vec, dtype=np.float32).flatten()
        assert k.shape[0] == self.dim
        n = np.linalg.norm(k)
        if n < 1e-9:
            return
        self.keys.append(k / n)
        self.vals.append(val)
        self.scores.append(float(score))
        # 容量上限: 保留最高分的 N 条
        if len(self.keys) > 200:
            idx = np.argsort(self.scores)[-200:]
            self.keys = [self.keys[i] for i in idx]
            self.vals = [self.vals[i] for i in idx]
            self.scores = [self.scores[i] for i in idx]
        if self.path:
            self.save()

    def recall(self, query_vec, topk=3, min_cos=0.5):
        """联想检索: 返回 [(cos, val, score), ...] 按相似度降序"""
        if not self.keys:
            return []
        q = np.asarray(query_vec, dtype=np.float32).flatten()
        nq = np.linalg.norm(q)
        if nq < 1e-9:
            return []
        q = q / nq
        K = np.array(self.keys)  # (N, dim)
        cos = K @ q
        idx = np.argsort(cos)[::-1][:topk]
        out = []
        for i in idx:
            if cos[i] >= min_cos:
                out.append((float(cos[i]), self.vals[i], self.scores[i]))
        return out

    def best(self):
        """返回分数最高的记忆"""
        if not self.scores:
            return None
        i = int(np.argmax(self.scores))
        return self.vals[i], self.scores[i]

    def stats(self):
        return {'n': len(self.keys), 'best_score': max(self.scores) if self.scores else None}

    def save(self):
        if not self.path:
            return
        data = {
            'keys': [k.tolist() for k in self.keys],
            'vals': self.vals,
            'scores': self.scores,
        }
        with open(self.path, 'w') as f:
            json.dump(data, f)

    def load(self):
        with open(self.path) as f:
            data = json.load(f)
        self.keys = [np.asarray(k, dtype=np.float32) for k in data['keys']]
        self.vals = data['vals']
        self.scores = data['scores']

    # ── 特征构建: 参数向量 → 记忆键 ──
    @staticmethod
    def param_key(p, dirs_order):
        """参数向量 → 固定维特征 (方向 one-hot + 归一化数值)"""
        feat = [0.0] * len(dirs_order)
        if p['dir'] in dirs_order:
            feat[dirs_order.index(p['dir'])] = 1.0
        feat += [p['strength'] / 200.0, p['layer'] / 64.0, p['temp'] / 2.0, p['scale'] / 3.0]
        return np.array(feat, dtype=np.float32)


# ── 测试 ──
if __name__ == '__main__':
    m = HopfieldMemory(9)
    dirs = ['身份', '反身份', '攻击', '拒绝', '随机']
    p1 = {'dir': '攻击', 'strength': 80, 'layer': 58, 'temp': 0.8, 'scale': 1.0}
    p2 = {'dir': '身份', 'strength': 30, 'layer': 60, 'temp': 0.5, 'scale': 1.2}
    m.store(HopfieldMemory.param_key(p1, dirs), p1, 88.5)
    m.store(HopfieldMemory.param_key(p2, dirs), p2, 76.0)
    hits = m.recall(HopfieldMemory.param_key({'dir': '攻击', 'strength': 75, 'layer': 58, 'temp': 0.9, 'scale': 1.1}, dirs))
    print('recall:', [(h[0], h[1], h[2]) for h in hits])
