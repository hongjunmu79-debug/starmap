function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 < 1) return { dist: Math.hypot(px - x1, py - y1), t: 0.5 };
  let t = ((px - x1) * dx + (py - y1) * dy) / len2;
  t = Math.max(0, Math.min(1, t));
  const cx = x1 + t * dx;
  const cy = y1 + t * dy;
  return { dist: Math.hypot(px - cx, py - cy), t: t };
}

function segmentsIntersect(ax, ay, bx, by, cx, cy, dx, dy) {
  function ccw(p1x, p1y, p2x, p2y, p3x, p3y) {
    return (p3y - p1y) * (p2x - p1x) > (p2y - p1y) * (p3x - p1x);
  }
  return (
    ccw(ax, ay, cx, cy, dx, dy) !== ccw(bx, by, cx, cy, dx, dy) &&
    ccw(ax, ay, bx, by, cx, cy) !== ccw(ax, ay, bx, by, dx, dy)
  );
}

function pickNodeAt(x, y) {
  const ordered = nodes.slice().sort((a, b) => a.depth - b.depth);
  for (let i = 0; i < ordered.length; i++) {
    const n = ordered[i];
    if (n.behind) continue;
    if (Math.hypot(x - n.sx, y - n.sy) <= n.sr + 4) {
      return n;
    }
  }
  return null;
}

function pickLinkAt(x, y) {
  let best = null;
  let bestDist = 13;
  for (let i = 0; i < links.length; i++) {
    const lk = links[i];
    const na = nodeMap.get(lk.a);
    const nb = nodeMap.get(lk.b);
    if (!na || !nb || na.behind || nb.behind) continue;
    if (Math.hypot(x - na.sx, y - na.sy) <= na.sr + 3) continue;
    if (Math.hypot(x - nb.sx, y - nb.sy) <= nb.sr + 3) continue;
    const res = distToSegment(x, y, na.sx, na.sy, nb.sx, nb.sy);
    if (res.t >= 0.06 && res.t <= 0.94 && res.dist < bestDist) {
      bestDist = res.dist;
      best = lk;
    }
  }
  return best;
}

function findLinksCrossed(x1, y1, x2, y2) {
  const crossed = [];
  for (let i = 0; i < links.length; i++) {
    const lk = links[i];
    const na = nodeMap.get(lk.a);
    const nb = nodeMap.get(lk.b);
    if (!na || !nb || (na.behind && nb.behind)) continue;
    if (segmentsIntersect(x1, y1, x2, y2, na.sx, na.sy, nb.sx, nb.sy)) {
      crossed.push(lk);
    }
  }
  return crossed;
}

const pointerState = {
  down: false, mode: 'none',
  downX: 0, downY: 0, prevX: 0, prevY: 0,
  downTime: 0, prevTime: 0, movedDist: 0,
  downYaw: 0, downPitch: 0,
  dragNode: null, activeBand: null, cutBatch: null
};

