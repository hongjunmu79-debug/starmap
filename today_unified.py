#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The one ordered list of what to do today. The home page, the phone and Feishu all read it.

Pure functions: server.py reads the files and passes the data in, so this module never
touches the disk. Standard library only.
"""

import datetime
import hashlib
import json
import re

BEIJING = datetime.timezone(datetime.timedelta(hours=8))
UTC = datetime.timezone.utc
VISIBLE = 4
CARD_KINDS = ("running", "explore", "light")
CARD_TAGS = {"running": "在跑", "explore": "探索", "light": "轻量"}
CARD_BLOCKS = {"running": 1, "explore": 5, "light": 6}
ACTIVE = ("pending", "doing", "needs_review")
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}
TODO_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Rows come out in this order: running card, pushes, overdue P0, due today,
# explore card, light card, the other overdue rows.
BLOCK_PUSH = 2
BLOCK_OVERDUE_P0 = 3
BLOCK_TODAY = 4
BLOCK_OVERDUE_REST = 7


def bj_today(now=None):
    """Beijing calendar date (UTC+8) of `now`, default the current time. A naive `now` counts as UTC."""
    if now is None:
        now = datetime.datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(BEIJING).date()


def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def _parse_ts(value):
    """Aware datetime for an ISO timestamp (naive means UTC); None when it cannot be read."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _bj_date_of(value):
    parsed = _parse_ts(value)
    return None if parsed is None else parsed.astimezone(BEIJING).date()


def _due_date(value):
    """'2026-11-03' -> date. Anything else means no due date."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        return None


def _is_index(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _minutes(step):
    value = step.get("min") if isinstance(step, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _hz_is_done(event):
    """hz_done carries a boolean; a missing value means done, as validate() in server.py does."""
    return event.get("done", True) is not False


def _events_once(events):
    """The event dicts in order, each id once: Syncthing conflict copies can repeat a line."""
    seen = set()
    for event in events or []:
        if not isinstance(event, dict):
            continue
        event_id = event.get("id")
        if isinstance(event_id, str) and event_id:
            if event_id in seen:
                continue
            seen.add(event_id)
        yield event


def skipped_items(events, today):
    """{card kind: set of item ids} skipped with 换一个 on `today` (Beijing date)."""
    day = _as_date(today)
    out = {kind: set() for kind in CARD_KINDS}
    for event in _events_once(events):
        if (event.get("type") == "skip" and event.get("kind") in CARD_KINDS and event.get("item")
                and _bj_date_of(event.get("ts")) == day):
            out[event["kind"]].add(str(event["item"]))
    return out


def _done_today(events, day):
    count = 0
    for event in _events_once(events):
        kind = event.get("type")
        if kind not in ("done", "undo", "hz_done") or _bj_date_of(event.get("ts")) != day:
            continue
        if kind == "done":
            count += 1
        elif kind == "undo":
            count -= 1
        else:
            count += 1 if _hz_is_done(event) else -1
    return max(0, count)


def _latest_hz(events):
    """{todo id: {"when": datetime, "event": event}} for the newest hz_done of each todo."""
    latest = {}
    for event in _events_once(events):
        if event.get("type") != "hz_done":
            continue
        todo_id, when = event.get("todo_id"), _parse_ts(event.get("ts"))
        if not isinstance(todo_id, str) or when is None:
            continue
        current = latest.get(todo_id)
        if current is None or when >= current["when"]:
            latest[todo_id] = {"when": when, "event": event}
    return latest


def _normalize(raw):
    priority, parent = raw.get("priority"), raw.get("parent_id")
    return {
        "id": str(raw["id"]),
        "title": str(raw.get("title") or ""),
        "status": str(raw.get("status") or ""),
        "priority": priority if isinstance(priority, str) and priority in PRIORITY_RANK else None,
        "due": _due_date(raw.get("due_date")),
        "parent": str(parent) if parent not in (None, "") else None,
    }


def _todo_index(horizon):
    """{todo id: normalized todo}. A repeated id keeps its last entry, as server.py does."""
    raw = horizon.get("todos") if isinstance(horizon, dict) else None
    index = {}
    for todo in raw if isinstance(raw, list) else []:
        if isinstance(todo, dict) and todo.get("id") is not None and str(todo["id"]):
            normalized = _normalize(todo)
            index[normalized["id"]] = normalized
    return index


def _effective_status(todo, latest, generated):
    """A newer hz_done beats the snapshot, because the bridge has not written the snapshot yet."""
    status = todo["status"]
    if latest is not None and (generated is None or latest["when"] > generated):
        if _hz_is_done(latest["event"]):
            return "done"
        if status not in ACTIVE:
            return "pending"
    return status


def _root_of(todo_id, todos):
    """Follow parent links up. A parent that is not in the snapshot makes its child a root."""
    seen = set()
    current = todo_id
    while True:
        seen.add(current)
        parent = todos[current]["parent"]
        if parent is None or parent not in todos or parent in seen:
            return current
        current = parent


def _target_key(todo):
    """Earliest due first, then priority, then title: the rule for a root's next live child."""
    return (todo["due"] or datetime.date.max, PRIORITY_RANK.get(todo["priority"], 1), todo["title"], todo["id"])


