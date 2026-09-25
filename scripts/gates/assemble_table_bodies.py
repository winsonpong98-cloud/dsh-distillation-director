# -*- coding: utf-8 -*-
r"""assemble_table_bodies.py —— **逐表拼装表体**（多图表体 → 单一数据件）（任务通用 · 确定性）

为什么需要它（2026-09-21 · O-44）：
  某册表体是**截图图像**，且实测 **7/31 张表由 2 张图构成**（续图右上角标「（续）」）。
  `tools\map_table_images.py` 已给出"表体区＝标题与来源行之间的全部图像"，
  `tools\ocr_deepseek_vision.py --kind table` 已把每张图 OCR 成管道表。
  本脚本只做**拼装与留痕**：按 y 序把同一张表的各图管道表接起来（**不删不改任何行**），
  补上表标题行与 `注：/资料来源` 行，输出可直接交付的**数据件**＋一张**拼装台账**。

纪律（硬约束，违反即产物作废）：
  ① **只拼接、不改字**：OCR 文本原样进入产物（含 `【?】` 等不确定标记），**不得**顺手"修正"数字；
  ② **续图必须留痕**：每张图的来源（`pNNNN_iNN`）以 HTML 注释写在该段之前，可回溯到页图；
  ③ **不确定处必须显式**：图间若出现表头重复（续图重印表头）**不合并**，原样保留并标注；
  ④ 产物**不进技能**：数据件属数据层（`数据件/<task>/`），技能只引用表号（见 check_table_inventory 边界声明 1）。

用法：
  python tools\assemble_table_bodies.py --task guozhai-qihuo \
      --map .work\guozhai-qihuo\表图像映射.json --textdir tabletext \
      --out-dir .work\guozhai-qihuo\tablebodies --ledger .work\guozhai-qihuo\表体拼装台账.md
退出码：0 = 跑通；1 = 缺件／有表未拼出（必须在台账里看到是哪张）
"""
import argparse
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _paths import ROOT                       # noqa: E402

CONT = re.compile(r'[（(]\s*续\s*[)）]')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--map', required=True)
    ap.add_argument('--textdir', default='tabletext')
    ap.add_argument('--out-dir', required=True, dest='outdir')
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--ext', default='md', help='产物扩展名（默认 md）')
    a = ap.parse_args()

    mp = a.map if os.path.isabs(a.map) else os.path.join(ROOT, a.map)
    if not os.path.exists(mp):
        print('🔴 缺映射文件：%s' % mp); return 1
    data = json.loads(io.open(mp, encoding='utf-8').read())
    tdir = os.path.join(ROOT, '.work', a.task, a.textdir)
    odir = a.outdir if os.path.isabs(a.outdir) else os.path.join(ROOT, a.outdir)
    os.makedirs(odir, exist_ok=True)

    led, n_ok, n_bad, n_multi = [], 0, 0, 0
    for r in data['rows']:
        key = r['key']
        segs, missing, has_cont = [], [], False
        for im in r['imgs']:
            stem = 'p%04d_i%02d' % (im['page'], im['idx'])
            fp = os.path.join(tdir, stem + '.md')
            if not os.path.exists(fp):
                missing.append(stem)
                continue
            t = io.open(fp, encoding='utf-8', errors='replace').read().strip()
            if CONT.search(t):
                has_cont = True
            segs.append((stem, t))
        if missing:
            n_bad += 1
            led.append((key, r['title'], len(r['imgs']), 0, '🔴 缺 OCR 文本：%s' % '、'.join(missing), ''))
            continue
        if not any(ln.strip().startswith('|') for _, t in segs for ln in t.splitlines()):
            n_bad += 1
            led.append((key, r['title'], len(r['imgs']), 0, '🔴 无管道表内容', ''))
            continue
        n_ok += 1
        n_multi += 1 if len(segs) > 1 else 0
        # 产物：标题行 ＋ 各段（带来源注释）＋ 注/资料来源行
        L = ['# 表 %s ｜ %s' % (key, r['title']),
             '',
             '> 数据件 · 由页图视觉转写拼装（来源：`%s`，PDF p%d–p%d）'
             % (os.path.basename(data.get('pdf', '')), min(i['page'] for i in r['imgs']),
                max(i['page'] for i in r['imgs'])),
             '> 拼装工装：`tools\\assemble_table_bodies.py`；逐图转写：`tools\\ocr_deepseek_vision.py --kind table`',
             '> ⚠ 本件为**数据层**产物：逐格照抄页图，**未做任何数值修正**；`【?】` 表示图上不清。', '']
        for si, (stem, t) in enumerate(segs):
            lines = t.splitlines()
            # 续图：OCR 若把「（续）」单独成行，去掉该行（避免与下方说明重复）；标记不丢，见下句
            if si > 0 and lines and CONT.fullmatch(lines[0].strip()):
                lines = lines[1:]
                while lines and not lines[0].strip():
                    lines = lines[1:]
            L += ['<!-- 来源图像 %s -->' % stem, '']
            if si > 0:
                L += ['**（续）** — 本段为续图（原图右上角标「（续）」或**表头逐字重复**）', '']
            L += ['\n'.join(lines).strip(), '']
        for nt in r.get('notes', []):
            L += ['> %s' % nt]
        body = '\n'.join(L) + '\n'
        fn = '表%s.%s' % (key, a.ext)
        io.open(os.path.join(odir, fn), 'w', encoding='utf-8', newline='\n').write(body)
        led.append((key, r['title'], len(r['imgs']), len(body.splitlines()),
                    '✔ 拼装完成', ('含续图' if has_cont else '')))

    L = ['# 表体拼装台账 · %s' % a.task, '',
         '> 工装：`tools\\assemble_table_bodies.py`（**只拼接不改字**）',
         '> 输入：`%s` ／ 逐图 OCR：`%s`' % (os.path.relpath(mp, ROOT), os.path.relpath(tdir, ROOT)),
         '> 产物目录：`%s`' % os.path.relpath(odir, ROOT), '',
         '| 表号 | 标题 | 图数 | 产物行数 | 判态 | 备注 |', '|---|---|---|---|---|---|']
    for key, title, nimg, nline, verdict, note in led:
        L.append('| 表 %s | %s | %d | %d | **%s** | %s |' % (key, title[:36], nimg, nline, verdict, note))
    L += ['', '## 计数', '',
          '表 **%d** 张 ｜ ✔ 拼装完成 **%d** ／ 🔴 失败 **%d** ｜ 其中多图表 **%d** 张'
          % (len(led), n_ok, n_bad, n_multi), '',
          '## 边界声明', '',
          '1. **拼装 ≠ 数值正确**：本件是页图的逐格转写；**数值抽检**须另做（人眼抽查或第二引擎互核），'
          '不得以"已拼装"当作"数字无误"；',
          '2. **续图证据**：续图以图上「（续）」字样为识别依据，属**视觉证据**（非文字层）⇒ 若某张续图未标「（续）」，'
          '本脚本不会合并也不会报错 ⇒ 多图表的完整性**仍须对图核**；',
          '3. 数据件**不进技能根**：技能引用表号、数据件承载数值（`check_table_inventory.py` 边界声明 1）。', '']
    lp = a.ledger if os.path.isabs(a.ledger) else os.path.join(ROOT, a.ledger)
    io.open(lp, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print('→ 台账已写入 %s ／ 数据件 %d 件 → %s' % (lp, n_ok, odir))
    return 1 if n_bad else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
