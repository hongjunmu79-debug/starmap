"""Scripted check of a 3D star-map copy (A: star3d-free.html, B: star3d-spec.html) in the controlled Chrome.

    python verify3d.py free      -> http://127.0.0.1:8791/3d/free.html
    python verify3d.py spec      -> http://127.0.0.1:8791/3d/spec.html

Writes shots/3d/<tag>-*.png and shots/3d/report-<tag>.json, prints a short table.
Only depends on the agreed test hooks (window.__star3d) and a few DOM ids; every check is isolated, one failure does not stop the rest.
"""
import io
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TAG = sys.argv[1] if len(sys.argv) > 1 else "free"
URL = "http://127.0.0.1:8791/3d/%s.html" % TAG
os.environ["STAR_URL"] = URL
os.environ.setdefault("STAR_PORT", "9334")
os.environ.setdefault("STAR_HEADLESS", "1")   # no window: frames always run, no sound   # own Chrome, so it can run while Gemini drives the one on 9333
import star_eye as se  # noqa: E402
import star_eye_watch as sw  # noqa: E402
from PIL import Image, ImageChops, ImageDraw  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "shots", "3d")
os.makedirs(OUT, exist_ok=True)
REPORT = {"tag": TAG, "url": URL, "checks": [], "notes": {}}
ws = None

INIT_JS = """
window.__errs = [];
window.addEventListener('error', function (e) { window.__errs.push('error: ' + e.message + ' @' + String(e.filename || '').split('/').pop() + ':' + e.lineno); });
window.addEventListener('unhandledrejection', function (e) { window.__errs.push('rejection: ' + (e.reason && e.reason.message || e.reason)); });
(function () { var ce = console.error; console.error = function () { window.__errs.push('console.error: ' + [].slice.call(arguments).join(' ')); ce.apply(console, arguments); }; })();
window.__gaps = []; (function () { var last = performance.now(); setInterval(function () { var n = performance.now(); window.__gaps.push(n - last); last = n; if (window.__gaps.length > 4000) window.__gaps.shift(); }, 8); })();
"""


def ev(js):
    return se.evaluate(ws, js)


def jev(js):
    v = ev("JSON.stringify((function(){" + js + "})())")
    return json.loads(v) if v is not None else None


