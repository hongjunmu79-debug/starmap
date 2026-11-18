"""B 续上 — step 4: score. Judges must get >= 80% of the 10 known-answer pairs right; qualified judges must agree
(Fleiss' kappa >= 0.6); the gold label of a pair is the majority of qualified judges ('same' = relevant).
Queries are split by time: the earlier half picks each method's 'claim a match' threshold (top-1 score), the later half
is only used to report. Pass (pre-registered): test Recall@3 >= 80% and false alarm <= 15%."""
import collections, datetime, glob, json, math, os, sys

sys.stdout.reconfigure(encoding="utf-8")
B = "C:/Agent-Shared/home/star/research/B"
key = json.load(open(os.path.join(B, "pool_key.json"), encoding="utf-8"))
ranks = json.load(open(os.path.join(B, "ranks.json"), encoding="utf-8"))
queries = {q["qid"]: q for q in (json.loads(l) for l in open(os.path.join(B, "queries.jsonl"), encoding="utf-8"))}
LABELS = ("same", "related", "unrelated")
judges = {}
for f in glob.glob(os.path.join(B, "judges", "*.json")):
    name = os.path.basename(f).split("_")[0]
    for r in json.load(open(f, encoding="utf-8"))["results"]:
        judges.setdefault(name, {})[r["id"]] = r["label"] if r["label"] in LABELS else "unrelated"
out = {"judges": {}}
qualified = []
cal = [k for k in key if k["gold"] is not None]
for name, v in sorted(judges.items()):
    acc = sum(1 for k in cal if v.get(k["pid"]) == k["gold"]) / len(cal)
    missing = sum(1 for k in key if k["pid"] not in v)
    ok = acc >= 0.8 and missing == 0
    out["judges"][name] = {"calibration_accuracy": acc, "missing": missing, "used": ok}
    if ok:
        qualified.append(name)
    print("%-9s calibration %d/%d = %.0f%%  missing %d -> %s" % (name, round(acc * len(cal)), len(cal), 100 * acc, missing, "USED" if ok else "NOT USED"))
n = len(qualified)
rows = [k for k in key if k["gold"] is None]
kappa = None
if n >= 2:
    P, tot = [], collections.Counter()
    for k in rows:
        c = collections.Counter(judges[j][k["pid"]] for j in qualified)
        tot.update(c)
        P.append((sum(x * x for x in c.values()) - n) / (n * (n - 1)))
    pbar = sum(P) / len(P)
    pe = sum((tot[l] / (n * len(rows))) ** 2 for l in LABELS)
    kappa = (pbar - pe) / (1 - pe)
    out["fleiss_kappa"] = kappa
    print("Fleiss kappa (%s): %.2f -> %s" % ("+".join(qualified), kappa, "PASS" if kappa >= 0.6 else "FAIL"))
out["gold_trusted"] = bool(n >= 2 and kappa is not None and kappa >= 0.6)  # pre-registered gate: >= 2 qualified judges and kappa >= 0.6
print("gold labels trusted:", "YES" if out["gold_trusted"] else "NO (fewer than 2 qualified judges or kappa < 0.6) - results below are not valid")
gold, disputed = {}, 0
for k in rows:
    c = collections.Counter(judges[j][k["pid"]] for j in qualified).most_common()
    if c[0][1] * 2 > n:
        gold[(k["qid"], k["rid"])] = c[0][0]
    else:
        disputed += 1
print("pairs with a majority label: %d, disputed: %d" % (len(gold), disputed))
same = collections.defaultdict(set)
for (q, r), lab in gold.items():
    if lab == "same":
        same[q].add(r)
order = sorted(ranks, key=lambda q: datetime.datetime.fromisoformat(queries[q]["ts"].replace("Z", "+00:00")))  # instants, not strings
dev, test = order[: len(order) // 2], order[len(order) // 2:]
pos = {q for q in order if same[q]}
print("queries: %d (dev %d / test %d) | with a prior record of the same thing: %d" % (len(order), len(dev), len(test), len(pos)))


def wilson(k, m):
    if m == 0:
        return (0.0, 0.0)
    p, z = k / m, 1.96
    d = 1 + z * z / m
    c = p + z * z / (2 * m)
    r = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m))
    return ((c - r) / d, (c + r) / d)


