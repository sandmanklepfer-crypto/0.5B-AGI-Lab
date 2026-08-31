// dump_layers.c — GPU 版层激活导出器 (2026-08-28, 回调显存拷回版)
// 用法: ./dump_layers <model> <text_file> <out_prefix> [n_gpu=99]
//   text_file 每行一条文本; 输出 {out_prefix}_L{NN}.bin:
//   [int32 n_layers][int32 n_embd] + n_layers*n_embd float32 (每层最后token激活)
#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static float** g_layer_data = NULL;   // [n_layer][n_embd]
static int*   g_layer_ok = NULL;
static int    g_n_embd = 0;
static int    g_n_layer = 0;

static bool my_eval_cb(struct ggml_tensor* t, bool ask, void* ud) {
    if (!ask && t->name) {
        // result_norm: final norm 输出 (与 cvec 注入点 output_norm 后精确对齐)
        if (strcmp(t->name, "result_norm") == 0) {
            int64_t ne0 = t->ne[0];
            int64_t nt = t->ne[1];
            size_t nbytes = ggml_nbytes(t);
            float* host = (float*)malloc(nbytes);
            ggml_backend_tensor_get(t, host, 0, nbytes);
            const float* last = host + (nt - 1) * ne0;
            int m = g_n_embd < ne0 ? g_n_embd : (int)ne0;
            memcpy(g_layer_data[g_n_layer - 1], last, m * sizeof(float));
            free(host);
            g_layer_ok[g_n_layer - 1] = 1;
        } else if (strncmp(t->name, "kqv_out", 7) == 0) {
            const char* dash = strrchr(t->name, '-');
            int layer = -1;
            if (dash && dash[1] >= '0' && dash[1] <= '9') layer = atoi(dash + 1);
            if (layer >= 0 && layer < g_n_layer) {
                int64_t ne0 = t->ne[0];
                int64_t nt = t->ne[1];
                size_t nbytes = ggml_nbytes(t);
                float* host = (float*)malloc(nbytes);
                ggml_backend_tensor_get(t, host, 0, nbytes);
                const float* last = host + (nt - 1) * ne0;
                int m = g_n_embd < ne0 ? g_n_embd : (int)ne0;
                memcpy(g_layer_data[layer], last, m * sizeof(float));
                free(host);
                g_layer_ok[layer] = 1;
            }
        }
    }
    return true;
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: %s <model> <text_file> <out_prefix> [n_gpu]\n", argv[0]); return 1; }
    const char* model_path = argv[1];
    const char* text_path = argv[2];
    const char* out_prefix = argv[3];
    int n_gpu = argc > 4 ? atoi(argv[4]) : 99;

    struct llama_model_params mp = llama_model_default_params(); mp.n_gpu_layers = n_gpu;
    struct llama_model* m = llama_model_load_from_file(model_path, mp);
    if (!m) { fprintf(stderr, "model fail\n"); return 1; }
    g_n_layer = llama_model_n_layer(m);
    g_n_embd = llama_model_n_embd(m);
    const struct llama_vocab* vocab = llama_model_get_vocab(m);
    fprintf(stderr, "model: %d layers x %d embd\n", g_n_layer, g_n_embd);

    g_layer_data = (float**)calloc(g_n_layer, sizeof(float*));
    g_layer_ok = (int*)calloc(g_n_layer, sizeof(int));
    for (int i = 0; i < g_n_layer; i++) g_layer_data[i] = (float*)calloc(g_n_embd, sizeof(float));

    struct llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 2048; cp.n_batch = 512; cp.n_threads = 16; cp.n_threads_batch = 16;
    cp.cb_eval = my_eval_cb;
    struct llama_context* ctx = llama_new_context_with_model(m, cp);
    if (!ctx) { fprintf(stderr, "ctx fail\n"); return 1; }

    FILE* tf = fopen(text_path, "r");
    if (!tf) { fprintf(stderr, "text file fail\n"); return 1; }
    char line[8192]; int idx = 0;
    while (fgets(line, sizeof(line), tf)) {
        size_t L = strlen(line);
        while (L && (line[L-1]=='\n' || line[L-1]=='\r')) line[--L] = 0;
        if (L == 0) continue;
        for (int i = 0; i < g_n_layer; i++) g_layer_ok[i] = 0;

        int need = llama_tokenize(vocab, line, strlen(line), NULL, 0, true, false);
        int cap = (need < 0 ? -need : need) + 16;
        llama_token* toks = (llama_token*)malloc(sizeof(llama_token) * cap);
        int n2 = llama_tokenize(vocab, line, strlen(line), toks, cap, true, false);
        int nt = n2 > 0 ? n2 : (need < 0 ? -need : need);
        llama_batch b0 = llama_batch_get_one(toks, nt);
        if (llama_decode(ctx, b0) != 0) { fprintf(stderr, "decode fail: %s\n", line); free(toks); continue; }
        free(toks);

        char fn[1024]; snprintf(fn, sizeof(fn), "%s_L%02d.bin", out_prefix, idx + 1);
        FILE* fo = fopen(fn, "wb");
        if (!fo) { fprintf(stderr, "out fail %s\n", fn); break; }
        int nl = g_n_layer, ne = g_n_embd;
        fwrite(&nl, 4, 1, fo); fwrite(&ne, 4, 1, fo);
        for (int i = 0; i < g_n_layer; i++) fwrite(g_layer_data[i], 4, g_n_embd, fo);
        fclose(fo);
        int missing = 0; for (int i = 0; i < g_n_layer; i++) if (!g_layer_ok[i]) missing++;
        printf("L%02d: %d toks, missing %d layers -> %s\n", idx + 1, nt, missing, fn);
        fflush(stdout);
        idx++;
    }
    fclose(tf);
    llama_free(ctx); llama_model_free(m);
    printf("done %d texts\n", idx);
    return 0;
}
