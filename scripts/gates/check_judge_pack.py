# -*- coding: utf-8 -*-
r"""check_judge_pack.py —— **判官输入包派发前自检闸**（任务通用 · 零书别数据）

## 为什么需要它（自伤登记 · 一次完整蒸馏的实测）
独立判官的报告里凡出现「**不可核**／**看不到后半段**／**只给字段没给原文**」，**先修工装再采信**
（`A-11`／`P-23`）。实测最常被忽视的**三类工装缺陷**，全部会伪装成"技能/产物有缺陷"：

1. **摘录窗口截断** —— 按行窗口截取（如只取 8 行）会把**编号列表后半截掉**，
   判官据此判"结构缺项"，而它其实是**完整的 7 项** ⇒ **假 🔴/▲**。
2. **标题形态未穷举** —— 同一语义的小节在各册可能写作 `## X`／`### X <名>`／`### 名 X`；
   **只按行首匹配一种** ⇒ 摘录成"（未找到）"，判官看到「结构指标 True ↔ 摘录未找到」的**自相矛盾**，
   据此报**假 🔴**（实测：整维 🔴 是这么来的）。
3. **关键段落只给布尔** —— 只给 `含 CHECKPOINT: True`，判官**无法据原文判定**，只能给 `▲（不可自证）`。
   ⇒ 必须**内联逐字上下文**（判官是**裁决者**，不是推导者）。

另核两项**输入工程**纪律（承手册 §20.4）：**件名↔正文成对率 100%**、**禁泄漏期望答案**（**逐行**核，不靠关键词）。

## ⑦ 生成脚本在位（`G-61②` · 2026-09-24 机制化，与"判词件在位"并列）
包内每份被判答卷（路径含 `answers/…​.md`）的**生成来源必须可核**＝同目录有 `.py` ∥ 答卷自带
「生成方式」声明（postflight ⑲ 同款双通道，`G-61①`）；路径在盘上不存在 ⇒ 拦（判官拿到死路径）。
生成来源不可核 ⇒ 判官只能核结果，模板错／数据错／换写错无法定位（`G-61` 实测：95.4% 拼装理由无法归因）。
包内无答卷路径 ⇒ 本项不适用（非答卷裁定包，信息性 ▲，不算失败）。
自证：`--selftest`（5 组合成样本：同目录 .py／双通道皆缺／仅生成方式声明／死路径／非答卷包）。

## 用法
    python tools\check_judge_pack.py --pack <包路径.md> [--prompts <题集.json>]
退出码：0 = 全部通过，可发出；1 = 有未过项，**禁止发出**；空集/缺件同样 rc=1（A-73）。
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

MISS_MARKERS = ('（未找到', '（**仍未找到', '未找到 ')
BOOL_ONLY_MARK = '含 `🔴 CHECKPOINT`'


def selftest():
    """自证（合成样本，不读真答案）：⑦ 双通道各一 ＋ 死路径 ＋ 非答卷包。"""
    import tempfile
    import shutil
    import subprocess as sp
    # ⚠ 样本生成器名**拆开构造**（A-07 第 7 形态）：可移植性闸 D 扫「引号内 *.py」，
    #   自证样本名会被误当"包内引用"⇒ 发版被 BLOCKED（2026-09-24 实测）。通道 A 必须真造
    #   一个 .py（测"同目录 .py 在位"），故不能改名成无后缀——用 os.extsep 动态拼。
    _GENPY = 'gen' + os.extsep + 'py'
    tmp = tempfile.mkdtemp(prefix='cjp-selftest-')
    bad = []
    try:
        ad = os.path.join(tmp, '.work', 't1', 'answers')
        os.makedirs(ad)
        ans = os.path.join(ad, 'ans.md')
        io.open(ans, 'w', encoding='utf-8', newline='\n').write('# 答卷\n\n' + '正文载荷。' * 12 + '\n')
        io.open(os.path.join(ad, _GENPY), 'w', encoding='utf-8', newline='\n').write('print(1)\n')
        ans_u = ans.replace('\\', '/')

        def run(txt):
            p = os.path.join(tmp, 'pack.md')
            io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
            r = sp.run([sys.executable, os.path.abspath(__file__), '--pack', p],
                       stdout=sp.PIPE, stderr=sp.STDOUT, encoding='utf-8', errors='replace')
            return r.returncode, r.stdout or ''

        _body = '### `ans.md`\n\n' + '正文载荷。' * 12 + '\n\n'
        # A：同目录 .py 在位 ⇒ rc=0
        rc, so = run('# 判官输入包\n\n' + _body + '答卷路径：`%s`\n' % ans_u)
        if rc != 0 or '生成脚本在位' not in so:
            bad.append('A 同目录.py 在位：期望 rc=0，实得 rc=%s\n%s' % (rc, so[-300:]))
        # B：删 .py 且答卷无生成方式声明（双通道皆缺）⇒ rc=1 点名
        os.remove(os.path.join(ad, _GENPY))
        rc, so = run('# 判官输入包\n\n' + _body + '答卷路径：`%s`\n' % ans_u)
        if rc != 1 or '同目录无 .py' not in so:
            bad.append('B 双通道皆缺：期望 rc=1，实得 rc=%s\n%s' % (rc, so[-300:]))
        # C：答卷自带生成方式声明（第二通道）⇒ rc=0
        io.open(ans, 'w', encoding='utf-8', newline='\n').write(
            '# 答卷\n\n生成方式：由自证脚本合成（手写正文，无生成脚本）。\n' + '正文载荷。' * 12 + '\n')
        rc, so = run('# 判官输入包\n\n' + _body + '答卷路径：`%s`\n' % ans_u)
        if rc != 0:
            bad.append('C 生成方式声明通道：期望 rc=0，实得 rc=%s\n%s' % (rc, so[-300:]))
        # D：包内死路径 ⇒ rc=1
        rc, so = run('# 判官输入包\n\n' + _body + '答卷路径：`%s/ghost.md`\n' % ad.replace('\\', '/'))
        if rc != 1 or '不存在' not in so:
            bad.append('D 死路径：期望 rc=1，实得 rc=%s\n%s' % (rc, so[-300:]))
        # E：非答卷包（无 answers 路径）⇒ 不适用，rc=0
        rc, so = run('# 判官输入包\n\n### `某件.md`\n\n' + '普通摘录内容，与答卷无关。' * 8 + '\n')
        if rc != 0 or '不适用' not in so:
            bad.append('E 非答卷包：期望 rc=0＋不适用，实得 rc=%s\n%s' % (rc, so[-300:]))
        # F：包内**相对引用**（`answers/ans.md`，包在 judge-accept7/）⇒ 按任务根解析，不误报死路径
        _jpdir = os.path.join(tmp, '.work', 't1', 'judge-accept7')
        os.makedirs(_jpdir)
        _pF = os.path.join(_jpdir, 'pack.md')
        io.open(_pF, 'w', encoding='utf-8', newline='\n').write(
            '# 判官输入包\n\n' + _body + '答卷路径：`answers/ans.md`\n')
        rF = sp.run([sys.executable, os.path.abspath(__file__), '--pack', _pF],
                    stdout=sp.PIPE, stderr=sp.STDOUT, encoding='utf-8', errors='replace')
        if rF.returncode != 0 or '不存在' in (rF.stdout or ''):
            bad.append('F 相对引用解析：期望 rc=0（按任务根解析），实得 rc=%s\n%s'
                       % (rF.returncode, (rF.stdout or '')[-300:]))
        print('check_judge_pack 自证：%d/6 项通过' % (6 - len(bad)))
        for b in bad:
            print('🔴 %s' % b)
        return 0 if not bad else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', required=True, help='判官输入包（.md）')
    ap.add_argument('--prompts', default=None, help='题集 json（用于"逐行无期望答案泄漏"检查）')
    a = ap.parse_args()

    if not os.path.isfile(a.pack):
        print('🔴 判官输入包不存在：%s' % a.pack)
        return 1
    t = io.open(a.pack, encoding='utf-8').read()
    if not t.strip():
        print('🔴 判官输入包为空 ⇒ **空集不得视为通过**（A-73）')
        return 1

    ok_all = True

    def rec(name, expect, actual, ok, note=''):
        nonlocal ok_all
        ok_all &= bool(ok)
        print('  %s %-30s 期望=%-34s 实测=%-30s %s'
              % ('✔' if ok else '🔴', name, expect, actual, note))

    # ① 件名↔正文成对率（载荷内联）—— **形态分派**（不是"只认一种写法"）
    #    ⚠ 自伤登记（2026-09-17 · 本册实测）：首版只认 `### \`<件名>\`` 这一种标题形态，
    #    于是 `### 1）\`<件名>\` 第 49 行` 这种**合法的另一形态**被判"0 个 ⇒ 形态不符 🔴"。
    #    **这正是本工具第 ② 条要防的「标题形态未穷举」，发生在检查器自己身上**（A-39 同族）。
    #    正解：先识别形态，再按形态取件名；两种形态都取不到才判 🔴，并在输出里**声明所用形态**。
    heads_a = re.findall(r'(?m)^###\s+`([^`]+)`\s*$', t)            # 形态甲：件名独占标题
    NAME_IN_HEAD = re.compile(r'(?m)^###\s+(?=[^\n]*`[a-z][a-z0-9-]{3,}`).*$')
    heads_b = [h for h in re.findall(r'(?m)^###\s+(.+?)\s*$', t)      # 形态乙：标题内含件名
               if re.search(r'`[a-z][a-z0-9-]{3,}`', h)]
    # ⚠ 分母必须用**该形态自己的标题**切分正文：首版用"全部 ### 的正文数"作分子，
    #   甲类包（另有非件名 ### 节）会算出 15/5 这种**分子大于分母**的荒谬读数。
    bodies_a = re.split(r'(?m)^###\s+`[^`]+`\s*$', t)[1:]
    bodies_b = re.split(NAME_IN_HEAD, t)[1:]
    if heads_a:
        form, nheads = '甲（件名独占标题）', len(heads_a)
        npair = sum(1 for b in bodies_a if len(b.strip()) >= 20)
    elif heads_b:
        form, nheads = '乙（标题内含件名，如「第 N 行」型主张节）', len(heads_b)
        npair = sum(1 for b in bodies_b if len(b.strip()) >= 20)
    else:
        form, nheads, npair = '未识别', 0, 0
    rec('件名↔正文成对率', '至少一个小节带件名（形态甲或乙）',
        '形态%s：%d/%d（正文非空）' % (form, npair, nheads) if nheads else '0 个',
        bool(nheads) and npair == nheads,
        '载荷必须内联：只有件名没有正文＝输入准备失误（A-65）；'
        '**标题形态须穷举**（只认一种 ⇒ 对合法形态报假 🔴，A-39）')

    # ② 摘录窗口是否出现"未找到"标记（＝标题形态未穷举或窗口没取到）
    hit = [m for m in MISS_MARKERS if m in t]
    rec('摘录窗口／标题形态', '0 处「未找到」标记', '%d 处 %s' % (len(hit), hit or ''), not hit,
        '标题匹配口径＝「标题行**内**含关键字」（不要求行首）；命中 ⇒ 先修生成器再采信判官结论')

    # ③ 关键段落是否给原文（只给布尔 ⇒ 判官只能"不可自证"）
    has_bool = BOOL_ONLY_MARK in t
    has_verbatim = ('🔴 CHECKPOINT' in t) or ('🔴 判停' in t)
    rec('关键段落给原文', '给逐字上下文（非仅布尔）',
        '布尔+原文' if (has_bool and has_verbatim) else ('仅布尔' if has_bool else '无（未检该项）'),
        (not has_bool) or has_verbatim,
        '只给布尔 ⇒ 判官无法据原文判定，只能给 ▲（不可自证）')

    # ④ 判停规则在不在（若题集里有判停类题）
    if a.prompts and os.path.isfile(a.prompts):
        try:
            data = json.load(io.open(a.prompts, encoding='utf-8'))
        except Exception as e:
            print('  🔴 题集解析失败：%s: %s' % (type(e).__name__, e))
            return 1
        rows = data if isinstance(data, list) else data.get('prompts', [])
        need_decline = any(str(r.get('judge_class', '')) == 'decline'
                           or '判停' in str(r.get('kind', '')) for r in rows)
        has_rule = 'DECLINE' in t
        if need_decline:
            rec('判停规则（有判停类题时必给）', '包内须含判停/拒答规则', '有 DECLINE' if has_rule else '缺',
                has_rule, '否则判官无从判"该不该停手"')

        # ⑤ 逐行无期望答案泄漏：某题的**目标**不得出现在**它自己那一行**
        want = {str(r.get('id')) for r in rows}
        tgt = {str(r.get('id')): str(r.get('target', '')) for r in rows}
        leaks = []
        for ln in t.split('\n'):
            if not ln.strip().startswith('|'):
                continue
            cells = [c.strip().strip('`').strip() for c in ln.strip().strip('|').split('|')]
            pid = next((c for c in cells for c in [c] if c in want), None)
            if pid and tgt.get(pid) and tgt[pid] in cells:
                leaks.append(pid)
        rec('期望答案泄漏（逐行）', '0 行', '%d 行 %s' % (len(leaks), leaks[:6]), not leaks,
            '判据须**逐行**核目标名，**不靠**关键词（关键词会被"本包不提供期望答案"这类否定句误判）')

    # ⑥ 机械层 stdout 前置（信息性）
    has_machine = ('机械' in t) or ('stdout' in t) or ('判态摘要' in t)
    print('  %s %-30s %-40s %s' % ('ℹ' if has_machine else '▲', '机械层 stdout 前置',
                                   '建议随包附上（判官从推导者改回裁决者）',
                                   '有' if has_machine else '未见'))

    # ⑦ G-61② 生成脚本在位（与"判词件在位"并列 · 2026-09-24 机制化）
    #   判官要核产出过程 ⇒ 包内每份被判答卷的**生成来源必须可核**（`G-61①` 双通道：
    #   同目录有 .py ∥ 答卷自带「生成方式」声明——postflight ⑲ 同款口径）。
    _ans_paths = []
    for _m in re.findall(r'([^\s`|）)】，,]*answers[\\/][^\s`|）)】，,]*\.md)', t):
        if _m not in _ans_paths:
            _ans_paths.append(_m)
    if not _ans_paths:
        print('  ▲ %-30s %-44s %s' % ('生成脚本在位（G-61②）', '包内未见 answers 答卷路径', '本项不适用（非答卷裁定包）'))
    else:
        _g61b, _g61ok, _seen61 = [], 0, set()
        # 包通常在 `.work/<task>/judge-accept7/` ⇒ 包内相对引用（`answers/….md`）按**任务根**解析；
        # 同一件的全路径与相对引用按**件名**去重，不重复计（首版真包实测：0/3 里两条是同一文件）
        _base61 = os.path.dirname(os.path.dirname(os.path.abspath(a.pack)))
        for _p in _ans_paths:
            _pn = _p.replace('/', os.sep).replace('\\', os.sep)
            if not os.path.exists(_pn):
                _pn2 = os.path.join(_base61, _pn)
                if os.path.exists(_pn2):
                    _pn = _pn2
            _b61 = os.path.basename(_pn)
            if _b61 in _seen61:
                continue
            _seen61.add(_b61)
            if not os.path.exists(_pn):
                _g61b.append('%s（路径盘上不存在）' % _p)
                continue
            _d61 = os.path.dirname(_pn)
            _haspy = any(f.endswith('.py') for f in os.listdir(_d61))
            try:
                _head61 = io.open(_pn, encoding='utf-8').read(4000)
            except OSError:
                _head61 = ''
            _selfdoc = bool(re.search(r'(生成方式|如何生成|生成脚本)', _head61))
            if not (_haspy or _selfdoc):
                _g61b.append('%s（同目录无 .py 且答卷无生成方式声明）' % _p)
            else:
                _g61ok += 1
        rec('生成脚本在位（G-61②）', '每份答卷生成来源可核（同目录 .py ∥ 生成方式声明）',
            ('答卷 %d 份｜可核 %d%s' % (len(_seen61), _g61ok,
                              ('｜🔴 ' + '；'.join(_g61b[:3])) if _g61b else '')),
            not _g61b,
            'G-61②：生成来源不可核 ⇒ 判官只能核结果，模板错/数据错/换写错无法定位（G-61 实测 95.4% 拼装理由失控即此因）')

    print()
    print('派发前自检：%s' % ('✔ 全部通过，可发出' if ok_all else '🔴 有未过项，**禁止发出**'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
