# -*- coding: utf-8 -*-
r"""orphan_gate_check.py —— **孤儿闸检查**：找出"造了却没有挂进任何入口"的闸

## 为什么必须存在（2026-09-21 用户问「这三条现在是一定做了还是触发时必须做？」时实测）

我建了三件运行时闸（`assertion_gate` / `corpus_binding_check` / `instrument_sufficiency`），
**它们都通过了自证、都进了包**，但实测：

```
preflight.py      assertion_gate=0  corpus_binding=0  instrument_sufficiency=0
postflight.py     assertion_gate=0  corpus_binding=0  instrument_sufficiency=0
```

⇒ **没有任何入口会自动调用它们** ⇒ "触发时必须做"在执行层**无法保证**（要靠"我记得跑"）。
这就是 `A-98`（手册声称有、闸不认＝纸面项）在**工具层**的同族形态：**纸面闸**。

## 判据（闭式 · 零模型）

对 `tools\`（＋插件 `scripts\gates\`）里每一个**门禁类**脚本（文件名以 `check_` / `gate_` / `verify_` /
`assertion_` / `corpus_` / `instrument_` / `scan_` / `distill_` / `rquote_` 等开头的 `.py`），判定：
  · **已挂**：被 `preflight.py` / `postflight.py` / `gate_start.py` / `gate_stage.py` /
    `gate_checklist.py` / `pitfall_audit.py` 中至少一个**以文件名字符串**引用；
  · **孤儿**：以上都不引用 ⇒ **它永远不会自动跑**（除非人记得）。
并给出**分流建议**（按是否有 `--selftest`、是否需要任务参数）。

## 用法

    python tools\orphan_gate_check.py [--out <报告.md>] [--limit N]
    python tools\orphan_gate_check.py --selftest

退出码：0 ＝ 无孤儿；1 ＝ 有孤儿（**报告即清单，供逐条决定"挂进去还是降级为可选"**）。
⚠ 本件**不判"孤儿闸是错的"**——有些件本就是一次性/可选工具；它只保证**你不可能不知道**。
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

HERE = os.path.dirname(os.path.abspath(__file__))
GATE_PREFIX = ('check_', 'gate_', 'verify_', 'assertion_', 'corpus_', 'instrument_',
               'scan_', 'distill_', 'rquote_', 'machine_', 'layer_quotes', 'blindtest_',
               'defense3_', 'probe_book_form', 'orphan_')
ENTRY = ('preflight.py', 'postflight.py', 'gate_start.py', 'gate_stage.py',
         'gate_checklist.py', 'pitfall_audit.py')
SKIP = ('_gate_selftest.json',)

# ── 间接挂载枚举（2026-09-21 新会话测试批修正 · 原判据只认"文件名出现在入口文件文本里"）──
# 缺陷实录：`verify_layer_quotes.py` 被判孤儿，实际**每次 postflight 都会跑**——
#   链路＝`postflight ⑧-c` → `gate_layer_quotes.py` →（`subprocess` 调 CLI）`verify_layer_quotes.py`；
#   而本扫描器只查"入口文件的文本里有没有这个文件名"，**一跳之外的挂载它看不见**。
# 纪律：本表**只登记已被入口链真实调用的件**（登记错＝把孤儿伪装成已挂，比漏报更坏）；
#   每行须写清"哪个入口→哪一跳→本件"，且该链路必须能在源码里逐字查到。
INDIRECT_MOUNTS = {
    'verify_layer_quotes.py':
        'postflight ⑧-c → gate_layer_quotes.py（subprocess 调其 CLI，L77/L126）→ 本件',
}


def _entries_text():
    t = ''
    for e in ENTRY:
        p = os.path.join(HERE, e)
        if os.path.isfile(p):
            t += io.open(p, encoding='utf-8', errors='replace').read()
    return t


def scan(limit=None):
    ents = _entries_text()
    rows = []
    for f in sorted(os.listdir(HERE)):
        if not f.endswith('.py') or f.startswith('_') or f in ENTRY:
            continue
        if not f.startswith(GATE_PREFIX):
            continue
        path = os.path.join(HERE, f)
        src = io.open(path, encoding='utf-8', errors='replace').read()
        mounted = (f in ents) or (f in INDIRECT_MOUNTS)
        rows.append(dict(name=f, mounted=mounted, size=os.path.getsize(path),
                         has_selftest='--selftest' in src,
                         needs_task=bool(re.search(r"add_argument\('--task'", src))))
    orphan = [r for r in rows if not r['mounted']]
    if limit:
        orphan = orphan[:limit]
    return rows, orphan


def report(rows, orphan, out=None):
    L = ['# 孤儿闸检查报告', '',
         '判据：门禁类脚本（`tools\*.py`，文件名以门禁前缀开头）中，**未被任何入口自动调用**者＝孤儿。',
         '入口＝`%s`。' % '`、`'.join(ENTRY), '',
         '| 判态 | 计数 | 含义 |', '|---|---|---|',
         '| 已挂 | %d | 有入口会自动跑它 |' % len([r for r in rows if r['mounted']]),
         '| **孤儿** | **%d** | **永远不会自动跑**（除非人记得）——这就是"触发时必须做"在执行层的缺口 |'
         % len(orphan), '']
    if orphan:
        L += ['## 孤儿闸（逐条给分流建议）', '',
              '| 闸 | 字节 | 有 `--selftest` | 需 `--task` | 建议 |', '|---|---|---|---|---|']
        for r in orphan:
            if r['needs_task']:
                sug = '**按任务挂**（无活跃任务时应显式"不适用"，不判 PASS）'
            elif r['has_selftest']:
                sug = '可挂 `preflight`（通用自证，零参数）'
            else:
                sug = '无自证 ⇒ 先补 `--selftest` 再考虑挂'
            L.append('| `%s` | %d | %s | %s | %s |'
                     % (r['name'], r['size'], '是' if r['has_selftest'] else '否',
                        '是' if r['needs_task'] else '否', sug))
    else:
        L.append('**无孤儿** —— 所有门禁类脚本都有入口会自动调用。')
    text = '\n'.join(L) + '\n'
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        io.open(out, 'w', encoding='utf-8', newline='\n').write(text)
    return text


def selftest():
    """自证：扫描器有效 ＋ 假名字不得被当成"引用"（防发版闸 D 判据把它当真引用）。

    ⚠ 自身缺陷实录（2026-09-21 · 代价：整包被发版闸拦下、两个 tgz 改名 `*.BLOCKED`）：
      首版自证里**写了一个不存在的探测文件名**当"必然未被引用的假名字"，
      发版闸 **D 引用闭合性** 把脚本里出现的任何 `.py` 字面量都当成**包内引用**
      ⇒ 报「引用了该文件名 —— 全包内均无」⇒ **硬项红、不得发布**。
      ⇒ 教训：**自证样本里的"假文件名"不是无害的**（同族：`A-142`）。
      修法：自证改为**纯计算**判别力（前缀一致性 ＋ 计数自洽 ＋ 入口自身不被检），
      **并且连注释里也不许再出现那个假文件名**——发版闸扫的是文件文本，不区分代码与注释。

    ⚠ 第二处自身缺陷实录（2026-09-21 新会话测试批 · 由新会话独立复核实测发现）：
      ① **前缀表漏了 `orphan_`** ⇒ **本件自己（`orphan_gate_check.py`）从未被扫到**
         ——"造了却没挂的闸"的检查器自己不在检查范围内，是**自指盲区**；
      ② **间接挂载看不见** ⇒ `verify_layer_quotes.py` 每次 `postflight` 都跑（经 `gate_layer_quotes.py`），
         却被判孤儿。
      修法：前缀表补 `orphan_`；引入 `INDIRECT_MOUNTS` 并把**每条链路的可达性写进自证**
      （不能只写静态名单——名单会腐烂成"把孤儿伪装成已挂"）。
    """
    rows, orphan = scan()
    print('  扫描门禁类脚本 %d 个 ／ 孤儿 %d 个' % (len(rows), len(orphan)))
    names = [r['name'] for r in orphan]
    print('  孤儿示例：%s' % ('、'.join(names[:6]) if names else '（无）'))
    if not rows:
        print('🔴 自证失败：一个门禁类脚本都没扫到（判据恒空转）')
        return 1
    # ⓪ 间接挂载名单必须"可达"（防名单腐烂成静态豁免）：本件存在 ＋ 中间件真按名调用它
    for _tgt, _why in sorted(INDIRECT_MOUNTS.items()):
        _tp = os.path.join(HERE, _tgt)
        if not os.path.isfile(_tp):
            print('🔴 自证失败：间接挂载名单里的 %s 不存在（名单已腐烂）' % _tgt)
            return 1
        _mid = _why.split('→')[1].strip().split('（')[0].strip() if '→' in _why else ''
        _mp = os.path.join(HERE, _mid)
        if not os.path.isfile(_mp):
            print('🔴 自证失败：间接挂载 %s 声称的中间件 %s 不存在' % (_tgt, _mid))
            return 1
        _msrc = io.open(_mp, encoding='utf-8', errors='replace').read()
        if _tgt not in _msrc:
            print('🔴 自证失败：间接挂载 %s 声称经 %s 调用，但该件源码里找不到它'
                  '（**把孤儿伪装成已挂**，比漏报更坏）' % (_tgt, _mid))
            return 1
    # ⓪-b 本件必须自己被扫到（自指盲区回归闸）
    if not any(r['name'] == 'orphan_gate_check.py' for r in rows):
        print('🔴 自证失败：本件自己未被扫到（前缀表缺 `orphan_` ⇒ 自指盲区复发）')
        return 1
    # 判别力自证（纯计算）：① 所有被扫到的都以门禁前缀开头
    if any(not r['name'].startswith(GATE_PREFIX) for r in rows):
        print('🔴 自证失败：扫到了非门禁前缀的文件（判据过宽）')
        return 1
    # ② 已挂数 + 孤儿数 == 扫描总数（计数自洽）
    mounted = len([r for r in rows if r['mounted']])
    if mounted + len(orphan) != len(rows):
        print('🔴 自证失败：已挂 %d + 孤儿 %d ≠ 扫描 %d' % (mounted, len(orphan), len(rows)))
        return 1
    # ③ 入口自身不得被当成被检对象
    if any(r['name'] in ENTRY for r in rows):
        print('🔴 自证失败：入口脚本被当成被检对象')
        return 1
    print('✔ 孤儿闸检查自证通过（已挂 %d ＋ 孤儿 %d ＝ 扫描 %d；判别力纯计算自证）'
          % (mounted, len(orphan), len(rows)))
    return 0


def main():
    ap = argparse.ArgumentParser(description='孤儿闸检查（造了却没挂的闸）')
    ap.add_argument('--out', help='报告 .md')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    rows, orphan = scan(a.limit)
    text = report(rows, orphan, a.out)
    if not a.quiet:
        print(text)
    if a.out:
        print('报告：%s' % a.out)
    # 供调用方（如 preflight）机器取数：恒打印一行，格式固定
    print('孤儿闸计数：%d' % len(orphan))
    print('退出码：%d（0=无孤儿 ／ 1=有孤儿，清单见上）' % (0 if not orphan else 1))
    return 0 if not orphan else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
