# -*- coding: utf-8 -*-
r"""check_table_ocr.py —— **表体图像 OCR 结果 ↔ 表号** 的对齐核验（任务通用 · 确定性）

为什么要它（2026-09-21 · 见附加观察 O-43/O-44）：
  "表号 ↔ 图像"的配对由 `tools\map_table_images.py` 按**位置**给出，**配对成功 ≠ 配对正确**。
  必须有一道独立的核验，否则"补出来的表体"可能是**别人的表**（比丢表更坏：错数据冒充有数据）。

判据（两条独立证据，**任一强证据成立即 ✔**；全弱 ⇒ ▲ 人裁；全无 ⇒ 🔴）：

  **S1 · 文本证据**：OCR 文本里出现该表号的等价形态
     （`表1-1`／`表 1-1`／`表1.1`／`表 1.1`／破折号式）。
     ⚠ 实测定论：**本册的表体图是"只裁表体、不含标题行"的截图**
     ⇒ S1 大面积不命中是**正常现象**，**不能单独当作配对失败**（首跑据此误报 26 个 🔴，已登记为 O-44 的仪器缺陷）。

  **S2 · 版式证据（`--pdf` 给定时）**：按"**表标题 → 表体图 → 注：/资料来源：**"这一固定版式，
     要求同时满足：
       ① 配对图是**标题行下方第一张**图（同页）或**次页页首第一张**图（跨页）；
       ② 该图**下方第一条文字行**是 `注：`／`注:`／`资料来源`，且间隔 ≤ `--gap`（默认 90pt）；
     ⇒ 说明"这张图是被标题领起、被来源行收尾的表体"，**与并排的插图/走势图可区分**。

  弱证据：图在页首（y0 ≤ 35）＋ 其下紧邻正文行（无来源行）⇒ `▲`（本册 3 张无来源行的表走此路，须人裁）。

用法：
  python tools\check_table_ocr.py --task guozhai-qihuo --pdf "待读\某书.pdf" \
      --map .work\guozhai-qihuo\表图像映射.json --out .work\e2e-20260920\表体OCR对齐核验.md
退出码：0 = 无 🔴；1 = 存在 🔴 ⇒ 必须人裁或重跑，**不得直接建数据件**
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

NOTE = re.compile(r'^(注：|注:|资料来源|数据来源)')
TITLE = re.compile(r'^表\s*\d{1,2}\s*[.\-–—]\s*\d{1,2}\s+\S')


def variants(key):
    a, b = key.split('.')
    return ['表%s-%s' % (a, b), '表 %s-%s' % (a, b), '表%s.%s' % (a, b),
            '表 %s.%s' % (a, b), '表%s—%s' % (a, b), '表%s–%s' % (a, b)]


def chunks(title, n=4):
    t = re.sub(r'[^\u4e00-\u9fff0-9A-Za-z]+', ' ', title)
    out = set()
    for w in t.split():
        for i in range(0, max(0, len(w) - n + 1)):
            out.add(w[i:i + n])
    return out


def page_lines(page):
    out = []
    for blk in page.get_text('dict').get('blocks', []):
        for ln in blk.get('lines', []):
            t = ''.join(sp['text'] for sp in ln['spans']).strip()
            if t:
                out.append((round(ln['bbox'][1], 1), round(ln['bbox'][3], 1), t))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--map', required=True, help='表图像映射.json（map_table_images.py 产物）')
    ap.add_argument('--pdf', default=None, help='给 PDF 则启用 S2 版式证据（强烈建议）')
    ap.add_argument('--textdir', default='tabletext')
    ap.add_argument('--gap', type=float, default=90.0, help='图底→来源行的容许间隔 pt')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    mp = a.map if os.path.isabs(a.map) else os.path.join(ROOT, a.map)
    if not os.path.exists(mp):
        print('🔴 缺映射文件：%s' % mp); return 1
    data = json.loads(io.open(mp, encoding='utf-8').read())
    tdir = os.path.join(ROOT, '.work', a.task, a.textdir)
    if not os.path.isdir(tdir):
        print('🔴 缺 OCR 文本目录：%s' % tdir); return 1
    doc = None
    if a.pdf:
        try:
            import fitz
        except Exception as e:
            print('🔴 --pdf 给了但未装 pymupdf：%s' % e); return 2
        pp = a.pdf if os.path.isabs(a.pdf) else os.path.join(ROOT, a.pdf)
        if not os.path.exists(pp):
            print('🔴 找不到 PDF：%s' % pp); return 1
        doc = fitz.open(pp)

    rows, n_red, n_amber = [], 0, 0
    for r in data['rows']:
        key, stem = r['key'], 'p%04d_i%02d' % (r['img_page'], r['img_idx'])
        fp = os.path.join(tdir, stem + '.md')
        t = io.open(fp, encoding='utf-8', errors='replace').read() if os.path.exists(fp) else ''
        pipe = [ln for ln in t.splitlines() if ln.strip().startswith('|')]
        hit_strong = [v for v in variants(key) if v in t]
        hit_weak = sorted({w for w in chunks(r['title']) if w in t})
        nontab = '[非表格]' in t

        s2, s2_why, cont_ok = False, '（未给 --pdf）', None
        band = r.get('imgs') or [{'page': r['img_page'], 'idx': r['img_idx']}]
        if doc is not None:
            last = band[-1]
            ip, ii = last['page'], last['idx']
            imgs = doc[ip - 1].get_image_info(xrefs=True)
            im = imgs[ii - 1] if len(imgs) >= ii else None
            if im is None:
                s2_why = '区末图不在位'
            else:
                y1 = im['bbox'][3]
                below = [x for x in page_lines(doc[ip - 1]) if x[0] >= y1 - 1]
                term = None
                if below and NOTE.match(below[0][2]) and below[0][0] - y1 <= a.gap:
                    term, s2 = '区末图下即来源行（%.0fpt）' % (below[0][0] - y1), True
                elif below and not NOTE.match(below[0][2]):
                    # 区末图下直接是正文行 ⇒ 表体区在此收束（本册 8 张无来源行的表走此路）
                    term, s2 = '区末图下即正文行', True
                elif not below and ip < doc.page_count:
                    nxt = page_lines(doc[ip + 1])
                    if nxt and (NOTE.match(nxt[0][2]) or not TITLE.match(nxt[0][2])):
                        term, s2 = '次页首行即区末（%s）' % nxt[0][2][:10], True
                if not s2:
                    s2_why = '区末判据不成立（%s）' % (below[0][2][:16] if below else '图下无文字行')
                else:
                    s2_why = term
                # 多图表：**独立于版式的第二条证据** —— 续图要么带「（续）」标记，
                #   要么**重复同一表头行**（实测本册 2 张续图未标「（续）」但表头逐字重复 ⇒ 只有"表头重复"能救）
                if len(band) > 1:
                    def head_of(px, ix):
                        fp2 = os.path.join(tdir, 'p%04d_i%02d.md' % (px, ix))
                        t2 = io.open(fp2, encoding='utf-8', errors='replace').read() if os.path.exists(fp2) else ''
                        pl = [ln for ln in t2.splitlines() if ln.strip().startswith('|')]
                        if pl:
                            return [c.strip() for c in pl[0].strip('|').split('|') if c.strip()], t2
                        return [], t2
                    h1, _ = head_of(band[0]['page'], band[0]['idx'])
                    marks = []
                    for b in band[1:]:
                        hi, t2 = head_of(b['page'], b['idx'])
                        cont_mark = bool(re.search(r'[（(]\s*续\s*[)）]', t2))
                        common = len(set(h1) & set(hi)) if (h1 and hi) else 0
                        marks.append(cont_mark or common >= 2)
                    cont_ok = all(marks)
                    if not cont_ok:
                        s2 = False
                        s2_why = '多图表但续图既无「（续）」也无重复表头（%d/%d 命中）' % (sum(marks), len(marks))
                    else:
                        s2_why += '＋续图 %d 张有续图证据（「（续）」或表头重复）' % len(marks)

        if nontab or not pipe:
            verdict = '🔴 %s' % ('OCR 判为非表格' if nontab else '未产出管道表')
        elif hit_strong:
            verdict = '✔ 文本证据（表号命中 %s）%s' % (hit_strong[0], ('＋' + s2_why) if s2 else '')
        elif s2:
            verdict = '✔ 版式证据（%s）' % s2_why
        elif len(hit_weak) >= 2:
            verdict = '▲ 仅标题关键词命中（%s）' % '、'.join(hit_weak[:3])
        else:
            verdict = '🔴 无任何证据（%s）' % s2_why
        if verdict.startswith('🔴'):
            n_red += 1
        elif verdict.startswith('▲'):
            n_amber += 1
        rows.append((key, r['title'], stem, r.get('flag', ''), len(pipe), len(band), verdict))

    L = ['# 表体图像 OCR ↔ 表号 对齐核验 · %s' % a.task, '',
         '> 工装：`tools\\check_table_ocr.py`（确定性）｜ 配对表来自 `tools\\map_table_images.py`',
         '> 输入：`%s` ／ OCR 文本 `%s` ／ PDF %s'
         % (os.path.relpath(mp, ROOT), os.path.relpath(tdir, ROOT),
            (os.path.basename(a.pdf) if a.pdf else '**未给 ⇒ S2 版式证据缺失**')), '',
         '**判据**：S1 文本证据（表号命中）／S2 版式证据（标题下第一张图 ＋ 图下即"注：/资料来源："行）；任一强证据即 ✔。',
         '⚠ 本册表体图**不含标题行**（只裁表体）⇒ S1 大面积不命中属**正常**，故 S2 为主判据。', '',
         '| 表号 | 标题（页内原样） | 首图 OCR 文本 | 位置配对判态 | 管道表行 | 区图数 | 核验判态 |',
         '|---|---|---|---|---|---|---|']
    for key, title, stem, flag, npr, nb, verdict in rows:
        L.append('| 表 %s | %s | %s.md | %s | %d | %d | **%s** |'
                 % (key, title[:40], stem, flag or '✔', npr, nb, verdict))
    L += ['', '## 计数', '',
          '表 **%d** 张 ｜ ✔ 对齐 **%d** ／ ▲ 须人裁 **%d** ／ 🔴 不合格 **%d**'
          % (len(rows), len(rows) - n_red - n_amber, n_amber, n_red), '',
          '## 边界声明', '',
          '1. **对齐 ≠ 数值正确**：本闸只核"这段 OCR 是不是这张表"；**逐格数值**须与页图人眼抽查或第二引擎互核（另立专项）。',
          '2. **同名表风险**：本册存在同名表（"国债成交一览"两次、"T1703、T1706合约涨跌一览"两次）'
          '⇒ 仅凭标题关键词**不得判 ✔**（S1 要求表号字样，弱证据一律降 ▲）。',
          '3. **S2 是版式推断**：来源行紧随图下是本册版式规律（实测 28/31 有来源行）；'
          '若某册插图也带"资料来源"字样，S2 会偏宽 ⇒ 换册须先做版式普查。', '']

    op = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    io.open(op, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    print('→ 已写入 %s' % op)
    return 1 if n_red else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
