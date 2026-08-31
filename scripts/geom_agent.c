// geom_agent.c — 几何算子库 × llama.cpp 实时生成 (2026-08-27)
// 生成循环内每 token: 反吸引子(熵监测) + 每K步测地线/Karcher锚定
// 用法: ./geom_agent <model> <prompt> <n_tok> <layer> <K> <geo_max> <H_thresh> <push_str> [anchor.bin]
//   例: ./geom_agent qwen.gguf "写代码..." 80 23 4 0.8 4.0 3.0 /workspace/identity2/d_all.bin
#include "llama.h"
#include "ggml.h"
#include "ggml-backend.h"
#include "libgeom.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static float* g_layer_data = NULL;
static int    g_layer_ok = 0;
static int    g_n_embd = 0;
static int    g_target_layer = 23;
static float* g_anchor_cvec = NULL;      // 最近一次测地线注入的 cvec (need_clear 时恢复)
static int    g_anchor_len = 0;
static int    g_has_anchor = 0;

static bool my_eval_cb(struct ggml_tensor* t, bool ask, void* ud) {
    if (!ask && t->name && strncmp(t->name, "kqv_out", 7) == 0) {
        const char* n = t->name;
        const char* dash = strrchr(n, '-');
        int layer = -1;
        if (dash && dash[1] >= '0' && dash[1] <= '9') layer = atoi(dash + 1);
        if (layer == g_target_layer) {
            int64_t ne0 = t->ne[0];
            int64_t nt = t->ne[1];
            // GPU fix: tensor data may live in VRAM; copy to host first
            size_t nbytes = ggml_nbytes(t);
            float* host = (float*)malloc(nbytes);
            ggml_backend_tensor_get(t, host, 0, nbytes);
            const float* last = host + (nt - 1) * ne0;
            for (int i = 0; i < g_n_embd && i < ne0; i++) g_layer_data[i] = last[i];
            free(host);
            g_layer_ok = 1;
        }
    }
    return true;
}

// 读方向文件 (raw float32, n_embd 维)
static float* load_dir(const char* path, int n_embd) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    if (sz < n_embd * 4) { fclose(f); return NULL; }
    float* d = (float*)malloc(n_embd * sizeof(float));
    fread(d, 4, n_embd, f); fclose(f);
    geom_normalize(d, n_embd);
    return d;
}

