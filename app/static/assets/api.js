/* ==========================================================================
   PCBA BOM 工作台 — 前端基础库
   · BOM.api      ：REST 调用（统一错误处理）
   · BOM.icon/svg ：内联 Lucide 图标（本地内联，不依赖 CDN，离线可用）
   · BOM.toast    ：轻提示
   · BOM.overlay  ：阻塞式进度遮罩
   · BOM.empty    ：空状态
   ========================================================================== */

(function () {
  'use strict';

  var ICONS = {
    check: '<path d="M20 6 9 17l-5-5"/>',
    'circle-check': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    'triangle-alert':
      '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>' +
      '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    'circle-x': '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    'arrow-right': '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    'arrow-left': '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    'chevron-right': '<path d="m9 18 6-6-6-6"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    upload: '<path d="M12 3v12"/><path d="m17 8-5-5-5 5"/>' +
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>',
    download: '<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
      '<path d="m7 10 5 5 5-5"/>',
    'refresh-cw':
      '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>' +
      '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    trash: '<path d="M10 11v6"/><path d="M14 11v6"/>' +
      '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>' +
      '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>' +
      '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11"/>',
    'folder-open':
      '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>',
    database:
      '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    'file-spreadsheet':
      '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>' +
      '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
    menu: '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>',
    play: '<polygon points="6 3 20 12 6 21 6 3"/>',
    pause: '<rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/>',
    'list-checks':
      '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    'shield-check':
      '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>' +
      '<path d="m9 12 2 2 4-4"/>',
    settings:
      '<path d="M14 17H5"/><path d="M19 7h-9"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    'square-check':
      '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    square: '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    'circle-dot': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
    circle: '<circle cx="12" cy="12" r="10"/>',
    history:
      '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    'file-code-2':
      '<path d="M4 12.15V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.706.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2h-3.35"/>' +
      '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="m5 16-3 3 3 3"/><path d="m9 22 3-3-3-3"/>',
    'table-2':
      '<path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18"/>',
    'circuit-board':
      '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M11 9h4a2 2 0 0 0 2-2V3"/><circle cx="9" cy="9" r="2"/>' +
      '<path d="M7 21v-4a2 2 0 0 1 2-2h4"/><circle cx="15" cy="15" r="2"/>',
    eraser:
      '<path d="M21 21H8a2 2 0 0 1-1.42-.587l-3.994-3.999a2 2 0 0 1 0-2.828l10-10a2 2 0 0 1 2.829 0l5.999 6a2 2 0 0 1 0 2.828L12.834 21"/>' +
      '<path d="m5.082 11.09 8.828 8.828"/>',
    'rotate-ccw':
      '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    'file-text':
      '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>' +
      '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    hash:
      '<line x1="4" x2="20" y1="9" y2="9"/><line x1="4" x2="20" y1="15" y2="15"/>' +
      '<line x1="10" x2="8" y1="3" y2="21"/><line x1="16" x2="14" y1="3" y2="21"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    'panel-right': '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/>',
    'file-plus':
      '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>' +
      '<path d="M14 2v5a1 1 0 0 0 1 1h5"/><path d="M9 15h6"/><path d="M12 18v-6"/>',
    copy:
      '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>' +
      '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>'
  };

  function svg(name, cls) {
    var body = ICONS[name] || ICONS.info;
    return '<svg class="lucide lucide-' + name + ' ' + (cls || '') +
      '" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' + body + '</svg>';
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function formatSize(bytes) {
    var value = typeof bytes === 'number' && isFinite(bytes) && bytes > 0 ? bytes : 0;
    var units = ['B', 'KB', 'MB', 'GB'];
    var unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return (unit === 0 ? String(Math.round(value)) : value.toFixed(1)) + ' ' + units[unit];
  }

  function formatNumber(value) {
    if (value == null || value === '') { return '—'; }
    return Number(value).toLocaleString('zh-CN');
  }

  // ---------------------------------------------------------------- REST
  function request(method, url, body, isForm) {
    var init = { method: method, headers: {} };
    if (body !== undefined && body !== null) {
      if (isForm) {
        init.body = body;
      } else {
        init.headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
    }
    return fetch(url, init).then(function (res) {
      return res.json().catch(function () {
        throw new Error('服务返回了非 JSON 响应（HTTP ' + res.status + '）');
      }).then(function (data) {
        if (!res.ok || data.ok === false) {
          throw new Error(data && data.error ? data.error : '请求失败（HTTP ' + res.status + '）');
        }
        return data;
      });
    });
  }

  var api = {
    get: function (url) { return request('GET', url); },
    post: function (url, body) { return request('POST', url, body || {}); },
    del: function (url) { return request('DELETE', url); },
    upload: function (kind, file, onProgress) {
      return new Promise(function (resolve, reject) {
        var form = new FormData();
        form.append('kind', kind);
        form.append('file', file, file.name);
        var xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/upload');
        xhr.upload.onprogress = function (event) {
          if (onProgress && event.lengthComputable) {
            onProgress(Math.round(event.loaded * 100 / event.total));
          }
        };
        xhr.onload = function () {
          var data = null;
          try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
          if (xhr.status >= 200 && xhr.status < 300 && data && data.ok !== false) {
            resolve(data);
          } else {
            reject(new Error(data && data.error ? data.error : '上传失败（HTTP ' + xhr.status + '）'));
          }
        };
        xhr.onerror = function () { reject(new Error('上传失败：无法连接本地服务')); };
        xhr.send(form);
      });
    }
  };

  // ---------------------------------------------------------------- toast
  function toastBox() {
    var box = document.querySelector('.bom-toasts');
    if (!box) {
      box = document.createElement('div');
      box.className = 'bom-toasts';
      box.setAttribute('role', 'status');
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    return box;
  }

  var TOAST_ICON = {
    success: 'circle-check', error: 'circle-x', warning: 'triangle-alert', info: 'info'
  };

  function toast(type, text, timeout) {
    var kind = TOAST_ICON[type] ? type : 'info';
    var el = document.createElement('div');
    el.className = 'bom-toast bom-toast--' + kind;
    el.innerHTML = svg(TOAST_ICON[kind], 'bom-toast__icon') +
      '<span>' + escapeHtml(text) + '</span>';
    toastBox().appendChild(el);
    var life = typeof timeout === 'number' ? timeout : (kind === 'error' ? 7000 : 4000);
    setTimeout(function () {
      el.style.transition = 'opacity 140ms linear';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 160);
    }, life);
    return el;
  }

  // ---------------------------------------------------------------- overlay
  function overlay(show, title, desc) {
    var el = document.getElementById('bom-overlay');
    if (!el) {
      el = document.createElement('div');
      el.id = 'bom-overlay';
      el.className = 'bom-overlay';
      el.hidden = true;
      el.innerHTML =
        '<div class="bom-overlay__panel" role="alertdialog" aria-live="assertive">' +
        '<span class="bom-spinner"></span>' +
        '<p class="bom-overlay__title"></p><p class="bom-overlay__desc"></p></div>';
      document.body.appendChild(el);
    }
    if (show) {
      el.querySelector('.bom-overlay__title').textContent = title || '处理中';
      el.querySelector('.bom-overlay__desc').textContent = desc || '';
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  }

  // ---------------------------------------------------------------- empty
  function empty(opts) {
    var o = opts || {};
    var actions = (o.actions || []).map(function (a) {
      return '<a class="' + (a.primary ? 'wb-btn wb-btn--primary' : 'wb-btn wb-btn--ghost') +
        '" href="' + escapeHtml(a.href || '#') + '">' + escapeHtml(a.label) + '</a>';
    }).join('');
    return '<div class="bom-empty">' +
      svg(o.icon || 'inbox', 'bom-empty__icon') +
      '<p class="bom-empty__title">' + escapeHtml(o.title || '暂无数据') + '</p>' +
      (o.desc ? '<p class="bom-empty__desc">' + escapeHtml(o.desc) + '</p>' : '') +
      (actions ? '<div class="bom-empty__actions">' + actions + '</div>' : '') +
      '</div>';
  }

  function query(name, fallback) {
    var value = new URLSearchParams(window.location.search).get(name);
    return value == null || value === '' ? (fallback === undefined ? null : fallback) : value;
  }

  // ------------------------------------------------- 桌面窗口（pywebview）
  function desktopApi() {
    var bridge = window.pywebview;
    if (bridge && bridge.api && typeof bridge.api.save_task_output === 'function') {
      return bridge.api;
    }
    return null;
  }

  /** 桌面桥接对象在页面加载后才注入，这里做一次带超时的就绪探测。 */
  function onDesktopReady(fn) {
    var fired = false;
    function fire() {
      if (fired) { return; }
      fired = true;
      fn(desktopApi());
    }
    if (desktopApi()) { fire(); return; }
    window.addEventListener('pywebviewready', fire);
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      if (desktopApi()) { clearInterval(timer); fire(); }
      else if (tries > 20) { clearInterval(timer); }
    }, 150);
  }

  function downloadText(filename, text) {
    var blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /** 导出任务结果：桌面模式走原生「另存为」，浏览器模式直接下载。 */
  function saveTaskOutput(taskId, downloadUrl) {
    var api = desktopApi();
    if (!api) { window.location.href = downloadUrl; return; }
    api.save_task_output(taskId).then(function (res) {
      if (res && res.ok) { toast('success', '已保存到 ' + res.path); }
      else if (res && res.cancelled) { /* 用户取消，不打扰 */ }
      else { toast('error', (res && res.error) || '保存失败'); }
    }).catch(function (err) {
      toast('error', '保存失败：' + (err && err.message ? err.message : err));
    });
  }

  /** 导出前端生成的文本：桌面模式走原生「另存为」，浏览器模式下载。 */
  function saveTextFile(filename, text) {
    var api = desktopApi();
    if (!api || typeof api.save_text !== 'function') { downloadText(filename, text); return; }
    api.save_text(filename, text).then(function (res) {
      if (res && res.ok) { toast('success', '已保存到 ' + res.path); }
      else if (res && res.cancelled) { /* 用户取消，不打扰 */ }
      else { toast('error', (res && res.error) || '保存失败'); }
    }).catch(function (err) {
      toast('error', '保存失败：' + (err && err.message ? err.message : err));
    });
  }

  function openFolder(kind) {
    var api = desktopApi();
    if (!api || typeof api.open_folder !== 'function') { return; }
    api.open_folder(kind || 'outputs').then(function (res) {
      if (res && !res.ok && !res.cancelled) { toast('error', res.error || '打开目录失败'); }
    }).catch(function () { /* 忽略 */ });
  }

  window.BOM = {
    api: api, svg: svg, icon: svg, escape: escapeHtml,
    formatSize: formatSize, formatNumber: formatNumber,
    toast: toast, overlay: overlay, empty: empty, query: query,
    downloadText: downloadText,
    desktop: {
      api: desktopApi,
      onReady: onDesktopReady,
      saveTaskOutput: saveTaskOutput,
      saveTextFile: saveTextFile,
      openFolder: openFolder
    }
  };
})();
