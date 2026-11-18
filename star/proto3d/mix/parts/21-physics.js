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
  const spanX = 420;
  const spanY = 320;
  const spanZ = 260;
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

  anchorActive = hasAnchor;
  // B's layout runs at a fixed 60 ticks per second whatever the frame rate
  simAcc += Math.min(dt, 0.1);
  let guard = 0;
  while (simAcc >= 1 / 60 && guard++ < 5) {
    layoutTick();
    simAcc -= 1 / 60;
  }
}

/* ---- B's layout physics (the four forces; with Claude's fixes to the written spec) ---- */
const LINK_PARAMS = {
  struct:    { L0: 150, k0: 0.55 },
  poss:      { L0: 160, k0: 0.45 },
  kept:      { L0: 160, k0: 0.45 },
  mine:      { L0: 340, k0: 0.30 },
  confirmed: { L0: 360, k0: 0.04 },
  suggest:   { L0: 360, k0: 0.03 }
};
let simAcc = 0;
let anchorActive = false;

function layoutTick() {
  const hasAnchor = anchorActive;
  if (!hasAnchor) {
    if (simAlpha < 0.004) { simAlpha = 0; return; }
    simAlpha += (0 - simAlpha) * 0.0228;
    if (simAlpha < 0.004) {
      simAlpha = 0;
      for (let i = 0; i < nodes.length; i++) { nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].vz = 0; }
      return;
    }
  }
  const alpha = hasAnchor ? Math.max(simAlpha, 0.65) : simAlpha;
  // the window is wider than tall: pull y in harder, as in the 2D layout
  const aspectY = Math.pow(Math.min(2, Math.max(1, viewW / Math.max(1, viewH))), 2.2);
  const Mrepel = 0.2 + 2.4 * forces.repel;
  const Mdist = 0.4 + 1.6 * forces.distance;
  const Mlink = 2.0 * forces.link;
  const Mcenter = 0.05 * forces.center;
  const N = nodes.length;

  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    if (a.fx !== null) continue;
    const cf = Mcenter * alpha * (a.kind === 'center' ? 3 : 1);
    a.vx += -a.x * cf;
    a.vy += -a.y * cf * aspectY;
    a.vz += -a.z * cf;
    if (a.kind === 'center' && a.zStatus !== undefined) a.vz += (a.zStatus - a.z) * 0.02;
    if (a.kind === 'member' && a.parentId) {
      const p = nodeMap.get(a.parentId);
      if (p) {
        a.vx += (p.x - a.x) * 0.008 * alpha;
        a.vy += (p.y - a.y) * 0.008 * alpha;
        a.vz += (p.z - a.z) * 0.008 * alpha;
      }
    }
    if (hasAnchor && a.anchorTarget) {
      a.vx += (a.anchorTarget.x - a.x) * 0.085;
      a.vy += (a.anchorTarget.y - a.y) * 0.085;
      a.vz += (a.anchorTarget.z - a.z) * 0.085;
    }
  }

  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    const freeA = a.fx === null;
    const chargeA = a.kind === 'center' ? -600 : -220;
    for (let j = i + 1; j < N; j++) {
      const b = nodes[j];
      const freeB = b.fx === null;
      if (!freeA && !freeB) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = b.z - a.z;
      let d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > 520 * 520) continue;
      if (d2 < 1) d2 = 1;
      const denom = Math.max(d2, 400);
      const chargeB = b.kind === 'center' ? -600 : -220;
      if (freeA) {
        const fa = (chargeB * Mrepel * alpha) / denom;
        a.vx += dx * fa; a.vy += dy * fa; a.vz += dz * fa;
      }
      if (freeB) {
        const fb = (chargeA * Mrepel * alpha) / denom;
        b.vx -= dx * fb; b.vy -= dy * fb; b.vz -= dz * fb;
      }
    }
  }

  for (let i = 0; i < links.length; i++) {
    const lk = links[i];
    const a = nodeMap.get(lk.a);
    const b = nodeMap.get(lk.b);
    if (!a || !b) continue;
    const lp = LINK_PARAMS[lk.kind] || LINK_PARAMS.struct;
    const L = lp.L0 * Mdist;
    const k = lp.k0 * Mlink;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dz = b.z - a.z;
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.001;
    const f = ((d - L) / d) * k * alpha * 0.5;
    if (a.fx === null) { a.vx += dx * f; a.vy += dy * f; a.vz += dz * f; }
    if (b.fx === null) { b.vx -= dx * f; b.vy -= dy * f; b.vz -= dz * f; }
  }

  for (let i = 0; i < N; i++) {
    const n = nodes[i];
    if (n.fx !== null) {
      n.x = n.fx; n.y = n.fy; n.z = n.fz;
      n.vx = 0; n.vy = 0; n.vz = 0;
      continue;
    }
    n.vx *= 0.42; n.vy *= 0.42; n.vz *= 0.42;
    n.x += n.vx; n.y += n.vy; n.z += n.vz;
  }

  // balls keep a gap: min distance = radii + 18 (B's numbers: centre 22 and the rest 11, times 1.4)
  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    const freeA = a.fx === null;
    const ra = (a.kind === 'center' ? 22 : 11) * 1.4;
    for (let j = i + 1; j < N; j++) {
      const b = nodes[j];
      const freeB = b.fx === null;
      if (!freeA && !freeB) continue;
      const rb = (b.kind === 'center' ? 22 : 11) * 1.4;
      const minDist = ra + rb + 18;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = b.z - a.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < minDist * minDist) {
        const d = Math.sqrt(d2) || 0.001;
        const push = ((minDist - d) / d) * 0.7 * (freeA && freeB ? 0.5 : 1.0);
        if (freeA) { a.x -= dx * push; a.y -= dy * push; a.z -= dz * push; }
        if (freeB) { b.x += dx * push; b.y += dy * push; b.z += dz * push; }
      }
    }
  }
}

function warmUpSimulation(ticks) {
  const n = ticks || 300;
  simAlpha = 1.0;
  anchorActive = false;
  for (let i = 0; i < n; i++) layoutTick();
  simAlpha = 0;
  for (let i = 0; i < nodes.length; i++) {
    nodes[i].vx = 0; nodes[i].vy = 0; nodes[i].vz = 0;
  }
  updateAllProjections();
}

// dragging a constellation centre carries everything that hangs below it (members and their possibilities) as a rigid group
function collectCarryGroup(center) {
  const out = [];
  const seen = new Set([center.id]);
  let frontier = [center.id];
  while (frontier.length) {
    const next = [];
    for (let i = 0; i < nodes.length; i++) {
      const m = nodes[i];
      if (seen.has(m.id) || !m.parentId || frontier.indexOf(m.parentId) < 0 || m.kind === 'center') continue;
      seen.add(m.id);
      out.push(m);
      next.push(m.id);
    }
    frontier = next;
  }
  return out;
}
