# -*- coding: utf-8 -*-
r"""ocr_deepseek_vision.py —— 用 `deepseek-flash`（DeepSeek-V4.1-Flash，原生视觉）做 OCR／**表体图像转管道表**

为什么值得试（用户 2026-09-17 提出）：
  ① **同一把刀可同时干两件事**：OCR 段与蒸馏段都走 **DSH→DeepSeek 一条账**，
     `tools\cost_meter.py` 直接计量 ⇒ **OCR 成本可自测**（硅基那条账 API 不报钱，只能靠人肉核对控制台余额）；
  ② 官方视觉计费口径：**图片按普通输入 token 计费、每图封顶 1024 token、不加价**
     （来源：官方定价页 ＋ vision 指南）；
  ③ 若质量与 PaddleOCR-VL 相当 ⇒ 可省掉"LOC 残留清洗"这一整道工序。

两种模式（**同一工具**，因为都是"图 → 文字"且共用一条账）：
  · `--pages`：**整页**扫描件 OCR（页图须已渲染，见 `tools\render_pdf_pages.py`）；
  · `--images` ＋ `--kind table`：**裁出的表格图像** → **markdown 管道表**（2026-09-21 新增）。
    用途：某册文字版 PDF 里**表体是截图图像**（实测 31 张表全如此、文字层只剩标题／注／资料来源行）
    ⇒ 表体只能回到像素补；先跑 `tools\map_table_images.py` 做**表号↔图像**配对，再只 OCR 那 31 张，
    避免把全册 215 个图像对象（多为插图/软件截图）全烧一遍。

用法：
  # 整页模式（页图须先渲染）
  python tools\render_pdf_pages.py --pdf "待读\某书.pdf" --task <slug> --pages 1-40 --dpi 150
  python tools\ocr_deepseek_vision.py --task <slug> --book 书名 --pages 1,3,10 --dump --workers 4
  # 表格图像模式（表号↔图像配对由 map_table_images.py 给出）
  python tools\ocr_deepseek_vision.py --task <slug> --book 书名 \
      --images "tableimgs\p0014_i01.jpeg,tableimgs\p0015_i01.jpeg" --kind table --dump

产物：
  · 整页：`.work\<task>\deepseek_text\pNNNN.txt`（`--dump`）＋ 计量 log `.work\<task>\ocr_deepseek_<tag>.jsonl`
  · 表格图：`.work\<task>\tabletext\<图像名>.md`（`--dump`）＋ 同一 log
  记录字段 `has_pipe` / `pipe_rows` / `is_image_only` ⇒ **"表体是否重建出来"可机核**（不靠人眼）。

退出码：0 = 跑通；1 = 无输入可跑；2 = 环境缺件（无凭据／任务目录不在）
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
from _creds import get_key  # noqa: E402       # 凭据解析唯一来源（异机：环境变量优先）

MODEL = 'deepseek-flash'          # 官方名；V4.1-Flash；旧名 deepseek-v4-flash 亦路由到它
ENDPOINT = 'https://api.deepseek.com/v1/chat/completions'

PAGE_PROMPT = (
    '这是中文书《{book}》第 {page} 页的扫描件。请**逐字转写图上真实可见的文字**：'
    '1) 标题（章/节/小节）原样保留；2) 正文全部照抄，不翻译不总结不改写；'
    '3) 表格按行列出，保留表头与全部数据，数字务必精确；'
    '4) 图注原样；页眉页脚与页码跳过；5) 看不清的字写【?】；'
    '6) 若本页只有插图/照片/二维码/印章而无正文，只写"[本页为图像页，无正文文字]"；'
    '7) 不要输出任何坐标或位置标记。'
)

TABLE_PROMPT = (
    '这是从中文书《{book}》里裁出的一张图（文件 {name}）。请只做一件事：判断它是不是表格，并尽力转写。\n'
    '1) 若图中是**表格**：输出一个 markdown 管道表（`| 表头 | … |`），**逐格照抄**，'
    '数字与千分位空格、单位、百分号一律原样，不四舍五入、不补算、不合计；'
    '表标题行（形如“表1-1 …”或图上第一行标题）原样放在管道表**上一行**；'
    '表下方的“注：…”“资料来源：…”行原样放在管道表**下一行**；\n'
    '2) 若图中**不是表格**（插图／照片／软件截图／公式／示意图）：第一行只输出 `[非表格]`，'
    '第二行给出图上最显眼的标题文字（≤40 字），**不要**编造表格；\n'
    '3) 看不清的字符写 `【?】`；**不要**输出坐标、不要解释、不要总结、不要加任何前后缀。'
)


def read_key():
    """DeepSeek 密钥：**先环境变量 DEEPSEEK_API_KEY**，再按可移植规则找 `.credentials.yaml`
    （`$DSH_CREDENTIALS` → `$DSH_HOME/` → 工作区根 → `~/`）。缺则打印三种给法并退出。"""
    return get_key('DEEPSEEK_API_KEY')


def parse_pages(spec):
    out = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            s, e = part.split('-')
            out += list(range(int(s), int(e) + 1))
        elif part:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True, help='任务 slug（决定 .work\\<slug>\\）')
    ap.add_argument('--book', default='', help='书名（写进提示词；留空则用 slug 顶替）')
    ap.add_argument('--pages', default='', help='整页模式：页号，如 1,3 或 1-40')
    ap.add_argument('--images', default='', help='表格图模式：图像路径（逗号分隔，相对 .work\\<task>\\ 或绝对）')
    ap.add_argument('--kind', choices=['page', 'table'], default='page',
                    help='page=整页转写（默认）；table=表格图 → 管道表')
    ap.add_argument('--tag', default=None, help='log 标签（默认：page→dsvision，table→dstbl）')
    ap.add_argument('--dump', action='store_true')
    ap.add_argument('--max-tokens', type=int, default=4000)
    ap.add_argument('--workers', type=int, default=1,
                    help='并发（引擎限流上限高，可放心用 6；默认 1 便于对照测试）')
    ap.add_argument('--resume', action='store_true',
                    help='断点续跑：跳过 logs 里已成功的项（避免重复计费）')
    a = ap.parse_args()

    task_dir = os.path.join(ROOT, '.work', a.task)
    if not os.path.isdir(task_dir):
        print('🔴 缺任务目录：%s（先 init_workspace 或建目录）' % task_dir)
        return 2
    book = a.book or a.task
    tag = a.tag or ('dstbl' if a.kind == 'table' else 'dsvision')
    if not a.pages and not a.images:
        print('🔴 未给 --pages 也未给 --images：没有输入可跑（这不是失败，是没活干）')
        return 1

    key = read_key()
    # ---- 输入清单：(唯一键, 图像绝对路径, 提示词, 输出路径) ----
    items = []
    if a.kind == 'table':
        for spec in [s.strip() for s in a.images.split(',') if s.strip()]:
            ip = spec if os.path.isabs(spec) else os.path.join(task_dir, spec)
            if not os.path.exists(ip):
                print('  ⚠ 缺图，跳过：%s' % ip)
                continue
            stem = os.path.splitext(os.path.basename(ip))[0]
            items.append((stem, ip, TABLE_PROMPT.format(book=book, name=os.path.basename(ip)),
                          os.path.join(task_dir, 'tabletext', stem + '.md')))
        outdir = os.path.join(task_dir, 'tabletext')
    else:
        for p in parse_pages(a.pages):
            ip = os.path.join(task_dir, 'pages', 'p%04d.png' % p)
            if not os.path.exists(ip):
                print('  ⚠ 页图不存在（先跑 render_pdf_pages.py）：%s' % ip)
                continue
            items.append((str(p), ip, PAGE_PROMPT.format(book=book, page=p),
                          os.path.join(task_dir, 'deepseek_text', 'p%04d.txt' % p)))
        outdir = os.path.join(task_dir, 'deepseek_text')

    log = os.path.join(task_dir, 'ocr_deepseek_%s.jsonl' % tag)
    done = set()
    if a.resume and os.path.exists(log):
        for ln in io.open(log, encoding='utf-8', errors='ignore'):
            try:
                r = json.loads(ln)
                if r.get('ok'):
                    done.add(str(r['key']))       # 只信"成功"记录 ⇒ 失败项会自动重试
            except Exception:
                pass
    todo = [it for it in items if it[0] not in done]
    print('模式=%s  items=%d  already-ok=%d  todo=%d  workers=%d%s'
          % (a.kind, len(items), len(done), len(todo), a.workers,
             '（断点续跑：已完成项不再调用 ⇒ 不重复计费）' if done else ''))
    if not todo:
        print('没有待做项（全部已完成）。')
    if a.dump:
        os.makedirs(outdir, exist_ok=True)
    fout = io.open(log, 'a', encoding='utf-8', newline='\n')
    import threading
    lock = threading.Lock()
    rows = []

    def work(it):
        name, img, prompt, dst = it
        b64 = base64.b64encode(open(img, 'rb').read()).decode()
        _ext = os.path.splitext(img)[1].lower().lstrip('.')
        _mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp',
                 'gif': 'image/gif'}.get(_ext, 'image/png')   # 图片 MIME 必须与真实格式一致
        body = {'model': MODEL, 'max_tokens': a.max_tokens, 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': prompt},
            {'type': 'image_url', 'image_url': {'url': 'data:%s;base64,' % _mime + b64}}]}]}
        t0 = time.time()
        txt, usage, err, finish = None, {}, None, None
        for _attempt in range(3):
            try:
                req = urllib.request.Request(
                    ENDPOINT, data=json.dumps(body).encode(),
                    headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
                with urllib.request.urlopen(req, timeout=600) as resp:
                    data = json.loads(resp.read().decode())
                _ch = data['choices'][0]
                txt = _ch['message']['content']
                usage = data.get('usage', {}) or {}
                finish = _ch.get('finish_reason')
                # ⚠ 2026-09-21 实测坑：图**很大/多列**时，模型可能把额度烧在**思考**上，
                #   `finish_reason='length'` 且 `content=''`（`completion_tokens` 恰好等于 max_tokens）。
                #   ⇒ 只判 `txt is not None` 会把"空输出"记成成功。故：空串一律当失败重试/报错。
                if txt is not None and not txt.strip():
                    err = 'EMPTY content (finish_reason=%s, completion_tokens=%s) ⇒ 提高 --max-tokens 重跑'
                    err = err % (finish, usage.get('completion_tokens'))
                    txt = None
                    time.sleep(3)
                    continue
                break
            except Exception as e:
                err = str(e)[:200]
                if getattr(e, 'read', None):
                    try:
                        err = e.read().decode()[:300]
                    except Exception:
                        pass
                time.sleep(3)
        dt = time.time() - t0
        rec = {'key': name, 'ok': txt is not None, 'model': MODEL, 'kind': a.kind,
               'img': os.path.relpath(img, ROOT), 'finish_reason': finish,
               'prompt_tokens': usage.get('prompt_tokens', 0),
               'completion_tokens': usage.get('completion_tokens', 0),
               'cached_tokens': (usage.get('prompt_cache_hit_tokens')
                                 or usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)),
               'seconds': round(dt, 2), 'err': err}
        if txt is not None:
            pipe = [ln for ln in txt.splitlines() if ln.strip().startswith('|')]
            rec.update({'chars': len(txt),
                        'has_pipe': bool(pipe), 'pipe_rows': len(pipe),
                        'is_image_only': ('[非表格]' in txt or '[本页为图像页' in txt),
                        'loc_tokens': len(re.findall(r'<\|LOC_\d+\|>', txt)),
                        'has_weird': len(set(re.findall(r'[\u0400-\u04FF\u3040-\u30FF\u0600-\u06FF]', txt)))})
            if a.dump:
                io.open(dst, 'w', encoding='utf-8', newline='\n').write(txt)
        with lock:
            rows.append(rec)
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
            fout.flush()
            if len(rows) % 10 == 0 or not rec['ok']:
                print('  进度 %d/%d  last %s ct=%s %.1fs %s'
                      % (len(rows), len(todo), name, rec['completion_tokens'], dt, (err or '')[:50]),
                      flush=True)

    if todo:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            list(ex.map(work, todo))
    fout.close()
    if rows:
        pt = sum(r['prompt_tokens'] for r in rows)
        ct = sum(r['completion_tokens'] for r in rows)
        ok = sum(1 for r in rows if r['ok'])
        print('-' * 74)
        print('本次成功=%d/%d  prompt_tokens=%d (mean %.1f)  completion_tokens=%d (mean %.1f)'
              % (ok, len(rows), pt, pt / len(rows), ct, ct / len(rows)))
        if a.kind == 'table':
            hp = sum(1 for r in rows if r.get('has_pipe'))
            io_ = sum(1 for r in rows if r.get('is_image_only'))
            print('表体重建：has_pipe **%d/%d**  ｜ 判为[非表格] %d 个 ⇒ 这些是**配对错**或**非表图**，须人工裁'
                  % (hp, len(rows), io_))
        print('注意：`prompt_tokens` 已含图片（官方口径：每图封顶 1024 token，按普通输入计价）')
        print('log: %s' % log)
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
