"""Lint every first step with fixed rules (added after round 1 — recorded as a post-hoc rule in the report), rewrite the
failures with DeepSeek using the judges' reasons, and build a small re-judge sheet (rewrites + 4 known-answer rows)."""
import io, json, os, random, re, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dsapi import deepseek  # noqa: E402  (same API call as a2_steps.py)

D = "C:/Agent-Shared/home/star/research/A/first_steps"
units = {u["rid"]: u for u in json.load(open(os.path.join(D, "writer_output.json"), encoding="utf-8"))}
verdicts = json.load(open(os.path.join(D, "verdicts.json"), encoding="utf-8"))
PERSPECTIVE = re.compile(r"(给|问|让|请|通知|提醒)用户|用户确认|我会|请你|助手会|AI 会|问自己|发消息给自己")
MIN = re.compile(r"约\s*(\d+)\s*分钟")


def units_len(s):
    """CJK characters count one each; an English word or number counts one."""
    return len(re.findall(r"[一-鿿]", s)) + len(re.findall(r"[A-Za-z0-9]+", s))


def lint(step):
    probs = []
    if PERSPECTIVE.search(step):
        probs.append("视角错：第一步是给你本人做的，不能出现「用户/我会/助手」")
    if "如果" not in step or "就" not in step:
        probs.append("缺「如果…就…」")
    m = MIN.search(step)
    if not m or int(m.group(1)) > 15:
        probs.append("没写时长或超过 15 分钟")
    if units_len(step) > 45:
        probs.append("超过 45 字")
    if re.search(r"该仓库|该项目|那个东西", step):
        probs.append("对象不具体（「该…」）")
    return probs


redo = {}
for it in verdicts["items"]:
    probs = lint(it["step"])
    if not it["keep"] or probs:
        reasons = probs + ["%s 判不过：%s" % (j, ",".join(f)) for j, f in it["fails"].items()]
        redo[it["rid"]] = reasons
print("to rewrite:", {k: v for k, v in redo.items()})
SYS = ("你是执行教练。下面的「第一步」被评审打回，按理由重写。格式「如果<具体时间或情境>，就<具体动作+具体对象>（约 N 分钟）」，"
       "不超过 45 字，N ≤ 15；这是给本人自己做的，不要出现「用户」，也不要「问自己」；对象要写出具体名字，不要「该仓库/该项目」。"
       "如果事情里的名称像是语音识别听错了（数字和字母混在一起，比如「Agent 2L」很可能是「Agent RL」），第一步就是去搜最可能的正确写法。"
       "只输出 JSON：{\"steps\":[{\"id\":\"r03\",\"step\":\"...\"}]}")
user = "\n".join("%s ｜ %s ｜ 原第一步：%s ｜ 打回理由：%s" % (rid, units[rid]["context"], units[rid]["step"], "；".join(rs)) for rid, rs in redo.items())
out = deepseek(SYS, user)
new = {s["id"]: s["step"].strip() for s in out.get("steps", [])}
for rid in redo:
    print(" ", rid, "→", new.get(rid), "| lint:", lint(new.get(rid, "")) or "ok")
GOLD = [("准备 Q4 复盘会", "如果明早 9 点坐到书桌前，就打开 Horizon 把复盘会的议程写成 3 行（约 10 分钟）", True),
        ("交房租", "如果周三午饭后，就给房东发微信确认这个月的房租金额（约 3 分钟）", True),
        ("搞懂 Agent RL", "研究一下 Agent RL。", False),
        ("写季度报告", "如果服务器配好、数据都整理完，就开始写报告第一章。", False)]
sheet = [{"key": rid, "task": re.sub(r"。.*$", "", units[rid]["context"]), "step": new[rid], "gold": None} for rid in redo if rid in new]
sheet += [{"key": "g%02d" % (i + 1), "task": t, "step": s, "gold": g} for i, (t, s, g) in enumerate(GOLD)]
random.Random(7).shuffle(sheet)
for i, r in enumerate(sheet, 1):
    r["sid"] = "t%02d" % i
json.dump(sheet, open(os.path.join(D, "sheet2_key.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
head = open(os.path.join(D, "judge_sheet.txt"), encoding="utf-8").read().split("\n\n")[0]
text = head + "\n\n" + "\n".join("%s ｜ 事：%s ｜ 第一步：%s" % (r["sid"], r["task"], r["step"]) for r in sheet) + "\n"
text = text.replace('"s01"', '"t01"').replace('"s02"', '"t02"')
open(os.path.join(D, "judge_sheet2.txt"), "w", encoding="utf-8").write(text)
dj = deepseek("你只输出 JSON。", text)
json.dump(dj, open(os.path.join(D, "judge2_deepseek.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("sheet2 rows:", len(sheet), "| deepseek verdicts:", len(dj.get("results", [])))
print(text)
