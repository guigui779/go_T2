# -*- coding: utf-8 -*-
"""数据库模块 — SQLite(本地) / PostgreSQL(Vercel) 自适应"""
import json
import os
import time

STORE = None  # 'sqlite' or 'postgres'


def _init_store():
    global STORE
    if STORE:
        return
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url and "postgres" in db_url:
        STORE = "postgres"
        _pg_connect(db_url)
        _pg_init()
    else:
        STORE = "sqlite"
        _sq_connect()
        _sq_init()


# ═══════════════════════════════════════
#  SQLite — 本地开发
# ═══════════════════════════════════════
import sqlite3 as _sq
_sq_conn = None
_sq_path = os.environ.get("DB_PATH", 
    "/tmp/data.db" if os.environ.get("VERCEL") else 
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))


def _sq_connect():
    global _sq_conn
    _sq_conn = _sq.connect(_sq_path)
    _sq_conn.row_factory = _sq.Row


def _sq_init():
    _sq_conn.executescript("""
    CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS domains (
        id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, name TEXT DEFAULT '',
        tag TEXT DEFAULT '', status INTEGER DEFAULT 1, created TEXT NOT NULL, checked TEXT);
    CREATE TABLE IF NOT EXISTS relay (
        id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL);
    """)
    _sq_conn.commit()
    _ensure_defaults()


# ═══════════════════════════════════════
#  PostgreSQL — Vercel 生产（按需加载）
# ═══════════════════════════════════════
_pg_conn = None
_pg = None
_pgx = None

def _pg_connect(url):
    global _pg, _pgx, _pg_conn
    import psycopg2 as _pg_mod
    import psycopg2.extras as _pgx_mod
    _pg = _pg_mod
    _pgx = _pgx_mod
    _pg_conn = _pg.connect(url)


