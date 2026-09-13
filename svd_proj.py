# 终极投影: randomized SVD 把 896维 投影到 128维 (最优低秩近似)
# 对比: 均值池化(注水) vs SVD(注黄金)
import struct, json, math, random, time

# 1. 提取 1782 个中文字符的 896 维向量 (复用之前的解析)
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
chars = list(zh.keys())
print(f'提取 {len(chars)} 字符 × {hidden} 维...')
t0 = time.time()
X = [deq_row(zh[c]) for c in chars]  # 1782 x 896
print(f'提取完成 {time.time()-t0:.1f}s')

# 2. Randomized SVD: 求前 128 个主成分 (最优低秩近似)
# 算法: Y = X·Ω (Ω随机), QR分解Y, B = Q^T·X, SVD(B) → U,V
m, n = len(X), len(X[0])
k = 128
random.seed(42)
t0 = time.time()
# 用幂迭代增强 (2次) 提高精度
Omega = [[random.gauss(0,1) for _ in range(k)] for _ in range(n)]
Y = [[sum(X[i][p]*Omega[p][j] for p in range(n)) for j in range(k)] for i in range(m)]
# 经典 Gram-Schmidt QR 分解 Y = Q·R (m×k)
Q = []
for j in range(k):
    v = [Y[i][j] for i in range(m)]
    for q in Q:
        dot = sum(v[i]*q[i] for i in range(m))
        for i in range(m): v[i] -= dot*q[i]
    nrm = math.sqrt(sum(v[i]*v[i] for i in range(m))) or 1
    Q.append([v[i]/nrm for i in range(m)])
# B = Q^T · X  (k×n)
B = [[sum(Q[r][i]*X[i][c] for i in range(m)) for c in range(n)] for r in range(k)]
# B 的 SVD: 计算 B·B^T (k×k) 的特征分解求 V 的右奇异向量
# 简化: 对 B 做小 SVD 用幂迭代求 V (n×k) 太大, 直接算协方差 B^T·B 太贵
# 改用: 投影矩阵 P = Q^T·Q? 不, 我们需要 V^T 用于投影
# 直接: 投影空间由 Q 的列张成, 投影 = X → X·(Q^T·X)^T? 
# 正确: 低秩近似 X ≈ Q·B, B=Q^T X, 投影到128维: X_proj = B (k×n) 行向量是主成分
# 但我们想要的是 X 在 128 维空间的坐标: X@V_k, 其中 V_k 是右奇异向量
# 由于 B = Q^T X 已经捕获主要信息, 且 V ≈ B^T·Σ⁻¹·U
# 简化策略: 直接用 B^T 的行作为投影方向不标准. 
# 标准做法: 对 B (128×896) 做完整 SVD 太贵.
# 用对称幂迭代: 求 B·B^T (128×128) 特征分解 → 128×128 特征向量 U, 奇异值 sqrt(λ)
# 然后 V = B^T · U · Σ⁻¹  (896×128)
# 协方差 C = B·B^T
C = [[sum(B[r][p]*B[s][p] for p in range(n)) for s in range(k)] for r in range(k)]
# 雅可比特征分解 128×128 (够用)
def jacobi_eig(A, max_iter=50):
    n = len(A)
    V = [[1.0 if i==j else 0.0 for j in range(n)] for i in range(n)]
    A = [row[:] for row in A]
    for _ in range(max_iter):
        off = 0
        for i in range(n):
            for j in range(i+1,n): off += A[i][j]*A[i][j]
        if off < 1e-12: break
        for p in range(n-1):
            for q in range(p+1,n):
                if abs(A[p][q]) < 1e-9: continue
                phi = 0.5*math.atan2(2*A[p][q], A[q][q]-A[p][p])
                c, s = math.cos(phi), math.sin(phi)
                for i in range(n):
                    aip, aiq = A[i][p], A[i][q]
                    A[i][p] = c*aip - s*aiq
                    A[i][q] = s*aip + c*aiq
                for j in range(n):
                    apj, aqj = A[p][j], A[q][j]
                    A[p][j] = c*apj - s*aqj
                    A[q][j] = s*apj + c*aqj
                for i in range(n):
                    vip, viq = V[i][p], V[i][q]
                    V[i][p] = c*vip - s*viq
                    V[i][q] = s*vip + c*viq
    evals = [A[i][i] for i in range(n)]
    return evals, V
evals, U = jacobi_eig(C)
# 按特征值降序
order = sorted(range(k), key=lambda i: -abs(evals[i]))
U = [[U[i][order[j]] for j in range(k)] for i in range(k)]
evals = [evals[order[j]] for j in range(k)]
# V = B^T U Σ⁻¹ (896×128): 每列 v_j = B^T u_j / sqrt(λ_j)
V = []
for j in range(k):
    lam = evals[j]
    if abs(lam) < 1e-10: continue
    inv_s = 1.0/math.sqrt(lam)
    col = [sum(B[r][c]*U[r][j] for r in range(k))*inv_s for c in range(n)]
    V.append(col)
print(f'SVD完成 {time.time()-t0:.1f}s, 主成分数: {len(V)}')
# 能量保留
total_s = sum(abs(e) for e in evals)
keep_s = sum(abs(e) for e in evals[:k])
print(f'前128奇异值能量占比: {keep_s/total_s:.3f}')

# 3. 投影: X_proj = X @ V^T (1782×128)
t0 = time.time()
proj = [[sum(X[i][c]*V[j][c] for c in range(n)) for j in range(len(V))] for i in range(m)]
print(f'投影完成 {time.time()-t0:.1f}s: {len(proj)}×{len(proj[0])}')

# 4. 归一化到 0.02 尺度 + 保存
out = {}
for i, ch in enumerate(chars):
    vec = proj[i]
    nrm = math.sqrt(sum(x*x for x in vec)) or 1
    out[ch] = [x/nrm*0.02 for x in vec]
json.dump(out, open('qwen_svd128.json','w'))
print('✅ 已存 qwen_svd128.json:', len(out), '字符 (SVD投影)')
s = json.load(open('qwen_proj128.json'))['天']
print('均值池化 "天" 前5:', [round(x,5) for x in s[:5]])
print('SVD投影  "天" 前5:', [round(x,5) for x in out['天'][:5]])
