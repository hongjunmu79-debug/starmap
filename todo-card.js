/* 首页「待办」卡：把 Horizon 的待办按事分组放进首页。自带样式，不往 window 上挂任何名字。
   数据 GET /api/todos；勾选 POST /api/today-tick（id 为 hz:<待办 id>）；改组 POST /api/todos/assign；新建 POST /api/todos。
   外观：跟首页同一套夜空配色；逾期的待办左边一道琥珀色的光，拖得越久越亮；只有逾期用强调色。 */
(function () {
  'use strict';
  var host = document.getElementById('todos');
  if (!host) return;

  var style = document.createElement('style');
  style.textContent = [
    '.tc-card{margin-top:16px;gap:4px}',
    '.tc-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:2px}',
    '.tc-head h3{margin:0;font-size:16px;font-weight:600;color:var(--ink);letter-spacing:.5px}',
    '.tc-count{font-size:12.5px;color:var(--muted)}',
    '.tc-count b{font-weight:600;color:var(--warn,#F2A33A)}',
    '.tc-tools{margin-left:auto;display:flex;gap:8px;align-items:center;flex-wrap:wrap}',
    '.tc-seg{display:inline-flex;padding:2px;border:1px solid var(--line);border-radius:999px;background:rgba(0,0,0,.18)}',
    '.tc-seg button{border:0;border-radius:999px;background:transparent;color:var(--muted);font-size:12.5px;padding:3px 11px}',
    '.tc-seg button:hover{background:transparent;color:var(--ink)}',
    '.tc-seg button.on{background:var(--card-hi);color:var(--ink)}',
    '.tc-new{font-size:12.5px;padding:4px 12px;border-radius:999px}',
    '.tc-copy{font-size:12px;color:var(--faint);padding:6px 10px;border:1px dashed var(--line);border-radius:10px;margin:6px 0 2px}',
    '.tc-form{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 6px;padding:10px;border:1px solid var(--line);border-radius:12px;background:rgba(0,0,0,.16)}',
    '.tc-form input,.tc-form select,.tc-side select{font:inherit;font-size:13px;color:var(--ink);background:rgba(0,0,0,.25);border:1px solid var(--line);border-radius:8px;padding:5px 8px;color-scheme:dark}',
    '.tc-form input:focus,.tc-form select:focus,.tc-side select:focus{outline:none;border-color:var(--accent)}',
    '.tc-form input[type=text]{flex:1 1 240px;min-width:0}',
    '.tc-form button{font-size:13px;padding:5px 14px}',
    '.tc-group{margin-top:14px;animation:tc-in .35s ease both}',
    '.tc-ghead{display:flex;align-items:center;gap:10px;cursor:pointer;padding:2px 2px 6px;user-select:none}',
    '.tc-gname{font-size:13px;font-weight:600;color:var(--muted);letter-spacing:.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:60%}',
    '.tc-gline{flex:1;height:1px;background:var(--line)}',
    '.tc-gcount{font-size:12px;color:var(--faint);white-space:nowrap}',
    '.tc-caret{font-size:11px;color:var(--faint);transition:transform .2s}',
    '.tc-ghead.closed .tc-caret{transform:rotate(-90deg)}',
    '.tc-ghead:hover .tc-gname{color:var(--ink)}',
    '.tc-hot{color:var(--warn,#F2A33A)}',
    '.tc-row{position:relative;display:flex;align-items:flex-start;gap:12px;padding:8px 10px 8px 14px;border-radius:10px;transition:background .2s,opacity .3s,transform .3s}',
    '.tc-row:hover{background:var(--card-hi)}',
    '.tc-row::before{content:"";position:absolute;left:4px;top:11px;bottom:11px;width:2px;border-radius:2px;background:var(--warn,#F2A33A);opacity:0;box-shadow:0 0 8px var(--warn,#F2A33A)}',
    '.tc-heat1::before{opacity:.22}.tc-heat2::before{opacity:.55}.tc-heat3::before{opacity:1}',
    '.tc-row.tc-ticked{opacity:0;transform:translateX(8px);pointer-events:none}',
    '.tc-kids-list{margin:0 0 4px 24px;padding-left:6px;border-left:1px solid var(--line)}',
    '.tc-kids-list .tc-row{padding-top:6px;padding-bottom:6px}',
    '.tc-kids-list .tc-title{font-size:14px;color:var(--muted)}',
    '.tc-tick{position:relative;width:19px;height:19px;border-radius:50%;border:1.5px solid var(--line-hi);background:transparent;padding:0;flex:none;margin-top:3px;cursor:pointer;transition:border-color .2s,background .2s}',
    '.tc-tick::after{content:"✓";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;line-height:1;color:var(--ok);opacity:0;transition:opacity .15s}',
    '.tc-tick:hover:not(:disabled){border-color:var(--ok);background:transparent}',
    '.tc-tick:hover:not(:disabled)::after{opacity:.6}',
    '.tc-tick:disabled{cursor:not-allowed;opacity:.28}',
    '.tc-ticked .tc-tick{background:var(--ok);border-color:var(--ok)}',
    '.tc-ticked .tc-tick::after{opacity:1;color:var(--bg,#070b16)}',
    '.tc-sync{flex:none;font-size:11px;color:var(--faint);margin-top:3px;min-width:19px}',
    '.tc-main{flex:1;min-width:0}',
    '.tc-title{font-size:15px;color:var(--ink);overflow-wrap:anywhere;line-height:1.5}',
    '.tc-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:1px;font-size:12px;color:var(--faint)}',
    '.tc-meta:empty{display:none}',
    '.tc-p0{font-weight:700;font-size:10.5px;letter-spacing:.5px;color:var(--ink);border:1px solid var(--line-hi);border-radius:5px;padding:0 5px;line-height:16px}',
    '.tc-kids{background:transparent;border:0;border-radius:6px;color:var(--muted);font-size:12px;padding:0 4px;margin-left:-4px}',
    '.tc-kids:hover{background:var(--card-hi);color:var(--ink)}',
    '.tc-side{flex:none;display:flex;gap:6px;align-items:center;transition:opacity .2s}',
    '.tc-side select{font-size:12px;padding:3px 6px;max-width:150px;background:transparent}',
    '.tc-auto{font-size:11px;color:var(--faint)}',
    '@media (hover:hover){.tc-side{opacity:.35}.tc-row:hover .tc-side,.tc-side:focus-within{opacity:1}}',
    '.tc-foot{min-height:0}',
    '.tc-undo{position:relative;overflow:hidden;display:inline-flex;align-items:center;gap:10px;margin-top:10px;padding:6px 8px 6px 12px;border:1px solid var(--line-hi);border-radius:999px;font-size:12.5px;color:var(--muted);background:rgba(0,0,0,.25)}',
    '.tc-undo button{font-size:12px;padding:2px 10px;border-radius:999px}',
    '.tc-undo i{position:absolute;left:0;bottom:0;height:2px;width:100%;background:var(--ok);transform-origin:left;animation:tc-timer 5s linear forwards}',
    '.tc-note{margin-top:10px;font-size:12.5px;color:var(--muted)}',
    '.tc-empty{padding:18px 4px 6px;color:var(--muted);display:flex;gap:10px;align-items:center;flex-wrap:wrap}',
    '.tc-empty b{font-size:18px;color:var(--ok);font-weight:400}',
    '.tc-skel{height:12px;border-radius:6px;margin:12px 0;background:linear-gradient(90deg,var(--card) 0%,var(--card-hi) 50%,var(--card) 100%);background-size:200% 100%;animation:tc-shim 1.4s ease-in-out infinite}',
    '@keyframes tc-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}',
    '@keyframes tc-timer{from{transform:scaleX(1)}to{transform:scaleX(0)}}',
    '@keyframes tc-shim{from{background-position:100% 0}to{background-position:-100% 0}}',
    '@media (max-width:560px){.tc-row{flex-wrap:wrap}.tc-side{width:100%;padding-left:31px}.tc-kids-list{margin-left:10px}.tc-tools{margin-left:0;width:100%}.tc-gname{max-width:70%}}'
  ].join('\n');
  document.head.appendChild(style);

  var S = { data: null, failed: false, mode: 'overdue', groups: {}, kids: {}, formOpen: false,
            form: { title: '', due: '', pri: 'P1', group: '' }, foot: null, pending: false, firstPaint: true };
  var footTimer = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function late(t) { return (t.overdue_days || 0) > 0; }
  function rootLate(r) { return late(r) || (r.children || []).some(late); }
  function heat(days) { return days > 7 ? ' tc-heat3' : days > 3 ? ' tc-heat2' : days > 0 ? ' tc-heat1' : ''; }
  function rootDays(r) {
    return (r.children || []).reduce(function (m, c) { return Math.max(m, c.overdue_days || 0); }, r.overdue_days || 0);
  }
  function when(t) {
    if (late(t)) return '<span class="tc-hot">逾期 ' + t.overdue_days + ' 天</span>';
    var m = String(t.due || '').split('-');
    return m.length === 3 ? '<span>' + parseInt(m[1], 10) + '月' + parseInt(m[2], 10) + '日</span>' : '';
  }
  function p0(t) { return t.priority === 'P0' ? '<span class="tc-p0">P0</span>' : ''; }
  function lateCount(d) {
    var n = 0;
    (d.groups || []).forEach(function (g) {
      (g.roots || []).forEach(function (r) { if (late(r)) n++; n += (r.children || []).filter(late).length; });
    });
    return n;
  }
  // forRow: the per-row picker shows a quiet "移到…" and ticks the current group inside the list;
  // the new-todo form shows the chosen group itself.
  function optionsHtml(current, forRow) {
    var mark = function (key, title) {
      var here = key === current;
      return '<option value="' + esc(key) + '"' + (here && !forRow ? ' selected' : '') + '>' + (here && forRow ? '✓ ' : '') + esc(title) + '</option>';
    };
    var seen = {}, out = forRow ? '<option value="__keep__" selected hidden>移到…</option>' : '';
    out += mark('', '其他');
    ((S.data && S.data.choices) || []).forEach(function (c) { seen[c.key] = 1; out += mark(c.key, c.title); });
    if (current && !seen[current]) out += mark(current, current.replace(/^label:/, ''));
    return out + '<option value="__new__">新分组…</option>';
  }
  function tickHtml(t, isRoot) {
    if (isRoot && t.pending) return '<span class="tc-sync" title="正在写进 Horizon">同步中</span>';
    var hint = isRoot && t.open_children > 0 ? ' title="先做完子待办"' : ' title="做完了"';
    return '<button class="tc-tick" data-act="tc-tick" aria-label="完成"' + (t.tickable ? '' : ' disabled') + hint + '></button>';
  }
  function rowHtml(t, isRoot, days, extra, side) {
    return '<div class="tc-row' + heat(days) + '" data-id="' + esc(t.id) + '" data-title="' + esc(t.title) + '">' +
      tickHtml(t, isRoot) + '<div class="tc-main"><div class="tc-title">' + esc(t.title) + '</div>' +
      '<div class="tc-meta">' + when(t) + p0(t) + (extra || '') + '</div></div>' + (side || '') + '</div>';
  }
  function rootHtml(r, g) {
    var kids = r.children || [], lateKids = kids.filter(late).length;
    var kidsBtn = r.open_children > 0 ? '<button class="tc-kids" data-act="tc-kids" data-id="' + esc(r.id) + '">子待办 ' +
      r.open_children + (lateKids ? ' · <span class="tc-hot">逾期 ' + lateKids + '</span>' : '') + (S.kids[r.id] ? ' ▴' : ' ▾') + '</button>' : '';
    var side = '<div class="tc-side">' + (r.auto ? '<span class="tc-auto" title="这个分组是自动给的，可以改">自动</span>' : '') +
      '<select data-act="tc-assign" data-id="' + esc(r.id) + '" aria-label="移到别的分组">' + optionsHtml(g.key, true) + '</select></div>';
    var html = rowHtml(r, true, rootDays(r), kidsBtn, side);
    if (S.kids[r.id]) {
      var shown = S.mode === 'overdue' ? kids.filter(late) : kids;
      html += '<div class="tc-kids-list">' + shown.map(function (c) { return rowHtml(c, false, 0); }).join('') + '</div>';
    }
    return html;
  }
  function groupHtml(g, i) {
    var roots = S.mode === 'overdue' ? (g.roots || []).filter(rootLate) : (g.roots || []);
    if (!roots.length) return '';
    var open = Object.prototype.hasOwnProperty.call(S.groups, g.key) ? S.groups[g.key] : g.overdue > 0;
    var delay = S.firstPaint ? ' style="animation-delay:' + Math.min(i, 8) * 40 + 'ms"' : ' style="animation:none"';
    return '<div class="tc-group" data-group="' + esc(g.key) + '"' + delay + '>' +
      '<div class="tc-ghead' + (open ? '' : ' closed') + '" data-act="tc-group" data-key="' + esc(g.key) + '">' +
      '<span class="tc-gname">' + esc(g.title) + '</span><span class="tc-gline"></span>' +
      '<span class="tc-gcount">' + (g.overdue ? '<span class="tc-hot">逾期 ' + g.overdue + '</span> · ' : '') + '共 ' + g.open + '</span>' +
      '<span class="tc-caret">▾</span></div>' +
      (open ? roots.map(function (r) { return rootHtml(r, g); }).join('') : '') + '</div>';
  }
  function formHtml() {
    var f = S.form;
    return '<div class="tc-form">' +
      '<input type="text" data-f="title" placeholder="要做什么？回车添加" maxlength="80" value="' + esc(f.title) + '">' +
      '<input type="date" data-f="due" value="' + esc(f.due) + '" aria-label="截止日期">' +
      '<select data-f="pri" aria-label="优先级">' + ['P0', 'P1', 'P2'].map(function (p) {
        return '<option' + (p === f.pri ? ' selected' : '') + '>' + p + '</option>';
      }).join('') + '</select>' +
      '<select data-f="group" aria-label="归到">' + optionsHtml(f.group) + '</select>' +
      '<button class="primary" data-act="tc-add">添加</button></div>';
  }
  function footHtml() {
    var f = S.foot;
    if (!f) return '';
    if (f.kind === 'undo') {
      return '<div class="tc-undo"><span>已完成「' + esc(f.title) + '」</span><button class="ghost" data-act="tc-undo">撤销</button><i></i></div>';
    }
    return '<div class="tc-note">' + esc(f.text) + '</div>';
  }
  function shell(inner) { return '<article class="card tc-card">' + inner + '</article>'; }

  function render() {
    var a = document.activeElement;
    if (S.data && a && host.contains(a) && /^(INPUT|SELECT)$/.test(a.tagName)) { S.pending = true; return; }
    S.pending = false;
    var d = S.data;
    if (!d) {
      host.innerHTML = shell('<div class="tc-head"><h3>待办</h3></div>' + (S.failed
        ? '<div class="tc-empty">待办接口没连上。<button class="ghost tc-new" data-act="tc-retry">重试</button></div>'
        : '<div class="tc-skel" style="width:62%"></div><div class="tc-skel" style="width:78%"></div><div class="tc-skel" style="width:45%"></div>'));
      return;
    }
    var groups = (d.groups || []).map(groupHtml).join('');
    if (!groups) {
      groups = S.mode === 'overdue'
        ? '<div class="tc-empty"><b>✓</b>没有逾期的待办。<button class="ghost tc-new" data-act="tc-filter" data-mode="all">看全部</button></div>'
        : '<div class="tc-empty"><b>✓</b>待办都清空了。</div>';
    }
    var lateN = lateCount(d);
    host.innerHTML = shell(
      '<div class="tc-head"><h3>待办</h3><span class="tc-count">' + ((d.counts && d.counts.open) || 0) + ' 件' +
      (lateN ? ' · <b>逾期 ' + lateN + '</b>' : '') + '</span>' +
      '<div class="tc-tools"><span class="tc-seg" role="group" aria-label="显示">' +
      '<button data-act="tc-filter" data-mode="overdue" class="' + (S.mode === 'overdue' ? 'on' : '') + '">只看逾期</button>' +
      '<button data-act="tc-filter" data-mode="all" class="' + (S.mode === 'all' ? 'on' : '') + '">全部</button></span>' +
      '<button class="ghost tc-new" data-act="tc-new">' + (S.formOpen ? '收起' : '＋ 新建') + '</button></div></div>' +
      (d.copy ? '<div class="tc-copy">这是副本：在这里勾的是 Horizon 的副本，不会改到你真正的待办。</div>' : '') +
      (S.formOpen ? formHtml() : '') + groups + '<div class="tc-foot">' + footHtml() + '</div>');
    S.firstPaint = false;
  }

  function load(force) {
    return fetch('/api/todos', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        S.failed = false;
        if (!force && S.data && d.rev === S.data.rev) return;
        S.data = d;
        render();
      })
      .catch(function () { if (!S.data) { S.failed = true; render(); } });
  }
  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (!r.ok || !j.ok) throw new Error(j.error || r.status);
          return j;
        });
      });
  }
  function setFoot(f, ms) {
    S.foot = f;
    clearTimeout(footTimer);
    footTimer = setTimeout(function () { S.foot = null; render(); }, ms || 5000);
    render();
  }
  function askLabel() {
    var name = (window.prompt('新分组的名字（1–20 个字）') || '').trim();
    return name ? 'label:' + name.slice(0, 20) : null;
  }
  function blurInside() {
    var a = document.activeElement;
    if (a && host.contains(a) && a.blur) a.blur();
  }

  function tick(row) {
    if (!row || row.classList.contains('tc-ticked')) return;
    var id = row.getAttribute('data-id'), title = row.getAttribute('data-title');
    row.classList.add('tc-ticked');
    post('/api/today-tick', { id: 'hz:' + id, done: true })
      .then(function () { return load(true); })
      .then(function () { setFoot({ kind: 'undo', id: id, title: title }, 5000); })
      .catch(function () { row.classList.remove('tc-ticked'); setFoot({ kind: 'text', text: '没记上，再试一次。' }, 4000); });
  }
  function undo() {
    var f = S.foot;
    if (!f || f.kind !== 'undo') return;
    post('/api/today-tick', { id: 'hz:' + f.id, done: false })
      .then(function () { S.foot = null; return load(true); })
      .catch(function () { setFoot({ kind: 'text', text: '没撤销成，再试一次。' }, 4000); });
  }
  function assign(sel) {
    var id = sel.getAttribute('data-id'), key = sel.value;
    if (key === '__keep__') return;
    if (key === '__new__') key = askLabel();
    blurInside();
    if (key === null) { render(); return; }
    post('/api/todos/assign', { todo_id: id.indexOf('new:') === 0 ? id.slice(4) : id, group: key, auto: false })
      .then(function (j) { S.data = j.todos; render(); })
      .catch(function () { render(); setFoot({ kind: 'text', text: '没改成，再试一次。' }, 4000); });
  }
  function add() {
    var f = S.form, title = (f.title || '').trim();
    if (!title) {
      var inp = host.querySelector('input[data-f="title"]');
      if (inp) inp.focus();
      return;
    }
    post('/api/todos', { title: title, due_date: f.due || '', priority: f.pri || 'P1', group: f.group || '' })
      .then(function (j) {
        S.form.title = '';
        S.form.due = '';
        S.data = j.todos;
        blurInside();
        setFoot({ kind: 'text', text: '加好了。写进 Horizon 以后就能勾。' }, 4000);
      })
      .catch(function () { setFoot({ kind: 'text', text: '没加上，再试一次。' }, 4000); });
  }

  host.addEventListener('click', function (e) {
    var el = e.target.closest('[data-act]');
    if (!el || !host.contains(el)) return;
    var act = el.getAttribute('data-act');
    if (act.indexOf('tc-') !== 0) return;
    e.stopPropagation();
    if (el.tagName === 'SELECT') return;
    if (act === 'tc-filter') { S.mode = el.getAttribute('data-mode'); render(); }
    else if (act === 'tc-new') { S.formOpen = !S.formOpen; render(); if (S.formOpen) { var t = host.querySelector('input[data-f="title"]'); if (t) t.focus(); } }
    else if (act === 'tc-group') {
      var k = el.getAttribute('data-key');
      var g = ((S.data && S.data.groups) || []).filter(function (x) { return x.key === k; })[0];
      var cur = Object.prototype.hasOwnProperty.call(S.groups, k) ? S.groups[k] : !!(g && g.overdue > 0);
      S.groups[k] = !cur;
      render();
    }
    else if (act === 'tc-kids') { var rid = el.getAttribute('data-id'); S.kids[rid] = !S.kids[rid]; render(); }
    else if (act === 'tc-tick') tick(el.closest('.tc-row'));
    else if (act === 'tc-undo') undo();
    else if (act === 'tc-add') add();
    else if (act === 'tc-retry') { S.failed = false; render(); load(true); }
  });
  host.addEventListener('change', function (e) {
    var el = e.target;
    if (el.matches('select[data-act="tc-assign"]')) assign(el);
    else if (el.matches('select[data-f="group"]')) {
      if (el.value === '__new__') {
        var key = askLabel();
        if (key) S.form.group = key;
        blurInside();
        render();
      } else S.form.group = el.value;
    } else if (el.matches('[data-f]')) S.form[el.getAttribute('data-f')] = el.value;
  });
  host.addEventListener('input', function (e) {
    if (e.target.matches('input[data-f]')) S.form[e.target.getAttribute('data-f')] = e.target.value;
  });
  host.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.matches('input[data-f="title"]')) { e.preventDefault(); e.stopPropagation(); add(); }
  });
  host.addEventListener('focusout', function () { setTimeout(function () { if (S.pending) render(); }, 0); });

  render();
  load(true);
  setInterval(function () { if (!document.hidden) load(false); }, 5000);
})();
