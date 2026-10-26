/* 物料库与模板：指标、物料总表浏览、模板卡片、上传投放区 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var PAGE_SIZE = 10;
  var page = 1;
  var status = 'all';
  var query = '';
  var debounce = null;

  // ------------------------------------------------------------------ 指标
  function renderMetrics(state) {
    var box = document.querySelector('[data-render="metrics"]');
    var m = state.material;
    if (!m) {
      box.innerHTML = metric('—', '物料条目', '尚未导入物料总表', '') +
        metric('—', '有效物料', '—', '') +
        metric('—', '已禁用', '—', '') +
        metric('—', '最近导入', '请在下方投放区上传', 'lib-metrics__value--date');
      return;
    }
    box.innerHTML =
      metric(BOM.formatNumber(m.count), '物料条目', '来源：' + (m.name || m.source || '—'),
        'lib-metrics__value--primary') +
      metric(BOM.formatNumber(m.valid), '有效物料', '数据状态正常', 'lib-metrics__value--success') +
      metric(BOM.formatNumber(m.disabled), '已禁用', '不参与匹配', 'lib-metrics__value--error') +
      metric(m.syncedAt || '—', '最近导入',
        '表头第 ' + (m.headerRow || 1) + ' 行 · ' + (m.header ? m.header.length : 0) + ' 列',
        'lib-metrics__value--date');
  }

  function metric(value, label, sub, modifier) {
    return '<div class="lib-metrics__item">' +
      '<span class="lib-metrics__value bom-num ' + (modifier || '') + '">' + BOM.escape(value) + '</span>' +
      '<span class="lib-metrics__label">' + BOM.escape(label) + '</span>' +
      '<span class="lib-metrics__sub">' + BOM.escape(sub || '') + '</span></div>';
  }

  // ------------------------------------------------------------------ 筛选
  function renderFilters(state) {
    var box = document.querySelector('[data-render="filters"]');
    var m = state.material;
    var items = m
      ? [['all', '全部 ' + BOM.formatNumber(m.count)],
         ['valid', '有效 ' + BOM.formatNumber(m.valid)],
         ['disabled', '已禁用 ' + BOM.formatNumber(m.disabled)]]
      : [['all', '全部 0'], ['valid', '有效 0'], ['disabled', '已禁用 0']];
    box.innerHTML = items.map(function (item) {
      return '<button type="button" class="lib-chip bom-num" data-status="' + item[0] + '"' +
        (status === item[0] ? ' data-active="true"' : '') + '>' + BOM.escape(item[1]) + '</button>';
    }).join('');
  }

  function renderReady(state) {
    var box = document.querySelector('[data-render="ready"]');
    var m = state.material;
    if (!m) {
      box.setAttribute('data-visible', 'false');
      box.innerHTML = '';
      return;
    }
    box.setAttribute('data-visible', 'true');
    box.innerHTML = BOM.svg('check', 'lib-ready__icon') +
      '<span class="lib-ready__name bom-mono">' + BOM.escape(m.name || m.source || '') + '</span>' +
      '<span class="lib-ready__size bom-num">' + BOM.formatNumber(m.count) + ' 条</span>' +
      '<span class="lib-ready__state">已载入 · 有效 ' + BOM.formatNumber(m.valid) +
      ' / 禁用 ' + BOM.formatNumber(m.disabled) + '</span>';
  }

  // ------------------------------------------------------------------ 物料表
  function renderTable() {
    var box = document.querySelector('[data-render="table"]');
    var pager = document.querySelector('[data-render="pager"]');
    var state = BOM.app.state();

    if (!state || !state.material) {
      box.innerHTML = BOM.empty({
        icon: 'database',
        title: '还没有物料总表',
        desc: '导入 ERP 导出的 .xlsx 后，可用于「编码不存在」与「名称与总表不符」两类核对。',
        actions: [{ label: '导入物料总表', href: '#', primary: true }]
      });
      pager.innerHTML = '';
      return;
    }

    box.innerHTML = '<div class="bom-loading"><span class="bom-spinner"></span>正在读取物料总表…</div>';

    BOM.api.get('/api/library/materials?query=' + encodeURIComponent(query) +
      '&status=' + encodeURIComponent(status) + '&page=' + page + '&pageSize=' + PAGE_SIZE
    ).then(function (res) {
      if (!res.rows.length) {
        box.innerHTML = BOM.empty({
          icon: 'search', title: '没有匹配的物料',
          desc: '试着调整搜索关键词或数据状态筛选。'
        });
        pager.innerHTML = '';
        return;
      }
      box.innerHTML = '<table class="lib-table"><colgroup>' +
        '<col style="width:15%"><col style="width:25%"><col style="width:21%">' +
        '<col style="width:11%"><col style="width:8%"><col style="width:9%"><col style="width:11%">' +
        '</colgroup><thead><tr>' +
        '<th scope="col">物料编码</th><th scope="col">物料名称</th><th scope="col">规格型号</th>' +
        '<th scope="col">数据状态</th><th scope="col">禁用</th><th scope="col">基本单位</th>' +
        '<th scope="col">库存位置</th></tr></thead><tbody>' +
        res.rows.map(function (row) {
          var disabledCls = row.disabled ? ' class="lib-row--disabled"' : '';
          var statusTag = row.disabled
            ? '<span class="lib-tag lib-tag--disabled">已禁用</span>'
            : '<span class="lib-tag lib-tag--success">' + BOM.escape(row.status || '有效') + '</span>';
          return '<tr' + disabledCls + '>' +
            '<td><span class="lib-code bom-mono">' + BOM.escape(row.code) + '</span></td>' +
            '<td class="lib-cell-truncate">' + BOM.escape(row.name) + '</td>' +
            '<td class="lib-cell-truncate">' + BOM.escape(row.spec) + '</td>' +
            '<td>' + statusTag + '</td>' +
            '<td class="lib-off' + (row.disabled ? ' lib-off--yes' : '') + '">' +
            (row.disabled ? '是' : '否') + '</td>' +
            '<td>' + BOM.escape(row.unit || 'PCS') + '</td>' +
            '<td class="lib-cell-truncate">' + BOM.escape(row.location || '—') + '</td>' +
            '</tr>';
        }).join('') + '</tbody></table>';

      renderPager(res);
    }).catch(function (err) {
      box.innerHTML = BOM.empty({ icon: 'triangle-alert', title: '读取失败', desc: err.message });
      pager.innerHTML = '';
    });
  }

  function renderPager(res) {
    var pager = document.querySelector('[data-render="pager"]');
    var totalPages = Math.max(1, Math.ceil(res.total / res.pageSize));
    var start = (res.page - 1) * res.pageSize + 1;
    var end = Math.min(res.total, res.page * res.pageSize);

    var pages = [];
    for (var i = 1; i <= totalPages; i += 1) {
      if (i <= 2 || i > totalPages - 2 || Math.abs(i - res.page) <= 1) { pages.push(i); }
    }
    var unique = pages.filter(function (v, idx, arr) { return arr.indexOf(v) === idx; });
    var group = '<button type="button" class="lib-page" data-page="' + (res.page - 1) + '"' +
      (res.page <= 1 ? ' disabled style="opacity:.5"' : '') + '>上一页</button>';
    unique.forEach(function (p, idx) {
      if (idx > 0 && p - unique[idx - 1] > 1) {
        group += '<span class="lib-page__ellipsis" aria-hidden="true">…</span>';
      }
      group += '<button type="button" class="lib-page bom-num" data-page="' + p + '"' +
        (p === res.page ? ' data-active="true" aria-current="page"' : '') + '>' + p + '</button>';
    });
    group += '<button type="button" class="lib-page" data-page="' + (res.page + 1) + '"' +
      (res.page >= totalPages ? ' disabled style="opacity:.5"' : '') + '>下一页</button>';

    pager.innerHTML = '<span class="lib-pager__info bom-num">显示 ' + start + '–' + end +
      ' / 共 ' + BOM.formatNumber(res.total) + ' 条</span>' +
      '<div class="lib-pager__group" role="group" aria-label="物料总表分页">' + group + '</div>';
  }

  // ------------------------------------------------------------------ 模板
  var TEMPLATE_HINT = {
    item: '项次', code: '子项物料编码', name: '子项物料名称', spec: '子项规格型号',
    unit: '子项单位', qty: '用量:分子', denom: '用量:分母', refs: '位置号', note: '备注'
  };

  function renderTemplates(state) {
    var box = document.querySelector('[data-render="templates"]');
    var list = state.templates || [];
    if (!list.length) {
      box.innerHTML = BOM.empty({
        icon: 'file-spreadsheet',
        title: '还没有上传 BOM 模板',
        desc: '不传模板时将使用内置 9 列模板（项次 → 备注）。上传企业模板可保留自定义列结构与格式。'
      });
      return;
    }
    box.innerHTML = list.map(function (t) {
      var isDefault = t.id === state.defaultTemplateId;
      var mapped = Object.keys(t.fields || {}).map(function (k) { return TEMPLATE_HINT[k] || k; });
      return '<article class="lib-tpl">' +
        '<div class="lib-tpl__top">' + BOM.svg('file-spreadsheet', 'lib-tpl__icon') +
        '<h3 class="lib-tpl__name">' + BOM.escape(t.name) + '</h3>' +
        (isDefault ? '<span class="lib-tag lib-tag--primary lib-tpl__flag">默认</span>' : '') +
        '</div>' +
        '<p class="lib-tpl__meta">' +
        '<span>' + t.columnCount + ' 列 · 表头第 ' + t.headerRow + ' 行' +
        (t.freeze ? ' · 冻结首行' : '') + (t.filter ? ' · 含筛选' : '') + '</span>' +
        '<span>工作表 ' + BOM.escape(t.sheet || '—') + ' · 导入 ' + BOM.escape(t.syncedAt || '—') + '</span>' +
        '<span>已识别字段：' + BOM.escape(mapped.join(' / ') || '—') + '</span>' +
        '</p>' +
        '<div class="lib-tpl__foot">' +
        '<span class="lib-tpl__note">' + (isDefault ? '当前使用' : '新建 BOM 时套用') + '</span>' +
        (isDefault ? '' : '<button type="button" class="lib-btn lib-btn--ghost lib-btn--sm" data-default="' +
          t.id + '">设为默认</button>') +
        '<button type="button" class="lib-btn lib-btn--ghost lib-btn--sm" data-delete="' + t.id + '">删除</button>' +
        '</div></article>';
    }).join('');
  }

  // ------------------------------------------------------------------ 投放区
  function renderDrops() {
    var box = document.querySelector('[data-render="drops"]');
    box.innerHTML = '';
    [['master', '拖入或点击上传物料总表',
      '支持 ERP 导出的 .xlsx；导入后自动校验编码唯一性与名称重复项'],
     ['template', '拖入或点击上传 BOM 模板',
      '支持 .xlsx；模板只决定列结构与格式，不沿用模板内的物料内容与位号']
    ].forEach(function (item) {
      var kind = item[0];
      var cfg = BOM.slots.KINDS[kind];
      var drop = document.createElement('button');
      drop.type = 'button';
      drop.className = 'lib-drop';
      drop.setAttribute('data-loaded', 'false');
      drop.style.gridTemplateColumns = '40px minmax(0, 1fr) auto';
      drop.innerHTML = BOM.svg('upload', 'lib-drop__icon') +
        '<span class="lib-drop__text">' +
        '<span class="lib-drop__title" data-drop-title data-drop-label>' + BOM.escape(item[1]) + '</span>' +
        '<span class="lib-drop__hint bom-num" data-drop-hint>' + BOM.escape(item[2]) + '</span>' +
        '</span><span class="lib-drop__flag">待导入</span>';
      box.appendChild(drop);

      var input = document.createElement('input');
      input.type = 'file';
      input.className = 'lib-upload-input';
      // 用 data-upload-input 暴露给工具栏按钮：全页只有这一个物料总表选择器，
      // 避免出现「按钮点了但没人监听 change」的两套机制
      input.setAttribute('data-upload-input', kind);
      input.setAttribute('accept', cfg.accept);
      input.setAttribute('aria-label', cfg.title);
      box.appendChild(input);

      var title = drop.querySelector('[data-drop-title]');
      var hint = drop.querySelector('[data-drop-hint]');

      BOM.app.wireUpload({
        trigger: drop,
        input: input,
        kind: kind,
        onStart: function (file) {
          title.textContent = file.name;
          hint.textContent = BOM.formatSize(file.size) + ' · 正在上传并解析…';
          drop.setAttribute('data-loaded', 'true');
        },
        onDone: function (file, up) {
          if (up.status === '已解析') {
            title.textContent = file.name;
            hint.textContent = BOM.slots.describe(kind, up);
            BOM.toast('success', file.name + ' 解析完成：' +
              (kind === 'master'
                ? BOM.formatNumber(up.summary.count) + ' 条物料'
                : up.summary.columnCount + ' 列模板'));
          } else {
            hint.textContent = '解析失败：' + up.error;
            BOM.toast('error', file.name + ' 解析失败：' + up.error);
          }
        }
      });
    });
  }

  // ------------------------------------------------------------------ 交互
  document.addEventListener('click', function (event) {
    var chip = event.target.closest('[data-status]');
    if (chip) {
      status = chip.getAttribute('data-status');
      page = 1;
      renderFilters(BOM.app.state());
      renderTable();
      return;
    }

    var pageBtn = event.target.closest('[data-page]');
    if (pageBtn && !pageBtn.disabled) {
      page = Math.max(1, parseInt(pageBtn.getAttribute('data-page'), 10) || 1);
      renderTable();
      return;
    }

    var defBtn = event.target.closest('[data-default]');
    if (defBtn) {
      BOM.api.post('/api/library/templates/' + defBtn.getAttribute('data-default') + '/default', {})
        .then(function () {
          BOM.toast('success', '已设为默认模板');
          return BOM.app.loadState();
        }).catch(function (err) { BOM.toast('error', err.message); });
      return;
    }

    var delBtn = event.target.closest('[data-delete]');
    if (delBtn) {
      BOM.api.del('/api/library/templates/' + delBtn.getAttribute('data-delete'))
        .then(function () {
          BOM.toast('success', '模板已移除');
          return BOM.app.loadState();
        }).catch(function (err) { BOM.toast('error', err.message); });
      return;
    }

    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');
    if (kind === 'import-master') {
      event.preventDefault();
      var masterInput = document.querySelector('[data-upload-input="master"]');
      if (masterInput) {
        masterInput.click();
      } else {
        BOM.toast('error', '物料总表选择器未就绪，请刷新页面后重试');
      }
    } else if (kind === 'refresh') {
      BOM.app.loadState().then(function () {
        BOM.toast('success', '已刷新物料库状态');
      }).catch(function () {});
    }
  });

  document.addEventListener('input', function (event) {
    if (event.target.closest('[data-render="search"]')) {
      query = event.target.value.trim();
      page = 1;
      clearTimeout(debounce);
      debounce = setTimeout(renderTable, 220);
    }
  });

  renderDrops();

  BOM.app.onState(function (state) {
    renderMetrics(state);
    renderFilters(state);
    renderReady(state);
    renderTemplates(state);
    renderTable();
  });
})();
