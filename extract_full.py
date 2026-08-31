# 完整: 提取 Qwen embedding → 池化投影128维 → 存 json
import struct, json
data = open('qwen2.5-0.5b-instruct-q4_k_m.gguf','rb').read()
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
tensor_offsets = {}
for i in range(n_tensors):
    name, off = read_str(off)
    nd = struct.unpack('<I', data[off:off+4])[0]; off += 4
    dims = [struct.unpack('<Q', data[off+8*j:off+8*j+8])[0] for j in range(nd)]; off += 8*nd
    ttype = struct.unpack('<I', data[off:off+4])[0]; off += 4
    toff = struct.unpack('<Q', data[off:off+8])[0]; off += 8
    tensor_offsets[name] = (dims, ttype, toff)
data_start = (off + 31) & ~31
dims, ttype, toff = tensor_offsets['token_embd.weight']
hidden, vocab = dims[0], dims[1]
emb_base = data_start + toff
print(f'token_embd: {vocab}x{hidden} Q8_0 @ {emb_base}')

def deq_row(row_idx):
    start = row_idx * hidden
    out = []
    for i in range(hidden):
        elem = start + i
        blk = elem // 32
        pos = elem % 32
        b = emb_base + blk * 34
        d = struct.unpack('<e', data[b:b+2])[0]
        q = struct.unpack('<b', bytes([data[b+2+pos]]))[0]
        out.append(q * d)
    return out

zh = json.load(open('zh_token_map.json'))
# 用完整映射, 取能映射到的所有字
chars = list(zh.keys())
print('可映射中文字符:', len(chars))
out = {}
for ch in chars:
    vec = deq_row(zh[ch])
    proj = [sum(vec[i*7:(i+1)*7])/7.0 for i in range(128)]
    n = sum(x*x for x in proj) ** 0.5 or 1
    out[ch] = [x/n*0.02 for x in proj]
json.dump(out, open('qwen_proj128.json','w'))
print('✅ 已存 qwen_proj128.json:', len(out), '字符')
# 抽样验证
import random
samples = random.sample(list(out.items()), 3)
for ch, v in samples:
    print(f'  "{ch}": 前5维', [round(x,5) for x in v[:5]])
