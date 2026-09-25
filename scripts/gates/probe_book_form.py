# -*- coding: utf-8 -*-
r"""probe_book_form.py —— 第三册**形态普查**（决定表体补抽流水线适不适用 · 零模型调用）

为什么（O-41/O-43 的推广纪律）："换册必须重跑同一条流水线，不得假定文字版免 OCR"——
但**换册前要先做形态普查**：这本书的表格在**文字层**、在**嵌入图像**、还是**整页扫描件**？
三种形态对应三种修法，**猜错就会白烧 OCR 或建出错误数据件**。

判据（确定性，逐页统计）：
  · 文字层字数／页；含"表 N"引用的页；含 `^\|` 管道表的页；
  · 嵌入图像数／页，及其 bbox 占页面比例（**整页图＝扫描版**，行内条状图＝表体截图）；
  · `page.find_tables()` 命中页数（矢量表）。
输出：一张逐页表 ＋ 一句结论（四类形态：①矢量表 ②文字层表格 ③表体截图 ④整页扫描）。
用法：python tools\..\probe_book_form.py <pdf 路径> [<pdf 路径> ...]
"""
import io
import os
import re
import sys

try:
    import fitz  # pymupdf
except ModuleNotFoundError:
    import sys as _s
    _s.stderr.write("\n[X] 缺第三方依赖 PyMuPDF（import fitz）——本工具无法运行。\n"
                   "    请先安装：pip install pymupdf（或 python -m pip install PyMuPDF）\n"
                   "    说明：本件负责 PDF 文本/版面提取，属可选能力；不装它不影响其它门禁。\n"
                   "    退出码 2 表示『依赖缺失（指引式失败）』，不是代码错误。\n")
    _s.exit(2)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

TREF = re.compile(r'表\s*\d{1,2}\s*[.\-–—]\s*\d{1,2}')
TREF2 = re.compile(r'(?m)^表\s*\d{1,3}[\s　]')


def probe(path):
    doc = fitz.open(path)
    print('=' * 96)
    print('册：%s ｜ 页数 %d' % (os.path.basename(path), doc.page_count))
    rows, n_txt_pages, n_scan, n_band, n_vec = [], 0, 0, 0, 0
    for i in range(doc.page_count):
        pg = doc[i]
        t = pg.get_text('text')
        chars = len(re.sub(r'\s', '', t))
        imgs = pg.get_image_info(xrefs=True)
        ph = pg.rect.height
        full = sum(1 for x in imgs if (x['bbox'][3] - x['bbox'][1]) > 0.85 * ph)
        band = len(imgs) - full
        try:
            nt = len(pg.find_tables().tables)
        except Exception:
            nt = 0
        pipes = len(re.findall(r'(?m)^\|', t))
        refs = len(TREF.findall(t)) + len(TREF2.findall(t))
        if chars > 200:
            n_txt_pages += 1
        if full:
            n_scan += 1
        if band:
            n_band += 1
        if nt:
            n_vec += 1
        rows.append((i + 1, chars, refs, pipes, len(imgs), full, band, nt))
    L = ['| 页 | 文字层字数 | 表号引用 | 管道表行 | 嵌入图 | 其中整页图 | 条状图 | 矢量表 |',
         '|---|---|---|---|---|---|---|---|']
    for r in rows:
        L.append('| p%d | %d | %d | %d | %d | %d | %d | %d |' % r)
    print('\n'.join(L[:14]))          # 只打前 12 页（长册时避免刷屏；完整表由调用方重定向到文件）
    if len(L) > 14:
        print('   …（后 %d 页略，见重定向文件）' % (len(L) - 14))
    print('-' * 96)
    print('汇总：文字层有内容的页 %d/%d ｜ 含整页图（扫描式）的页 %d ｜ 含条状图（表体截图候选）的页 %d ｜ 含矢量表的页 %d'
          % (n_txt_pages, doc.page_count, n_scan, n_band, n_vec))
    if n_vec:
        verdict = '① 矢量表为主 ⇒ 可用 PyMuPDF `find_tables()` 直取（无需 OCR）'
    elif n_band and n_txt_pages > doc.page_count * 0.6:
        verdict = '③ 文字版 ＋ 表体截图 ⇒ **本工作区「表体补抽流水线」适用**（render→map→ocr→assemble）'
    elif n_txt_pages < doc.page_count * 0.4:
        verdict = '④ 扫描版为主 ⇒ 走整册视觉 OCR（`pdf_to_text` 不可用；用 `ocr_pages`／`ocr_deepseek_vision`）'
    elif n_txt_pages > doc.page_count * 0.6:
        verdict = '② 文字层为主、未见条状图 ⇒ 先按文字层抽（`pdf_to_text`），**再逐表清点**确认表体是否真在'
    else:
        verdict = '⚠ 形态混杂 ⇒ 逐页看汇总，**不得一刀切**'
    print('结论：%s' % verdict)
    return 0


if __name__ == '__main__':
    USAGE = ('用法：python probe_book_form.py <pdf> [<pdf> ...]\n'
             '  作用：**形态普查**——判定该册的表格在哪一层，据此选抽取路：\n'
             '    ① 矢量表   ⇒ `extract_vector_tables.py`（零模型调用）\n'
             '    ③ 表体截图 ⇒ `render_pdf_pages` → `map_table_images` → `ocr_deepseek_vision --kind table`'
             ' → `assemble_table_bodies`\n'
             '    ④ 整页扫描 ⇒ 整册视觉 OCR（`ocr_pages` / `ocr_deepseek_vision`）\n'
             '  依赖：pymupdf（`pip install pymupdf`）')
    # ⚠ 2026-09-21（异机装完即用批）：本件由一次性脚本提升为随包件时**漏了 `--help` 处理** ——
    #   异机安装仿真当场抓到（把 `--help` 当 PDF 路径 ⇒ `fitz.open('--help')` 裸栈），
    #   发版闸据此把 tgz 改名 `*.BLOCKED`（rc=10）。⇒ 已补：`-h/--help` 打用法、缺文件/缺库给指引。
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(USAGE)
        sys.exit(0 if len(sys.argv) > 1 else 2)
    try:
        import fitz  # noqa: F401
    except Exception as e:
        print('🔴 未装 pymupdf（%s）：pip install pymupdf\n%s' % (e, USAGE))
        sys.exit(2)
    bad = [p for p in sys.argv[1:] if not os.path.isfile(p)]
    if bad:
        print('🔴 找不到文件：%s\n%s' % ('、'.join(bad), USAGE))
        sys.exit(2)
    for p in sys.argv[1:]:
        probe(p)
    sys.exit(0)
