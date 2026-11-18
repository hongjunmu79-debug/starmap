"""Builds the merged 3D copy 'mix' = A's look and feel (Gemini 4's free design) + B's spatial arrangement (Claude's spec).

    python make_mix.py        -> proto3d/mix/ (parts copied from free/, patched)   then:  python assemble.py mix

What is taken from B (the user liked B's arrangement): the seeded starting positions (constellations in the four corners of the
scene, depth by status: running near and bright ... frozen far and dark, members on spherical shells), and B's layout physics
(with the four fixes Claude made to the spec: 1/d repulsion with the 520 cut-off and the 2D charges, the window-aspect pull on y,
and so on). Everything else is A: rendering, labels, camera (orbit + wheel), input, band, slice, sounds.
Also new in both: a ball dropped after a drag stays where it was dropped (like the 2D page), and dragging a constellation centre
carries its members along as a rigid group (the 2D rule the user asked for).
"""
import io
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "free")
DST = os.path.join(HERE, "mix")


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def sub(s, old, new, count=1):
    assert s.count(old) == count, ("pattern not found %d time(s): %r" % (count, old[:80]), s.count(old))
    return s.replace(old, new)


if os.path.isdir(DST):
    shutil.rmtree(DST)
shutil.copytree(os.path.join(SRC, "parts"), os.path.join(DST, "parts"))
shutil.copytree(os.path.join(SRC, "ref"), os.path.join(DST, "ref"))
P = lambda n: os.path.join(DST, "parts", n)  # noqa: E731

# ---------------------------------------------------------------- 00-head.html
s = read(P("00-head.html"))
s = sub(s, "<title>星图 · 3D · Gemini 自由版</title>", "<title>星图 · 3D · 融合版</title>")
s = sub(s, '<span id="version-tag">3D · Gemini 自由版</span>', '<span id="version-tag">3D · 融合版</span>')
write(P("00-head.html"), s)

