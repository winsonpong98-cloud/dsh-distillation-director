# -*- coding: utf-8 -*-
r"""_bandid.py —— **波段条目 id 语法的唯一来源**（工作台级单一真源）

## 为什么必须存在这个文件（2026-09-19 · NAS 异机实测 · 避坑手册 A-132）

「波段条目 id」（官方模板的 `### {band}-NNN  [类型] [技能=…]` 里的 `{band}-NNN`）
这套语法在工作台里**被内联写了 16 遍**，而且有 **4 种互不兼容、各自残缺**的写法：

| 内联写法 | 吃得到 | 吃不到（⇒ 该仪器对该册**恒不命中**） |
|---|---|---|
| `[A-Za-z]\d+` | `T1-001` | 纯字母波段 `A-001`（manias 册 A..G） |
| `[A-Za-z]\d*` | `A-001`、`T1-001` | 多字母前缀 `ST-001` |
| `[A-Za-z]+`    | `A-001`、`ST-001` | **「字母＋数字」波段 `E1-001`／`T1-001`** |
| `[A-Za-z][0-9]*` | `A-001`、`T1-001` | 多字母前缀 `ST-001` |

**实测后果（本次抓到的活体标本）**：NAS 上的册 `cn-pop-2100` 波段名是 `E1..E6`，
产出 `candidates/notes_E1.md … notes_E6.md` **完全合规**（`### E1-001  [PR] [技能=S3]`），
但 `tools\gate_stage.py` 的阶段1 两条判据用了**两种写法** ——
`[A-Za-z][0-9]*-[0-9]{3}`（过得了 `E1-001`）与 `tools\verify_candidates.py` 的
`[A-Za-z]+-`（过不了）⇒ 同一份产出**一半判据绿、一半报 🔴「切块为空：条目正则未命中任何块
（工装缺陷，不得视为通过）」**，且这条红被诚实地标注成"工装缺陷"，**却没人发现缺陷就是尺子本身**。

这与《避坑手册》`A-72`「同一判据写两遍＝改一处等于没改」同族，但**更狠：写了 16 遍**
（且其中 4 遍各自"修"过一次，每次都把另一形态修坏 —— 这是"修判据要写该形态的完整语法，
不是比旧版松一点"这条教训的第 4 次复发）。

## 纪律

1. **任何脚本需要"波段条目 id"的正则时，一律 `from _bandid import BAND, NUM, ID, ...`**；
   **不得再在别处内联** `[A-Za-z]...-\d{3}`。巡检闸：`tools\check_bandid_single_source.py`
   （扫全 `tools\` 的内联残片 ⇒ 期望 rc=0），已挂 `postflight`。
2. 改语法**只改本文件一处**，全工作台同时生效（`gate_selftest` 内含本模块自证）。

## 语法（覆盖全部历史册与在役册的实测形态）

```
BAND = [A-Za-z][A-Za-z0-9]*     波段前缀：**字母开头**，其后可含字母与数字
                                A ／ T1 ／ E1 ／ ST ／ ST1 ／ ST1a ／ B12  …都收
NUM  = \d{3}                    条目序号：**恰好三位数字**（官方模板硬纪律）
ID   = <BAND>-<NUM>             A-001 ／ T1-001 ／ E1-001 ／ ST-001 ／ B12-005
```

**为什么前缀必须是「字母开头 + 字母数字混合」而不是更窄的四种写法**：
上面表格里每一种窄写法都会把另外某一册的**全部条目**判成不存在（＝**判据过窄导致的假红**，
`A-04` 家族），而"假红"会诱导执行者去改**合规的产出**（比假绿更伤 —— 见 `A-55` 家族）。

**为什么不收到"数字开头"（如 `2024-001`）**：官方模板规定条目 id 以**字母**开头；
放宽会把**年份／页码／表格行**误当条目头，正是本模块要拦的假通过。
负样本自证：`python tools\_bandid.py`（或 `--selftest`）。

**为什么不收到"任意非空白"**：`ID` 必须能被 `[技能=…]`／`[类型]` 两段紧跟校验（见 `ENTRY`），
前缀一旦过宽，`### --- [AB] [技能=x]` 这类噪声也会"看起来像条目"（`A-28` 假通过家族）。
"""

import re

# ── 唯一真源（**只此一份**；下列常量之外的任何内联写法都由巡检闸判红）──────────────
BAND = r"[A-Za-z][A-Za-z0-9]*"      # 波段前缀
NUM = r"\d{3}"                       # 条目序号（三位）
ID = BAND + "-" + NUM                # 完整 id
# 宽松档：容忍非三位序号（拆分器/规范化器等**改文件**的工具用；**不得**用作校验判据）
ID_LOOSE = BAND + r"-\d+"

# 条目块起点：`^### <id>` 之后必须跟空白（防 `### E1-0012` 这类更长 id 被截断误解）
# ⚠ 空白必须是 `[ \t]+`（**一个或多个**）：官方模板的条目头是
#   `### {band}-NNN  [类型] [技能=…]` —— id 与 `[类型]` 之间**是两个空格**；
#   写死一个空格会**恒不命中模板产出**（本次自证当场抓到：切块 3 块应得、实得 0）。
#   这是"形态必须写全"（A-57 家族）在空白维度上的同一课。
HEAD = r"^###\s+" + ID + r"(?:[ \t]+\[|$)"
HEAD_RE = re.compile(HEAD, re.M)
BLOCK_RE = re.compile(r"^###\s+" + ID + r"[ \t]+\[")

