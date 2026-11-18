#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse mind-map and document files (.xmind, .pdf, .md, .mm, .opml, .txt, .json)
into a clean Markdown outline for Star Map import.
"""

import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile

MAX_OUTLINE_NODES = 120
MAX_ITEM_CHARS = 80


def _clip_line(text):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:MAX_ITEM_CHARS]


def _tree_to_markdown(title, children, depth=0, out=None):
    if out is None:
        out = []
    if len(out) >= MAX_OUTLINE_NODES:
        return out
    clean = _clip_line(title)
    if clean:
        if depth == 0:
            out.append("# " + clean)
        elif depth == 1:
            out.append("## " + clean)
        elif depth == 2:
            out.append("### " + clean)
        else:
            indent = "  " * (depth - 3)
            out.append(indent + "- " + clean)
    for child in (children or []):
        if len(out) >= MAX_OUTLINE_NODES:
            break
        if isinstance(child, dict):
            _tree_to_markdown(child.get("title", ""), child.get("children", []), depth + 1, out)
    return out


def _xmind_json_topic(topic):
    if not isinstance(topic, dict):
        return None
    title = _clip_line(topic.get("title") or "")
    children_obj = topic.get("children")
    raw_children = []
    if isinstance(children_obj, dict):
        for bucket in ("attached", "detached", "summary"):
            arr = children_obj.get(bucket)
            if isinstance(arr, list):
                raw_children.extend(arr)
    kids = []
    for ch in raw_children:
        parsed = _xmind_json_topic(ch)
        if parsed and (parsed["title"] or parsed["children"]):
            kids.append(parsed)
    return {"title": title or "未命名主题", "children": kids}


def _xmind_xml_topic(elem):
    title_el = elem.find("title")
    title = _clip_line("".join(title_el.itertext()) if title_el is not None else elem.get("text", ""))
    kids = []
    children_el = elem.find("children")
    if children_el is not None:
        for topics_el in children_el.findall("topics"):
            for t in topics_el.findall("topic"):
                parsed = _xmind_xml_topic(t)
                if parsed and (parsed["title"] or parsed["children"]):
                    kids.append(parsed)
    return {"title": title or "未命名主题", "children": kids}


def parse_xmind_bytes(raw_bytes):
    lines = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = set(zf.namelist())
        if "content.json" in names:
            sheets = json.loads(zf.read("content.json").decode("utf-8", "replace"))
            if isinstance(sheets, dict):
                sheets = sheets.get("sheets") if isinstance(sheets.get("sheets"), list) else [sheets]
            if isinstance(sheets, list):
                for sheet in sheets:
                    if not isinstance(sheet, dict):
                        continue
                    root = _xmind_json_topic(sheet.get("rootTopic"))
                    if root:
                        _tree_to_markdown(root["title"], root["children"], 0, lines)
        elif "content.xml" in names:
            root_xml = ET.fromstring(zf.read("content.xml"))
            for sheet in root_xml.findall(".//sheet"):
                topic = sheet.find("topic")
                if topic is not None:
                    tree = _xmind_xml_topic(topic)
                    _tree_to_markdown(tree["title"], tree["children"], 0, lines)
    return "\n".join(lines)


def _mm_node(elem):
    title = _clip_line(elem.get("TEXT") or "")
    kids = []
    for ch in elem.findall("node"):
        parsed = _mm_node(ch)
        if parsed and (parsed["title"] or parsed["children"]):
            kids.append(parsed)
    return {"title": title, "children": kids}


def parse_mm_bytes(raw_bytes):
    root = ET.fromstring(raw_bytes.decode("utf-8", "replace"))
    lines = []
    for node in root.findall("node"):
        tree = _mm_node(node)
        _tree_to_markdown(tree["title"] or "导图", tree["children"], 0, lines)
    return "\n".join(lines)


def _opml_node(elem):
    title = _clip_line(elem.get("text") or elem.get("title") or "")
    kids = []
    for ch in elem.findall("outline"):
        parsed = _opml_node(ch)
        if parsed and (parsed["title"] or parsed["children"]):
            kids.append(parsed)
    return {"title": title, "children": kids}


def parse_opml_bytes(raw_bytes):
    root = ET.fromstring(raw_bytes.decode("utf-8", "replace"))
    lines = []
    body = root.find("body")
    parent = body if body is not None else root
    for out_el in parent.findall("outline"):
        tree = _opml_node(out_el)
        _tree_to_markdown(tree["title"] or "大纲", tree["children"], 0, lines)
    return "\n".join(lines)


def parse_pdf_bytes(raw_bytes, filename=""):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise RuntimeError("PyPDF2 unavailable")
    reader = PdfReader(io.BytesIO(raw_bytes))
    chunks = []
    for page in reader.pages[:25]:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            chunks.append(txt)
    full = "\n".join(chunks).strip()
    if not full:
        return ""
    raw_lines = [re.sub(r"\s+", " ", ln).strip() for ln in full.splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]
    base_title = os.path.splitext(os.path.basename(filename or "PDF 文档"))[0]
    out = ["# " + _clip_line(base_title)]
    for ln in raw_lines:
        if len(out) >= MAX_OUTLINE_NODES:
            break
        if re.match(r"^(第[一二三四五六七八九十0-9]+[章节部分]|(\d+\.)+\s+|\d+、)", ln):
            out.append("## " + _clip_line(ln))
        elif re.match(r"^([•·\-*]|\(\d+\)|[（(]?[一二三四五六七八九十]+[)）]?[、.])\s*", ln):
            cleaned = re.sub(r"^[•·\-*]+\s*", "", ln)
            out.append("- " + _clip_line(cleaned))
        elif len(ln) >= 6:
            out.append("- " + _clip_line(ln))
    return "\n".join(out)


def parse_json_bytes(raw_bytes, filename=""):
    data = json.loads(raw_bytes.decode("utf-8-sig", "replace"))
    lines = []
    if isinstance(data, dict) and isinstance(data.get("nodes"), list):
        # Star map exported JSON
        base_title = os.path.splitext(os.path.basename(filename or "星图备份"))[0]
        lines.append("# " + _clip_line(base_title))
        for n in data["nodes"][:MAX_OUTLINE_NODES - 1]:
            if not isinstance(n, dict):
                continue
            txt = _clip_line(n.get("text") or n.get("title") or "")
            if not txt:
                continue
            prefix = "## " if n.get("kind") == "item" else "- "
            lines.append(prefix + txt)
        return "\n".join(lines)
    if isinstance(data, dict) and ("title" in data or "text" in data or "children" in data):
        def norm(d):
            return {
                "title": _clip_line(d.get("title") or d.get("text") or ""),
                "children": [norm(c) for c in (d.get("children") or []) if isinstance(c, dict)],
            }
        tree = norm(data)
        _tree_to_markdown(tree["title"] or "导图", tree["children"], 0, lines)
        return "\n".join(lines)
    raise ValueError("unsupported json structure")


def parse_file_to_outline(filename, raw_bytes):
    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext == ".xmind":
        outline = parse_xmind_bytes(raw_bytes)
        fmt = "xmind"
    elif ext == ".pdf":
        outline = parse_pdf_bytes(raw_bytes, filename)
        fmt = "pdf"
    elif ext == ".mm":
        outline = parse_mm_bytes(raw_bytes)
        fmt = "mm"
    elif ext == ".opml":
        outline = parse_opml_bytes(raw_bytes)
        fmt = "opml"
    elif ext == ".json":
        outline = parse_json_bytes(raw_bytes, filename)
        fmt = "json"
    elif ext in (".md", ".markdown", ".txt", ""):
        outline = raw_bytes.decode("utf-8-sig", "replace").strip()
        fmt = ext.lstrip(".") or "txt"
    else:
        raise ValueError("unsupported file type: " + ext)
    return fmt, outline.strip()
