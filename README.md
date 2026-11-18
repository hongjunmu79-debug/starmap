# 开机首页（Agent Home）

打开电脑就弹出来的那一页：今天做什么、四个在跑的项目到哪了、每一件事的下一步。
地址 http://localhost:8777 ，只在本机监听。

## 你自己怎么用

- 最上面「今天」三张卡：做完点「做完了」，下一步会自己亮起来。标着「已备好」的，点「看我备好的」看一眼就行。
- 右上角「记一笔」：想到什么就记，回车保存，会出现在想法池。
- 想法池里每条想法有三个按钮：
  - 「编辑」：想法的内容、属于哪一件、第一步都能在这里改，第一步可以先空着，保存。
  - 「复制给 Agent」：复制一段提示词，贴给台式机上的 Claude Code（接 DeepSeek）或 Hermes，它会替你写归属和第一步。
  - 「删掉」。
- 想法攒了几条之后，点想法池上方的「复制『整理想法池』」，贴给 Claude，它会把这些想法并进正式清单。
- 台式机装好 Hermes 的每日备料以后（见 `../incoming/KICKOFF.md`），上面这些每天会自动做一遍，你只需要看。
- 手机上：Hermes 每天 10:30 把「今天三件事」推到你的飞书；在飞书或 Telegram 发「记个想法：……」，就会进想法池。

## 文件

| 文件 | 谁写 | 是什么 |
|---|---|---|
| `content.json` | Claude（或任何 Agent，按下面的格式） | 19 件事和它们的步骤；每件的 `includes` 写着合并了哪些原始想法 |
| `events-<主机名>.jsonl` | 首页服务（每台电脑只写自己那一份） | 进度记录：做完、撤销、记的想法、改状态 |
| `events-hermes.jsonl`、`events-mosaico.jsonl` | Hermes、Mosaico | 从手机或桌面硬件记进来的想法 |
| `handoff/<项目 id>.md` | 台式机上做这个项目的 Agent | 在跑项目的交接卡，规则见 `../templates/HANDOFF_RULE.md` |
| `全部清单.md` | 首页服务自动生成 | 给 Agent 和 Obsidian 读的纯文本版，别手改 |
| `server.py` / `launcher.py` / `install.py` | — | 服务、解锁时打开、注册计划任务 |

两台电脑通过 Syncthing 同步这个文件夹。每个文件只有一个写入方，所以不会冲突。

## 往想法池里加一条（给 Hermes、Mosaico 或任何脚本）

往同目录自己的事件文件里追加一行 JSON（UTF-8，一行一条）：

```json
{"id": "随机唯一字符串", "ts": "2026-11-06T14:30:00+00:00", "host": "hermes", "type": "idea", "idea_id": "同 id", "text": "想法内容"}
```

`ts` 用 UTC。首页一分钟内会显示出来，标成「待补第一步」。

也可以直接调接口：`POST http://localhost:8777/api/event`，`Content-Type: application/json`，body 为 `{"type": "idea", "text": "想法内容"}`。

## 已备好、想法归属、早报（给 Hermes）

台式机上的 Hermes 每天照 `../templates/HERMES_DAILY_PREP.md` 跑一次：
- 备好的材料存成 `prepared/<项目 id>.<第几步，从 1 数>.md`，首页自动把那一步标成「已备好」，今天的卡片优先推它。
- 新想法的归属和第一步，以 `idea_note` 一行追加到 `events-hermes.jsonl`，首页显示在想法下面。
- 一句话早报写进纯文本 `brief.md`，首页顶部显示。
- 交接卡超过 2 天没更新，首页服务自己会标出来，不用模型。

## 整理想法池（给 Claude）

用户说「整理想法池」时：读 `全部清单.md` 末尾「你记下的新想法」（有的已经带着 Hermes 或用户写的归属和第一步，优先采用），先判断它是不是已有 19 件里某一件的一部分；是就追加到那一件的 `includes` 和 `steps`，不是再在 `content.json` 里新增一项（`status: "pool"`，步骤写到 30 分钟内能做完的程度），最后往事件文件追加一条 `{"type": "idea_drop", "idea_id": ...}` 把它从待补列表里拿掉。

## 接口

- `GET /api/all`：全部数据
- `GET /api/today`：今天的三张卡（在跑一件、探索一件、轻松一件），待办工作台、Hermes、Mosaico 读这个就行
- `POST /api/event`：`done`、`undo`（带 `item`、`step`），`idea`（带 `text`），`idea_edit`（带 `idea_id`、`text`，改想法内容），`idea_note`（带 `idea_id`、`belongs`、`first_step`，第一步可以是空的），`idea_drop`（带 `idea_id`），`skip`（带 `item`、`kind`），`promote`（带 `item`、`to`）

## 安装和卸载

每台电脑双击一次 `install.bat`：登录时启动服务并打开首页；离开两小时以上回来解锁时再打开一次。
双击 `uninstall.bat` 删除这两个计划任务。日志在 `%LOCALAPPDATA%\agent-home\server.log`。
