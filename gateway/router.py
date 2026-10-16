#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
router.py —— AI 入口的「渡口」：一句话 → 送去该去的地方

架构：
   用户 → [AI 入口页] → 本服务(意图分诊) → 目的地(店铺/服务/工具)
核心铁律：
   1) **目的地只能来自白名单注册表 destinations.json**，AI 不许自己编 URL
      （否则就是开放重定向漏洞 / AI幻觉乱跳）
   2) 拿不准 → 反问澄清，不硬猜
   3) 一次最多给 3 个去处，按相关性排序

用法：
  python3 router.py --serve                 # 起 API（给入口页用）
  python3 router.py --ask "我想喝奶茶"       # 命令行测
  python3 router.py --ask "..." --mock      # 离线测
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REG = os.path.join(HERE, "destinations.json")

# ---------------------------------------------------------------- 目的地注册表
# 只允许跳到这些地方；加新去处 = 往这里加一条
DEFAULT_DESTS = [
    {"slug": "yikoucha", "name": "一口茶（奶茶）", "url": "s/yikoucha/",
     "keywords": ["奶茶", "喝的", "茶", "珍珠", "饮品", "饮料", "下午茶"]},
    {"slug": "fruit3", "name": "宿舍楼下水果", "url": "s/fruit3/",
     "keywords": ["水果", "切果", "果盒", "苹果", "西瓜", "削"]},
    {"slug": "game", "name": "天泪纪元（游戏）", "url": "tianlei3d/index.html",
     "keywords": ["游戏", "玩", "打游戏", "娱乐", "天泪", "上线"]},
    {"slug": "join", "name": "免费开店（商家入驻）", "url": "join.html",
     "keywords": ["开店", "入驻", "卖东西", "做个店", "下单页", "商家", "我要卖"]},
    {"slug": "orders", "name": "我的订单", "url": "orders.html",
     "keywords": ["订单", "我买的", "查订单", "买的东西", "物流", "发货"]},
    {"slug": "chat", "name": "联系商家 / 客服", "url": "index.html",
     "keywords": ["客服", "联系", "咨询", "投诉", "售后", "退"]},
]

def load_dests():
    if os.path.exists(REG):
        return json.load(open(REG, encoding="utf-8"))
    json.dump(DEFAULT_DESTS, open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return DEFAULT_DESTS

# ---------------------------------------------------------------- 规则快通道（不依赖 LLM）
def keyword_route(text, dests):
    hits = []
    for d in dests:
        score = sum(1 for k in d["keywords"] if k in text)
        if score: hits.append((score, d))
    hits.sort(key=lambda x: -x[0])
    return [d for _, d in hits[:3]]

# ---------------------------------------------------------------- LLM 分诊
def llm_route(llm, text, dests):
    menu = "\n".join(f"- {d['slug']}｜{d['name']}｜能帮你：{', '.join(d['keywords'][:6])}" for d in dests)
    SYS = ("你是「渡口」——把用户的一句话，送到该去的地方。"
           "只能从下面这菜单里选（用 slug）。最多选3个，按相关度排序。"
           "如果用户话说不清/不在菜单里，route 返回空数组，并在 reply 里礼貌反问一句。"
           "reply 要口语、简短（≤50字），像人引导。只输出 JSON："
           '{"reply":"...","route":["slug1","slug2"]}\n\n菜单：\n' + menu)
    raw = llm.chat(SYS, text, temperature=0.3)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m: return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

# ---------------------------------------------------------------- 对外：route()
def route(text, llm=None):
    dests = load_dests()
    by_slug = {d["slug"]: d for d in dests}

    # ① 规则快通道：明确命中就直接走（快、稳、免费）
    kw = keyword_route(text, dests)
    result = {"reply": "", "destinations": [], "source": "keyword"}
    if kw and llm is None:
        result["reply"] = f"给你找到这些：{kw[0]['name']}"
        result["destinations"] = [dict(slug=d["slug"], name=d["name"], url=d["url"]) for d in kw]
        return result

    # ② LLM 分诊
    if llm is not None:
        j = llm_route(llm, text, dests)
        if j is not None:
            picked = [by_slug[s] for s in j.get("route", []) if s in by_slug][:3]
            result["source"] = "llm"
            result["reply"] = j.get("reply", "") or ("给你找到这些：" + (picked[0]["name"] if picked else ""))
            result["destinations"] = [dict(slug=d["slug"], name=d["name"], url=d["url"]) for d in picked]
            if picked: return result
            # LLM 没给出 → 退回规则
    if kw:
        result["reply"] = f"给你找到这些：{kw[0]['name']}"
        result["destinations"] = [dict(slug=d["slug"], name=d["name"], url=d["url"]) for d in kw]
        result["source"] = "keyword"
    else:
        result["reply"] = "我这边能帮你：点奶茶 / 买水果 / 逛游戏 / 免费开店 / 查订单。你想干哪个？"
        result["destinations"] = []
    return result

# ---------------------------------------------------------------- LLM 客户端
class LLM:
    def __init__(self, mock=False):
        self.mock = mock
        self.base = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        keys = os.environ.get("OPENAI_API_KEYS") or os.environ.get("OPENAI_API_KEY", "")
        self.keys = [k.strip() for k in keys.split(",") if k.strip()] or [""]
        self._i = 0
    def chat(self, system, user, temperature=0.3):
        if self.mock:
            return '{"reply":"（mock）好的，带你过去～","route":["yikoucha"]}'
        import urllib.request
        body = json.dumps({"model": "deepseek-chat", "temperature": temperature,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        for att in range(3):
            key = self.keys[self._i % len(self.keys)]; self._i += 1
            req = urllib.request.Request(self.base.rstrip("/") + "/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())["choices"][0]["message"]["content"]
            except Exception:
                time.sleep(1)
        return ""

# ---------------------------------------------------------------- API
def serve(port=8100):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.parse
    llm = LLM()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _j(self, o, code=200):
            b = json.dumps(o, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_OPTIONS(self):
            self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.end_headers()
        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            if p.path == "/api/dests":
                self._j(load_dests()); return
            if p.path == "/api/route":
                q = urllib.parse.parse_qs(p.query).get("q", [""])[0]
                if not q: self._j({"reply": "你想做点什么？", "destinations": []}); return
                self._j(route(q, llm)); return
            self._j({"error": "not found"}, 404)
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if urllib.parse.urlparse(self.path).path == "/api/route":
                self._j(route(body.get("text", ""), llm)); return
            self._j({"error": "not found"}, 404)

    print(f"[渡口 API] http://127.0.0.1:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--ask")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if a.serve: serve(a.port); return
    if a.ask:
        llm = None if a.mock else LLM()
        print(json.dumps(route(a.ask, llm), ensure_ascii=False, indent=1)); return
    ap.print_help()

if __name__ == "__main__":
    main()
