# -*- coding: utf-8 -*-
r"""verify_candidates.py —— 候选池**机器校验**（阶段1.5 机械层 · ¥0 确定性）

校验对象：官方模板格式的提取笔记（`candidates/notes_<band>.md`）
校验项（逐条）：
  ① 条目格式行是否合规：`### <band>-NNN  [类型] [技能=…]`
  ② 是否含「锚」行与「原文（逐字）」行
  ③ **引文是否真的在源文件里**（去空白后 Contains —— 与提取器口径一致）
  ④ 引文长度是否 ≤160 字（模板「引文硬纪律 1」）
  ⑤ 引文是否误引了页标记（`--- [bark p242] ---` 这类不算原文）

用法：
  python tools\verify_candidates.py --notes <notes_T2.md> --src <源文件.txt>
  python tools\verify_candidates.py --all            # 扫 candidates/ 全部并自动配 source/
退出码：0 = 全过；1 = 有不合格项
"""
import argparse, glob, io, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
import _bandid as BID  # noqa: E402  ← 波段 id 语法的**唯一来源**（A-132）
WORK = None                    # 由 main() 依 --task 设定 —— **不留任何册别兜底值**（A-74）
# ⚠ 自伤登记（2026-09-19 脱敏批 · 当场被门禁抓到）：下面两行原为 `os.path.join(WORK, …)`，
#   把 WORK 改成 None 后 ⇒ **模块级 `join(None, …)` 在 import 时就抛 TypeError**
#   ⇒ 任何 `import verify_candidates` 的工具（通用引文闸等）**统统崩**（表现为 rc=2 ＋ 裸栈）。
#   **教训：拿掉"兜底值"时要连同"由它派生的模块级常量"一起处理** ——
#   改一个常量不是改一个字符串，是改它的**依赖闭包**（同 A-132：只改一处＝没改）。
CAND = None                    # 同上（main() 里按 --task 重算）
SRCD = None                    # 同上（main() 里按 --task 重算）

# 格式行：模板规定为 `### {band}-NNN  [类型] [技能=建议]`。
# 放宽（2026-09-13 实测登记）：允许 `[技能=…]` 后再跟说明文字——T5 有 21 条 CAM 条目写作
# `### T5-029  [CE] [技能=S3] 饮食疗法（总评）`。它**不影响 id/类型/技能的机械解析**，
# 故分两档：**完全无法解析＝🔴**；**可解析但有尾部说明＝▲（格式偏离，登记而非阻断）**。
#
# ⚠⚠ 本判据的历史＝**同一处被"修"四次、每次都修坏另一种形态**（A-132，2026-09-19 定案）：
#   ① 原写 `[A-Za-z]\d+`（字母后必须跟数字）→ 只吃旧册 `T1-001`，**纯字母波段 `A-001` 恒不命中**；
#   ② 改成 `[A-Za-z]\d*` → 仍吃不到双字母前缀 `ST-001`；
#   ③ 再改成 `[A-Za-z]+` → **吃不到「字母＋数字」波段 `E1-001`/`T1-001`**（NAS 册 `<task>`
#      波段名恰是 `E1..E6` ⇒ 本脚本对**完全合规**的 `notes_E1..E6.md` 报
#      🔴「切块为空：条目正则未命中任何块（工装缺陷，不得视为通过）」——**假红**，
#      而同一册在 `gate_stage` 的格式判据（当时已是 `[A-Za-z][0-9]*`）下却是绿的 ⇒
#      **一手绿一手红**，判决取决于"用哪把尺子"）；
#   ④ 而同期 `tools\_bandid.py` 定案前，全工作台 16 处各写一遍、共 4 种残缺写法。
#   **现一律取自 `_bandid`（单一真源）**：`BAND=[A-Za-z][A-Za-z0-9]*` 同时覆盖
#   `A`／`T1`／`E1`／`ST`／`B12`。**教训（A-07 第 9 形态）**：判据只在一处"放宽一点"必然
#   在另一形态上收紧；**正确做法是把该形态的完整语法写在一处，别处全部引用它**。
ENTRY = BID.ENTRY
SPLIT_ENTRY = BID.SPLIT        # ← 必须 re.M，否则 ^ 不匹配行首（实测踩过：切块为空⇒校验静默假通过）

