// geomgpu.c — 几何计算卡 GEOMGPU v1 (2026-08-27)
// 脉动阵列(GEMM/热核/幂迭代) + 向量单元(NORM/DOT/PROJ/KARCHER/GEOSTEP)
// ISA: 通用卡没有的几何指令 —— 热核扩散/谱分解/测地线/Karcher 都在卡上
//
// 演示: 复现身份切割 (identity2: 30身份+30普通, 896维层23激活)
//   热核 → 幂迭代谱聚类(符号分簇) → Karcher均值(方向) → 测地线注入步
// 验收: 聚类纯度≈100% (vs python 100%), 方向 cos(d_karc, d_lda)≈0.972
//
// 用法: ./geomgpu
// 数据: /workspace/identity2/{pos,neg}_L*.bin (dump_layers4_new 格式)

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include <glob.h>

#define PE_N   32          // 阵列宽度 (向量单元 lane 数)
#define NPT    60          // 点数 (30 pos + 30 neg)
#define DIM    896         // 激活维度
#define LAYER  23

// ── 算子计数器 ──
long long cyc_heat = 0, cyc_gemm = 0, cyc_powit = 0;
long long cyc_vec  = 0;    // 向量单元总时钟

// ── 卡上数据寄存器 ──
static float X[NPT][DIM];        // 激活点集 (数据面)
static float S[NPT][NPT];        // 相似度/热核矩阵 (权重驻留区)
static float wv[DIM];            // 向量寄存器 (结果/方向)
static int   labels[NPT];

// ── 向量单元: PE_N 个 lane 并行 (每指令时钟 = ceil(DIM/PE_N)) ──
static void vu_norm(float* v, int n) {
    float s = 0; for (int i = 0; i < n; i++) s += v[i] * v[i];
    s = sqrtf(s) + 1e-9f;
    for (int i = 0; i < n; i++) v[i] /= s;
    cyc_vec += (n + PE_N - 1) / PE_N * 2;
}
static float vu_dot(const float* a, const float* b, int n) {
    float s = 0; for (int i = 0; i < n; i++) s += a[i] * b[i];
    cyc_vec += (n + PE_N - 1) / PE_N;
    return s;
}
// 切空间投影: v ← v - (v·d)d   (球面切空间)
static void vu_proj(float* v, const float* d, int n) {
    float c = vu_dot(v, d, n);
    for (int i = 0; i < n; i++) v[i] -= c * d[i];
    cyc_vec += (n + PE_N - 1) / PE_N;
}
// 测地线一步: x ← normalize(x + α·proj(dir))   (切空间小步+指数映射)
static void vu_geostep(float* x, const float* dir, float alpha, int n) {
    float t[DIM]; memcpy(t, dir, n * 4);
    // 投影到 x 的切空间 (去掉沿 x 的分量 → 保证球面上走)
    vu_proj(t, x, n);
    vu_norm(t, n);
    for (int i = 0; i < n; i++) x[i] += alpha * t[i];
    vu_norm(x, n);
    cyc_vec += (n + PE_N - 1) / PE_N * 2;
}
// Karcher 均值: μ ← normalize(mean(log_μ(x_i))) 球面迭代
static void vu_karcher(float* mu, const int* idx, int cnt, int n, int iters) {
    float p[DIM];
    for (int i = 0; i < n; i++) p[i] = mu[i];
    vu_norm(p, n);
    for (int it = 0; it < iters; it++) {
        float acc[DIM]; memset(acc, 0, sizeof(acc));
        for (int k = 0; k < cnt; k++) {
            const float* x = X[idx[k]];
            float c = vu_dot(p, x, n);
            c = fminf(1.f, fmaxf(-1.f, c));
            float th = acosf(c);
            float f = (th > 1e-6f) ? th / sinf(th) : 1.f;
            for (int i = 0; i < n; i++) acc[i] += (x[i] - c * p[i]) * f;
        }
        for (int i = 0; i < n; i++) p[i] += acc[i] / cnt;
        vu_norm(p, n);
    }
    memcpy(mu, p, n * 4);
}