# ---------------------------------------------------------------- 20-core.js
s = read(P("20-core.js"))
s = sub(s, """const PRESETS = {
  claude: { center: 0.20, repel: 0.80, link: 0.50, distance: 0.60 },   // Claude: swept by metrics (tools/tune3d.py)
  gemini: { center: 0.52, repel: 0.54, link: 0.58, distance: 0.42 }
};""", """const PRESETS = {
  claude: { center: 0.30, repel: 0.85, link: 0.50, distance: 0.80 },   // the set B's arrangement was tuned with (tools/tune3d.py)
  gemini: { center: 0.36, repel: 0.46, link: 0.54, distance: 0.44 }    // the set Gemini chose for B
};""")
s = sub(s, """  center: PRESETS.gemini.center,
  repel: PRESETS.gemini.repel,
  link: PRESETS.gemini.link,
  distance: PRESETS.gemini.distance
};""", """  center: PRESETS.claude.center,
  repel: PRESETS.claude.repel,
  link: PRESETS.claude.link,
  distance: PRESETS.claude.distance
};""")
i = s.index("function initGraphFromData() {")
new_init = r'''function mulberry32(a) {
  return function () {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// depth = attention (B's arrangement): running sits nearest and brightest, frozen farthest and darkest
const STATUS_Z = { running: -140, explore: 0, pool: 140, frozen: 280 };

function initGraphFromData() {
  nodes.length = 0;
  nodeMap.clear();
  links.length = 0;
  initBgStars();
  if (typeof DATA === 'undefined') return;

  // B's starting layout, same seed and same order of random numbers: the same data always gives the same picture
  const rand = mulberry32(7);
  const quadSigns = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  const consts = DATA.constellations || [];

  for (let i = 0; i < consts.length; i++) {
    const c = consts[i];
    const q = quadSigns[i % 4];
    const zSt = STATUS_Z[c.status] !== undefined ? STATUS_Z[c.status] : 0;
    const cx = q[0] * (380 + rand() * 80);
    const cy = q[1] * (380 + rand() * 80);
    const col = getDomainColor(c.domain);
    const br = getStatusBrightness(c.status);
    const centerId = 'item:' + c.id;

    const centerNode = addNode({
      id: centerId,
      rawId: c.id,
      constellationId: c.id,
      kind: 'center',
      label: c.title,
      domain: c.domain,
      status: c.status,
      icon: c.icon,
      color: col,
      bright: br,
      r: 24,
      x: cx,
      y: cy,
      z: zSt
    });
    centerNode.zStatus = zSt;

    const incs = c.includes || [];
    const total = incs.length;
    const rotOffset = rand() * Math.PI * 2;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    for (let j = 0; j < total; j++) {
      const yUnit = total > 1 ? 1 - (j / (total - 1)) * 2 : 0;
      const radXY = Math.sqrt(Math.max(0, 1 - yUnit * yUnit));
      const theta = goldenAngle * j + rotOffset + (rand() - 0.5) * 0.25;
      const shellR = 90 + rand() * 60;
      const memId = 'inc:' + c.id + ':' + j;
      addNode({
        id: memId,
        parentId: centerId,
        constellationId: c.id,
        kind: 'member',
        label: incs[j],
        domain: c.domain,
        status: c.status,
        icon: (c.incIcons && c.incIcons[j]) || c.icon,
        color: col,
        bright: br,
        r: 14,
        x: cx + Math.cos(theta) * radXY * shellR,
        y: cy + Math.sin(theta) * radXY * shellR,
        z: zSt + yUnit * shellR
      });
      addLink({ a: centerId, b: memId, kind: 'struct' });
    }
  }

  const ideas = DATA.ideas || [];
  for (let i = 0; i < ideas.length; i++) {
    const idea = ideas[i];
    const ix = (rand() - 0.5) * 110;
    const iy = (rand() - 0.5) * 110;
    const iz = -60 + rand() * 120;
    addNode({
      id: 'idea:' + idea.id,
      rawId: idea.id,
      kind: 'idea',
      label: idea.text,
      icon: idea.icon || 'spark',
      color: DATA.unsortedColor || '#e2e8f0',
      bright: 1.0,
      r: 16.5,
      x: ix,
      y: iy,
      z: iz
    });
  }

  const rawLinks = DATA.links || [];
  for (let i = 0; i < rawLinks.length; i++) {
    const lk = rawLinks[i];
    if (nodeMap.has(lk.a) && nodeMap.has(lk.b)) {
      addLink({ a: lk.a, b: lk.b, kind: lk.kind || 'confirmed', label: lk.label || '' });
    }
  }

  if (DATA.expansions) {
    const pKeys = Object.keys(DATA.expansions);
    for (let k = 0; k < pKeys.length; k++) {
      const pid = pKeys[k];
      const pNode = nodeMap.get(pid);
      if (!pNode) continue;
      const list = DATA.expansions[pid] || [];
      for (let m = 0; m < list.length; m++) {
        const exp = list[m];
        const possId = 'poss:' + exp.id;
        if (nodeMap.has(possId)) continue;
        const a = (m / Math.max(1, list.length)) * Math.PI * 2 + rand() * 0.5;
        const dist = 110 + rand() * 40;
        addNode({
          id: possId,
          rawId: exp.id,
          parentId: pid,
          constellationId: pNode.constellationId,
          kind: 'poss',
          label: exp.text,
          lens: exp.lens || '',
          domain: pNode.domain,
          icon: getLensIcon(exp.lens),
          color: pNode.color || DATA.unsortedColor || '#cbd5e1',
          bright: 0.9,
          r: 12.5,
          x: pNode.x + Math.cos(a) * dist,
          y: pNode.y + Math.sin(a) * dist,
          z: pNode.z + (rand() - 0.5) * 60
        });
        addLink({ a: pid, b: possId, kind: 'poss', lens: exp.lens || '' });
      }
    }
  }
}
'''
s = s[:i] + new_init
write(P("20-core.js"), s)

# camera: B's numbers (perspective 900 at distance 1100, yaw +0.35, pitch 0.22) so the whole arrangement fits like it does on B;
# wheel range widened to match (A's old range was built around a distance of 760)
s = read(P("20-core.js"))
s = sub(s, "yaw: -0.34, pitch: 0.22, dist: 760, fov: 660,", "yaw: 0.35, pitch: 0.22, dist: 1100, fov: 900,")
write(P("20-core.js"), s)

# the camera sits 340 units farther away than A's (1100 instead of 760); A's depth fade is written in absolute depth, so shift it by the same
# amount, otherwise everything would be 25-40% dimmer than on A (the fade still works with depth: running near / frozen far, and with the wheel)
s = read(P("30-render.js"))
s = sub(s, "const avgDepth = (na.depth + nb.depth) * 0.5;", "const avgDepth = (na.depth + nb.depth) * 0.5 - 340;")
write(P("30-render.js"), s)
s = read(P("31-labels.js"))
s = sub(s, "const depthVis = Math.max(0.36, Math.min(1.0, 1.26 - n.depth / 1550));", "const depthVis = Math.max(0.36, Math.min(1.0, 1.26 - (n.depth - 340) / 1550));")
s = sub(s, "const fogT = Math.max(0, Math.min(0.42, (n.depth - 520) / 950));", "const fogT = Math.max(0, Math.min(0.42, (n.depth - 340 - 520) / 950));")
s = sub(s, "const depthVis = Math.max(0.42, Math.min(1.0, 1.25 - n.depth / 1600));", "const depthVis = Math.max(0.42, Math.min(1.0, 1.25 - (n.depth - 340) / 1600));")
write(P("31-labels.js"), s)

