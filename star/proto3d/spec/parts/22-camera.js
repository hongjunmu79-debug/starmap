function prewarmPhysics(ticks) {
  simAlpha = 1.0;
  const count = ticks || 300;
  for (let i = 0; i < count; i++) {
    stepPhysicsTick();
  }
  simAlpha = 0;
  for (let i = 0; i < nodes.length; i++) {
    nodes[i].vx = 0;
    nodes[i].vy = 0;
    nodes[i].vz = 0;
  }
}

function stepSpring1D(val, vel, target, omega, zeta, dt) {
  const step = Math.min(dt, 0.033);
  // Claude fix to the written spec: with omega 180 and damping 0.85 the explicit integrator diverges once a sub-step is longer than ~6.5 ms,
  // so a frame longer than ~26 ms threw the dragged ball to infinity. Use fixed ~4 ms sub-steps like the 2D version (240 Hz).
  const sub = Math.max(1, Math.ceil(step / (1 / 240)));
  const h = step / sub;
  let x = val;
  let v = vel;
  for (let i = 0; i < sub; i++) {
    const acc = -omega * omega * (x - target) - 2 * zeta * omega * v;
    v += acc * h;
    x += v * h;
  }
  return { x: x, v: v };
}

function projectWorldToScreen(wx, wy, wz) {
  const rx = wx - cam.tx;
  const ry = wy - cam.ty;
  const rz = wz - cam.tz;

  const cosY = Math.cos(cam.yaw);
  const sinY = Math.sin(cam.yaw);
  const x1 = rx * cosY + rz * sinY;
  const y1 = ry;
  const z1 = -rx * sinY + rz * cosY;

  const cosP = Math.cos(cam.pitch);
  const sinP = Math.sin(cam.pitch);
  const xp = x1;
  const yp = y1 * cosP - z1 * sinP;
  const zp = y1 * sinP + z1 * cosP;

  const depth = cam.D + zp;
  const effDepth = Math.max(80, depth);
  const s = F_PERSP / effDepth;
  const sx = W * 0.5 + xp * s;
  const sy = H * 0.5 - 20 + yp * s;

  return {
    sx: sx,
    sy: sy,
    depth: depth,
    effDepth: effDepth,
    s: s,
    xp: xp,
    yp: yp,
    zp: zp
  };
}

function unprojectScreenToWorld(sx, sy, depth) {
  const effDepth = Math.max(80, depth);
  const s = F_PERSP / effDepth;
  const xp = (sx - W * 0.5) / s;
  const yp = (sy - (H * 0.5 - 20)) / s;
  const zp = depth - cam.D;

  const cosP = Math.cos(cam.pitch);
  const sinP = Math.sin(cam.pitch);
  const x1 = xp;
  const y1 = yp * cosP + zp * sinP;
  const z1 = -yp * sinP + zp * cosP;

  const cosY = Math.cos(cam.yaw);
  const sinY = Math.sin(cam.yaw);
  const rx = x1 * cosY - z1 * sinY;
  const ry = y1;
  const rz = x1 * sinY + z1 * cosY;

  return {
    x: rx + cam.tx,
    y: ry + cam.ty,
    z: rz + cam.tz
  };
}

function recomputeFocusHops() {
  focusHopMap.clear();
  if (!focusedId || !nodeMap.has(focusedId)) return;
  focusHopMap.set(focusedId, 0);
  const queue = [{ id: focusedId, hops: 0 }];
  while (queue.length > 0) {
    const cur = queue.shift();
    if (cur.hops >= 2) continue;
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      if (l.cut) continue;
      let nextId = null;
      if (l.a === cur.id) nextId = l.b;
      else if (l.b === cur.id) nextId = l.a;
      if (nextId && !focusHopMap.has(nextId)) {
        focusHopMap.set(nextId, cur.hops + 1);
        queue.push({ id: nextId, hops: cur.hops + 1 });
      }
    }
  }
}

