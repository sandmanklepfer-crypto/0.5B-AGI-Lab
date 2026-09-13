#!/usr/bin/env python3
"""几何工具代理 v1: 模型自主调用几何工具 (内化)
0.5B 在输出中写标记 → 解释器执行 → 反馈继续
工具:
  ⟨RETRIEVE:线索⟩  内容寻址检索记忆
  ⟨PUSH⟩           换思路 (随机方向注入)
"""
import subprocess, re, sys, os, numpy as np

CLI = '/workspace/llama.cpp/build/bin/llama-cli'
MODEL = '/workspace/qwen2.5-0.5b-instruct-q4_k_m.gguf'
RETRIEVE = '/workspace/heartbeat/memory_retrieve.py'

TOOL_PROMPT = """你是拥有几何工具的智能体。遇到以下情况时, 你可以在回复中插入工具标记:
- 需要回忆相关历史知识: ⟨RETRIEVE:线索词⟩
- 需要换个思路重新思考: ⟨PUSH⟩
工具会被自动执行并反馈结果。请开始。
"""

def gen(context, n=40, cv=None, cv_str=0, timeout=150):
    cmd = [CLI, '-m', MODEL, '-p', context, '-n', str(n), '-st', '--temp', '0.6',
           '--seed', '42', '--no-display-prompt']
    if cv:
        cmd += ['--control-vector-scaled', f'{cv}:{cv_str}']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    out = re.sub(r'[\x00-\x1f]', '', r.stdout)
    i = out.rfind('请开始')
    return out[i+3:].strip() if i >= 0 else out[-300:].strip()

def retrieve(clue):
    r = subprocess.run(['python3', RETRIEVE, 'query', clue, '2'],
                       capture_output=True, text=True, timeout=180)
    lines = r.stdout.split('\n')
    if '===RETRIEVED===' in lines:
        i = lines.index('===RETRIEVED===')
        return '\n'.join(lines[i+1:]).strip()[:300]
    return '(无记忆)'

def make_push_cv():
    """生成随机推开方向 bin (PUSH工具)"""
    rng = np.random.default_rng(7)
    d = rng.standard_normal(896).astype(np.float32)
    d /= np.linalg.norm(d)
    d *= 8.77
    path = '/tmp/push_dir.bin'
    d.tofile(path)
    return path

def main():
    goal = sys.argv[1] if len(sys.argv) > 1 else "深入分析:在资源有限的世界里,一个智能体如何通过持续扩张和探索来生存和进化,并给出具体策略"
    context = TOOL_PROMPT + f"\n任务: {goal}\n思考:"
    push_cv = make_push_cv()
    used_tools = []
    print("═══ 几何工具代理启动 ═══\n")

    for rnd in range(5):
        print(f"── 轮次{rnd+1} ──")
        out = gen(context)
        print(f"[输出] {out[:150]}")
        # 解析工具标记
        r_m = re.search(r'⟨RETRIEVE:([^⟩]+)⟩', out)
        p_m = re.search(r'⟨PUSH⟩', out)
        if r_m:
            clue = r_m.group(1).strip()
            print(f"[工具] 模型调用 RETRIEVE: {clue}")
            mem = retrieve(clue)
            print(f"[反馈] 检索到: {mem[:80]}...")
            context += f"\n[工具结果] 回忆到的记忆: {mem}\n继续:"
            used_tools.append(f'RETRIEVE({clue})')
            continue
        if p_m:
            print("[工具] 模型调用 PUSH (换思路)")
            out2 = gen(context + "\n[工具] 换个角度重新思考:", cv=push_cv, cv_str=10)
            print(f"[新思路] {out2[:120]}")
            context += f"\n[工具结果] 新角度: {out2}\n继续:"
            used_tools.append('PUSH')
            continue
        # 无工具调用 → 结束
        print("[结束] 模型未调用工具")
        break

    print(f"\n═══ 完成: 使用工具 {used_tools} ═══")
    print(f"最终上下文长度: {len(context)} 字符")

if __name__ == '__main__':
    main()
