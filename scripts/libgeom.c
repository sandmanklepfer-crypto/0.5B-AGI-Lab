// libgeom.c — 几何算子库实现
#include "libgeom.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

double geom_entropy(const float* logits, int n) {
    double H = 0;
    float max_l = -1e30f;
    for (int i = 0; i < n; i++) if (logits[i] > max_l) max_l = logits[i];
    double sum = 0;
    for (int i = 0; i < n; i++) { double p = exp((double)logits[i] - max_l); sum += p; }
    for (int i = 0; i < n; i++) {
        double p = exp((double)logits[i] - max_l) / sum;
        if (p > 1e-12) H -= p * log2(p);
    }
    return H;
}

void geom_normalize(float* v, int n) {
    double dn = 0;
    for (int i = 0; i < n; i++) dn += v[i] * v[i];
    dn = sqrt(dn) + 1e-9;
    for (int i = 0; i < n; i++) v[i] /= (float)dn;
}

geom_t* geom_new(int n_embd, int n_vocab, int n_layer, int target_layer,
                 int k_step, float geo_max, float H_thresh, float push_str) {
    geom_t* g = (geom_t*)calloc(1, sizeof(geom_t));
    g->n_embd = n_embd; g->n_vocab = n_vocab; g->n_layer = n_layer;
    g->target_layer = target_layer; g->k_step = k_step > 0 ? k_step : 1;
    g->geo_max = geo_max; g->H_thresh = H_thresh; g->push_str = push_str;
    g->cvec = (float*)calloc(n_embd * n_layer, sizeof(float));
    g->ent_min = 1e30;
    return g;
}

void geom_free(geom_t* g) {
    if (!g) return;
    free(g->anchor); free(g->push_dir); free(g->cvec);
    free(g);
}

void geom_set_anchor(geom_t* g, const float* d) {
    if (!g->anchor) g->anchor = (float*)malloc(g->n_embd * sizeof(float));
    memcpy(g->anchor, d, g->n_embd * sizeof(float));
    geom_normalize(g->anchor, g->n_embd);
}

void geom_set_push(geom_t* g, const float* d) {
    if (!g->push_dir) g->push_dir = (float*)malloc(g->n_embd * sizeof(float));
    memcpy(g->push_dir, d, g->n_embd * sizeof(float));
    geom_normalize(g->push_dir, g->n_embd);
}

// ── 算子1: 反吸引子 (熵监测 + 推开) ──
float* geom_on_logits(geom_t* g, const float* logits) {
    double H = geom_entropy(logits, g->n_vocab);
    if (H < g->ent_min) g->ent_min = H;
    g->ent_sum += H; g->ent_n++;
    g->need_clear = 0;

    if (H < g->H_thresh) {
        g->low_run++;
        if (g->low_run >= 3 && g->cur_push == 0.f) {
            int il = g->n_layer - 1;                 // 最后一层注入
            for (int i = 0; i < g->n_embd; i++)
                g->cvec[il * g->n_embd + i] = g->push_dir[i] * g->push_str;
            g->cur_push = g->push_str;
            g->pushes++;
            return g->cvec;
        }
    } else {
        g->low_run = 0;
        if (g->cur_push != 0.f) {                    // 熵恢复 → 松开
            g->cur_push = 0.f;
            g->need_clear = 1;
        }
    }
    return NULL;
}

// ── 算子2+3: 测地线修正 + Karcher 锚定 (激活层) ──
float* geom_on_act(geom_t* g, const float* cur_act) {
    if (!g->anchor) return NULL;
    // 测地线方向 = anchor 在切空间的投影 (去掉沿当前激活的分量)
    double dot = 0, an = 0;
    for (int i = 0; i < g->n_embd; i++) { dot += g->anchor[i] * cur_act[i]; an += cur_act[i] * cur_act[i]; }
    float* d_tan = (float*)malloc(g->n_embd * sizeof(float));
    float tdn = 0;
    for (int i = 0; i < g->n_embd; i++) {
        d_tan[i] = g->anchor[i] - (float)(dot / (an + 1e-9)) * cur_act[i];
        tdn += d_tan[i] * d_tan[i];
    }
    tdn = sqrtf(tdn);
    const float* d_use;
    float tmp[2048];
    if (tdn > 0.01f && g->n_embd <= 2048) {
        for (int i = 0; i < g->n_embd; i++) { tmp[i] = d_tan[i] / tdn; d_use = tmp; }
    } else {
        d_use = g->anchor;                           // 退化: 直接用锚方向
    }
    // 强度逐步递增 (ramp, 避免陡峭注入崩流形)
    g->cur_geo = fminf(g->cur_geo + g->geo_max / 10.f, g->geo_max);
    // 全层注入 (层1..n_layer-1)
    for (int l = 1; l < g->n_layer; l++)
        for (int i = 0; i < g->n_embd; i++)
            g->cvec[l * g->n_embd + i] = d_use[i] * g->cur_geo;
    g->geos++;
    free(d_tan);
    return g->cvec;
}
