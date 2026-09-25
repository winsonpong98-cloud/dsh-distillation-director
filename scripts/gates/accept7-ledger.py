#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""accept7-ledger.py —— 蒸馏册「7 条状态」单一台账（**机器生成 · 只读 · ¥0**）

为什么要它（用户 2026-09-23 指令）：
    「**所有我之前蒸馏过的，和我以后需要蒸馏的书籍，最后都能达到这 7 个要求才算完成**」。
    此前「哪本书过没过 7 条」**无人能回答**，因为产物散落在 4 个位置、且没有索引。
    本件把答案变成**机器算出来的表**，不再依赖任何人的记忆。

口径（唯一数据源）：
    `.work/<task>/accept7-<task>.md`（册级验收记录件；其存在性由
    `check_distill_artifacts.py` 的 **R4** 硬拦保障，判态取值合法性也由 R4 负责）。
    本件**只汇总与搬运，不判质量、不改任何文件**（`--out` 除外）。

两类册：
    A 类＝`.work/*` 下**有 `read_receipt.json`** 的目录 ⇒ 走过现行蒸馏流程（R4 射程内）。
    B 类＝`投资蒸馏/*` 册目录，但**在 A 类里找不到对应任务** ⇒ 未走现行流程（无收据），
          accept7 待建；**如实列出，不隐藏**。

完成判据（与 accept7 件内的定义一致）：
    完成 ⟺ 判态行 7/7 且 ✅=7（即 🔴=⛔=⏸=0）且 **右栏判官裁无"待派"**。
    暂缓 ⟺ 判态行 7/7 且 🔴=⛔=0 且 ⏸>0（第 6 条按用户指令暂缓）。
    其余 ⇒ 未完成（附计数，便于一眼看出卡在哪）。

用法：
    python tools\accept7-ledger.py                      # 打印到屏幕
    python tools\accept7-ledger.py --out 输出\蒸馏台账-2026-09-23.md

