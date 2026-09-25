# -*- coding: utf-8 -*-
"""check_gate_ledger.py —— 缺陷台账（`输出\\*闸缺陷台账*.md`）的**结构自检闸**。

为什么单独有这一件（2026-09-23 实测教训）：
  这一册台账是"本工作区缺陷的**唯一索引**"，但它在一天之内被我自己坏过 **5 种**：
    ① 表头被插入脚本写坏（锚多义）；② `## 附：` 标题重复；③ 表体夹空行（7 处）＋夹整段说明（1 段）；
    ④ 1 行只有 5 格（`G-21`，缺「影响」格）；⑤ 计数句/汇总行与实际行数不符。
  其中 ③④ 之所以能**与闸并存一整轮**，是因为既有哨兵 `check_md_tables.py` 的口径是
  **"块内管道数一致"** —— 表被空行切成 N 段时，**每段各自一致** ⇒ 它报 0 不一致；
  而台账**当时根本不在 postflight ③ 的 `MD_WATCH` 列表里**（手写 11 条）。
  本件的射程＝那些**通用件看不见、但又必须成立**的不变量：连续性、编号、计数、汇总算术、标题唯一。

用法：
  python check_gate_ledger.py                 # 默认**发现式**：查 输出\\*闸缺陷台账*.md 全部（不写死日期文件名）
  python check_gate_ledger.py --ledger <md>   # 指定台账
  python check_gate_ledger.py --selftest      # 自证：正 2 ＋ 负 8（每一类破损必须被拦下；含"围栏内 `# 注释` 不得当标题"）
退出码：0 ＝ 全过（或无台账可查）；1 ＝ 有硬失败。

**本件不随包**（2026-09-23 决策）：它守的是**本工作区的台账**（异机没有这个文件）⇒
`postflight` 用**存在性守卫**调用它，缺件记「N/A（非随包件）」**不判红**；因此不必进 `PAIRS`／随包清单。
"""
import io
import os
import re
import sys
import glob
import shutil
import tempfile

# --- UTF-8 输出保护（甲-A5 严格版；坑 P-16）---
if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
# --- UTF-8 输出保护 结束 ---

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER_GLOB = os.path.join(ROOT, '输出', '*闸缺陷台账*.md')

PIPE = re.compile(r'(?<!\\)\|')
ROW = re.compile(r'^\|\s*\*\*(G-\d+)\*\*\s*\|')
COUNT = re.compile(r'\*\*闸缺陷\s*(\d+)\s*处（G-1…G-(\d+)）\*\*')
SUM_TOTAL = re.compile(r'共\s*\*\*(\d+)\*\*\s*条')
SUM_FIXED = re.compile(r'完全修好\s*(\d+)\*\*（([^）]*)）')
SUM_HALF = re.compile(r'半修\s*(\d+)\*\*（([^）]*)）')
SUM_PEND = re.compile(r'待修\s*(\d+)\*\*（([^）]*)）')
SUM_EDGE = re.compile(r'已知边界\s*(\d+)\*\*（([^）]*)）')


def cells(line):
    """转义感知切格（`\\|` 不算格界）。"""
    return line.replace('\\|', '\x01').split('|')[1:-1]


def ids_of(text):
    """取 id 列表：**不依赖分隔符**（`／`／`；`／`、`／空格都能吃）—— 首版按 `／` 切，
    于是「`G-1`；**不改**」被读成 0 条 ⇒ 汇总比对**假红**（2026-09-23 实测，本件自身的首版 bug）。"""
    return re.findall(r'G-\d+', re.sub(r'`', '', text)) if text is not None else []


def fence_mask(L):
    """被 ``` 围起来（代码围栏内）的行号集合（0-based）—— 围栏里的 `# 注释` 不是标题。"""
    inside, out = False, set()
    for i, x in enumerate(L):
        if x.lstrip().startswith('```'):
            inside = not inside
            out.add(i)
            continue
        if inside:
            out.add(i)
    return out


def derive_status(cell):
    c = cell
    if '**已修' in c and ('**已登记待修' in c or '半修' in c):
        return '半修'
    if '**已修' in c:
        return '已修'
    if '**已登记待修' in c:
        return '待修'
    if '已知边界' in c:
        return '边界'
    return '未标'


