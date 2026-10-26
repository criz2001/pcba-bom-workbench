/* ==========================================================================
   PCBA BOM 工作台 — 应用外壳脚本
   职责：主题切换、移动端抽屉导航、导航跳转与激活态、全局状态同步（/api/state）、
        通用文件槽交互。各页面的业务逻辑放在 pages/<page>.js。
   ========================================================================== */

(function () {
  'use strict';

  var NAV_HREF = {
    workbench: '/',
    check: '/check/setup',
    generate: '/gen/setup',
    library: '/library'
  };
  var NAV_PARENT = {
    'check-running': 'check',
    'check-result': 'check',
    'check-detail': 'check',
    'gen-result': 'generate'
  };

  // ---------------------------------------------------------------- 主题
  var THEME_KEY = 'bom-color-scheme';
  var root = document.documentElement;

  function applyTheme(mode) {
    root.classList.remove('light', 'dark');
    root.classList.add(mode === 'dark' ? 'dark' : 'light');
  }

  try {
    var saved = window.localStorage.getItem(THEME_KEY);
    if (saved === 'dark' || saved === 'light') { applyTheme(saved); }
  } catch (e) { /* 隐私模式下忽略 */ }

  document.addEventListener('click', function (event) {
    var btn = event.target.closest && event.target.closest('[data-theme-toggle]');
    if (!btn) { return; }
    var next = root.classList.contains('dark') ? 'light' : 'dark';
    applyTheme(next);
    try { window.localStorage.setItem(THEME_KEY, next); } catch (e) { /* 忽略 */ }
  });

  // ---------------------------------------------------------------- 导航
  var page = root.getAttribute('data-page') || 'workbench';
  var activeKey = NAV_PARENT[page] || page;

  Array.prototype.forEach.call(document.querySelectorAll('[data-nav-key]'), function (item) {
    var key = item.getAttribute('data-nav-key');
    if (NAV_HREF[key]) { item.setAttribute('href', NAV_HREF[key]); }
    if (key === activeKey) {
      item.setAttribute('data-active', 'true');
      item.setAttribute('aria-current', 'page');
    } else {
      item.removeAttribute('data-active');
      item.removeAttribute('aria-current');
    }
  });

  // ------------------------------------------------- 移动端抽屉导航
  var titlebarActions = document.querySelector('.app-titlebar__actions');
  var sidebar = document.querySelector('.app-sidebar');
  var backdrop = document.createElement('div');

  if (titlebarActions && sidebar) {
    var toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'app-nav-toggle';
    toggle.setAttribute('aria-label', '打开导航菜单');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.innerHTML = window.BOM.svg('menu');
    titlebarActions.insertBefore(toggle, titlebarActions.firstChild);

    backdrop.className = 'app-backdrop';
    backdrop.setAttribute('data-visible', 'false');
    document.body.appendChild(backdrop);

    var setOpen = function (open) {
      sidebar.setAttribute('data-open', open ? 'true' : 'false');
      backdrop.setAttribute('data-visible', open ? 'true' : 'false');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    };

    toggle.addEventListener('click', function () {
      setOpen(sidebar.getAttribute('data-open') !== 'true');
    });
    backdrop.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { setOpen(false); }
    });
    sidebar.addEventListener('click', function (event) {
      if (event.target.closest && event.target.closest('a')) { setOpen(false); }
    });
  }

  // ---------------------------------------------------------------- 状态
  var state = null;
  var listeners = [];

  function text(selector, value) {
    var el = document.querySelector(selector);
    if (el && value != null) { el.textContent = value; }
  }

  function applyState(next) {
    state = next;

    var material = next.material;
    var materialText = material ? window.BOM.formatNumber(material.count) + ' 条' : '未载入';
    var templateText = (next.templates ? next.templates.length : 0) + ' 套';

    text('[data-bind="material-count"]', materialText);
    text('[data-bind="template-count"]', templateText);
    text('[data-bind="engine-state"]', '就绪');

    var project = next.lastCheck || next.lastGenerate;
    var chip = document.querySelector('.app-titlebar__project');
    if (chip) {
      var name = '';
      if (next.selection && next.selection.schematic) {
        name = next.selection.schematic.name.replace(/\.[^.]+$/, '');
      } else if (project && project.files && project.files.schematic) {
        name = project.files.schematic.name.replace(/\.[^.]+$/, '');
      }
      chip.textContent = name || '未导入工程';
    }

    text('[data-bind="statusbar-left"]',
      '核对引擎就绪 · 物料总表 ' + materialText + ' · 模板 ' + templateText);

    listeners.forEach(function (fn) {
      try { fn(next); } catch (e) { /* 单个页面渲染失败不影响外壳 */ }
    });
  }

  function loadState() {
    return window.BOM.api.get('/api/state').then(function (data) {
      applyState(data);
      return data;
    }).catch(function (err) {
      window.BOM.toast('error', '无法读取工作区状态：' + err.message);
      throw err;
    });
  }

  // ---------------------------------------------------------------- 通用文件槽
  /**
   * 绑定一个文件槽：点击 / 回车选择文件，支持拖拽，选中后上传并回填状态。
   * @param {Object} cfg {trigger, input, kind, onDone, onError}
   */
  function wireUpload(cfg) {
    var trigger = cfg.trigger;
    var input = cfg.input;
    if (!trigger || !input) { return; }

    var depth = 0;

    function clearDrag() {
      depth = 0;
      trigger.classList.remove('is-dragover');
    }

    function pick() { input.click(); }

    trigger.addEventListener('click', function (event) {
      event.preventDefault();
      pick();
    });

    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      input.value = '';
      if (file) { send(file); }
    });

    function send(file) {
      if (cfg.onStart) { cfg.onStart(file); }
      window.BOM.api.upload(cfg.kind, file).then(function (res) {
        if (cfg.onDone) { cfg.onDone(file, res.upload, res); }
        loadState().catch(function () {});
      }).catch(function (err) {
        if (cfg.onError) { cfg.onError(file, err); }
        window.BOM.toast('error', file.name + '：' + err.message);
        loadState().catch(function () {});
      });
    }

    ['dragenter', 'dragover'].forEach(function (type) {
      trigger.addEventListener(type, function (event) {
        event.preventDefault();
        if (type === 'dragenter') { depth += 1; }
        if (event.dataTransfer) { event.dataTransfer.dropEffect = 'copy'; }
        trigger.classList.add('is-dragover');
      });
    });

    trigger.addEventListener('dragleave', function () {
      depth = Math.max(0, depth - 1);
      if (depth === 0) { clearDrag(); }
    });

    trigger.addEventListener('drop', function (event) {
      event.preventDefault();
      clearDrag();
      var dt = event.dataTransfer;
      var file = dt && dt.files && dt.files[0];
      if (file) { send(file); }
    });
  }

  document.addEventListener('dragover', function (event) { event.preventDefault(); });
  document.addEventListener('drop', function (event) {
    if (!event.target.closest || !event.target.closest('[data-upload-slot], .ck-drop, .gs-file, .lib-drop')) {
      event.preventDefault();
    }
  });

  // ---------------------------------------------------------------- 导出
  window.BOM.app = {
    page: page,
    navKey: activeKey,
    state: function () { return state; },
    loadState: loadState,
    onState: function (fn) { listeners.push(fn); if (state) { fn(state); } },
    wireUpload: wireUpload,
    setStatusbar: function (contextText, metaText) {
      var right = document.querySelector('.app-statusbar__right');
      if (!right) { return; }
      var first = right.querySelector('[data-bind="statusbar-context"]');
      var last = right.querySelector('[data-bind="statusbar-meta"]');
      if (first && contextText != null) { first.textContent = contextText; }
      if (last && metaText != null) { last.textContent = metaText; }
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    loadState().catch(function () {});
  });

  // ----------------------------------------- 桌面窗口模式（pywebview）增强
  // 只在独立窗口里显示的原生能力入口（打开输出目录等）；浏览器模式下保持隐藏
  window.BOM.desktop.onReady(function (api) {
    Array.prototype.forEach.call(document.querySelectorAll('[data-desktop-only]'), function (el) {
      el.hidden = !api;
    });
    var mode = document.querySelector('[data-bind="mode"]');
    if (mode) { mode.textContent = api ? '桌面窗口' : '本地模式'; }
    if (!api) { return; }

    document.documentElement.setAttribute('data-desktop', 'true');

    // WebView2 不转发系统的文件拖放，桌面模式下把投放区文案改成「点击选择」。
    // 投放区可能由页面脚本在本文件之后渲染，因此用观察器覆盖后续新增的节点。
    function relabel(el) {
      if (el && el.textContent.indexOf('拖入或点击上传') >= 0) {
        el.textContent = el.textContent.replace('拖入或点击上传', '点击选择');
      }
    }

    function scan(root) {
      if (!root || root.nodeType !== 1) { return; }
      if (root.hasAttribute && root.hasAttribute('data-drop-label')) { relabel(root); }
      if (root.querySelectorAll) {
        Array.prototype.forEach.call(root.querySelectorAll('[data-drop-label]'), relabel);
      }
    }

    scan(document.body);
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        Array.prototype.forEach.call(record.addedNodes || [], scan);
      });
    }).observe(document.body, { childList: true, subtree: true });
  });
})();
