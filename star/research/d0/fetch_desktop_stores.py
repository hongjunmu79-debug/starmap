"""Read-only: dump the desktop-side capture stores the ideas could have landed in (runs in WSL python3).
Horizon inbox/todos (opened mode=ro), project folders with dates. Output: one JSON object on stdout."""
import json, os, sqlite3, time

out = {"horizon_inbox": [], "horizon_todos": [], "projects": []}
con = sqlite3.connect("file:/home/max237/horizon/data/horizon.db?mode=ro", uri=True, timeout=5)
for r in con.execute("select id, raw_text, parse_status, created_at from inbox"):
    out["horizon_inbox"].append({"id": r[0], "text": (r[1] or "")[:400], "status": r[2], "ts": r[3]})
for r in con.execute("select id, title, coalesce(detail,''), status, priority, due_date, created_at, completed_at, parent_id from todos"):
    out["horizon_todos"].append({"id": r[0], "text": ((r[1] or "") + " " + (r[2] or ""))[:400], "title": r[1], "status": r[3], "priority": r[4],
                                 "due": r[5], "ts": r[6], "done_at": r[7], "parent": r[8]})
con.close()
root = "/mnt/d/Claude Code 工作区/projects"
for name in sorted(os.listdir(root)):
    p = os.path.join(root, name)
    if not os.path.isdir(p):
        continue
    oldest = None
    for dirpath, dirnames, filenames in os.walk(p):
        dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build")]
        for fn in filenames[:200]:
            try:
                m = os.path.getmtime(os.path.join(dirpath, fn))
            except OSError:
                continue
            oldest = m if oldest is None or m < oldest else oldest
        if dirpath.count(os.sep) - root.count(os.sep) >= 2:
            dirnames[:] = []
    readme = ""
    for cand in ("CLAUDE.md", "README.md", "intent.md"):
        f = os.path.join(p, cand)
        if os.path.isfile(f):
            try:
                readme = open(f, encoding="utf-8", errors="replace").read(300)
            except OSError:
                pass
            break
    out["projects"].append({"name": name, "oldest_file": time.strftime("%Y-%m-%d", time.localtime(oldest)) if oldest else None, "head": readme})
print(json.dumps(out, ensure_ascii=False))