def check_text(c):
    """返回 (items, rows, detail)；items = [(名, 期望, 实测, ok)]"""
    items = []
    L = c.split('\n')
    FEN = fence_mask(L)

    h1 = [i for i, x in enumerate(L) if x.startswith('# ') and i not in FEN]
    items.append(('① 唯一 H1 标题', '1 个（代码围栏内不算）', '%d 个' % len(h1), len(h1) == 1))

    h2 = [x for i, x in enumerate(L) if x.startswith('## ') and i not in FEN]
    dup = sorted({x for x in h2 if h2.count(x) > 1})
    items.append(('② 无重复 H2 标题', '0 组重复（代码围栏内不算）',
                  ('%d 组：%s' % (len(dup), '｜'.join(x[:24] for x in dup[:3]))) if dup else '0 组',
                  not dup))

    hdr = [i for i, x in enumerate(L) if x.strip().startswith('|') and '| # |' in x and i not in FEN]
    sep_ok = bool(hdr) and re.match(r'^\|[\s:\-|]+\|$', L[hdr[0] + 1].strip()) is not None
    items.append(('③ 主表头 ＋ 分隔行', '各 1 个',
                  '表头 %d 个／分隔行 %s' % (len(hdr), '在' if sep_ok else '缺'), len(hdr) == 1 and sep_ok))

    rows = [(i + 1, ROW.match(x).group(1), x) for i, x in enumerate(L)
            if ROW.match(x) and i not in FEN]
    if not rows:
        items.append(('④ 表体连续（无空行／无夹段）', '连续', '无条目行 ⇒ 无法判', False))
        items.append(('⑤ 每行列数＝表头', '一致', '无条目行 ⇒ 无法判', False))
        return items, rows, {'note': '无 G- 条目行'}

    first, last = rows[0][0] - 1, rows[-1][0] - 1
    cuts = [i + 1 for i in range(first + 1, last)
            if L[i].strip() == '' or not L[i].strip().startswith('|')]
    items.append(('④ 表体连续（无空行／无夹段）', '0 处切断',
                  ('%d 处：L%s' % (len(cuts), '／L'.join(str(x) for x in cuts[:8]))) if cuts else '0 处',
                  not cuts))

    ncol = len(cells(L[hdr[0]])) if hdr else 6
    off = [(i, ROW.match(L[i]).group(1), len(cells(L[i]))) for i in range(first, last + 1)
           if ROW.match(L[i]) and len(cells(L[i])) != ncol]
    items.append(('⑤ 每行列数＝表头', '%d 格' % ncol,
                  ('%d 行不符：%s' % (len(off), '、'.join('%s=%d格' % (g, n) for _, g, n in off[:5])))
                  if off else '全部 %d 格' % ncol, not off))

    gids = [g for _, g, _ in rows]
    nums = [int(g.split('-')[1]) for g in gids]
    want = list(range(1, len(nums) + 1))
    dupid = sorted({g for g in gids if gids.count(g) > 1})
    items.append(('⑥ 编号唯一且连续 G-1…G-N', '1..%d 无重无缺（**不要求升序**）' % len(nums),
                  '重复 %d ／ 缺号 %d ／ 乱序 %s（仅信息）'
                  % (len(dupid), len(set(want) - set(nums)), '有' if nums != sorted(nums) else '无'),
                  not dupid and set(want) == set(nums)))

    mc = COUNT.search(c)
    items.append(('⑦ 计数句＝实际行数', '%d 处（G-1…G-%d）' % (len(nums), len(nums)),
                  mc.group(0).strip('*') if mc else '未找到计数句',
                  bool(mc) and int(mc.group(1)) == len(nums) and int(mc.group(2)) == len(nums)))

    st = {}
    for ln, g, x in rows:
        st[g] = derive_status(cells(x)[-1])
    unmarked = sorted(g for g, v in st.items() if v == '未标')
    fixed = [g for g in gids if st[g] == '已修']
    half = [g for g in gids if st[g] == '半修']
    pend = [g for g in gids if st[g] == '待修']
    edge = [g for g in gids if st[g] == '边界']
    items.append(('⑨ 状态词只有三种', '0 处未标', ('未标 %d 条：%s' % (len(unmarked), '／'.join(unmarked[:5])))
                  if unmarked else '0 处', not unmarked))

    mt = SUM_TOTAL.search(c)
    mf, mh, mp, me = SUM_FIXED.search(c), SUM_HALF.search(c), SUM_PEND.search(c), SUM_EDGE.search(c)
    if not (mt and mf and mh and mp and me):
        items.append(('⑧ 汇总行算术自校', '共 N ＝ 修好＋半修＋待修＋边界', '汇总行解析失败', False))
    else:
        got = [int(mt.group(1)), int(mf.group(1)), int(mh.group(1)), int(mp.group(1)), int(me.group(1))]
        exp = [len(gids), len(fixed), len(half), len(pend), len(edge)]
        arith = got[0] == sum(got[1:])
        lists_ok = (sorted(ids_of(mf.group(2))) == sorted(fixed) and sorted(ids_of(mh.group(2))) == sorted(half)
                    and sorted(ids_of(mp.group(2))) == sorted(pend) and sorted(ids_of(me.group(2))) == sorted(edge))
        items.append(('⑧ 汇总行算术自校', '共 %d ＝ %d＋%d＋%d＋%d 且 id 列表一致'
                      % (exp[0], exp[1], exp[2], exp[3], exp[4]),
                      '读作 共 %d ＝ %d＋%d＋%d＋%d ／ 算术%s ／ id 列表%s'
                      % (got[0], got[1], got[2], got[3], got[4],
                         '对' if arith else '**错**', '一致' if lists_ok else '**不一致**'),
                      got == exp and arith and lists_ok))

    out_blank = [i + 1 for i in range(len(L) - 1)
                 if L[i].strip() == '' and L[i + 1].strip() == '' and i not in FEN and (i + 1) not in FEN]
    items.append(('⑩ 无连续空行（≥2）', '0 处', ('%d 处：L%s' % (len(out_blank), '／L'.join(map(str, out_blank[:8]))))
                  if out_blank else '0 处', not out_blank))

    detail = {'n': len(gids), 'fixed': fixed, 'half': half, 'pend': pend, 'edge': edge}
    return items, rows, detail