def check(name, ok, detail=""):
    REPORT["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("  PASS " if ok else "  FAIL ") + name + (" — " + str(detail) if detail != "" else ""), flush=True)


def guarded(fn):
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            check(fn.__name__, False, "脚本出错：%s" % str(exc)[:200])
    run.__name__ = fn.__name__
    return run


def shot(name, fmt="png"):
    r = ws.call("Page.captureScreenshot", {"format": fmt})
    import base64
    raw = base64.b64decode(r["data"])
    if name:
        with open(os.path.join(OUT, "%s-%s.%s" % (TAG, name, "png" if fmt == "png" else "jpg")), "wb") as f:
            f.write(raw)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def positions():
    return jev("""var S = window.__star3d, T = S.test, o = {};
        S.nodes.forEach(function (n) { var p = T.screenOf(n.id); if (p) o[n.id] = [p.x, p.y, p.depth]; });
        return o;""") or {}


def mean_move(p0, p1):
    ds = [math.hypot(p1[k][0] - p0[k][0], p1[k][1] - p0[k][1]) for k in p0 if k in p1]
    return sum(ds) / len(ds) if ds else 0.0, max(ds) if ds else 0.0


def settle(max_s=20, tol=0.6):
    """Wait until no node moves more than tol px between two samples 0.5 s apart."""
    t0 = time.time()
    prev = positions()
    while time.time() - t0 < max_s:
        time.sleep(0.5)
        cur = positions()
        if mean_move(prev, cur)[1] < tol:
            return round(time.time() - t0, 1)
        prev = cur
    return None


def state():
    return jev("return window.__star3d.state();")


def audio_types():
    return jev("return window.__star3d.audioLog.map(function (e) { return e.type; });") or []


def now_ms():
    return ev("performance.now()")


def audio_since(t0):
    """Sound types logged after t0 (performance.now): audioLog is capped at 200 entries, so counting by length is not safe."""
    return jev("var t0 = %s; return window.__star3d.audioLog.filter(function (e) { return e.at >= t0; }).map(function (e) { return e.type; });" % repr(t0)) or []


def clear_links(min_y=40, max_y=600):
    """Links whose middle point is far from every ball (so a press there really grabs the line), best first."""
    return jev("""var S = window.__star3d, T = S.test, pts = [];
        S.nodes.forEach(function (x) { var p = T.screenOf(x.id); if (p) pts.push([p.x, p.y]); });
        var out = [];
        S.links.forEach(function (l) {
          var a = l.a && l.a.id || l.a || l.source && l.source.id || l.source, b = l.b && l.b.id || l.b || l.target && l.target.id || l.target;
          if (typeof a !== 'string' || typeof b !== 'string') return;
          var m = T.screenOfLink(a, b, 0.5); if (!m || m.y > %d || m.y < %d || m.x < 40 || m.x > 1240) return;
          var gap = Math.min.apply(null, pts.map(function (p) { return Math.hypot(p[0] - m.x, p[1] - m.y); }));
          out.push([a, b, gap, m.x, m.y]);
        });
        out.sort(function (u, v) { return v[2] - u[2]; });
        return out.slice(0, 8);""" % (max_y, min_y)) or []


def click_xy(x, y):
    se.mouse(ws, "mouseMoved", x, y)
    se.mouse(ws, "mousePressed", x, y, buttons=1, click=1)
    se.mouse(ws, "mouseReleased", x, y, buttons=0, click=1)


def drag_mod(x1, y1, x2, y2, ms, modifiers=0, button="left"):
    """A drag with a held modifier (Shift = 8) or the right button."""
    steps = max(4, int(ms / 16))
    bmask = 1 if button == "left" else 2
    base = {"modifiers": modifiers, "button": button}
    ws.send_nowait("Input.dispatchMouseEvent", dict(base, type="mouseMoved", x=x1, y=y1, buttons=0, clickCount=0))
    ws.send_nowait("Input.dispatchMouseEvent", dict(base, type="mousePressed", x=x1, y=y1, buttons=bmask, clickCount=1))
    start = time.time()
    for i in range(1, steps + 1):
        x, y = x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps
        w = start + ms / 1000 * i / steps - time.time()
        if w > 0:
            time.sleep(w)
        ws.send_nowait("Input.dispatchMouseEvent", dict(base, type="mouseMoved", x=x, y=y, buttons=bmask, clickCount=0))
    ws.send_nowait("Input.dispatchMouseEvent", dict(base, type="mouseReleased", x=x2, y=y2, buttons=0, clickCount=1))
    ws.drain()


def wheel(x, y, dy):
    ws.call("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy, "modifiers": 0})


def disc_changed(a, b, center, r_in, r_out, thr=40):
    """How many pixels changed by more than thr in the ring r_in..r_out around center."""
    box = (int(center[0] - r_out), int(center[1] - r_out), int(center[0] + r_out), int(center[1] + r_out))
    box = (max(0, box[0]), max(0, box[1]), min(a.width, box[2]), min(a.height, box[3]))
    d = ImageChops.difference(a.crop(box).convert("L"), b.crop(box).convert("L")).point(lambda v: 255 if v > thr else 0)
    mask = Image.new("L", d.size, 0)
    dr = ImageDraw.Draw(mask)
    cx, cy = center[0] - box[0], center[1] - box[1]
    dr.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), fill=255)
    dr.ellipse((cx - r_in, cy - r_in, cx + r_in, cy + r_in), fill=0)
    d = ImageChops.multiply(d, mask)
    return sum(1 for v in d.getdata() if v)


def img_diff(a, b, thr=24):
    d = ImageChops.difference(a.convert("L"), b.convert("L")).point(lambda v: 255 if v > thr else 0)
    return sum(1 for v in d.getdata() if v)


# ---------------------------------------------------------------------------------------------------------------------

@guarded
def t_load():
    ws.call("Page.navigate", {"url": URL})
    time.sleep(3.0)
    ok = False
    for _ in range(40):
        if ev("typeof window.__star3d === 'object' && document.readyState === 'complete'"):
            ok = True
            break
        time.sleep(0.5)
    errs = ev("window.__errs || []")
    check("页面能打开并有 __star3d", ok, "")
    check("加载后控制台没有报错", not errs, "; ".join(errs[:3]) if errs else "")
    if not ok:
        raise RuntimeError("no __star3d")
    miss = jev("""var S = window.__star3d, T = S.test || {}, miss = [];
        ['nodes', 'links', 'cam', 'audioLog', 'state', 'test'].forEach(function (k) { if (!(k in S)) miss.push(k); });
        ['screenOf', 'screenOfLink', 'labelsShown', 'overlaps', 'setForces', 'getForces'].forEach(function (k) { if (typeof T[k] !== 'function') miss.push('test.' + k); });
        var st = S.state ? S.state() : {};
        ['nodes', 'links', 'labels', 'fps', 'view', 'focus', 'forces'].forEach(function (k) { if (!(k in st)) miss.push('state().' + k); });
        return miss;""")
    check("测试钩子齐全", not miss, ",".join(miss))
    foc = ev("document.activeElement && document.activeElement.id")
    check("输入框一打开就聚焦", foc == "idea-input", str(foc))
    meta = jev("""var el = document.getElementById('idea-input'); var r = el ? el.getBoundingClientRect() : null;
        var corner = Array.from(document.querySelectorAll('body *')).filter(function (e) { return !/^(SCRIPT|STYLE)$/.test(e.tagName); }).map(function (e) { return e.children.length ? '' : (e.textContent || ''); }).filter(function (t) { return /3D/.test(t); }).map(function (t) { return t.slice(0, 40); }).slice(0, 3);
        return {w: r && Math.round(r.width), h: r && Math.round(r.height), ph: el && el.placeholder, cx: r && Math.round(r.left + r.width / 2), ver: corner, title: document.title};""")
    check("输入框规格 560x46、居中、占位文字", meta and meta["w"] == 560 and meta["h"] == 46 and abs(meta["cx"] - 640) <= 2 and meta["ph"] == "想到什么，直接打，回车记下", json.dumps(meta, ensure_ascii=False))
    REPORT["notes"]["version_label_texts"] = meta and meta.get("ver")


