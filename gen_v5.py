#!/usr/bin/env python3
# gen_v5: 容器直连 llama-server(127.0.0.1:8081), 解析 JSON content, 按行切分 Qwen 回答
# 产出高质量中文短句语料 (每行一句)
import json, re, subprocess, sys, time

OUT = "/workspace/qwen_data_v5.txt"
LOG = "/workspace/gen_v5.log"

PROMPTS = [
    "写5句生活常识", "写5句日常对话", "写5句问候语",
    "写5句开心的话", "写5句赞美的话", "写5句难过的话", "写5句生气的话",
    "写5句问句", "写5句关于动物的句子", "写5句关于植物的句子",
    "写5句关于天气的句子", "写5句关于食物的句子", "写5句关于城市的句子", "写5句鼓励的话",
    "写5句感谢的话", "写5句道歉的话", "写5句告别的话", "写5句关于学习的话",
    "写5句关于工作的句子", "写5句关于家人的句子", "写5句关于朋友的句子", "写5句感叹句",
    "写5句关于时间的句子", "写5句关于地点的句子", "写5句关于颜色的句子", "写5句日常提醒",
    "写5句关于健康的话", "写5句关于梦想的话", "写5句关于努力的话", "写5句关于成功的话",
    "写5句关于失败的话", "写5句关于月亮的话", "写5句关于大海的话", "写5句关于星星的话",
    "写5句关于阳光的话", "写5句关于读书的话", "写5句关于音乐的话", "写5句关于运动的话",
]

def gen(prompt: str) -> list[str]:
    """调用 llama-server, 返回提取出的干净句子列表"""
    body = json.dumps({"prompt": prompt, "n_predict": 200, "temperature": 0.9})
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "25", "http://127.0.0.1:8081/completion", "-d", body],
            capture_output=True, text=True, timeout=30)
        data = json.loads(r.stdout)
        content = data.get("content", "")
    except Exception as e:
        return []
    lines = []
    for ln in content.split("\n"):
        ln = ln.strip()
        # 去掉编号前缀 "1." "1、" "1)" "12."
        ln = re.sub(r'^\d+[\.、)．]', '', ln).strip()
        # 去掉引号包裹
        ln = ln.strip('"').strip('"')
        if not ln:
            continue
        # 丢弃: 模型复述/元话语/残句/含ASCII/含/或= /太短太长
        if re.search(r'[a-zA-Z/="]', ln):
            continue
        if re.match(r'^[，。、！？：；,\.]', ln):
            continue
        if re.search(r'好的|我来|以下是|写5句|为你|让我|开始|请|谢谢你的', ln):
            continue
        if len(ln) < 4 or len(ln) > 50:
            continue
        lines.append(ln)
    return lines

def main():
    with open(OUT, "w") as f:
        pass
    with open(LOG, "w") as f:
        pass
    seen = set()
    total = 0
    for p in PROMPTS:
        got = gen(p)
        new = [s for s in got if s not in seen]
        for s in new:
            seen.add(s)
        with open(OUT, "a") as f:
            for s in new:
                f.write(s + "\n")
        total = len(seen)
        with open(LOG, "a") as f:
            f.write(f"{p} -> +{len(new)} (total {total})\n")
        print(f"{p} -> +{len(new)} (total {total})", flush=True)
        time.sleep(0.3)
    with open(LOG, "a") as f:
        f.write(f"DONE: {total} 条\n")
    print(f"DONE: {total} 条")

if __name__ == "__main__":
    main()
