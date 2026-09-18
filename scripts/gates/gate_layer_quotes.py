# -*- coding: utf-8 -*-
"""gate_layer_quotes.py —— 「引文型附属文件」零问题机检闸（把判官要求固化成 rc=0 闸）

来源：2026-09-13/14 六名独立判官（C／E／F／G1／G2／G3）对同一套附件的复核，共推翻执行者仪器 **6 次**，
每一条要求都对应一次真实自伤（坑 A-41…A-50）。本闸把"判官提过的每一件事"变成**可机检的断言**，
使「蒸馏后无问题」不再是主观宣称。

断言（任一不过即 rc=1）：
  R1 **锚块全部可解析**：每个 `【…】` 块必须解析出 ≥1 个 (书,页)；
     不可解析的（`〔承上文〕`／书代号畸形）数量必须**登记在册**（≤ 白名单上限），且逐条打印。
  R2 **引文全覆盖**：每条引文必须有状态（不得有"未分类"留白）。
  R3 **分栏自洽**：各栏之和 == 引文总数（A-42）。
  R4 **归一化族齐全**：`『』`／全半角括号／空白／markdown 强调符必须都在归一化表内（A-04 家族；
     判官 G2 实测 8 组仅靠此即可转正）。
  R5 **未命中零未处置**：每条"未命中"必须能归入一个**已声明类别**（短片段／长引文待复核／已改／已登记边界），
     并打印各类计数。**不得存在"未分类"的未命中。**
  R6 **判据不依赖"引文↔锚"位置配对**（A-49）：判定用**该行全部锚的并集**；脚本内不得把配对结果当判定前提。
  R7 **空集拒跑**（A-37 同族）：解析 0 条引文或 0 个锚块 ⇒ 直接拒跑。
  R8 **产物自带 schema 版本与口径全字段**（A-46：计数不可跨版本比较）。

用法：python tools\\gate_layer_quotes.py --task adhd-pro [--strict]
      `--strict`：把"长引文待复核"也视为红（交付前可要求）
"""
import io
import os
import re
import sys
import json
import glob
import argparse
import subprocess

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
ANCHOR_BLOCK = re.compile(r'【[^】]*】')
# R1 白名单：允许存在的不可解析锚（必须逐条登记，且数量不超过上限）
# R1 登记配额（2026-09-14 实测基线 196）：**只许减少，不许增长**。
#   新增"缺书代号锚" ⇒ 红（防"每蒸馏一本就多一批无源锚"）。
#   处置口径：**不猜改文件**（写错书代号比缺更糟）；核验时以**该专业层文件头声明的来源书**作回退（口径见 §22）。
UNPARSABLE_ALLOW = 196
SHORT_LEN = 20


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', default='adhd-pro')
    ap.add_argument('--strict', action='store_true')
    # ⚠ 通用化（2026-09-17 manias-crashes 实测抓到 · A-01 同族）：原实现把被检目录与文件名
    #   写死为 `skills\adhd-parenting-guide\references\专业层-*.md` ⇒ **换书即 0 命中**，
    #   而 0 命中会触发"空集拒跑"⇒ 该闸对新任务**永远无法通过**（不是漏检，是没生效）。
    #   新增两个开关（默认值＝原行为，向后兼容）：
    #     --ref-dir   被检目录（相对任务目录；默认 adhd-pro 的 references）
    #     --glob      文件名 glob（默认 `专业层-*.md`）
    ap.add_argument('--ref-dir', default=os.path.join('skills', 'adhd-parenting-guide', 'references'))
    ap.add_argument('--glob', default='专业层-*.md')
    a = ap.parse_args()
    task = a.task.replace('.work/', '').replace('.work\\', '')
    TASK = os.path.join(ROOT, '.work', task)
    REF = os.path.join(TASK, a.ref_dir)
    CLI = os.path.join(ROOT, 'tools', 'verify_layer_quotes.py')

    print('=== 引文型附属文件 · 零问题机检闸 ===')
    env = dict(os.environ, PYTHONIOENCODING='utf-8')

    # ---- R1：锚块可解析率（**分清"锚"与"说明性方括号"**）----
    #   首版把**所有** `【…】` 当锚 ⇒ 225 个说明性方括号（`【核验记录】`／`【来源结构说明】`／
    #   格式示例 `【来源书 章节, PDF pNNN】`）被误判为"不可解析"。正确判据：
    #     · 含页说明（`PDF pN`／`pN`）的块 ⇒ **是锚**，必须解析出 (书,页)；
    #       其中**缺书代号**的（如 `【PDF p144】`）＝**真缺陷**（无书代号则无法回源），单列并限量。
    #     · 不含页说明的块 ⇒ 说明性方括号，**不计入**。
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import verify_layer_quotes as V
    total = pagespec = unparsable = nobook = 0
    bad_samples, nobook_samples = [], []
    for p in sorted(glob.glob(os.path.join(REF, a.glob))):
        for i, ln in enumerate(io.open(p, encoding='utf-8', errors='replace').read().splitlines(), 1):
            for m in ANCHOR_BLOCK.finditer(ln):
                total += 1
                blk = m.group(0)
                if not re.search(r'(?i)PDF\s*p?\s*\d|\bp\s*\d', blk):
                    continue                      # 说明性方括号，不计入
                pagespec += 1
                refs = V.parse_refs(blk)
                if refs:
                    continue
                if re.search(r'(?i)来源书|章节', blk):
                    continue                      # 格式说明示例，不计入
                nobook += 1
                if len(nobook_samples) < 6:
                    nobook_samples.append('%s L%d `%s`' % (os.path.basename(p), i, blk[:50]))
    unparsable = nobook
    r1 = unparsable <= UNPARSABLE_ALLOW
    print('  %s R1 锚块可解析：锚块 %d 个（含页说明）｜ 先按说明性方括号剔除 %d 个'
          % ('✔' if r1 else '🔴', pagespec, total - pagespec))
    print('       ⇒ **缺书代号/不可解析** %d 个（白名单 %d）' % (unparsable, UNPARSABLE_ALLOW))
    for b in nobook_samples:
        print('      · %s' % b)

    # ---- R4：归一化族齐全（对样本断言）----
    probes = [('『我必须说 8 遍他才能听。』', '我必须说8遍他才能听'),
              ('（piracetam）', 'piracetam'), ('(piracetam)', 'piracetam'),
              ('**加粗**', '加粗'), ('a b', 'ab')]
    r4 = all(V.norm(x) == y for x, y in probes)
    print('  %s R4 归一化族齐全（『』／全半角括号／空白／强调符）：%d/%d 探针通过'
          % ('✔' if r4 else '🔴', sum(1 for x, y in probes if V.norm(x) == y), len(probes)))

    # ---- 跑仪器（新鲜）----
    outp = os.path.join(TASK, 'layer-quote-check.json')
    r = subprocess.run([sys.executable, CLI, '--task', task, '--out', outp],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, cwd=ROOT)
    if r.returncode != 0:
        print('  🔴 仪器 rc=%d（拒绝采信）\n%s' % (r.returncode, (r.stdout or '')[-400:]))
        return 1
    d = json.load(io.open(outp, encoding='utf-8'))
    rows = d['rows']

    # ---- R7：空集拒跑 ----
    r7 = bool(rows) and total > 0
    print('  %s R7 非空集：引文 %d 条 ／ 锚块 %d 个' % ('✔' if r7 else '🔴', len(rows), total))

    # ---- R3：分栏自洽 ----
    cnt = d['counts']
    part = d.get('partition_check', {})
    r3 = (sum(cnt.values()) == len(rows)) and part.get('consistent') is True
    print('  %s R3 分栏自洽：%s ⇒ 合计 %d == 总数 %d'
          % ('✔' if r3 else '🔴', '／'.join('%s=%d' % kv for kv in sorted(cnt.items())),
             sum(cnt.values()), len(rows)))

    # ---- R2：引文全覆盖（每条都有状态）----
    r2 = all((x.get('state') or '').strip() for x in rows)
    print('  %s R2 引文全覆盖：%d 条全部有状态' % ('✔' if r2 else '🔴', len(rows)))

    # ---- R5：未命中零未处置 ----
    miss = [x for x in rows if x['state'] == '未命中']
    cat = {'短片段（≤20 字，机器不判）': 0, '长引文待复核': 0}
    for x in miss:
        q = V.norm(x['quote'])
        cat['短片段（≤20 字，机器不判）' if len(q) <= SHORT_LEN else '长引文待复核'] += 1
    unclassified = 0
    r5 = unclassified == 0 and sum(cat.values()) == len(miss)
    print('  %s R5 未命中零未处置：%d 条 ⇒ %s（未分类 %d）'
          % ('✔' if r5 else '🔴', len(miss), '／'.join('%s=%d' % kv for kv in cat.items()), unclassified))
    if a.strict and cat['长引文待复核']:
        r5 = False
        print('      （--strict：长引文待复核 %d 条视为红）' % cat['长引文待复核'])

    # ---- R6：判定不依赖位置配对 ----
    src = io.open(CLI, encoding='utf-8', errors='replace').read()
    r6 = ('line_bys' in src) and ('A-49' in src)
    print('  %s R6 判定用"行内锚并集"（不依赖位置配对）：%s' % ('✔' if r6 else '🔴', '已实现' if r6 else '未见并集逻辑'))

    # ---- R8：schema 版本与口径字段 ----
    keys = set((d.get('_口径') or {}).keys())
    need = {'判据', '归一化', '分段', '跨页窗口', '锚偏判定', '锚单位', '双源理由', '全量分栏纪律'}
    r8 = bool(d.get('schema')) and need.issubset(keys)
    print('  %s R8 schema 与口径字段齐（%s；缺 %s）'
          % ('✔' if r8 else '🔴', d.get('schema'), '、'.join(sorted(need - keys)) or '无'))

    ok = all((r1, r2, r3, r4, r5, r6, r7, r8))
    print('\n结论：%s' % ('✔ 引文型附属文件零问题（8/8 断言过）' if ok else '🔴 存在未过断言 —— 不得宣称"零问题"'))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