退出码：0 ＝ 已出表；1 ＝ 有册缺 accept7 件（＝待办清单，不是"错误"）。
"""
import argparse
import glob
import io
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _o
import sys as _s
_H = _o.path.dirname(_o.path.abspath(__file__))
_s.path.insert(0, _H)
from _paths import ROOT  # noqa: E402

# B 类册目录里**不是书**的（工具/实验/快照类），按 §3 口径排除。
#   🔴 2026-09-23：改 import **单一来源** `distill_book_skip`（原先这里与 `tools_common.py`
#   各写一份同义表 ⇒ `A-72` 家族「同一判据写两遍＝改一处等于没改」）。
from distill_book_skip import SKIP_DIRS   # noqa: E402

# 册名 → 任务 slug 的**别名**：**从 `bookspec-<task>.json` 的 `book` 字段派生**
#   （⚠ **不得在源码里写死书名** —— `A-74`／`A-95`「通用件不得特定化」；
#    本项目自己的 `bookspec-qushi-liliang.json` 的 `_说明` 亦明写「不得在工具源码里写死本书数据」。
#    实测教训：首版把 5 个书名硬编码进 SLUG_MAP ⇒ `check_tools_generic.py` 当场判红「乙类未登记」。）
# 用途＝**去重**：首版台账把**同一册**列了两次（一次按 A 类 slug、一次按 B 类册目录名）
#   ＝重复计数 ⇒ 会把册数报大，属错答案。


def _alias_map():
    """{册目录名: slug}。**两个来源，都由数据决定，源码零书名**：
       ① `.work/_accept7-book-alias.json`（数据件，每条带 _evidence）；
       ② 各册 `bookspec-<task>.json` 的 `book` 字段（书名 → slug，再按前缀匹配目录名）。
       读不到就**返回空表（不猜）**。"""
    m = {}
    ap = _o.path.join(ROOT, '.work', '_accept7-book-alias.json')
    if _o.path.isfile(ap):
        try:
            d = json.load(io.open(ap, encoding='utf-8', errors='replace'))
            for e in (d.get('alias') or []):
                if isinstance(e, dict) and e.get('dir') and e.get('slug'):
                    m[e['dir']] = e['slug']
        except Exception:
            pass
    for f in glob.glob(_o.path.join(ROOT, '.work', '*', 'bookspec-*.json')):
        try:
            d = json.load(io.open(f, encoding='utf-8', errors='replace'))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        task = d.get('task') or _o.path.basename(_o.path.dirname(f))
        book = (d.get('book') or '').strip()
        if task and book and book not in m:
            m[book] = task
    return m


def _match_slug(dirname, alias):
    """册目录名 → slug：精确命中，或**目录名与 bookspec 的书名互为前缀**
       （实测形态：册目录名＝书名去掉副标题后的部分）。**匹配不到就返回 None，不猜。**"""
    if not dirname or not alias:
        return None
    if dirname in alias:
        return alias[dirname]
    for book, task in alias.items():
        if book.startswith(dirname) or dirname.startswith(book):
            return task
    return None


# ── 右栏状态判据（`G-58` · 2026-09-24）────────────────────────────────────
#   旧版 `if '待派' in r` 有两错：① 搜**整行**（证据格里提到「待派」也被算成未裁）；
#   ② 只认「待派」二字 ⇒ 写成「待判官回」「待复核」「已派未回」就**静默算成已裁**，
#   而「右栏已派」正是 §27.2.1 完成判据的一项 ⇒ **措辞一变，完成判据即被绕过**。
#   新版纪律：**只看右栏格** ＋ **状态词表** ＋ **一个词都没有就归类为 `?` 并报警**
#   （宁可报警，不可静默；本工作区既有纪律：没有可跑命令／无状态词的"完成"不算完成）。
PEND_WORDS = ('待派', '待判官', '待复核', '未裁', '已派未回')
JUDGED_WORDS = ('已裁', '已派')
SKIP_WORDS = ('暂缓', '按令未做', '按用户指令', '—',
              # 冻结册的固有措辞（用户 2026-09-24 指令：「有些冻结的、不用的书和技能，你就跳过…
              # 有注明的你就不要动」）——首版词表漏了它，新报警当场报出 6 格无状态词。
              '冻结', '跳过', '不追')


def _right_state(right):
    """右栏格 → `'pend'`（未裁）／`'judged'`（已裁）／`'skip'`（暂缓等）／`'?'`（**无状态词，须报警**）。"""
    s = right or ''
    if any(w in s for w in PEND_WORDS):
        return 'pend'
    if any(w in s for w in JUDGED_WORDS):
        return 'judged'
    if any(w in s for w in SKIP_WORDS):
        return 'skip'
    return '?'


def parse_accept7(p):
    """返回 (found_rows_dict, n_ok, n_bad, n_noback, n_stall, n_pend, n_noword, has_warn)"""
    t = io.open(p, encoding='utf-8', errors='replace').read()
    found = {}
    for m in re.finditer(r'^\s*\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|(.*)$', t, re.M):
        n = int(m.group(1))
        if 1 <= n <= 7 and n not in found:
            found[n] = m.group(2)
    n_ok = n_bad = n_noback = n_stall = n_pend = n_noword = n_vmiss = 0
    vmiss_rows = []
    for n in range(1, 8):
        r = found.get(n)
        if r is None:
            continue
        # 判态格＝第 2 格（`| 条号 | 标准 | 判态格 | 证据 | 右栏 |`）；**与 R4 同口径**，
        # 不得改回"整行找符号"（实测把证据格里的 ✅ 误当判态 ⇒ 报错数）。
        cells = [c.strip() for c in r.split('|')]
        # ⚠ `m.group(2)` 是 `| **N** |` **之后**的内容，行尾那个 `|` 仍在 ⇒ split 后**末元素是空串**。
        #   不剥掉它，`cells[-1]` 取到的就是空串（＝"右栏无状态词"）——**本条由新增自证当场抓到**
        #   （首版实测：17 册 × 7 行＝119 格全被判成无状态词）。
        while cells and cells[-1] == '':
            cells.pop()
        jc = cells[1] if len(cells) >= 2 else (cells[0] if cells else '')
        # ── 判态＝**格内第一个判态符号**（`G-60` · 2026-09-24）──────────────────
        #   旧版对四类符号各做 `in jc` ⇒ **格内"提到"某个符号也会被计数**：实测我在第 3 条格里
        #   写「本条不得再记 ✅」，该行便被**同时**算成 ✅ 与 🔴 ⇒ 册级计数虚高（本册读数
        #   ✅5／🔴2 里那个 ✅5 有 1 个就是"提到"出来的）。现改为**只认第一个出现的判态符号**
        #   （判态格的行文惯例＝判态写在最前；`⏸` 另容「暂缓」一词）。
        _pos = [(jc.find(c), c) for c in '✅🔴⛔⏸' if jc.find(c) >= 0]
        _first = min(_pos)[1] if _pos else None
        if _first == '✅':
            n_ok += 1
        elif _first == '🔴':
            n_bad += 1
        elif _first == '⛔':
            n_noback += 1
        elif _first == '⏸' or '暂缓' in jc:
            n_stall += 1
        # ── 右栏状态（`G-58` 修法 · 2026-09-24）：**只看右栏格**，且须有状态词 ──
        #   旧版 `if '待派' in r` 两错：① 搜**整行**（证据格里出现「待派」也被算未裁）；
        #   ② 只认「待派」二字（写成「待判官回」即**静默算成已裁**）。
        stt = _right_state(cells[-1] if cells else '')
        if stt == 'pend':
            n_pend += 1
        elif stt == '?':
            n_noword += 1
        elif stt == 'judged':
            # ── G-58 硬闸（判词路径必填 · 2026-09-24 棘轮式升级）─────────────────
            #   已裁必须可回查：右栏「已裁」格须附判词件路径（`verdict-….md`）。
            #   棘轮口径（同 postflight ⑲）：只对**裁定日期 ≥ 2026-09-24**（取行内
            #   第一个 ISO 日期，判态格行文惯例＝裁定日期写在最前）的已裁行强制；
            #   历史裁定（日期更早／无日期）**不追溯**——硬拦历史＝闸在要求"没做过的事"。
            _dm = re.search(r'2026-\d{2}-\d{2}', r)
            _recent = bool(_dm) and _dm.group(0) >= '2026-09-24'
            _has_vp = bool(re.search(r'verdict[^｜\s]*\.md', cells[-1], re.I))
            if _recent and not _has_vp:
                n_vmiss += 1
                vmiss_rows.append(str(n))
    return found, n_ok, n_bad, n_noback, n_stall, n_pend, n_noword, n_vmiss, ','.join(vmiss_rows), ('⚠' in t)


# ── 池的**形态**判据（`G-59` · 2026-09-24）────────────────────────────────
#   **为什么改（旧口径错在哪）**：旧版按**体积取大**（`verified.md` vs `candidates/*.md`
#   合计），于是把一个**根本没有池**的册报成「池 82KB」——实测 `talabu-suiji-manbu`：
#   `.work` 与册目录**都没有 `verified.md`**，那 82KB 是 `candidates/` 下的**候选件**，
#   其形态是 `- id: ca01` ／ `- title:` ／ `- source_chapter:`，机器逐件计数
#   「`### 波段-id` ＝ 0 处、`原文（逐字）` ＝ 0 处」⇒ **不是池式件**。
#   这与 `G-31` 已定的口径（**候选≠池**，见 `backfill_task.py --pool` 帮助）**正相反**
#   ⇒ 同一个事实在库里两把尺子。修法＝**认形态不认体积**：
#   含有「`原文（逐字）`」条目行的 `.md` 才算池件；`candidates/` 的体积只作
#   **信息性**读数（明标「非池」），不再参与取大。
POOL_MARK = '原文（逐字）'
POOL_SCAN_BYTES = 64 * 1024     # 只读头部：池式件的条目从第 1 屏就开始，不必读完大件
#   ⚠ **波段条目头**的语法一律取自唯一真源 `_bandid`（`A-132`：工作台级单一真源，
#   巡检闸 `check_bandid_single_source.py` 已挂 postflight）——**不得在本文件内联**。
from _bandid import HEAD_RE as _BAND_HEAD_RE   # noqa: E402
# 引文行的**标签容错**沿用唯一真源（`verify_candidates.QUOTE`，与 `scan_pool_counterexamples`
#   同一处）：池件的引文标签历史上有 `原文（逐字）`／`原文(逐字)`／`逐字原文`／`原文` 四种写法，
#   只认一种会**造假红**（`A-04` 家族；`A-55`：漏检比误报更致命）。
import verify_candidates as _VC          # noqa: E402

# 层位排除（`G-31`）：这两个目录里的件**按角色**是取料／候选／笔记层，**不是池**——
#   即便它们长成池的样子（实测 `candidates\cases.md` 与 `notes\notes_C1.md` 都含
#   `### <id>` 头与「原文（逐字）」行 ⇒ 只按形态会被误认）。
NON_POOL_DIRS = ('candidates', 'notes')


def _pool_marks(path):
    """该件含几条**池式条目头**；判据＝**两个形态同时在场**：
       ① `### <波段-id>` 条目头（语法取自 `_bandid.HEAD_RE`，单一真源）
       ② 至少一行「`原文（逐字）`」条目字段。
       ⇒ **只讲池格式的计划书／精读笔记**（`- id: pr01` 形态）与**只被提到过**的文件
       都不会被误判成池（这是首版"只认标记"当场踩到的假阳性）。
       只读前 64 KB；读不动返回 0（**不猜**）。"""
    try:
        with io.open(path, encoding='utf-8', errors='replace') as fh:
            head = fh.read(POOL_SCAN_BYTES)
    except Exception:
        return 0
    if not _BAND_HEAD_RE.search(head):
        return 0
    if not (_VC.QUOTE.search(head) or POOL_MARK in head):
        return 0
    return len(_BAND_HEAD_RE.findall(head))


def _pool_form(d):
    """按**形态 ＋ 层位**找池 ⇒ `(池KB, 池件名, candidates KB)`。
       · **层位（`G-31`）**：`candidates/`（取料／候选层）与 `notes/`（精读笔记层）**目录内**的件
         **一律不认作池**——实测它们**也会**长成池的样子（`### <id>  [..]` ＋ `原文（逐字）`），
         但按 `G-31` 的口径它们是候选层、不是池。只认 `.work/<task>/` 或册目录**自己**的 `*.md`。
       · **形态**：含 `### <波段-id>` 条目头 ＋ 至少一行「`原文（逐字）`」（见 `_pool_marks`）。
       只扫**该目录自己的** `*.md`（子目录天然不入选，`candidates/` 另有显式排除）。
       阈值（≥50 KB 算真池）由调用方判。"""
    pk, pname = 0, None
    if _o.path.basename(_o.path.normpath(d)) in NON_POOL_DIRS:
        pk, pname = 0, None            # 层位排除：候选／笔记目录内的件不是池
        csz = _cand_kb(d)
        return pk, pname, csz
    try:
        names = sorted(os.listdir(d))
    except Exception:
        names = []
    for f in names:
        if not f.lower().endswith('.md'):
            continue
        p = _o.path.join(d, f)
        if not _o.path.isfile(p):
            continue
        if _pool_marks(p) < 1:
            continue
        kb = _o.path.getsize(p) // 1024
        if pname is None or kb > pk:
            pk, pname = kb, f
    return pk, pname, _cand_kb(d)


def _cand_kb(d):
    """`candidates/*.md` 的体积 —— **仅作信息性读数**（明标「非池」，见 `G-31`／`G-59`）。"""
    csz = 0
    cd = _o.path.join(d, 'candidates')
    if _o.path.isdir(cd):
        for f in sorted(os.listdir(cd)):
            if f.lower().endswith('.md'):
                try:
                    csz += _o.path.getsize(_o.path.join(cd, f)) // 1024
                except Exception:
                    pass
    return csz


def _pool_txt(pk, pname, csz, thresh=50):
    """池读数的人类可读形态（**不藏判据**：非池式的大 candidates 会明标出来）。
       `pname` 为 None ＝ 该目录**没有池式件**（这才是"无池"）；有件但太小也会印名字，不吞掉。"""
    if pname and (thresh <= 0 or pk >= thresh):
        t = '✔%dKB(%s)' % (pk, pname)
    elif pname:
        t = '⚠%dKB(%s 不足%dKB)' % (pk, pname, thresh)
    else:
        t = '✗'
    if csz:
        t += '(cand%dKB**非池**)' % csz
    return t


def _prereq(slug, work):
    """第 1 条的**四件前置**在位情况（机器算）：`bookspec` ／ `src` ／ `池` ／ `技能`。
       口径声明（**不藏判据**）：**池 ≥ 50 KB 且为池式件（含「原文（逐字）」条目行）才算"真池"**；
       池的判定已由「体积取大」改为「**形态判定**」（`G-59` · 2026-09-24，见 `_pool_form`），
       `candidates/*.md` **不是池**（`G-31`）——其体积只作信息性标注。
       ⚠ `src` 兼容**绝对路径与相对路径**：实测 `qushi-liliang` 的 `src` 存绝对路径，
       用 `Join-Path` 拼接会得到非法路径 ⇒ **假阴性**（我踩过，已修）。
       返回 (n_ok, detail)。"""
    d = _o.path.join(work, slug)
    n = 0
    sp = _o.path.join(d, 'bookspec-%s.json' % slug)
    has_spec = _o.path.isfile(sp)
    if has_spec:
        n += 1
    src_ok = False
    if has_spec:
        try:
            j = json.load(io.open(sp, encoding='utf-8', errors='replace'))
            s = (j.get('src') or '').strip()
            if s:
                p = s if _o.path.isabs(s) else _o.path.join(d, s)
                src_ok = _o.path.isfile(p)
        except Exception:
            pass
    if src_ok:
        n += 1
    pk, pname, csz = _pool_form(d)
    if pk >= 50:
        n += 1
    sk = 0
    skd = _o.path.join(d, 'skills')
    if _o.path.isdir(skd):
        for x in sorted(os.listdir(skd)):
            if x.startswith('_'):
                continue
            if _o.path.isfile(_o.path.join(skd, x, 'SKILL.md')):
                sk += 1
    if sk:
        n += 1
    det = 'spec%s src%s 池%s 技能%d' % (
        '✔' if has_spec else '✗',
        '✔' if src_ok else '✗',
        _pool_txt(pk, pname, csz),
        sk)
    return n, det


def _dir_prereq(dirpath):
    """册目录（未建任务目录者）里**等价件**的在位情况：池（**形态判定**·`G-59`）＋ 技能数 ＋ parts 片目录数。
       ⚠ 册目录这一侧**不套 50 KB 阈值**（只报"池式件在不在、多大"），与 `.work` 侧刻意不同：
       册目录是交付副本，读者要的是"这里有没有池式件"，交由人判断。"""
    pk, pname, csz = 0, None, 0
    for root, _dirs, _fs in os.walk(dirpath):
        if _o.path.basename(_o.path.normpath(root)) in NON_POOL_DIRS:
            continue                    # 层位排除（G-31）：候选／笔记层不算池
        k, nm, c = _pool_form(root)
        if k > pk:
            pk, pname = k, nm
        if c > csz:
            csz = c
    sk = 0
    parts = 0
    for root, dirs, _fs in os.walk(dirpath):
        if _o.path.isfile(_o.path.join(root, 'SKILL.md')) and _o.path.basename(root) != '':
            sk += 1
            dirs[:] = []
            continue
        for x in list(dirs):
            if x == 'parts':
                parts += 1
    return '池%s 技能%d parts%d' % (_pool_txt(pk, pname, csz, thresh=0), sk, parts)


def _frozen_slugs():
    """冻结册名单 —— **单一来源** `tools\\distill_frozen.py`（用户 2026-09-24 指令：
    冻结／不用的书与技能"有注明的就不要动"）。取不到就返回空集并**明写**，不静默当"没有冻结件"。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from distill_frozen import frozen_tasks
        return frozen_tasks()
    except Exception as e:
        print('  ⚠ 冻结名单不可用（%s: %s）⇒ 本表**不标**冻结，请查 tools\\distill_frozen.py' % (type(e).__name__, e))
        return {}


