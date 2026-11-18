const PRESETS = {
  claude: { center: 0.30, repel: 0.85, link: 0.50, distance: 0.80 },   // the set B's arrangement was tuned with (tools/tune3d.py)
  gemini: { center: 0.36, repel: 0.46, link: 0.54, distance: 0.44 }    // the set Gemini chose for B
};

const canvas = document.getElementById('stage');
const ctx = canvas.getContext('2d');
let viewW = window.innerWidth;
let viewH = window.innerHeight;
let dpr = Math.min(window.devicePixelRatio || 1, 2);

const nodes = [];
const nodeMap = new Map();
const links = [];
const iconPathCache = new Map();

const forces = {
  center: PRESETS.claude.center,
  repel: PRESETS.claude.repel,
  link: PRESETS.claude.link,
  distance: PRESETS.claude.distance
};

const cam = {
  yaw: 0.35, pitch: 0.22, dist: 1100, fov: 900,
  tx: 0, ty: 0, tz: 0,
  targetTx: 0, targetTy: 0, targetTz: 0,
  vx: 0, vy: 0, vz: 0
};

let focusId = null, focusSet = new Set(), focusLinks = new Set();
let hoverNodeId = null, hoverLink = null;
let typedSeq = 0, sparkSeq = 0, simAlpha = 1.0, anchorEndTime = 0;
let currentFps = 60, forcesPanel = null, isSyncingForces = false;
const ripples = [], sparks = [], rubberBands = [], cutHistory = [], bgStars = [];
let slashTrail = [], shownLabelIds = [], placedLabelBoxes = [];

function getDomainColor(domainId) {
  if (typeof DATA !== 'undefined' && Array.isArray(DATA.domains)) {
    for (let i = 0; i < DATA.domains.length; i++) {
      if (DATA.domains[i].id === domainId) return DATA.domains[i].color;
    }
  }
  return '#60a5fa';
}

function getStatusBrightness(status) {
  if (status === 'running') return 1.3;
  if (status === 'explore') return 1.0;
  if (status === 'pool') return 0.85;
  if (status === 'frozen') return 0.55;
  return 1.0;
}

function getIconPath(name) {
  if (!name || typeof DATA === 'undefined' || !DATA.icons) return null;
  let key = DATA.icons[name] ? name : 'spark';
  if (!DATA.icons[key]) {
    const keys = Object.keys(DATA.icons);
    if (!keys.length) return null;
    key = keys[0];
  }
  if (!iconPathCache.has(key)) {
    iconPathCache.set(key, new Path2D(DATA.icons[key]));
  }
  return iconPathCache.get(key);
}

function getLensIcon(lens) {
  if (typeof DATA !== 'undefined' && DATA.lensIcons && DATA.lensIcons[lens]) {
    return DATA.lensIcons[lens];
  }
  return 'spark';
}

function addNode(spec) {
  const n = {
    id: spec.id,
    rawId: spec.rawId || spec.id,
    parentId: spec.parentId || null,
    constellationId: spec.constellationId || null,
    kind: spec.kind || 'member',
    label: spec.label || '',
    lens: spec.lens || '',
    domain: spec.domain || null,
    status: spec.status || 'explore',
    icon: spec.icon || 'spark',
    color: spec.color || '#e2e8f0',
    bright: spec.bright !== undefined ? spec.bright : 1.0,
    r: spec.r || 15,
    x: spec.x || 0,
    y: spec.y || 0,
    z: spec.z || 0,
    vx: 0,
    vy: 0,
    vz: 0,
    fx: null,
    fy: null,
    fz: null,
    anchorTarget: null,
    sx: 0,
    sy: 0,
    sr: spec.r || 15,
    depth: 760,
    scale: 1,
    behind: false,
    dimFactor: 1.0,
    bornAt: spec.bornAt || 0
  };
  nodes.push(n);
  nodeMap.set(n.id, n);
  return n;
}

function addLink(spec) {
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if ((l.a === spec.a && l.b === spec.b) || (l.a === spec.b && l.b === spec.a)) {
      return l;
    }
  }
  const lk = {
    a: spec.a,
    b: spec.b,
    kind: spec.kind || 'struct',
    label: spec.label || '',
    lens: spec.lens || ''
  };
  links.push(lk);
  return lk;
}

function initBgStars() {
  bgStars.length = 0;
  let seed = 4219;
  function rand() {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  }
  for (let i = 0; i < 110; i++) {
    const theta = rand() * Math.PI * 2;
    const phi = Math.acos(2 * rand() - 1);
    const rad = 520 + rand() * 580;
    bgStars.push({
      x: rad * Math.sin(phi) * Math.cos(theta),
      y: rad * Math.sin(phi) * Math.sin(theta),
      z: rad * Math.cos(phi),
      size: 0.7 + rand() * 1.2,
      alpha: 0.12 + rand() * 0.26
    });
  }
}

function mulberry32(a) {
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