def _pg_init():
    with _pg_conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS domains (
            id SERIAL PRIMARY KEY, url TEXT NOT NULL, name TEXT DEFAULT '',
            tag TEXT DEFAULT '', status INTEGER DEFAULT 1, created TEXT NOT NULL, checked TEXT);
        CREATE TABLE IF NOT EXISTS relay (
            id SERIAL PRIMARY KEY, domain TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL);
        """)
        _pg_conn.commit()
    _ensure_defaults()


# ═══════════════════════════════════════
#  公共接口
# ═══════════════════════════════════════
def _ensure_defaults():
    defaults = {
        "siteName": "独立跳转站", "probeAssets": json.dumps(["/logo.png"]),
        "probeAssetThreshold": "2", "wildcardEnabled": "true",
        "wildcardBaseDomain": "", "wildcardCandidateCount": "6",
        "wildcardLabelLength": "8", "relayLabelLength": "4", "version": "1"
    }
    for k, v in defaults.items():
        if get_config(k) is None:
            set_config(k, json.loads(v) if v in ("true",) else v if isinstance(v, str) and v.startswith("[") else v)
            # simpler: just store string
    # re-do properly
    defaults2 = {
        "siteName": "独立跳转站", "probeAssets": ["/logo.png"],
        "probeAssetThreshold": 2, "wildcardEnabled": True,
        "wildcardBaseDomain": "", "wildcardCandidateCount": 6,
        "wildcardLabelLength": 8, "relayLabelLength": 4, "version": 1
    }
    for k, v in defaults2.items():
        if get_config(k) is None:
            set_config(k, v)


def get_config(key):
    _init_store()
    if STORE == "sqlite":
        row = _sq_conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        if row:
            return json.loads(row["value"])
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("SELECT value FROM config WHERE key=%s", (key,))
            row = cur.fetchone()
        if row:
            return json.loads(row[0])
    return None


def set_config(key, value):
    _init_store()
    val = json.dumps(value, ensure_ascii=False)
    if STORE == "sqlite":
        _sq_conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, val))
        _sq_conn.commit()
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("INSERT INTO config(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=%s",
                        (key, val, val))
            _pg_conn.commit()


# ── 域名 ──
def domain_list(status=None, search="", tag="", offset=0, limit=100):
    _init_store()
    sql = "SELECT * FROM domains WHERE 1=1"
    params = []

    def _add(field, op, val):
        nonlocal sql
        sql += f" AND {field} {op} ?"
        params.append(val)

    if status is not None:
        _add("status", "=", status)
    if search:
        sql += " AND (url ILIKE ? OR name ILIKE ? OR tag ILIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if tag:
        _add("tag", "=", tag)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    if STORE == "sqlite":
        rows = _sq_conn.execute(sql.replace("ILIKE", "LIKE"), params).fetchall()
        return [dict(r) for r in rows]
    else:
        with _pg_conn.cursor(cursor_factory=_pgx.RealDictCursor) as cur:
            cur.execute(sql.replace("?", "%s"), params)
            return list(cur)


def domain_count(status=None, search="", tag=""):
    _init_store()
    sql = "SELECT COUNT(*) as n FROM domains WHERE 1=1"
    params = []
    if status is not None:
        sql += " AND status=?"
        params.append(status)
    if search:
        sql += " AND (url ILIKE ? OR name ILIKE ? OR tag ILIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    if tag:
        sql += " AND tag=?"
        params.append(tag)

    sql_ = sql.replace("ILIKE", "LIKE")
    if STORE == "sqlite":
        return _sq_conn.execute(sql_, params).fetchone()["n"]
    else:
        sql_ = sql_.replace("?", "%s")
        with _pg_conn.cursor() as cur:
            cur.execute(sql_, params)
            return cur.fetchone()[0]


def domain_add(url, name="", tag=""):
    _init_store()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if STORE == "sqlite":
        _sq_conn.execute("INSERT INTO domains(url,name,tag,status,created) VALUES(?,?,?,1,?)",
                         (url, name, tag, now))
        _sq_conn.commit()
        return _sq_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("INSERT INTO domains(url,name,tag,status,created) VALUES(%s,%s,%s,1,%s) RETURNING id",
                        (url, name, tag, now))
            _pg_conn.commit()
            return cur.fetchone()[0]


def domain_update(domain_id, **kwargs):
    _init_store()
    sets = []
    params = []
    for k in ("url", "name", "tag", "status"):
        if k in kwargs:
            sets.append(f"{k}=?")
            params.append(kwargs[k])
    if not sets:
        return
    params.append(domain_id)
    if STORE == "sqlite":
        _sq_conn.execute(f"UPDATE domains SET {','.join(sets)} WHERE id=?", params)
        _sq_conn.commit()
    else:
        sql = f"UPDATE domains SET {','.join(sets).replace('?','%s')} WHERE id=%s"
        with _pg_conn.cursor() as cur:
            cur.execute(sql, params)
            _pg_conn.commit()


def domain_batch_delete(ids):
    _init_store()
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    if STORE == "sqlite":
        _sq_conn.execute(f"DELETE FROM domains WHERE id IN ({placeholders})", ids)
        _sq_conn.commit()
    else:
        placeholders = ",".join(["%s"] * len(ids))
        with _pg_conn.cursor() as cur:
            cur.execute(f"DELETE FROM domains WHERE id IN ({placeholders})", ids)
            _pg_conn.commit()


def domain_batch_status(ids, status):
    _init_store()
    if not ids:
        return
    placeholders = ",".join(["?"] * len(ids))
    params = [status] + list(ids)
    if STORE == "sqlite":
        _sq_conn.execute(f"UPDATE domains SET status=? WHERE id IN ({placeholders})", params)
        _sq_conn.commit()
    else:
        placeholders = ",".join(["%s"] * len(ids))
        with _pg_conn.cursor() as cur:
            cur.execute(f"UPDATE domains SET status=%s WHERE id IN ({placeholders})", params)
            _pg_conn.commit()


def domain_all_tags():
    _init_store()
    if STORE == "sqlite":
        rows = _sq_conn.execute("SELECT DISTINCT tag FROM domains WHERE tag!='' ORDER BY tag").fetchall()
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("SELECT DISTINCT tag FROM domains WHERE tag!='' ORDER BY tag")
            rows = [type('R', (), {'tag': r[0]}) for r in cur]
    return [r["tag"] if isinstance(r, dict) else r.tag for r in rows]


def domain_import_batch(items):
    _init_store()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if STORE == "sqlite":
        _sq_conn.executemany("INSERT OR IGNORE INTO domains(url,name,tag,status,created) VALUES(?,?,?,1,?)",
                             [(u, n, t, now) for u, n, t in items])
        _sq_conn.commit()
    else:
        with _pg_conn.cursor() as cur:
            for u, n, t in items:
                cur.execute("INSERT INTO domains(url,name,tag,status,created) VALUES(%s,%s,%s,1,%s) ON CONFLICT DO NOTHING",
                            (u, n, t, now))
            _pg_conn.commit()


# ── 中继域名 ──
def relay_list(kind=""):
    _init_store()
    if STORE == "sqlite":
        if kind:
            rows = _sq_conn.execute("SELECT * FROM relay WHERE kind=? ORDER BY id", (kind,)).fetchall()
        else:
            rows = _sq_conn.execute("SELECT * FROM relay ORDER BY kind, id").fetchall()
        return [dict(r) for r in rows]
    else:
        with _pg_conn.cursor(cursor_factory=_pgx.RealDictCursor) as cur:
            if kind:
                cur.execute("SELECT * FROM relay WHERE kind=%s ORDER BY id", (kind,))
            else:
                cur.execute("SELECT * FROM relay ORDER BY kind, id")
            return list(cur)


def relay_add(domain, kind):
    _init_store()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    d = domain.strip().lower()
    if not d:
        return
    if STORE == "sqlite":
        _sq_conn.execute("INSERT OR IGNORE INTO relay(domain,kind,created) VALUES(?,?,?)", (d, kind, now))
        _sq_conn.commit()
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("INSERT INTO relay(domain,kind,created) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (d, kind, now))
            _pg_conn.commit()


def relay_delete(domain_id):
    _init_store()
    if STORE == "sqlite":
        _sq_conn.execute("DELETE FROM relay WHERE id=?", (domain_id,))
        _sq_conn.commit()
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("DELETE FROM relay WHERE id=%s", (domain_id,))
            _pg_conn.commit()


def relay_get_by_kind(kind):
    _init_store()
    if STORE == "sqlite":
        rows = _sq_conn.execute("SELECT domain FROM relay WHERE kind=?", (kind,)).fetchall()
        return [r["domain"] for r in rows]
    else:
        with _pg_conn.cursor() as cur:
            cur.execute("SELECT domain FROM relay WHERE kind=%s", (kind,))
            return [r[0] for r in cur]
