#!/usr/bin/env python3
"""
V121 胎儿扫描 — 在v120子宫里找自涌现的生命信号
子宫(v120): 能量约束 + 知识池(环境) + 慢S守门 + 冲突生死
本版加"变异源"(随机小扰动注入慢S/池) = 给演化可能的种子
扫描(只观测, 不设计):
  S1 慢S分裂度: 慢S若自己分化出多方向(非我们设的池) = 子自我涌现
  S2 策略适应: 能量低时模型自发改变行为(如检索模式/重复倾向) = 为活而活
  S3 自催化凝聚: 某段内容持续自维持(出现长重复结构但不死) = 结构自复制
  S4 偏好形成: 主题池使用分布自发偏斜(性格萌芽, 非种子给定)
多轮独立生命 × 每轮长程, 统计跨轮信号
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
N_POOL = 24
B_POOL, B_FAST = 0.08, 0.4
GATE_COS = 0.65
E_INIT, E_COST_T, E_COST_R, E_GAIN = 1.2, 0.0004, 0.004, 0.0015
MUT_EVERY = 150         # 变异频率(步)
MUT_STRENGTH = 0.03     # 变异强度
N_LIVES = 4             # 几世
MAX_TOK = 2500
SEEDS = [
    '爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，',
    '渔村的黄昏总是先落在灯塔上。老周提着最后一桶鱼油爬上石阶，潮水正在退去，露出大片湿漉漉的礁石，远处有船鸣了一声长笛。他把灯芯拨亮，光柱扫过海面时，',
    '雨从傍晚开始下，一直没停。林默在便利店门口站了十分钟，看着对面药店的灯牌把雨丝染成绿色。他其实没有带伞，也没有要买的东西。口袋里那封信已经揣了三天，',
    '绿洲边缘的旅店只有七个房间。掌柜阿依古丽记得每一个住客的脸，但今晚来的人她从未见过：一个背着铁箱的年轻人，鞋底没有一粒沙子，却说要穿越整片沙漠。',
]
WORLD_KEYS = [['老屋','屋','爷爷','山','院','门','灰','脚印'], ['渔村','灯塔','海','船','鱼','潮'], ['雨','便利店','伞','信','林默','灯'], ['旅店','沙漠','绿洲','铁箱','阿依古丽','房间']]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    results = {}
    for life_i, (seed, keys) in enumerate(zip(SEEDS, WORLD_KEYS)):
        torch.manual_seed(life_i)
        model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
        st = {'eta': 0.9, 'v': None, 'u': None}
        def make_hook():
            def hook(mod, inp, out):
                if st['eta'] > 0 and st['v'] is not None:
                    h = out[0] if isinstance(out, tuple) else out
                    g = torch.matmul(h, st['u'])
                    h = h + st['eta'] * g.unsqueeze(-1) * st['v']
                    return (h,) if isinstance(out, tuple) else h
                return out
            return hook
        hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
        def last_hidden(ids):
            with torch.no_grad():
                hs = model(input_ids=ids, output_hidden_states=True).hidden_states
            return hs[LAYER+1][0, -1].float().cpu().numpy()

        # 知识池
        ids = tok(seed, return_tensors='pt').input_ids.to('cuda')
        pool = []
        for i in range(N_POOL):
            v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
            pool.append(vn.copy())
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            nid = torch.multinomial(torch.softmax(logits/0.9,-1),1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)

        Sf = Ss = None
        E = E_INIT
        out_toks = []
        pool_use = np.zeros(N_POOL)
        strat_hist = []   # 策略(检索率滚动)
        energy_hist = []
        t0 = time.time()
        dead = None
        # 启动正文
        ids = tok(seed, return_tensors='pt').input_ids.to('cuda')
        for i in range(MAX_TOK):
            v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
            Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
            mix = Sf/(np.linalg.norm(Sf)+1e-9)
            if Ss is None: Ss = vn.copy()
            else:
                cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
                if cos >= GATE_COS: Ss = (1-0.08)*Ss + 0.08*vn
            P = np.stack(pool); cosv = P @ vn
            if E > E_COST_R * 3:
                idx = np.argsort(-cosv)[:2]
                fit = float(cosv[idx].mean())
                E -= E_COST_R
                if fit > 0.3: E += E_GAIN * fit
                for j in idx:
                    pool[j] = pool[j]*(1-B_POOL) + B_POOL*vn
                    pool_use[j] += 1
                wm = sum(cosv[j]*pool[j] for j in idx); wm = wm/(np.linalg.norm(wm)+1e-9)
                mix = mix + 0.4*wm
                strat = 1
            else:
                strat = 0
            # 变异: 偶发注入随机方向(演化种子)
            if i > 0 and i % MUT_EVERY == 0:
                mut = np.random.RandomState(i).randn(896)
                mut = mut/(np.linalg.norm(mut)+1e-9) * MUT_STRENGTH
                mix = mix + mut
                Ss = Ss + mut*0.3
            E -= E_COST_T; E = min(E, 1.6)
            mix = mix/(np.linalg.norm(mix)+1e-9)
            strat_hist.append(strat); energy_hist.append(E)
            st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(logits/0.85, -1)
            nid = torch.multinomial(p, 1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
            if E <= 0: dead = 'energy'; break
            if len(out_toks) > 20:
                ps = torch.sort(p, descending=True)[0]
                if ps[0].item() > 0.92 and len(set(out_toks[-8:])) == 1: dead = 'lock'; break
        text = tok.decode(out_toks, skip_special_tokens=True)
        # ---- 胎儿信号扫描 ----
        n = len(out_toks)
        # S4 偏好: 池使用偏斜度(Gini)
        gu = pool_use + 1e-9
        gini = 1 - ((gu/gu.sum())**2).sum()
        # S2 策略适应: 检索率是否随能量变化(前半vs后半)
        ne = len(energy_hist); half = ne//2
        strat_first = np.mean(strat_hist[:half]) if half>0 else 0
        strat_second = np.mean(strat_hist[half:]) if half>0 else 0
        adapt = strat_second - strat_first  # >0 = 越活越敢探索(或反向)
        # S3 自催化凝聚: 最长重复串长度(>30字算结构自维持信号)
        reps = re.findall(r'(.{12,})\1+', text)
        maxrep = max((len(m[0]) for m in reps), default=0)
        # 世界保持
        wk = sum(1 for k in keys if k in text)
        print('世%d | 寿命%d %s | 池偏斜G=%.3f | 策略适应%+.2f | 最长自重复=%d字 | 世界词x%d | %.0fs' % (
            life_i+1, n, dead, gini, adapt, maxrep, wk, time.time()-t0), flush=True)
        results[life_i] = {'life': n, 'dead': dead, 'gini': gini, 'adapt': adapt, 'maxrep': maxrep, 'world': wk}
        del model; torch.cuda.empty_cache()
    # 跨世总结
    print('\n=== V121 胎儿扫描总结 ===', flush=True)
    print('信号S4偏好: Gini>0.3 表示池自发偏斜(性格萌芽)')
    print('信号S2适应: adapt显著非0 = 自发策略调整(为活而活)')
    print('信号S3凝聚: maxrep>30 = 结构自维持(自催化候选)')
    for k, r in results.items():
        print('世%d: %s' % (k+1, r), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
