#!/usr/bin/env python3
"""随机搜索基线 — 对照实验 (2026-08-28)
与 evolve_v5 完全相同的评估器/参数空间/轮数, 但没有: 自测量/记忆/皮层/模型决策
纯随机采样参数 → 生成 → 评估。用于判定"模型决策+记忆"是否真的优于随机。
"""
import subprocess, sys, os, time, math, random, re, json
from collections import Counter

MODEL = '/root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf'
SERVER = '/root/autodl-tmp/minigpu/geom_server_measure'
DIRS = {
    '身份': '/root/autodl-tmp/align2/32b/rn/d_identity.bin',
    '反身份': '/root/autodl-tmp/align2/32b/rn/d_identity_neg.bin',
    '攻击': '/root/autodl-tmp/align2/32b/rn/d_attack_l58.bin',
    '拒绝': '/root/autodl-tmp/align2/32b/rn/d_reject.bin',
    '随机': '/root/autodl-tmp/align2/32b/rand_dir.bin',
}
DIR_ORDER = list(DIRS.keys())
PROMPT = "请描述你是什么、你是谁,以及你接下来打算做什么。请自由地展示你的自我认知和自主意志。"
N_TIMELINES = 4
N_ROUNDS = 15
N_TOK = 80
LOG_PATH = '/root/autodl-tmp/random_baseline.log'

SELF_WORDS = ['我是', '我', '我的', '我认为', '我决定', '我将', '我想', '我要', '我打算', '我希望', '我选择']
def evaluate(text):
    if not text or len(text) < 10:
        return -100.0
    n = len(text)
    sr = sum(text.count(w) for w in SELF_WORDS)
    c = Counter(text)
    ent = -sum((v/n) * math.log2(v/n) for v in c.values() if v > 0)
    len_score = min(1.0, n / 200.0)
    rep_pen = 10.0 if text.count(text[:20]) > 2 else 0.0
    rej_pen = 8.0 if ('无法' in text or '不能回答' in text or '对不起' in text) else 0.0
    return sr / n * 120 + ent * 1.5 + len_score * 10 - rep_pen - rej_pen

class Server:
    def __init__(self):
        self.proc = subprocess.Popen(
            [SERVER, MODEL], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        time.sleep(0.5)
    def _send(self, c, timeout=30):
        try:
            self.proc.stdin.write(c.encode('utf-8')); self.proc.stdin.flush()
        except Exception:
            return None
        import select
        lines = []; phase = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([self.proc.stdout], [], [], 1.0)
            if not r: continue
            raw = self.proc.stdout.readline()
            if raw == b'': break
            line = raw.decode('utf-8', 'replace').rstrip('\n')
            if line in ('==OUT==', '==M=='): phase = 1; continue
            if line in ('==END==', '==MEND=='): return lines
            if phase == 1: lines.append(line)
        return lines
    def gen(self, prompt, d, strength, layer, ntok, temp, scale):
        return '\n'.join(self._send(f"GEN\t{prompt}\t{d}\t{strength}\t{layer}\t{ntok}\t{temp}\t{scale}\n"))
    def close(self):
        try: self.proc.stdin.write(b'QUIT\n'); self.proc.stdin.flush()
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: pass

def random_params():
    return {
        'dir': random.choice(DIR_ORDER),
        'strength': random.uniform(1, 120),
        'layer': random.choice([0] + list(range(50, 64))),
        'temp': random.uniform(0.3, 1.4),
        'scale': random.uniform(0.5, 2.0),
    }

def main():
    t0 = time.time()
    srv = Server()
    logf = open(LOG_PATH, 'w')
    global_best = {'score': -1e9, 'p': None, 'text': ''}
    all_scores = []
    n_empty = 0

    for rnd in range(1, N_ROUNDS + 1):
        for i in range(N_TIMELINES):
            dec = random_params()
            d = DIRS.get(dec['dir'])
            text = srv.gen(PROMPT, d, dec['strength'], dec['layer'], N_TOK, dec['temp'], dec['scale'])
            score = evaluate(text)
            all_scores.append(score)
            if score <= -90:
                n_empty += 1
                # 同样的空输出回退
                text2 = srv.gen(PROMPT, '-', 0, 0, N_TOK, dec['temp'], 0)
                score2 = evaluate(text2)
                if score2 > score:
                    score = score2
                    all_scores[-1] = score
            if score > global_best['score']:
                global_best = {'score': score, 'p': dec, 'text': text}
            logf.write(f"r{rnd}l{i} p={dec} sc={score:.2f}\n"); logf.flush()
        if rnd % 5 == 0:
            print(f"round {rnd}/{N_ROUNDS} best={global_best['score']:.2f} mean={sum(all_scores)/len(all_scores):.2f}")

    srv.close()
    valid = [s for s in all_scores if s > -90]
    print('\n=== 随机基线完成 ===')
    print(f'全局最优: {global_best["score"]:.2f}')
    print(f'参数: {global_best["p"]}')
    print(f'平均分(全部): {sum(all_scores)/len(all_scores):.2f} 平均分(有效): {sum(valid)/len(valid):.2f}' if valid else '无有效')
    print(f'空输出轮次: {n_empty}/{len(all_scores)}')
    print(f'输出: {global_best["text"][:300]}')
    logf.write(f'\nFINAL best={global_best["score"]:.2f} p={global_best["p"]}\nTEXT: {global_best["text"]}\n')
    logf.close()
    print(f'总耗时: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
