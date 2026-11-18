function clamp01(v, fallback) {
  const num = Number(v);
  if (isNaN(num)) return fallback;
  return Math.max(0, Math.min(1, num));
}

function applyForceValues(v) {
  if (!v) return;
  forces.center = clamp01(v.center, forces.center);
  forces.repel = clamp01(v.repel, forces.repel);
  forces.link = clamp01(v.link, forces.link);
  forces.distance = clamp01(v.distance, forces.distance);
  simAlpha = Math.max(simAlpha, 0.4);
}

function handleApplyAnchors(list) {
  if (!Array.isArray(list) || list.length === 0) return;
  anchorTargets = new Map();
  for (let i = 0; i < list.length; i++) {
    const item = list[i];
    if (!item || !item.id) continue;
    const id = String(item.id).startsWith('item:') ? String(item.id) : 'item:' + item.id;
    const tx = Math.max(-1, Math.min(1, Number(item.x) || 0)) * 420;
    const ty = Math.max(-1, Math.min(1, Number(item.y) || 0)) * 320;
    const tz = Math.max(-1, Math.min(1, Number(item.z) || 0)) * 260;
    anchorTargets.set(id, { x: tx, y: ty, z: tz });
    const n = nodeMap.get(id);
    if (n) n.pinned = false;
  }
  anchorTimer = 3.0;
  simAlpha = Math.max(simAlpha, 0.5);
}

function initForcesPanelAndHealth() {
  if (typeof createForcesPanel === 'function') {
    forcesPanel = createForcesPanel({
      mode: '3d',
      presets: PRESETS,
      initial: {
        center: PRESETS.claude.center,
        repel: PRESETS.claude.repel,
        link: PRESETS.claude.link,
        distance: PRESETS.claude.distance
      },
      initialMode: 'claude',
      modelReady: false,
      getStats: computePanelStats,
      onChange: function (values) {
        applyForceValues(values);
      },
      applyAnchors: handleApplyAnchors
    });
  }

  if (location.protocol === 'http:' || location.protocol === 'https:') {
    fetch('/api/health')
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .then(function (data) {
        if (data && data.ok && data.model && forcesPanel && typeof forcesPanel.setModelReady === 'function') {
          forcesPanel.setModelReady(true);
        }
      })
      .catch(function () {});
  }
}

function installTestHook() {
  window.__star3d = {
    nodes: nodes,
    links: links,
    cam: cam,
    audioLog: typeof audioLog !== 'undefined' ? audioLog : [],
    state: function () {
      let activeLinks = 0;
      for (let i = 0; i < links.length; i++) {
        if (!links[i].cut) activeLinks += 1;
      }
      let shownLabels = 0;
      for (let i = 0; i < nodes.length; i++) {
        if (nodes[i].labelShown) shownLabels += 1;
      }
      return {
        nodes: nodes.length,
        links: activeLinks,
        labels: shownLabels,
        fps: Math.round(fpsValue),
        view: '3d',
        focus: focusedId,
        forces: {
          center: forces.center,
          repel: forces.repel,
          link: forces.link,
          distance: forces.distance
        }
      };
    },
    test: {
      screenOf: function (id) {
        const n = nodeMap.get(id);
        if (!n) return null;
        return { x: n.sx, y: n.sy, depth: n.depth };
      },
      screenOfLink: function (a, b, t) {
        const u = t === undefined ? 0.5 : t;
        let found = null;
        for (let i = 0; i < links.length; i++) {
          const l = links[i];
          if (!l.cut && ((l.a === a && l.b === b) || (l.a === b && l.b === a))) {
            found = l;
            break;
          }
        }
        if (!found) return null;
        const na = nodeMap.get(a);
        const nb = nodeMap.get(b);
        if (!na || !nb) return null;
        if (elastic && elastic.link === found) {
          if (u <= 0.5) {
            const k = u * 2;
            return { x: na.sx + (elastic.px - na.sx) * k, y: na.sy + (elastic.py - na.sy) * k };
          } else {
            const k = (u - 0.5) * 2;
            return { x: elastic.px + (nb.sx - elastic.px) * k, y: elastic.py + (nb.sy - elastic.py) * k };
          }
        }
        return {
          x: na.sx + (nb.sx - na.sx) * u,
          y: na.sy + (nb.sy - na.sy) * u
        };
      },
      labelsShown: function () {
        const arr = [];
        for (let i = 0; i < nodes.length; i++) {
          if (nodes[i].labelShown) arr.push(nodes[i].id);
        }
        return arr;
      },
      overlaps: function () {
        return countLabelOverlaps();
      },
      setForces: function (vals) {
        applyForceValues(vals);
        if (forcesPanel) {
          if (typeof forcesPanel.setMode === 'function') forcesPanel.setMode('manual');
          if (typeof forcesPanel.setValues === 'function') forcesPanel.setValues(forces, false);
        }
      },
      getForces: function () {
        return {
          center: forces.center,
          repel: forces.repel,
          link: forces.link,
          distance: forces.distance
        };
      }
    }
  };
}

function boot() {
  resizeCanvas();
  window.addEventListener('resize', function () {
    resizeCanvas();
    updateProjections(0.016);
    renderFrame(performance.now() * 0.001);
  });

  initBgStars();
  buildGraphFromData();
  prewarmPhysics(300);
  updateProjections(0.016);
  initUIElements();
  setupInputEvents();
  initForcesPanelAndHealth();
  installTestHook();
  renderFrame(0);

  let lastFrameTime = performance.now();
  function frame(now) {
    const rawDt = Math.max(0.001, (now - lastFrameTime) / 1000);
    lastFrameTime = now;
    const instFps = 1 / rawDt;
    fpsValue = fpsValue * 0.9 + Math.min(120, instFps) * 0.1;

    stepPhysicsTick();
    stepCameraAndEffects(rawDt);
    updateProjections(rawDt);
    renderFrame(now * 0.001);

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

boot();