def my_rows(p7):
    """读一份 accept7 件的**逐条符号**：{条号: 符号}。"""
    per = {}
    if not _o.path.isfile(p7):
        return per
    for x in io.open(p7, encoding='utf-8').read().split('\n'):
        m = re.match(r'^\|\s*\*\*([1-7])\*\*\s*\|', x)
        if not m:
            continue
        cells = x.replace('\\|', '\x01').split('|')
        cell = cells[3] if len(cells) > 3 else ''
        s = SYM.search(cell)
        per[int(m.group(1))] = s.group(1) if s else '?'
    return per


SYM = re.compile(r'(✅|🔴|⛔|⏸)')


def is_composite(text):
    """复合册：accept7 件里**有 `## 子册清单` 这一节标题**（该册由多本子书合成）。
    ⚠ 自伤登记（2026-09-24）：首版只判「正文出现该词」⇒ 把 5 个子册件也误判成复合册（汇总里出现 6 个"汇总行"）。"""
    return re.search(r'(?m)^#{2,4}\s*子册清单', text) is not None


def sub_rows(slug):
    """读该复合册 5（或 N）个子册件 → {子册: {条: 符号}}。子册名从「子册清单」节里的 `.work/<x>/` 提。"""
    comp = _o.path.join(ROOT, '.work', slug, 'accept7-%s.md' % slug)
    if not _o.path.isfile(comp):
        return {}
    t = io.open(comp, encoding='utf-8').read()
    names = sorted(set(re.findall(r'\.work[\\/]([a-z0-9-]+)[\\/]accept7', t))
                   | set(re.findall(r'`(talabu-[a-z0-9-]+)`', t)))
    out = {}
    for nm in names:
        f = _o.path.join(ROOT, '.work', nm, 'accept7-%s.md' % nm)
        if not _o.path.isfile(f) or nm == slug:
            continue
        per = {}
        for x in io.open(f, encoding='utf-8').read().split('\n'):
            m = re.match(r'^\|\s*\*\*([1-7])\*\*\s*\|', x)
            if not m:
                continue
            cells = x.replace('\\|', '\x01').split('|')
            cell = cells[3] if len(cells) > 3 else ''
            s = SYM.search(cell)
            per[int(m.group(1))] = s.group(1) if s else '?'
        if per:
            out[nm] = per
    return out