# 标签容错（2026-09-19 · NAS 实测）：等价写法（半角冒号／「逐字原文」「原文」）**不得**被判"切块为空"。
#   实质判据不变：引文仍必须**逐字**出现在源文中（只放宽"标签名/冒号形态"，不放松来源校验）。
QUOTE = re.compile(r"^-\s*(?:原文（逐字）|原文\(逐字\)|逐字原文|原文)\s*[：:]\s*[「“\"](.+?)[」”\"]\s*$", re.M)
# 标签容错：`锚`／`页锚`／`出处` 等价（同上，只放宽标签名与冒号形态）。
ANCHOR = re.compile(r"^-\s*(?:页锚|锚|出处)\s*[：:]\s*(.+)$", re.M)
# 口径修正（2026-09-13 阶段1.5 实测抓到 ⇒ 登记 A-30）：源文实际页标记形如
# `--- [bark PDF p84] ---`（书代号 + PDF + 页号）。原正则 `[a-z]+\s*p\d+` 中间的
# `p\d+` 要求紧跟 `[a-z]+`，被 "PDF " 挡开 ⇒ **全程零命中**，两个后果：
#   ① 「引文误引页标记」这项检查**从未生效**（假通过）；
#   ② `clean_src` 的页标记剔除**从未生效**（跨页引文会假报「回源未命中」）。
# 修法：不猜书代号格式，按结构匹配 `[...]`。
PAGEMARK = re.compile(r"---\s*\[[^\]]*\]\s*---")

# ── 通用化（2026-09-17 · <task> 实测）──────────────────────────────────
# 原实现把 WORK 写死为 <task>、页标记写死为 `--- [bark PDF p84] ---` 形态 ⇒ **换书即报废**（A-01 同族）。
# 现支持三种页标记形态（`--pagemark` 选择，默认 auto）：
#   dash   : `--- [bark PDF p84] ---`          （<task>／投资线旧册）
#   equals : `===== [PAGE 84] =====`           （`ocr_pages.py` / `build_ocr_text.py` 产物）
#   hline  : `[p84]` **独占一行**                （`pdf_to_text.py` 产物 ⇒ 文字版 PDF 免 OCR 册，2026-09-17 新增）
#   ⚠ hline 必须锚定"整行"（行首行尾），否则正文里的 `[p84]` 字样会被误当页标记（A-57 同族：形态必须写准）。
PAGEMARK_FORMS = {
    'dash':   r"---\s*\[[^\]]*\]\s*---",
    'equals': r"=====\s*\[PAGE\s*\d+\]\s*=====",
    'hline':  r"(?m)^\[p\d+\][ \t]*$",
}
PAGEMARK_MARK_FORMS = {
    # 从标记里取出"页标识"文本（供页锚三态比对）
    'dash':   r"---\s*\[([^\]]*)\]\s*---",
    'equals': r"=====\s*\[PAGE\s*(\d+)\]\s*=====",
    'hline':  r"(?m)^\[p(\d+)\][ \t]*$",
}
CUR_FORM = 'dash'          # 由 main() 依据 --pagemark 覆盖


def set_pagemark(form):
    """切换页标记口径（并在模块级重绑 PAGEMARK / PAGEMARK_ANY / PAGEMARK_ANY_MARK）。"""
    global CUR_FORM, PAGEMARK, PAGEMARK_ANY, PAGEMARK_ANY_MARK
    CUR_FORM = form
    PAGEMARK = re.compile(PAGEMARK_FORMS[form])
    PAGEMARK_ANY = PAGEMARK
    PAGEMARK_ANY_MARK = re.compile(PAGEMARK_MARK_FORMS[form])


PAGEMARK_ANY_MARK = re.compile(PAGEMARK_MARK_FORMS[CUR_FORM])


def detect_pagemark(path):
    """以**实际源文件**探测页标记形态 —— **唯一权威口径**（`main()` 与套件其它仪器共用）。

    判据顺序：`===== [PAGE n] =====` ⇒ `equals`；行首 `[pn]` **独占一行** ⇒ `hline`；否则 `dash`。
    为什么抽成函数（2026-09-17 修）：`tools\\rquote_page_check.py` 曾自己写死 `equals`（上一册形态），
    换书后分页全错；若在这里再写一份探测逻辑，就又是「同一判据写两遍＝改一处等于没改」（A-72 变体）。
    **不得凭推断**——格式类判据须先做形态普查（A-29 家族）。
    """
    head = io.open(path, encoding="utf-8", errors="replace").read(200000)
    if '===== [PAGE ' in head:
        return 'equals'
    if re.search(r"(?m)^\[p\d+\][ \t]*$", head):
        return 'hline'
    return 'dash'


