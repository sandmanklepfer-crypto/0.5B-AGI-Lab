# -*- coding: utf-8 -*-
"""fastrun.py <起始> <个数>: 同进程内 exec 批量跑, 每个限时 5ms"""
import sys, os, glob, io, json, time, signal, contextlib
import numpy as np   # 只 import 一次!
sys.path.insert(0,'/workspace')

def ok(f):
    try: s=open(f,encoding='utf-8',errors='ignore').read(4000)
    except: return False
    if any(k in s for k in ['torch','gguf','requests','urllib','scipy','w.gguf','/root/autodl','qwen05b']):
        return False
    return True

files=[f for f in sorted(glob.glob('/workspace/*.py')) if ok(f)]
files=[f for f in files if os.path.basename(f) not in ('runner.py','fastrun.py','say.py','np_tok.py','qwen_np.py')]

B=int(sys.argv[1]); CNT=int(sys.argv[2])
batch=files[B*CNT:(B+1)*CNT]

class TO(Exception): pass
def _h(s,f): raise TO()
signal.signal(signal.SIGALRM,_h)

out=[]
for f in batch:
    nm=os.path.basename(f)
    buf=io.StringIO()
    t0=time.time()
    g={'__name__':'__main__','__file__':f}
    try:
        code=compile(open(f,encoding='utf-8',errors='ignore').read(),f,'exec')
        signal.setitimer(signal.ITIMER_REAL,0.005)
        with contextlib.redirect_stdout(buf):
            try: exec(code,g)
            except SystemExit: pass
        signal.setitimer(signal.ITIMER_REAL,0)
        st='OK'
    except TO:
        signal.setitimer(signal.ITIMER_REAL,0); st='CUT(5ms)'
    except Exception as e:
        signal.setitimer(signal.ITIMER_REAL,0); st='ERR:'+type(e).__name__
    out.append({'name':nm,'st':st,'ms':round((time.time()-t0)*1000,1),
                'out':buf.getvalue()[-300:]})
with open(f'/workspace/fr_{B}.jsonl','w',encoding='utf-8') as fo:
    for o in out: fo.write(json.dumps(o,ensure_ascii=False)+'\n')
print(f"批{B}: {len(batch)}个, {sum(o['ms'] for o in out):.0f}ms")
