"""Star map prototype server: serves star-proto.html and asks DeepSeek about ideas.

Runs on 127.0.0.1 only. The DeepSeek key stays in this process (read from the
DEEPSEEK_API_KEY environment variable, or the user's environment in the Windows
registry) and never reaches the page. Requests must be addressed to this
machine's loopback name and come from this page, so other websites cannot use
the key through the browser.

    python star_server.py            # http://127.0.0.1:8791/
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "star-proto.html")
PORT = int(os.environ.get("STAR_PORT", "8791"))
ALLOWED_HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
MAX_BODY = 64 * 1024
MAX_CALLS_PER_MIN = 30

ICONS = ["chip", "gear", "check", "chat", "spark", "people", "dice", "card", "cap", "flask",
         "doc", "book", "tool", "sliders", "db", "bulb", "flag", "question", "link"]
KINDS = ["extends", "supports", "contradicts", "same", "part_of"]
LENSES = ["可以变成", "第一步", "卡在", "像", "连着"]

POSS_RULES = (
    "lens 只能是「可以变成」「第一步」「卡在」「像」「连着」之一；text 不超过 18 个字，要具体，不要空话；"
    "「第一步」必须 30 分钟内能做完；「连着」要说出连着他已有的哪件事。每条再给一个 icon。"
    "icon 只能从这些里选：" + " ".join(ICONS) + "。"
)
RELATE_SYSTEM = (
    "你帮一个人整理灵感。他刚记下一条新想法，下面是他已有的概念（id｜文字｜所属星座）。请判断：\n"
    "1. item：这条想法最该归进哪个星座，给星座中心的 id（形如 item:xxx）；和哪个星座都不沾边就给 null。\n"
    "2. links：它和哪些已有概念有值得一想的逻辑关系，最多 3 条。每条给 to（概念 id，必须来自列表）、"
    "kind（extends 往下延伸 / supports 撑住 / contradicts 矛盾 / same 可能是一件事 / part_of 属于）、"
    "label（不超过 10 个字的问句，只提问，不下结论）。没有就给空数组，不要硬凑。\n"
    "3. possibilities：顺着这条想法往下长 3 到 4 条可能性。" + POSS_RULES + "\n"
    "4. icon：给这条新想法挑一个图标，只能从上面的列表里选。\n"
    "只输出 JSON，格式：{\"item\": ..., \"links\": [{\"to\": ..., \"kind\": ..., \"label\": ...}], "
    "\"possibilities\": [{\"lens\": ..., \"text\": ..., \"icon\": ...}], \"icon\": ...}"
)
EXPAND_SYSTEM = (
    "你帮一个人顺着一个概念往下想。下面是他已有的概念（id｜文字｜所属星座），以及他想往下想的那一个。"
    "请长出 3 到 4 条可能性。" + POSS_RULES + "\n"
    "只输出 JSON：{\"possibilities\": [{\"lens\": ..., \"text\": ..., \"icon\": ...}]}"
)
PAIR_SYSTEM = (
    "你帮一个人看两个概念之间有没有值得一想的逻辑关系。有就给一句不超过 10 个字的问句当线索"
    "（只提问，不下结论），并给 kind（extends / supports / contradicts / same / part_of）；"
    "只是字面相近或者牵强，就算没有。只输出 JSON：{\"related\": true 或 false, \"kind\": ..., \"label\": ...}"
)


LAYOUT_SYSTEM = (
    "你是一个图谱布局调参员。布局方式和 Obsidian 的图谱「Forces」面板一样，有四个 0 到 1 的旋钮：\n"
    "- center 向心力：把所有节点往场景中心拉，越大越集中，各星座之间靠得越近；\n"
    "- repel 排斥力：节点之间互相推开，越大越松散；\n"
    "- link 连线吸引力：相连节点之间的拉力，越大成员越紧贴自己的星座中心；\n"
    "- distance 连线长度：相连节点之间的静止距离，越大连线越长。\n"
    "我会给你这张图的概况、当前四个值和拥挤指标。请给出让整张图「第一眼清楚、不挤、不散、能装进窗口」的一组新值。\n"
    "还可以给每个星座中心一个目标位置 anchors：x、y（三维时再加 z）都在 -1 到 1 之间"
    "（-1 是窗口的左 / 上 / 近，1 是右 / 下 / 远），让星座在版面上分布得有章法"
    "（比如在跑的靠中间偏前，冻结的靠边靠后；成员多的星座给更大的空间）。不需要摆位置就给空数组。\n"
    "只输出 JSON：{\"center\":0到1,\"repel\":0到1,\"link\":0到1,\"distance\":0到1,"
    "\"anchors\":[{\"id\":\"item:xxx\",\"x\":数,\"y\":数,\"z\":数}],\"why\":\"不超过 30 个字的理由\"}"
)
STATIC_3D = {"/3d/free.html": "star3d-free.html", "/3d/spec.html": "star3d-spec.html", "/3d/mix.html": "star3d-mix.html"}


def unit(v, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v)) if v == v else default


def signed(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return max(-1.0, min(1.0, v)) if v == v else None


def layout(payload):
    cur = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    cons = [c for c in (stats.get("constellations") or [])[:12] if isinstance(c, dict) and str(c.get("id", "")).startswith("item:")]
    ids = {str(c["id"])[:64] for c in cons}
    brief = {
        "维度": "三维" if payload.get("mode") == "3d" else "二维",
        "窗口": [int(v) for v in (payload.get("viewport") or [1280, 720])[:2] if isinstance(v, (int, float))],
        "当前四个值": {k: round(unit(cur.get(k), 0.5), 2) for k in ("center", "repel", "link", "distance")},
        "节点数": int(stats.get("nodes") or 0), "连线数": int(stats.get("links") or 0), "想法数": int(stats.get("ideas") or 0),
        "星座": [{"id": str(c["id"])[:64], "名称": clip(c.get("title"), 20), "成员数": int(c.get("members") or 0), "想法数": int(c.get("ideas") or 0),
                  "状态": clip(c.get("status"), 12)} for c in cons],
        "拥挤指标": {"标签重叠数": int(stats.get("labelOverlaps") or 0), "整体是否装进窗口": bool(stats.get("fits")),
                     "最近两个节点的距离_像素": stats.get("nearestMin")},
    }
    res = ask(LAYOUT_SYSTEM, json.dumps(brief, ensure_ascii=False), max_tokens=500)
    anchors = []
    for a in (res.get("anchors") or [])[:12]:
        if not isinstance(a, dict) or str(a.get("id", "")) not in ids:
            continue
        x, y = signed(a.get("x")), signed(a.get("y"))
        if x is None or y is None:
            continue
        item = {"id": str(a["id"]), "x": x, "y": y}
        z = signed(a.get("z"))
        if z is not None and payload.get("mode") == "3d":
            item["z"] = z
        anchors.append(item)
    return {"center": unit(res.get("center"), unit(cur.get("center"), 0.5)), "repel": unit(res.get("repel"), unit(cur.get("repel"), 0.5)),
            "link": unit(res.get("link"), unit(cur.get("link"), 0.5)), "distance": unit(res.get("distance"), unit(cur.get("distance"), 0.5)),
            "anchors": anchors, "why": clip(res.get("why"), 30)}


def log(msg):
    sys.stderr.write("[star %s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key or os.name != "nt":
        return key
    try:  # a process started outside a fresh login may not have the user variable yet
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")[0]).strip()
    except OSError:
        return ""


KEY = load_key()
_calls = []
_calls_lock = threading.Lock()


def allow_call():
    now = time.time()
    with _calls_lock:
        while _calls and now - _calls[0] > 60:
            _calls.pop(0)
        if len(_calls) >= MAX_CALLS_PER_MIN:
            return False
        _calls.append(now)
        return True


def ask(system, user, max_tokens=700):
    if not KEY:
        raise RuntimeError("no key")
    if not allow_call():
        raise RuntimeError("too many calls")
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(DEEPSEEK_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=20) as r:
        out = json.loads(r.read().decode("utf-8"))
    return json.loads(out["choices"][0]["message"]["content"])


def clip(s, n):
    s = str(s or "").strip().replace("\n", " ")
    return s[:n]


def clean_nodes(raw):
    nodes = []
    for n in (raw or [])[:300]:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nodes.append({"id": clip(n["id"], 64), "text": clip(n.get("text"), 80), "group": clip(n.get("group"), 40)})
    return nodes


def listing(nodes):
    return "\n".join("%s｜%s｜%s" % (n["id"], n["text"], n["group"] or "（未归类）") for n in nodes)


def clean_poss(raw):
    out = []
    for p in (raw or [])[:4]:
        if not isinstance(p, dict) or p.get("lens") not in LENSES or not str(p.get("text") or "").strip():
            continue
        out.append({"lens": p["lens"], "text": clip(p["text"], 20),
                    "icon": p.get("icon") if p.get("icon") in ICONS else "spark"})
    return out


def relate(payload):
    idea = clip(payload.get("idea"), 200)
    nodes = clean_nodes(payload.get("nodes"))
    if not idea:
        raise ValueError("empty idea")
    res = ask(RELATE_SYSTEM, "已有概念：\n" + listing(nodes) + "\n\n新想法：" + idea)
    ids = {n["id"] for n in nodes}
    items = {i for i in ids if i.startswith("item:")}
    links, seen = [], set()
    for l in (res.get("links") or [])[:3]:
        if not isinstance(l, dict) or l.get("to") not in ids or l["to"] in seen:
            continue
        seen.add(l["to"])
        links.append({"to": l["to"], "kind": l.get("kind") if l.get("kind") in KINDS else "extends",
                      "label": clip(l.get("label"), 12)})
    return {"item": res.get("item") if res.get("item") in items else None,
            "links": [l for l in links if l["label"]],
            "possibilities": clean_poss(res.get("possibilities")),
            "icon": res.get("icon") if res.get("icon") in ICONS else "bulb"}


def expand(payload):
    text = clip(payload.get("text"), 200)
    nodes = clean_nodes(payload.get("nodes"))
    if not text:
        raise ValueError("empty text")
    res = ask(EXPAND_SYSTEM, "已有概念：\n" + listing(nodes) + "\n\n往下想这一个：" + text, max_tokens=500)
    return {"possibilities": clean_poss(res.get("possibilities"))}


def pair(payload):
    a, b = payload.get("a") or {}, payload.get("b") or {}
    ta, tb = clip(a.get("text"), 80), clip(b.get("text"), 80)
    if not ta or not tb:
        raise ValueError("need two texts")
    res = ask(PAIR_SYSTEM, "A：" + ta + "\nB：" + tb, max_tokens=120)
    related = res.get("related") is True and bool(clip(res.get("label"), 12))
    return {"related": related,
            "kind": res.get("kind") if res.get("kind") in KINDS else "extends",
            "label": clip(res.get("label"), 12) if related else ""}


ROUTES = {"/api/relate": relate, "/api/expand": expand, "/api/pair": pair, "/api/layout": layout}


class Handler(BaseHTTPRequestHandler):
    server_version = "StarProto/1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, data, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _trusted(self):
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc in ALLOWED_HOSTS

    def do_GET(self):
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        path = urlparse(self.path).path
        if path in ("/", "/star-proto.html"):
            with open(PAGE, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path in STATIC_3D:
            for base in (os.path.join(HERE, "..", "proto3d"), os.path.join(HERE, "proto3d")):
                f = os.path.join(base, STATIC_3D[path])
                if os.path.isfile(f):
                    with open(f, "rb") as fh:
                        return self._send(200, fh.read(), "text/html; charset=utf-8")
            return self._json({"error": "not built yet"}, 404)
        if path == "/api/health":
            return self._json({"ok": True, "model": bool(KEY), "name": MODEL})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        fn = ROUTES.get(urlparse(self.path).path)
        if not fn:
            return self._json({"error": "not found"}, 404)
        if "application/json" not in self.headers.get("Content-Type", ""):
            return self._json({"error": "json only"}, 415)
        size = int(self.headers.get("Content-Length") or 0)
        if size <= 0 or size > MAX_BODY:
            return self._json({"error": "bad size"}, 400)
        t0 = time.time()
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            out = fn(payload if isinstance(payload, dict) else {})
            log("%s ok %.1fs" % (self.path, time.time() - t0))
            return self._json(out)
        except (ValueError, KeyError) as exc:
            return self._json({"error": "bad request: %s" % exc}, 400)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            log("%s failed: %r" % (self.path, exc))
            return self._json({"error": "model unavailable"}, 502)
        except Exception as exc:
            log("%s error: %r" % (self.path, exc))
            return self._json({"error": "server error"}, 500)


class Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"   # on Windows a second copy must fail, not share the port
    daemon_threads = True


def main():
    httpd = Server(("127.0.0.1", PORT), Handler)
    log("serving http://127.0.0.1:%d/  model=%s key=%s" % (PORT, MODEL, "yes" if KEY else "MISSING"))
    httpd.serve_forever()


if __name__ == "__main__":
    main()
