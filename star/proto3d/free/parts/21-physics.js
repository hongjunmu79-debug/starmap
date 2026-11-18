function project3D(wx, wy, wz) {
  const dx = wx - cam.tx;
  const dy = wy - cam.ty;
  const dz = wz - cam.tz;
  const cosY = Math.cos(cam.yaw);
  const sinY = Math.sin(cam.yaw);
  const x1 = dx * cosY + dz * sinY;
  const z1 = -dx * sinY + dz * cosY;
  const cosP = Math.cos(cam.pitch);
  const sinP = Math.sin(cam.pitch);
  const y2 = dy * cosP - z1 * sinP;
  const z2 = dy * sinP + z1 * cosP;
  const depth = z2 + cam.dist;
  const safeDepth = Math.max(80, depth);
  const scale = cam.fov / safeDepth;
  return {
    x: viewW * 0.5 + x1 * scale,
    y: viewH * 0.5 + y2 * scale,
    depth: depth,
    scale: scale,
    vx: x1,
    vy: y2,
    vz: z2,
    behind: depth < 90
  };
}

function cameraToWorld(vx, vy, vz) {
  const cosP = Math.cos(cam.pitch);
  const sinP = Math.sin(cam.pitch);
  const dy = vy * cosP + vz * sinP;
  const z1 = -vy * sinP + vz * cosP;
  const cosY = Math.cos(cam.yaw);
  const sinY = Math.sin(cam.yaw);
  const dx = vx * cosY - z1 * sinY;
  const dz = vx * sinY + z1 * cosY;
  return {
    x: cam.tx + dx,
    y: cam.ty + dy,
    z: cam.tz + dz
  };
}

function screenDeltaToWorld(dsx, dsy, depth) {
  const scale = cam.fov / Math.max(80, depth || cam.dist);
  const vx = dsx / scale;
  const vy = dsy / scale;
  const w0 = cameraToWorld(0, 0, 0);
  const w1 = cameraToWorld(vx, vy, 0);
  return { x: w1.x - w0.x, y: w1.y - w0.y, z: w1.z - w0.z };
}

function updateAllProjections() {
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const p = project3D(n.x, n.y, n.z);
    n.sx = p.x;
    n.sy = p.y;
    n.depth = p.depth;
    n.scale = p.scale;
    n.behind = p.behind;
    n.sr = Math.max(5, n.r * p.scale);
  }
}

function rebuildFocusSet() {
  focusSet.clear();
  focusLinks.clear();
  if (!focusId || !nodeMap.has(focusId)) {
    focusId = null;
    cam.targetTx = 0;
    cam.targetTy = 0;
    cam.targetTz = 0;
    return;
  }
  const hop0 = focusId;
  focusSet.add(hop0);
  const hop1 = new Set();
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.a === hop0) { hop1.add(l.b); focusSet.add(l.b); focusLinks.add(l); }
    else if (l.b === hop0) { hop1.add(l.a); focusSet.add(l.a); focusLinks.add(l); }
  }
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (hop1.has(l.a)) { focusSet.add(l.b); focusLinks.add(l); }
    else if (hop1.has(l.b)) { focusSet.add(l.a); focusLinks.add(l); }
  }
  const fn = nodeMap.get(focusId);
  if (fn) {
    cam.targetTx = fn.x * 0.34;
    cam.targetTy = fn.y * 0.34;
    cam.targetTz = fn.z * 0.34;
  }
}

function setFocusNode(id) {
  focusId = (id && nodeMap.has(id)) ? id : null;
  rebuildFocusSet();
}

function wakeSim(a) {
  if (a === undefined) a = 0.75;
  if (a > simAlpha) simAlpha = a;
}

function applyAnchors(list) {
  if (!Array.isArray(list)) return;
  const spanX = Math.min(viewW, 1100) * 0.33;
  const spanY = Math.min(viewH, 800) * 0.31;
  const spanZ = 190;
  for (let i = 0; i < list.length; i++) {
    const item = list[i];
    if (!item || !item.id) continue;
    const id = nodeMap.has(item.id) ? item.id : ('item:' + item.id);
    const n = nodeMap.get(id);
    if (!n) continue;
    const nx = Math.max(-1, Math.min(1, Number(item.x) || 0));
    const ny = Math.max(-1, Math.min(1, Number(item.y) || 0));
    const nz = Math.max(-1, Math.min(1, Number(item.z) || 0));
    n.anchorTarget = cameraToWorld(nx * spanX, ny * spanY, nz * spanZ);
  }
  anchorEndTime = performance.now() + 3000;
  wakeSim(1.0);
}

