# -*- coding: utf-8 -*-
"""runner.py 批N : 跑第 N 批纯numpy脚本, 每脚本限时2秒, 结果写 result_N.jsonl"""
import subprocess, sys, os, time, json, glob

def is_runnable(f):
    try: s=open(f,encoding='utf-8',errors='ignore').read(3000)
    except: return False
    if 'torch' in s or 'gguf' in s or 'requests' in s or 'urllib' in s or 'scipy' in s: return False
    if 'w.gguf' in s or 'qwen05b' in s or '/root/autodl' in s: return False
    return True

files=[f for f in sorted(glob.glob('/workspace/*.py')) if is_runnable(f)]
files=[f for f in files if os.path.basename(f) not in ('runner.py','say.py','np_tok.py')]

B=25
N=int(sys.argv[1]) if len(sys.argv)>1 else 0
batch=files[N*B:(N+1)*B]
out=f'/workspace/result_{N}.jsonl'
with open(out,'w',encoding='utf-8') as fo:
    for f in batch:
        nm=os.path.basename(f)
        t0=time.time()
        try:
            r=subprocess.run([sys.executable,f],capture_output=True,timeout=2,
                             cwd='/workspace',text=True,errors='ignore')
            ok = r.returncode==0
            tail=(r.stdout or '')[-400:]
            err=(r.stderr or '')[-200:]
        except subprocess.TimeoutExpired as e:
            ok=None
            tail=(e.stdout or b'').decode('utf-8','ignore')[-400:] if isinstance(e.stdout,bytes) else (e.stdout or '')[-400:]
            err='TIMEOUT'
        except Exception as e:
            ok=False; tail=''; err=str(e)[:200]
        dt=time.time()-t0
        fo.write(json.dumps({'name':nm,'ok':ok,'dt':round(dt,2),
                             'tail':tail,'err':err},ensure_ascii=False)+'\n')
        fo.flush()
print(f"批{N} 完成: {len(batch)} 个脚本 -> {out}")
print("脚本清单: " + ", ".join(os.path.basename(x) for x in batch))
