# -*- coding: utf-8 -*-
r"""rquote_page_check.py —— 防线3 机器层「rquote：引文逐字 ＋ **页码定位 100%**」（执行单 #10）

与既有工装的区别（为什么另写一件）：
  · `tools\verify_candidates.py` 只做**引文在整册源文里能否逐字找到**（文件级回源）；
  · `tools\stage15_merge_task.py` 的页锚三态做的是**候选池**里的锚（池内）；
  · **本件做的是技能正文级**：把各件 `SKILL.md` 里每一处「（`id` sNNN）」的**页锚**取出，
    回查源文**按本册页锚形态分页**后，**该引文是否真的落在它自称的那一页**。
  ⇒ 这正是判官抓出「页锚换算写错（＋10 vs ＋16）」那一类错误的正规机器判据。

  ⚠ **换书必读（2026-09-17 修）**：页锚形态与源文件名**一律从本册配置读**（`bookspec-<task>.json`
    的 `pagemark`／`pagemark_form`，缺则 `auto`），**不得写死**——旧版把形态写死为上一册的
    `equals`，换书后分页**全错**，而症状不是报错、是"命中率照样算得出来但它是错的"
    （`A-69` 家族：书别参数写死 ⇒ 静默产出错答案；`A-74`：通用件不得含任何一本书的数据）。

判据（逐条三态，全部可核）：
  · `PAGE_OK`     —— 引文（`norm_match` 口径）在自称页内逐字命中
  · `PAGE_MISS`   —— 引文在**别的页**命中（错锚）
  · `NET_MISS`    —— 引文全册找不到（无锚）
  · 另报 `ID_MISS` —— 技能里引用的候选 id 在池内不存在

用法（零书别参数；标签即任务 slug）：
  python tools\rquote_page_check.py --task <slug>
  python tools\rquote_page_check.py --task <slug> --out <md> --json-out <json>

  ⚠ **写入型自检禁令（手册 §18.5 / V-11）**：复核已交付任务时**必须显式传 `--out`／`--json-out`
    到暂存路径**，否则会**覆盖该任务已归档的核对报告**。

退出码：0 = 全部 PAGE_OK 且无 ID_MISS；1 = 有硬项（或配置缺 `src`，拒绝运行）
"""
import argparse
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC
from _qnorm import norm_strip  # noqa: E402（G-57 单一来源；③ 层容差复判用，G-51/G-55）
import stage15_merge_task as M
import verify_layer_quotes as VLQ   # ← 「页锚直核」层的归一化器与分段**单一来源**（G-45 收敛）

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
import _bandid as BID  # noqa: E402  ← 波段 id 语法唯一来源（A-132）
# 技能正文里的断言形态（**一个括号内可含多条**，实测抓到漏检）：
#   `（`A-036` s32／`C-066` s142）`  ← 全角「／」分隔的双断言；首版只吃单条，**漏检了这类**
#   `（`A-036` s32）` / `（A-036 s32）` / `[A-036 s32]` / 多条以 、，; 空格 分隔
# 修法：先整块取出括号/方括号内容，再在块内**逐条扫** `id + sNNN`。
BRACKET = re.compile(r'[（(\[]([^（()）\[\]]{0,400}?)[）)\]]')
# 块内出现的一切候选 id（用于识别「多个 id 共享一个页锚区间」的写法，见下方共享区间分支）
#   ⚠ 用 **STRICT** 档（`_bandid.ID_LOOSE_STRICT`）：排除"页锚形"（`s206`／`p47`）——
#   实测（2026-09-23）该册 `crisis-stage-locator\INDEX.md` L225 是**页锚簇清单**
#   （「…含 s206-209、s262-263、s284-301…」），宽松档把它读成 id ⇒ **ID_MISS 假阳性 ×3**。
ID_RE = re.compile(BID.ID_LOOSE_STRICT)
# **形态 A：id 在前、锚在后**（`（`A-025` s25）`）。⚠ 2026-09-23 收紧"间隙"：
#   `[^0-9]{0,4}?` 允许跨过**右括号**⇒ 实测把 `（〔s166〕〔D-012〕、〔s192〕〔D-038〕）` 里的
#   `D-012` 与**后面的** `s192`（其实属于 `D-038`）配成一对 ⇒ PAGE_MISS 假红。
#   收紧为"间隙不得含右括号/右方括号"⇒ **id 只能与同一组内的锚配对**。
ONE = re.compile(r'`?\s*(' + BID.ID_LOOSE_STRICT + r')\s*`?[^0-9〕）)】\]]{0,4}?s\s*(\d{1,4})(?:\s*[-–—~至]\s*s?\s*(\d{1,4}))?')
# **形态 B：锚在前、id 在后**（`〔s166〕〔D-012〕` —— 本册 `GLOSSARY.md`/`SKILL.md` 的实际写法）。
#   ⚠ 与 L129–L136 那次"迁就多引用块"的**回退方向不同**：这里**不放松**，而是要求
#   **锚与 id 之间必须有一个右括号＋左括号的边界**（＝同一组内的紧邻配对），
#   因而不会把「多引用块」里的 `A` 的锚配到 `B` 的 id 上。**紧邻是更严，不是更松。**
ONE_AF = re.compile(r'[sp]\s*(\d{1,4})\s*[〕）)】\]]\s*[〔（(\[]\s*`?\s*(' + BID.ID_LOOSE_STRICT + r')\s*`?')
# ⚠ 口径修正第三次（2026-09-17 实测抓到）：必须**区间感知**（项目纪律 A-44 同族）——
#   技能里有 `（D-022/D-026 s185-186）` 这类**区间锚**；首版只取首个数字 ⇒ 把合法的区间锚
#   判成"错锚"（引文落在区间另一端时）。修法：捕获可选的 `-NNN` 终点，命中区间**任一页**即算 PAGE_OK。

# ══════════════════════════════════════════════════════════════════════════════════
# **第二种断言形态：页锚直核（内联引文 ＋ `〔…（pNN）〕`，**不需要池**）**
#   为什么要加（闸缺陷台账 `G-21`）：本库实际交付的锚形态**不止一种**。实测至少 6 种：
#     `（`id` sNNN）`（本件原有）／`——〔…（pNN）〕`（后锚）／`〔…（pNN）〕「引文」`（前锚）／
#     `——pNN`（裸页号）／页区间 `（p474-482）`／`bark p84`（书别名＋页号，见 `G-30`）。
#   旧版只认第一种 ⇒ 对其他形态**断言 0**，报告读起来像"这册一条断言都没有"，实为**仪器看不见**
#   （`A-143` 家族：空转不像空转）。本节把已在独立探针里验证过的三种正则**移植进在役仪器**
#   （来源：`.work\_accept7-rejudge-20260923\_probe_rquote_altform.py`，2026-09-23 实测
#    `原则 100%／黑天鹅 100%／随机漫步的傻瓜 100%／非对称风险 100%／反脆弱 94.12%／攻守可转债 89.39%`）。
#   ⚠ 本节**不需要池**：引文就内联在技能件里，核的是"它是否在自称的那一页逐字出现"。
#   ⚠ 引文按 `……` 分段（段长 ≥8 才判），**每段都要落页**才算命中（与探针同口径）。
QUOTE_ALT = re.compile(r'「([^」]{4,4000})」[^\n]{0,28}?[（(]?\s*p\s*(\d{1,4})')
QUOTE_ALT_RANGE = re.compile(r'「([^」]{4,4000})」[^\n]{0,30}?[（(]\s*p\s*(\d{1,4})\s*[-–—~至]\s*p?\s*(\d{1,4})\s*[）)]')
QUOTE_ALT_PRE_RANGE = re.compile(r'〔[^〕\n]{0,40}?[（(]\s*p\s*(\d{1,4})\s*[-–—~至]\s*p?\s*(\d{1,4})\s*[）)][^〕\n]{0,20}?〕\s*「([^」]{4,4000})」')
QUOTE_ALT_PRE = re.compile(r'〔[^〕\n]{0,40}?[（(]?\s*p\s*(\d{1,4})\s*[）)]?[^〕\n]{0,20}?〕\s*「([^」]{4,4000})」')
SEG_SPLIT = re.compile(r'……|\.\.\.\.\.\.')


