#!/usr/bin/env python3
"""probe_geom.py — 从 teacher_dump 输出解析 probe 激活, 计算泛化/涌现几何目标
用法: probe_geom.py <probe_dir> <out.npz> [--t-nembd 5120] [--proj 256]
输出 npz: {probes, D (距离矩阵), task_centers, icl_dirs, analogy_dirs}
"""
import struct, sys, os, glob, json, argparse
import numpy as np

def parse_act(path, t_nembd):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    assert magic == 0x54444344, f'bad magic {path}'
    prompt_len = np_ * 4; gen_len = ng * 4
    off = 16 + prompt_len + gen_len + ng * k * 4 + ng * k * 4
    # 跳过 pieces
    try:
        for j in range(ng):
            (pl,) = struct.unpack_from('<I', data, off); off += 4 + pl
    except Exception:
        pass
    n_act = (len(data) - off) // 4
    if n_act < ng * t_nembd:
        return None
    acts = np.frombuffer(data, dtype=np.float32, count=ng * t_nembd, offset=off).reshape(ng, t_nembd)
    return acts[0]  # max_new=1 -> 单激活

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("probe_dir")
    ap.add_argument("out")
    ap.add_argument("--t-nembd", type=int, default=5120)
    ap.add_argument("--proj", type=int, default=256)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.probe_dir, "p*.bin")))
    acts = []
    for f in files:
        a = parse_act(f, args.t_nembd)
        if a is not None:
            acts.append(a)
    A = np.stack(acts)  # [N, 5120]
    N = A.shape[0]
    print(f"[acts] {N} probes x {A.shape[1]}d", flush=True)

    # 投影 (SVD 主成分 256 维)
    U, S, Vt = np.linalg.svd(A, full_matrices=False)
    P = Vt[:args.proj].T
    Ap = A @ P  # [N, 256]
    # L2 归一化
    Ap = Ap / (np.linalg.norm(Ap, axis=1, keepdims=True) + 1e-12)

    # 距离矩阵 D[i,j] = 1 - |cos|(i,j)
    C = np.abs(Ap @ Ap.T)
    D = 1.0 - C

    np.savez(args.out, A=Ap, D=D)
    print(f"[saved] {args.out}  D={D.shape}  mean={D.mean():.3f} std={D.std():.3f}", flush=True)

if __name__ == "__main__":
    main()
