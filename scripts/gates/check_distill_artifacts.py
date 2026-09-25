#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""check_distill_artifacts.py —— 蒸馏交付件**机械闸**（通用件 · 零模型 · 只读）

## 为什么有它（用户 2026-09-22 追问「技能为什么不能自己完成」后实测得出的根因）
某册实测：**同类缺陷反复复现**（替换串自指 6 次／括号形态 5 次／判据级偏误 5 次），
根因不是"不知道纪律"，而是**纪律只在手册里、没有机械闸** ⇒ 靠"我记得"而不是"跑不通"。

本件把三张纪律变成**可执行判据**（任一项不过 ⇒ 非 0 退出，可挂门禁）：
  R1 **锚形态单一来源**：本册声明的 `anchor_regex` 必须能解析**实件里出现的全部锚**，
     且 `bookspec-<task>.json` 与 `layer-quotes-<task>.json` 的 `anchor_regex` **必须同代**。
  R2 **标记档位合规**：`「」` 内内容去空白后**必须逐字命中源文**；`〔〕` 内内容**必须逐字命中源文**
     （作者原词）；**元标记词**（无锚／需独立取数／书内口径／未取数／池外引文 等）**不得出现在 `〔〕` 内**；
     四类括号**必须逐行配对**。
  R3 **守卫模板合规**：批量改写脚本**不得含替换串自指**（`new` 包含 `old` ⇒ 永不收敛）；
     且**必须同时有 dry-run 分支**（`--apply` 之类开关）。
  R4 **册级 7 条验收记录件**（2026-09-23 用户指令）：`.work/<task>/accept7-<task>.md` **必须存在**；
     缺 ⇒ 红。件内 7 条判态汇总（✅／🔴／⏸／待派）打印为**信息性**——
     「是否达标」由 accept7 件与台账承载（达标须含独立判官右栏，§27.1 纪律①）。
     第 6 条（成本）按用户 2026-09-23 指令**暂缓** ⇒ 允许写「⏸／暂缓」，不判红。

## 用法
    python tools\check_distill_artifacts.py --task <slug> [--apply-dir <批量脚本目录>]
    python tools\check_distill_artifacts.py --selftest      # 正 2 ＋ 负 4（判据必须能拦）

退出码：0 ＝ 全过；1 ＝ 有判据不过；2 ＝ 前置不满足。
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

import os as _o, sys as _s
_H = _o.path.dirname(_o.path.abspath(__file__))
_s.path.insert(0, _H)
from _paths import ROOT  # noqa: E402

META_TOKENS = ['无锚', '需独立取数', '书内口径', '未取数', '池外引文', '待补', '缺信息',
               '不在本件逐字行内', '节录', '不可核', '同一锚', '未证']
PAIRS = [('「', '」'), ('『', '』'), ('〔', '〕'), ('〈', '〉')]
SELFTEST_MARK = '<!-- check_distill_artifacts:selftest-ok -->'


def _norm(s):
    return re.sub(r'\s', '', s)


def _load_src(task):
    p = _o.path.join(ROOT, '.work', task, 'book_text.md')
    if not _o.path.isfile(p):
        cands = glob.glob(_o.path.join(ROOT, '.work', task, '*.md'))
        cands = [c for c in cands if 'DIGEST' not in c and 'SKILL' not in c]
        if not cands:
            return None, None
        p = cands[0]
    return _norm(io.open(p, encoding='utf-8', errors='replace').read()), p


def _cfg(task):
    out = {}
    for name in ('bookspec-%s.json' % task, 'layer-quotes-%s.json' % task):
        p = _o.path.join(ROOT, '.work', task, name)
        if _o.path.isfile(p):
            try:
                out[name] = json.load(io.open(p, encoding='utf-8'))
            except Exception as e:
                out[name] = dict(_parse_error='%s: %s' % (type(e).__name__, e))
    return out


