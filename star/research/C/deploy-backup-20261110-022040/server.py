#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent Home: the start page that opens when the computer opens.

Serves index.html and a small JSON API on 127.0.0.1. What to do lives in
content.json. Progress is an append-only event log per machine
(events-<host>.jsonl), so the two machines syncing this folder through
Syncthing never write the same file. Running projects report their status
through handoff/<id>.md, written by the agent working on them.

Standard library only, so it runs on any Python 3.7+ without installing
anything.
"""

import argparse
import datetime
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import urlopen

HOME = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(HOME, "content.json")
INDEX = os.path.join(HOME, "index.html")
HANDOFF_DIR = os.path.join(HOME, "handoff")
PREPARED_DIR = os.path.join(HOME, "prepared")
PUSH_DIR = os.path.join(HOME, "push")
BRIEF = os.path.join(HOME, "brief.md")
LIST_MD = os.path.join(HOME, "全部清单.md")
DEFAULT_PORT = 8777
STALE_DAYS = 2
# prepared/<item id>.<step, counted from 1>.<ext> marks that step as ready
PREPARED_NAME = re.compile(r"^([a-z0-9-]+)\.(\d+)\.[A-Za-z0-9]+$")
TEXT_EXTS = {"md", "txt", "csv", "json", "html"}
VAULT = os.path.dirname(HOME)
DOCS = {
    "readme": ("怎么用这个首页", os.path.join(HOME, "README.md")),
    "list": ("全部清单", LIST_MD),
    "kickoff": ("台式机开工说明", os.path.join(VAULT, "incoming", "KICKOFF.md")),
    "hermes": ("Hermes 说明书", os.path.join(VAULT, "templates", "HERMES_DAILY_PREP.md")),
    "handoff": ("交接规则", os.path.join(VAULT, "templates", "HANDOFF_RULE.md")),
}

HOST_RAW = socket.gethostname()
HOST = re.sub(r"[^A-Za-z0-9_-]", "_", HOST_RAW) or "host"
EVENTS = os.path.join(HOME, "events-%s.jsonl" % HOST)

EVENT_TYPES = {"done", "undo", "skip", "idea", "idea_edit", "idea_drop", "idea_note", "promote",
               "suggest_ok", "suggest_no"}
CARD_KINDS = {"running", "explore", "light"}
STATUSES = {"running", "explore", "paused", "pool", "frozen"}
EMPTY = {"", "无", "没有", "暂无", "none", "n/a", "-"}

LOCK = threading.Lock()
ALLOWED_HOSTS = set()


def state_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, "agent-home")
    os.makedirs(path, exist_ok=True)
    return path


def log(msg):
    try:
        with open(os.path.join(state_dir(), "server.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg))
    except OSError:
        pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load_content():
    with open(CONTENT, encoding="utf-8-sig") as f:
        return json.load(f)


def read_events():
    events = []
    for name in os.listdir(HOME):
        if not (name.startswith("events-") and name.endswith(".jsonl")):
            continue
        try:
            with open(os.path.join(HOME, name), encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and ev.get("type") in EVENT_TYPES:
                        events.append(ev)
        except OSError:
            continue
    events.sort(key=lambda e: str(e.get("ts", "")))
    return events


def compute_state(events):
    """Replay the event log. Syncthing conflict copies may repeat events, so dedupe by id."""
    done, last, ideas, notes, edits, status, skips, seen = {}, {}, {}, {}, {}, {}, {}, set()
    decisions, decision_times = {}, {}
    for position, ev in enumerate(events):
        eid = ev.get("id")
        if eid:
            if eid in seen:
                continue
            seen.add(eid)
        kind, item = ev["type"], ev.get("item")
        if kind in ("done", "undo") and item and isinstance(ev.get("step"), int):
            steps = done.setdefault(item, set())
            if kind == "done":
                steps.add(ev["step"])
                last[item] = ev.get("ts", "")
            else:
                steps.discard(ev["step"])
        elif kind == "idea" and ev.get("text"):
            iid = ev.get("idea_id") or eid or uuid.uuid4().hex
            ideas[iid] = {"id": iid, "text": ev["text"], "ts": ev.get("ts", ""), "host": ev.get("host", "")}
        elif kind == "idea_drop":
            ideas.pop(ev.get("idea_id"), None)
        elif kind == "idea_edit" and ev.get("idea_id") and str(ev.get("text", "")).strip():
            edits[ev["idea_id"]] = str(ev["text"]).strip()[:2000]
        elif kind == "idea_note" and ev.get("idea_id"):
            notes[ev["idea_id"]] = {"belongs": str(ev.get("belongs", ""))[:100],
                                    "first_step": str(ev.get("first_step", ""))[:500], "ts": ev.get("ts", "")}
        elif kind == "skip" and item:
            # Recorded for the review only; skips don't change which cards come up.
            skipped = skips.setdefault(item, {"count": 0, "last": ""})
            skipped["count"] += 1
            skipped["last"] = ev.get("ts", "")
        elif kind == "promote" and item and ev.get("to") in STATUSES:
            status[item] = ev["to"]
        elif kind in ("suggest_ok", "suggest_no") and ev.get("suggestion"):
            sid = str(ev["suggestion"])
            when = (str(ev.get("ts", "")), position)
            if sid not in decision_times or when >= decision_times[sid]:
                decisions[sid] = "ok" if kind == "suggest_ok" else "no"
                decision_times[sid] = when
    # Applied after the replay, so an edit or note still lands if its file is read before the idea's own.
    for iid, idea in ideas.items():
        if iid in edits:
            idea["text"] = edits[iid]
        if iid in notes:
            idea["note"] = notes[iid]
    return {
        "done": {k: sorted(v) for k, v in done.items()},
        "last": last,
        "ideas": sorted(ideas.values(), key=lambda i: i["ts"], reverse=True),
        "status": status,
        "skips": skips,
        "decisions": decisions,
    }


HANDOFF_KEYS = {"状态": "status", "下一步": "next", "卡点": "blocker", "需要你": "needs_you", "更新": "updated"}
HANDOFF_LINE = re.compile(r"^\s*[-*]?\s*(状态|下一步|卡点|需要你|更新)\s*[：:]\s*(.*?)\s*$")


def filled(value):
    return value.strip().strip("。.").lower() not in EMPTY


def read_handoffs():
    out = {}
    if not os.path.isdir(HANDOFF_DIR):
        return out
    for name in os.listdir(HANDOFF_DIR):
        if not name.endswith(".md") or name.startswith(".") or ".sync-conflict-" in name:
            continue
        path = os.path.join(HANDOFF_DIR, name)
        mtime = os.path.getmtime(path)
        info = {"mtime": datetime.datetime.fromtimestamp(mtime).isoformat(timespec="minutes"),
                "stale": time.time() - mtime > STALE_DAYS * 86400}
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    m = HANDOFF_LINE.match(line)
                    if m:
                        info[HANDOFF_KEYS[m.group(1)]] = m.group(2)
        except OSError:
            continue
        st = info.get("status", "")
        info["waiting"] = "等你" in st or "卡住" in st or filled(info.get("needs_you", ""))
        out[name[:-3]] = info
    return out


def read_prepared():
    """{item id: {step index as str: file name}} from prepared/, written by Hermes or Claude."""
    out = {}
    if not os.path.isdir(PREPARED_DIR):
        return out
    for name in sorted(os.listdir(PREPARED_DIR)):
        m = PREPARED_NAME.match(name)
        if m and ".sync-conflict-" not in name and int(m.group(2)) >= 1:
            out.setdefault(m.group(1), {}).setdefault(str(int(m.group(2)) - 1), name)
    return out


def read_brief():
    """The daily one-liner Hermes writes. Plain text, so a bad write can't break the page."""
    try:
        with open(BRIEF, encoding="utf-8-sig", errors="replace") as f:
            lines = [line.strip() for line in f.read().splitlines() if line.strip()][:6]
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(BRIEF)).isoformat(timespec="minutes")
    except OSError:
        return None
    return {"lines": [line[:200] for line in lines], "mtime": mtime} if lines else None


