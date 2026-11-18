#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Route tests for the unified list. server.py runs as a subprocess on a free port against a
temporary home under this folder's _tmp, so no real data is read or written."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
TMP_PARENT = os.path.join(HERE, "_tmp")
BEIJING = timezone(timedelta(hours=8))
HOST = re.sub(r"[^A-Za-z0-9_-]", "_", socket.gethostname()) or "host"
OLD_GENERATED = "2020-01-01T00:00:00+00:00"

CONTENT = {
    "version": 2,
    "groups": [{"id": "running", "name": "在跑"}, {"id": "learn", "name": "学习"},
               {"id": "pool", "name": "想法池"}],
    "items": [
        {"id": "run1", "group": "running", "status": "running", "order": 1, "title": "在跑的事",
         "steps": [{"t": "第一步", "min": 15}, {"t": "第二步"}]},
        {"id": "exp1", "group": "learn", "status": "explore", "order": 1, "title": "探索甲",
         "steps": [{"t": "甲一"}]},
        {"id": "exp2", "group": "learn", "status": "explore", "order": 2, "title": "探索乙",
         "steps": [{"t": "乙一"}]},
        {"id": "exp3", "group": "learn", "status": "explore", "order": 3, "title": "探索丙",
         "steps": [{"t": "丙一"}]},
        {"id": "lt1", "group": "pool", "status": "pool", "light": True, "order": 1, "title": "轻量事",
         "steps": [{"t": "轻一"}]},
    ],
}


def bj_day(offset=0):
    return (datetime.now(BEIJING).date() + timedelta(days=offset)).isoformat()


def horizon_snapshot(extra=()):
    def todo(tid, title, priority, due, parent=None):
        return {"id": tid, "title": title, "status": "pending", "priority": priority,
                "due_date": due, "completed_at": None, "parent_id": parent}
    return {"version": 1, "generated_at": OLD_GENERATED, "todos": [
        todo("R1", "报告", "P0", bj_day(-2)),
        todo("C1", "收集资料", "P1", bj_day(-2), parent="R1"),
        todo("R2", "季度复盘", "P1", bj_day(-5)),
        todo("R3", "下周会", "P1", bj_day(0)),
        todo("R4", "明年计划", "P2", bj_day(10)),
    ] + list(extra)}


def push_plan():
    # Five units and two shown a day: an unpinned list would refill the second row after a tick.
    return {"window": [bj_day(-1), bj_day(1)], "per_day": 2, "units": [
        {"unit": "p-exp1", "kind": "home", "item": "exp1", "step_index": 0, "title": "探索甲", "step": "甲一"},
        {"unit": "p-exp2", "kind": "home", "item": "exp2", "step_index": 0, "title": "探索乙", "step": "乙一"},
        {"unit": "p-exp3", "kind": "home", "item": "exp3", "step_index": 0, "title": "探索丙", "step": "丙一"},
        {"unit": "p-lt1", "kind": "home", "item": "lt1", "step_index": 0, "title": "轻量事", "step": "轻一"},
        {"unit": "hz:R2", "kind": "horizon", "title": "季度复盘", "step": "先列提纲"},
    ]}


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def explore_item(cards):
    return next(card["item"] for card in cards if card["kind"] == "explore")


