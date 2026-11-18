function hitTestNode(x, y) {
  const sorted = nodes.slice().sort(function (a, b) {
    return a.depth - b.depth;
  });
  for (let i = 0; i < sorted.length; i++) {
    const n = sorted[i];
    if (n.depth < 80) continue;
    const dx = x - n.sx;
    const dy = y - n.sy;
    const hitR = n.sr + 5;
    if (dx * dx + dy * dy <= hitR * hitR) {
      return n;
    }
  }
  return null;
}

function pointToSegmentInfo(px, py, x1, y1, x2, y2) {
  const vx = x2 - x1;
  const vy = y2 - y1;
  const len2 = vx * vx + vy * vy;
  if (len2 < 1e-4) {
    return { dist: Math.hypot(px - x1, py - y1), u: 0.5 };
  }
  let u = ((px - x1) * vx + (py - y1) * vy) / len2;
  const clampedU = Math.max(0, Math.min(1, u));
  const cx = x1 + clampedU * vx;
  const cy = y1 + clampedU * vy;
  return {
    dist: Math.hypot(px - cx, py - cy),
    u: u
  };
}

function hitTestLinkMid(x, y) {
  let bestLink = null;
  let bestDist = 9.5;
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.cut) continue;
    const a = nodeMap.get(l.a);
    const b = nodeMap.get(l.b);
    if (!a || !b || a.depth < 80 || b.depth < 80) continue;
    const info = pointToSegmentInfo(x, y, a.sx, a.sy, b.sx, b.sy);
    if (info.u >= 0.14 && info.u <= 0.86 && info.dist < bestDist) {
      bestDist = info.dist;
      bestLink = l;
    }
  }
  return bestLink;
}

function segmentsIntersect(x1, y1, x2, y2, x3, y3, x4, y4) {
  function ccw(ax, ay, bx, by, cx, cy) {
    return (cy - ay) * (bx - ax) > (by - ay) * (cx - ax);
  }
  return (
    ccw(x1, y1, x3, y3, x4, y4) !== ccw(x2, y2, x3, y3, x4, y4) &&
    ccw(x1, y1, x2, y2, x3, y3) !== ccw(x1, y1, x2, y2, x4, y4)
  );
}

function findCrossedLinks(x1, y1, x2, y2) {
  const crossed = [];
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.cut) continue;
    const a = nodeMap.get(l.a);
    const b = nodeMap.get(l.b);
    if (!a || !b || a.depth < 80 || b.depth < 80) continue;
    if (segmentsIntersect(x1, y1, x2, y2, a.sx, a.sy, b.sx, b.sy)) {
      crossed.push(l);
    }
  }
  return crossed;
}

function panCameraInScreenPlane(dx, dy, dtSec) {
  cam.focusGoal = null;
  cam.resetAnim = null;
  const s = F_PERSP / Math.max(80, cam.D);
  const wxp = -dx / s;
  const wyp = -dy / s;

  const cosP = Math.cos(cam.pitch);
  const sinP = Math.sin(cam.pitch);
  const x1 = wxp;
  const y1 = wyp * cosP;
  const z1 = -wyp * sinP;

  const cosY = Math.cos(cam.yaw);
  const sinY = Math.sin(cam.yaw);
  const dtx = x1 * cosY - z1 * sinY;
  const dty = y1;
  const dtz = x1 * sinY + z1 * cosY;

  cam.tx += dtx;
  cam.ty += dty;
  cam.tz += dtz;

  const invDt = 1 / Math.max(0.008, Math.min(0.05, dtSec));
  cam.vtx = dtx * invDt * 0.45;
  cam.vty = dty * invDt * 0.45;
  cam.vtz = dtz * invDt * 0.45;
}

function undoLastCutBatch() {
  if (cutHistory.length === 0) return;
  const batch = cutHistory.pop();
  for (let i = 0; i < batch.length; i++) {
    batch[i].cut = false;
  }
  simAlpha = Math.max(simAlpha, 0.38);
  if (focusedId) recomputeFocusHops();
}