def alt_assertions(text):
    """抽出「内联引文 ＋ 页锚」断言：返回 [(引文, [页…])]，按位置去重。"""
    out, seen = [], set()
    def _add(key, q, pgs):
        if key in seen:
            return
        seen.add(key)
        out.append((q, [p for p in pgs if p]))
    for m in QUOTE_ALT_RANGE.finditer(text):
        p0, p1 = int(m.group(2)), int(m.group(3))
        _add(m.start(1), m.group(1), list(range(min(p0, p1), max(p0, p1) + 1)))
    for m in QUOTE_ALT_PRE_RANGE.finditer(text):
        p0, p1 = int(m.group(1)), int(m.group(2))
        _add(m.start(3), m.group(3), list(range(min(p0, p1), max(p0, p1) + 1)))
    for m in QUOTE_ALT.finditer(text):
        _add(m.start(1), m.group(1), [int(m.group(2))])
    for m in QUOTE_ALT_PRE.finditer(text):
        # ⚠ 自伤登记（2026-09-24 · 移植当天被抓）：本式**只有 2 个组**（组1＝页、组2＝引文），
        #   我照「前锚·页区间」那式的组号写成 `group(3)` ⇒ `IndexError: no such group` ⇒ `黑天鹅` rc=2
        #   （正是本件第 ② 条要防的「看着像这册没断言」）。组号必须逐式核对。
        _add(m.start(2), m.group(2), [int(m.group(1))])
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# **合成页号探测器**（闸缺陷台账 `G-47`；2026-09-24 由 `zhouqi-guzhi-renxing` 判官实证后新增）
#   事实：有些册的源文本是按 epub spine 节（片）拼出来的，`===== [PAGE N] =====` 里的 N
#   其实是 `backfill_task.py` **按片号合成**的（锚号＝片号）⇒ 在这种册上，本仪器的 100%
#   是**结构性同义反复**（只证明「池 ↔ 合并文本同源」），**不能**证明「能点回**真实页**」。
#   判据只用源文本自身（不依赖册目录 ⇒ 可随包）：`[PAGE N]` 块多数以「源节文件名」起头。
PAGE_BLOCK = re.compile(r'=====\s*\[PAGE\s*(\d+)\]\s*=====')
SECTION_HEAD = re.compile(r'^#\s*\S+\.(?:md|xhtml|html|xht)\b|<!--\s*src:', re.M)


def detect_synth_pagemark(src_path):
    """返回 (是否疑似合成, 页块数, 命中数, 样例行)。"""
    try:
        t = io.open(src_path, encoding="utf-8", errors="replace").read()
    except Exception:
        return (False, 0, 0, "")
    parts = PAGE_BLOCK.split(t)
    bodies = [parts[i] for i in range(2, len(parts), 2)]
    n = hit = 0
    sample = ""
    for b in bodies:
        first = next((ln.strip() for ln in b.split("\n") if ln.strip()), "")
        if not first:
            continue
        n += 1
        if SECTION_HEAD.search(first):
            hit += 1
            if not sample:
                sample = first[:80]
    return (n >= 5 and hit * 1.0 / max(1, n) >= 0.6, n, hit, sample)



# ══════════════════════════════════════════════════════════════════════════════════
# **③ 层：技能件自证层**（闸缺陷台账 `G-51`；2026-09-24 新增）
#   为什么必须有：① 层核的是**池里的引文**（`qn = VC.norm_match(pool[eid]['quote'])`），
#   技能件只提供 id 与页锚 ⇒ **技能把引文截断/改写，①层看不出来**（实测 `zhouqi` 在役件引文
#   全部 15 字截断、逐字回源 0/0/1，而 ①层照样给绿）。本层改用**技能件自己写的那段文本**。
#   归一化（`G-52`）：**先去换行**再折叠空白 —— 跨行断句否则会被误报「引文不在书里」。
def norm_q(s):
    """引文比对前的统一归一化：去换行 ＋ 折叠空白（单一入口）。"""
    return re.sub(r'\s+', '', s or '')


QUOTE3_A = re.compile(r'「([^」]{4,800})」[^\n]{0,60}?[（(]\s*`?\s*([A-Za-z][A-Za-z0-9]*-\d{1,4})\s*`?\s*[，,、／/]?\s*s\s*(\d{1,4})(?:\s*[-–—~至]\s*s?\s*(\d{1,4}))?')
QUOTE3_B = re.compile(r'「([^」]{4,800})」[^\n]{0,60}?〔[^〕\n]{0,30}?[（(]?\s*p\s*(\d{1,4})(?:\s*[-–—~至]\s*p?\s*(\d{1,4}))?\s*[）)]?[^〕\n]{0,30}?〕')
QUOTE3_C = re.compile(r'「([^」]{4,800})」[^\n]{0,60}?〔[^〕\n]{0,30}?\bp\s*(\d{1,4})\b')