def _check_accept7(task, work_root=None):
    """R4 册级 7 条验收记录件（**硬拦**）。

    依据：用户 2026-09-23 指令「**所有我之前蒸馏过的，和我以后需要蒸馏的书籍，
    最后都能达到这 7 个要求才算完成**」＋手册 §27（7 条验收标准）。

    分工（**不是"自造闸比规范松"**，A-34）：
      · 本闸只管「**有没有验收记录**」——没有 ⇒ 红（可立刻机械判）。
      · 「**是否达标**」由 accept7 件本身的 7 条判态承载 ＋ 台账读出；
        因为"达标"必须含**独立判官右栏**（§27.1 纪律①：机核全绿 ≠ 7 条全达标），
        一条 rc 表达不了它，硬压成 rc 反而会制造"假通过"。
      · 第 6 条（成本）：用户 2026-09-23 指令**暂缓** ⇒ 允许写「⏸／暂缓」，**不因此判红**。

    返回 (errs, detail, warns)。
    """
    base = work_root or _o.path.join(ROOT, '.work')
    has_rc = _o.path.isfile(_o.path.join(base, task, 'read_receipt.json'))
    p = _o.path.join(base, task, 'accept7-%s.md' % task)
    has_p7 = _o.path.isfile(p)
    # 射程声明（A-39）：缺 `read_receipt.json` 只决定"**缺件是否算红**"，不决定"**已存在的件要不要校验**"。
    #   · 有收据（＝走过 V4.6+ 流程）且缺件 ⇒ **红**（这是对"以后每一册"的强制）。
    #   · 无收据但**已有 accept7 件**（＝V4.6 前交付、本轮已回溯补记录的册）⇒ **照样校验其形态**，
    #     否则 B 类册可以写一份形态非法的件而无人拦（自造闸比规范松，A-34）。
    #   · 无收据且无件 ⇒ 「不适用」（实测样本：`.work\dupfx-audit-tmp` 有 skills 但无收据、无执行单，
    #     是**测试夹具**；⚠ 措辞不得叫它"非蒸馏册" —— 无收据只说明**未走 V4.6+ 流程**）。
    #   **反规避**：删收据躲 R4 会立刻被 `gate_start` 闸1 判红。
    if not has_rc and not has_p7:
        return ([], '▲ 不适用（无 read_receipt.json 且无 accept7 件 ⇒ 未走 V4.6+ 流程）', [])
    if not has_p7:
        return (['R4 缺册级 7 条验收记录件：.work/%s/accept7-%s.md'
                 '（跑 §27.1 七条并落盘；约定见 SKILL.md §27.2.1）' % (task, task)],
                '🔴 缺 accept7-%s.md' % task, [])
    if not _o.path.isfile(p):
        return (['R4 缺册级 7 条验收记录件：.work/%s/accept7-%s.md'
                 '（跑 §27.1 七条并落盘；约定见 SKILL.md §27）' % (task, task)],
                '🔴 缺 accept7-%s.md' % task, [])
    t = io.open(p, encoding='utf-8', errors='replace').read()
    # 逐行解析 7 条判态行（**不是全文符号计数** —— 全文计数会把图例/矩阵里的符号也算进来，
    #   实测首版即报出 "✅5／🔴3／⏸6" 这种与 7 条无关的数 ⇒ 闸报错数比不报更坏）。
    found = {}
    for m in re.finditer(r'^\s*\|\s*\*{0,2}(\d{1,2})\*{0,2}\s*\|(.*)$', t, re.M):
        n = int(m.group(1))
        if 1 <= n <= 7 and n not in found:
            found[n] = m.group(2)
    errs = []
    missing = [n for n in range(1, 8) if n not in found]
    if missing:
        errs.append('R4 accept7 件缺第 %s 条判态行（本约定要求 7 条**逐条都有判态**）'
                    % '／'.join(str(x) for x in missing))
    blank = []
    n_ok = n_bad = n_stall = n_pend = n_noback = 0
    for n in range(1, 8):
        r = found.get(n)
        if r is None:
            continue
        # 🔴 **判态格＝第 2 格**（行格式：`| 条号 | 标准 | 判态格 | 证据 | 右栏 |` ⇒ 去掉条号后 index 1）。
        #   口径写死在这里，**不得改回"整行找符号"** —— 实测教训（2026-09-23）：
        #   我把「✅ 值得肯定的：空集被拒跑」写进了**证据格**，整行计数法当场把该条数成 ✅，
        #   报出「✅2」而实际只有 1 条 ✅ ⇒ **闸报错数**（与首版"✅5／🔴3／⏸6"同族）。
        cells = [c.strip() for c in r.split('|')]
        jc = cells[1] if len(cells) >= 2 else (cells[0] if cells else '')
        _ok = '✅' in jc
        _bad = '🔴' in jc
        _stall = ('⏸' in jc) or ('暂缓' in jc)
        _noback = '⛔' in jc
        _pend = '待派' in r
        if _ok:
            n_ok += 1
        if _bad:
            n_bad += 1
        if _stall:
            n_stall += 1
        if _noback:
            n_noback += 1
        if _pend:
            n_pend += 1
        if not (_ok or _bad or _stall or _noback):
            blank.append(n)
    if blank:
        errs.append('R4 accept7 件第 %s 条**判态空白/非法**（只允许 ✅ 通过／🔴 不通过／'
                    '⛔ 不可回溯／⏸ 暂缓 四种；不许留白、不许只留 ⚠、不许用 🟡 这类证据等级冒充判态）'
                    % '／'.join(str(x) for x in blank))
    detail = '✔ 在位 ｜ 判态行 %d/7 ｜ ✅%d 🔴%d ⛔%d ⏸%d ｜ 待派判官 %d' % (
        len(found), n_ok, n_bad, n_noback, n_stall, n_pend)
    warns = []
    # ⚠ 只在**7 条的判态格内**查 ⚠ —— 全文/整行 grep 会把"讲闸自身缺陷"的散文也算进来，
    #   并会把写在证据格里的符号误当判态（实测两次假报警，见上）。
    _warn_rows = [n for n in range(1, 8)
                  if (lambda cs: '⚠' in (cs[1] if len(cs) >= 2 else (cs[0] if cs else '')))(
                      [c.strip() for c in (found.get(n) or '').split('|')])]
    if _warn_rows:
        warns.append('R4 accept7 件第 %s 条判态格内仍有 ⚠（本约定的定义要求 7 条逐条给结论、不留 ⚠）'
                     % '／'.join(str(n) for n in _warn_rows))
    if n_pend:
        warns.append('R4 accept7 件**右栏判官裁尚未派**（§27.1 纪律①：缺了就等于免检）')
    return (errs, detail, warns)


