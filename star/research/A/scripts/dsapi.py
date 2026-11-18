"""Tiny DeepSeek chat call (JSON mode). The key comes from DEEPSEEK_API_KEY or the user's environment in the registry,
the same place the star prototype server reads it from; it is never printed or written anywhere."""
import json, os, urllib.request


def load_key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
        return str(winreg.QueryValueEx(h, "DEEPSEEK_API_KEY")[0]).strip()


def deepseek(system, user, temperature=0):
    body = {"model": "deepseek-chat", "temperature": temperature, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + load_key()})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"])
