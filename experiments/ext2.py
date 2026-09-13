import json,time
from collections import defaultdict
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
def lcsub(a,b,cap=60):
    """答案前cap个字里, 有多少是问题里的连续片段(快速: 用子串查)"""
    best=0
    for L in range(cap,3,-1):
        # 取答案开头L个字, 看是否出现在问题里
        seg=a[:L]
        if seg in b:
            return L
    # 退一步: 滑动窗口找最长
    for L in range(min(cap,len(a)),3,-1):
        for s in range(0,len(a)-L+1,3):
            if a[s:s+L] in b:
                return L
    return 0
rows=[]
for d in QA:
    L=lcsub(d['a'],d['q'])
    rows.append((d['task'],L/max(len(d['a']),1),len(d['a'])))
print("="*88)
print("修正: 答案有多少是【直接从问题里复制】的?")
print("="*88)
by=defaultdict(list)
for t,c,la in rows: by[t].append(c)
print(f"  {'任务类型':<12}{'条数':<8}{'复制占比':<14}{'判定'}")
print("  "+"-"*62)
for t,v in sorted(by.items(),key=lambda x:-sum(x[1])/len(x[1])):
    m=sum(v)/len(v)
    tag="★ 提取型(纯复制)" if m>0.5 else ("⚠️ 部分复制" if m>0.2 else "❌ 需外部")
    print(f"  {t:<12}{len(v):<8}{m:<14.3f}{tag}")
ex=sum(1 for _,c,_ in rows if c>0.5); pt=sum(1 for _,c,_ in rows if 0.2<c<=0.5); non=sum(1 for _,c,_ in rows if c<=0.2)
print()
print("="*88)
print("三类客观占比")
print("="*88)
print(f"  提取型(答案>50%来自问题原文)  {ex:>4} 条  {100*ex/len(rows):>5.1f}%  ✅ 规则/搬运可做")
print(f"  部分复制(20~50%)              {pt:>4} 条  {100*pt/len(rows):>5.1f}%  ⚠️ 要拼接")
print(f"  需外部信息(<20%)              {non:>4} 条  {100*non/len(rows):>5.1f}%  ❌ 靠库")
print()
print("="*88)
print("实例: summary 的答案在问题里的位置")
print("="*88)
n=0
for d in QA:
    if d['task']=='summary' and n<2:
        q,a=d['q'],d['a']
        p=q.find(a[:35])
        print(f"  问: {q[:50]}...")
        print(f"  答: {a[:55]}...")
        print(f"  -> 答案起点在问题第 {p} 字处  {'★ 就是复制' if p>=0 else ''}")
        print(); n+=1
print(f"用时 {time.time()-t0:.2f}s")