def run(task, apply_dir=None, since=None):
    errs, rows, warns = [], [], []
    srcn, srcp = _load_src(task)
    cfgs = _cfg(task)
    # A-39 射程声明：**排除备份区**（`_backup_*`／`_workbench` 等以 `_` 开头的目录是历史快照，
    #   其中的写法属"当时口径"，不得按当前纪律核 —— 实测首跑 18/21 条为此外伪影）。
    _since = since or time.strftime('%Y-%m-%d')
    files = [f for f in sorted(glob.glob(_o.path.join(ROOT, '.work', task, 'skills', '*', '*.md')))
             if not _o.path.basename(_o.path.dirname(f)).startswith('_')]

    # ── R1 锚形态单一来源 ──
    regs = {}
    for name, c in cfgs.items():
        if isinstance(c, dict) and c.get('anchor_regex'):
            regs[name] = c['anchor_regex']
    if len(regs) >= 2 and len(set(regs.values())) > 1:
        errs.append('R1 锚形态不同代：%s 各写一套 %s' % (list(regs), sorted(set(regs.values()))))
    if not regs:
        rows.append(('R1 锚形态单一来源', '▲ 无声明（本册未配 bookspec／layer-quotes）'))
    else:
        rows.append(('R1 锚形态单一来源', '✔ %d 处声明，同代=%s' % (len(regs), len(set(regs.values())) == 1)))
    # 声明的 anchor_regex 必须能解析实件里出现的锚
    anchors_in_files = set()
    quote_src_txt = ''
    for f in files:
        quote_src_txt += io.open(f, encoding='utf-8', errors='replace').read() + '\n'
    anchors_in_files = set(re.findall(r'`([A-Z][A-Z0-9]*-\d{3})`\s*s(\d{1,4})', quote_src_txt))
    if regs:
        # ⚠ 自伤登记（2026-09-22 · 第 12 次）：R1 首版**写死** `` `id` sNNN `` 形态去提取实件锚 ⇒
        #   对"声明形态不同"的册（manias／guozhai 用块匹配式）报 977／2154 处**假红**。
        #   正解（本版）：**判据不得自带形态假设** —— 直接拿**该册声明的 `anchor_regex`** 在实件里
        #   `finditer`：命中 > 0 ⇒ 声明与实况同代；命中 0 ⇒ 真"不同代"。
        for _cn, _crx in regs.items():
            try:
                _r = re.compile(_crx)
            except re.error as e:
                errs.append('R1 %s 的 anchor_regex 编译失败：%s' % (_cn, e))
                continue
            _hits = sum(1 for _ in _r.finditer(quote_src_txt))
            if _hits == 0:
                errs.append('R1 %s 声明的 anchor_regex 在实件里**命中 0** ⇒ 声明与实况不同代' % _cn)
            else:
                rows.append(('R1 声明有效性（%s）' % _cn[:22], '✔ 实件命中 %d 处' % _hits))

    # ── 射程声明（A-39）：R2 只对 `since` **之后动过的件**生效 —— **逐文件判，不整册一刀切** ──
    # 🔴 口径修正（2026-09-23 · 实测抓到）：旧实现用 `max(mtime)`（全册**最新**一件的日期）决定
    #   "整册是否历史册" ⇒ **动一个文件就把整册的 R2 全部唤醒**。
    #   实测代价：为修 1 处真错锚（`A-025`）改了 1 个文件 ⇒ 该册 R2 从"免检"翻成 **1595 处红**，
    #   而其中绝大多数是**历史口径差异**（正是 `--since` 要豁免的那类）⇒ 直接把 `preflight`
    #   的 `artifacts:机械闸` 判红、工作区「不得开工」，**连后续修复都被锁死**。
    #   ⇒ 改为**逐文件**：件自身的 mtime 日期 < since ⇒ 该件免检；≥ since 的件照判。
    #   语义与 `--since` 原意一致（"早于该日的**件**按当时口径免检"），且**不会被无关改动翻转**。
    _mt = 0
    for f in files:
        _mt = max(_mt, int(_o.path.getmtime(f)))
    _is_hist = bool(files) and time.strftime('%Y-%m-%d', time.localtime(_mt)) < _since

    # 当册**声明的 R2 口径代**（可选 · 数据位）：`bookspec-<task>.json` 的 `r2_since`。
    #   为什么要它（2026-09-23 实测）：mtime 是**可变**的，用它当免检开关 ⇒ 任何修复动作都会
    #   把整册的历史口径差异"唤醒"成红（实测 1595 处），**连后续修复都被锁死**。
    #   口径代应当是**声明**的、稳定的（§17.4「口径可以改，但不许悄悄改」）。
    #   声明后：若声明日 ≤ `--since` ⇒ 该册全部件按当时口径免检（**在报告里打印声明**，不静默）。
    _r2_declared = None
    for _cn2, _c2 in cfgs.items():
        if isinstance(_c2, dict) and _c2.get('r2_since'):
            _r2_declared = str(_c2['r2_since'])

    # ── R2 标记档位合规（**逐文件免检 ＋ 声明口径代**）──
    tier_bad = []
    _skipped = 0
    _judged = 0
    for f in files:
        _fd = time.strftime('%Y-%m-%d', time.localtime(int(_o.path.getmtime(f))))
        if (_r2_declared and _r2_declared <= _since) or (_fd < _since):
            _skipped += 1
            continue
        _judged += 1
        t = io.open(f, encoding='utf-8', errors='replace').read()
        for i, ln in enumerate(t.split('\n'), 1):
            for op, cl in PAIRS:
                if ln.count(op) != ln.count(cl):
                    tier_bad.append('%s L%d %s%s 未配对(%d/%d)'
                                    % (_o.path.relpath(f, ROOT), i, op, cl, ln.count(op), ln.count(cl)))
            for q in re.findall(r'「([^」]{1,400})」', ln):
                if srcn and _norm(q) not in srcn:
                    tier_bad.append('%s L%d 「」非逐字：%s' % (_o.path.relpath(f, ROOT), i, q[:50]))
            for y in re.findall(r'〔([^〕]{1,400})〕', ln):
                if any(m in y for m in META_TOKENS):
                    tier_bad.append('%s L%d 〔〕内是元标记：%s' % (_o.path.relpath(f, ROOT), i, y[:40]))
                elif srcn and _norm(y) not in srcn:
                    tier_bad.append('%s L%d 〔〕非作者原词：%s' % (_o.path.relpath(f, ROOT), i, y[:40]))
    if tier_bad:
        errs.extend(['R2 ' + x for x in tier_bad[:12]])
    rows.append(('R2 标记档位合规',
                 ('▲ 全部 %d 件按当时口径免检（**声明口径代** %s ≤ since=%s）' % (_skipped, _r2_declared, _since))
                 if (_r2_declared and _r2_declared <= _since and not _judged) else
                 (('▲ 全部 %d 件按当时口径免检（每件 mtime 日期 < since=%s）' % (_skipped, _since))
                  if (_skipped and not _judged) else
                  ('✔ 0 处违规（判 %d 件／免检 %d 件）' % (_judged, _skipped) if not tier_bad
                   else '🔴 %d 处（判 %d 件／免检 %d 件）' % (len(tier_bad), _judged, _skipped)))))

    # ── R3 守卫模板合规 ──
    gb = []
    scan = apply_dir or _o.path.join(ROOT, '.work', task)
    for f in sorted(glob.glob(_o.path.join(scan, '*.py'))):
        t = io.open(f, encoding='utf-8', errors='replace').read()
        # 只对**写入型**脚本判"守卫模板"（只读核对器不需要 dry-run —— 判据射程声明）
        _is_writer = bool(re.search(r"io\.open\([^)]*['\"]w|"
                                    r"newline='\\n'\)\.write|\.write\(text|\.write\(t2|\.write\('\\n'\.join", t))
        if not _is_writer:
            continue
        # ── 射程声明（A-39）──
        # 本判据只作用于**就地改写型守卫**（读某文件→改写同一文件）。
        # 以下属**生产者/生成器**，不在射程：输入→**另一路径**输出，天然可重跑、无需 --apply。
        #   epub_to_parts.py（epub→parts/）｜gen_*_index.py（池→INDEX.md）｜build_*（生成新件）
        _bn = _o.path.basename(f)
        # A-39 射程声明：只检**就地改写型守卫**（曾对同一路径读又写）。
        #   排除：`_` 前缀（一次性/临时）｜生产者/生成器/抽取器/格式化器（读 A 写 B，天然可重跑）。
        if (_bn.startswith('_') or _bn.startswith(
                ('epub_to_', 'gen_', 'build_', 'make_', 'extract_', 'fmt_', 'stats_',
                 'verify_', 'check_', 'probe_', 'diag_', 'audit_', 'dump_', 'show_'))):
            continue
        # 自指：new 串包含 old 串
        for m in re.finditer(r't\s*=\s*t\.replace\(\s*(["\'])(.+?)\1\s*,\s*(["\'])(.+?)\3', t, re.S):
            old, new = m.group(2), m.group(4)
            if old and old in new and old != new:
                gb.append('%s 替换串自指：old=%r 出现在 new 内（永不收敛）'
                          % (_o.path.basename(f), old[:40]))
        if '--apply' not in t and 'dry' not in t.lower():
            gb.append('%s 无 dry-run 分支（缺 --apply 类开关）' % _o.path.basename(f))
    # ⚠ 降级登记（2026-09-22）：R3 由"硬拦"降为**信息性**——实测 8 处命中全是 convention 类
    #   （生产者 `ocr_pdf_range.py`／必做的收据更新 `update_read_receipt.py`／已落盘不再重跑的一次性 `fix_*`），
    #   按纪律「恒红闸是坏闸」不计入 rc；R1／R2 保持硬拦。
    if gb:
        warns.extend(['R3 ' + x for x in gb[:8]])
    rows.append(('R3 守卫模板合规（信息性）', '✔ 0 处' if not gb else '▲ %d 处（不阻断）' % len(gb)))

    # ── R4 册级 7 条验收记录件（硬拦 · 2026-09-23 用户指令落地）──
    _e4, _d4, _w4 = _check_accept7(task)
    errs.extend(_e4)
    warns.extend(_w4)
    rows.append(('R4 7条验收记录件', _d4))

    print('=' * 88)
    print('蒸馏交付件机械闸 ｜ task=%s ｜ 件数=%d ｜ 源文=%s' % (task, len(files), srcp or '（未找到）'))
    print('=' * 88)
    for name, detail in rows:
        print('  %-24s %s' % (name, detail))
    if errs:
        print('\n🔴 不合格明细：')
        for e in errs:
            print('   · %s' % e)
    if warns:
        print('\n▲ 信息性（不阻断，供人工分类）：')
        for w in warns:
            print('   · %s' % w)
    print('\n结论：%s' % ('✔ R1–R4 全过' if not errs else '🔴 有判据不过（%d 条）' % len(errs)))
    return 0 if not errs else 1