def report(path, quiet=False):
    c = io.open(path, encoding='utf-8').read()
    items, rows, detail = check_text(c)
    if not quiet:
        print('台账自检：%s' % path)
        print('  条目 %d 条 ｜ 修好 %d ／ 半修 %d ／ 待修 %d ／ 边界 %d'
              % (detail.get('n', 0), len(detail.get('fixed', [])), len(detail.get('half', [])),
                 len(detail.get('pend', [])), len(detail.get('edge', []))))
        print('  %-28s %-30s %s' % ('检查项', '期望', '实测'))
        for name, exp, got, ok in items:
            print('  %s %-26s %-30s %s' % ('✔' if ok else '✗', name, exp, got))
        bad = [n for n, _, _, ok in items if not ok]
        print('  结论：%s' % ('✔ 台账结构自检全过（%d 项）' % len(items) if not bad
                            else '🔴 硬失败 %d 项：%s' % (len(bad), '、'.join(bad))))
    return all(ok for _, _, _, ok in items)


GOOD = '''# 闸缺陷台账（自证样本）
> 说明行。

| # | 闸 / 判据 | 位置 | 证据 | 影响 | 状态 |
|---|---|---|---|---|---|
| **G-1** | 甲 | a.py L1 | 实测 1 | 影响 1 | **已修（2026-09-23）**：修了 |
| **G-2** | 乙 | b.py L2 | 实测 2 | 影响 2 | **已登记待修**（路一条） |
| **G-3** | 丙 | c.py L3 | 实测 3 | 影响 3 | **已登记待修**；②**已修（2026-09-23）**：半件 |

## 附：比例
正文。

A-157 曾记「本会话同向：**闸缺陷 3 处（G-1…G-3）** vs 产物真缺陷 0 处」——这一句用于自证计数句比对。

**当前状态汇总（2026-09-23 · 派生 ＋ 自校）**：共 **3** 条 ＝ **完全修好 1**（G-1）＋ **半修 1**（G-3）＋ **待修 1**（G-2）＋ **已知边界 0**（`—`）。
'''


