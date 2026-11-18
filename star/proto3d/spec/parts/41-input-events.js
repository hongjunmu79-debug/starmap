function setupInputEvents() {
  let pointerDown = false, activePointerId = null;
  let interactionType = 'none', blankSubMode = 'undecided';
  let downX = 0, downY = 0, lastX = 0, lastY = 0;
  let downTime = 0, lastMoveTime = 0;
  let downYaw = YAW_INIT, downPitch = PITCH_INIT;
  let downNode = null, hasMovedEnough = false;
  let currentCutBatch = [], swishPlayed = false;
  let lastBlankClickTime = 0, lastBlankClickX = -9999, lastBlankClickY = -9999;

  canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });

  canvas.addEventListener('pointerdown', function (e) {
    if (typeof ensureAudio === 'function') ensureAudio();
    if (pointerDown) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    pointerPos.x = x;
    pointerPos.y = y;

    pointerDown = true;
    activePointerId = e.pointerId;
    downX = x;
    downY = y;
    lastX = x;
    lastY = y;
    downTime = performance.now();
    lastMoveTime = downTime;
    downYaw = cam.yaw;
    downPitch = cam.pitch;
    hasMovedEnough = false;
    currentCutBatch = [];
    swishPlayed = false;
    slashTrail = [];

    try {
      canvas.setPointerCapture(e.pointerId);
    } catch (err) {}

    if (e.button === 2 || e.shiftKey) {
      interactionType = 'pan';
      cam.vYaw = 0;
      cam.vPitch = 0;
      canvas.classList.add('dragging-cam');
      return;
    }

    const hitN = hitTestNode(x, y);
    if (hitN) {
      interactionType = 'node';
      downNode = hitN;
      return;
    }

    const hitL = hitTestLinkMid(x, y);
    if (hitL) {
      interactionType = 'elastic';
      elastic = {
        link: hitL, active: true, rebounding: false,
        px: x, py: y, vx: 0, vy: 0,
        tension: 0, dirX: 0, dirY: -1, elapsed: 0
      };
      return;
    }

    interactionType = 'blank';
    blankSubMode = 'undecided';
    cam.vYaw = 0;
    cam.vPitch = 0;
    cam.vtx = 0;
    cam.vty = 0;
    cam.vtz = 0;
  });

  window.addEventListener('pointermove', function (e) {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    pointerPos.x = x;
    pointerPos.y = y;

    if (!pointerDown || (activePointerId !== null && e.pointerId !== activePointerId)) {
      const hn = hitTestNode(x, y);
      hoveredNode = hn;
      hoveredLink = hn ? null : hitTestLinkMid(x, y);
      canvas.classList.toggle('hovering-node', !!hoveredNode);
      canvas.classList.toggle('hovering-link', !hoveredNode && !!hoveredLink);
      return;
    }

    const now = performance.now();
    const dtMs = Math.max(1, now - lastMoveTime);
    const dtSec = dtMs / 1000;
    const dx = x - lastX;
    const dy = y - lastY;
    const totalDist = Math.hypot(x - downX, y - downY);

    if (totalDist > 4.5) {
      hasMovedEnough = true;
    }

    if (interactionType === 'node' && downNode) {
      if (hasMovedEnough && !draggedNode) {
        draggedNode = downNode;
        draggedNode.pinned = false;
        draggedNode.dragVx = 0;
        draggedNode.dragVy = 0;
        draggedNode.dragVz = 0;
        simAlpha = Math.max(simAlpha, 0.35);
      }
    } else if (interactionType === 'elastic' && elastic && elastic.active) {
      const a = nodeMap.get(elastic.link.a);
      const b = nodeMap.get(elastic.link.b);
      if (a && b) {
        const mx = (a.sx + b.sx) * 0.5;
        const my = (a.sy + b.sy) * 0.5;
        const d = Math.hypot(x - mx, y - my);
        const s = 125 * Math.tanh(d / 125);
        const t = s / 125;
        elastic.tension = t;
        if (typeof creak === 'function') creak(t, 1);
      }
    } else if (interactionType === 'pan') {
      panCameraInScreenPlane(dx, dy, dtSec);
    } else if (interactionType === 'blank') {
      const segDist = Math.hypot(dx, dy);
      const speed = (segDist / dtMs) * 1000;
      const elapsedSinceDown = now - downTime;
      const crossed = findCrossedLinks(lastX, lastY, x, y);

      if (blankSubMode === 'undecided') {
        if (elapsedSinceDown <= 300 && speed >= 700 && crossed.length > 0) {
          blankSubMode = 'slash';
          cam.yaw = downYaw;
          cam.pitch = downPitch;
          cam.vYaw = 0;
          cam.vPitch = 0;
          slashTrail = [{ x: downX, y: downY }, { x: lastX, y: lastY }, { x: x, y: y }];
          if (!swishPlayed && typeof swishSound === 'function') {
            swishSound();
            swishPlayed = true;
          }
          for (let i = 0; i < crossed.length; i++) {
            crossed[i].cut = true;
            currentCutBatch.push(crossed[i]);
            if (typeof sliceSound === 'function') sliceSound();
          }
          simAlpha = Math.max(simAlpha, 0.38);
          if (focusedId) recomputeFocusHops();
        } else if (elapsedSinceDown > 300) {
          blankSubMode = 'orbit';
          canvas.classList.add('dragging-cam');
        }
      } else if (blankSubMode === 'slash') {
        slashTrail.push({ x: x, y: y });
        if (slashTrail.length > 18) slashTrail.shift();
        for (let i = 0; i < crossed.length; i++) {
          if (!crossed[i].cut) {
            crossed[i].cut = true;
            currentCutBatch.push(crossed[i]);
            if (typeof sliceSound === 'function') sliceSound();
            simAlpha = Math.max(simAlpha, 0.38);
          }
        }
        if (crossed.length > 0 && focusedId) recomputeFocusHops();
      }

      if (blankSubMode !== 'slash' && hasMovedEnough) {
        cam.focusGoal = null;
        cam.resetAnim = null;
        cam.yaw += dx * 0.005;
        cam.pitch = Math.max(-1.2, Math.min(1.2, cam.pitch + dy * 0.005));
        const instVYaw = (dx * 0.005) / Math.max(0.008, dtSec);
        const instVPitch = (dy * 0.005) / Math.max(0.008, dtSec);
        cam.vYaw = cam.vYaw * 0.35 + instVYaw * 0.65;
        cam.vPitch = cam.vPitch * 0.35 + instVPitch * 0.65;
      }
    }

    lastX = x;
    lastY = y;
    lastMoveTime = now;
  });

  function finishPointer(e) {
    if (!pointerDown) return;
    if (activePointerId !== null && e.pointerId !== undefined && e.pointerId !== activePointerId) return;

    const now = performance.now();
    if (now - lastMoveTime > 65) {
      cam.vYaw = 0;
      cam.vPitch = 0;
      cam.vtx = 0;
      cam.vty = 0;
      cam.vtz = 0;
    }

    if (interactionType === 'node' && downNode) {
      if (draggedNode) {
        draggedNode.pinned = true;
        draggedNode.vx = 0;
        draggedNode.vy = 0;
        draggedNode.vz = 0;
        draggedNode = null;
      } else {
        if (downNode.kind === 'poss') {
          downNode.kind = 'kept';
          for (let i = 0; i < links.length; i++) {
            const l = links[i];
            if (!l.cut && (l.a === downNode.id || l.b === downNode.id) && l.kind === 'poss') {
              l.kind = 'kept';
            }
          }
          simAlpha = Math.max(simAlpha, 0.3);
        }
        setFocusNode(downNode.id);
        addRipple(downNode.sx, downNode.sy, 300, 1.45, 0.22, downNode.color);
      }
    } else if (interactionType === 'elastic' && elastic && elastic.active) {
      const t = elastic.tension || 0;
      const launch = t >= 0.7;
      if (typeof twang === 'function') twang(t, launch);
      if (launch && elastic.link) {
        const na = nodeMap.get(elastic.link.a);
        const nb = nodeMap.get(elastic.link.b);
        if (na && nb) {
          const midDepth = (na.depth + nb.depth) * 0.5;
          const tx = elastic.px + elastic.dirX * 85;
          const ty = elastic.py + elastic.dirY * 85;
          sparks.push({
            startX: elastic.px,
            startY: elastic.py,
            x: elastic.px,
            y: elastic.py,
            tx: tx,
            ty: ty,
            depth: midDepth,
            a: elastic.link.a,
            b: elastic.link.b,
            elapsed: 0,
            dur: 0.38,
            trail: [{ x: elastic.px, y: elastic.py }]
          });
        }
      }
      elastic.active = false;
      elastic.rebounding = true;
      elastic.elapsed = 0;
    } else if (interactionType === 'blank') {
      if (blankSubMode === 'slash') {
        if (currentCutBatch.length > 0) {
          cutHistory.push(currentCutBatch.slice());
        }
        slashTrail = [];
      } else if (!hasMovedEnough) {
        const isDbl =
          now - lastBlankClickTime < 320 &&
          Math.hypot(downX - lastBlankClickX, downY - lastBlankClickY) < 24;
        if (isDbl) {
          triggerCameraReset();
          lastBlankClickTime = 0;
        } else {
          lastBlankClickTime = now;
          lastBlankClickX = downX;
          lastBlankClickY = downY;
          setFocusNode(null);
          addRipple(downX, downY, 60, 0.4, 0.22, '#DCE6FF');
        }
      }
    }

    pointerDown = false;
    activePointerId = null;
    interactionType = 'none';
    downNode = null;
    slashTrail = [];
    canvas.classList.remove('dragging-cam');
  }

  window.addEventListener('pointerup', finishPointer);
  window.addEventListener('pointercancel', finishPointer);

  canvas.addEventListener(
    'wheel',
    function (e) {
      e.preventDefault();
      cam.resetAnim = null;
      cam.targetD = Math.max(500, Math.min(2400, cam.targetD * Math.exp(e.deltaY * 0.001)));
    },
    { passive: false }
  );
}
