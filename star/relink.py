#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click connect for the star map.

The model proposes a whole set of links between the map's concepts.  This module turns
its answer into one batch of star events, and can reverse the newest batch that is still
undoable.  Nothing here reads a file or calls the model: server.py does both and passes
the data in, so the rules can be tested on their own.

The prompt is built the way verify/relink_probe.py builds it.  The rules:
- only items ("item:") and ideas ("idea:") can be linked; a part (inc) appears only as
  text in its item's line;
- the model sees short ids n1..nN in node order, and its answer is mapped back;
- forbidden pairs are the user's own cuts and dismissals, plus each idea with its parent
  item.  A line the tool itself removed does not forbid its pair;
- kinds are supports, extends, contradicts and same (part_of is never asked for);
- at most 3 links per point, and a label is at most 8 characters.
"""

import datetime
import json
import uuid

PER_NODE = 3
LABEL_MAX = 8
PART_MAX = 14
TEXT_MAX = 40
LINKABLE_TYPES = ("item", "idea")
LINK_KINDS = ("supports", "extends", "contradicts", "same")
SYSTEM = (
    "你在帮一个人整理他的「星图」：每件「事」是他在做的一个项目（括号里是它包含的部分，帮你理解它），「想法」是还没落地的念头。\n"
    "请找出事与事、事与想法、想法与想法之间真正有意义的联系，用线连起来。只能用 n 编号。\n"
    "\n"
    "线的种类（只能用这四种，按实际情况用，不要硬凑）：\n"
    "- supports：一个能直接帮到另一个（提供工具、方法、素材、能力、数据）。\n"
    "- extends：一个是另一个的延伸、下一步或升级版。\n"
    "- contradicts：两个在抢同一段时间或精力，或者目标互相冲突。\n"
    "- same：两个其实说的是同一件事，可以合并。只是「同类」「都是游戏」不算 same。\n"
    "\n"
    "规则：\n"
    "1. 只连有把握的，宁缺毋滥；总数 %d 到 %d 条。\n"
    "2. 每个点最多 %d 条线。\n"
    "3. 「不要再连」里的对是他亲手剪掉的，一对都不许连。\n"
    "4. label 最多 6 个汉字，说清关系本身，不要复述两端的名字。\n"
    "\n"
    "只输出 JSON：{\"links\":[{\"a\":\"n1\",\"b\":\"n2\",\"kind\":\"supports\",\"label\":\"...\"}]}"
)


def link_range(count):
    """(lowest, highest) number of links to ask for, given `count` linkable points."""
    return max(5, count * 2 // 5), count


def _text_of(node):
    text = str(node.get("title") or node.get("short") or node.get("text") or "")
    return text.strip().replace("\n", " ")[:TEXT_MAX]


def _label(value):
    return str(value or "").replace("\n", " ").strip()[:LABEL_MAX]


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _key(event):
    """The unordered pair an event names, or None when it names no real pair."""
    a, b = event.get("a"), event.get("b")
    if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
        return None
    return frozenset((a, b))


def tool_made(event):
    """True for an event this feature wrote: a batch (it has "batch") or an undo (it has "undo_of")."""
    return bool(event.get("batch") or event.get("undo_of"))


def user_blocked(star_events):
    """Pairs the user cut or dismissed and has not undismissed since.

    Events the tool wrote never block or unblock a pair.  So a line the tool removed can be
    proposed again, while a cut the user made stays in force even if the tool later removes
    the same line.
    """
    blocked = set()
    for event in star_events:
        kind = event.get("type")
        if kind not in ("unlink", "dismiss", "undismiss"):
            continue
        key = _key(event)
        if key is None:
            continue
        if kind == "undismiss":
            blocked.discard(key)
        elif not tool_made(event):
            blocked.add(key)
    return blocked


def _context(graph, star_events):
    """(all nodes, linkable nodes, short ids, own pairs, cut pairs) for one graph.

    Cut pairs are the dismissed pairs between two linkable points that the user made.  With
    star_events=None every dismissed pair counts as the user's.
    """
    all_nodes = [node for node in graph.get("nodes") or [] if isinstance(node, dict) and node.get("id")]
    nodes = [node for node in all_nodes if str(node["id"]).split(":")[0] in LINKABLE_TYPES]
    short = {node["id"]: "n%d" % (number + 1) for number, node in enumerate(nodes)}
    own = {frozenset((node["id"], node["parent"])) for node in nodes if node.get("parent") in short}
    blocked = None if star_events is None else user_blocked(star_events)
    cut = set()
    for pair in graph.get("dismissed") or []:
        if "|" not in str(pair):
            continue
        a, b = str(pair).split("|", 1)
        key = frozenset((a, b))
        if a in short and b in short and key not in own and (blocked is None or key in blocked):
            cut.add(key)
    return all_nodes, nodes, short, own, cut


def build_prompt(graph, star_events=None):
    """(system, user, short_map) for one click; short_map maps each real id to its n-number."""
    all_nodes, nodes, short, _, cut = _context(graph, star_events)
    lines = []
    for node in nodes:
        if node["id"].startswith("item:"):
            lines.append("%s 事 · %s" % (short[node["id"]], _text_of(node)))
            parts = [_text_of(member)[:PART_MAX] for member in all_nodes if member.get("parent") == node["id"]]
            if parts:
                lines[-1] += "（包含：" + "、".join(parts) + "）"
    lines += ["%s 想法 · %s" % (short[node["id"]], _text_of(node))
              for node in nodes if node["id"].startswith("idea:")]
    ban = ", ".join(sorted("%s-%s" % tuple(sorted(short[x] for x in pair)) for pair in cut)) or "（没有）"
    low, high = link_range(len(nodes))
    user = "\n".join(lines) + "\n\n不要再连：" + ban
    return SYSTEM % (low, high, PER_NODE), user, dict(short)


def forbidden_pairs(graph, star_events=None):
    """Pairs no proposal may use: the user's cuts and dismissals, and each idea with its parent item."""
    _, _, _, own, cut = _context(graph, star_events)
    return own | cut


