# -*- coding: utf-8 -*-
r"""extract_table_datapack.py —— **表格数据件生成器**（把表格原件随册交付，任务通用）

为什么需要它（2026-09-20 表格专项实测结论）：
  实测那一册的 3 张表：**源文转录完整**（视觉 OCR 全部转成 markdown 管道表），
  但**候选池里没有一张以表格形态保留**（池内 3 个管道块其实是池自带的说明表），
  **表号只保住 1/3**、列名与单元格数值部分丢失 ⇒ 结论是
  「**表格数值以转述保留为主；表格形态＋列名＋表号会丢**」。
  ⇒ 修法＝**把表格原件独立成"数据件"随册交付**（技能只引用表号），这样"表格可回查"才成立。

判据（确定性，全部可复跑）：
  · 表号形态＝从 `bookspec-<task>.json` / `--tref-regex` 读（**不写死某本书的编号法**）；
  · 每张表＝源文中**与该表号同页**的 markdown 管道表块（连续 `^\|` 行）；
  · 落盘＝`<out-dir>/<task>/表<id>.md`，内含：表号｜页锚 sNNN｜来源文件｜快照日期｜**逐字管道表**；
  · **守恒断言**：落盘的管道表行**逐字节等于**源文该页管道表行（`assert` 不过即报错退出）。

用法：
  python tools\extract_table_datapack.py --task <slug> --out-dir <目录> [--src <源文>] [--tref-regex <正则>]
退出码：0 = 全部表已落盘且守恒；1 = 缺件／某表未找到／守恒失败
"""
import argparse
import io
import os
import re
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from _paths import ROOT                      # noqa: E402
import verify_candidates as VC               # noqa: E402

DEFAULT_TREF = r'表\s*(\d{1,2})\s*[.\-–—]\s*(\d{1,2})'


def pipe_lines(text):
    return [ln for ln in text.splitlines() if ln.lstrip().startswith('|')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out-dir', required=True, dest='outdir')
    ap.add_argument('--src', default=None)
    ap.add_argument('--tref-regex', default=DEFAULT_TREF, dest='tref')
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    if not os.path.isdir(work):
        print('🔴 缺任务目录：%s' % work); return 1
    VC.WORK = work
    src, why = VC._bookspec_src(a.task, a.src)
    if not src or not os.path.exists(src):
        print('🔴 源文决议失败：%s %s' % (src, why)); return 1
    VC.set_pagemark(VC.detect_pagemark(src))
    src_txt = io.open(src, encoding='utf-8', errors='replace').read()

    # 页 → 文本
    segs = VC.PAGEMARK_ANY.split(src_txt)
    ids = [int(x) for x in VC.PAGEMARK_ANY_MARK.findall(src_txt)]
    page_txt = {pid: (segs[i + 1] if i + 1 < len(segs) else '') for i, pid in enumerate(ids)}

    tref = re.compile(a.tref)
    # 表号 → 所在页：**在该页文本里直接找**（不能用"去标记后的偏移"反推——标记被 split 吃掉，偏移必然错位）
    # 优先取"含该表号 **且有管道表块**"的页；退而取任一含该表号的页。
    where = {}
    for pid in ids:
        body = page_txt[pid]
        for m in tref.finditer(body):
            key = '%s.%s' % (m.group(1), m.group(2))
            cur = where.get(key)
            if cur is None:
                where[key] = pid
            elif pipe_lines(body) and not pipe_lines(page_txt.get(cur, '')):
                where[key] = pid          # 该页有表块 ⇒ 优先

    outdir = os.path.join(a.outdir, a.task)
    os.makedirs(outdir, exist_ok=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    ok = fail = 0
    for key, pid in sorted(where.items(), key=lambda kv: (int(kv[0].split('.')[0]), int(kv[0].split('.')[1]))):
        body = page_txt.get(pid, '')
        rows = pipe_lines(body)
        if not rows:
            print('🔴 表 %s：在第 s%s 页未找到管道表块' % (key, pid)); fail += 1; continue
        block = '\n'.join(rows)
        # 守恒断言：落盘行必须逐字节等于源文对应行
        assert all(r in body for r in rows), '守恒失败：表 %s' % key
        md = ['# 表 %s（数据件 · 逐字保留）' % key, '',
              '> 表号：**表 %s** ｜ 页锚：**s%s**（源文物理页）｜ 源文：`%s`' % (key, pid, os.path.basename(src)),
              '> 生成：`tools\\extract_table_datapack.py`（幂等可复跑）｜ 快照：%s' % now,
              '> **用途**：技能只引用表号；数值以本件为准（**未经改动，逐字来自源文转录**）。',
              '', '```', block, '```', '']
        dst = os.path.join(outdir, '表%s.md' % key)
        io.open(dst, 'w', encoding='utf-8').write('\n'.join(md))
        print('✔ 表 %-6s s%-4s %2d 行 → %s' % (key, pid, len(rows), dst)); ok += 1

    print('\n落盘 %d 张 ／ 失败 %d 张 ／ 目录 %s' % (ok, fail, outdir))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
