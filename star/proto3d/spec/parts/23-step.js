function addRipple(x, y, maxR, dur, startAlpha, color) {
  ripples.push({
    x: x,
    y: y,
    maxR: maxR || 300,
    dur: dur || 1.45,
    elapsed: 0,
    startAlpha: startAlpha !== undefined ? startAlpha : 0.22,
    color: color || '#DCE6FF'
  });
}

function stepCameraAndEffects(dt) {
  const step = Math.min(dt || 0.016, 0.05);

  if (anchorTimer > 0) {
    anchorTimer = Math.max(0, anchorTimer - step);
    simAlpha = Math.max(simAlpha, 0.35);
    if (anchorTimer <= 0) {
      anchorTargets = null;
    }
  }

  const spD = stepSpring1D(cam.D, cam.velD, cam.targetD, 16, 1.0, step);
  cam.D = spD.x;
  cam.velD = spD.v;

  if (cam.resetAnim) {
    cam.resetAnim.elapsed += step;
    const w = 10.5;
    const z = 0.92;
    const sx = stepSpring1D(cam.tx, cam.vtx, 0, w, z, step);
    const sy = stepSpring1D(cam.ty, cam.vty, 0, w, z, step);
    const sz = stepSpring1D(cam.tz, cam.vtz, 0, w, z, step);
    const syaw = stepSpring1D(cam.yaw, cam.vYaw, YAW_INIT, w, z, step);
    const spitch = stepSpring1D(cam.pitch, cam.vPitch, PITCH_INIT, w, z, step);
    cam.tx = sx.x; cam.vtx = sx.v;
    cam.ty = sy.x; cam.vty = sy.v;
    cam.tz = sz.x; cam.vtz = sz.v;
    cam.yaw = syaw.x; cam.vYaw = syaw.v;
    cam.pitch = Math.max(-1.2, Math.min(1.2, spitch.x));
    cam.vPitch = spitch.v;
    if (cam.resetAnim.elapsed > 0.75 &&
        Math.abs(cam.yaw - YAW_INIT) < 0.001 &&
        Math.abs(cam.pitch - PITCH_INIT) < 0.001 &&
        Math.abs(cam.tx) < 0.2 && Math.abs(cam.ty) < 0.2 && Math.abs(cam.tz) < 0.2) {
      cam.yaw = YAW_INIT;
      cam.pitch = PITCH_INIT;
      cam.tx = 0; cam.ty = 0; cam.tz = 0;
      cam.vtx = 0; cam.vty = 0; cam.vtz = 0;
      cam.vYaw = 0; cam.vPitch = 0;
      cam.resetAnim = null;
    }
  } else if (cam.focusGoal) {
    const fg = cam.focusGoal;
    const sx = stepSpring1D(cam.tx, cam.vtx, fg.tx, 4, 1.0, step);
    const sy = stepSpring1D(cam.ty, cam.vty, fg.ty, 4, 1.0, step);
    const sz = stepSpring1D(cam.tz, cam.vtz, fg.tz, 4, 1.0, step);
    const syaw = stepSpring1D(cam.yaw, fg.vYaw, fg.yaw, 4, 1.0, step);
    const spitch = stepSpring1D(cam.pitch, fg.vPitch, fg.pitch, 4, 1.0, step);
    cam.tx = sx.x; cam.vtx = sx.v;
    cam.ty = sy.x; cam.vty = sy.v;
    cam.tz = sz.x; cam.vtz = sz.v;
    cam.yaw = syaw.x; fg.vYaw = syaw.v;
    cam.pitch = Math.max(-1.2, Math.min(1.2, spitch.x));
    fg.vPitch = spitch.v;
  } else {
    if (Math.abs(cam.vYaw) > 0.00005 || Math.abs(cam.vPitch) > 0.00005) {
      cam.yaw += cam.vYaw * step;
      cam.pitch = Math.max(-1.2, Math.min(1.2, cam.pitch + cam.vPitch * step));
      const rotDecay = Math.exp(-4 * step);
      cam.vYaw *= rotDecay;
      cam.vPitch *= rotDecay;
    } else {
      cam.vYaw = 0;
      cam.vPitch = 0;
    }

    if (Math.abs(cam.vtx) > 0.01 || Math.abs(cam.vty) > 0.01 || Math.abs(cam.vtz) > 0.01) {
      cam.tx += cam.vtx * step;
      cam.ty += cam.vty * step;
      cam.tz += cam.vtz * step;
      const panDecay = Math.exp(-6 * step);
      cam.vtx *= panDecay;
      cam.vty *= panDecay;
      cam.vtz *= panDecay;
    } else {
      cam.vtx = 0;
      cam.vty = 0;
      cam.vtz = 0;
    }
  }

  if (draggedNode) {
    const worldGoal = unprojectScreenToWorld(pointerPos.x, pointerPos.y, draggedNode.depth);
    const sx = stepSpring1D(draggedNode.x, draggedNode.dragVx, worldGoal.x, 180, 0.85, step);
    const sy = stepSpring1D(draggedNode.y, draggedNode.dragVy, worldGoal.y, 180, 0.85, step);
    const sz = stepSpring1D(draggedNode.z, draggedNode.dragVz, worldGoal.z, 180, 0.85, step);
    draggedNode.x = sx.x; draggedNode.dragVx = sx.v;
    draggedNode.y = sy.x; draggedNode.dragVy = sy.v;
    draggedNode.z = sz.x; draggedNode.dragVz = sz.v;
    simAlpha = Math.max(simAlpha, 0.32);
  }

  if (elastic && elastic.link) {
    const na = nodeMap.get(elastic.link.a);
    const nb = nodeMap.get(elastic.link.b);
    if (!na || !nb || elastic.link.cut) {
      elastic = null;
    } else {
      const mx = (na.sx + nb.sx) * 0.5;
      const my = (na.sy + nb.sy) * 0.5;
      if (elastic.active) {
        const dx = pointerPos.x - mx;
        const dy = pointerPos.y - my;
        const d = Math.sqrt(dx * dx + dy * dy);
        const s = 125 * Math.tanh(d / 125);
        const t = s / 125;
        const tx = d > 0.001 ? mx + (dx / d) * s : mx;
        const ty = d > 0.001 ? my + (dy / d) * s : my;
        const spX = stepSpring1D(elastic.px, elastic.vx, tx, 26, 0.5, step);
        const spY = stepSpring1D(elastic.py, elastic.vy, ty, 26, 0.5, step);
        elastic.px = spX.x; elastic.vx = spX.v;
        elastic.py = spY.x; elastic.vy = spY.v;
        elastic.tension = t;
        if (d > 1) {
          elastic.dirX = dx / d;
          elastic.dirY = dy / d;
        }
      } else if (elastic.rebounding) {
        elastic.elapsed += step;
        const spX = stepSpring1D(elastic.px, elastic.vx, mx, 20, 0.2, step);
        const spY = stepSpring1D(elastic.py, elastic.vy, my, 20, 0.2, step);
        elastic.px = spX.x; elastic.vx = spX.v;
        elastic.py = spY.x; elastic.vy = spY.v;
        const dist = Math.hypot(elastic.px - mx, elastic.py - my);
        elastic.tension = Math.min(1, dist / 125);
        if (elastic.elapsed > 1.1 || (dist < 0.75 && Math.hypot(elastic.vx, elastic.vy) < 4)) {
          elastic = null;
        }
      }
    }
  }

  for (let i = sparks.length - 1; i >= 0; i--) {
    const sp = sparks[i];
    sp.elapsed += step;
    const u = Math.min(1, sp.elapsed / sp.dur);
    const ease = 1 - Math.pow(1 - u, 3);
    sp.x = sp.startX + (sp.tx - sp.startX) * ease;
    sp.y = sp.startY + (sp.ty - sp.startY) * ease;
    sp.trail.push({ x: sp.x, y: sp.y });
    if (sp.trail.length > 10) sp.trail.shift();
    if (u >= 1) {
      spawnSparkBetweenNodes(sp);
      sparks.splice(i, 1);
    }
  }

  for (let i = ripples.length - 1; i >= 0; i--) {
    ripples[i].elapsed += step;
    if (ripples[i].elapsed >= ripples[i].dur) {
      ripples.splice(i, 1);
    }
  }
}

