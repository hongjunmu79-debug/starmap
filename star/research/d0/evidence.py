"""For every idea cluster: where else does it show up? (local char-bigram TF-IDF search)
Stores: home content.json (items + includes), event-file ideas, Horizon inbox/todos, brainstorm notes, handoff cards,
project folders on both machines, GLOBAL_INDEX session titles. Also: messages in OTHER sessions (before/after).
Prints a compact evidence sheet; nothing is written outside the scratchpad."""
import collections, glob, io, json, math, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
msgs = {r["id"]: r for r in json.load(open(os.path.join(D, "all_msgs.json"), encoding="utf-8"))}
labels = {}
for n in (1, 2, 3):
    for l in open(os.path.join(D, "labels-%d.jsonl" % n), encoding="utf-8"):
        if l.strip():
            x = json.loads(l)
            labels[x["id"]] = x
stores = []  # (kind, ref, ts, text)
C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))
for it in C["items"]:
    stores.append(("home-item", it["id"], C.get("updated", ""), "%s %s %s" % (it.get("title", ""), it.get("summary", ""), it.get("why", ""))))
    for inc in it.get("includes", []):
        t = inc if isinstance(inc, str) else json.dumps(inc, ensure_ascii=False)
        stores.append(("home-include", it["id"], C.get("updated", ""), t))
for f in glob.glob("C:/Agent-Shared/home/events-*.jsonl"):
    for l in open(f, encoding="utf-8"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("type") == "idea":
            stores.append(("pool-idea", os.path.basename(f), e.get("ts", ""), e.get("text", "")))
ds = json.load(open(os.path.join(D, "desktop_stores.json"), encoding="utf-8"))
for r in ds["horizon_inbox"]:
    stores.append(("horizon-inbox", r["id"], r["ts"], r["text"]))
for r in ds["horizon_todos"]:
    stores.append(("horizon-todo", r["id"], r["ts"], r["text"]))
for p in ds["projects"]:
    stores.append(("desktop-project", p["name"], p["oldest_file"] or "", p["name"] + " " + p["head"]))
for f in glob.glob("C:/Agent-Shared/knowledge/brainstorm/*.md"):
    try:
        head = open(f, encoding="utf-8", errors="replace").read(600)
    except OSError:
        continue
    stores.append(("brainstorm", os.path.basename(f), "", os.path.basename(f) + " " + head))
for f in glob.glob("C:/Agent-Shared/home/handoff/*.md"):
    stores.append(("handoff", os.path.basename(f), "", os.path.basename(f) + " " + open(f, encoding="utf-8", errors="replace").read(600)))
for l in open("C:/Agent-Shared/GLOBAL_INDEX.md", encoding="utf-8", errors="replace"):
    if l.startswith("|") and "---" not in l:
        stores.append(("session-title", "GLOBAL_INDEX", l.split("|")[1].strip() if l.count("|") > 2 else "", l))
for name in os.listdir("C:/Users/User"):
    if os.path.isdir(os.path.join("C:/Users/User", name)) and not name.startswith(".") and name not in ("AppData", "Documents", "Downloads", "Desktop", "Music", "Pictures", "Videos", "OneDrive", "Favorites", "Links", "Saved Games", "Searches", "Contacts", "3D Objects"):
        stores.append(("laptop-folder", name, "", name))

CJK = re.compile(r"[\u4e00-\u9fff]+")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9]+")
STOP = set("帮我 一下 看一下 我想 这个 一个 就是 然后 可以 现在 什么 怎么 能不 不能 我的 你的 他的 它的 没有 还是 如果 因为 所以 但是 应该 一些 东西 这样 那个 我们 你们".split())


def grams(t):
    g = []
    for seg in CJK.findall(t):
        g += [seg[i:i + 2] for i in range(len(seg) - 1) if seg[i:i + 2] not in STOP]
    g += [w.lower() for w in WORD.findall(t) if len(w) > 2]
    return g


docs = [s[3] for s in stores] + [m["text"] for m in msgs.values()]
df = collections.Counter()
for d in docs:
    df.update(set(grams(d)))
N = len(docs)


def vec(t):
    tf = collections.Counter(grams(t))
    v = {g: (1 + math.log(c)) * math.log((N + 1) / (df[g] + 0.5)) for g, c in tf.items()}
    n = math.sqrt(sum(x * x for x in v.values())) or 1
    return {g: x / n for g, x in v.items()}


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0) for g, x in a.items())


svec = [vec(s[3]) for s in stores]
mvec = {k: vec(m["text"]) for k, m in msgs.items()}
clusters = collections.OrderedDict()
for mid in sorted(labels):
    clusters.setdefault(labels[mid]["cluster"], []).append(mid)
for cl, mids in clusters.items():
    first = min(msgs[m]["ts"] for m in mids)
    sess = sorted(set(msgs[m]["sess"] for m in mids))
    print("\n### %s | first %s | sessions %s | %s" % (cl, first[:10], ",".join(sess), " / ".join(labels[m]["gist"] for m in mids)[:160]))
    q = {}
    for m in mids:
        for g, x in mvec[m].items():
            q[g] = q.get(g, 0) + x
    nq = math.sqrt(sum(x * x for x in q.values())) or 1
    q = {g: x / nq for g, x in q.items()}
    hits = sorted(((cos(q, svec[i]), i) for i in range(len(stores))), reverse=True)[:5]
    for sc, i in hits:
        if sc >= 0.06:
            k, ref, ts, t = stores[i]
            print("  store %.2f %-15s %-26s %s | %s" % (sc, k, str(ref)[:26], str(ts)[:10], re.sub(r"\s+", " ", t)[:90]))
    own = set(m for m in mids)
    mh = sorted(((cos(q, mvec[k]), k) for k in msgs if k not in own and msgs[k]["sess"] not in sess), reverse=True)[:5]
    for sc, k in mh:
        if sc >= 0.10:
            m = msgs[k]
            when = "after" if m["ts"] > first else "before"
            print("  msg   %.2f %-6s %s %s %s | %s" % (sc, when, k, m["sess"], m["ts"][:10], re.sub(r"\s+", " ", m["text"])[:90]))
    later_same = [k for k in msgs if msgs[k]["sess"] in sess and msgs[k]["ts"] > first and k not in own]
    print("  same-session later msgs: %d" % len(later_same))
