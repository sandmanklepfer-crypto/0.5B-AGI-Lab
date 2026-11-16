#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨境货盘 SaaS 后端 —— 零依赖 Python + SQLite 真多租户"""
import os, json, time, sqlite3, hmac, hashlib, secrets, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
DB   = os.environ.get("SDS_DB", os.path.join(ROOT, "data", "sds.db"))
SEC  = os.environ.get("SDS_SECRET", "sds-2026-secret-key")
PORT = int(os.environ.get("PORT", "8081"))

DDL = """
CREATE TABLE IF NOT EXISTS tenants(id TEXT PRIMARY KEY,name TEXT,plan TEXT,created_at INT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT,username TEXT,
  pw_hash TEXT,role TEXT,created_at INT,UNIQUE(tenant_id,username));
CREATE TABLE IF NOT EXISTS products(tenant_id TEXT,sku TEXT,name TEXT,img TEXT,cat TEXT,supplier TEXT,
  cost REAL,price REAL,retail REAL,stock INT,moq INT,t1 INT,t2 INT,p1 REAL,p2 REAL,
  status TEXT,created_at INT,PRIMARY KEY(tenant_id,sku));
CREATE TABLE IF NOT EXISTS orders(no TEXT PRIMARY KEY,tenant_id TEXT,buyer TEXT,phone TEXT,addr TEXT,
  amount REAL,profit REAL,status TEXT,remark TEXT,created_at INT);
CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_no TEXT,
  tenant_id TEXT,sku TEXT,name TEXT,price REAL,qty INT);
CREATE TABLE IF NOT EXISTS suppliers(tenant_id TEXT,sid TEXT,name TEXT,region TEXT,settle TEXT,
  status TEXT,created_at INT,PRIMARY KEY(tenant_id,sid));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,tenant_id TEXT,actor TEXT,
  action TEXT,target TEXT,ip TEXT,at INT);
"""

def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(DDL)
    return c

def hh(s): return hashlib.sha256((SEC+":"+str(s)).encode()).hexdigest()

def mk(uid,tid,role):
    exp=int(time.time())+86400
    b="%s|%s|%s|%d"%(uid,tid,role,exp)
    return b+"|"+hmac.new(SEC.encode(),b.encode(),hashlib.sha256).hexdigest()[:32]

def ck(t):
    try:
        u,tid,r,e,sg=t.split("|")
        b="%s|%s|%s|%s"%(u,tid,r,e)
        w=hmac.new(SEC.encode(),b.encode(),hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sg,w) or int(e)<time.time(): return None
        return {"uid":u,"tid":tid,"role":r}
    except Exception: return None

