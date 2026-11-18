# B 续上 — 判卷和评分规则（在看到任何判卷结果之前定下，2026-11-09 18:09 +0800）

- 过线：测试集（按时间后一半）前 3 命中 ≥ 80% 且误报 ≤ 15%；门槛只用前一半来定。
- 判卷：DeepSeek（deepseek-chat）、Gemini（agy gemini-4-argon-high）、Claude（agy claude-opus-5-5-high），各自盲判同一份考卷；每家 10 道已知答案题对 ≥ 8 道才算数；能用的至少 2 家且 Fleiss κ ≥ 0.6，否则结果作废、停下汇报。
- 金标准：能用的几家多数票；同票算有争议，不进金标准。
- 选方法：从便宜到贵 M0 字面 → M1 BM25 → M2 bge-m3 → M3 融合 → M4 加拼音，取第一个过线的。
- 外发：每份考卷 ≤ 40 行，每段 ≤ 200 字，先过 b_redact 脱敏，再过 b_gate 扫描，0 命中才发。
- 时间比较一律按时刻（UTC），不按字符串；本批数据核对过，旧写法和新写法的可见记录 0 处不同。

脚本 SHA-256（前 16 位）：

```
56cfab501103f9c5 *b_rank.py
8c26161873cbebaf *b_pool.py
be72ff696d584b99 *b_redact.py
ad8b427709ef97ae *b_gate.py
f440aee73b425a64 *b_judge_ds.py
e08872730dbc2078 *b_judge_agy.py   （18:11 改：读 agy 已校验的 structured_output；只在两行假题上试过，未发任何真实考卷）
688f474401d1871f *b_score.py
```

已知答案题实际 9 道（msg:m366 / msg:m367 那对有一条不在语料里），「对 ≥ 80%」即对 8 道以上，标准不变。考卷 18:13 生成：326 对 + 9 道，分 9 份，b_gate 0 命中，人工抽查 @ / key / token / 微信 的上下文，均为文件路径和普通用语。

18:17 起第二个 Gemini 进程倒序判（b_judge_agy.py 加了 --reverse，只改顺序；新指纹 f475178bf4a68be0）。

18:24 补漏：考卷 05–09 里有一处用户全名（简历文件名），b_redact 只遮了「某总」式称呼。已发出：DeepSeek 01–09、Claude(agy) 05–08、Gemini 07–09。随即加规则 name-before-cv（简历/履历/CV 前的 2–4 个汉字 → 某某），05–09 当场遮掉；之后发出的 Gemini 05–06 与 Claude 09 都是遮过的。b_redact 新指纹 3612388cac4f460b。
