#!/usr/bin/env python3
"""实时进度监视: 通过 ComfyUI WebSocket 打印采样进度条"""
import json, time, sys, urllib.request
import websocket

BASE = "http://127.0.0.1:8188"
WS = "ws://127.0.0.1:8188/ws"

def get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": str(e)}

# 取当前运行/最近的 prompt_id
def current_prompt_id():
    q = get("/queue")
    for item in q.get("queue_running", []):
        return item[1]
    # fallback: 最近 history
    h = get("/history")
    if h and not h.get("_err"):
        return list(h.keys())[-1]
    return None

pid = current_prompt_id()
print(f"[{time.strftime('%H:%M:%S')}] 监视任务 {pid}", flush=True)

client_id = f"watch-{int(time.time())}"
ws = websocket.create_connection(WS + f"?clientId={client_id}", timeout=30)

def bar(pct, width=24):
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

start = time.time()
cur_print = 0
prog = None
while True:
    try:
        msg = json.loads(ws.recv())
    except Exception:
        break
    t = msg.get("type")
    d = msg.get("data", {})
    if t != "status":
        print(f"\n[WS:{time.strftime('%H:%M:%S')}] type={t} {str(d)[:120]}", flush=True)
    if t == "progress":
        v, m = d.get("value", 0), d.get("max", 1)
        if m and m > 0:
            prog = (v, m)
    elif t == "executed":
        node = d.get("node", "")
        out = d.get("output", {})
        imgs = out.get("images") or out.get("gifs") or out.get("video") or []
        if imgs:
            print(f"\n[{time.strftime('%H:%M:%S')}] 节点 {node} 输出: {imgs}", flush=True)
    elif t == "execution_success" or t == "execution_cached":
        print(f"\n[{time.strftime('%H:%M:%S')}] ✓ 任务完成!", flush=True)
        break
    elif t == "execution_error":
        print(f"\n[{time.strftime('%H:%M:%S')}] ✗ 任务出错: {str(d)[:300]}", flush=True)
        break
    if prog:
        v, m = prog
        pct = v / m * 100
        now = time.time()
        if now - cur_print > 1.0:
            el = now - start
            speed = v / el if el > 0 else 0
            eta = (m - v) / speed if speed > 0 else "?"
            print(f"\r[{bar(pct)}] {pct:5.1f}%  采样 {v}/{m} 步  用时 {el:.0f}s  ETA {eta:.0f}s" if isinstance(eta, float) else f"\r[{bar(pct)}] {pct:5.1f}%  采样 {v}/{m} 步  用时 {el:.0f}s", end="", flush=True)
            cur_print = now
time.sleep(1)
