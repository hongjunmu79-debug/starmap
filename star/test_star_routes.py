#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Route tests for /star, /api/star, /api/star-event and the model bridge.

The server is started on port 8810 against a temporary home.  No test touches
the real event log or calls DeepSeek: the model tests force the no-key path.
"""

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.client import HTTPConnection
from unittest import mock

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.abspath(os.path.join(HERE, ".."))
if HOME not in sys.path:
    sys.path.insert(0, HOME)


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
PORT = 8810


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "agent_home_server_star_routes_test", os.path.join(HOME, "server.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = _load_server()


class StarRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.join(TMP_ROOT, "star-routes-" + uuid.uuid4().hex)
        cls.home = os.path.join(cls.tmp, "home")
        cls.state = os.path.join(cls.tmp, "state")
        os.makedirs(cls.home)
        os.makedirs(cls.state)
        os.makedirs(os.path.join(cls.home, "star"))
        os.makedirs(os.path.join(cls.home, "push"))
        shutil.copyfile(os.path.join(HOME, "content.json"), os.path.join(cls.home, "content.json"))
        shutil.copyfile(os.path.join(HERE, "domains.json"),
                        os.path.join(cls.home, "star", "domains.json"))
        shutil.copyfile(os.path.join(HOME, "push", "plan.json"),
                        os.path.join(cls.home, "push", "plan.json"))
        with open(os.path.join(cls.home, "index.html"), "w", encoding="utf-8") as f:
            f.write("<html>test</html>")

        cls.saved = {}
        cls.saved_env = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = cls.state
        for name in ("HOME", "CONTENT", "INDEX", "HANDOFF_DIR", "PREPARED_DIR", "PUSH_DIR",
                     "BRIEF", "LIST_MD", "EVENTS", "VAULT", "ALLOWED_HOSTS"):
            cls.saved[name] = getattr(SERVER, name)
        SERVER.HOME = cls.home
        SERVER.CONTENT = os.path.join(cls.home, "content.json")
        SERVER.INDEX = os.path.join(cls.home, "index.html")
        SERVER.HANDOFF_DIR = os.path.join(cls.home, "handoff")
        SERVER.PREPARED_DIR = os.path.join(cls.home, "prepared")
        SERVER.PUSH_DIR = os.path.join(cls.home, "push")
        SERVER.BRIEF = os.path.join(cls.home, "brief.md")
        SERVER.LIST_MD = os.path.join(cls.home, "全部清单.md")
        SERVER.EVENTS = os.path.join(cls.home, "events-%s.jsonl" % SERVER.HOST)
        SERVER.VAULT = os.path.dirname(cls.home)
        SERVER.ALLOWED_HOSTS = {"127.0.0.1:%d" % PORT, "localhost:%d" % PORT}
        os.makedirs(SERVER.HANDOFF_DIR, exist_ok=True)
        os.makedirs(SERVER.PREPARED_DIR, exist_ok=True)

        cls.httpd = SERVER.HomeServer(("127.0.0.1", PORT), SERVER.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        for _ in range(40):
            try:
                status, _ = cls.request("GET", "/health")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("test server did not start")

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

    def _write_star(self, html):
        page = os.path.join(self.home, "star", "star.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write(html)
        return page

    @classmethod
    def request(cls, method, path, body=None, host=None, origin=None):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        connection = HTTPConnection("127.0.0.1", PORT, timeout=10)
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

    def test_star_page_404_then_200_and_open_log(self):
        status, _ = self.request("GET", "/star")
        self.assertEqual(status, 404)
        page = os.path.join(self.home, "star", "star.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write("<html>star</html>")
        status, body = self.request("GET", "/star")
        self.assertEqual(status, 200)
        self.assertIn("star", body)
        log_path = os.path.join(self.state, "agent-home", "star-opens.jsonl")
        self.assertTrue(os.path.isfile(log_path))
        with open(log_path, encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["host"], SERVER.HOST_RAW)
        self.assertIn("ts", rows[-1])

    def test_api_star_returns_graph(self):
        status, graph = self.request("GET", "/api/star")
        self.assertEqual(status, 200)
        self.assertEqual(graph["version"], 1)
        self.assertEqual(len([n for n in graph["nodes"] if n["kind"] == "item"]), 19)
        self.assertEqual(len([n for n in graph["nodes"] if n["kind"] == "inc"]), 48)
        self.assertIn("dismissed", graph)
        self.assertIn("dropped_links", graph)

    def test_api_version_fingerprint(self):
        status, body = self.request("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertRegex(body["v"], re.compile(r"^[0-9a-f]{16}$"))
        path = os.path.join(self.home, "events-version-%s.jsonl" % uuid.uuid4().hex)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"type": "version-test"}\n')
            status, first = self.request("GET", "/api/version")
            self.assertEqual(status, 200)
            self.assertRegex(first["v"], re.compile(r"^[0-9a-f]{16}$"))
            with open(path, "a", encoding="utf-8") as f:
                f.write('{"type": "version-test-2"}\n')
            status, second = self.request("GET", "/api/version")
            self.assertEqual(status, 200)
            self.assertNotEqual(first["v"], second["v"])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        status, _ = self.request("GET", "/api/version", host="evil.example")
        self.assertEqual(status, 403)

    def test_api_star_health_reports_model_availability(self):
        old = SERVER._starmodel.KEY
        try:
            SERVER._starmodel.KEY = ""
            status, result = self.request("GET", "/api/star/health")
            self.assertEqual(status, 200)
            self.assertEqual(result, {"model": False})
            SERVER._starmodel.KEY = "test-key"
            status, result = self.request("GET", "/api/star/health")
            self.assertEqual(status, 200)
            self.assertEqual(result, {"model": True})
        finally:
            SERVER._starmodel.KEY = old

    def test_star_page_build_graph_failure_is_contained(self):
        self._write_star("<html><head><!--STAR_GRAPH--></head><body></body></html>")
        with mock.patch.object(SERVER._starapi, "build_graph",
                               side_effect=RuntimeError("boom")):
            status, body = self.request("GET", "/star")
        self.assertEqual(status, 200)
        self.assertIn('{"error": "graph unavailable"}', body)

    def test_star_page_injects_graph_and_escapes_unsafe_text(self):
        evil = "</script><script>alert(1)</script>"
        suffix = "&\u2028<>\u2029end"
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "idea", "text": evil + suffix})
        self.assertEqual(status, 200)
        self._write_star("<!doctype html><html><head><!--STAR_GRAPH--></head>"
                         "<body>star</body></html>")
        status, body = self.request("GET", "/star")
        self.assertEqual(status, 200)
        self.assertIn('<script id="star-graph" type="application/json">', body)
        self.assertNotIn(evil, body)
        match = re.search(r'<script id="star-graph" type="application/json">(.*?)</script>',
                          body, re.S)
        self.assertIsNotNone(match)
        raw = match.group(1)
        self.assertIn("\\u003c/script\\u003e", raw)
        self.assertIn("\\u0026", raw)
        self.assertIn("\\u2028", raw)
        self.assertIn("\\u2029", raw)
        graph = json.loads(raw)
        self.assertEqual(graph["version"], 1)
        self.assertIs(graph["model"], False)
        self.assertIn("domains", graph)
        with open(os.path.join(self.home, "star", "domains.json"), encoding="utf-8") as f:
            self.assertEqual(graph["domains"], json.load(f))
        self.assertTrue(any(n["kind"] == "idea" and n["text"] == evil + suffix
                            for n in graph["nodes"]))

    def test_star_page_returns_html_unchanged_without_marker(self):
        self._write_star("<html><body>plain</body></html>")
        status, body = self.request("GET", "/star")
        self.assertEqual(status, 200)
        self.assertEqual(body, "<html><body>plain</body></html>")

    def test_star_page_404_without_star_html(self):
        page = os.path.join(self.home, "star", "star.html")
        if os.path.exists(page):
            os.remove(page)
        status, _ = self.request("GET", "/star")
        self.assertEqual(status, 404)

    def test_star_event_written_to_star_file(self):
        event = {"type": "link", "a": "idea:x", "b": "item:personal-os",
                 "kind": "supports", "label": "能复用吗？"}
        status, response = self.request("POST", "/api/star-event", event)
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertRegex(response["event"]["id"], re.compile(r"^[0-9a-f]{32}$"))
        self.assertTrue(response["event"]["ts"].endswith("+00:00"))
        self.assertEqual(response["event"]["host"], SERVER.HOST_RAW)
        path = os.path.join(self.home, "events-star-%s.jsonl" % SERVER.HOST)
        self.assertTrue(os.path.isfile(path))
        with open(path, encoding="utf-8") as f:
            stored = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(stored[-1]["type"], "link")
        self.assertEqual(stored[-1]["id"], response["event"]["id"])
        self.assertFalse(os.path.exists(os.path.join(self.home, "events-%s.jsonl" % SERVER.HOST)))

    def test_star_event_rejects_bad_type_and_long_text(self):
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "suggest_node", "parent": "idea:x", "text": "x"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "edit", "node": "idea:x", "text": "x" * 2001})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "link", "a": "idea:x", "b": "item:personal-os",
                                  "kind": "unknown"})
        self.assertEqual(status, 400)

    def test_untrusted_host_and_origin(self):
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "pin", "node": "idea:x", "x": 1, "y": 2},
                                 host="evil.example")
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "pin", "node": "idea:x", "x": 1, "y": 2},
                                 origin="http://evil.example")
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "pin", "node": "idea:x", "x": 1, "y": 2},
                                 origin="http://127.0.0.1:%d" % PORT)
        self.assertEqual(status, 200)

    def test_model_routes_offline_without_key(self):
        bodies = {
            "/api/star/relate": {"idea": "test", "nodes": []},
            "/api/star/expand": {"text": "test", "nodes": []},
            "/api/star/pair": {"a": {"text": "a"}, "b": {"text": "b"}},
            "/api/star/layout": {},
        }
        for path, body in bodies.items():
            status, result = self.request("POST", path, body)
            self.assertEqual(status, 200, path)
            self.assertEqual(result, {"offline": True}, path)

    def _star_rows(self):
        path = os.path.join(self.home, "events-star-%s.jsonl" % SERVER.HOST)
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [line for line in f if line.strip()]

    def _graph(self):
        return SERVER._starapi.build_graph(self.home)

    def _pool_ids(self):
        """Idea ids in the star graph's pool and in the home server's pool, without the idea: prefix."""
        graph = {node["id"][len("idea:"):] for node in self._graph()["nodes"]
                 if node["kind"] == "idea" and node["state"] == "pool"}
        server = {idea["id"] for idea in SERVER.compute_state(SERVER.read_events())["ideas"]}
        return graph, server

    def test_idea_id_from_page_is_used_or_rejected(self):
        own = uuid.uuid4().hex
        status, response = self.request("POST", "/api/star-event",
                                        {"type": "idea", "text": "带自己的编号", "idea_id": own})
        self.assertEqual(status, 200)
        self.assertEqual(response["event"]["idea_id"], own)
        self.assertNotEqual(response["event"]["id"], own)
        for body in ({"type": "idea", "text": "没带编号"},
                     {"type": "idea", "text": "编号是 null", "idea_id": None}):
            status, response = self.request("POST", "/api/star-event", body)
            self.assertEqual(status, 200)
            self.assertEqual(response["event"]["idea_id"], response["event"]["id"])
        before = self._star_rows()
        for bad in ("A" * 32, own[:31], own + "0", "g" * 32, "", 12345, own + "\n"):
            status, response = self.request("POST", "/api/star-event",
                                            {"type": "idea", "text": "x", "idea_id": bad})
            self.assertEqual(status, 400, repr(bad))
            self.assertEqual(response, {"error": "bad idea_id"}, repr(bad))
        self.assertEqual(self._star_rows(), before)

    def test_star_events_batch_writes_all_in_order(self):
        before = self._star_rows()
        own = uuid.uuid4().hex
        status, response = self.request("POST", "/api/star-events", {"events": [
            {"type": "idea", "text": "批量一"},
            {"type": "idea", "text": "批量二", "idea_id": own},
            {"type": "pin", "node": "idea:batch", "x": 1, "y": 2},
        ]})
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(len(response["ids"]), 3)
        self.assertEqual([ev["id"] for ev in response["events"]], response["ids"])
        rows = [json.loads(line) for line in self._star_rows()[len(before):]]
        self.assertEqual([row["id"] for row in rows], response["ids"])
        self.assertEqual([row["type"] for row in rows], ["idea", "idea", "pin"])
        self.assertEqual(rows[1]["idea_id"], own)

    def test_star_events_batch_is_all_or_nothing(self):
        before = self._star_rows()
        status, response = self.request("POST", "/api/star-events", {"events": [
            {"type": "idea", "text": "好的一条"},
            {"type": "link", "a": "idea:x", "b": "item:personal-os", "kind": "unknown"},
            {"type": "idea", "text": "后面的好条"},
        ]})
        self.assertEqual(status, 400)
        self.assertEqual(response, {"error": "event 2: bad link"})
        status, response = self.request("POST", "/api/star-events",
                                        {"events": [{"type": "idea", "text": "t"}, "不是对象"]})
        self.assertEqual(status, 400)
        self.assertEqual(response, {"error": "event 2: bad body"})
        self.assertEqual(self._star_rows(), before)

    def test_star_events_batch_count_and_size_limits(self):
        before = self._star_rows()
        for body in ({}, {"events": []}, {"events": "idea"}, [{"type": "idea", "text": "t"}]):
            status, _ = self.request("POST", "/api/star-events", body)
            self.assertEqual(status, 400, body)
        status, response = self.request("POST", "/api/star-events",
                                        {"events": [{"type": "idea", "text": "t"}] * 201})
        self.assertEqual((status, response), (400, {"error": "too many events"}))
        status, response = self.request("POST", "/api/star-events",
                                        {"events": [{"type": "idea", "text": "x" * 1900}] * 150})
        self.assertEqual((status, response), (400, {"error": "bad size"}))
        self.assertEqual(self._star_rows(), before)
        status, response = self.request("POST", "/api/star-events",
                                        {"events": [{"type": "idea", "text": "y" * 1900}] * 100})
        self.assertEqual(status, 200)
        self.assertEqual(len(response["ids"]), 100)

    def test_star_events_batch_rejects_untrusted_host_origin_and_non_json(self):
        before = self._star_rows()
        body = {"events": [{"type": "idea", "text": "t"}]}
        status, _ = self.request("POST", "/api/star-events", body, host="evil.example")
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/star-events", body, origin="http://evil.example")
        self.assertEqual(status, 403)
        connection = HTTPConnection("127.0.0.1", PORT, timeout=10)
        try:
            connection.request("POST", "/api/star-events", body=json.dumps(body).encode("utf-8"),
                               headers={"Content-Type": "text/plain"})
            response = connection.getresponse()
            self.assertEqual(response.status, 415)
            response.read()
        finally:
            connection.close()
        self.assertEqual(self._star_rows(), before)

    def test_batch_idea_then_link_to_it_is_in_graph(self):
        own = uuid.uuid4().hex
        status, _ = self.request("POST", "/api/star-events", {"events": [
            {"type": "idea", "text": "同批新想法", "idea_id": own},
            {"type": "link", "a": "idea:" + own, "b": "item:personal-os", "kind": "supports",
             "label": "同批连线"},
        ]})
        self.assertEqual(status, 200)
        graph = self._graph()
        node = next(n for n in graph["nodes"] if n["id"] == "idea:" + own)
        self.assertEqual(node["state"], "pool")
        edge = next(e for e in graph["links"] if {e["a"], e["b"]} == {"idea:" + own, "item:personal-os"})
        self.assertEqual((edge["state"], edge["kind"]), ("confirmed", "supports"))

    def test_batch_drop_then_readd_keeps_idea_and_reverse_removes_it(self):
        kept = uuid.uuid4().hex
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "idea", "text": "先有的", "idea_id": kept})
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/star-events", {"events": [
            {"type": "idea_drop", "idea_id": kept, "reason": "deleted"},
            {"type": "idea", "text": "先有的", "idea_id": kept},
        ]})
        self.assertEqual(status, 200)
        graph_pool, server_pool = self._pool_ids()
        self.assertIn(kept, graph_pool)
        self.assertIn(kept, server_pool)

        status, _ = self.request("POST", "/api/star-events", {"events": [
            {"type": "idea", "text": "先有的", "idea_id": kept},
            {"type": "idea_drop", "idea_id": kept, "reason": "deleted"},
        ]})
        self.assertEqual(status, 200)
        graph_pool, server_pool = self._pool_ids()
        self.assertNotIn(kept, graph_pool)
        self.assertNotIn(kept, server_pool)

    def test_undismiss_events_are_star_only_and_checked(self):
        status, response = self.request("POST", "/api/star-event",
                                        {"type": "undismiss", "a": "idea:x", "b": "item:personal-os"})
        self.assertEqual(status, 200)
        self.assertEqual(response["event"]["type"], "undismiss")
        status, response = self.request("POST", "/api/star-event",
                                        {"type": "undismiss_node", "node": "poss:abc"})
        self.assertEqual(status, 200)
        self.assertEqual(response["event"]["node"], "poss:abc")
        for body in ({"type": "undismiss", "a": "idea:x"}, {"type": "undismiss_node"},
                     {"type": "undismiss_node", "node": "   "}):
            status, _ = self.request("POST", "/api/star-event", body)
            self.assertEqual(status, 400, body)
        self.assertNotIn("undismiss", SERVER.EVENT_TYPES)
        self.assertNotIn("undismiss_node", SERVER.EVENT_TYPES)

    def test_dismiss_then_undismiss_brings_back_hermes_suggestion(self):
        idea = uuid.uuid4().hex
        pair = {"a": "idea:" + idea, "b": "item:personal-os"}
        status, _ = self.request("POST", "/api/star-event",
                                 {"type": "idea", "text": "要不要合并", "idea_id": idea})
        self.assertEqual(status, 200)
        path = os.path.join(self.home, "events-hermes-%s.jsonl" % uuid.uuid4().hex)
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": uuid.uuid4().hex, "ts": "2026-11-09T00:00:00+00:00",
                                "host": "hermes", "type": "suggest", "kind": "supports",
                                "label": "同一件事吗？", "why": "", **pair}, ensure_ascii=False) + "\n")

        def shown():
            return any({edge["a"], edge["b"]} == set(pair.values()) for edge in self._graph()["links"])

        try:
            self.assertTrue(shown())
            status, _ = self.request("POST", "/api/star-event", {"type": "dismiss", **pair})
            self.assertEqual(status, 200)
            self.assertFalse(shown())
            status, _ = self.request("POST", "/api/star-event", {"type": "undismiss", **pair})
            self.assertEqual(status, 200)
            self.assertTrue(shown())
        finally:
            os.remove(path)

    def test_multi_map_create_isolate_rename_delete_and_voice_fix(self):
        status, initial = self.request("GET", "/api/star/maps")
        self.assertEqual(status, 200)
        self.assertEqual(initial["maps"][0]["id"], "main")

        status, created = self.request("POST", "/api/star/maps", {"action": "create", "name": "活动策划"})
        self.assertEqual(status, 200)
        self.assertTrue(created["ok"])
        map_id = created["map"]["id"]
        self.assertTrue(map_id.startswith("map_"))

        # New map starts empty (no 19 main constellations)
        status, custom_graph = self.request("GET", "/api/star?map=" + map_id)
        self.assertEqual(status, 200)
        self.assertEqual(custom_graph["map"], map_id)
        self.assertEqual(custom_graph["nodes"], [])

        # Writing an idea to the custom map stays isolated from main map and home pool
        v_before = self.request("GET", "/api/version")[1]["v"]
        idea_id = uuid.uuid4().hex
        status, ev_res = self.request("POST", "/api/star-event?map=" + map_id, {
            "type": "idea", "text": "独立星图节点", "idea_id": idea_id, "map": map_id
        })
        self.assertEqual(status, 200)
        self.assertTrue(ev_res["ok"])
        self.assertNotEqual(self.request("GET", "/api/version")[1]["v"], v_before)

        _, custom_after = self.request("GET", "/api/star?map=" + map_id)
        self.assertEqual([n["text"] for n in custom_after["nodes"]], ["独立星图节点"])
        graph_pool, server_pool = self._pool_ids()
        self.assertNotIn(idea_id, graph_pool)
        self.assertNotIn(idea_id, server_pool)

        # Rename & delete
        status, ren = self.request("POST", "/api/star/maps", {
            "action": "rename", "map_id": map_id, "name": "AI 培训策划"
        })
        self.assertEqual(status, 200)
        self.assertEqual(ren["map"]["name"], "AI 培训策划")

        status, bad_del = self.request("POST", "/api/star/maps", {"action": "delete", "map_id": "main"})
        self.assertEqual(bad_del.get("ok"), False)
        self.assertEqual(status, 400)

        status, deleted = self.request("POST", "/api/star/maps", {"action": "delete", "map_id": map_id})
        self.assertEqual(status, 200)
        self.assertFalse(any(m["id"] == map_id for m in deleted["maps"]))
        status, missing = self.request("GET", "/api/star?map=" + map_id)
        self.assertEqual(status, 404)

        # Voice-fix offline route check
        status, vf = self.request("POST", "/api/star/voice-fix", {"text": "嗯那个测试一下", "nodes": []})
        self.assertEqual((status, vf), (200, {"offline": True}))

    def test_star_settings_api_key_auto_match_and_never_leaks_key(self):
        saved_state = (SERVER._starmodel.KEY, SERVER._starmodel.PROVIDER,
                       SERVER._starmodel.MODEL, SERVER._starmodel.DEEPSEEK_URL)
        try:
            status, res = self.request("POST", "/api/star/settings", {
                "api_key": "sk-or-v1-secret-12345678",
                "model": "openai/gpt-4o-mini",
            })
            self.assertEqual(status, 200)
            self.assertTrue(res["ok"])
            self.assertTrue(res["has_key"])
            self.assertEqual(res["provider"], "openrouter")
            self.assertEqual(res["url"], "https://openrouter.ai/api/v1/chat/completions")
            self.assertNotIn("secret-12345678", json.dumps(res))

            status, got = self.request("GET", "/api/star/settings")
            self.assertEqual(status, 200)
            self.assertTrue(got["has_key"])
            self.assertEqual(got["key_masked"], "sk-o****5678")
            self.assertNotIn("secret-12345678", json.dumps(got))

            status, cleared = self.request("POST", "/api/star/settings", {"clear_key": True})
            self.assertEqual(status, 200)
            self.assertFalse(cleared["has_key"])
        finally:
            SERVER._starmodel.KEY, SERVER._starmodel.PROVIDER, SERVER._starmodel.MODEL, SERVER._starmodel.DEEPSEEK_URL = saved_state

    def test_star_import_file_parses_xmind_md_and_opml(self):
        import base64
        import io
        import zipfile

        # 1. Markdown
        md_b64 = base64.b64encode("# 主标题\n- 子节点一\n".encode("utf-8")).decode("ascii")
        status, res = self.request("POST", "/api/star/import-file", {
            "filename": "notes.md", "content_base64": md_b64
        })
        self.assertEqual(status, 200)
        self.assertEqual(res["format"], "md")
        self.assertIn("# 主标题", res["outline"])

        # 2. XMind (zip with content.json)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.json", json.dumps([{
                "rootTopic": {
                    "title": "XMind 中心",
                    "children": {"attached": [{"title": "分支 A"}, {"title": "分支 B"}]}
                }
            }], ensure_ascii=False))
        xm_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        status, xres = self.request("POST", "/api/star/import-file", {
            "filename": "map.xmind", "content_base64": xm_b64
        })
        self.assertEqual(status, 200)
        self.assertEqual(xres["format"], "xmind")
        self.assertIn("# XMind 中心", xres["outline"])
        self.assertIn("## 分支 A", xres["outline"])

        # 3. OPML
        opml = '<?xml version="1.0"?><opml><body><outline text="根"><outline text="子项"/></outline></body></opml>'
        op_b64 = base64.b64encode(opml.encode("utf-8")).decode("ascii")
        status, ores = self.request("POST", "/api/star/import-file", {
            "filename": "outline.opml", "content_base64": op_b64
        })
        self.assertEqual(status, 200)
        self.assertEqual(ores["format"], "opml")
        self.assertIn("# 根", ores["outline"])


if __name__ == "__main__":
    unittest.main()