def hit(q, m):
    return any(rid in same[q] for rid, _ in ranks[q][m][:3])


def top1(q, m):
    return ranks[q][m][0][1] if ranks[q][m] else -1e9


res = {}
for m in ("M0", "M1", "M2", "M3", "M4"):
    cands = sorted({top1(q, m) for q in dev})
    best = None
    for t in cands + [1e9]:
        neg = [q for q in dev if q not in pos]
        fa = sum(1 for q in neg if top1(q, m) >= t) / max(1, len(neg))
        rc = sum(1 for q in dev if q in pos and hit(q, m) and top1(q, m) >= t) / max(1, sum(1 for q in dev if q in pos))
        if fa <= 0.15 and (best is None or rc > best[1]):
            best = (t, rc, fa)
    t = best[0]
    tp = [q for q in test if q in pos]
    tn = [q for q in test if q not in pos]
    k_rec = sum(1 for q in tp if hit(q, m) and top1(q, m) >= t)
    k_raw = sum(1 for q in tp if hit(q, m))
    k_fa = sum(1 for q in tn if top1(q, m) >= t)
    res[m] = {"threshold": t, "test_pos": len(tp), "test_neg": len(tn), "recall3": k_rec / max(1, len(tp)), "recall3_ci": wilson(k_rec, len(tp)),
              "recall3_ungated": k_raw / max(1, len(tp)), "false_alarm": k_fa / max(1, len(tn)), "false_alarm_ci": wilson(k_fa, len(tn)),
              "hits": {q: hit(q, m) and top1(q, m) >= t for q in tp}}
    res[m]["pass"] = res[m]["recall3"] >= 0.8 and res[m]["false_alarm"] <= 0.15
for m in ("M1", "M2", "M3", "M4"):
    b = sum(1 for q in res[m]["hits"] if res[m]["hits"][q] and not res["M0"]["hits"][q])
    c = sum(1 for q in res[m]["hits"] if not res[m]["hits"][q] and res["M0"]["hits"][q])
    nn = b + c
    p = min(1.0, 2 * sum(math.comb(nn, i) for i in range(0, min(b, c) + 1)) / (2 ** nn)) if nn else 1.0
    res[m]["mcnemar_vs_M0"] = {"better": b, "worse": c, "p": p}
lines = ["| 方法 | 测试集前 3 命中（门槛后） | 不设门槛的前 3 命中 | 误报 | 和字面基线比 | 过线 |", "|---|---|---|---|---|---|"]
NAMES = {"M0": "字面（基线）", "M1": "BM25", "M2": "bge-m3 向量", "M3": "BM25+向量", "M4": "再加拼音"}
for m, r in res.items():
    mc = r.get("mcnemar_vs_M0")
    lines.append("| %s | %.0f%%（%.0f–%.0f%%）%d 题 | %.0f%% | %.0f%%（%.0f–%.0f%%）%d 题 | %s | %s |" % (
        NAMES[m], 100 * r["recall3"], 100 * r["recall3_ci"][0], 100 * r["recall3_ci"][1], r["test_pos"], 100 * r["recall3_ungated"],
        100 * r["false_alarm"], 100 * r["false_alarm_ci"][0], 100 * r["false_alarm_ci"][1], r["test_neg"],
        "—" if not mc else "好 %d / 差 %d，p=%.2f" % (mc["better"], mc["worse"], mc["p"]), "过" if r["pass"] else "不过"))
print("\n".join(lines))
for r in res.values():
    r.pop("hits")
chosen = next((m for m in ("M0", "M1", "M2", "M3", "M4") if res[m]["pass"]), None) if out["gold_trusted"] else None  # cheapest first
out.update({"qualified": qualified, "disputed": disputed, "results": res, "chosen": chosen})
print("VERDICT:", ("ship " + NAMES[chosen]) if chosen else "no method passes (or gold not trusted) - stop and report")
json.dump(out, open(os.path.join(B, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
open(os.path.join(B, "results.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
