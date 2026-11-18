#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for today_unified.py: plain data in, rows out. No files and no server."""

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import today_unified as tu  # noqa: E402

UTC = timezone.utc
TODAY = date(2026, 11, 11)
GENERATED = "2026-11-10T00:00:00+00:00"


def todo(tid, title, status="pending", priority="P1", due=None, parent=None):
    return {"id": tid, "title": title, "status": status, "priority": priority,
            "due_date": due, "completed_at": None, "parent_id": parent}


def snapshot(*todos, generated=GENERATED):
    return {"version": 1, "generated_at": generated, "todos": list(todos)}


def step_card(kind, item, title, index, text, minutes=None):
    step = {"t": text}
    if minutes is not None:
        step["min"] = minutes
    return {"kind": kind, "item": item, "title": title, "group": "g", "progress": [0, 1],
            "source": "steps", "step_index": index, "step": step}


def handoff_card(item, title, text):
    return {"kind": "running", "item": item, "title": title, "group": "g", "progress": [1, 3],
            "handoff": {"next": text}, "source": "handoff", "step_index": None,
            "step": {"t": text, "d": ""}}


def hz_done(event_id, todo_id, done=True, ts="2026-11-11T01:00:00+00:00"):
    return {"id": event_id, "ts": ts, "host": "h", "type": "hz_done", "todo_id": todo_id, "done": done}


def build(cards=(), push=(), todos=(), events=(), items=(), generated=GENERATED, today=TODAY):
    return tu.build(cards=list(cards), push_units=list(push), horizon=snapshot(*todos, generated=generated),
                    events=list(events), items=list(items), today=today, url="http://127.0.0.1:8781/")


def ids(result):
    return [row["id"] for row in result["items"]]


class OrderAndDedupeTests(unittest.TestCase):
    def test_rows_follow_the_one_order_rule(self):
        cards = [step_card("running", "a", "A 在跑", 1, "a2"),
                 step_card("explore", "b", "B 探索", 0, "b1"),
                 step_card("light", "c", "C 轻量", 0, "c1")]
        push = [{"unit": "d0", "kind": "home", "item": "d", "step_index": 0, "title": "D 推进", "step": "d1"}]
        items = [{"id": "d", "steps": [{"t": "d0"}, {"t": "d1"}]}]
        todos = [todo("E", "E 逾期P0", priority="P0", due="2026-11-08"),
                 todo("T", "T 今天", due="2026-11-11"),
                 todo("F", "F 逾期P1晚", due="2026-11-10"),
                 todo("H", "H 逾期P1早", due="2026-11-07"),
                 todo("G", "G 逾期P2", priority="P2", due="2026-11-02"),
                 todo("X", "X 明天", priority="P0", due="2026-11-12")]
        result = build(cards=cards, push=push, todos=todos, items=items)
        self.assertEqual(ids(result), ["step:a:1", "step:d:0", "hz:E", "hz:T",
                                       "step:b:0", "step:c:0", "hz:H", "hz:F", "hz:G"])
        self.assertEqual(result["more"], 5)
        self.assertEqual(result["visible"], 4)

    def test_one_row_per_item_and_per_root(self):
        cards = [step_card("running", "a", "A", 1, "a2")]
        push = [{"unit": "x", "kind": "home", "item": "a", "step_index": 2, "title": "A", "step": "a3"},
                {"unit": "y", "kind": "home", "item": "d", "step_index": 0, "title": "D", "step": "d1"}]
        items = [{"id": "a", "steps": [{"t": "a1"}, {"t": "a2"}, {"t": "a3"}]}, {"id": "d", "steps": [{"t": "d0"}]}]
        self.assertEqual(ids(build(cards=cards, push=push, items=items)), ["step:a:1", "step:d:0"])

        todos = [todo("R", "R 报告", due="2026-11-10"), todo("C", "C 收集", due="2026-11-10", parent="R")]
        push = [{"unit": "hz:C", "kind": "horizon", "title": "C 推", "step": "先读"}]
        result = build(push=push, todos=todos)
        self.assertEqual(ids(result), ["hz:C"])
        row = result["items"][0]
        self.assertEqual((row["tag"], row["kind"], row["next"], row["overdue_days"]), ("推进", "push", "先读", 1))

    def test_handoff_rows_cannot_be_ticked(self):
        result = build(cards=[handoff_card("h", "H 交接", "写下一段")])
        row = result["items"][0]
        self.assertEqual((row["id"], row["tickable"], row["next"], row["item"]),
                         ("handoff:h", False, "写下一段", "h"))

    def test_cards_without_a_next_step_are_skipped(self):
        cards = [step_card("running", "a", "A", None, "")]
        cards[0]["step"] = None
        self.assertEqual(ids(build(cards=cards)), [])
        self.assertEqual(ids(build(cards=[handoff_card("h", "H", "")])), [])

    def test_minutes_come_from_the_step(self):
        cards = [step_card("running", "a", "A", 0, "a1", minutes=15)]
        push = [{"unit": "d0", "kind": "home", "item": "d", "step_index": 0, "title": "D", "step": "d1"}]
        items = [{"id": "d", "steps": [{"t": "d0", "min": 30}]}]
        by_id = {row["id"]: row for row in build(cards=cards, push=push, items=items)["items"]}
        self.assertEqual(by_id["step:a:0"]["min"], 15)
        self.assertEqual(by_id["step:d:0"]["min"], 30)

    def test_push_horizon_rows_need_a_live_todo_in_the_snapshot(self):
        todos = [todo("Q", "Q", status="done", due="2026-11-11")]
        push = [{"unit": "hz:Q", "kind": "horizon", "title": "Q", "step": ""},
                {"unit": "hz:missing", "kind": "horizon", "title": "?", "step": ""}]
        self.assertEqual(ids(build(push=push, todos=todos)), [])


