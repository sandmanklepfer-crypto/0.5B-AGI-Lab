#!/usr/bin/env python3
import json, time, urllib.request, sys

BASE = "http://127.0.0.1:8188"
def get(path, timeout=5):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": str(e)}

def post(path, data, timeout=20):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"_err": str(e)}

print(f"[{time.strftime('%H:%M:%S')}] 等 API...", flush=True)
for i in range(120):
    st = get("/system_stats")
    if "_err" not in st:
        print(f"[{time.strftime('%H:%M:%S')}] API 就绪", flush=True)
        break
    time.sleep(5)
else:
    print("API 未就绪", flush=True); sys.exit(1)

print(f"[{time.strftime('%H:%M:%S')}] 等 Wan 节点...", flush=True)
for i in range(60):
    oi = get("/object_info/WanVideoModelLoader")
    if "_err" not in oi and oi:
        print(f"[{time.strftime('%H:%M:%S')}] WanVideoModelLoader 已注册 ✓", flush=True)
        break
    time.sleep(5)
else:
    print("Wan 节点未注册", flush=True); sys.exit(1)

wf = json.load(open("/workspace/wan_t2v_test.json"))
print(f"[{time.strftime('%H:%M:%S')}] 提交 workflow...", flush=True)
resp = post("/prompt", {"prompt": wf, "client_id": "rikkahub"})
if "_err" in resp:
    print("提交失败:", resp, flush=True); sys.exit(1)
if "error" in resp:
    print("提交错误:", json.dumps(resp["error"], ensure_ascii=False)[:300], flush=True)
    sys.exit(1)
pid = resp.get("prompt_id", "?")
print(f"[{time.strftime('%H:%M:%S')}] 提交成功 prompt_id={pid}", flush=True)
# 轮询任务状态
for i in range(60):
    time.sleep(10)
    h = get(f"/history/{pid}")
    if "_err" in h or not h:
        continue
    entry = h.get(pid, {})
    st = entry.get("status", {})
    if st.get("completed"):
        print(f"[{time.strftime('%H:%M:%S')}] 任务完成! 输出: {entry.get('outputs', {})}", flush=True)
        break
    if st.get("status_str") == "error":
        msgs = st.get("messages", [])
        print(f"[{time.strftime('%H:%M:%S')}] 任务出错: {msgs[-2:] if msgs else 'unknown'}", flush=True)
        break
    print(f"[{time.strftime('%H:%M:%S')}] 执行中...", flush=True)
