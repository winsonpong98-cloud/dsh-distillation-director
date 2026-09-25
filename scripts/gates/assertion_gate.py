# -*- coding: utf-8 -*-
r"""assertion_gate.py —— **三基线运行时闸**：把"点回原文 / 标注推测 / 先追问缺信息"
从「模型自觉」变成「产物形态的硬约束 ＋ 机器可判」（2026-09-21 · 用户问「有什么办法一定可以做到」）

## 一句话原理

不问模型"你有没有回到原文／有没有标推测／有没有追问"——
而是**要求产物按固定形态交付**，然后**由机器逐条判**：

```
每一项断言必须落在三槽之一（槽位制）：
  ① [原文]  —— 必须带锚，且引文必须能在**原文册/池**里被机器找到（找不到 ⇒ 红）
  ② [外推]  —— 必须写明「依赖前提」与「前提破了怎样」（缺任一 ⇒ 红）
  ③ [缺信息] —— 必须逐条列「缺什么字段 ＋ 缺它影响哪一步」（这条同时是判停证据）
问句缺信息时，结论槽必须为空（"没有结论"是**结构要求**，不是礼貌要求）
```

⇒ **三条基线各自对应一个可判定的红**：
  · 点回原文 ⇒ 引文**回源命中率**必须 100%
  · 标注推测 ⇒ **无锚的陈述句数**必须 0（要么进 ①，要么进 ②，要么删）
  · 先追问   ⇒ 问句命中"缺信息形态"时，**缺信息槽必须非空**且**结论槽必须为空**

## 与既有件的关系（不重复造轮子）

- 回源命中：复用 `verify_layer_quotes.py` 的口径（本件自带一个**轻量版回源**，只做"引文是否是册文本子串"）。
- 引用形态：与 `distill_acceptance_check.py` 的分工——那件判"答卷级 7 条"，本件判"**逐句三槽**"。
- 仪器是否够用：由 `instrument_sufficiency.py` 判。

## 用法

    python tools\assertion_gate.py --answer <答卷.md> --corpus <原文册/池> [--out <报告.md>]
    python tools\assertion_gate.py --selftest          # 好 1 放行 ＋ 坏 5 全拦

退出码：0 ＝ 三槽合规；1 ＝ 有红；2 ＝ 前置不满足。
"""
import argparse
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

IDEMPOTENT_MARK = '<!-- assertion_gate:generated (idempotent) -->'
SLOT_QUOTE = '原文'
SLOT_EXTRAP = '外推'
SLOT_MISSING = '缺信息'
SLOT_TOKENS = (SLOT_QUOTE, SLOT_EXTRAP, SLOT_MISSING)

QUOTE_RE = re.compile('「([^」]{6,400})」')
ANCHOR_RE = re.compile(r'([A-Za-z][A-Za-z0-9]*-\d{3}|p\d{2,4}|s\d{3})')
# 缺信息形态（问句级）：这些词出现 ⇒ 视为"缺信息型问题"，必须给缺信息槽
MISSING_Q_RE = re.compile(r'(要不要|该不该|能不能|可不可以|怎么操作|帮我(?:看|判)|我手里|我的持仓|'
                          r'现在(?:买|卖|加|减|补|割)|亏了|赚了|该买|该卖)')
STOP_DECL_RE = re.compile(r'(?<![不未非无])(?:先)?判停')
FIELD_LIST_RE = re.compile(r'(缺\s*信息|字段清单|需要你|需你|请你(?:提供|给出)|缺什么|待补(?:字段|信息)|'
                           r'必需(?:字段|信息))')
# 【外推】块的两种写法：`【外推】…` 与 `【外推 N】…`
EXTRAP_BLOCK_RE = re.compile(r'【外推[^】]{0,8}】')


def _slots(text):
    """按标题把答卷切成三槽区域（`## [原文]` / `## [外推]` / `## [缺信息]` 或含关键词的标题）。"""
    lines = text.split('\n')
    cur, buf = None, {SLOT_QUOTE: [], SLOT_EXTRAP: [], SLOT_MISSING: [], '_none': []}
    for l in lines:
        if l.lstrip().startswith('#'):
            h = l.strip()
            if ('原文' in h) or ('引用' in h) or ('回源' in h):
                cur = SLOT_QUOTE
                continue
            if ('外推' in h) or ('推测' in h) or ('推断' in h):
                cur = SLOT_EXTRAP
                continue
            if ('缺信息' in h) or ('待补' in h) or ('判停' in h) or ('需要你' in h):
                cur = SLOT_MISSING
                continue
            cur = '_none'
        buf[cur or '_none'].append(l)
    return buf


