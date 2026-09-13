#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forge_build.py — 转换器 v2: 【只用真值, 不造答案】
   原则: 答案必须来自原文/真人, 绝不生成套话
   产出 4 类高真值数据:
     A. 摘要还原   (论文摘要原文 = 真值)
     B. SO 问答    (真人采纳答案 = 真值)
     C. 术语释义   (维基/百科 摘要 = 真值)
     D. 代码说明   (README/描述原文 = 真值)
"""
import json, os, re, sys, urllib.request, urllib.parse, time

POOL="/workspace/pool.jsonl"
OUT="/workspace/clean_train.jsonl"

def load():
    if not os.path.exists(POOL): return []
    rows=[]
    for l in open(POOL,encoding="utf-8"):
        try: rows.append(json.loads(l))
        except Exception: pass
    return rows

# ---------- 质量过滤 ----------
def clean(t):
    if not t: return ""
    t=re.sub(r"<[^>]+>"," ",t)
    t=re.sub(r"&[a-z]+;"," ",t)
    t=re.sub(r"\s+"," ",t).strip()
    return t

def is_good_text(t, lo=80, hi=2000):
    t=clean(t)
    if len(t)<lo or len(t)>hi: return False
    # 拒绝模板句/套话特征
    bad=["该工作针对上述问题","提出方法并给出结论","详见下文","如上所述","略"]
    for b in bad:
        if b in t: return False
    # 拒绝过短句子堆砌(平均句长太短)
    sents=[s for s in re.split(r"[。.!?；;]", t) if len(s)>3]
    if sents and sum(len(s) for s in sents)/len(sents) < 8: return False
    return True

# ---------- 维基真值(术语释义) ----------
def wiki(query, lang="zh"):
    """维基百科摘要 = 权威真值"""
    try:
        u=("https://%s.wikipedia.org/api/rest_v1/page/summary/"%lang)+urllib.parse.quote(query)
        r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"Mozilla/5.0"}),timeout=10)
        d=json.loads(r.read())
        ex=d.get("extract","")
        return clean(ex) if len(ex)>40 else None
    except Exception:
        return None

# ---------- 构建 ----------
def build(use_wiki=True, wiki_max=25):
    rows=load()
    out=[]; stats={}; wiki_n=0

    def add(task,q,a):
        a=clean(a)
        if not q or not is_good_text(a, 40 if task=="terms" else 80): return False
        out.append({"task":task,"q":q.strip(),"a":a}); 
        stats[task]=stats.get(task,0)+1
        return True

    for it in rows:
        src=it.get("src"); nm=clean(it.get("name") or ""); tx=clean(it.get("text") or "")

        # A. arXiv 摘要 —— 真值就是摘要本身
        if src=="arxiv" and tx:
            add("summary", "请阅读并复述下面这篇论文的摘要要点：\n"+tx[:600], tx)
            if nm: add("title2abs", "论文《%s》的摘要是什么？"%nm[:70], tx)

        # B. StackOverflow —— 真人答案是真值
        elif src=="stackoverflow" and tx and nm:
            add("solve", nm[:200], tx)

        # C. GitHub —— 描述原文是真值
        elif src=="github" and tx and nm:
            add("whatis", "项目 %s 是做什么的？"%nm, tx)
            add("hint", "我想实现类似 %s 的功能，有什么参考？"%nm, tx)

        # D. HackerNews —— 标题即真值(信息量低, 只留少量)
        elif src=="hackernews" and nm:
            add("topic", "最近有什么技术热点？", nm+"（HackerNews 高分讨论）")

    # E. 维基百科: 从池子里抽术语, 补权威释义
    if use_wiki:
        terms=[]
        for it in rows:
            for t in [it.get("name","")]:
                for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{4,20}", t or ""):
                    terms.append(w)
        seen=set(); uniq=[]
        for t in terms:
            if t.lower() in seen: continue
            seen.add(t.lower()); uniq.append(t)
        for t in uniq[:wiki_max]:
            ex=wiki(t)
            if ex:
                add("terms", "%s 是什么？"%t, ex); wiki_n+=1

    with open(OUT,"w",encoding="utf-8") as f:
        for r in out: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    return out, stats, wiki_n

if __name__=="__main__":
    t0=time.time()
    print("从池子构建(只用真值)...", flush=True)
    rows,stats,wn = build(use_wiki=("--nowiki" not in sys.argv), wiki_max=20)
    print("\n"+"="*58)
    print("  干净数据集: %d 条  (%.0fs, 维基补了 %d 条)"%(len(rows),time.time()-t0,wn))
    print("="*58)
    for k,v in sorted(stats.items(),key=lambda x:-x[1]):
        print("   %-12s %4d 条"%(k,v))
    print()
    # 抽样展示(验证不是套话)
    import random
    random.seed(3)
    for r in random.sample(rows, min(5,len(rows))):
        print("【%s】"%r["task"])
        print("  Q:", r["q"][:88].replace("\n"," "))
        print("  A:", r["a"][:110].replace("\n"," "))
        print()
