# -*- coding: utf-8 -*-
r"""slice_verified_by_skill.py —— 把阶段1.5 的 `verified.md` 按**技能族归属**切片（任务通用）

为什么需要它：
  `verified.md` 是大文件（一本书可达数百 KB、上千条）。阶段2 构造通常**按技能分派**（一件一个执行者），
  若让每个执行者都读整份 verified.md，既贵又容易串味（读到别件的料）。本件按条目自带的 `- 归属：`slug``
  切成 `pool_<slug>.md`，**每片只含该件的条目**，并把归属不存在的条目单列出来（**不许静默丢**）。

判据与纪律：
  · 用**权威模块** `tools\verify_candidates.py` 的 `SPLIT_ENTRY`／`ENTRY` 切块与识别条目头
    （不另写一套切块正则 —— A-72 变体：同一判据写两遍＝改一处等于没改）。
  · **空集拒跑**：解析出 0 条 ⇒ rc≠0（A-73：空集不得视为通过）。
  · **归属缺失不静默**：无 `- 归属：` 行的条目归入 `pool_UNASSIGNED.md` 并在报告里点名。
  · **各栏之和 ＝ 总数**，当场可核（A-42）。
  · 输出路径由参数决定（V-11：写入型命令必须显式传输出路径）。

用法：
  python tools\slice_verified_by_skill.py --task <slug> --out-dir <目录>
退出码：0 = 跑通；1 = 空集／缺 verified.md
"""
import argparse
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC          # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
OWNER = re.compile(r'^-\s*归属：\s*`?([A-Za-z0-9_\-]+)`?\s*$', re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out-dir', required=True, help='显式输出目录（V-11：不得写死路径）')
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    vp = os.path.join(ROOT, '.work', a.task, 'verified.md')
    if not os.path.isfile(vp):
        print('🔴 缺 verified.md：%s ⇒ 阶段1.5 未做，拒绝运行' % vp)
        return 1
    txt = io.open(vp, encoding='utf-8').read()

    groups, order = {}, []
    ids_all = []
    for blk in VC.SPLIT_ENTRY.split(txt):
        head = blk.split('\n')[0]
        m = VC.ENTRY.match(head)
        if not m:
            continue
        eid = '%s-%s' % (m.group(1), m.group(2))
        ids_all.append(eid)
        om = OWNER.search(blk)
        slug = om.group(1) if om else 'UNASSIGNED'
        if slug not in groups:
            groups[slug] = []
            order.append(slug)
        groups[slug].append((eid, blk.rstrip()))

    if not ids_all:
        print('🔴 verified.md 解析出 **0 条** ⇒ 空集不得视为通过（A-73），拒绝运行')
        return 1
    if len(ids_all) != len(set(ids_all)):
        dup = sorted({i for i in ids_all if ids_all.count(i) > 1})
        print('🔴 条目 id 重复：%s ⇒ 先修底账（底账同代铁律 R8），拒绝切片' % ','.join(dup[:10]))
        return 1

    written = []
    for slug in order:
        rows = groups[slug]
        L = ['# pool_%s.md —— 阶段2 构造输入分片（归属 `%s`）' % (slug, slug), '',
             '> 由 `tools\\slice_verified_by_skill.py` 从 `.work/%s/verified.md` 切出。' % a.task,
             '> 本片 **%d 条** ｜ 每条含 id／类型／锚／引文态／**逐字原文**／转述。' % len(rows),
             '> 构造纪律：R 段依据必须逐条引用本片 id 与锚；**引文必须逐字来自本片 `原文（逐字）`**（≤160 字）；'
             '操作层用 `◈` 标注。', '']
        for eid, blk in rows:
            L.append(blk)
            L.append('')
        p = os.path.join(a.out_dir, 'pool_%s.md' % slug)
        io.open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
        written.append((slug, len(rows), p))

    tot = sum(n for _, n, _ in written)
    print('条目总数 %d ｜ 分片 %d 个 ｜ 各片之和 %d %s'
          % (len(ids_all), len(written), tot, '✔ 相等' if tot == len(ids_all) else '🔴 不等'))
    for slug, n, p in sorted(written, key=lambda x: -x[1]):
        print('  %-34s %5d 条  → %s' % (slug, n, os.path.basename(p)))
    if 'UNASSIGNED' in groups:
        print('  ⚠ **归属缺失**（须人工裁断，不得静默丢弃）：%s'
              % ','.join(e for e, _ in groups['UNASSIGNED'][:20]))
    if tot != len(ids_all):
        return 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
