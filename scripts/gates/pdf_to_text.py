# -*- coding: utf-8 -*-
r"""pdf_to_text.py —— 文字版 PDF → 蒸馏主文本（带行首页锚），**免 OCR**

用途：书籍 PDF 若自带文本层（非扫描版），走本脚本直抽，**不产生任何 OCR 费用**。
判据（先跑 `probe_textlayer_pages.py` 或本脚本 `--probe`）：全书文本层字符数量级
与"页数 × 每页字数"相符（例：260 页 → 13 万字符以上）即判为文字版。

输出（写入 `<out>`，默认 `.work/<task>/book_text.md`）：
    [p1]
    第一段落第一行
    第一段落第二行
    ...
    [p2]
    ...
——**页锚 `[p<n>]` 独占一行、位于该页正文之前**；正文逐行保留（不合并段落、不折行），
以便下游"逐字引文回源"按字符比对（比对器须忽略空白差异：本抽取按行切，行间为换行）。

**自证（内置）**：输出"输入页数 / 有字符页数 / 输出字符数 / 页锚数"，并断言
`页锚数 == 输入页数`；再对全书做一次 `去空白后字符数` 的前后对账，缺失即报红退出。
（依据：A-11「闸必须自证覆盖」；不许"跑了就算过"。）

用法（本脚本是通用件，**不认识任何书名**）：
    python tools\pdf_to_text.py --task <slug> --pdf "<待读目录下的 PDF 文件名>"
    python tools\pdf_to_text.py --pdf <path> --probe          # 只判定文字版/扫描版
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

try:
    import fitz  # pymupdf
except ModuleNotFoundError:
    import sys as _s
    _s.stderr.write("\n[X] 缺第三方依赖 PyMuPDF（import fitz）——本工具无法运行。\n"
                   "    请先安装：pip install pymupdf（或 python -m pip install PyMuPDF）\n"
                   "    说明：本件负责 PDF 文本/版面提取，属可选能力；不装它不影响其它门禁。\n"
                   "    退出码 2 表示『依赖缺失（指引式失败）』，不是代码错误。\n")
    _s.exit(2)

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
def iter_pages(doc):
    """逐页产出 (页号 1-based, 该页原始文本)。"""
    for i in range(doc.page_count):
        yield i + 1, (doc[i].get_text() or '')


def probe(doc):
    tot, nonempty = 0, 0
    for _, t in iter_pages(doc):
        s = t.strip()
        tot += len(s)
        if s:
            nonempty += 1
    per = tot / float(max(1, doc.page_count))
    verdict = '文字版（可直抽，免 OCR）' if per >= 200 else '扫描版或文本层严重缺失（须 OCR）'
    print('页数 %d ｜ 有字符页 %d ｜ 文本层合计 %d 字符 ｜ 均值 %.0f 字符/页'
          % (doc.page_count, nonempty, tot, per))
    print('判定：%s' % verdict)
    return per >= 200


def clean_page(t):
    """页内清理：统一换行、去行尾空白、去连续空行。
    **不删任何字符**——页眉页脚与页码一律保留（原样即真值，删了会毁"逐字回源"）。"""
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.rstrip() for ln in t.split('\n')]
    # 压掉连续空行（≥2 → 1），但保留段间空行
    out, blank = [], 0
    for ln in lines:
        if ln.strip() == '':
            blank += 1
            if blank <= 1:
                out.append('')
        else:
            blank = 0
            out.append(ln)
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)


def norm_ws(s):
    """去空白归一（仅供对账与下游比对，不用于落盘）。"""
    return re.sub(r'\s+', '', s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', required=True, help='PDF 路径（相对 ROOT 或绝对）')
    ap.add_argument('--task', default=None, help='任务 slug ⇒ 输出 .work/<task>/book_text.md')
    ap.add_argument('--out', default=None, help='显式输出路径（优先于 --task）')
    ap.add_argument('--probe', action='store_true', help='只判定文字版/扫描版，不落盘')
    a = ap.parse_args()

    pdf = a.pdf if os.path.isabs(a.pdf) else os.path.join(ROOT, a.pdf)
    if not os.path.exists(pdf):
        print('🔴 找不到 PDF：%s' % pdf)
        return 1

    doc = fitz.open(pdf)
    ok = probe(doc)
    if a.probe:
        doc.close()
        return 0 if ok else 2

    if not ok:
        print('🔴 判定为扫描版：本脚本不适用（应走 OCR 流程 ocr_pages.py → build_ocr_text.py）')
        doc.close()
        return 2

    page_count = doc.page_count
    parts, raw_chars = [], 0
    n_anchor = 0
    for n, t in iter_pages(doc):
        raw_chars += len(norm_ws(t))
        parts.append('[p%d]' % n)
        n_anchor += 1
        c = clean_page(t)
        if c:
            parts.append(c)
    doc.close()

    body = '\n'.join(parts) + '\n'
    # 自证口径：**把页锚剥掉**再与输入正文对账——页锚是新增标注，不是正文
    # （自伤登记：首版把页锚算进"正文"，260 个页锚使两数不等，闸把一次正确抽取判成红）
    body_nows = norm_ws(re.sub(r'^\[p\d+\]$', '', body, flags=re.M))
    out_chars = len(body_nows)

    if a.out:
        op = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    elif a.task:
        op = os.path.join(ROOT, '.work', a.task, 'book_text.md')
    else:
        print('🔴 必须给 --task 或 --out 之一')
        return 1
    os.makedirs(os.path.dirname(op), exist_ok=True)

    nlines = body.count('\n')
    if os.path.exists(op):
        old = io.open(op, encoding='utf-8', errors='replace').read()
        print('⚠ 目标已存在（%d B）→ 覆盖。旧文件长度 %d 字符' % (os.path.getsize(op), len(old)))
    io.open(op, 'w', encoding='utf-8', newline='\n').write(body)

    print('-' * 64)
    print('输出：%s' % op)
    print('页锚行 %d ｜ 总行数 %d ｜ 落盘 %.1f KB' % (n_anchor, nlines, os.path.getsize(op) / 1024.0))
    print('去空白字符对账（页锚已剥离）：输入正文 %d ｜ 输出正文 %d ｜ 差 %d'
          % (raw_chars, out_chars, raw_chars - out_chars))
    # 自证断言
    bad = []
    if n_anchor != page_count:
        bad.append('页锚数 %d ≠ 输入页数' % n_anchor)
    if raw_chars != out_chars:
        bad.append('前后字符数不等（有丢失，须查 clean_page）')
    if not re.match(r'^\[p1\]\n', body):
        bad.append('首行不是 [p1] 页锚')
    if bad:
        print('🔴 自证失败：%s' % '；'.join(bad))
        return 1
    print('✔ 自证通过：页锚数＝输入页数；字符零丢失；首行页锚正确')
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
