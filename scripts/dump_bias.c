// dump_bias.c — 权重手术: 方向 → lm_head bias (2026-08-28)
// 用法: ./dump_bias <model.gguf> <dir.bin> <alpha> <out.bias.bin>
// 原理: bias[v] = alpha * (W @ d)[v], W = output.weight (反量化), d = 方向向量
// 效果: 每个 token 的 logits 永久 +bias[v], 方向固化进权重
#include "llama.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: %s <model.gguf> <dir.bin> <alpha> <out.bias.bin>\n", argv[0]); return 1; }
    const char* model_path = argv[1];
    const char* dir_path = argv[2];
    float alpha = (float)atof(argv[3]);
    const char* out_path = argv[4];

    struct llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 0;   // 纯 CPU 加载, 反量化在 CPU
    struct llama_model* m = llama_model_load_from_file(model_path, mp);
    if (!m) { fprintf(stderr, "model fail\n"); return 1; }
    const struct llama_vocab* vocab = llama_model_get_vocab(m);
    int n_vocab = llama_vocab_n_tokens(vocab);
    int n_embd = llama_model_n_embd(m);
    fprintf(stderr, "vocab=%d embd=%d\n", n_vocab, n_embd);

    float* W = (float*)malloc((size_t)n_vocab * n_embd * sizeof(float));
    if (!W) { fprintf(stderr, "alloc fail\n"); return 1; }
    if (!llama_model_get_tensor(m, "output.weight", W)) {
        fprintf(stderr, "get_tensor output.weight fail\n"); return 1;
    }
    fprintf(stderr, "W (%d x %d) dequantized\n", n_vocab, n_embd);

    float* d = (float*)malloc(n_embd * sizeof(float));
    FILE* f = fopen(dir_path, "rb");
    if (!f || fread(d, 4, n_embd, f) != (size_t)n_embd) { fprintf(stderr, "dir read fail\n"); return 1; }
    fclose(f);
    double dn = 0; for (int i = 0; i < n_embd; i++) dn += (double)d[i] * d[i];
    dn = sqrt(dn) + 1e-12;
    for (int i = 0; i < n_embd; i++) d[i] /= (float)dn;
    fprintf(stderr, "direction loaded, |d|=1\n");

    float* bias = (float*)calloc(n_vocab, sizeof(float));
    double bias_max = 0, bias_abs = 0;
    for (int v = 0; v < n_vocab; v++) {
        const float* wrow = W + (size_t)v * n_embd;
        double s = 0;
        for (int i = 0; i < n_embd; i++) s += (double)wrow[i] * d[i];
        bias[v] = (float)(s * alpha);
        if (fabs(bias[v]) > bias_abs) bias_abs = fabs(bias[v]);
    }
    fprintf(stderr, "bias range: |max|=%.4f (alpha=%.3f)\n", bias_abs, alpha);

    FILE* fo = fopen(out_path, "wb");
    fwrite(bias, 4, n_vocab, fo);
    fclose(fo);
    fprintf(stderr, "bias written: %s (%d x f32)\n", out_path, n_vocab);

    // top 词 (bias 最大的)
    int idx[12] = {0};
    for (int v = 0; v < n_vocab; v++) {
        for (int k = 0; k < 12; k++) if (bias[v] > bias[idx[k]]) { for (int j = 11; j > k; j--) idx[j] = idx[j-1]; idx[k] = v; break; }
    }
    char piece[64];
    fprintf(stderr, "--- top bias tokens ---\n");
    for (int k = 0; k < 12; k++) {
        int plen = llama_token_to_piece(vocab, idx[k], piece, 64, 0, true);
        piece[plen < 0 ? 0 : plen] = 0;
        fprintf(stderr, "top[%d] %+.4f %s\n", k, bias[idx[k]], piece);
    }
    free(W); free(d); free(bias);
    llama_model_free(m);
    return 0;
}
