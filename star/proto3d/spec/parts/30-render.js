function boxesOverlap(a, b) {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

function getNodeLabelPriority(n) {
  if (focusedId && n.id === focusedId) return 4;
  if (n.kind === 'center') return 3;
  if (n.kind === 'idea') return 2;
  return 1;
}

function computeLabelLayout() {
  const ordered = nodes.slice().sort(function (a, b) {
    const pa = getNodeLabelPriority(a);
    const pb = getNodeLabelPriority(b);
    if (pa !== pb) return pb - pa;
    return a.depth - b.depth;
  });

  const placedBoxes = [];
  for (let i = 0; i < ordered.length; i++) {
    const n = ordered[i];
    n.labelShown = false;
    n.labelBox = null;
    if (!n.label || n.depth < 85) continue;

    const baseFont = n.kind === 'center' ? 18 : 13;
    const fSize = Math.max(11, Math.min(18, baseFont * Math.sqrt(n.s / REF_S)));
    const weight = n.kind === 'center' ? '600' : '400';
    ctx.font = weight + ' ' + fSize.toFixed(1) + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';
    const tw = ctx.measureText(n.label).width;
    const lx = n.sx;
    const ly = n.sy + n.sr + 6 + fSize * 0.52;
    const padX = 4;
    const padY = 2;
    const box = {
      x1: lx - tw * 0.5 - padX,
      y1: ly - fSize * 0.55 - padY,
      x2: lx + tw * 0.5 + padX,
      y2: ly + fSize * 0.55 + padY
    };

    if (box.x1 < 6 || box.x2 > W - 6 || box.y1 < 6 || box.y2 > H - 6) {
      continue;
    }

    let collided = false;
    for (let j = 0; j < placedBoxes.length; j++) {
      if (boxesOverlap(box, placedBoxes[j])) {
        collided = true;
        break;
      }
    }

    if (!collided) {
      n.labelShown = true;
      n.labelBox = box;
      n.labelX = lx;
      n.labelY = ly;
      n.labelFontSize = fSize;
      n.labelWeight = weight;
      placedBoxes.push(box);
    }
  }

  lastLabelOverlaps = countLabelOverlaps();
  return placedBoxes;
}

function countLabelOverlaps() {
  const shown = [];
  for (let i = 0; i < nodes.length; i++) {
    if (nodes[i].labelShown && nodes[i].labelBox) {
      shown.push(nodes[i].labelBox);
    }
  }
  let count = 0;
  for (let i = 0; i < shown.length; i++) {
    for (let j = i + 1; j < shown.length; j++) {
      if (boxesOverlap(shown[i], shown[j])) {
        count += 1;
      }
    }
  }
  return count;
}

function drawBackground(timeSec) {
  const cx = W * 0.5;
  const cy = H * 0.5;
  const maxR = Math.hypot(W, H) * 0.65;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  grad.addColorStop(0, '#0A0D18');
  grad.addColorStop(1, '#05060B');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);

  for (let i = 0; i < bgStars.length; i++) {
    const st = bgStars[i];
    const a = Math.max(0.04, Math.min(0.85, st.baseAlpha + Math.sin(timeSec * st.speed + st.phase) * st.amp));
    ctx.fillStyle = 'rgba(218, 228, 252, ' + a.toFixed(3) + ')';
    ctx.beginPath();
    ctx.arc(st.u * W, st.v * H, st.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawLinks(placedBoxes) {
  const activeLinks = [];
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (l.cut) continue;
    const a = nodeMap.get(l.a);
    const b = nodeMap.get(l.b);
    if (!a || !b) continue;
    activeLinks.push({
      link: l,
      a: a,
      b: b,
      midDepth: (a.depth + b.depth) * 0.5
    });
  }

  activeLinks.sort(function (x, y) {
    return y.midDepth - x.midDepth;
  });

  const warmRgb = { r: 255, g: 168, b: 96 };

  for (let i = 0; i < activeLinks.length; i++) {
    const item = activeLinks[i];
    const l = item.link;
    const a = item.a;
    const b = item.b;
    const lp = LINK_PARAMS[l.kind] || LINK_PARAMS.struct;
    const avgS = (a.s + b.s) * 0.5;
    const wScale = Math.max(0.5, Math.min(1.6, avgS / REF_S));
    const fog = (a.fog + b.fog) * 0.5;
    const focusMul = Math.min(a.focusMul, b.focusMul);
    const isHovered = hoveredLink === l;

    ctx.save();
    if (elastic && elastic.link === l) {
      const t = Math.max(0, Math.min(1, elastic.tension || 0));
      const baseRgb = lerpRgb(a.rgb, b.rgb, 0.5);
      const colRgb = lerpRgb(baseRgb, warmRgb, t * 0.88);
      const lw = 2.2 * (1 - t * 0.55) * wScale;
      ctx.lineWidth = Math.max(0.6, lw);
      ctx.strokeStyle = rgbaFromRgb(colRgb, Math.min(0.95, (0.58 + t * 0.38) * fog * focusMul), 1.15);
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(elastic.px, elastic.py);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();

      ctx.fillStyle = rgbaFromRgb(colRgb, 0.85 * fog, 1.25);
      ctx.beginPath();
      ctx.arc(elastic.px, elastic.py, 2.6, 0, Math.PI * 2);
      ctx.fill();
    } else {
      const baseAlpha = l.kind === 'struct' ? 0.34 : l.kind === 'confirmed' ? 0.42 : 0.32;
      const alpha = Math.min(0.92, (baseAlpha + (isHovered ? 0.25 : 0)) * fog * focusMul);
      const mixRgb = lerpRgb(a.rgb, b.rgb, 0.5);
      ctx.strokeStyle = rgbaFromRgb(mixRgb, alpha, 1.05);
      ctx.lineWidth = lp.width * wScale * (isHovered ? 1.25 : 1.0);
      if (l.kind === 'suggest' || l.kind === 'poss') {
        ctx.setLineDash([5 * wScale, 4.5 * wScale]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(a.sx, a.sy);
      ctx.lineTo(b.sx, b.sy);
      ctx.stroke();

      if (l.kind === 'suggest' && l.label && focusMul > 0.3) {
        const mx = (a.sx + b.sx) * 0.5;
        const my = (a.sy + b.sy) * 0.5 - 6;
        ctx.font = '400 11.5px -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif';
        const tw = ctx.measureText(l.label).width;
        const lBox = { x1: mx - tw * 0.5 - 3, y1: my - 8, x2: mx + tw * 0.5 + 3, y2: my + 8 };
        let overlap = false;
        if (placedBoxes) {
          for (let k = 0; k < placedBoxes.length; k++) {
            if (boxesOverlap(lBox, placedBoxes[k])) {
              overlap = true;
              break;
            }
          }
        }
        if (!overlap) {
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.lineJoin = 'round';
          ctx.lineWidth = 3.2;
          ctx.strokeStyle = 'rgba(5, 6, 11, ' + (0.88 * fog * focusMul).toFixed(3) + ')';
          ctx.strokeText(l.label, mx, my);
          ctx.fillStyle = 'rgba(205, 216, 240, ' + (0.72 * fog * focusMul).toFixed(3) + ')';
          ctx.fillText(l.label, mx, my);
          if (placedBoxes) placedBoxes.push(lBox);
        }
      }
    }
    ctx.restore();
  }
}