def norm(s):
    return re.sub(r"\s+", "", s)


# ── 源文件决议：**唯一一份**（探测与逐文件校验共用）· A-133 ────────────────────────
# 为什么必须抽成一个函数（NAS 真机实测）：原实现有**两套**决议规则 ——
#   探测页标记形态用「候选名优先」（`book_text.md` 排第一，正确）；
#   逐文件校验却用「<work>/*.txt|md 里 mtime 最新者」⇒ 实际决议到 **`DIGEST.md`**
#   （任务自己的产出文档，最新修改）⇒ **6 波段 236 条引文 100% 报"回源未命中"**。
#   症状极具误导性：既不像"产出错"也不像"仪器坏"，只是"每条都不合格"。
# 现规则（四级，逐级打印依据，**不静默降级** —— A-70 家族）：
#   ① `--src` 显式；② `bookspec-<task>.json` 的 `src`；③ `<work>/notes/source/<band>-*.{txt,md}`；
#   ④ <work> 下的**候选名优先**列表（book_text / ocr_ds / source / 整书 md）；
#   ⑤ 最后才"最新修改"兜底，**但必须通过内容闸**：文件里真的有页标记（真实源文一定分页）。
#      ⇒ 产出型文档（DIGEST.md／POOL_INDEX.md／judge-*.md…）自然被排除（与书、与目录名无关）。
_SRC_NAME_PRIORITY = ['book_text.md', 'book_text.txt', 'ocr_ds.txt', 'ocr_ds.md',
                      'ocr.txt', 'source.md', 'source.txt']
# 兜底排除：本工作台自己的**产物**（按文件名前缀/形态，与具体书名无关）
_OUTPUTISH = re.compile(r'^(DIGEST|POOL_INDEX|verified|执行单|口径登记单|PIPELINE_STATE|BOOK_OVERVIEW|'
                        r'CONSTRUCTION_SPEC|BOUNDARIES|GLOSSARY|INDEX|构造自查|蒸馏记录|freeze-fingerprint|'
                        r'polish-scan|route-overlap|rquote-check|layer-quotes|defense3|engine-visibility|'
                        r'fair-regression|gates-|judge-|blind|blindtest|d8-|candidates-machine|anchor-value)')


def _has_pagemarks(path):
    """内容闸：该文件是否**真的含页标记**（三种形态任一种，≥2 处）。

    为什么用"内容"而不是"文件名黑名单"：文件名黑名单必然漏（本工作台每天新增产物名），
    而"真实源文一定分页"是**书无关的硬性质**（`A-29` 家族：格式类判据要用该形态的固有性质）。
    """
    try:
        t = io.open(path, encoding='utf-8', errors='replace').read(400000)
    except Exception:
        return False
    n = len(re.findall(PAGEMARK_FORMS['dash'], t)) + len(re.findall(PAGEMARK_FORMS['equals'], t)) \
        + len(re.findall(PAGEMARK_FORMS['hline'], t))
    return n >= 2


def _bookspec_src(task, cli_src=None):
    """决议 ①/②：`--src` → `bookspec-<task>.json` 的 `src`。返回 (路径 or None, 依据说明)。"""
    if cli_src:
        return cli_src, '（--src 显式给定）'
    spec_p = os.path.join(WORK, 'bookspec-%s.json' % task)
    if not os.path.exists(spec_p):
        return None, '（无 bookspec：未声明源）'
    try:
        p = os.path.join(WORK, json.load(io.open(spec_p, encoding='utf-8'))['src'])
        note = '（bookspec-%s.json）' % task
    except Exception as e:
        # ⚠ 2026-09-17 实测抓到：此处原先 `except Exception: explicit_src = None` **静默吞异常**，
        #   而真实故障是**模块顶部漏了 `import json`**（NameError 被吞）⇒ 配置读取**永远失败**、
        #   却看起来像"没配 bookspec"（**静默降级**，A-70 同族：解析失败必须响亮）。
        print("⚠ bookspec-%s.json 解析失败 ⇒ 源文件改走兜底路径。异常：%s: %s"
              % (task, type(e).__name__, e))
        return None, '（bookspec 读取失败，已降级）'
    if not os.path.exists(p):
        print("⚠ bookspec 声明的源不存在：%s ⇒ 改走兜底路径" % p)
        return None, '（bookspec 源缺失，已降级）'
    return p, note


