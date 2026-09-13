# -*- coding: utf-8 -*-
"""forkrun.py <起> <数>: fork子进程跑, 硬超时 30ms 就 kill"""
import os, signal, sys, glob, json, time, tempfile
import numpy as np
sys.path.insert(0,'/workspace')

def ok(f):
    try: s=open(f,encoding='utf-8',errors='ignore').read(4000)
    except: return False
    if any(k in s for k in ['torch','gguf','requests','urllib','scipy','w.gguf','/root/autodl','qwen05b']): return False
    return True

files=[f for f in sorted(glob.glob('/workspace/*.py')) if ok(f)]
files=[f for f in files if os.path.basename(f) not in ('runner.py','fastrun.py','forkrun.py','say.py','np_tok.py','qwen_np.py')]
B=int(sys.argv[1]); CNT=int(sys.argv[2])
batch=files[B*CNT:(B+1)*CNT]
TO=float(sys.argv[3]) if len(sys.argv)>3 else 0.03

res=[]
for path in batch:
    nm=os.path.basename(path)
    fd,tmp=tempfile.mkstemp()
    pid=os.fork()
    if pid==0:
        try:
            os.dup2(fd,1); os.dup2(fd,2); os.close(fd)
            g={'__name__':'__main__','__file__':path}
            exec(compile(open(path,encoding='utf-8',errors='ignore').read(),path,'exec'),g)
        except BaseException: pass
        os._exit(0)
    os.close(fd)
    t0=time.time(); st='OK'
    while True:
        p,ss=os.waitpid(pid,os.WNOHANG)
        if p==pid: break
        if time.time()-t0>TO:
            try: os.kill(pid,signal.SIGKILL); os.waitpid(pid,0)
            except: pass
            st='CUT'; break
        time.sleep(0.0005)
    try: body=open(tmp,encoding='utf-8',errors='ignore').read()[-300:]
    except: body=''
    try: os.unlink(tmp)
    except: pass
    res.append({'name':nm,'st':st,'ms':round((time.time()-t0)*1000,1),'out':body})
with open(f'/workspace/fk_{B}.jsonl','w',encoding='utf-8') as fo:
    for o in res: fo.write(json.dumps(o,ensure_ascii=False)+'\n')
print(f"批{B}: {len(batch)}个, 合计{sum(o['ms'] for o in res):.0f}ms, CUT={sum(1 for o in res if o['st']=='CUT')}")
