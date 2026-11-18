"""星图原型的「手和眼」：一个很小的固定工具，让评审员（比如 Gemini）能自己操作页面。

只驱动本机的 http://127.0.0.1:8791/，一个单独的 Chrome 窗口（用临时配置目录，不碰你自己的 Chrome）。
没有「打开别的网址」这个动作；只用 Python 标准库，没有第三方包。

    python star_eye.py start                      启动 Chrome 并打开星图（窗口 1280x720）
    python star_eye.py shot NAME                  截图存成 shots/gemini-run/NAME.jpg，打印路径
    python star_eye.py click X Y                  点击（坐标 = 截图上的像素）
    python star_eye.py drag X1 Y1 X2 Y2 [MS]      按住拖动，默认 700 毫秒
    python star_eye.py swipe X1 Y1 X2 Y2          快速一划（120 毫秒）
    python star_eye.py type TEXT                  往当前聚焦的输入框打字（先 click 输入框）
    python star_eye.py key NAME                   按键：Enter、Escape、Alt+v、Alt+m
    python star_eye.py wait MS                    等待
    python star_eye.py where NODE_ID              查某个节点现在的屏幕坐标（如 item:personal-os）
    python star_eye.py linkpoint A_ID B_ID [T]    查两个节点之间那条线上 T（默认 0.5）处的坐标
    python star_eye.py state                      打印页面的几个健康数字
    python star_eye.py stop                       关掉 Chrome
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\User\starmap\shots\gemini-run"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = int(os.environ.get("STAR_PORT", "9333"))   # a second controlled Chrome (own port, own profile) can run next to Gemini's
BASE = "http://127.0.0.1:8791/"
START_URL = os.environ.get("STAR_URL", BASE)   # e.g. http://127.0.0.1:8791/3d/free.html for a 3D copy
HEADLESS = os.environ.get("STAR_HEADLESS") == "1"   # my own scripts run without a window; Gemini's channel keeps the visible one
STATE = os.path.join(ROOT, "eye-state.json" if PORT == 9333 else "eye-state-%d.json" % PORT)
W, H = 1280, 720


class WS:
    """The smallest WebSocket client that Chrome's DevTools protocol needs."""

    def __init__(self, url):
        assert url.startswith("ws://127.0.0.1:%d/" % PORT), url
        path = url[len("ws://127.0.0.1:%d" % PORT):]
        self.sock = socket.create_connection(("127.0.0.1", PORT), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(("GET %s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, PORT, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("websocket handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake refused: " + head.split(b"\r\n")[0].decode(errors="replace"))
        self.buf = head.split(b"\r\n\r\n", 1)[1]
        self.id = 0

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise RuntimeError("connection closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _send_text(self, text):
        data = text.encode("utf-8")
        n = len(data)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv_message(self):
        message = b""
        while True:
            b0, b1 = self._read(2)
            fin, opcode, length = b0 & 0x80, b0 & 0x0F, b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(length)
            if opcode == 8:
                raise RuntimeError("browser closed the connection")
            if opcode in (1, 0, 2):
                message += payload
                if fin:
                    return message.decode("utf-8", errors="replace")

    def send_nowait(self, method, params=None):
        """Send without waiting for the reply, so a fast swipe is paced by the clock, not by the browser's round trip."""
        self.id += 1
        self.pending = getattr(self, "pending", set())
        self.pending.add(self.id)
        self._send_text(json.dumps({"id": self.id, "method": method, "params": params or {}}))

    def drain(self, timeout=10):
        end = time.time() + timeout
        while getattr(self, "pending", None) and time.time() < end:
            msg = json.loads(self._recv_message())
            self.pending.discard(msg.get("id"))

    def call(self, method, params=None, timeout=30):
        self.id += 1
        mid = self.id
        self._send_text(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self._recv_message())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s: %s" % (method, msg["error"].get("message")))
                return msg.get("result", {})
        raise RuntimeError("timeout waiting for " + method)


def jpeg_size(raw):
    i = 2
    while i + 9 < len(raw):
        if raw[i] != 0xFF:
            i += 1
            continue
        marker = raw[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return struct.unpack(">H", raw[i + 7:i + 9])[0], struct.unpack(">H", raw[i + 5:i + 7])[0]
        i += 2 + struct.unpack(">H", raw[i + 2:i + 4])[0]
    return 0, 0


def http_json(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def connect():
    for t in http_json("/json"):
        if t.get("type") == "page" and t.get("url", "").startswith(BASE):
            return WS(t["webSocketDebuggerUrl"])
    raise RuntimeError("星图页面没开着，先运行：python star_eye.py start")


def evaluate(ws, js):
    r = ws.call("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
    if r.get("exceptionDetails"):
        raise RuntimeError("页面里报错：" + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:300])
    return r.get("result", {}).get("value")


def mouse(ws, kind, x, y, buttons=0, click=0, wait=True):
    params = {"type": kind, "x": x, "y": y, "button": "left" if kind != "mouseMoved" or buttons else "none",
              "buttons": buttons, "clickCount": click}
    if wait:
        ws.call("Input.dispatchMouseEvent", params)
    else:
        ws.send_nowait("Input.dispatchMouseEvent", params)


def cmd_start():
    os.makedirs(ROOT, exist_ok=True)
    try:
        http_json("/json/version")
        print("Chrome 已经在运行")
    except Exception:
        profile = os.path.join(ROOT, "chrome-profile" if PORT == 9333 else "chrome-profile-%d" % PORT)
        args = [CHROME, "--remote-debugging-port=%d" % PORT, "--remote-allow-origins=*",
                "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--force-device-scale-factor=1",
                # a window that other windows cover must keep animating, or the page freezes
                "--disable-features=CalculateNativeWinOcclusion", "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding", "--disable-background-timer-throttling"]
        if HEADLESS:
            # no window at all: the page is always 'visible', frames always run, and --mute-audio keeps the test sounds off the speakers
            args += ["--headless=new", "--window-size=%d,%d" % (W, H), "--hide-scrollbars", "--mute-audio", START_URL]
        else:
            args += ["--window-size=%d,%d" % (W + 16, H + 140), "--window-position=%d,40" % (40 + (PORT - 9333) * 30), "--new-window", START_URL]
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        json.dump({"pid": proc.pid}, open(STATE, "w"))
        for _ in range(60):
            try:
                http_json("/json/version")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("Chrome 没有在 30 秒内启动")
    ws = None
    for _ in range(40):
        try:
            ws = connect()
            break
        except Exception:
            time.sleep(0.5)
    if ws is None:
        raise RuntimeError("找不到星图页面")
    for _ in range(40):
        if evaluate(ws, "(typeof window.__star === 'object' || typeof window.__star3d === 'object') && document.readyState === 'complete'"):
            break
        time.sleep(0.5)
    try:
        ws.call("Page.bringToFront")
    except Exception:
        pass
    # Make the page viewport exactly W x H CSS pixels (the window frame adds some): adjust the outer window to match.
    for _ in range(3):
        inner = evaluate(ws, "[innerWidth, innerHeight]")
        if inner == [W, H]:
            break
        try:
            win = ws.call("Browser.getWindowForTarget")
            b = win["bounds"]
            ws.call("Browser.setWindowBounds", {"windowId": win["windowId"],
                                                "bounds": {"windowState": "normal", "width": b["width"] + W - inner[0], "height": b["height"] + H - inner[1]}})
        except Exception:
            if not HEADLESS:
                raise
            break
        time.sleep(0.8)
    inner = evaluate(ws, "[innerWidth, innerHeight, devicePixelRatio]")
    print("已打开 %s ，视口 %dx%d，缩放比例 %g（截图像素和点击坐标一一对应）" % (START_URL, inner[0], inner[1], inner[2]))


def cmd_shot(name):
    safe = "".join(c for c in name if c.isalnum() or c in "-_")[:40] or "shot"
    ws = connect()
    r = ws.call("Page.captureScreenshot", {"format": "jpeg", "quality": 85})
    path = os.path.join(ROOT, safe + ".jpg")
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    raw = base64.b64decode(r["data"])
    w, h = jpeg_size(raw)
    print("截图已保存：%s （%dx%d 像素；图上的坐标就是点击用的坐标）" % (path, w, h))


def cmd_click(x, y):
    ws = connect()
    mouse(ws, "mouseMoved", x, y)
    mouse(ws, "mousePressed", x, y, buttons=1, click=1)
    mouse(ws, "mouseReleased", x, y, buttons=0, click=1)
    print("已点击 (%g, %g)" % (x, y))


def cmd_drag(x1, y1, x2, y2, ms):
    ws = connect()
    steps = max(4, int(ms / 16))
    mouse(ws, "mouseMoved", x1, y1, wait=False)
    mouse(ws, "mousePressed", x1, y1, buttons=1, click=1, wait=False)
    start = time.time()
    for i in range(1, steps + 1):
        x, y = x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps
        wait = start + ms / 1000 * i / steps - time.time()
        if wait > 0:
            time.sleep(wait)
        mouse(ws, "mouseMoved", x, y, buttons=1, wait=False)
    mouse(ws, "mouseReleased", x2, y2, buttons=0, click=1, wait=False)
    ws.drain()
    print("已拖动 (%g,%g) → (%g,%g)，用时 %d 毫秒" % (x1, y1, x2, y2, ms))


KEYS = {"Enter": ("Enter", "Enter", 13, "\r"), "Escape": ("Escape", "Escape", 27, ""), "Return": ("Enter", "Enter", 13, "\r")}


def cmd_key(name):
    ws = connect()
    mods = 0
    while name.lower().startswith(("alt+", "ctrl+")):
        if name.lower().startswith("alt+"):
            mods, name = mods | 1, name[4:]
        else:
            mods, name = mods | 2, name[5:]
    if name in KEYS:
        key, code, vk, text = KEYS[name]
    elif len(name) == 1:
        key, code, vk, text = name.lower(), "Key" + name.upper(), ord(name.upper()), ""
    else:
        raise RuntimeError("不认识的按键：" + name)
    base = {"modifiers": mods, "key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    ws.call("Input.dispatchKeyEvent", dict(base, type="keyDown", text=text if not mods else ""))
    ws.call("Input.dispatchKeyEvent", dict(base, type="keyUp"))
    print("已按键 " + ("Ctrl+" if mods & 2 else "") + ("Alt+" if mods & 1 else "") + name)


TEST = "(window.__star3d || window.__star).test"


def cmd_where(node_id):
    ws = connect()
    v = evaluate(ws, "(function(){var p=%s.screenOf(%s);return p?[Math.round(p.x),Math.round(p.y)]:null})()" % (TEST, json.dumps(node_id)))
    print("%s 现在在屏幕坐标 %s" % (node_id, v) if v else "没有这个节点：" + node_id)


def cmd_linkpoint(a, b, t):
    ws = connect()
    v = evaluate(ws, "(function(){var p=%s.screenOfLink(%s,%s,%g);return p?[Math.round(p.x),Math.round(p.y)]:null})()" % (TEST, json.dumps(a), json.dumps(b), t))
    print("线 %s—%s 上 %g 处的坐标 %s" % (a, b, t, v) if v else "这两个节点之间现在没有线")


def cmd_state():
    ws = connect()
    v = evaluate(ws, """(function(){
      var T = %s, is3 = !!window.__star3d, S = is3 ? __star3d : __star;
      var o = {viewport:[innerWidth,innerHeight], dpr:devicePixelRatio, sound: (typeof audioCtx !== 'undefined' && audioCtx) ? audioCtx.state : 'none'};
      if (is3) { var st = S.state(); o.view = '3d'; o.nodes = st.nodes; o.links = st.links; o.labels = st.labels; o.focus = st.focus; o.forces = st.forces; o.fps = Math.round(st.fps || 0); o.labelOverlaps = T.overlaps(); }
      else { o.view = viewMode; o.zoom = +cam.zoom.toFixed(2); o.nodes = S.nodes.length; o.links = S.links.length; o.labels = T.labelsShown().length; o.labelOverlaps = T.labelOverlaps(); o.ballOverlaps = T.ballOverlaps();
             o.pointer = S.state().pointer; o.focus = (focus && focus.id) || null; o.model = LLM.ready; if (T.getForces) o.forces = T.getForces(); }
      return JSON.stringify(o); })()""" % TEST)
    print(v)


def cmd_forces(c, r, l, d, animate):
    ws = connect()
    v = evaluate(ws, "JSON.stringify((function(){%s.setForces({center:%g,repel:%g,link:%g,distance:%g}, %s); return %s.getForces();})())" % (TEST, c, r, l, d, 'true' if animate else 'false', TEST))
    print("forces set to", v)


def cmd_metrics():
    ws = connect()
    v = evaluate(ws, """(function(){
      var T = %s;
      if (T.metrics) return JSON.stringify(T.metrics());
      var S = window.__star3d, pts = S.nodes.map(function(n){ var p = T.screenOf(n.id); return p ? [p.x, p.y] : null; }).filter(Boolean), nm = Infinity;
      for (var i = 0; i < pts.length; i++) for (var j = i + 1; j < pts.length; j++) nm = Math.min(nm, Math.hypot(pts[i][0]-pts[j][0], pts[i][1]-pts[j][1]));
      var xs = pts.map(function(p){return p[0]}), ys = pts.map(function(p){return p[1]});
      return JSON.stringify({nearestMin: Math.round(nm), labelOverlaps: T.overlaps(), bounds: {l: Math.round(Math.min.apply(0,xs)), t: Math.round(Math.min.apply(0,ys)), r: Math.round(Math.max.apply(0,xs)), b: Math.round(Math.max.apply(0,ys))}, labels: T.labelsShown().length});
    })()""" % TEST)
    print(v)


def cmd_stop():
    try:
        pid = json.load(open(STATE))["pid"]
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    except Exception:
        pass
    print("已关闭")


def main(argv):
    if not argv:
        print(__doc__)
        return
    c, a = argv[0], argv[1:]
    if c == "start":
        cmd_start()
    elif c == "shot":
        cmd_shot(a[0] if a else "shot")
    elif c == "click":
        cmd_click(float(a[0]), float(a[1]))
    elif c == "drag":
        cmd_drag(float(a[0]), float(a[1]), float(a[2]), float(a[3]), int(a[4]) if len(a) > 4 else 700)
    elif c == "swipe":
        cmd_drag(float(a[0]), float(a[1]), float(a[2]), float(a[3]), 120)
    elif c == "type":
        connect().call("Input.insertText", {"text": " ".join(a)})
        print("已输入：" + " ".join(a))
    elif c == "key":
        cmd_key(a[0])
    elif c == "wait":
        time.sleep(min(30000, int(a[0])) / 1000)
        print("已等待 %s 毫秒" % a[0])
    elif c == "where":
        cmd_where(a[0])
    elif c == "linkpoint":
        cmd_linkpoint(a[0], a[1], float(a[2]) if len(a) > 2 else 0.5)
    elif c == "state":
        cmd_state()
    elif c == "forces":
        cmd_forces(float(a[0]), float(a[1]), float(a[2]), float(a[3]), len(a) > 4 and a[4] in ("1", "true", "animate"))
    elif c == "metrics":
        cmd_metrics()
    elif c == "stop":
        cmd_stop()
    else:
        print("不认识的命令：%s\n%s" % (c, __doc__))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as exc:
        print("出错：%s" % exc)
        sys.exit(1)
