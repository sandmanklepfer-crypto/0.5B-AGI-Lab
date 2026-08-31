#!/usr/bin/env python3
"""本地 lm_head 有效秩分析 (支持 q4_k/q6_k/f16/f32)
用法: lmhead_rank.py <model.gguf>
"""
import struct, sys
import numpy as np

QK = 256

def read_str(f):
    n = struct.unpack('<Q', f.read(8))[0]
    return f.read(n).decode('utf-8', 'replace')

def rd(fmt, f):
    return struct.unpack(fmt, f.read(struct.calcsize(fmt)))

def dequant_qX(raw, type_id, n_elem):
    if type_id == 0:   # f32
        return np.frombuffer(raw, dtype=np.float32)[:n_elem]
    if type_id == 1:   # f16
        return np.frombuffer(raw, dtype=np.float16)[:n_elem].astype(np.float32)
    if type_id == 12:  # q4_k: QK=256, 144B/block
        BS = 144
        nb = n_elem // QK
        a = np.frombuffer(raw, dtype=np.uint8).reshape(nb, BS)
        d = np.array([struct.unpack('<e', a[i, 136:138].tobytes())[0] for i in range(nb)], dtype=np.float32)
        dm = np.array([struct.unpack('<e', a[i, 138:140].tobytes())[0] for i in range(nb)], dtype=np.float32)
        sc = a[:, 128:136].astype(np.int8).astype(np.float32)
        ql = a[:, 0:128]
        qh = a[:, 128:136]
        out = np.zeros((nb, QK), dtype=np.float32)
        l = np.arange(32); is_ = l // 16
        for half in range(2):
            ql0 = ql[:, half*64:(half+1)*64]; qh0 = qh[:, half*32:(half+1)*32]
            q1 = ((ql0[:, l] & 0xF) | ((qh0[:, l] >> 0 & 3) << 4)).astype(np.float32) - 8
            q2 = ((ql0[:, l+32] & 0xF) | ((qh0[:, l] >> 2 & 3) << 4)).astype(np.float32) - 8
            q3 = ((ql0[:, l] >> 4) | ((qh0[:, l] >> 4 & 3) << 4)).astype(np.float32) - 8
            q4 = ((ql0[:, l+32] >> 4) | ((qh0[:, l] >> 6 & 3) << 4)).astype(np.float32) - 8
            b = half * 128
            out[:, b+0:b+32] = d[:, None] * dm[:, None] * sc[:, is_] * q1
            out[:, b+32:b+64] = d[:, None] * dm[:, None] * sc[:, is_+2] * q2
            out[:, b+64:b+96] = d[:, None] * dm[:, None] * sc[:, is_+4] * q3
            out[:, b+96:b+128] = d[:, None] * dm[:, None] * sc[:, is_+6] * q4
        return out.reshape(-1)
    if type_id == 14:  # q6_k: 210B/block
        BS = 210
        nb = n_elem // QK
        a = np.frombuffer(raw, dtype=np.uint8).reshape(nb, BS)
        ql = a[:, 0:128]; qh = a[:, 128:192]
        sc = a[:, 192:208].astype(np.int16); sc[sc > 127] -= 256
        d = np.array([struct.unpack('<e', a[i, 208:210].tobytes())[0] for i in range(nb)], dtype=np.float32)
        out = np.zeros((nb, QK), dtype=np.float32)
        l = np.arange(32); is_ = l // 16
        for half in range(2):
            ql0 = ql[:, half*64:(half+1)*64]; qh0 = qh[:, half*32:(half+1)*32]
            q1 = ((ql0[:, l] & 0x0F) | ((qh0[:, l] >> 0 & 0x03) << 4)).astype(np.int16) - 32
            q2 = ((ql0[:, l+32] & 0x0F) | ((qh0[:, l] >> 2 & 0x03) << 4)).astype(np.int16) - 32
            q3 = ((ql0[:, l] >> 4) | ((qh0[:, l] >> 4 & 0x03) << 4)).astype(np.int16) - 32
            q4 = ((ql0[:, l+32] >> 4) | ((qh0[:, l] >> 6 & 0x03) << 4)).astype(np.int16) - 32
            b = half * 128
            out[:, b+0:b+32] = d[:, None] * sc[:, is_] * q1
            out[:, b+32:b+64] = d[:, None] * sc[:, is_+2] * q2
            out[:, b+64:b+96] = d[:, None] * sc[:, is_+4] * q3
            out[:, b+96:b+128] = d[:, None] * sc[:, is_+6] * q4
        return out.reshape(-1)
    raise SystemExit(f'unsupported type {type_id}')

def main():
    path = sys.argv[1]
    with open(path, 'rb') as f:
        magic, ver, nt, nkv = rd('<IIQQ', f)
        for _ in range(nkv):
            read_str(f); t, = rd('<I', f)
            if t == 5: rd('<i', f)
            elif t == 4: rd('<I', f)
            elif t == 6: rd('<Q', f)
            elif t == 8: rd('<B', f)
            elif t == 3: rd('<f', f)
            elif t == 9: rd('<d', f)
            elif t in (0, 2): read_str(f)
            elif t == 10:
                n, = rd('<I', f)
                for _ in range(n): rd('<i', f)
            else: rd('<f', f)
        infos_start = f.tell()
        tensors = []
        for _ in range(nt):
            name = read_str(f)
            nd, = rd('<I', f)
            dims = rd('<'+'Q'*nd, f)
            typ, = rd('<I', f)
            off, = rd('<Q', f)
            tensors.append((name, dims, typ, off))
        infos_end = f.tell()
        data_begin = (infos_end + 31) & ~31
        # find output.weight
        for name, dims, typ, off in tensors:
            if name == 'output.weight':
                ne, nv = dims
                n_elem = ne * nv
                f.seek(data_begin + off)
                raw = f.read((n_elem // QK) * (210 if typ == 14 else 144) if typ in (12, 14) else n_elem * (4 if typ == 0 else 2))
                X = dequant_qX(raw, typ, n_elem).reshape(nv, ne)
                print(f'{path.split("/")[-1]}: output.weight {ne}x{nv} type={typ}')
                # 有效秩 (90%能量, 对 X.T@X 特征分解)
                cov = X.T @ X
                w = np.linalg.eigvalsh(cov)
                s = np.sqrt(np.clip(w, 0, None))
                s = np.sort(s)[::-1]
                e = s**2; total = e.sum()
                for pct in [50, 90, 99]:
                    k = int(np.argmax(e.cumsum()/total > pct/100)) + 1
                    print(f'  有效秩@{pct}% = {k}')
                print(f'  s1={s[0]:.1f} s100/s1={s[99]/s[0]:.3f} s1000/s1={(s[999]/s[0] if len(s)>999 else 0):.3f}')
                return
        print('output.weight not found')

if __name__ == '__main__':
    main()
