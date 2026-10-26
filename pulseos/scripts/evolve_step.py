#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evolve_step.py —— 每一步都吃上一步的结果

关键设计：
  第 N 步的输入 = 第 N-1 步的输出（不是独立的随机种子）
  所以：
    · 你不能跳步
    · 你不能只算最后一步
    · 想拿到最终值，必须走完全部 10 步

这是「陈列柜」和「真链」的区别。
"""
import json, sys, hashlib, math


def digest(x: str, rounds: int) -> str:
    """迭代 SHA-256 rounds 次 —— 纯文本 AI 手算不出"""
    h = x
    for _ in range(rounds):
        h = hashlib.sha256(h.encode()).hexdigest()
    return h


def work(seq: int, prev_value: str):
    """
    prev_value: 上一步的 value（第 0 步是 GENESIS）
    返回本步的 value 和可读的中间结果
    """
    # ① 用上一步的值 + 步号派生本次参数
    seed = hashlib.sha256((prev_value + "|" + str(seq)).encode()).hexdigest()

    n = int(seed[:6], 16) % 3000 + 1000       # 1000..4000
    rounds = int(seed[6:8], 16) % 40 + 20     # 20..60 次迭代哈希

    # ② 本步的真计算：n 以内的素数个数
    def is_prime(x):
        if x < 2: return False
        if x % 2 == 0: return x == 2
        r = int(x ** 0.5)
        for d in range(3, r + 1, 2):
            if x % d == 0: return False
        return True

    primes = [i for i in range(2, n) if is_prime(i)]

    # ③ 关键：本步的 value = 迭代哈希(上一步 + 素数个数 + n)
    payload = f"{prev_value}|{seq}|{n}|{len(primes)}"
    value = digest(payload, rounds)

    # ④ 校验和（让 AI 能快速核对，不用算完整 64 位）
    checksum = sum(ord(c) for c in value) % 100000

    return {
        "seq": seq,
        "input_prev": prev_value,
        "derived_n": n,
        "hash_rounds": rounds,
        "prime_count": len(primes),
        "prime_max": primes[-1] if primes else 0,
        "value": value,
        "checksum": checksum,
        "next_hint": f"下一步的输入 = {value[:24]}…（你必须把这个值传给第 {seq + 1} 步）",
    }


if __name__ == "__main__":
    seq = int(sys.argv[1])
    prev = sys.argv[2] if len(sys.argv) > 2 else "GENESIS"
    print(json.dumps(work(seq, prev), ensure_ascii=False, indent=2))
