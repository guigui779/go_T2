#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Go Page V5 — Flask 版，可部署到 Vercel"""
import base64
import hashlib
import hmac
import json
import os
import random
import string
import time
import urllib.parse

from flask import Flask, request, jsonify, redirect, send_from_directory, make_response

import db

app = Flask(__name__, static_folder=None)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 环境变量 ──
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "") or base64.b64encode(os.urandom(32)).decode()
TOKEN_TTL = int(os.environ.get("TOKEN_TTL", "300"))
GATE_SECRET = os.environ.get("GATE_SECRET", "") or base64.b64encode(os.urandom(32)).decode()

CHARS = string.ascii_lowercase + string.digits


# ── Token ──
def _hmac_sign(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]


def _make_token(secret):
    ts = str(int(time.time()))
    raw = ts + ":" + _hmac_sign(secret, ts)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _check_token(token, secret):
    try:
        padding = 4 - len(token) % 4
        if padding != 4:
            token += "=" * padding
        raw = base64.urlsafe_b64decode(token).decode()
        ts_str, sig = raw.split(":", 1)
        if abs(time.time() - int(ts_str)) > TOKEN_TTL:
            return False
        return hmac.compare_digest(sig, _hmac_sign(secret, ts_str))
    except Exception:
        return False


def rand_label(n):
    return "".join(random.choices(CHARS, k=n))


def clean_domain(raw):
    s = str(raw).strip().lower()
    for p in ("https://", "http://"):
        if s.startswith(p):
            s = s[len(p):]
    s = s.split("/")[0].split(":")[0]
    if s.startswith("*."):
        s = s[2:]
    return s.strip()


def clean_assets(items):
    out = []
    for p in items or []:
        s = str(p).strip().replace("\\", "/")
        if s and not s.startswith("/"):
            s = "/" + s
        if s:
            out.append(s)
    return out


def build_config():
    cfg = {}
    defaults = {"siteName": "独立跳转站", "probeAssetThreshold": 2,
                "wildcardEnabled": True, "wildcardBaseDomain": "",
                "wildcardCandidateCount": 6, "wildcardLabelLength": 8,
                "relayLabelLength": 4, "version": 1}
    for k in defaults:
        v = db.get_config(k)
        cfg[k] = v if v is not None else defaults[k]
    cfg["probeAssets"] = db.get_config("probeAssets") or ["/logo.png"]
    cfg["domains"] = db.domain_list(status=1)
    cfg["mainDomains"] = db.relay_get_by_kind("main")
    cfg["relayDomains"] = db.relay_get_by_kind("relay")
    return cfg


# ── 认证 ──
def check_auth():
    if not ADMIN_PASS:
        return True
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            return False
        u, p = base64.b64decode(auth[6:]).decode().split(":", 1)
        return u == ADMIN_USER and p == ADMIN_PASS
    except Exception:
        return False


def need_auth():
    return make_response("", 401, {"WWW-Authenticate": 'Basic realm="Go V5"'})


# ── 页面 ──
@app.route("/")
def index_page():
    return _file("index.html")


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "db": bool(os.environ.get("DATABASE_URL", ""))})


@app.route("/admin.css")
@app.route("/admin.js")
@app.route("/app.js")
@app.route("/style.css")
def serve_static():
    return _file(request.path.lstrip("/"))


@app.route("/admin")
@app.route("/admin/")
def admin_page():
    if not check_auth():
        return need_auth()
    return _file("admin.html")


def _file(path):
    for d in [BASE_DIR, "/var/task"]:
        fp = os.path.join(d, path)
        if os.path.isfile(fp):
            with open(fp, "rb") as f:
                body = f.read()
            ct = "text/html"
            if path.endswith(".css"): ct = "text/css"
            elif path.endswith(".js"): ct = "application/javascript"
            return make_response(body, 200, {"Content-Type": ct + "; charset=utf-8"})
    return make_response("", 404)


# ── Admin API ──
@app.route("/admin/api/config", methods=["GET"])
def admin_config_get():
    if not check_auth():
        return need_auth()
    return jsonify(build_config())


@app.route("/admin/api/config", methods=["POST"])
def admin_config_post():
    if not check_auth():
        return need_auth()
    data = request.get_json(force=True, silent=True) or {}
    for k in ("siteName", "probeAssetThreshold", "wildcardEnabled",
              "wildcardBaseDomain", "wildcardCandidateCount",
              "wildcardLabelLength", "relayLabelLength"):
        if k in data:
            db.set_config(k, data[k])
    if "probeAssets" in data:
        db.set_config("probeAssets", clean_assets(data["probeAssets"]))
    db.set_config("version", (db.get_config("version") or 0) + 1)
    return jsonify({"ok": True, "message": "已保存"})


