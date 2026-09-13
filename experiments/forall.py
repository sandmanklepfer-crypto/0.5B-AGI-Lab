# -*- coding: utf-8 -*-
"""forall.py: 从上次进度继续, 跑 0.55 秒就停, 记进度"""
import os,signal,glob,json,time,tempfile,sys
import numpy as np
sys.path.insert(0,'/workspace')
def ok(f):
    try: s=open(f,encoding='utf-8',errors='ignore').read(4000)
    except: return False
    if any(k in s for k in ['torch','gguf','requests','urllib','scipy','w.gguf','/root/autodl','qwen05b']): return False
    return True
files=[f for f in sorted(glob.glob('/workspace/*.py')) if ok(f)]
files=[f for f in files if os.path.basename(f) not in ('runner.py','fastrun.py','forkrun.py','forall.py','say.py','np_tok.py','qwen_np.py')]
PF='/workspace/_prog.json'; RF='/workspace/_res.jsonl'
try: i=json.load(open(PF))['i']
except: i=0
t0=time.time(); BUD=0.55
fo=open(RF,'a',encoding='utf-8')
n0=i
while i<len(files) and time.time()-t0<BUD:
    path=files[i]; fd,tmp=tempfile.mkstemp()
    pid=os.fork()
    if pid==0:
        try:
            os.dup2(fd,1);os.dup2(fd,2);os.close(fd)
            g={'__name__':'__main__','__file__':path}
            exec(compile(open(path,encoding='utf-8',errors='ignore').read(),path,'exec'),g)
        except BaseException: pass
        os._exit(0)
    os.close(fd); tt=time.time(); st='OK'
    while True:
        p,ss=os.waitpid(pid,os.WNOHANG)
        if p==pid: break
        if time.time()-tt>0.012:
            try: os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            except: pass
            st='CUT';break
        time.sleep(0.0004)
    try: b=open(tmp,encoding='utf-8',errors='ignore').read()[-350:]
    except: b=''
    try: os.unlink(tmp)
    except: pass
    fo.write(json.dumps({'name':os.path.basename(path),'st':st,'out':b},ensure_ascii=False)+'\n')
    i+=1
fo.close()
json.dump({'i':i},open(PF,'w'))
print(f"进度 {n0} -> {i} / {len(files)}   (本次{time.time()-t0:.2f}s)")
