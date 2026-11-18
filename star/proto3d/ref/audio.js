/* 声音模块（从 2D 版抽出，已调响）。第一次点击或按键时调用 ensureAudio()；之后直接调用：
   creak(t, scale)   拉皮筋时的「吱」，t 是张力 0 到 1；  twang(t, launch)   松手的「嘣」，launch 为真时再带一声「嗖」；
   whoosh()          弹出火花的「嗖」；              swishSound()     一划切线时刀光的「嗖」；    sliceSound()   线被切断的「咔」。
   只有这五种声音，别的操作一律静音。audioLog 记录每次真正发声（测试用）。setMuted(true/false) 静音开关。 */
const SOUND = {
    master: 0.8,
    comp: { threshold: -8, knee: 6, ratio: 6, attack: 0.002, release: 0.15 },
    creak: { stepT: 0.02, maxPerSec: 40, fBase: 700, fK: 1900, q: 2.2, attack: 0.002, decay: 0.028,
             gainBase: 0.5, gainK: 0.5, toneBase: 90, toneK: 260, toneGain: 0.14, toneDecay: 0.035,
             jitter: 0.08, nodeDragScale: 0.6, nodeDragFrom: 0.7 },
    twang: { minT: 0.08, f0Base: 240, f0K: 200, bendFrom: 1.6, bendMs: 40, vibHz: 7.5, vibDepth: 0.03,
             tauBase: 0.07, tauK: 0.12, gainBase: 0.10, gainK: 0.25, snapGainK: 0.22, snapDecay: 0.012, snapHp: 2000 },
    whoosh: { fFrom: 1800, fTo: 350, q: 0.9, ms: 260, gain: 0.6, attack: 0.02 },
    swish: { fFrom: 3200, fTo: 900, q: 0.7, ms: 140, gain: 0.5, attack: 0.012 },
    slice: { hp: 2200, lp: 6500, noiseGain: 0.4, noiseDecay: 0.035, pluckFrom: 340, pluckTo: 210, pluckMs: 90, pluckGain: 0.22, pluckDecay: 0.09 },
    logMax: 200
  };
