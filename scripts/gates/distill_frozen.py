# -*- coding: utf-8 -*-
r"""distill_frozen.py —— **冻结／不用件的单一来源**（册与技能的"跳过名单"）

## 为什么有这一件（用户 2026-09-24 指令）
> 用户原话：「**有些冻结的，不用的书和技能，你就跳过，因为这些是当时决定的，重复技能，
> 所以你发现这些有注明的你就不要动了**」。

在此之前，这个"知道"只散落在两份文书里（`archived\README.md` 与《归档技能重复度精判报告-2026-09-12》），
**没有任何机器可读的单一来源** ⇒ 后果实测有两种：
  ① 我会把它们**反复当成"待办/缺口"**（例：`talabu-zhihui-mozhou` 的第 7 条被判成"真缺口，须用户定"）；
  ② 判官/补做会把工时花在**已经决定不再动的件**上。
本件把"注明的冻结件"变成**一处可读的数据**，供判官派发、台账、补做计划统一引用。

## 口径（不新造判据，只做归一）
- **冻结技能**：两份权威文书里写明「**保持归档、本次不动**」或判定为 **C（保持归档、不改名、宿主侧 0 处改动）** 的技能。
- **冻结册**：其**交付技能集合**（accept7 件里点到名的技能）**非空且全部 ⊆ 冻结技能** ⇒ 整册按"当时决定"跳过。
- **只跳过、不删除、不改动**任何产物；跳过的事实**照样登记**（不静默消失）。

## 用法
    python tools\distill_frozen.py                 # 打印冻结技能／冻结册（人读）
    python tools\distill_frozen.py --json          # 机器读
    python tools\distill_frozen.py --selftest      # 自证：正 3 ＋ 负 3
    from distill_frozen import frozen_skills, frozen_tasks, is_frozen_task   # 供其它工具 import
退出码：0＝解析成功；2＝无法执行（缺权威文书）
"""
import argparse
import glob
import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)                                   # 蒸馏工作区
PARENT = os.path.dirname(WS)                                 # workspaces
ARCH_README = os.path.join(PARENT, '金融投资', '.dsh', 'skills', 'archived', 'README.md')
DUP_REPORT = os.path.join(WS, '输出', '归档技能重复度精判报告-2026-09-12.md')
WORK = os.path.join(WS, '.work')

# 用户 2026-09-24 当面指令（最高优先级的"跳过"来源；逐条带依据，不许空口）
USER_SKIP_TASKS = {
    'talabu-zhihui-mozhou': '用户 2026-09-24：「冻结的、不用的、当时决定的重复技能 ⇒ 跳过、不要动」'
                            '；该册两件交付技能（`procrustean-bed-audit`／`modern-captivity-audit`）'
                            '正是精判报告的 **C 类（保持归档、不改名、宿主侧 0 处改动）**',
}

KEEP_ARCHIVED = re.compile(r'保持归档[、，]?本次不动')
BACKTICK = re.compile(r'`([a-z][a-z0-9-]{3,})`')
CROW = re.compile(r'^\|\s*\*\*C[^|]*\*\*\s*\|\s*`([a-z][a-z0-9-]{3,})`')


def _read(p):
    return io.open(p, encoding='utf-8', errors='replace').read()


def frozen_skills():
    """冻结技能 → 依据（人读字符串）。**两份文书都必须读到**，否则判"无法执行"。"""
    out = {}
    if not os.path.isfile(ARCH_README):
        raise IOError('缺权威文书：%s' % ARCH_README)
    t = _read(ARCH_README)
    for line in t.split('\n'):
        if KEEP_ARCHIVED.search(line):
            # ⚠ 自伤登记（2026-09-24 · 自证当场抓到）：首版对**整行**取反引号 ⇒ 把行尾括号里的
            #   「承接者」（如 `soros-reflexivity` 的判据"已由活动技能 `bubble-…` 承接"）也当成冻结件
            #   ⇒ 冻结名单多 1 件（5 件）。修法：**只取行首到第一个括号之前**的那一段（名单就在那里）。
            head = re.split(r'[（(]', line, 1)[0]
            for m in BACKTICK.finditer(head):
                out.setdefault(m.group(1), '`archived\\README.md`「保持归档、本次不动」')
    if not os.path.isfile(DUP_REPORT):
        raise IOError('缺权威文书：%s' % DUP_REPORT)
    for line in _read(DUP_REPORT).split('\n'):
        m = CROW.match(line)
        if m:
            out.setdefault(m.group(1), '《归档技能重复度精判报告-2026-09-12》判定 **C（保持归档、不改名、宿主侧 0 处改动）**')
    return out


def _skills_named_in(text):
    """从一段文字里取"像技能名"的反引号词（kebab-case，≥4 字符）。"""
    return sorted({m.group(1) for m in BACKTICK.finditer(text)})