@guarded
def t_settle_and_quiet():
    s = state()
    REPORT["notes"]["initial_state"] = s
    t = settle(25)
    check("布局在 25 秒内静下来", t is not None, "用时 %s 秒" % t)
    time.sleep(0.5)
    cam0 = ev("JSON.stringify(window.__star3d.cam)")
    p0 = positions()
    time.sleep(3.0)
    p1 = positions()
    cam1 = ev("JSON.stringify(window.__star3d.cam)")
    mm, mx = mean_move(p0, p1)
    check("没有操作时什么都不动（3 秒内节点最大位移 < 0.5 px、镜头不变）", mx < 0.5 and cam0 == cam1, "最大位移 %.2f px，镜头%s" % (mx, "不变" if cam0 == cam1 else "变了"))
    o = jev("""var T = window.__star3d.test; return {overlaps: T.overlaps(), shown: T.labelsShown().length};""")
    check("总览文字 0 重叠", o["overlaps"] == 0, "显示了 %d 个文字，重叠 %d 对" % (o["shown"], o["overlaps"]))
    pos = positions()
    out = [k for k, v in pos.items() if not (0 <= v[0] <= 1280 and 0 <= v[1] <= 720)]
    check("总览：所有节点都在窗口里", not out, "窗口外：%s" % out[:5] if out else "共 %d 个节点" % len(pos))
    xs = [v[0] for v in pos.values()]
    ys = [v[1] for v in pos.values()]
    REPORT["notes"]["overview_bounds"] = [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]
    shot("1-overview")


@guarded
def t_hover_quiet():
    pos = positions()
    node = "inc:school:0" if "inc:school:0" in pos else sorted(k for k in pos if k.startswith("inc:"))[0]
    x, y = pos[node][0], pos[node][1]
    se.mouse(ws, "mouseMoved", 1250, 700)
    time.sleep(0.8)
    a = shot("")
    t_hover0 = now_ms()
    se.mouse(ws, "mouseMoved", x, y)
    time.sleep(0.25)
    mid = shot("")
    time.sleep(1.4)
    b = shot("hover")
    se.mouse(ws, "mouseMoved", 1250, 700)
    n_inner = disc_changed(a, b, (x, y), 0, 34)
    n_ring_mid = disc_changed(a, mid, (x, y), 46, 200)
    n_ring = disc_changed(a, b, (x, y), 46, 200)
    check("悬停：球周围 46–200 px 没有扩散的圈（变化像素少，且 0.25 秒到 1.6 秒之间没有增长）", n_ring < 3000 and (n_ring - n_ring_mid) < 500, "0.25 秒 %d、1.6 秒 %d 个像素变了（球自己 %d）" % (n_ring_mid, n_ring, n_inner))
    heard = audio_since(t_hover0)
    check("悬停没有声音", not heard, "悬停期间的声音：%s" % heard)


