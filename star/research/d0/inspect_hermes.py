"""Structure-only look at Hermes director transcripts (WSL python3; prints no message content)."""
import collections, glob, json, os, sqlite3, time

HH = "/mnt/d/Claude Code 工作区/agents/hermes-agents/director/hermes-home"
sd = os.path.join(HH, "sessions")
jl = sorted(glob.glob(os.path.join(sd, "*.jsonl")), key=os.path.getmtime)
print("jsonl transcripts:", len(jl))
keys = collections.Counter()
roles = collections.Counter()
recent = 0
rows = []
for f in jl:
    n_user = 0
    first = last = None
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            keys.update(d.keys())
            r = d.get("role") or (d.get("message") or {}).get("role")
            roles[r] += 1
            if r == "user":
                n_user += 1
            ts = d.get("timestamp") or d.get("ts") or d.get("created_at")
            if ts:
                first = first or str(ts)
                last = str(ts)
    mt = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(f)))
    rows.append((mt, n_user, (first or "")[:10], (last or "")[:10], os.path.basename(f)[:28]))
    if mt >= "2026-10-12":
        recent += 1
print("line keys:", [k for k, _ in keys.most_common(20)])
print("roles:", dict(roles))
print("transcripts modified since 2026-10-12:", recent)
for r in rows[-8:]:
    print("  mtime %s | user msgs %3d | ts %s..%s | %s" % r)

print("=== sessions.json index (keys only)")
idx = json.load(open(os.path.join(sd, "sessions.json"), encoding="utf-8"))
for k, v in idx.items():
    if k.startswith("_"):
        continue
    kind = k.split(":")[2] if k.count(":") >= 2 else k
    vk = sorted(v.keys())[:12] if isinstance(v, dict) else type(v).__name__
    print("  %s -> %s" % (kind, vk))

print("=== state.db via immutable=1 (read-only snapshot of the main file; WAL not included)")
try:
    con = sqlite3.connect("file:%s?mode=ro&immutable=1" % os.path.join(HH, "state.db"), uri=True)
    tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    print("tables:", tabs[:20])
    for t in ("sessions", "messages"):
        if t in tabs:
            cols = [r[1] for r in con.execute('pragma table_info("%s")' % t)]
            n = con.execute('select count(*) from "%s"' % t).fetchone()[0]
            print("  %s (%d rows): %s" % (t, n, cols))
    if "sessions" in tabs:
        cols = [r[1] for r in con.execute('pragma table_info("sessions")')]
        for c in ("source", "platform"):
            if c in cols:
                print("  sessions by %s:" % c, con.execute("select %s, count(*) from sessions group by 1 order by 2 desc limit 10" % c).fetchall())
        tcol = "started_at" if "started_at" in cols else None
        if tcol:
            print("  sessions started_at range:", con.execute("select min(%s), max(%s) from sessions" % (tcol, tcol)).fetchone())
    if "messages" in tabs:
        cols = [r[1] for r in con.execute('pragma table_info("messages")')]
        if "role" in cols:
            print("  messages by role:", con.execute("select role, count(*) from messages group by 1").fetchall())
except Exception as e:
    print("state.db:", type(e).__name__, str(e)[:120])
