function stepRubberBands(dt) {
  const subSteps = 2;
  const subDt = Math.min(dt, 0.03) / subSteps;
  for (let i = rubberBands.length - 1; i >= 0; i--) {
    const b = rubberBands[i];
    const na = nodeMap.get(b.link.a);
    const nb = nodeMap.get(b.link.b);
    if (!na || !nb || !links.includes(b.link)) {
      rubberBands.splice(i, 1);
      continue;
    }
    const mx = (na.sx + nb.sx) * 0.5;
    const my = (na.sy + nb.sy) * 0.5;
    for (let s = 0; s < subSteps; s++) {
      if (b.dragging) {
        const dx = b.pointerX - mx;
        const dy = b.pointerY - my;
        const d = Math.hypot(dx, dy);
        const disp = 125 * Math.tanh(d / 125);
        b.tension = disp / 125;
        const tx = d > 0.001 ? (dx / d) * disp : 0;
        const ty = d > 0.001 ? (dy / d) * disp : 0;
        const w = 26, z = 0.5;
        b.vx += (-2 * w * z * b.vx + w * w * (tx - b.ox)) * subDt;
        b.vy += (-2 * w * z * b.vy + w * w * (ty - b.oy)) * subDt;
        b.ox += b.vx * subDt;
        b.oy += b.vy * subDt;
      } else {
        const w = 20, z = 0.2;
        b.vx += (-2 * w * z * b.vx - w * w * b.ox) * subDt;
        b.vy += (-2 * w * z * b.vy - w * w * b.oy) * subDt;
        b.ox += b.vx * subDt;
        b.oy += b.vy * subDt;
        b.tension = Math.min(1, Math.hypot(b.ox, b.oy) / 125);
      }
    }
    if (!b.dragging && Math.hypot(b.ox, b.oy) < 0.35 && Math.hypot(b.vx, b.vy) < 2.2) {
      rubberBands.splice(i, 1);
    }
  }
}

function spawnSparkBetween(lk, ox, oy) {
  const na = nodeMap.get(lk.a);
  const nb = nodeMap.get(lk.b);
  if (!na || !nb) return null;

  const k1 = lk.a + '|' + lk.b;
  const k2 = lk.b + '|' + lk.a;
  const sparkText = (typeof DATA !== 'undefined' && DATA.sparks && (DATA.sparks[k1] || DATA.sparks[k2]))
    || (typeof DATA !== 'undefined' && DATA.sparkPlaceholder)
    || '两者之间';
  const sparkLens = (typeof DATA !== 'undefined' && DATA.sparkLens) || '两者之间';

  const mx = (na.sx + nb.sx) * 0.5;
  const my = (na.sy + nb.sy) * 0.5;
  let vx = ox, vy = oy;
  if (Math.hypot(vx, vy) < 8) {
    const ldx = nb.sx - na.sx;
    const ldy = nb.sy - na.sy;
    const ll = Math.hypot(ldx, ldy) || 1;
    vx = (-ldy / ll) * 75;
    vy = (ldx / ll) * 75;
  }
  const avgDepth = (na.depth + nb.depth) * 0.5;
  const wDelta = screenDeltaToWorld(vx * 1.28, vy * 1.28, avgDepth);

  sparkSeq += 1;
  const pid = 'poss:spark-' + sparkSeq;
  const now = performance.now();
  const pNode = addNode({
    id: pid,
    rawId: 'spark-' + sparkSeq,
    parentId: lk.a,
    kind: 'poss',
    label: sparkText,
    lens: sparkLens,
    icon: getLensIcon(sparkLens),
    color: (typeof DATA !== 'undefined' && DATA.unsortedColor) || '#e2e8f0',
    bright: 1.0,
    r: 13,
    x: (na.x + nb.x) * 0.5 + wDelta.x,
    y: (na.y + nb.y) * 0.5 + wDelta.y,
    z: (na.z + nb.z) * 0.5 + wDelta.z,
    bornAt: now
  });

  addLink({ a: lk.a, b: pid, kind: 'poss', lens: sparkLens });
  addLink({ a: lk.b, b: pid, kind: 'poss', lens: sparkLens });

  sparks.push({
    x0: mx + ox,
    y0: my + oy,
    targetId: pid,
    born: now,
    duration: 0.42,
    color: '#fbbf24'
  });

  if (focusId) rebuildFocusSet();
  wakeSim(0.55);
  updateAllProjections();
  return pNode;
}

function keepPossibilityNode(node) {
  if (!node || node.kind !== 'poss') return;
  node.kind = 'kept';
  node.bright = 1.05;
  node.r = 14.5;
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if ((l.a === node.id || l.b === node.id) && l.kind === 'poss') {
      l.kind = 'kept';
    }
  }
  wakeSim(0.45);
}

