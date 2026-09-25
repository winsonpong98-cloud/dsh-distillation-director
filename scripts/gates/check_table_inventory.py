# -*- coding: utf-8 -*-
r"""check_table_inventory.py —— **逐表清点闸**（表格专项 · 任务通用）

为什么要它（2026-09-20 能力审计发现的缺口）：
  能力审计结论：涉表的三个既有脚本（`table_to_blocks.py` 格式修复／`check_md_tables.py` 行列一致性／
  `check_r5_table.py` 引文锚表对账）**全是"格式与对账"闸，没有一件做"逐表清点"**——
  即"源文有几张表、每张表有没有进来"，此前**无从回答**。

判据（三层对账，全部确定性，不做语义价值判断）：
  ① **源文表号**：正则提取表号（默认 `表 N.M` 点号式；可用 `--tref-regex` 换形态，**不写死某本书的编号法**）；
  ② **源文管道表块**：连续 `^\|` 行构成一个块；块数与其所在页一并列出（视觉 OCR 通常把表格转成管道表）；
  ③ **落点核对**：每个表号在 ①候选池（`<work>\verified.md`）②技能根各件 `*.md` 里是否出现。

判态：
  · `PASS` 源文无表号引用 ⇒ 本闸对本册不适用（打印理由，不假装通过）；
  · `PASS` 表号在池内命中；
  · `▲` 表号仅在技能命中、池内未命中；
  · `🔴` 池内与技能内**都未命中**（该表既没进取料池、也没进交付件 ⇒ 实质缺表）。

用法：
  python tools\check_table_inventory.py --task <slug> --out <报告.md> [--skills-root <路径>] [--tref-regex <正则>]
退出码：0 = 跑通且无 🔴；1 = 缺件／解析失败／**存在 🔴 缺表**
"""
import argparse
import glob
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from _paths import ROOT                      # noqa: E402
import verify_candidates as VC               # noqa: E402

# 默认表号形态：`表 13.1` / `表13-1` / `表 6—1`（点号/连字符/破折号等价类）
# ⚠ 形态必须可配置（A-29 家族：格式类判据先做形态普查，不猜）
DEFAULT_TREF = r'表\s*(\d{1,2})\s*[.\-–—]\s*(\d{1,2})'


