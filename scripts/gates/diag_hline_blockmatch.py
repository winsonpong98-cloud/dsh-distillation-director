# -*- coding: utf-8 -*-
r"""diag_hline_blockmatch.py —— 「条目头正则」形态普查器（**只读诊断**，不给结论）

BANDID-OK-FILE: 本文件是**诊断器**，**故意**枚举历史残缺写法做对照实验，
  故不引用 `_bandid` 的语法常量（引用它就没得对照了）。
  这是 `tools\check_bandid_single_source.py` 允许的**文件级**豁免之一（另一处＝闸自身）。

## 为什么留这个文件（2026-09-19 重写 · A-132）

它第一次被写出来时，是为了查 `### ST-001` 形头被判"切块为空"的原因，
当时的结论是「正确写法＝`[A-Za-z]+`」并据此改了 `verify_candidates.py`。
**那个结论是错的（只对 `ST-` 对，对 `E1-` 错）**：`[A-Za-z]+` 吃不到「字母＋数字」波段
（NAS 册 `cn-pop-2100` 的 `E1..E6`）⇒ 换了一批书之后**同一个脚本对合规产出报假红**。

**本次重写不再"给结论"，只做形态普查**：把 4 种历史写法与现行唯一真源
（`_bandid.BAND = [A-Za-z][A-Za-z0-9]*`）**并排列出**，对 6 个波段形态逐一实测，
让"每种窄写法各漏哪一册"变成一张**可当场看懂的对照表**——
因为"改判据只放宽一点"这件事已经复发 4 次，靠记性挡不住，只能靠这张表。

用法：python tools\diag_hline_blockmatch.py
"""
import argparse
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402

# ── 对照实验用的 5 把尺子（**故意内联**，见文件头 bandid-waiver）───────────────────
#   ①…④ = 历史上真实存在过的写法（各自"修"过一次，每次都修坏另一形态）
#   ⑤   = 现行唯一真源（`tools\_bandid.py` 的 BAND）
RULERS = [
    ('① `[A-Za-z]\\d+`（最初）', r'[A-Za-z]\d+'),
    ('② `[A-Za-z]\\d*`（第 1 次修）', r'[A-Za-z]\d*'),
    ('③ `[A-Za-z][0-9]*`（第 2 次修 · gate_stage 曾用）', r'[A-Za-z][0-9]*'),
    ('④ `[A-Za-z]+`（第 3 次修 · verify_candidates 曾用）', r'[A-Za-z]+'),
    ('⑤ `[A-Za-z][A-Za-z0-9]*`（★ 现行真源 _bandid.BAND）', r'[A-Za-z][A-Za-z0-9]*'),
]

# 实册波段形态（全部来自真实产出，不是编的）
FORMS = [
    ('A-001', 'manias-crashes 册（波段 A..G）'),
    ('T1-001', 'adhd-pro 册（波段 T1..T6）'),
    ('E1-001', 'cn-pop-2100 册（NAS 实测 · 波段 E1..E6）'),
    ('ST-001', '换书准备批正样本（双字母前缀）'),
    ('B12-005', '文档里出现过的三位波段号'),
    ('2024-001', '**负样本**（年份/页码，应被全部拦下）'),
]