function setFocusNode(nodeId) {
  if (!nodeId || !nodeMap.has(nodeId)) {
    focusedId = null;
    focusHopMap.clear();
    cam.focusGoal = null;
    return;
  }
  focusedId = nodeId;
  recomputeFocusHops();

  const centerNode = nodeMap.get(nodeId);
  let sumX = centerNode.x * 2;
  let sumY = centerNode.y * 2;
  let sumZ = centerNode.z * 2;
  let weight = 2;

  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.cut) continue;
    let nbId = null;
    if (l.a === nodeId) nbId = l.b;
    else if (l.b === nodeId) nbId = l.a;
    if (nbId && nodeMap.has(nbId)) {
      const nb = nodeMap.get(nbId);
      sumX += nb.x;
      sumY += nb.y;
      sumZ += nb.z;
      weight += 1;
    }
  }

  const gx = sumX / weight;
  const gy = sumY / weight;
  const gz = sumZ / weight;

  const desiredYaw = Math.atan2(-centerNode.x, -centerNode.z || 400);
  let dYaw = desiredYaw - cam.yaw;
  while (dYaw > Math.PI) dYaw -= Math.PI * 2;
  while (dYaw < -Math.PI) dYaw += Math.PI * 2;
  dYaw = Math.max(-0.25, Math.min(0.25, dYaw * 0.35));

  const desiredPitch = Math.atan2(centerNode.y, 600);
  let dPitch = Math.max(-0.25, Math.min(0.25, (desiredPitch - cam.pitch) * 0.35));

  cam.resetAnim = null;
  cam.focusGoal = {
    tx: gx,
    ty: gy,
    tz: gz,
    yaw: cam.yaw + dYaw,
    pitch: Math.max(-1.2, Math.min(1.2, cam.pitch + dPitch)),
    vYaw: 0,
    vPitch: 0
  };
}

function triggerCameraReset() {
  focusedId = null;
  focusHopMap.clear();
  cam.focusGoal = null;
  cam.vYaw = 0;
  cam.vPitch = 0;
  cam.targetD = D_INIT;
  cam.resetAnim = {
    elapsed: 0
  };
}

function spawnSparkBetweenNodes(spark) {
  const pos = unprojectScreenToWorld(spark.x, spark.y, spark.depth);
  sparkSeq += 1;
  const id = 'poss:spark-' + sparkSeq;
  const pairKey1 = spark.a + '|' + spark.b;
  const pairKey2 = spark.b + '|' + spark.a;
  let text = (DATA && DATA.sparkPlaceholder) || '两者之间的新可能';
  if (DATA && DATA.sparks) {
    if (DATA.sparks[pairKey1]) text = DATA.sparks[pairKey1];
    else if (DATA.sparks[pairKey2]) text = DATA.sparks[pairKey2];
  }
  const lens = (DATA && DATA.sparkLens) || '两者之间';
  const iconName = (DATA && DATA.lensIcons && DATA.lensIcons[lens]) || 'spark';
  const nodeA = nodeMap.get(spark.a);
  const col = (nodeA && nodeA.color) || ((DATA && DATA.unsortedColor) || '#E4EAF6');

  registerNode({
    id: id,
    kind: 'poss',
    parentId: spark.a,
    status: 'explore',
    label: text,
    lens: lens,
    icon: iconName,
    color: col,
    baseR: 11,
    iconSize: 12,
    x: pos.x,
    y: pos.y,
    z: pos.z
  });

  addLink(spark.a, id, 'poss', lens);
  addLink(spark.b, id, 'poss', lens);
  simAlpha = Math.max(simAlpha, 0.35);
  if (focusedId) recomputeFocusHops();
}

function updateProjections(dt) {
  const step = Math.min(dt || 0.016, 0.05);
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const p = projectWorldToScreen(n.x, n.y, n.z);
    n.rawSx = p.sx;
    n.rawSy = p.sy;
    n.depth = p.depth;
    n.s = p.s;

    const ratio = Math.max(0.55, Math.min(1.6, p.s / REF_S));
    n.sr = n.baseR * ratio;
    n.sIcon = n.iconSize * ratio;

    let targetShiftX = 0;
    let targetShiftY = 0;
    let targetHover = 0;
    if (n !== draggedNode && pointerPos.x > -1000) {
      const dx = pointerPos.x - n.rawSx;
      const dy = pointerPos.y - n.rawSy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const radius = n.sr + 48;
      if (dist < radius && dist > 0.01) {
        const factor = Math.pow(1 - dist / radius, 1.5);
        const shift = Math.min(7, factor * 7);
        targetShiftX = (dx / dist) * shift;
        targetShiftY = (dy / dist) * shift;
        targetHover = factor;
      }
    }
    const blend = Math.min(1, step * 14);
    n.hoverShiftX += (targetShiftX - n.hoverShiftX) * blend;
    n.hoverShiftY += (targetShiftY - n.hoverShiftY) * blend;
    n.hoverGlow += (targetHover - n.hoverGlow) * blend;

    n.sx = n.rawSx + n.hoverShiftX;
    n.sy = n.rawSy + n.hoverShiftY;

    const fog = n.depth <= cam.D ? 1.0 : Math.max(0.35, 1.0 - ((n.depth - cam.D) / 500) * 0.65);
    const targetFocusMul = !focusedId || focusHopMap.has(n.id) ? 1.0 : 0.16;
    n.focusMul += (targetFocusMul - n.focusMul) * Math.min(1, step * 10);
    n.fog = fog;
  }
}
