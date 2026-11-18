"""DeepSeek judges every B batch sheet independently (separate call per batch). Output: B/judges/deepseek_batch_XX.json
A batch counts only if every row id comes back exactly once with an allowed label; otherwise it is retried (3 tries)."""
import glob, json, os, re, sys, time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "C:/Users/User/starmap/research_a")
from dsapi import deepseek  # noqa: E402

B = "C:/Agent-Shared/home/star/research/B"
os.makedirs(os.path.join(B, "judges"), exist_ok=True)
for f in sorted(glob.glob(os.path.join(B, "judge_batch_*.txt"))):
    tag = os.path.basename(f)[len("judge_"):-4]
    out = os.path.join(B, "judges", "deepseek_%s.json" % tag)
    if os.path.exists(out):
        continue
    sheet = open(f, encoding="utf-8").read()
    want = re.findall(r"^(p\d{3}) ｜", sheet, flags=re.M)
    for attempt in range(1, 4):
        try:
            r = deepseek("你只输出 JSON。", sheet)
            res = r.get("results", [])
            got = [x.get("id") for x in res]
            if sorted(got) != sorted(want) or any(x.get("label") not in ("same", "related", "unrelated") for x in res):
                raise ValueError("ids or labels do not match the sheet (%d back, %d asked)" % (len(set(got) & set(want)), len(want)))
            json.dump({"model": "deepseek-chat", "results": res}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
            print(tag, "ok:", len(res), "rows")
            break
        except Exception as e:  # noqa: BLE001 - network drops, bad JSON: retry
            print(tag, "attempt %d failed: %s" % (attempt, str(e)[:200]))
            time.sleep(10 * attempt)
    else:
        print(tag, "GAVE UP after 3 attempts")
