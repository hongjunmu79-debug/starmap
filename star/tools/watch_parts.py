"""Prints one line whenever the two Gemini builders (A = free, B = spec) write a new part, finish, or hit a stream error."""
import glob
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\User\starmap\proto3d"
BRAIN = os.path.join(os.path.expanduser("~"), ".gemini", "antigravity-cli", "brain")
start = time.time()
seen_files = {}
seen_err = {}
seen_steps = {}


def label_of(steps):
    for s in steps:
        for tc in s.get("tool_calls") or []:
            blob = json.dumps(tc.get("args") or {})
            if "/free/" in blob or "\\\\free\\\\" in blob:
                return "A"
            if "/spec/" in blob or "\\\\spec\\\\" in blob:
                return "B"
    return None


while True:
    for tag, name in (("free", "A"), ("spec", "B")):
        pdir = os.path.join(ROOT, tag, "parts")
        cur = {}
        if os.path.isdir(pdir):
            for n in os.listdir(pdir):
                p = os.path.join(pdir, n)
                cur[n] = os.path.getsize(p)
        old = seen_files.get(tag, {})
        for n, size in sorted(cur.items()):
            if n not in old:
                with open(os.path.join(pdir, n), encoding="utf-8", errors="replace") as f:
                    lines = sum(1 for _ in f)
                print("%s 新部件 %s（%d 行，%d 字节）" % (name, n, lines, size), flush=True)
        seen_files[tag] = cur
        if os.path.isfile(os.path.join(ROOT, tag, "DONE.txt")) and not seen_files.get(tag + "-done"):
            seen_files[tag + "-done"] = True
            print("%s 写了 DONE.txt" % name, flush=True)
    for f in glob.glob(os.path.join(BRAIN, "*", ".system_generated", "logs", "transcript.jsonl")):
        if os.path.getmtime(f) < start - 30:
            continue
        try:
            steps = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        except Exception:
            continue
        lab = label_of(steps) or "?"
        errs = [s for s in steps if s.get("type") == "ERROR_MESSAGE"]
        sid = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(f))))
        if len(errs) > seen_err.get(sid, 0):
            seen_err[sid] = len(errs)
            print("%s 流中断/出错 第 %d 次：%s" % (lab, len(errs), str(errs[-1].get("error", ""))[:80]), flush=True)
        final = [s for s in steps if s.get("type") == "PLANNER_RESPONSE" and s.get("content") and not s.get("tool_calls")]
        if final and seen_steps.get(sid) != len(steps):
            seen_steps[sid] = len(steps)
            print("%s 给出了文字回答：%s" % (lab, str(final[-1]["content"]).replace("\n", " ")[:160]), flush=True)
    time.sleep(4)