def composite_violations(slug, my_rows):
    """返回违反「任一子册非 ✅ ⇒ 本册不得 ✅」的 (条, 本册符号, 子册符号) 列表。"""
    subs = sub_rows(slug)
    if not subs:
        return []
    bad = []
    for n in range(1, 8):
        mine = my_rows.get(n, '?')
        if mine != '✅':
            continue
        worse = sorted({s.get(n, '?') for s in subs.values()} - {'✅'})
        if worse:
            bad.append((n, mine, '／'.join(worse)))
    return bad


def verdict(nrows, n_ok, n_bad, n_noback, n_stall, n_pend, frozen_why=None, n_vmiss=0):
    if frozen_why:
        # 冻结件**优先**：按当时决定跳过 ⇒ 不当作"未完成的待办"（但事实照样登记在此列）
        return '**⏸ 冻结（当时决定·跳过，不追）**'
    if nrows < 7:
        return '未完成（判态行 %d/7）' % nrows
    if n_vmiss > 0:
        # G-58 硬闸（2026-09-24）：落地日后的「已裁」必须附判词路径，缺 ⇒ 不得记 完成/暂缓
        return '未完成（G-58 硬闸：已裁缺判词路径 %d 条）' % n_vmiss
    if n_ok == 7 and n_pend == 0:
        return '**完成**'
    if n_bad == 0 and n_noback == 0 and n_stall > 0 and n_pend == 0:
        return '暂缓（第 6 条·用户指令）'
    if n_pend > 0:
        return '未完成（右栏判官未派）'
    return '未完成（机核有红）'