def frozen_tasks():
    """冻结册 → 依据：册的交付技能集合非空且全部 ⊆ 冻结技能。"""
    fs = set(frozen_skills())
    out = {}
    for f in sorted(glob.glob(os.path.join(WORK, '*', 'accept7-*.md'))):
        slug = os.path.basename(os.path.dirname(f))
        if slug.startswith('_') or slug.startswith('e2e-'):
            continue
        txt = _read(f)
        # 只看件头（第一条分隔线之前）——那里写"交付技能 N 件"，不掺正文里的引用
        head = txt.split('\n---')[0]
        named = set(_skills_named_in(head))
        # 该册在役/交付的技能名集合：取"技能根里真实存在过的"那批（用 .work/<slug>/skills 或册目录）
        real = set()
        for d in (os.path.join(WORK, slug, 'skills'),
                  os.path.join(WORK, slug, 'judge-accept7')):
            if os.path.isdir(d):
                real |= {x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))}
        cand = (named & fs) | (real & fs)
        all_named = named | real
        if cand and all_named and cand == all_named:
            out[slug] = '全部交付技能都在冻结名单里：%s' % '／'.join('`%s`' % s for s in sorted(cand))
    for slug, why in USER_SKIP_TASKS.items():
        out[slug] = why
    return out


def is_frozen_task(slug):
    return slug in frozen_tasks()


def report():
    fs = frozen_skills()
    ft = frozen_tasks()
    print('冻结技能 **%d** 个（两份权威文书归一）：' % len(fs))
    for k, v in sorted(fs.items()):
        print('  - `%s`  ← %s' % (k, v))
    print('冻结册 **%d** 个（交付技能全在冻结名单 ⇒ 整册跳过、不改动）：' % len(ft))
    for k, v in sorted(ft.items()):
        print('  - `%s`  ← %s' % (k, v))
    print('口径：**只跳过、不删除、不改动**；跳过的事实照样登记（不静默消失）。')
    return fs, ft


def selftest():
    ok = True
    # 正 1：两份权威文书存在且能解析出 4 件 C 类
    try:
        fs = frozen_skills()
    except IOError as e:
        print('  🔴 正1 失败：%s' % e)
        return False
    got = sorted(fs)
    want = ['druckenmiller', 'modern-captivity-audit', 'procrustean-bed-audit', 'soros-reflexivity']
    pos1 = got == want
    print('  %s 正1 C 类 4 件解析：%s' % ('✔' if pos1 else '🔴', '／'.join(got)))
    ok &= pos1
    # 正 2：冻结判定必须**只吃** C 类，不吃 D 类（D 类是要合并且**最终改名/保留可加载**的）
    pos2 = ('order-transition-poise' not in fs) and ('klarman-deep-value' not in fs)
    print('  %s 正2 不把 D 类（21 件）误判成冻结' % ('✔' if pos2 else '🔴'))
    ok &= pos2
    # 正 3：用户点名的册必须在冻结册里
    ft = frozen_tasks()
    pos3 = 'talabu-zhihui-mozhou' in ft
    print('  %s 正3 用户点名的册在冻结册名单里（`talabu-zhihui-mozhou`）' % ('✔' if pos3 else '🔴'))
    ok &= pos3
    # 负 1：把权威文书路径改坏 ⇒ 必须抛（不得静默返回空集）
    global ARCH_README
    bak = ARCH_README
    ARCH_README = bak + '.not-exist'
    try:
        frozen_skills()
        neg1 = False
    except IOError:
        neg1 = True
    ARCH_README = bak
    print('  %s 负1 缺权威文书必须抛（不得静默空集）' % ('✔' if neg1 else '🔴'))
    ok &= neg1
    # 负 2：非冻结册不得被判成冻结
    neg2 = not is_frozen_task('guozhai-qihuo')
    print('  %s 负2 正常册（`guozhai-qihuo`）不被判冻结' % ('✔' if neg2 else '🔴'))
    ok &= neg2
    # 负 3：只冻结一部分技能的册，不得整册冻结
    neg3 = not is_frozen_task('talabu-heitian-e')
    print('  %s 负3 部分冻结的册不整册跳过（`talabu-heitian-e`）' % ('✔' if neg3 else '🔴'))
    ok &= neg3
    print('  结论：%s' % ('✔ 自证通过（正 3 ＋ 负 3）' if ok else '🔴 自证失败'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return 0 if selftest() else 1
    try:
        fs, ft = report()
    except IOError as e:
        print('🔴 本步骤无法执行：%s' % e)
        return 2
    if a.json:
        print(json.dumps(dict(frozen_skills=fs, frozen_tasks=ft), ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
