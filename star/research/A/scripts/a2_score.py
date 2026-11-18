"""Score the three independent judges on the blind sheet.
Gate (from the approved plan): a judge is used only if it gets >= 80% of the 10 known-answer rows right; the qualified
judges' agreement (Fleiss' kappa) must be >= 0.6; a real first step is kept only if a majority of qualified judges pass it."""
import json, os, sys

sys.stdout.reconfigure(encoding="utf-8")
D = "C:/Agent-Shared/home/star/research/A/first_steps"
sheet = {r["sid"]: r for r in json.load(open(os.path.join(D, "sheet_key.json"), encoding="utf-8"))}
judges = {}
for name in ("deepseek", "gemini", "claude"):
    res = json.load(open(os.path.join(D, "judge_%s.json" % name), encoding="utf-8"))["results"]
    judges[name] = {r["id"]: (bool(r["pass"]), r.get("fail", [])) for r in res}
gold = [sid for sid, r in sheet.items() if r["gold"] is not None]
qualified = []
for name, v in judges.items():
    missing = [sid for sid in sheet if sid not in v]
    acc = sum(1 for sid in gold if v.get(sid, (None,))[0] == sheet[sid]["gold"]) / len(gold)
    ok = acc >= 0.8 and not missing
    qualified.append(name) if ok else None
    print("%-9s gold accuracy %d/%d = %.0f%%  missing rows %d  -> %s" % (name, round(acc * len(gold)), len(gold), 100 * acc, len(missing), "USED" if ok else "NOT USED"))
# Fleiss' kappa over all rows, binary categories
rows = sorted(sheet)
n = len(qualified)
if n >= 2:
    P, pj = [], [0.0, 0.0]
    for sid in rows:
        k = sum(1 for q in qualified if judges[q][sid][0])
        counts = [k, n - k]
        P.append((sum(c * c for c in counts) - n) / (n * (n - 1)))
        pj[0] += k
        pj[1] += n - k
    tot = n * len(rows)
    Pbar = sum(P) / len(P)
    Pe = (pj[0] / tot) ** 2 + (pj[1] / tot) ** 2
    kappa = (Pbar - Pe) / (1 - Pe) if Pe < 1 else 1.0
    print("Fleiss kappa (%s): %.2f -> %s" % ("+".join(qualified), kappa, "PASS (>= 0.6)" if kappa >= 0.6 else "FAIL (< 0.6)"))
need = n // 2 + 1
final = []
print("\nreal first steps (majority of %d qualified judges, need %d):" % (n, need))
for sid in rows:
    r = sheet[sid]
    if r["gold"] is not None:
        continue
    votes = {q: judges[q][sid] for q in qualified}
    k = sum(1 for v in votes.values() if v[0])
    keep = k >= need
    final.append({"rid": r["key"], "sid": sid, "step": r["step"], "pass_votes": k, "keep": keep,
                  "fails": {q: v[1] for q, v in votes.items() if not v[0]}})
    print("  %s %s %d/%d %s | %s %s" % (r["key"], sid, k, n, "KEEP " if keep else "REDO ", r["step"][:50], "" if keep else final[-1]["fails"]))
json.dump({"qualified": qualified, "items": final}, open(os.path.join(D, "verdicts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nkept %d / %d" % (sum(f["keep"] for f in final), len(final)))