def census():
    """**真实数据普查**：对工作区里每一册的 `candidates/notes_*.md`，
    分别用 5 把尺子数条目数 ⇒ 一眼看出"哪把尺子把哪一册判成 0 条"。

    为什么必须跑真实数据（本项目纪律 A-29 家族：格式类判据须先做形态普查）：
      * 合成样本只能证明"尺子能吃这个字符串"，证明不了"**在役册的产出**被吃住";
      * 2026-09-17 那次"旧册回归一致"的结论，就是**只对了一册**得出的
        （当时那册的波段名恰好是单字母），换册即假红 ⇒ **回归必须跨册**。
    """
    import glob
    tasks = sorted(glob.glob(os.path.join(ROOT, '.work', '*', 'candidates')))
    if not tasks:
        print('⚠ 未找到任何 .work/*/candidates 目录 —— 无可普查的真实数据')
        return 0
    rows = []
    for cand in tasks:
        task = os.path.basename(os.path.dirname(cand))
        files = sorted(p for p in glob.glob(os.path.join(cand, 'notes_*.md'))
                       if '.bak' not in p and 'pre-repair' not in p)
        if not files:
            continue
        counts = []
        for _, band in RULERS:
            rx = re.compile(r'^###\s+' + band + r'-\d{3}\s+\[', re.M)
            n = 0
            for f in files:
                n += len(rx.findall(io.open(f, encoding='utf-8', errors='replace').read()))
            counts.append(n)
        # 真实波段名样本（取首条条目头里的波段，供人核对形态）
        sample = ''
        for f in files:
            t = io.open(f, encoding='utf-8', errors='replace').read()
            m = re.search(r'^###\s+(\S+?)-(\d{3})\s+\[', t, re.M)
            if m:
                sample = '%s-%s' % (m.group(1), m.group(2))
                break
        rows.append((task, len(files), sample, counts))
    print('真实数据普查（条目总数 · 5 把尺子并排）')
    print('=' * 96)
    print('%-26s %-5s %-12s %s' % ('册（.work/<task>）', '文件', '首条 id',
                                   '    ①     ②     ③     ④     ⑤'))
    print('-' * 96)
    for task, nf, sample, counts in rows:
        star = ' ★' if len(set(counts)) > 1 else ''
        print('%-26s %-5d %-12s %s%s' % (task, nf, sample,
                                         '  '.join('%6d' % c for c in counts), star))
    print('=' * 96)
    print('列序（左→右）：①[A-Za-z]\\d+  ②[A-Za-z]\\d*  ③[A-Za-z][0-9]*  ④[A-Za-z]+  ⑤[A-Za-z][A-Za-z0-9]*（真源）')
    print('带 ★ 的行＝**该册在 5 把尺子下条目数不一致** ⇒ 说明"用哪把尺子"决定了判决（A-132 的病灶）')
    any_star = any(len(set(c)) > 1 for _, _, _, c in rows)
    if not any_star:
        print('（本次未出现不一致 —— 但仍须用真源：一致性只说明本批册的波段形态恰好同族）')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--census', action='store_true',
                    help='对工作区真实册做条目数普查（跨册回归证据）')
    a = ap.parse_args()
    if a.census:
        return census()
    print('条目头正则形态普查（只读）· 工作区根：%s' % ROOT)
    print('被测行模板：`### <id>  [PR] [技能=建议]`（id 与 [类型] 之间是**两个空格**，与官方模板一致）')
    print('=' * 96)
    head = '%-58s %s' % ('尺子（波段前缀写法）', '  '.join('%-9s' % f[0] for f in FORMS))
    print(head)
    print('-' * 96)
    for name, band in RULERS:
        full = r'^###\s+(' + band + r')-(\d{3})\s+\[([A-Z]{2})\]\s+\[技能=([^\]]*)\](?:\s+(.*))?$'
        rx = re.compile(full, re.M)
        cells = []
        for pid, _ in FORMS:
            line = '### %s  [PR] [技能=建议]' % pid
            cells.append('✔ 命中' if rx.match(line) else '✗ 漏掉')
        print('%-58s %s' % (name, '  '.join('%-9s' % c for c in cells)))
    print('-' * 96)
    for pid, desc in FORMS:
        print('  %-10s %s' % (pid, desc))
    print('=' * 96)
    # 结论：由对照表自行读出（本脚本**不下结论**，只报数）
    ok_all = []
    for name, band in RULERS:
        rx = re.compile(r'^###\s+(' + band + r')-(\d{3})\s+\[([A-Z]{2})\]\s+\[技能=([^\]]*)\]', re.M)
        pos = [pid for pid, _ in FORMS[:5]]
        hit = [pid for pid in pos if rx.match('### %s  [PR] [技能=建议]' % pid)]
        neg_pass = bool(rx.match('### 2024-001  [PR] [技能=建议]'))
        ok_all.append((name, len(hit), len(pos), neg_pass))
    print('对**正样本**的覆盖（5 个真实形态）／负样本是否误收：')
    for name, k, n, neg in ok_all:
        print('  %-58s %d/%d  负样本误收=%s' % (name, k, n, '是 🔴' if neg else '否 ✔'))
    print('=' * 96)
    print('读表要点：**①…④ 没有一把能吃全 5 个真实形态**（这就是"改判据只放宽一点"的代价）；')
    print('          ⑤ 覆盖 5/5 且不误收负样本 ⇒ 唯一真源 `tools\\_bandid.py`。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
