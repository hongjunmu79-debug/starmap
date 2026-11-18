/* FORCES-PANEL:BEGIN */
/* 布局力面板：向心力、排斥力、连线吸引力、连线长度（参考 Obsidian 图谱的 Forces），
   加四种方式：Claude 调的一组 / Gemini 调的一组 / 手动拖滑块 / DeepSeek 重排。
   自包含：自己注入样式、自己建 DOM，不依赖页面里的任何变量。

   const panel = createForcesPanel({
     mode: '2d',                       // '2d' 或 '3d'，只用来告诉 DeepSeek 要不要给 z
     presets: { claude: {center, repel, link, distance}, gemini: {…} },   // 四个数都在 0 到 1
     initial: { center, repel, link, distance },  initialMode: 'claude',
     modelReady: false,                // 能不能用 DeepSeek（页面是通过本机服务打开的才为 true）
     getStats: () => ({ nodes, links, ideas, labelOverlaps, fits, nearestMin, constellations: [{id,title,members,ideas,status}] }),
     onChange: (values) => {},         // 数值每变一次就调用一次（拖滑块、预设过渡的每一帧、重排）
     applyAnchors: (anchors) => {}     // DeepSeek 给的星座目标位置 [{id,x,y,z?}]，x,y,z 都在 -1 到 1
   });
   panel.setValues({center:0.5}, animate)  panel.getValues()  panel.mode()  panel.setMode('manual')
   panel.open()  panel.close()  panel.isOpen()  panel.setModelReady(true)  panel.rearrange()  panel.setWhy('一句话')
*/
function createForcesPanel(opts) {
  opts = opts || {};
  var ROWS = [
    ['center', '向心力', '把所有节点往中间拉，越大越集中'],
    ['repel', '排斥力', '节点之间互相推开，越大越松'],
    ['link', '连线吸引力', '相连的节点互相拉近'],
    ['distance', '连线长度', '相连节点之间的距离']
  ];
  var CHIPS = [['claude', 'Claude'], ['gemini', 'Gemini'], ['manual', '手动'], ['deepseek', 'DeepSeek 重排']];
  var st = {
    values: Object.assign({ center: 0.5, repel: 0.5, link: 0.5, distance: 0.5 }, opts.initial || {}),
    mode: opts.initialMode || 'claude', busy: false, modelReady: !!opts.modelReady, tween: 0, open: false
  };
  var presets = opts.presets || {};

  if (!document.getElementById('forces-panel-style')) {
    var css = document.createElement('style');
    css.id = 'forces-panel-style';
    css.textContent =
      '#forces-btn{pointer-events:auto;width:24px;height:24px;padding:0;border:0;background:transparent;color:#EEF1FA;opacity:.5;cursor:pointer;display:grid;place-items:center}' +
      '#forces-btn:hover,#forces-btn.on{opacity:.92}#forces-btn svg{width:20px;height:20px;display:block}' +
      '#forces-panel{position:fixed;top:56px;right:24px;width:292px;z-index:9;padding:14px 16px 12px;border-radius:12px;background:rgba(14,18,32,.88);' +
      '-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.1);color:#EEF1FA;' +
      'font:12px/1.45 var(--font,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif);display:none;user-select:none}' +
      '#forces-panel.open{display:block}' +
      '#forces-panel .fp-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-size:13px;font-weight:600}' +
      '#forces-panel .fp-x{border:0;background:transparent;color:#EEF1FA;opacity:.55;cursor:pointer;font-size:16px;line-height:1;padding:0 2px}' +
      '#forces-panel .fp-x:hover{opacity:.95}' +
      '#forces-panel .fp-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}' +
      '#forces-panel .fp-chip{height:26px;padding:0 10px;border-radius:13px;border:1px solid rgba(255,255,255,.14);background:transparent;color:#EEF1FA;opacity:.7;cursor:pointer;font:inherit}' +
      '#forces-panel .fp-chip:hover{opacity:1}' +
      '#forces-panel .fp-chip.on{opacity:1;border-color:rgba(220,211,255,.75);background:rgba(155,123,255,.2)}' +
      '#forces-panel .fp-chip[disabled]{opacity:.32;cursor:not-allowed}' +
      '#forces-panel .fp-row{margin:8px 0 10px}' +
      '#forces-panel .fp-lab{display:flex;justify-content:space-between;margin-bottom:3px}' +
      '#forces-panel .fp-lab span:last-child{opacity:.6;font-variant-numeric:tabular-nums}' +
      '#forces-panel input[type=range]{width:100%;margin:0;accent-color:#9B7BFF;cursor:pointer}' +
      '#forces-panel .fp-why{min-height:17px;margin-top:6px;opacity:.7;font-size:12px}';
    document.head.appendChild(css);
  }

  var btn = document.createElement('button');
  btn.id = 'forces-btn';
  btn.type = 'button';
  btn.title = '布局力：向心力、排斥力、连线吸引力、连线长度';
  btn.setAttribute('aria-label', '布局力');
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h16M4 17h16M9 5v4M15 10v4M7 15v4"/></svg>';
  var host = document.getElementById('top-right');
  var mute = document.getElementById('mute');
  if (host) host.insertBefore(btn, mute && mute.parentNode === host ? mute : null);
  else { btn.style.cssText = 'position:fixed;top:22px;right:60px;z-index:9;opacity:.6'; document.body.appendChild(btn); }

  var panel = document.createElement('div');
  panel.id = 'forces-panel';
  var html = '<div class="fp-head"><span>布局力</span><button class="fp-x" type="button" aria-label="关闭">×</button></div><div class="fp-chips">';
  CHIPS.forEach(function (c) { html += '<button class="fp-chip" type="button" data-mode="' + c[0] + '">' + c[1] + '</button>'; });
  html += '</div>';
  ROWS.forEach(function (r) {
    html += '<div class="fp-row" title="' + r[2] + '"><div class="fp-lab"><span>' + r[1] + '</span><span data-val="' + r[0] + '"></span></div>' +
            '<input type="range" min="0" max="100" step="1" data-key="' + r[0] + '"></div>';
  });
  html += '<div class="fp-why"></div>';
  panel.innerHTML = html;
  document.body.appendChild(panel);
  ['pointerdown', 'pointerup', 'click', 'wheel'].forEach(function (t) {
    panel.addEventListener(t, function (e) { e.stopPropagation(); });
    btn.addEventListener(t, function (e) { e.stopPropagation(); });
  });

  var chipEls = panel.querySelectorAll('.fp-chip');
  var sliders = panel.querySelectorAll('input[type=range]');
  var whyEl = panel.querySelector('.fp-why');

  function notify() { if (opts.onChange) opts.onChange(Object.assign({}, st.values)); }
  function render() {
    chipEls.forEach(function (el) {
      var m = el.getAttribute('data-mode');
      el.classList.toggle('on', st.mode === m);
      el.setAttribute('aria-pressed', st.mode === m ? 'true' : 'false');
      if (m === 'deepseek') {
        el.disabled = !st.modelReady || st.busy;
        el.textContent = st.busy ? 'DeepSeek …' : 'DeepSeek 重排';
        el.title = st.modelReady ? '请 DeepSeek 看一眼这张图，给出一组新的数值和星座位置' : '需要通过本机服务打开（双击 start-star.bat）才能用';
      }
    });
    sliders.forEach(function (el) {
      var k = el.getAttribute('data-key');
      var v = Math.round(st.values[k] * 100);
      if (document.activeElement !== el || !st.tween) el.value = v;
      var out = panel.querySelector('[data-val="' + k + '"]');
      if (out) out.textContent = v;
    });
    btn.classList.toggle('on', st.open);
  }
  function setWhy(t) { whyEl.textContent = t || ''; }
  function clamp01(v) { v = Number(v); return v === v ? Math.max(0, Math.min(1, v)) : 0.5; }

  function setValues(v, animate) {
    cancelAnimationFrame(st.tween); st.tween = 0;
    var target = {}, from = Object.assign({}, st.values);
    ROWS.forEach(function (r) { var k = r[0]; target[k] = v && v[k] != null ? clamp01(v[k]) : st.values[k]; });
    if (!animate) { st.values = target; render(); notify(); return; }
    var t0 = performance.now(), ms = 800;
    (function step(now) {
      var p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      ROWS.forEach(function (r) { var k = r[0]; st.values[k] = from[k] + (target[k] - from[k]) * e; });
      render(); notify();
      if (p < 1) st.tween = requestAnimationFrame(step); else st.tween = 0;
    })(t0);
  }
  function setMode(m) { st.mode = m; render(); }
  function open() { st.open = true; panel.classList.add('open'); render(); }
  function close() { st.open = false; panel.classList.remove('open'); render(); }

  function rearrange() {
    if (st.busy || !st.modelReady) return Promise.resolve(false);
    st.busy = true; render(); setWhy('DeepSeek 想一想…');
    var ctrl = new AbortController(), to = setTimeout(function () { ctrl.abort(); }, 15000);
    var body = { mode: opts.mode || '2d', viewport: [innerWidth, innerHeight], current: Object.assign({}, st.values), stats: opts.getStats ? opts.getStats() : {} };
    return fetch('/api/layout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal })
      .then(function (r) { clearTimeout(to); if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (res) {
        st.mode = 'deepseek';
        setValues({ center: res.center, repel: res.repel, link: res.link, distance: res.distance }, true);
        if (opts.applyAnchors && res.anchors && res.anchors.length) opts.applyAnchors(res.anchors);
        setWhy(res.why || '已重排');
        return true;
      })
      .catch(function () { clearTimeout(to); setWhy('没连上模型，保持现在的布局'); return false; })
      .then(function (ok) { st.busy = false; render(); return ok; });
  }

  chipEls.forEach(function (el) {
    el.addEventListener('click', function () {
      var m = el.getAttribute('data-mode');
      if (m === 'deepseek') { rearrange(); return; }
      st.mode = m;
      if (m === 'claude' || m === 'gemini') { if (presets[m]) { setValues(presets[m], true); setWhy(m === 'claude' ? 'Claude 调的一组' : 'Gemini 调的一组'); } }
      else setWhy('拖滑块自己调');
      render();
    });
  });
  sliders.forEach(function (el) {
    el.addEventListener('input', function () {
      cancelAnimationFrame(st.tween); st.tween = 0;
      st.values[el.getAttribute('data-key')] = clamp01(el.value / 100);
      st.mode = 'manual'; setWhy('手动');
      render(); notify();
    });
  });
  btn.addEventListener('click', function () { if (st.open) close(); else open(); });
  panel.querySelector('.fp-x').addEventListener('click', close);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && st.open) { close(); e.stopPropagation(); e.preventDefault(); }
  }, true);

  render();
  return {
    setValues: setValues, getValues: function () { return Object.assign({}, st.values); },
    mode: function () { return st.mode; }, setMode: setMode, open: open, close: close, isOpen: function () { return st.open; },
    setModelReady: function (b) { st.modelReady = !!b; render(); }, rearrange: rearrange, setWhy: setWhy
  };
}
/* FORCES-PANEL:END */
