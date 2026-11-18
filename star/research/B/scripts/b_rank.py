"""B 续上 — step 2 (runs on the desktop: ~/star-eval/.venv/bin/python b_rank.py data_dir out_file).
For every query rank only the records it was allowed to see (born before it, not from its own session) with five methods:
  M0 literal   char-bigram TF-IDF cosine (the D0 baseline)
  M1 bm25      jieba words + English words, BM25Okapi
  M2 bge-m3    dense cosine (BAAI/bge-m3, normalized)
  M3 hybrid    reciprocal-rank fusion of M1 and M2 (k=60)
  M4 phonetic  M3 fused with a pinyin char-trigram TF-IDF ranking (for speech-to-text spelling errors)
Writes top-10 (rid, score) per query per method as JSON."""
import collections, datetime, json, math, os, re, sys

import jieba
import numpy as np
from pypinyin import lazy_pinyin
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

jieba.setLogLevel(60)
data, out_file = sys.argv[1], sys.argv[2]
corpus = [json.loads(l) for l in open(os.path.join(data, "corpus.jsonl"), encoding="utf-8")]
queries = [json.loads(l) for l in open(os.path.join(data, "queries.jsonl"), encoding="utf-8")]


def epoch(s):
    """The data mixes '...Z' (UTC) and '...+08:00' stamps: compare instants, never strings."""
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


births = [epoch(r["birth"]) for r in corpus]
CJK = re.compile(r"[一-鿿]+")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9]+|\d+")


def bigrams(t):
    g = []
    for seg in CJK.findall(t):
        g += [seg[i:i + 2] for i in range(len(seg) - 1)] or [seg]
    return g + [w.lower() for w in WORD.findall(t)]


def words(t):
    toks = []
    for w in jieba.lcut(t):
        w = w.strip().lower()
        if w and (CJK.search(w) or re.match(r"[a-z0-9]{2,}$", w)):
            toks.append(w)
    return toks


def pinyin_trigrams(t):
    s = "".join(lazy_pinyin(t)).lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return [s[i:i + 3] for i in range(len(s) - 2)]


def tfidf_space(tokenizer):
    docs = [tokenizer(r["text"]) for r in corpus]
    df = collections.Counter()
    for d in docs:
        df.update(set(d))
    n = len(docs)

    def vec(toks):
        tf = collections.Counter(toks)
        v = {g: (1 + math.log(c)) * math.log((n + 1) / (df.get(g, 0) + 0.5)) for g, c in tf.items()}
        nr = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / nr for g, x in v.items()}
    return [vec(d) for d in docs], lambda t: vec(tokenizer(t))


def cos(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


lit_docs, lit_q = tfidf_space(bigrams)
py_docs, py_q = tfidf_space(pinyin_trigrams)
bm25 = BM25Okapi([words(r["text"]) or ["_"] for r in corpus])
model = SentenceTransformer("BAAI/bge-m3", device="cpu")
E = model.encode([r["text"] for r in corpus], normalize_embeddings=True, batch_size=16, show_progress_bar=False)
Q = model.encode([q["text"] for q in queries], normalize_embeddings=True, batch_size=16, show_progress_bar=False)


def rrf(*rankings, k=60):
    s = collections.defaultdict(float)
    for rk in rankings:
        for pos, (i, _) in enumerate(rk):
            s[i] += 1.0 / (k + pos + 1)
    return sorted(s.items(), key=lambda x: -x[1])


result = {}
for qi, q in enumerate(queries):
    qt = epoch(q["ts"])
    allowed = [i for i, r in enumerate(corpus) if births[i] < qt and r.get("session") != q["session"]]
    lq, pq = lit_q(q["text"]), py_q(q["text"])
    bm = bm25.get_scores(words(q["text"]) or ["_"])
    m0 = sorted(((i, cos(lq, lit_docs[i])) for i in allowed), key=lambda x: -x[1])
    m1 = sorted(((i, float(bm[i])) for i in allowed), key=lambda x: -x[1])
    m2 = sorted(((i, float(E[i] @ Q[qi])) for i in allowed), key=lambda x: -x[1])
    m3 = rrf(m1[:50], m2[:50])
    ph = sorted(((i, cos(pq, py_docs[i])) for i in allowed), key=lambda x: -x[1])
    m4 = rrf(m1[:50], m2[:50], ph[:50])
    result[q["qid"]] = {name: [[corpus[i]["rid"], round(s, 4)] for i, s in rk[:10]]
                        for name, rk in (("M0", m0), ("M1", m1), ("M2", m2), ("M3", m3), ("M4", m4))}
    result[q["qid"]]["visible"] = len(allowed)
json.dump(result, open(out_file, "w", encoding="utf-8"), ensure_ascii=False)
print("ranked", len(result), "queries over", len(corpus), "records")
