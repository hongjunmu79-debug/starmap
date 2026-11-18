function renderNodes(now) {
  const ordered = nodes.slice().sort((a, b) => b.depth - a.depth);
  const bgFog = { r: 8, g: 12, b: 20 };

  for (let i = 0; i < ordered.length; i++) {
    const n = ordered[i];
    if (n.behind) continue;

    const isHover = n.id === hoverNodeId;
    const isFocused = n.id === focusId;
    const hoverMult = isHover ? 1.18 : 1.0;
    const effBright = n.bright * hoverMult;
    const depthVis = Math.max(0.36, Math.min(1.0, 1.26 - n.depth / 1550));
    const fogT = Math.max(0, Math.min(0.42, (n.depth - 520) / 950));
    const rawRgb = brightenRgb(hexToRgb(n.color), effBright);
    const rgb = mixRgb(rawRgb, bgFog, fogT);
    const alpha = Math.max(0.08, Math.min(1.0, n.dimFactor * depthVis));

    let r = n.sr;
    if (n.bornAt > 0 && now - n.bornAt < 380) {
      const p = Math.max(0, (now - n.bornAt) / 380);
      const ease = 1 - Math.pow(1 - p, 3);
      r = n.sr * (0.35 + 0.65 * ease);
    }

    ctx.save();
    if (n.kind === 'poss') {
      ctx.fillStyle = 'rgba(10, 15, 26, ' + (0.76 * alpha).toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = rgbaStr(rgb, 0.85 * alpha);
      ctx.lineWidth = isHover ? 2.0 : 1.55;
      ctx.setLineDash([4, 3.5]);
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
    } else {
      if (n.kind === 'center' || isFocused) {
        const haloR = r * (isFocused ? 2.15 : 1.75);
        const halo = ctx.createRadialGradient(n.sx, n.sy, r * 0.5, n.sx, n.sy, haloR);
        halo.addColorStop(0, rgbaStr(rgb, (isFocused ? 0.30 : 0.18) * alpha));
        halo.addColorStop(1, rgbaStr(rgb, 0));
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(n.sx, n.sy, haloR, 0, Math.PI * 2);
        ctx.fill();
      }

      const hiRgb = brightenRgb(rgb, 1.38);
      const loRgb = brightenRgb(rgb, 0.42);
      const grad = ctx.createRadialGradient(
        n.sx - r * 0.32,
        n.sy - r * 0.34,
        r * 0.08,
        n.sx,
        n.sy,
        r
      );
      grad.addColorStop(0, rgbaStr(hiRgb, 0.96 * alpha));
      grad.addColorStop(0.54, rgbaStr(rgb, 0.91 * alpha));
      grad.addColorStop(1, rgbaStr(loRgb, 0.92 * alpha));

      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = rgbaStr(hiRgb, (n.kind === 'center' ? 0.76 : 0.56) * alpha);
      ctx.lineWidth = n.kind === 'center' ? 1.55 : 1.1;
      ctx.beginPath();
      ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    const iconPath = getIconPath(n.icon);
    if (iconPath) {
      const iconSize = Math.max(9.5, r * 1.1);
      const s = iconSize / 24;
      ctx.save();
      ctx.translate(n.sx - iconSize * 0.5, n.sy - iconSize * 0.5);
      ctx.scale(s, s);
      const iconAlpha = Math.min(1, alpha * (n.kind === 'poss' ? 0.85 : 0.96));
      ctx.strokeStyle = 'rgba(248, 250, 252, ' + iconAlpha.toFixed(3) + ')';
      ctx.lineWidth = 1.8;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke(iconPath);
      ctx.restore();
    }
    ctx.restore();
  }
}

function getLabelPriority(n) {
  let p = 100;
  if (n.kind === 'center') p = 300;
  else if (n.kind === 'idea') p = 200;
  else if (n.kind === 'member' || n.kind === 'kept') p = 100;
  else if (n.kind === 'poss') p = 85;

  if (focusId) {
    if (n.id === focusId) p += 1000;
    else if (focusSet.has(n.id)) p += 500;
  }
  if (n.id === hoverNodeId) p += 45;
  p -= n.depth * 0.01;
  return p;
}

function boxOverlapsAny(box, list, margin) {
  const m = margin || 0;
  for (let i = 0; i < list.length; i++) {
    const b = list[i];
    if (
      box.x1 < b.x2 + m &&
      box.x2 + m > b.x1 &&
      box.y1 < b.y2 + m &&
      box.y2 + m > b.y1
    ) {
      return true;
    }
  }
  return false;
}

function renderLabelsAndQuestions() {
  shownLabelIds = [];
  placedLabelBoxes = [];

  const candidates = [];
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (!n.label || n.behind) continue;
    if (n.sx < 24 || n.sx > viewW - 24 || n.sy < 18 || n.sy > viewH - 36) continue;
    candidates.push(n);
  }

  candidates.sort((a, b) => getLabelPriority(b) - getLabelPriority(a));

  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  for (let i = 0; i < candidates.length; i++) {
    const n = candidates[i];
    let fontSize = 11.5;
    let fontWeight = '400';
    if (n.kind === 'center') {
      fontSize = 13.5;
      fontWeight = '600';
    } else if (n.kind === 'idea') {
      fontSize = 12.5;
      fontWeight = '500';
    }
    ctx.font = fontWeight + ' ' + fontSize + 'px -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';

    const displayStr = (n.kind === 'poss' && n.lens) ? (n.lens + ' · ' + n.label) : n.label;
    const tw = ctx.measureText(displayStr).width;
    const lx = n.sx;
    const ly = n.sy + n.sr + 7 + fontSize * 0.5;
    const padX = 4;
    const padY = 2;
    const box = {
      id: n.id,
      x1: lx - tw * 0.5 - padX,
      y1: ly - fontSize * 0.5 - padY,
      x2: lx + tw * 0.5 + padX,
      y2: ly + fontSize * 0.5 + padY
    };

    if (box.x1 < 8 || box.x2 > viewW - 8 || box.y1 < 8 || box.y2 > viewH - 20) continue;
    if (boxOverlapsAny(box, placedLabelBoxes, 2)) continue;

    placedLabelBoxes.push(box);
    shownLabelIds.push(n.id);

    const depthVis = Math.max(0.42, Math.min(1.0, 1.25 - n.depth / 1600));
    const alpha = Math.max(0.12, Math.min(1.0, n.dimFactor * depthVis));

    ctx.strokeStyle = 'rgba(5, 8, 15, ' + (0.92 * alpha).toFixed(3) + ')';
    ctx.lineWidth = 3.2;
    ctx.lineJoin = 'round';
    ctx.strokeText(displayStr, lx, ly);

    if (n.kind === 'center') {
      ctx.fillStyle = 'rgba(248, 250, 252, ' + (0.97 * alpha).toFixed(3) + ')';
    } else if (n.kind === 'poss') {
      ctx.fillStyle = 'rgba(203, 213, 225, ' + (0.84 * alpha).toFixed(3) + ')';
    } else {
      ctx.fillStyle = 'rgba(226, 232, 240, ' + (0.92 * alpha).toFixed(3) + ')';
    }
    ctx.fillText(displayStr, lx, ly);
  }

  const auxBoxes = placedLabelBoxes.slice();
  ctx.font = '400 11px -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif';
  for (let i = 0; i < links.length; i++) {
    const lk = links[i];
    if (lk.kind !== 'suggest' || !lk.label) continue;
    const na = nodeMap.get(lk.a);
    const nb = nodeMap.get(lk.b);
    if (!na || !nb || na.behind || nb.behind) continue;
    const mx = (na.sx + nb.sx) * 0.5;
    const my = (na.sy + nb.sy) * 0.5 - 7;
    const tw = ctx.measureText(lk.label).width;
    const qBox = { x1: mx - tw * 0.5 - 3, y1: my - 7, x2: mx + tw * 0.5 + 3, y2: my + 7 };
    if (qBox.x1 < 8 || qBox.x2 > viewW - 8 || qBox.y1 < 8 || qBox.y2 > viewH - 20) continue;
    if (boxOverlapsAny(qBox, auxBoxes, 2)) continue;
    auxBoxes.push(qBox);

    const focusDim = (!focusId || focusLinks.has(lk)) ? 1.0 : 0.16;
    ctx.strokeStyle = 'rgba(5, 8, 15, ' + (0.9 * focusDim).toFixed(3) + ')';
    ctx.lineWidth = 3.0;
    ctx.strokeText(lk.label, mx, my);
    ctx.fillStyle = 'rgba(186, 200, 224, ' + (0.82 * focusDim).toFixed(3) + ')';
    ctx.fillText(lk.label, mx, my);
  }
  ctx.restore();
}

function renderScene(now) {
  updateAllProjections();
  renderBackground();
  renderLinks();
  renderRipplesAndEffects(now);
  renderNodes(now);
  renderLabelsAndQuestions();
}