def _row(row_id, kind, tag, title, next_text, item, *, due=None, overdue_days=0,
         priority=None, tickable=True, minutes=None):
    return {"id": row_id, "kind": kind, "tag": tag, "title": str(title or ""),
            "next": str(next_text or ""), "item": item, "due": due, "overdue_days": overdue_days,
            "priority": priority, "tickable": tickable, "min": minutes}


def _card_rows(cards):
    out = []
    for index, card in enumerate(cards or []):
        if not isinstance(card, dict):
            continue
        kind, item, step = card.get("kind"), card.get("item"), card.get("step")
        if not isinstance(kind, str) or kind not in CARD_TAGS or not item or not isinstance(step, dict):
            continue
        text = str(step.get("t") or "")
        if card.get("source") == "handoff":
            if not text:
                continue
            row = _row("handoff:%s" % item, "card", CARD_TAGS[kind], card.get("title"), text, item,
                       tickable=False)
        else:
            number = card.get("step_index")
            if not _is_index(number):
                continue
            row = _row("step:%s:%d" % (item, number), "card", CARD_TAGS[kind], card.get("title"),
                       text, item, minutes=_minutes(step))
        out.append((CARD_BLOCKS[kind], (index,), row, ("item", str(item))))
    return out


def _push_rows(push_units, items_by_id, todos, latest, generated, day):
    out = []
    for index, unit in enumerate(push_units or []):
        if not isinstance(unit, dict):
            continue
        if unit.get("kind") == "home":
            item = unit.get("item")
            steps = items_by_id.get(item) if isinstance(item, str) else None
            number = unit.get("step_index")
            if steps is None or not _is_index(number) or number >= len(steps):
                continue
            row = _row("step:%s:%d" % (item, number), "push", "推进", unit.get("title"), unit.get("step"),
                       item, minutes=_minutes(steps[number]))
            dedupe = ("item", item)
        elif unit.get("kind") == "horizon":
            unit_id = str(unit.get("unit") or "")
            todo_id = unit_id[len("hz:"):] if unit_id.startswith("hz:") else unit_id
            todo = todos.get(todo_id)
            if todo is None or _effective_status(todo, latest.get(todo_id), generated) not in ACTIVE:
                continue
            due = todo["due"]
            row = _row("hz:" + todo_id, "push", "推进", unit.get("title") or todo["title"], unit.get("step"),
                       None, due=due.isoformat() if due else None,
                       overdue_days=(day - due).days if due is not None and due < day else 0,
                       priority=todo["priority"])
            dedupe = ("root", _root_of(todo_id, todos))
        else:
            continue
        out.append((BLOCK_PUSH, (index,), row, dedupe))
    return out