def _fallback_src(exclude_basename, task):
    """决议 ④/⑤：名字优先 → 最新修改（**必须过内容闸**）。返回路径或 None（带诊断打印）。"""
    for nm in _SRC_NAME_PRIORITY:
        p = os.path.join(WORK, nm)
        if os.path.exists(p):
            return p
    pool = []
    for p in (glob.glob(os.path.join(WORK, "*.txt")) + glob.glob(os.path.join(WORK, "*.md"))):
        b = os.path.basename(p)
        if b == exclude_basename or '.bak' in b or _OUTPUTISH.match(b):
            continue
        pool.append(p)
    pool.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for p in pool:
        if _has_pagemarks(p):
            return p
    # 一个都不合格 ⇒ **响亮地说清楚**，不静默（A-70）／不静默挑一个"看起来像"的（A-45）
    if pool:
        print("🔴 兜底源候选 %d 个，但**没有一个含页标记**（真实源文一定分页）⇒ 拒用。" % len(pool))
        print("   候选（按 mtime 新→旧）：%s" % "、".join(os.path.basename(x) for x in pool[:6]))
        print("   处置：加 `--src <源文路径>`，或建 `<work>/bookspec-%s.json` 声明 `src`（推荐）。" % task)
    return None


# ── 标点族归一（2026-09-17 <task> 实测必需）─────────────────────────────
# 为什么必须做：提取器把源文的**中文弯引号**「“审判日”」转写成了**直引号**「"审判日"」，
#   而两串除引号字形外**逐字相同** ⇒ 旧口径判"回源未命中"。实测：波段 A 41 条、F 7 条、
#   B 1 条全属此类（**假红**：引文本身是对的，是尺子把字形当内容）。
# 依据：套件自己的纪律早就要求这一步 —— 《蒸馏工程避坑手册》§22.2 第 3 条：
#   「归一化族必须齐全：『』／“”／「」、全/半角括号、空白、markdown 强调符 一律先归一再比对」。
# 口径（**只用于"引文 ↔ 源文"的比对**，不改写任何产物文本）：
#   ① 引号族统一为 ASCII `"`／`'`（含中文弯引号、直角引号、全角引号）；
#   ② 破折号/连字符族统一为 `-`；
#   ③ 省略号族统一为 `...`。
# 方向性：只做**等价类折叠**（同类异形视为同字符），不删除任何实义字符 ⇒ 不会把"不同的话"判成相同。
_QUOTE_MAP = {
    '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u201f': '"',
    '\u300c': '"', '\u300d': '"', '\u300e': '"', '\u300f': '"',
    '\u2033': '"', '\uff02': '"', '\u00ab': '"', '\u00bb': '"',
    '\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201b': "'",
    '\u3008': "'", '\u3009': "'", '\u2032': "'", '\uff07': "'",
    '\u2014': '-', '\u2013': '-', '\u2012': '-', '\u2015': '-',
    '\uff0d': '-', '\u2212': '-', '\u301c': '-', '\uff5e': '-', '\u007e': '-',
    '\u2026': '...', '\u22ef': '...',
}
_PUNCT_TABLE = {ord(k): v for k, v in _QUOTE_MAP.items()}


def norm_match(s):
    """比对口径的归一化：空白折叠 ＋ **标点族折叠**（见上方口径说明）。"""
    return norm(s.translate(_PUNCT_TABLE))


