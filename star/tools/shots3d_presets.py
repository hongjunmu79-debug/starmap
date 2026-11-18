"""Overview screenshots of both 3D copies at both presets (Claude's and Gemini's), plus a 2x2 contact sheet.

    python shots3d_presets.py     -> shots/3d/{free,spec}-preset-{claude,gemini}.png and shots/3d/presets.jpg
"""
import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("STAR_PORT", "9335")
os.environ.setdefault("STAR_HEADLESS", "1")
os.environ["STAR_URL"] = "http://127.0.0.1:8791/3d/free.html"
import star_eye as se  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "shots", "3d")
se.cmd_start()
ws = se.connect()
ev = lambda js: se.evaluate(ws, js)


def settle(max_s=14):
    t0 = time.time()
    prev = None
    while time.time() - t0 < max_s:
        cur = ev("JSON.stringify(window.__star3d.nodes.map(function (n) { var p = window.__star3d.test.screenOf(n.id); return p ? [p.x, p.y] : [0, 0]; }))")
        if prev is not None and cur == prev:
            return
        prev = cur
        time.sleep(0.7)


files = {}
for tag in ("free", "spec"):
    ws.call("Page.navigate", {"url": "http://127.0.0.1:8791/3d/%s.html" % tag})
    time.sleep(3.5)
    presets = json.loads(ev("JSON.stringify(PRESETS)"))
    for name in ("gemini", "claude"):
        ev("window.__star3d.test.setForces(%s)" % json.dumps(presets[name]))
        time.sleep(1.0)
        settle()
        time.sleep(0.5)
        r = ws.call("Page.captureScreenshot", {"format": "png"})
        p = os.path.join(OUT, "%s-preset-%s.png" % (tag, name))
        open(p, "wb").write(base64.b64decode(r["data"]))
        files[(tag, name)] = (p, presets[name])
        print(tag, name, presets[name], flush=True)
se.cmd_stop()

font_path = r"C:\Windows\Fonts\msyh.ttc"
font = ImageFont.truetype(font_path, 18) if os.path.exists(font_path) else ImageFont.load_default()
W, H, PAD, HEAD = 640, 360, 8, 30
sheet = Image.new("RGB", (PAD + 2 * (W + PAD), 2 * (H + HEAD) + PAD), (14, 16, 26))
d = ImageDraw.Draw(sheet)
titles = {"free": "A · Gemini 自由版", "spec": "B · 脚本版"}
names = {"gemini": "Gemini 那一组", "claude": "Claude 那一组"}
for r, tag in enumerate(("free", "spec")):
    for c, name in enumerate(("gemini", "claude")):
        p, v = files[(tag, name)]
        x0, y0 = PAD + c * (W + PAD), r * (H + HEAD)
        d.text((x0 + 4, y0 + 4), "%s · %s  向心 %.2f 排斥 %.2f 吸引 %.2f 长度 %.2f" % (titles[tag], names[name], v["center"], v["repel"], v["link"], v["distance"]), fill=(225, 232, 250), font=font)
        sheet.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (x0, y0 + HEAD))
out = os.path.join(OUT, "presets.jpg")
sheet.save(out, quality=88)
print(out, sheet.size, os.path.getsize(out) // 1024, "KB")
