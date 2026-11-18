"""Combine the three message files, give each message a short id, mask names-with-titles, and write compact labeling sheets."""
import json, os, re, sys

D = os.path.dirname(os.path.abspath(__file__))
rows = []
for name in ("msgs-laptop.jsonl", "msgs-desktop.jsonl", "msgs-phone.jsonl"):
    rows += [json.loads(l) for l in open(os.path.join(D, name), encoding="utf-8") if l.strip()]
rows.sort(key=lambda r: (r["src"], r["session"], r["ts"]))
TITLE = re.compile(r"([一-鿿]{1,3})(师傅|老师|总|哥|姐|先生|女士|同学|经理|老板)")
sess_short = {}
SRC = {"laptop-claude": "L", "desktop-claude": "D", "phone-feishu": "F", "phone-weixin": "W", "phone-telegram": "T"}
out = []
for i, r in enumerate(rows):
    r["id"] = "m%03d" % i
    key = (r["src"], r["session"])
    sess_short.setdefault(key, "%s%02d" % (SRC.get(r["src"], "?"), sum(1 for k in sess_short if k[0] == r["src"]) + 1))
    r["sess"] = sess_short[key]
    t = TITLE.sub(lambda m: "某" + m.group(2), r["text"])
    r["text"] = t
    flat = re.sub(r"\s+", " ", t).strip()
    if len(flat) > 230:
        flat = flat[:170] + " … " + flat[-55:]
    out.append("%s\t%s\t%s\t%s" % (r["id"], r["sess"], r["ts"][5:10], flat))
json.dump(rows, open(os.path.join(D, "all_msgs.json"), "w", encoding="utf-8"), ensure_ascii=False)
chunks = [out[0:160], out[160:320], out[320:]]
for n, c in enumerate(chunks, 1):
    open(os.path.join(D, "snips-%d.txt" % n), "w", encoding="utf-8").write("\n".join(c) + "\n")
print("messages:", len(rows), "| sessions:", len(sess_short), "| sheets:", [len(c) for c in chunks])
