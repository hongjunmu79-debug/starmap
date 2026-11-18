"""Second masking pass over every working file of D0 (ids are kept). Catches key=value secrets and 24+ char mixed tokens
that the first pass missed. Prints only counts, never the values."""
import glob, json, os, re

D = os.path.dirname(os.path.abspath(__file__))
KV = re.compile(r"(?i)((?:secret\s*_?(?:id|key)|access\s*_?key(?:\s*_?id)?|api\s*_?key|app\s*_?secret|token|password|passwd|pwd|密码|口令|密钥)\s*[:：=]\s*)([^\s,，;；]+)")
MIXED = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{24,}\b")
PWD_WORD = re.compile(r"(密码|口令)\s*(是|为)?\s*(\S{3,})")


def scrub(s):
    n = 0
    s, k = KV.subn(lambda m: m.group(1) + "<secret>", s); n += k
    s, k = MIXED.subn("<token>", s); n += k
    s, k = PWD_WORD.subn(lambda m: m.group(1) + " <secret>", s); n += k
    return s, n


total = 0
p = os.path.join(D, "all_msgs.json")
rows = json.load(open(p, encoding="utf-8"))
for r in rows:
    r["text"], k = scrub(r["text"])
    total += k
json.dump(rows, open(p, "w", encoding="utf-8"), ensure_ascii=False)
for f in glob.glob(os.path.join(D, "msgs-*.jsonl")) + glob.glob(os.path.join(D, "snips-*.txt")) + glob.glob(os.path.join(D, "msgs-phone.raw")):
    txt = open(f, encoding="utf-8", errors="replace").read()
    txt, k = scrub(txt)
    total += k
    open(f, "w", encoding="utf-8").write(txt)
left = 0
for f in glob.glob(os.path.join(D, "*")):
    if os.path.isfile(f) and f.endswith((".json", ".jsonl", ".txt", ".raw")):
        left += len(re.findall(r"(?i)secret\s*_?key\s*[:：]\s*(?!<secret>)\S", open(f, encoding="utf-8", errors="replace").read()))
print("masked spans:", total, "| unmasked 'SecretKey:' values left in working files:", left)