@guarded
def t_orbit_wheel_pan():
    base = positions()
    sx, sy = sw.empty_spot(ws)
    drag_x1, drag_y1 = sx, sy
    # a slow drag on empty sky turns the camera
    se.cmd_drag(drag_x1, drag_y1, drag_x1 - 240 if drag_x1 > 640 else drag_x1 + 240, drag_y1 + 40, 650)
    time.sleep(0.15)
    p_rel = positions()
    time.sleep(0.9)
    p_after = positions()
    mm, mx = mean_move(base, p_after)
    drift = mean_move(p_rel, p_after)[0]
    check("空白处慢拖 = 转动镜头（节点整体位移）", mm > 15, "平均位移 %.0f px，松手后又滑了 %.1f px（惯性）" % (mm, drift))
    check("转动后文字仍 0 重叠", jev("return window.__star3d.test.overlaps();") == 0, "")
    shot("3-rotated")
    n_links = state()["links"]
    check("慢拖没有把线切断", n_links == REPORT["notes"]["initial_state"]["links"], "线数 %d" % n_links)
    # wheel dolly
    cx, cy = 640, 360
    spread0 = jev("""var T = window.__star3d.test, ps = window.__star3d.nodes.map(function (n) { return T.screenOf(n.id); }).filter(Boolean);
        var mx = ps.reduce(function (s, p) { return s + p.x; }, 0) / ps.length, my = ps.reduce(function (s, p) { return s + p.y; }, 0) / ps.length;
        return ps.reduce(function (s, p) { return s + Math.hypot(p.x - mx, p.y - my); }, 0) / ps.length;""")
    wheel(cx, cy, -400)
    time.sleep(1.4)
    spread1 = jev("""var T = window.__star3d.test, ps = window.__star3d.nodes.map(function (n) { return T.screenOf(n.id); }).filter(Boolean);
        var mx = ps.reduce(function (s, p) { return s + p.x; }, 0) / ps.length, my = ps.reduce(function (s, p) { return s + p.y; }, 0) / ps.length;
        return ps.reduce(function (s, p) { return s + Math.hypot(p.x - mx, p.y - my); }, 0) / ps.length;""")
    check("滚轮向前 = 推近（节点散开程度变大）", spread1 > spread0 * 1.05, "平均离中心 %.0f → %.0f px" % (spread0, spread1))
    wheel(cx, cy, 400)
    time.sleep(1.2)
    # shift-drag pans: all nodes translate by about the same vector
    q0 = positions()
    drag_mod(sx, sy, sx + 120, sy + 60, 500, modifiers=8)
    time.sleep(1.0)
    q1 = positions()
    vecs = [(q1[k][0] - q0[k][0], q1[k][1] - q0[k][1]) for k in q0 if k in q1]
    mvx = sum(v[0] for v in vecs) / len(vecs)
    mvy = sum(v[1] for v in vecs) / len(vecs)
    mm_ = math.hypot(mvx, mvy)
    same = sum(1 for v in vecs if math.hypot(*v) > 1 and (v[0] * mvx + v[1] * mvy) / (math.hypot(*v) * mm_ + 1e-9) > 0.8) / len(vecs) if mm_ > 1 else 0
    check("Shift+拖动 = 平移（几乎所有节点朝同一方向移动；透视下近的移得多、远的移得少）", mm_ > 30 and same >= 0.9, "平均位移 (%.0f,%.0f)，%.0f%% 的节点方向一致" % (mvx, mvy, same * 100))
    # double-click empty: back to the first view
    sx2, sy2 = sw.empty_spot(ws)
    se.mouse(ws, "mouseMoved", sx2, sy2)
    se.mouse(ws, "mousePressed", sx2, sy2, buttons=1, click=1)
    se.mouse(ws, "mouseReleased", sx2, sy2, buttons=0, click=1)
    se.mouse(ws, "mousePressed", sx2, sy2, buttons=1, click=2)
    se.mouse(ws, "mouseReleased", sx2, sy2, buttons=0, click=2)
    time.sleep(1.6)
    p_reset = positions()
    mm2, mx2 = mean_move(base, p_reset)
    check("双击空白 = 镜头回到最初", mm2 < 8, "离最初的画面平均 %.1f px（最大 %.0f）" % (mm2, mx2))


@guarded
def t_focus():
    pos = positions()
    cands = [k for k in ("item:school", "item:personal-os", "item:offline-social", "item:land-lease") if k in pos]
    cid = cands[0] if cands else sorted(k for k in pos if k.startswith("item:"))[0]
    # a click on the centre may land on a ball that sits on top of it (compact layouts): try each centre until one of them takes the focus
    for cand in cands:
        x, y = positions()[cand][0], positions()[cand][1]
        click_xy(x, y)
        time.sleep(0.6)
        if state()["focus"] == cand:
            cid = cand
            break
        sx, sy = sw.empty_spot(ws)
        click_xy(sx, sy)
        time.sleep(1.2)
    else:
        x, y = positions()[cid][0], positions()[cid][1]
        click_xy(x, y)
    # camera smoothness: sample positions every 0.1 s after the click
    prev = positions()
    steps = []
    t0 = time.time()
    while time.time() - t0 < 2.4:
        time.sleep(0.1)
        cur = positions()
        steps.append(mean_move(prev, cur)[1])
        prev = cur
    st = state()
    check("单击星座中心 = 聚焦", st["focus"] == cid, "点的是 %s，focus=%s" % (cid, st["focus"]))
    mx = max(steps)
    check("聚焦时镜头柔和（每 0.1 秒节点最大位移 < 100 px，没有突然缩放）", mx < 100, "最大一步 %.0f px（最近的球），共 %d 步" % (mx, len(steps)))
    check("聚焦后文字 0 重叠", jev("return window.__star3d.test.overlaps();") == 0, "显示文字 %d 个" % st["labels"])
    shot("2-focus")
    sx, sy = sw.empty_spot(ws)
    click_xy(sx, sy)
    time.sleep(1.8)
    st2 = state()
    check("点空白退出聚焦", st2["focus"] in (None, "", False), "focus=%s" % st2["focus"])
    p_a = positions()
    time.sleep(1.2)
    check("退出聚焦后镜头不再动", mean_move(p_a, positions())[1] < 1, "")


