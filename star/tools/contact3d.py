"""Builds one contact sheet that puts the two 3D copies side by side (rows: A free, B spec; columns: overview, focus, rotated).

    python contact3d.py            -> shots/3d/compare.jpg
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(r"C:\Users\User\starmap", "shots", "3d")
cols = [("1-overview", "总览"), ("2-focus", "单击聚焦"), ("3-rotated", "拖动旋转后")]
rows = [("free", "A · Gemini 自由版"), ("spec", "B · 脚本版（按 Claude 规格）"), ("mix", "融合版 · A 的手感 + B 的排布")]
W, H, PAD, HEAD = 640, 360, 8, 34
font_path = r"C:\Windows\Fonts\msyh.ttc"
font = ImageFont.truetype(font_path, 18) if os.path.exists(font_path) else ImageFont.load_default()
sheet = Image.new("RGB", (PAD + len(cols) * (W + PAD), HEAD + len(rows) * (H + HEAD) + PAD), (14, 16, 26))
d = ImageDraw.Draw(sheet)
for r, (tag, title) in enumerate(rows):
    y0 = HEAD * 0 + r * (H + HEAD)
    d.text((PAD + 4, y0 + 6), title, fill=(230, 236, 250), font=font)
    for c, (name, label) in enumerate(cols):
        p = os.path.join(ROOT, "%s-%s.png" % (tag, name))
        x0 = PAD + c * (W + PAD)
        if os.path.exists(p):
            im = Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS)
            sheet.paste(im, (x0, y0 + HEAD))
            d.text((x0 + W - 110, y0 + 6), label, fill=(150, 165, 200), font=font)
        else:
            d.rectangle((x0, y0 + HEAD, x0 + W, y0 + HEAD + H), outline=(80, 90, 120))
            d.text((x0 + 12, y0 + HEAD + 12), "（没有 %s-%s）" % (tag, name), fill=(150, 165, 200), font=font)
out = os.path.join(ROOT, "compare.jpg")
sheet.save(out, quality=88)
print(out, sheet.size, os.path.getsize(out) // 1024, "KB")