class HorizonRuleTests(unittest.TestCase):
    def test_group_row_targets_the_earliest_live_child(self):
        todos = [todo("R", "报告", due="2026-11-20"),
                 todo("C1", "收集", due="2026-11-11", parent="R"),
                 todo("C2", "写作", priority="P0", due="2026-11-11", parent="R"),
                 todo("C3", "旧的", status="done", due="2026-11-11", parent="R")]
        result = build(todos=todos)
        self.assertEqual(ids(result), ["hz:C2"])
        row = result["items"][0]
        self.assertEqual((row["title"], row["next"], row["tag"], row["due"], row["overdue_days"]),
                         ("报告", "写作", "今天", "2026-11-11", 0))

    def test_only_the_parent_late_still_ticks_an_open_subtask(self):
        # Ticking must never close a parent while its subtasks are open (12 of the 45 real todos have no date).
        todos = [todo("R", "搬家", priority="P1", due="2026-11-05"),
                 todo("C", "订车", due=None, parent="R")]
        result = build(todos=todos)
        self.assertEqual(ids(result), ["hz:C"])
        row = result["items"][0]
        self.assertEqual((row["next"], row["tag"], row["overdue_days"]), ("订车", "逾期", 6))

    def test_a_late_p0_subtask_makes_the_group_p0(self):
        # Real Horizon data: every P0 is a subtask under a P1/P2 parent; they must still come first.
        todos = [todo("R", "装修", priority="P1", due="2026-11-30"),
                 todo("A", "量尺寸", priority="P2", due="2026-11-01", parent="R"),
                 todo("B", "付定金", priority="P0", due="2026-11-05", parent="R")]
        result = build(cards=[step_card("explore", "x", "学歌", 0, "听三遍")], todos=todos)
        self.assertEqual(ids(result), ["hz:B", "step:x:0"])
        row = result["items"][0]
        self.assertEqual((row["next"], row["priority"], row["tag"], row["due"], row["overdue_days"]),
                         ("付定金", "P0", "逾期", "2026-11-01", 10))

    def test_same_day_children_break_ties_by_title(self):
        todos = [todo("R2", "根二", due="2026-11-11"),
                 todo("k1", "b", due="2026-11-11", parent="R2"),
                 todo("k2", "a", due="2026-11-11", parent="R2")]
        self.assertEqual(ids(build(todos=todos)), ["hz:k2"])

    def test_orphan_child_is_its_own_root(self):
        todos = [todo("O", "孤儿", due="2026-11-11", parent="missing")]
        self.assertEqual(ids(build(todos=todos)), ["hz:O"])

    def test_parent_cycle_does_not_hang(self):
        todos = [todo("A", "A", parent="B"), todo("B", "B", parent="A", due="2026-11-11")]
        self.assertIsInstance(build(todos=todos)["items"], list)

    def test_future_and_undated_roots_are_not_listed(self):
        todos = [todo("F", "future", due="2026-11-12"), todo("U", "undated", due=None)]
        self.assertEqual(ids(build(todos=todos)), [])

    def test_optimistic_completion_follows_the_newer_of_event_and_snapshot(self):
        todos = [todo("X", "X", due="2026-11-11"),
                 todo("Y", "Y", due="2026-11-11"),
                 todo("Z", "Z", status="done", due="2026-11-11"),
                 todo("W", "W", status="done", due="2026-11-11")]
        events = [hz_done("e1", "X", True, "2026-11-11T01:00:00+00:00"),   # newer than the snapshot: done
                  hz_done("e2", "Y", True, "2026-11-09T12:00:00+00:00"),   # older than the snapshot: ignored
                  hz_done("e3", "Z", False, "2026-11-11T02:00:00+00:00")]  # newer: not done, so back to pending
        self.assertEqual(ids(build(todos=todos, events=events)), ["hz:Y", "hz:Z"])