@guarded
def t_drag_node():
    pos = positions()
    node = "inc:school:0" if "inc:school:0" in pos else sorted(k for k in pos if k.startswith("inc:"))[0]
    x0, y0 = pos[node][0], pos[node][1]
    dx, dy = (-150, 0) if x0 > 700 else (150, 0)
    se.cmd_drag(x0, y0, x0 + dx, y0 + dy, 700)
    time.sleep(0.8)
    p = ev("JSON.stringify(window.__star3d.test.screenOf(%s))" % json.dumps(node))
    p = json.loads(p)
    err = math.hypot(p["x"] - (x0 + dx), p["y"] - (y0 + dy))
    check("拖一个球：松手后停在鼠标放开的位置（误差 < 30 px）", err < 30, "误差 %.0f px" % err)
    time.sleep(2.0)
    p2 = json.loads(ev("JSON.stringify(window.__star3d.test.screenOf(%s))" % json.dumps(node)))
    check("放下的球固定不动（2 秒后没漂走）", math.hypot(p2["x"] - p["x"], p2["y"] - p["y"]) < 6, "漂了 %.1f px" % math.hypot(p2["x"] - p["x"], p2["y"] - p["y"]))
    # a drag must not start the elastic band or slice: link count unchanged
    check("拖球没有切断线", state()["links"] == REPORT["notes"]["initial_state"]["links"], "")


def pick_link(prefer):
    for a, b in prefer:
        ok = ev("!!window.__star3d.test.screenOfLink(%s,%s,0.5)" % (json.dumps(a), json.dumps(b)))
        if ok:
            return a, b
    return None


@guarded
def t_band():
    cand = clear_links()
    if not cand:
        raise RuntimeError("找不到可拉的线")
    a, b, gap, x, y = cand[0]
    n0 = state()["nodes"]
    t0 = now_ms()
    # press on the middle of the line, pull straight down 150 px in 700 ms, hold, then release
    ws.send_nowait("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none", "buttons": 0, "clickCount": 0})
    ws.send_nowait("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
    t_start = time.time()
    for i in range(1, 44):
        yy = y + 150 * i / 43
        w = t_start + 0.7 * i / 43 - time.time()
        if w > 0:
            time.sleep(w)
        ws.send_nowait("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": yy, "button": "left", "buttons": 1, "clickCount": 0})
    ws.drain()
    time.sleep(0.35)
    held = shot("4-band-held")
    types_hold = audio_since(t0)
    ws.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y + 150, "button": "left", "buttons": 0, "clickCount": 1})
    frames = []
    box = (int(x - 260), int(max(0, y - 120)), int(x + 260), int(min(720, y + 330)))
    prev = None
    for i in range(16):
        im = shot("", fmt="jpeg").crop(box)
        if prev is not None:
            frames.append(img_diff(prev, im, 30))
        prev = im
        time.sleep(0.06)
    time.sleep(2.2)
    types_all = audio_since(t0)
    nodes1 = state()["nodes"]
    still = ev("!!window.__star3d.test.screenOfLink(%s,%s,0.5)" % (json.dumps(a), json.dumps(b)))
    check("拉线：吱 / 嘣 都发声了", "creak" in types_all and "twang" in types_all, "声音：%s×%d 共 %d 次" % (",".join(sorted(set(types_all))), len(types_all), len(types_all)))
    check("拉线：拉着的时候已经有『吱』", "creak" in types_hold, "按住期间 %d 次" % len(types_hold))
    check("拉线：线没有被拉断", bool(still), "拉的是 %s — %s（离最近的球 %d px）" % (a, b, gap))
    check("拉线：拉到张力 ≥ 0.7 松手，开出一个新球（带嗖）", nodes1 == n0 + 1 and "whoosh" in types_all, "节点 %d → %d，嗖 %s" % (n0, nodes1, "有" if "whoosh" in types_all else "没有"))
    REPORT["notes"]["band_frame_diffs"] = frames
    mov = [i for i, d in enumerate(frames) if d > 30]
    last = (mov[-1] + 1) * 0.17 if mov else 0
    check("拉线：松手后弹回有一段时间（回弹期间画面持续变化，随后停下）", len(mov) >= 3 and last < 3.0, "有变化的帧：%d/%d，约 %.1f 秒后停" % (len(mov), len(frames), last))
    shot("5-band-after")


