/* 星图「一键连接」：让大模型把事和想法之间的联系一次连好，可以一键撤销。
   POST /api/star/relink 写一批连线（页面靠热合并画出来）；POST /api/star/relink-undo 撤销最近一批；
   GET /api/star/relink-status 让刷新后也能撤销。自带样式，不往 window 上挂任何名字。 */
(function () {
  'use strict';
  var bar = document.getElementById('top-right');
  if (!bar) return;

  var style = document.createElement('style');
  style.textContent = [
    '.rl-wrap{display:inline-flex;gap:8px;align-items:center;margin-right:12px;pointer-events:auto}',  // #top-right itself ignores the mouse; its controls opt back in
    '.rl-btn{background:transparent;border:1px solid rgba(255,255,255,.24);color:inherit;font:inherit;font-size:13px;padding:2px 10px;border-radius:999px;cursor:pointer}',
    '.rl-btn:hover{border-color:rgba(255,255,255,.55)}',
    '.rl-btn[disabled]{opacity:.6;cursor:progress}',
    '.rl-undo{background:transparent;border:0;color:inherit;opacity:.65;font:inherit;font-size:12px;cursor:pointer;text-decoration:underline;padding:0}',
    '.rl-toast{position:fixed;left:50%;bottom:96px;transform:translateX(-50%);background:rgba(10,14,24,.9);color:#fff;font-size:13px;' +
      'padding:8px 14px;border-radius:12px;z-index:999998;display:flex;gap:10px;align-items:center;box-shadow:0 6px 24px rgba(0,0,0,.4);max-width:calc(100vw - 32px)}',
    '.rl-toast[hidden]{display:none}',
    '.rl-toast button{background:transparent;border:1px solid rgba(255,255,255,.35);color:#fff;border-radius:8px;padding:1px 8px;font-size:12px;cursor:pointer}'
  ].join('\n');
  document.head.appendChild(style);

  var wrap = document.createElement('span');
  wrap.className = 'rl-wrap';
  wrap.innerHTML = '<button class="rl-btn" type="button" title="让大模型把事和想法之间的联系一次连好，连错了可以撤销">一键连接</button>' +
    '<button class="rl-undo" type="button" hidden>撤销上次连接</button>';
  bar.insertBefore(wrap, bar.firstChild);
  var btn = wrap.querySelector('.rl-btn'), undoBtn = wrap.querySelector('.rl-undo');
  var toastEl = null, toastTimer = null, busy = false;
  ['pointerdown', 'mousedown', 'click'].forEach(function (t) { wrap.addEventListener(t, function (e) { e.stopPropagation(); }); });

  function toast(text, withUndo) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'rl-toast';
      document.body.appendChild(toastEl);
      toastEl.addEventListener('pointerdown', function (e) { e.stopPropagation(); });
      toastEl.addEventListener('click', function (e) {
        e.stopPropagation();
        if (e.target.closest('[data-rl-undo]')) undo();
      });
    }
    toastEl.innerHTML = '<span></span>' + (withUndo ? '<button type="button" data-rl-undo>撤销</button>' : '');
    toastEl.firstChild.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, withUndo ? 12000 : 5000);
  }
  function mapQuery() {
    var q = new URLSearchParams(location.search || '');
    var m = q.get('map');
    return (m && m !== 'main') ? ('?map=' + encodeURIComponent(m)) : '';
  }
  function post(url) {
    var ctl = new AbortController(), timer = setTimeout(function () { ctl.abort(); }, 120000);
    return fetch(url + mapQuery(), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: ctl.signal })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { clearTimeout(timer); j._status = r.status; return j; });
      });
  }
  function refreshStatus() {
    fetch('/api/star/relink-status' + mapQuery(), { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (j) { undoBtn.hidden = !(j && j.last && j.last.batch && !j.last.undone); })
      .catch(function () {});
  }
  function summary(j) {
    var parts = [];
    if (j.added) parts.push('新连 ' + j.added + ' 条');
    if (j.changed) parts.push('改了 ' + j.changed + ' 条');
    if (j.removed) parts.push('断了 ' + j.removed + ' 条');
    return parts.join('，') + (j.kept_user ? '（你自己连的 ' + j.kept_user + ' 条没动）' : '');
  }
  function undo() {
    post('/api/star/relink-undo')
      .then(function (j) {
        if (j._status === 200 && j.ok && j.undone) {
          toast('撤销了：' + (j.reverted || 0) + ' 条线回到连接之前' + (j.skipped ? '（' + j.skipped + ' 条你后来改过，没动）' : ''));
        } else if (j._status === 200 && j.ok) toast('没有可以撤销的连接');
        else toast('没撤销成，再试一次');
      })
      .catch(function () { toast('没撤销成，再试一次'); })
      .then(refreshStatus);
  }

  btn.addEventListener('click', function () {
    if (busy) return;
    busy = true;
    btn.disabled = true;
    btn.textContent = '连接中…';
    try { window.dispatchEvent(new CustomEvent('star-relink-start')); } catch (e) {}
    post('/api/star/relink')
      .then(function (j) {
        if (j._status === 200 && j.ok) toast(j.batch ? summary(j) : '没有新的联系', !!j.batch);
        else if (j._status === 503) toast('还没配置大模型，连不了');
        else if (j._status === 409) toast('正在连，稍等一下');
        else if (j._status === 502) toast('模型没连上，稍后再试');
        else toast('没连成，再试一次');
        try { window.dispatchEvent(new CustomEvent('star-relink-end', { detail: j })); } catch (e) {}
      })
      .catch(function () {
        toast('没连成，再试一次');
        try { window.dispatchEvent(new CustomEvent('star-relink-end', { detail: { ok: false } })); } catch (e) {}
      })
      .then(function () { busy = false; btn.disabled = false; btn.textContent = '一键连接'; refreshStatus(); });
  });
  undoBtn.addEventListener('click', undo);
  window.addEventListener('star-map-changed', refreshStatus);
  refreshStatus();
})();
