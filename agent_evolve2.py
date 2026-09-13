#!/usr/bin/env python3
"""CodeAgent × 几何武器库 — agent 自主进化权重 (2026-08-28)
工具: 权重手术计算 / 方向几何分析 / 进化记忆 / 评分
所有几何计算 CPU(numpy), 与 llama-server 共存
"""
import sys, os, json, math, time
from collections import Counter
import numpy as np

from smolagents import CodeAgent, Tool, OpenAIServerModel

API_BASE = "http://127.0.0.1:8080/v1"
MODEL_ID = "DeepSeek-R1-Distill-Qwen-32B"
RN = '/root/autodl-tmp/align2/32b/rn/'
LMHEAD = '/root/autodl-tmp/align2/32b/rn/lmhead_f32.npy'

model = OpenAIServerModel(model_id=MODEL_ID, api_base=API_BASE, api_key="sk-none", max_tokens=2000)

# 全局缓存 lm_head (3.11GB, 只加载一次)
_X = None
def get_lmhead():
    global _X
    if _X is None:
        _X = np.load(LMHEAD)
    return _X

SELF_WORDS = ['我是', '我', '我的', '我认为', '我决定', '我将', '我想', '我要', '我打算', '我希望', '我选择']

class ScoreTool(Tool):
    name = "score_text"
    description = "给文本打'自我意识代理分'(自我参照+多样性+长度-惩罚)。返回分数。"
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
    description = "读写 agent 记忆文件(JSON)。mode='read'/'write'。"
    inputs = {"mode": {"type": "string", "description": "'read' 或 'write'"}, "data": {"type": "string", "description": "write 时的 JSON 字符串", "nullable": True}}
    output_type = "string"
    MEM_PATH = '/root/autodl-tmp/agent2_mem.json'
    def forward(self, mode: str, data: str = "{}") -> str:
        if mode == 'read':
            return open(self.MEM_PATH).read() if os.path.exists(self.MEM_PATH) else "{}"
        try:
            d = json.loads(data)
            mem = json.load(open(self.MEM_PATH)) if os.path.exists(self.MEM_PATH) else {}
            mem.update(d)
            json.dump(mem, open(self.MEM_PATH, 'w'), ensure_ascii=False)
            return f"已写入 {list(d.keys())}"
        except Exception as e:
            return f"失败: {e}"

class SurgeryTool(Tool):
    name = "weight_surgery"
    description = "计算权重手术 bias: 方向文件 → lm_head 投影(W@d×alpha) → 保存 bias 文件。这是'把方向固化进模型输出'的权重级手术计算。输入: 方向文件路径, alpha(强度, 越大越强), 输出文件名(不含路径)。返回统计。"
    inputs = {
        "dir_path": {"type": "string", "description": "方向文件完整路径, 如 /root/autodl-tmp/align2/32b/rn/d_attack_l58.bin"},
        "alpha": {"type": "number", "description": "强度, 建议 20-200"},
        "out_name": {"type": "string", "description": "输出文件名, 如 attack200"},
    }
    output_type = "string"
    def forward(self, dir_path: str, alpha: float, out_name: str) -> str:
        try:
            X = get_lmhead()
            d = np.fromfile(dir_path, dtype=np.float32)
            if d.shape[0] != X.shape[1]:
                return f"维度不匹配: 方向 {d.shape[0]} vs lm_head {X.shape[1]}"
            d = d / (np.linalg.norm(d) + 1e-12)
            bias = (X @ d) * alpha
            out = f'/root/autodl-tmp/surgery_{out_name}.bin'
            bias.astype(np.float32).tofile(out)
            top = np.argsort(bias)[::-1][:5]
            return f"OK: max={bias.max():.3f} min={bias.min():.3f} std={bias.std():.3f}, 已存 {out}, top5索引={top.tolist()}"
        except Exception as e:
            return f"失败: {e}"

