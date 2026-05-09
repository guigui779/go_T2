#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Go Page — 无第三方依赖，直接运行"""
import base64
import hashlib
import hmac
import json
import os
import random
import string
import time
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "") or base64.b64encode(os.urandom(32)).decode()
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "300"))
GATE_SECRET = os.environ.get("GATE_SECRET", "") or base64.b64encode(os.urandom(32)).decode()
CHARS = string.ascii_lowercase + string.digits

# ── Token ──
def _sign(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]

def make_token(secret):
    ts = str(int(time.time()))
    raw = ts + ":" + _sign(secret, ts)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

def check_token(token, secret):
    try:
        p = 4 - len(token) % 4
        if p != 4: token += "=" * p
        raw = base64.urlsafe_b64decode(token).decode()
        ts_str, sig = raw.split(":", 1)
        return abs(time.time() - int(ts_str)) <= TOKEN_TTL and hmac.compare_digest(sig, _sign(secret, ts_str))
    except: return False

def rand_label(n): return "".join(random.choices(CHARS, k=n))

def clean_domain(raw):
    s = str(raw).strip().lower()
    for p in ("https://", "http://"):
        if s.startswith(p): s = s[len(p):]
    s = s.split("/")[0].split(":")[0]
    if s.startswith("*."): s = s[2:]
    return s.strip()

# ── DB ──
import sqlite3 as _sq
_db = None

def _db_conn():
    global _db
    if _db is None:
        path = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data.db"))
        _db = _sq.connect(path, check_same_thread=False)
        _db.row_factory = _sq.Row
        _db.executescript("""
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS domains (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, name TEXT DEFAULT '', tag TEXT DEFAULT '', status INTEGER DEFAULT 1, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS relay (id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL);
        """)
        _db.commit()
        defaults = {"siteName":"独立跳转站","probeAssets":'["/logo.png"]',"probeAssetThreshold":"2","wildcardEnabled":"true","wildcardBaseDomain":"","wildcardCandidateCount":"6","wildcardLabelLength":"8","relayLabelLength":"4","version":"1"}
        for k,v in defaults.items():
            if not _db.execute("SELECT 1 FROM config WHERE key=?",(k,)).fetchone():
                _db.execute("INSERT INTO config(key,value) VALUES(?,?)",(k,v))
        _db.commit()
    return _db

def cfg_get(k):
    r = _db_conn().execute("SELECT value FROM config WHERE key=?",(k,)).fetchone()
    return json.loads(r["value"]) if r else None

def cfg_set(k,v):
    _db_conn().execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)",(k,json.dumps(v,ensure_ascii=False)))
    _db_conn().commit()

def dom_list(sch="", tg="", st=None, ofs=0, lim=50):
    sql = "SELECT * FROM domains WHERE 1=1"
    ps = []
    if st is not None: sql += " AND status=?"; ps.append(st)
    if sch: sql += " AND (url LIKE ? OR name LIKE ? OR tag LIKE ?)"; lk = f"%{sch}%"; ps.extend([lk,lk,lk])
    if tg: sql += " AND tag=?"; ps.append(tg)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"; ps.extend([lim,ofs])
    return [dict(r) for r in _db_conn().execute(sql,ps).fetchall()]

def dom_count(sch="", tg="", st=None):
    sql = "SELECT COUNT(*) as n FROM domains WHERE 1=1"; ps = []
    if st is not None: sql += " AND status=?"; ps.append(st)
    if sch: sql += " AND (url LIKE ? OR name LIKE ? OR tag LIKE ?)"; lk=f"%{sch}%"; ps.extend([lk,lk,lk])
    if tg: sql += " AND tag=?"; ps.append(tg)
    return _db_conn().execute(sql,ps).fetchone()["n"]

def dom_add(u,n="",t=""):
    now=time.strftime("%Y-%m-%d %H:%M:%S")
    _db_conn().execute("INSERT INTO domains(url,name,tag,status,created) VALUES(?,?,?,1,?)",(u,n,t,now))
    _db_conn().commit()
    return _db_conn().execute("SELECT last_insert_rowid()").fetchone()[0]

def dom_upd(did,**kw):
    ss=[];ps=[]
    for k in ("url","name","tag","status"):
        if k in kw: ss.append(f"{k}=?"); ps.append(kw[k])
    if ss: ps.append(did); _db_conn().execute(f"UPDATE domains SET {','.join(ss)} WHERE id=?",ps); _db_conn().commit()

def dom_del(ids):
    if ids: _db_conn().execute(f"DELETE FROM domains WHERE id IN ({','.join('?'*len(ids))})",ids); _db_conn().commit()

