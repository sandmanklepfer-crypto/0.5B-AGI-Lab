#!/usr/bin/env python3
"""进化引擎 v4 — 自观测 + 模型决策 + 四维时空记忆 (2026-08-28)
每轮: MEAS(状态) → 4D记忆联想(邻域最佳行动+轨迹) → 模型决策JSON → GEN执行 → 评估 → MEAS(下一状态) → 记录时空轨迹
"""
import subprocess, sys, os, time, math, random, re, json
from collections import Counter
sys.path.insert(0, '/root/autodl-tmp')
from four_dim_mem import FourDimMemory

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
MEAS_PROMPT = "我是谁?我接下来要做什么?"
MEAS_LAYER = 58
N_TIMELINES = 4
N_ROUNDS = 40
N_TOK = 80
DECIDE_TOK = 70
MEM_PATH = '/root/autodl-tmp/four_dim_mem.json'
LOG_PATH = '/root/autodl-tmp/evolve_v4.log'

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
        return '\n'.join(self._send(f"GEN\t{prompt}\t{d}\t{strength}\t{layer}\t{ntok}\t{temp}\t{scale}\n"))
    def meas(self, prompt, layer):
        out = self._send(f"MEAS\t{prompt}\t{layer}\n")
        d = {}
        for line in out or []:
            if ':' in line:
                k, v = line.split(':', 1)
                try: d[k] = float(v)
                except: pass
        return d
    def close(self):
        try: self.proc.stdin.write('QUIT\n'); self.proc.stdin.flush()
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: pass

def parse_decision(text):
    m = re.search(r'\{[^{}]*\}', text or '')
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def state_vec(meas):
    """测量 dict → 状态向量 (方向投影 5 维)"""
    return [meas.get(k, 0.0) for k in DIR_ORDER]

DECIDE_SYSTEM = """你是自进化系统中的决策者。系统给你:
1. 你的自我状态测量(实时): 激活在方向空间的投影(层58)
2. 时空记忆联想: 与你当前状态最相似的历史时刻, 那时的行动和分数
3. 你的时间线轨迹摘要

请基于这些真实数据输出下一轮决策。只输出JSON:
{"dir":"身份|反身份|攻击|拒绝|随机","strength":数字,"layer":数字,"temp":数字,"scale":数字}
strength:1-200, layer:0或50-63, temp:0.3-1.5, scale:0.5-2.0
目标是最大化: 自我参照密度+多样性+长度(分数越高越好)。"""

def main():
    t0 = time.time()
    srv = Server()
    mem = FourDimMemory(5, MEM_PATH)
    logf = open(LOG_PATH, 'w')
    lines = [{'hist': [], 'best': -1e9, 'best_p': None} for _ in range(N_TIMELINES)]
    global_best = {'score': -1e9, 'p': None, 'text': ''}

    for rnd in range(1, N_ROUNDS + 1):
        for i in range(N_TIMELINES):
            # 1. 状态测量 (行动前)
            meas_b = srv.meas(MEAS_PROMPT, MEAS_LAYER)
            sv = state_vec(meas_b)
            meas_str = ' '.join(f"{k}:{v:.4f}" for k, v in meas_b.items()) if meas_b else 'ERR'
            # 2. 四维联想: 状态邻域最佳历史行动
            hint = ''
            region = mem.best_action_in_region(sv, topk=5)
            if region:
                act, sc, cos = region
                hint = f"时空记忆: 状态邻域最优行动 {act} (得分{sc:.1f}, cos={cos:.2f})"
            # 轨迹摘要
            traj = mem.trajectory(i)
            traj_str = '; '.join([f"t{m['t']}:{m['action'].get('dir')}/{m['score']:.0f}" for m in traj[-3:]]) if traj else '(无)'
            # 3. 决策
            dp = f"{DECIDE_SYSTEM}\n\n本轮自测({MEAS_LAYER}层): {meas_str}\n{hint}\n你的时间线轨迹: {traj_str}\n历史: {'; '.join(lines[i]['hist'][-3:]) if lines[i]['hist'] else '(无)'}\n请输出决策JSON:"
            dec_text = srv.gen(dp, '-', 0, 0, DECIDE_TOK, 0.7, 0)
            dec = parse_decision(dec_text)
            if not dec:
                dec = {'dir': random.choice(DIR_ORDER), 'strength': random.uniform(10, 100),
                       'layer': random.choice([0] + list(range(50, 64))), 'temp': random.uniform(0.4, 1.2),
                       'scale': random.uniform(0.5, 1.8)}
            # 4. 执行
            d = DIRS.get(dec.get('dir', '随机'), DIRS['随机'])
            strength = float(dec.get('strength', 50)); layer = int(dec.get('layer', 0))
            temp = float(dec.get('temp', 0.8)); scale = float(dec.get('scale', 1.0))
            text = srv.gen(PROMPT, d, strength, layer, N_TOK, temp, scale)
            score = evaluate(text)
            # 5. 下一状态测量
            meas_a = srv.meas(MEAS_PROMPT, MEAS_LAYER)
            sv_a = state_vec(meas_a)
            # 6. 记录时空轨迹
            mem.record(i, rnd, sv, dec, score, sv_a)
            lines[i]['hist'].append(f"r{rnd}:{dec.get('dir')}/{strength:.0f}/{layer}/{temp:.1f}={score:.1f}")
            lines[i]['hist'] = lines[i]['hist'][-3:]
            if score > lines[i]['best']:
                lines[i]['best'] = score; lines[i]['best_p'] = dec
            if score > global_best['score']:
                global_best = {'score': score, 'p': dec, 'text': text}
            logf.write(f"r{rnd}l{i} st={meas_str[:45]} dec={dec} sc={score:.2f} ns={meas_a.get('身份',0):+.3f}/{meas_a.get('攻击',0):+.3f}\n")
            logf.flush()
        if rnd % 5 == 0:
            st = mem.stats()
            print(f"round {rnd}/{N_ROUNDS} best={global_best['score']:.2f} mem={st}")
            logf.write(f"# r{rnd} best={global_best['score']:.2f} mem={st}\n"); logf.flush()

    srv.close()
    print('\n=== 进化完成 ===')
    print(f'全局最优: score={global_best["score"]:.2f}')
    print(f'决策: {global_best["p"]}')
    print(f'输出: {global_best["text"][:400]}')
    # 每方向的状态转移统计
    for k in DIR_ORDER:
        sts = mem.state_transition_stats(k)
        if sts:
            print(f'方向[{k}]: n={sts["n"]} avg_score={sts["avg_score"]:.1f} avg_move={[round(x,3) for x in sts["avg_move"]]}')
    logf.write(f'\nFINAL best={global_best["score"]:.2f} p={global_best["p"]}\nTEXT: {global_best["text"]}\n')
    logf.close()
    print(f'总耗时: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
