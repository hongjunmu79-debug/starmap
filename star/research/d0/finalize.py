"""Write ideas_raw.jsonl (idea moments + provenance + outcome), the 30-item spot-check list, and Wilson intervals."""
import collections, json, math, os, random, re, sys

sys.stdout.reconfigure(encoding="utf-8")
D = os.path.dirname(os.path.abspath(__file__))
OUT = "C:/Agent-Shared/home/star/research"
msgs = {m["id"]: m for m in json.load(open(os.path.join(D, "all_msgs.json"), encoding="utf-8"))}
labels = {}
for n in (1, 2, 3):
    for l in open(os.path.join(D, "labels-%d.jsonl" % n), encoding="utf-8"):
        if l.strip():
            x = json.loads(l)
            labels[x["id"]] = x

# cluster outcome, judged by hand from evidence.txt + content.json + Horizon + project folders (see D0-report.md)
OUTCOME = {
    "esp32-voice-assistant": ("recorded", "首页 voice「Hermes 实时语音前台（含桌宠）」里的 ESP32 桌宠"),
    "esp32-recorder": ("dangling", "只在 10-17/18 台式机会话里；首页只有缩小版「Mosaico 按住说话记想法」"),
    "esp32-task-display": ("done", "当场做了桌面任务提示器；首页 personal-os「坐下即知 / Mosaico 小屏」"),
    "esp32-task-apps": ("partly", "电脑端 exe 当场做了；手机 app（安卓/鸿蒙）没见下文"),
    "esp32-sim": ("done", "当场搭了模拟器；11-02 在另一个会话又提起（试 Agent 固件仿真）"),
    "cross-agent-session-ref": ("done", "当场做成项目 agy-context（台式机 projects/，11-01）"),
    "workbench-radar-aihot": ("recorded", "首页 hub「情报雷达接 AI hot」，还没做"),
    "six-hats-device": ("done", "当场做了（暂停键、换帽语音、音效）"),
    "todo-alarm-huawei": ("done", "Horizon 提醒→日历→手表已打通（11-04 有联调待办，11-06 完成）"),
    "hermes-watchdog": ("done", "当场做了看门狗和崩溃循环处理"),
    "obsidian-color-groups": ("done", "当场做了颜色分组"),
    "wiki-visualize": ("done", "当场把 wiki 接进 Obsidian 的图谱"),
    "concert-lyrics-sync": ("recorded", "10-25 演唱会现场手机提出并当场试过；11 天后（11-05）在台式机重新提起，成了 singalong 项目和首页 lyrics"),
    "land-contract-cloud-db": ("dangling", "首页和 Horizon 里都没找到（没查 land-lease 项目文档）"),
    "nfc-werewolf": ("recorded", "首页 offline-social 有「NFC 卡发身份，ESP32 当法官」；「每局直接洗牌」「网址分开」没找到"),
    "own-hermesh-agent-net": ("done", "11-04 手机提出，11-06 在笔记本重新提起；后来做成 agent-bridge"),
    "starmap": ("done", "正在做（星图原型、第 1 期）"),
    "starmap-3d": ("done", "当场做了 3D 两个副本和融合版"),
    "idea-dump-1106": ("recorded", "当场合并进首页 19 件事"),
    "boot-homepage": ("done", "当场做了开机首页"),
    "agent-task-sync-feishu": ("handled", "当场在 Hermes 里部署试了；之后没记下、没再提"),
    "ocr-aggregator": ("handled", "当场问到了答案；没记下"),
    "moss-live": ("recorded", "11-03 飞书提出，11-06 微信又提；首页 voice 里有「试 MOSS-Live」（字面匹配没找到，人工核对才找到）"),
    "super-agent-research": ("recorded", "Horizon 收件箱→待办「调研 Comma 能否直接用」，还没做"),
}
SRC = {"laptop-claude": "笔记本 Claude Code", "desktop-claude": "台式机 Claude Code", "phone-feishu": "手机 飞书→Hermes",
       "phone-weixin": "手机 微信→Hermes", "phone-telegram": "手机 Telegram→Hermes"}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "ideas_raw.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for mid in sorted(labels, key=lambda k: msgs[k]["ts"]):
        m, l = msgs[mid], labels[mid]
        o = OUTCOME[l["cluster"]]
        f.write(json.dumps({"id": mid, "ts": m["ts"], "source": SRC.get(m["src"], m["src"]), "session": m["session"], "message": m["uuid"],
                            "project": m["project"], "kind": {"I1": "旁支想法", "I2": "当前任务里的想法"}[l["label"]], "cluster": l["cluster"],
                            "text": m["text"], "gist": l["gist"], "outcome": o[0], "outcome_note": o[1]}, ensure_ascii=False) + "\n")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def show(name, k, n):
    lo, hi = wilson(k, n)
    print("%-34s %3d / %-3d = %5.1f%%  (95%% CI %4.1f–%4.1f%%)" % (name, k, n, 100 * k / n, 100 * lo, 100 * hi))


oc = collections.Counter(v[0] for v in OUTCOME.values())
print("outcomes:", dict(oc))
show("messages that hold an idea", len(labels), len(msgs))
for src in ("desktop-claude", "laptop-claude", "phone-feishu", "phone-weixin"):
    n = sum(1 for m in msgs.values() if m["src"] == src)
    k = sum(1 for i in labels if msgs[i]["src"] == src)
    if n:
        show("  of which from " + src, k, n)
show("ideas done / realized", oc["done"], len(OUTCOME))
show("ideas recorded, not done", oc["recorded"], len(OUTCOME))
show("handled in chat, no record", oc["handled"], len(OUTCOME))
show("dangling (no record found)", oc["dangling"], len(OUTCOME))
show("dangling incl. half-dangling", oc["dangling"] + oc["partly"], len(OUTCOME))
show("re-raised in a later session", 4, len(OUTCOME))
show("home steps done", 2, 89)
show("Horizon top-level todos done", 2, 16)
show("open Horizon todos overdue", 7, 14)
show("sessions opening with a pasted dump", 7, 81)

# spot-check: 15 of my idea labels + 15 longer non-idea messages (no system/auto text)
rnd = random.Random(20261109)
idea_ids = sorted(labels)
auto = re.compile(r"^\s*(\[|What do you see|You've reached|I hit my usage|Try again|<pasted_content)")
non = [k for k, m in msgs.items() if k not in labels and m["chars"] >= 30 and not auto.match(m["text"])]
pick = [(k, "想法") for k in rnd.sample(idea_ids, 15)] + [(k, "不是想法") for k in rnd.sample(non, 15)]
rnd.shuffle(pick)
lines = []
for n, (k, lab) in enumerate(pick, 1):
    t = re.sub(r"\s+", " ", msgs[k]["text"]).strip()
    t = t if len(t) <= 90 else t[:88] + "…"
    lines.append("%d. 【我判：%s】%s（%s，%s）" % (n, lab, t, SRC.get(msgs[k]["src"], msgs[k]["src"]), msgs[k]["ts"][5:10]))
open(os.path.join(D, "spotcheck.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
json.dump(pick, open(os.path.join(D, "spotcheck_ids.json"), "w", encoding="utf-8"))
print("spot-check items:", len(lines), "| non-idea pool size (>=30 chars, not system text):", len(non))
