# -*- coding: utf-8 -*-
r"""render_pdf_pages.py —— **PDF 页渲染 ＋ 嵌入图像抽离**（任务通用 · 确定性 · 零模型调用）

为什么要它（2026-09-21 能力审计缺口 · 见附加观察 O-41/O-42）：
  `ocr_deepseek_vision.py` 明文写着"**只读复用**已渲染的页图 `.work\<task>\pages\pNNNN.png`，
  不重新渲染"——即**渲染这一步从来就没有工具**，靠一次性脚本凑。后果：
  ① 换任务（如某册文字版）无图可 OCR ⇒ 表格专项修法走不通；
  ② 文本层抽取丢的表体，**只能回到页面像素**才能补（O-41 实测：文字版 31 张表里 26 张表体全无，
     而该 PDF 页内**确有嵌入图像** ⇒ 表体是**截图贴进 PDF 的图像**，不在文字层）。

能力（两件事，都只读 PDF、只写本任务目录）：
  ① `--pages` 渲染页图 → `.work\<task>\pages\pNNNN.png`（文件名口径与既有 OCR 脚本一致，四位补零）；
  ② `--image-info` 列出每页**嵌入图像的数量与 bbox**（判断"表体是不是图像"）；
  ③ `--extract-images` 把嵌入图像原样导出 → `.work\<task>\tableimgs\p<页>_i<序号>.<ext>`
     （附 `_index.json`：页／序号／bbox／宽高／字节数），供"逐表 OCR"用（比整页 OCR 更聚焦、更省 token）。

用法：
  # 1) 探明表体层级（先做形态普查，不猜）
  python tools\render_pdf_pages.py --pdf "待读\某书.pdf" --task <slug> --pages 14,15,16 --image-info
  # 2) 渲染页图（给视觉 OCR 复用）
  python tools\render_pdf_pages.py --pdf "待读\某书.pdf" --task <slug> --pages 14-40 --dpi 150
  # 3) 导出嵌入图像（表体截图）
  python tools\render_pdf_pages.py --pdf "待读\某书.pdf" --task <slug> --pages 14-40 --extract-images

退出码：0 = 跑通；1 = 缺文件／无页可渲染；2 = 环境缺件（未装 pymupdf / 未初始化工作区）
"""
import argparse
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _paths import ROOT                       # noqa: E402


def parse_pages(spec):
    out = []
    for part in str(spec).split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            s, e = part.split('-')
            out += list(range(int(s), int(e) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', required=True, help='PDF 路径（相对工作区根或绝对）')
    ap.add_argument('--task', required=True, help='任务 slug（产物落 .work\\<slug>\\）')
    ap.add_argument('--pages', default='', help='页号，如 14,15 或 14-40；默认全书（慎用）')
    ap.add_argument('--dpi', type=int, default=150)
    ap.add_argument('--force', action='store_true', help='已存在的页图重新渲染（默认跳过 ⇒ 不白烧时间）')
    ap.add_argument('--image-info', action='store_true', dest='image_info',
                    help='列出每页嵌入图像数量与 bbox（判"表体是否图像"用）')
    ap.add_argument('--extract-images', action='store_true', dest='extract_images',
                    help='导出嵌入图像到 .work\\<task>\\tableimgs\\')
    a = ap.parse_args()

    pdf = a.pdf if os.path.isabs(a.pdf) else os.path.join(ROOT, a.pdf)
    if not os.path.exists(pdf):
        print('🔴 找不到 PDF：%s' % pdf)
        print('   fallback：① 检查路径是否含全角括号《》；② 用 glob 自查 待读\\*关键词*.pdf')
        return 1
    try:
        import fitz                                        # noqa: F401
    except Exception as e:
        print('🔴 未装 pymupdf（%s）：pip install pymupdf' % e)
        return 2

    import fitz
    doc = fitz.open(pdf)
    n = doc.page_count
    pages = parse_pages(a.pages) if a.pages else list(range(1, n + 1))
    pages = [p for p in pages if 1 <= p <= n]
    if not pages:
        print('🔴 无有效页：--pages=%r（PDF 共 %d 页）' % (a.pages, n))
        return 1

    work = os.path.join(ROOT, '.work', a.task)
    if not os.path.isdir(work):
        print('🔴 缺任务目录：%s（先 init_workspace 或建目录）' % work)
        return 2
    pdir = os.path.join(work, 'pages')
    idir = os.path.join(work, 'tableimgs')

    print('PDF = %s  pages=%d  本次处理 %d 页  dpi=%d' % (os.path.basename(pdf), n, len(pages), a.dpi))
    made, skipped, imgs = 0, 0, []
    if not a.image_info and not a.extract_images:
        os.makedirs(pdir, exist_ok=True)
    if a.extract_images:
        os.makedirs(idir, exist_ok=True)

    for p in pages:
        pg = doc[p - 1]
        # ---- ① 页图渲染 ----
        if not a.image_info and not a.extract_images:
            dst = os.path.join(pdir, 'p%04d.png' % p)
            if os.path.exists(dst) and not a.force:
                skipped += 1
            else:
                pg.get_pixmap(dpi=a.dpi).save(dst)
                made += 1
        # ---- ② 嵌入图像清单 ----
        if a.image_info or a.extract_images:
            info = pg.get_image_info(xrefs=True)
            for i, im in enumerate(info, 1):
                bb = [round(float(v), 1) for v in im.get('bbox', (0, 0, 0, 0))]
                rec = {'page': p, 'idx': i, 'xref': im.get('xref'),
                       'bbox': bb, 'w': im.get('width'), 'h': im.get('height'),
                       'bytes': im.get('size') or 0}
                imgs.append(rec)
                if a.image_info:
                    print('  p%-4d img#%d  bbox=%s  %sx%s  %sB  xref=%s'
                          % (p, i, bb, rec['w'], rec['h'], rec['bytes'], rec['xref']))
                if a.extract_images and im.get('xref'):
                    try:
                        d = doc.extract_image(im['xref'])
                        fn = 'p%04d_i%02d.%s' % (p, i, d.get('ext', 'png'))
                        with open(os.path.join(idir, fn), 'wb') as fh:
                            fh.write(d['image'])
                        rec['file'] = fn
                    except Exception as e:
                        rec['file'] = None
                        rec['err'] = str(e)[:120]

    if not a.image_info and not a.extract_images:
        print('渲染完成：新渲染 %d 页 ／ 跳过已存在 %d 页  → %s' % (made, skipped, pdir))
    if a.image_info or a.extract_images:
        nz = [r for r in imgs if r['bytes']]
        print('-' * 74)
        print('含嵌入图像的页 = %d ／ 本次处理 %d 页；图像对象 %d 个'
              % (len({r['page'] for r in imgs}), len(pages), len(imgs)))
        if a.extract_images:
            io.open(os.path.join(idir, '_index.json'), 'w', encoding='utf-8').write(
                json.dumps(imgs, ensure_ascii=False, indent=1))
            print('图像已导出 → %s（_index.json 含页/序号/bbox/宽高/字节）' % idir)
        if not imgs:
            print('⚠ 本批页**无嵌入图像** ⇒ 表体若也缺失，则属"矢量绘制或被抽取脚本丢弃"'
                  '（改走 `page.get_drawings()` 或视觉整页 OCR，别假定是截图）')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