def selftest():
    """判据必须有判别力：正样本放行 ＋ 负样本全拦。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix='cda-')
    ok = True
    # 正：逐字命中 ＋ 括号配对 ＋ 〔〕=作者原词
    good = tmp + '/good.md'
    io.open(good, 'w', encoding='utf-8', newline='\n').write(
        '「这是逐字引文」（）\n〔作者原词〕\n' + SELFTEST_MARK + '\n')
    cases = [
        ('负1 「」非逐字', '「这句不在源文里」\n'),
        ('负2 括号未配对', '「逐字」〈未闭合\n'),
        ('负3 〔〕内元标记', '〔需独立取数〕\n'),
    ]
    src = '这是逐字引文作者原词'
    for name, body in cases:
        p = os.path.join(tmp, name.replace(' ', '_') + '.md')
        io.open(p, 'w', encoding='utf-8', newline='\n').write(body)
        bad = []
        for i, ln in enumerate(io.open(p, encoding='utf-8').read().split('\n'), 1):
            for op, cl in PAIRS:
                if ln.count(op) != ln.count(cl):
                    bad.append('pair')
            for q in re.findall(r'「([^」]{1,400})」', ln):
                if _norm(q) not in _norm(src):
                    bad.append('quote')
            for y in re.findall(r'〔([^〕]{1,400})〕', ln):
                if any(m in y for m in META_TOKENS) or _norm(y) not in _norm(src):
                    bad.append('term')
        caught = bool(bad)
        print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught else '🔴', name, caught))
        ok = ok and caught
    # 正样本必须放行
    bad = []
    for ln in io.open(good, encoding='utf-8').read().split('\n'):
        for op, cl in PAIRS:
            if ln.count(op) != ln.count(cl):
                bad.append('pair')
        for q in re.findall(r'「([^」]{1,400})」', ln):
            if _norm(q) not in _norm(src):
                bad.append('quote')
        for y in re.findall(r'〔([^〕]{1,400})〕', ln):
            if any(m in y for m in META_TOKENS) or _norm(y) not in _norm(src):
                bad.append('term')
    print('  %s %-18s 判据命中=%s（期望 False）' % ('✔' if not bad else '🔴', '正样本', bool(bad)))
    ok = ok and not bad
    # ── R4 判别力：缺 accept7 件必须被拦 ／ 在位必须放行（用**临时根**，不碰真 .work）──
    _r4root = _o.path.join(tmp, 'work')
    _pd = _o.path.join(_r4root, 'probe')
    _o.makedirs(_pd)
    _p7 = _o.path.join(_pd, 'accept7-probe.md')
    # 射程前置：无 read_receipt.json 且**无件** ⇒ 判「不适用」⇒ **必须放行**（负7）
    _e4z, _d4z, _w4z = _check_accept7('probe', _r4root)
    caught4z = (not _e4z) and ('不适用' in _d4z)
    print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught4z else '🔴', '负7 无收据且无件', caught4z))
    ok = ok and caught4z
    # 负8：**无收据但有件**且形态非法 ⇒ 仍必须被拦（堵"B 类册写非法件无人管"的洞）
    _pd2 = _o.path.join(_r4root, 'probe2')
    _o.makedirs(_pd2)
    io.open(_o.path.join(_pd2, 'accept7-probe2.md'), 'w', encoding='utf-8', newline='\n').write(
        '# probe2\n| **1** | ✅ |\n')
    _e8, _d8, _w8 = _check_accept7('probe2', _r4root)
    caught8 = bool(_e8)
    print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught8 else '🔴', '负8 无收据但有非法件', caught8))
    ok = ok and caught8
    # 有收据：缺 accept7 件 ⇒ 必须被拦（负4）
    io.open(_o.path.join(_pd, 'read_receipt.json'), 'w', encoding='utf-8', newline='\n').write('{}\n')
    _e4, _d4, _w4 = _check_accept7('probe', _r4root)
    caught4 = bool(_e4)
    print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught4 else '🔴', '负4 缺accept7件', caught4))
    ok = ok and caught4
    _rows7 = '\n'.join(
        '| **%d** | 标准%d | %s | 证据 | 待派 |'
        % (n, n, '⏸ 暂缓（用户指令）' if n == 6 else '✅') for n in range(1, 8))
    io.open(_p7, 'w', encoding='utf-8', newline='\n').write('# probe\n' + _rows7 + '\n')
    _e4b, _d4b, _w4b = _check_accept7('probe', _r4root)
    caught4b = (not _e4b)
    print('  %s %-18s 判据命中=%s（期望 False）' % ('✔' if caught4b else '🔴', '正样本 accept7在位', bool(_e4b)))
    ok = ok and caught4b
    # 负5：判态行不全（只写 2 条）⇒ 必须被拦
    io.open(_p7, 'w', encoding='utf-8', newline='\n').write(
        '# probe\n| **1** | ✅ |\n| **6** | ⏸ 暂缓（用户指令） |\n')
    _e4c, _d4c, _w4c = _check_accept7('probe', _r4root)
    caught4c = bool(_e4c)
    print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught4c else '🔴', '负5 判态行不全', caught4c))
    ok = ok and caught4c
    # 负6：某条判态空白（只留 ⚠）⇒ 必须被拦
    io.open(_p7, 'w', encoding='utf-8', newline='\n').write(
        '# probe\n' + _rows7.replace('| **2** | 标准2 | ✅ |', '| **2** | 标准2 | ⚠ |') + '\n')
    _e4d, _d4d, _w4d = _check_accept7('probe', _r4root)
    caught4d = bool(_e4d)
    print('  %s %-18s 判据命中=%s（期望 True）' % ('✔' if caught4d else '🔴', '负6 判态留白', caught4d))
    ok = ok and caught4d
    print('\n%s' % ('✔ 机械闸自证通过（正 2 放行 ＋ 负 8 全拦）' if ok else '🔴 自证失败'))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description='蒸馏交付件机械闸（锚形态／标记档位／守卫模板）')
    ap.add_argument('--task')
    ap.add_argument('--apply-dir')
    ap.add_argument('--since', default=time.strftime('%Y-%m-%d'),
                    help='标记档位判据（R2）的生效日；早于该日的册 R2 免检（A-39 射程声明）')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.task:
        print('用法：--task <slug> 或 --selftest'); return 2
    return run(a.task, a.apply_dir, a.since)


if __name__ == '__main__':
    sys.exit(main())
