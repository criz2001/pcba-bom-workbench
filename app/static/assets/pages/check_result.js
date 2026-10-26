/* BOM 校对 · 核对结果 / 问题详情
   /check/result?task=<id>  → 结果页
   /check/detail?task=<id>&no=<n> → 结果页 + 打开第 n 条问题的详情抽屉 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var isDetail = BOM.app.page === 'check-detail';
  var filterLevel = 'all';
  var keyword = '';
  var taskId = BOM.query('task');
  var data = null;
  var booted = false;

  // ------------------------------------------------------------------ 工具
  var CODE_RE = /^(\d+\.\d+\.\d+(\.\d+)?|\d{3,4}|[A-Za-z]{1,3}\d{1,4}|SOT-?23|SSOP\d+|SMA|SMB|DFN\d*|QFN\d*)$/;

  function rich(text) {
    return BOM.escape(text).replace(/[A-Za-z0-9_.\-]+/g, function (tok) {
      return CODE_RE.test(tok) ? '<span class="cr-code">' + tok + '</span>' : tok;
    });
  }

  function pickCodes(text) {
    var out = { refs: [], codes: [] };
    String(text || '').replace(/[A-Za-z0-9_.\-]+/g, function (tok) {
      if (/^\d+\.\d+\.\d+(\.\d+)?$/.test(tok)) { out.codes.push(tok); }
      else if (/^[A-Za-z]{1,3}\d{1,4}$/.test(tok) && !/^\d/.test(tok)) { out.refs.push(tok); }
      return tok;
    });
    out.refs = out.refs.filter(function (v, i, a) { return a.indexOf(v) === i; });
    out.codes = out.codes.filter(function (v, i, a) { return a.indexOf(v) === i; });
    return out;
  }

  function levelTag(level) {
    var cls = level === '严重' ? 'cr-tag--error'
      : (level === '一般' ? 'cr-tag--warning' : 'cr-tag--info');
    return '<span class="cr-tag ' + cls + '">' + BOM.escape(level) + '</span>';
  }

  // ------------------------------------------------------------------ 渲染
  function renderBand() {
    var box = document.querySelector('[data-render="band"]');
    var m = data.metrics || {};
    var b = data.baseline || {};

    box.innerHTML =
      '<div class="cr-metrics">' +
      '<div class="cr-metric"><p class="cr-metric__value cr-metric__value--primary">' + m.total + '</p>' +
      '<p class="cr-metric__label">问题总数</p><p class="cr-metric__sub">严重 ' + m.severe +
      ' · 一般 ' + m.normal + '</p></div>' +
      '<div class="cr-metric"><p class="cr-metric__value cr-metric__value--error">' + m.severe + '</p>' +
      '<p class="cr-metric__label">严重</p><p class="cr-metric__sub">封装 / 位号 / 用量 / 编码类</p></div>' +
      '<div class="cr-metric"><p class="cr-metric__value cr-metric__value--warning">' + m.normal + '</p>' +
      '<p class="cr-metric__label">一般</p><p class="cr-metric__sub">位号格式 / 项次类</p></div>' +
      '<div class="cr-metric"><p class="cr-metric__value cr-metric__value--info">' + m.valueDiff + '</p>' +
      '<p class="cr-metric__label">值差异待确认</p><p class="cr-metric__sub">仅提示，不判为严重</p></div>' +
      '</div>' +
      '<p class="cr-band__note">' + BOM.svg(b.identical ? 'check' : 'triangle-alert') +
      '<span>' + (b.identical
        ? '基准：PCB ' + (b.pcbRefCount != null ? b.pcbRefCount : b.pcbCount) +
          ' / 原理图 ' + (b.schRefCount != null ? b.schRefCount : b.schCount) +
          ' 个位号，集合完全一致' +
          ((b.unlabeled || []).length ? ' · PCB 另有 ' + b.unlabeled.length + ' 个无位号元件已标注' : '')
        : '基准不一致：仅 PCB 有 ' + ((b.onlyPcb || []).join('、') || '无') +
          '；仅原理图有 ' + ((b.onlySch || []).join('、') || '无') + ' → 版次可能未对齐') +
      '</span></p>' +
      ((data.refsFromNote || []).length
        ? '<p class="cr-band__note">' + BOM.svg('info') +
          '<span>' + (data.refsFromNote.length) +
          ' 行的位置号列为空、位号写在备注列：已从备注取回并按设计文件核对，' +
          '不计入「位号缺失」（行 ' +
          BOM.escape(data.refsFromNote.slice(0, 8).map(function (r) { return r.row; }).join('、')) +
          (data.refsFromNote.length > 8 ? ' 等' : '') + '）</span></p>'
        : '');
  }

  function renderDistribution() {
    var box = document.querySelector('[data-render="distribution"]');
    var dist = data.distribution || [];
    if (!dist.length) {
      box.innerHTML = '<li style="list-style:none">' +
        BOM.empty({ icon: 'circle-check', title: '未发现问题', desc: '本次核对 9 类规则全部通过。' }) + '</li>';
      return;
    }
    box.innerHTML = dist.map(function (d) {
      var cls = d.level === '一般' ? 'cr-tag--warning' : 'cr-tag--error';
      return '<li class="cr-dist__row">' +
        '<span class="cr-dist__name">' + BOM.escape(d.kind) + '</span>' +
        '<span class="cr-tag ' + cls + ' cr-dist__tag">' + BOM.escape(d.level) + '</span>' +
        '<span class="cr-bar cr-dist__bar"><span class="cr-bar__fill" style="width: ' + d.pct + '%"></span></span>' +
        '<span class="cr-dist__count">' + d.count + '</span>' +
        '<span class="cr-dist__pct">' + d.pct + '%</span></li>';
    }).join('');
  }

  function filtered() {
    return (data.problems || []).filter(function (p) {
      if (filterLevel !== 'all' && p.level !== filterLevel) { return false; }
      if (keyword) {
        var hay = (p.kind + ' ' + p.msg + ' ' + p.advice + ' ' + (p.row || '')).toUpperCase();
        if (hay.indexOf(keyword.toUpperCase()) < 0) { return false; }
      }
      return true;
    });
  }

  function renderChips() {
    var box = document.querySelector('[data-render="chips"]');
    var m = data.metrics || {};
    var items = [
      ['all', '全部 ' + m.total],
      ['严重', '严重 ' + m.severe],
      ['一般', '一般 ' + m.normal],
      ['提示', '提示 ' + m.info]
    ];
    box.innerHTML = items.map(function (item) {
      return '<button type="button" class="cr-chip" data-level="' + item[0] + '"' +
        (filterLevel === item[0] ? ' data-active="true"' : '') + '>' + BOM.escape(item[1]) + '</button>';
    }).join('');
  }

  function renderProblems() {
    var box = document.querySelector('[data-render="problems"]');
    var rows = filtered();

    if (!rows.length) {
      box.innerHTML = BOM.empty({
        icon: data.problems.length ? 'search' : 'circle-check',
        title: data.problems.length ? '没有匹配的问题' : '未发现问题',
        desc: data.problems.length ? '试着调整级别筛选或搜索关键词。'
                                   : '9 类核对规则全部通过，BOM 与设计文件一致。'
      });
      return;
    }

    var detailHref = function (p) {
      return '/check/detail?task=' + taskId + '&no=' + p.no;
    };

    box.innerHTML = '<table class="cr-table"><thead><tr>' +
      '<th scope="col">序号</th><th scope="col">级别</th><th scope="col">问题类型</th>' +
      '<th scope="col">行号</th><th scope="col">涉及列</th><th scope="col">问题描述</th>' +
      '<th scope="col">处理建议</th><th scope="col">详情</th></tr></thead><tbody>' +
      rows.map(function (p) {
        return '<tr>' +
          '<td class="cr-cell-index">' + p.no + '</td>' +
          '<td>' + levelTag(p.level) + '</td>' +
          '<td>' + BOM.escape(p.kind) + '</td>' +
          '<td class="cr-cell-mono">' + (p.row ? '第' + p.row + '行' : '全局') + '</td>' +
          '<td class="cr-cell-mono">' + BOM.escape(p.cols || '—') + '</td>' +
          '<td>' + rich(p.msg) + '</td>' +
          '<td class="cr-cell-tip">' + rich(p.advice || '') + '</td>' +
          '<td><a href="' + detailHref(p) + '" class="cr-detail">详情</a></td>' +
          '</tr>';
      }).join('') + '</tbody></table>';
  }

  function renderMissing() {
    var box = document.querySelector('[data-render="missing"]');
    var items = data.missingRefs || [];
    if (!items.length) {
      box.innerHTML = '<li style="list-style:none;width:100%">' +
        BOM.empty({ icon: 'circle-check', title: '无位号缺失', desc: 'PCB ∪ 原理图的位号已全部出现在 BOM 中。' }) +
        '</li>';
      return;
    }
    box.innerHTML = items.map(function (item) {
      var meta = item.footprint + (item.value && item.value !== item.footprint ? ' ' + item.value : '');
      return '<li class="cr-badge">' +
        '<span class="cr-badge__ref">' + BOM.escape(item.ref) + '</span>' +
        '<span class="cr-badge__meta">' + BOM.escape(meta) + '</span></li>';
    }).join('');
  }

  function renderValues() {
    var box = document.querySelector('[data-render="values"]');
    var items = data.valueDiffs || [];
    if (!items.length) {
      box.innerHTML = '<li style="list-style:none;width:100%">' +
        BOM.empty({ icon: 'circle-check', title: '无可比对的差异', desc: '未在原理图中找到与 BOM 声明值可比的标注值。' }) +
        '</li>';
      return;
    }
    box.innerHTML = items.map(function (d) {
      var tag = d.equivalent
        ? '<span class="cr-tag cr-tag--success">一致</span>'
        : '<span class="cr-tag cr-tag--warning">需确认</span>';
      var sameText = String(d.bom).toUpperCase() === String(d.sch).toUpperCase();
      var desc = 'BOM 声明 ' + d.bom + '，原理图标注 ' + d.sch +
        (d.equivalent && !sameText ? '（等价写法）' : '');
      return '<li class="cr-value">' +
        '<span class="cr-value__ref">' + BOM.escape(d.refs) + '</span>' +
        '<span class="cr-value__desc">' + BOM.escape(desc) + '</span>' + tag + '</li>';
    }).join('');
  }

  function renderStatusbar() {
    var m = data.metrics || {};
    BOM.app.setStatusbar(
      '核对完成 ' + (data.meta.createdAt || '') + ' · ' + m.total + ' 项问题 · 0 处文件改动'
    );
  }

  function renderAll() {
    renderBand();
    renderDistribution();
    renderChips();
    renderProblems();
    renderMissing();
    renderValues();
    renderStatusbar();
  }

  function renderEmptyState() {
    document.querySelector('[data-render="band"]').innerHTML = BOM.empty({
      icon: 'shield-check',
      title: '还没有核对结果',
      desc: '上传原理图、PCB 与待核对 BOM 后执行一次核对，问题清单、位号对照与值比对会展示在这里。',
      actions: [{ label: '去核对', href: '/check/setup', primary: true }]
    });
    // 没有结果时不展示空的清单骨架，避免误读为「零问题」
    Array.prototype.forEach.call(document.querySelectorAll('[data-section]'), function (el) {
      el.style.display = 'none';
    });
  }

  // ------------------------------------------------------------------ 抽屉
  function renderDrawer(no) {
    var host = document.querySelector('[data-render="drawer"]');
    if (!host) { return; }
    var problem = (data.problems || []).filter(function (p) { return p.no === no; })[0];
    if (!problem) {
      host.innerHTML = '';
      host.hidden = true;
      return;
    }
    var meta = pickCodes(problem.msg);

    host.innerHTML =
      '<div class="cd-overlay">' +
      '<div class="cd-scrim" data-drawer-close></div>' +
      '<aside class="cd-drawer" role="dialog" aria-modal="true" aria-labelledby="cd-drawer-title">' +
      '<div class="cd-drawer__head"><div>' +
      '<h2 id="cd-drawer-title" class="bom-h2">问题详情</h2>' +
      '<p class="bom-caption" style="margin-top:4px">第 ' + problem.no + ' 条 / 共 ' +
      data.problems.length + ' 条</p></div>' +
      '<button type="button" class="cd-close" data-drawer-close aria-label="关闭详情">' +
      BOM.svg('x') + '</button></div>' +
      '<div class="cd-drawer__body">' +
      '<dl class="cd-kv">' +
      '<dt>问题类型</dt><dd>' + BOM.escape(problem.kind) + '</dd>' +
      '<dt>级别</dt><dd>' + levelTag(problem.level) + '</dd>' +
      '<dt>BOM 行号</dt><dd>' + (problem.row ? '第 ' + problem.row + ' 行' : '全局（不针对具体行）') + '</dd>' +
      '<dt>涉及列</dt><dd>' + BOM.escape(problem.cols || '—') + '</dd>' +
      (meta.refs.length ? '<dt>涉及位号</dt><dd class="bom-mono">' + BOM.escape(meta.refs.join(' ')) + '</dd>' : '') +
      (meta.codes.length ? '<dt>物料编码</dt><dd class="bom-mono">' + BOM.escape(meta.codes.join(' ')) + '</dd>' : '') +
      '</dl>' +
      '<section aria-labelledby="cd-desc-title">' +
      '<h3 id="cd-desc-title" class="bom-h3">问题描述</h3>' +
      '<p class="bom-body" style="margin-top:8px">' + rich(problem.msg) + '</p></section>' +
      '<section aria-labelledby="cd-chain-title">' +
      '<h3 id="cd-chain-title" class="bom-h3">证据链</h3>' +
      '<p class="bom-caption" style="margin-top:6px">按「BOM 声明 → 基准比对 → 结论」逐层核对。</p>' +
      '<div class="cd-chain" style="margin-top:12px">' +
      chainRow('file-text', 'BOM 第 ' + (problem.row || '—') + ' 行', problem.kind + ' · ' + (problem.cols || '—'), '') +
      chainRow('database', '物料总表基准', '编码 / 名称以物料总表为准', '') +
      chainRow('circuit-board', 'PCB 与原理图基准', '封装以 PCB PATTERN 为准，位号以两者并集为准', 'cd-chain__row--success') +
      chainRow('check', '结论：' + problem.kind, problem.advice || '按建议修正后重新核对', 'cd-chain__row--result') +
      '</div></section>' +
      '<section aria-labelledby="cd-advice-title">' +
      '<h3 id="cd-advice-title" class="bom-h3">处理建议</h3>' +
      '<p class="bom-body" style="margin-top:8px">' + rich(problem.advice || '按上述结论修正 BOM 后重新核对。') + '</p>' +
      '</section></div>' +
      '<div class="cd-drawer__foot">' +
      '<button type="button" class="cr-btn" data-drawer-close>关闭</button>' +
      '<a class="cr-btn cd-btn--accent" href="/check/result?task=' + taskId + '">返回结果列表</a>' +
      '</div></aside></div>';
    host.hidden = false;

    Array.prototype.forEach.call(host.querySelectorAll('[data-drawer-close]'), function (el) {
      el.addEventListener('click', function () {
        host.hidden = true;
        host.innerHTML = '';
        history.replaceState(null, '', '/check/result?task=' + taskId);
      });
    });
  }

  function chainRow(icon, main, sub, modifier) {
    return '<div class="cd-chain__row ' + (modifier || '') + '">' +
      '<span class="cd-chain__icon" aria-hidden="true">' + BOM.svg(icon) + '</span>' +
      '<div><p class="cd-chain__main">' + BOM.escape(main) + '</p>' +
      '<p class="cd-chain__sub">' + BOM.escape(sub) + '</p></div></div>';
  }

  // ------------------------------------------------------------------ 数据
  function load(id) {
    BOM.overlay(true, '正在载入核对结果', '读取问题清单与位号对照');
    BOM.api.get('/api/tasks/' + id).then(function (res) {
      var task = res.task;
      if (task.status === 'running') {
        window.location.href = '/check/running?task=' + id;
        return;
      }
      if (task.status !== 'done') {
        BOM.overlay(false);
        document.querySelector('[data-render="band"]').innerHTML = BOM.empty({
          icon: 'triangle-alert',
          title: task.status === 'failed' ? '核对失败' : '核对已取消',
          desc: task.error || '本次任务没有产生结果。',
          actions: [{ label: '重新核对', href: '/check/setup', primary: true }]
        });
        return;
      }
      data = task.result || {};
      data.metrics = data.metrics || {};
      taskId = id;
      renderAll();
      BOM.overlay(false);
      if (isDetail) { renderDrawer(parseInt(BOM.query('no', '1'), 10) || 1); }
    }).catch(function (err) {
      BOM.overlay(false);
      BOM.toast('error', err.message);
      renderEmptyState();
    });
  }

  function boot() {
    if (booted) { return; }
    if (taskId) {
      booted = true;
      load(taskId);
      return;
    }
    BOM.app.onState(function (state) {
      if (booted) { return; }
      booted = true;
      if (state.lastCheck) { load(state.lastCheck.id); } else { renderEmptyState(); }
    });
  }

  // ------------------------------------------------------------------ 交互
  document.addEventListener('click', function (event) {
    var chip = event.target.closest('[data-level]');
    if (chip) {
      filterLevel = chip.getAttribute('data-level');
      renderChips();
      renderProblems();
      return;
    }
    var action = event.target.closest('[data-action]');
    if (action) {
      var kind = action.getAttribute('data-action');
      if (kind === 'download') {
        event.preventDefault();
        if (taskId) {
          BOM.desktop.saveTaskOutput(taskId, '/api/tasks/' + taskId + '/download');
        }
      } else if (kind === 'open-output') {
        BOM.desktop.openFolder('outputs');
      }
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.closest('[data-render="search"]')) {
      keyword = event.target.value.trim();
      renderProblems();
    }
  });

  boot();
})();
