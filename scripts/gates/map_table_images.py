# -*- coding: utf-8 -*-
r"""map_table_images.py —— **表号 ↔ 页内嵌入图像** 的确定性配对（任务通用 · 零模型调用）

为什么要它（2026-09-21 · 见附加观察 O-41/O-43）：
  「文字版」PDF 的**表体就是截图贴进 PDF 的图像**（实测某册 p16 图即该册表1-3 全表，
  而 `find_tables()` 返回 0、文字层只有标题／注／资料来源行）。
  全册 **215 个图像对象散布在 148 页**，其中绝大多数是**插图/软件截图**而非表格
  ⇒ 若"整册图像都 OCR"，则 **90% 的模型调用花在非表格图上**（浪费且稀释产物）。
  ⇒ 先做**位置配对**：表标题（表N-M 标题行）**下方最近的图像**＝该表表体。

判据（全部确定性，不做语义判断）：
  ① **标题行**＝行首 `表 N-M` ＋ **空白** ＋ 后续文字（"表1-1为…"这类正文引用**没有空白** ⇒ 排除）；
  ② **配对**＝该标题 rect **下方**（y0 ≥ 标题 y1）**同页**距离最小的图像；同页无 ⇒ 退到**下一页页首**图像；
  ③ 记 `dist`（标题底到图顶的距离）与 `same_page`；`dist` 过大或多标题共享一图 ⇒ 标 `疑`，交人工裁。

用法：
  python tools\map_table_images.py --task <slug> --pdf "待读\<书名>.pdf" \
      --out .work\guozhai-qihuo\表图像映射.md --json .work\guozhai-qihuo\表图像映射.json
退出码：0 = 跑通；1 = 缺件；2 = 环境缺件
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

TREF = re.compile(r'表\s*(\d{1,2})\s*[.\-–—]\s*(\d{1,2})')
# 标题行：行首表号 + 空白 + 内容（正文引用「表1-1为…」无空白 ⇒ 被排除）
TITLE = re.compile(r'^表\s*\d{1,2}\s*[.\-–—]\s*\d{1,2}\s+\S')
# 表体区内的附属文字行（不终止表体区）：注：/资料来源：/数据来源：
NOTE = re.compile(r'^(注：|注:|资料来源|数据来源)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--json', default=None)
    ap.add_argument('--max-dist', type=float, default=90.0,
                    help='标题底→图顶的容许距离(pt)；超过即标疑（默认 90）')
    a = ap.parse_args()

    pdf = a.pdf if os.path.isabs(a.pdf) else os.path.join(ROOT, a.pdf)
    if not os.path.exists(pdf):
        print('🔴 找不到 PDF：%s' % pdf); return 1
    try:
        import fitz
    except Exception as e:
        print('🔴 未装 pymupdf：%s' % e); return 2
    task_dir = os.path.join(ROOT, '.work', a.task)
    idir = os.path.join(task_dir, 'tableimgs')
    if not os.path.isdir(idir):
        print('🔴 缺图像目录（先跑 render_pdf_pages.py --extract-images）：%s' % idir); return 1

    doc = fitz.open(pdf)
    # ① 逐页取标题 rect ＋ 全部文字行（供"表体区"判据用；都用 get_text('dict') 的行级 bbox）
    titles = []          # (page, key, text, rect)
    lines_by_page = {}   # page -> [(y0, y1, text)]
    for i in range(doc.page_count):
        pg = doc[i]
        d = pg.get_text('dict')
        ls = []
        for blk in d.get('blocks', []):
            for ln in blk.get('lines', []):
                txt = ''.join(sp['text'] for sp in ln['spans']).strip()
                if not txt:
                    continue
                bbox = tuple(round(float(v), 1) for v in ln['bbox'])
                ls.append((bbox[1], bbox[3], txt))
                if TITLE.match(txt):
                    m = TREF.search(txt)
                    if m:
                        titles.append((i + 1, '%s.%s' % (m.group(1), m.group(2)), txt, bbox))
        if ls:
            lines_by_page[i + 1] = sorted(ls)
    # ② 逐页取图像（与 render_pdf_pages.py 同一口径：idx 从 1 起，文件名 p%04d_i%02d.*）
    imgs_by_page = {}
    for i in range(doc.page_count):
        info = doc[i].get_image_info(xrefs=True)
        lst = []
        for k, im in enumerate(info, 1):
            lst.append({'idx': k, 'bbox': tuple(round(float(v), 1) for v in im.get('bbox', (0, 0, 0, 0))),
                        'w': im.get('width'), 'h': im.get('height'), 'bytes': im.get('size') or 0})
        if lst:
            imgs_by_page[i + 1] = lst

    def band(page, y1, max_pages=3):
        """表体区 = 标题行下方，**直到第一条正文行**之间的**全部图像**（可跨页、可多张）。

        🔴 模型更正（2026-09-21 实测 · O-44）：初版假设"一张表 = 一张图"，**实测为假**——
        表1-1 由**两张图**构成（第二张右上角标「（续）」），首版只取了第一张 ⇒ 表体被腰斩。
        新判据（本册版式普查得出）：`表标题` 与 `注：/资料来源：` 之间的**所有**图像都属于该表；
        遇到**非**注/资料来源的正文行 ⇒ 表体区结束；页末未结束 ⇒ 续到下一页（最多 max_pages 页）。
        """
        out, notes, q, ys, reason = [], [], page, y1, '正文行'
        for _hop in range(max_pages):
            lines = [x for x in lines_by_page.get(q, []) if x[0] >= ys - 1]
            imgs = [x for x in imgs_by_page.get(q, []) if x['bbox'][1] >= ys - 1]
            seq = ([('L', x[0], x[2]) for x in lines] + [('I', x['bbox'][1], x['idx']) for x in imgs])
            seq.sort(key=lambda z: z[1])
            ended = False
            for kind, y0, payload in seq:
                if kind == 'I':
                    out.append((q, payload))
                else:
                    if NOTE.match(payload):
                        notes.append(payload)         # 注/资料来源 ⇒ 仍属表体区，且随册交付
                        continue
                    if TITLE.match(payload):
                        ended, reason = True, '撞上下一张表的标题'
                        break
                    ended, reason = True, '正文行'
                    break
            if ended:
                return out, notes, reason
            q += 1
            ys = 0
        return out, notes, '超过 %d 页上限' % max_pages

    rows, unpicked = [], []
    for page, key, txt, rect in titles:
        got, notes, why = band(page, rect[3])
        if not got:
            unpicked.append((page, key, txt))
            continue
        ip, ii = got[0]
        im0 = next(x for x in imgs_by_page[ip] if x['idx'] == ii)
        dist = im0['bbox'][1] - rect[3]
        flag = '' if (len(got) > 1 or (ip == page and dist <= a.max_dist)) else '疑'
        rows.append({'key': key, 'title': txt, 'title_page': page, 'title_bbox': rect,
                     'imgs': [{'page': p, 'idx': i} for p, i in got],
                     'n_imgs': len(got), 'end_reason': why, 'notes': notes,
                     'img_page': ip, 'img_idx': ii, 'dist': round(dist, 1),
                     'same_page': ip == page, 'flag': flag})

    # ③ 一图多表 / 多表一图 的自查
    by_img = {}
    for r in rows:
        for im in r['imgs']:
            by_img.setdefault((im['page'], im['idx']), []).append(r['key'])
    dup = {k: v for k, v in by_img.items() if len(v) > 1}
    used = set(by_img)
    n_img = sum(len(v) for v in imgs_by_page.values())

    L = ['# 表号 ↔ 页内嵌入图像 配对表 · %s' % a.task, '',
         '> 工装：`tools\\map_table_images.py`（确定性；判据：标题行 = 行首「表N-M」＋空白＋内容）',
         '> PDF：`%s`（共 %d 页）｜ 图像对象 %d 个（%d 页含图）'
         % (os.path.basename(pdf), doc.page_count, n_img, len(imgs_by_page)),
         '> 标题行（判据①）**%d** 条 ｜ 成功配对 **%d** 条 ｜ 未配对 **%d** 条'
         % (len(titles), len(rows), len(unpicked)),
         '> 🔴 口径更正（O-44）：**一张表可由多张图构成**（续页/续图，图上标「（续）」）——',
         '> 表体区 ＝ 标题行与 `注：/资料来源：` 之间**全部**图像；本册实测 **%d/%d** 张表为多图。'
         % (sum(1 for r in rows if r['n_imgs'] > 1), len(rows)), '',
         '| 表号 | 标题（页内原样） | 标题页 | 表体图（按 y 序） | 图数 | 区末判据 | 首图距离pt | 判态 |',
         '|---|---|---|---|---|---|---|---|']
    for r in rows:
        figs = '、'.join('p%04d_i%02d' % (im['page'], im['idx']) for im in r['imgs'])
        L.append('| 表 %s | %s | p%d | %s | %d | %s | %.1f | %s |'
                 % (r['key'], r['title'][:38], r['title_page'], figs, r['n_imgs'],
                    r['end_reason'], r['dist'], ('⚠ ' + r['flag']) if r['flag'] else '✔'))
    if unpicked:
        L += ['', '## 未配对（须人工裁）', '', '| 表号 | 标题 | 标题页 |', '|---|---|---|']
        for page, key, txt in unpicked:
            L.append('| %s | %s | p%d |' % (key, txt[:48], page))
    L += ['', '## 自查', '',
          '| 项 | 值 |', '|---|---|',
          '| 一图被多表占用 | %s |' % (('；'.join('%s→%s' % (('p%d_i%d' % k), '、'.join(v))
                                                for k, v in dup.items())) or '0 处'),
          '| 未被任何表占用的图像 | %d 个（多为插图/软件截图 ⇒ 不 OCR） |' % (n_img - len(used)), '',
          '## 边界声明', '',
          '1. **配对是位置＋版式推断，不是内容核对**：`✔` 只说明"标题与来源行之间就是这些图"，'
          '不证明图里写的就是这张表 ⇒ 归属正确性须由 `tools\\check_table_ocr.py` 独立核（文本证据／版式证据）；',
          '2. **一张表可由多张图构成**（本册实测 %d/%d 张；续图右上角标「（续）」）'
          '⇒ 首版"一张表＝一张图"的假设**是错的**，曾把表1-1 腰斩（O-44）；'
          % (sum(1 for r in rows if r['n_imgs'] > 1), len(rows)),
          '3. **表体区止于第一条正文行**：`注：/资料来源/数据来源` 行**不**终止表体区（它们属于该表）；'
          '撞上"下一张表的标题"也终止（表3-1 即此情形）；',
          '4. `dist` 为负＝首图在次页（跨页表体），属正常版式，**不是**错误；'
          '`疑` 标记只在"首图不在标题页且同页无多图"时给出。', '']

    out = '\n'.join(L)
    op = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    io.open(op, 'w', encoding='utf-8').write(out + '\n')
    if a.json:
        jp = a.json if os.path.isabs(a.json) else os.path.join(ROOT, a.json)
        io.open(jp, 'w', encoding='utf-8').write(json.dumps(
            {'task': a.task, 'pdf': pdf, 'n_img': n_img, 'rows': rows,
             'unpicked': unpicked, 'dup': {'%d_%d' % k: v for k, v in dup.items()}},
            ensure_ascii=False, indent=1))
    print(out)
    print('→ 已写入 %s' % op)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
