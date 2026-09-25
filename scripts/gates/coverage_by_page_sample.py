# -*- coding: utf-8 -*-
r"""coverage_by_page_sample.py —— **页级**取材覆盖核验（防线4 的页级版 · 任务通用）

为什么要它（2026-09-20 能力审计发现的缺口）：
  现有的 `coverage_by_chapter.py` 只核到**章节级**（"每章零贡献须有理由"），
  判态 PASS 的同时，产物自己写着边界声明「**未**逐页核对 425 页里每页是否都被读过」。
  ⇒ 用户要的"不丢细节"缺一层证据。本工具补这一层：**逐页清点 ＋ 抽样核验 ＋ 零覆盖簇告警**。

判据（只做确定性的"锚→页"计数，不做内容价值判断）：
  · 页集合 = 源文的页标记（**唯一权威**：`verify_candidates.detect_pagemark()` ＋ `PAGEMARK_ANY_MARK`）；
  · 候选页集合 = 候选池每条 `- 锚：sN`（含区间 `sN-M`）归一到页号（**唯一权威**：`verify_candidates.ANCHOR`）；
  · 零覆盖页 = 页集合 − 候选页集合；
  · 连续零覆盖簇 = 零覆盖页中长度 ≥ `--min-run` 的连续段（**最可疑的漏读形态**，须逐段给理由）；
  · 抽样 = 从**零覆盖页**（无则全页）里按固定 seed 抽 `--sample` 页，供逐页核理由。

⚠ 三个必须与结果一起读的边界（不许省略）：
  ① **零候选 ≠ 没读**：提取器按波段读完全书，只产出**有选择**的条目；本工具出的是
     「**待核清单**」，不是「漏读清单」——理由由人来给，工具不代判（与防线4 同一精神）。
  ② 本工具不覆盖"**页内某段被读过但未入选**"这一中间态（那需要页-段级证据，本工具不做）。
  ③ 源文若本身缺页（OCR 丢页），页集合会缺号——本工具会打印页号连续性检查，**缺号即报**。

用法：
  python tools\coverage_by_page_sample.py --task <slug> --out <报告.md> [--sample 20] [--seed 20260920] [--min-run 5] [--src <源文>] [--pool <候选池>]
退出码：0 = 跑通（含"有零覆盖页"的情形——那是待核事项不是工具失败）；1 = 缺件／解析失败／页集合为空
"""
import argparse
import io
import os
import random
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from _paths import ROOT                      # noqa: E402  单一来源根目录
import verify_candidates as VC               # noqa: E402  ← 页标记与锚的**唯一权威**


def _read(p):
    return io.open(p, encoding='utf-8', errors='replace').read()


