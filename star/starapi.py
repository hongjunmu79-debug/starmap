#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compose the star-map graph from the home directory's plain files.

The function in this module is deliberately read-only: the home server can call
it on every request without changing the event log.  The rules are the ones in
``star/DESIGN.md`` section 6.4.
"""

import datetime
import hashlib
import json
import logging
import math
import os
import re
import uuid

LOGGER = logging.getLogger(__name__)

BEIJING = datetime.timezone(datetime.timedelta(hours=8), "Asia/Shanghai")
STATUSES = {"running", "explore", "paused", "pool", "frozen"}
LINK_KINDS = {"extends", "supports", "contradicts", "same", "part_of"}
DEFAULT_COLOR = "#E8E4DA"
DEFAULT_BRIGHTNESS = 1.0
MAX_TEXT = 2000


def _now_date():
    return datetime.datetime.now(BEIJING).date()


def _as_date(value):
    """Accept a date, a datetime, an ISO date string, or None (Beijing today)."""
    if value is None:
        return _now_date()
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            return value.astimezone(BEIJING).date()
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8-sig") as f:
            value = json.load(f)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def _read_events(home_dir):
    """Read every events-*.jsonl, skipping unreadable files and malformed lines.

    Sorting and de-duplication mirror ``server.py``: sort by the textual ts and
    keep the first event for an id.
    """
    events = []
    try:
        names = sorted(os.listdir(home_dir))
    except OSError:
        return []
    for name in names:
        if not (name.startswith("events-") and name.endswith(".jsonl")):
            continue
        path = os.path.join(home_dir, name)
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(event, dict):
                        events.append(event)
        except OSError:
            continue
    events.sort(key=lambda event: str(event.get("ts", "")))
    ordered = []
    seen = set()
    for event in events:
        event_id = event.get("id")
        if event_id:
            event_id = event_id if isinstance(event_id, str) else str(event_id)
            if event_id in seen:
                continue
            seen.add(event_id)
        ordered.append(event)
    return ordered


def _sha1_8(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _clip(value, limit, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text[:limit] if text else default


def _short(text, limit=10):
    text = _clip(text, 400)
    for marker in ("：", ":", "（", "("):
        index = text.find(marker)
        if index > 0:
            text = text[:index]
            break
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
    except (OverflowError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _pair(a, b):
    return "|".join(sorted((str(a), str(b))))


def _content(path):
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    items = data.get("items")
    groups = data.get("groups")
    if not isinstance(items, list):
        items = []
    if not isinstance(groups, list):
        groups = []
    return data, items, groups


def _domains(path):
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    domains = data.get("domains")
    if not isinstance(domains, list):
        domains = []
    mapping = data.get("items")
    if not isinstance(mapping, dict):
        mapping = {}
    colours = {}
    for domain in domains:
        if isinstance(domain, dict) and domain.get("id"):
            colours[str(domain["id"])] = str(domain.get("color") or DEFAULT_COLOR)
    brightness = data.get("statusBrightness")
    if not isinstance(brightness, dict):
        brightness = {}
    return mapping, colours, brightness, str(data.get("unsortedColor") or DEFAULT_COLOR)


def _replay(events):
    ideas = {}
    dropped = {}
    edits = {}
    notes = {}
    statuses = {}
    actions = []
    poss_events = []
    dismissed_nodes = set()
    sequence = 0

    for event in events:
        sequence += 1
        kind = event.get("type")
        if not isinstance(kind, str):
            continue

        if kind == "idea":
            text = event.get("text")
            if not text:
                continue
            event_id = event.get("id")
            idea_id = event.get("idea_id") or event_id or uuid.uuid4().hex
            idea_id = str(idea_id)
            ideas[idea_id] = {
                "id": idea_id,
                "text": text,
                "ts": str(event.get("ts", "")),
                "host": str(event.get("host", "")),
                "via": str(event.get("via") or "home"),
                "source": event.get("source") if isinstance(event.get("source"), dict) else None,
                "parent": str(event.get("parent")) if event.get("parent") else None,
                "seq": sequence,
            }
            dropped.pop(idea_id, None)
        elif kind == "idea_drop":
            idea_id = event.get("idea_id")
            if not idea_id:
                continue
            idea_id = str(idea_id)
            if idea_id in ideas:
                dropped[idea_id] = {"idea": ideas.pop(idea_id), "event": event}
            elif idea_id in dropped:
                dropped[idea_id]["event"] = event
        elif kind == "idea_edit":
            idea_id = event.get("idea_id")
            text = str(event.get("text", "")).strip()
            if idea_id and text:
                edits[str(idea_id)] = text[:MAX_TEXT]
        elif kind == "idea_note":
            idea_id = event.get("idea_id")
            if idea_id:
                notes[str(idea_id)] = {
                    "belongs": str(event.get("belongs", ""))[:100],
                    "host": str(event.get("host", "")),
                }
        elif kind == "promote":
            item = event.get("item")
            to = event.get("to")
            if item and isinstance(to, str) and to in STATUSES:
                statuses[str(item)] = to
        elif kind in ("link", "unlink", "dismiss", "undismiss", "suggest"):
            actions.append({"seq": sequence, "type": kind, "event": event})
        elif kind == "pin":
            actions.append({"seq": sequence, "type": "pin", "event": event})
        elif kind == "edit":
            actions.append({"seq": sequence, "type": "edit", "event": event})
        elif kind == "collapse":
            actions.append({"seq": sequence, "type": "collapse", "event": event})
        elif kind == "suggest_node":
            poss_events.append({"seq": sequence, "event": event})
        elif kind == "dismiss_node":
            node = event.get("node")
            if node:
                node = str(node)
                dismissed_nodes.add(node)
                if not node.startswith("poss:"):
                    dismissed_nodes.add("poss:" + node)
        elif kind == "undismiss_node":
            node = event.get("node")
            if node:
                node = str(node)
                # Both spellings a dismiss may have used (bare id, or "poss:" + id) are cleared.
                bare = node[len("poss:"):] if node.startswith("poss:") else node
                dismissed_nodes.discard(bare)
                dismissed_nodes.discard("poss:" + bare)

    return {
        "ideas": ideas,
        "dropped": dropped,
        "edits": edits,
        "notes": notes,
        "statuses": statuses,
        "actions": actions,
        "poss_events": poss_events,
        "dismissed_nodes": dismissed_nodes,
    }


def _include_index(content_items):
    """(include id, text, item id) plus lookup maps used for merged ideas."""
    includes = []
    by_text = {}
    by_item_text = {}
    seen = set()
    for item in content_items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        item_id = str(item["id"])
        values = item.get("includes")
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            inc_id = "inc:%s:%s" % (item_id, _sha1_8(text))
            if inc_id in seen:
                continue
            seen.add(inc_id)
            includes.append({"id": inc_id, "text": text, "item": item_id})
            by_text.setdefault(text, []).append(inc_id)
            by_item_text.setdefault((item_id, text), []).append(inc_id)
    return includes, by_text, by_item_text


def _merged_target(drop_event, idea, by_text, by_item_text):
    """Return the include a dropped idea was merged into, if it can be found."""
    text = str(idea.get("text") or "").strip()
    as_text = str(drop_event.get("as") or "").strip()
    into = str(drop_event.get("into") or "").strip()
    if into.startswith("item:"):
        into = into[len("item:"):]
    needle = as_text or text
    if not needle:
        return None
    candidates = []
    if into:
        candidates = by_item_text.get((into, needle), [])
    if not candidates:
        candidates = by_text.get(needle, [])
    return candidates[0] if candidates else None


def _find_merged_inc(drop_event, idea, by_text, by_item_text):
    return _merged_target(drop_event, idea, by_text, by_item_text)


def _node_common(node_id, kind, text, group, item, ts="", via="", source=None,
                 state=None, belongs=None, parent=None):
    return {
        "id": node_id,
        "kind": kind,
        "text": text,
        "short": text if kind in ("idea", "poss") else _short(text),
        "group": group,
        "item": item,
        "ts": ts,
        "via": via,
        "source": source,
        "state": state,
        "belongs": belongs,
        "parent": parent,
        "pin": None,
        "collapsed": False,
    }


def _plan_first_steps(home_dir, today):
    """{item id: {"text": step, "unit": unit}} when today is inside the plan window."""
    plan = _read_json(os.path.join(home_dir, "push", "plan.json"), {})
    if not isinstance(plan, dict):
        return {}
    window = plan.get("window")
    units = plan.get("units")
    if not isinstance(window, (list, tuple)) or len(window) != 2 or not isinstance(units, list):
        return {}
    try:
        start = datetime.date.fromisoformat(str(window[0]))
        end = datetime.date.fromisoformat(str(window[1]))
    except (TypeError, ValueError):
        return {}
    day = _as_date(today)
    if day is None or not (start <= day < end):
        return {}
    out = {}
    for unit in units:
        if not isinstance(unit, dict) or unit.get("kind") != "home":
            continue
        item = unit.get("item")
        step = unit.get("step")
        unit_id = unit.get("unit")
        if not item or not step or not unit_id:
            continue
        item = str(item)
        if item not in out:
            out[item] = {"text": str(step), "unit": str(unit_id)}
    return out


def build_graph(home_dir, today=None, domains_path=None):
    """Return the version-1 star graph for ``home_dir``.

    Only files are read.  The home server's event log is replayed here rather
    than imported, because importing ``server`` would create a cycle when the
    server itself imports this module.
    """
    home_dir = os.path.abspath(str(home_dir))
    _, content_items, content_groups = _content(os.path.join(home_dir, "content.json"))
    dpath = domains_path or os.path.join(home_dir, "star", "domains.json")
    if not os.path.isfile(dpath) and domains_path is None:
        fallback = os.path.abspath(os.path.join(home_dir, "..", "..", "domains.json"))
        if os.path.isfile(fallback):
            dpath = fallback
    domain_by_item, colours, brightness, unsorted_colour = _domains(dpath)

    events = _read_events(home_dir)
    state = _replay(events)

    includes, inc_by_text, inc_by_item_text = _include_index(content_items)
    item_nodes = {}
    nodes = []

    for item in content_items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        item_id = str(item["id"])
        title = str(item.get("title") or item_id)
        base_status = item.get("status") if isinstance(item.get("status"), str) else ""
        status = state["statuses"].get(item_id, base_status)
        if status not in STATUSES:
            status = base_status
        domain = domain_by_item.get(item_id)
        domain = str(domain) if domain else None
        colour = colours.get(domain, unsorted_colour) if domain else unsorted_colour
        value = brightness.get(status, DEFAULT_BRIGHTNESS)
        try:
            value = float(value)
        except (TypeError, ValueError, OverflowError):
            value = DEFAULT_BRIGHTNESS
        node = _node_common(
            "item:" + item_id, "item", title, str(item.get("group") or ""), item_id,
            state=None, belongs=None, parent=None)
        node.update({
            "title": title,
            "status": status,
            "domain": domain,
            "brightness": value,
            "color": colour,
        })
        item_nodes[item_id] = node
        nodes.append(node)

    for inc in includes:
        parent = item_nodes.get(inc["item"])
        node = _node_common(
            inc["id"], "inc", inc["text"], parent["group"] if parent else "",
            inc["item"], state=None, belongs=None, parent="item:" + inc["item"])
        nodes.append(node)

    notes = state["notes"]
    edits = state["edits"]
    idea_nodes = {}

    # Ideas still in the pool.
    for idea_id, idea in state["ideas"].items():
        text = edits.get(idea_id, idea["text"])
        node = _node_common(
            "idea:" + idea_id, "idea", text, "pool", None,
            ts=idea["ts"], via=idea.get("via") or "home", source=idea.get("source"),
            state="pool", belongs=None, parent=idea.get("parent"))
        note = notes.get(idea_id)
        if note and note.get("belongs"):
            node["belongs"] = note["belongs"]
        idea_nodes[idea_id] = node
        nodes.append(node)

    # Dropped ideas: reason star remains in the map; merged/deleted do not.
    alias = {}
    for idea_id, info in state["dropped"].items():
        drop_event = info["event"]
        idea = info["idea"]
        merge_idea = dict(idea)
        merge_idea["text"] = edits.get(idea_id, idea["text"])
        reason = str(drop_event.get("reason") or "")
        if reason == "merged":
            target = _find_merged_inc(drop_event, merge_idea, inc_by_text, inc_by_item_text)
            if target:
                alias["idea:" + idea_id] = target
            continue
        if not reason:
            target = _find_merged_inc(drop_event, merge_idea, inc_by_text, inc_by_item_text)
            if target:
                alias["idea:" + idea_id] = target
                continue
            continue
        if reason == "star":
            text = edits.get(idea_id, idea["text"])
            node = _node_common(
                "idea:" + idea_id, "idea", text, "pool", None,
                ts=idea["ts"], via=idea.get("via") or "home", source=idea.get("source"),
                state="star", belongs=None, parent=idea.get("parent"))
            note = notes.get(idea_id)
            if note and note.get("belongs"):
                node["belongs"] = note["belongs"]
            idea_nodes[idea_id] = node
            nodes.append(node)
        # Other drop reasons delete the idea from the map.

    def resolved(node_id):
        value = str(node_id)
        return alias.get(value, value)

    # Possibility nodes (suggest_node) not dismissed by dismiss_node.
    for entry in state["poss_events"]:
        event = entry["event"]
        event_id = event.get("id")
        if not event_id:
            continue
        node_id = "poss:" + str(event_id)
        if node_id in state["dismissed_nodes"] or str(event_id) in state["dismissed_nodes"]:
            continue
        text = _clip(event.get("text"), MAX_TEXT)
        if not text:
            continue
        parents = event.get("parents")
        if not isinstance(parents, list):
            parents = []
        parents = [str(value) for value in parents if value]
        parent = event.get("parent")
        parent = str(parent) if parent else (parents[0] if parents else None)
        group = "pool"
        item_id = None
        if parent and parent.startswith("item:"):
            item_id = parent[len("item:"):]
            group = item_nodes.get(item_id, {}).get("group", group)
        elif parent and parent.startswith("inc:"):
            parts = parent.split(":")
            if len(parts) >= 3:
                item_id = parts[1]
                group = item_nodes.get(item_id, {}).get("group", group)
        node = _node_common(
            node_id, "poss", text, group, item_id,
            ts=str(event.get("ts", "")), via=str(event.get("via") or "hermes"),
            source=event.get("source") if isinstance(event.get("source"), dict) else None,
            state="suggested", belongs=None, parent=parent)
        node.update({
            "lens": str(event.get("lens") or ""),
            "parents": parents,
        })
        if event.get("to"):
            node["to"] = str(event.get("to"))
        nodes.append(node)

    node_by_id = {node["id"]: node for node in nodes}
    node_ids = set(node_by_id)

    # pin / edit / collapse are last-writer-wins per node.
    for entry in state["actions"]:
        event = entry["event"]
        kind = entry["type"]
        if kind == "pin":
            node_id = event.get("node")
            x, y = _number(event.get("x")), _number(event.get("y"))
            if not node_id or x is None or y is None:
                continue
            node = node_by_id.get(resolved(node_id))
            if node:
                node["pin"] = {"x": x, "y": y}
        elif kind == "edit":
            node_id = event.get("node")
            text = str(event.get("text", "")).strip()
            if not node_id or not text:
                continue
            node = node_by_id.get(resolved(node_id))
            if node and node["kind"] in ("idea", "poss"):
                node["text"] = text[:MAX_TEXT]
                node["short"] = text[:MAX_TEXT]
        elif kind == "collapse":
            node_id = event.get("node")
            if not node_id or not isinstance(event.get("on"), bool):
                continue
            node = node_by_id.get(resolved(node_id))
            if node:
                node["collapsed"] = event["on"]

    # Structural edges: every include belongs to its item; a note's belongs is
    # a Hermes proposal (the part_of line in the contract's example).
    structural = []
    for inc in includes:
        structural.append({
            "a": inc["id"], "b": "item:" + inc["item"], "kind": "part_of",
            "state": "structural", "by": "content", "label": "", "why": "",
        })
    for idea_id, node in idea_nodes.items():
        belongs = node.get("belongs")
        if not belongs:
            continue
        note = notes.get(idea_id) or {}
        structural.append({
            "a": "idea:" + idea_id, "b": "item:" + str(belongs), "kind": "part_of",
            "state": "suggested", "by": note.get("host") or "hermes",
            "label": "属于这件事吗？", "why": "",
        })

    confirmed = {}
    suggestions = {}
    blocked = set()
    unlinked = set()
    for entry in state["actions"]:
        event = entry["event"]
        kind = entry["type"]
        if kind not in ("link", "unlink", "dismiss", "undismiss", "suggest"):
            continue
        a, b = event.get("a"), event.get("b")
        if not a or not b:
            continue
        a, b = resolved(a), resolved(b)
        if a == b:
            continue
        key = _pair(a, b)
        if kind == "link":
            link_kind = str(event.get("kind") or "")
            if link_kind not in LINK_KINDS:
                continue
            confirmed[key] = {
                "a": a, "b": b, "kind": link_kind, "state": "confirmed",
                "by": str(event.get("host") or ""), "via": str(event.get("via") or ""),
                "label": _clip(event.get("label"), MAX_TEXT),
                "why": "",
            }
            unlinked.discard(key)
        elif kind == "unlink":
            confirmed.pop(key, None)
            blocked.add(key)
            unlinked.add(key)
        elif kind == "dismiss":
            blocked.add(key)
        elif kind == "undismiss":
            # Undoes a dismiss only: an unlink on the same pair still hides the proposal.
            blocked.discard(key)
        elif kind == "suggest":
            link_kind = str(event.get("kind") or "")
            if link_kind not in LINK_KINDS:
                continue
            suggestions[key] = {
                "a": a, "b": b, "kind": link_kind, "state": "suggested",
                "by": str(event.get("host") or "hermes"),
                "label": _clip(event.get("label"), MAX_TEXT),
                "why": _clip(event.get("why"), MAX_TEXT),
            }

    chosen = {}
    for link in structural:
        key = _pair(link["a"], link["b"])
        if key in unlinked:
            continue
        chosen[key] = link
    for key, link in suggestions.items():
        if key not in blocked and key not in unlinked:
            chosen[key] = link
    for key, link in confirmed.items():
        if key not in unlinked:
            chosen[key] = link

    links = []
    dropped_links = 0
    for key in sorted(chosen):
        link = chosen[key]
        if link["a"] not in node_ids or link["b"] not in node_ids:
            dropped_links += 1
            LOGGER.info("star: dropping link with missing node: %s -> %s", link["a"], link["b"])
            continue
        links.append(link)

    first_steps = _plan_first_steps(home_dir, today)
    for item_id, first_step in first_steps.items():
        node = item_nodes.get(item_id)
        if node:
            node["first_step"] = first_step

    last_ts = None
    for event in events:
        ts = event.get("ts")
        if ts and (last_ts is None or str(ts) > last_ts):
            last_ts = str(ts)

    groups = []
    for group in content_groups:
        if isinstance(group, dict) and group.get("id"):
            groups.append({"id": str(group["id"]), "name": str(group.get("name") or group["id"])})

    return {
        "version": 1,
        "groups": groups,
        "nodes": nodes,
        "links": links,
        "dismissed": sorted(blocked),
        "dropped_links": dropped_links,
        "last_ts": last_ts,
    }
