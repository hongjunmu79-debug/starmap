"""Watches an inbox folder and runs "action scripts" written by a reviewer (e.g. Gemini) on the star-map page.

Why: Gemini's headless mode cannot ask for permission to run commands, but it can write and read files. So the reviewer
writes a small script into inbox/NAME.txt, this watcher runs it with the fixed verbs below (nothing else), and the results
and screenshots come back as files. It only drives http://127.0.0.1:8791/ in a separate Chrome (see star_eye.py).

A script is plain text, one action per line ('#' starts a comment):

  start                              start Chrome and open the page (viewport 1280x720, 1 px = 1 click coordinate)
  shot NAME                          screenshot -> gemini-run/NAME.jpg
  state                              a few health numbers of the page
  where NODE_ID                      the node's current screen position
  clickid NODE_ID                    click a node (e.g. item:personal-os)
  clickempty                         click an empty spot of the sky
  dragid NODE_ID DX DY [MS]          press on a node, drag it by (DX,DY) pixels, release (default 700 ms)
  pullline A_ID B_ID DY [MS]         press the middle of the line A-B and pull it DY pixels down, release (rubber band)
  cutline A_ID B_ID                  one quick swipe across the line A-B (slice it)
  swipe X1 Y1 X2 Y2                  one quick swipe, 120 ms
  drag X1 Y1 X2 Y2 [MS]              press, drag, release
  click X Y
  typeidea TEXT                      click the capture box, type TEXT, press Enter
  key NAME                           Enter, Escape, Alt+v (look toggle), Alt+m (mute), z with Ctrl is 'Ctrl+z'
  wait MS                            at most 30000
  stop                               close Chrome

Results: outbox/NAME.out.txt (one line per action, ends with DONE) and the marker outbox/NAME.done.
Stop the watcher by creating inbox/STOP. It also stops itself after 25 idle minutes.
"""
import contextlib
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import star_eye as se  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = se.ROOT
INBOX = os.path.join(ROOT, "inbox")
OUTBOX = os.path.join(ROOT, "outbox")
DONE_DIR = os.path.join(INBOX, "done")
MAX_LINES = 80
IDLE_LIMIT = 25 * 60
PLAIN = {"start", "shot", "state", "where", "click", "drag", "swipe", "key", "wait", "stop", "forces", "metrics"}
HIGH = {"clickid", "clickempty", "dragid", "pullline", "cutline", "typeidea"}


def ev(ws, js):
    return se.evaluate(ws, js)


def node_pos(ws, node_id):
    v = ev(ws, "(function(){var p=%s.screenOf(%s);return p?JSON.stringify([p.x,p.y]):null})()" % (se.TEST, json.dumps(node_id)))
    if not v:
        raise RuntimeError("没有这个节点：" + node_id)
    return json.loads(v)


def line_pos(ws, a, b):
    v = ev(ws, "(function(){var p=%s.screenOfLink(%s,%s,0.5);return p?JSON.stringify([p.x,p.y]):null})()" % (se.TEST, json.dumps(a), json.dumps(b)))
    if not v:
        raise RuntimeError("这两个节点之间现在没有线：%s — %s" % (a, b))
    return json.loads(v)


def empty_spot(ws):
    # a point at least 80 px away from every node centre (works on 2D and 3D pages)
    v = ev(ws, """(function(){
      var T = %s, S = window.__star3d || window.__star;
      var pts = S.nodes.map(function(n){ var p = T.screenOf(n.id); return p ? [p.x, p.y] : null; }).filter(Boolean);
      var cands = [[1180,330],[90,330],[640,60],[1180,120],[90,520],[1000,600],[300,620],[640,330],[560,600],[800,60],[1180,560],[90,150]];
      for (var i = 0; i < cands.length; i++) {
        var ok = pts.every(function(p){ return Math.hypot(p[0]-cands[i][0], p[1]-cands[i][1]) >= 80; });
        if (ok) return JSON.stringify(cands[i]); }
      return JSON.stringify([1180,330]); })()""" % se.TEST)
    return json.loads(v)


