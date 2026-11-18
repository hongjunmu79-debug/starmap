#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for one-click connect: the rules in star/relink.py and the routes in server.py.

The routes run in this process, on a free port, against a temporary home.  No test calls
the model: the no-key path is forced, STAR_RELINK_FAKE supplies the links, and the live
path is exercised with starmodel.ask patched.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import uuid
from http.client import HTTPConnection
from unittest import mock

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.abspath(os.path.join(HERE, ".."))
if HOME not in sys.path:
    sys.path.insert(0, HOME)

from star import relink  # noqa: E402


def _pick_tmp_root():
    candidates = [
        os.environ.get("C1_TEST_TMP"),
        os.path.join(os.path.dirname(os.path.dirname(HOME)), "_tmp"),
        tempfile.gettempdir(),
        os.path.dirname(HOME),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            os.makedirs(candidate, exist_ok=True)
            probe = os.path.join(candidate, ".probe-" + uuid.uuid4().hex)
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(probe)
            except OSError:
                pass
            return candidate
        except OSError:
            continue
    raise RuntimeError("no writable temporary directory")


TMP_ROOT = _pick_tmp_root()


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "agent_home_server_relink_test", os.path.join(HOME, "server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = _load_server()

ALPHA, BETA, GAMMA, DELTA = "item:alpha", "item:beta", "item:gamma", "item:delta"
IDEA1, IDEA2 = "idea:" + "1" * 32, "idea:" + "2" * 32
LINKABLE = {ALPHA, BETA, GAMMA, DELTA, IDEA1, IDEA2}
B1, B2 = "111111111111", "222222222222"
T1, T2 = "2026-11-11T01:00:00+00:00", "2026-11-11T01:30:00+00:00"
NOW = "2026-11-11T02:00:00+00:00"
CONTENT = {
    "items": [
        {"id": "alpha", "title": "项目甲", "status": "running", "includes": ["子任务一"]},
        {"id": "beta", "title": "项目乙", "status": "explore"},
        {"id": "gamma", "title": "项目丙", "status": "pool"},
        {"id": "delta", "title": "项目丁", "status": "frozen"},
    ],
    "groups": [],
}


def pair(a, b):
    return frozenset((a, b))


def key_of(a, b):
    """The "a|b" spelling star/starapi uses in the graph's dismissed list."""
    return "|".join(sorted((a, b)))


def proposal(a, b, kind="supports", label=""):
    return {"a": a, "b": b, "kind": kind, "label": label}


def link_event(a, b, kind="supports", label="", batch=None, ts=T1):
    event = {"id": uuid.uuid4().hex, "ts": ts, "host": "test", "type": "link",
             "a": a, "b": b, "kind": kind, "label": label}
    if batch:
        event.update(batch=batch, via="relink")
    return event


def unlink_event(a, b, batch=None, undo_of=None, ts=T1):
    event = {"id": uuid.uuid4().hex, "ts": ts, "host": "test", "type": "unlink", "a": a, "b": b}
    if batch:
        event.update(batch=batch, via="relink")
    if undo_of:
        event.update(undo_of=undo_of, via="relink-undo")
    return event


def user_event(event_type, a, b, ts=T2, **extra):
    event = {"id": uuid.uuid4().hex, "ts": ts, "host": "test", "type": event_type, "a": a, "b": b}
    event.update(extra)
    return event


def two_batches():
    """Batch B1 adds two lines; batch B2 changes one of them and removes the other."""
    return [
        link_event(ALPHA, BETA, "supports", "A", batch=B1, ts=T1),
        link_event(GAMMA, DELTA, "extends", "B", batch=B1, ts=T1),
        link_event(ALPHA, BETA, "contradicts", "C", batch=B2, ts=T2),
        unlink_event(GAMMA, DELTA, batch=B2, ts=T2),
    ]


def sample_graph(dismissed=()):
    """A graph shaped like star/starapi.build_graph's output, with only the fields relink reads."""
    return {
        "nodes": [
            {"id": ALPHA, "kind": "item", "title": "项目甲", "parent": None},
            {"id": "inc:alpha:0", "kind": "inc", "title": "ABCDEFGHIJKLMNOPQRST", "parent": ALPHA},
            {"id": BETA, "kind": "item", "title": "项目乙", "parent": None},
            {"id": GAMMA, "kind": "item", "title": "项目丙", "parent": None},
            {"id": DELTA, "kind": "item", "title": "项目丁", "parent": None},
            {"id": IDEA1, "kind": "idea", "short": "想法一", "text": "想法一", "parent": GAMMA},
            {"id": IDEA2, "kind": "idea", "short": "想法二", "text": "想法二", "parent": None},
            {"id": "poss:p1", "kind": "poss", "short": "可能性", "text": "可能性", "parent": None},
        ],
        "dismissed": list(dismissed),
    }


class PromptTests(unittest.TestCase):
    def test_linkable_points_get_short_ids_in_node_order(self):
        _, _, short = relink.build_prompt(sample_graph())
        self.assertEqual(short, {ALPHA: "n1", BETA: "n2", GAMMA: "n3", DELTA: "n4", IDEA1: "n5", IDEA2: "n6"})

    def test_every_point_is_listed_and_no_part_or_suggestion_is_numbered(self):
        system, user, _ = relink.build_prompt(sample_graph())
        for line in ("n1 事 · 项目甲", "n2 事 · 项目乙", "n3 事 · 项目丙", "n4 事 · 项目丁",
                     "n5 想法 · 想法一", "n6 想法 · 想法二"):
            self.assertIn(line, user)
        self.assertNotIn("inc:", system + user)
        self.assertNotIn("可能性", user)

    def test_parts_are_background_text_cut_to_fourteen_characters(self):
        _, user, _ = relink.build_prompt(sample_graph())
        self.assertIn("n1 事 · 项目甲（包含：ABCDEFGHIJKLMN）", user)
        self.assertNotIn("ABCDEFGHIJKLMNO", user)

    def test_the_count_and_per_point_limits_are_in_the_system_prompt(self):
        system, _, _ = relink.build_prompt(sample_graph())
        self.assertIn("总数 5 到 6 条", system)
        self.assertIn("每个点最多 3 条线", system)

    def test_link_range(self):
        self.assertEqual(relink.link_range(6), (5, 6))
        self.assertEqual(relink.link_range(60), (24, 60))

    def test_the_users_cut_is_in_the_do_not_link_line(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        _, user, _ = relink.build_prompt(graph, [user_event("unlink", ALPHA, BETA)])
        self.assertIn("不要再连：n1-n2", user)

    def test_a_line_the_tool_removed_is_not_in_the_do_not_link_line(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        events = [link_event(ALPHA, BETA, batch=B1), unlink_event(ALPHA, BETA, batch=B2)]
        _, user, _ = relink.build_prompt(graph, events)
        self.assertIn("不要再连：（没有）", user)


class ForbiddenTests(unittest.TestCase):
    def test_an_idea_and_its_parent_item_are_always_forbidden(self):
        self.assertIn(pair(IDEA1, GAMMA), relink.forbidden_pairs(sample_graph()))

    def test_the_users_cut_is_forbidden(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        self.assertIn(pair(ALPHA, BETA), relink.forbidden_pairs(graph, [user_event("unlink", ALPHA, BETA)]))

    def test_a_pair_the_tool_removed_can_be_proposed_again(self):
        graph = sample_graph([key_of(ALPHA, BETA)])  # the tool's unlink is recorded as dismissed too
        events = [link_event(ALPHA, BETA, batch=B1), unlink_event(ALPHA, BETA, batch=B2)]
        self.assertNotIn(pair(ALPHA, BETA), relink.forbidden_pairs(graph, events))

    def test_an_undo_never_bans_its_pairs(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        events = [link_event(ALPHA, BETA, batch=B1), unlink_event(ALPHA, BETA, undo_of=B1)]
        self.assertNotIn(pair(ALPHA, BETA), relink.forbidden_pairs(graph, events))

    def test_a_users_dismissal_stays_when_the_tool_later_removes_the_line(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        events = [link_event(ALPHA, BETA, batch=B1), user_event("dismiss", ALPHA, BETA),
                  unlink_event(ALPHA, BETA, batch=B2)]
        self.assertIn(pair(ALPHA, BETA), relink.forbidden_pairs(graph, events))

    def test_an_undismiss_lifts_the_users_cut(self):
        graph = sample_graph([key_of(ALPHA, BETA)])
        events = [user_event("unlink", ALPHA, BETA), user_event("undismiss", ALPHA, BETA)]
        self.assertEqual(relink.user_blocked(events), set())
        self.assertNotIn(pair(ALPHA, BETA), relink.forbidden_pairs(graph, events))


class ParseTests(unittest.TestCase):
    def setUp(self):
        _, _, self.short = relink.build_prompt(sample_graph())
        self.forbidden = relink.forbidden_pairs(sample_graph())  # only IDEA1 with its parent GAMMA

    def test_numbers_map_back_and_labels_are_cut_to_eight_characters(self):
        content = '{"links": [{"a": "n1", "b": "n2", "kind": "supports", "label": "一二三四五六七八九十"}]}'
        kept, dropped = relink.parse(content, self.short, self.forbidden)
        self.assertEqual(kept, [{"a": ALPHA, "b": BETA, "kind": "supports", "label": "一二三四五六七八"}])
        self.assertEqual(dropped, {})

    def test_an_answer_already_decoded_is_accepted(self):
        kept, _ = relink.parse({"links": [{"a": "n1", "b": "n2", "kind": "same", "label": ""}]},
                               self.short, self.forbidden)
        self.assertEqual(len(kept), 1)

    def test_a_bad_answer_raises_and_keeps_nothing(self):
        for bad in ("not json", "[1, 2]", '{"links": "n1"}', '{"other": []}', None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    relink.parse(bad, self.short, self.forbidden)

    def test_each_reason_is_counted_and_only_the_bad_links_go(self):
        content = {"links": [
            {"a": "n1", "b": "n2", "kind": "supports", "label": "甲乙"},
            {"a": "n9", "b": "n1", "kind": "supports", "label": "x"},
            {"a": "n3", "b": "n3", "kind": "supports", "label": "x"},
            {"a": "n5", "b": "n3", "kind": "same", "label": "x"},
            {"a": "n2", "b": "n1", "kind": "extends", "label": "x"},
            {"a": "n4", "b": "n6", "kind": "part_of", "label": "x"},
        ]}
        kept, dropped = relink.parse(content, self.short, self.forbidden)
        self.assertEqual(kept, [{"a": ALPHA, "b": BETA, "kind": "supports", "label": "甲乙"}])
        self.assertEqual(dropped, {"编号不认识": 1, "自连": 1, "禁止对": 1, "重复": 1, "种类不对": 1})

    def test_a_point_takes_at_most_three_links(self):
        content = {"links": [{"a": "n6", "b": "n%d" % k, "kind": "supports", "label": ""} for k in (1, 2, 3, 4)]}
        kept, dropped = relink.parse(content, self.short, set())
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, {"超过每点上限": 1})

    def test_the_users_cut_is_dropped_as_forbidden(self):
        forbidden = relink.forbidden_pairs(sample_graph([key_of(ALPHA, BETA)]), [user_event("unlink", ALPHA, BETA)])
        kept, dropped = relink.parse({"links": [{"a": "n1", "b": "n2", "kind": "supports", "label": ""}]},
                                     self.short, forbidden)
        self.assertEqual((kept, dropped), ([], {"禁止对": 1}))


class FakeSwitchTests(unittest.TestCase):
    def test_real_ids_in_the_file_become_short_ids(self):
        _, _, short = relink.build_prompt(sample_graph())
        with tempfile.TemporaryDirectory(dir=TMP_ROOT) as folder:
            path = os.path.join(folder, "fake.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"links": [{"a": ALPHA, "b": IDEA2, "kind": "supports", "label": "x"}]}, f)
            kept, dropped = relink.parse(relink.fake_content(path, short), short, set())
        self.assertEqual((kept, dropped), ([{"a": ALPHA, "b": IDEA2, "kind": "supports", "label": "x"}], {}))


class PlanTests(unittest.TestCase):
    def test_a_new_pair_becomes_one_link_event_with_the_batch(self):
        result = relink.plan([proposal(ALPHA, BETA, "supports", "一条线")], [], LINKABLE, host="HOST", now=NOW)
        self.assertEqual((result["added"], result["changed"], result["removed"], result["kept_user"]), (1, 0, 0, 0))
        self.assertRegex(result["batch"], r"^[0-9a-f]{12}$")
        (event,) = result["events"]
        self.assertEqual((event["type"], event["a"], event["b"], event["kind"], event["label"]),
                         ("link", ALPHA, BETA, "supports", "一条线"))
        self.assertEqual((event["batch"], event["via"], event["host"], event["ts"]),
                         (result["batch"], "relink", "HOST", NOW))
        self.assertRegex(event["id"], r"^[0-9a-f]{32}$")

    def test_a_users_line_is_never_changed_or_removed(self):
        events = [link_event(ALPHA, BETA, "supports", "我的")]
        result = relink.plan([proposal(ALPHA, BETA, "extends", "模型")], events, LINKABLE, now=NOW)
        self.assertEqual((result["events"], result["kept_user"], result["batch"]), ([], 1, None))
        result = relink.plan([], events, LINKABLE, now=NOW)
        self.assertEqual((result["events"], result["removed"]), ([], 0))

    def test_kept_user_counts_the_users_lines_in_scope_even_when_not_proposed(self):
        events = [link_event(ALPHA, BETA, "supports", "我的")]
        self.assertEqual(relink.plan([], events, LINKABLE, now=NOW)["kept_user"], 1)
        self.assertEqual(relink.plan([], events, {ALPHA}, now=NOW)["kept_user"], 0)

    def test_linkable_can_be_left_out_of_the_call(self):
        self.assertEqual(relink.plan([proposal(ALPHA, BETA)], [], now=NOW)["added"], 1)
        removed = relink.plan([], [link_event(ALPHA, "idea:" + "9" * 32, batch=B1)], now=NOW)
        self.assertEqual(removed["removed"], 1)

    def test_a_line_the_batch_made_can_change_its_kind_or_label(self):
        events = [link_event(ALPHA, BETA, "supports", "旧", batch=B1)]
        result = relink.plan([proposal(ALPHA, BETA, "extends", "新")], events, LINKABLE, now=NOW)
        self.assertEqual((result["changed"], result["added"], result["removed"]), (1, 0, 0))
        (event,) = result["events"]
        self.assertEqual((event["type"], event["kind"], event["label"]), ("link", "extends", "新"))
        self.assertEqual(event["batch"], result["batch"])

    def test_a_line_the_batch_made_is_removed_when_it_is_not_proposed(self):
        events = [link_event(ALPHA, BETA, "supports", "", batch=B1)]
        result = relink.plan([], events, LINKABLE, now=NOW)
        self.assertEqual(result["removed"], 1)
        (event,) = result["events"]
        self.assertEqual((event["type"], event["a"], event["b"]), ("unlink", ALPHA, BETA))

    def test_an_unchanged_line_gives_no_events_and_no_batch(self):
        events = [link_event(ALPHA, BETA, "supports", "同", batch=B1)]
        result = relink.plan([proposal(ALPHA, BETA, "supports", "同")], events, LINKABLE, now=NOW)
        self.assertEqual((result["events"], result["batch"]), ([], None))

    def test_lines_outside_the_linkable_points_are_left_alone(self):
        events = [link_event(ALPHA, "idea:" + "9" * 32, "supports", "", batch=B1)]
        result = relink.plan([], events, LINKABLE, now=NOW)
        self.assertEqual((result["removed"], result["events"]), (0, []))

    def test_a_pair_the_tool_removed_is_added_again_when_proposed(self):
        events = [link_event(ALPHA, BETA, batch=B1), unlink_event(ALPHA, BETA, batch=B2)]
        result = relink.plan([proposal(ALPHA, BETA)], events, LINKABLE, now=NOW)
        self.assertEqual((result["added"], result["changed"]), (1, 0))


class UndoTests(unittest.TestCase):
    def test_undo_puts_back_what_the_newest_batch_changed(self):
        events = two_batches()
        self.assertEqual(relink.undo_target(events), B2)
        undo = relink.plan_undo(events, B2, host="HOST", now=NOW)
        self.assertEqual((undo["reverted"], undo["skipped"]), (2, 0))
        restored = {pair(e["a"], e["b"]): e for e in undo["events"]}
        self.assertEqual((restored[pair(ALPHA, BETA)]["type"], restored[pair(ALPHA, BETA)]["kind"],
                          restored[pair(ALPHA, BETA)]["label"]), ("link", "supports", "A"))
        self.assertEqual((restored[pair(GAMMA, DELTA)]["type"], restored[pair(GAMMA, DELTA)]["kind"],
                          restored[pair(GAMMA, DELTA)]["label"]), ("link", "extends", "B"))
        for event in undo["events"]:
            self.assertEqual((event["undo_of"], event["via"], event["host"]), (B2, "relink-undo", "HOST"))
            self.assertNotIn("batch", event)

    def test_after_an_undo_the_older_batch_has_nothing_left_to_undo(self):
        events = two_batches()
        undo = relink.plan_undo(events, B2, host="HOST", now=NOW)
        after = events + undo["events"]
        self.assertTrue(relink.status(after)["last"]["undone"])
        self.assertIsNone(relink.undo_target(after))

    def test_a_pair_the_user_touched_later_is_skipped(self):
        events = [link_event(ALPHA, BETA, "supports", "A", batch=B1, ts=T1),
                  link_event(GAMMA, DELTA, "extends", "B", batch=B1, ts=T1),
                  user_event("link", ALPHA, BETA, kind="same", label="手动")]
        target = relink.undo_target(events)
        undo = relink.plan_undo(events, target, host="HOST", now=NOW)
        self.assertEqual((target, undo["reverted"], undo["skipped"]), (B1, 1, 1))
        self.assertEqual([pair(e["a"], e["b"]) for e in undo["events"]], [pair(GAMMA, DELTA)])


class StatusTests(unittest.TestCase):
    def test_status_describes_the_newest_batch(self):
        last = relink.status(two_batches())["last"]
        self.assertEqual((last["batch"], last["ts"], last["added"], last["changed"], last["removed"], last["undone"]),
                         (B2, T2, 0, 1, 1, False))

    def test_no_batch_means_null(self):
        self.assertEqual(relink.status([]), {"last": None})
        self.assertEqual(relink.status([user_event("link", ALPHA, BETA, kind="same")]), {"last": None})
        self.assertIsNone(relink.undo_target([]))


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.join(TMP_ROOT, "relink-routes-" + uuid.uuid4().hex)
        cls.home = os.path.join(cls.tmp, "home")
        cls.state = os.path.join(cls.tmp, "state")
        for folder in (os.path.join(cls.home, "star"), os.path.join(cls.home, "push"), cls.state):
            os.makedirs(folder)
        with open(os.path.join(cls.home, "content.json"), "w", encoding="utf-8") as f:
            json.dump(CONTENT, f, ensure_ascii=False)
        with open(os.path.join(cls.home, "events-seed.jsonl"), "w", encoding="utf-8") as f:
            for number, (idea, text) in enumerate(((IDEA1, "想法一"), (IDEA2, "想法二")), 1):
                f.write(json.dumps({"id": uuid.uuid4().hex, "ts": "2026-11-01T00:00:0%d+00:00" % number,
                                    "host": "test", "type": "idea", "idea_id": idea[len("idea:"):],
                                    "text": text}, ensure_ascii=False) + "\n")
        shutil.copyfile(os.path.join(HERE, "domains.json"), os.path.join(cls.home, "star", "domains.json"))
        cls.saved_env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = cls.state
        names = ("HOME", "CONTENT", "INDEX", "HANDOFF_DIR", "PREPARED_DIR", "PUSH_DIR", "BRIEF",
                 "LIST_MD", "EVENTS", "VAULT", "ALLOWED_HOSTS")
        cls.saved = {name: getattr(SERVER, name) for name in names}
        SERVER.HOME = cls.home
        SERVER.CONTENT = os.path.join(cls.home, "content.json")
        SERVER.INDEX = os.path.join(cls.home, "index.html")
        SERVER.HANDOFF_DIR = os.path.join(cls.home, "handoff")
        SERVER.PREPARED_DIR = os.path.join(cls.home, "prepared")
        SERVER.PUSH_DIR = os.path.join(cls.home, "push")
        SERVER.BRIEF = os.path.join(cls.home, "brief.md")
        SERVER.LIST_MD = os.path.join(cls.home, "list.md")
        SERVER.EVENTS = os.path.join(cls.home, "events-%s.jsonl" % SERVER.HOST)
        SERVER.VAULT = cls.tmp
        cls.httpd = SERVER.HomeServer(("127.0.0.1", 0), SERVER.Handler)
        cls.port = cls.httpd.server_address[1]
        SERVER.ALLOWED_HOSTS = {"127.0.0.1:%d" % cls.port, "localhost:%d" % cls.port}
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.key_patch = mock.patch.object(SERVER._starmodel, "KEY", "")
        cls.key_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.key_patch.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        if cls.saved_env is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = cls.saved_env
        for name, value in cls.saved.items():
            setattr(SERVER, name, value)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        for path in (self.star_events_path(), os.path.join(self.home, "star", "relink.js")):
            if os.path.exists(path):
                os.remove(path)

    def star_events_path(self):
        return os.path.join(self.home, "events-star-%s.jsonl" % SERVER.HOST)

    def request(self, method, path, body=None):
        headers, data = {}, None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection = HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            try:
                parsed = json.loads(payload.decode("utf-8")) if payload else None
            except ValueError:
                parsed = payload.decode("utf-8", "replace")
            return response.status, parsed
        finally:
            connection.close()

    def write_fake(self, links):
        path = os.path.join(self.tmp, "fake-%s.json" % uuid.uuid4().hex)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"links": links}, f, ensure_ascii=False)
        return path

    def fake_run(self, links):
        with mock.patch.dict(os.environ, {"STAR_RELINK_FAKE": self.write_fake(links)}):
            return self.request("POST", "/api/star/relink")

    def shown(self):
        """({pair: (kind, label)} for the links the map shows, and the dismissed list)."""
        status, graph = self.request("GET", "/api/star")
        self.assertEqual(status, 200)
        lines = {pair(link["a"], link["b"]): (link["kind"], link["label"]) for link in graph["links"]}
        return lines, graph["dismissed"]

    def test_no_model_and_no_fake_is_503_and_writes_nothing(self):
        with mock.patch.dict(os.environ), mock.patch.object(SERVER._starmodel, "ask") as ask:
            os.environ.pop("STAR_RELINK_FAKE", None)
            status, body = self.request("POST", "/api/star/relink")
        self.assertEqual((status, body), (503, {"ok": False, "error": "no model"}))
        ask.assert_not_called()
        self.assertFalse(os.path.exists(self.star_events_path()))

    def test_one_click_writes_one_batch_that_shows_on_the_map(self):
        before = self.request("GET", "/api/version")[1]["v"]
        status, body = self.fake_run([proposal(ALPHA, BETA, "supports", "同一条线"),
                                      proposal(IDEA1, GAMMA, "extends", "下一步")])
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertRegex(body["batch"], r"^[0-9a-f]{12}$")
        self.assertEqual((body["added"], body["changed"], body["removed"], body["kept_user"], body["dropped"]),
                         (2, 0, 0, 0, {}))
        self.assertNotEqual(self.request("GET", "/api/version")[1]["v"], before)
        lines, _ = self.shown()
        self.assertEqual(lines[pair(ALPHA, BETA)], ("supports", "同一条线"))
        self.assertEqual(lines[pair(IDEA1, GAMMA)], ("extends", "下一步"))
        status, last = self.request("GET", "/api/star/relink-status")
        self.assertEqual((status, last["last"]["batch"], last["last"]["undone"]), (200, body["batch"], False))

    def test_undo_takes_the_batch_off_the_map_and_undoing_again_says_nothing(self):
        links = [proposal(ALPHA, BETA, "supports", "一"), proposal(IDEA1, GAMMA, "extends", "二")]
        _, body = self.fake_run(links)
        status, undo = self.request("POST", "/api/star/relink-undo")
        self.assertEqual((status, undo), (200, {"ok": True, "undone": body["batch"], "reverted": 2, "skipped": 0}))
        lines, _ = self.shown()
        self.assertNotIn(pair(ALPHA, BETA), lines)
        self.assertNotIn(pair(IDEA1, GAMMA), lines)
        self.assertTrue(self.request("GET", "/api/star/relink-status")[1]["last"]["undone"])
        self.assertEqual(self.request("POST", "/api/star/relink-undo"), (200, {"ok": True, "undone": None}))
        # an undo never bans its pairs: the same lines can be made again
        _, again = self.fake_run(links)
        self.assertEqual((again["added"], again["dropped"]), (2, {}))

    def test_a_pair_the_tool_removed_can_come_back_but_a_users_cut_cannot(self):
        self.fake_run([proposal(ALPHA, BETA, "supports", "一"), proposal(GAMMA, DELTA, "extends", "二")])
        _, removed = self.fake_run([proposal(GAMMA, DELTA, "extends", "二")])
        self.assertEqual((removed["added"], removed["removed"]), (0, 1))
        _, dismissed = self.shown()
        self.assertIn(key_of(ALPHA, BETA), dismissed)  # starapi records the tool's unlink as dismissed...
        _, back = self.fake_run([proposal(ALPHA, BETA, "supports", "一"), proposal(GAMMA, DELTA, "extends", "二")])
        self.assertEqual((back["added"], back["dropped"]), (1, {}))  # ...but that does not forbid the pair
        status, _ = self.request("POST", "/api/star-event", {"type": "unlink", "a": GAMMA, "b": DELTA})
        self.assertEqual(status, 200)
        _, refused = self.fake_run([proposal(GAMMA, DELTA, "extends", "二"), proposal(ALPHA, BETA, "supports", "一")])
        self.assertEqual((refused["dropped"], refused["batch"]), ({"禁止对": 1}, None))
        lines, _ = self.shown()
        self.assertNotIn(pair(GAMMA, DELTA), lines)

    def test_changed_and_removed_lines_come_back_when_undone(self):
        self.fake_run([proposal(ALPHA, BETA, "supports", "甲"), proposal(GAMMA, DELTA, "extends", "乙")])
        _, second = self.fake_run([proposal(ALPHA, BETA, "contradicts", "丙")])
        self.assertEqual((second["added"], second["changed"], second["removed"]), (0, 1, 1))
        lines, _ = self.shown()
        self.assertEqual(lines[pair(ALPHA, BETA)], ("contradicts", "丙"))
        self.assertNotIn(pair(GAMMA, DELTA), lines)
        _, undo = self.request("POST", "/api/star/relink-undo")
        self.assertEqual(undo, {"ok": True, "undone": second["batch"], "reverted": 2, "skipped": 0})
        lines, _ = self.shown()
        self.assertEqual(lines[pair(ALPHA, BETA)], ("supports", "甲"))
        self.assertEqual(lines[pair(GAMMA, DELTA)], ("extends", "乙"))
        # the undo handed those lines back to the user, so the first batch has nothing left to undo
        self.assertEqual(self.request("POST", "/api/star/relink-undo")[1], {"ok": True, "undone": None})

    def test_undo_leaves_alone_the_pairs_the_user_touched(self):
        self.fake_run([proposal(ALPHA, BETA, "supports", "甲"), proposal(GAMMA, DELTA, "extends", "乙")])
        self.request("POST", "/api/star-event", {"type": "link", "a": ALPHA, "b": BETA, "kind": "same", "label": "手动"})
        _, undo = self.request("POST", "/api/star/relink-undo")
        self.assertEqual((undo["reverted"], undo["skipped"]), (1, 1))
        lines, _ = self.shown()
        self.assertEqual(lines[pair(ALPHA, BETA)], ("same", "手动"))
        self.assertNotIn(pair(GAMMA, DELTA), lines)

    def test_a_run_already_going_gives_409(self):
        self.assertTrue(SERVER.RELINK_LOCK.acquire(blocking=False))
        try:
            with mock.patch.dict(os.environ, {"STAR_RELINK_FAKE": self.write_fake([])}):
                self.assertEqual(self.request("POST", "/api/star/relink"), (409, {"ok": False, "error": "busy"}))
            self.assertEqual(self.request("POST", "/api/star/relink-undo"), (409, {"ok": False, "error": "busy"}))
        finally:
            SERVER.RELINK_LOCK.release()

    def test_model_failures_are_502_and_write_nothing(self):
        with mock.patch.dict(os.environ), mock.patch.object(SERVER._starmodel, "KEY", "test-key"):
            os.environ.pop("STAR_RELINK_FAKE", None)
            with mock.patch.object(SERVER._starmodel, "ask", side_effect=RuntimeError("boom")) as ask:
                status, body = self.request("POST", "/api/star/relink")
            self.assertEqual((status, body), (502, {"ok": False, "error": "model error"}))
            _, kwargs = ask.call_args
            self.assertEqual((kwargs["max_tokens"], kwargs["timeout"]), (4000, 90))
            with mock.patch.object(SERVER._starmodel, "ask", return_value=["not", "a", "links", "object"]):
                status, body = self.request("POST", "/api/star/relink")
            self.assertEqual((status, body), (502, {"ok": False, "error": "bad output"}))
        self.assertFalse(os.path.exists(self.star_events_path()))
        self.assertEqual(self.request("GET", "/api/star/relink-status")[1], {"last": None})

    def test_a_users_edits_made_while_the_model_answers_are_respected(self):
        def user_edits_meanwhile(*args, **kwargs):
            # written while the model is still answering: a link on n1-n2 and a cut on n3-n4
            for body in ({"type": "link", "a": ALPHA, "b": BETA, "kind": "same", "label": "手动"},
                         {"type": "unlink", "a": GAMMA, "b": DELTA}):
                ev, _ = SERVER.validate_star_event(body)
                SERVER.append_star_event(ev)
            return {"links": [{"a": "n1", "b": "n2", "kind": "supports", "label": "模型"},
                              {"a": "n3", "b": "n4", "kind": "extends", "label": "模型"}]}

        with mock.patch.dict(os.environ), mock.patch.object(SERVER._starmodel, "KEY", "test-key"):
            os.environ.pop("STAR_RELINK_FAKE", None)
            with mock.patch.object(SERVER._starmodel, "ask", side_effect=user_edits_meanwhile) as ask:
                status, body = self.request("POST", "/api/star/relink")
        self.assertEqual(status, 200)
        _, kwargs = ask.call_args
        self.assertEqual((kwargs["max_tokens"], kwargs["timeout"]), (4000, 90))
        self.assertEqual((body["batch"], body["kept_user"], body["dropped"]), (None, 1, {"禁止对": 1}))
        lines, _ = self.shown()
        self.assertEqual(lines[pair(ALPHA, BETA)], ("same", "手动"))
        self.assertNotIn(pair(GAMMA, DELTA), lines)

    def test_relink_js_is_served_once_it_exists(self):
        self.assertEqual(self.request("GET", "/star/relink.js")[0], 404)
        path = os.path.join(self.home, "star", "relink.js")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("// placeholder\n")
        try:
            status, body = self.request("GET", "/star/relink.js")
        finally:
            os.remove(path)
        self.assertEqual((status, body), (200, "// placeholder\n"))

    def test_status_and_undo_say_nothing_before_any_batch(self):
        self.assertEqual(self.request("GET", "/api/star/relink-status"), (200, {"last": None}))
        self.assertEqual(self.request("POST", "/api/star/relink-undo"), (200, {"ok": True, "undone": None}))


if __name__ == "__main__":
    unittest.main()
