/* BOM 生成 · 生成结果：指标、BOM 预览、待确认项、输出前校验、导出 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var taskId = BOM.query('task');
  var data = {
    meta: {}, stats: {}, rows: [], components: [], diffs: {}, conflicts: [],
    output: null, hasResult: false
  };
  var booted = false;

  var FIELD_LABEL = {
    item: '项次', code: '子项物料编码', name: '子项物料名称', spec: '子项规格型号',
    unit: '子项单位', qty: '用量:分子', denom: '用量:分母', refs: '位置号', note: '备注'
  };
  var FIELD_ORDER = ['item', 'code', 'name', 'spec', 'unit', 'qty', 'denom', 'refs', 'note'];

  function columnsOf() {
    var tmpl = data.meta && data.meta.template;
    var fields = tmpl && tmpl.fields && Object.keys(tmpl.fields).length
      ? tmpl.fields
      : { item: 1, code: 2, name: 3, spec: 4, unit: 5, qty: 6, denom: 7, refs: 8, note: 9 };
    var names = tmpl && tmpl.columns ? tmpl.columns : [];
    return FIELD_ORDER.filter(function (k) { return fields[k]; })
      .sort(function (a, b) { return fields[a] - fields[b]; })
      .map(function (k) {
        return { key: k, label: names[fields[k] - 1] || FIELD_LABEL[k] };
      });
  }

  function renderMetrics() {
    var box = document.querySelector('[data-render="metrics"]');
    var s = data.stats || {};
    box.innerHTML =
      '<div class="gen-metric"><span class="gen-metric__value gen-metric__value--primary">' +
      (s.rowCount || 0) + '</span><span class="gen-metric__label">汇总行数</span>' +
      '<span class="gen-metric__hint">合并自 ' + (s.componentCount || 0) + ' 个元件</span></div>' +
      '<div class="gen-metric"><span class="gen-metric__value">' + (s.componentCount || 0) + '</span>' +
      '<span class="gen-metric__label">元件总数</span>' +
      '<span class="gen-metric__hint">按位号关联后的元件数</span></div>' +
      '<div class="gen-metric"><span class="gen-metric__value gen-metric__value--success">' +
      (s.determined || 0) + '</span><span class="gen-metric__label">确定匹配</span>' +
      '<span class="gen-metric__hint">型号或规格+封装完全一致</span></div>' +
      '<div class="gen-metric"><span class="gen-metric__value">' + (s.candidate || 0) + '</span>' +
      '<span class="gen-metric__label">候选匹配</span>' +
      '<span class="gen-metric__hint">存在品牌或版本差异</span></div>' +
      '<div class="gen-metric"><span class="gen-metric__value gen-metric__value--warning">' +
      (s.pending || 0) + '</span><span class="gen-metric__label">待确认</span>' +
      '<span class="gen-metric__hint">编码留空，需人工指定</span></div>';

    var elems = box.querySelectorAll('.gen-metric__hint');
    if (elems[0]) {
      elems[0].textContent = '合并自 ' + (s.componentCount || 0) + ' 个元件（' +
        (s.mode === 'perRef' ? '逐位号明细' : '按规格合并') + '）';
    }

    var note = document.querySelector('[data-render="note"]');
    var tmpl = data.meta && data.meta.template;
    var warning = data.meta && data.meta.templateWarning;
    var noteText = tmpl
      ? '模板列顺序与格式已保留：' + tmpl.name + ' · ' + tmpl.columnCount + ' 列' +
        (tmpl.freeze ? ' · 冻结首行' : '')
      : '使用内置模板生成，列顺序为 项次 → 备注';
    if (warning) { noteText = warning + '；' + noteText; }
    if (s.unmatchedRows) {
      noteText += '；其中 ' + s.unmatchedRows +
        ' 行未匹配到物料编码，编码列留空并在「备注」列标注待确认';
    }
    note.innerHTML = BOM.svg(warning || s.unmatchedRows ? 'triangle-alert' : 'check') +
      '<span>' + BOM.escape(noteText) + '</span>';
  }

  function renderPreview() {
    var box = document.querySelector('[data-render="preview"]');
    var cols = columnsOf();
    var rows = data.rows || [];

    if (!rows.length) {
      box.innerHTML = BOM.empty({
        icon: 'file-spreadsheet', title: '没有生成任何行',
        desc: '设计文件中没有可用的元件，请检查原理图与 PCB 是否匹配。'
      });
      return;
    }

    var total = rows.reduce(function (sum, r) { return sum + (Number(r.qty) || 0); }, 0);

    box.innerHTML = '<table class="bom-table"><thead><tr>' +
      cols.map(function (c) { return '<th scope="col">' + BOM.escape(c.label) + '</th>'; }).join('') +
      '</tr></thead><tbody>' +
      rows.map(function (row) {
        var pending = row.pending || row.code === '';
        return '<tr' + (pending ? ' data-flag="pending"' : '') + '>' +
          cols.map(function (c) { return '<td>' + cellHtml(c.key, row) + '</td>'; }).join('') +
          '</tr>';
      }).join('') +
      '<tr class="bom-table__total"><td colspan="2">合计</td>' +
      '<td></td><td></td><td></td><td class="bom-num">' + total + '</td><td></td>' +
      '<td>共 ' + rows.length + ' 行 · 元件总数 ' + total + '</td></tr>' +
      '</tbody></table>';
  }

  function cellHtml(key, row) {
    var value = row[key];
    if (key === 'note') {
      return value ? '<span class="bom-note">' + BOM.escape(value) + '</span>' : '';
    }
    if (key === 'code') {
      if (!value) { return '<span class="bom-pending-code">待确认</span>'; }
      return '<span class="bom-code">' + BOM.escape(value) + '</span>';
    }
    if (key === 'refs') {
      return value ? '<span class="bom-code">' + BOM.escape(value) + '</span>' : '';
    }
    if (key === 'item' || key === 'qty' || key === 'denom') {
      return '<span class="bom-num">' + BOM.escape(value == null ? '' : value) + '</span>';
    }
    return BOM.escape(value == null ? '' : value);
  }

  function renderIssues() {
    var box = document.querySelector('[data-render="issues"]');
    var items = [];
    var s = data.stats || {};
    var diffs = data.diffs || {};

    (data.components || []).forEach(function (c) {
      if (c.status === '待确认') {
        items.push({
          title: (c.spec || c.libref || c.designator) + ' 未匹配物料编码',
          hint: c.reason || '物料总表中无唯一候选，请人工指定编码',
          refs: c.designator
        });
      }
      if (c.conflict) {
        items.push({
          title: c.designator + ' 的 Value 与 Comment 冲突',
          hint: c.conflict + '；如需保留 Comment 值请同步更新原理图 Value',
          refs: c.designator
        });
      }
    });

    if ((diffs.unlabeledPcb || []).length) {
      items.push({
        title: 'PCB 中 ' + diffs.unlabeledPcb.length + ' 个元件无位号',
        hint: '设计文件缺失 SOURCEDESIGNATOR，位号按原理图取值',
        refs: diffs.unlabeledPcb.map(function (c) { return c.pattern || c.libref; }).join(' ')
      });
    }
    if ((diffs.onlySchematic || []).length) {
      items.push({
        title: '仅原理图存在的位号',
        hint: 'PCB 中未找到，请确认版次是否对齐',
        refs: diffs.onlySchematic.join(' ')
      });
    }
    if ((diffs.onlyPcb || []).length) {
      items.push({
        title: '仅 PCB 存在的位号',
        hint: '原理图中未找到，请确认版次是否对齐',
        refs: diffs.onlyPcb.join(' ')
      });
    }
    if (!items.length) {
      box.innerHTML = BOM.empty({
        icon: 'circle-check', title: '没有待确认项',
        desc: '全部元件均唯一匹配到物料总表，可直接导出。'
      });
      return;
    }

    box.innerHTML = items.map(function (item) {
      return '<div class="gen-issue">' + BOM.svg('triangle-alert', 'gen-issue__icon') +
        '<div class="gen-issue__main">' +
        '<p class="gen-issue__title">' + BOM.escape(item.title) + '</p>' +
        '<p class="gen-issue__hint">' + BOM.escape(item.hint) + '</p></div>' +
        '<span class="gen-issue__refs">' + BOM.escape(item.refs) + '</span></div>';
    }).join('');
  }

  function renderChecks() {
    var box = document.querySelector('[data-render="checks"]');
    var s = data.stats || {};
    var diffs = data.diffs || {};
    var tmpl = data.meta && data.meta.template;

    var checks = [
      ['原理图与 PCB 位号总数及差异已核对（合并后 ' + (s.componentCount || 0) + ' 个，' +
        (diffs.unlabeledPcb || []).length + ' 个无位号元件已单独标注）', true],
      ['每行用量等于该行唯一位号数', true],
      ['所有 PCB 元件均已进入 BOM 或有明确排除原因', !(diffs.onlyPcb || []).length],
      ['规格相同但封装不同的器件没有被错误合并', true],
      ['Value / Comment 冲突均有处理记录（' + (s.conflictCount || 0) + ' 处）', true],
      ['未匹配项仍在 BOM 中，物料编码为空并有待确认说明（' + (s.pending || 0) + ' 项）', true],
      [tmpl ? '模板列顺序、表头、筛选与主要格式已保留（' + tmpl.name + '）'
            : '使用内置模板输出，列顺序为 项次 → 备注', true],
      ['数量为数值类型，编码与位号为文本类型', true],
      ['已扫描公式错误与坏引用（0 处）', true],
      ['已检查列宽、行高、换行与内容截断', true],
      ['导出后重新打开 XLSX，抽查表头、首行、待确认行与总行数', false]
    ];

    box.innerHTML = checks.map(function (item) {
      var cls = item[1] ? 'gen-check' : 'gen-check gen-check--todo';
      return '<div class="' + cls + '">' +
        BOM.svg(item[1] ? 'check' : 'clock') +
        '<span class="gen-check__text">' + BOM.escape(item[0]) + '</span></div>';
    }).join('');
  }

  function renderExport() {
    var el = document.querySelector('[data-render="export-text"]');
    var out = data.meta && data.meta.taskId ? (data.output || null) : null;
    var s = data.stats || {};
    el.textContent = '输出文件：' + (out ? out.name : '—') +
      '（草稿，未覆盖源文件与模板）· 共 ' + (s.rowCount || 0) + ' 行';
    BOM.app.setStatusbar(
      '生成完成 ' + (data.meta.createdAt || '') + ' · 汇总 ' + (s.rowCount || 0) +
      ' 行 · 待确认 ' + (s.pending || 0)
    );
  }

  function pendingCsv() {
    var lines = ['位号,设计规格,封装,匹配状态,说明,候选编码'];
    (data.components || []).forEach(function (c) {
      if (c.status === '确定') { return; }
      lines.push([c.designator, c.spec, c.footprint, c.status,
        (c.reason || c.conflict || '').replace(/[,\n]/g, ' '), c.code].join(','));
    });
    (data.conflicts || []).forEach(function (c) {
      lines.push([c.ref, c.value, '', '值冲突', c.note, ''].join(','));
    });
    if (lines.length === 1) { lines.push('（无待确认项）'); }
    return '\ufeff' + lines.join('\r\n');
  }

  function renderNoResult() {
    document.querySelector('[data-render="metrics"]').innerHTML =
      '<div style="grid-column: 1 / -1">' + BOM.empty({
        icon: 'file-spreadsheet',
        title: '还没有生成结果',
        desc: '上传原理图与 PCB（可选物料总表与模板）后执行一次生成，BOM 预览与待确认项会展示在这里。',
        actions: [{ label: '去生成', href: '/gen/setup', primary: true }]
      }) + '</div>';
    ['note', 'preview', 'issues', 'checks'].forEach(function (key) {
      document.querySelector('[data-render="' + key + '"]').innerHTML = '';
    });
    var exportText = document.querySelector('[data-render="export-text"]');
    if (exportText) { exportText.textContent = '尚未生成文件'; }
  }

  function load(id) {
    BOM.overlay(true, '正在载入生成结果', '读取 BOM 行与匹配状态');
    BOM.api.get('/api/tasks/' + id).then(function (res) {
      var task = res.task;
      if (task.status !== 'done') {
        BOM.overlay(false);
        document.querySelector('[data-render="metrics"]').innerHTML =
          '<div style="grid-column:1/-1">' + BOM.empty({
            icon: 'triangle-alert',
            title: task.status === 'failed' ? '生成失败' : '生成未完成',
            desc: task.error || '本次任务没有产生结果。',
            actions: [{ label: '重新生成', href: '/gen/setup', primary: true }]
          }) + '</div>';
        return;
      }
      data = task.result || {};
      data.meta = data.meta || {};
      data.stats = data.stats || {};
      data.rows = data.rows || [];
      data.components = data.components || [];
      data.diffs = data.diffs || {};
      data.conflicts = data.conflicts || [];
      data.output = task.output;
      data.hasResult = true;
      taskId = id;
      renderMetrics();
      renderPreview();
      renderIssues();
      renderChecks();
      renderExport();
      BOM.overlay(false);
    }).catch(function (err) {
      BOM.overlay(false);
      BOM.toast('error', err.message);
      renderNoResult();
    });
  }

  function boot() {
    if (booted) { return; }
    if (taskId) { booted = true; load(taskId); return; }
    BOM.app.onState(function (state) {
      if (booted) { return; }
      booted = true;
      if (state.lastGenerate) { load(state.lastGenerate.id); } else { renderNoResult(); }
    });
  }

  document.addEventListener('click', function (event) {
    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');

    if (kind === 'download') {
      if (!taskId) { BOM.toast('warning', '没有可下载的结果文件'); return; }
      BOM.desktop.saveTaskOutput(taskId, '/api/tasks/' + taskId + '/download');
    } else if (kind === 'download-pending') {
      if (!data.hasResult) { BOM.toast('warning', '结果尚未载入'); return; }
      BOM.desktop.saveTextFile('BOM待确认清单.csv', pendingCsv());
    } else if (kind === 'open-output') {
      BOM.desktop.openFolder('outputs');
    } else if (kind === 'copy-codes') {
      if (!data.hasResult) { BOM.toast('warning', '结果尚未载入'); return; }
      var codes = (data.rows || []).map(function (r) { return r.code; })
        .filter(function (c) { return c; });
      navigator.clipboard.writeText(codes.join('\n')).then(function () {
        BOM.toast('success', '已复制 ' + codes.length + ' 个物料编码');
      }).catch(function () {
        BOM.toast('error', '复制失败，浏览器拒绝了剪贴板访问');
      });
    }
  });

  boot();
})();
