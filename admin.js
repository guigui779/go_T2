// Go V5 Admin — 域名管理
var G = {};
var page = 1, pageSize = 50;

function $(id) { return document.getElementById(id); }
function S(sel) { return document.querySelector(sel); }
function H(id) { var e = typeof id === 'string' ? $(id) : id; if (e) e.classList.toggle('X'); }
function toast(msg, ok) {
  var t = $('toast'); t.textContent = msg; t.className = 'toast ' + (ok ? 'ok' : 'err'); t.classList.remove('X');
  setTimeout(function () { t.classList.add('X'); }, 2000);
}

// API
function api(method, path, body) {
  var o = { method: method, cache: 'no-store' };
  if (body) { o.headers = { 'Content-Type': 'application/json' }; o.body = JSON.stringify(body); }
  return fetch('/admin/api/' + path, o).then(function (r) {
    if (r.status === 401) throw new Error('need login');
    return r.json();
  });
}

// Tabs
document.querySelectorAll('.tab').forEach(function (t) {
  t.onclick = function () {
    document.querySelectorAll('.tab,.tab-content').forEach(function (e) { e.classList.toggle('active', false); e.classList.toggle('X', !e.classList.contains('active')); });
    this.classList.add('active'); $('tab-' + this.dataset.tab).classList.remove('X');
  };
});

// ── 域名管理 ──
function loadTags() {
  api('GET', 'domains/tags').then(function (d) {
    var s = $('dom_tag'); s.innerHTML = '<option value="">全部标签</option>';
    d.tags.forEach(function (t) { s.innerHTML += '<option value="'+t+'">'+t+'</option>'; });
  });
}

function loadDomains() {
  var q = 'search=' + encodeURIComponent($('dom_search').value) + '&tag=' + encodeURIComponent($('dom_tag').value) + '&page=' + page + '&size=' + pageSize;
  api('GET', 'domains?' + q).then(function (d) {
    var tbody = document.querySelector('#dom_table tbody');
    tbody.innerHTML = '';
    d.items.forEach(function (item, i) {
      tbody.innerHTML += '<tr><td><input type="checkbox" value="' + item.id + '"></td>' +
        '<td>' + esc(item.url) + '</td>' +
        '<td>' + esc(item.name) + '</td>' +
        '<td>' + (item.tag ? '<span class="tag">' + esc(item.tag) + '</span>' : '') + '</td>' +
        '<td>' + (item.status === 1 ? '<span class="st on">启用</span>' : '<span class="st off">停用</span>') + '</td>' +
        '<td><a href="#" class="act" data-id="' + item.id + '" data-act="edit">编辑</a> ' +
        '<a href="#" class="act" data-id="' + item.id + '" data-act="toggle">' + (item.status === 1 ? '停用' : '启用') + '</a></td></tr>';
    });
    var total = d.total || 0;
    var pages = Math.ceil(total / pageSize);
    var p = $('dom_pager');
    p.innerHTML = pages <= 1 ? '' : '<span class="pg">共 ' + total + ' 条，' + pages + ' 页</span> ';
    for (var i = 1; i <= pages; i++) {
      p.innerHTML += '<a href="#" class="pg' + (i === page ? ' on' : '') + '" data-p="' + i + '">' + i + '</a> ';
    }
    bindActs();
  }).catch(function (e) { toast(e.message, false); });
}

