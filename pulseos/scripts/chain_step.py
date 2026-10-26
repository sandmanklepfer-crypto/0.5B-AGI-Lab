#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chain_step.py —— 哈希链每一环的真实计算

每条的 hash 依赖 prev_hash + seq + at，
所以每一环的计算都是「独一无二」的，不可能复制粘贴。
"""
import json, sys, hashlib, math
from datetime import datetime, timezone


def work(seq, at, prev16):
    """
    用 seq / at / prev16 做一次确定性但不同的计算。
    保证每一条的 result 都是真的算出来的。
    """
    seed = f"{seq}:{at}:{prev16}"
    h = hashlib.sha256(seed.encode()).hexdigest()

    # ① 从 hash 派生出三个参数，保证每条都不同
    n = int(h[:6], 16) % 4000 + 1000          # 1000..5000
    k = int(h[6:10], 16) % 900 + 100           # 100..1000
    mod = int(h[10:14], 16) % 99 + 2           # 2..100

    # ② 真算：找 n 以内、与 mod 互质且是素数的个数
    def is_prime(x):
        if x < 2: return False
        if x % 2 == 0: return x == 2
        r = int(x ** 0.5)
        for d in range(3, r + 1, 2):
            if x % d == 0: return False
        return True

    primes = [i for i in range(2, n) if is_prime(i)]
    coprime = [p for p in primes if math.gcd(p, mod) == 1]

    # ③ 再用 hash 算一个校验数字
    checksum = sum(ord(c) for c in h) % 10000

    return {
        "task": f"在 2~{n} 中找素数，并统计与 {mod} 互质的个数",
        "result": f"{n} 以内有 {len(primes)} 个素数，其中 {len(coprime)} 个与 {mod} 互质",
        "detail": (
            f"seed = {seed}\n"
            f"派生出 n={n}  k={k}  mod={mod}\n"
            f"素数个数 = {len(primes)}\n"
            f"与 {mod} 互质的素数个数 = {len(coprime)}\n"
            f"hash 校验和 = {checksum}\n"
            f"最大素数 = {primes[-1] if primes else 0}"
        ),
        "n": n, "k": k, "mod": mod,
        "prime_count": len(primes),
        "coprime_count": len(coprime),
        "checksum": checksum,
        "seed": seed,
    }


if __name__ == "__main__":
    seq = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    at = sys.argv[2] if len(sys.argv) > 2 else "0"
    prev16 = sys.argv[3] if len(sys.argv) > 3 else "GENESIS"
    r = work(seq, at, prev16)
    r["seq"] = seq
    r["at"] = at
    r["computed_at"] = datetime.now(timezone.utc).isoformat()
    r["runtime"] = f"Python {sys.version.split()[0]}"
    print(json.dumps(r, ensure_ascii=False, indent=2))
