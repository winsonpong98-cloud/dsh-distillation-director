# -*- coding: utf-8 -*-
r"""coverage_by_chapter.py —— **逐章取材覆盖表**（防线4 的机器证据 · 任务通用）

为什么需要它（手册 §11 防线4）：
  「每章零贡献须有理由」是**忠实度四防线**的第四道。人工肉眼数"哪章没取料"最易出错，
  而**章 → 页锚 → 候选条目**这条链是**确定的**：主文本里的章标题行决定"该章从哪一页开始"，
  条目的 `- 锚：s<n>` 决定"它取自哪一页" ⇒ 两者相除即可得**逐章取材计数**。

判据与纪律：
  · 章标题形态**从配置读**（`bookspec-<task>.json` 的 `chapter_heading_regex`，缺省用中文通用形态
    `^第[一二三四五六七八九十百零〇\d]+[章部分]`）——**不在代码里写死某本书的章名**（A-69／A-74）。
  · 页锚形态用**唯一权威** `verify_candidates.detect_pagemark()`／配置 `pagemark`（A-30／A-81 家族）。
  · **各栏之和 == 条目总数**，当场可核（A-42）；条目锚落在"最后一章之后"的（如后记/参考文献/附录）
    单列 **【章外】** 栏，**不许静默丢弃**。
  · 输出必须显式传路径（V-11：写入型命令不得写死输出）。

用法：
  python tools\coverage_by_chapter.py --task <slug> --out <报告.md>
退出码：0 = 跑通且各栏之和 == 总数；1 = 不等／缺件
"""
import argparse
import glob
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC          # noqa: E402
import json                             # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
DEFAULT_HEAD = r'^第[一二三四五六七八九十百零〇\d]+[章部分](?:\s|$|　)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    sp = os.path.join(work, 'bookspec-%s.json' % a.task)
    if not os.path.isfile(sp):
        print('🔴 缺任务配置：%s（A-69／A-74）' % sp)
        return 1
    spec = json.load(io.open(sp, encoding='utf-8'))
    src_name = spec.get('src')
    src = os.path.join(work, src_name or '')
    if not src_name or not os.path.isfile(src):
        print('🔴 配置缺 `src` 或源文件不存在：%s' % src)
        return 1

    form = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
    if form == 'auto':
        form = VC.detect_pagemark(src)
    VC.set_pagemark(form)
    head_re = re.compile(spec.get('chapter_heading_regex') or DEFAULT_HEAD)

    # ── ① 章 → 起始页锚（顺序扫描主文本）──
    # ⚠ 自伤登记（2026-09-17 本册实测）：首版**没排目录页** ⇒ 目录里那 11 行章名被当成"章起点"（落在 s2–s6），
    #   于是正文各章全被判"零贡献 11 个"，**一个纯工装伪影看起来像"全书没取料"**（P-23：判官/报告出现
    #   异常时先修自己的工装再采信）。
    #   修法：① 配置可给 `toc_pages`／`skip_pages`（页号列表）显式排除；
    #        ② **结构性判据**：连续 ≥5 条、且落在 ≤6 页跨度内的章标题行 ⇒ 判为目录块并**整体丢弃**
    #           （正文不可能有 5 章挤在 6 页内），丢弃项**显式打印**，不静默。
    raw = io.open(src, encoding='utf-8').read().split('\n')
    page_re = re.compile(VC.PAGEMARK_MARK_FORMS[form])
    skip_pages = {int(x) for x in (spec.get('toc_pages') or spec.get('skip_pages') or [])}
    hits, cur_page = [], None
    for ln in raw:
        pm = page_re.search(ln)
        if pm:
            cur_page = pm.group(1)
            continue
        s = ln.strip()
        if cur_page and s and head_re.match(s):
            hits.append((s, int(cur_page)))

    def in_toc_block(hs):
        """连续 ≥5 条且页跨度 ≤6 ⇒ 目录块。"""
        drop = [False] * len(hs)
        i = 0
        while i < len(hs):
            j = i
            while j + 1 < len(hs) and hs[j + 1][1] - hs[i][1] <= 6:
                j += 1
            if (j - i + 1) >= 5:
                for k in range(i, j + 1):
                    drop[k] = True
            i = j + 1
        return drop

    dropped_struct = in_toc_block(hits)
    chapters, seen, dropped = [], set(), []
    for (title, pg), ds in zip(hits, dropped_struct):
        key = title[:6]
        if pg in skip_pages or ds:
            dropped.append((title, pg, 'toc_pages' if pg in skip_pages else '结构判据(目录块)'))
            continue
        if key in seen:
            dropped.append((title, pg, '同名前缀重复（保留后出现者）'))
            continue
        seen.add(key)
        chapters.append((title, pg))
    if not chapters:
        print('🔴 未识别到任何章标题 ⇒ 判据不成立，拒绝出表（check 你的 chapter_heading_regex）')
        return 1

    def chapter_of(page):
        hit = None
        for name, sp0 in chapters:
            if page >= sp0:
                hit = name
            else:
                break
        return hit

    # ── ② 条目 → 章（按锚）──
    files = sorted(glob.glob(os.path.join(work, 'candidates', 'notes_*.md')))
    if not files:
        print('🔴 无 candidates/notes_*.md ⇒ 空集不得视为通过（A-73）')
        return 1
    per_ch = {name: 0 for name, _ in chapters}
    out_of_book, bad_anchor, total = 0, 0, 0
    # ⚠ 2026-09-17 修（本册实测）：**末章之后的页面**（后记／参考文献／附录）若按
    #   "取最后一个起始页 ≤ 本页的章"归章，会被**误算进最后一章**（本册实测 2 条）。
    #   修法：配置可声明 `epilogue_pages`（页号列表）⇒ 这些页上的条目**强制归【章外】**。
    epi = {int(x) for x in (spec.get('epilogue_pages') or [])}
    for fp in files:
        for blk in VC.SPLIT_ENTRY.split(io.open(fp, encoding='utf-8').read()):
            if not VC.ENTRY.match(blk.split('\n')[0]):
                continue
            total += 1
            am = VC.ANCHOR.search(blk)
            if not am:
                bad_anchor += 1
                continue
            nums = [int(x) for x in re.findall(r'\d{1,4}', am.group(1))]
            page = nums[0] if nums else 0
            ch = None if page in epi else chapter_of(page)
            if ch is None:
                out_of_book += 1
            else:
                per_ch[ch] += 1

    ssum = sum(per_ch.values()) + out_of_book
    L = ['# 逐章取材覆盖表（防线4 机器证据）', '',
         '> 任务 `%s` ｜ 源 `%s` ｜ 页锚形态 `%s` ｜ 由 `tools\\coverage_by_chapter.py` 生成' % (a.task, src_name, form),
         '> 口径：章起点＝主文本中章标题行**当前生效的页锚**；条目归属＝其 `- 锚：` 的首个页号。', '',
         '| 章（行首标题原文） | 起始页锚 | 取材条目数 |', '|---|---|---|']
    zero = []
    for name, sp0 in chapters:
        n = per_ch[name]
        if n == 0:
            zero.append(name)
        L.append('| %s | s%d | **%d** |' % (name, sp0, n))
    L += ['| **【章外】**（后记／参考文献／附录／序言等，锚晚于末章或早于首章） | — | **%d** |' % out_of_book,
          '',
          '| 项 | 值 |', '|---|---|',
          '| 条目总数 | **%d** |' % total,
          '| 各章之和 ＋ 章外 | **%d** |' % ssum,
          '| 锚行无法解析 | %d |' % bad_anchor,
          '| **零贡献章** | **%d** 个%s |' % (len(zero), ('　→　' + '；'.join(zero)) if zero else '（无）'),
          '| 判为目录/重复而**丢弃**的章标题行 | %d |' % len(dropped),
          '']
    if dropped:
        L += ['### 被判为目录块或重复而丢弃的标题行（**不静默**，逐条列出）', '',
              '| 标题行 | 页锚 | 丢弃理由 |', '|---|---|---|']
        for t, pg, why in dropped:
            L.append('| %s | s%d | %s |' % (t, pg, why))
        L.append('')
    if zero:
        L.append('> ⚠ **零贡献章必须逐条给出理由**（手册 §11 防线4）：本表只出**机器计数**，理由由人工补写。')
    if ssum != total:
        L.append('> 🔴 **各栏之和 ≠ 总数**（%d ≠ %d）⇒ 有对象未被归类，先修口径再看结论（A-82 同族）。'
                 % (ssum, total))
    io.open(a.out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    print('条目总数 %d ｜ 各章之和＋章外 %d %s ｜ 零贡献章 %d 个 ｜ 锚不可解析 %d'
          % (total, ssum, '✔ 相等' if ssum == total else '🔴 不等', len(zero), bad_anchor))
    print('报告：%s' % a.out)
    return 0 if (ssum == total and not bad_anchor) else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