function esc(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function bindActs() {
  document.querySelectorAll('.act').forEach(function (a) {
    a.onclick = function (e) { e.preventDefault();
      var id = this.dataset.id, act = this.dataset.act;
      if (act === 'edit') openEdit(id);
      if (act === 'toggle') toggleDomain(id);
    };
  });
  document.querySelectorAll('.pg').forEach(function (a) {
    a.onclick = function (e) { e.preventDefault(); page = parseInt(this.dataset.p); loadDomains(); };
  });
}

function openEdit(id) {
  if (id) {
    api('GET', 'domains?search=&page=1&size=1&status=&id=' + id).then(function (d) {
      // need specific get — use list filter hack
    });
    // simpler: just fetch all and find
    api('GET', 'domains?size=200&page=1').then(function (d) {
      var item = (d.items || []).filter(function(x){return x.id == id})[0];
      if (item) {
        $('edit_title').textContent = '编辑域名';
        $('edit_id').value = item.id;
        $('edit_url').value = item.url;
        $('edit_name').value = item.name || '';
        $('edit_tag').value = item.tag || '';
        H('edit_modal');
      }
    });
  } else {
    $('edit_title').textContent = '添加域名';
    $('edit_id').value = '';
    $('edit_url').value = '';
    $('edit_name').value = '';
    $('edit_tag').value = '';
    H('edit_modal');
  }
}

$('edit_ok').onclick = function () {
  var id = $('edit_id').value;
  var data = { url: $('edit_url').value.trim(), name: $('edit_name').value.trim(), tag: $('edit_tag').value.trim() };
  if (id) {
    data.action = 'update'; data.id = parseInt(id);
  } else {
    data.action = 'add';
  }
  api('POST', 'domain', data).then(function (d) {
    if (d.ok) { H('edit_modal'); toast('保存成功', true); loadDomains(); loadTags(); }
    else toast(d.message, false);
  });
};

function toggleDomain(id) {
  api('GET', 'domains?size=200').then(function (d) {
    var item = (d.items || []).filter(function(x){return x.id == id})[0];
    if (item) {
      api('POST', 'domain', { action: 'status', ids: [id], status: item.status === 1 ? 0 : 1 }).then(function () {
        toast('已' + (item.status === 1 ? '停用' : '启用'), true); loadDomains();
      });
    }
  });
}

$('dom_add_btn').onclick = function () { openEdit(); };
$('dom_search_btn').onclick = function () { page = 1; loadDomains(); };
$('dom_search').onkeydown = function (e) { if (e.key === 'Enter') { page = 1; loadDomains(); } };
$('dom_all').onclick = function () {
  document.querySelectorAll('#dom_table input[type=checkbox]').forEach(function (c) { c.checked = this.checked; });
};

$('dom_del_sel').onclick = function () {
  var ids = [];
  document.querySelectorAll('#dom_table tbody input:checked').forEach(function (c) { ids.push(parseInt(c.value)); });
  if (!ids.length) return toast('请选择域名', false);
  api('POST', 'domain', { action: 'delete', ids: ids }).then(function () { toast('已删除', true); loadDomains(); });
};

$('dom_import_btn').onclick = function () { H('import_modal'); };
$('import_ok').onclick = function () {
  api('POST', 'domain', { action: 'import', lines: $('import_txt').value }).then(function (d) {
    if (d.ok) { H('import_modal'); toast('成功导入 ' + d.count + ' 条', true); loadDomains(); loadTags(); }
    else toast(d.message, false);
  });
};

// ── 中继配置 ──
function loadRelay() {
  api('GET', 'relay').then(function (d) {
    var m = d.items.filter(function (x) { return x.kind === 'main'; });
    var r = d.items.filter(function (x) { return x.kind === 'relay'; });
    $('relay_main_list').innerHTML = m.map(function (x) { return '<li>' + esc(x.domain) + ' <a href="#" class="act del" data-id="' + x.id + '" data-kind="main">删</a></li>'; }).join('');
    $('relay_relay_list').innerHTML = r.map(function (x) { return '<li>' + esc(x.domain) + ' <a href="#" class="act del" data-id="' + x.id + '" data-kind="relay">删</a></li>'; }).join('');
    document.querySelectorAll('.act.del').forEach(function (a) {
      a.onclick = function (e) { e.preventDefault(); api('POST', 'relay', { action: 'delete', id: parseInt(this.dataset.id) }).then(function () { toast('已删除', true); loadRelay(); }); };
    });
  });
}

['main','relay'].forEach(function (kind) {
  $('relay_' + kind + '_add').onclick = function () { $('relay_kind').value = kind; $('relay_domain').value = ''; H('relay_modal'); };
});
$('relay_ok').onclick = function () {
  api('POST', 'relay', { action: 'add', domain: $('relay_domain').value.trim(), kind: $('relay_kind').value }).then(function (d) { if (d.ok) { H('relay_modal'); toast('已添加', true); loadRelay(); } });
};

// ── 站点设置 ──
function loadSettings() {
  api('GET', 'config').then(function (cfg) {
    $('set_name').value = cfg.siteName || '';
    $('set_wc').checked = cfg.wildcardEnabled !== false;
    $('set_base').value = cfg.wildcardBaseDomain || '';
    $('set_cnt').value = cfg.wildcardCandidateCount || 6;
    $('set_plen').value = cfg.wildcardLabelLength || 8;
    $('set_thr').value = cfg.probeAssetThreshold || 2;
    $('set_assets').value = (cfg.probeAssets || []).join('\n');
    $('relay_len').value = cfg.relayLabelLength || 4;
  });
}

$('relay_save').onclick = function () {
  api('POST', 'config', { relayLabelLength: parseInt($('relay_len').value) || 4 }).then(function () { toast('已保存', true); });
};

$('set_save').onclick = function () {
  api('POST', 'config', {
    siteName: $('set_name').value.trim(),
    wildcardEnabled: $('set_wc').checked,
    wildcardBaseDomain: $('set_base').value.trim(),
    wildcardCandidateCount: parseInt($('set_cnt').value) || 6,
    wildcardLabelLength: parseInt($('set_plen').value) || 8,
    probeAssetThreshold: parseInt($('set_thr').value) || 2,
    probeAssets: $('set_assets').value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean)
  }).then(function () { toast('已保存', true); });
};

// Init
loadDomains(); loadTags(); loadRelay(); loadSettings();