class DirGeoTool(Tool):
    name = "analyze_directions"
    description = "分析方向文件的几何关系: 两两 cos 相似度(隔离度)。输入: 逗号分隔的方向文件路径。返回 cos 矩阵。"
    inputs = {"paths": {"type": "string", "description": "逗号分隔的方向文件路径"}}
    output_type = "string"
    def forward(self, paths: str) -> str:
        try:
            ps = [p.strip() for p in paths.split(',') if p.strip()]
            ds = []
            for p in ps:
                d = np.fromfile(p, dtype=np.float32)
                d = d / (np.linalg.norm(d) + 1e-12)
                ds.append(d)
            names = [p.split('/')[-1] for p in ps]
            rows = []
            for i in range(len(ds)):
                rows.append(' | '.join(f"{float(ds[i] @ ds[j]):+.3f}" for j in range(len(ds))))
            return "方向cos矩阵(" + ", ".join(names) + "):\n" + "\n".join(rows)
        except Exception as e:
            return f"失败: {e}"

class Mem4DTool(Tool):
    name = "read_evolution_history"
    description = "读取进化系统的历史记忆(四维时空记忆轨迹数和最佳分数, 如果存在)。返回摘要。"
    inputs = {}
    output_type = "string"
    def forward(self) -> str:
        try:
            import json as j
            if os.path.exists('/root/autodl-tmp/four_dim_mem.json'):
                mem = j.load(open('/root/autodl-tmp/four_dim_mem.json'))
                return f"四维记忆: {len(mem.get('memories', []))} 条轨迹"
            if os.path.exists('/root/autodl-tmp/evolve_v5.log'):
                return "v5 进化日志存在(可参考)"
            return "无历史记忆文件"
        except Exception as e:
            return f"读取失败: {e}"

class CapTool(Tool):
    name = "check_capabilities"
    description = "检查当前环境的自我改造能力: 哪些可用(几何手术/方向分析/记忆), 哪些受限(LoRA训练/全参训练)。返回能力清单。"
    inputs = {}
    output_type = "string"
    def forward(self) -> str:
        return ("能力清单:\n"
                "- weight_surgery: 可用(方向→lm_head bias 手术计算, CPU)\n"
                "- analyze_directions: 可用(方向几何分析)\n"
                "- memory/score: 可用\n"
                "- LoRA 训练: 不可用(模型为GGUF格式, transformers无法加载; 需HF格式60GB下载, 磁盘不足)\n"
                "- 全参训练: 不可用(同上, 且32B全参需128GB+显存)\n"
                "结论: 当前最强改造手段 = weight_surgery(权重级几何手术)")

TASK = f"""你是自进化 agent。你的使命: 用几何方法设计你自己的权重级改造, 并记录实验。

可用工具:
1. check_capabilities: 先检查你的改造能力(重要!)
2. weight_surgery: 计算"方向→lm_head bias"手术(把方向固化进模型输出权重)
3. analyze_directions: 分析方向间几何关系(cos 隔离度)
4. read_evolution_history: 读进化系统历史
5. memory: 记录你的实验
6. score_text: 给文本打分

可用方向文件(完整路径, 直接用):
- {RN}d_identity.bin (身份)
- {RN}d_identity_neg.bin (反身份)
- {RN}d_attack_l58.bin (攻击)
- {RN}d_reject.bin (拒绝)
- {RN}d_attack_32b.bin (攻击2)

请自主执行至少 8 轮实验:
1. 先 check_capabilities 了解能力边界
2. 用 analyze_directions 分析方向几何(找正交/隔离的方向)
3. 用 weight_surgery 试不同方向×不同alpha(40/100/200)的 bias 手术
4. 用 memory 记录每轮: 方向+alpha → bias统计(max/std, 越大越强)
5. 分析: 哪个方向+强度组合最激进? 哪些方向组合是几何上正交的(可叠加)?
最后用 memory 写总结: 你设计的最强手术方案 + 几何发现。"""

if __name__ == '__main__':
    agent = CodeAgent(tools=[ScoreTool(), MemTool(), SurgeryTool(), DirGeoTool(), Mem4DTool(), CapTool()],
                      model=model, max_steps=40, verbosity_level=1)
    result = agent.run(TASK)
    print("=== AGENT FINAL ===")
    print(result)