def point_clear(x, y, node_gap=42, link_gap=26):
    """True when (x, y) is not on a ball and not near any line (so a press there starts a camera drag / a slice, not a band or a ball drag)."""
    return bool(jev("""var S = window.__star3d, T = S.test, X = %f, Y = %f, ok = X > 8 && X < 1272 && Y > 8 && Y < 712;
        var pts = {};
        S.nodes.forEach(function (n) { var p = T.screenOf(n.id); if (p) { pts[n.id] = p; if (Math.hypot(p.x - X, p.y - Y) < %d) ok = false; } });
        S.links.forEach(function (l) {
          var a = l.a && l.a.id || l.a || l.source && l.source.id || l.source, b = l.b && l.b.id || l.b || l.target && l.target.id || l.target;
          var p = pts[a], q = pts[b]; if (!p || !q) return;
          var dx = q.x - p.x, dy = q.y - p.y, L2 = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((X - p.x) * dx + (Y - p.y) * dy) / L2));
          if (Math.hypot(p.x + dx * t - X, p.y + dy * t - Y) < %d) ok = false; });
        return ok;""" % (x, y, node_gap, link_gap)))


@guarded
def t_cut():
    cand = clear_links(min_y=120, max_y=560)
    if not cand:
        raise RuntimeError("找不到可切的线")
    L0 = state()["links"]
    chosen = None
    for a, b, gap, x, y in cand:
        pa, pb = positions().get(a), positions().get(b)
        if not pa or not pb:
            continue
        ux, uy = pb[0] - pa[0], pb[1] - pa[1]
        ln = math.hypot(ux, uy) or 1.0
        base = math.atan2(ux / ln, -uy / ln)   # the line's normal
        for ang in (0, 0.35, -0.35, 0.7, -0.7, 1.05, -1.05):
            for half in (110, 150):
                dxn, dyn = math.cos(base + ang), math.sin(base + ang)
                sx0, sy0, sx1, sy1 = x - dxn * half, y - dyn * half, x + dxn * half, y + dyn * half
                if point_clear(sx0, sy0) and point_clear(sx1, sy1):
                    chosen = (a, b, sx0, sy0, sx1, sy1)
                    break
            if chosen:
                break
        if chosen:
            break
    if not chosen:
        raise RuntimeError("找不到起点和终点都落在空白处的划线")
    a, b, sx0, sy0, sx1, sy1 = chosen
    t0 = now_ms()
    se.cmd_drag(sx0, sy0, sx1, sy1, 150)
    time.sleep(0.8)
    L1 = state()["links"]
    types1 = audio_since(t0)
    check("快速一划切断线", L1 < L0, "线 %d → %d（一划划过 %s — %s 附近，起点和终点都在空白处）" % (L0, L1, a, b))
    check("切线的声音：嗖 + 咔", "swish" in types1 and "slice" in types1, "%s，共 %d 次" % (",".join(sorted(set(types1))), len(types1)))
    se.cmd_key("Ctrl+z")
    time.sleep(0.8)
    L2 = state()["links"]
    check("Ctrl+Z 一次接回所有切断的线", L2 == L0, "线 %d → %d → %d" % (L0, L1, L2))


@guarded
def t_type_idea():
    n0 = state()["nodes"]
    box = json.loads(ev("(function(){var r=document.getElementById('idea-input').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2])})()"))
    click_xy(box[0], box[1])
    ws.call("Input.insertText", {"text": "周末办一场桌游夜"})
    se.cmd_key("Enter")
    time.sleep(6.0)
    n1 = state()["nodes"]
    ids = jev("return window.__star3d.nodes.map(function (n) { return n.id; }).filter(function (i) { return /typed/.test(i); });")
    check("打一条想法：落进场景并长出 3 条可能性（节点 +4）", n1 >= n0 + 4, "节点 %d → %d，新想法 %s" % (n0, n1, ids))
    p = ev("JSON.stringify(window.__star3d.test.screenOf(%s))" % json.dumps(ids[0])) if ids else None
    inside = p and p != "null" and 0 <= json.loads(p)["x"] <= 1280 and 0 <= json.loads(p)["y"] <= 720
    check("新想法在窗口里", bool(inside), p or "")
    check("新想法之后文字仍 0 重叠", jev("return window.__star3d.test.overlaps();") == 0, "")
    shot("6-typed")


