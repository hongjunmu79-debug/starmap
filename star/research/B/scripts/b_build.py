"""B 续上 — step 1: build the record index (every record has a birth time) and the query set.
Queries = the 35 idea moments from D0 + the 7 session openers that pasted a big block of context.
Rule for every query: it may only see records born strictly before it, and never messages from its own session.
Outputs (UTF-8 JSONL) in C:/Agent-Shared/home/star/research/B/: corpus.jsonl, queries.jsonl."""
import datetime, glob, io, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
SP = "C:/Users/User/AppData/Local/Temp/claude/ec29f026d20d029c/5fba9b10-424a-41e7-9e22-d60178a1cfc8/scratchpad"
OUT = "C:/Agent-Shared/home/star/research/B"
os.makedirs(OUT, exist_ok=True)
TZ8 = datetime.timezone(datetime.timedelta(hours=8))


def iso(dt):
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def from_local(s, end_of_day=False):
    s = str(s)
    if len(s) == 10:
        d = datetime.datetime.fromisoformat(s).replace(tzinfo=TZ8)
        return iso(d + datetime.timedelta(hours=23, minutes=59) if end_of_day else d)
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    return iso(d if d.tzinfo else d.replace(tzinfo=TZ8))


corpus = []
C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))
home_birth = from_local("2026-11-06", end_of_day=True)  # the 39 -> 19 merge happened on 11-06; end of day is the safe side
for it in C["items"]:
    corpus.append({"rid": "home:" + it["id"], "kind": "home-item", "birth": home_birth,
                   "text": "%s。%s %s" % (it.get("title", ""), it.get("summary", ""), it.get("why", ""))})
    for k, inc in enumerate(it.get("includes", [])):
        t = inc if isinstance(inc, str) else json.dumps(inc, ensure_ascii=False)
        corpus.append({"rid": "home:%s:inc%d" % (it["id"], k), "kind": "home-include", "birth": home_birth, "text": t, "parent": "home:" + it["id"]})
for f in glob.glob("C:/Agent-Shared/home/events-*.jsonl"):
    for l in open(f, encoding="utf-8"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("type") == "idea" and e.get("text") and e.get("text") != "测试":
            corpus.append({"rid": "pool:" + (e.get("idea_id") or e["id"]), "kind": "pool-idea", "birth": from_local(e["ts"]), "text": e["text"]})
DS = json.load(open(os.path.join(SP, "d0", "desktop_stores.json"), encoding="utf-8"))
for t in DS["horizon_todos"]:
    corpus.append({"rid": "hz:" + t["id"], "kind": "horizon-todo", "birth": from_local(t["ts"]), "text": t["text"]})
for t in DS["horizon_inbox"]:
    corpus.append({"rid": "hzin:" + t["id"], "kind": "horizon-inbox", "birth": from_local(t["ts"]), "text": t["text"]})
for p in DS["projects"]:
    if p["name"].startswith(".") or not p["oldest_file"]:
        continue
    corpus.append({"rid": "proj:desktop:" + p["name"], "kind": "project", "birth": from_local(p["oldest_file"], end_of_day=True),
                   "text": "%s %s" % (p["name"], p["head"][:300])})
for name in ("starmap", "xuanwu", "hermeshchange"):
    d = os.path.join("C:/Users/User", name)
    if os.path.isdir(d):
        head = ""
        for cand in ("README.md", "CLAUDE.md", "brief-proto.md"):
            if os.path.isfile(os.path.join(d, cand)):
                head = open(os.path.join(d, cand), encoding="utf-8", errors="replace").read(300)
                break
        oldest = min((os.path.getmtime(os.path.join(dp, fn)) for dp, _, fns in os.walk(d) for fn in fns[:50]), default=None)
        if oldest:
            corpus.append({"rid": "proj:laptop:" + name, "kind": "project", "birth": iso(datetime.datetime.fromtimestamp(oldest, TZ8)),
                           "text": "%s %s" % (name, head)})
for f in glob.glob("C:/Agent-Shared/home/handoff/*.md"):
    corpus.append({"rid": "handoff:" + os.path.basename(f), "kind": "handoff", "birth": iso(datetime.datetime.fromtimestamp(os.path.getmtime(f), TZ8)),
                   "text": open(f, encoding="utf-8", errors="replace").read(500)})
msgs = json.load(open(os.path.join(SP, "d0", "all_msgs.json"), encoding="utf-8"))
for m in msgs:
    if m["chars"] < 8 or re.match(r"^\s*(\[|What do you see|You've reached|I hit my usage|Try again)", m["text"]):
        continue
    corpus.append({"rid": "msg:" + m["id"], "kind": "message", "birth": m["ts"], "text": m["text"][:600], "session": m["src"] + ":" + m["session"]})

ideas = [json.loads(l) for l in open("C:/Agent-Shared/home/star/research/ideas_raw.jsonl", encoding="utf-8")]
byid = {m["id"]: m for m in msgs}
queries = []
for i in ideas:
    m = byid[i["id"]]
    queries.append({"qid": "q:" + i["id"], "kind": "idea-moment", "ts": m["ts"], "session": m["src"] + ":" + m["session"], "text": m["text"][:600], "cluster": i["cluster"]})
for mid in ("m144", "m228", "m251", "m275", "m309", "m347", "m367"):
    m = byid[mid]
    if not any(q["qid"] == "q:" + mid for q in queries):
        queries.append({"qid": "q:" + mid, "kind": "session-opener", "ts": m["ts"], "session": m["src"] + ":" + m["session"], "text": m["text"][:600]})
with open(os.path.join(OUT, "corpus.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for r in corpus:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open(os.path.join(OUT, "queries.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for q in queries:
        f.write(json.dumps(q, ensure_ascii=False) + "\n")
kinds = {}
for r in corpus:
    kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
print("corpus records:", len(corpus), kinds)
print("queries:", len(queries), "| idea moments:", sum(q["kind"] == "idea-moment" for q in queries), "| openers:", sum(q["kind"] == "session-opener" for q in queries))
T = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731 - mixed Z / +08:00 stamps
visible = [sum(1 for r in corpus if T(r["birth"]) < T(q["ts"]) and r.get("session") != q["session"]) for q in queries]
print("records visible per query (point-in-time): min %d, median %d, max %d" % (min(visible), sorted(visible)[len(visible) // 2], max(visible)))
