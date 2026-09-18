# -*- coding: utf-8 -*-
"""check_md_tables.py —— 检查给定 md 文件里每个表格块的行列数一致性（防止多次补丁后表格破损）。

口径修正（2026-09-12）：管道计数**只数未转义的 `|`**。
  原因：Markdown 表格里 `\\|` 是**正确的转义写法**（用于在单元格内显示竖线，如正则 `回本\\|恢复原`）；
  旧版用 `str.count('|')` 把 `\\|` 也算进去 → 把**渲染完全正常**的表格误报为破损（假阳性）。
"""
import io, re, sys
import os
import sys

# --- UTF-8 输出保护（甲-A5 严格版 · 2026-09-13 加入；坑 P-16）---
# 本块由 utf8_guard_patch.py 幂等插入，勿手删：GBK 控制台下打印 ✔ 会抛
# UnicodeEncodeError → 退出码非 0 的**假报警**（前面所有闸其实都过了）。
if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
# --- UTF-8 输出保护 结束 ---

PIPE = re.compile(r'(?<!\\)\|')

for path in sys.argv[1:]:
    lines = io.open(path, encoding='utf-8').read().splitlines()
    bad, tables = [], 0
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:\-|]+\|$', lines[i + 1].strip()):
            start = i
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append((i + 1, len(PIPE.findall(lines[i]))))
                i += 1
            tables += 1
            counts = {c for _, c in rows}
            if len(counts) > 1:
                bad.append((start + 1, rows))
        else:
            i += 1
    print('%s：表格 %d 个，管道数不一致的块 %d 个' % (path.split('\\')[-1], tables, len(bad)))
    for ln, rows in bad:
        print('  ✗ 起始行 %d：%s' % (ln, ', '.join('L%d=%d' % r for r in rows)))
