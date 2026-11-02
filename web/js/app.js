/* ==========================================================================
   我的日程 · 前端逻辑
   ========================================================================== */
(function () {
  'use strict';

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

  const REMIND_OPTIONS = [
    { value: -1, label: '不提醒' },
    { value: 0, label: '准时提醒' },
    { value: 5, label: '提前 5 分钟' },
    { value: 10, label: '提前 10 分钟' },
    { value: 15, label: '提前 15 分钟' },
    { value: 30, label: '提前 30 分钟' },
    { value: 60, label: '提前 1 小时' },
    { value: 120, label: '提前 2 小时' },
    { value: 1440, label: '提前 1 天' }
  ];

  const state = {
    view: 'calendar',
    today: '',
    selected: '',
    cursor: { year: new Date().getFullYear(), month: new Date().getMonth() + 1 },
    statsMonth: '',
    events: [],
    todayEvents: [],
    settings: {},
    categories: [],
    repeatNames: {},
    appInfo: {},
    holidays: {},
    holidayToday: null,
    holidayUpcoming: [],
    holidayMeta: {},
    editingId: null,
    pendingDelete: null,
    notiCursor: 0,
    bootShown: false,
    ready: false
  };

  // ------------------------------------------------------------ 基础工具
  const pad2 = (n) => String(n).padStart(2, '0');

  function fmtDate(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  }

  function parseDate(text) {
    const parts = String(text).split('-').map(Number);
    return new Date(parts[0], (parts[1] || 1) - 1, parts[2] || 1);
  }

  function monthKey(year, month) {
    return `${year}-${pad2(month)}`;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function hexAlpha(hex, alpha) {
    const text = String(hex || '#4567f2').replace('#', '');
    const full = text.length === 3 ? text.split('').map((c) => c + c).join('') : text;
    const num = parseInt(full, 16);
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function remindLabel(minutes) {
    const found = REMIND_OPTIONS.find((item) => item.value === Number(minutes));
    return found ? found.label : `提前 ${minutes} 分钟`;
  }

  // ------------------------------------------------------------ API
  async function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, opts);
    let data = null;
    try {
      data = await response.json();
    } catch (error) {
      data = null;
    }
    if (!response.ok) {
      throw new Error((data && data.error) || `请求失败（${response.status}）`);
    }
    return data || {};
  }

  // ------------------------------------------------------------ 提示
  function showToast(title, body, kind) {
    const stack = $('#toastStack');
    if (!stack) return;
    const node = document.createElement('div');
    node.className = 'toast';
    const mark = kind === 'reminder' ? '⏰' : kind === 'digest' ? '🌤' : kind === 'summary' ? '📊' : kind === 'holiday' ? '🎉' : '✓';
    node.innerHTML = `
      <div class="toast-mark">${mark}</div>
      <div class="toast-body">
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(body)}</p>
      </div>
      <button class="toast-close" type="button" aria-label="关闭">×</button>`;
    stack.appendChild(node);
    const remove = () => {
      node.style.transition = 'opacity .2s ease, transform .2s ease';
      node.style.opacity = '0';
      node.style.transform = 'translateY(6px)';
      setTimeout(() => node.remove(), 220);
    };
    $('.toast-close', node).addEventListener('click', remove);
    setTimeout(remove, 9000);
  }

  function showBanner(title, items) {
    $('#bannerTitle').textContent = title;
    $('#bannerList').innerHTML = (items || [])
      .slice(0, 5)
      .map((item) => `<li><i style="background:${escapeHtml(item.color || '#4567f2')}"></i>${escapeHtml(item.time)} ${escapeHtml(item.title)}</li>`)
      .join('');
    $('#banner').hidden = false;
  }

  // ------------------------------------------------------------ 数据加载
  async function loadAll(options) {
    const settings = options || {};
    const key = monthKey(state.cursor.year, state.cursor.month);
    const data = await api(`/api/bootstrap?month=${key}`);

    state.today = data.today;
    state.events = data.events || [];
    state.todayEvents = data.todayEvents || [];
    state.settings = data.settings || {};
    state.categories = data.categories || [];
    state.repeatNames = data.repeatNames || {};
    state.appInfo = data.app || {};
    state.holidays = data.holidays || {};
    state.holidayToday = data.holidayToday || null;
    state.holidayUpcoming = data.holidayUpcoming || [];
    state.holidayMeta = data.holidayMeta || {};

    if (!state.selected) state.selected = state.today;
    if (!state.statsMonth) state.statsMonth = state.today.slice(0, 7);
    if (!state.categories.length) return;

    if (!settings.skipNotifications) {
      const list = data.notifications || [];
      list.forEach((item) => {
        state.notiCursor = Math.max(state.notiCursor, item.id || 0);
      });
      if (data.bootDigest && !state.bootShown) {
        state.bootShown = true;
        showBanner(data.bootDigest.title, data.bootDigest.items);
      }
    }

    state.ready = true;
    renderAll();
  }

  function renderAll() {
    renderHeaderSub();
    renderCalendar();
    renderScheduleList();
    renderMini();
    renderHolidayCard();
    renderSettings();
    if (state.view === 'stats') renderStats();
  }

  async function refresh() {
    try {
      await loadAll({ skipNotifications: true });
    } catch (error) {
      showToast('操作失败', error.message);
    }
  }

  // ------------------------------------------------------------ 渲染：头部
  function renderHeaderSub() {
    const total = state.todayEvents.length;
    const done = state.todayEvents.filter((item) => item.done).length;
    $('#headerSub').textContent = total
      ? `今天有 ${total} 项安排${done ? `，已完成 ${done} 项` : ''}`
      : '把时间留给重要的事';
  }

  // ------------------------------------------------------------ 渲染：日历
  function labelStyle(item) {
    return `background:${hexAlpha(item.color, 0.12)};color:${item.color}`;
  }

  function renderCalendar() {
    const year = state.cursor.year;
    const month = state.cursor.month;
    $('#monthTitle').textContent = `${year}年${month}月`;

    const first = new Date(year, month - 1, 1);
    const offset = first.getDay();
    const dayCount = new Date(year, month, 0).getDate();

    const grouped = {};
    state.events.forEach((item) => {
      (grouped[item.date] = grouped[item.date] || []).push(item);
    });

    let html = '';
    for (let i = 0; i < offset; i++) html += '<div class="day empty"></div>';

    for (let day = 1; day <= dayCount; day++) {
      const date = new Date(year, month - 1, day);
      const key = fmtDate(date);
      const items = (grouped[key] || []).slice().sort((a, b) => a.time.localeCompare(b.time));
      const shown = items.slice(0, 2);
      const preview = items.length
        ? `<span class="event-list">${shown
            .map((item) => `<span class="event-label ${item.done ? 'is-done' : ''}" style="${labelStyle(item)}">${escapeHtml(item.time)} ${escapeHtml(item.title)}</span>`)
            .join('')}${items.length > 2 ? `<span class="event-more">+${items.length - 2} 项</span>` : ''}</span>`
        : '';

      const classes = ['day'];
      if (key === state.selected) classes.push('selected');
      if (key === state.today) classes.push('today');

      const weekday = date.getDay();
      if (weekday === 6) classes.push('sat');
      if (weekday === 0) classes.push('sun');

      // 节假日：放假日标「休」，调休上班日标「班」（左下角）
      const holiday = state.holidays[key];
      let badge = '';
      if (holiday) {
        if (holiday.type === 'rest') {
          classes.push('rest');
          badge = '<span class="day-badge rest">休</span>';
        } else {
          classes.push('makeup');
          badge = '<span class="day-badge work">班</span>';
        }
      }

      html += `<button type="button" class="${classes.join(' ')}" data-date="${key}">
        <span class="number">${day}</span>${preview}${badge}
      </button>`;
    }

    $('#calendarDays').innerHTML = html;
  }

  // ------------------------------------------------------------ 渲染：选中日期
  function renderScheduleList() {
    const date = parseDate(state.selected);
    const items = state.events
      .filter((item) => item.date === state.selected)
      .sort((a, b) => a.time.localeCompare(b.time));

    $('#selectedTitle').textContent = date.toLocaleDateString('zh-CN', {
      month: 'long', day: 'numeric', weekday: 'long'
    });
    $('#selectedDesc').textContent = state.selected === state.today
      ? '今天，安排从容开始'
      : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
    $('#eventCount').textContent = `${items.length} 项日程`;

    if (!items.length) {
      $('#scheduleList').innerHTML = '<div class="empty-state">这一天还没有安排<br>给自己留一点空白吧</div>';
      $('#eventDate').value = state.selected;
      return;
    }

    $('#scheduleList').innerHTML = items.map((item) => {
      const chips = [];
      if (Number(item.remindBefore) >= 0) {
        chips.push(`<span class="chip remind">${escapeHtml(remindLabel(item.remindBefore))}</span>`);
      }
      if (item.isRepeat) {
        chips.push(`<span class="chip repeat">${escapeHtml(item.repeatName || '重复')}</span>`);
      }
      if (item.note) {
        chips.push(`<span class="event-note">${escapeHtml(item.note)}</span>`);
      }

      const pending = state.pendingDelete === item.occurrenceId;
      const actions = pending
        ? `<button class="confirm-del" type="button" data-action="confirm-delete">删除</button>
           <button class="confirm-cancel" type="button" data-action="cancel-delete">取消</button>`
        : `<button class="icon-btn" type="button" data-action="edit" title="编辑">✎</button>
           <button class="delete" type="button" data-action="delete" title="删除日程">×</button>`;

      return `<div class="event ${item.done ? 'done' : ''}" data-occ="${escapeHtml(item.occurrenceId)}">
        <button class="check ${item.done ? 'on' : ''}" type="button" data-action="toggle" aria-label="标记完成">✓</button>
        <span class="event-color" style="background:${escapeHtml(item.color)}"></span>
        <div class="event-main">
          <div class="event-name">${escapeHtml(item.title)}</div>
          <div class="event-meta">
            <span class="event-time">${escapeHtml(item.time)}${item.endTime ? ' - ' + escapeHtml(item.endTime) : ''}</span>
            ${chips.join('')}
          </div>
        </div>
        <div class="event-actions">${actions}</div>
      </div>`;
    }).join('');

    $('#eventDate').value = state.selected;
  }

  // ------------------------------------------------------------ 渲染：概览
  function renderMini() {
    const total = state.events.length;
    const done = state.events.filter((item) => item.done).length;
    const rate = total ? Math.round((done / total) * 100) : 0;
    $('#miniTotal').textContent = total;
    $('#miniDone').textContent = done;
    $('#miniRate').textContent = `${rate}%`;
    $('#miniProgress').style.width = `${rate}%`;
    const isCurrent = monthKey(state.cursor.year, state.cursor.month) === state.today.slice(0, 7);
    const head = $('.mini-head > span');
    if (head) head.textContent = isCurrent ? '本月概览' : `${state.cursor.year}年${state.cursor.month}月概览`;
  }

  // ------------------------------------------------------------ 渲染：节假日
  function fmtHolidayRange(block) {
    const start = block.start.slice(5).replace('-', '/');
    const end = block.end.slice(5).replace('-', '/');
    return start === end ? start : `${start} – ${end}`;
  }

  function renderHolidayCard() {
    const today = state.holidayToday;
    const box = $('#holidayToday');
    if (!box) return;

    if (today) {
      const isRest = today.type === 'rest';
      box.className = `holiday-today${isRest ? '' : ' is-work'}`;
      box.innerHTML = `
        <span class="holiday-tag ${isRest ? 'rest' : 'work'}">${isRest ? '休' : '班'}</span>
        <div><b>${escapeHtml(today.title)}</b><span>${escapeHtml(today.detail || '')}</span></div>`;
    } else {
      box.className = 'holiday-today flat';
      box.innerHTML = `
        <span class="holiday-tag flat">今</span>
        <div><b>今天是普通工作日</b><span>本周暂无节假日安排</span></div>`;
    }

    const list = (state.holidayUpcoming || []).filter((block) => block.end >= state.today);
    $('#holidayUpcoming').innerHTML = list.length
      ? list.map((block) => {
          let chip = `${block.days}天`;
          let tone = '';
          if (block.hasData === false) {
            chip = '放假安排待公布';
            tone = 'tentative';
          } else if (block.provisional) {
            chip = `参考 · ${block.days}天`;
            tone = 'tentative';
          }
          return `<li><i></i><b>${escapeHtml(block.name)}</b>
            <span class="holiday-date">${escapeHtml(fmtHolidayRange(block))}</span>
            <em class="${tone}">${chip}</em></li>`;
        }).join('')
      : '<li class="holiday-empty">近期暂无假期</li>';
  }

  // ------------------------------------------------------------ 渲染：统计
  async function renderStats() {
    if (!state.statsMonth) state.statsMonth = state.today.slice(0, 7);
    let data;
    try {
      data = await api(`/api/stats?month=${state.statsMonth}`);
    } catch (error) {
      showToast('统计加载失败', error.message);
      return;
    }

    $('#statsTitle').textContent = `${data.monthLabel} · 月度总结`;
    $('#statsSub').textContent = `共 ${data.total} 项安排，完成 ${data.done} 项`;

    $('#statTotal').textContent = data.total;
    $('#statTotalHint').textContent = `日均 ${data.avgPerDay} 项 · 活跃 ${data.activeDays} 天`;
    $('#statDone').textContent = data.done;
    $('#statDoneHint').textContent = data.finishedDays ? `${data.finishedDays} 天全部完成` : '坚持就有收获';
    $('#statRate').textContent = data.rate;
    $('#statRateHint').textContent = data.total ? `${data.done}/${data.total} 项已完成` : '还没有安排';

    if (data.busiestDay) {
      $('#statBusiest').textContent = `${data.busiestDay.day}日`;
      $('#statBusiestUnit').textContent = '';
      $('#statBusiestHint').textContent = `${data.busiestDay.weekday} · ${data.busiestDay.total} 项安排`;
    } else {
      $('#statBusiest').textContent = '-';
      $('#statBusiestUnit').textContent = '';
      $('#statBusiestHint').textContent = '还没有记录';
    }

    const dailyItems = data.daily.map((item) => ({
      label: String(item.day),
      value: item.total,
      done: item.done,
      tipTitle: `${item.day} 日 · ${item.weekday}`
    }));
    window.MiniCharts.barChart($('#chartDaily'), dailyItems, { showDone: true, emptyText: '本月还没有安排' });

    window.MiniCharts.donutChart(
      $('#chartCategory'),
      data.categories.map((item) => ({ name: item.name, value: item.total, color: item.color })),
      { centerValue: data.total, centerLabel: '项日程', emptyText: '暂无分类数据' }
    );

    window.MiniCharts.areaChart($('#chartTrend'), data.cumulative, { emptyText: '暂无数据' });

    const periodColors = { '凌晨': '#8b5cf6', '上午': '#4567f2', '下午': '#e9914b', '晚上': '#22b07d' };
    window.MiniCharts.hbarChart(
      $('#chartPeriod'),
      data.periods.map((item) => ({
        name: item.name,
        value: item.total,
        done: item.done,
        color: periodColors[item.name] || '#4567f2'
      })),
      { emptyText: '暂无数据' }
    );

    window.MiniCharts.barChart(
      $('#chartWeekday'),
      data.weekday.map((item) => ({ label: item.name, value: item.total, done: item.done, tipTitle: item.name })),
      { showDone: true, barRatio: 0.5, emptyText: '暂无数据' }
    );

    $('#summaryText').textContent = data.summary;
    $('#summaryActive').textContent = `活跃 ${data.activeDays} 天`;
    $('#summaryRepeat').textContent = `重复日程 ${data.repeatCount} 项`;
    $('#summaryCompare').textContent = data.prevTotal
      ? `上月 ${data.prevTotal} 项（${data.total - data.prevTotal >= 0 ? '+' : ''}${data.total - data.prevTotal}）`
      : '上月无记录';
  }

  // ------------------------------------------------------------ 渲染：设置
  function renderSettings() {
    const settings = state.settings || {};
    toggleSwitch($('#switchAutostart'), !!settings.autostart);
    toggleSwitch($('#switchBootNotify'), !!settings.bootNotify);
    toggleSwitch($('#switchBootWindow'), !!settings.bootOpenWindow);
    toggleSwitch($('#switchDigest'), !!settings.digestEnabled);
    toggleSwitch($('#switchSummary'), !!settings.monthlySummaryNotify);
    toggleSwitch($('#switchHoliday'), settings.holidayNotify !== false);
    $('#digestTime').value = settings.digestTime || '08:30';
    $('#dataDir').textContent = state.appInfo.dataDir || '-';
    $('#versionLine').textContent = `我的日程 v${state.appInfo.version || '1.1.0'}`;

    const select = $('#defaultRemind');
    if (select.options.length === 0) {
      REMIND_OPTIONS.filter((item) => item.value > 0).forEach((item) => {
        const option = document.createElement('option');
        option.value = String(item.value);
        option.textContent = item.label;
        select.appendChild(option);
      });
    }
    select.value = String(settings.defaultRemindBefore || 10);
  }

  function toggleSwitch(node, on) {
    if (!node) return;
    node.classList.toggle('on', !!on);
    node.setAttribute('aria-checked', on ? 'true' : 'false');
  }

  // ------------------------------------------------------------ 表单
  function buildFormSelects() {
    const categorySelect = $('#eventCategory');
    categorySelect.innerHTML = state.categories
      .map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.name)}</option>`)
      .join('');

    const repeatSelect = $('#eventRepeat');
    repeatSelect.innerHTML = Object.keys(state.repeatNames)
      .map((key) => `<option value="${escapeHtml(key)}">${escapeHtml(state.repeatNames[key])}</option>`)
      .join('');

    const remindSelect = $('#eventRemind');
    remindSelect.innerHTML = REMIND_OPTIONS
      .map((item) => `<option value="${item.value}">${escapeHtml(item.label)}</option>`)
      .join('');
  }

  function resetForm() {
    state.editingId = null;
    $('#formTitle').textContent = '添加日程';
    $('#submitBtn').textContent = '添加到日程';
    $('#cancelEdit').hidden = true;
    $('#eventName').value = '';
    $('#eventNote').value = '';
    $('#eventDate').value = state.selected || state.today;
    $('#eventTime').value = '09:00';
    $('#eventCategory').value = state.categories.length ? state.categories[0].key : 'work';
    $('#eventRepeat').value = 'none';
    $('#eventRemind').value = String(state.settings.defaultRemindBefore || 10);
  }

  function startEdit(item) {
    state.editingId = item.eventId;
    $('#formTitle').textContent = '编辑日程';
    $('#submitBtn').textContent = '保存修改';
    $('#cancelEdit').hidden = false;
    $('#eventName').value = item.title;
    $('#eventDate').value = item.date;
    $('#eventTime').value = item.time;
    $('#eventNote').value = item.note || '';
    $('#eventCategory').value = item.category;
    $('#eventRepeat').value = item.repeat || 'none';
    $('#eventRemind').value = String(item.remindBefore);
    $('#eventName').focus();
    $('#eventName').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  async function submitForm(event) {
    event.preventDefault();
    const payload = {
      title: $('#eventName').value.trim(),
      date: $('#eventDate').value,
      time: $('#eventTime').value,
      category: $('#eventCategory').value,
      repeat: $('#eventRepeat').value,
      remindBefore: Number($('#eventRemind').value),
      note: $('#eventNote').value.trim()
    };
    if (!payload.title) {
      $('#eventName').focus();
      return;
    }

    const editing = state.editingId;
    try {
      if (editing) {
        await api(`/api/events/${encodeURIComponent(editing)}`, { method: 'PUT', body: payload });
        showToast('已保存修改', `${payload.date} ${payload.time} ${payload.title}`);
      } else {
        await api('/api/events', { method: 'POST', body: payload });
        showToast('已添加日程', `${payload.date} ${payload.time} ${payload.title}`);
      }
      const target = parseDate(payload.date);
      state.cursor = { year: target.getFullYear(), month: target.getMonth() + 1 };
      state.selected = payload.date;
      resetForm();
      await refresh();
    } catch (error) {
      showToast('保存失败', error.message);
    }
  }

  // ------------------------------------------------------------ 交互绑定
  function bindEvents() {
    // 顶部标签
    $('#tabs').addEventListener('click', (event) => {
      const button = event.target.closest('.tab');
      if (!button) return;
      switchView(button.dataset.view);
    });

    $$('[data-goto]').forEach((node) => {
      node.addEventListener('click', () => switchView(node.dataset.goto));
    });

    // 日历
    $('#calendarDays').addEventListener('click', (event) => {
      const cell = event.target.closest('[data-date]');
      if (!cell) return;
      state.selected = cell.dataset.date;
      state.pendingDelete = null;
      renderCalendar();
      renderScheduleList();
    });

    $('#prevBtn').addEventListener('click', () => shiftMonth(-1));
    $('#nextBtn').addEventListener('click', () => shiftMonth(1));

    $('#todayBtn').addEventListener('click', () => {
      const today = parseDate(state.today || fmtDate(new Date()));
      state.selected = state.today;
      state.cursor = { year: today.getFullYear(), month: today.getMonth() + 1 };
      state.statsMonth = state.today.slice(0, 7);
      state.pendingDelete = null;
      refresh();
      if (state.view === 'stats') renderStats();
      if (state.view === 'settings') switchView('calendar');
    });

    // 日程列表操作
    $('#scheduleList').addEventListener('click', async (event) => {
      const actionNode = event.target.closest('[data-action]');
      const row = event.target.closest('[data-occ]');
      if (!actionNode || !row) return;
      const occurrenceId = row.dataset.occ;
      const occurrence = state.events.find((item) => item.occurrenceId === occurrenceId);
      const action = actionNode.dataset.action;

      if (action === 'toggle') {
        try {
          await api(`/api/occurrences/${encodeURIComponent(occurrenceId)}/toggle`, { method: 'POST', body: {} });
          await refresh();
        } catch (error) {
          showToast('操作失败', error.message);
        }
        return;
      }

      if (action === 'edit') {
        if (occurrence) startEdit(occurrence);
        return;
      }

      if (action === 'delete') {
        state.pendingDelete = occurrenceId;
        renderScheduleList();
        return;
      }

      if (action === 'cancel-delete') {
        state.pendingDelete = null;
        renderScheduleList();
        return;
      }

      if (action === 'confirm-delete') {
        try {
          await api(`/api/events/${encodeURIComponent(occurrence.eventId)}`, { method: 'DELETE' });
          state.pendingDelete = null;
          if (state.editingId === occurrence.eventId) resetForm();
          showToast('已删除日程', occurrence.title);
          await refresh();
        } catch (error) {
          showToast('删除失败', error.message);
        }
      }
    });

    // 表单
    $('#scheduleForm').addEventListener('submit', submitForm);
    $('#cancelEdit').addEventListener('click', resetForm);
    $('#eventDate').addEventListener('change', (event) => {
      if (!event.target.value) return;
      const target = parseDate(event.target.value);
      state.selected = event.target.value;
      state.cursor = { year: target.getFullYear(), month: target.getMonth() + 1 };
      refresh();
    });

    // 提醒横幅
    $('#bannerClose').addEventListener('click', () => {
      $('#banner').hidden = true;
    });

    // 节假日数据说明
    $('#holidayInfoBtn').addEventListener('click', () => {
      const meta = state.holidayMeta || {};
      const years = (meta.years || []).join('、') || '无';
      const provisional = (meta.provisionalYears || []).join('、');
      showToast(
        '节假日数据',
        `数据来源：${meta.source || '国务院办公厅放假安排'}\n` +
        `已录入年份：${years}${provisional ? `（${provisional} 为参考安排，请以官方通知为准）` : ''}\n` +
        '如需更新年份，编辑程序目录下 backend/holidays.json 后重启应用即可。'
      );
    });

    // 统计翻月
    $('#statsPrev').addEventListener('click', () => shiftStatsMonth(-1));
    $('#statsNext').addEventListener('click', () => shiftStatsMonth(1));

    // 设置：开关
    const switchMap = {
      switchAutostart: 'autostart',
      switchBootNotify: 'bootNotify',
      switchBootWindow: 'bootOpenWindow',
      switchDigest: 'digestEnabled',
      switchSummary: 'monthlySummaryNotify',
      switchHoliday: 'holidayNotify'
    };
    Object.keys(switchMap).forEach((id) => {
      const node = $('#' + id);
      if (!node) return;
      node.addEventListener('click', async () => {
        const key = switchMap[id];
        const next = !node.classList.contains('on');
        toggleSwitch(node, next);
        state.settings[key] = next;
        try {
          const result = await api('/api/settings', { method: 'PATCH', body: { [key]: next } });
          state.settings = result.settings || state.settings;
          renderSettings();
          if (key === 'autostart') {
            showToast(next ? '已开启开机自启' : '已关闭开机自启',
              next ? '下次开机时会自动启动并提醒今日待办。' : '下次开机不再自动启动。');
          }
        } catch (error) {
          toggleSwitch(node, !next);
          showToast('设置失败', error.message);
        }
      });
    });

    $('#digestTime').addEventListener('change', async (event) => {
      try {
        const result = await api('/api/settings', { method: 'PATCH', body: { digestTime: event.target.value } });
        state.settings = result.settings || state.settings;
        renderSettings();
        showToast('已更新', `每日待办将在 ${state.settings.digestTime} 推送`);
      } catch (error) {
        showToast('设置失败', error.message);
      }
    });

    $('#defaultRemind').addEventListener('change', async (event) => {
      try {
        const result = await api('/api/settings', { method: 'PATCH', body: { defaultRemindBefore: Number(event.target.value) } });
        state.settings = result.settings || state.settings;
      } catch (error) {
        showToast('设置失败', error.message);
      }
    });

    // 设置：按钮
    $('#testNotify').addEventListener('click', async () => {
      try {
        await api('/api/test-notify', { method: 'POST', body: {} });
        showToast('已发送测试通知', '如果没有看到系统通知，请检查 Windows 通知设置。');
      } catch (error) {
        showToast('发送失败', error.message);
      }
    });

    $('#digestNow').addEventListener('click', async () => {
      try {
        const result = await api('/api/digest', { method: 'POST', body: {} });
        const digest = result.digest || {};
        showBanner(digest.title || '今日待办', digest.items || []);
      } catch (error) {
        showToast('播报失败', error.message);
      }
    });

    $('#createShortcut').addEventListener('click', async () => {
      try {
        const result = await api('/api/desktop-shortcut', { method: 'POST', body: {} });
        showToast(result.ok ? '已创建桌面快捷方式' : '创建失败', result.detail || '');
      } catch (error) {
        showToast('创建失败', error.message);
      }
    });

    $('#openDataDir').addEventListener('click', async () => {
      try {
        await api('/api/open-data-dir', { method: 'POST', body: {} });
      } catch (error) {
        showToast('打开失败', error.message);
      }
    });

    $('#quitApp').addEventListener('click', async () => {
      try {
        await api('/api/shutdown', { method: 'POST', body: {} });
      } catch (error) {
        // 服务关闭时连接中断属正常
      }
      document.body.innerHTML = `
        <div style="min-height:100vh;display:grid;place-items:center;padding:24px;">
          <div style="max-width:420px;text-align:center;background:#fff;border:1px solid #e9edf3;border-radius:18px;padding:36px 28px;box-shadow:0 12px 34px #25325c14;">
            <div style="width:52px;height:52px;border-radius:16px;display:grid;place-items:center;font-size:24px;margin:0 auto 16px;background:linear-gradient(135deg,#8b5cf6,#4567f2);color:#fff;">✓</div>
            <h2 style="margin:0 0 10px;font-size:18px;">我的日程已退出</h2>
            <p style="margin:0;color:#718096;font-size:13px;line-height:1.9;">
              退出后将不再接收日程提醒。<br>
              重新启动：双击桌面上的「我的日程」快捷方式，
              或运行文件夹里的「启动日程软件.vbs」。
            </p>
          </div>
        </div>`;
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && state.editingId) resetForm();
    });
  }

  function switchView(view) {
    state.view = view;
    $$('.tab').forEach((tab) => tab.classList.toggle('is-active', tab.dataset.view === view));
    $('#view-calendar').hidden = view !== 'calendar';
    $('#view-stats').hidden = view !== 'stats';
    $('#view-settings').hidden = view !== 'settings';
    if (view === 'stats') renderStats();
    if (view === 'settings') renderSettings();
  }

  function shiftMonth(delta) {
    const date = new Date(state.cursor.year, state.cursor.month - 1 + delta, 1);
    state.cursor = { year: date.getFullYear(), month: date.getMonth() + 1 };
    const current = parseDate(state.selected || state.today);
    if (current.getFullYear() !== state.cursor.year || current.getMonth() + 1 !== state.cursor.month) {
      state.selected = fmtDate(date);
    }
    state.pendingDelete = null;
    refresh();
  }

  function shiftStatsMonth(delta) {
    const parts = String(state.statsMonth || state.today.slice(0, 7)).split('-');
    const date = new Date(Number(parts[0]), Number(parts[1]) - 1 + delta, 1);
    state.statsMonth = monthKey(date.getFullYear(), date.getMonth() + 1);
    renderStats();
  }

  // ------------------------------------------------------------ 通知轮询
  async function pollNotifications() {
    if (!state.ready) return;
    try {
      const data = await api(`/api/notifications?since=${state.notiCursor}`);
      (data.items || []).forEach((item) => {
        state.notiCursor = Math.max(state.notiCursor, item.id || 0);
        if (item.kind === 'digest') {
          showBanner(item.title, item.items);
        } else {
          showToast(item.title, item.body, item.kind);
        }
      });
      if (data.digest && !state.bootShown) {
        state.bootShown = true;
        showBanner(data.digest.title, data.digest.items);
      }
    } catch (error) {
      /* 服务未响应时静默重试 */
    }
  }

  // ------------------------------------------------------------ 启动
  async function init() {
    bindEvents();
    const params = new URLSearchParams(location.search);
    const monthParam = params.get('month') || '';
    if (/^\d{4}-\d{2}$/.test(monthParam)) {
      const parts = monthParam.split('-').map(Number);
      state.cursor = { year: parts[0], month: parts[1] };
      state.selected = `${monthParam}-01`;
      state.statsMonth = monthParam;
    }
    try {
      await loadAll();
      buildFormSelects();
      resetForm();
      renderSettings();
      const viewParam = params.get('view');
      if (viewParam && ['calendar', 'stats', 'settings'].indexOf(viewParam) >= 0) {
        switchView(viewParam);
      }
      setInterval(pollNotifications, 15000);
      setInterval(() => { refresh(); }, 60000);
      pollNotifications();
    } catch (error) {
      $('#headerSub').textContent = '未连接到本地服务';
      showBanner('无法连接本地服务', []);
      $('#bannerTitle').textContent = '无法连接本地服务，请通过「启动日程软件.vbs」打开应用';
      $('#bannerList').innerHTML = `<li><i style="background:#f06464"></i>${escapeHtml(error.message)}</li>`;
      $('#banner').hidden = false;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})(window);
