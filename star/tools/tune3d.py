"""Pick the 'Claude' preset for a 3D copy by metrics (the way the 2D one was found).

    python tune3d.py free|spec

Sweeps center x repel x distance (link fixed at 0.5), lets the layout settle, scores each combination on:
no text overlaps, every node inside the window (room for the input box), nearest pair not touching, the whole picture using
the window, constellations apart from each other, members clearly around their centre. Prints the best five and writes
shots/3d/tune-<tag>.json. Then a second pass varies link around the winner.
"""
import itertools
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

OUT = os.path.join(os.path.dirname(HERE), "shots", "3d")
os.makedirs(OUT, exist_ok=True)
ws = None


def ev(js):
    return se.evaluate(ws, js)


def positions():
    v = ev("""JSON.stringify((function(){ var S = window.__star3d, T = S.test, o = {};
        S.nodes.forEach(function (n) { var p = T.screenOf(n.id); if (p) o[n.id] = [p.x, p.y, p.depth]; }); return o; })())""")
    return json.loads(v)


def settle(max_s=14, tol=0.8):
    t0 = time.time()
    prev = positions()
    while time.time() - t0 < max_s:
        time.sleep(0.5)
        cur = positions()
        mx = max(math.hypot(cur[k][0] - prev[k][0], cur[k][1] - prev[k][1]) for k in cur if k in prev)
        if mx < tol:
            return round(time.time() - t0, 1)
        prev = cur
    return None


def measure():
    pos = positions()
    overlaps = ev("window.__star3d.test.overlaps()")
    ids = list(pos)
    pts = [pos[k] for k in ids]
    outside = sum(1 for p in pts if not (40 <= p[0] <= 1240 and 40 <= p[1] <= 640))
    near = min(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in itertools.combinations(pts, 2))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    fw = (max(xs) - min(xs)) / 1240.0
    fh = (max(ys) - min(ys)) / 600.0
    items = [pos[k] for k in ids if k.startswith("item:")]
    sep = min(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in itertools.combinations(items, 2)) if len(items) > 1 else 999
    rs = []
    for k in ids:
        if k.startswith("inc:"):
            c = pos.get("item:" + k.split(":")[1])
            if c:
                rs.append(math.hypot(pos[k][0] - c[0], pos[k][1] - c[1]))
    memberR = sum(rs) / len(rs) if rs else 0
    return {"overlaps": overlaps, "outside": outside, "nearest": round(near, 1), "fillW": round(fw, 2), "fillH": round(fh, 2),
            "itemSep": round(sep), "memberR": round(memberR), "depthSpan": round(max(p[2] for p in pts) - min(p[2] for p in pts))}


def score(m):
    s = 0.0
    s -= 1000 * m["overlaps"]
    s -= 60 * m["outside"]
    s -= 8 * max(0, 40 - m["nearest"])
    s -= 120 * max(0, 0.55 - m["fillW"]) + 120 * max(0, 0.55 - m["fillH"])
    s -= 200 * max(0, m["fillW"] - 0.95) + 200 * max(0, m["fillH"] - 0.95)
    s -= 0.5 * max(0, 200 - m["itemSep"])
    s -= 1.0 * max(0, 70 - m["memberR"]) + 1.0 * max(0, m["memberR"] - 190)
    return round(s, 1)


def run_combo(c, r, l, d):
    ev("window.__star3d.test.setForces(%s)" % json.dumps({"center": c, "repel": r, "link": l, "distance": d}))
    t = settle()
    m = measure()
    m["settle"] = t
    m["score"] = score(m) - (30 if t is None else 0)
    return m


def main():
    global ws
    se.cmd_start()
    ws = se.connect()
    ws.call("Page.navigate", {"url": URL})
    time.sleep(3)
    for _ in range(40):
        if ev("typeof window.__star3d === 'object'"):
            break
        time.sleep(0.5)
    settle(25)
    results = []
    grid = [[float(v) for v in a.split(",")] for a in sys.argv[2:5]] if len(sys.argv) >= 5 else [[0.30, 0.45, 0.60], [0.30, 0.50, 0.70], [0.30, 0.50, 0.70]]
    for c, r, d in itertools.product(*grid):
        m = run_combo(c, r, 0.5, d)
        m.update({"center": c, "repel": r, "link": 0.5, "distance": d})
        results.append(m)
        print("C%.2f R%.2f L0.50 D%.2f -> score %6.1f  %s" % (c, r, d, m["score"], {k: m[k] for k in ("overlaps", "outside", "nearest", "fillW", "fillH", "itemSep", "memberR", "settle")}), flush=True)
    results.sort(key=lambda m: -m["score"])
    best = results[0]
    for l in (0.35, 0.65):
        m = run_combo(best["center"], best["repel"], l, best["distance"])
        m.update({"center": best["center"], "repel": best["repel"], "link": l, "distance": best["distance"]})
        results.append(m)
        print("refine link %.2f -> score %6.1f" % (l, m["score"]), flush=True)
    results.sort(key=lambda m: -m["score"])
    print("\n最好的五组：")
    for m in results[:5]:
        print("  C%.2f R%.2f L%.2f D%.2f  score %.1f  %s" % (m["center"], m["repel"], m["link"], m["distance"], m["score"], {k: m[k] for k in ("nearest", "fillW", "fillH", "itemSep", "memberR")}))
    with open(os.path.join(OUT, "tune-%s.json" % TAG), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    b = results[0]
    ev("window.__star3d.test.setForces(%s)" % json.dumps({k: b[k] for k in ("center", "repel", "link", "distance")}))
    settle()
    print("\nPRESETS.claude =", json.dumps({k: b[k] for k in ("center", "repel", "link", "distance")}))


if __name__ == "__main__":
    main()