def seed():
    c=db()
    if c.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]: c.close(); return
    n=int(time.time())
    c.execute("INSERT INTO tenants VALUES(?,?,?,?)",("t1","深圳华强北电子","pro",n))
    c.execute("INSERT INTO users(tenant_id,username,pw_hash,role,created_at) VALUES(?,?,?,?,?)",
              ("t1","admin",hh("admin123"),"owner",n))
    for sid,nm,rg in [("s1","深圳华强北电子","广东 深圳"),("s2","东莞制造","广东 东莞"),
                      ("s3","义乌小商品","浙江 义乌"),("s4","广州天河数码","广东 广州")]:
        c.execute("INSERT INTO suppliers VALUES(?,?,?,?,?,?,?)",("t1",sid,nm,rg,"月结30天","ok",n))
    P=[("SKU-TWS-001","蓝牙耳机 TWS-Pro 降噪版","earphone","数码配件","s1",128,299,299,2480,10,50,200,118,108),
       ("SKU-PWB-002","充电宝 20000mAh 双向快充","powerbank","数码配件","s2",99,189,219,1860,20,50,200,89,82),
       ("SKU-STD-003","手机支架 磁吸折叠款","stand","数码配件","s1",18.5,39.9,49.9,48,50,100,500,15,13),
       ("SKU-CBL-004","数据线 三合一 快充编织","cable","数码配件","s3",12,25.9,35.9,0,100,500,2000,9.5,8.5),
       ("SKU-CAR-005","车载充电器 66W 双口","car","数码配件","s2",45,89,109,920,30,100,500,39,35),
       ("SKU-MSE-006","无线鼠标 静音办公","mouse","数码配件","s1",38,79,99,640,20,50,200,33,29),
       ("SKU-SPK-007","蓝牙音箱 便携防水","speaker","数码配件","s3",76,159,199,380,15,50,200,68,62),
       ("SKU-HUB-008","USB集线器 4口 3.0","hub","数码配件","s4",22,49,69,1240,50,100,500,18,16)]
    for p in P:
        c.execute("INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("t1",)+p+("on",n))
    c.commit(); c.close()
    print("[seed] 已初始化演示数据")

def alog(c,tid,actor,action,target,ip):
    c.execute("INSERT INTO audit(tenant_id,actor,action,target,ip,at) VALUES(?,?,?,?,?,?)",
              (tid,actor,action,target,ip,int(time.time())))

class H(BaseHTTPRequestHandler):
    server_version="SDS/1.0"
    def log_message(self,*a): pass
    def ip(self):
        return (self.headers.get("X-Forwarded-For","").split(",")[0].strip()
                or self.client_address[0])
    def out(self,code,obj,ct="application/json; charset=utf-8"):
        b=json.dumps(obj,ensure_ascii=False).encode() if isinstance(obj,(dict,list)) else (
           obj.encode() if isinstance(obj,str) else obj)
        self.send_response(code)
        self.send_header("Content-Type",ct)
        self.send_header("Content-Length",str(len(b)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers()
        try: self.wfile.write(b)
        except Exception: pass
    def do_OPTIONS(self): self.out(204,b"")
    def auth(self):
        t=self.headers.get("Authorization","").replace("Bearer ","").strip()
        return ck(t) if t else None

    def do_GET(self):
        u=urlparse(self.path); p=u.path; q=parse_qs(u.query)

        if p.startswith("/api/"):
            if p=="/api/health":
                return self.out(200,{"ok":True,"ver":"1.0","ts":int(time.time())})
            a=self.auth()
            if p=="/api/products":
                if not a: return self.out(401,{"ok":False,"error":"未登录"})
                c=db()
                rows=c.execute("SELECT * FROM products WHERE tenant_id=? ORDER BY created_at DESC",
                               (a["tid"],)).fetchall()
                c.close()
                return self.out(200,{"ok":True,"products":[dict(r) for r in rows]})
            if p=="/api/orders":
                if not a: return self.out(401,{"ok":False,"error":"未登录"})
                c=db()
                rows=c.execute("SELECT * FROM orders WHERE tenant_id=? ORDER BY created_at DESC LIMIT 100",
                               (a["tid"],)).fetchall()
                c.close()
                return self.out(200,{"ok":True,"orders":[dict(r) for r in rows]})
            if p=="/api/stats":
                if not a: return self.out(401,{"ok":False,"error":"未登录"})
                c=db()
                g=lambda s: c.execute(s,(a["tid"],)).fetchone()[0]
                d={"products":g("SELECT COUNT(*) FROM products WHERE tenant_id=?"),
                   "orders":g("SELECT COUNT(*) FROM orders WHERE tenant_id=?"),
                   "gmv":g("SELECT COALESCE(SUM(amount),0) FROM orders WHERE tenant_id=?"),
                   "profit":g("SELECT COALESCE(SUM(profit),0) FROM orders WHERE tenant_id=?"),
                   "suppliers":g("SELECT COUNT(*) FROM suppliers WHERE tenant_id=?")}
                c.close()
                return self.out(200,{"ok":True,"stats":d})
            if p=="/api/suppliers":
                if not a: return self.out(401,{"ok":False,"error":"未登录"})
                c=db()
                rows=c.execute("SELECT * FROM suppliers WHERE tenant_id=?",(a["tid"],)).fetchall()
                c.close()
                return self.out(200,{"ok":True,"suppliers":[dict(r) for r in rows]})
            if p=="/api/audit":
                if not a: return self.out(401,{"ok":False,"error":"未登录"})
                c=db()
                rows=c.execute("SELECT * FROM audit WHERE tenant_id=? ORDER BY at DESC LIMIT 100",
                               (a["tid"],)).fetchall()
                c.close()
                return self.out(200,{"ok":True,"audit":[dict(r) for r in rows]})
            return self.out(404,{"ok":False,"error":"接口不存在"})

        # 静态
        if p=="/" or p=="": p="/login.html"
        fp=os.path.normpath(os.path.join(ROOT,p.lstrip("/")))
        if not fp.startswith(ROOT): return self.out(403,{"ok":False,"error":"forbidden"})
        if not os.path.isfile(fp): return self.out(404,"<h1>404</h1>","text/html; charset=utf-8")
        ct=mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if ct.startswith("text/") or "javascript" in ct: ct+="; charset=utf-8"
        try:
            with open(fp,"rb") as f: d=f.read()
            self.out(200,d,ct)
        except Exception: self.out(500,{"ok":False})

    def do_POST(self):
        u=urlparse(self.path); p=u.path
        n=int(self.headers.get("Content-Length") or 0)
        if n>65536: return self.out(413,{"ok":False,"error":"过大"})
        try: d=json.loads((self.rfile.read(n) if n else b"{}").decode() or "{}")
        except Exception: return self.out(400,{"ok":False,"error":"格式错误"})
        if not isinstance(d,dict): return self.out(400,{"ok":False,"error":"格式错误"})

        if p=="/api/login":
            un=str(d.get("username","")).strip()[:64]
            pw=str(d.get("password",""))[:128]
            if not un or not pw: return self.out(400,{"ok":False,"error":"请输入账号密码"})
            c=db()
            r=c.execute("SELECT * FROM users WHERE username=?",(un,)).fetchone()
            if not r or not hmac.compare_digest(r["pw_hash"],hh(pw)):
                alog(c,None,un,"login_fail","",self.ip()); c.commit(); c.close()
                return self.out(401,{"ok":False,"error":"账号或密码错误"})
            alog(c,r["tenant_id"],un,"login_ok","",self.ip()); c.commit(); c.close()
            return self.out(200,{"ok":True,"token":mk(r["id"],r["tenant_id"],r["role"]),
                                 "user":{"username":r["username"],"role":r["role"],
                                         "tenant":r["tenant_id"]}})

        a=self.auth()
        if not a: return self.out(401,{"ok":False,"error":"未登录"})

        if p=="/api/order":
            tid=a["tid"]; items=d.get("items") or []
            if not items: return self.out(400,{"ok":False,"error":"购物车为空"})
            c=db(); amt=0.0; prof=0.0; lines=[]
            for it in items:
                sku=str(it.get("sku",""))[:40]
                qty=int(it.get("qty") or 0)
                if qty<=0: continue
                pr=c.execute("SELECT * FROM products WHERE tenant_id=? AND sku=?",(tid,sku)).fetchone()
                if not pr: continue
                if pr["stock"]<qty: c.close(); return self.out(400,{"ok":False,"error":"库存不足: "+sku})
                amt+=pr["price"]*qty; prof+=(pr["price"]-pr["cost"])*qty
                lines.append((sku,pr["name"],pr["price"],qty))
            if not lines: c.close(); return self.out(400,{"ok":False,"error":"无有效商品"})
            # 原子扣减防超卖
            for sku,nm,pr_,qty in lines:
                cur=c.execute("UPDATE products SET stock=stock-? WHERE tenant_id=? AND sku=? AND stock>=?",
                              (qty,tid,sku,qty))
                if cur.rowcount!=1: c.rollback(); c.close()
                return self.out(400,{"ok":False,"error":"库存不足: "+sku})
            no="GS"+time.strftime("%y%m%d%H%M%S")+secrets.token_hex(2).upper()
            c.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (no,tid,str(d.get("buyer",""))[:40],str(d.get("phone",""))[:20],
                       str(d.get("addr",""))[:200],round(amt,2),round(prof,2),"pending",
                       str(d.get("remark",""))[:200],int(time.time())))
            for sku,nm,pr_,qty in lines:
                c.execute("INSERT INTO order_items(order_no,tenant_id,sku,name,price,qty) VALUES(?,?,?,?,?,?)",
                          (no,tid,sku,nm,pr_,qty))
            alog(c,tid,a["uid"],"create_order",no,self.ip()); c.commit(); c.close()
            return self.out(200,{"ok":True,"order_no":no,"amount":round(amt,2)})

        if p=="/api/product":
            tid=a["tid"]; sku=str(d.get("sku",""))[:40]
            if not sku: return self.out(400,{"ok":False,"error":"缺 sku"})
            c=db()
            c.execute("""INSERT INTO products(tenant_id,sku,name,img,cat,supplier,cost,price,retail,
                        stock,moq,t1,t2,p1,p2,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(tenant_id,sku) DO UPDATE SET name=excluded.name,price=excluded.price,
                        retail=excluded.retail,stock=excluded.stock,cost=excluded.cost""",
                      (tid,sku,str(d.get("name",""))[:100],str(d.get("img",""))[:60],
                       str(d.get("cat",""))[:30],str(d.get("supplier",""))[:30],
                       float(d.get("cost") or 0),float(d.get("price") or 0),
                       float(d.get("retail") or 0),int(d.get("stock") or 0),
                       int(d.get("moq") or 10),int(d.get("t1") or 50),int(d.get("t2") or 200),
                       float(d.get("p1") or 0),float(d.get("p2") or 0),"on",int(time.time())))
            alog(c,tid,a["uid"],"save_product",sku,self.ip()); c.commit(); c.close()
            return self.out(200,{"ok":True,"sku":sku})

        if p=="/api/order_status":
            tid=a["tid"]; no=str(d.get("order_no",""))[:40]; st=str(d.get("status",""))[:20]
            if st not in ("pending","paid","delivering","done","cancelled"):
                return self.out(400,{"ok":False,"error":"状态非法"})
            c=db()
            cur=c.execute("UPDATE orders SET status=? WHERE tenant_id=? AND no=?",(st,tid,no))
            ok=cur.rowcount==1
            if ok: alog(c,tid,a["uid"],"order_status",no,self.ip())
            c.commit(); c.close()
            return self.out(200,{"ok":ok})

        return self.out(404,{"ok":False,"error":"接口不存在"})

def main():
    seed()
    print("SDS 后端启动 http://0.0.0.0:%d"%PORT,flush=True)
    srv=ThreadingHTTPServer(("0.0.0.0",PORT),H)
    srv.daemon_threads=True
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__=="__main__": main()