function stepPhysics(dt, now) {
  const chx = cam.targetTx - cam.tx;
  const chy = cam.targetTy - cam.ty;
  const chz = cam.targetTz - cam.tz;
  if (Math.abs(chx) + Math.abs(chy) + Math.abs(chz) + Math.abs(cam.vx) + Math.abs(cam.vy) + Math.abs(cam.vz) > 0.02) {
    const w = 3.8, z = 0.88;
    cam.vx += (-2 * w * z * cam.vx + w * w * chx) * dt;
    cam.vy += (-2 * w * z * cam.vy + w * w * chy) * dt;
    cam.vz += (-2 * w * z * cam.vz + w * w * chz) * dt;
    cam.tx += cam.vx * dt;
    cam.ty += cam.vy * dt;
    cam.tz += cam.vz * dt;
  } else {
    cam.tx = cam.targetTx; cam.ty = cam.targetTy; cam.tz = cam.targetTz;
    cam.vx = 0; cam.vy = 0; cam.vz = 0;
  }

  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const targetDim = (!focusId || focusSet.has(n.id)) ? 1.0 : 0.16;
    n.dimFactor += (targetDim - n.dimFactor) * Math.min(1, dt * 10);
  }

  const hasAnchor = now < anchorEndTime;
  if (!hasAnchor && anchorEndTime > 0) {
    anchorEndTime = 0;
    for (let i = 0; i < nodes.length; i++) nodes[i].anchorTarget = null;
    wakeSim(0.6);
  }

  if (simAlpha <= 0.002 && !hasAnchor) {
    simAlpha = 0;
    return;
  }

  const step = Math.min(dt, 0.033) * 60;
  const activeAlpha = hasAnchor ? Math.max(simAlpha, 0.65) : simAlpha;
  const kCenterBase = 0.0035 + forces.center * 0.024;
  const kRepel = 220 + forces.repel * 1850;
  const kLinkBase = 0.022 + forces.link * 0.13;
  const distScale = 0.52 + forces.distance * 1.25;

  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    if (a.fx !== null) continue;
    const cm = a.kind === 'center' ? 1.45 : (a.kind === 'idea' ? 1.15 : 0.48);
    a.vx -= a.x * kCenterBase * cm * activeAlpha * step;
    a.vy -= a.y * kCenterBase * cm * activeAlpha * step;
    a.vz -= a.z * (kCenterBase * cm + 0.004) * activeAlpha * step;

    if (hasAnchor && a.anchorTarget) {
      a.vx += (a.anchorTarget.x - a.x) * 0.085 * step;
      a.vy += (a.anchorTarget.y - a.y) * 0.085 * step;
      a.vz += (a.anchorTarget.z - a.z) * 0.085 * step;
    }
  }

  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let dz = b.z - a.z;
      let d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < 1) {
        dx = (i % 2 === 0 ? 1 : -1) * 0.5;
        dy = (j % 2 === 0 ? 1 : -1) * 0.5;
        dz = 0.5;
        d2 = 1;
      }
      const d = Math.sqrt(d2);
      let pairMult = 1.0;
      if (a.kind === 'center' && b.kind === 'center') pairMult = 2.6;
      else if (a.constellationId && a.constellationId === b.constellationId) pairMult = 0.68;
      const f = Math.min(14, (kRepel * pairMult) / (d2 + 180)) * activeAlpha * step;
      const fx = (dx / d) * f;
      const fy = (dy / d) * f;
      const fz = (dz / d) * f;
      if (a.fx === null) { a.vx -= fx; a.vy -= fy; a.vz -= fz; }
      if (b.fx === null) { b.vx += fx; b.vy += fy; b.vz += fz; }
    }
  }

  for (let i = 0; i < links.length; i++) {
    const lk = links[i];
    const a = nodeMap.get(lk.a);
    const b = nodeMap.get(lk.b);
    if (!a || !b) continue;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dz = b.z - a.z;
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
    let rest = 82 * distScale;
    let stiff = kLinkBase;
    if (lk.kind === 'confirmed' || lk.kind === 'suggest') {
      rest = 185 * distScale;
      stiff = kLinkBase * 0.55;
    } else if (lk.kind === 'poss' || lk.kind === 'kept') {
      rest = 68 * distScale;
      stiff = kLinkBase * 1.1;
    } else {
      stiff = kLinkBase * 1.25;
    }
    const diff = (d - rest) * stiff * activeAlpha * step;
    const fx = (dx / d) * diff;
    const fy = (dy / d) * diff;
    const fz = (dz / d) * diff;
    if (a.fx === null) { a.vx += fx * 0.5; a.vy += fy * 0.5; a.vz += fz * 0.5; }
    if (b.fx === null) { b.vx -= fx * 0.5; b.vy -= fy * 0.5; b.vz -= fz * 0.5; }
  }

  const damp = Math.pow(0.76, step);
  const maxBound = 310;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.fx !== null) {
      n.x = n.fx; n.y = n.fy; n.z = n.fz;
      n.vx = 0; n.vy = 0; n.vz = 0;
      continue;
    }
    n.vx *= damp;
    n.vy *= damp;
    n.vz *= damp;
    n.x += n.vx * step;
    n.y += n.vy * step;
    n.z += n.vz * step;
    const rDist = Math.hypot(n.x, n.y, n.z);
    if (rDist > maxBound) {
      const s = maxBound / rDist;
      n.x *= s; n.y *= s; n.z *= s;
    }
  }

  if (!hasAnchor) {
    simAlpha *= Math.pow(0.16, dt);
    if (simAlpha <= 0.002) {
      simAlpha = 0;
      for (let i = 0; i < nodes.length; i++) {
        nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].vz = 0;
      }
    }
  }
}

function warmUpSimulation(ticks) {
  const n = ticks || 160;
  simAlpha = 1.0;
  for (let i = 0; i < n; i++) {
    stepPhysics(0.016, 0);
    simAlpha = Math.max(0.05, 1 - i / n);
  }
  simAlpha = 0;
  for (let i = 0; i < nodes.length; i++) {
    nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].vz = 0;
  }
  updateAllProjections();
}
