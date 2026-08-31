#!/usr/bin/env python3
"""探路(wait test_t5 SUCCESS) -> 清场 -> 重启ComfyUI -> 提交生成 -> 持续报进度"""
import json, time, subprocess, urllib.request, urllib.error, sys, os, signal

BASE = "http://127.0.0.1:8188"
def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

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

# 1) 探路 (可用 --skip-probe 跳过): 等 test_t5 SUCCESS
SKIP_PROBE = "--skip-probe" in sys.argv
if SKIP_PROBE:
    log("跳过探路: T5 已确认可用, 直接生成")
else:
    log("探路: 等 T5 编码 SUCCESS ...")
    t0 = time.time()
    while time.time() - t0 < 480:
        try:
            txt = open("/workspace/test_t5.log").read()
        except Exception:
            txt = ""
        if "\nSUCCESS" in txt or txt.startswith("SUCCESS"):
            log("探路通过: T5 编码成功 ✓")
            break
        if "Traceback" in txt or "KeyError" in txt:
            log("探路失败: 有 traceback")
            print(txt[-2000:])
            sys.exit(1)
        time.sleep(10)
    else:
        log("探路超时"); sys.exit(1)

# 2) 清场: 杀所有 python3 除了自己
log("清场: 杀掉其他 python3 ...")
my_pid = os.getpid()
for p in subprocess.run("pgrep -x python3", shell=True, capture_output=True, text=True).stdout.split():
    if int(p) != my_pid:
        try:
            os.kill(int(p), signal.SIGKILL)
        except Exception:
            pass
time.sleep(4)

# 3) 启动 ComfyUI (用 subprocess, 独立进程)
log("启动 ComfyUI ...")
pf = open("/workspace/comfyui.log", "w")
subprocess.Popen(["python3", "/workspace/ComfyUI/main.py", "--cpu", "--port", "8188"],
                 cwd="/workspace/ComfyUI", stdout=pf, stderr=subprocess.STDOUT,
                 start_new_session=True)

# 4) 等 API + DiT GGUF 注册
log("等 API ...")
for i in range(90):
    if "_err" not in get("/system_stats"):
        log("API 就绪 ✓")
        break
    time.sleep(5)
else:
    log("API 未就绪"); sys.exit(1)

log("等 DiT GGUF 模型列表 ...")
for i in range(60):
    oi = get("/object_info/WanVideoModelLoader")
    opts = oi.get("WanVideoModelLoader", {}).get("input", {}).get("required", {}).get("model", [[]])[0]
    if any("Q4_K_M" in o for o in opts):
        log(f"DiT GGUF 已注册: {[o for o in opts if 'Q4' in o]}")
        break
    time.sleep(5)
else:
    log("警告: DiT GGUF 未列, 继续试提交")

# 5) 提交
log("提交生成任务 ...")
wf = json.load(open("/workspace/wan_t2v_test.json"))
resp = post("/prompt", {"prompt": wf, "client_id": "rikkahub"})
if "_err" in resp or "error" in resp:
    log(f"提交失败: {resp}")
    sys.exit(1)
pid = resp.get("prompt_id", "?")
log(f"提交成功 prompt_id={pid}")

# 6) 持续报进度
last = set()
for i in range(400):
    time.sleep(15)
    h = get(f"/history/{pid}")
    if "_err" in h or not h:
        continue
    entry = h.get(pid, {})
    st = entry.get("status", {})
    msgs = st.get("messages", [])
    had_new = False
    for m in msgs:
        if m[0] not in last:
            last.add(m[0])
            log(f"进度: {m[0]} {str(m[1])[:130]}")
            had_new = True
    if st.get("completed"):
        log(f"完成! 输出: {str(entry.get('outputs'))[:300]}")
        sys.exit(0)
    if st.get("status_str") == "error":
        log(f"出错: {json.dumps(msgs[-2:], ensure_ascii=False)[:400]}")
        sys.exit(1)
log("超时")