def pipe_blocks(text):
    """连续 `^\\|` 行构成一个管道表块；返回块数（用于形态守恒对账）。"""
    n, prev = 0, False
    for ln in text.splitlines():
        cur = bool(re.match(r'^\|', ln.strip()))
        if cur and not prev:
            n += 1
        prev = cur
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--src', default=None)
    ap.add_argument('--pool', default=None)
    ap.add_argument('--skills-root', default=None, dest='skills_root')
    ap.add_argument('--tref-regex', default=DEFAULT_TREF, dest='tref')
    ap.add_argument('--datapack-dir', default=None, dest='datapack',
                    help='表格数据件根目录（含 <task>\\表<id>.md）；给了则"数据件在位"即判 PASS')
    a = ap.parse_args()

    work = os.path.join(ROOT, '.work', a.task)
    if not os.path.isdir(work):
        print('🔴 缺任务目录：%s' % work); return 1
    VC.WORK = work
    src, why = VC._bookspec_src(a.task, a.src)
    if not src or not os.path.exists(src):
        print('🔴 源文决议失败：%s %s' % (src, why)); return 1
    pool_path = a.pool or os.path.join(work, 'verified.md')
    if not os.path.exists(pool_path):
        print('🔴 缺候选池：%s' % pool_path); return 1

    VC.set_pagemark(VC.detect_pagemark(src))
    src_txt = io.open(src, encoding='utf-8', errors='replace').read()
    pool_txt = io.open(pool_path, encoding='utf-8', errors='replace').read()

    # 技能根：默认取宿主（由 --skills-root 覆盖；不写死册别根）
    skills_root = a.skills_root
    skill_files = []
    if skills_root and os.path.isdir(skills_root):
        for d in sorted(os.listdir(skills_root)):
            p = os.path.join(skills_root, d)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, 'SKILL.md')):
                skill_files += sorted(glob.glob(os.path.join(p, '*.md')))
    skill_txt = '\n'.join(io.open(f, encoding='utf-8', errors='replace').read() for f in skill_files)

    tref = re.compile(a.tref)
    hits = tref.finditer(src_txt)
    refs = {}
    for m in hits:
        key = '%s.%s' % (m.group(1), m.group(2))
        refs.setdefault(key, 0)
        refs[key] += 1

    n_src_blocks = pipe_blocks(src_txt)
    n_pool_blocks = pipe_blocks(pool_txt)
    n_skill_blocks = pipe_blocks(skill_txt)

    # 管道表块 → 页
    segs = VC.PAGEMARK_ANY.split(src_txt)
    ids = [int(x) for x in VC.PAGEMARK_ANY_MARK.findall(src_txt)]
    block_pages = []
    for i, pid in enumerate(ids):
        body = segs[i + 1] if i + 1 < len(segs) else ''
        if re.search(r'(?m)^\|', body):
            block_pages.append(pid)

    rows, n_red, n_amber = [], 0, 0
    # 🔴 整体级告警（2026-09-21 依"表格密集书实测"新增 · 见 附加观察 O-41）：
    #   源文**有表号引用**但**管道表块为 0** ⇒ 表格**结构整体缺失**（实测某册文字版直抽：
    #   31 个表标题行里 26 个表体全无）。此时逐表 🔴 只是症状，**根因在主文本抽取方式**
    #   （文字版 `pdf_to_text.py` 直抽不重建表格；扫描版走视觉 OCR 才会产出管道表）。
    # ⚠ 2026-09-21 二次修正（O-45）：**数据件已补齐时不得再报 🔴**——
    #   否则"补抽流水线跑完"与"表格仍缺失"在闸上**读数相同**，闸就永远红着、失去分辨力
    #   （正是本项目 A-36 家族"假通过/假告警"的反面）。故：结构缺失 ∧ 数据件齐全 ⇒ 降级为 ℹ️ 并 rc=0。
    all_pack = bool(a.datapack) and all(
        os.path.exists(os.path.join(a.datapack, a.task, '表%s.md' % k)) for k in refs) if refs else False
    structural_loss = (len(refs) > 0 and n_src_blocks == 0 and not all_pack)
    if structural_loss:
        n_red += 1
    elif len(refs) > 0 and n_src_blocks == 0 and all_pack:
        n_info_pack = len(refs)
    else:
        n_info_pack = 0
    for key in sorted(refs, key=lambda k: (int(k.split('.')[0]), int(k.split('.')[1]))):
        # ⚠ 收紧（2026-09-20 自伤登记 · 首跑即假通过）：**变体一律「表」字锚定**。
        #   初版把裸 `6.1` 也当变体 ⇒ 会撞上池里任意数字（如 "6.1%"）⇒ 三张表全报 PASS，
        #   其中一张（表 6.1）实测在池内其实**不存在**。假通过比漏报更坏（A-36…A-39 家族）。
        variants = ['表' + key, '表 ' + key,
                    '表' + key.replace('.', '-'), '表 ' + key.replace('.', '-')]
        in_pool = any(v in pool_txt for v in variants)
        in_skill = any(v in skill_txt for v in variants)
        in_pack = False
        if a.datapack:
            in_pack = os.path.exists(os.path.join(a.datapack, a.task, '表%s.md' % key))
        if in_pack:
            verdict = 'PASS（数据件在位）'
        elif in_pool:
            verdict = 'PASS'
        elif in_skill:
            verdict = '▲ 仅技能命中'
            n_amber += 1
        else:
            verdict = '🔴 池内与技能内都未命中'
            n_red += 1
        rows.append((key, refs[key], '✔' if in_pack else '—', verdict))

    L = ['# 逐表清点闸 · %s' % a.task, '',
         '> 工装：`tools\\check_table_inventory.py`（任务通用；表号形态可配置：`%s`）' % a.tref,
         '> 源文：`%s`（%s）｜ 候选池：`%s`' % (os.path.basename(src), why, os.path.basename(pool_path)),
         '> 技能根：%s（%d 个 md 文件）' % (skills_root or '（未给 --skills-root）', len(skill_files)), '',
         '## 一、表格形态（确定性计数）', '',
         '| 项 | 值 |', '|---|---|',
         '| 源文表号引用（去重） | **%d** 个 |' % len(refs),
         '| 表号引用总命中 | %d 处 |' % len(list(tref.finditer(src_txt))),
         '| 源文 markdown 管道表块数 | **%d** |' % n_src_blocks,
         '| 含管道表的页 | %s |' % ((' '.join('s%d' % p for p in block_pages)) or '无'),
         '| 候选池管道表块数 | %d |' % n_pool_blocks,
         '| 技能根管道表块数 | %d |' % n_skill_blocks, '']
    if structural_loss:
        L += ['> 🔴 **整体级告警：表格结构整体缺失** —— 源文**有 %d 个表号引用**但**管道表块为 0**。' % len(refs),
              '> 逐表 🔴 只是**症状**，**根因在主文本抽取方式**：文字版 PDF 经 `pdf_to_text.py` 直抽**不重建表格**',
              '> （实测某册：31 个表标题行里 **26 个表体全无**，只剩标题／注／资料来源行）；',
              '> 扫描版走视觉 OCR（`ocr_deepseek_vision.py`）**才会产出管道表**。',
              '> **修法**：含表号的页走**视觉补抽** → 重建表体 → 交 `extract_table_datapack.py` 生成数据件。', '']
    if n_info_pack:
        L += ['> ℹ️ **源文管道表块为 0，但数据件已补齐 %d/%d** —— 表格**已以数据件形式交付**（表体由页图视觉转写，'
              '见 `tools\\render_pdf_pages.py` → `map_table_images.py` → `ocr_deepseek_vision.py --kind table` → '
              '`assemble_table_bodies.py` 一条流水线），故**不再计为结构缺失**。' % (n_info_pack, len(refs)),
              '> ⚠ **源头局限仍在**：该册正文本仍**不含**表体（文字版直抽不重建表格）⇒ '
              '**换新书必须重跑同一条补抽流水线**，不得假定"文字版免 OCR"。', '']
    L += ['## 二、逐表对账', '',
         '| 表号 | 源文引用次数 | 数据件在位 | 判态 |', '|---|---|---|---|']
    for r in rows:
        L.append('| 表 %s | %d | %s | **%s** |' % r)
    if not rows:
        L += ['| （无） | — | **PASS（本册无表号引用 ⇒ 本闸不适用）** |']
    L += ['', '## 三、计数', '',
          '表号 **%d** 个 ｜ PASS **%d** ／ ▲ 仅技能 **%d** ／ 🔴 都未命中 **%d**' % (
              len(refs), len(refs) - n_amber - n_red, n_amber, n_red), '',
          '## 四、边界声明（必须与结果一起读）', '',
          '1. 本闸判的是"**表号有没有被引用到**"，**不是**"表格数值有没有被逐格搬进技能"。'
          '表格数值属**数据层**，技能属**判断层**——把整张表塞进技能不是目标；目标是"表格作为可回查的数据件随册交付 ＋ 转录完整"。',
          '2. 管道表块数是**形态计数**，不等于"表格张数"（一张大表可能被拆成多块，或表内空行导致断开）。',
          '3. 表号形态因书而异（本册为点号式）；换书须先做形态普查（`--tref-regex` 覆盖），**不许凭推断**。',
          '4. 技能内命中只说明"表号或表意被引用"，不说明数值可核。', '']

    out = '\n'.join(L)
    io.open(a.out, 'w', encoding='utf-8').write(out + '\n')
    print(out)
    print('→ 已写入 %s' % a.out)
    return 1 if n_red else 0


if __name__ == '__main__':
    sys.exit(main())
