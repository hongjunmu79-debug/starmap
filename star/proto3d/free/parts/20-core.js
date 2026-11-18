const PRESETS = {
  claude: { center: 0.20, repel: 0.80, link: 0.50, distance: 0.60 },   // Claude: swept by metrics (tools/tune3d.py)
  gemini: { center: 0.52, repel: 0.54, link: 0.58, distance: 0.42 }
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
  center: PRESETS.gemini.center,
  repel: PRESETS.gemini.repel,
  link: PRESETS.gemini.link,
  distance: PRESETS.gemini.distance
};

const cam = {
  yaw: -0.34, pitch: 0.22, dist: 760, fov: 660,
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

function initGraphFromData() {
  nodes.length = 0;
  nodeMap.clear();
  links.length = 0;
  initBgStars();
  if (typeof DATA === 'undefined') return;

  const consts = DATA.constellations || [];
  const count = consts.length || 1;
  const ringR = 175;

  for (let i = 0; i < consts.length; i++) {
    const c = consts[i];
    const ang = (i / count) * Math.PI * 2 - 0.45;
    const cx = Math.cos(ang) * ringR;
    const cy = Math.sin(ang) * (ringR * 0.78);
    const cz = (i % 2 === 0 ? 1 : -1) * 78 + (i - 1.5) * 22;
    const col = getDomainColor(c.domain);
    const br = getStatusBrightness(c.status);
    const centerId = 'item:' + c.id;

    addNode({
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
      z: cz
    });

    const incs = c.includes || [];
    for (let j = 0; j < incs.length; j++) {
      const mAng = ang + ((j - (incs.length - 1) / 2) * 0.68);
      const mPhi = ((j % 3) - 1) * 0.55;
      const dist = 76 + (j % 2) * 16;
      const mx = cx + Math.cos(mAng) * Math.cos(mPhi) * dist;
      const my = cy + Math.sin(mAng) * Math.cos(mPhi) * dist;
      const mz = cz + Math.sin(mPhi) * dist;
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
        x: mx,
        y: my,
        z: mz
      });
      addLink({ a: centerId, b: memId, kind: 'struct' });
    }
  }

  const ideas = DATA.ideas || [];
  for (let i = 0; i < ideas.length; i++) {
    const idea = ideas[i];
    const id = 'idea:' + idea.id;
    addNode({
      id: id,
      rawId: idea.id,
      kind: 'idea',
      label: idea.text,
      icon: idea.icon || 'spark',
      color: DATA.unsortedColor || '#e2e8f0',
      bright: 1.0,
      r: 16.5,
      x: (i - (ideas.length - 1) / 2) * 70,
      y: 25 + i * 35,
      z: 65
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
        const a = (m / Math.max(1, list.length)) * Math.PI * 2 + k * 0.7;
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
          x: pNode.x + Math.cos(a) * 64,
          y: pNode.y + Math.sin(a) * 64,
          z: pNode.z + ((m % 2 === 0) ? 36 : -36)
        });
        addLink({ a: pid, b: possId, kind: 'poss', lens: exp.lens || '' });
      }
    }
  }
}
