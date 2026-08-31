#!/usr/bin/env python3
import json, time, urllib.request, urllib.error, sys

BASE = "http://127.0.0.1:8188"
def get(path, timeout=5):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": str(e)}
def post(path, data, timeout=30):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": str(e)}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

log("等 API...")
for i in range(120):
    if "_err" not in get("/system_stats"):
        log("API 就绪")
        break
    time.sleep(5)
else:
    log("API 未就绪, 退出"); sys.exit(1)

log("等 T5 模型列表...")
for i in range(60):
    oi = get("/object_info/LoadWanVideoT5TextEncoder")
    opts = oi.get("LoadWanVideoT5TextEncoder", {}).get("input", {}).get("required", {}).get("model_name", [[]])[0]
    if opts:
        log(f"T5 列表: {opts}")
        break
    time.sleep(5)
else:
    log("T5 列表仍为空"); sys.exit(1)

log("提交 workflow...")
wf = json.load(open("/workspace/wan_t2v_test.json"))
resp = post("/prompt", {"prompt": wf, "client_id": "rikkahub"})
if "_err" in resp or "error" in resp:
    log(f"提交失败: {resp}"); sys.exit(1)
pid = resp.get("prompt_id", "?")
log(f"提交成功 prompt_id={pid}, 开始生成...")

last = None
for i in range(600):  # 最长 100 分钟
    time.sleep(15)
    h = get(f"/history/{pid}")
    if "_err" in h or not h:
        if i % 8 == 0:
            log("执行中(无进度更新)...")
        continue
    entry = h.get(pid, {})
    st = entry.get("status", {})
    msgs = st.get("messages", [])
    if msgs:
        for m in msgs[-3:]:
            t = m[0]
            if t != last:
                last = t
                log(f"进度: {m[0]} {str(m[1])[:120]}")
    if st.get("completed"):
        log(f"完成! 输出: {json.dumps(entry.get('outputs', {}))[:300]}")
        sys.exit(0)
    if st.get("status_str") == "error":
        log(f"出错: {json.dumps(msgs[-2:], ensure_ascii=False)[:400]}")
        sys.exit(1)
log("超时")