# 口径修正（P-23 工装伪影优先 · 实测抓到）：引文**跨页**时，源文在页与页之间夹着
# `--- [bark p91] ---`（页标记）与其后紧跟的页眉（如 `76如何养育多动症孩子`）。
# 提取器正确跳过了它们（模板「引文硬纪律 1」禁止引锚行/文件头），而首版校验器直接
# norm(源文) 比对 ⇒ 跨页引文一律**假报"回源未命中"**（实测：T1-006、T3-042）。
# 修法：比对前先从源文剔除【页标记】与【页标记后紧跟的"页码+书名"页眉行】。
PAGEMARK_ANY = PAGEMARK      # 同一口径（结构匹配，不猜书代号格式 —— 见上方 A-30）
# 页眉：页标记**之后紧跟**的「页码 + 书名」行（如 `70 如何养育多动症孩子`）。
HEADER_LINE = re.compile(r"^[ \t]*\d{1,4}[ \t]*[\u4e00-\u9fff][^\n]{0,28}$")


def _clean_seg(seg):
    """剔掉一个「页」段开头的页眉行（只碰段首，不碰正文中部）。"""
    lines = seg.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and HEADER_LINE.match(lines[i]):
        lines = lines[:i] + lines[i + 1:]
    return "\n".join(lines)


def clean_src(raw):
    """按**页**切段，只在每段段首剔一条页眉行，再整体去空白。

    旧口径（2026-09-13 阶段1.5 实测抓到 ⇒ 并入 A-30）：页眉正则带 `re.M` **全文逐行** sub，
    会把正文里恰好形如「数字开头 + 中文短句」的行也剔掉 ⇒ 让「跨过该行」的引文**假命中**
    （即"引文并非连续原文"却判为命中）。新口径只作用于段首 ⇒ 触及不到正文中部，
    严格方向更保守（只会更难命中，不会更容易）。
    """
    return norm("\n".join(_clean_seg(s) for s in PAGEMARK_ANY.split(raw)))


def split_pages(raw):
    """按页标记切页 → `[(页标记, 该页 norm 文本), ...]`。

    供**页锚校验**（阶段1.5 三态：命中锚页／错锚／无锚）与**跨页引文**观测使用。
    """
    toks = PAGEMARK_ANY.split(raw)
    marks = PAGEMARK_ANY_MARK.findall(raw)
    pages = []
    for k, mark in enumerate(marks):
        seg = toks[k + 1] if k + 1 < len(toks) else ""
        pages.append((str(mark).strip(), norm(_clean_seg(seg))))
    return pages


