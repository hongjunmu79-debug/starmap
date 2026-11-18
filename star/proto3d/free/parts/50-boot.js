function resizeStage() {
  viewW = window.innerWidth || 1280;
  viewH = window.innerHeight || 800;
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(viewW * dpr);
  canvas.height = Math.round(viewH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  updateAllProjections();
}

function initStaticUI() {
  const legendItemsEl = document.getElementById('legend-items');
  const legendNoteEl = document.getElementById('legend-note');
  if (legendItemsEl && typeof DATA !== 'undefined' && Array.isArray(DATA.domains)) {
    legendItemsEl.innerHTML = '';
    for (let i = 0; i < DATA.domains.length; i++) {
      const d = DATA.domains[i];
      const item = document.createElement('span');
      item.className = 'legend-item';
      const dot = document.createElement('span');
      dot.className = 'legend-dot';
      dot.style.backgroundColor = d.color;
      dot.style.color = d.color;
      const txt = document.createElement('span');
      txt.textContent = d.name;
      item.appendChild(dot);
      item.appendChild(txt);
      legendItemsEl.appendChild(item);
    }
    const ideaItem = document.createElement('span');
    ideaItem.className = 'legend-item';
    const ideaDot = document.createElement('span');
    ideaDot.className = 'legend-dot';
    const uCol = DATA.unsortedColor || '#e2e8f0';
    ideaDot.style.backgroundColor = uCol;
    ideaDot.style.color = uCol;
    const ideaTxt = document.createElement('span');
    ideaTxt.textContent = '想法';
    ideaItem.appendChild(ideaDot);
    ideaItem.appendChild(ideaTxt);
    legendItemsEl.appendChild(ideaItem);
  }
  if (legendNoteEl && typeof DATA !== 'undefined' && DATA.legendNote) {
    legendNoteEl.textContent = DATA.legendNote;
  }

  const hintEl = document.getElementById('op-hint');
  if (hintEl) {
    if (typeof DATA !== 'undefined' && DATA.hint) {
      hintEl.textContent = DATA.hint;
    }
    setTimeout(function () {
      hintEl.classList.add('fade-out');
    }, 8000);
  }

  const muteBtn = document.getElementById('mute');
  if (muteBtn) {
    let localMuted = false;
    muteBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      if (typeof ensureAudio === 'function') ensureAudio();
      localMuted = !localMuted;
      if (typeof setMuted === 'function') setMuted(localMuted);
      muteBtn.classList.toggle('is-muted', localMuted);
      muteBtn.textContent = localMuted ? '🔇' : '🔊';
    });
  }

  const ideaInput = document.getElementById('idea-input');
  if (ideaInput) {
    setTimeout(function () {
      try { ideaInput.focus(); } catch (_) {}
    }, 20);
    ideaInput.addEventListener('keydown', function (e) {
      if (typeof ensureAudio === 'function') ensureAudio();
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = ideaInput.value.trim();
        if (val) {
          spawnTypedIdea(val);
          ideaInput.value = '';
          renderScene(performance.now());
        }
      }
    });
  }
}

function initForcesPanelAndHealth() {
  if (typeof createForcesPanel === 'function') {
    forcesPanel = createForcesPanel({
      mode: '3d',
      presets: PRESETS,
      initial: {
        center: PRESETS.gemini.center,
        repel: PRESETS.gemini.repel,
        link: PRESETS.gemini.link,
        distance: PRESETS.gemini.distance
      },
      initialMode: 'gemini',
      modelReady: false,
      getStats: function () {
        updateAllProjections();
        return {
          nodes: nodes.length,
          links: links.length,
          ideas: nodes.filter(function (n) { return n.kind === 'idea'; }).length,
          labelOverlaps: computeOverlapsCount(),
          fits: checkFitsInWindow(),
          nearestMin: computeNearestMinScreenDist(),
          constellations: buildConstellationStats()
        };
      },
      onChange: function (values) {
        if (!values || isSyncingForces) return;
        if (values.center !== undefined) forces.center = Math.max(0, Math.min(1, Number(values.center)));
        if (values.repel !== undefined) forces.repel = Math.max(0, Math.min(1, Number(values.repel)));
        if (values.link !== undefined) forces.link = Math.max(0, Math.min(1, Number(values.link)));
        if (values.distance !== undefined) forces.distance = Math.max(0, Math.min(1, Number(values.distance)));
        wakeSim(0.85);
      },
      applyAnchors: function (list) {
        applyAnchors(list);
      }
    });
  }

  if (location.protocol === 'http:' || location.protocol === 'https:') {
    fetch('/api/health')
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (data && data.ok && data.model && forcesPanel && typeof forcesPanel.setModelReady === 'function') {
          forcesPanel.setModelReady(true);
        }
      })
      .catch(function () {});
  }
}

