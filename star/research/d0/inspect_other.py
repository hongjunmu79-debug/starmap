"""Structure-only look at Codex sessions and Hermes director sessions on the desktop (runs in WSL python3; prints no message content)."""
import collections, glob, json, os, sqlite3

CODEX = "/mnt/c/Users/23715/.codex/sessions"
HH = "/mnt/d/Claude Code 工作区/agents/hermes-agents/director/hermes-home"

print("=== Codex")
files = sorted(glob.glob(os.path.join(CODEX, "**", "*.jsonl"), recursive=True))
print("files:", len(files), "| first/last names:", os.path.basename(files[0]) if files else "-", os.path.basename(files[-1]) if files else "-")
types = collections.Counter()
ptypes = collections.Counter()
roles = collections.Counter()
recent = 0
for f in files:
    seen_recent = False
    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            types[d.get("type")] += 1
            p = d.get("payload") or {}
            if isinstance(p, dict):
                ptypes[(d.get("type"), p.get("type"))] += 1
                if p.get("role"):
                    roles[p.get("role")] += 1
            if str(d.get("timestamp", ""))[:10] >= "2026-10-12":
                seen_recent = True
    recent += seen_recent
print("record types:", dict(types.most_common(8)))
print("(type, payload.type):", ptypes.most_common(14))
print("roles:", dict(roles))
print("files with activity since 2026-10-12:", recent)

print("=== Hermes director: sessions dir")
sd = os.path.join(HH, "sessions")
names = os.listdir(sd) if os.path.isdir(sd) else []
print("entries:", len(names), "| extensions:", collections.Counter(os.path.splitext(n)[1] for n in names).most_common(6))
sample = sorted((n for n in names if n.endswith((".json", ".jsonl"))), key=lambda n: os.path.getmtime(os.path.join(sd, n)))[-3:]
for n in sample:
    p = os.path.join(sd, n)
    try:
        if n.endswith(".jsonl"):
            with open(p, encoding="utf-8", errors="replace") as fh:
                first = json.loads(fh.readline())
            print(" ", n[:40], "jsonl first keys:", sorted(first.keys())[:15])
        else:
            d = json.load(open(p, encoding="utf-8", errors="replace"))
            if isinstance(d, dict):
                print(" ", n[:40], "keys:", sorted(d.keys())[:20])
                msgs = d.get("messages")
                if isinstance(msgs, list) and msgs:
                    print("    messages:", len(msgs), "| msg keys:", sorted(msgs[0].keys())[:12], "| roles:", dict(collections.Counter(m.get("role") for m in msgs if isinstance(m, dict))))
            else:
                print(" ", n[:40], type(d).__name__, len(d))
    except Exception as e:
        print(" ", n[:40], "unreadable:", type(e).__name__)

print("=== Hermes director: state db")
for cand in sorted(glob.glob(os.path.join(HH, "*.db"))):
    try:
        con = sqlite3.connect("file:%s?mode=ro" % cand, uri=True, timeout=5)
        tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        info = []
        for t in tabs[:12]:
            try:
                n = con.execute('select count(*) from "%s"' % t).fetchone()[0]
            except Exception:
                n = "?"
            info.append("%s(%s)" % (t, n))
        print(os.path.basename(cand), "->", ", ".join(info))
        for t in ("sessions", "messages"):
            if t in tabs:
                cols = [r[1] for r in con.execute('pragma table_info("%s")' % t)]
                print("   %s columns:" % t, cols)
        if "sessions" in tabs:
            cols = [r[1] for r in con.execute('pragma table_info("sessions")')]
            for c in ("source", "platform", "channel"):
                if c in cols:
                    print("   sessions by %s:" % c, con.execute('select %s, count(*) from sessions group by 1 order by 2 desc limit 8' % c).fetchall())
        con.close()
    except Exception as e:
        print(os.path.basename(cand), "unreadable:", type(e).__name__, str(e)[:80])
