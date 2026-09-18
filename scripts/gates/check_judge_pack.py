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

    print()
    print('派发前自检：%s' % ('✔ 全部通过，可发出' if ok_all else '🔴 有未过项，**禁止发出**'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