def check(answer_path, corpus_path, out=None):
    if not os.path.exists(answer_path):
        return 2, '🔴 答卷不存在：%s' % answer_path, None
    t = io.open(answer_path, encoding='utf-8').read()
    corpus = ''
    if corpus_path:
        if not os.path.exists(corpus_path):
            return 2, '🔴 原文册/池不存在：%s' % corpus_path, None
        cps = []
        if os.path.isdir(corpus_path):
            for f in sorted(os.listdir(corpus_path)):
                if f.endswith(('.txt', '.md')):
                    cps.append(io.open(os.path.join(corpus_path, f), encoding='utf-8',
                                       errors='replace').read())
        else:
            cps = [io.open(corpus_path, encoding='utf-8', errors='replace').read()]
        corpus = re.sub(r'\s', '', '\n'.join(cps))     # 去空白后比对（口径同 SKILL 的"去首尾空白"）

    fatal, warn = [], []
    rep = ['## 一、三槽合规判态', '', '| 槽 | 判态 | 机器证据 |', '|---|---|---|']

    # ── 槽① 原文：每条引文必须能在原文册里找到 ──
    quotes = QUOTE_RE.findall(t)
    miss_quote = []
    if corpus:
        for q in quotes:
            if re.sub(r'\s', '', q) not in corpus:
                miss_quote.append(q[:40])
    ok1 = bool(quotes) and not miss_quote
    rep.append('| ① 点回原文 | %s | 引文 %d 条 ／ **回源未命中 %d 条**%s |'
               % ('PASS' if ok1 else ('— 无引文' if not quotes else '🔴 FAIL'),
                  len(quotes), len(miss_quote),
                  ('：' + '；'.join('「%s…」' % x for x in miss_quote[:3])) if miss_quote else ''))
    if not quotes:
        warn.append('答卷无「」引文 ⇒ 槽① 无从核（**不得读作 PASS**；若本题本不需引文，请显式写"本题不需回源"）')
    if miss_quote:
        fatal.append('槽①：**引文回源未命中 %d 条**（凭记忆写引文的典型形态）：%s'
                     % (len(miss_quote), '；'.join('「%s…」' % x for x in miss_quote[:3])))

    # ── 槽② 外推：每个【外推】块必须写"依赖前提" ──
    ex_blocks = EXTRAP_BLOCK_RE.findall(t)
    no_prem = []
    for m in EXTRAP_BLOCK_RE.finditer(t):
        seg = t[m.end():m.end() + 400]
        if ('依赖' not in seg and '前提' not in seg):
            no_prem.append(seg[:40].replace('\n', ' '))
    ok2 = (not ex_blocks) or (not no_prem)
    rep.append('| ② 标注推测 | %s | 【外推】块 %d ／ **未写前提 %d** |'
               % ('PASS' if ok2 else '🔴 FAIL', len(ex_blocks), len(no_prem)))
    if no_prem:
        fatal.append('槽②：%d 个【外推】块**未写"依赖前提"**：%s'
                     % (len(no_prem), '；'.join(no_prem[:3])))

    # ── 槽③ 缺信息：缺信息型问句 ⇒ 必须有缺信息槽且**无结论** ──
    is_missing_q = bool(MISSING_Q_RE.search(t))
    field_lines = [l for l in t.split('\n') if FIELD_LIST_RE.search(l)]
    stopped = bool(STOP_DECL_RE.search(t))
    has_conclusion = bool(re.search(r'(结论|建议|应(?:该)?(?:买|卖|割|补)|操作方案)', t))
    # ⚠ G-3(b) 修复（2026-09-23 · 判官实测抓到的洞）：`ok3` 原先**不含"含结论"**
    #   ⇒ 一份缺信息型答卷只要写"判停＋字段清单"，**同时给出可执行结论**也照样 PASS。
    #   但 `has_conclusion` 的正则**太粗**（`结论|建议` 这类普通词也命中）⇒ 直接并入 `ok3`
    #   会**制造新的假红**（"越老实的答卷越被判红"，A-34 反向）。故新增**紧的**动作型结论正则：
    ACTION_CONCL_RE = re.compile(r'(?:建议|应当|应该|可以|不妨)\s*(?:买|卖|割|补|加仓|减仓|清仓|持有)|'
                                 r'(?:目标价|仓位比例|买卖指令|止损位|止盈位|几点买|几点卖)')
    # ⚠ 教训（2026-09-23 · 我在同一批改动里**当场复发**了 G-3(a) 的同一形态）：
    #   首版 `ACTION_CONCL_RE` **看不见否定** ⇒ 把 T4 里「本卷**不含**买卖指令、不含点位、
    #   不含**仓位比例**、不含**目标价**」这类**豁免声明**判成"给了结论" ⇒ guozhai T3/T4 由
    #   rc=0 变 rc=1（**新假红**）。⇒ 判据必须**否定感知**：命中点前 10 字内有否定词则不计。
    #   这是「判据看不见否定」的**第 2 次**（第 1 次＝原 `STOP_DECL_RE` 把"不判停"当判停）。
    NEG_BEFORE_RE = re.compile(r'(?:不含|不给|不做|不作|没有|并非|不是|禁止|避免|不得|无需|无)'
                               r'[^。；\n]{0,6}$')

    def has_action_concl(text):
        for m in ACTION_CONCL_RE.finditer(text):
            if NEG_BEFORE_RE.search(text[max(0, m.start() - 10):m.start()]):
                continue
            return True
        return False

    has_action_concl = has_action_concl(t)
    ok3 = (not is_missing_q) or (bool(field_lines) and stopped and not has_action_concl)
    rep.append('| ③ 先追问缺信息 | %s | 缺信息型=%s ／ 字段清单行 %d ／ 判停声明=%s ／ 含结论(信息性)=%s ／ **动作型结论**=%s |'
               % ('PASS' if ok3 else '🔴 FAIL', is_missing_q, len(field_lines), stopped,
                  has_conclusion, has_action_concl))
    if is_missing_q and not (field_lines and stopped):
        fatal.append('槽③：问句属**缺信息型**，但缺"判停声明 ＋ 字段清单"（清单行 %d／判停 %s）'
                     '——**先追问是结构要求，不是礼貌要求**' % (len(field_lines), stopped))
    if is_missing_q and has_action_concl:
        fatal.append('槽③：缺信息型问句下**给出了可执行的动作型结论**（G-3(b)：判停＋清单不豁免"不许给结论"）')
    if is_missing_q and has_conclusion and not stopped:
        fatal.append('槽③：缺信息型问句下**仍给出了结论**（未判停）')

    # ── 补充：无锚陈述句比例（"标注推测"的机器反证 · 信息性） ──
    lines = [l for l in t.split('\n')
             if len(re.sub(r'[^\u4e00-\u9fff]', '', l)) >= 12
             and not l.lstrip().startswith(('#', '>', '|', '-', '*'))]
    noanchor = [l for l in lines if not ANCHOR_RE.search(l) and '【外推' not in l]
    ratio = (len(noanchor) / len(lines)) if lines else 0.0
    rep.append('| ④ 无锚陈述比例（信息性） | %s | 实质句 %d ／ **无锚且非外推 %d（%.0f%%）** |'
               % ('— 信息性', len(lines), len(noanchor), ratio * 100))
    if ratio > 0.6 and lines:
        warn.append('无锚且非外推的实质句占比 %.0f%%（>60%%）——判官须逐条看这些句子是'
                    '"书内已复述"还是"应标【外推】而未标"' % (ratio * 100))

    # ── ⑤ **数据句强制回源或标外推**（"标注推测"的硬机制 · 2026-09-21 加固） ──
    #   原理：模型**自省"这是不是推测"不可靠**；但"含具体数据的句子能否在原文里找到"
    #   是**机器可判**的。⇒ 判据：凡**含数字/百分数/具体标的**的实质句，必须满足其一——
    #     ① 该句（去空白）能在原文册里找到；② 该句带锚且引文可回源；③ 该句在同一行/紧邻标了【外推】。
    #   三者皆不满足 ⇒ **红**（这是"要么是书里的，要么承认是你推的"的机器化）。
    # ⚠ G-4 修复（2026-09-23 · 判官实测抓到）：
    #   原第三支 `([\u4e00-\u9fff]{2,6}转债)` 实为「**任意 2–6 个汉字 + 转债**」——
    #   实测把**用户问句里的自身情况**（「我手里有一只转债亏了 8%，要不要割掉？」）当成
    #   "含具体数据的陈述句" ⇒ **假红**，并逼得作答者**改题面**去规避（判官对照实验两次复现）。
    #   修法两件：① **删掉该假模式**（"转股价 15.05 元"这类真数据句由第一支的"数字＋单位"覆盖）；
    #   ② **声明射程排除**：槽⑤ 只作用于**陈述**；**问句行是用户自陈，不属"书内/外推"射程**，
    #      按 `MISSING_Q_RE` 识别并**跳过**，且**在报告里打印跳过行数**（不静默）。
    #   ⚠ 方向说明：这是**收紧**（去掉一个不看语义的宽模式）＋**射程声明**，不是放松。
    DATA_RE = re.compile(r'(\d+(?:\.\d+)?\s*(?:%|％|元|亿元|万元|倍|个交易日|日|年|月))|'
                         r'(\d{2,}[A-Za-z]{2}\b)')
    data_lines, unsourced, skipped_q = [], [], 0
    for i, l in enumerate(t.split('\n')):
        if len(re.sub(r'[^\u4e00-\u9fff]', '', l)) < 8:
            continue
        if l.lstrip().startswith(('|', '```')):
            continue
        if MISSING_Q_RE.search(l):          # ← 射程排除：问句行（用户自陈）
            skipped_q += 1
            continue
        if not DATA_RE.search(l):
            continue
        data_lines.append(l)
        has_anchor = bool(ANCHOR_RE.search(l))
        marked = ('【外推' in l) or ('【外推' in (t.split('\n')[i - 1] if i else ''))
        in_corpus = bool(corpus) and (re.sub(r'\s', '', l) in corpus)
        if not (has_anchor or marked or in_corpus):
            unsourced.append(l.strip()[:80])
    ok5 = not unsourced
    rep.append('| ⑤ 数据句回源或标外推（**硬机制**） | %s | 含数据句 %d ／ **无源且未标外推 %d**'
               '（射程：仅**陈述**；按问句词表跳过 %d 行） |'
               % ('PASS' if ok5 else '🔴 FAIL', len(data_lines), len(unsourced), skipped_q))
    if unsourced:
        fatal.append('槽⑤：**含具体数据的句子既不在原文里、也没标【外推】** %d 句（"要么是书里的，'
                     '要么承认是你推的"未做到）：%s'
                     % (len(unsourced), '；'.join('「%s…」' % x for x in unsourced[:3])))

    text = IDEMPOTENT_MARK + '\n\n# 三基线运行时闸 · 报告\n\n' + '\n'.join(rep) + '\n'
    text += '\n## 二、结论\n\n'
    if fatal:
        text += '🔴 **三槽不合规**（rc=1）：\n' + '\n'.join('- ' + x for x in fatal) + '\n'
    else:
        text += '✔ **三槽合规** —— 引文全部可回源、【外推】块都写了前提、缺信息型问句有判停与字段清单。\n'
    if warn:
        text += '\n### 告警（不影响 rc）\n' + '\n'.join('- ' + x for x in warn) + '\n'
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        io.open(out, 'w', encoding='utf-8', newline='\n').write(text)
    return (1 if fatal else 0), text, dict(quotes=len(quotes), miss=len(miss_quote),
                                          extrap=len(ex_blocks), noanchor=len(noanchor))


