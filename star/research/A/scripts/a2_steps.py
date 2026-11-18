"""A 推进 — step 2: DeepSeek writes a first step for every push unit; build one blind judge sheet (real steps + 10 gold
steps with known answers, shuffled); DeepSeek judges it in a separate call. Gemini and Claude judge the same sheet elsewhere.
usage: python a2_steps.py <horizon_detail.json>
Only short, redacted text is sent out (person names with titles are masked)."""
import io, json, os, random, re, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
OUT = "C:/Agent-Shared/home/star/research/A/first_steps"
os.makedirs(OUT, exist_ok=True)
A = json.load(open("C:/Agent-Shared/home/star/research/A/assignment.json", encoding="utf-8"))
HZ = json.load(open(sys.argv[1], encoding="utf-8"))
C = json.load(io.open("C:/Agent-Shared/home/content.json", encoding="utf-8-sig"))
ITEMS = {it["id"]: it for it in C["items"]}
NAME = re.compile(r"([\u4e00-\u9fff])(哥|姐|师傅|老师|总)")


def red(s):
    return NAME.sub(lambda m: "某" + m.group(2), s or "")


def load_key():
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
        return str(winreg.QueryValueEx(h, "DEEPSEEK_API_KEY")[0]).strip()


def deepseek(system, user):
    body = {"model": "deepseek-chat", "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + load_key()})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"])


units = []
for u in A["units"]:
    if u["group"] != "push":
        continue
    kind, rest = u["unit"].split(":", 1)
    if kind == "hz":
        d = HZ[rest]
        ctx = "待办：%s。说明：%s。已拆的子任务：%s" % (red(d["title"]), red(d["detail"])[:200], "；".join(red(s) for s in d["subtasks"]) or "无")
    else:
        item_id, idx = rest.rsplit(":", 1)
        it = ITEMS[item_id]
        st = it["steps"][int(idx)]
        ctx = "项目：%s。当前这一步：%s。说明：%s" % (red(it["title"]), red(st.get("t", "")), red(st.get("d", ""))[:200])
    units.append({"rid": "r%02d" % (len(units) + 1), "unit": u["unit"], "context": ctx})

WRITER_SYS = ("你是执行教练。为每件事写「第一步」：一句中文，格式「如果<具体时间或情境>，就<具体动作+具体对象>（约 N 分钟）」，"
              "不超过 45 字。必须 15 分钟内能开始并做完；不能依赖先完成别的事；不能只是把整件事换个说法；动作要具体（打开/写下/发消息/搜/列出…），"
              "不要用「研究一下/了解/想想」。名称不确定的，第一步就是先把名称查清。只输出 JSON：{\"steps\":[{\"id\":\"r01\",\"step\":\"...\"}]}")
writer_user = "\n".join("%s：%s" % (x["rid"], x["context"]) for x in units)
open(os.path.join(OUT, "writer_input.txt"), "w", encoding="utf-8").write(WRITER_SYS + "\n\n" + writer_user)
w = deepseek(WRITER_SYS, writer_user)
steps = {s["id"]: s["step"].strip() for s in w.get("steps", [])}
for x in units:
    x["step"] = steps.get(x["rid"], "")
json.dump(units, open(os.path.join(OUT, "writer_output.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

GOLD = [  # (task, step, expected pass)
    ("准备 Q4 复盘会", "如果明早 9 点坐到书桌前，就打开 Horizon 把复盘会的议程写成 3 行（约 10 分钟）", True),
    ("练一首吉他曲", "如果今晚吃完饭，就把吉他拿出来，用节拍器 60 把前奏弹两遍（约 10 分钟）", True),
    ("调研一个开源项目能否直接用", "如果下午打开电脑，就在浏览器打开它的 GitHub 首页，读 README 的安装一节（约 10 分钟）", True),
    ("交房租", "如果周三午饭后，就给房东发微信确认这个月的房租金额（约 3 分钟）", True),
    ("整理滑雪装备", "如果今晚 10 点前，就在手机备忘录里列出要寄的滑雪装备前 5 件（约 5 分钟）", True),
    ("搞懂 Agent RL", "研究一下 Agent RL。", False),
    ("做一个网站", "把整个网站做完并上线。", False),
    ("规划下半年", "如果有空，就想想这件事。", False),
    ("写季度报告", "如果服务器配好、数据都整理完，就开始写报告第一章。", False),
    ("学 Transformer", "学习 Transformer 的全部原理并写一篇完整总结。", False),
]
sheet = [{"key": x["rid"], "task": re.sub(r"。.*$", "", x["context"]), "step": x["step"], "gold": None} for x in units]
sheet += [{"key": "g%02d" % (i + 1), "task": t, "step": s, "gold": g} for i, (t, s, g) in enumerate(GOLD)]
random.Random(20261109).shuffle(sheet)
for i, row in enumerate(sheet, 1):
    row["sid"] = "s%02d" % i
json.dump(sheet, open(os.path.join(OUT, "sheet_key.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

JUDGE = ("你是严格的评审。下面每一行是一件事和为它写的「第一步」。逐条按 6 条标准判断，全部满足才算 pass：\n"
         "A 动作具体（打开/写下/发消息/搜索/列出等，不是「研究一下/了解/想想/学习」）\n"
         "B 对象具体（明确做在什么东西上）\n"
         "C 15 分钟内能开始并做完这一步\n"
         "D 不需要先完成别的事\n"
         "E 有时间或情境触发（「如果…」）\n"
         "F 和这件事有关，不是跑题\n"
         "只输出 JSON：{\"results\":[{\"id\":\"s01\",\"pass\":true,\"fail\":[]},{\"id\":\"s02\",\"pass\":false,\"fail\":[\"A\",\"C\"]}]}，每一行都要有。\n\n")
lines = "\n".join("%s ｜ 事：%s ｜ 第一步：%s" % (r["sid"], r["task"], r["step"]) for r in sheet)
open(os.path.join(OUT, "judge_sheet.txt"), "w", encoding="utf-8").write(JUDGE + lines + "\n")
dj = deepseek("你只输出 JSON。", JUDGE + lines)
json.dump(dj, open(os.path.join(OUT, "judge_deepseek.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("push units:", len(units), "| steps written:", sum(1 for x in units if x["step"]), "| sheet rows:", len(sheet),
      "| deepseek verdicts:", len(dj.get("results", [])))
for x in units:
    print(" ", x["rid"], x["unit"], "→", x["step"])
