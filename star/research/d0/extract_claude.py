"""Extract the HUMAN-typed messages from Claude Code transcripts (runs locally on each machine).
usage: python extract_claude.py <projects_dir> <since YYYY-MM-DD> <source-label>   -> JSONL on stdout (UTF-8)
Skips: tool results, subagent/sidechain files, meta/compact summaries, headless (sdk-cli) and T3-started sessions,
slash-command wrappers, interruptions. Masks e-mails, phone numbers, account ids, keys, long tokens; URLs keep the host only."""
import glob, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
root, since, label = sys.argv[1], sys.argv[2], sys.argv[3]

URL = re.compile(r"https?://([^/\s\"'<>]+)[^\s\"'<>]*")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
IDS = re.compile(r"o9cq[\w-]{6,}(@im\.wechat)?|wxid_[\w-]{6,}|\b(oc|ou|on)_[0-9a-f]{16,}\b")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEY = re.compile(r"\b(sk|pk|rk|ghp|gho|github_pat|xox[abp]|AKIA)[-_A-Za-z0-9]{12,}")
LONGTOK = re.compile(r"\b[A-Za-z0-9_\-]{36,}\b")
TAGBLOCK = re.compile(r"<(system-reminder|local-command-caveat|local-command-stdout|command-message|command-args)>.*?</\1>", re.S)
SKIP_PREFIX = ("<command-name>", "<local-command", "<task-notification", "[Request interrupted", "Caveat: The messages below",
               "This session is being continued", "<bash-input>", "<bash-stdout>", "<user-prompt-submit-hook>")


def redact(s):
    s = URL.sub(lambda m: "<url:%s>" % m.group(1), s)
    s = EMAIL.sub("<email>", s)
    s = IDS.sub("<id>", s)
    s = PHONE.sub("<phone>", s)
    s = KEY.sub("<key>", s)
    s = LONGTOK.sub("<token>", s)
    return s


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "tool_result":
                    return None
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
        return "\n".join(parts)
    return None


seen = set()
out = 0
for f in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
    if "subagents" in f.replace("\\", "/").lower():
        continue
    rows = []
    bad_session = False
    try:
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("entrypoint") in ("sdk-cli", "t3-code"):
                    bad_session = True
                if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary") or d.get("toolUseResult"):
                    continue
                t = text_of((d.get("message") or {}).get("content"))
                if not t:
                    continue
                t = TAGBLOCK.sub("", t).strip()
                if not t or t.startswith(SKIP_PREFIX):
                    continue
                ts = d.get("timestamp") or ""
                if ts[:10] < since:
                    continue
                u = d.get("uuid")
                if u in seen:
                    continue
                seen.add(u)
                rows.append({"src": label, "session": d.get("sessionId"), "uuid": u, "ts": ts,
                             "project": os.path.basename(os.path.dirname(f)), "chars": len(t), "text": redact(t)[:1500]})
    except OSError:
        continue
    if bad_session:
        continue
    for i, r in enumerate(sorted(rows, key=lambda r: r["ts"])):
        r["idx"] = i
        print(json.dumps(r, ensure_ascii=False))
        out += 1
print("extracted %d messages" % out, file=sys.stderr)
