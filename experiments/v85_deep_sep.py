#!/usr/bin/env python3
"""V85 深层方向级分离测试 — 换角度: 在深层找"知识方向/推理方向", 测能否完全分开
不再看整层平均(太粗), 而是:
 1 采更多任务(每种10+) 的深层(20-23)激活
 2 PCA 降维 → LDA 找区分知识/推理的最佳方向
 3 测: 两类在深层空间是否线性可分? 分隔方向强度?
"""
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
DEEP = [20, 21, 22, 23]

KNOW = [
    "中国的首都是什么？", "水的沸点是多少？", "7乘8等于多少？", "地球绕什么转？",
    "一年几个月？", "太阳从哪升起？", "中国有多少省份？", "光速大约多少？",
    "水的化学式？", "一年有多少天？", "中国的货币是什么？", "珠穆朗玛峰多高？",
]
REASON = [
    "所有鸟有翅膀，企鹅是鸟，企鹅会怎样？", "大象比马重马比羊重谁最轻？",
    "A比B高B比C高谁最高？", "明天下雨活动取消明天确实下雨活动怎样？",
    "地湿路滑下雨地湿为什么路滑？", "猫会抓老鼠小花是猫小花会抓老鼠吗？",
    "A是B的爸爸B是C的爸爸C是A的什么？", "如果P则QP真则Q怎样？",
    "张三比李四高李四比王五矮谁最矮？", "所有鱼会游泳鲸鱼不是鱼鲸鱼会游泳吗？",
    "只有满18能进小明满了能进吗？", "先烧水再放茶泡好倒杯先做什么？",
]

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()

    def acts(texts, layer):
        out = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode():
                hs = model(input_ids=ids, output_hidden_states=True).hidden_states
            # 末token 激活 (句末 = 任务处理完成点, 最可能分离)
            out.append(hs[layer+1][0, -1].float().cpu().numpy())
        return np.array(out)

    print('[V85] 深层方向级分离 (每层独立测)', flush=True)
    for L in DEEP:
        K = acts(KNOW, L)   # (12,896)
        R = acts(REASON, L)
        # LDA 方向: 类间散布/类内散布 最大方向 (w = Sw^-1 (mu1-mu2))
        mk, mr = K.mean(0), R.mean(0)
        # 类内散布
        Sw = np.cov(K.T) + np.cov(R.T) + 1e-6*np.eye(896)
        try:
            w = np.linalg.solve(Sw, mk - mr)
        except Exception:
            w = mk - mr
        w = w / (np.linalg.norm(w) + 1e-9)
        # 投影后两类分布
        pk = K @ w
        pr = R @ w
        sep = (pk.mean() - pr.mean()) ** 2 / (pk.var() + pr.var() + 1e-9)
        # 可分离度: 投影后两类均值差 / 标准差和
        dprime = abs(pk.mean() - pr.mean()) / np.sqrt((pk.var() + pr.var()) / 2 + 1e-9)
        # 准确率 (最近质心)
        correct = 0
        for x in K:
            if abs(x@w - pk.mean()) < abs(x@w - pr.mean()): correct += 1
        for x in R:
            if abs(x@w - pr.mean()) < abs(x@w - pk.mean()): correct += 1
        acc = correct / (len(K) + len(R))
        print(f'  层{L}: d\'={dprime:.2f} LDA分类准确率={acc:.2f} {"✅可分离" if acc>0.9 else "❌"}', flush=True)

    # 拼接深层 (20-23 concat) 再测
    print('\n  深层拼接(20-23合体)再测:', flush=True)
    Kc = np.concatenate([acts(t, 20) for t in KNOW], axis=0) if False else None
    # 直接concat每任务4层
    K_all = np.hstack([acts(KNOW, L) for L in DEEP])
    R_all = np.hstack([acts(REASON, L) for L in DEEP])
    mk, mr = K_all.mean(0), R_all.mean(0)
    Sw = np.cov(K_all.T) + np.cov(R_all.T) + 1e-6*np.eye(K_all.shape[1])
    w = np.linalg.solve(Sw, mk-mr); w = w/(np.linalg.norm(w)+1e-9)
    pk, pr = K_all@w, R_all@w
    dprime = abs(pk.mean()-pr.mean())/np.sqrt((pk.var()+pr.var())/2+1e-9)
    correct = sum(1 for x in K_all if abs(x@w-pk.mean())<abs(x@w-pr.mean()))
    correct += sum(1 for x in R_all if abs(x@w-pr.mean())<abs(x@w-pk.mean()))
    acc = correct/(len(K_all)+len(R_all))
    print(f'  拼接4层: d\'={dprime:.2f} 准确率={acc:.2f} {"✅深层可完全分离" if acc>0.95 else "❌"}', flush=True)

if __name__ == '__main__':
    main()
