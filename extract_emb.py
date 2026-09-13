import struct, json, sys

# GGUF v3 类型表 + 解析 (复用, 精简)
data = open('qwen2.5-0.5b-instruct-q4_k_m.gguf','rb').read()
off = 8
n_tensors = struct.unpack('<Q', data[off:off+8])[0]; off += 8
n_kv = struct.unpack('<Q', data[off:off+8])[0]; off += 8
def read_str(o):
    ln = struct.unpack('<Q', data[o:o+8])[0]; o += 8
    return data[o:o+ln].decode('utf8','replace'), o+ln
GGUF_TYPES = {0:'UINT8',1:'INT8',2:'UINT16',3:'INT16',4:'UINT32',5:'INT32',6:'FLOAT32',7:'BOOL',8:'STRING',9:'ARRAY',10:'UINT64',11:'INT64',12:'FLOAT64'}
for i in range(n_kv):
    k, off = read_str(off)
    t = struct.unpack('<I', data[off:off+4])[0]; off += 4
    if t == 0: off += 1
    elif t == 1: off += 1
    elif t == 2: off += 2
    elif t == 3: off += 2
    elif t == 4: off += 4
    elif t == 5: off += 4
    elif t == 6: off += 4
    elif t == 7: off += 1
    elif t == 8: _, off = read_str(off)
    elif t == 9:
        at = struct.unpack('<I', data[off:off+4])[0]; off += 4
        n = struct.unpack('<Q', data[off:off+8])[0]; off += 8
        for j in range(n):
            if at == 0: off += 1
            elif at == 1: off += 1
            elif at == 2: off += 2
            elif at == 3: off += 2
            elif at == 4: off += 4
            elif at == 5: off += 4
            elif at == 6: off += 4
            elif at == 7: off += 1
            elif at == 8: _, off = read_str(off)
            else: off += 8
    else: off += 8

# 找 token_embd (Q8_0)
emb_info = None
for i in range(n_tensors):
    name, off = read_str(off)
    nd = struct.unpack('<I', data[off:off+4])[0]; off += 4
    dims = [struct.unpack('<Q', data[off+8*j:off+8*j+8])[0] for j in range(nd)]; off += 8*nd
    ttype = struct.unpack('<I', data[off:off+4])[0]; off += 4
    toff = struct.unpack('<Q', data[off:off+8])[0]; off += 8
    if 'token_embd' in name:
        emb_info = (dims, ttype, toff)
        break
print('token_embd:', emb_info, '(Q8_0=8)')
dims, ttype, toff = emb_info
hidden, vocab = dims[0], dims[1]  # 896, 151936

# Q8_0 反量化: 每32元素块 = 1个fp16 scale + 32个int8
def dequant_q8_0(blk):
    d = struct.unpack('<e', blk[0:2])[0]  # fp16 scale
    qs = blk[2:34]  # 32 int8
    return [struct.unpack('<b', bytes([qs[i]]))[0] * d for i in range(32)]

# 我们小模型需要的词 (从 core_fixed RealBPE 的 vocab)
# 用 Qwen tokenizer 的 tokens 列表映射
tokens_kv = None
# 简化: 直接测试几个已知字符在 Qwen vocab 的位置 —— 需要 tokenizer 数据
# 重新解析拿到 tokenizer.ggml.tokens
print('需要 Qwen tokenizer tokens 来映射字符→行号...')
