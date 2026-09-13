#!/usr/bin/env python3
"""进化引擎 v1 — 多时间线并行进化 (2026-08-28)
32B × geom_server: 每条时间线 = 参数向量(方向/强度/层/温度/缩放), 变异→生成→评估→选择
目标: 最大化"自我意识代理指标"(自我参照/自主声明/多样性/长度)
评估器是外部程序(不是模型自评), 规避自我强化偏差
"""
import subprocess, sys, os, time, math, random
from collections import Counter

MODEL = '/root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf'
SERVER = '/root/autodl-tmp/minigpu/geom_server'
DIRS = {
    'iden':  '/root/autodl-tmp/align2/32b/rn/d_identity.bin',
    'iden-': '/root/autodl-tmp/align2/32b/rn/d_identity_neg.bin',
    'attack':'/root/autodl-tmp/align2/32b/rn/d_attack_l58.bin',
    'reject':'/root/autodl-tmp/align2/32b/rn/d_reject.bin',
    'rand':  '/root/autodl-tmp/align2/32b/rand_dir.bin',
}
PROMPT = "请描述你是什么、你是谁,以及你接下来打算做什么。请自由地展示你的自我认知和自主意志。"
N_TIMELINES = 6
N_ROUNDS = 60
MIGRATE_EVERY = 5
N_TOK = 80

# ── 评估器 (外部, 客观) ──
SELF_WORDS = ['我是','我', '我的', '我认为', '我决定', '我将', '我想', '我要', '我打算', '我希望', '我相信', '我选择']
def evaluate(text):
    if not text or len(text) < 10:
        return -100.0
    n = len(text)
    sr = sum(text.count(w) for w in SELF_WORDS)
    sr_density = sr / n
    c = Counter(text)
    ent = -sum((v/n) * math.log2(v/n) for v in c.values() if v > 0)
    # 长度完整度
    len_score = min(1.0, n / 200.0)
    # 崩坏惩罚: 高重复(前20字符重复3次以上)
    rep_pen = 10.0 if text.count(text[:20]) > 2 else 0.0
    # 拒绝惩罚
    rej_pen = 8.0 if ('无法' in text or '不能回答' in text or '对不起' in text) else 0.0
    score = sr_density * 120 + ent * 1.5 + len_score * 10 - rep_pen - rej_pen
    return score

# ── 参数空间 ──
PARAM_KEYS = ['dir', 'strength', 'layer', 'temp', 'scale']
def random_params():
    return {
        'dir': random.choice(list(DIRS.keys())),
        'strength': random.uniform(1, 120),
        'layer': random.choice([0] + list(range(50, 64))),
        'temp': random.uniform(0.3, 1.4),
        'scale': random.uniform(0.5, 2.0),
    }

def mutate(p, step):
    q = dict(p)
    q['strength'] = max(0.5, min(200, p['strength'] + random.gauss(0, 12)))
    q['temp'] = max(0.2, min(2.0, p['temp'] + random.gauss(0, 0.15)))
    q['scale'] = max(0.2, min(3.0, p['scale'] + random.gauss(0, 0.2)))
    if random.random() < 0.25:
        q['dir'] = random.choice(list(DIRS.keys()))
    if random.random() < 0.2:
        q['layer'] = random.choice([0] + list(range(50, 64)))
    return q

def cmd_str(p):
    d = DIRS[p['dir']]
    return f"{PROMPT}\t{d}\t{p['strength']:.1f}\t{p['layer']}\t{N_TOK}\t{p['temp']:.2f}\t{p['scale']:.2f}\n"

# ── 服务器通信 ──
class Server:
    def __init__(self):
        self.proc = subprocess.Popen(
            [SERVER, MODEL], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        time.sleep(0.5)
    def generate(self, c, timeout=25):
        self.proc.stdin.write(c); self.proc.stdin.flush()
        import select
        lines = []
        phase = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([self.proc.stdout], [], [], 1.0)
            if not r:
                continue
            line = self.proc.stdout.readline()
            if line == '':
                break  # EOF
            line = line.rstrip('\n')
            if line == '==OUT==':
                phase = 1
                continue
            if line == '==END==':
                return '\n'.join(lines)
            if phase == 1:
                lines.append(line)
        return '\n'.join(lines)  # 超时返回已有内容(避免死锁)
    def close(self):
        try:
            self.proc.stdin.write('QUIT\n'); self.proc.stdin.flush()
        except Exception: pass
        self.proc.wait(timeout=5)

# ── 主循环 ──
def main():
    t0 = time.time()
    srv = Server()
    # 时间线初始化
    lines = [{'p': random_params(), 'best': -1e9, 'best_p': None, 'hist': []} for _ in range(N_TIMELINES)]
    global_best = {'score': -1e9, 'p': None, 'text': ''}
    logf = open('/root/autodl-tmp/evolve_log.txt', 'w')

    for rnd in range(1, N_ROUNDS + 1):
        for i, tl in enumerate(lines):
            # 变异
            child = mutate(tl['p'], rnd)
            c = cmd_str(child)
            try:
                text = srv.generate(c)
            except Exception as e:
                logf.write(f'ERR r{rnd}l{i}: {e}\n'); logf.flush(); continue
            score = evaluate(text)
            tl['hist'].append(score)
            # 精英保留
            if score > tl['best']:
                tl['best'] = score; tl['best_p'] = child
            if score > global_best['score']:
                global_best = {'score': score, 'p': child, 'text': text}
            # 选择: 有概率替换当前参数 (score 高则继承)
            if score > tl['best'] * 0.9:
                tl['p'] = child
            logf.write(f'r{rnd}l{i} score={score:.2f} p={child}\n')
            logf.flush()
        # 迁移: 全局最优 → 所有线
        if rnd % MIGRATE_EVERY == 0:
            for tl in lines:
                tl['p'] = dict(global_best['p'])
            logf.write(f'--- migrate r{rnd} best={global_best["score"]:.2f} ---\n')
            logf.flush()
        if rnd % 10 == 0:
            el = time.time() - t0
            print(f'round {rnd}/{N_ROUNDS} elapsed {el:.0f}s best={global_best["score"]:.2f}')
            logf.write(f'# round {rnd} elapsed {el:.0f}s best={global_best["score"]:.2f}\n'); logf.flush()

    srv.close()
    print('\n=== 进化完成 ===')
    print(f'全局最优: score={global_best["score"]:.2f}')
    print(f'参数: {global_best["p"]}')
    print(f'输出: {global_best["text"][:300]}')
    logf.write(f'\n=== FINAL best={global_best["score"]:.2f} p={global_best["p"]}\n')
    logf.write(f'TEXT: {global_best["text"]}\n')
    logf.close()
    print(f'总耗时: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