def check_one(notes_path, src_path):
    t = io.open(notes_path, encoding="utf-8").read()
    raw = io.open(src_path, encoding="utf-8").read()
    src = clean_src(raw)
    src_m = norm_match(src)          # ← 比对用（标点族折叠）；src 保留供可读性
    pages = split_pages(raw)          # 供「跨页引文」观测（见下）
    cross_page = []
    entries = list(ENTRY.finditer(t))
    quotes = list(QUOTE.finditer(t))
    anchors = list(ANCHOR.finditer(t))
    # 以条目块切分，逐条取引文
    # 以条目块切分，逐条取引文（放宽后：可解析即入块；带尾部说明单独计数）
    # ⚠ 此处曾**另写了一遍**窄正则 ⇒ 即使 SPLIT_ENTRY 已放宽，块过滤仍把条目全滤掉
    #   ⇒ 又回到"切块为空/条目 0"（A-04 家族：同一判据写两遍＝改一处等于没改）。
    #   现与 ENTRY/SPLIT 同源（`_bandid.BLOCK_RE`）：**语法只有一份**（A-132）。
    blocks = BID.split_blocks(t)
    # 空块保护（A-28 家族）：切块为空＝校验无对象，绝不允许"静默通过"
    # 自诊断加强（2026-09-19 · A-132）：光报"工装缺陷"没用——**必须把"实际看到的标题行"打出来**，
    #   这样"尺子错"与"产出错"当场可分（本次实测就是靠这一步才把 16 处内联语法挖出来）。
    if not blocks:
        heads = [l for l in t.splitlines() if l.lstrip().startswith('#')][:3]
        return dict(entries=0, quotes=0, anchors=0, quote_ok=0, with_tail=0, cross_page=[],
                    format=0, no_quote=0, not_found=[], too_long=[], pagemark=[], no_anchor=0,
                    fatal="切块为空：条目正则未命中任何块（工装缺陷，不得视为通过）"
                          "｜期望语法：`### <波段>-<三位序号>  [类型] [技能=…]`，"
                          "波段前缀 = `%s`（见 tools\\_bandid.py）"
                          "｜文件实测标题行：%s" % (BID.BAND, " ／ ".join(heads) if heads else "（无 # 开头行）"))
    bad = {"format": 0, "no_quote": 0, "not_found": [], "too_long": [], "pagemark": [], "no_anchor": 0}
    n_quote_ok = 0
    n_tail = 0
    multi_q = []          # 一个条目里写了**多条**引文（▲ 信息项，不阻断）
    for b in blocks:
        m = ENTRY.match(b.split("\n")[0])
        if not m:
            bad["format"] += 1
            continue
        if m.group(5):
            n_tail += 1
        eid = "%s-%s" % (m.group(1), m.group(2))
        # 一个条目就该有**一行**引文（模板硬纪律：引文 ≤160 字）。实测抓到（NAS 册 `<task>`
        # 的 `E6-019`）：长引文被拆成 **3 行**，于是"33 条目 / 35 引文行"——数量不符却**静默通过**
        # （`A-28` 家族：判据只看"有没有"，不看"几条"）。**不阻断**（拆行是压 160 字的正当手法），
        # 但**必须显式列出来**，否则格式漂移无人可见。
        nq = len(QUOTE.findall(b))
        if nq > 1:
            multi_q.append((eid, nq))
        qm = QUOTE.search(b)
        if not qm:
            bad["no_quote"] += 1
            continue
        if not ANCHOR.search(b):
            bad["no_anchor"] += 1
        q = qm.group(1)
        if PAGEMARK.search(q):
            bad["pagemark"].append(eid)
        if len(norm(q)) > 160:
            bad["too_long"].append((eid, len(norm(q))))
        if norm_match(q) in src_m:
            n_quote_ok += 1
            # 跨页引文观测（A-30 附带）：全文命中、但**任何单页内都找不到** ⇒ 该条
            # 横跨页边界（提取器正确跳过了页标记与页眉，引文本身仍连续）。登记为 ▲ 信息项。
            if not any(norm_match(q) in norm_match(pt) for _, pt in pages):
                cross_page.append(eid)
        else:
            bad["not_found"].append(eid)
    return dict(entries=len(entries), quotes=len(quotes), anchors=len(anchors),
                quote_ok=n_quote_ok, with_tail=n_tail, cross_page=cross_page,
                multi_quote=multi_q, **bad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notes")
    ap.add_argument("--src")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--task", required=True,
                    help="任务 slug（决定 candidates/ 与默认源文件；**必填**，无册别默认值）")
    ap.add_argument("--src-dir", default=None, help="--all 模式下按 <band>-*.txt 找源的目录（默认 <work>/notes/source）")
    ap.add_argument("--pagemark", choices=['auto', 'dash', 'equals', 'hline'], default='auto',
                    help="页标记形态；auto＝探测源文件（`===== [PAGE n] =====`→equals；行首 `[pn]`→hline；否则 dash）")
    a = ap.parse_args()

    global WORK, CAND, SRCD
    WORK = os.path.join(ROOT, ".work", a.task)
    CAND = os.path.join(WORK, "candidates")
    SRCD = a.src_dir or os.path.join(WORK, "notes", "source")

    # 页标记形态探测：以**实际源文件**为准（不得凭推断 —— A-29 格式类判据须先做形态普查）
    # 2026-09-17 修（换书准备批）：① 增 hline 形态；② 探测源**不再只 glob `*.txt`**——
    #   `pdf_to_text.py` 的产物是 `book_text.md`，旧 glob 在 `<work>/*.txt` 里取到 `bands-*.txt` 之类
    #   非正文文件会**探错形态**（探测源挑错 ⇒ 判据全歪）。现按"候选名优先"列表查找。
    # 2026-09-17 修（换书准备批）：① 增 hline 形态；② 探测源**不再只 glob `*.txt`**——
    #   `pdf_to_text.py` 的产物是 `book_text.md`，旧 glob 在 `<work>/*.txt` 里取到 `bands-*.txt` 之类
    #   非正文文件会**探错形态**（探测源挑错 ⇒ 判据全歪）。现按"候选名优先"列表查找。
    # ⚠ 2026-09-19 二次定案（**NAS 真机抓到，A-133**）：探测用的"名字优先"规则与**逐文件校验**用的
    #   "最新修改"规则是**两套**。实测后果：探测正确识别 `book_text.md ⇒ hline`，而逐文件校验却把
    #   源决议到 **`DIGEST.md`**（任务自己的产出文档、最新修改）⇒ **6 个波段 236 条引文 100% 报
    #   "回源未命中"**（`notes_E1.md ← DIGEST.md`）。⇒ 现改为**唯一决议函数 `resolve_src()`**，
    #   探测与校验共用；兜底候选还必须**真的含页标记**（内容判据，与书无关）。
    explicit_src, spec_note = _bookspec_src(a.task, a.src)
    form = a.pagemark
    if form == 'auto':
        probe = explicit_src or _fallback_src(None, a.task)
        if probe and os.path.exists(probe):
            form = detect_pagemark(probe)          # ← 唯一权威探测函数（见上方定义）
            print("页标记形态探测：源＝%s ⇒ %s（%s）" % (os.path.basename(probe), form, spec_note))
        else:
            form = 'dash'
    set_pagemark(form)
    print("页标记形态：%s（%s）｜任务目录：%s" % (form, a.pagemark, WORK))

    jobs = []
    if a.all:
        # 显式 --src 优先（**本册实况**：全册共用同一份 OCR 主文本）
        # ⚠ 实测抓到（2026-09-17）：兜底按 `sorted(glob(<work>/*.txt))` 取第一个字符序文件，
        #   实际取到了**对照引擎的** `ocr.txt`（PaddleOCR），而主文本是 `ocr_ds.txt`
        #   ⇒ 引文全部"回源未命中"（**判据指向了错误的源** ＝ A-45「取该页原文必须用正确来源」同族）。
        if explicit_src:
            print("源文件决议：%s %s" % (os.path.basename(explicit_src), spec_note))
        for n in sorted(glob.glob(os.path.join(CAND, "notes_*.md"))):
            # 备份/中间稿一律排除（`notes_F.pre-repair.bak.md` 曾被当成波段 ⇒ 假红，实测抓到）
            bn = os.path.basename(n)
            if '.bak' in bn or 'pre-repair' in bn:
                continue
            # 波段名可为**纯字母**（本册 A..G）或字母+数字（旧册 T1..T6 / NAS 册 E1..E6）——
            # 语法取自唯一真源 `_bandid`（A-132）。
            mb = re.search(r"notes_(" + BID.BAND + r")\.md", n)
            if not mb:
                print("🔴 %s 波段名无法解析" % bn)
                continue
            band = mb.group(1)
            # 源基准候选集补 `.md`（2026-09-19 · NAS 实测）：源文未必是"波段 txt"，
            # 常见是整本 `book_text.md`（放在书树里、任务目录仅软链）⇒ 只认 .txt 会误判缺源。
            cands = (sorted(glob.glob(os.path.join(SRCD, band + "-*.txt"))) +
                     sorted(glob.glob(os.path.join(SRCD, band + "-*.md"))))
            if cands:
                jobs.append((n, cands[0]))
            elif explicit_src and os.path.exists(explicit_src):
                jobs.append((n, explicit_src))
            else:
                fb = _fallback_src(bn, a.task)
                if fb:
                    jobs.append((n, fb))
                else:
                    print("🔴 %s 找不到对应源文件（找过：%s/%s-*.txt|md、<work>/*.txt|md、bookspec 的 src）"
                          % (bn, SRCD, band))

        # ── 空集拒跑闸（2026-09-17 换书准备批实测抓到 · A-55 家族）────────────────────
        # 实测：在 candidates/ 下**一个 `notes_*.md` 都没有**时，`--all` 会直接走到汇总并打印
        #   `总判定：✔ 全部通过` —— **"没有对象可检"被报成"通过"**，即 A-55「漏检比误报致命」的活体标本。
        #   ⇒ 显式拒跑：解析出 0 个待检文件即 rc≠0 并说明原因（宁红不假绿）。
        #   ⚠ 落位纪律：本闸必须放在 **`for` 循环之后、`else:` 之前**——
        #    首版误插进 `if a.all:` 与其 `else:` 之间 ⇒ 悬空 else ＋ `IndentationError`（当场语法自检抓到）。
        if not jobs:
            print("🔴 --all 解析出 **0 个待检文件**（%s\\notes_*.md）——**空集不得视为通过**。" % CAND)
            print("   若阶段1 尚未产出提取笔记，这是**正常的红**（此刻本就不该有结论）；")
            print("   若已有产出，请检查文件名是否形如 `notes_<波段>.md`。")
            return 1
        print("待检文件 %d 个（波段 %s）" % (len(jobs), '、'.join(
            re.search(r"notes_(" + BID.BAND + r")\.md", n).group(1) for n, _ in jobs)))
    else:
        assert a.notes and a.src, "需同时给 --notes 与 --src（或 --all）"
        jobs.append((a.notes, a.src))

    total_bad = 0
    for notes_path, src_path in jobs:
        r = check_one(notes_path, src_path)
        nb = (r["format"] + r["no_quote"] + len(r["not_found"]) + len(r["too_long"])
              + len(r["pagemark"]) + r["no_anchor"] + (1 if r.get("fatal") else 0))
        total_bad += nb
        print("=" * 74)
        print("%s  ←  %s" % (os.path.basename(notes_path), os.path.basename(src_path)))
        if r.get("fatal"):
            print("  🔴 %s" % r["fatal"])
        print("  条目 %d ｜ 引文行 %d ｜ 锚行 %d" % (r["entries"], r["quotes"], r["anchors"]))
        print("  引文回源命中：%d / %d" % (r["quote_ok"], r["quotes"]))
        # 全数未命中 ⇒ **先自证"谁错了"**（A-133 教训：NAS 实测 236/236 未命中，真因是源决议错到了
        # `DIGEST.md`；若只报"236 项不合格"，使用者会去改**合规的产出**）。故此处强制打印：
        # 本文件实际使用的源 + 最可能的原因 + 可执行处置。
        if r["quotes"] and r["quote_ok"] == 0:
            print("  ⚠⚠ **全数回源未命中（0/%d）** —— 优先怀疑**源文件决议错误**，不要先改产出：" % r["quotes"])
            print("     本文件实际使用的源：%s" % src_path)
            print("     自证三步：① `--src <源文路径>` 显式指定再跑一次；"
                  "② 确认该源**含页标记**（真实源文必分页）；"
                  "③ 建 `<work>/bookspec-<task>.json` 的 `src` 字段固定下来（推荐，一次性）。")
        print("  格式不合规 %d ｜ 缺引文 %d ｜ 缺锚 %d ｜ 引文超 160 字 %d ｜ 误引页标记 %d ｜ 回源未命中 %d"
              % (r["format"], r["no_quote"], r["no_anchor"], len(r["too_long"]), len(r["pagemark"]), len(r["not_found"])))
        if r.get("with_tail"):
            print("  ▲ 格式偏离（`[技能=…]` 后有说明文字）：%d 条 —— **可机械解析，登记不阻断**" % r["with_tail"])
        if r.get("multi_quote"):
            print("  ▲ 一条目多引文：%d 条 —— %s"
                  % (len(r["multi_quote"]),
                     "、".join("%s(%d 行)" % x for x in r["multi_quote"][:8])))
            print("     （模板硬纪律是**每条目一行引文**；拆行是压 160 字的正当手法 ⇒ 不阻断，但须可见）")
        if r.get("cross_page"):
            print("  ▲ 跨页引文（横跨页边界；提取器已跳过页标记与页眉，引文本身仍连续）：%d 条 —— %s"
                  % (len(r["cross_page"]), "、".join(r["cross_page"][:12])))
        if r["not_found"]:
            print("  🔴 回源未命中：%s" % "、".join(r["not_found"][:12]))
        if r["too_long"]:
            print("  🔴 超长引文：%s" % "、".join("%s(%d字)" % x for x in r["too_long"][:8]))
        if r["pagemark"]:
            print("  🔴 误引页标记：%s" % "、".join(r["pagemark"][:8]))
        print("  → %s" % ("✔ 通过" if nb == 0 else "🔴 %d 项不合格" % nb))
    print("=" * 74)
    print("总判定：%s" % ("✔ 全部通过" if total_bad == 0 else "🔴 合计 %d 项不合格" % total_bad))
    return 1 if total_bad else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