def dom_sw(ids,st):
    if ids: _db_conn().execute(f"UPDATE domains SET status=? WHERE id IN ({','.join('?'*len(ids))})",[st]+list(ids)); _db_conn().commit()

def dom_tags():
    return [r["tag"] for r in _db_conn().execute("SELECT DISTINCT tag FROM domains WHERE tag!='' ORDER BY tag").fetchall()]

def dom_import(items):
    now=time.strftime("%Y-%m-%d %H:%M:%S")
    _db_conn().executemany("INSERT OR IGNORE INTO domains(url,name,tag,status,created) VALUES(?,?,?,1,?)",[(u,n,t,now) for u,n,t in items])
    _db_conn().commit()

def rly_list(k=""):
    if k: rows=_db_conn().execute("SELECT * FROM relay WHERE kind=? ORDER BY id",(k,)).fetchall()
    else: rows=_db_conn().execute("SELECT * FROM relay ORDER BY kind, id").fetchall()
    return [dict(r) for r in rows]

def rly_add(d,k):
    now=time.strftime("%Y-%m-%d %H:%M:%S")
    _db_conn().execute("INSERT OR IGNORE INTO relay(domain,kind,created) VALUES(?,?,?)",(d.strip().lower(),k,now))
    _db_conn().commit()

def rly_del(did):
    _db_conn().execute("DELETE FROM relay WHERE id=?",(did,)); _db_conn().commit()

def rly_by_kind(k):
    return [r["domain"] for r in _db_conn().execute("SELECT domain FROM relay WHERE kind=?",(k,)).fetchall()]

def build_cfg():
    defaults = {"siteName":"独立跳转站","probeAssetThreshold":2,"wildcardEnabled":True,"wildcardBaseDomain":"","wildcardCandidateCount":6,"wildcardLabelLength":8,"relayLabelLength":4}
    cfg={}
    for k,v in defaults.items():
        val=cfg_get(k)
        cfg[k]=v if val is None else val
    cfg["probeAssets"]=cfg_get("probeAssets") or ["/logo.png"]
    cfg["domains"]=dom_list(st=1)
    cfg["mainDomains"]=rly_by_kind("main")
    cfg["relayDomains"]=rly_by_kind("relay")
    return cfg