// ── MAC 阵列: 小矩阵 GEMM (NPT×NPT) 用于热核/幂迭代 ──
static void gemm_nt(const float* A, const float* B, float* C, int m, int n, int k) {
    // C[m×n] = A[m×k] × B^T[n×k]  (A行向量 × B行向量 → 点积矩阵)
    for (int i = 0; i < m; i++)
        for (int j = 0; j < n; j++) {
            float s = 0;
            for (int t = 0; t < k; t++) s += A[i * k + t] * B[j * k + t];
            C[i * n + j] = s;
        }
    cyc_gemm += (m / PE_N + 1) * (n / PE_N + 1) * k;
}
static void gemv(const float* M, const float* v, float* out, int m, int n) {
    for (int i = 0; i < m; i++) {
        float s = 0;
        for (int j = 0; j < n; j++) s += M[i * n + j] * v[j];
        out[i] = s;
    }
    cyc_gemm += (m / PE_N + 1) * n;
}

// ── 数据加载: dump_layers4_new 格式 (8字节头 + 24层×896×4B) ──
static int load_acts(const char* pat, float* dst, int base) {
    glob_t g; glob(pat, 0, NULL, &g);
    int cnt = 0;
    for (size_t f = 0; f < g.gl_pathc && base + cnt < NPT; f++) {
        FILE* fp = fopen(g.gl_pathv[f], "rb");
        if (!fp) continue;
        int nl, ne; fread(&nl, 4, 1, fp); fread(&ne, 4, 1, fp);
        fseek(fp, 8 + LAYER * ne * 4, SEEK_SET);
        float* row = dst + (base + cnt) * DIM;
        if (fread(row, 4, ne, fp) != (size_t)ne) { fclose(fp); continue; }
        fclose(fp); cnt++;
    }
    globfree(&g);
    return cnt;
}

