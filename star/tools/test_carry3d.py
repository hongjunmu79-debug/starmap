"""Drag a constellation centre on a 3D copy and check that its members keep their formation (world offsets).
    python test_carry3d.py mix|free|spec"""
import json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
tag = sys.argv[1] if len(sys.argv) > 1 else "mix"
os.environ.setdefault("STAR_PORT", "9335")
os.environ.setdefault("STAR_HEADLESS", "1")
os.environ["STAR_URL"] = "http://127.0.0.1:8791/3d/%s.html" % tag
import star_eye as se
se.cmd_start()
ws = se.connect()
ev = lambda js: se.evaluate(ws, js)
ws.call("Page.navigate", {"url": os.environ["STAR_URL"]})
time.sleep(4)
SNAP = """JSON.stringify((function(){ var S = window.__star3d, it = S.nodes.find(function(n){return n.id==='item:school'}), o = {item: [Math.round(it.x), Math.round(it.y), Math.round(it.z)], kids: {}};
  S.nodes.filter(function(n){return n.id !== it.id && (n.parentId === 'item:school' || (n.constellationId === 'school' && n.kind !== 'center'))}).forEach(function(n){ o.kids[n.id] = [Math.round(n.x - it.x), Math.round(n.y - it.y), Math.round(n.z - it.z)]; });
  return o; })())"""
snap = lambda: json.loads(ev(SNAP))
s0 = snap()
print(tag, 'children:', len(s0['kids']))
p = json.loads(ev("JSON.stringify(window.__star3d.test.screenOf('item:school'))")); x0, y0 = p['x'], p['y']
ws.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x0, "y": y0, "button": "none", "buttons": 0, "clickCount": 0})
ws.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x0, "y": y0, "button": "left", "buttons": 1, "clickCount": 1})
worst = 0
for i in range(1, 31):
    ws.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x0 + 220 * i / 30, "y": y0 - 60 * i / 30, "button": "left", "buttons": 1, "clickCount": 0})
    time.sleep(0.02)
    if i % 10 == 0:
        s = snap()
        worst = max(worst, max(math.dist(s['kids'][k], s0['kids'][k]) for k in s0['kids']))
ws.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x0 + 220, "y": y0 - 60, "button": "left", "buttons": 0, "clickCount": 1})
print('during the drag: members changed their offset by at most %.1f world units' % worst)
for t, wait in ((0.3, 0.3), (1.0, 0.7), (3.0, 2.0)):
    time.sleep(wait)
    s = snap()
    print('  t+%.1fs after release: formation change %.0f' % (t, max(math.dist(s['kids'][k], s0['kids'][k]) for k in s0['kids'])))
se.cmd_stop()
