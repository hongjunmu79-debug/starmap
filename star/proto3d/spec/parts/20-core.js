const PRESETS = {
  claude: { center: 0.30, repel: 0.85, link: 0.50, distance: 0.80 },   // Claude: swept by metrics (tools/tune3d.py)
  gemini: { center: 0.36, repel: 0.46, link: 0.54, distance: 0.44 }
};

const F_PERSP = 900;
const D_INIT = 1100;
const YAW_INIT = 0.35;
const PITCH_INIT = 0.22;
const REF_S = F_PERSP / D_INIT;

const STATUS_Z = {
  running: -140,
  explore: 0,
  pool: 140,
  frozen: 280
};

const STATUS_BRIGHT = {
  running: 1.3,
  explore: 1.0,
  pool: 0.85,
  frozen: 0.55
};

const LINK_PARAMS = {
  struct:    { L0: 150, k0: 0.55, width: 1.5 },
  poss:      { L0: 160, k0: 0.45, width: 1.3 },
  kept:      { L0: 160, k0: 0.45, width: 1.5 },
  mine:      { L0: 340, k0: 0.30, width: 1.6 },
  confirmed: { L0: 360, k0: 0.04, width: 1.5 },
  suggest:   { L0: 360, k0: 0.03, width: 1.3 }
};

const canvas = document.getElementById('starmap-canvas');
const ctx = canvas.getContext('2d');
let W = window.innerWidth;
let H = window.innerHeight;
let dpr = Math.min(window.devicePixelRatio || 1, 2);

let forces = {
  center: PRESETS.claude.center,
  repel: PRESETS.claude.repel,
  link: PRESETS.claude.link,
  distance: PRESETS.claude.distance
};

let nodes = [];
let nodeMap = new Map();
let links = [];
let bgStars = [];
let ripples = [];
let sparks = [];
let cutHistory = [];
let slashTrail = [];
let elastic = null;

let simAlpha = 1.0;
let focusedId = null;
let focusHopMap = new Map();
let hoveredNode = null;
let hoveredLink = null;
let draggedNode = null;
let pointerPos = { x: -9999, y: -9999 };
let typedSeq = 0;
let sparkSeq = 0;
let lastLabelOverlaps = 0;
let fpsValue = 60;
let forcesPanel = null;
let anchorTargets = null;
let anchorTimer = 0;

const cam = {
  yaw: YAW_INIT,
  pitch: PITCH_INIT,
  D: D_INIT,
  targetD: D_INIT,
  velD: 0,
  tx: 0,
  ty: 0,
  tz: 0,
  vtx: 0,
  vty: 0,
  vtz: 0,
  vYaw: 0,
  vPitch: 0,
  focusGoal: null,
  resetAnim: null
};

const iconPathCache = new Map();
function getIconPath(name) {
  if (!name || !DATA || !DATA.icons) return null;
  const d = DATA.icons[name];
  if (!d) return null;
  if (!iconPathCache.has(name)) {
    try {
      iconPathCache.set(name, new Path2D(d));
    } catch (e) {
      iconPathCache.set(name, null);
    }
  }
  return iconPathCache.get(name);
}

function mulberry32(a) {
  return function () {
    let t = (a += 0x6D2B79F5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgb(hex) {
  if (!hex || typeof hex !== 'string') return { r: 210, g: 220, b: 240 };
  let s = hex.trim().replace(/^#/, '');
  if (s.length === 3) {
    s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
  }
  const num = parseInt(s, 16);
  if (isNaN(num)) return { r: 210, g: 220, b: 240 };
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255
  };
}

function rgbaFromRgb(rgb, a, bright) {
  const b = bright === undefined ? 1 : bright;
  const r = Math.max(0, Math.min(255, Math.round(rgb.r * b)));
  const g = Math.max(0, Math.min(255, Math.round(rgb.g * b)));
  const bl = Math.max(0, Math.min(255, Math.round(rgb.b * b)));
  const alpha = Math.max(0, Math.min(1, a));
  return 'rgba(' + r + ',' + g + ',' + bl + ',' + alpha.toFixed(3) + ')';
}

function lerpRgb(c1, c2, t) {
  const u = Math.max(0, Math.min(1, t));
  return {
    r: c1.r + (c2.r - c1.r) * u,
    g: c1.g + (c2.g - c1.g) * u,
    b: c1.b + (c2.b - c1.b) * u
  };
}

function getDomainColor(domainId) {
  if (DATA && Array.isArray(DATA.domains)) {
    for (let i = 0; i < DATA.domains.length; i++) {
      if (DATA.domains[i].id === domainId) return DATA.domains[i].color;
    }
  }
  return (DATA && DATA.unsortedColor) || '#DCE3F5';
}

function registerNode(n) {
  n.rgb = hexToRgb(n.color);
  n.vx = n.vx || 0;
  n.vy = n.vy || 0;
  n.vz = n.vz || 0;
  n.pinned = !!n.pinned;
  n.sx = W / 2;
  n.sy = H / 2;
  n.rawSx = W / 2;
  n.rawSy = H / 2;
  n.depth = D_INIT;
  n.s = REF_S;
  n.sr = n.baseR;
  n.sIcon = n.iconSize;
  n.alpha = 1;
  n.bright = STATUS_BRIGHT[n.status] || 1.0;
  n.hoverShiftX = 0;
  n.hoverShiftY = 0;
  n.hoverGlow = 0;
  n.focusMul = 1;
  n.labelShown = false;
  n.labelBox = null;
  n.dragVx = 0;
  n.dragVy = 0;
  n.dragVz = 0;
  nodes.push(n);
  nodeMap.set(n.id, n);
  return n;
}

function addLink(a, b, kind, label) {
  if (!nodeMap.has(a) || !nodeMap.has(b)) return null;
  for (let i = 0; i < links.length; i++) {
    const l = links[i];
    if (!l.cut && ((l.a === a && l.b === b) || (l.a === b && l.b === a))) {
      return l;
    }
  }
  const linkObj = {
    a: a,
    b: b,
    kind: kind || 'struct',
    label: label || '',
    cut: false
  };
  links.push(linkObj);
  return linkObj;
}

function initBgStars() {
  const sRand = mulberry32(107);
  bgStars = [];
  for (let i = 0; i < 140; i++) {
    bgStars.push({
      u: sRand(),
      v: sRand(),
      r: 0.55 + sRand() * 1.15,
      baseAlpha: 0.14 + sRand() * 0.42,
      amp: 0.06 + sRand() * 0.18,
      speed: 0.35 + sRand() * 0.85,
      phase: sRand() * Math.PI * 2
    });
  }
}