function addNewIdeaFromInput(rawText) {
  const text = (rawText || '').trim();
  if (!text) return null;

  let bestNode = null;
  let bestScore = 0;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (!n.label) continue;
    let score = 0;
    for (let c = 0; c < text.length; c++) {
      const ch = text[c];
      if (ch.trim() && n.label.indexOf(ch) !== -1) {
        score += 1;
      }
    }
    if (score > bestScore) {
      bestScore = score;
      bestNode = n;
    }
  }

  typedSeq += 1;
  const ideaId = 'idea:typed-' + typedSeq;
  const unsortedCol = (DATA && DATA.unsortedColor) || '#E4EAF6';
  let x = (Math.random() - 0.5) * 120;
  let y = (Math.random() - 0.5) * 90;
  let z = -90;

  if (bestNode && bestScore > 0) {
    const ang = Math.random() * Math.PI * 2;
    x = bestNode.x + Math.cos(ang) * 95;
    y = bestNode.y + Math.sin(ang) * 95;
    z = bestNode.z + (Math.random() - 0.5) * 35;
  }

  const newIdea = registerNode({
    id: ideaId,
    kind: 'idea',
    status: 'explore',
    label: text,
    icon: 'bulb',
    color: unsortedCol,
    baseR: 12,
    iconSize: 12,
    x: x,
    y: y,
    z: z
  });

  if (bestNode && bestScore > 0) {
    addLink(ideaId, bestNode.id, 'suggest', '有关联吗？');
  }

  const placeholders = (DATA && DATA.placeholder) || [
    { lens: '可以变成', text: '做成一个小工具试试' },
    { lens: '反过来想', text: '如果不这样做会怎样' },
    { lens: '下一步', text: '写下第一个具体例子' }
  ];

  const count = Math.min(3, placeholders.length);
  for (let i = 0; i < count; i++) {
    const ph = placeholders[i];
    const possId = 'poss:typed-' + typedSeq + '-' + (i + 1);
    const ang = (i / Math.max(1, count)) * Math.PI * 2 + 0.35;
    const dist = 115;
    const lensIcon = (DATA && DATA.lensIcons && DATA.lensIcons[ph.lens]) || 'spark';
    registerNode({
      id: possId,
      kind: 'poss',
      parentId: ideaId,
      status: 'explore',
      label: ph.text,
      lens: ph.lens || '',
      icon: lensIcon,
      color: unsortedCol,
      baseR: 11,
      iconSize: 12,
      x: x + Math.cos(ang) * dist,
      y: y + Math.sin(ang) * dist,
      z: z + (i - 1) * 24
    });
    addLink(ideaId, possId, 'poss', ph.lens || '');
  }

  simAlpha = Math.max(simAlpha, 0.45);
  updateProjections(0.016);
  addRipple(newIdea.sx, newIdea.sy, 180, 1.1, 0.22, unsortedCol);
  if (focusedId) recomputeFocusHops();
  return newIdea;
}
