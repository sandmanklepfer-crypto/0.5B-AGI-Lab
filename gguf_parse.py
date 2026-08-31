import struct, sys

# GGUF v3 正确类型表
GGUF_TYPES = {
    0: 'UINT8', 1: 'INT8', 2: 'UINT16', 3: 'INT16', 4: 'UINT32', 5: 'INT32',
    6: 'FLOAT32', 7: 'BOOL', 8: 'STRING', 9: 'ARRAY', 10: 'UINT64', 11: 'INT64', 12: 'FLOAT64'
}
GGML_TYPES = {0:'F32',1:'F16',2:'Q4_0',3:'Q4_1',6:'Q5_0',7:'Q5_1',8:'Q8_0',10:'Q2_K',11:'Q3_K',12:'Q4_K',13:'Q5_K',14:'Q6_K',15:'Q8_K'}

data = open('qwen2.5-0.5b-instruct-q4_k_m.gguf','rb').read()
off = 8
n_tensors = struct.unpack('<Q', data[off:off+8])[0]; off += 8
n_kv = struct.unpack('<Q', data[off:off+8])[0]; off += 8

def read_str(o):
    ln = struct.unpack('<Q', data[o:o+8])[0]; o += 8
    return data[o:o+ln].decode('utf8','replace'), o+ln

kv = {}
for i in range(n_kv):
    k, off = read_str(off)
    t = struct.unpack('<I', data[off:off+4])[0]; off += 4
    tn = GGUF_TYPES.get(t, '?')
    if t == 0: v = data[off]; off += 1
    elif t == 1: v = struct.unpack('<b', data[off:off+1])[0]; off += 1
    elif t == 2: v = struct.unpack('<H', data[off:off+2])[0]; off += 2
    elif t == 3: v = struct.unpack('<h', data[off:off+2])[0]; off += 2
    elif t == 4: v = struct.unpack('<I', data[off:off+4])[0]; off += 4
    elif t == 5: v = struct.unpack('<i', data[off:off+4])[0]; off += 4
    elif t == 6: v = struct.unpack('<f', data[off:off+4])[0]; off += 4
    elif t == 7: v = bool(data[off]); off += 1
    elif t == 8: v, off = read_str(off)
    elif t == 9:
        at = struct.unpack('<I', data[off:off+4])[0]; off += 4
        n = struct.unpack('<Q', data[off:off+8])[0]; off += 8
        arr = []
        for j in range(n):
            if at == 0: arr.append(data[off]); off += 1
            elif at == 1: arr.append(struct.unpack('<b', data[off:off+1])[0]); off += 1
            elif at == 2: arr.append(struct.unpack('<H', data[off:off+2])[0]); off += 2
            elif at == 3: arr.append(struct.unpack('<h', data[off:off+2])[0]); off += 2
            elif at == 4: arr.append(struct.unpack('<I', data[off:off+4])[0]); off += 4
            elif at == 5: arr.append(struct.unpack('<i', data[off:off+4])[0]); off += 4
            elif at == 6: arr.append(struct.unpack('<f', data[off:off+4])[0]); off += 4
            elif at == 7: arr.append(bool(data[off])); off += 1
            elif at == 8: s, off = read_str(off); arr.append(s)
            elif at in (10,11,12): arr.append(struct.unpack('<Q' if at==10 else '<q' if at==11 else '<d', data[off:off+8])[0]); off += 8
            else: off += 8
        v = arr
    elif t in (10,11,12):
        fmt = '<Q' if t==10 else '<q' if t==11 else '<d'
        v = struct.unpack(fmt, data[off:off+8])[0]; off += 8
    else: v = None; off += 8
    kv[k] = v

print('KV 解析完成, 共', len(kv), '项')
print('关键KV:')
for k in ['general.architecture','general.name','tokenizer.ggml.model','tokenizer.ggml.tokens']:
    if k in kv:
        v = kv[k]
        print(' ', k, '=', (str(v)[:80] + '...') if isinstance(v, str) and len(str(v))>80 else (f'<list of {len(v)}>' if isinstance(v,list) else v))

# tensor infos
print('\n=== Tensor 列表 (前25个) ===')
tinfos = []
data_start = off
for i in range(n_tensors):
    name, off = read_str(off)
    nd = struct.unpack('<I', data[off:off+4])[0]; off += 4
    dims = [struct.unpack('<Q', data[off+8*j:off+8*j+8])[0] for j in range(nd)]; off += 8*nd
    ttype = struct.unpack('<I', data[off:off+4])[0]; off += 4
    toff = struct.unpack('<Q', data[off:off+8])[0]; off += 8
    tinfos.append((name, dims, ttype, toff))
    if i < 25 or 'token_embd' in name or 'output' in name:
        print(f'  {name}: dims={dims} type={GGML_TYPES.get(ttype, ttype)} offset={toff}')
print('...')
print('tensor data 起点:', data_start)

# 保存 token_embd 信息
for t in tinfos:
    if 'token_embd' in t[0]:
        print('\n*** token_embd:', t, 'type=', GGML_TYPES.get(t[2], t[2]))
        # vocab/hidden 维
        print('    vocab:', t[1][0], 'hidden:', t[1][1] if len(t[1])>1 else '?')