# ---------------------------------------------------------------- 21-physics.js
s = read(P("21-physics.js"))
i = s.index("  const step = Math.min(dt, 0.033) * 60;")
j = s.index("function warmUpSimulation(ticks) {")
step_new = r'''  anchorActive = hasAnchor;
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

'''
s = s[:i] + step_new + s[j:]
# the old early-return test and the alpha bookkeeping at the top of stepPhysics stay; fix warm-up
k = s.index("function warmUpSimulation(ticks) {")
s = s[:k] + r'''function warmUpSimulation(ticks) {
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
'''
# DeepSeek anchors: same spans as B (x 420, y 320, z 260)
s = sub(s, "  const spanX = Math.min(viewW, 1100) * 0.33;\n  const spanY = Math.min(viewH, 800) * 0.31;\n  const spanZ = 190;", "  const spanX = 420;\n  const spanY = 320;\n  const spanZ = 260;")
# group carry for centre drags
s += r'''
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
'''
write(P("21-physics.js"), s)

# ---------------------------------------------------------------- 40-input.js
s = read(P("40-input.js"))
s = sub(s, """      pointerState.dragNode = hitNode;
      hitNode.fx = hitNode.x; hitNode.fy = hitNode.y; hitNode.fz = hitNode.z;
      return;""", """      pointerState.dragNode = hitNode;
      pointerState.wasPinned = !!hitNode.pinned;
      pointerState.carried = null;
      hitNode.fx = hitNode.x; hitNode.fy = hitNode.y; hitNode.fz = hitNode.z;
      return;""")
s = sub(s, """        n.fx = n.x;
        n.fy = n.y;
        n.fz = n.z;
        if (focusId === n.id) {""", """        n.fx = n.x;
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
        if (focusId === n.id) {""")
s = sub(s, """      const n = pointerState.dragNode;
      n.fx = n.fy = n.fz = null;
      if (pointerState.movedDist <= 5) {""", """      const n = pointerState.dragNode;
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
      if (pointerState.movedDist <= 5) {""")
s = sub(s, "cam.dist = Math.max(380, Math.min(1350, cam.dist + e.deltaY * 0.45));", "cam.dist = Math.max(450, Math.min(2200, cam.dist + e.deltaY * 0.7));")
write(P("40-input.js"), s)

# ---------------------------------------------------------------- 50-boot.js
s = read(P("50-boot.js"))
s = sub(s, """      initial: {
        center: PRESETS.gemini.center,
        repel: PRESETS.gemini.repel,
        link: PRESETS.gemini.link,
        distance: PRESETS.gemini.distance
      },
      initialMode: 'gemini',""", """      initial: {
        center: PRESETS.claude.center,
        repel: PRESETS.claude.repel,
        link: PRESETS.claude.link,
        distance: PRESETS.claude.distance
      },
      initialMode: 'claude',""")
s = sub(s, "        wakeSim(0.85);\n      },\n      applyAnchors", "        wakeSim(0.5);\n      },\n      applyAnchors")
s = sub(s, """      for (let i = 0; i < 36; i++) {
        simAlpha = 0.85;
        stepPhysics(0.016, performance.now());
      }
      wakeSim(0.85);""", """      wakeSim(0.5);""")
s = sub(s, "warmUpSimulation(170);", "warmUpSimulation(300);")
write(P("50-boot.js"), s)

# ---------------------------------------------------------------- hint + notes
write(os.path.join(DST, "hint.txt"), "拖空白转镜头 · 滚轮推拉 · 拖球放下固定（拖星座中心，小球整组跟着走） · 拉线弹弓 · 快划切线（Ctrl+Z） · 单击聚焦 · 齿轮：布局力")
write(os.path.join(DST, "README.txt"), "融合版：A（Gemini 4 自由发挥）的外观和手感 + B（Claude 的规格）的空间排布。由 make_mix.py 从 free/ 生成并打补丁，再用 assemble.py mix 拼成 star3d-mix.html。\n")
print("mix/ built from free/ (parts patched)")