def parse(content, short_map, forbidden):
    """(kept links, dropped counts) for the model's answer.

    content is the JSON text, or the object already decoded.  Anything that is not an object
    with a "links" list raises ValueError and keeps nothing.  A link that fails a check is
    dropped and counted under the first reason it fails.  Kept links use real ids.
    """
    value = json.loads(content) if isinstance(content, (str, bytes, bytearray)) else content
    if not isinstance(value, dict) or not isinstance(value.get("links"), list):
        raise ValueError("model answer is not a links object")
    back = {short: real for real, short in short_map.items()}
    kept, dropped, seen, degree = [], {}, set(), {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for item in value["links"]:
        if not isinstance(item, dict):
            drop("编号不认识")
            continue
        a = back.get(item["a"]) if isinstance(item.get("a"), str) else None
        b = back.get(item["b"]) if isinstance(item.get("b"), str) else None
        kind = item.get("kind")
        key = frozenset((a, b)) if a and b else None
        if a is None or b is None:
            drop("编号不认识")
        elif a == b:
            drop("自连")
        elif key in forbidden:
            drop("禁止对")
        elif key in seen:
            drop("重复")
        elif not isinstance(kind, str) or kind not in LINK_KINDS:
            drop("种类不对")
        elif degree.get(a, 0) >= PER_NODE or degree.get(b, 0) >= PER_NODE:
            drop("超过每点上限")
        else:
            seen.add(key)
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
            kept.append({"a": a, "b": b, "kind": kind, "label": _label(item.get("label"))})
    return kept, dropped


def fake_content(path, short_map):
    """The STAR_RELINK_FAKE switch: the links in a JSON file, with real ids written as short ids.

    Ids that are not on the map are left as they are, so parse() counts them as unknown.
    """
    with open(path, encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("links"), list):
        raise ValueError("fake file needs a links list")
    links = []
    for item in value["links"]:
        if isinstance(item, dict):
            item = dict(item)
            for field in ("a", "b"):
                if isinstance(item.get(field), str) and item[field] in short_map:
                    item[field] = short_map[item[field]]
        links.append(item)
    return {"links": links}


def _star_event(event_type, now, host, a, b, batch, link_kind=None, label=None):
    """An event shaped like validate_star_event's output, with the batch and via fields added."""
    event = {"id": uuid.uuid4().hex, "ts": now, "host": host, "type": event_type, "a": a, "b": b}
    if event_type == "link":
        event["kind"] = link_kind
        event["label"] = label
    event["batch"] = batch
    event["via"] = "relink"
    return event


def _replay(star_events):
    """Walk the link and unlink events once, in order.

    Returns (latest, batches, prior):
      latest:  pair -> newest link or unlink event for that pair;
      batches: batch id -> {"ts", "added", "changed", "removed", "keys"}, in write order;
      prior:   (batch, pair) -> the pair's newest event before that batch first touched it.
    """
    latest, batches, prior = {}, {}, {}
    for event in star_events:
        if event.get("type") not in ("link", "unlink"):
            continue
        key = _key(event)
        if key is None:
            continue
        before = latest.get(key)
        batch = event.get("batch")
        if batch:
            info = batches.get(batch)
            if info is None:
                info = batches[batch] = {"ts": str(event.get("ts", "")), "added": 0, "changed": 0,
                                         "removed": 0, "keys": []}
            if event["type"] == "unlink":
                info["removed"] += 1
            elif before is not None and before["type"] == "link":
                info["changed"] += 1
            else:
                info["added"] += 1
            if key not in info["keys"]:
                info["keys"].append(key)
                prior[(batch, key)] = before
        latest[key] = event
    return latest, batches, prior


def _undo_steps(batch, info, latest, prior):
    """The reversals undoing `batch` would write, as (current event, event type, event to restore).

    A pair is reversed only while its newest event is still the batch's own.  A line the batch
    added is removed; a line it changed or removed gets back the kind and label it had.
    """
    steps = []
    for key in info["keys"]:
        current = latest.get(key)
        if current is None or current.get("batch") != batch:
            continue
        before = prior.get((batch, key))
        if current["type"] == "link" and (before is None or before["type"] != "link"):
            steps.append((current, "unlink", None))
        elif before is not None and before["type"] == "link" and before.get("kind") in LINK_KINDS:
            steps.append((current, "link", before))
    return steps


def plan(links, star_events, linkable=None, host="", now=None):
    """The one batch of events that turns the current lines into the proposed ones.

    links: the kept proposals from parse(), with real ids.  linkable: the ids the model was
    shown (None means no limit).  The user's own lines are never changed or removed; they are
    counted in kept_user when they are in scope.  A line a batch made can be changed (its kind
    or label differs now) or removed (it is not proposed now), but only between linkable ids.
    Returns {"batch", "events", "added", "changed", "removed", "kept_user"}; batch is None and
    events is empty when nothing changes.
    """
    scope = None if linkable is None else set(linkable)

    def in_scope(key):
        return scope is None or key <= scope

    now = now or _utc_now()
    batch = uuid.uuid4().hex[:12]
    latest, _, _ = _replay(star_events)
    events = []
    counts = {"added": 0, "changed": 0, "removed": 0, "kept_user": 0}
    proposed = set()
    for link in links:
        key = frozenset((link["a"], link["b"]))
        proposed.add(key)
        current = latest.get(key)
        if current is not None and current["type"] == "link":
            if not current.get("batch"):
                continue  # the user's own line stays as it is
            if current.get("kind") == link["kind"] and str(current.get("label") or "") == link["label"]:
                continue
            counts["changed"] += 1
        else:
            counts["added"] += 1
        events.append(_star_event("link", now, host, link["a"], link["b"], batch,
                                  link_kind=link["kind"], label=link["label"]))
    for key, current in latest.items():
        if current["type"] != "link" or not in_scope(key):
            continue
        if not current.get("batch"):
            counts["kept_user"] += 1
        elif key not in proposed:
            counts["removed"] += 1
            events.append(_star_event("unlink", now, host, current["a"], current["b"], batch))
    if not events:
        batch = None
    return dict(counts, batch=batch, events=events)


def status(star_events):
    """{"last": {...}} for the newest batch, or {"last": None}, worked out from the events alone.

    "undone" is true once no pair the batch touched still has its event as the newest one.
    """
    latest, batches, prior = _replay(star_events)
    if not batches:
        return {"last": None}
    batch = list(batches)[-1]
    info = batches[batch]
    return {"last": {"batch": batch, "ts": info["ts"], "added": info["added"], "changed": info["changed"],
                     "removed": info["removed"], "undone": not _undo_steps(batch, info, latest, prior)}}


def undo_target(star_events):
    """The newest batch that still has something to undo, or None."""
    latest, batches, prior = _replay(star_events)
    for batch in reversed(list(batches)):
        if _undo_steps(batch, batches[batch], latest, prior):
            return batch
    return None


def plan_undo(star_events, batch, host="", now=None):
    """The events that undo `batch`: {"batch", "events", "reverted", "skipped"}.

    Restored lines carry no batch field, so they count as the user's from then on.
    """
    latest, batches, prior = _replay(star_events)
    info = batches.get(batch)
    if info is None:
        return {"batch": batch, "events": [], "reverted": 0, "skipped": 0}
    now = now or _utc_now()
    steps = _undo_steps(batch, info, latest, prior)
    events = []
    for current, event_type, restore in steps:
        event = {"id": uuid.uuid4().hex, "ts": now, "host": host, "type": event_type,
                 "a": current["a"], "b": current["b"]}
        if event_type == "link":
            event["kind"] = restore["kind"]
            event["label"] = str(restore.get("label") or "")
        event["undo_of"] = batch
        event["via"] = "relink-undo"
        events.append(event)
    return {"batch": batch, "events": events, "reverted": len(steps),
            "skipped": len(info["keys"]) - len(steps)}
