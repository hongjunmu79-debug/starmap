"""Section-2 baselines from the logs (counts only), plus re-explanation cost from the 477 messages."""
import collections, datetime, glob, io, json, math, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime(2026, 11, 9, 9, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))


def parse(ts):
    try:
        t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    except ValueError:
        return None


ev = []
for f in glob.glob("C:/Agent-Shared/home/events-*.jsonl"):
    for l in open(f, encoding="utf-8"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        e["_file"] = os.path.basename(f)
        ev.append(e)
print("== home event log:", len(ev), "events |", dict(collections.Counter(e.get("type") for e in ev)))
ideas = [e for e in ev if e.get("type") == "idea"]
touch = collections.defaultdict(list)
for e in ev:
    if e.get("type") in ("idea_edit", "idea_note", "idea_drop", "promote") and e.get("idea_id"):
        touch[e["idea_id"]].append((e.get("type"), e.get("host"), e.get("ts")))
rows = []
for i in ideas:
    iid = i.get("idea_id") or i.get("id")
    t0 = parse(i.get("ts"))
    age = (NOW - t0).days if t0 else None
    by_user = [x for x in touch.get(iid, []) if x[1] not in ("hermes",)]
    by_any = touch.get(iid, [])
    rows.append((str(i.get("ts"))[:10], i.get("host"), age, len(by_user), len(by_any), (i.get("text") or "")[:24]))
for r in sorted(rows):
    print("   idea %s host=%-16s age=%sd user-touches=%d all-touches=%d | %s" % r)
old = [r for r in rows if r[2] is not None and r[2] >= 7]
print("   ideas >= 7 days old: %d | touched by the user at all: %d | touched by anyone (incl. Hermes notes): %d" % (
    len(old), sum(1 for r in old if r[3] > 0), sum(1 for r in old if r[4] > 0)))
done = [e for e in ev if e.get("type") == "done"]
undo = [e for e in ev if e.get("type") == "undo"]
C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))
steps_total = sum(len(it.get("steps", [])) for it in C["items"])
print("== home steps: total %d | done events %d | undo %d | items touched %d | first/last done %s .. %s" % (
    steps_total, len(done), len(undo), len(set(e.get("item") for e in done)),
    min((e["ts"] for e in done), default="-")[:10], max((e["ts"] for e in done), default="-")[:10]))

ds = json.load(open(os.path.join(D, "desktop_stores.json"), encoding="utf-8"))
todos = [t for t in ds["horizon_todos"] if not t.get("parent")]
subs = [t for t in ds["horizon_todos"] if t.get("parent")]
st = collections.Counter(t["status"] for t in todos)
ages = sorted((NOW - parse(t["ts"])).days for t in todos if parse(t["ts"]) and t["status"] != "done")
today = NOW.strftime("%Y-%m-%d")
overdue = sum(1 for t in todos if t["status"] != "done" and t.get("due") and t["due"] < today)
print("== Horizon: top-level todos %d (+%d subtasks) | status %s | with due date %d | overdue %d | P0 %d | open age median %s d (max %s d)" % (
    len(todos), len(subs), dict(st), sum(1 for t in todos if t.get("due")), overdue, sum(1 for t in todos if t.get("priority") == "P0"),
    ages[len(ages) // 2] if ages else "-", ages[-1] if ages else "-"))
per_day = collections.Counter(str(t["ts"])[:10] for t in todos)
print("   created per day:", dict(sorted(per_day.items())))
print("   done:", [(t["title"][:20], str(t["ts"])[:10], str(t.get("done_at"))[:10]) for t in todos if t["status"] == "done"])

msgs = json.load(open(os.path.join(D, "all_msgs.json"), encoding="utf-8"))
CJK = re.compile(r"[\u4e00-\u9fff]+")


def grams(t):
    g = []
    for seg in CJK.findall(t):
        g += [seg[i:i + 2] for i in range(len(seg) - 1)]
    g += [w.lower() for w in re.findall(r"[A-Za-z]{3,}", t)]
    return collections.Counter(g)


def cosc(a, b):
    num = sum(a[k] * b.get(k, 0) for k in a)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0


long_msgs = [m for m in msgs if m["chars"] >= 40]
G = {m["id"]: grams(m["text"]) for m in long_msgs}
dups = []
for i, a in enumerate(long_msgs):
    for b in long_msgs[i + 1:]:
        if a["sess"] == b["sess"]:
            continue
        s = cosc(G[a["id"]], G[b["id"]])
        if s >= 0.8:
            first, second = (a, b) if a["ts"] <= b["ts"] else (b, a)
            dups.append((round(s, 2), first["id"], first["sess"], first["ts"][:16], second["id"], second["sess"], second["ts"][:16], first["chars"]))
print("== re-sent near-identical long messages across sessions (cos >= 0.8, >= 40 chars): %d pairs" % len(dups))
for d in sorted(dups, key=lambda x: x[3]):
    print("   %.2f  %s %s %s  ->  %s %s %s  (%d chars)" % d)
first_by_sess = {}
for m in sorted(msgs, key=lambda m: m["ts"]):
    first_by_sess.setdefault((m["src"], m["session"]), m)
fl = sorted(m["chars"] for m in first_by_sess.values())
big = [m for m in first_by_sess.values() if m["chars"] >= 400]
print("== session openers: %d sessions | median first-message length %d chars | openers >= 400 chars: %d (%s)" % (
    len(fl), fl[len(fl) // 2], len(big), ", ".join(sorted(m["id"] for m in big))))
pasted = [m["id"] for m in msgs if "<pasted_content" in m["text"] or m["text"].lstrip().startswith(("【任务", "# ", "> "))]
print("   messages that are pasted docs/briefs:", len(pasted), pasted[:12])
cont = [m["id"] for m in msgs if re.search(r"I hit my usage limit|Try again|继续$|接着|上次|之前那个|重新发起|已重启，继续", m["text"])]
print("   'continue / try again / limit' type messages:", len(cont))