# 官方模板完整条目头：`### {band}-NNN  [类型] [技能=建议]`（可带尾部说明）
#   组：1=波段 2=序号 3=类型(两位大写) 4=技能 5=尾部说明(可空)
ENTRY = re.compile(
    r"^###\s+(" + BAND + r")-(" + NUM + r")\s+\[([A-Z]{2})\]\s+\[技能=([^\]]*)\](?:\s+(.*))?$",
    re.M)

# 同上的**前缀档**（只要 `### <id>  [类型] [技能=` 即可，不要求行尾）——
# 供 gate_stage 这类"计数条目"的闸使用；与 ENTRY 同语法、同真源。
TEMPLATE_HEAD = re.compile(r"^###\s+" + ID + r"\s+\[[A-Z]{2}\]\s+\[技能=", re.M)

# 以 `### <id>  [` 为切分点的前瞻（**必须 re.M**，否则 `^` 不匹配行首）
SPLIT = re.compile(r"(?=^###\s+" + BAND + r"-" + NUM + r"\s+\[)", re.M)

# 正文里出现的 id 令牌（技能 SKILL.md 的引文页锚、附属文件等）
ID_RE = re.compile(ID_LOOSE)
ID_EXACT_RE = re.compile(r"(?<![A-Za-z0-9])(" + ID + r")(?![0-9])")

# 源文分波段文件名里的波段名：`<band>.txt` / `<band>.md`（同一语法，避免各处再写一遍）
BAND_ONLY = re.compile(r"^(" + BAND + r")\.(?:txt|md)$")
# 候选笔记文件名里的波段名：`notes_<band>.md`
BAND_FROM_NOTES = re.compile(r"notes_(" + BAND + r")\.md")


def split_blocks(text):
    """按条目头切块，**只保留真条目块**（首行必须是 `### <id>  [`）。"""
    return [b for b in SPLIT.split(text) if BLOCK_RE.match(b)]


def iter_entries(text):
    return ENTRY.finditer(text)


def ids(text):
    return [m.group(0) for m in ID_RE.finditer(text)]


def is_entry_head(line):
    return bool(BLOCK_RE.match(line))


# ── 自证（正样本必须全中、负样本必须全不中）────────────────────────────────────
POS = [
    ("### A-001  [PR] [技能=S1]", ("A", "001", "PR", "S1")),
    ("### T1-001  [CE] [技能=S3]", ("T1", "001", "CE", "S3")),
    ("### E1-001  [PR] [技能=S3]", ("E1", "001", "PR", "S3")),
    ("### ST-001  [CE] [技能=S2]", ("ST", "001", "CE", "S2")),
    ("### ST1-007  [DR] [技能=待定]", ("ST1", "007", "DR", "待定")),
    ("### B12-005  [CE] [技能=S4] 尾部说明", ("B12", "005", "CE", "S4")),
    # 回归：旧册 T1..T6 与 manias A..G（历史上分别被两种写法漏掉过）
    ("### T5-029  [CE] [技能=S3] 饮食疗法（总评）", ("T5", "029", "CE", "S3")),
]
NEG = [
    "### 2024-001  [PR] [技能=S1]",      # 数字开头（年份/页码）
    "### E1-01  [PR] [技能=S1]",         # 序号非三位
    "### E1-001  [P] [技能=S1]",         # 类型非两位
    "### E1-001  [PR]",                  # 缺 [技能=…]
    "### -001  [PR] [技能=S1]",          # 无波段前缀
    "#### E1-001  [PR] [技能=S1]",       # 四级标题
]
# 其中**连块头都不该算**的（另两条：id 本身合法、只是模板字段不全 ⇒ 该被 ENTRY 拦，不该被 BLOCK_RE 拦）
NEG_BLOCK = [NEG[0], NEG[1], NEG[4], NEG[5]]


def selftest():
    bad = []
    for line, want in POS:
        m = ENTRY.match(line)
        if not m:
            bad.append("正样本未命中：%s" % line)
            continue
        got = (m.group(1), m.group(2), m.group(3), m.group(4))
        if got != want:
            bad.append("正样本字段错：%s ⇒ %s（应 %s）" % (line, got, want))
    for line in NEG:
        if ENTRY.match(line):
            bad.append("负样本被误收（ENTRY）：%s" % line)
    for line in NEG_BLOCK:
        if BLOCK_RE.match(line):
            bad.append("负样本块头被误收（BLOCK_RE）：%s" % line)
    # 切块自证：三种波段形态混排必须切出 3 块
    txt = "\n".join([POS[0][0], "正文", POS[2][0], "正文", POS[3][0], "正文"])
    n = len(split_blocks(txt))
    if n != 3:
        bad.append("切块数错：3 块应得，实得 %d" % n)
    # 令牌自证
    if ids("见（`E1-001` s12／`A-007` s3）") != ["E1-001", "A-007"]:
        bad.append("ID_RE 取令牌错")
    print("BAND=%s  NUM=%s  ID=%s" % (BAND, NUM, ID))
    print("正样本 %d／负样本 %d" % (len(POS), len(NEG)))
    if bad:
        for b in bad:
            print("🔴 %s" % b)
        return 1
    print("✔ _bandid 自证通过（正样本 %d 全中、负样本 %d 全拦、切块 3/3）" % (len(POS), len(NEG)))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
