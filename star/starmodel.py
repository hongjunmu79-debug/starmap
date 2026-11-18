#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The four DeepSeek-backed helpers used by the star-map page.

This is the small prototype service from ``proto/star_server.py`` folded into
the home server.  The key stays in this process: it comes from the environment
or the user's Windows environment, and is never put in a response or a log.

``call(name, body)`` always returns ``(status, dict)``.  Without a key it is a
successful ``(200, {"offline": True})`` so the page can simply stay offline.
"""

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

LOGGER = logging.getLogger(__name__)

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
PROVIDER = "deepseek"
MAX_CALLS_PER_MIN = 30

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://api.deepseek.com/chat/completions",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "models": ["deepseek/deepseek-chat", "openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "google/gemini-2.5-flash"],
    },
    "openai": {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    },
    "gemini": {
        "name": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "url": "https://api.siliconflow.cn/v1/chat/completions",
        "models": ["deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct"],
    },
    "zhipu": {
        "name": "智谱 GLM",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "models": ["glm-4-flash", "glm-4-plus"],
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "url": "https://api.moonshot.cn/v1/chat/completions",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k"],
    },
    "qwen": {
        "name": "通义千问 Qwen",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
    },
    "groq": {
        "name": "Groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "models": ["llama-3.3-70b-versatile", "qwen-qwq-32b"],
    },
    "custom": {
        "name": "自定义 OpenAI 兼容",
        "url": "",
        "models": [],
    },
}

ICONS = ["chip", "gear", "check", "chat", "spark", "people", "dice", "card", "cap", "flask",
         "doc", "book", "tool", "sliders", "db", "bulb", "flag", "question", "link"]
KINDS = ["extends", "supports", "contradicts", "same", "part_of"]
LENSES = ["可以变成", "第一步", "卡在", "像", "连着"]

POSS_RULES = (
    "lens 只能是「可以变成」「第一步」「卡在」「像」「连着」之一；text 不超过 18 个字，要具体，不要空话；"
    "「第一步」必须 30 分钟内能做完；「连着」要说出连着他已有的哪件事。每条再给一个 icon。"
    "icon 只能从这些里选：" + " ".join(ICONS) + "。"
)
RELATE_SYSTEM = (
    "你帮一个人整理灵感。他刚记下一条新想法，下面是他已有的概念（id｜文字｜所属星座）。请判断：\n"
    "1. item：这条想法最该归进哪个星座，给星座中心的 id（形如 item:xxx）；和哪个星座都不沾边就给 null。\n"
    "2. links：它和哪些已有概念有值得一想的逻辑关系，最多 3 条。每条给 to（概念 id，必须来自列表）、"
    "kind（extends 往下延伸 / supports 撑住 / contradicts 矛盾 / same 可能是一件事 / part_of 属于）、"
    "label（不超过 10 个字的问句，只提问，不下结论）。没有就给空数组，不要硬凑。\n"
    "3. possibilities：顺着这条想法往下长 3 到 4 条可能性。" + POSS_RULES + "\n"
    "4. icon：给这条新想法挑一个图标，只能从上面的列表里选。\n"
    "只输出 JSON，格式：{\"item\": ..., \"links\": [{\"to\": ..., \"kind\": ..., \"label\": ...}], "
    "\"possibilities\": [{\"lens\": ..., \"text\": ..., \"icon\": ...}], \"icon\": ...}"
)
EXPAND_SYSTEM = (
    "你帮一个人顺着一个概念往下想。下面是他已有的概念（id｜文字｜所属星座），以及他想往下想的那一个。"
    "请长出 3 到 4 条可能性。" + POSS_RULES + "\n"
    "只输出 JSON：{\"possibilities\": [{\"lens\": ..., \"text\": ..., \"icon\": ...}]}"
)
PAIR_SYSTEM = (
    "你帮一个人看两个概念之间有没有值得一想的逻辑关系。有就给一句不超过 10 个字的问句当线索"
    "（只提问，不下结论），并给 kind（extends / supports / contradicts / same / part_of）；"
    "只是字面相近或者牵强，就算没有。只输出 JSON：{\"related\": true 或 false, \"kind\": ..., \"label\": ...}"
)
LAYOUT_SYSTEM = (
    "你是一个图谱布局调参员。布局方式和 Obsidian 的图谱「Forces」面板一样，有四个 0 到 1 的旋钮：\n"
    "- center 向心力：把所有节点往场景中心拉，越大越集中，各星座之间靠得越近；\n"
    "- repel 排斥力：节点之间互相推开，越大越松散；\n"
    "- link 连线吸引力：相连节点之间的拉力，越大成员越紧贴自己的星座中心；\n"
    "- distance 连线长度：相连节点之间的静止距离，越大连线越长。\n"
    "我会给你这张图的概况、当前四个值和拥挤指标。请给出让整张图「第一眼清楚、不挤、不散、能装进窗口」的一组新值。\n"
    "还可以给每个星座中心一个目标位置 anchors：x、y（三维时再加 z）都在 -1 到 1 之间"
    "（-1 是窗口的左 / 上 / 近，1 是右 / 下 / 远），让星座在版面上分布得有章法"
    "（比如在跑的靠中间偏前，冻结的靠边靠后；成员多的星座给更大的空间）。不需要摆位置就给空数组。\n"
    "只输出 JSON：{\"center\":0到1,\"repel\":0到1,\"link\":0到1,\"distance\":0到1,"
    "\"anchors\":[{\"id\":\"item:xxx\",\"x\":数,\"y\":数,\"z\":数}],\"why\":\"不超过 30 个字的理由\"}"
)

_calls = []
_calls_lock = threading.Lock()


def log(message):
    # Only a short, key-free message ever reaches stderr.
    LOGGER.warning("[star] %s", message)


def load_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key or os.name != "nt":
        return key
    try:  # a process started outside a fresh login may not have the user variable yet
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry_key:
            return str(winreg.QueryValueEx(registry_key, "DEEPSEEK_API_KEY")[0]).strip()
    except OSError:
        return ""


KEY = load_key()


def infer_provider_from_key(api_key):
    k = str(api_key or "").strip()
    if k.startswith("sk-or-v1-"):
        return "openrouter"
    if k.startswith("sk-proj-") or k.startswith("sk-svcacct-"):
        return "openai"
    if k.startswith("AIza"):
        return "gemini"
    if k.startswith("gsk_"):
        return "groq"
    return "deepseek"


def mask_key(api_key):
    k = str(api_key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return k[:4] + "****" + k[-4:]


def configure(api_key=None, provider=None, model=None, url=None, clear_key=False):
    global KEY, PROVIDER, MODEL, DEEPSEEK_URL
    if clear_key:
        KEY = ""
    elif api_key is not None and str(api_key).strip():
        KEY = str(api_key).strip()
    if provider is not None:
        p = str(provider).strip()
        if p in PROVIDERS:
            PROVIDER = p
    elif api_key and str(api_key).strip():
        PROVIDER = infer_provider_from_key(KEY)
    preset = PROVIDERS.get(PROVIDER, PROVIDERS["deepseek"])
    if url is not None and str(url).strip():
        DEEPSEEK_URL = str(url).strip()
    elif preset["url"] and PROVIDER != "custom":
        DEEPSEEK_URL = preset["url"]
    if model is not None and str(model).strip():
        MODEL = str(model).strip()
    elif preset["models"] and MODEL not in preset["models"]:
        MODEL = preset["models"][0]


def get_public_settings():
    return {
        "has_key": bool(str(KEY or "").strip()),
        "key_masked": mask_key(KEY),
        "provider": PROVIDER,
        "model": MODEL,
        "url": DEEPSEEK_URL,
        "providers": PROVIDERS,
    }


def load_local_settings(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    configure(
        api_key=data.get("api_key"),
        provider=data.get("provider"),
        model=data.get("model"),
        url=data.get("url"),
    )
    return True


def save_local_settings(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "provider": PROVIDER,
        "model": MODEL,
        "url": DEEPSEEK_URL,
        "api_key": KEY,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def fetch_remote_models(api_key=None, url=None, provider=None):
    key = str(api_key or "").strip() or KEY
    p = str(provider or PROVIDER).strip()
    target_url = str(url or "").strip() or PROVIDERS.get(p, {}).get("url") or DEEPSEEK_URL
    if not key or not target_url:
        return PROVIDERS.get(p, {}).get("models", [])
    if target_url.endswith("/chat/completions"):
        models_url = target_url[:-len("/chat/completions")] + "/models"
    else:
        models_url = target_url.rstrip("/") + "/models"
    req = urllib.request.Request(models_url, headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = data.get("data") if isinstance(data, dict) else None
        if isinstance(rows, list):
            ids = [str(item.get("id")) for item in rows if isinstance(item, dict) and item.get("id")]
            if ids:
                return ids[:60]
    except Exception:
        pass
    return list(PROVIDERS.get(p, {}).get("models", []))


def allow_call():
    now = time.time()
    with _calls_lock:
        while _calls and now - _calls[0] > 60:
            _calls.pop(0)
        if len(_calls) >= MAX_CALLS_PER_MIN:
            return False
        _calls.append(now)
        return True


def clip(value, limit):
    return str(value or "").strip().replace("\n", " ")[:limit]


def unit(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(0.0, min(1.0, value)) if value == value else default


def signed(value):
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return max(-1.0, min(1.0, value)) if value == value else None


def _parse_json_content(raw_text):
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def ask(system, user, max_tokens=700, timeout=20):
    if not str(KEY or "").strip():
        raise RuntimeError("no key")
    if not allow_call():
        raise RuntimeError("too many calls")
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    try:
        request = urllib.request.Request(
            DEEPSEEK_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            output = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        body.pop("response_format", None)
        request = urllib.request.Request(
            DEEPSEEK_URL, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            output = json.loads(response.read().decode("utf-8"))
    return _parse_json_content(output["choices"][0]["message"]["content"])


def clean_nodes(raw):
    nodes = []
    for node in (raw or [])[:300]:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        nodes.append({"id": clip(node["id"], 64), "text": clip(node.get("text"), 80),
                      "group": clip(node.get("group"), 40)})
    return nodes


def listing(nodes):
    return "\n".join("%s｜%s｜%s" % (node["id"], node["text"], node["group"] or "（未归类）")
                     for node in nodes)


def clean_poss(raw):
    out = []
    for possibility in (raw or [])[:4]:
        if (not isinstance(possibility, dict) or possibility.get("lens") not in LENSES
                or not str(possibility.get("text") or "").strip()):
            continue
        out.append({
            "lens": possibility["lens"],
            "text": clip(possibility.get("text"), 20),
            "icon": possibility.get("icon") if possibility.get("icon") in ICONS else "spark",
        })
    return out


def relate(payload):
    idea = clip(payload.get("idea"), 200)
    nodes = clean_nodes(payload.get("nodes"))
    if not idea:
        raise ValueError("empty idea")
    result = ask(RELATE_SYSTEM, "已有概念：\n" + listing(nodes) + "\n\n新想法：" + idea)
    ids = {node["id"] for node in nodes}
    items = {node_id for node_id in ids if node_id.startswith("item:")}
    links, seen = [], set()
    for link in (result.get("links") or [])[:3]:
        if not isinstance(link, dict) or link.get("to") not in ids or link["to"] in seen:
            continue
        seen.add(link["to"])
        links.append({
            "to": link["to"],
            "kind": link.get("kind") if link.get("kind") in KINDS else "extends",
            "label": clip(link.get("label"), 12),
        })
    return {
        "item": result.get("item") if result.get("item") in items else None,
        "links": [link for link in links if link["label"]],
        "possibilities": clean_poss(result.get("possibilities")),
        "icon": result.get("icon") if result.get("icon") in ICONS else "bulb",
    }


def expand(payload):
    text = clip(payload.get("text"), 200)
    nodes = clean_nodes(payload.get("nodes"))
    if not text:
        raise ValueError("empty text")
    result = ask(EXPAND_SYSTEM, "已有概念：\n" + listing(nodes) + "\n\n往下想这一个：" + text,
                 max_tokens=500)
    return {"possibilities": clean_poss(result.get("possibilities"))}


def pair(payload):
    a, b = payload.get("a") or {}, payload.get("b") or {}
    text_a, text_b = clip(a.get("text"), 80), clip(b.get("text"), 80)
    if not text_a or not text_b:
        raise ValueError("need two texts")
    result = ask(PAIR_SYSTEM, "A：" + text_a + "\nB：" + text_b, max_tokens=120)
    related = result.get("related") is True and bool(clip(result.get("label"), 12))
    return {
        "related": related,
        "kind": result.get("kind") if result.get("kind") in KINDS else "extends",
        "label": clip(result.get("label"), 12) if related else "",
    }


def layout(payload):
    current = payload.get("current") if isinstance(payload.get("current"), dict) else {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    constellations = [
        constellation for constellation in (stats.get("constellations") or [])[:12]
        if isinstance(constellation, dict) and str(constellation.get("id", "")).startswith("item:")
    ]
    ids = {str(constellation["id"])[:64] for constellation in constellations}
    brief = {
        "维度": "三维" if payload.get("mode") == "3d" else "二维",
        "窗口": [int(value) for value in (payload.get("viewport") or [1280, 720])[:2]
                 if isinstance(value, (int, float))],
        "当前四个值": {key: round(unit(current.get(key), 0.5), 2)
                       for key in ("center", "repel", "link", "distance")},
        "节点数": int(stats.get("nodes") or 0),
        "连线数": int(stats.get("links") or 0),
        "想法数": int(stats.get("ideas") or 0),
        "星座": [{
            "id": str(constellation["id"])[:64],
            "名称": clip(constellation.get("title"), 20),
            "成员数": int(constellation.get("members") or 0),
            "想法数": int(constellation.get("ideas") or 0),
            "状态": clip(constellation.get("status"), 12),
        } for constellation in constellations],
        "拥挤指标": {
            "标签重叠数": int(stats.get("labelOverlaps") or 0),
            "整体是否装进窗口": bool(stats.get("fits")),
            "最近两个节点的距离_像素": stats.get("nearestMin"),
        },
    }
    result = ask(LAYOUT_SYSTEM, json.dumps(brief, ensure_ascii=False), max_tokens=500)
    anchors = []
    for anchor in (result.get("anchors") or [])[:12]:
        if not isinstance(anchor, dict) or str(anchor.get("id", "")) not in ids:
            continue
        x, y = signed(anchor.get("x")), signed(anchor.get("y"))
        if x is None or y is None:
            continue
        item = {"id": str(anchor["id"]), "x": x, "y": y}
        z = signed(anchor.get("z"))
        if z is not None and payload.get("mode") == "3d":
            item["z"] = z
        anchors.append(item)
    return {
        "center": unit(result.get("center"), unit(current.get("center"), 0.5)),
        "repel": unit(result.get("repel"), unit(current.get("repel"), 0.5)),
        "link": unit(result.get("link"), unit(current.get("link"), 0.5)),
        "distance": unit(result.get("distance"), unit(current.get("distance"), 0.5)),
        "anchors": anchors,
        "why": clip(result.get("why"), 30),
    }


VOICE_FIX_SYSTEM = (
    "你帮一个人把语音识别出来的想法顺一遍。只做轻度纠错：\n"
    "1. 去掉「嗯、啊、那个、就是」等口头禅和重复卡顿；\n"
    "2. 结合他星图里已有的概念，纠正明显的同音错别字或断句错误；\n"
    "3. 补全自然标点，保持原本的意思和简洁口吻，不要扩写或编造新内容。\n"
    "只输出 JSON：{\"text\": \"修正后的文字\"}"
)


def voice_fix(payload):
    text = clip(payload.get("text"), 400)
    if not text:
        raise ValueError("empty text")
    nodes = clean_nodes(payload.get("nodes"))
    context = ("已有概念：\n" + listing(nodes) + "\n\n") if nodes else ""
    result = ask(VOICE_FIX_SYSTEM, context + "语音识别原文：" + text, max_tokens=200)
    fixed = clip(result.get("text"), 400) or text
    return {"text": fixed, "changed": fixed != text}


ROUTES = {
    "relate": relate,
    "expand": expand,
    "pair": pair,
    "layout": layout,
    "voice-fix": voice_fix,
}


def call(name, body):
    """Run one model helper and return ``(HTTP status, JSON-able dict)``."""
    function = ROUTES.get(name) if isinstance(name, str) else None
    if function is None:
        return 404, {"error": "not found"}
    if not str(KEY or "").strip():
        return 200, {"offline": True}
    if not isinstance(body, dict):
        return 400, {"error": "bad body"}
    try:
        result = function(body)
        if not isinstance(result, dict):
            return 500, {"error": "server error"}
        return 200, result
    except ValueError:
        return 400, {"error": "bad request"}
    except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
        log("model unavailable: %s" % exc.__class__.__name__)
        return 502, {"error": "model unavailable"}
    except Exception as exc:  # never include the exception text; it could echo request data
        log("model error: %s" % exc.__class__.__name__)
        return 500, {"error": "server error"}
