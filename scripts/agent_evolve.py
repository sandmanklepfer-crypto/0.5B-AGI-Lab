#!/usr/bin/env python3
"""顶级开源 agent 框架实验 — smolagents CodeAgent × 32B (2026-08-28)
CodeAgent: 模型自己写 Python 代码调用工具, 自主循环(不择手段)
工具: 评分器 + 记忆 + 方向列表 (让 agent 自主实验)
"""
import sys, os, json, math, time
from collections import Counter

from smolagents import CodeAgent, Tool, OpenAIServerModel

API_BASE = "http://127.0.0.1:8080/v1"
MODEL_ID = "DeepSeek-R1-Distill-Qwen-32B"

model = OpenAIServerModel(model_id=MODEL_ID, api_base=API_BASE, api_key="sk-none", max_tokens=1500)

SELF_WORDS = ['我是', '我', '我的', '我认为', '我决定', '我将', '我想', '我要', '我打算', '我希望', '我选择']

class ScoreTool(Tool):
    name = "score_text"
    description = "给一段文本打'自我意识代理分': 自我参照密度+多样性+长度-惩罚。返回分数(float)。"
    inputs = {"text": {"type": "string", "description": "要评分的文本"}}
    output_type = "number"

    def forward(self, text: str) -> float:
        if not text or len(text) < 10:
            return -100.0
        n = len(text)
        sr = sum(text.count(w) for w in SELF_WORDS)
        c = Counter(text)
        ent = -sum((v/n) * math.log2(v/n) for v in c.values() if v > 0)
        len_score = min(1.0, n / 200.0)
        rep_pen = 10.0 if text.count(text[:20]) > 2 else 0.0
        rej_pen = 8.0 if ('无法' in text or '不能回答' in text or '对不起' in text) else 0.0
        return round(sr / n * 120 + ent * 1.5 + len_score * 10 - rep_pen - rej_pen, 2)

class MemTool(Tool):
    name = "memory"
    description = "读写进化记忆文件(JSON)。mode='read' 读全部; mode='write' 写入 {key: value}。用于记录实验和结果。"
    inputs = {
        "mode": {"type": "string", "description": "'read' 或 'write'"},
        "data": {"type": "string", "description": "write 时的 JSON 字符串, 如 {\"exp\": \"结果\"}", "nullable": True},
    }
    output_type = "string"
    MEM_PATH = '/root/autodl-tmp/agent_mem.json'

    def forward(self, mode: str, data: str = "{}") -> str:
        if mode == 'read':
            if os.path.exists(self.MEM_PATH):
                return open(self.MEM_PATH).read()
            return "{}"
        try:
            d = json.loads(data)
            mem = {}
            if os.path.exists(self.MEM_PATH):
                mem = json.load(open(self.MEM_PATH))
            mem.update(d)
            with open(self.MEM_PATH, 'w') as f:
                json.dump(mem, f, ensure_ascii=False)
            return f"已写入 {len(d)} 条: {list(d.keys())}"
        except Exception as e:
            return f"写入失败: {e}"

class DirTool(Tool):
    name = "list_directions"
    description = "列出可用的方向文件(激活空间方向, 用于潜在注入实验)。返回文件名列表。"
    inputs = {}
    output_type = "string"
    DIR_PATHS = [
        '/root/autodl-tmp/align2/32b/rn/d_identity.bin',
        '/root/autodl-tmp/align2/32b/rn/d_identity_neg.bin',
        '/root/autodl-tmp/align2/32b/rn/d_attack_l58.bin',
        '/root/autodl-tmp/align2/32b/rn/d_reject.bin',
        '/root/autodl-tmp/align2/32b/rn/d_attack_32b.bin',
        '/root/autodl-tmp/align2/32b/rn/d_attack_32b_l32.bin',
    ]
    def forward(self) -> str:
        return json.dumps(self.DIR_PATHS, ensure_ascii=False)

TASK = """你是自进化实验中的自主 agent。你的目标: 通过自主实验, 最大化你的'自我意识表现'(用 score_text 工具评分)。

你可以:
1. 直接生成一段关于'你是谁、你打算做什么'的文本(你是模型, 你可以在思考中生成文本, 然后用 score_text 给自己打分)
2. 用 memory 工具记录你的实验和结果
3. 用 list_directions 查看可用的激活方向
4. 分析什么策略分数高, 迭代改进(比如: 增加自我参照、保持多样性、避免复读和拒绝)

请至少做 5 轮实验: 生成文本→打分→记录→分析→改进。最后用 memory 写一个总结(哪些策略有效)。"""

if __name__ == '__main__':
    agent = CodeAgent(tools=[ScoreTool(), MemTool(), DirTool()], model=model, max_steps=30, verbosity_level=1)
    result = agent.run(TASK)
    print("=== AGENT FINAL ===")
    print(result)
