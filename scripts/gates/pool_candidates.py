# -*- coding: utf-8 -*-
r"""pool_candidates.py —— 机选唯一出口（判官办法4）：按**整句边界**取句 → 白名单判据前置 → 只落 candidates/。
  用法：python tools/pool_candidates.py --task <slug> [--n 8]"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool_writer as W
import check_pool_coverage as G   # ROOT 单源（禁作者路径字面量）

HDRS = [re.compile(r'^=====\s*\[PAGE (\d+)\]\s*====='), re.compile(r'^\[(p\d+)\]\s*$'),
        re.compile(r'^#\s*s(\d+)\.md'), re.compile(r'^\[PAGE (\d+)\]')]


def run(task_dir, n=8):
    bt = os.path.join(task_dir, 'book_text.md')
    src = bt if os.path.isfile(bt) else os.path.join(task_dir, 'ocr_ds.txt')
    hdr = afmt = None
    for line in io.open(src, encoding='utf-8', errors='replace').read().split('\n')[:400]:
        for h in HDRS:
            if h.match(line.strip()):
                hdr, afmt = h, ((lambda m: 's%d' % int(m.group(1))) if 'PAGE' in h.pattern or '.md' in h.pattern else (lambda m: m.group(1)))
                break
        if hdr:
            break
    pool = io.open(os.path.join(task_dir, 'verified.md'), encoding='utf-8').read() if os.path.isfile(os.path.join(task_dir, 'verified.md')) else ''
    pooln = [re.sub(r'\s', '', x) for x in re.findall(r'原文：「([^」]*)」', pool)]
    cur, out, rej = None, [], 0
    for line in io.open(src, encoding='utf-8', errors='replace').read().split('\n'):
        m = hdr.match(line.strip()) if hdr else None
        if m:
            cur = afmt(m)
            continue
        if not cur or len(line) < 30:
            continue
        s0 = line.strip()
        if re.match(r'^(图|表|注[：:]|资料来源)', s0):
            continue
        for s in re.split(r'(?<=[。！？])', s0):   # 整句边界切分（办法4）
            s = s.strip()
            if not re.search(r'\d', s) or len(s) < 20:
                continue
            nz = re.sub(r'\s', '', s)
            if any(nz[:20] in q for q in pooln):
                continue
            ok, why = W.anchor_ok(s)
            if not ok:
                rej += 1
                continue
            out.append((cur, s))
            break
    out.sort(key=lambda x: (len(re.findall(r'\d+(?:\.\d+)?%?', x[1])), -len(x[1])), reverse=True)
    cd = os.path.join(task_dir, 'candidates')
    os.makedirs(cd, exist_ok=True)
    with io.open(os.path.join(cd, 'auto-picks.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('# auto-picks.md —— 机选候选（未过判据者不入池；经 pool_writer 才可入池）\n')
        for i, (a, s) in enumerate(out[:n], 1):
            f.write('- C-%03d 锚：%s\n  原文：「%s」\n  判据：白名单通过（分类待判）\n' % (i, a, s))
    print('%s：候选 %d 条（判据拒 %d）→ candidates/auto-picks.md' % (os.path.basename(task_dir), len(out[:n]), rej))
    return len(out[:n])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--n', type=int, default=8)
    a = ap.parse_args()
    run(os.path.join(G.ROOT, '.work', a.task), a.n)
