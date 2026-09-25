# -*- coding: utf-8 -*-
r"""check_root_pair_freshness.py —— **双根副本新鲜度闸**（任意两个技能根之间 · 只读 · 通用）

为什么需要它（2026-09-21 实测事故）：
  本轮把「出处硬纪律」与「前提核对表」推到**装机根**后，**原稿根没跟着变** ⇒ 两处 SKILL.md 各差 24 行；
  而**金融投资线没有挂任何新鲜度闸**（教育线有 `check_copy_freshness.py`）⇒ **漂移无闸可拦**，
  直到一次**独立验收**才发现（`.work\e2e-20260920\附加观察.md` O-35 缺陷 3）。
  ⇒ 本闸＝把"原稿根 ↔ 装机根"这一类**成对根**的一致性做成确定性检查。

判据（确定性，只读）：
  ① 两根**同名技能目录**（含 `SKILL.md` 才算技能件）取交集；
  ② 逐件比对**指定文件**（默认 6 件：SKILL.md／BOUNDARIES.md／INDEX.md／GLOSSARY.md／SUPPLEMENT.md／DIGEST.md）
     的 **sha256**；
  ③ **只报差异，不改文件**；差异含"仅 A 有／仅 B 有／两侧不同"三种形态。

用法：
  python tools\check_root_pair_freshness.py --a <根A> --b <根B> [--files SKILL.md,BOUNDARIES.md] [--slug <名>]… [--out <报告.md>]
退出码：0 = 全部一致；1 = 存在漂移（或根不存在）
"""
import argparse
import hashlib
import io
import os
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

DEFAULT_FILES = ['SKILL.md', 'BOUNDARIES.md', 'INDEX.md', 'GLOSSARY.md', 'SUPPLEMENT.md', 'DIGEST.md']


def sha(p):
    return hashlib.sha256(io.open(p, 'rb').read()).hexdigest()[:16]


def skills_of(root):
    out = []
    if not os.path.isdir(root):
        return out
    for d in sorted(os.listdir(root)):
        p = os.path.join(root, d)
        if os.path.isdir(p) and os.path.exists(os.path.join(p, 'SKILL.md')):
            out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True, help='根 A（如原稿根）')
    ap.add_argument('--b', required=True, help='根 B（如装机根）')
    ap.add_argument('--files', default=','.join(DEFAULT_FILES))
    ap.add_argument('--slug', action='append', default=None)
    ap.add_argument('--out', default=None)
    a = ap.parse_args()

    if not os.path.isdir(a.a) or not os.path.isdir(a.b):
        print('🔴 根不存在：%s 或 %s' % (a.a, a.b)); return 1
    files = [f for f in a.files.split(',') if f]
    A, B = set(skills_of(a.a)), set(skills_of(a.b))
    common = sorted(A & B)
    if a.slug:
        common = [s for s in common if s in set(a.slug)]

    L = ['# 双根副本新鲜度闸', '',
         '> 根 A（原稿）：`%s`（%d 件）' % (a.a, len(A)),
         '> 根 B（装机）：`%s`（%d 件）' % (a.b, len(B)),
         '> 比对文件：%s ｜ 检查时刻：%s' % ('／'.join(files), datetime.now().strftime('%Y-%m-%d %H:%M')),
         '> 本闸**只读**、不改文件；差异须人工决定"以谁为准"后同步。', '']
    if A - B:
        L.append('- ⚠ 仅 A 有：%s' % '、'.join(sorted(A - B)))
    if B - A:
        L.append('- ⚠ 仅 B 有：%s' % '、'.join(sorted(B - A)))
    L += ['', '| 件 | 文件 | A 哈希 | B 哈希 | 判定 |', '|---|---|---|---|---|']
    bad = 0
    for s in common:
        for f in files:
            pa, pb = os.path.join(a.a, s, f), os.path.join(a.b, s, f)
            ea, eb = os.path.exists(pa), os.path.exists(pb)
            if not ea and not eb:
                continue
            if ea and not eb:
                L.append('| %s | %s | %s | — | 🔴 仅 A 有 |' % (s, f, sha(pa))); bad += 1
            elif eb and not ea:
                L.append('| %s | %s | — | %s | 🔴 仅 B 有 |' % (s, f, sha(pb))); bad += 1
            else:
                ha, hb = sha(pa), sha(pb)
                ok = ha == hb
                if not ok:
                    bad += 1
                L.append('| %s | %s | %s | %s | %s |' % (s, f, ha, hb, '✔' if ok else '🔴 不一致'))
    L += ['', '**结论：%s**（比对 %d 件 × %d 文件）' % (
        '✔ 全部一致' if bad == 0 else '🔴 存在 %d 处漂移' % bad, len(common), len(files))]
    txt = '\n'.join(L)
    if a.out:
        io.open(a.out, 'w', encoding='utf-8').write(txt + '\n')
    print(txt)
    if a.out:
        print('→ 已写入 %s' % a.out)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