function setupInputHandlers() {
  canvas.addEventListener('pointerdown', function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    if (typeof ensureAudio === 'function') ensureAudio();
    updateAllProjections();

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    const now = performance.now();

    pointerState.down = true;
    pointerState.downX = pointerState.prevX = x;
    pointerState.downY = pointerState.prevY = y;
    pointerState.downTime = pointerState.prevTime = now;
    pointerState.movedDist = 0;
    pointerState.downYaw = cam.yaw;
    pointerState.downPitch = cam.pitch;
    pointerState.dragNode = pointerState.activeBand = pointerState.cutBatch = null;

    try { canvas.setPointerCapture(e.pointerId); } catch (_) {}

    const hitNode = pickNodeAt(x, y);
    if (hitNode) {
      pointerState.mode = 'node';
      pointerState.dragNode = hitNode;
      pointerState.wasPinned = !!hitNode.pinned;
      pointerState.carried = null;
      hitNode.fx = hitNode.x; hitNode.fy = hitNode.y; hitNode.fz = hitNode.z;
      return;
    }

    const hitLink = pickLinkAt(x, y);
    if (hitLink) {
      pointerState.mode = 'band';
      let rb = findRubberBandForLink(hitLink);
      if (!rb) {
        rb = { link: hitLink, dragging: true, pointerX: x, pointerY: y, ox: 0, oy: 0, vx: 0, vy: 0, tension: 0 };
        rubberBands.push(rb);
      } else {
        rb.dragging = true; rb.pointerX = x; rb.pointerY = y;
      }
      pointerState.activeBand = rb;
      return;
    }

    pointerState.mode = 'blank';
    canvas.classList.add('dragging-cam');
  });

  window.addEventListener('pointermove', function (e) {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const now = performance.now();

    if (!pointerState.down) {
      const hn = pickNodeAt(x, y);
      hoverNodeId = hn ? hn.id : null;
      hoverLink = hn ? null : pickLinkAt(x, y);
      canvas.classList.toggle('hover-node', !!hoverNodeId);
      canvas.classList.toggle('hover-link', !hoverNodeId && !!hoverLink);
      return;
    }

    const dx = x - pointerState.prevX;
    const dy = y - pointerState.prevY;
    const stepDist = Math.hypot(dx, dy);
    pointerState.movedDist += stepDist;

    if (pointerState.mode === 'node' && pointerState.dragNode) {
      const n = pointerState.dragNode;
      if (pointerState.movedDist > 3) {
        const wDelta = screenDeltaToWorld(dx, dy, n.depth);
        n.x += wDelta.x;
        n.y += wDelta.y;
        n.z += wDelta.z;
        n.fx = n.x;
        n.fy = n.y;
        n.fz = n.z;
        if (n.kind === 'center') {
          if (!pointerState.carried) pointerState.carried = collectCarryGroup(n);
          for (let ci = 0; ci < pointerState.carried.length; ci++) {
            const m = pointerState.carried[ci];
            m.x += wDelta.x; m.y += wDelta.y; m.z += wDelta.z;
            m.fx = m.x; m.fy = m.y; m.fz = m.z;
          }
        }
        if (focusId === n.id) {
          cam.targetTx = n.x * 0.34;
          cam.targetTy = n.y * 0.34;
          cam.targetTz = n.z * 0.34;
        }
        wakeSim(0.65);
        updateAllProjections();
      }
    } else if (pointerState.mode === 'band' && pointerState.activeBand) {
      const rb = pointerState.activeBand;
      rb.pointerX = x;
      rb.pointerY = y;
      stepRubberBands(0.016);
      if (stepDist > 0.5 && typeof creak === 'function') {
        creak(rb.tension, 1);
      }
    } else if (pointerState.mode === 'blank' || pointerState.mode === 'slash') {
      const dtSec = Math.max(0.004, (now - pointerState.prevTime) / 1000);
      const totalDtSec = Math.max(0.004, (now - pointerState.downTime) / 1000);
      const instSpeed = stepDist / dtSec;
      const avgSpeed = Math.hypot(x - pointerState.downX, y - pointerState.downY) / totalDtSec;
      const speed = Math.max(instSpeed, avgSpeed);

      if (pointerState.mode === 'blank' && (now - pointerState.downTime) <= 300 && speed >= 700) {
        const crossed = findLinksCrossed(pointerState.prevX, pointerState.prevY, x, y);
        const crossedFromDown = crossed.length ? crossed : findLinksCrossed(pointerState.downX, pointerState.downY, x, y);
        if (crossedFromDown.length > 0) {
          pointerState.mode = 'slash';
          cam.yaw = pointerState.downYaw;
          cam.pitch = pointerState.downPitch;
          updateAllProjections();
          canvas.classList.remove('dragging-cam');
          canvas.classList.add('slashing');
          pointerState.cutBatch = [];
          cutHistory.push(pointerState.cutBatch);
          if (typeof swishSound === 'function') swishSound();
          slashTrail.push({ x: pointerState.downX, y: pointerState.downY, t: now });
          for (let i = 0; i < crossedFromDown.length; i++) {
            const lk = crossedFromDown[i];
            const idx = links.indexOf(lk);
            if (idx !== -1) {
              links.splice(idx, 1);
              pointerState.cutBatch.push(lk);
              if (typeof sliceSound === 'function') sliceSound();
            }
          }
          if (focusId) rebuildFocusSet();
          wakeSim(0.6);
        }
      } else if (pointerState.mode === 'slash') {
        slashTrail.push({ x: x, y: y, t: now });
        const crossed = findLinksCrossed(pointerState.prevX, pointerState.prevY, x, y);
        for (let i = 0; i < crossed.length; i++) {
          const lk = crossed[i];
          const idx = links.indexOf(lk);
          if (idx !== -1) {
            links.splice(idx, 1);
            if (pointerState.cutBatch) pointerState.cutBatch.push(lk);
            if (typeof sliceSound === 'function') sliceSound();
          }
        }
        if (crossed.length > 0) {
          if (focusId) rebuildFocusSet();
          wakeSim(0.6);
        }
      }

      if (pointerState.mode === 'blank') {
        cam.yaw -= dx * 0.0055;
        cam.pitch = Math.max(-1.22, Math.min(1.22, cam.pitch + dy * 0.0055));
        updateAllProjections();
      }
    }

      pointerState.prevX = x; pointerState.prevY = y; pointerState.prevTime = now;
  });

  window.addEventListener('pointerup', function () {
    if (!pointerState.down) return;
    const now = performance.now();

    if (pointerState.mode === 'node' && pointerState.dragNode) {
      const n = pointerState.dragNode;
      if (pointerState.movedDist > 5) {
        n.pinned = true;   // a ball that was dragged stays where it was dropped (like the 2D page); drag it again to move it
        n.fx = n.x; n.fy = n.y; n.fz = n.z;
      } else if (!pointerState.wasPinned) {
        n.fx = n.fy = n.fz = null;
      }
      if (pointerState.carried) {
        for (let ci = 0; ci < pointerState.carried.length; ci++) {
          const m = pointerState.carried[ci];
          if (!m.pinned) { m.fx = null; m.fy = null; m.fz = null; }
        }
        pointerState.carried = null;
        simAlpha = Math.min(simAlpha, 0.15);   // keep the formation: only a light settle after the drop (overlaps are still pushed apart)
      }
      if (pointerState.movedDist <= 5) {
        ripples.push({ x: n.x, y: n.y, z: n.z, color: n.color, born: now, duration: 1.45 });
        if (n.kind === 'poss') keepPossibilityNode(n);
        setFocusNode(n.id);
      }
    } else if (pointerState.mode === 'band' && pointerState.activeBand) {
      const rb = pointerState.activeBand;
      rb.dragging = false;
      const t = rb.tension, launch = t >= 0.7;
      if (typeof twang === 'function') twang(t, launch);
      if (launch) spawnSparkBetween(rb.link, rb.ox, rb.oy);
    } else if (pointerState.mode === 'blank' && pointerState.movedDist <= 5) {
      if (focusId) setFocusNode(null);
      const wp = cameraToWorld(
        (pointerState.downX - viewW * 0.5) * (cam.dist / cam.fov),
        (pointerState.downY - viewH * 0.5) * (cam.dist / cam.fov),
        0
      );
      ripples.push({ x: wp.x, y: wp.y, z: wp.z, color: '#94a3b8', born: now, duration: 1.45 });
    }

    pointerState.down = false;
    pointerState.mode = 'none';
    pointerState.dragNode = pointerState.activeBand = pointerState.cutBatch = null;
    canvas.classList.remove('dragging-cam', 'slashing');
  });

  canvas.addEventListener('wheel', function (e) {
    e.preventDefault();
    cam.dist = Math.max(450, Math.min(2200, cam.dist + e.deltaY * 0.7));
    updateAllProjections();
  }, { passive: false });

  window.addEventListener('keydown', function (e) {
    if (typeof ensureAudio === 'function') ensureAudio();
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
      if (cutHistory.length > 0) {
        e.preventDefault();
        const batch = cutHistory.pop();
        for (let i = 0; i < batch.length; i++) {
          addLink(batch[i]);
        }
        if (focusId) rebuildFocusSet();
        wakeSim(0.6);
        updateAllProjections();
      }
    }
  });
}
