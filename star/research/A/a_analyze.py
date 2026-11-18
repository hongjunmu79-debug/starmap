"""A 推进 — pre-registered analysis (its SHA-256 is recorded before any outcome exists).
usage: python a_analyze.py [--as-of YYYY-MM-DD]
Outcome per unit = completed inside the window [start, end):
  horizon unit -> horizon-todos.json status 'done' with completed_at inside the window (+08:00 local dates)
  home unit    -> a 'done' event for (item, step_index) inside the window that is not undone later
Report: completion rate per group, risk difference with Newcombe (Wilson) 95% CI, ratio, two-sided Fisher exact p.
Success rule (fixed in assignment.json): push rate >= 2x control rate AND the CI of the difference excludes 0."""
import datetime, glob, json, math, os, sys

sys.stdout.reconfigure(encoding="utf-8")
HOME = "C:/Agent-Shared/home"
A = json.load(open(os.path.join(HOME, "star/research/A/assignment.json"), encoding="utf-8"))
start, end = A["window"]
as_of = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else datetime.date.today().isoformat()
end_eff = min(end, (datetime.date.fromisoformat(as_of) + datetime.timedelta(days=1)).isoformat())


def local_date(ts):
    t = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace(" ", "T"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
    return t.astimezone(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()


todos = {}
try:
    todos = {t["id"]: t for t in json.load(open(os.path.join(HOME, "horizon-todos.json"), encoding="utf-8"))["todos"]}
except (OSError, ValueError):
    pass
steps = {}
for f in glob.glob(os.path.join(HOME, "events-*.jsonl")):
    for l in open(f, encoding="utf-8"):
        try:
            e = json.loads(l)
        except ValueError:
            continue
        if e.get("type") in ("done", "undo") and e.get("item") is not None:
            steps.setdefault((e["item"], e.get("step")), []).append((e.get("ts", ""), e["type"]))


def completed(u):
    kind, rest = u["unit"].split(":", 1)
    if kind == "hz":
        t = todos.get(rest)
        return bool(t and t.get("status") == "done" and t.get("completed_at") and start <= local_date(t["completed_at"]) < end_eff)
    item, idx = rest.rsplit(":", 1)
    evs = sorted(steps.get((item, int(idx)), []))
    state, when = False, None
    for ts, kind_ in evs:
        state, when = (kind_ == "done"), ts
    return bool(state and when and start <= local_date(when) < end_eff)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def fisher_two_sided(a, b, c, d):
    n1, n2, k = a + b, c + d, a + c
    def p(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n1 + n2, k)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= p0 + 1e-12))


res = {}
for g in ("push", "control"):
    us = [u for u in A["units"] if u["group"] == g]
    k = sum(1 for u in us if completed(u))
    res[g] = (k, len(us))
(kp, np_), (kc, nc) = res["push"], res["control"]
pp, pc = kp / np_, kc / nc
lp, up = wilson(kp, np_)
lc, uc = wilson(kc, nc)
diff = pp - pc
lo = diff - math.sqrt((pp - lp) ** 2 + (uc - pc) ** 2)
hi = diff + math.sqrt((up - pp) ** 2 + (pc - lc) ** 2)
fp = fisher_two_sided(kp, np_ - kp, kc, nc - kc)
ratio = (pp / pc) if pc > 0 else (float("inf") if pp > 0 else 1.0)
success = (pp >= 2 * pc) and (lo > 0)
print("window %s .. %s (counted up to %s)" % (start, end, end_eff))
print("push    %d / %d = %.0f%% (95%% CI %.0f-%.0f%%)" % (kp, np_, 100 * pp, 100 * lp, 100 * up))
print("control %d / %d = %.0f%% (95%% CI %.0f-%.0f%%)" % (kc, nc, 100 * pc, 100 * lc, 100 * uc))
print("difference %.0f points (95%% CI %.0f to %.0f) | ratio %s | Fisher p = %.3f | success rule: %s" % (
    100 * diff, 100 * lo, 100 * hi, "inf" if ratio == float("inf") else "%.2f" % ratio, fp, "MET" if success else "not met"))
