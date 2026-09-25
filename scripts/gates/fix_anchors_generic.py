# -*- coding: utf-8 -*-
r"""fix_anchors_generic.py —— 阶段1.5 错锚**确定性勘误**（任务通用 · 与合并器同一把尺子）

## 为什么另写一件（自伤登记 · 2026-09-17）
已有 `tools\fix_anchors.py`，但它是**早期单册（adhd-pro）形态**：要求"每波段一个独立源文件
`<work>\notes\source\<band>-*.txt`"、锚写成 `<书代号> pNNN`、并 import 旧模块 `stage15_merge`。
换成"**单一主文本 ＋ `sNNN` 锚**"的书之后，它对本册**恒报"待改 0 条"**——而合并器同时报 **71 条 MISANCHOR**。
⇒ **两个仪器打架时，先查仪器**（P-23）。本件改为复用**任务通用合并器**的 `load_entries()` 与
`quote_state()`：**判定尺子与被修的底账完全同源**（A-04／A-81 家族：同一判据不许写两遍）。

## 只改什么、不改什么（判据全在合并器侧）
| 合并器判态 | 本件动作 |
|---|---|
| `OK` ／ `CROSS_OK` | **不动**（CROSS_OK＝跨页且与声明页相邻，成立） |
| `MISANCHOR` 且 `actual` **恰好 1 页** | 改锚为 `s<该页>`（引文逐字已核过，仅页号标错） |
| `MISANCHOR` 且 `actual` **多页** | **不猜**，列人工清单（同一句话在多页出现 ⇒ 归属有歧义） |
| `MISANCHOR_CROSS` | 取前缀命中的**起始页**为锚；**逐条打印对比**供人工复核；跨页不连续则列人工清单 |
| `NOANCHOR` ／ `NOANCHOR_SPEC` | **不自动改**，列人工清单 |

## 纪律 （手册 §17.3）
**幂等**（已是目标值则 0 写盘）｜**全有全无**（断言全过才写盘）｜**改前备份**｜
**作用域限定在条目块内**（P-22：不做全文替换）｜默认 **dry-run**，`--apply` 才写盘。

## 用法
    python tools\fix_anchors_generic.py --task <slug>              # dry-run
    python tools\fix_anchors_generic.py --task <slug> --apply
退出码：0 = 无待改或已改妥；1 = dry-run 下有待改项／出现人工项
"""
import argparse
import glob
import io
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC          # noqa: E402
import stage15_merge_task as M          # noqa: E402  ← 与合并器**同一权威**

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--backup-dir', default=None)
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    spec, spec_p = M.load_spec(a.task)
    src_name = spec.get('src')
    if not src_name:
        print('🔴 配置缺 `src`（A-69／A-74），拒绝运行：%s' % spec_p)
        return 1
    src = os.path.join(work, src_name)
    form = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
    if form == 'auto':
        form = VC.detect_pagemark(src)
    VC.set_pagemark(form)

    cand_dir = os.path.join(work, 'candidates')
    bands = [b['band'] for b in spec['bands']]
    entries, fatal = M.load_entries(cand_dir, bands)
    if fatal:
        for f in fatal:
            print('🔴 %s' % f)
        return 1
    if not entries:
        print('🔴 解析出 0 条 ⇒ 空集不得视为通过（A-73），拒绝运行')
        return 1
    src_norm, idx, order, dup = M.build_page_index(src)
    if not idx:
        print('🔴 页索引为空 ⇒ 判据失效，拒绝运行')
        return 1
    print('任务 %s ｜ 页锚形态 %s ｜ 页索引 %d 页 ｜ 条目 %d 条' % (a.task, form, len(idx), len(entries)))

    fixes, manual = [], []
    for e in entries:
        st = M.quote_state(e, idx, order, src_norm)
        s = st['state']
        if s in ('OK', 'CROSS_OK'):
            continue
        if s == 'MISANCHOR':
            act = list(st['actual'])
            if len(act) == 1:
                fixes.append((e, 's%s' % act[0], st))
            else:
                manual.append((e, s, '引文在 %s 多页出现 ⇒ 归属歧义' % act))
        elif s == 'MISANCHOR_CROSS':
            act = list(st['actual'])
            if len(act) == 2 and int(act[0]) + 1 == int(act[1]):
                fixes.append((e, 's%s' % act[0], st))
            else:
                manual.append((e, s, '跨页但 span=%s 非相邻两页 ⇒ 需人工' % act))
        else:
            manual.append((e, s, st['detail']))

    print('=' * 80)
    print('待改 %d 条 ｜ 人工裁断 %d 条 ｜ 模式=%s' % (len(fixes), len(manual), 'APPLY' if a.apply else 'dry-run'))
    for e, new, st in fixes:
        print('  · %-8s %-18s → %-8s（%s）' % (e['eid'], e['anchor_raw'], new, st['detail']))
    if manual:
        print('  —— 人工裁断清单（**本件不改**）：')
        for e, s, d in manual:
            print('     %-8s %-18s %s' % (e['eid'], s, d))

    if not fixes:
        print('  ✔ 无待改项（幂等）')
        return 0 if not manual else 1
    if not a.apply:
        print('  （dry-run 未写盘；加 --apply 生效）')
        return 1

    # ── 备份 ──
    bdir = a.backup_dir or os.path.join(work, '_anchor_fix_backup-%s' % time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bdir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(cand_dir, 'notes_*.md')))
    for f in files:
        shutil.copy2(f, os.path.join(bdir, os.path.basename(f)))
    print('  备份 → %s' % bdir)

    # ── 全有全无：先在内存里改完所有文件，再统一写盘 ──
    by_file, texts = {}, {}
    for e, new, _st in fixes:
        by_file.setdefault(e['band'], []).append((e['eid'], new))
    for band, items in by_file.items():
        p = os.path.join(cand_dir, 'notes_%s.md' % band)
        txt = io.open(p, encoding='utf-8').read()
        texts[p] = txt
        for eid, new in items:
            blocks = VC.SPLIT_ENTRY.split(txt)
            hit = 0
            for i, b in enumerate(blocks):
                m = VC.ENTRY.match(b.split('\n')[0])
                if m and '%s-%s' % (m.group(1), m.group(2)) == eid:
                    nb, n = re.subn(r'(?m)^-\s*锚：.*$', '- 锚：%s' % new, b, count=1)
                    if n == 1 and nb != b:
                        blocks[i] = nb
                        hit += 1
            if hit != 1:
                print('🔴 断言失败：%s 的锚行命中 %d 次（要求恰好 1）⇒ **整批拒写**' % (eid, hit))
                return 1
            txt = ''.join(blocks)
        texts[p] = txt

    # 写盘前断言：新锚形态合法（防把 `sNone` 之类写进去）
    for e, new, _st in fixes:
        if not re.fullmatch(r's\d+', new):
            print('🔴 新锚形态不合法：%s ⇒ 整批拒写' % new)
            return 1
    for p, txt in texts.items():
        io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
    print('  ✔ 已写盘 %d 个文件（%d 条锚）' % (len(texts), len(fixes)))
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
