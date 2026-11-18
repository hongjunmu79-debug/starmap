"""A 推进 — step 1: inventory + stratified random assignment, committed by SHA-256 before the experiment starts.

usage: python assign.py <horizon_open.json> <out_dir>
Rules (fixed here, before any outcome is seen):
  units  = open top-level Horizon todos whose due date is not after the experiment end
         + the next not-done step of every home item with status running or explore
  groups = within each stratum (horizon / home) shuffle with a seed derived from a fresh random salt; first half -> push
  new units that appear later: push if sha256(salt + unit_id) first byte is even, else control
  window = 2026-11-10 00:00 to 2026-11-24 00:00 (+08:00)
  primary outcome = unit completed inside the window (Horizon status done with completed_at in window;
                    home step has a 'done' event in window that is not undone later)
"""
import datetime, hashlib, io, json, os, random, secrets, sys

HZ = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]
START, END = "2026-11-10", "2026-11-24"
C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))

done = {}
for f in os.listdir("C:/Agent-Shared/home"):
    if f.startswith("events-") and f.endswith(".jsonl"):
        for l in open(os.path.join("C:/Agent-Shared/home", f), encoding="utf-8"):
            try:
                e = json.loads(l)
            except ValueError:
                continue
            if e.get("type") in ("done", "undo") and e.get("item") is not None:
                done.setdefault(e["item"], []).append((e.get("ts", ""), e["type"], e.get("step")))
finished = {}
for item, evs in done.items():
    s = set()
    for ts, kind, step in sorted(evs):
        (s.add if kind == "done" else s.discard)(step)
    finished[item] = s

units = []
for t in HZ:
    if t["due"] and t["due"] > END:
        continue
    units.append({"unit": "hz:" + t["id"], "stratum": "horizon", "title": t["title"], "due": t["due"], "created": t["created"]})
for it in C["items"]:
    if it.get("status") not in ("running", "explore"):
        continue
    steps = it.get("steps", [])
    nxt = next((i for i in range(len(steps)) if i not in finished.get(it["id"], set())), None)
    if nxt is None:
        continue
    st = steps[nxt]
    text = st.get("t", "") if isinstance(st, dict) else str(st)
    units.append({"unit": "home:%s:%d" % (it["id"], nxt), "stratum": "home", "title": "%s → %s" % (it["title"], text), "due": None, "created": C.get("updated", "")})

salt = secrets.token_hex(16)
rng = random.Random(int(hashlib.sha256(salt.encode()).hexdigest(), 16))
for stratum in ("horizon", "home"):
    group = sorted([u for u in units if u["stratum"] == stratum], key=lambda u: u["unit"])
    rng.shuffle(group)
    half = (len(group) + 1) // 2
    for i, u in enumerate(group):
        u["group"] = "push" if i < half else "control"
units.sort(key=lambda u: (u["stratum"], u["unit"]))
doc = {
    "created_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec="seconds"),
    "window": [START, END], "salt": salt,
    "new_unit_rule": "push if sha256(salt + unit_id) first byte is even",
    "primary_outcome": "completed inside the window (Horizon done/completed_at; home 'done' event not undone)",
    "success_rule": "push completion rate >= 2x control AND the 95% CI of the difference excludes 0 (Newcombe); Fisher exact test reported",
    "units": units,
}
os.makedirs(OUT, exist_ok=True)
raw = json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")
open(os.path.join(OUT, "assignment.json"), "wb").write(raw)
h = hashlib.sha256(raw).hexdigest()
open(os.path.join(OUT, "assignment.sha256"), "w", encoding="ascii").write(h + "  assignment.json\n")
print("units:", len(units), "| push:", sum(u["group"] == "push" for u in units), "| control:", sum(u["group"] == "control" for u in units))
for s in ("horizon", "home"):
    print("  %-8s push %d / control %d" % (s, sum(1 for u in units if u["stratum"] == s and u["group"] == "push"), sum(1 for u in units if u["stratum"] == s and u["group"] == "control")))
print("sha256(assignment.json) =", h)