let audioCtx = null, masterGain = null, noiseBuffer = null, muted = false, lastCreakAt = -Infinity;
const audioLog = [];
function ensureAudio() {
  if (!audioCtx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    try {
      audioCtx = new AC();
      const comp = audioCtx.createDynamicsCompressor();
      comp.threshold.value = SOUND.comp.threshold;
      comp.ratio.value = SOUND.comp.ratio;
      comp.knee.value = SOUND.comp.knee;
      comp.attack.value = SOUND.comp.attack;
      comp.release.value = SOUND.comp.release;
      masterGain = audioCtx.createGain();
      masterGain.gain.value = muted ? 0 : SOUND.master;
      masterGain.connect(comp);
      comp.connect(audioCtx.destination);
      const len = Math.max(1, Math.floor(audioCtx.sampleRate));
      noiseBuffer = audioCtx.createBuffer(1, len, audioCtx.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
            const unlock = audioCtx.createBuffer(1, 1, audioCtx.sampleRate);
      const us = audioCtx.createBufferSource(); us.buffer = unlock; us.connect(audioCtx.destination); us.start(0);
    } catch (err) {
      audioCtx = null;
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
}
function logAudio(type, t) {
  audioLog.push({ type: type, t: t, at: performance.now() });
  while (audioLog.length > SOUND.logMax) audioLog.shift();
}
function canPlaySound() { return !!audioCtx && !muted && audioCtx.state !== 'closed'; }
function creak(t, scale) {
  if (!canPlaySound() || !noiseBuffer) return;
  const nowMs = performance.now();
  if (nowMs - lastCreakAt < 1000 / SOUND.creak.maxPerSec) return;
  lastCreakAt = nowMs;
  const c = SOUND.creak;
  const now = audioCtx.currentTime + 0.003;
  const jitter = 1 + (Math.random() * 2 - 1) * c.jitter;
  const noise = audioCtx.createBufferSource();
  noise.buffer = noiseBuffer;
  const bp = audioCtx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.frequency.value = (c.fBase + c.fK * t) * jitter;
  bp.Q.value = c.q;
  const ng = audioCtx.createGain();
  const peak = (c.gainBase + c.gainK * t) * scale;
  ng.gain.setValueAtTime(0.0001, now);
  ng.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), now + c.attack);
  ng.gain.exponentialRampToValueAtTime(0.0001, now + c.attack + c.decay);
  noise.connect(bp);
  bp.connect(ng);
  ng.connect(masterGain);
  const tone = audioCtx.createOscillator();
  tone.type = 'triangle';
  tone.frequency.value = c.toneBase + c.toneK * t;
  const tg = audioCtx.createGain();
  const tPeak = Math.max(0.0002, c.toneGain * t * scale);
  tg.gain.setValueAtTime(0.0001, now);
  tg.gain.exponentialRampToValueAtTime(tPeak, now + c.attack);
  tg.gain.exponentialRampToValueAtTime(0.0001, now + c.attack + c.toneDecay);
  tone.connect(tg);
  tg.connect(masterGain);
  try {
    noise.start(now, Math.random() * 0.7);
    tone.start(now);
    noise.stop(now + 0.06);
    tone.stop(now + 0.06);
  } catch (err) { /* ignore */ }
  logAudio('creak', t);
}
function twang(t, launch) {
  if (!canPlaySound()) return;
  const c = SOUND.twang;
  const now = audioCtx.currentTime + 0.003;
  const f0 = c.f0Base + c.f0K * t;
  const osc = audioCtx.createOscillator();
  osc.type = 'triangle';
  osc.frequency.setValueAtTime(Math.max(30, f0 * c.bendFrom), now);
  osc.frequency.exponentialRampToValueAtTime(Math.max(30, f0), now + c.bendMs / 1000);
  const lfo = audioCtx.createOscillator();
  lfo.type = 'sine';
  lfo.frequency.value = c.vibHz;
  const lfoGain = audioCtx.createGain();
  lfoGain.gain.value = f0 * c.vibDepth;
  lfo.connect(lfoGain);
  lfoGain.connect(osc.frequency);
  const g = audioCtx.createGain();
  const peak = c.gainBase + c.gainK * t;
  const tau = c.tauBase + c.tauK * t;
  g.gain.setValueAtTime(0.0001, now);
  g.gain.linearRampToValueAtTime(Math.max(0.0002, peak), now + 0.003);
  g.gain.setTargetAtTime(0.0001, now + 0.003, tau);
  osc.connect(g);
  g.connect(masterGain);
  try {
    osc.start(now);
    lfo.start(now);
    osc.stop(now + 0.003 + tau * 5);
    lfo.stop(now + 0.003 + tau * 5);
  } catch (err) { /* ignore */ }
  if (noiseBuffer) {
    const noise = audioCtx.createBufferSource();
    noise.buffer = noiseBuffer;
    const hp = audioCtx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = c.snapHp;
    const ng = audioCtx.createGain();
    const np = Math.max(0.0002, c.snapGainK * t);
    ng.gain.setValueAtTime(np, now);
    ng.gain.exponentialRampToValueAtTime(0.0001, now + c.snapDecay);
    noise.connect(hp);
    hp.connect(ng);
    ng.connect(masterGain);
    try { noise.start(now, Math.random() * 0.5); noise.stop(now + 0.06); } catch (err) { /* ignore */ }
  }
  logAudio('twang', t);
  if (launch) whoosh();
}
function whoosh() {
  if (!canPlaySound() || !noiseBuffer) return;
  const c = SOUND.whoosh;
  const now = audioCtx.currentTime + 0.003;
  const noise = audioCtx.createBufferSource();
  noise.buffer = noiseBuffer;
  const bp = audioCtx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.Q.value = c.q;
  bp.frequency.setValueAtTime(c.fFrom, now);
  bp.frequency.exponentialRampToValueAtTime(Math.max(20, c.fTo), now + c.ms / 1000);
  const g = audioCtx.createGain();
  g.gain.setValueAtTime(0.0001, now);
  g.gain.linearRampToValueAtTime(c.gain, now + c.attack);
  g.gain.linearRampToValueAtTime(0.0001, now + c.ms / 1000);
  noise.connect(bp);
  bp.connect(g);
  g.connect(masterGain);
  try { noise.start(now, Math.random() * 0.5); noise.stop(now + c.ms / 1000); } catch (err) { /* ignore */ }
  logAudio('whoosh', 0);
}
function swishSound() {
  if (!canPlaySound() || !noiseBuffer) return;
  const c = SOUND.swish, now = audioCtx.currentTime + 0.003;
  const src = audioCtx.createBufferSource(); src.buffer = noiseBuffer;
  const bp = audioCtx.createBiquadFilter(); bp.type = 'bandpass'; bp.Q.value = c.q;
  bp.frequency.setValueAtTime(c.fFrom, now);
  bp.frequency.exponentialRampToValueAtTime(c.fTo, now + c.ms / 1000);
  const g = audioCtx.createGain();
  g.gain.setValueAtTime(0.0001, now);
  g.gain.linearRampToValueAtTime(c.gain, now + c.attack);
  g.gain.exponentialRampToValueAtTime(0.0001, now + c.ms / 1000);
  src.connect(bp); bp.connect(g); g.connect(masterGain);
  src.start(now, Math.random() * 0.5); src.stop(now + c.ms / 1000 + 0.05);
  logAudio('swish', 1);
}
function sliceSound() {
  if (!canPlaySound() || !noiseBuffer) return;
  const c = SOUND.slice, now = audioCtx.currentTime + 0.003;
  const src = audioCtx.createBufferSource(); src.buffer = noiseBuffer;
  const hp = audioCtx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = c.hp;
  const lp = audioCtx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = c.lp;
  const g = audioCtx.createGain();
  g.gain.setValueAtTime(0.0001, now);
  g.gain.linearRampToValueAtTime(c.noiseGain, now + 0.001);
  g.gain.exponentialRampToValueAtTime(0.0001, now + 0.001 + c.noiseDecay);
  src.connect(hp); hp.connect(lp); lp.connect(g); g.connect(masterGain);
  src.start(now, Math.random() * 0.5); src.stop(now + 0.15);
  const o = audioCtx.createOscillator(); o.type = 'triangle';
  o.frequency.setValueAtTime(c.pluckFrom, now);
  o.frequency.exponentialRampToValueAtTime(c.pluckTo, now + c.pluckMs / 1000);
  const og = audioCtx.createGain();
  og.gain.setValueAtTime(0.0001, now);
  og.gain.linearRampToValueAtTime(c.pluckGain, now + 0.002);
  og.gain.exponentialRampToValueAtTime(0.0001, now + 0.002 + c.pluckDecay);
  o.connect(og); og.connect(masterGain); o.start(now); o.stop(now + 0.25);
  logAudio('slice', 1);
}
function setMuted(b) {
  muted = !!b;
  if (masterGain && audioCtx) masterGain.gain.setTargetAtTime(muted ? 0 : SOUND.master, audioCtx.currentTime, 0.01);
}