function findClosestTextNode(text) {
  let best = null;
  let bestScore = 0;
  const chars = Array.from(new Set(text.split('').filter(c => c.trim())));
  if (!chars.length) return null;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (!n.label) continue;
    let score = 0;
    for (let c = 0; c < chars.length; c++) {
      if (n.label.indexOf(chars[c]) !== -1) score += 1;
    }
    if (score > bestScore) {
      bestScore = score;
      best = n;
    }
  }
  return bestScore > 0 ? best : null;
}

function spawnTypedIdea(rawText) {
  const text = (rawText || '').trim();
  if (!text) return null;
  typedSeq += 1;
  const id = 'idea:typed-' + typedSeq;
  const match = findClosestTextNode(text);
  let wx, wy, wz;
  if (match) {
    const ang = (typedSeq * 1.7) % (Math.PI * 2);
    wx = match.x + Math.cos(ang) * 72;
    wy = match.y + Math.sin(ang) * 62;
    wz = match.z + (typedSeq % 2 === 0 ? 34 : -34);
  } else {
    const offset = ((typedSeq - 1) % 3 - 1) * 58;
    const wPos = cameraToWorld(offset, -15, -75);
    wx = wPos.x;
    wy = wPos.y;
    wz = wPos.z;
  }

  const now = performance.now();
  const ideaColor = (typeof DATA !== 'undefined' && DATA.unsortedColor) || '#f1f5f9';
  const ideaNode = addNode({
    id: id,
    rawId: 'typed-' + typedSeq,
    kind: 'idea',
    label: text,
    icon: 'spark',
    color: ideaColor,
    bright: 1.0,
    r: 16.5,
    x: wx,
    y: wy,
    z: wz,
    bornAt: now
  });

  const placeholders = (typeof DATA !== 'undefined' && Array.isArray(DATA.placeholder) && DATA.placeholder.length)
    ? DATA.placeholder.slice(0, 3)
    : [
        { lens: '可以变成', text: '做成一个小实验' },
        { lens: '反过来想', text: '如果完全反过来呢' },
        { lens: '下一步', text: '先画第一张草图' }
      ];

  for (let i = 0; i < placeholders.length; i++) {
    const p = placeholders[i];
    const pAngle = (i / placeholders.length) * Math.PI * 2 - 0.5;
    const pid = 'poss:typed-' + typedSeq + '-' + (i + 1);
    addNode({
      id: pid,
      rawId: 'typed-' + typedSeq + '-' + (i + 1),
      parentId: id,
      kind: 'poss',
      label: p.text || '',
      lens: p.lens || '',
      icon: getLensIcon(p.lens),
      color: ideaColor,
      bright: 0.9,
      r: 12.5,
      x: wx + Math.cos(pAngle) * 62,
      y: wy + Math.sin(pAngle) * 62,
      z: wz + (i - 1) * 26,
      bornAt: now
    });
    addLink({ a: id, b: pid, kind: 'poss', lens: p.lens || '' });
  }

  for (let k = 0; k < 18; k++) {
    simAlpha = 0.65;
    stepPhysics(0.016, now);
  }
  updateAllProjections();
  ripples.push({ x: ideaNode.x, y: ideaNode.y, z: ideaNode.z, color: ideaColor, born: now, duration: 1.45 });
  wakeSim(0.65);
  return ideaNode;
}

function computeOverlapsCount() {
  let count = 0;
  for (let i = 0; i < placedLabelBoxes.length; i++) {
    const a = placedLabelBoxes[i];
    for (let j = i + 1; j < placedLabelBoxes.length; j++) {
      const b = placedLabelBoxes[j];
      if (a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1) {
        count += 1;
      }
    }
  }
  return count;
}

function checkFitsInWindow() {
  if (!nodes.length) return true;
  const padX = 24, padY = 24;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.behind) return false;
    if (n.sx - n.sr < padX || n.sx + n.sr > viewW - padX) return false;
    if (n.sy - n.sr < padY || n.sy + n.sr > viewH - padY) return false;
  }
  return true;
}

function computeNearestMinScreenDist() {
  if (nodes.length < 2) return 0;
  let minD = Infinity;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      const d = Math.hypot(a.sx - b.sx, a.sy - b.sy);
      if (d < minD) minD = d;
    }
  }
  return minD === Infinity ? 0 : Math.round(minD * 10) / 10;
}

function buildConstellationStats() {
  const consts = (typeof DATA !== 'undefined' && Array.isArray(DATA.constellations)) ? DATA.constellations : [];
  return consts.map(c => {
    const cid = 'item:' + c.id;
    let linkedIdeas = 0;
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      const otherId = l.a === cid ? l.b : (l.b === cid ? l.a : null);
      if (otherId) {
        const on = nodeMap.get(otherId);
        if (on && on.kind === 'idea') linkedIdeas += 1;
      }
    }
    return {
      id: c.id,
      title: c.title,
      members: Array.isArray(c.includes) ? c.includes.length : 0,
      ideas: linkedIdeas,
      status: c.status
    };
  });
}
