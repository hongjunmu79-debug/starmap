"""Show what the running Gemini (agy) sessions are doing: one line per step with time, tokens, tool calls and errors.

    python agy_progress.py [minutes]      sessions touched in the last N minutes (default 30), last 14 steps each
"""
import datetime
import glob
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 30
base = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli", "brain")
now = time.time()
rows = []
for d in glob.glob(os.path.join(base, "*")):
    f = os.path.join(d, ".system_generated", "logs", "transcript.jsonl")
    if os.path.isfile(f) and now - os.path.getmtime(f) < minutes * 60:
        rows.append((os.path.getmtime(f), d, f))
for _, d, f in sorted(rows):
    steps = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
    first = next((s for s in steps if s.get("type") == "USER_INPUT"), {})
    print("=== %s  steps=%d  last write %s" % (os.path.basename(d)[:8], len(steps), datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%H:%M:%S")))
    for s in steps[-14:]:
        t = s.get("created_at", "")
        try:
            t = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
        except Exception:
            pass
        extra = ""
        for tc in s.get("tool_calls") or []:
            a = tc.get("args") or {}
            target = a.get("TargetFile") or a.get("Path") or a.get("AbsolutePath") or a.get("File") or ""
            if not target:
                target = " ".join(str(v)[:60] for v in list(a.values())[:1])
            size = len(json.dumps(a, ensure_ascii=False))
            extra += " %s(%s, %dB)" % (tc.get("name"), str(target).replace("\\\\", "/")[-48:], size)
        if s.get("error"):
            extra += " ERR=" + str(s["error"])[:70]
        elif s.get("type") == "GENERIC" and s.get("content"):
            extra += " " + str(s["content"]).replace("\n", " ")[-80:]
        print("  %s #%-3s %-16s out=%-6s%s" % (t, s.get("step_index"), s.get("type"), s.get("output_tokens", ""), extra))
