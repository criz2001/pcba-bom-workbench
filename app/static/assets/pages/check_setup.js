/* BOM 校对 · 文件与规则：文件槽上传、规则开关、基准校验、启动核对 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var SLOTS = BOM.slots.KINDS;
  var ORDER = ['schematic', 'pcb', 'bom', 'master'];

  var RULES = [
    ['footprint', '封装不符', 'BOM 规格中的封装代号 ≠ PCB 实际 PATTERN', '严重'],
    ['name', '名称与总表不符', 'BOM 子项物料名称 ≠ 物料总表同编码名称', '严重'],
    ['missing', '位号缺失', 'PCB ∪ 原理图位号 − BOM 位号 ≠ 空集', '严重'],
    ['unknown', '位号不存在', 'BOM 位号 −（PCB ∪ 原理图）≠ 空集', '严重'],
    ['qty', '用量≠位号数', '用量分子 ≠ 位置号拆分后的位号个数', '严重'],
    ['nocode', '缺物料编码', '子项物料编码为空', '严重'],
    ['badcode', '编码不存在', '编码在物料总表中查不到', '严重'],
    ['format', '位号格式', '全角逗号 / 分号 / 连续逗号 / 多余空格', '一般'],
    ['item', '项次跳号或缺项次', '项次不连续，或有项次用量但无编码与名称', '一般']
  ];

  var OUTPUTS = [
    ['highlight', '在原 BOM 上高亮问题单元格', '严重红底 / 一般黄底，并新增「核对结果」列逐行说明'],
    ['problemSheet', '生成「问题清单」Sheet', '序号 / 级别 / 类型 / 行号 / 涉及列 / 描述 / 处理建议，冻结首行'],
    ['refSheet', '生成「位号对照」Sheet', '每个位号 × PCB 封装 / 原理图值 / 是否在 BOM / 结论'],
    ['valueSheet', '生成「值比对（需确认）」Sheet', '原理图与 BOM 常非同一版次，此项仅作提示，不判为严重问题', 'info'],
    ['verifyBaseline', '校验 PCB 与原理图基准一致性（推荐）', '不一致时先提醒版次未对齐']
  ];

  var enabled = {};
  RULES.forEach(function (r) { enabled[r[0]] = true; });
  var outputs = {};
  OUTPUTS.forEach(function (o) { outputs[o[0]] = true; });

  var baselineData = null;

  // ------------------------------------------------------------------ 文件槽
  function slotMarkup(cfg, upload) {
    var tplId = upload ? 'tpl-slot-filled' : 'tpl-slot-empty';
    var node = document.getElementById(tplId).content.firstElementChild.cloneNode(true);
    node.setAttribute('data-upload-slot', cfg.kind);

    var input = node.querySelector('[data-upload-input]');
    input.setAttribute('accept', cfg.accept);
    input.setAttribute('aria-label', cfg.label);

    var icon = node.querySelector('.ck-file__icon, .ck-drop__icon');
    icon.innerHTML = BOM.svg(cfg.icon);

    var dropTitle = node.querySelector('.ck-drop__title');
    var dropNote = node.querySelector('.ck-drop__note');
    if (dropTitle) {
      dropTitle.textContent = cfg.title;
      dropTitle.setAttribute('data-drop-label', '');
    }
    if (dropNote) { dropNote.textContent = cfg.note; }

    var name = node.querySelector('[data-upload-name]');
    var meta = node.querySelector('[data-upload-meta]');
    var tag = node.querySelector('[data-upload-tag]');

    if (upload) {
      name.textContent = upload.name;
      meta.textContent = BOM.slots.describe(cfg.kind, upload);
      var t = BOM.slots.tag(upload);
      tag.className = 'ck-tag ' + t.cls;
      tag.textContent = t.text;
      if (upload.status === '解析失败') {
        meta.textContent = '解析失败：' + upload.error;
      }
      node.setAttribute('data-upload-filled', 'true');
    } else {
      name.textContent = '未选择文件';
      meta.textContent = '已载入，等待解析';
    }
    return node;
  }

  function renderSlots(state) {
    var box = document.querySelector('[data-render="file-slots"]');
    if (!box) { return; }
    box.innerHTML = '';
    ORDER.forEach(function (kind) {
      var cfg = SLOTS[kind];
      var upload = state.selection[kind];
      var node = slotMarkup(cfg, upload);
      box.appendChild(node);

      BOM.app.wireUpload({
        trigger: node.querySelector('.ck-file__pick') || node.querySelector('.ck-drop'),
        input: node.querySelector('[data-upload-input]'),
        kind: kind,
        onStart: function (file) {
          var metaEl = node.querySelector('[data-upload-meta]');
          if (metaEl) { metaEl.textContent = BOM.formatSize(file.size) + ' · 正在上传并解析…'; }
        },
        onDone: function (file, upload) {
          BOM.toast(upload.status === '已解析' ? 'success' : 'error',
            file.name + ' ' + (upload.status === '已解析' ? '解析完成' : '解析失败：' + upload.error));
        }
      });

      // 「替换」按钮共用同一个 input
      Array.prototype.forEach.call(node.querySelectorAll('[data-upload-trigger]'), function (btn) {
        if (btn === node.querySelector('.ck-file__pick')) { return; }
        btn.addEventListener('click', function (event) {
          event.preventDefault();
          node.querySelector('[data-upload-input]').click();
        });
      });
    });
  }

  // ------------------------------------------------------------------ 规则
  function renderRules() {
    var box = document.querySelector('[data-render="rules"]');
    if (!box) { return; }
    box.innerHTML = RULES.map(function (r) {
      var level = r[3] === '一般'
        ? '<span class="ck-level ck-level--warning">一般</span>'
        : '<span class="ck-level ck-level--error">严重</span>';
      return '<li class="ck-rule" data-rule="' + r[0] + '">' +
        '<span class="ck-rule__mark" data-rule-mark>' + BOM.svg('square-check') + '</span>' +
        '<span class="ck-rule__text">' +
        '<span class="ck-rule__name">' + BOM.escape(r[1]) + '</span>' +
        '<span class="ck-rule__desc">' + BOM.escape(r[2]) + '</span></span>' +
        level + '</li>';
    }).join('');
  }

  function renderOutputs() {
    var box = document.querySelector('[data-render="outputs"]');
    if (!box) { return; }
    box.innerHTML = OUTPUTS.map(function (o) {
      var info = o[3] === 'info';
      return '<li class="ck-rule" data-output="' + o[0] + '">' +
        '<span class="ck-rule__mark' + (info ? ' ck-rule__mark--info' : '') + '" data-output-mark>' +
        BOM.svg(info ? 'info' : 'square-check') + '</span>' +
        '<span class="ck-rule__text">' +
        '<span class="ck-rule__name">' + BOM.escape(o[1]) + '</span>' +
        '<span class="ck-rule__desc' + (info ? ' ck-rule__desc--info' : '') + '">' +
        BOM.escape(o[2]) + '</span></span></li>';
    }).join('');
  }

  function bindToggles() {
    var rulesBox = document.querySelector('[data-render="rules"]');
    rulesBox.addEventListener('click', function (event) {
      var li = event.target.closest('[data-rule]');
      if (!li) { return; }
      var key = li.getAttribute('data-rule');
      enabled[key] = !enabled[key];
      li.style.opacity = enabled[key] ? '' : '0.45';
      li.querySelector('[data-rule-mark]').innerHTML = BOM.svg(enabled[key] ? 'square-check' : 'square');
    });

    var outBox = document.querySelector('[data-render="outputs"]');
    outBox.addEventListener('click', function (event) {
      var li = event.target.closest('[data-output]');
      if (!li) { return; }
      var key = li.getAttribute('data-output');
      outputs[key] = !outputs[key];
      if (li.querySelector('[data-output-mark]').querySelector('.lucide-info')) {
        li.style.opacity = outputs[key] ? '' : '0.45';
        return;
      }
      li.style.opacity = outputs[key] ? '' : '0.45';
      li.querySelector('[data-output-mark]').innerHTML = BOM.svg(outputs[key] ? 'square-check' : 'square');
    });
  }

  // ------------------------------------------------------------------ 确认条
  function renderConfirm(state) {
    var box = document.querySelector('[data-render="confirm"]');
    if (!box) { return; }

    var missing = [];
    if (!state.selection.schematic) { missing.push('原理图'); }
    if (!state.selection.pcb) { missing.push('PCB'); }
    if (!state.selection.bom) { missing.push('待核对 BOM'); }

    var statusHtml;
    var noteHtml;
    var dotClass = 'ck-dot';
    var dotStyle = '';

    if (!baselineData || !baselineData.ready) {
      dotStyle = 'background: var(--bom-subtle)';
      statusHtml = '基准一致性待校验：' +
        BOM.escape((baselineData && baselineData.reason) || missing.join('、') || '请先上传原理图与 PCB');
    } else if (baselineData.identical) {
      statusHtml = '基准一致性校验通过：PCB ' + baselineData.pcbCount + ' 个位号 / 原理图 ' +
        baselineData.schCount + ' 个位号，集合完全一致' +
        ((baselineData.unlabeledPcb || []).length
          ? ' · PCB 另有 ' + baselineData.unlabeledPcb.length + ' 个无位号元件（已在核对中标注）'
          : '');
    } else {
      dotStyle = 'background: var(--bom-state-warning)';
      statusHtml = '基准不一致：仅 PCB 有 ' + (baselineData.onlyPcb.join('、') || '无') +
        '；仅原理图有 ' + (baselineData.onlySchematic.join('、') || '无') + ' → 版次可能未对齐';
    }

    if (!state.material) {
      noteHtml = '物料总表未上传：将跳过「编码不存在」与「名称与总表不符」两类核对，其余 7 类正常执行';
    } else {
      noteHtml = '物料总表 ' + BOM.formatNumber(state.material.count) + ' 条（有效 ' +
        BOM.formatNumber(state.material.valid) + ' / 禁用 ' + BOM.formatNumber(state.material.disabled) +
        '）；模板 ' + (state.templates || []).length + ' 套可用';
    }

    box.innerHTML =
      '<p class="ck-confirm__status bom-num">' +
      '<i class="ck-dot" style="' + dotStyle + '" aria-hidden="true"></i>' + statusHtml + '</p>' +
      '<p class="ck-confirm__note">' + BOM.svg('info') + ' ' + BOM.escape(noteHtml) + '</p>' +
      '<div class="ck-confirm__actions">' +
      '<a href="/" class="ck-btn">' + BOM.svg('arrow-left') + '返回工作台</a>' +
      '<button type="button" class="ck-btn ck-btn--primary" data-action="run"' +
      (missing.length ? ' disabled style="opacity:.5;cursor:not-allowed"' : '') + '>开始核对</button>' +
      '</div>';
  }

  function refreshBaseline(state) {
    if (!state.selection.schematic || !state.selection.pcb) {
      baselineData = { ready: false, reason: '请先上传原理图与 PCB' };
      renderConfirm(state);
      return;
    }
    BOM.api.post('/api/baseline', {
      schematicId: state.selection.schematic.id,
      pcbId: state.selection.pcb.id
    }).then(function (data) {
      baselineData = data;
      renderConfirm(BOM.app.state());
    }).catch(function (err) {
      baselineData = { ready: false, reason: err.message };
      renderConfirm(BOM.app.state());
    });
  }

  // ------------------------------------------------------------------ 动作
  function runCheck() {
    var state = BOM.app.state();
    if (!state || !state.selection.bom) {
      BOM.toast('warning', '请先上传待核对 BOM');
      return;
    }
    var rules = RULES.filter(function (r) { return enabled[r[0]]; }).map(function (r) { return r[0]; });
    if (!rules.length) {
      BOM.toast('warning', '至少要开启一类核对规则');
      return;
    }
    BOM.overlay(true, '正在启动核对', '准备文件与规则，马上进入核对流程');
    BOM.api.post('/api/check/run', {
      options: {
        rules: rules,
        outputs: outputs,
        useMaster: true,
        verifyBaseline: outputs.verifyBaseline !== false
      }
    }).then(function (res) {
      window.location.href = '/check/running?task=' + res.taskId;
    }).catch(function (err) {
      BOM.overlay(false);
      BOM.toast('error', err.message);
    });
  }

  document.addEventListener('click', function (event) {
    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');

    if (kind === 'run') {
      runCheck();
    } else if (kind === 'load-last') {
      var state = BOM.app.state();
      if (state && state.lastCheck) {
        window.location.href = '/check/result?task=' + state.lastCheck.id;
      } else {
        BOM.toast('info', '还没有可查看的核对结果');
      }
    } else if (kind === 'clear-all') {
      BOM.api.post('/api/upload/clear', { kinds: ORDER }).then(function () {
        BOM.toast('success', '已清空 4 类输入');
        return BOM.app.loadState();
      }).then(function () {
        baselineData = null;
      }).catch(function (err) { BOM.toast('error', err.message); });
    }
  });

  // ------------------------------------------------------------------ 启动
  renderRules();
  renderOutputs();
  bindToggles();

  BOM.app.onState(function (state) {
    renderSlots(state);
    refreshBaseline(state);
    BOM.app.setStatusbar(
      '输入检查 4 类 · 已就绪 ' + ORDER.filter(function (k) { return state.selection[k]; }).length + ' 类'
    );
  });
})();
