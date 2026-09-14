import subprocess,os,json,time,glob
R='/workspace/agilab'
fs=set()
for pat in ('experiments/*.py','src/*.py','*.py'):
    fs|=set(glob.glob(os.path.join(R,pat)))
fs=sorted(fs)
log=os.path.join(R,'_RUNLOG.jsonl'); open(log,'w').close()
for f in fs:
    d,b=os.path.dirname(f),os.path.basename(f); t0=time.time()
    try:
        p=subprocess.run(['python3',b],cwd=d,capture_output=True,timeout=2,text=True,errors='replace')
        code,out=p.returncode,(p.stdout or '')+(p.stderr or '')
    except subprocess.TimeoutExpired as e:
        code,out=-9,(e.stdout or '')+(e.stderr or '')
        if isinstance(out,bytes): out=out.decode('utf-8','replace')
    ls=[l.strip() for l in out.splitlines() if l.strip()]
    with open(log,'a') as L:
        L.write(json.dumps({'f':f.replace(R+'/',''),'code':code,'n':len(ls),
            'dur':round(time.time()-t0,2),'last':ls[-2:]},ensure_ascii=False)+'\n')
