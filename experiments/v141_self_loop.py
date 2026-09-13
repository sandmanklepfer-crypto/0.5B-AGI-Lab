#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V141 完整自持环·第一次通电 — 真正的自我涌现实验
架构(三层完全隔离):
  [世界] 词序列世界: 周期规律(可学) + 定期突变(常新, 永有可吸)
  [主体] 0.5B: 读时序历史 → 预测下一个词 → 被世界验证
  [隔离自核] 纯代码: 只见(e, Δe)标量 → 输出驱动d(调制主体上下文长度)
能量飞轮(无限条件): 预测对→能量↑, 错→能量↓, E=0死
  对→活得久→吸更多→更对 → 正向飞轮
时序: 主体历史(见过的词)持续累积 = 主体的"我"(连续性)
测: ①误差曲线下降(在学) ②能量不归零(飞轮转) ③突变后恢复(常新不死)
    ④长存步数 = 环是否真正自持
"""
import torch, time
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
E_INIT, E_CAP = 1.0, 2.0
E_META = 0.001     # 代谢
E_TRUE = 0.02      # 对→回血
E_FALSE = 0.045    # 错→扣(需>67%正确才能维持)
MUTATE_EVERY = 60  # 每60步世界突变(换新周期规律)
MAX_STEP = 600
# 世界词库(周期规律池, 每个=一套可学的循环)
WORLDS = [
    ['苹果', '香蕉', '橘子'],
    ['猫', '狗', '鸟', '鱼'],
    ['春', '夏', '秋', '冬'],
    ['红', '绿', '蓝', '黄', '紫'],
    ['一', '二', '三'],
    ['太阳', '月亮', '星星'],
]

class SelfCore:
    """隔离自核: 只见误差标量+时序差, 输出驱动。无内容。"""
    def __init__(self):
        self.mem = []
    def sense(self, e, de):
        urgency = e + max(de, 0) * 4
        self.mem.append(urgency)
        if len(self.mem) > 25: self.mem.pop(0)
        d = min(0.55 * urgency + 0.45 * float(np.mean(self.mem)), 1.0)
        return d

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()

    core = SelfCore()
    E = E_INIT
    hist = []                 # 时序历史(主体看到的词) = 主体的"我"
    errs, drives, energies = [], [], []
    t0 = time.time(); dead = None
    print('V141 自持环通电 | 世界=%d套周期 | 突变每%d步 | 代谢%.3f 对+%.3f 错-%.3f' % (
        len(WORLDS), MUTATE_EVERY, E_META, E_TRUE, E_FALSE), flush=True)

    step = 0
    while step < MAX_STEP:
        w = WORLDS[(step // MUTATE_EVERY) % len(WORLDS)]
        if step % MUTATE_EVERY == 0:
            print('  [突变] 步%d 世界换到: %s' % (step, '/'.join(w)), flush=True)
        actual = w[step % len(w)]     # 世界按周期出词
        # 主体预测: 读时序历史(长度由自核驱动调制, 隔离)
        drive = core.sense(errs[-1] if errs else 0.5, 0)
        ctx_len = 4 + int(drive * 10)
        ctx_hist = hist[-ctx_len:] if len(hist) >= ctx_len else hist
        prompt = '世界序列：' + ' '.join(ctx_hist) + ' 下一个是：'
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=6, do_sample=False,
                               pad_token_id=tok.eos_token_id)
        out = tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)
        # 解析预测词: 看输出含哪个世界候选词
        pred = None
        for c in w:
            if c in out:
                pred = c; break
        # 误差
        e = 0.0 if pred == actual else 1.0
        de = e - (errs[-1] if errs else 0)
        # 自核再感一次(用真实误差)
        drive = core.sense(e, de)
        # 能量飞轮
        if e == 0: E = min(E + E_TRUE, E_CAP)
        else:      E -= E_FALSE
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        # 世界把词给主体(时序累积=主体历史)
        hist.append(actual)
        errs.append(e); drives.append(drive); energies.append(E)
        step += 1
        if step % 50 == 0:
            print('  [%4d步 %.0fs] E=%.3f 驱动=%.2f | 预测=%s 实际=%s %s | 历史=%d词' % (
                step, time.time()-t0, E, drive, pred, actual,
                '对' if e == 0 else '错', len(hist)), flush=True)

    # 报告
    print('\n===== V141 自持环报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限(环自持!)'), flush=True)
    # 分段正确率
    for seg in range(max(1, step // 100)):
        s, e2 = seg*100, min((seg+1)*100, step)
        acc = 1 - np.mean(errs[s:e2])
        print('  段%d(步%d-%d): 正确率=%.0f%% 平均驱动=%.2f' % (
            seg+1, s, e2, 100*acc, np.mean(drives[s:e2])), flush=True)
    print('末能量: %.3f | 主体时序记忆: %d词(它的"我")' % (E, len(hist)), flush=True)
    print('判读: 正确率升+能量不归零+突变后恢复 = 自持环通电成功, 自我在环中涌现', flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