@guarded
def t_forces():
    base = {"center": 0.45, "repel": 0.5, "link": 0.5, "distance": 0.5}

    def measure():
        return jev("""var S = window.__star3d, T = S.test;
            function wp(n) { var q = n.pos || n.p || n; return [q.x, q.y, q.z || 0]; }
            var nodes = S.nodes.filter(function (n) { return !/typed|poss/.test(n.id); });
            var items = nodes.filter(function (n) { return /^item:/.test(n.id); });
            function cen(list) { var c = [0, 0, 0]; list.forEach(function (n) { var q = wp(n); c[0] += q[0]; c[1] += q[1]; c[2] += q[2]; }); return c.map(function (v) { return v / list.length; }); }
            var c0 = cen(nodes);
            var spread = items.reduce(function (s, n) { var q = wp(n); return s + Math.hypot(q[0] - c0[0], q[1] - c0[1], q[2] - c0[2]); }, 0) / items.length;
            var byId = {}; S.nodes.forEach(function (n) { byId[n.id] = n; });
            var lens = []; S.links.forEach(function (l) {
                var A = byId[l.a && l.a.id || l.a || l.source && l.source.id || l.source], B = byId[l.b && l.b.id || l.b || l.target && l.target.id || l.target];
                var kind = l.kind || l.type || '';
                if (A && B && /^item:/.test(A.id) && /^inc:/.test(B.id) || (A && B && /^inc:/.test(A.id) && /^item:/.test(B.id))) { var p = wp(A), q = wp(B); lens.push(Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2])); } });
            var ps = S.nodes.map(function (n) { return T.screenOf(n.id); }).filter(Boolean);
            var near = Infinity; for (var i = 0; i < ps.length; i++) for (var j = i + 1; j < ps.length; j++) near = Math.min(near, Math.hypot(ps[i].x - ps[j].x, ps[i].y - ps[j].y));
            return {spread: spread, memberLen: lens.length ? lens.reduce(function (s, v) { return s + v; }, 0) / lens.length : null, nLens: lens.length, overlaps: T.overlaps(), nearest: near};""")

    res = {}
    for key in ("center", "repel", "link", "distance"):
        for tag, val in (("lo", 0.0), ("hi", 1.0)):
            v = dict(base)
            v[key] = val
            ev("window.__star3d.test.setForces(%s)" % json.dumps(v))
            t = settle(18, 0.8)
            res[(key, tag)] = measure()
            res[(key, tag)]["settle"] = t
    ev("window.__star3d.test.setForces(%s)" % json.dumps(base))
    settle(15, 0.8)
    REPORT["notes"]["forces_measure"] = {"%s_%s" % k: v for k, v in res.items()}
    d = lambda k, f: (res[(k, "lo")][f], res[(k, "hi")][f])  # noqa: E731
    lo, hi = d("center", "spread")
    check("向心力 ↑ → 星座更集中", hi < lo * 0.97, "星座离中心平均 %.0f → %.0f" % (lo, hi))
    lo, hi = d("repel", "spread")
    check("排斥力 ↑ → 范围更大", hi > lo * 1.03, "星座离中心平均 %.0f → %.0f" % (lo, hi))
    lo, hi = d("distance", "memberLen")
    check("连线长度 ↑ → 成员离星座中心更远", lo is not None and hi > lo * 1.05, "成员连线平均长度 %s → %s" % (lo and round(lo), hi and round(hi)))
    lo, hi = d("link", "memberLen")
    check("连线吸引力 ↑ → 成员更靠拢", lo is not None and hi < lo * 0.98, "成员连线平均长度 %s → %s" % (lo and round(lo), hi and round(hi)))
    worst = max(r["overlaps"] for r in res.values())
    check("四个力扫到两端，文字重叠始终为 0", worst == 0, "最多 %d 对" % worst)
    unset = [k for k, r in res.items() if r["settle"] is None]
    check("四个力扫到两端，布局都能静下来", not unset, "没静下来：%s" % unset)


@guarded
def t_panel():
    has = ev("!!document.getElementById('forces-btn') && !!document.getElementById('forces-panel')")
    check("面板：有齿轮按钮和面板", has, "")
    if not has:
        return

    def center(sel):
        return json.loads(ev("(function(){var e=document.querySelector(%s); if(!e) return 'null'; var r=e.getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2,r.left,r.width])})()" % json.dumps(sel)))

    gear = center("#forces-btn")
    click_xy(gear[0], gear[1])
    time.sleep(0.5)
    check("面板：点齿轮打开", ev("document.getElementById('forces-panel').classList.contains('open')"), "")
    presets = jev("return typeof PRESETS === 'object' ? PRESETS : null;")
    check("文件开头有 PRESETS（claude / gemini 两组）", presets and "claude" in presets and "gemini" in presets, json.dumps(presets))
    mode0 = ev("(document.querySelector('.fp-chip.on')||{}).getAttribute && document.querySelector('.fp-chip.on').getAttribute('data-mode')")
    REPORT["notes"]["panel_initial_mode"] = mode0
    for m in ("gemini", "claude"):
        c = center(".fp-chip[data-mode=%s]" % m)
        click_xy(c[0], c[1])
        time.sleep(1.3)
        got = jev("return window.__star3d.test.getForces();")
        want = presets[m] if presets else {}
        ok = all(abs(got[k] - want[k]) < 0.02 for k in want) if want else False
        check("预设芯片「%s」把四个值移到它那一组" % m, ok, "now %s, want %s" % (json.dumps(got), json.dumps(want)))
    sl = center("input[data-key=repel]")
    click_xy(sl[0] + 30, sl[1])
    time.sleep(0.5)
    mode = ev("document.querySelector('.fp-chip.on') && document.querySelector('.fp-chip.on').getAttribute('data-mode')")
    check("拖滑块自动切到「手动」", mode == "manual", str(mode))
    typed = ev("(function(){var el=document.getElementById('idea-input'); el.focus(); return document.activeElement.id})()")
    se.cmd_key("Escape")
    time.sleep(0.4)
    check("Esc 关闭面板", not ev("document.getElementById('forces-panel').classList.contains('open')"), "")
    ev("window.__star3d.test.setForces(%s)" % json.dumps(presets["claude"] if presets else {"center": 0.45, "repel": 0.5, "link": 0.5, "distance": 0.5}))
    settle(15, 0.8)


