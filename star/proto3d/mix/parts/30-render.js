function hexToRgb(hex) {
  const s = String(hex || '#94a3b8').replace('#', '').trim();
  if (s.length === 3) {
    return {
      r: parseInt(s[0] + s[0], 16) || 180,
      g: parseInt(s[1] + s[1], 16) || 190,
      b: parseInt(s[2] + s[2], 16) || 210
    };
  }
  const num = parseInt(s.substring(0, 6), 16);
  if (isNaN(num)) return { r: 180, g: 195, b: 215 };
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255
  };
}

function clampByte(v) {
  return Math.max(0, Math.min(255, Math.round(v)));
}

function brightenRgb(rgb, factor) {
  const boost = factor > 1 ? (factor - 1) * 48 : 0;
  return {
    r: clampByte(rgb.r * factor + boost),
    g: clampByte(rgb.g * factor + boost),
    b: clampByte(rgb.b * factor + boost)
  };
}

function mixRgb(a, b, t) {
  return {
    r: clampByte(a.r + (b.r - a.r) * t),
    g: clampByte(a.g + (b.g - a.g) * t),
    b: clampByte(a.b + (b.b - a.b) * t)
  };
}

function rgbaStr(rgb, alpha) {
  return 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',' + Math.max(0, Math.min(1, alpha)).toFixed(3) + ')';
}

function findRubberBandForLink(lk) {
  for (let i = 0; i < rubberBands.length; i++) {
    if (rubberBands[i].link === lk) return rubberBands[i];
  }
  return null;
}

