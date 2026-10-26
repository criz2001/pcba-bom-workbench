/* BOM 生成 · 文件与模板：上传、预览提取结果、输出设置、启动生成 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var SLOTS = BOM.slots.KINDS;
  var mode = 'merge';
  var preview = null;

  var SOURCE_OF = {
    item: '从 1 连续编号',
    code: '物料总表编码；待确认项留空',
    name: '物料总表正式名称；未匹配时用设计规格描述',
    spec: '物料总表规格字段',
    unit: '物料总表基本单位',
    qty: '汇总数量',
    denom: '默认 1',
    refs: '空格分隔的位号列表',
    note: '字段冲突、候选依据与待确认事项',
    parentCode: '模板固定值（不沿用示例内容）',
    bomVersion: '模板固定值（不沿用示例内容）',
    bomShortName: '模板固定值（不沿用示例内容）',
    status: '模板固定值（不沿用示例内容）'
  };

  // ------------------------------------------------------------------ 文件槽
  function fileSlot(cfg, upload, tagOverride) {
    var tag = tagOverride || BOM.slots.tag(upload);
    var tagCls = String(tag.cls || '').replace('ck-tag--', 'gs-tag--');
    var name = upload ? upload.name : '未选择文件';
    var meta = upload ? BOM.slots.describe(cfg.kind, upload)
                      : (cfg.kind === 'template' ? '可选；不选则使用内置 9 列模板' : '尚未上传');
    if (upload && upload.status === '解析失败') { meta = '解析失败：' + upload.error; }

    var node = document.createElement('div');
    node.className = 'gs-slot';
    node.setAttribute('data-upload-slot', cfg.kind);
    node.innerHTML =
      '<input type="file" class="gs-upload-input" data-upload-input aria-hidden="true" tabindex="-1">' +
      '<button type="button" class="gs-file" data-upload-trigger aria-label="上传' + BOM.escape(cfg.label) + '">' +
      '<span class="gs-file__icon" aria-hidden="true">' + BOM.svg(cfg.icon) + '</span>' +
      '<span class="gs-file__body">' +
      '<span class="gs-file__name bom-mono">' + BOM.escape(name) + '</span>' +
      '<span class="gs-file__meta bom-num">' + BOM.escape(meta) + '</span></span>' +
      '<span class="gs-file__aside">' +
      '<span class="gs-file__pick-hint" aria-hidden="true">更换</span>' +
      '<span class="gs-tag ' + tagCls + '">' + BOM.escape(tag.text) + '</span>' +
      '</span></button>';

    node.querySelector('[data-upload-input]').setAttribute('accept', cfg.accept);
    return node;
  }

  function emptyDrop(cfg) {
    var node = document.createElement('div');
    node.className = 'gs-slot';
    node.setAttribute('data-upload-slot', cfg.kind);
    node.innerHTML =
      '<input type="file" class="gs-upload-input" data-upload-input aria-hidden="true" tabindex="-1">' +
      '<button type="button" class="gs-drop" data-upload-trigger aria-label="上传' + BOM.escape(cfg.label) + '">' +
      '<span class="gs-drop__icon" aria-hidden="true">' + BOM.svg('upload') + '</span>' +
      '<span class="gs-drop__text">' +
      '<span class="gs-drop__title" data-drop-label>' + BOM.escape(cfg.title) + '</span>' +
      '<span class="gs-drop__note">' + BOM.escape(cfg.note) + '</span></span>' +
      '<span class="gs-file__aside gs-drop__aside"><span class="gs-tag gs-tag--info">待解析</span></span>' +
      '</button>';
    node.querySelector('[data-upload-input]').setAttribute('accept', cfg.accept);
    return node;
  }

  function mount(container, cfg, upload, useDrop) {
    var node = upload ? fileSlot(cfg, upload)
      : (useDrop ? emptyDrop(cfg) : fileSlot(cfg, null, { text: '待上传', cls: 'gs-tag--info' }));
    container.appendChild(node);

    BOM.app.wireUpload({
      trigger: node.querySelector('[data-upload-trigger]'),
      input: node.querySelector('[data-upload-input]'),
      kind: cfg.kind,
      onStart: function (file) {
        var meta = node.querySelector('.gs-file__meta');
        if (meta) { meta.textContent = BOM.formatSize(file.size) + ' · 正在上传并解析…'; }
      },
      onDone: function (file, up) {
        BOM.toast(up.status === '已解析' ? 'success' : 'error',
          file.name + ' ' + (up.status === '已解析' ? '解析完成' : '解析失败：' + up.error));
      }
    });
  }

  function renderSlots(state) {
    var design = document.querySelector('[data-render="design-slots"]');
    var assets = document.querySelector('[data-render="asset-slots"]');
    design.innerHTML = '';
    assets.innerHTML = '';

    ['schematic', 'pcb'].forEach(function (kind) {
      mount(design, SLOTS[kind], state.selection[kind], false);
    });

    var masterCfg = SLOTS.master;
    if (state.material) {
      var upload = state.selection.master || {
        name: state.material.name || state.material.source,
        size: state.material.size || 0,
        status: '已解析',
        summary: state.material
      };
      mount(assets, masterCfg, upload, false);
    } else {
      mount(assets, masterCfg, null, true);
    }

    var tmplCfg = SLOTS.template;
    var tpl = (state.templates || []).filter(function (t) { return t.id === state.defaultTemplateId; })[0]
      || (state.templates || [])[0];
    if (tpl) {
      mount(assets, tmplCfg, {
        name: tpl.name, size: tpl.size, status: '已解析', summary: tpl
      }, false);
    } else {
      mount(assets, tmplCfg, null, true);
    }
  }

  // ------------------------------------------------------------------ 输出设置
  function renderModes() {
    var box = document.querySelector('[data-render="modes"]');
    var counts = preview ? preview.counts : null;
    var mergeRows = preview ? preview.mergeRowCount : null;
    var perRows = preview ? preview.perRefRowCount : null;

    var items = [
      ['merge', '按规格 + 封装 + 编码合并为一行，汇总数量与位号',
        mergeRows != null ? '本次预计 ' + mergeRows + ' 行' : '预计行数将在文件就绪后计算'],
      ['perRef', '每个位号单独一行（逐位号明细）',
        perRows != null ? '本次预计 ' + perRows + ' 行' : '预计行数将在文件就绪后计算']
    ];

    box.innerHTML = items.map(function (item) {
      var on = mode === item[0];
      return '<button type="button" class="gs-radio" role="radio" aria-checked="' + (on ? 'true' : 'false') +
        '" data-mode="' + item[0] + '">' +
        BOM.svg(on ? 'circle-dot' : 'circle', 'gs-radio__mark') +
        '<span class="gs-radio__text">' +
        '<span class="gs-radio__label">' + BOM.escape(item[1]) + '</span>' +
        '<span class="gs-radio__note bom-num">' + BOM.escape(item[2]) + '</span></span></button>';
    }).join('');

    if (counts) {
      BOM.app.setStatusbar('设计元件 ' + preview.componentCount + ' · 预计输出 ' + mergeRows + ' 行');
    }
  }

  function renderRules() {
    var spec = (preview && preview.specRule) ||
      ['原理图 Value', '原理图 Comment', '器件描述 / 库引用'];
    var fp = (preview && preview.footprintRule) ||
      ['PCB 实际 PATTERN', '原理图 PCB 模型', '库引用推断'];
    document.querySelector('[data-render="spec-rule"]').innerHTML = spec.map(function (t, i) {
      return '<li class="gs-order__item"><span class="gs-order__idx bom-num">' + (i + 1) + '</span>' +
        '<span class="gs-order__text">' + BOM.escape(t) + '</span></li>';
    }).join('');
    document.querySelector('[data-render="fp-rule"]').innerHTML = fp.map(function (t, i) {
      return '<li class="gs-order__item"><span class="gs-order__idx bom-num">' + (i + 1) + '</span>' +
        '<span class="gs-order__text">' + BOM.escape(t) + '</span></li>';
    }).join('');
  }

  // ------------------------------------------------------------------ 预览
  function renderExtract() {
    var box = document.querySelector('[data-render="extract"]');
    if (!preview || !preview.preview.length) {
      box.innerHTML = BOM.empty({
        icon: 'file-code-2',
        title: '还没有提取结果',
        desc: '上传原理图与 PCB 后，这里会显示位号、Value / Comment、PCB 封装与取值依据。',
        actions: [{ label: '去物料库', href: '/library' }]
      });
      return;
    }
    box.innerHTML = '<table class="gs-table gs-table--extract">' +
      '<caption class="sr-only">原理图与 PCB 提取到的字段取值</caption>' +
      '<thead><tr><th scope="col">位号</th><th scope="col">库引用</th><th scope="col">Value</th>' +
      '<th scope="col">Comment</th><th scope="col">PCB 封装</th><th scope="col">取值依据</th></tr></thead><tbody>' +
      preview.preview.map(function (c) {
        var basis = c.specBasis + (c.footprintBasis ? ' / ' + c.footprintBasis : '');
        return '<tr>' +
          '<td class="bom-mono">' + BOM.escape(c.ref) + '</td>' +
          '<td class="bom-mono">' + BOM.escape(c.libref || '—') + '</td>' +
          '<td class="bom-mono">' + BOM.escape(c.value || '—') + '</td>' +
          '<td class="bom-mono">' + BOM.escape(c.comment || '—') + '</td>' +
          '<td class="bom-mono">' + BOM.escape(c.footprint || '—') + '</td>' +
          '<td' + (c.conflict ? ' class="gs-td--warn"' : '') + '>' +
          '<span class="gs-cell"><span>' + BOM.escape(c.specBasis) + '</span>' +
          '<span class="gs-cell__sub">' + BOM.escape(c.conflict || basis) + '</span></span></td>' +
          '</tr>';
      }).join('') + '</tbody></table>';
  }

  function renderMap() {
    var box = document.querySelector('[data-render="map"]');
    var sub = document.querySelector('[data-render="map-sub"]');
    var tmpl = preview && preview.template;
    if (!tmpl) {
      box.innerHTML = BOM.empty({
        icon: 'file-spreadsheet',
        title: '未选择模板',
        desc: '将使用内置 9 列模板生成 BOM。可在「物料库与模板」页上传企业模板。',
        actions: [{ label: '去上传模板', href: '/library', primary: true }]
      });
      if (sub) { sub.textContent = '尚未选择模板'; }
      return;
    }
    if (sub) {
      sub.textContent = '来自 ' + tmpl.name + '，列顺序已锁定';
    }

    var byIndex = {};
    Object.keys(tmpl.fields || {}).forEach(function (key) { byIndex[tmpl.fields[key]] = key; });

    box.innerHTML = '<table class="gs-table gs-table--map">' +
      '<caption class="sr-only">BOM 模板列与取值来源的对应关系</caption>' +
      '<thead><tr><th scope="col">模板列</th><th scope="col">取值来源</th></tr></thead><tbody>' +
      (tmpl.columns || []).map(function (name, i) {
        var key = byIndex[i + 1];
        return '<tr><td class="gs-map__col bom-mono">' + BOM.escape(name) + '</td>' +
          '<td>' + BOM.escape(SOURCE_OF[key] || '模板固定值（不沿用示例内容）') + '</td></tr>';
      }).join('') + '</tbody></table>';
  }

  function renderConfirm() {
    var box = document.querySelector('[data-render="confirm"]');
    var state = BOM.app.state() || {};
    var missing = [];
    if (!state.selection.schematic) { missing.push('原理图'); }
    if (!state.selection.pcb) { missing.push('PCB'); }

    var status;
    if (!preview) {
      status = missing.length
        ? '尚未就绪：请先上传 ' + missing.join('、')
        : '正在计算提取结果与匹配情况…';
    } else {
      status = '设计元件 ' + preview.componentCount + ' 个 · 确定匹配 ' + preview.counts.determined +
        ' · 候选 ' + preview.counts.candidate + ' · 待确认 ' + preview.counts.pending +
        '（未匹配项仍会出现在 BOM 中并标记待确认）';
    }

    box.innerHTML =
      '<p class="gs-confirm__status">' + BOM.svg('info', 'gs-confirm__info') +
      '<span>' + BOM.escape(status) + '</span></p>' +
      '<div class="gs-confirm__actions">' +
      '<a href="/" class="gs-btn">' + BOM.svg('arrow-left') + '返回工作台</a>' +
      '<button type="button" class="gs-btn gs-btn--primary" data-action="run"' +
      (missing.length ? ' disabled style="opacity:.5;cursor:not-allowed"' : '') +
      '>开始生成</button></div>';
  }

  function loadPreview() {
    var state = BOM.app.state();
    if (!state || !state.selection.schematic || !state.selection.pcb) {
      preview = null;
      renderModes();
      renderExtract();
      renderMap();
      renderConfirm();
      return;
    }
    BOM.api.post('/api/generate/preview', {
      schematicId: state.selection.schematic.id,
      pcbId: state.selection.pcb.id
    }).then(function (res) {
      preview = res;
      renderModes();
      renderRules();
      renderExtract();
      renderMap();
      renderConfirm();
    }).catch(function (err) {
      preview = null;
      renderExtract();
      renderMap();
      renderConfirm();
      BOM.toast('error', '提取预览失败：' + err.message);
    });
  }

  // ------------------------------------------------------------------ 交互
  document.addEventListener('click', function (event) {
    var radio = event.target.closest('[data-mode]');
    if (radio) {
      mode = radio.getAttribute('data-mode');
      renderModes();
      return;
    }
    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');

    if (kind === 'run') {
      if (action.disabled) { return; }
      BOM.overlay(true, '正在启动生成', '解析设计文件并匹配物料总表');
      BOM.api.post('/api/generate/run', {
        mode: mode,
        options: {}
      }).then(function (res) {
        window.location.href = '/gen/result?task=' + res.taskId;
      }).catch(function (err) {
        BOM.overlay(false);
        BOM.toast('error', err.message);
      });
    } else if (kind === 'reset') {
      mode = 'merge';
      renderModes();
      loadPreview();
      BOM.toast('info', '已重置输出设置');
    }
  });

  renderRules();
  BOM.app.onState(function (state) {
    renderSlots(state);
    loadPreview();
  });
})();