// ── 卡上主流程: 身份切割 ──
int main(void) {
    // 1. 装载激活 (数据面) + 归一化 (向量单元)
    int npos = load_acts("/workspace/identity2/pos_L*.bin", X[0], 0);
    int nneg = load_acts("/workspace/identity2/neg_L*.bin", X[0], npos);
    printf("[LOAD] pos=%d neg=%d (共%d点×%d维)\n", npos, nneg, npos + nneg, DIM);
    for (int i = 0; i < npos + nneg; i++) vu_norm(X[i], DIM);

    // 2. 相似度矩阵 S = X·X^T (MAC阵列) → 热核 H = exp(-(2-2S)/(2σ))
    float S2[NPT][NPT];
    gemm_nt(X[0], X[0], S2[0], NPT, NPT, DIM);
    float sig = 0; int nn = 0;
    for (int i = 0; i < NPT; i++) for (int j = i + 1; j < NPT; j++) {
        float d2 = 2.f - 2.f * S2[i][j];
        float s[NPT*NPT]; (void)s;
        // 收集距离平方求中位σ (简化: 用均值)
        sig += d2; nn++;
    }
    sig = sig / nn;
    float H[NPT][NPT];
    for (int i = 0; i < NPT; i++)
        for (int j = 0; j < NPT; j++) {
            float d2 = 2.f - 2.f * S2[i][j];
            H[i][j] = (i == j) ? 0.f : expf(-d2 / (2.f * sig));
        }
    // 对称归一化 P = D^-1/2 H D^-1/2
    float deg[NPT];
    for (int i = 0; i < NPT; i++) { deg[i] = 0; for (int j = 0; j < NPT; j++) deg[i] += H[i][j]; }
    float P[NPT][NPT];
    for (int i = 0; i < NPT; i++)
        for (int j = 0; j < NPT; j++)
            P[i][j] = H[i][j] / sqrtf(deg[i] * deg[j] + 1e-9f);
    printf("[HEAT] 热核构建完成 σ=%.4f (卡上: 相似度GEMM+指数单元)\n", sig);
    cyc_heat += (NPT / PE_N + 1) * (NPT / PE_N + 1) * NPT;   // 热核构建时钟

    // 3. 幂迭代取 top-2 特征向量 (谱分解, 卡上)
    float v[NPT]; srand(7);
    for (int i = 0; i < NPT; i++) v[i] = (float)rand() / RAND_MAX - 0.5f;
    float ev[NPT]; memcpy(ev, v, NPT * 4);
    float psi2[NPT];
    for (int order = 0; order < 2; order++) {
        for (int it = 0; it < 30; it++) {
            float out[NPT];
            gemv(P[0], ev, out, NPT, NPT);
            float nrm = 0; for (int i = 0; i < NPT; i++) nrm += out[i] * out[i];
            nrm = sqrtf(nrm) + 1e-9f;
            for (int i = 0; i < NPT; i++) out[i] /= nrm;
            memcpy(ev, out, NPT * 4);
        }
        cyc_powit += 30 * (NPT / PE_N + 1) * NPT;
        if (order == 0) {
            // deflation: P ← P - λ ψ ψ^T
            float lam = vu_dot(ev, ev, 1); // 占位
            (void)lam;
            float P2[NPT][NPT];
            for (int i = 0; i < NPT; i++)
                for (int j = 0; j < NPT; j++)
                    P2[i][j] = P[i][j] - 0.99f * ev[i] * ev[j];
            memcpy(P, P2, sizeof(P));
            srand(9);
            for (int i = 0; i < NPT; i++) ev[i] = (float)rand() / RAND_MAX - 0.5f;
        } else {
            memcpy(psi2, ev, NPT * 4);
        }
    }
    printf("[SPECTRAL] 幂迭代完成 (top-2 特征向量, 卡上30轮×2)\n");

    // 4. 符号分簇 (Fiedler 向量符号 = 谱聚类)
    for (int i = 0; i < NPT; i++) labels[i] = (psi2[i] >= 0) ? 1 : 0;
    // 纯度 (真实标签: 前30=身份1, 后30=普通0)
    int match = 0;
    for (int i = 0; i < NPT; i++) {
        int truth = (i < npos) ? 1 : 0;
        match += (labels[i] == truth);
    }
    int match_f = (match > NPT - match) ? match : NPT - match;
    printf("[CLUSTER] 谱聚类纯度 = %d/%d = %.1f%% (python参考100%%)\n",
           match_f, NPT, 100.f * match_f / NPT);

    // 5. Karcher 均值 (每簇球面重心) → 身份方向
    int idx1[NPT], c1 = 0, idx2[NPT], c2 = 0;
    for (int i = 0; i < NPT; i++) {
        if (labels[i]) idx1[c1++] = i; else idx2[c2++] = i;
    }
    float mu1[DIM], mu2[DIM];
    for (int i = 0; i < DIM; i++) mu1[i] = X[idx1[0]][i];
    for (int i = 0; i < DIM; i++) mu2[i] = X[idx2[0]][i];
    vu_karcher(mu1, idx1, c1, DIM, 30);
    vu_karcher(mu2, idx2, c2, DIM, 30);
    for (int i = 0; i < DIM; i++) wv[i] = mu1[i] - mu2[i];
    vu_norm(wv, DIM);
    printf("[KARCHER] 簇均值完成 (簇1=%d点 簇2=%d点) → 身份方向已驻留wv\n", c1, c2);

    // 6. 与已知 LDA 方向对比 (d_all.bin, 期望 cos≈0.972)
    FILE* fd = fopen("/workspace/identity2/d_all.bin", "rb");
    if (fd) {
        float dl[DIM];
        if (fread(dl, 4, DIM, fd) == DIM) {
            float n = 0; for (int i = 0; i < DIM; i++) n += dl[i] * dl[i];
            n = sqrtf(n) + 1e-9f;
            for (int i = 0; i < DIM; i++) dl[i] /= n;
            float c = fabsf(vu_dot(wv, dl, DIM));
            printf("[VALID] 卡上方向 vs LDA方向 cos = %.3f (python参考0.972)\n", c);
        }
        fclose(fd);
    }

    // 7. 测地线注入一步: 沿身份方向推一个点 (卡上几何指令)
    float probe[DIM];
    memcpy(probe, X[0], DIM * 4);
    vu_geostep(probe, wv, 0.5f, DIM);
    float moved = 0;
    for (int i = 0; i < DIM; i++) moved += (probe[i] - X[0][i]) * (probe[i] - X[0][i]);
    printf("[GEOSTEP] 测地线注入: 点0沿方向推0.5 → 位移%.4f (球面保持)\n", sqrtf(moved));

    // 8. 算子时钟报告
    printf("\n═══ GEOMGPU 算子时钟报告 (阵列%d×%d @1GHz) ═══\n", PE_N, PE_N);
    printf("  GEMM(相似度) : %lld 时钟  (%lld us @1GHz)\n", cyc_gemm, cyc_gemm);
    printf("  HEAT(热核)   : %lld 时钟  (%.2f ms)\n", cyc_heat, cyc_heat / 1e6);
    printf("  SPECTRAL(幂迭代): %lld 时钟  (%.2f ms)\n", cyc_powit, cyc_powit / 1e6);
    printf("  VEC(向量单元): %lld 时钟  (%.2f ms)\n", cyc_vec, cyc_vec / 1e6);
    printf("  合计         : %lld 时钟 ≈ %.2f ms @1GHz\n",
           cyc_gemm + cyc_heat + cyc_powit + cyc_vec,
           (cyc_gemm + cyc_heat + cyc_powit + cyc_vec) / 1e6);
    return 0;
}
