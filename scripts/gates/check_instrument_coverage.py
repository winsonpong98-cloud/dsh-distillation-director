# -*- coding: utf-8 -*-
r"""check_instrument_coverage.py —— **引文面仪器覆盖对账闸**（通用 · 只读 · 毫秒级）

## 为什么需要它（2026-09-17 · 教育线迁移 A/B 实测后的结论）
A/B 实测（通用闸 vs 教育线专用闸）**可对齐键交集仅 145／1460**：
  · 通用闸 1339 键 ｜ 专用闸 962 键 ｜ 只在专用闸里的引文 **722 条**（其中 712 条它判"逐字命中"）
⇒ 两把尺子的**射程与切分规则根本不同**（它按"每条 R 段引文"切，通用闸按段落里的「…」切），
  **不是"缺三模式匹配"**。要对齐＝把专用闸重写一遍，且复刻不精确就会产出假红/假绿。

⇒ 正解不是"合并"，而是**把并存变成受管结构**：
  **凡有引文面的册，必须满足二者之一**——
    ⒜ 通用闸覆盖：`.work/<task>/layer-quotes-<task>.json` 里 `gate_ready=true`（由 postflight ⑧-c 跑）；
    ⒝ 专用闸覆盖：`gate_ready=false` ＋ **声明在役仪器** `incumbent_gate` ＋ **声明其门禁座位**
       `incumbent_gate_seat`（该座位字符串**必须真的存在于 postflight.py 里**，否则＝纸面覆盖）。

## 判据（逐条可核）
  1. 有引文面的任务＝`.work/<task>/skills/**/*.md` 中存在 `【…PDF p…】` 或 `（`ID` sNN）` 形态的引文面；
  2. 该任务必须有 `layer-quotes-<task>.json`（无 ⇒ 🔴 未声明覆盖方式）；
  3. `gate_ready=true` ⇒ ✔（通用闸座位）；`false` ⇒ `incumbent_gate` 与 `incumbent_gate_seat` 均非空
     且 **seat 字符串出现在 postflight.py 源码里**（防止"声明了却没人跑"）；
  4. 空集不算通过：一个任务都扫不到 ⇒ 打印"不适用"并说明（不静默 rc=0 放行数据缺失）。

用法：python tools\check_instrument_coverage.py
退出码：0 = 覆盖完整；1 = 有缺口（逐条列出）
"""
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
# ── 可移植根目录解析（**插件在别人电脑上必须能跑**）─────────────────────────────
# 优先级：① 环境变量 DSH_DISTILL_ROOT ／ DSH_WORKSPACE_ROOT
#         ② `gate_common.cfg`（它自己按 DSH_GATE_CONFIG → 从脚本位置上溯找
#            `<root>\.dsh\gate-kit\workspace.json` → 由配置位置反推）
#         ③ 从本文件位置逐级上溯找 `.dsh`
#         ④ **明确失败并打印可执行指引**（不静默用错路径 —— A-78/A-101 家族）
def _resolve_root():
    for k in ('DSH_DISTILL_ROOT', 'DSH_WORKSPACE_ROOT'):
        v = (os.environ.get(k) or '').strip()
        if v and os.path.isdir(v):
            return v
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from gate_common import cfg as _gc
        if _gc.root and os.path.isdir(_gc.root):
            return _gc.root
    except Exception:
        pass
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, '.dsh')):
            return d
        d = os.path.dirname(d)
    sys.exit('🔴 未找到蒸馏工作区根目录 —— 请任选其一：\n'
             '   ① 设环境变量 DSH_DISTILL_ROOT=<你的工作区根>\n'
             '   ② 写 <工作区>/.dsh/gate-kit/workspace.json 的 workspace_root\n'
             '   ③ 用 DSH_GATE_CONFIG 指向该配置文件')
ROOT = _resolve_root()
POST = os.path.join(ROOT, 'tools', 'postflight.py')
FACE = re.compile(r'【[^】]{0,120}PDF\s*[pP]|（`[A-Za-z]+-\d{3}`\s*s\d')


def has_quote_face(task_dir):
    for f in glob.glob(os.path.join(task_dir, 'skills', '**', '*.md'), recursive=True):
        if os.path.basename(f) == 'SKILL.md':
            continue
        try:
            if FACE.search(io.open(f, encoding='utf-8', errors='replace').read()):
                return True, os.path.relpath(f, ROOT)
        except Exception:
            continue
    return False, ''


def main():
    post_src = io.open(POST, encoding='utf-8', errors='replace').read()
    rows, gaps, n_face = [], [], 0
    for d in sorted(glob.glob(os.path.join(ROOT, '.work', '*'))):
        task = os.path.basename(d)
        if task.startswith('_'):
            continue
        ok, ev = has_quote_face(d)
        if not ok:
            continue
        n_face += 1
        cfg_p = os.path.join(d, 'layer-quotes-%s.json' % task)
        if not os.path.isfile(cfg_p):
            gaps.append((task, '缺 layer-quotes-%s.json（未声明覆盖方式）' % task))
            rows.append((task, '（无配置）', '🔴', '未声明'))
            continue
        cfg = json.load(io.open(cfg_p, encoding='utf-8'))
        if cfg.get('gate_ready'):
            rows.append((task, '通用闸（layer_quotes_gate）', '✔', 'postflight ⑧-c'))
            continue
        inc, seat = cfg.get('incumbent_gate'), cfg.get('incumbent_gate_seat')
        if not inc or not seat:
            gaps.append((task, 'gate_ready=false 但未声明 incumbent_gate／incumbent_gate_seat'))
            rows.append((task, inc or '（未声明）', '🔴', '缺声明'))
            continue
        if seat not in post_src:
            gaps.append((task, '声明了座位「%s」但 postflight.py 里找不到 ⇒ 纸面覆盖' % seat))
            rows.append((task, inc[:44], '🔴', '座位不存在'))
            continue
        rows.append((task, inc[:44], '✔', seat))
    print('=' * 96)
    print('引文面仪器覆盖对账 ｜ 有引文面的任务 %d ｜ 缺口 %d' % (n_face, len(gaps)))
    for t, inc, mark, seat in rows:
        print('  %s %-16s %-46s %s' % (mark, t, inc, seat))
    for t, why in gaps:
        print('  🔴 %-16s %s' % (t, why))
    if n_face == 0:
        print('  ⚠ 不适用：一个"有引文面"的任务都没扫到 —— 请先确认判据（不静默放行数据缺失）')
    print('结论：%s' % ('✔ 覆盖完整（每册要么通用闸过、要么有在门禁里有座位的专用闸）' if not gaps
                     else '🔴 %d 册无受管覆盖' % len(gaps)))
    return 1 if gaps else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