@guarded
def t_deepseek():
    ready = ev("(function(){var e=document.querySelector('.fp-chip[data-mode=deepseek]'); return !!e && !e.disabled})()")
    check("通过本机服务打开时「DeepSeek 重排」可点", ready, "")
    if not ready:
        return
    gear = json.loads(ev("(function(){var r=document.getElementById('forces-btn').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2])})()"))
    if not ev("document.getElementById('forces-panel').classList.contains('open')"):
        click_xy(gear[0], gear[1])
        time.sleep(0.4)
    before = jev("return window.__star3d.test.getForces();")
    p0 = positions()
    c = json.loads(ev("(function(){var r=document.querySelector('.fp-chip[data-mode=deepseek]').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2])})()"))
    click_xy(c[0], c[1])
    why = ""
    for _ in range(40):
        time.sleep(0.5)
        why = ev("document.querySelector('.fp-why').textContent")
        busy = ev("document.querySelector('.fp-chip[data-mode=deepseek]').textContent.indexOf('…') >= 0")
        if not busy and why and "想一想" not in why:
            break
    time.sleep(3.5)
    after = jev("return window.__star3d.test.getForces();")
    mode = ev("document.querySelector('.fp-chip.on') && document.querySelector('.fp-chip.on').getAttribute('data-mode')")
    p1 = positions()
    check("DeepSeek 重排：给出新的四个值并显示理由", mode == "deepseek" and why and "没连上" not in why, "理由「%s」，值 %s → %s" % (why, json.dumps(before), json.dumps(after)))
    mm, mx = mean_move(p0, p1)
    check("DeepSeek 重排：星座被牵到新位置（画面有变化）", mm > 10, "节点平均位移 %.0f px" % mm)
    t = settle(20, 0.8)
    check("重排之后能静下来、文字 0 重叠", t is not None and jev("return window.__star3d.test.overlaps();") == 0, "用时 %s" % t)
    shot("7-deepseek")
    se.cmd_key("Escape")


@guarded
def t_perf():
    gaps = jev("var g = window.__gaps.slice(); g.sort(function (a, b) { return a - b; }); return {n: g.length, p50: g[Math.floor(g.length * 0.5)], p95: g[Math.floor(g.length * 0.95)], max: g[g.length - 1]};")
    REPORT["notes"]["main_thread_gaps_ms"] = gaps
    # while the camera is being dragged
    ev("window.__gaps.length = 0")
    sx, sy = sw.empty_spot(ws)
    se.cmd_drag(sx, sy, sx - 200 if sx > 640 else sx + 200, sy + 30, 1200)
    time.sleep(0.3)
    g2 = jev("var g = window.__gaps.slice(); g.sort(function (a, b) { return a - b; }); return {n: g.length, p50: g[Math.floor(g.length * 0.5)], p95: g[Math.floor(g.length * 0.95)], max: g[g.length - 1]};")
    REPORT["notes"]["drag_gaps_ms"] = g2
    st = state()
    check("拖镜头时主线程不卡（8 ms 定时器的间隔 95 分位 < 50 ms）", g2 and g2["p95"] < 50, "p50 %.0f / p95 %.0f / 最大 %.0f ms；页面自报 fps=%s" % (g2["p50"], g2["p95"], g2["max"], st.get("fps")))
    errs = ev("window.__errs || []")
    check("整个测试过程控制台没有新报错", not errs, "; ".join(errs[:4]))


def main():
    global ws
    print("== 3D 检查：%s ==" % URL, flush=True)
    se.cmd_start()
    ws = se.connect()
    ws.call("Page.enable")
    ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": INIT_JS})
    only = sys.argv[2:]   # e.g. `verify3d.py spec cut perf` runs only those checks (after the load check)
    for fn in (t_load, t_settle_and_quiet, t_hover_quiet, t_orbit_wheel_pan, t_focus, t_drag_node, t_band, t_cut, t_type_idea, t_forces, t_panel, t_deepseek, t_perf):
        if only and fn is not t_load and fn.__name__[2:] not in only and fn is not t_settle_and_quiet:
            continue
        print("-- %s" % fn.__name__, flush=True)
        fn()
    ok = sum(1 for c in REPORT["checks"] if c["ok"])
    print("\n通过 %d / %d" % (ok, len(REPORT["checks"])))
    with open(os.path.join(OUT, "report-%s%s.json" % (TAG, "-part" if len(sys.argv) > 2 else "")), "w", encoding="utf-8") as f:
        json.dump(REPORT, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
