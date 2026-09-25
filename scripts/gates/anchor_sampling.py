# -*- coding: utf-8 -*-
r"""anchor_sampling.py —— 判官办法7：统计抽样验收（替代不可达的"零缺陷"）。
  判据：随机抽 n 条池内条目 → 机器白名单判定 + 输出待人工复核清单；验收＝不合格率 ≤ 5%
  （阈值属验收标准，2026-09-25 由蒸馏线按最低风险自定，可改）＋连续 3 批新册 0 不合格。"""
import argparse
import io
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool_writer as W
import check_pool_coverage as G   # ROOT 单源（禁作者路径字面量）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--seed', type=int, default=20260925)
    a = ap.parse_args()
    td = os.path.join(G.ROOT, '.work', a.task)
    vp = os.path.join(td, 'verified.md')
    quotes = [q for _a, _l, q in __import__('check_pool_coverage').parse_pool(vp) if q]
    random.seed(a.seed)
    pick = random.sample(quotes, min(a.n, len(quotes)))
    bad = [(q, '/'.join(w)) for q, w in ((q, W.anchor_ok(q)[1]) for q in pick) if w]
    rate = (len(bad) / len(pick) * 100) if pick else 0.0
    print('%s：抽 %d 条（池内 %d）｜不合格 %d｜不合格率 %.1f%%｜验收线 ≤5%% ⇒ %s'
          % (a.task, len(pick), len(quotes), len(bad), rate, 'PASS' if rate <= 5 else 'FAIL'))
    for q, w in bad[:5]:
        print('   · %s ｜%s' % (w, q[:50]))
    return 0 if rate <= 5 else 1


if __name__ == '__main__':
    sys.exit(main())
