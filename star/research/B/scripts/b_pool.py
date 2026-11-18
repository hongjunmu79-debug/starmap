"""B 续上 — step 3: pool the top-3 of every method per query and build blind judge sheets (with 10 known-answer pairs).
usage: python b_pool.py <ranks.json>
Writes B/pool_key.json (hidden mapping) and B/judge_batch_XX.txt (same text for every judge)."""
import json, os, random, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_redact import redact  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
B = "C:/Agent-Shared/home/star/research/B"
ranks = json.load(open(sys.argv[1], encoding="utf-8"))
corpus = {r["rid"]: r for r in (json.loads(l) for l in open(os.path.join(B, "corpus.jsonl"), encoding="utf-8"))}
queries = {q["qid"]: q for q in (json.loads(l) for l in open(os.path.join(B, "queries.jsonl"), encoding="utf-8"))}


def short(t, n=200):
    t = re.sub(r"\s+", " ", redact(t)).strip()
    return t if len(t) <= n else t[:n - 1] + "…"


pairs = {}
for qid, r in ranks.items():
    for m in ("M0", "M1", "M2", "M3", "M4"):
        for rid, _ in r[m][:3]:
            pairs[(qid, rid)] = None
rows = [{"qid": q, "rid": r, "gold": None, "q": short(queries[q]["text"]), "r": short(corpus[r]["text"])} for (q, r) in sorted(pairs)]
msg = {r["rid"]: r for r in corpus.values()}
CAL = [("msg:m148", "msg:m134", "same"), ("msg:m366", "msg:m367", "same"), ("msg:m311", "msg:m346", "same"),
       ("msg:m467", "home:voice", "same"), ("msg:m215", "home:lyrics:inc0", "same"),
       ("msg:m389", "home:lyrics", "unrelated"), ("msg:m406", "home:land-lease", "unrelated"),
       ("msg:m423", "msg:m072", "unrelated"), ("msg:m162", "hz:34b4c453c675", "unrelated"), ("msg:m330", "home:voice", "unrelated")]
for a, b, lab in CAL:
    if a in corpus and b in corpus:
        rows.append({"qid": "cal:" + a, "rid": b, "gold": lab, "q": short(corpus[a]["text"]), "r": short(corpus[b]["text"])})
    else:
        print("calibration pair missing:", a, b)
rnd = random.Random(20261109)
real = [r for r in rows if r["gold"] is None]
cal = [r for r in rows if r["gold"] is not None]
rnd.shuffle(real)
nb = max(1, -(-len(real) // 40))  # at most ~40 rows per sheet: keeps each prompt under ~18K chars (Windows command line limit 32K)
batches = [real[i::nb] for i in range(nb)]
for i, c in enumerate(cal):
    batches[i % nb].append(c)
HEAD = ("这是纯文本判断任务：不要调用任何工具，不要读写文件，不要搜索。\n"
        "每一行有两段文字：A 是用户新说的话，B 是一条以前的记录。判断 B 和 A 的关系，三选一：\n"
        "same = 说的是同一件事 / 同一个想法（B 就是这件事以前的记录，A 可以接着它往下做）\n"
        "related = 有关联（同一个领域或项目），但不是同一件事\n"
        "unrelated = 没关系\n"
        "只输出 JSON：{\"results\":[{\"id\":\"p001\",\"label\":\"same\"}]}，每一行都要有。\n\n")
key = []
for bi, batch in enumerate(batches, 1):
    rnd.shuffle(batch)
    lines = []
    for row in batch:
        pid = "p%03d" % (len(key) + 1)
        row["pid"], row["batch"] = pid, bi
        key.append(row)
        lines.append("%s ｜ A：%s ｜ B：%s" % (pid, row["q"], row["r"]))
    open(os.path.join(B, "judge_batch_%02d.txt" % bi), "w", encoding="utf-8").write(HEAD + "\n".join(lines) + "\n")
json.dump(key, open(os.path.join(B, "pool_key.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("pairs to judge:", len(real), "+ calibration", len(cal), "| batches:", nb, [len(b) for b in batches])