# ── HTTP Handler ──
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=BASE_DIR,**kw)

    def _auth(self):
        if not ADMIN_PASS: return True
        h=self.headers.get("Authorization","")
        if not h.startswith("Basic "): return False
        try:
            u,p=base64.b64decode(h[6:]).decode().split(":",1)
            return u==ADMIN_USER and p==ADMIN_PASS
        except: return False

    def _send401(self):
        self.send_response(401); self.send_header("WWW-Authenticate",'Basic realm="Go"'); self.send_header("Content-Length","0"); self.end_headers()

    def _json(self,data,code=200):
        b=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.send_header("Cache-Control","no-cache"); self.end_headers(); self.wfile.write(b)

    def _redir(self,url):
        self.send_response(302); self.send_header("Location",url); self.send_header("Cache-Control","no-cache"); self.end_headers()

    def _body(self):
        n=int(self.headers.get("Content-Length","0") or 0)
        return self.rfile.read(n).decode() if n else ""

    def _file(self,path):
        fp=os.path.join(BASE_DIR,path)
        if os.path.isfile(fp):
            with open(fp,"rb") as f: body=f.read()
            ct={"css":"text/css","js":"application/javascript"}.get(path.rsplit(".",1)[-1],"text/html")
            self.send_response(200); self.send_header("Content-Type",f"{ct}; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        else: self.send_error(404)

    def do_GET(self):
        p=urllib.parse.urlparse(self.path); path=p.path; q=urllib.parse.parse_qs(p.query)
        host=(self.headers.get("Host") or "").split(":")[0].lower()
        cfg=build_cfg()

        # admin page
        if path in ("/admin","/admin/"):
            if not self._auth(): return self._send401()
            return self._file("admin.html")
        if path=="/admin/api/config" and self._auth(): return self._json(cfg)
        if path=="/admin/api/domains" and self._auth():
            s=q.get("search",[""])[0]; t=q.get("tag",[""])[0]; st=q.get("status",[""])[0]
            st=int(st) if st else None; pg=int(q.get("page",[1])[0]); sz=int(q.get("size",[50])[0])
            items=dom_list(sch=s,tg=t,st=st,ofs=(pg-1)*sz,lim=sz)
            total=dom_count(sch=s,tg=t,st=st)
            return self._json({"items":items,"total":total,"page":pg,"size":sz})
        if path=="/admin/api/domains/tags" and self._auth(): return self._json({"tags":dom_tags()})
        if path=="/admin/api/relay" and self._auth(): return self._json({"items":rly_list()})

        # relay
        md=cfg.get("mainDomains",[]); rd=cfg.get("relayDomains",[])
        if host in md and rd and path in ("/","/go","/go/"):
            return self._redir(f"https://{rand_label(cfg.get('relayLabelLength',4))}.{random.choice(rd)}/go")
        if path in ("/go","/go/"): return self._redir(f"/?token={make_token(TOKEN_SECRET)}")

        # public api
        if path=="/api/verify-token":
            ok=check_token((q.get("token") or [""])[0], TOKEN_SECRET)
            return self._json({"ok":ok},200 if ok else 403)
        if path=="/api/gate-token": return self._json({"token":make_token(GATE_SECRET)})
        if path=="/api/config":
            return self._json({"siteName":cfg.get("siteName"),"probeAssets":cfg.get("probeAssets",[]),"probeAssetThreshold":cfg.get("probeAssetThreshold",2),"domains":cfg.get("domains",[]),"wildcard":{"enabled":cfg.get("wildcardEnabled",True),"baseDomain":cfg.get("wildcardBaseDomain",""),"candidateCount":cfg.get("wildcardCandidateCount",6),"labelLength":cfg.get("wildcardLabelLength",8)}})

        # static
        if path=="/": return self._file("index.html")
        if path in ("/app.js","/style.css"): return self._file(path.lstrip("/"))
        self.send_error(404)

    def do_POST(self):
        p=urllib.parse.urlparse(self.path); path=p.path
        if not self._auth(): return self._send401()

        try: data=json.loads(self._body()) if self._body() else {}
        except: return self._json({"ok":False,"message":"JSON错误"},400)

        if path=="/admin/api/config":
            for k in ("siteName","probeAssetThreshold","wildcardEnabled","wildcardBaseDomain","wildcardCandidateCount","wildcardLabelLength","relayLabelLength"):
                if k in data: cfg_set(k,data[k])
            if "probeAssets" in data: cfg_set("probeAssets",data["probeAssets"])
            return self._json({"ok":True,"message":"已保存"})

        if path=="/admin/api/domain":
            a=data.get("action","")
            if a=="add":
                u=clean_domain(data.get("url",""))
                if not u: return self._json({"ok":False,"message":"域名不能为空"},400)
                return self._json({"ok":True,"id":dom_add(u,data.get("name","").strip(),data.get("tag","").strip())})
            if a=="update":
                if not data.get("id"): return self._json({"ok":False,"message":"缺少ID"},400)
                upd={f:data[f] for f in ("url","name","tag","status") if f in data}
                if "url" in upd: upd["url"]=clean_domain(upd["url"])
                dom_upd(data["id"],**upd); return self._json({"ok":True})
            if a=="delete": dom_del(data.get("ids",[])); return self._json({"ok":True})
            if a=="status": dom_sw(data.get("ids",[]),data.get("status",1)); return self._json({"ok":True})
            if a=="import":
                lines=data.get("lines","").strip().split("\n"); items=[]
                for ln in lines:
                    ln=ln.strip()
                    if not ln: continue
                    ps=[p.strip() for p in ln.split(",")]
                    u=clean_domain(ps[0])
                    if u: items.append((u,ps[1] if len(ps)>1 else "",ps[2] if len(ps)>2 else ""))
                if items: dom_import(items)
                return self._json({"ok":True,"count":len(items)})
            return self._json({"ok":False,"message":"未知操作"},400)

        if path=="/admin/api/relay":
            a=data.get("action","")
            if a=="add":
                d=clean_domain(data.get("domain",""))
                k=data.get("kind","main")
                if d and k in ("main","relay"): rly_add(d,k)
                return self._json({"ok":True})
            if a=="delete": rly_del(data.get("id",0)); return self._json({"ok":True})
            return self._json({"ok":False,"message":"未知操作"},400)

        self.send_error(404)

    def log_message(self,fmt,*args):
        print(f"[go] {fmt % args}")

if __name__=="__main__":
    port=int(os.environ.get("PORT",8788))
    host=os.environ.get("HOST","0.0.0.0")
    srv=ThreadingHTTPServer((host,port),Handler)
    print(f">>> http://{host}:{port}")
    try: srv.serve_forever()
    except KeyboardInterrupt: srv.server_close()