let lastFrameTime = performance.now();
function animateLoop(now) {
  const rawDt = (now - lastFrameTime) / 1000;
  lastFrameTime = now;
  const dt = Math.max(0.001, Math.min(0.05, rawDt));
  const instFps = 1 / Math.max(0.004, rawDt);
  currentFps = currentFps * 0.9 + instFps * 0.1;

  stepPhysics(dt, now);
  stepRubberBands(dt);
  renderScene(now);

  requestAnimationFrame(animateLoop);
}

window.__star3d = {
  nodes: nodes,
  links: links,
  cam: cam,
  audioLog: typeof audioLog !== 'undefined' ? audioLog : [],
  state: function () {
    return {
      nodes: nodes.length,
      links: links.length,
      labels: shownLabelIds.length,
      fps: Math.round(currentFps),
      view: '3d',
      focus: focusId,
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
      const p = project3D(n.x, n.y, n.z);
      return { x: p.x, y: p.y, depth: p.depth };
    },
    screenOfLink: function (a, b, t) {
      const ratio = (t === undefined || t === null) ? 0.5 : Number(t);
      let exists = false;
      for (let i = 0; i < links.length; i++) {
        const l = links[i];
        if ((l.a === a && l.b === b) || (l.a === b && l.b === a)) {
          exists = true;
          break;
        }
      }
      if (!exists) return null;
      const na = nodeMap.get(a);
      const nb = nodeMap.get(b);
      if (!na || !nb) return null;
      const pa = project3D(na.x, na.y, na.z);
      const pb = project3D(nb.x, nb.y, nb.z);
      return {
        x: pa.x + (pb.x - pa.x) * ratio,
        y: pa.y + (pb.y - pa.y) * ratio
      };
    },
    labelsShown: function () {
      return shownLabelIds.slice();
    },
    overlaps: function () {
      return computeOverlapsCount();
    },
    setForces: function (vals) {
      if (!vals) return;
      if (vals.center !== undefined) forces.center = Math.max(0, Math.min(1, Number(vals.center)));
      if (vals.repel !== undefined) forces.repel = Math.max(0, Math.min(1, Number(vals.repel)));
      if (vals.link !== undefined) forces.link = Math.max(0, Math.min(1, Number(vals.link)));
      if (vals.distance !== undefined) forces.distance = Math.max(0, Math.min(1, Number(vals.distance)));
      if (forcesPanel) {
        isSyncingForces = true;
        try {
          if (typeof forcesPanel.setMode === 'function') forcesPanel.setMode('manual');
          if (typeof forcesPanel.setValues === 'function') forcesPanel.setValues({ ...forces }, false);
        } finally {
          isSyncingForces = false;
        }
      }
      for (let i = 0; i < 36; i++) {
        simAlpha = 0.85;
        stepPhysics(0.016, performance.now());
      }
      wakeSim(0.85);
      renderScene(performance.now());
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

window.addEventListener('resize', resizeStage);
resizeStage();
initGraphFromData();
warmUpSimulation(170);
initStaticUI();
setupInputHandlers();
initForcesPanelAndHealth();
renderScene(performance.now());
requestAnimationFrame(animateLoop);
