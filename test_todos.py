#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for todos.py: plain data in, the board out. No files and no server."""

import os
import sys
import unittest
from datetime import date

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import todos as tb  # noqa: E402

TODAY = date(2026, 11, 11)
GENERATED = "2026-11-10T00:00:00+00:00"
GROUPS = ["running", "learn", "pool"]
ITEMS = [
    {"id": "hub", "group": "learn", "order": 2, "title": "Hub 事项"},
    {"id": "run1", "group": "running", "order": 1, "title": "在跑一"},
    {"id": "exp1", "group": "learn", "order": 1, "title": "探索一"},
    {"id": "lt1", "group": "pool", "order": 1, "title": "想法池一"},
]


def todo(tid, title, status="pending", priority="P1", due=None, parent=None, source_msg_id=None):
    row = {"id": tid, "title": title, "status": status, "priority": priority, "due_date": due,
           "completed_at": None, "parent_id": parent}
    if source_msg_id is not None:
        row["source_msg_id"] = source_msg_id
    return row


def snapshot(*rows, generated=GENERATED):
    return {"version": 1, "generated_at": generated, "todos": list(rows)}


def hz_done(event_id, todo_id, done=True, ts="2026-11-11T01:00:00+00:00"):
    return {"id": event_id, "ts": ts, "host": "h", "type": "hz_done", "todo_id": todo_id, "done": done}


def hz_new(event_id, title, due="", priority="P1", group="", ts="2026-11-11T00:00:00+00:00"):
    return {"id": event_id, "ts": ts, "host": "h", "type": "hz_new", "title": title,
            "due_date": due, "priority": priority, "group": group}


def hz_assign(event_id, todo_id, group, auto=False, ts="2026-11-11T00:30:00+00:00"):
    return {"id": event_id, "ts": ts, "host": "h", "type": "hz_assign", "todo_id": todo_id,
            "group": group, "auto": auto}


def board(*rows, events=(), items=ITEMS, generated=GENERATED, copy=False, horizon=None):
    snap = horizon if horizon is not None else snapshot(*rows, generated=generated)
    return tb.build(todos_snapshot=snap, events=list(events), items=list(items),
                    groups_order=GROUPS, today=TODAY, copy=copy)


def all_roots(result):
    return [row for group in result["groups"] for row in group["roots"]]


def find_root(result, root_id):
    return next(row for row in all_roots(result) if row["id"] == root_id)


def group_of(result, root_id):
    return next(group["key"] for group in result["groups"]
                if any(row["id"] == root_id for row in group["roots"]))


def group_keys(result):
    return [group["key"] for group in result["groups"]]


class ParseGroupTests(unittest.TestCase):
    def test_well_formed_groups(self):
        self.assertEqual(tb.parse_group("item:hub"), ("item", "hub"))
        self.assertEqual(tb.parse_group("label:  周报 "), ("label", "周报"))
        self.assertEqual(tb.parse_group("label:" + "字" * 20), ("label", "字" * 20))

    def test_malformed_groups_are_none(self):
        for bad in ("", "item:", "item:a b", "label:", "label:   ", "label:" + "字" * 21, "bogus", None, 3):
            self.assertIsNone(tb.parse_group(bad), bad)


