# -*- coding: utf-8 -*-
r"""fix_quote_pagemarks.py —— 候选池**引文内嵌页锚标记/省略号**的机械修复器（任务通用）

## 为什么需要它（自伤登记 · 2026-09-17）
文字版 PDF 直抽文本的页锚 `[p<n>]` 是**独占一行**的。正文里很多句子**恰好被页锚行从中间断开**，
于是提取器会出现两种写法，**都过不了权威回源校验**：
  · 写法甲：把页锚行**抄进引文**（`…采用现金流[p25]贴现模型…`）；
  · 写法乙：用 **`……`** 顶替页锚行（`…n年之后一共有……我们将FV称为终值。`）。
**最坑的地方**：提取器**自己的"逐条回源自证"是通过的**——因为它是拿**未剥页锚行**的源文做子串断言
（归一化去空白后，`[p25]` 本身就在串里）。而权威校验器 `verify_candidates.py` 的 `clean_src`
**会先把页锚行剥掉** ⇒ 同一批引文在权威口径下**未命中**。
⇒ **元教训**：自证的**口径**必须与被校验方的口径**同源**，否则"自证通过"只是"用另一把尺子量过"
（本坑属 A-55／A-59 家族，已入《避坑手册》）。

## 修法（确定性、可复算）
对每条**权威口径下未命中**的引文，用**四个独立变换**做组合搜索（子集由小到大，**命中即停**）：
  · **T1** 删掉引文内的 `[p<数字>]` 标记；
  · **T2** 删掉引文内的省略号串（`……`／`…`／`...`／`。。。`），使断处**自然相接**；
  · **T3** 引号族**互换**：`"` → `'`（源文用**中文单引号** `‘…’` 而提取器转写成双引号时）；
  · **T4** 引号族**反向互换**：`'` → `"`。
组合命中后**必须再复验一次**（新引文在权威口径下确实命中）才允许写盘。
**一次都不中的条目一律不改**，列入「待人工清单」（须由人或提取器改引更短的连续句 —— **不许猜补**）。

> **为什么不用"放松尺子"来消掉这些未命中**：那等于**自造一把更松的尺**（手册 `A-34`），会把
> 「引号字形差异」与「真的引错了」一起放过。**修产物、不松尺**是唯一站得住的方向。

## 纪律（手册 §17.3 批量改写脚本）
· **幂等**：写入前判断"新文本是否已在"；修好的引文第二次跑必须 0 写盘。
· **全有全无**：先在内存里全部应用 → 跑完全部断言 → 才统一写盘；任一断言失败**整批拒写**。
· **改前备份**：`--backup-dir` 下逐文件留底（默认 `.work/<slug>/_quote_fix_backup-<时间戳>/`）。
· **作用域限定**：**只**处理 `<work>/candidates/notes_*.md`；**绝不**触碰 judge／证据／技能正文。
· 只动 `- 原文（逐字）：` 那一行内的引文，**不动锚、不动转述、不动备注**。

用法：
  python tools\fix_quote_pagemarks.py --task <slug> [--dry-run] [--backup-dir <dir>]
退出码：0 = 跑通（可能仍有待人工项，会打印）；1 = 断言失败已整批拒写／配置缺项
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC          # noqa: E402  （复用权威尺子，不另写一份）

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
PAGEMARK_IN_QUOTE = re.compile(r'\s*\[p\s*\d+\]\s*')
ELLIPSIS = re.compile(r'(?:…{1,}|\.{3,}|。{3,})')


# ── 四个独立变换（组合搜索用；**命中即停**）──────────────────────────────────
def _t1_pagemark(q):
    return PAGEMARK_IN_QUOTE.sub('', q)


def _t2_ellipsis(q):
    return ELLIPSIS.sub('', q)


def _t3_dq_to_sq(q):
    return q.replace('"', "'")


def _t4_sq_to_dq(q):
    return q.replace("'", '"')


TRANSFORMS = [('T1', _t1_pagemark), ('T2', _t2_ellipsis),
              ('T3', _t3_dq_to_sq), ('T4', _t4_sq_to_dq)]


# ── T5/T6：闭合引号**之后**多写了句末标点 ⇒ 权威 `QUOTE` 正则（要求引号收尾于行末）**整条认不出** ──
# 实测（本册 A 波段 2 条）：提取器写成 `…不足」。`（句号在引号外），而源文是 `…不足。`（句号在引号内）。
# 后果比"回源未命中"更隐蔽：**该条根本没有被回源校验过**（校验器数不到它），只会以"缺引文 2"出现。
# 修法（两条都试，**以权威口径验证为准**，命中即停）：
#   T5 把尾部标点**移进**引号内（保留句号 ⇒ 更贴近源文原貌）→ 优先；
#   T6 把尾部标点**删掉**（引号内已自带标点时适用）。
Q_LINE_LOOSE = re.compile(r'^(-\s*原文（逐字）：)[「“"](.+)[」”"]([。．.！!？?；;，,]+)[ \t]*$')


def repair_loose_quote_line(block, clean):
    """→ (新块, 规则名) 或 (None, None)：处理"权威 QUOTE 认不出的引文行"。"""
    for line in block.split('\n'):
        m = Q_LINE_LOOSE.match(line)
        if not m:
            continue
        prefix, inner, tail = m.group(1), m.group(2), m.group(3)
        if VC.norm_match(inner + tail) in clean:
            return block.replace(line, '%s「%s」' % (prefix, inner + tail), 1), 'T5'
        if VC.norm_match(inner) in clean:
            return block.replace(line, '%s「%s」' % (prefix, inner), 1), 'T6'
    return None, None


def repair_search(q, clean):
    """→ (修复后的引文, 规则名) 或 (None, None)。

    搜索序：单变换 → 两变换 → 三变换 → 四变换（同尺寸内按 TRANSFORMS 定义序），**命中即停**。
    每次候选都**真跑权威口径**（`VC.norm_match(cand) in clean`）——不看形状、只看命中。
    """
    import itertools
    for size in (1, 2, 3, 4):
        for combo in itertools.combinations(range(len(TRANSFORMS)), size):
            cand = q
            for i in combo:
                cand = TRANSFORMS[i][1](cand)
            if cand == q:
                continue
            if VC.norm_match(cand) in clean:
                return cand, '+'.join(TRANSFORMS[i][0] for i in combo)
    return None, None


def load_spec(task):
    import json
    p = os.path.join(ROOT, '.work', task, 'bookspec-%s.json' % task)
    if not os.path.exists(p):
        raise SystemExit('🔴 缺任务配置：%s（源文件名/页锚形态必须来自配置 —— A-69／A-74）' % p)
    return json.load(io.open(p, encoding='utf-8'))


def clean_src_text(src_path):
    return VC.norm_match(VC.clean_src(io.open(src_path, encoding='utf-8').read()))


def iter_entry_blocks(txt):
    """→ [(块文本, 起止) …]（用权威 SPLIT_ENTRY，不另写切块规则）"""
    parts, pos = [], 0
    for m in VC.SPLIT_ENTRY.finditer(txt):
        if pos:
            parts.append((txt[pos:m.start()], pos, m.start()))
        pos = m.start()
    if pos:
        parts.append((txt[pos:], pos, len(txt)))
    out = []
    for blk, s, e in parts:
        if VC.ENTRY.match(blk.split('\n')[0]):
            out.append((blk, s, e))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--backup-dir', default=None)
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    spec = load_spec(a.task)
    src_name = spec.get('src')
    if not src_name:
        print('🔴 配置缺 `src`，拒绝运行（A-69／A-74）')
        return 1
    src = os.path.join(work, src_name)
    pm = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
    if pm == 'auto':
        pm = VC.detect_pagemark(src)
    VC.set_pagemark(pm)
    CLEAN = clean_src_text(src)
    print('页锚形态：%s（源＝%s）' % (pm, src_name))

    files = sorted(glob.glob(os.path.join(work, 'candidates', 'notes_*.md')))
    if not files:
        print('🔴 `candidates/notes_*.md` 一个对象都没有 —— **空集不得视为通过**（A-73）：拒绝运行')
        return 1

    n_total = n_ok_before = n_fixed = 0
    by_rule = {}
    manual, noquote, writes = [], [], {}
    for fp in files:
        txt = io.open(fp, encoding='utf-8').read()
        new_txt = txt
        blocks = iter_entry_blocks(txt)
        if not blocks:
            print('🔴 %s 切块为空（工装缺陷，不得视为通过）' % os.path.basename(fp))
            return 1
        for blk, s, e in blocks:
            m = VC.ENTRY.match(blk.split('\n')[0])
            eid = '%s-%s' % (m.group(1), m.group(2))
            qm = VC.QUOTE.search(blk)
            if not qm:
                # 权威 QUOTE 认不出 ⇒ 先试"引号外多写了句末标点"（T5/T6，见上方说明）
                nb, rule = repair_loose_quote_line(blk, CLEAN)
                if nb is None:
                    noquote.append((os.path.basename(fp), eid))
                    continue
                n_total += 1
                n_fixed += 1
                by_rule[rule] = by_rule.get(rule, 0) + 1
                new_txt = new_txt.replace(blk, nb, 1)
                continue
            n_total += 1
            q = qm.group(1)
            if VC.norm_match(q) in CLEAN:
                n_ok_before += 1
                continue
            cand, rule = repair_search(q, CLEAN)
            if cand is None:
                manual.append((os.path.basename(fp), eid, q))
                continue
            by_rule[rule] = by_rule.get(rule, 0) + 1
            n_fixed += 1
            # 只替换该块内 `- 原文（逐字）：` 行的引文内容
            old_line = qm.group(0)
            new_line = old_line.replace(q, cand, 1)
            blk_new = blk.replace(old_line, new_line, 1)
            if blk_new == blk:
                print('🔴 %s 替换未生效（断言失败，整批拒写）' % eid)
                return 1
            new_txt = new_txt.replace(blk, blk_new, 1)
        if new_txt != txt:
            writes[fp] = new_txt

    print('条目 %d ｜ 修复前权威命中 %d ｜ **机械修复 %d** ｜ 待人工 %d ｜ 无引文行 %d'
          % (n_total, n_ok_before, n_fixed, len(manual), len(noquote)))
    if by_rule:
        print('   规则分布：' + ' ／ '.join('%s %d' % (k, v) for k, v in sorted(by_rule.items())))
    if noquote:
        print('\n无引文行清单（**权威 QUOTE 认不出且 T5/T6 也救不了** ⇒ 须人工补引）：')
        for f, eid in noquote[:40]:
            print('  %s %s' % (f, eid))
    if manual:
        print('\n待人工清单（**未改动**，须改引更短的连续句，禁猜补）：')
        for f, eid, q in manual[:60]:
            print('  %s %-8s %s' % (f, eid, q[:78]))
        if len(manual) > 60:
            print('  …（另有 %d 条）' % (len(manual) - 60))

    if not writes:
        print('\n✔ 无待写文件（幂等：第二次跑必然 0 写盘）')
        return 0
    if a.dry_run:
        print('\n（--dry-run：以下文件本应写入，但未写）')
        for fp in writes:
            print('  %s' % fp)
        return 0

    bdir = a.backup_dir or os.path.join(
        work, '_quote_fix_backup-%s' % time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bdir, exist_ok=True)
    for fp, _ in writes.items():
        shutil.copy2(fp, os.path.join(bdir, os.path.basename(fp)))

    # 断言：写前再全量复核一遍"新文本的每一条引文都在权威口径下命中或属待人工"
    manual_ids = {e for _, e, _ in manual}
    for fp, new_txt in writes.items():
        for blk, s, e in iter_entry_blocks(new_txt):
            m = VC.ENTRY.match(blk.split('\n')[0])
            eid = '%s-%s' % (m.group(1), m.group(2))
            qm = VC.QUOTE.search(blk)
            if not qm or eid in manual_ids:
                continue
            if VC.norm_match(qm.group(1)) not in CLEAN:
                print('🔴 断言失败（%s 仍不命中）⇒ **整批拒写**' % eid)
                return 1
    for fp, new_txt in writes.items():
        io.open(fp, 'w', encoding='utf-8', newline='\n').write(new_txt)
    print('\n✔ 已写盘 %d 个文件；备份：%s' % (len(writes), bdir))
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
