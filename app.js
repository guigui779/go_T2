(function () {
  "use strict";

  var PROBE_TIMEOUT = 2000;
  var GRACE_MS = 300;
  var CACHE_KEY = "_jc_v4";
  var CACHE_TTL = 300000;
  var COUNTDOWN_SEC = 3;
  var MAX_RETRY = 3;

  var $ = function (id) { return document.getElementById(id) };

  function rnd(n) { for (var s = "", c = "abcdefghijklmnopqrstuvwxyz0123456789", i = 0; i < n; i++)s += c[Math.random() * 36 | 0]; return s }

  /* ── 缓存 ── */
  function getCache() {
    try { var o = JSON.parse(localStorage.getItem(CACHE_KEY)); return (o && o.url && Date.now() - o.ts < CACHE_TTL) ? o : null } catch (e) { return null }
  }
  function setCache(url) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ url: url, ts: Date.now() })) } catch (e) { }
  }

  /* ── DNS 预连接 ── */
  function prefetch(host) {
    var lk = document.createElement("link"); lk.rel = "dns-prefetch"; lk.href = "//" + host; document.head.appendChild(lk);
  }

  /* ── 候选域名 ── */
  function buildDomains(cfg) {
    if (cfg.domains && cfg.domains.length) return cfg.domains;
    var wc = cfg.wildcard;
    if (!wc || !wc.enabled || !wc.baseDomain) return [];
    var base = wc.baseDomain, count = parseInt(wc.candidateCount, 10) || 6, len = parseInt(wc.labelLength, 10) || 3;
    var list = [], seen = {}, tries = 0;
    while (list.length < count && tries < count * 8) {
      tries++;
      var url = "https://" + rnd(len) + "." + base;
      if (seen[url]) continue;
      seen[url] = 1;
      list.push({ url: url, name: "线路" + (list.length + 1) });
    }
    return list;
  }

  /* ── 探测单个资源（不加 ?_= 参数） ── */
  function probeOne(url, timeout, cb) {
    var img = new Image(), done = false;
    var tm = setTimeout(function () { if (!done) { done = true; img.src = ""; cb(false) } }, timeout);
    img.onload = function () { if (!done) { done = true; clearTimeout(tm); cb(true) } };
    img.onerror = function () { if (!done) { done = true; clearTimeout(tm); cb(false) } };
    img.src = url;
  }

  /* ── 检测域名 ── */
  function checkDomain(domain, cfg, cb) {
    var t0 = Date.now();
    var base = domain.url.replace(/\/+$/, "");
    var assets = cfg.probeAssets || [];
    var need = parseInt(cfg.probeAssetThreshold, 10) || 2;
    if (!assets.length) { cb(false, 0); return }
    var ok = 0, total = 0, ended = false;
    var tm = setTimeout(fin, PROBE_TIMEOUT);
    function fin() { if (ended) return; ended = true; clearTimeout(tm); cb(ok >= need, ok >= need ? Date.now() - t0 : 0) }
    assets.forEach(function (path) {
      probeOne(base + path, PROBE_TIMEOUT - 500, function (pass) {
        total++; if (pass) ok++;
        if (!ended) { if (ok >= need) fin(); else if (total === assets.length) fin() }
      });
    });
  }

  /* ── UI ── */
  function setText(t) { $("statusText").textContent = t }
  function spinner(v) { $("spinnerWrap").style.display = v ? "" : "none" }

  function renderLines(domains) {
    var ul = $("lineList"); ul.innerHTML = "";
    domains.forEach(function (d, i) {
      var li = document.createElement("li"); li.id = "L" + i;
      li.innerHTML = '<span class="line-name">' + d.name + '</span><span class="line-status checking" id="S' + i + '">检测中</span>';
      ul.appendChild(li);
    });
  }

  function setLine(i, ok, lat) {
    var s = $("S" + i); if (s) { s.className = "line-status " + (ok ? "ok" : "fail"); s.textContent = ok ? (lat + "ms") : "超时" }
    var li = $("L" + i); if (li) li.className = ok ? "ok" : "fail";
  }

  function bindLine(i, url) { var li = $("L" + i); if (li) li.onclick = function () { jump(url) } }

  /* ── 跳转 ── */
  function jump(url) {
    setCache(url);
    setText("正在获取访问凭证...");
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/gate-token", true);
    xhr.timeout = 2000;
    xhr.onload = function () {
      var tk = ""; try { tk = JSON.parse(xhr.responseText).token || "" } catch (e) { }
      var sep = url.indexOf("?") >= 0 ? "&" : "?";
      location.replace(url + sep + "_gate=" + encodeURIComponent(tk));
    };
    xhr.onerror = xhr.ontimeout = function () { location.replace(url) };
    xhr.send();
  }

  /* ── 倒计时 ── */
  function startCountdown(results) {
    var best = results[0], sec = COUNTDOWN_SEC, cancel = false;
    spinner(false);
    setText(sec + " 秒后跳转到最快线路...");
    $("mainActions").className = "actions";
    var bLi = $("L" + best.i); if (bLi) bLi.className = "ok best";
    results.forEach(function (r) { bindLine(r.i, r.url) });
    $("cancelBtn").onclick = function () { cancel = true; clearInterval(iv); setText("已取消，点击线路手动跳转"); $("mainActions").className = "actions hide" };
    var iv = setInterval(function () { if (cancel) return; sec--; if (sec <= 0) { clearInterval(iv); jump(best.url) } else setText(sec + " 秒后跳转到最快线路...") }, 1000);
  }

  function showFallback() { $("mainContent").className = "hide"; $("fallbackContent").className = "" }

  function showDenied() {
    $("mainContent").className = "hide"; $("fallbackContent").className = "";
    var ic = document.querySelector(".fallback-icon"), tt = document.querySelector(".fallback-title"), ds = document.querySelector(".fallback-desc");
    if (ic) ic.textContent = "\uD83D\uDD12"; if (tt) tt.textContent = "访问受限"; if (ds) ds.textContent = "请通过正确链接访问";
    $("contactLinks").innerHTML = "";
  }

  /* ── 探测流程 ── */
  function probe(cfg, retry) {
    retry = retry || 0;
    var domains = buildDomains(cfg);
    if (!domains.length) { showFallback(); return }
    spinner(true); setText("正在检测最快线路..."); renderLines(domains);
    var results = [], done = 0, ended = false, grace = null;
    function finish() { if (ended) return; ended = true; if (grace) clearTimeout(grace); if (results.length) { results.sort(function (a, b) { return a.lat - b.lat }); startCountdown(results) } }
    domains.forEach(function (d, i) {
      checkDomain(d, cfg, function (ok, lat) {
        done++; setLine(i, ok, lat);
        if (ok) { results.push({ url: d.url, name: d.name, lat: lat, i: i }); bindLine(i, d.url); if (!grace) grace = setTimeout(finish, GRACE_MS) }
        if (done === domains.length) { if (results.length) finish(); else if (retry < MAX_RETRY) { setText("重试 (" + (retry + 1) + "/" + MAX_RETRY + ")..."); setTimeout(function () { probe(cfg, retry + 1) }, 800) } else showFallback() }
      });
    });
  }

  /* ── Token ── */
  function getToken() { var m = location.search.match(/[?&]token=([^&]+)/); return m ? decodeURIComponent(m[1]) : "" }

  function verifyToken(token, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/verify-token?token=" + encodeURIComponent(token), true);
    xhr.timeout = 3000;
    xhr.onload = function () { try { cb(JSON.parse(xhr.responseText).ok === true) } catch (e) { cb(false) } };
    xhr.onerror = xhr.ontimeout = function () { cb(false) };
    xhr.send();
  }

  /* ── 入口 ── */
  function init() {
    var token = getToken();
    if (!token) { showDenied(); return }
    setText("验证访问权限...");
    verifyToken(token, function (ok) {
      if (!ok) { showDenied(); return }
      if (history.replaceState) history.replaceState(null, "", location.pathname);
      var xhr = new XMLHttpRequest();
      xhr.open("GET", "/api/config?_=" + Date.now(), true);
      xhr.timeout = 3000;
      xhr.onload = function () { var cfg; try { cfg = JSON.parse(xhr.responseText) } catch (e) { cfg = {} } run(cfg) };
      xhr.onerror = xhr.ontimeout = function () { run({}) };
      xhr.send();
    });
  }

  function run(cfg) {
    if (cfg.siteName) $("brandName").textContent = cfg.siteName;
    if (cfg.wildcard && cfg.wildcard.baseDomain) prefetch(cfg.wildcard.baseDomain);
    var cached = getCache();
    if (cached) { setText("验证上次线路..."); checkDomain({ url: cached.url, name: "cache" }, cfg, function (ok) { if (ok) jump(cached.url); else probe(cfg) }) }
    else probe(cfg);
  }

  init();
})();