def _horizon_rows(todos, latest, generated, day):
    """One row per Horizon root that has a live task and a due date today or earlier."""
    live = {tid for tid, todo in todos.items() if _effective_status(todo, latest.get(tid), generated) in ACTIVE}
    groups = {}
    for tid in todos:
        groups.setdefault(_root_of(tid, todos), []).append(tid)
    out = []
    for root, members in groups.items():
        live_members = [tid for tid in members if tid in live]
        if not live_members:
            continue
        late = [tid for tid in live_members if todos[tid]["due"] is not None and todos[tid]["due"] <= day]
        if not late:
            continue
        # The group is as urgent as its most urgent late member: in Horizon the P0s are subtasks under
        # P1/P2 parents, so ranking by the root's priority alone buried every P0. The row's next step
        # is that most urgent late child (P0 first, then the earliest due).
        late_children = [tid for tid in late if tid != root]
        live_children = [tid for tid in live_members if tid != root]
        if late_children:
            target = min(late_children, key=lambda tid: (PRIORITY_RANK.get(todos[tid]["priority"], 1),) + _target_key(todos[tid]))
        elif live_children:
            # Only the parent is late: tick its next open subtask, never the parent itself while subtasks are open.
            target = min(live_children, key=lambda tid: _target_key(todos[tid]))
        else:
            target = root
        due, head = min(todos[tid]["due"] for tid in late), todos[root]
        rank = min(PRIORITY_RANK.get(todos[tid]["priority"], 1) for tid in late)
        overdue = due < day
        if overdue and rank == 0:
            block, key = BLOCK_OVERDUE_P0, (due, head["title"], target)
        elif overdue:
            block, key = BLOCK_OVERDUE_REST, (rank, due, head["title"], target)
        else:
            block, key = BLOCK_TODAY, (rank, head["title"], target)
        row = _row("hz:" + target, "horizon", "逾期" if overdue else "今天", head["title"],
                   "" if target == root else todos[target]["title"], None,
                   due=due.isoformat(), overdue_days=(day - due).days if overdue else 0,
                   priority={0: "P0", 1: "P1", 2: "P2"}[rank])
        out.append((block, key, row, ("root", root)))
    return out


def build(*, cards, push_units, horizon, events, items, today, url):
    """The unified list: {date, rev, done_today, visible, more, url, items}. Only unfinished rows are listed."""
    day = _as_date(today)
    generated = _parse_ts(horizon.get("generated_at")) if isinstance(horizon, dict) else None
    todos = _todo_index(horizon)
    latest = _latest_hz(events)
    items_by_id = {}
    for item in items or []:
        if isinstance(item, dict) and item.get("id") is not None:
            steps = item.get("steps")
            items_by_id[str(item["id"])] = steps if isinstance(steps, list) else []
    candidates = (_card_rows(cards)
                  + _push_rows(push_units, items_by_id, todos, latest, generated, day)
                  + _horizon_rows(todos, latest, generated, day))
    candidates.sort(key=lambda entry: (entry[0], entry[1]))
    rows, kept = [], set()
    for _block, _key, row, dedupe in candidates:
        if dedupe not in kept:
            kept.add(dedupe)
            rows.append(row)
    done = _done_today(events, day)
    date_text = day.isoformat()
    digest = json.dumps({"date": date_text, "done_today": done,
                         "rows": [[row["id"], row["tag"], row["next"]] for row in rows]},
                        ensure_ascii=False, sort_keys=True)
    return {"date": date_text, "rev": hashlib.sha1(digest.encode("utf-8")).hexdigest()[:12],
            "done_today": done, "visible": VISIBLE, "more": max(0, len(rows) - VISIBLE),
            "url": url, "items": rows}


def render_feishu(unified):
    """Plain text for Feishu: date and done count, the visible rows, then how many more are left."""
    lines = ["今天 %s · 已完成 %d 件" % (unified["date"][5:], unified["done_today"])]
    if not unified["items"]:
        lines.append("今天没有要做的")
    for number, row in enumerate(unified["items"][:VISIBLE], 1):
        text = "%d.【%s】%s" % (number, row["tag"], row["title"])
        if row["next"]:
            text += "｜" + row["next"]
        if row["overdue_days"]:
            text += "（逾期 %d 天）" % row["overdue_days"]
        lines.append(text)
    if unified["more"]:
        lines.append("还有 %d 件 · %s" % (unified["more"], unified["url"]))
    return "\n".join(lines)