def do_high(verb, args):
    ws = se.connect()
    if verb == "clickid":
        x, y = node_pos(ws, args[0])
        se.mouse(ws, "mouseMoved", x, y)
        se.mouse(ws, "mousePressed", x, y, buttons=1, click=1)
        se.mouse(ws, "mouseReleased", x, y, buttons=0, click=1)
        return "已点击 %s (%d,%d)" % (args[0], x, y)
    if verb == "clickempty":
        x, y = empty_spot(ws)
        se.mouse(ws, "mouseMoved", x, y)
        se.mouse(ws, "mousePressed", x, y, buttons=1, click=1)
        se.mouse(ws, "mouseReleased", x, y, buttons=0, click=1)
        return "已点击空白处 (%d,%d)" % (x, y)
    if verb == "dragid":
        x, y = node_pos(ws, args[0])
        dx, dy = float(args[1]), float(args[2])
        ms = int(args[3]) if len(args) > 3 else 700
        se.cmd_drag(x, y, x + dx, y + dy, ms)
        time.sleep(0.6)
        nx, ny = node_pos(ws, args[0])
        return "拖动 %s：从 (%d,%d) 拖 (%g,%g)，松手后它在 (%d,%d)" % (args[0], x, y, dx, dy, nx, ny)
    if verb == "pullline":
        x, y = line_pos(ws, args[0], args[1])
        dy = float(args[2])
        ms = int(args[3]) if len(args) > 3 else 900
        se.cmd_drag(x, y, x, y + dy, ms)
        time.sleep(0.8)
        return "已按住线中间 (%d,%d) 往下拉 %g 像素再松手" % (x, y, dy)
    if verb == "cutline":
        x, y = line_pos(ws, args[0], args[1])
        links0 = ev(ws, "__star.links.length")
        se.cmd_drag(x, y - 90, x, y + 90, 140)
        time.sleep(0.7)
        links1 = ev(ws, "__star.links.length")
        return "已在线 %s—%s 上一划：线的总数 %d → %d（%s）" % (args[0], args[1], links0, links1, "切断了" if links1 < links0 else "没有切断")
    if verb == "typeidea":
        text = " ".join(args)[:120]
        box = json.loads(ev(ws, "(function(){var r=document.getElementById('idea-input').getBoundingClientRect();return JSON.stringify([r.left+r.width/2,r.top+r.height/2])})()"))
        se.mouse(ws, "mouseMoved", box[0], box[1])
        se.mouse(ws, "mousePressed", box[0], box[1], buttons=1, click=1)
        se.mouse(ws, "mouseReleased", box[0], box[1], buttons=0, click=1)
        ws.call("Input.insertText", {"text": text})
        se.cmd_key("Enter")
        return "已在输入框打字并回车：" + text
    raise RuntimeError("未实现：" + verb)


def run_line(line):
    parts = line.split()
    verb, args = parts[0], parts[1:]
    if verb in HIGH:
        return do_high(verb, args)
    if verb in PLAIN:
        if verb == "wait":
            args = [str(min(30000, int(args[0])))]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            se.main([verb] + args)
        return buf.getvalue().strip()
    raise RuntimeError("不认识的动作：" + verb)


def run_script(path, name):
    out_path = os.path.join(OUTBOX, name + ".out.txt")
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        lines = [l.strip() for l in f.read().splitlines()]
    lines = [l for l in lines if l and not l.startswith("#")][:MAX_LINES]
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("# 脚本 %s，共 %d 个动作\n" % (name, len(lines)))
        out.flush()
        for i, line in enumerate(lines, 1):
            t0 = time.time()
            try:
                res = run_line(line)
            except Exception as exc:  # one bad action must not stop the rest
                res = "出错：%s" % exc
            out.write("[%d] %s\n    -> %s  (%.1fs)\n" % (i, line, res, time.time() - t0))
            out.flush()
        out.write("DONE\n")
    open(os.path.join(OUTBOX, name + ".done"), "w").write("done\n")


def main():
    for d in (INBOX, OUTBOX, DONE_DIR):
        os.makedirs(d, exist_ok=True)
    stop_file = os.path.join(INBOX, "STOP")
    if os.path.exists(stop_file):
        os.remove(stop_file)
    print("watching", INBOX, flush=True)
    last_activity = time.time()
    while True:
        if os.path.exists(stop_file):
            print("STOP file found, leaving", flush=True)
            break
        if time.time() - last_activity > IDLE_LIMIT:
            print("idle for too long, leaving", flush=True)
            break
        names = sorted(n for n in os.listdir(INBOX) if n.endswith(".txt"))
        for n in names:
            p = os.path.join(INBOX, n)
            if time.time() - os.path.getmtime(p) < 0.8:   # still being written
                continue
            name = n[:-4]
            print("running", n, flush=True)
            run_script(p, name)
            os.replace(p, os.path.join(DONE_DIR, n))
            last_activity = time.time()
        time.sleep(0.4)
    try:
        se.cmd_stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()
