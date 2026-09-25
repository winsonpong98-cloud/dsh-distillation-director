# -*- coding: utf-8 -*-
r"""log_qa_ledger.py —— **问答台账**：把历次回答登记成可检索的"第二大脑"底座（¥0 · 确定性）

为什么要它（用户第 ⑧ 条"结果能导出、能积累、能变成我的第二大脑"）：
  本工作区已积累大量**带出处、经判官裁定**的回答（散落在各批次目录里），但**没有任何索引**：
  想问"我以前哪次讲过 X"，只能靠记忆翻目录。⇒ 本工具把"**问—答**"登记成台账，并支持**按内容检索**。

设计（两条职责分开，避免过度设计）：
  · **台账（登记）**：每条记 `id／来源批次／路径／sha256／字节／汉字／池内 id 数／s 页锚数／路由声明／首行／摘要`；
    **按 sha256 去重**（幂等：重复入库不新增）；存 `JSONL`（机读）＋ `Markdown`（人读）两份。
  · **检索**：`--search <关键词>` **在已登记的路径上做确定性 grep**（给文件＋行号＋片段）——
    比在台账字段里搜更准：**答案是全文，索引字段只是元数据**。

用法：
  python tools\log_qa_ledger.py --ledger <台账.jsonl> --index <索引.md> --from-dir <答案目录> [--source 批次名]
  python tools\log_qa_ledger.py --ledger <台账.jsonl> --index <索引.md> --search "关键词" [--max 20]
退出码：0 = 跑通；1 = 参数不足／路径不存在
"""
import argparse
import glob
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

META = re.compile(r'路由[：:]\s*(.*?)\s*[｜|]\s*已读文件[：:]', re.S)


def analyze(path):
    t = io.open(path, encoding='utf-8', errors='replace').read()
    st = os.stat(path)
    h = hashlib.sha256(t.encode('utf-8', 'replace')).hexdigest()[:16]
    lines = t.splitlines()
    head = lines[0] if lines else ''
    body = '\n'.join(lines[1:]) if head.strip().startswith('<!--') else t
    m = META.search(head)
    route = (m.group(1).strip() if m else '')
    return {
        'id': os.path.splitext(os.path.basename(path))[0],
        'path': path,
        'sha256_16': h,
        'bytes': st.st_size,
        'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
        'hanzi': len(re.findall(r'[\u4e00-\u9fff]', body)),
        'anchor_id': len(re.findall(r'[A-G]-\d{2,3}', body)),
        'anchor_page': len(re.findall(r's\d{2,3}', body)),
        'route': route,
        'digest': re.sub(r'\s+', ' ', body[:200]).strip(),
    }


def load(ledger):
    recs = []
    if os.path.exists(ledger):
        for ln in io.open(ledger, encoding='utf-8'):
            ln = ln.strip()
            if ln:
                try:
                    recs.append(json.loads(ln))
                except Exception:
                    pass
    return recs


def save(ledger, index, recs):
    os.makedirs(os.path.dirname(os.path.abspath(ledger)), exist_ok=True)
    with io.open(ledger, 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    L = ['# 问答台账（第二大脑底座）', '',
         '> 生成：`tools\\log_qa_ledger.py`（幂等·按 sha256 去重）｜ 条数：**%d** ｜ 更新：%s' % (
             len(recs), datetime.now().strftime('%Y-%m-%d %H:%M')),
         '> 用途：①**积累**（每次问答留痕）②**检索**（`--search` 在已登记路径上 grep）③**审计**（锚密度／摘要可核）', '',
         '| id | 批次 | 汉字 | 池内id | s页锚 | 路由（主） | 路径 |', '|---|---|---|---|---|---|---|']
    for r in sorted(recs, key=lambda x: (x.get('source', ''), x.get('id', ''))):
        L.append('| `%s` | %s | %d | %d | %d | %s | `%s` |' % (
            r['id'], r.get('source', '—'), r['hanzi'], r['anchor_id'], r['anchor_page'],
            (r['route'].split(',')[0].strip() if r.get('route') else '—'), r['path']))
    io.open(index, 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--index', required=True)
    ap.add_argument('--from-dir', default=None, dest='frm')
    ap.add_argument('--source', default=None)
    ap.add_argument('--search', default=None)
    ap.add_argument('--max', type=int, default=20)
    a = ap.parse_args()

    if a.search:
        recs = load(a.ledger)
        if not recs:
            print('🔴 台账为空：%s' % a.ledger); return 1
        kw = a.search
        hits = 0
        print('检索「%s」于 %d 条已登记回答：' % (kw, len(recs)))
        for r in recs:
            p = r['path']
            if not os.path.exists(p):
                continue
            for i, ln in enumerate(io.open(p, encoding='utf-8', errors='replace'), 1):
                if kw in ln:
                    hits += 1
                    print('  %-12s L%-4d %s' % (r['id'], i, ln.strip()[:140]))
                    break
            if hits >= a.max:
                print('  …（达到 --max=%d 上限）' % a.max)
                break
        print('\n命中 %d 条回答 ｜ 台账：%s' % (hits, a.ledger))
        return 0

    if not a.frm:
        print('🔴 需给 --from-dir 或 --search'); return 1
    if not os.path.isdir(a.frm):
        print('🔴 目录不存在：%s' % a.frm); return 1

    recs = load(a.ledger)
    seen = {r['sha256_16'] for r in recs}
    added = skipped = 0
    for p in sorted(glob.glob(os.path.join(a.frm, '*.md'))):
        r = analyze(p)
        if r['sha256_16'] in seen:
            skipped += 1
            continue
        r['source'] = a.source or os.path.basename(os.path.normpath(a.frm))
        recs.append(r)
        seen.add(r['sha256_16'])
        added += 1
    save(a.ledger, a.index, recs)
    print('入库 %d 条 ／ 跳过（已存在）%d 条 ／ 台账共 %d 条' % (added, skipped, len(recs)))
    print('台账：%s\n索引：%s' % (a.ledger, a.index))
    return 0


if __name__ == '__main__':
    sys.exit(main())
