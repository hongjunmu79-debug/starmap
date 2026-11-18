function drawNodeBallAndIcon(n) {
  if (n.depth < 80) return;
  const visAlpha = Math.max(0.05, Math.min(1, n.fog * n.focusMul));
  const bright = (STATUS_BRIGHT[n.status] || 1.0) * (1 + n.hoverGlow * 0.22);
  const r = n.sr;
  const sx = n.sx;
  const sy = n.sy;

  ctx.save();

  const haloR = r + 14;
  const haloAlpha = 0.22 * visAlpha * (n.kind === 'poss' ? 0.65 : 1.0);
  const haloGrad = ctx.createRadialGradient(sx, sy, r * 0.35, sx, sy, haloR);
  haloGrad.addColorStop(0, rgbaFromRgb(n.rgb, haloAlpha, bright));
  haloGrad.addColorStop(1, rgbaFromRgb(n.rgb, 0, bright));
  ctx.fillStyle = haloGrad;
  ctx.beginPath();
  ctx.arc(sx, sy, haloR, 0, Math.PI * 2);
  ctx.fill();

  if (n.kind === 'poss') {
    ctx.fillStyle = 'rgba(10, 13, 24, ' + (0.72 * visAlpha).toFixed(3) + ')';
    ctx.beginPath();
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = rgbaFromRgb(n.rgb, 0.88 * visAlpha, bright);
    ctx.lineWidth = 1.6;
    ctx.setLineDash([4.2, 3.6]);
    ctx.beginPath();
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  } else {
    ctx.fillStyle = rgbaFromRgb(n.rgb, visAlpha, bright);
    ctx.beginPath();
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
    ctx.fill();
  }

  const iconPath = getIconPath(n.icon);
  if (iconPath && n.sIcon > 3) {
    const scale = n.sIcon / 24;
    ctx.save();
    ctx.translate(sx - 12 * scale, sy - 12 * scale);
    ctx.scale(scale, scale);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 1.8 / scale;
    if (n.kind === 'poss') {
      ctx.strokeStyle = rgbaFromRgb(n.rgb, 0.92 * visAlpha, bright);
    } else {
      ctx.strokeStyle = 'rgba(10, 12, 20, ' + (0.94 * visAlpha).toFixed(3) + ')';
    }
    ctx.stroke(iconPath);
    ctx.restore();
  }

  ctx.restore();
}

function drawNodeLabels() {
  const sorted = nodes.slice().sort(function (a, b) {
    return b.depth - a.depth;
  });

  ctx.save();
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  for (let i = 0; i < sorted.length; i++) {
    const n = sorted[i];
    if (!n.labelShown || !n.label) continue;

    const visAlpha = Math.max(0.08, Math.min(1, n.fog * n.focusMul));
    const bright = STATUS_BRIGHT[n.status] || 1.0;
    const fSize = n.labelFontSize || (n.kind === 'center' ? 18 : 13);
    const weight = n.labelWeight || (n.kind === 'center' ? '600' : '400');

    ctx.font = weight + ' ' + fSize.toFixed(1) + 'px -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.lineWidth = 3.6;
    ctx.strokeStyle = 'rgba(5, 6, 11, ' + (0.92 * visAlpha).toFixed(3) + ')';
    ctx.strokeText(n.label, n.labelX, n.labelY);

    if (n.kind === 'center') {
      const tint = lerpRgb({ r: 235, g: 241, b: 255 }, n.rgb, 0.28);
      ctx.fillStyle = rgbaFromRgb(tint, visAlpha, Math.min(1.15, bright));
    } else if (n.kind === 'poss') {
      ctx.fillStyle = rgbaFromRgb(n.rgb, 0.85 * visAlpha, bright);
    } else {
      ctx.fillStyle = 'rgba(222, 230, 248, ' + (0.92 * visAlpha * Math.min(1.08, bright)).toFixed(3) + ')';
    }
    ctx.fillText(n.label, n.labelX, n.labelY);
  }

  ctx.restore();
}

function drawEffects() {
  ctx.save();

  for (let i = 0; i < ripples.length; i++) {
    const rp = ripples[i];
    const u = Math.max(0, Math.min(1, rp.elapsed / rp.dur));
    const ease = 1 - Math.pow(1 - u, 2.2);
    const r = rp.maxR * ease;
    const alpha = rp.startAlpha * (1 - u);
    if (alpha <= 0.002) continue;
    const rgb = hexToRgb(rp.color);
    ctx.strokeStyle = rgbaFromRgb(rgb, alpha, 1.1);
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(rp.x, rp.y, r, 0, Math.PI * 2);
    ctx.stroke();
  }

  for (let i = 0; i < sparks.length; i++) {
    const sp = sparks[i];
    if (sp.trail && sp.trail.length > 1) {
      ctx.beginPath();
      ctx.moveTo(sp.trail[0].x, sp.trail[0].y);
      for (let j = 1; j < sp.trail.length; j++) {
        ctx.lineTo(sp.trail[j].x, sp.trail[j].y);
      }
      ctx.strokeStyle = 'rgba(255, 195, 115, 0.55)';
      ctx.lineWidth = 2.0;
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(255, 230, 165, 0.95)';
    ctx.beginPath();
    ctx.arc(sp.x, sp.y, 3.8, 0, Math.PI * 2);
    ctx.fill();
  }

  if (slashTrail.length > 1) {
    ctx.beginPath();
    ctx.moveTo(slashTrail[0].x, slashTrail[0].y);
    for (let i = 1; i < slashTrail.length; i++) {
      ctx.lineTo(slashTrail[i].x, slashTrail[i].y);
    }
    ctx.strokeStyle = 'rgba(235, 242, 255, 0.52)';
    ctx.lineWidth = 1.6;
    ctx.lineCap = 'round';
    ctx.stroke();
  }

  ctx.restore();
}

function renderFrame(timeSec) {
  drawBackground(timeSec);
  const placedBoxes = computeLabelLayout();
  drawLinks(placedBoxes);

  const sortedNodes = nodes.slice().sort(function (a, b) {
    return b.depth - a.depth;
  });
  for (let i = 0; i < sortedNodes.length; i++) {
    drawNodeBallAndIcon(sortedNodes[i]);
  }

  drawEffects();
  drawNodeLabels();
}
