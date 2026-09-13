#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""forge.py — 自主进化飞轮（零成本）
   ① 扩源并发爬取: GitHub / arXiv / HF / StackOverflow / HackerNews
   ② 客观打分: star / 引用 / 采纳 / 下载（外部裁判，防熵减）
   ③ 转换器: 原始内容 → 指令训练数据 (问题, 答案)
   ④ 循环: 可定时反复跑，数据池持续增长
用法:
  python3 forge.py once              # 跑一轮
  python3 forge.py loop 30           # 每30分钟一轮，持续
  python3 forge.py build             # 从池子里生成训练集
"""
import asyncio, aiohttp, json, os, time, hashlib, re, sys, random

CACHE = "/workspace/crawl_cache"; os.makedirs(CACHE, exist_ok=True)
POOL  = "/workspace/pool.jsonl"        # 原始数据池(去重累积)
TRAIN = "/workspace/forge_train.jsonl" # 转换后的训练数据
UA = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/120"

def ck(u): return os.path.join(CACHE, hashlib.sha1(u.encode()).hexdigest()[:20]+".json")

class Spider:
    def __init__(self, conc=24, timeout=10):
        self.conc=conc; self.timeout=timeout; self.hits=0; self.miss=0; self.sess=None
    async def __aenter__(self):
        c=aiohttp.TCPConnector(limit=self.conc, ttl_dns_cache=600)
        self.sess=aiohttp.ClientSession(connector=c,
            timeout=aiohttp.ClientTimeout(total=self.timeout, connect=6, sock_read=8),
            headers={"User-Agent":UA})
        return self
    async def __aexit__(self,*a):
        if self.sess: await self.sess.close()
    async def get(self,url,cached=True):
        c=ck(url)
        if cached and os.path.exists(c):
            try: self.hits+=1; return json.load(open(c))
            except Exception: pass
        self.miss+=1
        try:
            async with self.sess.get(url) as r:
                t=await r.text()
                d={"url":url,"code":r.status,"text":t}
                if r.status==200:
                    try: json.dump(d,open(c,"w"))
                    except Exception: pass
                return d
        except Exception as e:
            return {"url":url,"code":-1,"text":"","err":str(e)[:60]}
    async def many(self,urls,cached=True):
        return await asyncio.gather(*[self.get(u,cached) for u in urls])

# ============ 采集器 ============
async def src_github(sp):
    langs=("python","rust","go","c","cpp","typescript","java")
    urls=[f"https://api.github.com/search/repositories?q=language:{L}+stars:>2000&sort=updated&per_page=20" for L in langs]
    out=[]
    for r in await sp.many(urls):
        if r.get("code")!=200: continue
        try: j=json.loads(r["text"])
        except Exception: continue
        for it in j.get("items",[]):
            out.append({"src":"github","id":it["full_name"],"name":it["full_name"],
                "text":(it.get("description") or "")+" | topics:"+",".join(it.get("topics",[])[:5]),
                "score":it["stargazers_count"],"lang":it.get("language"),
                "url":it["html_url"],"ts":time.time()})
    return out

async def src_arxiv(sp):
    cats=("cs.AI","cs.CL","cs.LG","cs.SE","cs.PL","math.NA","stat.ML")
    urls=[f"https://export.arxiv.org/api/query?search_query=cat:{c}&sortBy=submittedDate&sortOrder=descending&max_results=20" for c in cats]
    out=[]
    for r in await sp.many(urls):
        if r.get("code")!=200: continue
        for m in re.finditer(r"<entry>(.*?)</entry>", r["text"], re.S):
            e=m.group(1)
            def g(tag,s=e):
                mm=re.search(rf"<{tag}[^>]*>(.*?)</{tag}>",s,re.S)
                return re.sub(r"\s+"," ",mm.group(1)).strip() if mm else ""
            out.append({"src":"arxiv","id":g("id"),"name":g("title"),
                "text":g("summary"),"score":80,"cat":g("arxiv:primary_category")[:40],
                "url":g("id"),"ts":time.time()})
    return out

async def src_hf(sp):
    qs=("code","math","reasoning","agent","instruction","chat","sql","tool")
    urls=[f"https://hf-mirror.com/api/datasets?search={q}&limit=12&sort=downloads&direction=-1" for q in qs]
    out=[]
    for u in urls:                       # 串行, 避免 hf-mirror 限流
        r = await sp.get(u)
        if r.get("code")!=200: continue
        try: j=json.loads(r["text"])
        except Exception: continue
        for it in j:
            out.append({"src":"hf","id":it.get("id"),"name":it.get("id"),
                "text":(it.get("description") or "")[:300],
                "score":it.get("downloads",0)*0.05+it.get("likes",0)*3,
                "url":"https://hf-mirror.com/datasets/"+str(it.get("id")),"ts":time.time()})
    return out

async def src_so(sp):
    """StackOverflow: 高票被采纳答案(真人验证)"""
    tags=("python","javascript","rust","algorithm","machine-learning","pytorch")
    urls=[f"https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged={t}&site=stackoverflow&filter=withbody&pagesize=10" for t in tags]
    out=[]
    for r in await sp.many(urls):
        if r.get("code")!=200: continue
        try: j=json.loads(r["text"])
        except Exception: continue
        for it in j.get("items",[]):
            body=re.sub(r"<[^>]+>"," ",it.get("body",""))[:600]
            out.append({"src":"stackoverflow","id":str(it.get("question_id")),
                "name":it.get("title"),"text":re.sub(r"\s+"," ",body),
                "score":it.get("score",0)*2+(200 if it.get("is_answered") else 0),
                "url":it.get("link"),"ts":time.time()})
    return out

async def src_hn(sp):
    """HackerNews: 高分讨论(技术社区认可)"""
    urls=["https://hacker-news.firebaseio.com/v0/topstories.json"]
    out=[]
    for r in await sp.many(urls):
        if r.get("code")!=200: continue
        try: ids=json.loads(r["text"])[:25]
        except Exception: continue
        iu=[f"https://hacker-news.firebaseio.com/v0/item/{i}.json" for i in ids]
        for r2 in await sp.many(iu):
            if r2.get("code")!=200: continue
            try: it=json.loads(r2["text"])
            except Exception: continue
            if not it or it.get("type")!="story": continue
            out.append({"src":"hackernews","id":str(it.get("id")),"name":it.get("title",""),
                "text":it.get("title",""),"score":it.get("score",0)*1.5,
                "url":it.get("url") or "https://news.ycombinator.com/item?id="+str(it.get("id")),
                "ts":time.time()})
    return out

# ============ 池子(去重累积) ============
def load_pool():
    seen=set(); n=0
    if os.path.exists(POOL):
        for ln in open(POOL,encoding="utf-8"):
            try:
                d=json.loads(ln); seen.add(d["src"]+":"+d["id"]); n+=1
            except Exception: pass
    return seen,n

def save_pool(items, seen):
    new=0
    with open(POOL,"a",encoding="utf-8") as f:
        for it in items:
            k=it["src"]+":"+it["id"]
            if k in seen: continue
            seen.add(k); f.write(json.dumps(it,ensure_ascii=False)+"\n"); new+=1
    return new

# ============ 转换器: 原始 → 指令训练数据 ============
def build_train():
    """论文摘要 → 问答对;  代码/讨论 → 指令对"""
    rows=[]
    if not os.path.exists(POOL): return rows
    pool=[json.loads(l) for l in open(POOL,encoding="utf-8")]
    for it in pool:
        t=(it.get("text") or "").strip()
        nm=(it.get("name") or "").strip()
        if len(t) < 60: continue
        if it["src"]=="arxiv":
            rows.append({"task":"summarize",
                "q":"请用中文简要总结这篇论文的核心贡献：\n"+t[:1200],
                "a":nm+"。该工作针对上述问题提出方法并给出结论。"})
            rows.append({"task":"qa",
                "q":"论文《%s》讲了什么？"%nm[:60], "a":t[:500]})
        elif it["src"]=="github":
            rows.append({"task":"describe",
                "q":"项目 %s 是做什么的？"%nm, "a":t[:400]})
            rows.append({"task":"code_hint",
                "q":"我想用 %s 实现类似 %s 的功能，应该怎么做？"%(it.get("lang") or "代码", nm),
                "a":"可参考 %s（%d stars）：%s"%(nm,it.get("score",0),t[:300])})
        elif it["src"]=="stackoverflow":
            rows.append({"task":"solve",
                "q":nm[:200], "a":t[:800]})
        elif it["src"]=="hackernews":
            rows.append({"task":"topic","q":"介绍一下：%s"%nm[:80],"a":t[:200]})
        else:
            rows.append({"task":"know","q":"什么是 %s？"%nm[:60] if nm else "介绍下文","a":t[:400]})
    with open(TRAIN,"w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    return rows

# ============ 主流程 ============
async def one_round(round_no=1, verbose=True):
    t0=time.time()
    async with Spider(conc=24, timeout=10) as sp:
        res = await asyncio.gather(
            src_github(sp), src_arxiv(sp), src_hf(sp), src_so(sp), src_hn(sp),
            return_exceptions=True)
    items=[]
    names=["github","arxiv","hf","stackoverflow","hackernews"]
    counts={}
    for n,r in zip(names,res):
        if isinstance(r,Exception): counts[n]="ERR"; continue
        counts[n]=len(r); items+=r
    seen,total=load_pool()
    new=save_pool(items,seen)
    el=time.time()-t0
    if verbose:
        print("[轮次%d] %.1fs  采集%d  新增%d  池子共%d  缓存%d/新%d"%(
            round_no, el, len(items), new, total+new, sp.hits, sp.miss), flush=True)
        print("        "+"  ".join("%s:%s"%(k,v) for k,v in counts.items()), flush=True)
    return new

async def loop(minutes=30):
    r=0
    while True:
        r+=1
        try: await one_round(r)
        except Exception as e: print("轮次%d 出错: %s"%(r,e), flush=True)
        # 每轮顺手重建训练集
        try:
            n=len(build_train()); print("        训练集: %d 条"%n, flush=True)
        except Exception: pass
        time.sleep(minutes*60) if hasattr(time,'sleep') else None

if __name__=="__main__":
    cmd = sys.argv[1] if len(sys.argv)>1 else "once"
    if cmd=="once":
        asyncio.run(one_round(1))
        n=len(build_train()); print("训练集: %d 条 → %s"%(n,TRAIN))
    elif cmd=="loop":
        mins=int(sys.argv[2]) if len(sys.argv)>2 else 30
        try: asyncio.run(loop(mins))
        except KeyboardInterrupt: print("停止")
    elif cmd=="build":
        n=len(build_train()); print("训练集: %d 条 → %s"%(n,TRAIN))
    else: print(__doc__)