GOOD2 = GOOD + '''
## 独立验证方式

```powershell
# G-1：这是 PowerShell 注释，不是 H1 标题
python -c "print(1)"   # 期望 1
```
'''


def selftest():
    d = tempfile.mkdtemp(prefix='ledger_selftest_')
    pos = os.path.join(d, 'pos.md')
    io.open(pos, 'w', encoding='utf-8', newline='\n').write(GOOD)
    pos_ok = report(pos, quiet=True)
    pos2 = os.path.join(d, 'pos2.md')
    io.open(pos2, 'w', encoding='utf-8', newline='\n').write(GOOD2)
    pos2_ok = report(pos2, quiet=True)
    negs = []
    muts = [
        ('负1 重复 H1 标题', GOOD.replace('# 闸缺陷台账（自证样本）',
                                    '# 闸缺陷台账（自证样本）\n\n# 闸缺陷台账（自证样本）', 1)),
        ('负2 重复 H2 标题', GOOD.replace('## 附：比例', '## 附：比例\n\n## 附：比例', 1)),
        ('负3 表内空行', GOOD.replace('| **G-2** |', '\n| **G-2** |', 1)),
        ('负4 表内夹段落', GOOD.replace('| **G-2** |', '夹进来的段落。\n| **G-2** |', 1)),
        ('负5 某行少一格', GOOD.replace('| **G-2** | 乙 | b.py L2 | 实测 2 | 影响 2 |',
                                    '| **G-2** | 乙 | b.py L2 | 实测 2 |', 1)),
        ('负6 计数句与行数不符', GOOD.replace('（G-1…G-3）', '（G-1…G-4）', 1)),
        ('负7 汇总算术不符', GOOD.replace('共 **3** 条', '共 **4** 条', 1)),
        ('负8 状态词缺失', GOOD.replace('**已登记待修**（路一条）', '回头再说', 1)),
    ]
    for name, text in muts:
        p = os.path.join(d, name.split()[0] + '.md')
        io.open(p, 'w', encoding='utf-8', newline='\n').write(text)
        negs.append((name, report(p, quiet=True)))
    shutil.rmtree(d, ignore_errors=True)
    npass = (1 if pos_ok else 0) + (1 if pos2_ok else 0) + sum(1 for _, ok in negs if not ok)
    print('自证：正 2 ＋ 负 %d —— 全中 %d 项（共 %d）' % (len(negs), npass, 2 + len(negs)))
    print('  正样本1（未改）→ %s' % ('✔ rc=0（放行）' if pos_ok else '✗ 竟然拦住正样本'))
    print('  正样本2（代码围栏里含 `# 注释`）→ %s' % ('✔ rc=0（放行）' if pos2_ok else '✗ 把围栏里的注释当标题（假红）'))
    for name, ok in negs:
        print('  %s → %s' % (name, '✔ 被拦下' if not ok else '✗ **漏过**'))
    ok = pos_ok and pos2_ok and all(not x for _, x in negs)
    print('  结论：%s' % ('✔ 自证通过' if ok else '🔴 自证失败'))
    return ok


def main():
    a = sys.argv[1:]
    if '-h' in a or '--help' in a:
        print(__doc__)
        return 0
    if '--selftest' in a:
        return 0 if selftest() else 1
    if '--ledger' in a:
        targets = [a[a.index('--ledger') + 1]]
    else:
        # 默认＝**发现式**（`输出\*闸缺陷台账*.md` 全部）——不写死日期文件名：
        # 台账是按日期新建的，写死会"换了台账就守不到"（本件第一版就是写死的）。
        targets = sorted(glob.glob(LEDGER_GLOB))
    if not targets:
        print('  跳过（本机未发现台账：%s）' % LEDGER_GLOB)
        return 0
    ok = True
    for p in targets:
        if not os.path.isfile(p):
            print('  跳过（文件不存在）：%s' % p)
            continue
        ok = report(p) and ok
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
