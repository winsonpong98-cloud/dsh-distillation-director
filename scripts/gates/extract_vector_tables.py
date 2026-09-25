# -*- coding: utf-8 -*-
r"""extract_vector_tables.py —— **矢量表直取**（形态① 的抽取路 · 零模型调用 · 零 API 成本）

为什么要它（2026-09-21 · 第三册形态普查发现）：
  表格**不止一种形态**，而修补方式**完全不同**——普查三册实测出三种：
    · **① 矢量表**（文字层有网格线／行列结构）：PyMuPDF `find_tables()` 直取 ⇒ **无需 OCR、零成本**；
    · **③ 表体截图**（文字层只有标题／注／资料来源，表体是嵌入图像）：走
      `render_pdf_pages` → `map_table_images` → `ocr_deepseek_vision --kind table` → `assemble_table_bodies`；
    · **④ 整页扫描**：整册视觉 OCR。
  此前本工作区只造了 ③ 的路（表体补抽流水线）；实测**新册（研究报告体、61 页）恰是形态①**
  ⇒ 若不补这条路，用户遇到矢量表册会"有闸无器"。本件即 ① 的路。

判据（确定性）：
  · 表格对象＝`page.find_tables()` 的每个 `Table`（含 bbox）；
  · 表号归属＝该表 bbox **上方最近的那条「表N-M …」标题行**（与 `map_table_images.py` 同一思路：
    行首表号＋空白＋内容才算标题行，正文引用（"表1-1为…"）不算）；找不到标题则用 `p<页>-t<序>` 兜底编号；
  · 表下方紧邻的 `注：`／`资料来源` 行一并收进产物（它们属于该表）；
  · **逐格原样**：`extract()` 的结果不重排、不四舍五入；单元格内换行 `<br>` 化。

用法：
  python tools\extract_vector_tables.py --task <slug> --pdf "待读\某册.pdf" \
      --out-dir .work\<slug>\tablebodies --ledger .work\<slug>\矢量表抽取台账.md [--pages 1-60]
退出码：0 = 跑通（表 0 张也 rc=0，但会明说"本册无矢量表"）；1 = 缺件／解析失败
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

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _paths import ROOT                       # noqa: E402

TREF = re.compile(r'表\s*(\d{1,2})\s*[.\-–—]\s*(\d{1,2})')
TITLE = re.compile(r'^表\s*\d{1,2}\s*[.\-–—]\s*\d{1,2}\s+\S')
NOTE = re.compile(r'^(注：|注:|资料来源|数据来源)')


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in str(spec).split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-')
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [p for p in out if 1 <= p <= n]


def page_lines(page):
    out = []
    for blk in page.get_text('dict').get('blocks', []):
        for ln in blk.get('lines', []):
            t = ''.join(sp['text'] for sp in ln['spans']).strip()
            if t:
                out.append((round(ln['bbox'][1], 1), round(ln['bbox'][3], 1), t))
    return sorted(out)


def cell(x):
    return ('' if x is None else str(x)).replace('\n', '<br>').replace('|', '\\|').strip()


def md_table(rows):
    if not rows:
        return ''
    w = max(len(r) for r in rows)
    rows = [list(r) + [''] * (w - len(r)) for r in rows]
    L = ['| ' + ' | '.join(cell(c) for c in rows[0]) + ' |',
         '|' + '---|' * w]
    for r in rows[1:]:
        L.append('| ' + ' | '.join(cell(c) for c in r) + ' |')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--pages', default='')
    ap.add_argument('--out-dir', required=True, dest='outdir')
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--title-regex', default=None, dest='title_re',
                    help='标题行形态（默认「表N-M ＋空白 ＋内容」；**报告体常用「表N」**，'
                         '如实测某研究报告为 `表1`…`表6` ⇒ 换册须先做形态普查再给本参数）')
    ap.add_argument('--key-regex', default=None, dest='key_re',
                    help='从标题行取编号的正则：**2 个捕获组** ⇒ `N-M`；**1 个捕获组** ⇒ `N`')
    ap.add_argument('--verify', action='store_true',
                    help='逐格数值反查：抽出的含数字单元格须能在该页文字层（去空白）找到 ⇒ 抓到"单元格被切碎/串行"')
    a = ap.parse_args()
    titlere = re.compile(a.title_re) if a.title_re else TITLE
    keyre = re.compile(a.key_re) if a.key_re else TREF
    pdf = a.pdf if os.path.isabs(a.pdf) else os.path.join(ROOT, a.pdf)
    if not os.path.exists(pdf):
        print('🔴 找不到 PDF：%s' % pdf)
        return 1
    try:
        import fitz
    except Exception as e:
        print('🔴 未装 pymupdf（%s）：pip install pymupdf' % e)
        return 2
    doc = fitz.open(pdf)
    odir = a.outdir if os.path.isabs(a.outdir) else os.path.join(ROOT, a.outdir)
    os.makedirs(odir, exist_ok=True)
    pages = parse_pages(a.pages, doc.page_count)
    print('册：%s（%d 页）｜ 本次处理 %d 页' % (os.path.basename(pdf), doc.page_count, len(pages)))

    led, n_ok, n_notitle = [], 0, 0
    for p in pages:
        pg = doc[p - 1]
        try:
            tabs = pg.find_tables().tables
        except Exception:
            tabs = []
        if not tabs:
            continue
        lines = page_lines(pg)
        for k, tb in enumerate(tabs, 1):
            y0 = tb.bbox[1]
            above = [x for x in lines if x[1] <= y0 + 2]
            title, key = '', ''
            for yb, ye, txt in reversed(above):
                if titlere.match(txt):
                    title = txt
                    m = keyre.search(txt)
                    if m:
                        key = ('%s.%s' % (m.group(1), m.group(2))) if (m.lastindex or 0) >= 2 \
                            else m.group(1)
                    break
            if not key:
                key = 'p%d-t%d' % (p, k)
                n_notitle += 1
            rows = tb.extract()
            body = md_table(rows)
            # 逐格数值反查（可选 · 确定性 · 零成本）：矢量表的数字**本就在文字层**，
            #   ⇒ 抽出来的每个含数字单元格都应能在该页文字层（去空白后）找到；
            #   找不到 ⇒ 多半是**单元格被切碎/串行**（A-36 家族：别把"抽坏了"当"原文如此"）。
            vrate, vmiss = None, []
            if a.verify:
                ptxt = re.sub(r'\s', '', pg.get_text('text'))
                toks = [re.sub(r'\s', '', str(c)) for r in rows for c in (r or [])
                        if c and re.search(r'\d', str(c))]
                vmiss = [t for t in toks if t not in ptxt][:5]
                vrate = (len(toks) - len(vmiss)) / len(toks) if toks else None
            notes = [t for yb, ye, t in lines if yb >= tb.bbox[3] - 2 and NOTE.match(t)][:2]
            fn = '表%s.md' % key
            L = ['# 表 %s ｜ %s' % (key, title or '（页内无「表N-M」标题行 ⇒ 以页序编号）'),
                 '',
                 '> 数据件 · **矢量表直取**（来源：`%s` 第 %d 页；工装：`tools\\extract_vector_tables.py`，'
                 'PyMuPDF `find_tables()`，**零模型调用**）' % (os.path.basename(pdf), p),
                 '> ⚠ 数据层产物：逐格照抄，**未做任何数值修正**；单元格内换行以 `<br>` 表示。', '',
                 body, '']
            for nt in notes:
                L += ['> %s' % nt]
            io.open(os.path.join(odir, fn), 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
            n_ok += 1
            led.append((key, title or '（无标题行）', p, len(rows), len(rows[0]) if rows else 0,
                        ('有注/来源行' if notes else '—'),
                        ('—' if vrate is None else '%.0f%%' % (vrate * 100)),
                        ('、'.join(vmiss)[:40] if vmiss else '')))
    L = ['# 矢量表抽取台账 · %s' % a.task, '',
         '> 工装：`tools\\extract_vector_tables.py`（形态① 矢量表直取；**零模型调用**）',
         '> 源：`%s` ｜ 产物：`%s`' % (os.path.basename(pdf), os.path.relpath(odir, ROOT)), '',
         '| 表号 | 页内标题行 | 页 | 行数 | 列数 | 附属行 | 数值反查 | 未命中样例 |', '|---|---|---|---|---|---|---|---|']
    L += ['| 表 %s | %s | p%d | %d | %d | %s | %s | %s |' % r for r in led]
    L += ['', '## 计数', '',
          '取到表 **%d** 张 ｜ 其中**页内无「表N-M」标题行**（以页序编号）**%d** 张 —— 后者须人核归属，'
          '因为报告体常用「表1」「表2」这类无点号编号（`--tref` 若要覆盖须先做形态普查）' % (n_ok, n_notitle), '',
          '## 边界声明', '',
          '1. **矢量表直取的准确率取决于 PDF 的网格线**：`find_tables()` 对"无线框表"（仅靠空白分列）会漏；'
          '实测本册（研究报告体）命中页数与条状图页数并存 ⇒ **换册必须跑 `probe_book_form.py` 先定形态**；',
          '2. **本件不做数值核对**：抽出来的数字须与页图／原文抽查比对（同 `assemble_table_bodies.py` 的纪律）；',
          '3. **表号归属是位置推断**：标题行在该表 bbox 上方最近处 ⇒ 与 `map_table_images.py` 同一判据、同一风险。', '']
    lp = a.ledger if os.path.isabs(a.ledger) else os.path.join(ROOT, a.ledger)
    io.open(lp, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print('→ 台账 %s ／ 数据件 %d 件 → %s' % (lp, n_ok, odir))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
