#!/usr/bin/env python3
"""虚状态+补全 压缩极限测试 — 多少内容能压到多少虚状态, 精度剩多少?
模拟知识库: N条知识(每条= 查询线索→答案), 高维向量
压缩: 知识压成 K个虚状态 (每个虚状态=代表一组知识)
补全: 给查询 → 找最近虚状态 → 从虚状态展开(存少量原型) → 出答案
测: 不同压缩率(知识数/虚状态数)下的 补全精度
"""
import numpy as np

def main():
    rng = np.random.RandomState(0)
    # 知识库: 300个"知识项"(模拟大模型知识子集), 每个知识= 输入线索→答案
    # 用高维向量模拟: query(线索) 和 answer(答案) 各 D 维
    D = 128
    N_KNOW = 300    # 知识条数 (模拟"300B模型的一小块知识")
    # 知识有潜结构: 由 F 个主题因子生成 (真实知识分主题)
    F = 30
    topics = rng.randn(F, D).astype(np.float32)
    topics /= np.linalg.norm(topics, axis=1, keepdims=True)
    # 每知识: 属于1个主题, query=主题方向+噪声, answer=主题方向+细节
    k_topic = rng.randint(0, F, N_KNOW)
    queries = topics[k_topic] + 0.2*rng.randn(N_KNOW, D).astype(np.float32)
    answers = topics[k_topic] + 0.3*rng.randn(N_KNOW, D).astype(np.float32)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    answers /= np.linalg.norm(answers, axis=1, keepdims=True)

    print(f'=== 虚状态压缩极限: {N_KNOW}条知识, 主题{F} ===')
    print(f'{"虚状态数K":>10}{"压缩率":>10}{"补全精度(cos)":>16}{"可用?":>8}')
    # 存"原型答案": 每主题存1个代表答案 (K=F=30 时=每主题1虚状态)
    # 压缩方案: K个虚状态 = K个主题中心; 补全=查query最近中心→取该中心存的原型答案
    for K in [5, 10, 15, 30, 60, 100]:
        # 对N_KNOW做K聚类(在query空间)
        idx = rng.choice(N_KNOW, min(K, N_KNOW), replace=False)
        centers = queries[idx].copy()
        for _ in range(30):
            d2 = ((queries[:,None,:]-centers[None,:,:])**2).sum(-1)
            lab = d2.argmin(1)
            for k in range(min(K, N_KNOW)):
                m = queries[lab==k]
                if len(m): centers[k] = m.mean(0)
        # 每个虚状态存"代表答案" = 簇内答案均值
        rep_ans = np.zeros((min(K, N_KNOW), D), np.float32)
        for k in range(min(K, N_KNOW)):
            m = answers[lab==k]
            if len(m): rep_ans[k] = m.mean(0)
        # 补全: 每个query → 最近中心 → 代表答案
        d2 = ((queries[:,None,:]-centers[None,:,:])**2).sum(-1)
        qlab = d2.argmin(1)
        recon = rep_ans[qlab]
        cos = np.sum(recon*answers, axis=1) / (np.linalg.norm(recon,axis=1)*np.linalg.norm(answers,axis=1)+1e-9)
        acc = float(cos.mean())
        usable = acc > 0.7
        mark = '✅' if usable else '❌'
        print(f'{K:>10}{N_KNOW/K:>9.1f}x{"":<1}{acc:>16.3f}{mark:>8}')

if __name__ == '__main__':
    main()
