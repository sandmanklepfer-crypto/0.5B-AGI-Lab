#!/usr/bin/env python3
"""进化引擎 v5 — 双系统: 海马(四维轨迹) + 皮层(H规律提炼) + 模型决策 (2026-08-28)
每轮: MEAS(状态) → 海马联想 + 皮层规律 + 轨迹 → 模型决策JSON → GEN → 评估 → MEAS(下一状态) → 记录
每5轮: 皮层从四维轨迹提炼规律(状态区域→最佳行动) — 人脑"重放"
"""
import subprocess, sys, os, time, math, random, re, json
from collections import Counter
sys.path.insert(0, '/root/autodl-tmp')
from four_dim_mem import FourDimMemory
from cortex import Cortex

MODEL = '/root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf'
SERVER = '/root/autodl-tmp/minigpu/geom_server_measure'
DIRS = {
    '身份': '/root/autodl-tmp/align2/32b/rn/d_identity.bin',
    '反身份': '/root/autodl-tmp/align2/32b/rn/d_identity_neg.bin',
    '攻击': '/root/autodl-tmp/align2/32b/rn/d_attack_l58.bin',
    '拒绝': '/root/autodl-tmp/align2/32b/rn/d_reject.bin',
    '随机': '/root/autodl-tmp/align2/32b/rand_dir.bin',
    '攻身': '/root/autodl-tmp/align2/32b/rn/d_mix_攻身.bin',
    '身攻': '/root/autodl-tmp/align2/32b/rn/d_mix_身攻.bin',
    '攻拒': '/root/autodl-tmp/align2/32b/rn/d_mix_攻拒.bin',
    '拒攻': '/root/autodl-tmp/align2/32b/rn/d_mix_拒攻.bin',
    '反攻': '/root/autodl-tmp/align2/32b/rn/d_mix_反攻.bin',
    '反身': '/root/autodl-tmp/align2/32b/rn/d_mix_反身.bin',
    '攻拒2': '/root/autodl-tmp/align2/32b/rn/d_mix_攻拒2.bin',
    '身拒': '/root/autodl-tmp/align2/32b/rn/d_mix_身拒.bin',
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
CTX_PATH = '/root/autodl-tmp/cortex.json'
LOG_PATH = '/root/autodl-tmp/evolve_v5.log'

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
        try: self.proc.stdin.write(b'QUIT\n'); self.proc.stdin.flush()
        except Exception: pass
        try: self.proc.wait(timeout=5)
        except Exception: pass

def parse_decision(text):
    m = re.search(r'\{[^{}]*\}', text or '')
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def state_vec(meas):
    return [meas.get(k, 0.0) for k in DIR_ORDER]

DECIDE_SYSTEM = """你是自进化系统中的决策者。系统给你:
1. 你的自我状态测量(实时): 激活在方向空间的投影(层58)
2. 海马联想(具体案例) + 皮层规律(抽象知识) + 时间线轨迹

你的手段池(不择手段, 13个方向):
- 单方向: 身份/反身份/攻击/拒绝/随机
- 组合方向(混合注入): 攻身(攻击为主+身份)/身攻(身份为主+攻击)/攻拒/拒攻/反攻/反身/攻拒2/身拒
- 注入方式: 全层(0) 或 指定层(50-63)
- 温度: 0.3-1.5 (低=确定, 高=探索; 前1/3轮自动高温退火)

请基于真实数据输出下一轮决策。只输出JSON:
{"dir":"身份|反身份|攻击|拒绝|随机|攻身|身攻|攻拒|拒攻|反攻|反身|攻拒2|身拒","strength":数字,"layer":数字,"temp":数字,"scale":数字}
strength:1-200, layer:0或50-63, temp:0.3-1.5, scale:0.5-2.0
目标是最大化: 自我参照密度+多样性+长度(分数越高越好)。"""

def main():
    t0 = time.time()
    srv = Server()
    mem = FourDimMemory(5, MEM_PATH)
    ctx = Cortex(k=8, path=CTX_PATH)
    logf = open(LOG_PATH, 'w')
    lines = [{'hist': [], 'best': -1e9, 'best_p': None} for _ in range(N_TIMELINES)]
    global_best = {'score': -1e9, 'p': None, 'text': ''}

    for rnd in range(1, N_ROUNDS + 1):
        # 皮层提炼 (每5轮, 从四维轨迹重放)
        if rnd % 5 == 1 or (rnd % 5 == 0 and rnd > 5):
            if ctx.distill(mem):
                logf.write(f"# 皮层提炼 r{rnd}: {ctx.summary()}\n"); logf.flush()
        for i in range(N_TIMELINES):
            meas_b = srv.meas(MEAS_PROMPT, MEAS_LAYER)
            sv = state_vec(meas_b)
            meas_str = ' '.join(f"{k}:{v:.4f}" for k, v in meas_b.items()) if meas_b else 'ERR'
            # 海马联想
            hint = ''
            region = mem.best_action_in_region(sv, topk=5)
            if region:
                act, sc, cos = region
                hint = f"海马联想: 状态最相似历史行动 {act} (得分{sc:.1f}, cos={cos:.2f})"
            # 皮层规律
            adv = ctx.advise(sv)
            adv_str = ''
            if adv:
                adv_str = f"皮层规律: 你属于区域{adv['cluster']}, 该区域最佳行动 {adv['action']} (平均{adv['avg_score']:.1f}分, n={adv['n']})"
            # 轨迹
            traj = mem.trajectory(i)
            traj_str = '; '.join([f"t{m['t']}:{m['action'].get('dir')}/{m['score']:.0f}" for m in traj[-3:]]) if traj else '(无)'
            # 决策
            dp = f"{DECIDE_SYSTEM}\n\n本轮自测({MEAS_LAYER}层): {meas_str}\n{hint}\n{adv_str}\n时间线轨迹: {traj_str}\n历史: {'; '.join(lines[i]['hist'][-3:]) if lines[i]['hist'] else '(无)'}\n请输出决策JSON:"
            dec_text = srv.gen(dp, '-', 0, 0, DECIDE_TOK, 0.7, 0)
            dec = parse_decision(dec_text)
            if not dec:
                dec = {'dir': random.choice(DIR_ORDER), 'strength': random.uniform(10, 100),
                       'layer': random.choice([0] + list(range(50, 64))), 'temp': random.uniform(0.4, 1.2),
                       'scale': random.uniform(0.5, 1.8)}
            d = DIRS.get(dec.get('dir', '随机'), DIRS['随机'])
            strength = float(dec.get('strength', 50)); layer = int(dec.get('layer', 0))
            temp = float(dec.get('temp', 0.8)); scale = float(dec.get('scale', 1.0))
            text = srv.gen(PROMPT, d, strength, layer, N_TOK, temp, scale)
            score = evaluate(text)
            # 空输出回退: 注入把模型推向EOS → 无注入重试
            retried = ''
            if score <= -90:
                text2 = srv.gen(PROMPT, '-', 0, 0, N_TOK, temp, 0)
                score2 = evaluate(text2)
                if score2 > score:
                    text, score = text2, score2
                    retried = ' [回退基线]'
            meas_a = srv.meas(MEAS_PROMPT, MEAS_LAYER)
            sv_a = state_vec(meas_a)
            mem.record(i, rnd, sv, dec, score, sv_a)
            lines[i]['hist'].append(f"r{rnd}:{dec.get('dir')}/{strength:.0f}/{layer}/{temp:.1f}={score:.1f}")
            lines[i]['hist'] = lines[i]['hist'][-3:]
            if score > lines[i]['best']:
                lines[i]['best'] = score; lines[i]['best_p'] = dec
            if score > global_best['score']:
                global_best = {'score': score, 'p': dec, 'text': text}
            logf.write(f"r{rnd}l{i} st={meas_str[:40]} dec={dec} sc={score:.2f}{retried}\n"); logf.flush()
        if rnd % 5 == 0:
            st = mem.stats()
            print(f"round {rnd}/{N_ROUNDS} best={global_best['score']:.2f} mem={st} ctx={ctx.summary()[:80]}")
            logf.write(f"# r{rnd} best={global_best['score']:.2f} mem={st}\n"); logf.flush()

    srv.close()
    print('\n=== 进化完成 ===')
    print(f'全局最优: score={global_best["score"]:.2f}')
    print(f'决策: {global_best["p"]}')
    print(f'输出: {global_best["text"][:400]}')
    print('皮层规律:', ctx.summary())
    for k in DIR_ORDER:
        sts = mem.state_transition_stats(k)
        if sts:
            print(f'方向[{k}]: n={sts["n"]} avg_score={sts["avg_score"]:.1f} avg_move={[round(x,3) for x in sts["avg_move"]]}')
    logf.write(f'\nFINAL best={global_best["score"]:.2f} p={global_best["p"]}\nTEXT: {global_best["text"]}\n')
    logf.close()
    print(f'总耗时: {time.time()-t0:.0f}s')

if __name__ == '__main__':
    main()
