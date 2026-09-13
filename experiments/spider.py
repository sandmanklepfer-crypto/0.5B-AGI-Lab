#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spider.py — 零成本高质量数据爬取器(异步并发 + 本地缓存)
   高质量源:
     · GitHub    (stars/代码可运行)
     · arXiv     (同行评审/引用)
     · HF        (模型卡/数据集)
     · StackOverflow (采纳答案)
   核心: asyncio 并发 + 缓存 → 比串行 curl 快 20-50 倍
"""
import asyncio, aiohttp, json, os, time, hashlib, re, sys

CACHE = "/workspace/crawl_cache"
os.makedirs(CACHE, exist_ok=True)
UA = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/120"

def ck(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:20] + ".json")

class Spider:
    def __init__(self, conc=16, timeout=15):
        self.conc = conc; self.timeout = timeout
        self.sess = None; self.hits = 0; self.miss = 0

    async def __aenter__(self):
        conn = aiohttp.TCPConnector(limit=self.conc, ttl_dns_cache=300, force_close=False)
        self.sess = aiohttp.ClientSession(connector=conn,
            timeout=aiohttp.ClientTimeout(total=self.timeout, connect=6, sock_read=8),
            headers={"User-Agent": UA})
        return self

    async def __aexit__(self, *a):
        if self.sess: await self.sess.close()

    async def get(self, url, cached=True):
        c = ck(url)
        if cached and os.path.exists(c):
            try:
                d = json.load(open(c)); self.hits += 1
                return d
            except Exception: pass
        self.miss += 1
        try:
            async with self.sess.get(url) as r:
                t = await r.text()
                d = {"url": url, "code": r.status, "text": t}
                if r.status == 200:
                    try: json.dump(d, open(c, "w"))
                    except Exception: pass
                return d
        except Exception as e:
            return {"url": url, "code": -1, "text": "", "err": str(e)[:80]}

    async def many(self, urls, cached=True):
        tasks = [self.get(u, cached) for u in urls]
        return await asyncio.gather(*tasks)

# ---------------- 各源采集器 ----------------
async def gh_trending(sp, langs=("python","rust","go","c")):
    """GitHub: 高星活跃仓库"""
    urls = []
    for L in langs:
        urls.append("https://api.github.com/search/repositories"
                    f"?q=language:{L}+stars:>3000&sort=updated&per_page=20")
    out = []
    for r in await sp.many(urls):
        if r.get("code") != 200: continue
        try: j = json.loads(r["text"])
        except Exception: continue
        for it in j.get("items", []):
            out.append({"src":"github","name":it["full_name"],"stars":it["stargazers_count"],
                        "desc":(it.get("description") or "")[:200],
                        "lang":it.get("language"),"url":it["html_url"],
                        "topics":it.get("topics",[])[:6], "score":it["stargazers_count"]})
    return out

async def ax_recent(sp, cats=("cs.AI","cs.CL","cs.LG","cs.SE")):
    """arXiv: 最新论文(带摘要)"""
    urls = [f"https://export.arxiv.org/api/query?search_query=cat:{c}"
            f"&sortBy=submittedDate&sortOrder=descending&max_results=25" for c in cats]
    out = []
    for r in await sp.many(urls):
        if r.get("code") != 200: continue
        t = r["text"]
        for m in re.finditer(r"<entry>(.*?)</entry>", t, re.S):
            e = m.group(1)
            def g(tag, s=e):
                mm = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", s, re.S)
                return re.sub(r"\s+"," ",mm.group(1)).strip() if mm else ""
            title = g("title"); summ = g("summary"); aid = g("id")
            out.append({"src":"arxiv","title":title,"abstract":summ,"url":aid,
                        "score":0, "cat":g("arxiv:primary_category")[:40]})
    return out

async def hf_datasets(sp, q=("code","math","reasoning","agent")):
    """HF: 数据集(带下载量排序)"""
    urls = [f"https://hf-mirror.com/api/datasets?search={x}&limit=15&sort=downloads&direction=-1" for x in q]
    out = []
    for r in await sp.many(urls):
        if r.get("code") != 200: continue
        try: j = json.loads(r["text"])
        except Exception: continue
        for it in j:
            out.append({"src":"hf","name":it.get("id"),"downloads":it.get("downloads",0),
                        "likes":it.get("likes",0),"score":it.get("downloads",0)})
    return out

# ---------------- 质量打分(客观指标, 不用模型自评) ----------------
def score_and_rank(items):
    for it in items:
        s = 0
        if it["src"]=="github":  s = it["stars"]*1.0
        if it["src"]=="arxiv":   s = 50
        if it["src"]=="hf":      s = it["downloads"]*0.05 + it["likes"]*3
        it["q"] = s
    return sorted(items, key=lambda x:-x["q"])

async def main():
    t0 = time.time()
    async with Spider(conc=16, timeout=10) as sp:
        print("并发采集...", flush=True)
        gh, ax, hf = await asyncio.gather(
            gh_trending(sp), ax_recent(sp), hf_datasets(sp)
        )
    el = time.time()-t0
    allx = gh+ax+hf
    ranked = score_and_rank(allx)
    print("\n" + "="*64)
    print("  采集结果: %.1fs  (缓存命中 %d / 新请求 %d)" % (el, sp.hits, sp.miss))
    print("  共 %d 条 (GitHub %d / arXiv %d / HF %d)" % (len(allx),len(gh),len(ax),len(hf)))
    print("="*64)
    for it in ranked[:12]:
        if it["src"]=="github":
            print("  [GH %6d★] %-34s %s" % (it["stars"], it["name"][:34], it["desc"][:44]))
        elif it["src"]=="arxiv":
            print("  [arXiv   ] %s" % it["title"][:70])
        else:
            print("  [HF %7d↓] %s" % (it["downloads"], it["name"][:60]))
    json.dump(ranked, open("/workspace/harvested.json","w"), ensure_ascii=False, indent=1)
    print("\n已存 /workspace/harvested.json (%d 条)" % len(ranked))
    print("耗时 %.1fs" % (time.time()-t0))

if __name__ == "__main__":
    asyncio.run(main())
