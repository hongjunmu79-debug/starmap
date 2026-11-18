function resizeCanvas() {
  W = window.innerWidth;
  H = window.innerHeight;
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function initUIElements() {
  const legendItemsEl = document.getElementById('legend-items');
  const legendNoteEl = document.getElementById('legend-note');
  if (legendItemsEl && DATA && Array.isArray(DATA.domains)) {
    legendItemsEl.innerHTML = '';
    for (let i = 0; i < DATA.domains.length; i++) {
      const d = DATA.domains[i];
      const item = document.createElement('div');
      item.className = 'legend-item';
      const dot = document.createElement('span');
      dot.className = 'legend-dot';
      dot.style.background = d.color;
      dot.style.boxShadow = '0 0 8px ' + d.color;
      const name = document.createElement('span');
      name.textContent = d.name;
      item.appendChild(dot);
      item.appendChild(name);
      legendItemsEl.appendChild(item);
    }
  }
  if (legendNoteEl && DATA && DATA.legendNote) {
    legendNoteEl.textContent = DATA.legendNote;
  }

  const hintEl = document.getElementById('top-left-hint');
  if (hintEl) {
    if (DATA && DATA.hint) {
      hintEl.textContent = DATA.hint;
    }
    setTimeout(function () {
      hintEl.classList.add('fade-out');
    }, 8000);
  }

  const muteBtn = document.getElementById('mute');
  if (muteBtn) {
    muteBtn.addEventListener('click', function () {
      if (typeof ensureAudio === 'function') ensureAudio();
      const nextMuted = typeof muted !== 'undefined' ? !muted : false;
      if (typeof setMuted === 'function') setMuted(nextMuted);
      muteBtn.classList.toggle('is-muted', nextMuted);
      muteBtn.textContent = nextMuted ? '✕' : '♪';
    });
  }

  const ideaInput = document.getElementById('idea-input');
  if (ideaInput) {
    ideaInput.addEventListener('keydown', function (e) {
      if (typeof ensureAudio === 'function') ensureAudio();
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = ideaInput.value.trim();
        if (val) {
          addNewIdeaFromInput(val);
          ideaInput.value = '';
        }
      }
    });
    setTimeout(function () {
      try {
        ideaInput.focus();
      } catch (err) {}
    }, 30);
  }

  window.addEventListener('keydown', function (e) {
    if (typeof ensureAudio === 'function') ensureAudio();
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
      const active = document.activeElement;
      if (!active || active.id !== 'idea-input' || !active.value) {
        if (cutHistory.length > 0) {
          e.preventDefault();
          undoLastCutBatch();
        }
      }
    } else if (e.key === 'Escape') {
      if (focusedId) {
        setFocusNode(null);
      }
    }
  });
}

function computePanelStats() {
  let activeLinkCount = 0;
  for (let i = 0; i < links.length; i++) {
    if (!links[i].cut) activeLinkCount += 1;
  }

  let ideaCount = 0;
  let allFit = true;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.kind === 'idea') ideaCount += 1;
    if (n.sx - n.sr < 0 || n.sx + n.sr > W || n.sy - n.sr < 0 || n.sy + n.sr > H) {
      allFit = false;
    }
  }

  let minScreenDist = Infinity;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const d = Math.hypot(nodes[i].sx - nodes[j].sx, nodes[i].sy - nodes[j].sy);
      if (d < minScreenDist) minScreenDist = d;
    }
  }
  if (!isFinite(minScreenDist)) minScreenDist = 0;

  const constStats = [];
  const rawConsts = (DATA && DATA.constellations) || [];
  for (let i = 0; i < rawConsts.length; i++) {
    const c = rawConsts[i];
    const cid = 'item:' + c.id;
    let memberCount = 0;
    let connectedIdeas = 0;
    for (let j = 0; j < nodes.length; j++) {
      if (nodes[j].kind === 'member' && nodes[j].parentId === cid) {
        memberCount += 1;
      }
    }
    for (let j = 0; j < links.length; j++) {
      const l = links[j];
      if (l.cut) continue;
      if (l.a === cid || l.b === cid) {
        const otherId = l.a === cid ? l.b : l.a;
        const other = nodeMap.get(otherId);
        if (other && other.kind === 'idea') connectedIdeas += 1;
      }
    }
    constStats.push({
      id: c.id,
      title: c.title,
      members: memberCount,
      ideas: connectedIdeas,
      status: c.status
    });
  }

  return {
    nodes: nodes.length,
    links: activeLinkCount,
    ideas: ideaCount,
    labelOverlaps: lastLabelOverlaps,
    fits: allFit,
    nearestMin: Math.round(minScreenDist * 10) / 10,
    constellations: constStats
  };
}
