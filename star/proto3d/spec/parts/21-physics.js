function buildGraphFromData() {
  const rand = mulberry32(7);
  nodes = [];
  nodeMap.clear();
  links = [];

  const constellations = (DATA && DATA.constellations) || [];
  const quadSigns = [[-1, -1], [1, -1], [-1, 1], [1, 1]];

  for (let ci = 0; ci < constellations.length; ci++) {
    const c = constellations[ci];
    const q = quadSigns[ci % 4];
    const zSt = STATUS_Z[c.status] !== undefined ? STATUS_Z[c.status] : 0;
    const cx = q[0] * (380 + rand() * 80);
    const cy = q[1] * (380 + rand() * 80);
    const cz = zSt;
    const cColor = getDomainColor(c.domain);
    const centerId = 'item:' + c.id;

    registerNode({
      id: centerId,
      kind: 'center',
      constellationId: c.id,
      domain: c.domain,
      status: c.status || 'explore',
      zStatus: zSt,
      label: c.title,
      icon: c.icon,
      color: cColor,
      baseR: 22,
      iconSize: 20,
      x: cx,
      y: cy,
      z: cz
    });

    const includes = c.includes || [];
    const incIcons = c.incIcons || [];
    const total = includes.length;
    const rotOffset = rand() * Math.PI * 2;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));

    for (let idx = 0; idx < total; idx++) {
      const yUnit = total > 1 ? 1 - (idx / (total - 1)) * 2 : 0;
      const radXY = Math.sqrt(Math.max(0, 1 - yUnit * yUnit));
      const theta = goldenAngle * idx + rotOffset + (rand() - 0.5) * 0.25;
      const shellR = 90 + rand() * 60;
      const mx = cx + Math.cos(theta) * radXY * shellR;
      const my = cy + Math.sin(theta) * radXY * shellR;
      const mz = cz + yUnit * shellR;
      const memId = 'inc:' + c.id + ':' + idx;

      registerNode({
        id: memId,
        kind: 'member',
        parentId: centerId,
        constellationId: c.id,
        domain: c.domain,
        status: c.status || 'explore',
        label: includes[idx],
        icon: incIcons[idx] || c.icon,
        color: cColor,
        baseR: 11,
        iconSize: 12,
        x: mx,
        y: my,
        z: mz
      });

      addLink(centerId, memId, 'struct', '');
    }
  }

  const ideas = (DATA && DATA.ideas) || [];
  const unsortedCol = (DATA && DATA.unsortedColor) || '#E4EAF6';
  for (let i = 0; i < ideas.length; i++) {
    const idea = ideas[i];
    const ix = (rand() - 0.5) * 110;
    const iy = (rand() - 0.5) * 110;
    const iz = -60 + rand() * 120;
    const ideaId = String(idea.id).startsWith('idea:') ? String(idea.id) : 'idea:' + idea.id;

    registerNode({
      id: ideaId,
      kind: 'idea',
      status: 'explore',
      label: idea.text,
      icon: idea.icon || 'bulb',
      color: unsortedCol,
      baseR: 12,
      iconSize: 12,
      x: ix,
      y: iy,
      z: iz
    });
  }

  if (DATA && DATA.expansions) {
    const expKeys = Object.keys(DATA.expansions);
    for (let k = 0; k < expKeys.length; k++) {
      const parentId = expKeys[k];
      const parentNode = nodeMap.get(parentId);
      if (!parentNode) continue;
      const list = DATA.expansions[parentId] || [];
      for (let j = 0; j < list.length; j++) {
        const exp = list[j];
        const possId = String(exp.id).startsWith('poss:') ? String(exp.id) : 'poss:' + exp.id;
        if (nodeMap.has(possId)) continue;
        const ang = (j / Math.max(1, list.length)) * Math.PI * 2 + rand() * 0.5;
        const dist = 110 + rand() * 40;
        const lensIcon = (DATA.lensIcons && DATA.lensIcons[exp.lens]) || 'spark';
        registerNode({
          id: possId,
          kind: 'poss',
          parentId: parentId,
          status: parentNode.status || 'explore',
          label: exp.text,
          lens: exp.lens || '',
          icon: lensIcon,
          color: parentNode.color,
          baseR: 11,
          iconSize: 12,
          x: parentNode.x + Math.cos(ang) * dist,
          y: parentNode.y + Math.sin(ang) * dist,
          z: parentNode.z + (rand() - 0.5) * 60
        });
        addLink(parentId, possId, 'poss', exp.lens || '');
      }
    }
  }

  const presetLinks = (DATA && DATA.links) || [];
  for (let i = 0; i < presetLinks.length; i++) {
    const l = presetLinks[i];
    addLink(l.a, l.b, l.kind || 'suggest', l.label || '');
  }
}

function isNodeFree(n) {
  return !n.pinned && n !== draggedNode;
}

