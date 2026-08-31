// test_cvec.c — 诊断 cvec 注入在 GPU 上的真实效果 (2026-08-28)
// 两个 context: 无注入 vs 注入(随机方向×strength), decode 同一 prompt, 对比 logits top-5
#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static void print_top5(const char* tag, struct llama_context* ctx, const struct llama_vocab* vocab, float* logits, int n_vocab) {
    int idx[5] = {0,0,0,0,0};
    for (int v = 0; v < n_vocab; v++) {
        for (int k = 0; k < 5; k++) {
            if (logits[v] > logits[idx[k]]) {
                for (int j = 4; j > k; j--) idx[j] = idx[j-1];
                idx[k] = v; break;
            }
        }
    }
    char piece[64];
    printf("%s top5:", tag);
    for (int k = 0; k < 5; k++) {
        int plen = llama_token_to_piece(vocab, idx[k], piece, 64, 0, true);
        piece[plen < 0 ? 0 : plen] = 0;
        printf(" [%d]%.3f %s", idx[k], logits[idx[k]], piece);
    }
    printf("\n");
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <model> <prompt> [strength] [dir_file] [il_layer]\n", argv[0]); return 1; }
    const char* model_path = argv[1];
    const char* prompt = argv[2];
    float strength = argc > 3 ? atof(argv[3]) : 0.001f;
    const char* dir_path = argc > 4 ? argv[4] : NULL;
    int il_only = argc > 5 ? atoi(argv[5]) : -1;

    struct llama_model_params mp = llama_model_default_params(); mp.n_gpu_layers = 99;
    struct llama_model* m = llama_model_load_from_file(model_path, mp);
    if (!m) { fprintf(stderr, "model fail\n"); return 1; }
    int n_layer = llama_model_n_layer(m);
    int n_embd = llama_model_n_embd(m);
    const struct llama_vocab* vocab = llama_model_get_vocab(m);
    int n_vocab = llama_vocab_n_tokens(vocab);

    // 方向: 文件或随机
    float* dir = (float*)malloc(n_embd * sizeof(float));
    if (dir_path) {
        FILE* f = fopen(dir_path, "rb");
        if (!f) { fprintf(stderr, "dir file fail\n"); return 1; }
        fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
        if (sz < n_embd * 4) { fprintf(stderr, "dir file too small (%ld)\n", sz); return 1; }
        fread(dir, 4, n_embd, f); fclose(f);
        fprintf(stderr, "using dir file: %s\n", dir_path);
    } else {
        srand(42);
        for (int i = 0; i < n_embd; i++) dir[i] = ((float)rand()/RAND_MAX - 0.5f) * 2.f;
    }
    float dn = 0;
    for (int i = 0; i < n_embd; i++) dn += dir[i]*dir[i];
    dn = sqrtf(dn);
    for (int i = 0; i < n_embd; i++) dir[i] /= dn;

    // cvec buffer: [n_layer][n_embd], 层1..63 = dir*strength (或只 il_only 层)
    float* cvec = (float*)calloc(n_embd * n_layer, sizeof(float));
    int il_start = il_only > 0 ? il_only : 1;
    int il_end   = il_only > 0 ? il_only : n_layer - 1;
    for (int l = il_start; l <= il_end; l++)
        for (int i = 0; i < n_embd; i++)
            cvec[l * n_embd + i] = dir[i] * strength;
    fprintf(stderr, "inject layers %d..%d\n", il_start, il_end);

    struct llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 2048; cp.n_batch = 512; cp.n_threads = 16; cp.n_threads_batch = 16;

    // ctx1: 无注入
    struct llama_context* c1 = llama_new_context_with_model(m, cp);
    // ctx2: 注入
    struct llama_context* c2 = llama_new_context_with_model(m, cp);
    llama_set_adapter_cvec(c2, cvec, n_embd * n_layer, n_embd, il_start, il_end);
    fprintf(stderr, "cvec set: strength=%.5f layers %d..%d\n", strength, il_start, il_end);

    int need = llama_tokenize(vocab, prompt, strlen(prompt), NULL, 0, true, false);
    int cap = (need < 0 ? -need : need) + 16;
    llama_token* toks = (llama_token*)malloc(sizeof(llama_token) * cap);
    int n2 = llama_tokenize(vocab, prompt, strlen(prompt), toks, cap, true, false);
    int nt = n2 > 0 ? n2 : (need < 0 ? -need : need);

    llama_batch b0 = llama_batch_get_one(toks, nt);
    if (llama_decode(c1, b0) != 0) { fprintf(stderr, "c1 decode fail\n"); return 1; }
    if (llama_decode(c2, b0) != 0) { fprintf(stderr, "c2 decode fail\n"); return 1; }

    float* l1 = llama_get_logits(c1);
    float* l2 = llama_get_logits(c2);

    // 统计差异
    double diff_sum = 0, diff_max = 0; int diff_n = 0;
    for (int v = 0; v < n_vocab; v += 1) {
        double dd = fabs((double)l1[v] - (double)l2[v]);
        diff_sum += dd; diff_n++;
        if (dd > diff_max) diff_max = dd;
    }
    printf("logits diff: mean=%.6f max=%.6f (n=%d)\n", diff_sum / diff_n, diff_max, diff_n);

    print_top5("no-inject", c1, vocab, l1, n_vocab);
    print_top5("inject  ", c2, vocab, l2, n_vocab);

    llama_free(c1); llama_free(c2);
    llama_model_free(m);
    free(cvec); free(dir); free(toks);
    return 0;
}
