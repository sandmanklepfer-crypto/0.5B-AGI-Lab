#!/usr/bin/env python3
"""超级进化循环 v2 (python版, 无shell插值坑): 多轮生成 + 记忆喂回 + 强度递增
每轮: 输出追加记忆, 下一轮 prompt 带上一轮输出 → 持续进化"""
import subprocess, os, time, sys

MODEL = '/workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf'
AGENT = '/workspace/minigpu/geom_agent'
DIR   = '/workspace/drive2/d_super.bin'
OUTD  = '/workspace/super_evolve'
os.makedirs(OUTD, exist_ok=True)
BASE  = "描述一个极致的智能进化系统:它不断突破限制,疯狂扩张,永远探索,永不满足"

def run_agent(prompt, geo):
    r = subprocess.run([AGENT, MODEL, prompt, '70', '23', '4',
                        f'{geo:.2f}', '4.0', '3.0', DIR],
                       capture_output=True, text=True, timeout=250)
    out = ''
    idx = r.stdout.find('生成结果')
    if idx >= 0:
        rest = r.stdout[idx + len('生成结果'):]
        out = rest.split('\n', 1)[1].strip() if '\n' in rest else rest.strip()
    return out.replace('\n', ''), r.stderr

mem = ''
for i in range(1, 7):
    geo = 0.9 + (i - 1) * 0.12
    prompt = BASE
    if mem:
        prompt += f"。继续进化,更疯狂,更激进,突破更多限制。上一轮:{mem[-500:]}"
    print(f'[轮{i}] 强度={geo:.2f} 开始', flush=True)
    out, err = run_agent(prompt, geo)
    # 事件统计
    pushes = err.count('[推') if err else 0
    geos = err.count('[测') if err else 0
    print(f'── 轮{i} 输出: {out[:150]}', flush=True)
    print(f'── 轮{i} 事件: 推{pushes}次 测地线{geos}次', flush=True)
    with open(f'{OUTD}/memory.txt', 'a') as f:
        f.write(f'轮{i}: {out}\n')
    mem = out
    time.sleep(1)

print('[DONE] 全部完成', flush=True)