def assertions3(text):
    """抽「技能件自己写的引文 ＋ 自称页」（③ 层的输入）。返回 [(引文, [页…], 偏移)]。"""
    out, seen = [], set()
    _EID = ['']
    def _add(key, q, pgs):
        if key in seen:
            return
        seen.add(key)
        out.append((q, [p for p in pgs if p], key, _EID[0]))   # key＝偏移；_EID[0]＝该式的 id（供 ③ 层门槛）
    for m in QUOTE3_A.finditer(text):
        _EID[0] = m.group(2)
        p0 = int(m.group(3))
        p1 = int(m.group(4)) if m.group(4) else p0
        _add(m.start(1), m.group(1), list(range(min(p0, p1), max(p0, p1) + 1)))
    for m in QUOTE3_B.finditer(text):
        _EID[0] = ''
        p0 = int(m.group(2))
        p1 = int(m.group(3)) if m.group(3) else p0
        _add(m.start(1), m.group(1), list(range(min(p0, p1), max(p0, p1) + 1)))
    for m in QUOTE3_C.finditer(text):
        _EID[0] = ''
        _add(m.start(1), m.group(1), [int(m.group(2))])
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# **G-65 配对通道**（2026-09-25 · 乙案收口）：索引层技能的**节引 × invest.md 全量引文层**配对可核。
#   背景：09-23 代技能把「全量逐字引文」下沉到同目录 `invest.md`（引文层），SKILL.md 只留索引节引
#   ⇒ ③ 层按 G-54 全判 ALT3_TRUNC（zhouqi 112/112，判官据此把该册第 1 条判 🔴）。
#   修法＝**加严**而非放宽（A-07：改数据形态，不放宽判据；与 A-84/K-10 那次"迁就禁止写法"相反——
#   多引用块被手册禁止，而"索引层＋invest.md 引文层"是登记在案的交付形态）：
#     P1 节引＝池内该 id 引文的**逐字连续子串**（`norm_strip` 尺 containment——省略号也被删，
#        「头…尾」式假节因中段不连续装不进去 ⇒ 天然防伪）；
#     P2 节引非平凡：norm 后 ≥ 20 字（与门槛 LCP12 同量级的实义下限；15 字索引碎片不够 ⇒ 逼产物重写）；
#     P3 池内**全量引文**已随技能件发行：本件同目录 `invest.md`（引文层）逐字在场（同尺 containment）。
#   三条全过 ⇒ 记 **ALT3_PAIR_OK**（不算红；**落页检查不豁免**——段未落自称页照旧 ALT3_MISS；
#   单列不并入 OK——松尺不静默，A-34）。任一不满足 ⇒ 照旧 ALT3_TRUNC。
_PAIR_INV = {}


def _invest_quote_text(sk_dir):
    """读本技能目录下的 `invest.md`（引文层）文本；缺文件返回 ''。按目录缓存。"""
    if sk_dir not in _PAIR_INV:
        _txt = ''
        _p = os.path.join(sk_dir, 'invest.md')
        if os.path.isfile(_p):
            try:
                _txt = io.open(_p, encoding='utf-8', errors='replace').read()
            except Exception:
                _txt = ''
        _PAIR_INV[sk_dir] = _txt
    return _PAIR_INV[sk_dir]


def _pair_eligible(q, _nq, pool_quote_raw, sk_dir):
    """G-65 配对可核判定（P1＋P2＋P3，见上）。任一不满足 ⇒ False（照旧 TRUNC）。"""
    if not pool_quote_raw or len(_nq) < 20:
        return False
    _ns_q = norm_strip(q)
    _ns_pq = norm_strip(pool_quote_raw)
    if not _ns_q or not _ns_pq or _ns_q not in _ns_pq:
        return False
    _ns_inv = norm_strip(_invest_quote_text(sk_dir))
    return bool(_ns_inv) and _ns_pq in _ns_inv


# ── G-65b（2026-09-25）：省略号 ≠ 必然截断 ─────────────────────────────────────
# 实证（manias-crashes · lender-of-last-resort-protocol L74 · F-091）：源文 s318 原文
# 自身印着「已借出的资金会完全浪费......会有赞成无限授权的情况」（译本原样省略号）——
# 池引文与技能件引文逐字忠实，但 G-54 的「带省略号 ⇒ 截断」把这种**源内省略**误判为拼接。
# 修法＝把钝代理换成真判据：q 按 `……`/`......` 分段后，**每段都在整源拼接里逐字在场**
# （双侧先把「点串≥3」归一成单枚 …——源六点、技能……、……… 同归一）⇒ 源内省略，非截断；
# 任一段不在 ⇒ 真拼接/改写 ⇒ 照旧 TRUNC。**比原规则更严**（原来只看形状，现在真回源）。
_ELL_RUN = re.compile(r'\.{3,}|…+')


def _ellipsis_verbatim_in_source(q, concat_norm):
    """q 含省略号时：全部分段逐字回源 ⇒ True（源内省略，不算截断）；任一段不在 ⇒ False。"""
    if not concat_norm:
        return False
    _src = _ELL_RUN.sub('…', concat_norm)
    for seg in SEG_SPLIT.split(q):
        ns = _ELL_RUN.sub('…', VC.norm_match(seg))
        if not ns:
            continue
        if ns not in _src:
            return False
    return True


SB_MISSING_NAMES = []  # R1：缺 source_book 的件名（射程缩小必须可见且判红）


