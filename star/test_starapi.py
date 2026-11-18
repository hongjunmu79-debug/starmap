#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for star/starapi.build_graph (temporary homes only)."""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import date

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.abspath(os.path.join(HERE, ".."))
if HOME not in sys.path:
    sys.path.insert(0, HOME)

from star.starapi import build_graph  # noqa: E402


def _pick_tmp_root():
    candidates = [
        os.environ.get("C1_TEST_TMP"),
        os.path.join(os.path.dirname(os.path.dirname(HOME)), "_tmp"),
        tempfile.gettempdir(),
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
        "agent_home_server_starapi_test", os.path.join(HOME, "server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = _load_server()


def _event(event_type, ts, **fields):
    event = {"id": fields.pop("id", uuid.uuid4().hex), "ts": ts, "host": "test", "type": event_type}
    event.update(fields)
    return event


class StarApiTests(unittest.TestCase):
    def _home(self):
        path = os.path.join(TMP_ROOT, "starapi-" + uuid.uuid4().hex)
        os.makedirs(path)
        self.addCleanup(shutil.rmtree, path, True)
        shutil.copyfile(os.path.join(HOME, "content.json"), os.path.join(path, "content.json"))
        os.makedirs(os.path.join(path, "star"))
        shutil.copyfile(os.path.join(HERE, "domains.json"), os.path.join(path, "star", "domains.json"))
        return path

    def _write(self, home, name, rows):
        with open(os.path.join(home, name), "a", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(row if isinstance(row, str) else json.dumps(row, ensure_ascii=False))
                f.write("\n")

    def _graph(self, home, today=date(2026, 11, 9)):
        return build_graph(home, today=today)

    def _node(self, graph, node_id):
        return next(node for node in graph["nodes"] if node["id"] == node_id)

    def _link(self, graph, a, b):
        key = "|".join(sorted((a, b)))
        return next((link for link in graph["links"]
                     if "|".join(sorted((link["a"], link["b"]))) == key), None)

    def _pool_from_server(self, home):
        old = SERVER.HOME
        SERVER.HOME = home
        try:
            return SERVER.compute_state(SERVER.read_events())["ideas"]
        finally:
            SERVER.HOME = old

    def test_real_content_nodes_and_pool_match(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="a", text="想法 A"),
            _event("idea", "2026-11-06T15:01:00+00:00", idea_id="b", text="想法 B"),
            _event("idea_edit", "2026-11-06T15:02:00+00:00", idea_id="b", text="想法 B2"),
            _event("idea_note", "2026-11-06T15:03:00+00:00", idea_id="a",
                   belongs="offline-social", first_step="先写一页纸"),
            _event("idea_drop", "2026-11-06T15:04:00+00:00", idea_id="b", reason="star"),
        ])
        graph = self._graph(home)
        items = [node for node in graph["nodes"] if node["kind"] == "item"]
        includes = [node for node in graph["nodes"] if node["kind"] == "inc"]
        self.assertEqual(len(items), 19)
        self.assertEqual(len(includes), 48)
        self.assertEqual(graph["version"], 1)
        self.assertEqual(len(graph["groups"]), 6)

        idea_a = self._node(graph, "idea:a")
        idea_b = self._node(graph, "idea:b")
        self.assertEqual(idea_a["state"], "pool")
        self.assertEqual(idea_a["belongs"], "offline-social")
        self.assertEqual(idea_b["state"], "star")
        self.assertEqual(idea_b["text"], "想法 B2")

        item = self._node(graph, "item:personal-os")
        self.assertEqual(item["domain"], "self")
        self.assertEqual(item["color"], "#9B7BFF")
        self.assertEqual(item["brightness"], 1.0)
        self.assertEqual(self._node(graph, "item:lyrics")["brightness"], 1.3)

        link = self._link(graph, "idea:a", "item:offline-social")
        self.assertIsNotNone(link)
        self.assertEqual(link["state"], "suggested")
        self.assertEqual(link["kind"], "part_of")
        self.assertFalse(any(node.get("first_step") for node in graph["nodes"]))

        expected = self._pool_from_server(home)
        actual = [node for node in graph["nodes"] if node["kind"] == "idea" and node["state"] == "pool"]
        self.assertEqual(sorted((idea["id"], idea["text"]) for idea in expected),
                         sorted((node["id"][len("idea:"):], node["text"]) for node in actual))

    def test_link_priority_dedupe_unlink_and_dismiss(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="x", text="X"),
            _event("idea", "2026-11-06T15:00:01+00:00", idea_id="y", text="Y"),
            _event("idea", "2026-11-06T15:00:02+00:00", idea_id="z", text="Z"),
            _event("idea_note", "2026-11-06T15:00:03+00:00", idea_id="x",
                   belongs="offline-social", first_step=""),
            _event("suggest", "2026-11-06T15:00:04+00:00", a="idea:x", b="item:offline-social",
                   kind="supports", label="同类吗？", why="都在说线下"),
            _event("link", "2026-11-06T15:00:05+00:00", a="idea:x", b="item:offline-social",
                   kind="extends", label="接着做"),
            _event("suggest", "2026-11-06T15:00:06+00:00", a="idea:y", b="item:personal-os",
                   kind="supports", label="要合并吗？", why=""),
            _event("unlink", "2026-11-06T15:00:07+00:00", a="idea:y", b="item:personal-os"),
            _event("suggest", "2026-11-06T15:00:08+00:00", a="idea:z", b="item:content",
                   kind="same", label="是一件事吗？", why=""),
            _event("dismiss", "2026-11-06T15:00:09+00:00", a="idea:z", b="item:content"),
        ])
        graph = self._graph(home)

        link = self._link(graph, "idea:x", "item:offline-social")
        self.assertIsNotNone(link)
        self.assertEqual(link["state"], "confirmed")
        self.assertEqual(link["kind"], "extends")
        self.assertEqual(sum(1 for candidate in graph["links"]
                             if "|".join(sorted((candidate["a"], candidate["b"])))
                             == "idea:x|item:offline-social"), 1)
        self.assertIsNone(self._link(graph, "idea:y", "item:personal-os"))
        self.assertIsNone(self._link(graph, "idea:z", "item:content"))
        self.assertIn("idea:y|item:personal-os", graph["dismissed"])
        self.assertIn("idea:z|item:content", graph["dismissed"])

    def test_unlink_removes_structural_edge_but_keeps_include(self):
        home = self._home()
        text = "一键备课"
        inc_id = "inc:school:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        self._write(home, "events-a.jsonl", [
            _event("unlink", "2026-11-06T15:00:00+00:00", a=inc_id, b="item:school"),
        ])
        graph = self._graph(home)
        self.assertIsNone(self._link(graph, inc_id, "item:school"))
        self.assertIn(inc_id, {node["id"] for node in graph["nodes"]})
        self.assertIn("|".join(sorted((inc_id, "item:school"))), graph["dismissed"])

    def test_unlink_then_link_returns_confirmed_link(self):
        home = self._home()
        text = "一键备课"
        inc_id = "inc:school:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        self._write(home, "events-a.jsonl", [
            _event("unlink", "2026-11-06T15:00:00+00:00", a=inc_id, b="item:school"),
            _event("link", "2026-11-06T15:00:01+00:00", a=inc_id, b="item:school",
                   kind="supports", label="能复用吗？"),
        ])
        graph = self._graph(home)
        link = self._link(graph, inc_id, "item:school")
        self.assertIsNotNone(link)
        self.assertEqual(link["state"], "confirmed")
        self.assertEqual(link["kind"], "supports")
        self.assertEqual(link["label"], "能复用吗？")

    def test_link_then_unlink_returns_no_link(self):
        home = self._home()
        text = "一键备课"
        inc_id = "inc:school:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        self._write(home, "events-a.jsonl", [
            _event("link", "2026-11-06T15:00:00+00:00", a=inc_id, b="item:school",
                   kind="supports", label="先连上"),
            _event("unlink", "2026-11-06T15:00:01+00:00", a=inc_id, b="item:school"),
        ])
        graph = self._graph(home)
        self.assertIsNone(self._link(graph, inc_id, "item:school"))
        self.assertIn(inc_id, {node["id"] for node in graph["nodes"]})

    def test_merge_alias_moves_links(self):
        home = self._home()
        text_one, text_two = "一键备课", "老师工作台"
        inc_one = "inc:school:" + hashlib.sha1(text_one.encode("utf-8")).hexdigest()[:8]
        inc_two = "inc:school:" + hashlib.sha1(text_two.encode("utf-8")).hexdigest()[:8]
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="m", text="old"),
            _event("idea_edit", "2026-11-06T15:00:01+00:00", idea_id="m", text=text_one),
            _event("idea_drop", "2026-11-06T15:00:02+00:00", idea_id="m",
                   reason="merged", into="school", **{"as": text_one}),
            _event("link", "2026-11-06T15:00:03+00:00", a="idea:m", b="item:personal-os",
                   kind="supports", label="能复用吗？"),
            _event("idea", "2026-11-06T15:00:04+00:00", idea_id="n", text=text_two),
            _event("idea_drop", "2026-11-06T15:00:05+00:00", idea_id="n"),
            _event("suggest", "2026-11-06T15:00:06+00:00", a="idea:n", b="item:content",
                   kind="same", label="是一件事吗？", why=""),
        ])
        graph = self._graph(home)
        ids = {node["id"] for node in graph["nodes"]}
        self.assertNotIn("idea:m", ids)
        self.assertNotIn("idea:n", ids)
        self.assertIn(inc_one, ids)
        self.assertIn(inc_two, ids)
        self.assertIsNotNone(self._link(graph, inc_one, "item:personal-os"))
        self.assertIsNotNone(self._link(graph, inc_two, "item:content"))
        self.assertEqual(graph["dropped_links"], 0)

    def test_bad_lines_duplicate_ids_and_missing_links(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            "{not json",
            "[]",
            _event("idea", "2026-11-06T15:00:00+00:00", id="dup", idea_id="dup", text="first"),
            _event("link", "2026-11-06T15:00:01+00:00", a="idea:missing", b="item:personal-os",
                   kind="supports", label="?"),
        ])
        self._write(home, "events-b.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", id="dup", idea_id="dup", text="second"),
        ])
        graph = self._graph(home)
        ideas = [node for node in graph["nodes"] if node["kind"] == "idea"]
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["text"], "first")
        self.assertEqual(graph["dropped_links"], 1)
        self.assertFalse(any(link["a"] == "idea:missing" for link in graph["links"]))

    def test_pin_edit_collapse_and_suggest_node(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="x", text="old"),
            _event("pin", "2026-11-06T15:00:01+00:00", node="idea:x", x=12.5, y=-3),
            _event("edit", "2026-11-06T15:00:02+00:00", node="idea:x", text="new text"),
            _event("collapse", "2026-11-06T15:00:03+00:00", node="idea:x", on=True),
            _event("suggest_node", "2026-11-06T15:00:04+00:00", id="sn1",
                   parent="idea:x", text="先写一页", lens="第一步", to="item:personal-os"),
            _event("suggest_node", "2026-11-06T15:00:05+00:00", id="sn2",
                   parent="idea:x", text="不要这条", lens="卡在"),
            _event("dismiss_node", "2026-11-06T15:00:06+00:00", node="poss:sn2"),
        ])
        graph = self._graph(home)
        idea = self._node(graph, "idea:x")
        self.assertEqual(idea["text"], "new text")
        self.assertEqual(idea["pin"], {"x": 12.5, "y": -3})
        self.assertTrue(idea["collapsed"])
        poss = self._node(graph, "poss:sn1")
        self.assertEqual(poss["kind"], "poss")
        self.assertEqual(poss["state"], "suggested")
        self.assertEqual(poss["lens"], "第一步")
        self.assertEqual(poss["parent"], "idea:x")
        self.assertEqual(poss["to"], "item:personal-os")
        self.assertNotIn("poss:sn2", {node["id"] for node in graph["nodes"]})

    def test_first_step_only_inside_plan_window(self):
        home = self._home()
        os.makedirs(os.path.join(home, "push"))
        shutil.copyfile(os.path.join(HOME, "push", "plan.json"),
                        os.path.join(home, "push", "plan.json"))
        with open(os.path.join(HOME, "push", "plan.json"), encoding="utf-8") as f:
            plan = json.load(f)
        expected = {}
        for unit in plan["units"]:
            if unit.get("kind") == "home" and unit.get("item") not in expected:
                expected[unit["item"]] = {"text": unit["step"], "unit": unit["unit"]}

        graph = self._graph(home, today=date(2026, 11, 10))
        self.assertTrue(expected)
        for item_id, first_step in expected.items():
            node = self._node(graph, "item:" + item_id)
            self.assertEqual(node["first_step"], first_step)
        self.assertNotIn("first_step", self._node(graph, "item:personal-os"))

        for outside in (date(2026, 11, 9), date(2026, 11, 24)):
            graph = self._graph(home, today=outside)
            self.assertFalse(any(node.get("first_step") for node in graph["nodes"]))

    def test_suggestion_beats_structural_edge_and_promote_changes_status(self):
        home = self._home()
        inc_id = "inc:school:" + hashlib.sha1("一键备课".encode("utf-8")).hexdigest()[:8]
        self._write(home, "events-a.jsonl", [
            _event("promote", "2026-11-06T15:00:00+00:00", item="personal-os", to="frozen"),
            _event("suggest", "2026-11-06T15:00:01+00:00", a=inc_id, b="item:school",
                   kind="supports", label="撑得住吗？", why=""),
        ])
        graph = self._graph(home)
        item = self._node(graph, "item:personal-os")
        self.assertEqual(item["status"], "frozen")
        self.assertEqual(item["brightness"], 0.55)
        link = self._link(graph, inc_id, "item:school")
        self.assertIsNotNone(link)
        self.assertEqual(link["state"], "suggested")

    def test_deleted_idea_can_return_to_pool(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="x", text="v1"),
            _event("idea_drop", "2026-11-06T15:00:01+00:00", idea_id="x", reason="deleted"),
            _event("idea", "2026-11-06T15:00:02+00:00", idea_id="x", text="v2"),
        ])
        graph = self._graph(home)
        self.assertEqual(self._node(graph, "idea:x")["text"], "v2")
        expected = self._pool_from_server(home)
        self.assertEqual([idea["text"] for idea in expected], ["v2"])

    def test_undismiss_restores_suggestion_and_last_action_wins(self):
        home = self._home()
        pair = ("idea:x", "item:personal-os")
        pair_key = "|".join(sorted(pair))
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="x", text="X"),
            _event("suggest", "2026-11-06T15:00:01+00:00", a=pair[0], b=pair[1],
                   kind="supports", label="同类吗？", why=""),
            _event("dismiss", "2026-11-06T15:00:02+00:00", a=pair[0], b=pair[1]),
        ])
        graph = self._graph(home)
        self.assertIsNone(self._link(graph, *pair))
        self.assertIn(pair_key, graph["dismissed"])

        self._write(home, "events-a.jsonl", [
            _event("undismiss", "2026-11-06T15:00:03+00:00", a=pair[0], b=pair[1]),
        ])
        graph = self._graph(home)
        link = self._link(graph, *pair)
        self.assertIsNotNone(link)
        self.assertEqual(link["state"], "suggested")
        self.assertNotIn(pair_key, graph["dismissed"])

        self._write(home, "events-a.jsonl", [
            _event("dismiss", "2026-11-06T15:00:04+00:00", a=pair[0], b=pair[1]),
        ])
        self.assertIsNone(self._link(self._graph(home), *pair))

    def test_undismiss_node_brings_back_only_that_possibility(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", idea_id="x", text="X"),
            _event("suggest_node", "2026-11-06T15:00:01+00:00", id="sn1",
                   parent="idea:x", text="先写一页", lens="第一步"),
            _event("suggest_node", "2026-11-06T15:00:02+00:00", id="sn2",
                   parent="idea:x", text="另一条", lens="卡在"),
            _event("suggest_node", "2026-11-06T15:00:03+00:00", id="sn3",
                   parent="idea:x", text="第三条", lens="像"),
            _event("dismiss_node", "2026-11-06T15:00:04+00:00", node="poss:sn1"),
            _event("dismiss_node", "2026-11-06T15:00:05+00:00", node="sn2"),
            _event("dismiss_node", "2026-11-06T15:00:06+00:00", node="poss:sn3"),
        ])
        ids = {node["id"] for node in self._graph(home)["nodes"]}
        self.assertFalse({"poss:sn1", "poss:sn2", "poss:sn3"} & ids)

        self._write(home, "events-a.jsonl", [
            _event("undismiss_node", "2026-11-06T15:00:07+00:00", node="poss:sn1"),
            _event("undismiss_node", "2026-11-06T15:00:08+00:00", node="sn2"),
        ])
        ids = {node["id"] for node in self._graph(home)["nodes"]}
        self.assertIn("poss:sn1", ids)
        self.assertIn("poss:sn2", ids)
        self.assertNotIn("poss:sn3", ids)

    def test_idea_node_uses_idea_id_and_matches_server_pool(self):
        home = self._home()
        self._write(home, "events-a.jsonl", [
            _event("idea", "2026-11-06T15:00:00+00:00", id="e-own-1", idea_id="kept", text="自带编号"),
            _event("idea", "2026-11-06T15:00:01+00:00", id="e-own-2", text="没带编号"),
        ])
        graph = self._graph(home)
        self.assertEqual(self._node(graph, "idea:kept")["text"], "自带编号")
        self.assertEqual(self._node(graph, "idea:e-own-2")["text"], "没带编号")
        self.assertEqual(sorted(idea["id"] for idea in self._pool_from_server(home)), ["e-own-2", "kept"])


if __name__ == "__main__":
    unittest.main()
