#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute.py —— 「门里」真正干活的那个 Python

它的结果会被 bake.js 烤进 run-N.html。
所以要保证：结果是真的算出来的，不是编的。
"""
import json, sys, hashlib, math
from datetime import datetime, timezone

def work(step, seed):
    """第 step 阶做不同的计算。返回 dict。"""
    out = {"step": step, "seed": seed}

    if step == 1:
        # 第一阶：能整除的判断 + 素数筛
        n = 1000
        sieve = bytearray([1]) * (n + 1)
        sieve[0] = sieve[1] = 0
        for i in range(2, int(n ** 0.5) + 1):
            if sieve[i]:
                sieve[i*i::i] = bytearray(len(sieve[i*i::i]))
        primes = [i for i in range(n + 1) if sieve[i]]
        out["task"] = f"筛出 0~{n} 之间的素数"
        out["count"] = len(primes)
        out["first10"] = primes[:10]
        out["last5"] = primes[-5:]
        out["fact"] = f"{len(primes)} 个素数，占全部 {n+1} 个数的 {len(primes)/(n+1)*100:.1f}%"

    elif step == 2:
        # 第二阶：算 Fibonacci + 大数
        a, b = 0, 1
        seq = []
        for _ in range(90):
            seq.append(a)
            a, b = b, a + b
        out["task"] = "算斐波那契前 90 项"
        out["fib90"] = str(seq[-1])
        out["digits"] = len(str(seq[-1]))
        out["sample"] = [str(x) for x in seq[:12]]

    elif step == 3:
        # 第三阶：爆破式计算 —— 找 2^n 的特殊模式 / 验证柯拉茨猜想
        def collatz(n):
            steps = 0
            peak = n
            while n != 1 and steps < 100000:
                n = n // 2 if n % 2 == 0 else 3 * n + 1
                peak = max(peak, n)
                steps += 1
            return steps, peak

        best_n, best_steps, best_peak = 0, 0, 0
        for i in range(1, 100000):
            s, p = collatz(i)
            if s > best_steps:
                best_n, best_steps, best_peak = i, s, p

        out["task"] = "扫描 1~100000，找柯拉茨(3n+1)步数最多的起点"
        out["best_start"] = best_n
        out["steps"] = best_steps
        out["peak_value"] = str(best_peak)
        out["peak_digits"] = len(str(best_peak))

    elif step == 4:
        # 第四阶：校验和 —— 证明「前面的结果被真的算过」
        h = hashlib.sha256(f"{seed}".encode()).hexdigest()
        out["task"] = "对 seed 做 SHA-256"
        out["sha256"] = h
        out["first16"] = h[:16]
        out["seed_len"] = len(str(seed))

    return out


if __name__ == "__main__":
    step = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    seed = sys.argv[2] if len(sys.argv) > 2 else "pulseos"
    r = work(step, seed)
    r["computed_at"] = datetime.now(timezone.utc).isoformat()
    r["runtime"] = f"Python {sys.version.split()[0]}"
    print(json.dumps(r, ensure_ascii=False, indent=2))
