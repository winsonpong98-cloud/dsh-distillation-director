# -*- coding: utf-8 -*-
r"""build_ocr_text.py —— 把逐页 OCR 文本装配成**册级主文本**（纯引擎 · 零书别数据）

为什么需要它：
  `tools\ocr_deepseek_vision.py --dump` 把每页写成 `<逐页目录>\pNNNN.txt`（**逐页落盘＝中断不丢**），
  但下游（阶段0 骨架／防线3 的 R 引文回源／fidelity-R 闸）需要的是**单一册级文本＋稳定页锚**。
  本脚本即"装配器"，并把**口径与分母**写进产物头部（避坑手册 §10.2 交付数字必填字段）。

页锚格式：`===== [PAGE n] =====`（与 `ocr_pages.py` 产物同形 ⇒ `machine_layer_readycheck`
  的 `source_pages` 计数可直接识别）。

═══ 设计铁律（同 `make_extractor_prompts.py` · 见《避坑手册》A-69）═══
**本脚本是通用件，不得含任何一本书的数据。** 装配前两件事必须由**调用者显式给出**：
  · `--title`：册级标题（写进产物首行；提示词/判官会引用它 ⇒ 不许猜、不许留空）；
  · `--expect-pages`：期望页数（用于缺页分母 ⇒ 不许写死成上一册的 425）。
早期版本把书名、期望页数、任务 slug 默认值全部写死为上一册（本脚本已被巡检器
`tools\check_tools_generic.py` 判红），现改为**必填/无默认**。

用法：
  python tools\build_ocr_text.py --task <slug> --title "<册级标题>" --expect-pages <N> \
         [--src deepseek_text] [--out ocr_ds.txt]
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

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True, help='任务 slug（决定 .work/<slug>/）')
    ap.add_argument('--title', required=True, help='册级标题（写进产物首行；不得留空）')
    ap.add_argument('--expect-pages', type=int, required=True,
                    help='期望页数（缺页分母；**必填**，禁止沿用上一册的值）')
    ap.add_argument('--src', default='deepseek_text', help='逐页 txt 所在子目录（相对 .work/<task>/）')
    ap.add_argument('--out', default='ocr_ds.txt', help='输出主文本文件名（相对 .work/<task>/）')
    ap.add_argument('--engine-note', default=None,
                    help='写入首行的引擎说明**原文**（含既有格式符号，如 `` `deepseek-flash`（…） ``）；'
                         '缺省则省略该段。脚本不自行补反引号/括号（保证对既有产物逐字节复现）')
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    sd = os.path.join(work, a.src)
    if not os.path.isdir(sd):
        print('🔴 无逐页目录：%s' % sd)
        return 1
    files = {}
    for fn in os.listdir(sd):
        m = re.match(r'p(\d{4})\.txt$', fn)
        if m:
            files[int(m.group(1))] = os.path.join(sd, fn)
    if not files:
        print('🔴 逐页目录里没有任何 `pNNNN.txt`：%s（装配器拒绝产出空主文本）' % sd)
        return 1
    missing = [p for p in range(1, a.expect_pages + 1) if p not in files]
    over = [p for p in files if p > a.expect_pages]
    if over:
        print('⚠ 存在超出 --expect-pages(%d) 的页：%s…（共 %d 页）' % (a.expect_pages, over[:6], len(over)))

    L = []
    A = L.append
    # 首行模板：`# <标题>OCR 全文`（＋可选 ` —— 引擎 <engine-note 原文>`）。
    # ⚠ 渲染口径必须**逐字节**复现既有产物，否则等于悄悄改了主文本（A-69 同族）：
    #   `--title` 传**标题原文**（含书名号与括注，如 `《{标题}》（第 N 版）`），  # generic-ok: DOCREF
    #   其后**不留空格**，直接接 `OCR 全文`；
    #   `--engine-note` 传**已带反引号的引擎说明原文**（如 `` `deepseek-flash`（…） ``），脚本不再补符号。
    head = '# %sOCR 全文' % a.title
    if a.engine_note:
        head += ' —— 引擎 %s' % a.engine_note
    A(head)
    A('')
    A('> 装配器：`tools\\build_ocr_text.py` ｜ 逐页源：`.work\\%s\\%s\\pNNNN.txt`' % (a.task, a.src))
    A('> 页锚格式：`===== [PAGE n] =====`（与 `ocr_pages.py` 同形，便于 `machine_layer_readycheck` 计页）')
    A('> **口径**：页号＝PDF 物理页号（非书内印刷页号）；渲染 150dpi；图片按官方口径计费（每图封顶 1024 token）')
    A('> 页数：%d / %d 应为 ｜ 缺页：%s' % (len(files), a.expect_pages, missing if missing else '无'))
    A('')
    for p in sorted(files):
        t = io.open(files[p], encoding='utf-8', errors='replace').read().strip()
        A('===== [PAGE %d] =====' % p)
        A(t)
        A('')
    out = os.path.join(work, a.out)
    io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    body = sum(len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', io.open(files[p], encoding='utf-8',
                errors='replace').read())) for p in files)
    print('已写 %s（%d 页；正文可见字符 %d；缺页 %s）'
          % (out, len(files), body, missing if missing else '无'))
    # 顺序自证：产物里页锚数必须等于逐页文件数（防"循环漏页"这类静默丢内容）
    txt = io.open(out, encoding='utf-8').read()
    n_anchor = len(re.findall(r'=====\s*\[PAGE\s*\d+\]\s*=====', txt))
    ok = (n_anchor == len(files))
    print('装配自证：产物页锚 %d ／ 逐页文件 %d ⇒ %s' % (n_anchor, len(files), '✔ 一致' if ok else '🔴 不一致'))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