function stepPhysicsTick() {
  if (simAlpha < 0.004) {
    simAlpha = 0;
    return;
  }
  simAlpha += (0 - simAlpha) * 0.0228;
  if (simAlpha < 0.004) {
    simAlpha = 0;
    for (let i = 0; i < nodes.length; i++) {
      nodes[i].vx = 0;
      nodes[i].vy = 0;
      nodes[i].vz = 0;
    }
    return;
  }

  const alpha = simAlpha;
  const ASPECT_Y = Math.pow(Math.min(2, Math.max(1, window.innerWidth / Math.max(1, window.innerHeight))), 2.2);
  const Mrepel = 0.2 + 2.4 * forces.repel;
  const Mdist = 0.4 + 1.6 * forces.distance;
  const Mlink = 2.0 * forces.link;
  const Mcenter = 0.05 * forces.center;
  const N = nodes.length;

  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    if (isNodeFree(a)) {
      const mul = a.kind === 'center' ? 3 : 1;
      const cf = Mcenter * alpha * mul;
      a.vx += -a.x * cf;
      // Claude fix to the written spec: the window is wider than tall, so pull y in harder (same idea as the 2D layout's aspect term);
      // without it the picture is taller than the window long before it uses the width.
      a.vy += -a.y * cf * ASPECT_Y;
      a.vz += -a.z * cf;

      if (a.kind === 'center' && a.zStatus !== undefined) {
        a.vz += (a.zStatus - a.z) * 0.02;
      }
      if (a.kind === 'member' && a.parentId) {
        const p = nodeMap.get(a.parentId);
        if (p) {
          a.vx += (p.x - a.x) * 0.008 * alpha;
          a.vy += (p.y - a.y) * 0.008 * alpha;
          a.vz += (p.z - a.z) * 0.008 * alpha;
        }
      }
      if (anchorTimer > 0 && anchorTargets && anchorTargets.has(a.id)) {
        const t = anchorTargets.get(a.id);
        a.vx += (t.x - a.x) * 0.085;
        a.vy += (t.y - a.y) * 0.085;
        a.vz += (t.z - a.z) * 0.085;
      }
    }
  }

  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    const freeA = isNodeFree(a);
    const chargeA = a.kind === 'center' ? -600 : -220;   // Claude fix: same charges as the 2D layout
    for (let j = i + 1; j < N; j++) {
      const b = nodes[j];
      const freeB = isNodeFree(b);
      if (!freeA && !freeB) continue;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let dz = b.z - a.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      const d = Math.sqrt(d2) || 0.001;
      if (d2 > 520 * 520) continue;   // Claude fix: the 2D layout cuts the push off at 520 units; without it every node pushes every other one
      const denom = Math.max(d2, 400);
      const ux = dx / d;
      const uy = dy / d;
      const uz = dz / d;

      const chargeB = b.kind === 'center' ? -600 : -220;
      // Claude fix to the written spec: the 2D layout multiplies the raw offset (dx), so the push falls off as 1/d, not 1/d^2.
      // The spec said 1/d^2 with a unit vector, which is ~100x weaker at these distances and made the repel slider do nothing.
      if (freeA) {
        const fa = (chargeB * Mrepel * alpha) / denom;
        a.vx += dx * fa;
        a.vy += dy * fa;
        a.vz += dz * fa;
      }
      if (freeB) {
        const fb = (chargeA * Mrepel * alpha) / denom;
        b.vx -= dx * fb;
        b.vy -= dy * fb;
        b.vz -= dz * fb;
      }
    }
  }

  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.cut) continue;
    const a = nodeMap.get(l.a);
    const b = nodeMap.get(l.b);
    if (!a || !b) continue;
    const lp = LINK_PARAMS[l.kind] || LINK_PARAMS.struct;
    const L = lp.L0 * Mdist;
    const k = lp.k0 * Mlink;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dz = b.z - a.z;
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.001;
    const f = ((d - L) / d) * k * alpha * 0.5;
    if (isNodeFree(a)) {
      a.vx += dx * f;
      a.vy += dy * f;
      a.vz += dz * f;
    }
    if (isNodeFree(b)) {
      b.vx -= dx * f;
      b.vy -= dy * f;
      b.vz -= dz * f;
    }
  }

  for (let i = 0; i < N; i++) {
    const n = nodes[i];
    if (!isNodeFree(n)) continue;
    n.vx *= 0.42;
    n.vy *= 0.42;
    n.vz *= 0.42;
    n.x += n.vx;
    n.y += n.vy;
    n.z += n.vz;
  }

  for (let i = 0; i < N; i++) {
    const a = nodes[i];
    const freeA = isNodeFree(a);
    const ra = (a.kind === 'center' ? 22 : 11) * 1.4;
    for (let j = i + 1; j < N; j++) {
      const b = nodes[j];
      const freeB = isNodeFree(b);
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
        if (freeA) {
          a.x -= dx * push;
          a.y -= dy * push;
          a.z -= dz * push;
        }
        if (freeB) {
          b.x += dx * push;
          b.y += dy * push;
          b.z += dz * push;
        }
      }
    }
  }
}
