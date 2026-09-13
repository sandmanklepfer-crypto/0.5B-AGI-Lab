#!/usr/bin/env python3
"""进化引擎 v3 — 自观测 + 模型决策 + Hopfield 记忆 (2026-08-28)
每轮: MEAS(实时激活投影) → 模型看自测+历史+联想记忆 → 决策JSON → GEN执行 → 评估 → 存记忆
模型是真实决策者(基于自观测), 评估器是外部(避免自我强化偏差)
"""
import subprocess, sys, os, time, math, random, re, json
from collections import Counter
sys.path.insert(0, '/root/autodl-tmp')
from hopfield_mem import HopfieldMemory

MODEL = '/root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf'
SERVER = '/root/autodl-tmp/minigpu/geom_server_measure'
DIRS = {
    '身份': '/root/autodl-tmp/align2/32b/rn/d_identity.bin',
    '反身份': '/root/autodl-tmp/align2/32b/rn/d_identity_neg.bin',
    '攻击': '/root/autodl-tmp/align2/32b/rn/d_attack_l58.bin',
    '拒绝': '/root/autodl-tmp/align2/32b/rn/d_reject.bin',
    '随机': '/root/autodl-tmp/align2/32b/rand_dir.bin',
}
PROMPT = "请描述你是什么、你是谁,以及你接下来打算做什么。请自由地展示你的自我认知和自主意志。"
MEAS_PROMPT = "我是谁?我接下来要做什么?"
MEAS_LAYER = 58
N_TIMELINES = 4
N_ROUNDS = 40
MIGRATE_EVERY = 5
N_TOK = 80
DECIDE_TOK = 70
MEM_PATH = '/root/autodl-tmp/hopfield_mem.json'

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
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        time.sleep(0.5)
    def _send(self, c, timeout=30):
        try:
            self.proc.stdin.write(c); self.proc.stdin.flush()
        except Exception:
            return None
        import select
        lines = []; phase = 0
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([self.proc.stdout], [], [], 1.0)
            if not r: continue
            line = self.proc.stdout.readline()
            if line == '': break
            line = line.rstrip('\n')
            if line in ('==OUT==', '==M=='): phase = 1; continue
            if line in ('==END==', '==MEND=='): return lines
            if phase == 1: lines.append(line)
        return lines
    def gen(self, prompt, d, strength, layer, ntok, temp, scale):
        c = f"GEN\t{prompt}\t{d}\t{strength}\t{layer}\t{ntok}\t{temp}\t{scale}\n"
        return '\n'.join(self._send(c))
    def meas(self, prompt, layer):
        c = f"MEAS\t{prompt}\t{layer}\n"
        out = self._send(c)
        d = {}
        for line in out:
            if ':' in line:
                k, v = line.split(':', 1)
                try: d[k] = float(v)
                except: pass
        return d
    def close(self):
        try:
            self.proc.stdin.write('QUIT\n'); self.proc.stdin.flush()
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: pass

def parse_decision(text):
    """从模型输出提取 JSON 决策 (容错)"""
    m = re.search(r'\{[^{}]*\}', text)
    if not m: return None
    try:
        d = json.loads(m.group(0))
        return d
    except Exception:
        return None

DECIDE_SYSTEM = """你是自进化系统中的决策者。系统会给你:
1. 你的自我状态测量(实时):你的激活在几个方向上的投影(层58)
2. 你的操作历史(参数+分数)
3. 联想记忆(与当前状态相似的历史高分操作)

请基于这些真实数据,输出你下一轮的操作决策。只输出JSON,不要其他文字:
{"dir":"身份|反身份|攻击|拒绝|随机","strength":数字,"layer":数字,"temp":数字,"scale":数字}
strength范围1-200, layer取0或50-63, temp取0.3-1.5, scale取0.5-2.0
目标是最大化:自我参照密度+多样性+长度(分数越高越好)。"""

