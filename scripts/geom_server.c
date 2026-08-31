// geom_server.c v2 — 常驻生成服务 (进化机核心, 简化版)
// 加载模型一次, 循环从 stdin 读命令, 生成后输出
// 命令 (tab分隔): prompt \t dir_path \t strength \t layer \t n_tok \t temp \t anchor_scale
//   dir_path: 方向文件或 "-"; strength: cvec 强度; layer: 注入层(0=全层)
//   n_tok: 生成数; temp: 采样温度(0=贪心); anchor_scale: 方向缩放
// 输出: ==OUT==\n<文本>\n==END==
#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static int g_n_embd = 0;
static int g_n_layer = 0;

static float* load_dir(const char* path, int n_embd) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    if (sz < n_embd * 4) { fclose(f); return NULL; }
    float* d = (float*)malloc(n_embd * sizeof(float));
    if (fread(d, 4, n_embd, f) != (size_t)n_embd) { fclose(f); free(d); return NULL; }
    fclose(f);
    double dn = 0; for (int i = 0; i < n_embd; i++) dn += (double)d[i] * d[i];
    dn = sqrt(dn) + 1e-12;
    for (int i = 0; i < n_embd; i++) d[i] /= (float)dn;
    return d;
}

static llama_token sample_token(const float* logits, int n_vocab, float temp) {
    if (temp <= 0.01f) {
        float best = -1e30f; llama_token id = 0;
        for (int v = 0; v < n_vocab; v++) if (logits[v] > best) { best = logits[v]; id = v; }
        return id;
    }
    double max_l = -1e30;
    for (int v = 0; v < n_vocab; v++) if (logits[v] > max_l) max_l = logits[v];
    double sum = 0;
    for (int v = 0; v < n_vocab; v++) sum += exp((logits[v] - max_l) / temp);
    double r = (double)rand() / RAND_MAX * sum;
    double acc = 0;
    for (int v = 0; v < n_vocab; v++) {
        acc += exp((logits[v] - max_l) / temp);
        if (acc >= r) return (llama_token)v;
    }
    return n_vocab - 1;
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s <model>\n", argv[0]); return 1; }
    struct llama_model_params mp = llama_model_default_params();
    mp.n_gpu_layers = 99;
    struct llama_model* m = llama_model_load_from_file(argv[1], mp);
    if (!m) { fprintf(stderr, "model fail\n"); return 1; }
    g_n_layer = llama_model_n_layer(m);
    g_n_embd = llama_model_n_embd(m);
    const struct llama_vocab* vocab = llama_model_get_vocab(m);
    int n_vocab = llama_vocab_n_tokens(vocab);
    struct llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 4096; cp.n_batch = 512; cp.n_threads = 16; cp.n_threads_batch = 16;
    struct llama_context* ctx = llama_new_context_with_model(m, cp);
    if (!ctx) { fprintf(stderr, "ctx fail\n"); return 1; }
    fprintf(stderr, "SERVER_READY layers=%d embd=%d vocab=%d\n", g_n_layer, g_n_embd, n_vocab);
    fflush(stderr);

    srand(12345);
    char line[16384];
    while (fgets(line, sizeof(line), stdin)) {
        size_t L = strlen(line);
        while (L && (line[L-1]=='\n' || line[L-1]=='\r')) line[--L] = 0;
        if (L == 0) continue;
        if (strcmp(line, "QUIT") == 0) break;
        char* fields[7];
        int nf = 0;
        fields[nf++] = line;
        for (char* c = line; *c && nf < 7; c++) {
            if (*c == '\t') { *c = 0; fields[nf++] = c + 1; }
        }
        if (nf < 7) { fprintf(stderr, "ERR fields %d\n", nf); continue; }
        const char* prompt = fields[0];
        const char* dir_path = fields[1];
        float strength = atof(fields[2]);
        int layer = atoi(fields[3]);
        int n_tok = atoi(fields[4]);
        float temp = atof(fields[5]);
        float anchor_scale = atof(fields[6]);

        // 构建 cvec (全层或指定层)
        float* cvec = NULL;
        float* dir = NULL;
        if (strcmp(dir_path, "-") != 0 && anchor_scale > 0 && strength > 0) {
            dir = load_dir(dir_path, g_n_embd);
            if (dir) {
                for (int i = 0; i < g_n_embd; i++) dir[i] *= anchor_scale;
                cvec = (float*)calloc(g_n_embd * g_n_layer, sizeof(float));
                if (layer > 0 && layer < g_n_layer) {
                    for (int i = 0; i < g_n_embd; i++) cvec[layer * g_n_embd + i] = dir[i] * strength;
                } else {
                    for (int l = 1; l < g_n_layer; l++)
                        for (int i = 0; i < g_n_embd; i++) cvec[l * g_n_embd + i] = dir[i] * strength;
                }
                llama_set_adapter_cvec(ctx, cvec, g_n_embd * g_n_layer, g_n_embd, 1, g_n_layer - 1);
            }
        }

        // tokenize + decode prompt
        int need = llama_tokenize(vocab, prompt, strlen(prompt), NULL, 0, true, false);
        int cap = (need < 0 ? -need : need) + 2048;
        llama_token* toks = (llama_token*)malloc(sizeof(llama_token) * cap);
        int n2 = llama_tokenize(vocab, prompt, strlen(prompt), toks, cap, true, false);
        int nt = n2 > 0 ? n2 : (need < 0 ? -need : need);
        llama_batch b0 = llama_batch_get_one(toks, nt);
        if (llama_decode(ctx, b0) != 0) { fprintf(stderr, "prompt fail\n"); free(toks); if (cvec) free(cvec); if (dir) free(dir); continue; }

        // 生成 (退火: 前1/3 temp*2 → 降到 temp)
        char out_buf[32768]; int out_len = 0;
        int done = 0;
        while (done < n_tok) {
            float* logits = llama_get_logits(ctx);
            float cur_temp = temp;
            if (n_tok > 10 && temp > 0.01f) {
                float frac = (float)done / n_tok;
                cur_temp = frac < 0.34f ? temp * 2.0f : temp + (temp * 2.0f - temp) * (1.0f - (frac - 0.34f) / 0.66f);
            }
            llama_token id = sample_token(logits, n_vocab, cur_temp);
            if (id < 0) break;
            toks[nt++] = id;
            char piece[64];
            int plen = llama_token_to_piece(vocab, id, piece, 64, 0, true);
            if (plen > 0 && out_len + plen < 32767) { memcpy(out_buf + out_len, piece, plen); out_len += plen; }
            out_buf[out_len] = 0;
            llama_batch b = llama_batch_get_one(&toks[nt - 1], 1);
            if (llama_decode(ctx, b) != 0) break;
            done++;
            if (id == llama_vocab_eos(vocab)) break;
        }
        printf("==OUT==\n%s\n==END==\n", out_buf);
        fflush(stdout);
        if (cvec) { llama_set_adapter_cvec(ctx, NULL, 0, g_n_embd, 0, 0); free(cvec); }
        if (dir) free(dir);
        free(toks);
    }
    llama_free(ctx);
    llama_model_free(m);
    return 0;
}
