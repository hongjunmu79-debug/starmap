#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Horizon todos on the home page: each open root with its open children, grouped under the home item
or label it belongs to.

Pure functions: server.py reads the files and passes the data in, so this module never touches the disk.
The root rule and the optimistic-completion rule (a newer hz_done beats the snapshot) come from today_unified.
Standard library plus today_unified only.

build() returns {"copy", "rev", "counts": {"open", "overdue"}, "choices", "groups"}.
"""

import datetime
import hashlib
import json
import re

import today_unified as tu

ITEM_GROUP = re.compile(r"item:([A-Za-z0-9_-]{1,64})")
LABEL_MAX = 20
HOME_PREFIX = "home:"
PENDING_PREFIX = "new:"
OTHER_TITLE = "其他"
EPOCH = datetime.datetime.min.replace(tzinfo=tu.UTC)


def parse_group(group):
    """("item", id) or ("label", name) for a well-formed group string; None for "" and for anything else.

    build() checks that the item exists, so a stale item id reads as ungrouped.
    """
    if not isinstance(group, str):
        return None
    if group.startswith("item:"):
        match = ITEM_GROUP.fullmatch(group)
        return ("item", match.group(1)) if match else None
    if group.startswith("label:"):
        name = group[len("label:"):].strip()
        return ("label", name) if 1 <= len(name) <= LABEL_MAX else None
    return None


def _group_key(group, item_ids):
    parsed = parse_group(group)
    if parsed is None:
        return ""
    kind, value = parsed
    if kind == "item":
        return "item:" + value if value in item_ids else ""
    return "label:" + value


def _due_key(due):
    """Earliest due date first; a todo without one goes last."""
    return (due is None, due or datetime.date.max)


def _rank(priority):
    return tu.PRIORITY_RANK.get(priority, 1)


def _days_overdue(due, day, is_open):
    return (day - due).days if is_open and due is not None and due < day else 0


def _iso(due):
    return due.isoformat() if due is not None else None


def _ancestors(todo_id, index):
    """The parents above a todo, nearest first, along the same links today_unified._root_of follows."""
    found, seen, parent = [], {todo_id}, index[todo_id]["parent"]
    while parent is not None and parent in index and parent not in seen:
        found.append(parent)
        seen.add(parent)
        parent = index[parent]["parent"]
    return found


def _home_items(items, groups_order):
    """(item ids in home order, {item id: title}). Home order: the content groups in their order, then each
    item's order; an item whose group is not in the content goes last."""
    rank = {}
    for position, group_id in enumerate(groups_order or []):
        rank.setdefault(str(group_id), position)
    unknown = len(rank)
    entries, seen = [], set()
    for position, item in enumerate(items or []):
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        item_id = str(item["id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        group, order = item.get("group"), item.get("order")
        group_rank = rank.get(group, unknown) if isinstance(group, str) else unknown
        order = order if isinstance(order, int) and not isinstance(order, bool) else 99
        entries.append(((group_rank, order, position), item_id, str(item.get("title") or item_id)))
    entries.sort(key=lambda entry: entry[0])
    return [item_id for _key, item_id, _title in entries], {item_id: title for _key, item_id, title in entries}


def _assign_table(events):
    """{todo id: ((ts, line), hz_assign event)}: the newest hz_assign of each todo.

    Equal timestamps go to the later line, because utc_now() has one-second resolution.
    """
    table = {}
    for line, event in enumerate(tu._events_once(events)):
        if event.get("type") != "hz_assign":
            continue
        todo_id = event.get("todo_id")
        if not isinstance(todo_id, str) or not todo_id:
            continue
        key = (tu._parse_ts(event.get("ts")) or EPOCH, line)
        current = table.get(todo_id)
        if current is None or key > current[0]:
            table[todo_id] = (key, event)
    return table


def _new_todos(events):
    """{event id: hz_new event} for the todos made on the home page."""
    found = {}
    for event in tu._events_once(events):
        if event.get("type") == "hz_new" and isinstance(event.get("id"), str) and event["id"]:
            found[event["id"]] = event
    return found


def _chosen_assign(keys, table):
    """The newest hz_assign among the keys (a root's own id, and the home event it was made from), or None."""
    best = None
    for key in keys:
        entry = table.get(key)
        if entry is not None and (best is None or entry[0] > best[0]):
            best = entry
    return best[1] if best is not None else None


def build(*, todos_snapshot, events, items, groups_order, today, copy):
    """The board for GET /api/todos and for the POST answers.

    todos_snapshot is horizon-todos.json (or {}), events is every event, items is the content items, and
    groups_order is the content group ids in their order. The rev is a hash of the rest of the output.
    """
    day = tu._as_date(today)
    snapshot = todos_snapshot if isinstance(todos_snapshot, dict) else {}
    generated = tu._parse_ts(snapshot.get("generated_at"))
    index = tu._todo_index(snapshot)
    latest = tu._latest_hz(events)
    table = _assign_table(events)
    new_todos = _new_todos(events)
    home_ids, titles = _home_items(items, groups_order)
    item_ids = set(home_ids)

    raw_todos = snapshot.get("todos") if isinstance(snapshot.get("todos"), list) else []
    origin_of, synced = {}, set()
    for raw in raw_todos:
        if not isinstance(raw, dict) or raw.get("id") is None:
            continue
        message = raw.get("source_msg_id")
        if isinstance(message, str) and message.startswith(HOME_PREFIX):
            origin_of[str(raw["id"])] = message[len(HOME_PREFIX):]
            synced.add(message[len(HOME_PREFIX):])

    status = {tid: tu._effective_status(todo, latest.get(tid), generated) for tid, todo in index.items()}
    live = {tid for tid, value in status.items() if value in tu.ACTIVE}
    root_of = {tid: tu._root_of(tid, index) for tid in index}
    below, children = {}, {}
    for tid in live:
        for ancestor in _ancestors(tid, index):
            below[ancestor] = below.get(ancestor, 0) + 1
        if root_of[tid] != tid:
            children.setdefault(root_of[tid], []).append(tid)

    rows_by_group, group_of_root = {}, {}
    for tid, todo in index.items():
        if root_of[tid] != tid or (tid not in live and not below.get(tid)):
            continue
        is_open, due = tid in live, todo["due"]
        kids = sorted(children.get(tid, []), key=lambda kid: (
            _due_key(index[kid]["due"]), _rank(index[kid]["priority"]), index[kid]["title"], kid))
        child_rows, child_overdue = [], False
        for kid in kids:
            kid_todo = index[kid]
            if kid_todo["due"] is not None and kid_todo["due"] < day:
                child_overdue = True
            child_rows.append({"id": kid, "title": kid_todo["title"], "priority": kid_todo["priority"],
                               "due": _iso(kid_todo["due"]),
                               "overdue_days": _days_overdue(kid_todo["due"], day, True),
                               "status": status[kid], "tickable": not below.get(kid)})
        origin = origin_of.get(tid)
        assigned = _chosen_assign([tid] + ([origin] if origin else []), table)
        if assigned is not None:
            group_raw, auto = assigned.get("group"), assigned.get("auto") is True
        else:
            # The group the home page gave it is only the fallback; any hz_assign beats it, whatever its time.
            group_raw, auto = (new_todos[origin].get("group") if origin in new_todos else ""), False
        overdue = (is_open and due is not None and due < day) or child_overdue
        row = {"id": tid, "title": todo["title"], "priority": todo["priority"], "due": _iso(due),
               "overdue_days": _days_overdue(due, day, is_open), "status": status[tid], "pending": False,
               "tickable": not below.get(tid), "auto": auto, "open_children": below.get(tid, 0),
               "children": child_rows}
        group_key = _group_key(group_raw, item_ids)
        sort_key = (0 if overdue else 1, _rank(todo["priority"]), _due_key(due), todo["title"], tid)
        rows_by_group.setdefault(group_key, []).append((sort_key, row, overdue))
        group_of_root[tid] = group_key

    for eid, event in new_todos.items():
        if eid in synced:
            continue
        due = tu._due_date(event.get("due_date"))
        raw_priority = event.get("priority")
        priority = raw_priority if isinstance(raw_priority, str) and raw_priority in tu.PRIORITY_RANK else None
        title = str(event.get("title") or "")
        assigned = _chosen_assign([eid], table)
        if assigned is not None:
            group_raw, auto = assigned.get("group"), assigned.get("auto") is True
        else:
            group_raw, auto = event.get("group"), False
        root_id = PENDING_PREFIX + eid
        overdue = due is not None and due < day
        row = {"id": root_id, "title": title, "priority": priority, "due": _iso(due),
               "overdue_days": _days_overdue(due, day, True), "status": "pending", "pending": True,
               "tickable": False, "auto": auto, "open_children": 0, "children": []}
        sort_key = (0 if overdue else 1, _rank(priority), _due_key(due), title, root_id)
        rows_by_group.setdefault(_group_key(group_raw, item_ids), []).append((sort_key, row, overdue))

    open_per_group = {}
    for tid in live:
        group_key = group_of_root.get(root_of[tid])
        if group_key is not None:
            open_per_group[group_key] = open_per_group.get(group_key, 0) + 1
    overdue_roots = sum(1 for entries in rows_by_group.values() for _key, _row, overdue in entries if overdue)

    order = [("item:" + item_id) for item_id in home_ids if ("item:" + item_id) in rows_by_group]
    labels = sorted((key for key in rows_by_group if key.startswith("label:")),
                    key=lambda key: key[len("label:"):])
    others = [""] if "" in rows_by_group else []
    groups = []
    for key in order + labels + others:
        entries = sorted(rows_by_group[key], key=lambda entry: entry[0])
        if key.startswith("item:"):
            item_id = key[len("item:"):]
            title = titles[item_id]
        elif key.startswith("label:"):
            item_id, title = None, key[len("label:"):]
        else:
            item_id, title = None, OTHER_TITLE
        groups.append({"key": key, "title": title, "item": item_id,
                       "open": open_per_group.get(key, 0),
                       "overdue": sum(1 for _key, _row, overdue in entries if overdue),
                       "roots": [row for _key, row, _overdue in entries]})

    choices = [{"key": "item:" + item_id, "title": titles[item_id]} for item_id in home_ids]
    label_names = sorted({key[len("label:"):] for key in rows_by_group if key.startswith("label:")})
    choices += [{"key": "label:" + name, "title": name} for name in label_names]

    body = {"copy": bool(copy), "counts": {"open": len(live), "overdue": overdue_roots},
            "choices": choices, "groups": groups}
    digest = json.dumps(body, ensure_ascii=False, sort_keys=True)
    body["rev"] = hashlib.sha1(digest.encode("utf-8")).hexdigest()[:12]
    return body