def selftest():
    """自证池判据（`G-59` 纪律：**闸必须先证明自己拦得住**）。
       四档样本 ⇒ 好样本必须认、三个坏样本必须不认（含"旧口径会认错"的那个）。
       rc=0 全过；任一档不符即 rc=1 并逐条打印。"""
    import shutil
    import tempfile
    bad = []
    tmp = tempfile.mkdtemp(prefix='a7ledger-selftest-')
    try:
        Q = '- 原文（逐字）：「这是一条用于自证的池内原文。」\n'
        big = 'x' * 60000          # 60 KB ⇒ 越过 50 KB 阈值

        # ① 好样本：池式件（含「原文（逐字）」条目行）且 ≥50 KB ⇒ 认池＋前置计数
        d1 = _o.path.join(tmp, 'good')
        _o.makedirs(d1)
        io.open(_o.path.join(d1, 'verified.md'), 'w', encoding='utf-8').write(
            '# 池\n\n### A-001  [FR] [技能=S1]\n- 锚：s001\n' + Q + '- 转述：…\n' + ('t' * 60000))
        io.open(_o.path.join(d1, 'bookspec-good.json'), 'w', encoding='utf-8').write(
            json.dumps({'task': 'good', 'src': 'src.md'}))
        io.open(_o.path.join(d1, 'src.md'), 'w', encoding='utf-8').write('x\n')
        pk, nm, cz = _pool_form(d1)
        if not (pk >= 50 and nm == 'verified.md'):
            bad.append('① 好样本：池式件未被认作池（pk=%d nm=%s）' % (pk, nm))

        # ② 坏样本（**旧口径就在这一档出错**）：只有 candidates/ 有内容 ⇒ **不得**认池
        d2 = _o.path.join(tmp, 'candonly')
        _o.makedirs(_o.path.join(d2, 'candidates'))
        io.open(_o.path.join(d2, 'candidates', 'principles.md'), 'w', encoding='utf-8').write(
            '# 候选\n- id: pr01\n  title: 甲\n  source_chapter: 乙\n' + big)
        pk2, nm2, cz2 = _pool_form(d2)
        if pk2 or nm2:
            bad.append('② 仅 candidates 有内容：被误认作池（pk=%d nm=%s）' % (pk2, nm2))
        if cz2 < 50:
            bad.append('② 仅 candidates 有内容：candidates 体积未作信息性读数（cz=%d）' % cz2)
        if '非池' not in _pool_txt(pk2, nm2, cz2):
            bad.append('② 仅 candidates 有内容：读数未明标「非池」')

        # ③ 坏样本：名为 verified.md 但**不是池式件**（门禁对照文书）⇒ 不得认池
        d3 = _o.path.join(tmp, 'fakeverified')
        _o.makedirs(d3)
        io.open(_o.path.join(d3, 'verified.md'), 'w', encoding='utf-8').write(
            '# 门禁对照文书\n本文件不是池，只是一张对照表。\n' + big)
        pk3, nm3, _cz3 = _pool_form(d3)
        if pk3 or nm3:
            bad.append('③ 非池式的 verified.md：被误认作池（pk=%d nm=%s）' % (pk3, nm3))

        # ④ 坏样本：池式件但**不足 50 KB** ⇒ `_prereq` 不得给"池"记分
        d4 = _o.path.join(tmp, 'smallpool')
        _o.makedirs(d4)
        io.open(_o.path.join(d4, 'bookspec-smallpool.json'), 'w', encoding='utf-8').write(
            json.dumps({'task': 'smallpool', 'src': 'src.md'}))
        io.open(_o.path.join(d4, 'src.md'), 'w', encoding='utf-8').write('x\n')
        io.open(_o.path.join(d4, 'verified.md'), 'w', encoding='utf-8').write(
            '# 池\n\n### A-001  [FR]\n- 锚：s001\n' + Q)
        n4, det4 = _prereq('smallpool', tmp)
        # 该档前置应为 spec✔＋src✔＋技能✗＋池✗ ⇒ n=2；池未达阈值
        if n4 != 2:
            bad.append('④ 不足 50 KB 的池式件：前置计数应为 2（spec+src），实得 %d（%s）' % (n4, det4))
        if '✔' in det4.split('池')[1].split('技能')[0]:
            bad.append('④ 不足 50 KB 的池式件：池读数不该是 ✔（%s）' % det4)

        # ⑤ 坏样本（**首版"只认标记"当场踩到的那一档**）：文件**提到**池格式（含「原文（逐字）」
        #    字样、且够大）但**没有波段条目头**（是计划书／精读笔记）⇒ 不得认池
        d5 = _o.path.join(tmp, 'planmention')
        _o.makedirs(d5)
        io.open(_o.path.join(d5, '阶段1-提取计划.md'), 'w', encoding='utf-8').write(
            '# 计划\n本阶段产出池件，格式为 `- 原文（逐字）：「…」`；\n- id: pr01\n  title: 甲\n' + big)
        pk5, nm5, _c5 = _pool_form(d5)
        if pk5 or nm5:
            bad.append('⑤ 只提到池格式的计划书：被误认作池（pk=%d nm=%s）' % (pk5, nm5))

        # ⑥ 坏样本（**层位**·`G-31`）：`candidates/` 里的件**长成池的样子**
        #    （`### A-001  [FR]` 头 ＋ 「原文（逐字）」行）⇒ 仍**不得**算池
        d6 = _o.path.join(tmp, 'layerrole')
        _o.makedirs(_o.path.join(d6, 'candidates'))
        _o.makedirs(_o.path.join(d6, 'notes'))
        poolish = ('# 候选（取料层）\n\n### A-001  [FR] [技能=S1]\n- 锚：s001\n' + Q + '- 转述：…\n' + big)
        io.open(_o.path.join(d6, 'candidates', 'cases.md'), 'w', encoding='utf-8').write(poolish)
        io.open(_o.path.join(d6, 'notes', 'notes_C1.md'), 'w', encoding='utf-8').write(poolish)
        pk6, nm6, _c6 = _pool_form(d6)
        if pk6 or nm6:
            bad.append('⑥ 层位：candidates/ 或 notes/ 里的池样子件被认作池（pk=%d nm=%s）' % (pk6, nm6))
        pk6b, nm6b, _c6b = _pool_form(_o.path.join(d6, 'candidates'))
        if pk6b or nm6b:
            bad.append('⑥ 层位：直接扫 candidates/ 目录本身也认了池（pk=%d nm=%s）' % (pk6b, nm6b))
        if '池✔' in _dir_prereq(d6):
            bad.append('⑥ 层位：册目录读数里出现了池✔（%s）' % _dir_prereq(d6))

        # ⑦ 右栏状态判据（`G-58`）：**只看右栏格** ＋ 状态词表 ＋ 无词报警
        for cell, want in [('**已派·同意**（判官 x）', 'judged'),
                           ('**待派判官（本轮已派，verdict 待回）**', 'pend'),
                           ('**待判官回**（已派）', 'pend'),
                           ('**已派未回**', 'pend'),
                           ('**已裁（判官 `abc` · 已裁）**', 'judged'),
                           ('暂缓', 'skip'),
                           ('判官按令未做', 'skip'),
                           ('（空）', '?'),
                           ('见上', '?')]:
            got = _right_state(cell)
            if got != want:
                bad.append('⑦ 右栏状态：%r 期望 %s 实得 %s' % (cell, want, got))
        # 端到端：证据格提到「待派」但右栏是已裁 ⇒ **不得**算未裁（旧版会算错）
        d7 = _o.path.join(tmp, 'pendrow')
        _o.makedirs(d7)
        io.open(_o.path.join(d7, 'accept7-pendrow.md'), 'w', encoding='utf-8').write(
            '| # | 标准 | 机核判态 | 证据 | 右栏判官裁 |\n|---|---|---|---|---|\n'
            '| **1** | 甲 | ✅ | 曾经待派，现已裁 | **已裁（判官 `a1`）** |\n'
            '| **2** | 乙 | ✅ | 无 | **待判官回（已派）** |\n'
            '| **3** | 丙 | ✅ | 无 | （空） |\n')
        _f, _ok, _bad, _nb, _st, _pend, _nw, _vm, _vmr, _wn = parse_accept7(_o.path.join(d7, 'accept7-pendrow.md'))
        if not (_ok == 3 and _pend == 1 and _nw == 1):
            bad.append('⑦ 端到端：期望 ✅3／待派 1／无词 1，实得 ✅%d／待派 %d／无词 %d' % (_ok, _pend, _nw))

        # ⑧ 判态计数「**提到即算**」的负样本（`G-60` · 2026-09-24）
        #    格内**提到** ✅（例如写「原格声称 ✅ 全 PASS，实测不过」）**不得**被算成一个 ✅；
        #    只认格内**第一个**判态符号 ⇒ 本档必须算成 🔴1／✅0。
        d8 = _o.path.join(tmp, 'symrow')
        _o.makedirs(d8)
        io.open(_o.path.join(d8, 'accept7-symrow.md'), 'w', encoding='utf-8').write(
            '| # | 标准 | 机核判态 | 证据 | 右栏判官裁 |\n|---|---|---|---|---|\n'
            '| **1** | 甲 | **🔴 不通过（原格声称 ✅ 全 PASS，实测不过）** | 无 | **已裁（判官 a1）** |\n'
            '| **2** | 乙 | **⛔ 不可回溯（此格也提到 ✅ 与 🔴）** | 无 | **已裁（判官 a1）** |\n')
        _f8, _ok8, _bad8, _nb8, _st8, _p8, _nw8, _vm8, _vmr8, _wn8 = parse_accept7(_o.path.join(d8, 'accept7-symrow.md'))
        if not (_ok8 == 0 and _bad8 == 1 and _nb8 == 1):
            bad.append('⑧ 判态计数（提到即算的负样本）：期望 ✅0／🔴1／⛔1，实得 ✅%d／🔴%d／⛔%d'
                       % (_ok8, _bad8, _nb8))

        # ⑨ G-58 硬闸（判词路径必填 · 2026-09-24 棘轮）：落地日后的已裁缺路径 ⇒ 计 vmiss；
        #    带路径不算；历史日期与无日期不算（不追溯）。
        d9 = _o.path.join(tmp, 'vpathrow')
        _o.makedirs(d9)
        io.open(_o.path.join(d9, 'accept7-vpathrow.md'), 'w', encoding='utf-8').write(
            '| # | 标准 | 机核判态 | 证据 | 右栏判官裁 |\n|---|---|---|---|---|\n'
            '| **1** | 甲 | ✅ | 无 | **已裁（2026-09-25 · 判官 a1 ✅）** |\n'
            '| **2** | 乙 | ✅ | 无 | **已裁（2026-09-25 · 判词 `verdict-x-20260925.md`）** |\n'
            '| **3** | 丙 | ✅ | 无 | **已裁（2026-09-20 · 判官 a0，历史）** |\n'
            '| **4** | 丁 | ✅ | 无 | **已裁（判官 a2，未写日期）** |\n')
        _f9, _ok9, _bad9, _nb9, _st9, _p9, _nw9, _vm9, _vmr9, _wn9 = parse_accept7(
            _o.path.join(d9, 'accept7-vpathrow.md'))
        if not (_vm9 == 1 and _vmr9 == '1'):
            bad.append('⑨ G-58 硬闸：期望 vmiss=1（仅第1条）／rows=1，实得 vmiss=%d／rows=%r'
                       % (_vm9, _vmr9))
        _v9 = verdict(7, 4, 0, 0, 0, 0, n_vmiss=_vm9)
        if 'G-58 硬闸' not in _v9:
            bad.append('⑨ G-58 硬闸：vmiss>0 时 verdict 必须被挡（实得 %r）' % _v9)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for b in bad:
        print('🔴 %s' % b)
    if bad:
        return 1
    print('✔ accept7-ledger 自证通过（池判据：好样本 1 认 ＋ 坏样本 5 全不认；'
          '右栏状态：状态词表 9 档 ＋ 端到端 1 例；判态计数：G-60 负样本 1 例 —— '
          '格内"提到"✅／🔴／⛔ 时**只认它前面那个判态**；G-58 硬闸：落地日后已裁缺判词路径 1 例拦截 ＋ 3 例豁免）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='蒸馏册 7 条状态单一台账（机器生成 · 只读）')
    ap.add_argument('--selftest', action='store_true', help='自证池判据（G-59），不读盘上数据')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    _FROZEN = _frozen_slugs()
    if _FROZEN:
        print('冻结册（当时决定·跳过，不追）：%s' % '、'.join(sorted(_FROZEN)))

    work = _o.path.join(ROOT, '.work')
    inv = _o.path.join(ROOT, '投资蒸馏')
    rows = []
    missing = []
    _alias_pre = _alias_map()
    _inv_alias = {}
    for _dn, _sl in _alias_pre.items():
        if _o.path.isdir(_o.path.join(inv, _dn)):
            _inv_alias[_sl] = _dn

    # ── 统一扫描：凡 `.work/<task>/` 下**有 read_receipt.json 或 accept7-<task>.md** 的都成行 ──
    #   分类：有收据＝A（现行流程册，R4 射程内）；仅"有 accept7 但无收据"＝B（V4.6 前交付，
    #   本轮已回溯补记录）；有收据但缺 accept7 ⇒ 判缺件（R4 会拦）。
    tasks = []
    for d in sorted(os.listdir(work)) if os.path.isdir(work) else []:
        p = _o.path.join(work, d)
        if not _o.path.isdir(p):
            continue
        has_rc = _o.path.isfile(_o.path.join(p, 'read_receipt.json'))
        p7 = _o.path.join(p, 'accept7-%s.md' % d)
        has_p7 = _o.path.isfile(p7)
        if not (has_rc or has_p7):
            continue
        tasks.append(d)
        cls = 'A' if has_rc else 'B'
        _pre, _pdet = _prereq(d, work)
        # 该册若有对应**册目录**，把册目录里的等价件一并报出（回答"池/技能到底有没有"）：
        #   任务目录缺、册目录有 ⇒ 是"缺落位"；两处都没有 ⇒ 才是真缺。
        _dirc = _inv_alias.get(d)
        if _dirc:
            _pdet += ' ｜册目录 ' + _dir_prereq(_o.path.join(inv, _dirc))
        if has_p7:
            found, ok, bad, nb, st, pend, noword, vmiss, vmiss_rows, warn = parse_accept7(p7)
            _txt7 = io.open(p7, encoding='utf-8').read()
            _comp = is_composite(_txt7)
            _cbad = composite_violations(d, my_rows(p7)) if _comp else []
            _v = verdict(len(found), ok, bad, nb, st, pend, frozen_why=_FROZEN.get(d),
                         n_vmiss=vmiss)
            if _comp:
                _v += ' ｜**复合册汇总行·不单独计数**'
                if _cbad:
                    _v += ' ｜🔴 **汇总不一致**：' + '、'.join('第%d条' % n for n, _m, _w in _cbad)
            rows.append(dict(cls=cls, name=d, slug=d, p7='有', nrows=len(found),
                             ok=ok, bad=bad, nb=nb, st=st, pend=pend, noword=noword, warn=warn,
                             vmiss=vmiss, vmiss_rows=vmiss_rows,
                             pre=_pre, pdet=_pdet, comp=_comp, compbad=_cbad,
                             verdict=_v))
        else:
            missing.append(d)
            rows.append(dict(cls=cls, name=d, slug=d, p7='**缺件**', nrows=0,
                             ok=0, bad=0, nb=0, st=0, pend=0, warn=False,
                             pre=_pre, pdet=_pdet,
                             verdict='未完成（缺 accept7 件）'))

    # ── B 类：投资蒸馏 下的册目录，未进 A 类者（**别名从 bookspec 派生，不写死书名**）──
    a_slugs = set(tasks)
    alias = _alias_map()
    if _o.path.isdir(inv):
        for d in sorted(os.listdir(inv)):
            p = _o.path.join(inv, d)
            if not _o.path.isdir(p) or d in SKIP_DIRS:
                continue
            slug = _match_slug(d, alias)
            if slug and slug in a_slugs:
                # 已有 A 类行（该册有收据）⇒ **不重复列**，只在 A 行上补册名
                for r in rows:
                    if r['slug'] == slug:
                        r['name'] = '%s（%s）' % (d, slug)
                continue
            if slug:
                note = '无 read_receipt（V4.6 前交付·任务目录 `%s` 在但未走现行流程）⇒ accept7 待建' % slug
                slugtxt = slug
            else:
                note = '无任务目录 ⇒ accept7 待建'
                slugtxt = '（无任务目录）'
            rows.append(dict(cls='B', name=d, slug=slugtxt, p7='**无**', nrows=0,
                             ok=0, bad=0, nb=0, st=0, pend=0, warn=False, noaccept=True,
                             pre=0, pdet=_dir_prereq(p),
                             verdict='未完成（%s）' % note))
    # ── 册目录全覆盖（**硬闸**：2026-09-23）────────────────────────────────
    #   为什么必须有：R4 只对 `.work/<task>/` 且**有收据**的任务生效 ⇒
    #   「册目录里有书、但从来没建过任务目录」这一类**对 R4 完全不可见**。
    #   实测代价：**4 册**（书名不写进源码；台账里逐行列名）
    #   因此**一直没有 accept7 件而无人拦**，直到本台账把它们列出来才被发现。
    #   ⇒ 口径：**册目录（B 类）缺 accept7 件 ＝ 待办清单，且必须让 rc≠0**，否则"单一台账"只是张报表。
    #   `SKIP_DIRS` 是**声明的**非册目录排除表（工具/实验/快照类），改动须写进该表的注释。
    missing_dirs = [r['name'] for r in rows if r.get('noaccept')]

    # ── 出表 ──
    L = []
    L.append('# 蒸馏台账 —— 7 条验收状态（**机器生成**·%s）'
             % time.strftime('%Y-%m-%d %H:%M'))
    L.append('')
    L.append('> **本表由 `tools\\accept7-ledger.py` 从 `.work/<task>/accept7-<task>.md` 读出**，'
             '不经任何人的手。')
    L.append('> **完成判据**：判态行 7/7 且 ✅=7 且 **右栏判官裁无"待派"**；'
             '第 6 条按用户 2026-09-23 指令暂缓（⏸ 不阻塞其它 6 条）。'
             '**2026-09-24 起已裁行必附判词件路径（`G-58` 硬闸 · 棘轮：只管落地日后的新裁定）。**')
    L.append('> **标准唯一权威**：`distillation-director-plugin\\SKILL.md` §27。')
    L.append('')
    L.append('| 类 | 册 / 任务 | accept7 件 | 判态行 | ✅ | 🔴 | ⛔ | ⏸ | 待派判官 | **前置（第1条四件）** | 结论 |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        L.append('| %s | %s | %s | %d/7 | %d | %d | %d | %d | %d | %s | %s |'
                 % (r['cls'], r['name'], r['p7'], r['nrows'], r['ok'], r['bad'],
                    r['nb'], r['st'], r['pend'], r.get('pdet', '—'), r['verdict']))
    L.append('')
    n_done = sum(1 for r in rows if r['verdict'].startswith('**完成**'))
    _noncomp = [r for r in rows if not r.get('comp')]
    _comps = [r for r in rows if r.get('comp')]
    n_stall = sum(1 for r in _noncomp if r['verdict'].startswith('暂缓'))
    _compbad = [r for r in _comps if r.get('compbad')]
    n_a = sum(1 for r in rows if r['cls'] == 'A')
    n_b = sum(1 for r in rows if r['cls'] == 'B')
    L.append('## 汇总（机器算，不由人报）')
    L.append('')
    L.append('- 列入台账的册/任务：**%d**（A 类＝有收据的现行册 **%d** ＋ B 类＝V4.6 前交付、本轮回溯补记录的册 **%d** ＋ 无任务目录的册 **%d**）'
             % (len(rows), n_a, n_b, len(rows) - n_a - n_b))
    L.append('- **完成**：**%d**')
    L[-1] = L[-1] % n_done
    L.append('- 暂缓（仅差第 6 条）：**%d**' % n_stall)
    _nw = [(r['name'], r.get('noword', 0)) for r in rows if r.get('noword')]
    L.append('- 右栏**无状态词**的格：**%d** 个%s'
             % (sum(c for _n, c in _nw),
                ('　→　' + '、'.join('%s×%d' % (n, c) for n, c in _nw)) if _nw else '　✔'))
    if _nw:
        L.append('  > 🔴 **`G-58` 报警**：右栏格必须含状态词之一（待派／待判官／待复核／未裁／已派未回 ⇒ **未裁**；'
                 '已裁／已派 ⇒ **已裁**；暂缓／按令未做 ⇒ 不适用）。**一个词都没有 ⇒ 本表的"裁没裁"读不出来**，'
                 '按报警处理（旧版只认「待派」二字，写成「待判官回」即被静默算成已裁）。')
    _vm = [(r['name'], r['vmiss'], r.get('vmiss_rows', '')) for r in rows if r.get('vmiss')]
    if _vm:
        L.append('- 🔴 **`G-58` 硬闸报警（判词路径必填 · 2026-09-24 起）**：%d 册共 **%d** 个落地日后的「已裁」右栏格**未附判词件路径**：%s'
                 % (len(_vm), sum(c for _n, c, _d in _vm),
                    '；'.join('%s（第 %s 条）' % (n, d) for n, c, d in _vm)))
        L.append('  > 裁定必须可回查：已裁格须带 `verdict-….md` 路径（判官任务书本来就要求落判词件）；'
                 '补上真实路径前，该册结论不得为 完成／暂缓。历史裁定（行内日期早于落地日）不追溯。')
    L.append('- 复合册**汇总行**（**不单独计数**）：**%d** 个%s'
             % (len(_comps), ('　→　' + '、'.join(r['slug'] for r in _comps)) if _comps else ''))
    if _comps:
        L.append('- 复合册**一致性机检**（任一子册非 ✅ ⇒ 本册该条不得 ✅）：%s'
                 % ('✔ 全部相容' if not _compbad else '🔴 **不一致 %d 个**：%s'
                    % (len(_compbad), '、'.join('%s（%s）' % (r['slug'], '／'.join('第%d条' % n for n, _m, _w in r['compbad'])) for r in _compbad))))
    L.append('- 缺 accept7 件（＝待建）：**%d**（A 类任务 %d ＋ **B 类册目录 %d**）%s'
             % (len(missing) + len(missing_dirs), len(missing), len(missing_dirs),
                ('　→　' + '、'.join(missing + missing_dirs)) if (missing or missing_dirs) else ''))
    L.append('- 本表**不判质量**：判态取值合法性由 `check_distill_artifacts.py` 的 **R4** 负责；'
             '**存在性**由 R4（有收据的册）＋ **本台账的 rc**（册目录全覆盖）两处一起兜。')
    L.append('')
    txt = '\n'.join(L) + '\n'

    if a.out:
        out = a.out if _o.path.isabs(a.out) else _o.path.join(ROOT, a.out)
        _o.makedirs(_o.path.dirname(out), exist_ok=True)
        io.open(out, 'w', encoding='utf-8', newline='\n').write(txt)
        print('已写：%s（%d 字节）' % (out, len(txt.encode('utf-8'))))
    else:
        print(txt)
    if _compbad:
        for r in _compbad:
            for n, _m, _w in r['compbad']:
                print('🔴 复合册 %s：本册第 %d 条记 %s，而子册里有 %s ⇒ 违反「任一子册非 ✅ ⇒ 本册不得 ✅」'
                      % (r['slug'], n, _m, _w))
    if missing or missing_dirs or _compbad:
        if missing:
            print('⚠ 缺 accept7 件的任务 %d 个：%s' % (len(missing), '、'.join(missing)))
        if missing_dirs:
            print('🔴 册目录缺 accept7 件 %d 个（R4 射程外、本台账兜底）：%s'
                  % (len(missing_dirs), '、'.join(missing_dirs)))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