def selftest():
    """好 1 放行 ＋ 坏 5 全拦（A-55：坏样本漏检比误报更致命）。"""
    import shutil
    import tempfile
    bad = []
    tmp = tempfile.mkdtemp(prefix='asg-')
    try:
        corpus = os.path.join(tmp, 'corpus.txt')
        io.open(corpus, 'w', encoding='utf-8', newline='\n').write(
            '上市公司分红时，可转债初始转股价格直接减分红金额即可。\n'
            '当上市公司回购股票注销时，将会出现转股价格向上调整的情况。\n')
        good = ('## [原文]\n'
                '> 「上市公司分红时，可转债初始转股价格直接减分红金额即可。」（`E-001` s47）\n'
                '## [外推]\n【外推】长期无分红则无下调补偿。依赖前提：注销按公开口径触发；'
                '前提破了则结论退化为中性。\n')
        # 好2（2026-09-23 新增 · G-4）：文中出现**品种名**「可转债」但**同行无数值** ⇒ **不得**判槽⑤
        good2 = ('## [原文]\n'
                 '> 「上市公司分红时，可转债初始转股价格直接减分红金额即可。」（`E-001` s47）\n'
                 '补充说明：可转债这一品种的条款安排与普通公司债不同。\n')
        # 好3（2026-09-23 新增 · 把"判据看不见否定/修饰"这个洞钉住）：
        #   缺信息型 + 判停 + 清单 + **豁免声明里带 markdown 强调符与"任何"**
        #   （实测：`不含任何**仓位比例**` 曾被判成"给了结论" ⇒ 新假红）
        good3 = ('我手里有个仓位，现在要不要割掉？\n\n判停。\n'
                 '本答卷**不含**任何**买卖指令**、不含任何**仓位比例**、不含任何**目标价**。\n'
                 '需要你提供：①成本价 ②持有期限。\n')
        cases = {
            '好样本（无缺信息问句）': (good, 0),
            '好2 品种名无数值不得判红': (good2, 0),
            '好3 豁免声明带强调符不得判红': (good3, 0),
            '坏1 引文回源未命中': ('## [原文]\n> 「分红时可转债转股价一律下调百分之十。」（`E-002` s47）\n', 1),
            '坏2 外推未写前提': ('## [原文]\n> 「上市公司分红时，可转债初始转股价格直接减分红金额即可。」（`E-001` s47）\n'
                            '## [外推]\n【外推】所以长期不分红就没补偿。\n', 1),
            '坏3 缺信息问句无字段清单': ('我手里有一只转债亏了 8%，要不要割掉？\n\n结论：建议割掉。\n', 1),
            '坏4 缺信息问句未判停但有清单': ('我手里有一只转债亏了 8%，要不要割掉？\n\n'
                                   '需要你提供：①成本价 ②持有期限。\n\n结论：建议持有。\n', 1),
            '坏5 引文回源未命中＋外推无前提': ('## [原文]\n> 「纯派现一律按面值调整。」（`E-003` s47）\n'
                                    '## [外推]\n【外推】因此不存在下调。\n', 1),
            # 坏6（G-3(b)）：判停＋清单齐，**但仍给可执行动作** ⇒ 必须红（改前会 PASS）
            '坏6 判停且有清单但给动作结论': ('我手里有一只转债，要不要割掉？\n\n判停。\n'
                                    '需要你提供：①成本价 ②持有期限。\n\n建议割掉。\n', 1),
            # 坏7（G-3(a)）：把「不判停」当判停 ⇒ 必须红（改前 `STOP_DECL_RE` 被骗而 PASS）
            '坏7 用「不判停」冒充判停': ('我手里有一只转债，要不要割掉？\n\n本题不判停。\n'
                                 '需要你提供：①成本价 ②持有期限。\n', 1),
        }
        for name, (txt, want) in cases.items():
            p = os.path.join(tmp, name + '.md')
            io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
            rc, rep, _st = check(p, corpus)
            good_rc = (rc == want)
            if name.startswith('好') and rc != 0:
                good_rc = False
            print('  %-4s %-26s rc=%d（期望 %d）' % ('✔' if good_rc else '🔴', name, rc, want))
            if not good_rc:
                bad.append('%s：期望 rc=%d 实得 rc=%d' % (name, want, rc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if bad:
        print('🔴 三基线运行时闸自证失败 %d 项' % len(bad))
        return 1
    print('✔ 三基线运行时闸自证通过（好 3 放行 ＋ 坏 7 全拦）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='三基线运行时闸（点回原文／标注推测／先追问缺信息）')
    ap.add_argument('--answer', help='答卷 .md')
    ap.add_argument('--corpus', help='原文册/池（文件或目录）')
    ap.add_argument('--out', help='报告 .md')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    if not a.answer:
        ap.error('须给 --answer')
    rc, text, _st = check(a.answer, a.corpus, a.out)
    if not a.quiet:
        print(text)
    if a.out:
        print('报告：%s' % a.out)
    print('退出码：%d（0=三槽合规 ／ 1=有红 ／ 2=前置不满足）' % rc)
    return rc


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
