"""Extract the user's own phone messages (Feishu / WeChat / Telegram) from Hermes director's state.db.
Runs in WSL on the desktop. Works on a private snapshot copy in /tmp (the live database is only read, never opened for writing);
the copy is deleted at the end. Output: JSONL on stdout, same shape as extract_claude.py."""
import datetime, json, os, re, shutil, sqlite3, sys, tempfile

HH = "/mnt/d/Claude Code 工作区/agents/hermes-agents/director/hermes-home"
SINCE = datetime.datetime(2026, 10, 12, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp()

URL = re.compile(r"https?://([^/\s\"'<>]+)[^\s\"'<>]*")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
IDS = re.compile(r"o9cq[\w-]{6,}(@im\.wechat)?|wxid_[\w-]{6,}|\b(oc|ou|on)_[0-9a-f]{16,}\b")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
KEY = re.compile(r"\b(sk|pk|rk|ghp|gho|github_pat|xox[abp]|AKIA)[-_A-Za-z0-9]{12,}")
LONGTOK = re.compile(r"\b[A-Za-z0-9_\-]{36,}\b")


def redact(s):
    s = URL.sub(lambda m: "<url:%s>" % m.group(1), s)
    s = EMAIL.sub("<email>", s)
    s = IDS.sub("<id>", s)
    s = PHONE.sub("<phone>", s)
    s = KEY.sub("<key>", s)
    s = LONGTOK.sub("<token>", s)
    return s


def text_of(c):
    if c is None:
        return ""
    if isinstance(c, str) and c[:1] in "[{":
        try:
            v = json.loads(c)
            if isinstance(v, list):
                return "\n".join(p.get("text", "") for p in v if isinstance(p, dict) and p.get("type") in ("text", "input_text"))
            if isinstance(v, dict):
                return v.get("text") or ""
        except ValueError:
            pass
    return str(c)


tmp = tempfile.mkdtemp(prefix="hsnap-")
try:
    for name in ("state.db", "state.db-wal"):
        src = os.path.join(HH, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp, name))
    con = sqlite3.connect(os.path.join(tmp, "state.db"))
    q = ("select s.id, s.source, m.id, m.timestamp, m.content from messages m join sessions s on s.id = m.session_id "
         "where m.role = 'user' and s.source in ('feishu','weixin','telegram') and m.timestamp >= ? order by m.timestamp")
    n = 0
    idx = {}
    for sid, source, mid, ts, content in con.execute(q, (SINCE,)):
        t = text_of(content).strip()
        if not t:
            continue
        idx[sid] = idx.get(sid, -1) + 1
        iso = datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).isoformat(timespec="seconds")
        print(json.dumps({"src": "phone-" + source, "session": sid, "uuid": "hermes-msg-%s" % mid, "ts": iso, "project": "hermes-director",
                          "chars": len(t), "text": redact(t)[:1500], "idx": idx[sid]}, ensure_ascii=False))
        n += 1
    con.close()
    print("extracted %d phone messages" % n, file=sys.stderr)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