class CountingTests(unittest.TestCase):
    def test_done_today_uses_the_beijing_day(self):
        events = [
            {"id": "d1", "ts": "2026-11-10T17:30:00Z", "type": "done", "item": "a", "step": 0},  # 11-11 01:30 BJ
            {"id": "d1", "ts": "2026-11-10T17:30:00Z", "type": "done", "item": "a", "step": 0},  # repeated line
            {"id": "d2", "ts": "2026-11-10T15:59:59Z", "type": "done", "item": "a", "step": 1},  # 11-10 23:59 BJ
            {"id": "d3", "ts": "2026-11-11T04:00:00Z", "type": "done", "item": "b", "step": 0},
            hz_done("h1", "T1", True, "2026-11-11T05:00:00+00:00"),
            hz_done("h2", "T1", False, "2026-11-11T06:00:00+00:00"),
        ]
        self.assertEqual(build(events=events)["done_today"], 2)

    def test_done_today_never_goes_negative(self):
        events = [{"id": "u1", "ts": "2026-11-11T02:00:00+00:00", "type": "undo", "item": "a", "step": 0},
                  {"id": "u2", "ts": "2026-11-11T03:00:00+00:00", "type": "undo", "item": "a", "step": 1}]
        self.assertEqual(build(events=events)["done_today"], 0)

    def test_skipped_items_are_todays_skips_per_kind(self):
        events = [
            {"id": "s1", "ts": "2026-11-11T01:00:00+00:00", "type": "skip", "item": "b", "kind": "explore"},
            {"id": "s2", "ts": "2026-11-11T02:00:00+00:00", "type": "skip", "item": "c", "kind": "explore"},
            {"id": "s3", "ts": "2026-11-10T02:00:00+00:00", "type": "skip", "item": "b", "kind": "explore"},
            {"id": "s4", "ts": "2026-11-11T03:00:00+00:00", "type": "skip", "item": "a", "kind": "running"},
            {"id": "s5", "ts": "2026-11-11T04:00:00+00:00", "type": "skip", "item": "a", "kind": "pool"},
            {"id": "s1", "ts": "2026-11-11T01:00:00+00:00", "type": "skip", "item": "b", "kind": "explore"},
            {"id": "s6", "ts": "2026-11-10T17:30:00+00:00", "type": "skip", "item": "b", "kind": "explore"},
            {"id": "x1", "ts": "2026-11-11T01:00:00+00:00", "type": "done", "item": "b", "step": 0},
        ]
        # Beijing date; each skipped thing once per kind; duplicates and other kinds ignored
        self.assertEqual(tu.skipped_items(events, TODAY), {"running": {"a"}, "explore": {"b", "c"}, "light": set()})

    def test_visible_and_more(self):
        six = [todo("T%d" % n, "T%d" % n, due="2026-11-11") for n in range(1, 7)]
        result = build(todos=six)
        self.assertEqual((result["visible"], result["more"], len(result["items"])), (4, 2, 6))
        four = build(todos=six[:4])
        self.assertEqual(four["more"], 0)
        empty = build()
        self.assertEqual((empty["items"], empty["more"]), ([], 0))

    def test_rev_is_twelve_characters_and_follows_the_rows(self):
        first = build(todos=[todo("T1", "t", due="2026-11-11")])
        again = build(todos=[todo("T1", "t", due="2026-11-11")])
        changed = build(todos=[todo("T1", "t", due="2026-11-11")],
                        cards=[step_card("running", "a", "A", 0, "next")])
        self.assertEqual(len(first["rev"]), 12)
        self.assertEqual(first["rev"], again["rev"])
        self.assertNotEqual(first["rev"], changed["rev"])

    def test_bj_today_is_the_beijing_calendar_date(self):
        self.assertEqual(tu.bj_today(datetime(2026, 11, 10, 17, 30, tzinfo=UTC)), date(2026, 11, 11))
        self.assertEqual(tu.bj_today(datetime(2026, 11, 10, 15, 59, tzinfo=UTC)), date(2026, 11, 10))
        self.assertEqual(tu.bj_today(datetime(2026, 11, 10, 17, 30)), date(2026, 11, 11))  # naive is UTC


class FeishuTextTests(unittest.TestCase):
    def test_render_matches_the_brief_example_exactly(self):
        unified = {
            "date": "2026-11-11", "done_today": 2, "more": 3, "url": "http://127.0.0.1:8781/",
            "items": [
                {"tag": "在跑", "title": "标题", "next": "下一步", "overdue_days": None},
                {"tag": "逾期", "title": "标题", "next": "下一步", "overdue_days": 8},
                {"tag": "推进", "title": "标题", "next": "", "overdue_days": None},
                {"tag": "探索", "title": "标题", "next": "下一步", "overdue_days": None},
            ],
        }
        expected = ("今天 11-11 · 已完成 2 件\n"
                    "1.【在跑】标题｜下一步\n"
                    "2.【逾期】标题｜下一步（逾期 8 天）\n"
                    "3.【推进】标题\n"
                    "4.【探索】标题｜下一步\n"
                    "还有 3 件 · http://127.0.0.1:8781/")
        self.assertEqual(tu.render_feishu(unified), expected)

    def test_render_with_nothing_to_do(self):
        unified = {"date": "2026-11-11", "done_today": 0, "more": 0, "url": "http://127.0.0.1:8781/", "items": []}
        self.assertEqual(tu.render_feishu(unified), "今天 11-11 · 已完成 0 件\n今天没有要做的")


if __name__ == "__main__":
    unittest.main()
