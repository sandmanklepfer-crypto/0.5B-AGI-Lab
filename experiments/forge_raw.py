#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forge_raw.py — 原文直喂（零加工）
   原则: 只做「清洗空白」, 一字不改; 不造答案, 不问句, 不总结
   格式: 连续文档流, 用特殊标记分隔 (模型学的是"语言本身")
   这一步才是对的: 预训练就是这个做法 —— 喂原文
"""
import json, os, re

POOL="/workspace/pool.jsonl"
OUT="/workspace/raw_corpus.txt"
MAN="/workspace/raw_manifest.jsonl"

def load():
    rows=[]
    for l in open(POOL,encoding="utf-8"):
        try: rows.append(json.loads(l))
        except Exception: pass
    return rows

def minimal_clean(t):
    """只做最小清洗: 去HTML标签 + 折叠空白. 不改内容、不删句子"""
    if not t: return ""
    t=re.sub(r"<[^>]+>"," ",t)          # 去HTML标签
    t=t.replace("&quot;",'"').replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&#39;","'")
    t=re.sub(r"[ \t\x0b\f\r]+"," ",t)   # 折叠空白
    t=re.sub(r"\n{3,}","\n\n",t)        # 折叠空行
    return t.strip()

def build():
    rows=load()
    docs=[]; man=[]
    seen=set()
    for it in rows:
        src=it.get("src"); nm=(it.get("name") or "").strip()
        tx=minimal_clean(it.get("text") or "")
        if len(tx) < 100:            # 太短的丢弃(不是加工, 是去噪)
            continue
        key=tx[:120]
        if key in seen: continue
        seen.add(key)
        # 文档 = 标题 + 正文 (原样, 只加标题分隔)
        head = nm if nm and nm not in tx[:80] else ""
        doc = (head + "\n" if head else "") + tx
        docs.append(doc)
        man.append({"src":src,"len":len(doc),"title":nm[:80],"score":it.get("score",0),
                    "url":it.get("url","")})
    # 拼接: 文档间用分隔符
    SEP = "\n\n<|doc|>\n\n"
    corpus = SEP.join(docs)
    with open(OUT,"w",encoding="utf-8") as f:
        f.write(corpus)
    with open(MAN,"w",encoding="utf-8") as f:
        for m in man: f.write(json.dumps(m,ensure_ascii=False)+"\n")
    return docs, man, corpus

if __name__=="__main__":
    docs, man, corpus = build()
    print("="*60)
    print("  原文直喂（零加工）")
    print("="*60)
    print("  文档数   : %d"%len(docs))
    print("  总字符   : %s"%f"{len(corpus):,}")
    print("  估算token: ~%s"%f"{len(corpus)//2:,}", "(中文约2字符/token, 英文约4)")
    print("  输出     : %s"%OUT)
    import collections
    c=collections.Counter(m["src"] for m in man)
    print("  来源分布 :", dict(c))
    print()
    # 展示原文(证明没加工)
    print("── 原文样例(未改动) ──")
    for d in docs[:2]:
        print(d[:300].replace("\n"," ⏎ "))
        print("---")