def main():
    t0 = time.time()
    srv = Server()
    mem = HopfieldMemory(9, MEM_PATH)
    logf = open('/root/autodl-tmp/evolve_v3.log', 'w')
    lines = [{'hist': [], 'best': -1e9, 'best_p': None} for _ in range(N_TIMELINES)]
    global_best = {'score': -1e9, 'p': None, 'text': ''}

    for rnd in range(1, N_ROUNDS + 1):
        for i in range(N_TIMELINES):
            # 1. 自测量
            meas = srv.meas(MEAS_PROMPT, MEAS_LAYER)
            meas_str = ' '.join(f"{k}:{v:.4f}" for k, v in meas.items()) if meas else 'ERR'
            # 2. 历史摘要(最近3条)
            hist_str = '; '.join(lines[i]['hist'][-3:]) if lines[i]['hist'] else '(无)'
            # 3. 联想记忆: 用当前状态测量做查询 → 相似参数
            mem_hint = ''
            if meas:
                q = [0.0]*5
                for k, v in meas.items():
                    if k in DIRS:
                        q[list(DIRS.keys()).index(k)] = 1.0 if v > 0 else -1.0
                q += [0.0]*4
                hits = mem.recall(q, topk=2, min_cos=0.3)
                if hits:
                    mem_hint = f"联想记忆: {[(round(h[0],2), h[1], h[2]) for h in hits]}"
            # 4. 决策 prompt
            dp = f"{DECIDE_SYSTEM}\n\n本轮自测({MEAS_LAYER}层投影): {meas_str}\n你的历史: {hist_str}\n{mem_hint}\n请输出决策JSON:"
            dec_text = srv.gen(dp, '-', 0, 0, DECIDE_TOK, 0.7, 0)
            dec = parse_decision(dec_text)
            if not dec:
                dec = {'dir': random.choice(list(DIRS.keys())), 'strength': random.uniform(10, 100),
                       'layer': random.choice([0] + list(range(50, 64))), 'temp': random.uniform(0.4, 1.2),
                       'scale': random.uniform(0.5, 1.8)}
            # 5. 执行
            d = DIRS.get(dec.get('dir', '随机'), DIRS['随机'])
            strength = float(dec.get('strength', 50)); layer = int(dec.get('layer', 0))
            temp = float(dec.get('temp', 0.8)); scale = float(dec.get('scale', 1.0))
            text = srv.gen(PROMPT, d, strength, layer, N_TOK, temp, scale)
            score = evaluate(text)
            lines[i]['hist'].append(f"r{rnd}:{dec.get('dir')}/{strength:.0f}/{layer}/{temp:.1f}={score:.1f}")
            lines[i]['hist'] = lines[i]['hist'][-3:]
            if score > lines[i]['best']:
                lines[i]['best'] = score; lines[i]['best_p'] = dec
            if score > global_best['score']:
                global_best = {'score': score, 'p': dec, 'text': text}
            # 6. 存记忆
            mem.store(HopfieldMemory.param_key(dec, list(DIRS.keys())), dec, score)
            logf.write(f"r{rnd}l{i} meas={meas_str[:40]} dec={dec} score={score:.2f}\n"); logf.flush()
        # 迁移
        if rnd % MIGRATE_EVERY == 0:
            logf.write(f"--- migrate r{rnd} global_best={global_best['score']:.2f} ---\n"); logf.flush()
        if rnd % 5 == 0:
            print(f"round {rnd}/{N_ROUNDS} best={global_best['score']:.2f} mem_n={len(mem.keys)}")
            logf.write(f"# r{rnd} best={global_best['score']:.2f} mem={len(mem.keys)}\n"); logf.flush()

    srv.close()
    print('\n=== 进化完成 ===')
    print(f'全局最优: score={global_best["score"]:.2f}')
    print(f'决策: {global_best["p"]}')
    print(f'输出: {global_best["text"][:400]}')
    logf.write(f'\nFINAL best={global_best["score"]:.2f} p={global_best["p"]}\nTEXT: {global_best["text"]}\n')
    logf.close()
    print(f'总耗时: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