function renderBackground() {
  const cx = viewW * 0.5;
  const cy = viewH * 0.48;
  const maxR = Math.max(viewW, viewH) * 0.78;
  const bgGrad = ctx.createRadialGradient(cx, cy, 10, cx, cy, maxR);
  bgGrad.addColorStop(0, '#0c1220');
  bgGrad.addColorStop(0.55, '#080c15');
  bgGrad.addColorStop(1, '#05070c');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, viewW, viewH);

  for (let i = 0; i < bgStars.length; i++) {
    const st = bgStars[i];
    const p = project3D(st.x + cam.tx, st.y + cam.ty, st.z + cam.tz);
    if (p.behind || p.x < 0 || p.x > viewW || p.y < 0 || p.y > viewH) continue;
    const a = st.alpha * (focusId ? 0.45 : 1.0);
    ctx.fillStyle = 'rgba(203, 213, 225, ' + a.toFixed(3) + ')';
    ctx.beginPath();
    ctx.arc(p.x, p.y, st.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

function renderLinks() {
  const ordered = links.slice().sort((l1, l2) => {
    const a1 = nodeMap.get(l1.a), b1 = nodeMap.get(l1.b);
    const a2 = nodeMap.get(l2.a), b2 = nodeMap.get(l2.b);
    const d1 = (a1 && b1) ? (a1.depth + b1.depth) * 0.5 : 1000;
    const d2 = (a2 && b2) ? (a2.depth + b2.depth) * 0.5 : 1000;
    return d2 - d1;
  });

  const warmColor = { r: 255, g: 148, b: 66 };
  for (let i = 0; i < ordered.length; i++) {
    const lk = ordered[i];
    const na = nodeMap.get(lk.a);
    const nb = nodeMap.get(lk.b);
    if (!na || !nb || (na.behind && nb.behind)) continue;

    const avgDepth = (na.depth + nb.depth) * 0.5 - 340;
    const depthVis = Math.max(0.28, Math.min(1.0, 1.24 - avgDepth / 1450));
    const focusDim = (!focusId || focusLinks.has(lk)) ? 1.0 : 0.16;
    const baseRgb = mixRgb(hexToRgb(na.color), hexToRgb(nb.color), 0.5);
    const rb = findRubberBandForLink(lk);

    ctx.save();
    if (rb) {
      const mx = (na.sx + nb.sx) * 0.5 + rb.ox;
      const my = (na.sy + nb.sy) * 0.5 + rb.oy;
      const t = Math.max(0, Math.min(1, rb.tension));
      const col = mixRgb(baseRgb, warmColor, Math.min(1, t * 1.15));
      const lw = 2.2 * (1 - t * (1 - 0.45));
      ctx.strokeStyle = rgbaStr(col, Math.min(1, (0.72 + t * 0.26) * focusDim));
      ctx.lineWidth = lw;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.moveTo(na.sx, na.sy);
      ctx.lineTo(mx, my);
      ctx.lineTo(nb.sx, nb.sy);
      ctx.stroke();

      if (t > 0.12) {
        ctx.fillStyle = rgbaStr(col, 0.85);
        ctx.beginPath();
        ctx.arc(mx, my, 2.2 + t * 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    } else {
      const isHover = lk === hoverLink;
      let alpha = 0.44 * depthVis * focusDim;
      if (lk.kind === 'suggest') alpha = 0.58 * depthVis * focusDim;
      else if (lk.kind === 'poss') alpha = 0.42 * depthVis * focusDim;
      else if (lk.kind === 'kept') alpha = 0.65 * depthVis * focusDim;
      if (isHover) alpha = Math.min(0.95, alpha + 0.28);

      ctx.strokeStyle = rgbaStr(baseRgb, alpha);
      ctx.lineWidth = isHover ? 2.1 : (lk.kind === 'struct' ? 1.35 : 1.55);
      if (lk.kind === 'suggest' || lk.kind === 'poss') {
        ctx.setLineDash([5, 5]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(na.sx, na.sy);
      ctx.lineTo(nb.sx, nb.sy);
      ctx.stroke();
    }
    ctx.restore();
  }
}

function renderRipplesAndEffects(now) {
  for (let i = ripples.length - 1; i >= 0; i--) {
    const rp = ripples[i];
    const elapsed = (now - rp.born) / 1000;
    if (elapsed >= rp.duration) {
      ripples.splice(i, 1);
      continue;
    }
    const p = elapsed / rp.duration;
    const proj = project3D(rp.x, rp.y, rp.z);
    if (proj.behind) continue;
    const ease = 1 - Math.pow(1 - p, 2.4);
    const rad = (14 + ease * 46) * proj.scale;
    const alpha = Math.pow(1 - p, 1.8) * 0.68;
    const rgb = hexToRgb(rp.color);
    ctx.save();
    ctx.strokeStyle = rgbaStr(rgb, alpha);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(proj.x, proj.y, rad, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  for (let i = sparks.length - 1; i >= 0; i--) {
    const sp = sparks[i];
    const elapsed = (now - sp.born) / 1000;
    if (elapsed >= sp.duration) {
      sparks.splice(i, 1);
      continue;
    }
    const t = elapsed / sp.duration;
    const ease = 1 - Math.pow(1 - t, 3);
    const targetNode = nodeMap.get(sp.targetId);
    const tx = targetNode ? targetNode.sx : sp.x0;
    const ty = targetNode ? targetNode.sy : sp.y0;
    const sx = sp.x0 + (tx - sp.x0) * ease;
    const sy = sp.y0 + (ty - sp.y0) * ease - Math.sin(t * Math.PI) * 18;
    ctx.save();
    ctx.fillStyle = 'rgba(251, 191, 36, ' + (1 - t * 0.5).toFixed(3) + ')';
    ctx.shadowColor = '#f59e0b';
    ctx.shadowBlur = 12;
    ctx.beginPath();
    ctx.arc(sx, sy, 3.6 * (1 - t * 0.35), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  if (slashTrail.length > 1) {
    ctx.save();
    for (let i = 1; i < slashTrail.length; i++) {
      const p0 = slashTrail[i - 1];
      const p1 = slashTrail[i];
      const age = (now - p1.t) / 220;
      if (age >= 1) continue;
      ctx.strokeStyle = 'rgba(248, 250, 252, ' + ((1 - age) * 0.78).toFixed(3) + ')';
      ctx.lineWidth = (1 - age) * 2.6;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(p0.x, p0.y);
      ctx.lineTo(p1.x, p1.y);
      ctx.stroke();
    }
    ctx.restore();
  }
  slashTrail = slashTrail.filter(p => (now - p.t) < 220);
}
