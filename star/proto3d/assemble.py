"""Join the parts Gemini wrote into one single-file page, then syntax-check the script.

    python assemble.py free      parts in free/parts/  ->  star3d-free.html   (served as /3d/free.html)
    python assemble.py spec      parts in spec/parts/  ->  star3d-spec.html   (served as /3d/spec.html)

Order: parts/00-head.html (ends with an opening <script>), then ref/data.js, ref/audio.js, ref/forces-panel.js (inlined as is),
then every parts/*.js in file-name order, then parts/99-tail.html.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
tag = sys.argv[1] if len(sys.argv) > 1 else "free"
base = os.path.join(HERE, tag)
parts = os.path.join(base, "parts")
out_path = os.path.join(HERE, "star3d-%s.html" % tag)


def read(path):
    with io.open(path, encoding="utf-8-sig", newline=None) as f:
        return f.read().replace("\r\n", "\n")


names = sorted(os.listdir(parts))
js_names = [n for n in names if re.match(r"^\d\d.*\.js$", n)]
if not os.path.isfile(os.path.join(parts, "00-head.html")):
    sys.exit("缺 parts/00-head.html")
head = read(os.path.join(parts, "00-head.html")).rstrip()
fixes = []
if not re.search(r"<script[^>]*>\s*$", head):
    head += "\n<script>"
    fixes.append("00-head.html 末尾没有 <script>，已补上")
tail_path = os.path.join(parts, "99-tail.html")
tail = read(tail_path).strip() if os.path.isfile(tail_path) else ""
if "</script>" not in tail:
    tail = "</script>\n" + tail
    fixes.append("99-tail.html 缺 </script>，已补上")
if "</html>" not in tail:
    tail = tail + ("\n</body>\n</html>" if "</body>" not in tail else "\n</html>")
    fixes.append("99-tail.html 缺 </html>，已补上")

refs = ["data.js", "audio.js", "forces-panel.js"]
chunks = []
for r in refs:
    chunks.append("/* ===== ref/%s (inlined as is) ===== */\n%s" % (r, read(os.path.join(base, "ref", r))))
hint_path = os.path.join(base, "hint.txt")
if os.path.isfile(hint_path):
    import json
    hint = read(hint_path).strip()
    chunks.append("/* ===== assembly override: the 2D hint line mentions tools that this 3D page does not have ===== */\nDATA.hint = %s;" % json.dumps(hint, ensure_ascii=False))
report = []
for n in js_names:
    text = read(os.path.join(parts, n))
    if re.search(r"</?script", text, re.I):
        text = re.sub(r"</?script[^>]*>", "", text, flags=re.I)
        fixes.append("%s 里有 <script> 标签，已删掉" % n)
    chunks.append("/* ===== parts/%s ===== */\n%s" % (n, text))
    report.append((n, text.count("\n") + 1, len(text.encode("utf-8"))))
js = "\n".join(chunks)

page = head + "\n" + js + "\n" + tail + "\n"
with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(page)

print("拼好了：%s（%d KB，%d 行）" % (out_path, len(page.encode("utf-8")) // 1024, page.count("\n")))
print("部件：00-head.html %d 行" % (head.count("\n") + 1))
for n, lines, size in report:
    print("      %-24s %4d 行 %6d 字节" % (n, lines, size))
for f in fixes:
    print("自动修正：" + f)

# syntax check of the whole script with node
tmp = os.path.join(tempfile.gettempdir(), "star3d-%s-check.js" % tag)
with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
    f.write(js)
r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
if r.returncode == 0:
    print("node --check：通过")
else:
    print("node --check：失败\n" + (r.stderr or r.stdout)[:1500])
    # map the error line back to a part
    m = re.search(r":(\d+)\n", r.stderr or "")
    if m:
        ln = int(m.group(1))
        pos = 0
        for i, line in enumerate(js.split("\n"), 1):
            if i == ln:
                break
        marks = [(i, l) for i, l in enumerate(js.split("\n"), 1) if l.startswith("/* ===== ")]
        where = [l for i, l in marks if i <= ln]
        print("出错的位置在：" + (where[-1] if where else "?"))
sys.exit(0 if r.returncode == 0 else 1)