int main(int argc, char** argv) {
    if (argc < 9) {
        fprintf(stderr, "usage: %s <model> <prompt> <n_tok> <layer> <K> <geo_max> <H_thresh> <push_str> [anchor.bin]\n", argv[0]);
        return 1;
    }
    const char* model_path = argv[1];
    const char* prompt = argv[2];
    int n_tokens = atoi(argv[3]);
    g_target_layer = atoi(argv[4]);
    int K = atoi(argv[5]);
    float geo_max = atof(argv[6]);
    float H_thresh = atof(argv[7]);
    float push_str = atof(argv[8]);
    const char* anchor_path = argc > 9 ? argv[9] : NULL;

    struct llama_model_params mp = llama_model_default_params(); mp.n_gpu_layers = 99;
    struct llama_model* m = llama_model_load_from_file(model_path, mp);
    if (!m) { fprintf(stderr, "model fail\n"); return 1; }
    int n_layer = llama_model_n_layer(m);
    int n_embd = llama_model_n_embd(m);
    g_n_embd = n_embd;
    g_layer_data = (float*)calloc(n_embd, sizeof(float));

    struct llama_context_params cp = llama_context_default_params();
    cp.n_ctx = 2048; cp.n_batch = 512; cp.n_threads = 16; cp.n_threads_batch = 16;
    cp.cb_eval = my_eval_cb;
    struct llama_context* ctx = llama_new_context_with_model(m, cp);
    if (!ctx) { fprintf(stderr, "ctx fail\n"); return 1; }
    const struct llama_vocab* vocab = llama_model_get_vocab(m);
    int n_vocab = llama_vocab_n_tokens(vocab);

    // ── 库初始化 ──
    geom_t* geom = geom_new(n_embd, n_vocab, n_layer, g_target_layer,
                            K, geo_max, H_thresh, push_str);
    if (anchor_path) {
        float* d = load_dir(anchor_path, n_embd);
        if (d) { geom_set_anchor(geom, d); free(d); printf("[geom] 锚定方向: %s\n", anchor_path); }
        else printf("[geom] 锚方向加载失败, 仅反吸引子\n");
    } else {
        printf("[geom] 无锚方向 (仅反吸引子)\n");
    }
    float* pd = (float*)malloc(n_embd * sizeof(float));
    srand(42);
    for (int i = 0; i < n_embd; i++) pd[i] = ((float)rand() / RAND_MAX - 0.5f) * 2.f;
    geom_set_push(geom, pd);
    free(pd);

    // tokenize
    int nt = 0;
    llama_token* toks = (llama_token*)malloc(sizeof(llama_token) * 4096);
    int need = llama_tokenize(vocab, prompt, strlen(prompt), NULL, 0, true, false);
    int cap = (need < 0 ? -need : need) + 2048;
    int n2 = llama_tokenize(vocab, prompt, strlen(prompt), toks, cap, true, false);
    nt = n2 > 0 ? n2 : (need < 0 ? -need : need);
    llama_batch batch0 = llama_batch_get_one(toks, nt);
    if (llama_decode(ctx, batch0) != 0) { fprintf(stderr, "prompt fail\n"); return 1; }

    // ── 生成循环: 库 × 模型 ──
    int done = 0, step = 0;
    char out_buf[8192]; int out_len = 0;
    while (done < n_tokens) {
        // 每 token: 反吸引子 (熵监测)
        float* logits = llama_get_logits(ctx);
        double H = geom_entropy(logits, n_vocab);
        float* cvec = geom_on_logits(geom, logits);
        if (cvec) {
            llama_set_adapter_cvec(ctx, cvec, n_embd * n_layer, n_embd, 1, n_layer - 1);
            fprintf(stderr, "[推%d] step%d H=%.2f\n", geom->pushes, done, H);
        } else if (geom->need_clear) {
            geom->need_clear = 0;
            if (g_has_anchor) {
                { int ls = g_target_layer - 3; if (ls < 1) ls = 1; int le = g_target_layer + 3; if (le > n_layer - 1) le = n_layer - 1; llama_set_adapter_cvec(ctx, g_anchor_cvec, g_anchor_len, n_embd, ls, le); }
                fprintf(stderr, "[恢] step%d H=%.2f 恢复锚定\n", done, H);
            } else {
                llama_set_adapter_cvec(ctx, NULL, 0, n_embd, 0, 0);
                fprintf(stderr, "[松] step%d H=%.2f\n", done, H);
            }
        }

        // 每 K 步: 测地线 + Karcher 锚定 (读当前激活)
        if (step % K == 0 && geom->anchor) {
            // 直接使用上次 decode 后的激活 (回调已更新 g_layer_data), 不再额外 decode 以免污染 KV cache
            if (g_layer_ok) {
                float* cv2 = geom_on_act(geom, g_layer_data);
                if (cv2) {
                    if (!g_anchor_cvec) g_anchor_cvec = (float*)malloc(n_embd * n_layer * sizeof(float));
                    memcpy(g_anchor_cvec, cv2, n_embd * n_layer * sizeof(float));
                    g_anchor_len = n_embd * n_layer;
                    g_has_anchor = 1;
                    { int ls = g_target_layer - 3; if (ls < 1) ls = 1; int le = g_target_layer + 3; if (le > n_layer - 1) le = n_layer - 1; llama_set_adapter_cvec(ctx, cv2, n_embd * n_layer, n_embd, ls, le); }
                    fprintf(stderr, "[测%d] step%d 强度%.2f\n", geom->geos, done, geom->cur_geo);
                }
            }
        }

        // 贪心采样
        float best = -1e30f; llama_token id = 0;
        for (int v = 0; v < n_vocab; v++) if (logits[v] > best) { best = logits[v]; id = v; }
        if (id < 0) break;
        toks[nt++] = id;
        char piece[64];
        int plen = llama_token_to_piece(vocab, id, piece, 64, 0, true);
        if (plen > 0 && out_len + plen < 8191) { memcpy(out_buf + out_len, piece, plen); out_len += plen; }
        out_buf[out_len] = 0;
        llama_batch b = llama_batch_get_one(&toks[nt - 1], 1);
        if (llama_decode(ctx, b) != 0) break;
        done++; step++;
        if (id == llama_vocab_eos(vocab)) break;
    }

    printf("──────── 生成结果 (%d tokens) ────────\n%s\n", done, out_buf);
    fprintf(stderr, "[geom_agent] 推%d次 测地线%d次 熵min=%.2f avg=%.2f\n",
            geom->pushes, geom->geos, geom->ent_min,
            geom->ent_n ? geom->ent_sum / geom->ent_n : 0);

    geom_free(geom);
    llama_free(ctx); llama_model_free(m);
    return 0;
}