def _page_nums_from_anchor(text):
    """把一条锚文本归一成页号列表：`s17` / `s17-18` / `bark PDF p84` / `p84` 一律取数字。

    区间只在"看起来是区间"时展开（`s17-18`）；其余取全部数字（多数字形态如
    `bark PDF p84` 只取本页）。展开上限 50 页，防把 `2026-09-17` 之类的日期串炸开。
    """
    nums = [int(m) for m in re.findall(r'\d+', text)]
    if not nums:
        return []
    if len(nums) == 2 and nums[1] > nums[0] and (nums[1] - nums[0]) <= 50:
        return list(range(nums[0], nums[1] + 1))
    return [nums[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True, help='任务 slug（.work\\<task>\\）')
    ap.add_argument('--out', required=True, help='报告输出路径（显式传，V-11）')
    ap.add_argument('--pool', default=None, help='候选池文件（默认 <work>\\verified.md）')
    ap.add_argument('--src', default=None, help='源文（默认按 bookspec-<task>.json 的 src）')
    ap.add_argument('--sample', type=int, default=20)
    ap.add_argument('--seed', type=int, default=20260920)
    ap.add_argument('--min-run', type=int, default=5, dest='min_run')
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    if not os.path.isdir(work):
        print('🔴 缺任务目录：%s' % work); return 1

    VC.WORK = work
    src, why = VC._bookspec_src(a.task, a.src)
    if not src or not os.path.exists(src):
        print('🔴 源文决议失败：%s %s' % (src, why)); return 1
    form = VC.detect_pagemark(src)
    VC.set_pagemark(form)

    pool = a.pool or os.path.join(work, 'verified.md')
    if not os.path.exists(pool):
        print('🔴 缺候选池：%s' % pool); return 1

    src_txt = _read(src)
    pages = sorted({int(n) for n in VC.PAGEMARK_ANY_MARK.findall(src_txt)})
    if not pages:
        print('🔴 页集合为空：页标记形态=%s（源 %s）' % (form, src)); return 1

    # 页 → 该页正文字数（**关键分叉**：区分「空页／图表页＝OCR 没拿到内容」与「有正文却零取料」）
    _segs = VC.PAGEMARK_ANY.split(src_txt)
    _ids = [int(n) for n in VC.PAGEMARK_ANY_MARK.findall(src_txt)]
    plen = {}
    for _i, _pid in enumerate(_ids):
        _body = _segs[_i + 1] if _i + 1 < len(_segs) else ''
        plen[_pid] = len(re.sub(r'\s+', '', _body))

    def _cls(n):
        c = plen.get(n, 0)
        if c <= 20:
            return '空页（≤20字）'
        if c <= 120:
            return '极短（≤120字）'
        return '有正文'

    pool_txt = _read(pool)
    anchors = VC.ANCHOR.findall(pool_txt)
    covered = {}
    for anc in anchors:
        for n in _page_nums_from_anchor(anc):
            covered[n] = covered.get(n, 0) + 1

    pset = set(pages)
    cov_pages = sorted(pset & set(covered))
    zero = sorted(pset - set(covered))
    outside = sorted(set(covered) - pset)

    # 连续零覆盖簇
    runs, cur = [], []
    for n in zero:
        if cur and n == cur[-1] + 1:
            cur.append(n)
        else:
            if len(cur) >= a.min_run:
                runs.append(cur)
            cur = [n]
    if len(cur) >= a.min_run:
        runs.append(cur)

    # 页号连续性（源文自身缺页）
    gaps = [n for i, n in enumerate(pages) if i and n != pages[i - 1] + 1]

    # 抽样：优先抽零覆盖页
    pool_for_sample = zero if zero else pages
    rnd = random.Random(a.seed)
    sample = sorted(rnd.sample(pool_for_sample, min(a.sample, len(pool_for_sample))))

    L = []
    L.append('# 页级取材覆盖核验 · %s' % a.task)
    L.append('')
    L.append('> 工装：`tools\\coverage_by_page_sample.py`（任务通用；页标记与锚口径取自 `verify_candidates` 单一权威）')
    L.append('> 源文：`%s`（依据：%s）｜ 页标记形态：**%s** ｜ 候选池：`%s`' % (
        os.path.basename(src), why, form, os.path.basename(pool)))
    L.append('> 抽样：seed=%d、抽 %d 页 ｜ 连续零覆盖簇阈值：≥%d 页' % (a.seed, a.sample, a.min_run))
    L.append('')
    L.append('## 一、覆盖总表')
    L.append('')
    L.append('| 项 | 值 |')
    L.append('|---|---|')
    L.append('| 源文页数（页标记数） | **%d** |' % len(pages))
    L.append('| 候选池锚行数 | **%d** |' % len(anchors))
    L.append('| 有候选锚定的页数 | **%d** |' % len(cov_pages))
    L.append('| 零覆盖页数 | **%d** |' % len(zero))
    L.append('| 页级覆盖率 | **%.1f%%** |' % (100.0 * len(cov_pages) / len(pages)))
    L.append('| 锚落在页集合之外的页号 | %d %s |' % (
        len(outside), ('（%s）' % outside[:12] if outside else '')))
    L.append('| 源文页号断号 | %d %s |' % (len(gaps), ('（%s）' % gaps[:12] if gaps else '')))
    L.append('')
    L.append('## 二、抽样核验表（逐页核"该页是否确实无可取料"，理由由人来给）')
    L.append('')
    L.append('| # | 页码 | 该页候选条数 | 该页正文字数 | 页类 | 核验理由（待填） |')
    L.append('|---|---|---|---|---|---|')
    for i, n in enumerate(sample, 1):
        L.append('| %d | s%d | %d | %d | %s |  |' % (i, n, covered.get(n, 0), plen.get(n, 0), _cls(n)))
    L.append('')
    L.append('## 三、连续零覆盖簇（最可疑的漏读形态，须逐段给理由）')
    L.append('')
    if runs:
        L.append('| # | 起始页 | 结束页 | 页数 | 理由（待填） |')
        L.append('|---|---|---|---|---|')
        for i, r in enumerate(runs, 1):
            L.append('| %d | s%d | s%d | %d |  |' % (i, r[0], r[-1], len(r)))
    else:
        L.append('**无**（不存在长度 ≥%d 的连续零覆盖段）' % a.min_run)
    L.append('')
    _empty = [n for n in zero if plen.get(n, 0) <= 20]
    _short = [n for n in zero if 20 < plen.get(n, 0) <= 120]
    _real = [n for n in zero if plen.get(n, 0) > 120]
    L.append('## 四、零覆盖页分类（**最关键的一张表**：区分"本就无内容"与"有正文却没取料"）')
    L.append('')
    L.append('| 页类 | 页数 | 含义 | 处置 |')
    L.append('|---|---|---|---|')
    L.append('| 空页（≤20 字） | **%d** | OCR 没拿到内容（多为整页图/表/空白页）⇒ **内容确已丢失**，须登记或补抽 | 逐页给理由，或在下一册改用逐页视觉补抽 |' % len(_empty))
    L.append('| 极短（≤120 字） | **%d** | 多为章首页／分隔页／图注 | 逐页给理由 |' % len(_short))
    L.append('| **有正文却零取料** | **%d** | **最可疑**：该页有实质正文，却没有一条候选锚定 | **逐页核**，判定是"有意不取"还是"漏读" |' % len(_real))
    L.append('')
    L.append('**空页**：%s' % (' '.join('s%d' % n for n in _empty) if _empty else '（无）'))
    L.append('')
    L.append('**有正文却零取料**：%s' % (' '.join('s%d' % n for n in _real) if _real else '（无）'))
    L.append('')
    L.append('## 五、零覆盖页全清单（共 %d 页）' % len(zero))
    L.append('')
    L.append('```')
    L.append(' '.join('s%d' % n for n in zero) if zero else '（无）')
    L.append('```')
    L.append('')
    L.append('## 六、边界声明（必须与结果一起读）')
    L.append('')
    L.append('1. **零候选 ≠ 没读**：提取器按波段读完全书、只产出有选择的条目；本表是「**待核清单**」，不是「漏读清单」。')
    L.append('2. **"空页"须按内容确认，别按字数认定**：≤20 字的页多为整页图/表/空白页（OCR 无文本），'
             '但**图表页正文丢失＝真丢内容**——这一栏要人去看原 PDF 该页确认（本工具只给字数控量）。')
    L.append('3. 本工具**不覆盖**"页内某段被读过但未入选"的中间态（那要页-段级证据）。')
    L.append('4. 页级覆盖率**不是质量分**：书首版权页、注释区、索引区天然可为零（须给理由，不必强求非零）。')
    L.append('5. 页标记形态取自 `detect_pagemark()`（**实测普查**，非推断）；换书后形态变化会自动切换。')
    L.append('')

    out = '\n'.join(L)
    with io.open(a.out, 'w', encoding='utf-8') as f:
        f.write(out + '\n')
    print(out)
    print('→ 已写入 %s' % a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