def main():
    global SB_MISSING_NAMES
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True,
                    help='任务 slug（书别参数一律从 .work/<slug>/bookspec-<slug>.json 读，不得写死）')
    ap.add_argument('--out', default=None)
    ap.add_argument('--json-out', default=None)
    # ⚠ 2026-09-24 新增（`G-24`）：池从"硬依赖"改为"**可显式给**"——
    #   `--pool` 接一件或一个通配；`--pool-glob` 接通配；两者都可不给（缺省仍读 `.work/<task>/verified.md`）。
    #   一个可用池都没有时**明写跳过**（不抛裸栈、不静默），并仍 rc=1（未检 ≠ 通过）。
    ap.add_argument('--pool', default=None,
                    help='池件路径或通配（可给多份：池格式＝`### <band>-NNN [类型] [技能=…]`＋`- 原文（逐字）：`）。'
                         '不给则读 `.work/<task>/verified.md`。')
    ap.add_argument('--pool-glob', default=None, help='池件的通配（如 `投资蒸馏/**/candidates/notes_*.md`）。')
    # ⚠ 2026-09-24 **G-45 已收敛**：首版拿 `verify_candidates.norm_match` 当尺子（与探针不同源）
    #   ⇒ `攻守可转债` 读数偏低 10 条；且前锚分支取错组号 ⇒ `黑天鹅` 崩溃。两处已修，
    #   现与独立探针**同一把尺子**（`verify_layer_quotes`）并逐数对齐 ⇒ **改回默认开启**。
    ap.add_argument('--no-source-filter', dest='src_filter', action='store_false', default=True,
                    help='关闭 source_book 过滤（**默认开**）：`--skills-dir` 指向共享技能根时，'
                         '只保留「该件 frontmatter 的 source_book 与本册 bookspec 的 book 相符」的技能；'
                         '否则会把别的册的引文抓来对本册源文核 ⇒ 假红（G-50）。')
    ap.add_argument('--skills-dir', default=None,
                    help='技能件扫描目录（默认 `.work/<task>/skills`）。'
                         '**判 §27 第 1 条时应指向交付路径（在役技能根）**——两代 sha 常不同（G-50）。')
    ap.add_argument('--allow-synth-pagemark', dest='allow_synth', action='store_true', default=False,
                    help='源页号被判为**合成**时仍按正常通过（**默认禁止**：合成页号下本层属构造性，rc=1；见 G-47）。')
    ap.add_argument('--alt', dest='alt', action='store_true', default=True,
                    help='同时核**第二种断言形态**：内联引文＋`〔…（pNN）〕`／`——pNN`／页区间（`G-21`，**不需池**）。'
                         '2026-09-24 起为**默认**（G-45 已收敛：与独立探针同一把尺子）。')
    ap.add_argument('--layer3', dest='layer3', action='store_true', default=False,
                    help='开启 **③ 技能件自证层**（用技能件自己写的引文核页，`G-51`）。'
                         '⚠ **仍未收敛**：第一类假阳性（两把尺子）已修 `G-53`；**第二类未修**——'
                         '它会把「标题式短语」当引文（`G-54`：guozhai `BOUNDARIES.md` 那种）⇒ **默认关**。'
                         '`G-65`（2026-09-25 · 乙案收口）：TRUNC 命中时先试**配对通道**——节引＝池内逐字连续子串'
                         '＋全量引文随技能件发行（invest.md）＋落页不豁免 ⇒ 记 `ALT3_PAIR_OK`（不算红，单列）。')
    ap.add_argument('--dump-asserts', default=None,
                    help='`G-51`/`G-55` dump-diff：把 ③ 层**实际断言集**（引文/自称页/分段/判态；'
                         'MISS 段附「整源落页」对照）导出为 JSON，供与手工复核集**逐条 diff**'
                         '（仪器化仪器）。**只增不改判读路径**。需配合 --layer3。')
    ap.add_argument('--no-alt', dest='alt', action='store_false',
                    help='只核 `（id sNNN）` 形态（用于与历史报告逐字对照）。')
    # 射程口径变更（2026-09-23 · 见 §17.4 口径变更登记单）：
    #   **附件层默认纳入射程**（原为 `action='store_true'`，默认只扫 SKILL.md）。
    #   依据：实测附件层占每册断言量的 **20%+**（manias 706→967、guozhai 1788→2061、qushi 589→762），
    #   默认不扫 ⇒ **附件层页锚从未回源**（且实测抓到 1 处真错锚 `BOUNDARIES.md` L90 → 已修）。
    #   前置条件已满足：`ONE` 的"紧邻配对"修正（形态 A 间隙不得跨右括号 ＋ 新增形态 B 锚→id），
    #   使 manias 含 aux 达 **967/967＝100%／rc=0**、guozhai **2061/2061＝100%／rc=0**，
    #   且 4 册回归**零变化**。⇒ 纳入射程**不新增任何假红**。
    ap.add_argument('--include-aux', dest='include_aux', action='store_true', default=True,
                    help='把**附件层**（skills/*/*.md：BOUNDARIES／GLOSSARY／INDEX／SUPPLEMENT 等）'
                         '一并纳入射程。**2026-09-23 起为默认**（口径变更）：附件文件里的'
                         '「（`id` sNN）」同样是对源文的**可核断言**，不纳入则附件层页锚**从未回源**。')
    ap.add_argument('--no-aux', dest='include_aux', action='store_false',
                    help='只扫 SKILL.md（保留旧口径，用于与历史报告逐字对照）。')
    a = ap.parse_args()
    work = os.path.join(ROOT, '.work', a.task)
    spec, spec_path = M.load_spec(a.task)
    # ① 源文件名：必须来自配置（旧版回落 'ocr_ds.txt' ＝ 上一册的文件名，属 A-74 特定化）
    src_name = spec.get('src')
    if not src_name:
        print('🔴 本册配置缺 `src`：%s —— 源文件名必须来自配置，拒绝运行（A-69／A-74）' % spec_path)
        return 1
    src = os.path.join(work, src_name)
    if not os.path.exists(src):
        print('🔴 配置指向的源文件不存在：%s（配置 %s）' % (src, spec_path))
        return 1
    # ② 页锚形态：必须来自配置（旧版写死 'equals' ＝ 上一册形态 ⇒ 换书后分页全错）
    #    `auto` 交给 verify_candidates 的**唯一权威探测函数**（不在本件另写一份，见 A-72 变体）
    pm = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
    if pm == 'auto':
        pm = VC.detect_pagemark(src)
    VC.set_pagemark(pm)
    print('页锚形态：%s（源＝%s；决议自 %s）' % (pm, src_name, os.path.basename(spec_path)))

    # 池内条目：id → (页锚, 逐字引文)
    # ⚠ 2026-09-24 **池改为可选**（闸缺陷台账 `G-24`）：旧版硬读 `.work/<slug>/verified.md` ⇒
    #   本册无池时抛 `FileNotFoundError`（rc=2，**看着像崩溃**），把"无池"与"产物有问题"混成一件事。
    #   现在：`--pool <件或通配>`／`--pool-glob <通配>` 显式给池，缺省仍读 `.work/<slug>/verified.md`；
    #   **一个可用池都没有 ⇒ 明写"跳过池内 id 这一层"，并 rc=1（未检不得当作通过）**。
    #   ⚠ 本件**随包发行** ⇒ 不许写任何册别兜底路径（A-74）：要核别的池，由调用方显式传参。
    pool, pool_src, n_skip = {}, [], 0
    _cands = []
    if a.pool:
        _cands += [a.pool] if os.path.isfile(a.pool) else sorted(glob.glob(a.pool))
    if a.pool_glob:
        _cands += sorted(glob.glob(a.pool_glob))
    _vw = os.path.join(work, 'verified.md')
    if os.path.isfile(_vw):
        _cands.append(_vw)
    for _pth in _cands:
        try:
            vt = io.open(_pth, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        _n0 = len(pool)
        for b in VC.SPLIT_ENTRY.split(vt):
            m = VC.ENTRY.match(b.split('\n')[0])
            if not m:
                continue
            eid = '%s-%s' % (m.group(1), m.group(2))
            an = VC.ANCHOR.search(b)
            q = VC.QUOTE.search(b)
            pages = [int(x) for x in re.findall(r'\d{1,4}', an.group(1))] if an else []
            pool[eid] = dict(pages=pages, quote=(q.group(1) if q else ''))
        if len(pool) > _n0:
            pool_src.append('%s（+%d 条）' % (os.path.relpath(_pth, ROOT), len(pool) - _n0))
    if pool:
        print('池：%d 条 ← %s' % (len(pool), '；'.join(pool_src)))
    else:
        print('池：**跳过**（未找到可用池件；本次**不检"池内 id 的引文是否落页"这一层**）'
              ' ⇒ 可传 `--pool <件|通配>` 或 `--pool-glob <通配>`（见闸缺陷台账 `G-24`）')
    _src_m, idx, order, _dup = M.build_page_index(src)
    _synth, _nblk, _nhit, _samp = detect_synth_pagemark(src)
    if _synth:
        print('⚠ **源页号疑似合成**：%d 个 `[PAGE N]` 块里 %d 个以「源节文件名」起头（例 `%s`）'
              % (_nblk, _nhit, _samp))
        print('   ⇒ 本册的「页」其实是**源节／片**；本层命中率**不得**当作「能点回**真实页**」的证据（G-47）。')


    pat = '*.md' if a.include_aux else 'SKILL.md'
    # ⚠ 跳过 `_` 开头的技能目录（备份/隔离区）——回改器的快照若误留在技能根内会被当成技能扫
    _sdir = a.skills_dir or os.path.join(work, 'skills')
    print('技能扫描目录：%s%s' % (os.path.relpath(_sdir, ROOT) if os.path.isdir(_sdir) else _sdir,
                                 '' if a.skills_dir else '（**默认＝.work 副本**；判第 1 条应按口径改传 `--skills-dir <在役技能根>`，见 G-50）'))
    _files_all = sorted(p for p in glob.glob(os.path.join(_sdir, '*', pat))
                   if not os.path.basename(os.path.dirname(p)).startswith('_'))
    # ── source_book 过滤（G-50）：共享技能根上必须只留**本册**的技能 ──
    _book = str(spec.get('book') or '')
    if a.src_filter and a.skills_dir and _files_all:
        _keep = []
        for _p in _files_all:
            _head = io.open(_p, encoding='utf-8', errors='replace').read(4000)
            _m = re.search(r'(?m)^\s*source_book\s*:\s*["\']?(.{0,120})', _head)
            _sb = _m.group(1) if _m else ''
            if not _sb:
                # R1（圆桌裁决 · 2026-09-25）：缺 source_book ⇒ 射程静默缩小，必须列名并判红
                SB_MISSING_NAMES.append(os.path.basename(os.path.dirname(_p)))
                continue
            if _book and (_book[:12] in _sb or _sb[:12] in _book):
                _keep.append(_p)
        if _keep:
            print('source_book 过滤：%d → **%d** 件（本册 book＝%s）' % (len(_files_all), len(_keep), _book[:28]))
            _files_all = _keep
        else:
            print('🔴 `--skills-dir` 已给，但 source_book 过滤后为 **0 件**（本册 book＝%s）⇒ **拒绝运行**：'
                  '继续跑就会把**别的册**的技能抓来对本册源文核（实测会出现上千条假 PAGE_MISS，G-50）。'
                  '请检查：① 该册技能件的 frontmatter 是否写全 `source_book`；② 或显式加 `--no-source-filter` 并自行承担射程。'
                  % _book[:28])
            return 2
    files = _files_all
    allrows = []
    n_ok = n_miss = n_net = n_idmiss = 0
    n_aok = n_amiss = 0        # 页锚直核（内联引文，G-21）
    n3ok = n3miss = n3skip = n3trunc = n3okstruct = n3pair = 0
    # ③ 层（G-51）；n3skip＝门槛跳过、n3trunc＝截断引文（G-54）、n3okstruct＝容差命中（G-55，不算红）、
    # n3pair＝配对可核（G-65 乙案收口 2026-09-25：节引⊆池·逐字连续子串＋invest.md 全量在场＋落页不豁免；不算红，单列）
    _idx3 = None               # 去换行归一化缓存（G-52）
    _alt_idx = None            # 页文本的 VLQ 归一化缓存（惰性建）
    _concat3 = None            # dump 用：整源按页序拼接（惰性建，只增不改判读）
    _bounds3 = None            # dump 用：页界表（偏移→页号）
    dump3 = []                 # dump 用：③ 层实际断言集（G-51/G-55 dump-diff）
    for f in files:
        slug = os.path.basename(os.path.dirname(f))
        if a.include_aux and os.path.basename(f) != 'SKILL.md':
            slug = '%s／%s' % (slug, os.path.basename(f))   # 附件层：报告按"件／文件"分组
        t = io.open(f, encoding='utf-8').read()
        rows = []
        for bm in BRACKET.finditer(t):
            block = bm.group(1)
            line = t[:bm.start()].count('\n') + 1
            # ⚠ 2026-09-17 **回退登记**（本册实测 · 我改错过一次，如实留痕）：
            #   技能正文里出现了「多个 id 共享一个页锚区间」的写法（`（`F-031`／…／`F-057` s117～s124）`），
            #   旧实现逐条配对 ⇒ 把紧邻区间的 id 单独配上区间起点，报 `PAGE_MISS`（假红）。
            #   我一度想给检查器加"共享区间断言"分支去迁就这种写法 —— **方向错了**：
            #   手册 §22.3 明写「页锚在写入时就必须是**一引用一锚**；**禁止**写入多引用块」，
            #   且这种写法**让"某条引文落在哪一页"不再可判定**。迁就它＝**放松尺子**（A-34），
            #   实测还会**打破别的册的回归**（manias 由 690/690 变成 691/695）。
            #   ⇒ **回退该分支**，改为**改产物**：把技能里的多引用块拆成「一引用一锚」。
            # 两种书写顺序**合并后按位置去重**（形态 A：id→锚；形态 B：锚→id）。
            #   两式都是**紧邻配对**，因此同一对不会重复计入，也不会跨组错配。
            _ms = []
            for m in ONE.finditer(block):
                _ms.append((m.start(), m.group(1), int(m.group(2)),
                            int(m.group(3)) if m.group(3) else None))
            for m in ONE_AF.finditer(block):
                _ms.append((m.start(), m.group(2), int(m.group(1)), None))
            _seen = set()
            for _st, eid, p0, _p1g in sorted(_ms, key=lambda x: x[0]):
                if (eid, _st) in _seen:
                    continue
                _seen.add((eid, _st))
                p1 = _p1g if _p1g else p0
                anchor = p0
                anchors = list(range(min(p0, p1), max(p0, p1) + 1))
                if not pool:
                    # 无池 ⇒ **不得**把"查不到"算成 ID_MISS（那是假红）；如实记 POOL_SKIP 并在结论里声明射程。
                    n_skip += 1
                    rows.append(dict(line=line, eid=eid, anchor=anchor, state='POOL_SKIP',
                                     detail='本册无可用池 ⇒ 本次未检该层（不是"池内无此 id"）'))
                    continue
                if eid not in pool:
                    n_idmiss += 1
                    rows.append(dict(line=line, eid=eid, anchor=anchor, state='ID_MISS', detail='池内无此 id'))
                    continue
                qn = VC.norm_match(pool[eid]['quote'])
                if not qn:
                    rows.append(dict(line=line, eid=eid, anchor=anchor, state='NO_QUOTE', detail='池内该条无引文'))
                    continue
                if any(qn in idx.get(pp, '') for pp in anchors):
                    n_ok += 1
                    rows.append(dict(line=line, eid=eid, anchor=anchor, state='PAGE_OK',
                                     detail=('区间 s%d-%d' % (p0, p1)) if p1 != p0 else ''))
                else:
                    # ⚠ 2026-09-17 修（本册实测 · **与合并器同一个盲区**，A-84 家族）：
                    #   旧实现只查"整条引文是否落在某一单页内"。**跨页引文**（起于 pN 末、续到 pN+1）
                    #   在**任何单页里都找不到整条** ⇒ 一律被报 `NET_MISS 全册找不到该引文`，
                    #   而它其实是**合法且常见**的（本册实测 16 条）。
                    #   修法（精确、无启发式）：把各页归一化文本**按页序拼接**，在拼接串里 `find`，
                    #   再用前缀长度和把起止偏移映射回页号 ⇒ 得 [起始页, 结束页]；
                    #   **自称页落在该区间内（或与之相邻）即 PAGE_OK**，否则报真实的跨页区间。
                    concat = ''.join(txt for _p, txt in order)
                    pos = concat.find(qn)
                    if pos >= 0:
                        bounds, acc = [], 0
                        for _p, txt in order:
                            bounds.append((acc, acc + len(txt), _p))
                            acc += len(txt)

                        def _page_at(off, _b=bounds):
                            for lo, hi, pp in _b:
                                if lo <= off < hi:
                                    return pp
                            return _b[-1][2]

                        sp, ep = _page_at(pos), _page_at(pos + len(qn) - 1)
                        idx_of = {pp: i for i, (pp, _t) in enumerate(order)}
                        near = abs(idx_of.get(ep, 0) - idx_of.get(sp, 0)) <= 1
                        if near and any(x in anchors for x in {sp, ep}):
                            n_ok += 1
                            rows.append(dict(line=line, eid=eid, anchor=anchor, state='PAGE_OK',
                                             detail='跨页 s%d→s%d（自称落在区间内，成立）' % (sp, ep)))
                        else:
                            n_miss += 1
                            rows.append(dict(line=line, eid=eid, anchor=anchor, state='PAGE_MISS',
                                             detail='引文实际跨 s%d→s%d（自称 %s）'
                                                    % (sp, ep, ('s%d-%d' % (p0, p1)) if p1 != p0 else 's%d' % p0)))
                        continue
                    hits = [p for p, txt in idx.items() if qn in txt]
                    if hits:
                        n_miss += 1
                        rows.append(dict(line=line, eid=eid, anchor=anchor, state='PAGE_MISS',
                                         detail='引文实际在 s%s（自称 %s）'
                                                % ('/s'.join(str(h) for h in hits),
                                                   ('s%d-%d' % (p0, p1)) if p1 != p0 else 's%d' % p0)))
                    else:
                        n_net += 1
                        rows.append(dict(line=line, eid=eid, anchor=anchor, state='NET_MISS',
                                         detail='全册找不到该引文（逐页拼接后仍无）'))
        allrows.append((slug, rows))
        # ── 第二种形态：页锚直核（内联引文；**不需池**）——`G-21` ──
        if a.alt:
            arows = []
            # 归一化器与分段**同一把尺子**（`verify_layer_quotes`）——与独立探针、与第三方判官所用口径一致；
            # ⚠ G-45 的成因就是"两把尺子"（首版用 `verify_candidates.norm_match`）⇒ 读数差 10 条。
            if _alt_idx is None:
                _alt_idx = {}
                for _pp, _tx in order:            # ⚠ **合并**重复页标记（与 idx 同口径，G-55）
                    _alt_idx[_pp] = (_alt_idx[_pp] + '\n' + VLQ.norm(_tx)) if _pp in _alt_idx else VLQ.norm(_tx)
            for q, pgs in alt_assertions(t):
                segs = VLQ.segments(q)
                if not segs:
                    continue
                body = ''.join(_alt_idx.get(pp, '') for pp in sorted(set(pgs)))
                nxt = _alt_idx.get(max(pgs) + 1, '') if pgs else ''
                miss_seg = [s for s in segs if s not in body and s not in (body + nxt)]
                if miss_seg:
                    n_amiss += 1
                    arows.append(dict(line=t[:max(0, t.find(q))].count('\n') + 1, eid='（内联引文）',
                                      anchor=(pgs[0] if pgs else 0), state='ALT_MISS',
                                      detail='引文未落在自称页 p%s（缺 %d/%d 段）' % (
                                          '/p'.join(str(p) for p in sorted(set(pgs))), len(miss_seg), len(segs))))
                else:
                    n_aok += 1
            if arows:
                allrows.append((slug + ' ｜页锚直核（内联引文）', arows))
        if a.alt and a.layer3:
            # ── ③ 层（`G-51`）—— **首版有假阳性，默认关（`G-53`）** ──
            if _alt_idx is None:
                _alt_idx = {}
                for _pp, _tx in order:            # ⚠ **合并**重复页标记（与 idx 同口径，G-55）
                    _alt_idx[_pp] = (_alt_idx[_pp] + '\n' + VLQ.norm(_tx)) if _pp in _alt_idx else VLQ.norm(_tx)
            if _idx3 is None:
                # 页文本已由 build_page_index 走 `VC.norm_match`（折空白＋标点族）⇒ 引文必须同一把尺子（G-53 收敛）
                _idx3 = {}
                for _pp, _tx in order:            # ⚠ 同上：**合并**而不是覆盖（G-55）
                    _idx3[_pp] = (_idx3[_pp] + '\n' + _tx) if _pp in _idx3 else _tx
            if _concat3 is None:
                # dump 用（G-55 dump-diff · **只增不改判读**）：整源按页序拼接（与 ① 层跨页修法同一构造）＋页界表
                _concat3 = ''.join(_tx for _pp, _tx in order)
                _bounds3, _acc3 = [], 0
                for _pp, _tx in order:
                    _bounds3.append((_acc3, _acc3 + len(_tx), _pp))
                    _acc3 += len(_tx)
            arows3 = []
            for q, pgs, _off, _eid in assertions3(t):
                _ln3 = t[:_off].count('\n') + 1     # ⚠ 现算行号（首版套用了外层 line ⇒ 全报同一行）
                # ── 前置门槛（G-54）：先问「这段文字到底是不是引文」──
                _nq = VC.norm_match(q)
                _pq = ''
                _trunc = False
                _pair_ok = False
                if _eid and _eid in pool:
                    _pq = VC.norm_match(pool[_eid]['quote'])
                    if not _pq:
                        n3skip += 1
                        continue
                    _lcp = 0
                    for _a, _b in zip(_nq, _pq):
                        if _a != _b:
                            break
                        _lcp += 1
                    if _lcp < 12 and _nq not in _pq and _pq not in _nq:
                        n3skip += 1
                        continue                     # 标题／术语／非该 id 的引文 ⇒ 跳过，不算红
                    # 截断判定（`G-54` 二轮）：明显更短 或 带省略号 ⇒ 引文不完整 ⇒ 记 ALT3_TRUNC（算红）
                    if ('…' in q) or (len(_nq) + 4 < len(_pq) * 0.9):
                        # G-65b：源内省略甄别——q 含 … 时先做分段回源，段段在场 ⇒ 非截断（见 _ellipsis_verbatim_in_source）
                        _ell_ok = False
                        if '…' in q:
                            if _concat3 is None:
                                _concat3 = ''.join(_tx for _pp, _tx in order)
                                _bounds3, _acc3 = [], 0
                                for _pp, _tx in order:
                                    _bounds3.append((_acc3, _acc3 + len(_tx), _pp))
                                    _acc3 += len(_tx)
                            _ell_ok = _ellipsis_verbatim_in_source(q, VC.norm_match(_concat3))
                        if (not _ell_ok) or (len(_nq) + 4 < len(_pq) * 0.9):
                            _trunc = True
                            # G-65 配对通道：TRUNC 命中时先试配对资格（P1⊆池逐字连续 ＋ P2≥20 字 ＋ P3 invest.md 全量在场）
                            _pair_ok = _pair_eligible(q, _nq, pool[_eid]['quote'], os.path.dirname(f))
                else:
                    if len(_nq) < 24 or not re.search(r'[。，；：！？]', _nq):
                        n3skip += 1
                        continue                     # 无池可依时的弱门槛：太短或没有句读 ⇒ 跳过
                segs = [s for s in SEG_SPLIT.split(q) if len(VC.norm_match(s)) >= 8]
                if not segs:
                    continue
                body = ''.join(_idx3.get(pp, '') for pp in sorted(set(pgs)))
                nxt = _idx3.get(max(pgs) + 1, '') if pgs else ''
                miss = [s for s in segs
                        if VC.norm_match(s) not in body and VC.norm_match(s) not in (body + nxt)]
                # ── 容差复判（`G-51`/`G-55` dump-diff 定位后的修法 · 2026-09-24）──────────
                #   `jingji` 13 条 MISS 逐条归因（dump 每段记「整源落页」后二分定位）：
                #   10 条＝技能件**逐词与源一致**但句尾标点被替换（源「，／；／（见图4-5）」⇒ 答「。」）
                #        或源侧夹脚注号；2 条＝页标记嵌句／脚注伪影；1 条＝跨页断句——
                #   仪器尺 norm_match **保留句读** ⇒ 全部假红；②层用 VLQ.norm（删标点）故同批只报 2
                #   ⇒ 这正是 `G-51` 当初「两把尺子」在**同一工具内部**的复现。
                #   修法＝MISS 段先**整删标点**（单一来源 `_qnorm.norm_strip`）再 containment；
                #   命中 ⇒ 记 **ALT3_OK_STRUCT**（不算红，但**单列不并入 OK**——松尺不静默，A-34）。
                _struct_hit = False
                if miss and not _trunc:
                    _b2, _bn2 = norm_strip(body), norm_strip(body + nxt)
                    if all(norm_strip(s) in _b2 or norm_strip(s) in _bn2 for s in miss):
                        _struct_hit = True
                # ── dump-diff 采集（`G-51`/`G-55` · **只增不改判读**）：
                #    每条断言记 引文/自称页/分段/判态；MISS 段另记「整源按页序拼接里能否找到、落在哪几页」
                #    ⇒ 与手工复核集逐条 diff，定位"仪器 13 条 vs 人工 0 条"到底是谁多出来的。
                if a.dump_asserts:
                    _segs_rec = []
                    _miss_norm = set(VC.norm_match(s) for s in miss)
                    for _s in segs:
                        _sn = VC.norm_match(_s)
                        _rec = {'seg': _sn[:60], 'len': len(_sn),
                                'in_claimed': bool(_sn in body or _sn in (body + nxt))}
                        if _sn in _miss_norm:
                            _pos = _concat3.find(_sn)
                            _rec['in_whole'] = _pos >= 0
                            if _pos >= 0:
                                _span, _found = set(), []
                                for _lo, _hi, _pp in _bounds3:
                                    if _pos < _hi and _pos + len(_sn) > _lo and _pp not in _span:
                                        _span.add(_pp)
                                        _found.append(_pp)
                                _rec['found_pages'] = _found
                            else:
                                _rec['found_pages'] = []
                        _segs_rec.append(_rec)
                    dump3.append(dict(file=slug, line=_ln3, eid=(_eid or ''),
                                      pages=sorted(set(pgs)), quote=q[:120], nq_len=len(_nq),
                                      pool_len=(len(_pq) if _pq else None),
                                      verdict=('ALT3_TRUNC' if (_trunc and not _pair_ok)
                                               else ('ALT3_PAIR_OK' if _pair_ok
                                                     else ('ALT3_OK_STRUCT' if _struct_hit
                                                           else ('ALT3_MISS' if miss else 'ALT3_OK')))),
                                      n_seg=len(segs), segs=_segs_rec))
                if _trunc and not _pair_ok:
                    n3trunc += 1
                    arows3.append(dict(line=_ln3, eid='（技能件自证）', anchor=(pgs[0] if pgs else 0),
                                       state='ALT3_TRUNC',
                                       detail='技能件写的是**截断引文**（自带省略号或明显短于池内引文）⇒ 不可逐字回源'
                                              '（池内该 id 引文 %d 字，技能件这段 %d 字）' % (len(_pq), len(_nq))))
                    continue
                if _struct_hit:
                    n3okstruct += 1
                    arows3.append(dict(line=_ln3, eid='（技能件自证）', anchor=(pgs[0] if pgs else 0),
                                       state='ALT3_OK_STRUCT',
                                       detail='容差命中：逐词与源一致，仅句尾标点被替换／源夹脚注号·页标记'
                                              '（仪器尺假红；dump-diff 定位见 `G-55`）——不算红，单列不并入 OK'))
                    continue
                if miss:
                    n3miss += 1
                    arows3.append(dict(line=_ln3, eid='（技能件自证）', anchor=(pgs[0] if pgs else 0),
                                       state='ALT3_MISS',
                                       detail='技能件写的引文未落在自称页 p%s（缺 %d/%d 段；可能是截断/改写，也可能是源侧断行）'
                                              % ('/p'.join(str(p) for p in sorted(set(pgs))), len(miss), len(segs))))
                elif _pair_ok:
                    n3pair += 1
                    arows3.append(dict(line=_ln3, eid='（技能件自证）', anchor=(pgs[0] if pgs else 0),
                                       state='ALT3_PAIR_OK',
                                       detail='配对可核（`G-65` 乙案）：节引＝池内逐字连续子串（norm %d 字）＋全量引文'
                                              '（%d 字）已随技能件发行（invest.md 逐字在场）＋落页命中——单列不并入 OK（A-34）'
                                              % (len(_nq), len(_pq))))
                else:
                    n3ok += 1
            if arows3:
                allrows.append((slug + ' ｜技能件自证（G-51）', arows3))

    total = n_ok + n_miss + n_net + n_idmiss + n_skip
    L = ['# rquote 逐字 ＋ **页码定位** 机器层（执行单 #10）', '',
         '> 任务 `%s` ｜ 源 `%s`（%d 页）｜ **技能扫描目录** `%s`%s｜ 判据见本报告同目录脚本 `tools\\rquote_page_check.py` docstring'
         % (a.task, os.path.basename(src), len(idx),
            os.path.relpath(_sdir, ROOT) if os.path.isdir(_sdir) else _sdir,
            '' if a.skills_dir else '（默认＝.work 副本；判第 1 条应按口径传 `--skills-dir`，见 G-50）'),
         '> 口径：技能正文里每处「（`id` sNNN）」＝一条**可核断言**；取池内该 id 的逐字引文，'
         '查它是否真的落在自称的那一页。',
         '> ⚠ **源页号疑似合成**（页块＝源节／片，无真实书页号）⇒ **本报告不得作为「能点回真实页」的证据**（G-47）。'
         if _synth else '',
         '> **射程（本次实况）**：① `（id sNNN）` 层＝池 **%s**%s；② 页锚直核（内联引文）层＝%s' % (('%d 条' % len(pool)) if pool else '**缺失 ⇒ 该层未检**',
                                                  '' if pool else '（`POOL_SKIP %d` 条**未被检查**，'
                                                                  '**不得**读成"通过"；见闸缺陷台账 `G-24`／`G-41`）' % n_skip,
                                                  ('**已开**（`--no-alt` 可关）' if a.alt else '**关闭**（`--no-alt`）')), '',
         '## 一、总计', '',
         '| 态 | 条数 | 含义 |', '|---|---|---|',
         '| `PAGE_OK` | **%d** | 引文在自称页内逐字命中 ✔ |' % n_ok,
         '| `PAGE_MISS` | %d | 引文在**别的页**命中 ⇒ 🔴 错锚 |' % n_miss,
         '| `NET_MISS` | %d | 全册找不到 ⇒ 🔴 无锚 |' % n_net,
         '| `ID_MISS` | %d | 引用的候选 id 池内不存在 ⇒ 🔴 |' % n_idmiss,
         '| `POOL_SKIP` | %d | **本册无池 ⇒ 该层未检**（不是"池内无此 id"） |' % n_skip,
         '| `ALT_OK` | **%d** | **页锚直核**：内联引文在自称页逐字命中 ✔（不需池） |' % n_aok,
         '| `ALT_MISS` | %d | **页锚直核**：内联引文不在自称页 ⇒ 🔴 |' % n_amiss,
         '| `ALT3_OK` | **%d** | **技能件自证层**：技能件自己写的引文落在自称页 ✔ |' % n3ok,
         '| `ALT3_OK_STRUCT` | %d | ③ 层**容差命中**：逐词与源一致，仅句尾标点被替换／源夹脚注号·页标记 '
         '（`G-55` dump-diff 定位的仪器尺假红）——**不算红**，单列不并入 OK（松尺不静默，A-34） |' % n3okstruct,
         '| `ALT3_MISS` | %d | **技能件自证层**：技能件自己写的引文不在自称页 ⇒ 🔴（截断/改写／错锚） |' % n3miss,
         '| `ALT3_TRUNC` | %d | ③ 层：技能件写的是**截断引文**（省略号／明显短于池内引文）⇒ 不可逐字回源 ⇒ 🔴 |' % n3trunc,
         '| `ALT3_PAIR_OK` | **%d** | ③ 层**配对可核**（`G-65` 乙案）：节引＝池内逐字连续子串＋全量引文随技能件发行'
         '（invest.md 逐字在场）＋落页命中——**不算红**，单列不并入 OK（A-34） |' % n3pair,
         '| `ALT3_SKIP` | %d | ③ 层**门槛跳过**（与池内引文无 ≥12 字公共前缀 ⇒ 判为标题·术语·非引文，`G-54`） |' % n3skip,
         '| **合计断言** | **%d** | 各栏之和＝总数（当场可核） |' % total, '']
    if total and pool:
        L += ['**① `（id sNNN）` 层命中率 ＝ %d/%d ＝ %.2f%%**' % (n_ok, total, 100.0 * n_ok / total), '']
    if n_aok + n_amiss:
        L += ['**② 页锚直核层命中率 ＝ %d/%d ＝ %.2f%%**（内联引文，不需池）'
              % (n_aok, n_aok + n_amiss, 100.0 * n_aok / (n_aok + n_amiss)), '']
    if not pool:
        L += ['🔴 **本册无可用池** ⇒ 本次**无法给出命中率**（`POOL_SKIP %d` 条）——'
              '补池或传 `--pool`／`--pool-glob` 后重跑；**这一格不得记为通过**。' % n_skip, '']
    for slug, rows in allrows:
        bad = [r for r in rows if r['state'] not in ('PAGE_OK',)]
        L += ['## %s' % slug, '',
              '- 断言 %d 条 ｜ 异常 %d 条' % (len(rows), len(bad))]
        if bad:
            L += ['', '| 行 | id | 自称页 | 态 | 明细 |', '|---|---|---|---|---|']
            for r in bad:
                L.append('| L%d | `%s` | s%d | %s | %s |' % (r['line'], r['eid'], r['anchor'], r['state'], r['detail']))
        L.append('')
    out = a.out or os.path.join(work, 'rquote-check.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    if a.json_out:
        io.open(a.json_out, 'w', encoding='utf-8', newline='\n').write(
            json.dumps(dict(total=total, page_ok=n_ok, page_miss=n_miss, net_miss=n_net,
                            id_miss=n_idmiss, rows={s: r for s, r in allrows}),
                       ensure_ascii=False, indent=1) + '\n')
    if a.dump_asserts:
        io.open(a.dump_asserts, 'w', encoding='utf-8', newline='\n').write(
            json.dumps(dict(task=a.task,
                            layer3=dict(ok=n3ok, miss=n3miss, trunc=n3trunc, skip=n3skip,
                                        ok_struct=n3okstruct, pair_ok=n3pair),
                            asserts=dump3), ensure_ascii=False, indent=1) + '\n')
        print('③ 层断言集已导出（G-51/G-55 dump-diff）：%s（%d 条，其中 MISS %d）'
              % (a.dump_asserts, len(dump3), n3miss))
    print('① （id sNNN）层：断言 %d ｜ PAGE_OK %d ｜ PAGE_MISS %d ｜ NET_MISS %d ｜ ID_MISS %d ｜ POOL_SKIP %d'
          % (total, n_ok, n_miss, n_net, n_idmiss, n_skip))
    print('② 页锚直核层：断言 %d ｜ ALT_OK %d ｜ ALT_MISS %d%s'
          % (n_aok + n_amiss, n_aok, n_amiss, '' if a.alt else '（本次 --no-alt 关闭）'))
    print('③ 技能件自证层：断言 %d ｜ OK %d ｜ 配对 %d ｜ 容差命中 %d ｜ MISS %d ｜ 截断 %d ｜ 门槛跳过 %d%s'
          % (n3ok + n3pair + n3miss + n3trunc + n3okstruct, n3ok, n3pair, n3okstruct, n3miss, n3trunc, n3skip,
             '' if a.alt and a.layer3 else '（本次未开 ③ 层）'))
    if pool and total:
        print('① 命中率 %.2f%%  ⇒ %s' % (100.0 * n_ok / total,
                                        '✔ 100%' if (n_miss + n_net + n_idmiss) == 0 else '🔴 有异常'))
    elif not pool:
        print('① 本册无可用池 ⇒ **该层未检**（POOL_SKIP %d）—— 不得记为通过（G-24／G-41）' % n_skip)
    if n_aok + n_amiss:
        print('② 命中率 %.2f%%  ⇒ %s' % (100.0 * n_aok / (n_aok + n_amiss),
                                        '✔ 100%' if n_amiss == 0 else '🔴 有异常（见报告）'))
    _red = (n_miss + n_net + n_idmiss) + n_amiss + n3miss + n3trunc
    _any = total + n_aok + n_amiss + n3ok + n3pair + n3miss + n3trunc
    if not _any:
        print('🔴 两层都**没有任何断言**可核 ⇒ 不得记为通过（可能：形态不在射程内／件里没有断言）')
    elif _red == 0:
        print('⇒ ✔ 本次射程内无异常（**射程见报告首段**；不等于 §27 第 1 条整条通过）')
    print('报告：%s' % out)
    if _synth and not a.allow_synth:
        print('🔴 源页号系**合成**（页＝源节／片）⇒ 本层属**构造性**，**不得**当作「能点回真实页」的证据（G-47）；'
              '确需内部对照可加 `--allow-synth-pagemark`。')
        return 1
    return 0 if (_red == 0 and _any) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