class ServerCase(unittest.TestCase):
    """One server.py per class, in its own temporary home, stopped by handle when the class ends."""

    WITH_PUSH = False
    EXTRA_ENV = {}

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(TMP_PARENT, "routes-" + uuid.uuid4().hex)
        cls.home = os.path.join(cls.root, "home")
        cls.state = os.path.join(cls.root, "state")
        os.makedirs(cls.home)
        os.makedirs(cls.state)
        for name in ("server.py", "today_unified.py", "todos.py"):
            shutil.copy(os.path.join(HERE, name), cls.home)
        write_json(os.path.join(cls.home, "content.json"), CONTENT)
        write_json(os.path.join(cls.home, "horizon-todos.json"), horizon_snapshot())
        with open(os.path.join(cls.home, "device.html"), "w", encoding="utf-8") as f:
            f.write("<!doctype html><title>device</title>")
        if cls.WITH_PUSH:
            os.makedirs(os.path.join(cls.home, "push"))
            write_json(os.path.join(cls.home, "push", "plan.json"), push_plan())
        cls.port = free_port()
        cls.events_path = os.path.join(cls.home, "events-%s.jsonl" % HOST)
        env = dict(os.environ, LOCALAPPDATA=cls.state, AGENT_HOME_PORT=str(cls.port))
        env.pop("HOME_IS_COPY", None)
        env.update(cls.EXTRA_ENV)
        cls.proc = subprocess.Popen([sys.executable, "server.py", "--port", str(cls.port)], cwd=cls.home,
                                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if cls.proc.poll() is not None:
                    raise RuntimeError("server.py exited with code %s" % cls.proc.returncode)
                try:
                    if cls.request("GET", "/health")[0] == 200:
                        return
                except OSError:
                    pass
                time.sleep(0.1)
            raise RuntimeError("server.py did not answer on port %d" % cls.port)
        except BaseException:
            cls.stop()
            raise

    @classmethod
    def stop(cls):
        proc = getattr(cls, "proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        shutil.rmtree(getattr(cls, "root", ""), ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        cls.stop()

    @classmethod
    def request(cls, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", cls.port, timeout=15)
        try:
            sent = dict(headers or {})
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                sent.setdefault("Content-Type", "application/json")
            connection.request(method, path, body=data, headers=sent)
            response = connection.getresponse()
            raw = response.read().decode("utf-8", "replace")
            if "application/json" in (response.getheader("Content-Type") or ""):
                return response.status, json.loads(raw)
            return response.status, raw
        finally:
            connection.close()

    @classmethod
    def raw(cls, method, path, body=None, headers=None):
        """(status, lower-case answer headers, body text) for a request whose answer headers matter."""
        connection = HTTPConnection("127.0.0.1", cls.port, timeout=15)
        try:
            sent = dict(headers or {})
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                sent.setdefault("Content-Type", "application/json")
            connection.request(method, path, body=data, headers=sent)
            response = connection.getresponse()
            answer = {name.lower(): value for name, value in response.getheaders()}
            return response.status, answer, response.read().decode("utf-8", "replace")
        finally:
            connection.close()

    def events(self):
        if not os.path.isfile(self.events_path):
            return []
        with open(self.events_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class SkipShiftRouteTests(ServerCase):
    def test_today_skips_shift_the_explore_card_on_the_unified_list(self):
        status, today = self.request("GET", "/api/today")
        self.assertEqual(status, 200)
        pick0 = explore_item(today["cards"])
        for _ in range(2):
            status, _ = self.request("POST", "/api/event", {"type": "skip", "item": pick0, "kind": "explore"})
            self.assertEqual(status, 200)

        status, unified = self.request("GET", "/api/today-unified")
        self.assertEqual(status, 200)
        explore_rows = [row for row in unified["items"] if row["tag"] == "探索"]
        self.assertEqual(len(explore_rows), 1)
        # 换一个 means "not this one today": the first candidate that was not skipped, however often it was pressed
        status, now = self.request("GET", "/api/today")
        expect = explore_item(now["cards"])
        if expect == pick0:
            status, now = self.request("GET", "/api/today?shift_explore=1")
            expect = explore_item(now["cards"])
        self.assertNotEqual(expect, pick0)
        self.assertEqual(explore_rows[0]["id"], "step:%s:0" % expect)
        self.assertEqual(explore_rows[0]["item"], expect)


        # /api/today still takes its shifts only from the query string
        status, plain = self.request("GET", "/api/today")
        self.assertEqual(explore_item(plain["cards"]), pick0)

        # ticking and then undoing the explore row puts the same thing back in the slot
        row = explore_rows[0]
        status, _ = self.request("POST", "/api/today-tick", {"id": row["id"], "done": True})
        self.assertEqual(status, 200)
        status, undone = self.request("POST", "/api/today-tick", {"id": row["id"], "done": False})
        self.assertEqual(status, 200)
        back = [r for r in undone["today"]["items"] if r["tag"] == "探索"]
        self.assertEqual(back[0]["id"], row["id"])


class TickRouteTests(ServerCase):
    def test_unified_list_ticks_and_read_paths(self):
        status, unified = self.request("GET", "/api/today-unified")
        self.assertEqual(status, 200)
        self.assertEqual(set(unified), {"date", "rev", "done_today", "visible", "more", "url", "items", "copy"})
        self.assertIs(unified["copy"], False)   # the test server is not started as a copy
        self.assertEqual((unified["visible"], unified["url"]), (4, "http://127.0.0.1:%d/" % self.port))
        ids = [row["id"] for row in unified["items"]]
        self.assertEqual(ids[0], "step:run1:0")
        for expected in ("hz:C1", "hz:R3", "hz:R2"):
            self.assertIn(expected, ids)
        self.assertNotIn("hz:R4", ids)
        self.assertEqual(unified["more"], len(ids) - 4)
        self.assertEqual(set(unified["items"][0]), {"id", "kind", "tag", "title", "next", "item", "due",
                                                    "overdue_days", "priority", "tickable", "min"})

        # a step tick moves the home card on to its next step
        status, body = self.request("POST", "/api/today-tick", {"id": "step:run1:0", "done": True})
        self.assertEqual((status, body["ok"]), (200, True))
        latest = body["today"]
        ids = [row["id"] for row in latest["items"]]
        self.assertNotIn("step:run1:0", ids)
        self.assertIn("step:run1:1", ids)
        self.assertEqual(latest["done_today"], 1)
        last = self.events()[-1]
        self.assertEqual((last["type"], last["item"], last["step"]), ("done", "run1", 0))

        # a horizon tick takes the child off; its root stays as the row, with the root's own title
        status, body = self.request("POST", "/api/today-tick", {"id": "hz:C1", "done": True})
        self.assertEqual(status, 200)
        latest = body["today"]
        rows = {row["id"]: row for row in latest["items"]}
        self.assertNotIn("hz:C1", rows)
        self.assertEqual((rows["hz:R1"]["title"], rows["hz:R1"]["next"], rows["hz:R1"]["tag"],
                          rows["hz:R1"]["overdue_days"]), ("报告", "", "逾期", 2))
        self.assertEqual(latest["done_today"], 2)
        last = self.events()[-1]
        self.assertEqual((last["type"], last["todo_id"], last["done"]), ("hz_done", "C1", True))

        # un-ticking brings the child back and takes the count down
        status, body = self.request("POST", "/api/today-tick", {"id": "hz:C1", "done": False})
        self.assertEqual(status, 200)
        latest = body["today"]
        self.assertIn("hz:C1", [row["id"] for row in latest["items"]])
        self.assertEqual(latest["done_today"], 1)

        # refused ticks
        for bad in ({"id": "handoff:run1", "done": True}, {"id": "hz:nope", "done": True},
                    {"id": "step:run1:9", "done": True}, {"id": "step:run1:0", "done": "yes"}):
            status, body = self.request("POST", "/api/today-tick", bad)
            self.assertEqual((status, body["ok"]), (400, False), bad)
        status, _ = self.request("POST", "/api/today-tick", {"id": "step:run1:0", "done": True},
                                 headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/today-tick", {"id": "step:run1:0", "done": True},
                                 headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)

        # the other read paths
        status, _ = self.request("GET", "/api/all")
        self.assertEqual(status, 200)
        status, text = self.request("GET", "/device")
        self.assertEqual(status, 200)
        self.assertIn("device", text)
        status, _ = self.request("GET", "/fusion")
        self.assertEqual(status, 404)
        with open(os.path.join(self.home, "today-%s.json" % HOST), encoding="utf-8") as f:
            written = json.load(f)
        self.assertTrue(written["unified"]["feishu_text"].startswith("今天 "))
        self.assertEqual(written["unified"]["ids"], [row["id"] for row in latest["items"][:4]])

        # the version fingerprint follows horizon-todos.json
        status, first = self.request("GET", "/api/version")
        extra = {"id": "R9", "title": "新待办", "status": "pending", "priority": "P2",
                 "due_date": None, "completed_at": None, "parent_id": None}
        write_json(os.path.join(self.home, "horizon-todos.json"), horizon_snapshot([extra]))
        status, second = self.request("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertNotEqual(first["v"], second["v"])


class PushRouteTests(ServerCase):
    WITH_PUSH = True

    def test_ticking_one_push_row_leaves_exactly_the_other_shown_row(self):
        status, first = self.request("GET", "/api/today-unified")
        self.assertEqual(status, 200)
        before = [row["id"] for row in first["items"] if row["tag"] == "推进"]
        self.assertEqual(len(before), 2)
        status, body = self.request("POST", "/api/today-tick", {"id": before[0], "done": True})
        self.assertEqual(status, 200)
        after = [row["id"] for row in body["today"]["items"] if row["tag"] == "推进"]
        # Pinned: the other shown row stays alone. An unpinned list would refill to two rows.
        self.assertEqual(after, [before[1]])


def board_roots(board):
    return [row for group in board["groups"] for row in group["roots"]]


def board_root(board, root_id):
    return next(row for row in board_roots(board) if row["id"] == root_id)


def board_group_of(board, root_id):
    return next(group["key"] for group in board["groups"]
                if any(row["id"] == root_id for row in group["roots"]))


class TodoBoardRouteTests(ServerCase):
    """The home-page todo board: GET /api/todos, the two POSTs, and the card script next to the page."""

    def setUp(self):
        # Every test starts from the same snapshot and no events: the class shares one temporary home.
        write_json(os.path.join(self.home, "horizon-todos.json"), horizon_snapshot())
        with open(self.events_path, "w", encoding="utf-8"):
            pass

    def test_board_is_served_with_its_shape_and_no_store(self):
        status, headers, raw = self.raw("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("cache-control"), "no-store")
        board = json.loads(raw)
        self.assertEqual(set(board), {"copy", "rev", "counts", "choices", "groups"})
        self.assertFalse(board["copy"])
        self.assertEqual(board["counts"], {"open": 5, "overdue": 2})
        self.assertEqual([group["key"] for group in board["groups"]], [""])
        roots = board["groups"][0]["roots"]
        self.assertEqual([root["id"] for root in roots], ["R1", "R2", "R3", "R4"])
        self.assertEqual((roots[0]["overdue_days"], roots[0]["open_children"], roots[0]["tickable"]), (2, 1, False))
        self.assertEqual([child["id"] for child in roots[0]["children"]], ["C1"])
        self.assertEqual(roots[1]["overdue_days"], 5)
        self.assertEqual([choice["key"] for choice in board["choices"]],
                         ["item:run1", "item:exp1", "item:exp2", "item:exp3", "item:lt1"])

    def test_new_todo_then_assign_moves_it_between_groups(self):
        status, all_before = self.request("GET", "/api/all")
        self.assertEqual(status, 200)
        status, answer = self.request("POST", "/api/todos", {"title": "新的事", "due_date": bj_day(0),
                                                             "priority": "P0", "group": "item:exp2"})
        self.assertEqual((status, answer["ok"]), (200, True))
        self.assertEqual(set(answer), {"ok", "todos"})
        home_event = self.events()[-1]
        self.assertEqual(home_event["type"], "hz_new")
        new_id = "new:" + home_event["id"]
        self.assertEqual(board_group_of(answer["todos"], new_id), "item:exp2")

        status, answer = self.request("POST", "/api/todos/assign", {"todo_id": home_event["id"],
                                                                    "group": "label:周报", "auto": True})
        self.assertEqual((status, answer["ok"]), (200, True))
        self.assertEqual(board_group_of(answer["todos"], new_id), "label:周报")
        self.assertTrue(board_root(answer["todos"], new_id)["auto"])
        self.assertIn({"key": "label:周报", "title": "周报"}, answer["todos"]["choices"])

        # the second assign may land in the same second: the later line wins
        status, answer = self.request("POST", "/api/todos/assign", {"todo_id": home_event["id"],
                                                                    "group": "item:exp1"})
        self.assertEqual(board_group_of(answer["todos"], new_id), "item:exp1")
        self.assertFalse(board_root(answer["todos"], new_id)["auto"])
        self.assertNotIn("label:周报", [choice["key"] for choice in answer["todos"]["choices"]])

        # the new events must not move the state or the today list that /api/all reports
        status, all_after = self.request("GET", "/api/all")
        self.assertEqual(status, 200)
        self.assertEqual(all_after["state"], all_before["state"])
        self.assertEqual(all_after["today"], all_before["today"])

    def test_a_synced_todo_keeps_the_group_given_on_the_home_page(self):
        status, answer = self.request("POST", "/api/todos", {"title": "同步后的事", "priority": "P2",
                                                             "group": "item:lt1"})
        self.assertEqual(status, 200)
        home_id = self.events()[-1]["id"]
        status, answer = self.request("POST", "/api/todos/assign", {"todo_id": home_id, "group": "label:稍后"})
        self.assertEqual(status, 200)
        synced = horizon_snapshot([{"id": "S9", "title": "同步后的事", "status": "pending", "priority": "P2",
                                    "due_date": None, "completed_at": None, "parent_id": None,
                                    "source_msg_id": "home:" + home_id}])
        write_json(os.path.join(self.home, "horizon-todos.json"), synced)
        status, board = self.request("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertEqual(board_group_of(board, "S9"), "label:稍后")
        self.assertFalse(board_root(board, "S9")["pending"])
        self.assertNotIn("new:" + home_id, [row["id"] for row in board_roots(board)])

    def test_bad_input_is_refused_with_400_and_writes_nothing(self):
        cases = [
            ("/api/todos", {"title": "   "}),
            ("/api/todos", {"title": "字" * 201}),
            ("/api/todos", {"title": "ok", "due_date": "2026-02-30"}),
            ("/api/todos", {"title": "ok", "due_date": "11/11"}),
            ("/api/todos", {"title": "ok", "priority": "P9"}),
            ("/api/todos", {"title": "ok", "group": "bogus"}),
            ("/api/todos", {"title": "ok", "group": "label:" + "字" * 21}),
            ("/api/todos/assign", {"todo_id": "nope", "group": ""}),
            ("/api/todos/assign", {"todo_id": "R1", "group": "label:"}),
            ("/api/todos/assign", {"todo_id": "R1", "group": "", "auto": "yes"}),
            ("/api/todos/assign", {"group": "item:exp1"}),
        ]
        for path, body in cases:
            status, answer = self.request("POST", path, body)
            self.assertEqual((status, answer["ok"]), (400, False), (path, body))
        status, answer = self.request("POST", "/api/todos", {"title": "x"},
                                      headers={"Content-Type": "text/plain"})
        self.assertEqual((status, answer["ok"]), (400, False))
        self.assertEqual(self.events(), [])

    def test_todo_card_script_is_served_when_present_and_404_when_not(self):
        path = os.path.join(self.home, "todo-card.js")
        if os.path.exists(path):
            os.remove(path)
        status, _headers, _text = self.raw("GET", "/todo-card.js")
        self.assertEqual(status, 404)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("// placeholder card script\n")
        try:
            status, headers, text = self.raw("GET", "/todo-card.js")
            self.assertEqual(status, 200)
            self.assertEqual(headers.get("content-type"), "application/javascript; charset=utf-8")
            self.assertEqual(headers.get("cache-control"), "no-store")
            self.assertIn("placeholder", text)
        finally:
            os.remove(path)


class TodoCopyRouteTests(ServerCase):
    EXTRA_ENV = {"HOME_IS_COPY": "1"}

    def test_copy_flag_is_set_when_the_home_is_a_copy(self):
        status, board = self.request("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertTrue(board["copy"])


if __name__ == "__main__":
    unittest.main()
