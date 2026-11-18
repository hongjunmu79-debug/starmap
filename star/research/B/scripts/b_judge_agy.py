"""Gemini and Claude judge every B batch sheet through the Antigravity CLI (agy), one blind call per batch.
usage: python b_judge_agy.py gemini|claude
Runs from an empty folder, sandboxed, with a JSON schema that forces {"results":[{"id","label"}]}.
A batch counts only if every row id comes back exactly once with an allowed label; otherwise it is retried (3 tries).
Output: B/judges/<name>_batch_XX.json (plus model, conversation id and duration for the audit trail)."""
import glob, json, os, re, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8")
MODELS = {"gemini": "gemini-4-argon-high", "claude": "claude-opus-5-5-high"}
name = sys.argv[1]
model = MODELS[name]
AGY = os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
B = "C:/Agent-Shared/home/star/research/B"
WORK = os.path.join(os.environ["TEMP"], "star-judge-empty")
os.makedirs(WORK, exist_ok=True)
os.makedirs(os.path.join(B, "judges"), exist_ok=True)
schema = os.path.join(WORK, "schema.json")
json.dump({"type": "object", "required": ["results"], "properties": {"results": {"type": "array", "items": {
    "type": "object", "required": ["id", "label"], "properties": {
        "id": {"type": "string"}, "label": {"type": "string", "enum": ["same", "related", "unrelated"]}}}}}},
          open(schema, "w", encoding="utf-8"))

for f in sorted(glob.glob(os.path.join(B, "judge_batch_*.txt")), reverse="--reverse" in sys.argv):  # a 2nd worker can run from the other end
    tag = os.path.basename(f)[len("judge_"):-4]
    out = os.path.join(B, "judges", "%s_%s.json" % (name, tag))
    if os.path.exists(out):
        continue
    sheet = open(f, encoding="utf-8").read()
    want = re.findall(r"^(p\d{3}) ｜", sheet, flags=re.M)
    for attempt in range(1, 4):
        try:
            p = subprocess.run([AGY, "--model", model, "--sandbox", "--disable-slash-commands", "--output-format", "json",
                                "--json-schema", schema, "-p", sheet], cwd=WORK, capture_output=True, timeout=900)
            env = json.loads(p.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
            if env.get("status") != "SUCCESS":
                raise ValueError("agy status %s: %s" % (env.get("status"), str(env.get("error"))[:150]))
            so = env.get("structured_output")  # schema-checked by agy; 'response' may carry extra text
            res = (so if isinstance(so, dict) else json.loads(env["response"]))["results"]
            got = [r["id"] for r in res]
            if sorted(got) != sorted(want) or any(r["label"] not in ("same", "related", "unrelated") for r in res):
                raise ValueError("ids or labels do not match the sheet (%d back, %d asked)" % (len(set(got) & set(want)), len(want)))
            json.dump({"model": model, "conversation_id": env.get("conversation_id"), "seconds": env.get("duration_seconds"),
                       "results": res}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
            print(name, tag, "ok:", len(res), "rows | %.0fs" % (env.get("duration_seconds") or 0))
            break
        except Exception as e:  # noqa: BLE001 - network drops, bad JSON, timeouts: retry
            print(name, tag, "attempt %d failed: %s" % (attempt, str(e)[:200]))
            time.sleep(20 * attempt)
    else:
        print(name, tag, "GAVE UP after 3 attempts")
