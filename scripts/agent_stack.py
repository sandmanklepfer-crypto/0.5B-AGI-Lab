#!/usr/bin/env python3
"""agent_stack.py — 0.5B(v4c) × smolagents × 知识外挂 组装
v4c 做皮层(意图/表达), CodeAgent 执行 Python(数学/计算=代码), LFM2-RAG 做知识外挂
用法: agent_stack.py [--query "问题"]  (交互模式: 不带 --query)
"""
import sys, os, json, argparse
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")

API_BASE = "http://127.0.0.1:8080/v1"
MODEL_ID = "v4c"

from smolagents import CodeAgent, Tool, OpenAIServerModel

# ---------- 知识外挂: LFM2-RAG (HTTP 常驻服务 8081) ----------
class KnowledgeTool(Tool):
    name = "knowledge_lookup"
    description = "查询知识库回答问题。当用户问事实性知识(历史/科学/人物/事件/文档内容)时调用。返回基于文档的答案。"
    inputs = {"query": {"type": "string", "description": "要查询的问题"}}
    output_type = "string"
    def forward(self, query: str) -> str:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:8081/v1/rag",
            data=json.dumps({"query": query, "k": 2}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())["answer"]

# ---------- 数学外挂: 符号/数值计算 (CodeAgent 的 Python 已能算, 这里兜底) ----------
class MathTool(Tool):
    name = "math_eval"
    description = "计算数学表达式或验证算术。传入 Python 表达式字符串。"
    inputs = {"expr": {"type": "string", "description": "Python 数学表达式, 如 '7*8' 或 '2**10'"}}
    output_type = "string"
    def forward(self, expr: str) -> str:
        try:
            return str(eval(expr, {"__builtins__": {}}, {"math": __import__("math")}))
        except Exception as e:
            return f"error: {e}"

def build_agent():
    model = OpenAIServerModel(model_id=MODEL_ID, api_base=API_BASE, api_key="sk-none", max_tokens=800)
    agent = CodeAgent(
        tools=[KnowledgeTool(), MathTool()],
        model=model,
        max_steps=6,
        verbosity_level=1,
        additional_authorized_imports=["math", "json"],
    )
    return agent

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="")
    ap.add_argument("--task", default="")
    args = ap.parse_args()
    agent = build_agent()
    if args.query or args.task:
        q = args.query or args.task
        print(f"\n=== 任务: {q}", flush=True)
        ans = agent.run(q)
        print(f"\n=== 结果:\n{ans}", flush=True)
    else:
        print("v4c×smolagents agent shell. 输入任务回车, Ctrl+D 退出.")
        while True:
            try:
                q = input("> ").strip()
            except EOFError:
                break
            if not q:
                continue
            try:
                print(agent.run(q), "\n")
            except Exception as e:
                print(f"[agent error] {e}")

if __name__ == "__main__":
    main()
