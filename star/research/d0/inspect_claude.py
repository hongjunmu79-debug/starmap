"""Structure-only look at Claude Code transcripts (no message content is printed).
usage: python inspect_claude.py <projects_dir> [since YYYY-MM-DD]"""
import collections, glob, json, os, sys, datetime

root = sys.argv[1]
since = sys.argv[2] if len(sys.argv) > 2 else "2026-10-12"
files = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
print("files:", len(files))
types = collections.Counter()
entry = collections.Counter()
usertype = collections.Counter()
keys = collections.Counter()
content_kinds = collections.Counter()
flags = collections.Counter()
per_file = []
for f in files:
    n_user_text = 0
    first_ts = last_ts = None
    sid = None
    ent = set()
    side = 0
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                t = d.get("type")
                types[t] += 1
                keys.update(d.keys())
                if d.get("entrypoint"):
                    entry[d["entrypoint"]] += 1
                    ent.add(d["entrypoint"])
                if d.get("userType"):
                    usertype[d["userType"]] += 1
                for fl in ("isSidechain", "isMeta", "isCompactSummary", "isVisibleInTranscriptOnly"):
                    if d.get(fl):
                        flags[fl] += 1
                if d.get("isSidechain"):
                    side += 1
                ts = d.get("timestamp")
                if ts:
                    first_ts = first_ts or ts
                    last_ts = ts
                sid = sid or d.get("sessionId")
                if t == "user":
                    m = d.get("message", {})
                    c = m.get("content")
                    if isinstance(c, str):
                        content_kinds["str"] += 1
                        if not d.get("isMeta") and not c.startswith("<"):
                            n_user_text += 1
                    elif isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict):
                                content_kinds["list:" + str(b.get("type"))] += 1
                                if b.get("type") == "text" and not d.get("isMeta"):
                                    n_user_text += 1
    except OSError:
        continue
    per_file.append((first_ts or "", last_ts or "", n_user_text, sorted(ent), side, os.path.getsize(f), os.path.relpath(f, root)))
print("line types:", dict(types.most_common(12)))
print("entrypoints:", dict(entry.most_common()))
print("userType:", dict(usertype))
print("flags:", dict(flags))
print("user content kinds:", dict(content_kinds.most_common(10)))
print("top keys:", [k for k, _ in keys.most_common(30)])
recent = [p for p in per_file if p[1][:10] >= since]
print("files with activity since %s: %d" % (since, len(recent)))
buckets = collections.Counter()
for p in recent:
    n = p[2]
    buckets["0" if n == 0 else "1-2" if n <= 2 else "3-9" if n <= 9 else "10-29" if n <= 29 else "30+"] += 1
print("user-text messages per recent file:", dict(buckets))
print("entrypoints among recent files:", collections.Counter(tuple(p[3]) for p in recent).most_common(6))
print("subagent/sidechain files (path contains 'subagents'):", sum(1 for p in per_file if "subagent" in p[6].lower()))
