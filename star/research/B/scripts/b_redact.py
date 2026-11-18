"""Redaction for anything that leaves the machine (judge sheets for DeepSeek / Gemini / Claude).
redact(text) masks secrets, tokens, personal numbers and names-with-titles.
scan(text) counts what would still look sensitive after redaction (used by b_gate.py; it reports counts only)."""
import re

PATTERNS = [  # (label, regex, replacement)
    ("kv-secret", re.compile(r"(?i)((?:secret\s*_?(?:id|key)|access\s*_?key(?:\s*_?id)?|api\s*_?key|app\s*_?secret|token|password|passwd|pwd|密码|口令|密钥)\s*[:：=]\s*)([^\s,，;；]+)"),
     lambda m: m.group(1) + "<secret>"),
    ("password-word", re.compile(r"(密码|口令)\s*(是|为)?\s*(?!<secret>)(\S{3,})"), lambda m: m.group(1) + " <secret>"),
    ("key-prefix", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|AKID[A-Za-z0-9]{13,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[bpas]-[A-Za-z0-9-]{10,})"), "<secret>"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]+)?"), "<secret>"),
    ("pem", re.compile(r"-----BEGIN [A-Z ]+-----"), "<secret>"),
    ("hex32", re.compile(r"\b[0-9a-fA-F]{32,}\b"), "<hex>"),
    ("mixed24", re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{24,}\b"), "<token>"),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "<email>"),
    ("id-card", re.compile(r"(?<!\d)\d{17}[\dXx](?![\dA-Za-z])"), "<id>"),
    ("mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "<phone>"),
    ("long-number", re.compile(r"(?<!\d)\d{12,}(?!\d)"), "<number>"),
    ("name-before-cv", re.compile(r"[一-鿿]{2,4}(?=[-_ ]?(?:简历|履历|个人简介|CV|cv|Resume|resume))"), "某某"),
    ("name-title", re.compile(r"([一-鿿])(哥|姐|师傅|老师|总|经理|主任)"), lambda m: "某" + m.group(2)),
]


def redact(text):
    s = text or ""
    for _, rx, rep in PATTERNS:
        s = rx.sub(rep, s)
    return s


def scan(text):
    """Counts per label of spans that still match after redaction (placeholders and 某X never match)."""
    hits = {}
    for label, rx, _ in PATTERNS:
        n = 0
        for m in rx.finditer(text or ""):
            if label == "name-title" and m.group(1) == "某":
                continue
            if label == "name-before-cv" and m.group(0) == "某某":
                continue
            if label in ("kv-secret", "password-word") and m.group(m.lastindex).startswith("<"):
                continue
            n += 1
        if n:
            hits[label] = n
    return hits