class BoardTests(unittest.TestCase):
    def test_roots_children_and_counts(self):
        result = board(
            todo("R", "报告", priority="P0", due="2026-11-09"),
            todo("C1", "收集资料", priority="P1", due="2026-11-09", parent="R"),
            todo("C2", "已做完的子待办", status="done", parent="R"),
            todo("R2", "今天的事", due="2026-11-11"),
            todo("D", "完成的根", status="done"),
        )
        self.assertEqual(group_keys(result), [""])
        self.assertEqual([row["id"] for row in result["groups"][0]["roots"]], ["R", "R2"])
        root = find_root(result, "R")
        self.assertEqual(set(root), {"id", "title", "priority", "due", "overdue_days", "status", "pending",
                                     "tickable", "auto", "open_children", "children"})
        self.assertEqual(root["children"], [{"id": "C1", "title": "收集资料", "priority": "P1",
                                             "due": "2026-11-09", "overdue_days": 2, "status": "pending",
                                             "tickable": True}])
        self.assertEqual((root["open_children"], root["tickable"], root["overdue_days"], root["pending"],
                          root["auto"]), (1, False, 2, False, False))
        self.assertEqual((find_root(result, "R2")["overdue_days"], find_root(result, "R2")["tickable"]), (0, True))
        self.assertEqual(result["counts"], {"open": 3, "overdue": 1})
        self.assertEqual((result["groups"][0]["open"], result["groups"][0]["overdue"]), (3, 1))
        self.assertEqual(set(result["groups"][0]), {"key", "title", "item", "open", "overdue", "roots"})

    def test_orphan_child_is_a_root(self):
        result = board(todo("X", "父不在快照里", parent="gone"))
        self.assertEqual([row["id"] for row in all_roots(result)], ["X"])

    def test_done_root_stays_listed_for_an_open_overdue_child(self):
        result = board(todo("D", "已完成的根", status="done", due="2026-11-01"),
                       todo("E", "子待办", due="2026-11-05", parent="D"))
        root = find_root(result, "D")
        self.assertEqual((root["status"], root["overdue_days"], root["open_children"], root["tickable"]),
                         ("done", 0, 1, False))
        self.assertEqual(root["children"][0]["overdue_days"], 6)
        self.assertEqual(result["counts"], {"open": 1, "overdue": 1})

    def test_descendants_below_a_child_block_its_tick(self):
        result = board(todo("R", "根"), todo("C", "子", parent="R"), todo("G", "孙", parent="C"))
        root = find_root(result, "R")
        self.assertEqual(root["open_children"], 2)
        self.assertFalse(root["tickable"])
        self.assertEqual([child["id"] for child in root["children"]], ["C", "G"])
        by_id = {child["id"]: child for child in root["children"]}
        self.assertFalse(by_id["C"]["tickable"])
        self.assertTrue(by_id["G"]["tickable"])

    def test_children_sort_by_due_then_priority_then_title(self):
        result = board(todo("R", "根"), todo("c1", "gamma", due="2026-11-20", parent="R"),
                       todo("c2", "beta", priority="P0", due="2026-11-12", parent="R"),
                       todo("c3", "alpha", priority="P0", due="2026-11-12", parent="R"),
                       todo("c4", "delta", parent="R"))
        self.assertEqual([child["id"] for child in find_root(result, "R")["children"]],
                         ["c3", "c2", "c1", "c4"])

    def test_roots_sort_overdue_first_then_priority_due_title(self):
        result = board(todo("a", "甲", priority="P2"),
                       todo("b", "乙", priority="P0", due="2026-11-12"),
                       todo("c", "丙", priority="P0", due="2026-11-10"),
                       todo("d", "丁", priority="P1", due="2026-11-09"),
                       todo("e", "戊", priority="P0"),
                       todo("f", "己", priority="P0", due="2026-11-10"))
        self.assertEqual([row["id"] for row in all_roots(result)], ["c", "f", "d", "b", "e", "a"])

    def test_optimistic_completion_follows_only_a_newer_hz_done(self):
        rows = [todo("A", "甲", due="2026-11-09"), todo("B", "乙", due="2026-11-09")]
        newer = board(*rows, events=[hz_done("e1", "A", True, "2026-11-11T01:00:00+00:00")])
        self.assertEqual([row["id"] for row in all_roots(newer)], ["B"])
        self.assertEqual(newer["counts"]["open"], 1)
        older = board(*rows, events=[hz_done("e2", "A", True, "2026-11-09T01:00:00+00:00")])
        self.assertEqual(sorted(row["id"] for row in all_roots(older)), ["A", "B"])
        undone = board(todo("U", "做完又撤回", status="done", due="2026-11-09"),
                       events=[hz_done("e3", "U", False, "2026-11-11T02:00:00+00:00")])
        self.assertEqual(find_root(undone, "U")["status"], "pending")

    def test_groups_follow_home_order_then_labels_then_other(self):
        rows = [todo(tid, title) for tid, title in
                (("A", "甲"), ("B", "乙"), ("C", "丙"), ("E", "丁"), ("F", "戊"), ("G", "己"), ("H", "庚"))]
        events = [
            hz_assign("a1", "A", "item:hub"),
            hz_assign("a2", "B", "item:run1"),
            hz_assign("a3", "C", "label:weekly"),
            hz_assign("a4", "E", "label:reading"),
            hz_assign("a5", "F", "item:ghost"),
            hz_assign("a6", "G", "label:"),
            hz_assign("a7", "H", "label:" + "长" * 21),
        ]
        result = board(*rows, events=events)
        self.assertEqual(group_keys(result), ["item:run1", "item:hub", "label:reading", "label:weekly", ""])
        self.assertEqual([group["title"] for group in result["groups"]],
                         ["在跑一", "Hub 事项", "reading", "weekly", "其他"])
        self.assertEqual([group["item"] for group in result["groups"]], ["run1", "hub", None, None, None])
        self.assertEqual(sorted(row["id"] for row in result["groups"][-1]["roots"]), ["F", "G", "H"])
        self.assertEqual(result["choices"], [
            {"key": "item:run1", "title": "在跑一"}, {"key": "item:exp1", "title": "探索一"},
            {"key": "item:hub", "title": "Hub 事项"}, {"key": "item:lt1", "title": "想法池一"},
            {"key": "label:reading", "title": "reading"}, {"key": "label:weekly", "title": "weekly"}])

    def test_item_missing_from_the_content_goes_last_in_choices(self):
        items = ITEMS + [{"id": "orphan", "group": "gone", "order": 1, "title": "无组"}]
        result = board(todo("A", "甲"), items=items)
        self.assertEqual([choice["key"] for choice in result["choices"]],
                         ["item:run1", "item:exp1", "item:hub", "item:lt1", "item:orphan"])

    def test_latest_assign_wins_and_equal_timestamps_go_to_the_later_line(self):
        rows = [todo("A", "甲")]
        same_ts = [hz_assign("x1", "A", "item:hub", ts="2026-11-11T00:40:00+00:00"),
                   hz_assign("x2", "A", "label:weekly", True, ts="2026-11-11T00:40:00+00:00")]
        result = board(*rows, events=same_ts)
        self.assertEqual(group_of(result, "A"), "label:weekly")
        self.assertTrue(find_root(result, "A")["auto"])
        later_ts_first = [hz_assign("y1", "A", "label:weekly", ts="2026-11-11T00:50:00+00:00"),
                          hz_assign("y2", "A", "item:hub", ts="2026-11-11T00:45:00+00:00")]
        self.assertEqual(group_of(board(*rows, events=later_ts_first), "A"), "label:weekly")

    def test_pending_todo_before_sync_then_the_same_todo_after_sync(self):
        events = [hz_new("n1", "新待办", due="2026-11-11", priority="P0", group="item:hub"),
                  hz_assign("a1", "n1", "label:weekly", True, ts="2026-11-11T00:20:00+00:00")]
        pending = board(events=events)
        root = find_root(pending, "new:n1")
        self.assertEqual((root["pending"], root["tickable"], root["status"], root["priority"], root["auto"]),
                         (True, False, "pending", "P0", True))
        self.assertEqual((root["due"], root["overdue_days"]), ("2026-11-11", 0))
        self.assertEqual(group_of(pending, "new:n1"), "label:weekly")
        self.assertEqual(pending["counts"], {"open": 0, "overdue": 0})
        synced = board(todo("H9", "新待办", priority="P0", due="2026-11-11", source_msg_id="home:n1"),
                       events=events)
        self.assertEqual(find_root(synced, "H9")["pending"], False)
        self.assertEqual(group_of(synced, "H9"), "label:weekly")
        self.assertEqual(synced["counts"], {"open": 1, "overdue": 0})
        self.assertNotIn("new:n1", [row["id"] for row in all_roots(synced)])

    def test_synced_todo_without_an_assign_keeps_its_home_group(self):
        events = [hz_new("n2", "没改组的", group="item:hub")]
        synced = board(todo("H8", "没改组的", source_msg_id="home:n2"), events=events)
        self.assertEqual(group_of(synced, "H8"), "item:hub")

    def test_hz_new_group_is_only_a_fallback_and_never_compared_by_time(self):
        events = [hz_new("n3", "新待办", group="item:hub", ts="2026-11-11T00:10:00+00:00"),
                  hz_assign("a3", "n3", "label:weekly", ts="2026-11-10T23:00:00+00:00")]
        self.assertEqual(group_of(board(events=events), "new:n3"), "label:weekly")

    def test_a_pending_todo_overdue_counts_in_overdue_but_not_open(self):
        result = board(events=[hz_new("n4", "昨天的事", due="2026-11-10")])
        self.assertEqual(result["counts"], {"open": 0, "overdue": 1})
        self.assertEqual(find_root(result, "new:n4")["overdue_days"], 1)

    def test_repeated_event_lines_count_once(self):
        events = [hz_new("n5", "只一条"), hz_new("n5", "只一条"),
                  hz_assign("a5", "n5", "item:hub"), hz_assign("a5", "n5", "item:hub")]
        result = board(events=events)
        self.assertEqual([row["id"] for row in all_roots(result)], ["new:n5"])

    def test_empty_board_and_copy_flag(self):
        empty = board()
        self.assertEqual((empty["groups"], empty["counts"], empty["copy"]), ([], {"open": 0, "overdue": 0}, False))
        self.assertEqual([choice["key"] for choice in empty["choices"]],
                         ["item:run1", "item:exp1", "item:hub", "item:lt1"])
        self.assertTrue(board(copy=True)["copy"])

    def test_rev_is_twelve_hex_digits_and_follows_the_content(self):
        base = board(todo("A", "甲", due="2026-11-09"))
        self.assertEqual(base["rev"], board(todo("A", "甲", due="2026-11-09"))["rev"])
        self.assertNotEqual(base["rev"], board(todo("A", "甲改", due="2026-11-09"))["rev"])
        self.assertNotEqual(base["rev"], board(todo("A", "甲", due="2026-11-09"), copy=True)["rev"])
        self.assertEqual(len(base["rev"]), 12)
        int(base["rev"], 16)


if __name__ == "__main__":
    unittest.main()
