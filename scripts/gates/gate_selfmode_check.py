# -*- coding: utf-8 -*-
r"""gate_selfmode_check.py —— 门禁工具「子模式退出码」自检（A-32 的脚本化落地）

为什么存在（A-32 实证，2026-09-13 ADHD 线阶段1.5）：
  `gate_stage.py --stage X` 的 docstring 承诺「退出码：0 = 该阶段可进入」，
  实现却 `return 0 if first_bad is None else 1`（取**全阶段**是否全过）
  ⇒ 明明打印「✔ 允许进入阶段1.5」却返回 rc=1。**拿它当闸用会误判为不可进入**。
  这类缺陷（**工具自述语义 ≠ 实际返回**）不会被任何"结果对不对"的检查抓到，
  只能靠"**打印与退出码一致性**"的独立断言抓。

本脚本的判据（唯一）：**stdout 的结论与进程退出码必须一致**——
  · 打印「✔ 允许进入…」 ⇒ rc 必须为 0
  · 打印「🔴 **不得进入…」/「🔴 未找到阶段」 ⇒ rc 必须为 1（非 0）

用法：
  python tools\gate_selfmode_check.py                 # 自动取 .work 下最近活跃任务
  python tools\gate_selfmode_check.py --task <slug>
退出码：0 = 全部一致；1 = 有不一致（列明）
"""
import argparse
import glob
import io
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
GATE = os.path.join(ROOT, "tools", "gate_stage.py")


def newest_task():
    cands = glob.glob(os.path.join(ROOT, ".work", "*", "PIPELINE_STATE.md"))
    if not cands:
        return None
    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return os.path.basename(os.path.dirname(cands[0]))


def run_stage(task, stage):
    p = subprocess.run([sys.executable, GATE, "--task", task, "--stage", stage],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def stage_names(task):
    """取全部阶段名（跑一次不带 --stage 的列表模式解析）。"""
    p = subprocess.run([sys.executable, GATE, "--task", task],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    out = (p.stdout or "") + (p.stderr or "")
    names = re.findall(r"^\s*[✔🔴]\s*阶段(\S+)", out, re.M)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=None)
    a = ap.parse_args()

    if not os.path.exists(GATE):
        print("⚠ gate_stage.py 不在 %s ⇒ 跳过（不视为通过，视为不适用）" % GATE)
        return 0

    task = a.task or newest_task()
    if not task:
        print("⚠ 未找到活跃任务（.work/*/PIPELINE_STATE.md）⇒ 跳过")
        return 0

    names = stage_names(task)
    print("=" * 72)
    print("gate_selfmode_check —— 子模式退出码自检（A-32）｜任务：%s" % task)
    print("  阶段名：%s" % "／".join(names))
    bad = []
    for n in names:
        # 传**序号片段**（`1.5-验证` → `1.5`）——`gate_stage` 的子模式匹配规则是
        # `名字.startswith(传入值 + "-")`；若传完整阶段名（`1.5-验证`），它会去找
        # `1.5-验证-…` 而匹配不到 ⇒ 全部落到"未找到阶段"分支，**测不到要测的路径**（首版实测踩到）。
        key = n.split("-")[0]
        rc, out = run_stage(task, key)
        allow = "允许进入" in out
        deny = ("不得进入" in out) or ("未找到阶段" in out)
        if allow and rc != 0:
            bad.append("%s：打印「允许进入」但 rc=%d ⇒ 言行不一（A-32）" % (n, rc))
        elif deny and rc == 0:
            bad.append("%s：打印「不得进入」但 rc=0 ⇒ 言行不一（A-32）" % n)
        elif not (allow or deny):
            bad.append("%s：结论行无法识别（既非允许也非拒绝）⇒ 判据不可用" % n)
        else:
            print("  ✔ %-22s rc=%d ｜ %s" % (n, rc, "允许" if allow else "拒绝"))
    print("-" * 72)
    if bad:
        for b in bad:
            print("  🔴 %s" % b)
        print("结论：🔴 %d 项不一致 —— 门禁工具的子模式退出码不可信" % len(bad))
        return 1
    print("结论：✔ 全部阶段子模式「打印 ↔ 退出码」一致")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
