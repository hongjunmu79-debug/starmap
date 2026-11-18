"""Gate before any B judge sheet goes to an outside model: every judge_batch_*.txt must have zero sensitive hits.
Prints counts only (never the matched text). Exit 0 = pass, 1 = blocked."""
import glob, os, sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from b_redact import scan  # noqa: E402

B = "C:/Agent-Shared/home/star/research/B"
files = sorted(glob.glob(os.path.join(B, "judge_batch_*.txt")))
if not files:
    print("no judge sheets found")
    sys.exit(1)
bad = 0
for f in files:
    hits = scan(open(f, encoding="utf-8").read())
    print(os.path.basename(f), "hits:", hits or 0)
    bad += sum(hits.values())
print("GATE", "PASS" if bad == 0 else "BLOCKED (%d hits)" % bad)
sys.exit(0 if bad == 0 else 1)
