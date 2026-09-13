import json,time
from collections import defaultdict
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
print("="*90)
print("修正指标: 答案的开头, 是不是问题里的原文? (只看开头, 不看比例)")
print("="*90)
rows=[]
for d in QA:
    q,a=d['q'],d['a']
    W=min(40,len(a))
    copy = a[:W] in q          # 答案开头是不是问题的原文
    rows.append((d['task'],copy))
by=defaultdict(lambda:[0,0])
for t,c in rows:
    by[t][1]+=1
    if c: by[t][0]+=1
print(f"  {'任务类型':<12}{'条数':<8}{'答案开头=问题原文':<20}{'判定'}")
print("  "+"-"*66)
for t,(ok,tot) in sorted(by.items(),key=lambda x:-x[1][0]/max(x[1][1],1)):
    tag="★ 提取型(规则可做)" if ok/tot>0.5 else "⚠️ 答案需另找"
    print(f"  {t:<12}{tot:<8}{f'{ok}/{tot} = {100*ok/tot:.0f}%':<20}{tag}")
ex=sum(1 for _,c in rows if c)
print()
print("="*90)
print("三类最终占比")
print("="*90)
print(f"  提取型 (答案开头就是问题原文)  {ex:>4} 条  {100*ex/len(rows):>5.1f}%   ✅ 纯规则")
print(f"  库内型 (答案在语料库, 靠锚点取) {len(rows)-ex:>4} 条  {100*(len(rows)-ex)/len(rows):>5.1f}%   ✅ 查库")
print()
print("★ 验证: solve 和 whatis 的答案开头在问题里吗?")
for t in ['solve','whatis','hint','topic']:
    d=[x for x in QA if x['task']==t][0]
    W=min(35,len(d['a']))
    print(f"  {t:<10} 答开头: {d['a'][:35]!r}")
    print(f"           在问题里? {d['a'][:W] in d['q']}")
print(f"用时 {time.time()-t0:.2f}s")
