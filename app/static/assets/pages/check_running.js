/* BOM 校对 · 核对进行中：轮询任务进度并实时渲染流程 / 日志 / 统计 */

(function () {
  'use strict';

  var BOM = window.BOM;
  var taskId = BOM.query('task');
  var autoScroll = true;
  var timer = null;
  var redirected = false;

  var LEVEL_CLASS = { OK: 'data-level="OK"', WARN: 'data-level="WARN"' };

  function levelAttr(level) {
    return LEVEL_CLASS[level] || 'data-level="INFO"';
  }

  function renderOverview(task) {
    var title = document.querySelector('[data-render="overview-title"]');
    var meta = document.querySelector('[data-render="overview-meta"]');
    var value = document.querySelector('[data-render="overview-progress"]');
    var track = document.querySelector('[data-render="overview-track"]');

    var active = (task.steps || []).filter(function (s) { return s.state === 'active'; })[0];
    var doneCount = (task.steps || []).filter(function (s) { return s.state === 'done'; }).length;

    if (task.status === 'running') {
      title.textContent = active ? '正在执行：' + active.name + (active.note ? '（' + active.note + '）' : '')
                                 : '正在准备核对…';
    } else if (task.status === 'done') {
      title.textContent = '核对完成';
    } else if (task.status === 'cancelled') {
      title.textContent = '核对已取消';
    } else {
      title.textContent = '核对失败';
    }

    meta.textContent = '已用时 ' + task.elapsed + ' s · 已完成 ' + doneCount + '/' +
      (task.steps || []).length + ' 步' + (task.error ? ' · ' + task.error : '');

    value.textContent = task.progress + '%';
    track.setAttribute('aria-valuenow', task.progress);
    track.querySelector('.check-overview__fill').style.width = task.progress + '%';
  }

  function renderSteps(task) {
    var box = document.querySelector('[data-render="steps"]');
    box.innerHTML = (task.steps || []).map(function (step, i) {
      var icon = step.state === 'done' ? BOM.svg('check') : (i + 1);
      return '<li class="check-step" data-state="' + step.state + '">' +
        '<span class="check-step__dot" aria-hidden="true">' + icon + '</span>' +
        '<p class="check-step__name">' + BOM.escape(step.name) + '</p>' +
        '<p class="check-step__note bom-num">' + BOM.escape(step.note || '等待中') + '</p></li>';
    }).join('');
  }

  function renderLog(task) {
    var box = document.querySelector('[data-render="log"]');
    var logs = task.logs || [];
    if (!logs.length) {
      box.innerHTML = '<div class="bom-loading"><span class="bom-spinner"></span>等待引擎输出…</div>';
      return;
    }
    box.innerHTML = logs.map(function (entry) {
      return '<div class="check-log__row">' +
        '<span class="check-log__time">' + BOM.escape(entry.time) + '</span>' +
        '<span class="check-log__level" ' + levelAttr(entry.level) + '>' +
        BOM.escape(entry.level) + '</span>' +
        '<span class="check-log__text">' + BOM.escape(entry.text) + '</span></div>';
    }).join('');
    if (autoScroll) { box.scrollTop = box.scrollHeight; }
  }

  function renderStats(task) {
    var m = task.metrics || {};
    var total = document.querySelector('[data-render="stat-total"]');
    var severe = document.querySelector('[data-render="stat-severe"]');
    var normal = document.querySelector('[data-render="stat-normal"]');
    var lines = document.querySelector('[data-render="stat-lines"]');
    var dist = document.querySelector('[data-render="stat-dist"]');

    if (total) { total.textContent = m.total != null ? m.total : 0; }
    if (severe) { severe.textContent = m.severe != null ? m.severe : 0; }
    if (normal) { normal.textContent = m.normal != null ? m.normal : 0; }
    if (lines) { lines.textContent = m.total != null ? '已完成' : '进行中'; }
    if (!dist) { return; }

    var d = m.distribution || [];
    if (!d.length) {
      dist.innerHTML = '<p class="check-stats__subtitle">问题类别将在核对完成后汇总</p>';
      return;
    }
    var max = d[0].count || 1;
    dist.innerHTML = '<p class="check-stats__subtitle">当前类别分布</p>' +
      d.slice(0, 4).map(function (item) {
        return '<div class="check-stats__bar-row">' +
          '<span class="check-stats__bar-name">' + BOM.escape(item.kind) + '</span>' +
          '<span class="check-stats__bar"><span class="check-stats__bar-fill" style="width:' +
          Math.round(item.count * 100 / max) + '%"></span></span>' +
          '<span class="check-stats__bar-num bom-num">' + item.count + '</span></div>';
      }).join('');
  }

  function apply(task) {
    renderOverview(task);
    renderSteps(task);
    renderLog(task);
    renderStats(task);

    BOM.app.setStatusbar(
      '核对' + (task.status === 'running' ? '进行中' : task.status === 'done' ? '完成' : '已结束') +
      ' ' + task.progress + '% · 已用时 ' + task.elapsed + ' s'
    );

    var cta = document.querySelector('[data-action="view-result"]');
    if (cta && task.status === 'done') {
      cta.setAttribute('href', '/check/result?task=' + task.id);
      cta.style.opacity = '';
      cta.style.pointerEvents = '';
    }

    var cancelBtn = document.querySelector('[data-action="cancel"]');
    if (cancelBtn && task.status !== 'running') {
      cancelBtn.disabled = true;
      cancelBtn.style.opacity = '.5';
      cancelBtn.style.cursor = 'not-allowed';
    }

    if (task.status === 'running') { return; }

    if (timer) { clearInterval(timer); timer = null; }

    if (task.status === 'done' && !redirected) {
      redirected = true;
      BOM.toast('success', '核对完成：' + ((task.metrics || {}).total || 0) + ' 项问题，正在打开结果页');
      setTimeout(function () {
        window.location.href = '/check/result?task=' + task.id;
      }, 900);
    } else if (task.status === 'cancelled') {
      BOM.toast('warning', '核对已取消');
    } else if (task.status === 'failed') {
      BOM.toast('error', '核对失败：' + (task.error || '未知原因'));
    }
  }

  function poll() {
    if (!taskId) {
      BOM.toast('error', '缺少任务号，无法显示进度');
      return;
    }
    BOM.api.get('/api/tasks/' + taskId).then(function (res) {
      apply(res.task);
    }).catch(function (err) {
      if (timer) { clearInterval(timer); timer = null; }
      BOM.toast('error', err.message);
    });
  }

  document.addEventListener('click', function (event) {
    var action = event.target.closest('[data-action]');
    if (!action) { return; }
    var kind = action.getAttribute('data-action');
    if (kind === 'cancel') {
      if (action.disabled) { return; }
      BOM.api.post('/api/tasks/' + taskId + '/cancel', {}).then(function () {
        BOM.toast('info', '已请求取消，等待引擎收尾');
      }).catch(function (err) { BOM.toast('error', err.message); });
    } else if (kind === 'toggle-autoscroll') {
      autoScroll = !autoScroll;
      action.setAttribute('data-on', autoScroll ? 'true' : 'false');
      action.setAttribute('aria-pressed', autoScroll ? 'true' : 'false');
      action.style.justifyContent = autoScroll ? 'flex-end' : 'flex-start';
    }
  });

  if (!taskId) {
    var state = BOM.app.state();
    taskId = state && state.lastCheck ? state.lastCheck.id : null;
  }
  poll();
  timer = setInterval(poll, 700);
})();
