(function () {
  'use strict';

  var el = function (id) { return document.getElementById(id) };

  var F = {
    main: el('f_main'), relay: el('f_relay'), rlen: el('f_rlen'),
    name: el('f_name'), wc: el('f_wc'), base: el('f_base'),
    cnt: el('f_cnt'), plen: el('f_plen'), thr: el('f_thr'),
    assets: el('f_assets'), fixed: el('f_fixed'), gt: el('f_gt')
  };

  function split(t) { return t.split(/\r?\n/).map(function (s) { return s.trim() }).filter(Boolean) }
  function rnd(n) { for (var s = '', c = 'abcdefghijklmnopqrstuvwxyz0123456789', i = 0; i < n; i++) s += c[Math.random() * 36 | 0]; return s }
  function msg(t, e) { var m = el('o_msg'); m.textContent = t || ''; m.style.color = e ? '#ff9b9b' : '#7dcea0' }

  function api(method, path, body) {
    var o = { method: method, cache: 'no-store' };
    if (body) { o.headers = { 'Content-Type': 'application/json' }; o.body = JSON.stringify(body) }
    var url = '/admin/api/' + path;
    if (method === 'GET') url += (url.indexOf('?') >= 0 ? '&' : '?') + '_=' + Date.now();
    return fetch(url, o).then(function (r) {
      if (r.status === 401) throw new Error('需要登录');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function syncWC() {
    var on = F.wc.checked;
    el('z_wc').classList.toggle('X', !on);
    el('z_pv').classList.toggle('X', !on);
    el('z_fd').classList.toggle('X', on);
  }
  F.wc.addEventListener('change', syncWC);

  function preview() {
    var base = F.base.value.trim(), n = parseInt(F.cnt.value, 10) || 6, len = parseInt(F.plen.value, 10) || 8, out = el('o_pv');
    if (!base) { out.textContent = '填写基础域名后预览'; return }
    var a = [], u = {};
    while (a.length < Math.min(n, 20)) { var lb = rnd(len); if (u[lb]) continue; u[lb] = 1; a.push((a.length + 1) + '. https://' + lb + '.' + base) }
    out.textContent = a.join('\n');
  }

  function fill(cfg) {
    F.name.value = cfg.siteName || '';
    var r = cfg.relay || {};
    F.main.value = (r.mainDomains || []).join('\n');
    F.relay.value = (r.relayDomains || []).join('\n');
    F.rlen.value = r.labelLength || 4;
    F.wc.checked = !!(cfg.wildcard && cfg.wildcard.enabled !== false);
    F.base.value = (cfg.wildcard && cfg.wildcard.baseDomain) || '';
    F.cnt.value = (cfg.wildcard && cfg.wildcard.candidateCount) || 6;
    F.plen.value = (cfg.wildcard && cfg.wildcard.labelLength) || 8;
    F.thr.value = cfg.probeAssetThreshold || 2;
    F.assets.value = (cfg.probeAssets || []).join('\n');
    F.fixed.value = (cfg.domains || []).map(function (d) { return d.name ? d.url + ',' + d.name : d.url }).join('\n');
    el('o_json').textContent = JSON.stringify(cfg, null, 2);
    syncWC(); preview();
  }

  function collect() {
    var doms = split(F.fixed.value).map(function (l, i) { var p = l.split(','); return { url: p[0].trim(), name: (p[1] || '').trim() || ('线路' + (i + 1)), provider: 'manual' } });
    return {
      siteName: F.name.value.trim() || '独立跳转站',
      relay: { mainDomains: split(F.main.value), relayDomains: split(F.relay.value), labelLength: parseInt(F.rlen.value, 10) || 4 },
      wildcard: { enabled: F.wc.checked, baseDomain: F.base.value.trim(), candidateCount: parseInt(F.cnt.value, 10) || 6, labelLength: parseInt(F.plen.value, 10) || 8 },
      probeAssets: split(F.assets.value),
      probeAssetThreshold: parseInt(F.thr.value, 10) || 2,
      domains: doms
    };
  }

  function load() {
    msg('加载中...');
    api('GET', 'config').then(function (d) { fill(d); msg('已加载') }).catch(function (e) { msg('加载失败: ' + e.message, true) });
  }

  function save() {
    var cfg = collect();
    if (cfg.wildcard.enabled && !cfg.wildcard.baseDomain) { msg('通配开启请填基础域名', true); return }
    if (!cfg.wildcard.enabled && !cfg.domains.length) { msg('通配关闭请填固定域名', true); return }
    if (!cfg.probeAssets.length) { msg('请填探测资源路径', true); return }
    msg('保存中...');
    api('POST', 'config', cfg).then(function (d) { if (!d.ok) throw new Error(d.message || '失败'); fill(d.config); msg('保存成功') }).catch(function (e) { msg('保存失败: ' + e.message, true) });
  }

  el('btn_save').onclick = save;
  el('btn_load').onclick = load;
  el('btn_gate').onclick = function () {
    msg('生成中...');
    api('GET', 'generate-gate?type=' + F.gt.value).then(function (d) {
      if (!d.ok) throw new Error(d.message || '失败');
      el('o_gate').textContent = d.config; el('z_gate').classList.remove('X'); msg('Gate 配置已生成');
    }).catch(function (e) { msg('生成失败: ' + e.message, true) });
  };
  el('btn_cp').onclick = function () {
    var t = el('o_gate').textContent; if (!t) return;
    if (navigator.clipboard) { navigator.clipboard.writeText(t).then(function () { msg('已复制') }) }
    else { var a = document.createElement('textarea'); a.value = t; a.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(a); a.select(); document.execCommand('copy'); document.body.removeChild(a); msg('已复制') }
  };
  el('tog_json').onclick = function () { this.classList.toggle('open'); el('o_json').classList.toggle('X') };
  [F.base, F.cnt, F.plen].forEach(function (e) { e.addEventListener('input', preview) });

  load();
})();