def _load_push_plan():
    """(plan, window start, window end, per_day, units), or None if unusable."""
    try:
        with open(os.path.join(PUSH_DIR, "plan.json"), encoding="utf-8-sig", errors="replace") as f:
            plan = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(plan, dict):
        return None
    window, units, per_day = plan.get("window"), plan.get("units"), plan.get("per_day")
    if not isinstance(window, (list, tuple)) or len(window) != 2 or not isinstance(units, list):
        return None
    if isinstance(per_day, bool) or not isinstance(per_day, int) or per_day < 0:
        return None
    try:
        start = datetime.date.fromisoformat(str(window[0]))
        end = datetime.date.fromisoformat(str(window[1]))
    except ValueError:
        return None
    return plan, start, end, per_day, units


def _load_horizon_statuses():
    """{todo id: status}; a missing or broken snapshot means nothing is done."""
    path = os.path.join(HOME, "horizon-todos.json")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not isinstance(data.get("todos"), list):
        return {}
    statuses = {}
    for todo in data["todos"]:
        if isinstance(todo, dict) and todo.get("id") is not None:
            statuses[str(todo["id"])] = str(todo.get("status") or "")
    return statuses


def _push_unit_done(unit, state, horizon_statuses):
    kind = unit.get("kind")
    if kind == "home":
        item, index = unit.get("item"), unit.get("step_index")
        if item is None or not isinstance(index, int) or isinstance(index, bool):
            return False
        done = (state or {}).get("done") or {}
        return isinstance(done, dict) and index in done.get(str(item), [])
    if kind == "horizon":
        unit_id = str(unit.get("unit") or "")
        if unit_id.startswith("hz:"):
            unit_id = unit_id[len("hz:"):]
        return horizon_statuses.get(unit_id) == "done"
    return False


