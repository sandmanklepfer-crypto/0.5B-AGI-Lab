from modelscope import snapshot_download
import time
t0 = time.time()
snapshot_download("Qwen/Qwen2.5-3B-Instruct", local_dir="/root/autodl-tmp/qwen3b", max_workers=8)
print("MS_3B_DONE", round(time.time()-t0,1), "s")
