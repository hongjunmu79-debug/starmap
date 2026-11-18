"""Leave-one-out placement baseline on the user's own historical merge decisions.
For each original idea ("includes") of each of the 19 items: hide it, then ask which item a plain
character-bigram TF-IDF matcher would put it in. Reports top-1 / top-3 and a bootstrap interval.
Caveat printed at the end: item titles/summaries were written AFTER the merge, so the score is optimistic."""
import io, json, math, random, re, collections

C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))
items = C["items"]


def strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from strings(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from strings(v)


def includes_of(it):
    return [s for s in strings(it.get("includes", [])) if s.strip()]


def item_text(it, with_steps):
    parts = [it.get("title", ""), it.get("summary", ""), it.get("why", ""), it.get("done_when", "")]
    if with_steps:
        parts += list(strings(it.get("steps", [])))
    return " ".join(p for p in parts if isinstance(p, str))


CJK = re.compile(r"[\u4e00-\u9fff]+")
WORD = re.compile(r"[A-Za-z0-9]+")


def grams(text):
    out = []
    for seg in CJK.findall(text):
        if len(seg) == 1:
            out.append(seg)
        out += [seg[i:i + 2] for i in range(len(seg) - 1)]
    out += [w.lower() for w in WORD.findall(text)]
    return out


def tfidf_vectors(docs):
    df = collections.Counter()
    toks = [grams(d) for d in docs]
    for t in toks:
        df.update(set(t))
    n = len(docs)
    vecs = []
    for t in toks:
        tf = collections.Counter(t)
        v = {g: (1 + math.log(c)) * math.log((n + 1) / (df[g] + 0.5)) for g, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({g: x / norm for g, x in v.items()})
    return vecs


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def run(with_steps, with_siblings):
    hits1 = hits3 = total = 0
    flags = []
    for i, it in enumerate(items):
        incs = includes_of(it)
        for k, x in enumerate(incs):
            profiles = []
            for j, jt in enumerate(items):
                txt = item_text(jt, with_steps)
                if with_siblings:
                    sib = [s for m, s in enumerate(includes_of(jt)) if not (j == i and m == k)]
                    txt += " " + " ".join(sib)
                profiles.append(txt)
            vecs = tfidf_vectors(profiles + [x])
            q = vecs[-1]
            scores = sorted(((cos(q, vecs[j]), j) for j in range(len(items))), reverse=True)
            rank = [j for _, j in scores].index(i) + 1
            total += 1
            hits1 += rank == 1
            hits3 += rank <= 3
            flags.append((rank == 1, rank <= 3))
    return hits1, hits3, total, flags


def boot(flags, idx, B=3000, seed=7):
    rnd = random.Random(seed)
    vals = []
    for _ in range(B):
        s = [flags[rnd.randrange(len(flags))][idx] for _ in flags]
        vals.append(sum(s) / len(s))
    vals.sort()
    return vals[int(0.025 * B)], vals[int(0.975 * B)]


print("items:", len(items), "| includes (ideas with a known home):", sum(len(includes_of(it)) for it in items))
sizes = sorted((len(includes_of(it)) for it in items), reverse=True)
print("includes per item (sorted):", sizes)
print("majority-class top-1 (always guess the biggest item): %.0f%%" % (100 * sizes[0] / sum(sizes)))
print("random top-1: %.0f%%   random top-3: %.0f%%" % (100 / len(items), 300 / len(items)))
for name, ws, sib in (("title+summary only", False, False), ("+ steps", True, False), ("+ the item's other ideas", False, True), ("everything", True, True)):
    h1, h3, n, fl = run(ws, sib)
    lo1, hi1 = boot(fl, 0)
    lo3, hi3 = boot(fl, 1)
    print("%-28s top-1 %2d/%d = %3.0f%% (95%% CI %2.0f-%2.0f%%) | top-3 %2d/%d = %3.0f%% (CI %2.0f-%2.0f%%)" % (
        name, h1, n, 100 * h1 / n, 100 * lo1, 100 * hi1, h3, n, 100 * h3 / n, 100 * lo3, 100 * hi3))
print("NOTE: item titles/summaries were written after the ideas were merged into them, so these scores are optimistic (label leakage).")
print("A clean test needs NEW ideas: log the matcher's guess vs. the home the user accepts, from now on.")