def _push_entry(unit):
    entry = {
        "unit": unit.get("unit"),
        "kind": unit.get("kind"),
        "title": unit.get("title", ""),
        "step": unit.get("step", ""),
    }
    if unit.get("kind") == "home":
        entry["item"] = unit.get("item")
    return entry


def _last_jsonl_line(path):
    last = ""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if line.strip():
                    last = line
    except OSError:
        return None
    return last


def _record_push_shown(date_str, items):
    """Append today's exposure once. Called only for an in-window result."""
    path = os.path.join(PUSH_DIR, "shown-%s.jsonl" % HOST)
    record = {"date": date_str, "host": HOST,
              "units": [str(item.get("unit", "")) for item in items]}
    try:
        with LOCK:
            last = _last_jsonl_line(path)
            if last:
                try:
                    previous = json.loads(last)
                    if isinstance(previous, dict) and previous.get("date") == date_str:
                        return
                except ValueError:
                    pass
            with open(path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
    except (OSError, TypeError, ValueError) as exc:
        log("push exposure write failed: %r" % exc)


def read_push(state, today=None):
    loaded = _load_push_plan()
    if loaded is None:
        return None
    plan, window_start, window_end, per_day, units = loaded
    if today is None:
        today = datetime.date.today()
    elif isinstance(today, datetime.datetime):
        today = today.date()
    if not isinstance(today, datetime.date):
        return None
    window = list(plan["window"])
    if not (window_start <= today < window_end):
        return {"active": False, "window": window}

    need_horizon = any(isinstance(unit, dict) and unit.get("kind") == "horizon" for unit in units)
    horizon_statuses = _load_horizon_statuses() if need_horizon else {}
    candidates = [unit for unit in units
                  if isinstance(unit, dict) and not _push_unit_done(unit, state, horizon_statuses)]
    selected = []
    if candidates:
        start = (today.toordinal() * per_day) % len(candidates)
        selected = [candidates[(start + i) % len(candidates)]
                    for i in range(min(per_day, len(candidates)))]
    items = [_push_entry(unit) for unit in selected]
    result = {"active": True, "date": today.isoformat(), "items": items, "left": len(candidates)}
    _record_push_shown(today.isoformat(), items)
    return result


def _load_suggestions():
    items = []
    try:
        with open(os.path.join(PUSH_DIR, "suggestions.jsonl"),
                  encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                    items.append(item)
    except OSError:
        return []
    return items


def read_suggestions(state):
    decided = (state or {}).get("decisions") or {}
    if not isinstance(decided, dict):
        decided = {}
    return [item for item in _load_suggestions() if str(item["id"]) not in decided]


def effective_status(item, state):
    return state["status"].get(item["id"], item["status"])


def next_step(item, state, ready=None):
    """First undone step; given `ready`, an undone step that's already prepared comes first."""
    done = set(state["done"].get(item["id"], []))
    undone = [i for i in range(len(item["steps"])) if i not in done]
    if ready:
        for i in undone:
            if str(i) in ready:
                return i
    return undone[0] if undone else None


def make_card(kind, item, state, handoffs, group_names, prepared):
    total = len(item["steps"])
    done_n = len([i for i in state["done"].get(item["id"], []) if i < total])
    card = {"kind": kind, "item": item["id"], "title": item["title"],
            "group": group_names.get(item["group"], ""), "progress": [done_n, total]}
    handoff = handoffs.get(item.get("handoff") or item["id"]) if kind == "running" else None
    if handoff:
        card["handoff"] = handoff
    if handoff and filled(handoff.get("next", "")):
        notes = []
        if filled(handoff.get("needs_you", "")):
            notes.append("需要你：" + handoff["needs_you"])
        if filled(handoff.get("blocker", "")):
            notes.append("卡点：" + handoff["blocker"])
        card["source"] = "handoff"
        card["step_index"] = None
        card["step"] = {"t": handoff["next"], "d": "；".join(notes)}
    else:
        ready = prepared.get(item["id"], {})
        idx = next_step(item, state, ready)
        card["source"] = "steps"
        card["step_index"] = idx
        card["step"] = item["steps"][idx] if idx is not None else None
        card["ready"] = ready.get(str(idx)) if idx is not None else None
    return card


def compute_today(content, state, handoffs, shifts, prepared):
    items = content["items"]
    order = {g["id"]: i for i, g in enumerate(content["groups"])}
    names = {g["id"]: g["name"] for g in content["groups"]}
    day = datetime.date.today().toordinal()

    def key(it):
        return (order.get(it["group"], 99), it.get("order", 99))

    def open_steps(it):
        return next_step(it, state) is not None

    def ready_now(it):
        ready = prepared.get(it["id"], {})
        idx = next_step(it, state, ready)
        return idx is not None and str(idx) in ready

    cards = []

    running = sorted([it for it in items if effective_status(it, state) == "running"], key=key)
    if running:
        def priority(it):
            h = handoffs.get(it.get("handoff") or it["id"])
            if h and h.get("waiting"):
                return 0
            if ready_now(it):
                return 1
            if not h:
                return 2 if open_steps(it) else 4
            return 3
        best = min(priority(it) for it in running)
        bucket = [it for it in running if priority(it) == best]
        pick = bucket[(day + shifts.get("running", 0)) % len(bucket)]
        cards.append(make_card("running", pick, state, handoffs, names, prepared))

    explore = sorted([it for it in items
                      if effective_status(it, state) in ("explore", "paused")
                      and not it.get("light") and not it.get("wait") and open_steps(it)], key=key)
    if explore:
        # Prepared steps first (the easiest start); after that keep going with whatever was
        # last worked on, and only rotate by day when nothing is in progress.
        ready = [it for it in explore if ready_now(it)]
        rest = [it for it in explore if it not in ready]
        if rest:
            started = [it for it in rest if it["id"] in state["last"]]
            start = rest.index(max(started, key=lambda it: state["last"][it["id"]])) if started else day % len(rest)
            rest = rest[start:] + rest[:start]
        ordered = ready + rest
        pick = ordered[shifts.get("explore", 0) % len(ordered)]
        cards.append(make_card("explore", pick, state, handoffs, names, prepared))

    light = sorted([it for it in items
                    if it.get("light") and effective_status(it, state) not in ("running", "frozen")
                    and not it.get("wait") and open_steps(it)], key=key)
    if light:
        ready = [it for it in light if ready_now(it)]
        rest = [it for it in light if it not in ready]
        if rest:
            rest = rest[day % len(rest):] + rest[:day % len(rest)]
        ordered = ready + rest
        pick = ordered[shifts.get("light", 0) % len(ordered)]
        cards.append(make_card("light", pick, state, handoffs, names, prepared))

    return {"date": datetime.date.today().isoformat(), "cards": cards}


def snapshot(shifts):
    content = load_content()
    state = compute_state(read_events())
    handoffs = read_handoffs()
    prepared = read_prepared()
    running_ids = {it.get("handoff") or it["id"] for it in content["items"]
                   if effective_status(it, state) == "running"}
    waiting = sorted(h for h, info in handoffs.items() if info.get("waiting") and h in running_ids)
    return {
        "content": content,
        "state": state,
        "handoff": handoffs,
        "prepared": prepared,
        "brief": read_brief(),
        "docs": [{"key": k, "name": n, "path": p} for k, (n, p) in DOCS.items() if os.path.isfile(p)],
        "waiting": waiting,
        "stale": sorted(h for h, info in handoffs.items() if info.get("stale") and h in running_ids),
        "today": compute_today(content, state, handoffs, shifts, prepared),
        "push": read_push(state),
        "suggestions": read_suggestions(state),
        "host": HOST_RAW,
        "home": HOME,
        "now": utc_now(),
    }


def render_list():
    """全部清单.md for agents and Obsidian. Written only when it changes, so both machines regenerating it doesn't churn Syncthing."""
    snap = snapshot({})
    content, state, handoffs, prepared = snap["content"], snap["state"], snap["handoff"], snap["prepared"]
    lines = ["# 全部清单", "",
             "> 自动生成，不要手改；要改内容就改同目录的 content.json。",
             "> " + content.get("merge_note", ""), ""]
    for group in content["groups"]:
        members = sorted([it for it in content["items"] if it["group"] == group["id"]], key=lambda it: it.get("order", 99))
        if not members:
            continue
        lines += ["## " + group["name"], ""]
        for it in members:
            done = set(state["done"].get(it["id"], []))
            status = effective_status(it, state)
            skipped = state["skips"].get(it["id"], {}).get("count", 0)
            lines.append("### %s（%d/%d）%s%s" % (it["title"], len([i for i in done if i < len(it["steps"])]),
                                                len(it["steps"]), "（被跳过 %d 次）" % skipped if skipped else "",
                                                "" if status == it["status"] else "  [已改为 %s]" % status))
            if it.get("includes"):
                lines.append("包含：" + "、".join(it["includes"]))
            if it.get("wait"):
                lines.append("等待：" + it["wait"])
            h = handoffs.get(it.get("handoff") or it["id"])
            if h:
                lines.append("交接卡：状态 %s；下一步 %s；需要你 %s" % (h.get("status", "?"), h.get("next", "?"), h.get("needs_you", "无")))
            ready = prepared.get(it["id"], {})
            for i, step in enumerate(it["steps"]):
                extra = "（已备好：prepared/%s）" % ready[str(i)] if str(i) in ready else ""
                lines.append("- [%s] %s%s" % ("x" if i in done else " ", step["t"], extra))
            lines.append("")
    if state["ideas"]:
        lines += ["## 你记下的新想法", ""]
        for idea in state["ideas"]:
            note = idea.get("note")
            if note and note["first_step"]:
                tag = "（属于 %s；第一步：%s）" % (note["belongs"], note["first_step"])
            elif note:
                tag = "（属于 %s；待补第一步）" % note["belongs"]
            else:
                tag = "（待补第一步）"
            lines.append("- %s %s%s" % (idea["ts"][:10], idea["text"], tag))
        lines.append("")
    text = "\n".join(lines)
    try:
        with open(LIST_MD, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    tmp = LIST_MD + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, LIST_MD)


def render_list_safely():
    try:
        render_list()
    except Exception as exc:  # the page must keep working even if the export fails
        log("render_list failed: %r" % exc)


def write_today(port):
    """today-<host>.json: today's three cards for Hermes to push to the phone. One file per machine, rewritten only on change."""
    snap = snapshot({})
    titles = {it.get("handoff") or it["id"]: it["title"] for it in snap["content"]["items"]}
    data = {
        "date": snap["today"]["date"],
        "host": HOST_RAW,
        "url": "http://127.0.0.1:%d/" % port,
        "cards": [{"kind": c["kind"], "title": c["title"], "step": (c.get("step") or {}).get("t", ""),
                   "min": (c.get("step") or {}).get("min"), "ready": bool(c.get("ready"))}
                  for c in snap["today"]["cards"]],
        "waiting": [titles.get(h, h) for h in snap["waiting"]],
        "stale": [titles.get(h, h) for h in snap["stale"]],
        "ideas_pending": len([i for i in snap["state"]["ideas"] if not (i.get("note") or {}).get("first_step")]),
    }
    text = json.dumps(data, ensure_ascii=False, indent=1)
    path = os.path.join(HOME, "today-%s.json" % HOST)
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def write_today_safely(port):
    try:
        write_today(port)
    except Exception as exc:
        log("write_today failed: %r" % exc)


def today_loop(port):
    while True:
        write_today_safely(port)
        time.sleep(600)


def validate(body, item_ids):
    if not isinstance(body, dict):
        return None, "bad body"
    kind = body.get("type")
    if kind not in EVENT_TYPES:
        return None, "bad type"
    ev = {"id": uuid.uuid4().hex, "ts": utc_now(), "host": HOST_RAW, "type": kind}
    if kind in ("done", "undo"):
        step = body.get("step")
        if body.get("item") not in item_ids or not isinstance(step, int) or isinstance(step, bool) or step < 0:
            return None, "bad step"
        ev.update(item=body["item"], step=step)
    elif kind == "skip":
        step = body.get("step")
        bad_step = step is not None and (not isinstance(step, int) or isinstance(step, bool) or step < 0)
        if body.get("item") not in item_ids or body.get("kind") not in CARD_KINDS or bad_step:
            return None, "bad skip"
        ev.update(item=body["item"], kind=body["kind"], step=step)
    elif kind == "idea":
        text = str(body.get("text", "")).strip()
        if not text or len(text) > 2000:
            return None, "bad text"
        ev.update(text=text, idea_id=ev["id"])
    elif kind == "idea_drop":
        if not body.get("idea_id"):
            return None, "bad idea"
        ev["idea_id"] = str(body["idea_id"])[:64]
    elif kind == "idea_edit":
        text = str(body.get("text", "")).strip()
        if not body.get("idea_id") or not text or len(text) > 2000:
            return None, "bad edit"
        ev.update(idea_id=str(body["idea_id"])[:64], text=text)
    elif kind == "idea_note":
        # first_step may be empty: the idea then has a home but is still waiting for its first step.
        if not body.get("idea_id"):
            return None, "bad note"
        ev.update(idea_id=str(body["idea_id"])[:64], belongs=str(body.get("belongs", ""))[:100],
                  first_step=str(body.get("first_step", "")).strip()[:500])
    elif kind == "promote":
        if body.get("item") not in item_ids or body.get("to") not in STATUSES:
            return None, "bad promote"
        ev.update(item=body["item"], to=body["to"])
    elif kind in ("suggest_ok", "suggest_no"):
        suggestion_id = body.get("suggestion")
        suggestion = next((item for item in _load_suggestions()
                           if item["id"] == suggestion_id), None) if isinstance(suggestion_id, str) else None
        if suggestion is None:
            return None, "bad suggestion"
        ev.update(suggestion=suggestion_id, unit=suggestion.get("unit"))
    return ev, None


def append_event(ev):
    with LOCK:
        with open(EVENTS, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def shifts_from(query):
    shifts = {}
    for kind in ("running", "explore", "light"):
        try:
            shifts[kind] = int(query.get("shift_" + kind, ["0"])[0])
        except ValueError:
            shifts[kind] = 0
    return shifts


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentHome/1"

    def log_message(self, fmt, *args):
        # pythonw has no stderr; keep the default access log quiet.
        pass

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _trusted(self):
        # Only answer requests addressed to this machine's loopback name, and
        # only accept writes from this page, so other websites can't read or
        # write through the browser.
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return origin is None or urlparse(origin).netloc in ALLOWED_HOSTS

    def do_GET(self):
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                with open(INDEX, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/health":
                return self._json({"ok": True, "host": HOST_RAW})
            if url.path.startswith("/prepared/"):
                return self._prepared(unquote(url.path[len("/prepared/"):]))
            if url.path.startswith("/docs/"):
                doc = DOCS.get(url.path[len("/docs/"):])
                if not doc or not os.path.isfile(doc[1]):
                    return self._json({"error": "not found"}, 404)
                with open(doc[1], "rb") as f:
                    return self._send(200, f.read(), "text/plain; charset=utf-8")
            if url.path == "/api/all":
                return self._json(snapshot(shifts_from(parse_qs(url.query))))
            if url.path == "/api/today":
                return self._json(snapshot(shifts_from(parse_qs(url.query)))["today"])
            return self._json({"error": "not found"}, 404)
        except Exception as exc:
            log("GET %s failed: %r" % (url.path, exc))
            return self._json({"error": "server error"}, 500)

    def _prepared(self, name):
        path = os.path.join(PREPARED_DIR, name)
        if not name or "/" in name or "\\" in name or name.startswith(".") or not os.path.isfile(path):
            return self._json({"error": "not found"}, 404)
        with open(path, "rb") as f:
            data = f.read()
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in TEXT_EXTS:
            # Shown as plain text, so nothing in a prepared file can run as a page.
            return self._send(200, data, "text/plain; charset=utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._trusted():
            return self._json({"error": "forbidden"}, 403)
        url = urlparse(self.path)
        if url.path != "/api/event":
            return self._json({"error": "not found"}, 404)
        if "application/json" not in self.headers.get("Content-Type", ""):
            return self._json({"error": "json only"}, 415)
        size = int(self.headers.get("Content-Length") or 0)
        if size <= 0 or size > 20000:
            return self._json({"error": "bad size"}, 400)
        try:
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            ev, err = validate(body, {it["id"] for it in load_content()["items"]})
            if err:
                return self._json({"error": err}, 400)
            append_event(ev)
            render_list_safely()
            write_today_safely(self.server.server_address[1])
            return self._json({"ok": True, "event": ev, "snapshot": snapshot(shifts_from(parse_qs(url.query)))})
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        except Exception as exc:
            log("POST failed: %r" % exc)
            return self._json({"error": "server error"}, 500)


class HomeServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a second process bind the same port and the two then split
    # requests between them. Refuse instead, so a second copy sees the port taken and steps aside.
    allow_reuse_address = os.name != "nt"


def healthy(port):
    try:
        with urlopen("http://127.0.0.1:%d/health" % port, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def in_wsl():
    return "microsoft" in platform.uname().release.lower()


def open_page(url):
    try:
        with open(os.path.join(state_dir(), "last_open.txt"), "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass
    if in_wsl():
        subprocess.Popen(["cmd.exe", "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description="Agent Home start page")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENT_HOME_PORT", DEFAULT_PORT)))
    parser.add_argument("--open", action="store_true", help="open the page in the browser once the server is up")
    args = parser.parse_args()

    ALLOWED_HOSTS.update({"localhost:%d" % args.port, "127.0.0.1:%d" % args.port})
    url = "http://127.0.0.1:%d/" % args.port
    os.makedirs(HANDOFF_DIR, exist_ok=True)
    try:
        httpd = HomeServer(("127.0.0.1", args.port), Handler)
    except OSError:
        if healthy(args.port):
            if args.open:
                open_page(url)
            return 0
        log("port %d is taken by something else" % args.port)
        return 1
    log("serving %s from %s" % (url, HOME))
    render_list_safely()
    threading.Thread(target=today_loop, args=(args.port,), daemon=True).start()
    if args.open:
        threading.Timer(0.5, open_page, [url]).start()
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