@app.route("/admin/api/domains")
def admin_domains():
    if not check_auth():
        return need_auth()
    s = request.args.get("search", "")
    t = request.args.get("tag", "")
    st = request.args.get("status", "")
    status = int(st) if st else None
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 50))
    items = db.domain_list(status=status, search=s, tag=t, offset=(page - 1) * size, limit=size)
    total = db.domain_count(status=status, search=s, tag=t)
    return jsonify({"items": items, "total": total, "page": page, "size": size})


@app.route("/admin/api/domains/tags")
def admin_domain_tags():
    if not check_auth():
        return need_auth()
    return jsonify({"tags": db.domain_all_tags()})


@app.route("/admin/api/domain", methods=["POST"])
def admin_domain_crud():
    if not check_auth():
        return need_auth()
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "")
    if action == "add":
        url = clean_domain(data.get("url", ""))
        if not url:
            return jsonify({"ok": False, "message": "域名不能为空"}), 400
        did = db.domain_add(url, data.get("name", url).strip(), data.get("tag", "").strip())
        return jsonify({"ok": True, "id": did})
    elif action == "update":
        if not data.get("id"):
            return jsonify({"ok": False, "message": "缺少 ID"}), 400
        upd = {f: data[f] for f in ("url", "name", "tag", "status") if f in data}
        if "url" in upd:
            upd["url"] = clean_domain(upd["url"])
        db.domain_update(data["id"], **upd)
        return jsonify({"ok": True})
    elif action == "delete":
        ids = data.get("ids", [])
        if ids:
            db.domain_batch_delete(ids)
        return jsonify({"ok": True})
    elif action == "status":
        ids = data.get("ids", [])
        if ids:
            db.domain_batch_status(ids, data.get("status", 1))
        return jsonify({"ok": True})
    elif action == "import":
        lines = data.get("lines", "").strip().split("\n")
        items = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            u = clean_domain(parts[0])
            if not u:
                continue
            items.append((u, parts[1] if len(parts) > 1 else "", parts[2] if len(parts) > 2 else ""))
        if items:
            db.domain_import_batch(items)
        return jsonify({"ok": True, "count": len(items)})
    return jsonify({"ok": False, "message": "未知 action"}), 400


@app.route("/admin/api/relay", methods=["GET"])
def admin_relay_get():
    if not check_auth():
        return need_auth()
    return jsonify({"items": db.relay_list()})


@app.route("/admin/api/relay", methods=["POST"])
def admin_relay_post():
    if not check_auth():
        return need_auth()
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "")
    if action == "add":
        d = clean_domain(data.get("domain", ""))
        k = data.get("kind", "main")
        if d and k in ("main", "relay"):
            db.relay_add(d, k)
        return jsonify({"ok": True})
    elif action == "delete":
        db.relay_delete(data.get("id", 0))
        return jsonify({"ok": True})
    return jsonify({"ok": False, "message": "未知 action"}), 400


# ── 中继跳转 ──
@app.route("/go")
@app.route("/go/")
def relay_go():
    cfg = build_config()
    host = (request.headers.get("Host") or "").split(":")[0].lower()
    main_domains = cfg.get("mainDomains", [])
    relay_domains = cfg.get("relayDomains", [])

    if host in main_domains and relay_domains:
        rd = random.choice(relay_domains)
        label = rand_label(cfg.get("relayLabelLength", 4))
        return redirect(f"https://{label}.{rd}/go", code=302)
    token = _make_token(TOKEN_SECRET)
    return redirect(f"/?token={token}", code=302)


# ── Public API ──
@app.route("/api/verify-token")
def api_verify_token():
    token = request.args.get("token", "")
    ok = _check_token(token, TOKEN_SECRET)
    return jsonify({"ok": ok}), 200 if ok else 403


@app.route("/api/gate-token")
def api_gate_token():
    return jsonify({"token": _make_token(GATE_SECRET)})


@app.route("/api/config")
def api_config():
    cfg = build_config()
    return jsonify({
        "siteName": cfg.get("siteName"),
        "probeAssets": cfg.get("probeAssets", []),
        "probeAssetThreshold": cfg.get("probeAssetThreshold", 2),
        "domains": cfg.get("domains", []),
        "wildcard": {
            "enabled": cfg.get("wildcardEnabled", True),
            "baseDomain": cfg.get("wildcardBaseDomain", ""),
            "candidateCount": cfg.get("wildcardCandidateCount", 6),
            "labelLength": cfg.get("wildcardLabelLength", 8),
        },
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8787))
    app.run(host="0.0.0.0", port=port, debug=True)
