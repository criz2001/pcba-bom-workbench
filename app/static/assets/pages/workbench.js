/* 工作台：运行指标 / 最近任务 / 问题分布 */

(function () {
  'use strict';

  var BOM = window.BOM;

  function metric(value, label, sub, modifier) {
    return '<div class="wb-metrics__item">' +
      '<span class="wb-metrics__value bom-num ' + (modifier || '') + '">' + value + '</span>' +
      '<span class="wb-metrics__label">' + BOM.escape(label) + '</span>' +
      '<span class="wb-metrics__sub">' + BOM.escape(sub || '') + '</span>' +
      '</div>';
  }

  function renderMetrics(state) {
    var box = document.querySelector('[data-render="metrics"]');
    if (!box) { return; }

    var check = state.lastCheck && state.lastCheck.status === 'done' ? state.lastCheck : null;
    var gen = state.lastGenerate && state.lastGenerate.status === 'done' ? state.lastGenerate : null;
    var cm = check ? check.metrics || {} : {};
    var gm = gen ? gen.metrics || {} : {};

    var sch = state.selection && state.selection.schematic ? state.selection.schematic.summary : null;
    var pcb = state.selection && state.selection.pcb ? state.selection.pcb.summary : null;
    var componentCount = (cm.pcbCount || (pcb && pcb.components) || (sch && sch.components) || 0);

    var material = state.material;
    box.innerHTML = [
      metric(componentCount ? BOM.formatNumber(componentCount) : '—', '设计元件',
        sch || pcb ? '原理图 ' + ((sch && sch.components) || 0) + ' / PCB ' + ((pcb && pcb.components) || 0)
                   : '尚未导入设计文件'),
      metric(cm.total != null ? BOM.formatNumber(cm.total) : '—', '已核对问题',
        cm.total != null ? '严重 ' + (cm.severe || 0) + ' · 一般 ' + (cm.normal || 0) : '尚未执行核对',
        'wb-metrics__value--primary'),
      metric(material ? BOM.formatNumber(material.count) : '—', '物料总表条目',
        material ? '有效 ' + BOM.formatNumber(material.valid) + ' · 禁用 ' + BOM.formatNumber(material.disabled)
                 : '未导入物料总表'),
      metric(gm.pending != null ? BOM.formatNumber(gm.pending) : '—', '未匹配待确认',
        gm.pending != null ? '生成 ' + (gm.rowCount || 0) + ' 行，需人工指定编码' : '尚未执行生成')
    ].join('');
  }

  var TYPE_LABEL = { check: 'BOM 校对', generate: 'BOM 生成' };

  function statusTag(task) {
    if (task.status === 'running') { return '<span class="bom-tag bom-tag--info">进行中</span>'; }
    if (task.status === 'failed') { return '<span class="bom-tag bom-tag--error">失败</span>'; }
    if (task.status === 'cancelled') { return '<span class="bom-tag">已取消</span>'; }
    return '';
  }

  function taskResult(task) {
    if (task.status === 'failed') { return task.error || '执行失败'; }
    if (task.status === 'running') { return '进度 ' + (task.progress || 0) + '%'; }
    var m = task.metrics || {};
    if (task.kind === 'check') { return (m.total != null ? m.total + ' 项问题' : '已完成'); }
    if (task.kind === 'generate') {
      return (m.rowCount != null ? m.rowCount + ' 行 · 待确认 ' + (m.pending || 0) : '已完成');
    }
    return '已完成';
  }

  function taskFiles(task) {
    var files = task.files || {};
    var parts = [];
    if (files.schematic) {
      parts.push('<span class="bom-mono">' + BOM.escape(files.schematic.name) + '</span>');
    }
    if (files.pcb) { parts.push('<span class="bom-mono">' + BOM.escape(files.pcb.name) + '</span>'); }
    if (!parts.length && files.bom) { parts.push('<span class="bom-mono">' + BOM.escape(files.bom.name) + '</span>'); }
    return parts.join('<span class="wb-file-sep"> + </span>') || '—';
  }

  function renderTasks(state) {
    var box = document.querySelector('[data-render="tasks"]');
    if (!box) { return; }
    var tasks = state.tasks || [];

    if (!tasks.length) {
      box.innerHTML = BOM.empty({
        icon: 'list-checks',
        title: '还没有任务记录',
        desc: '导入原理图、PCB 与 BOM 后执行一次核对或生成，任务会记录在这里。',
        actions: [
          { label: '开始核对', href: '/check/setup', primary: true },
          { label: '开始生成', href: '/gen/setup' }
        ]
      });
      return;
    }

    var rows = tasks.map(function (task) {
      var href = task.kind === 'check' ? '/check/result?task=' + task.id : '/gen/result?task=' + task.id;
      return '<tr data-task="' + task.id + '" data-href="' + href + '">' +
        '<td>' + BOM.escape(task.title || '未命名任务') + ' ' + statusTag(task) + '</td>' +
        '<td><span class="wb-tag">' + (TYPE_LABEL[task.kind] || task.kind) + '</span></td>' +
        '<td>' + taskFiles(task) + '</td>' +
        '<td>' + BOM.escape(taskResult(task)) + '</td>' +
        '<td class="bom-num">' + BOM.escape(task.finishedAt || task.createdAt || '') + '</td>' +
        '</tr>';
    }).join('');

    box.innerHTML = '<table class="wb-table" aria-label="最近任务记录">' +
      '<thead><tr><th scope="col">任务</th><th scope="col">类型</th>' +
      '<th scope="col">设计文件</th><th scope="col">结果</th><th scope="col">时间</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>';

    box.addEventListener('click', function (event) {
      var tr = event.target.closest('tr[data-href]');
      if (tr) { window.location.href = tr.getAttribute('data-href'); }
    });
  }

  function renderDistribution(state) {
    var box = document.querySelector('[data-render="distribution"]');
    var desc = document.querySelector('[data-bind="dist-desc"]');
    if (!box) { return; }

    var check = state.lastCheck && state.lastCheck.status === 'done' ? state.lastCheck : null;
    var dist = check && check.metrics ? check.metrics.distribution : null;

    if (!dist || !dist.length) {
      box.innerHTML = BOM.empty({
        icon: 'shield-check',
        title: '尚无核对结果',
        desc: '完成一次 BOM 三方核对后，这里会按 9 类规则汇总问题分布。',
        actions: [{ label: '去核对', href: '/check/setup', primary: true }]
      });
      if (desc) { desc.textContent = '尚未执行核对'; }
      return;
    }

    if (desc) {
      desc.textContent = '按 9 类核对规则汇总，共 ' + (check.metrics.total || 0) + ' 项 · ' +
        (check.finishedAt || check.createdAt || '');
    }
    box.innerHTML = dist.map(function (d) {
      var levelClass = d.level === '一般' ? 'wb-level--warning' : 'wb-level--error';
      return '<div class="wb-dist__row">' +
        '<span class="wb-dist__name">' + BOM.escape(d.kind) + '</span>' +
        '<span class="wb-level ' + levelClass + '">' + BOM.escape(d.level) + '</span>' +
        '<span class="wb-bar"><span class="wb-bar__fill" style="width:' + d.pct + '%"></span></span>' +
        '<span class="wb-dist__count">' + d.count + '</span>' +
        '<span class="wb-dist__pct">' + d.pct + '%</span>' +
        '</div>';
    }).join('');
  }

  function renderCardMeta(state) {
    var checkMeta = document.querySelector('[data-bind="check-meta"]');
    if (checkMeta) {
      var c = state.lastCheck;
      checkMeta.textContent = c && c.status === 'done'
        ? '上次核对 ' + (c.finishedAt || c.createdAt) + ' · ' + ((c.metrics || {}).total || 0) + ' 项问题'
        : '尚未执行核对';
    }
    var genMeta = document.querySelector('[data-bind="gen-meta"]');
    if (genMeta) {
      var g = state.lastGenerate;
      if (g && g.status === 'done') {
        var t = g.files && g.files.template ? g.files.template.name : '内置模板';
        genMeta.textContent = '上次生成 ' + (g.finishedAt || g.createdAt) + ' · ' + t;
      } else {
        genMeta.textContent = '尚未执行生成';
      }
    }
  }

  BOM.app.onState(function (state) {
    renderMetrics(state);
    renderTasks(state);
    renderDistribution(state);
    renderCardMeta(state);
  });

  document.addEventListener('click', function (event) {
    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');
    if (kind === 'import') {
      window.location.href = '/check/setup';
    } else if (kind === 'refresh') {
      BOM.app.loadState().then(function () {
        BOM.toast('success', '状态已刷新');
      }).catch(function () {});
    }
  });
})();
