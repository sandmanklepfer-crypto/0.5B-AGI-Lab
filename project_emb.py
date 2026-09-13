# 从 Qwen Q8_0 embedding 提取中文字符向量 → SVD 投影到 128 维 → 存初始化文件
import struct, json
import numpy as np

data = open('qwen2.5-0.5b-instruct-q4_k_m.gguf','rb').read()
# 解析到 token_embd
off = 8
n_tensors = struct.unpack('<Q', data[off:off+8])[0]; off += 8
n_kv = struct.unpack('<Q', data[off:off+8])[0]; off += 8
def read_str(o):
    ln = struct.unpack('<Q', data[o:o+8])[0]; o += 8
    return data[o:o+ln].decode('utf8','replace'), o+ln
for i in range(n_kv):
    k, off = read_str(off)
    t = struct.unpack('<I', data[off:off+4])[0]; off += 4
    if t == 8: _, off = read_str(off)
    elif t == 9:
        at = struct.unpack('<I', data[off:off+4])[0]; off += 4
        n = struct.unpack('<Q', data[off:off+8])[0]; off += 8
        for j in range(n):
            if at == 8: _, off = read_str(off)
            else: off += 4
    elif t == 0: off += 1
    elif t == 1: off += 1
    elif t == 2: off += 2
    elif t == 3: off += 2
    elif t == 4: off += 4
    elif t == 5: off += 4
    elif t == 6: off += 4
    elif t == 7: off += 1
    else: off += 8

emb = None
for i in range(n_tensors):
    name, off = read_str(off)
    nd = struct.unpack('<I', data[off:off+4])[0]; off += 4
    dims = [struct.unpack('<Q', data[off+8*j:off+8*j+8])[0] for j in range(nd)]; off += 8*nd
    ttype = struct.unpack('<I', data[off:off+4])[0]; off += 4
    toff = struct.unpack('<Q', data[off:off+8])[0]; off += 8
    if 'token_embd' in name: emb = (dims, ttype, toff); break
hidden, vocab = emb[0][0], emb[0][1]
emb_off = emb[2]
print(f'embedding: {vocab}x{hidden}, Q8_0, offset {emb_off}')

# Q8_0 反量化函数: 块大小32, 每块 2字节scale(fp16) + 32 int8
def deq_row(row_idx):
    start_elem = row_idx * hidden
    blk_start = (start_elem // 32) * 34  # 每32元素34字节
    # 行可能跨块: 896 = 28*32, 恰好整块!
    vals = []
    for i in range(hidden):
        elem = start_elem + i
        blk = elem // 32
        pos = elem % 32
        b_off = emb_off + blk * 34
        d = struct.unpack('<e', data[b_off:b_off+2])[0]
        q = struct.unpack('<b', bytes([data[b_off+2+pos]]))[0]
        vals.append(q * d)
    return vals

# 读中文字符映射
zh = json.load(open('zh_token_map.json'))
print('中文字符映射数:', len(zh))

# 提取前 256 个映射字符的向量 (够用: 我们的 vocab 也就几百)
chars = list(zh.keys())[:256]
ids = [zh[c] for c in chars]
print('提取', len(chars), '个字符向量...')
matrix = np.array([deq_row(i) for i in ids], dtype=np.float32)  # (256, 896)
print('矩阵:', matrix.shape)

# SVD 投影到 128 维
U, S, Vt = np.linalg.svd(matrix, full_matrices=False)
proj_128 = matrix @ Vt[:128].T  # (256, 128)
print('投影后:', proj_128.shape, '| 能量保留:', (S[:128].sum()/S.sum()).round(3))

# 保存: 字符 → 128维向量
out = {ch: proj_128[i].tolist() for i, ch in enumerate(chars)}
json.dump(out, open('qwen_proj128.json', 'w'))
print('已存 qwen_proj128.json:', len(out), '个字符向量')
print('样例 天:', out['天'][:5])
