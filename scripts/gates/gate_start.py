# -*- coding: utf-8 -*-
r"""gate_start.py —— 开工强制自检闸（针对"用摘要代替手册 / 自造模板 / 不跑机器层"三类偷懒）

判据全部机械化，不依赖 AI 自觉：
  闸1 手册哈希闸：read_receipt.json 记的 manual_sha256 必须等于当前权威手册 SKILL.md 的 sha256
        ⇒ 手册改版后旧收据立刻失效，必须重读并重抄条款
  闸2 条款抄录闸：收据里抄录的关键条款 ≥ {MIN_CLAUSES} 条，且每条都能在手册里【逐字】找到
        ⇒ "我读过了"不算数，抄不出原文就等于没读
  闸3 执行单闸：.work/<task>/执行单.md 必须存在，且含"阶段"字样与至少 {MIN_STAGES} 个阶段标题
  闸4 机器层闸：.work/<task>/machine-layer-run.json 必须存在（含脚本名/退出码/时刻）
        ⇒ ¥0 机器层没跑过，不许开工
  闸5 模板闸（条件触发）：若存在 extractor-prompts/，每个 prompt 必须含官方模板的格式行
        ⇒ 自造提取器格式会被当场拦下

用法: python tools\gate_start.py --task <task> [--quiet]
退出码: 0 = 可开工；1 = 有闸未过（不得开工）
"""
import argparse, hashlib, json, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 工作区常量：由 `gate_common` 从 .dsh\gate-kit\workspace.json 读取（A-81 通用化）──
#   一次性配置：`python gate_bootstrap.py --workspace "<工作区>" [--host name=路径]`
#   之后本脚本**零参数**可用；缺项由 `cfg` 返回 None ⇒ 调用方判"不适用"（**不假红**）。
import os as _os_, sys as _sys_
_HERE = _os_.path.dirname(_os_.path.abspath(__file__))
for _c in (_HERE,
           _os_.path.join(_os_.path.dirname(_HERE), 'distillation-director-plugin', 'scripts', 'gates')):
    if _c not in _sys_.path:
        _sys_.path.insert(0, _c)
from gate_common import cfg as _cfg
ROOT = _cfg.root
TOOLS = _cfg.tools
# ⚠ 三个"工作目录"必须分开（本节自伤登记 · 实测抓出）：
#   `WORK`      = **配套脚本目录**（`yaml_check_generic.cjs`／`check_md_tables.py`／`machine_scan_*.py` 等所在）
#                 ——旧常量 `WORK = <root>\.work\<配套脚本目录>` 指的就是它；首版被我换成 cfg.work ⇒
#                 `subprocess ... cwd=WORK` 指向新目录 ⇒ `NotADirectoryError`（该目录下没有那些 .cjs）。
#   `GATE_WORK` = **门禁自己的产物目录**（基线／沙箱／临时 json）——来自 `cfg.work`
#   `MACH`      = **机器层权威脚本目录**——来自 `cfg.mach`
WORK = _cfg.scripts_dir or _os_.path.join(ROOT, '.work', 'gate-kit', 'scripts')
GATE_WORK = _cfg.work
MACH = _cfg.mach
# ⚠ 两个"手册"必须分开（本节自伤登记 · 实测抓出）：
#   `MANUAL`   = **技能手册 SKILL.md**（开工收据比对的哈希对象；`gate_start` 用它）
#   `PITFALL_MANUAL` = **《避坑手册》**（`pitfall_audit` 对账对象）——它来自 `cfg.manual`
#   首版把两者统一成 `cfg.manual` ⇒ `gate_start` 拿《避坑手册》去比收据哈希 ⇒
#   `🔴 闸1 收据=59d3… 当前=03a3…（手册已改版）` **假红**（同名不同物，A-04 家族）。
MANUAL = _os_.path.join(ROOT, '.dsh', 'skills', 'distillation-director', 'SKILL.md')
PITFALL_MANUAL = _cfg.manual
NODE_EXE = _cfg.node
JS_YAML_DIR = _cfg.jsdir
BASELINE = _os_.path.join(TOOLS, '_mtime_baseline.json')
_WS_PARENT = _os_.path.dirname(ROOT)
FIN_DIR = _cfg.host('fin') or _os_.path.join(_WS_PARENT, '金融投资')
EDU_DIR = _cfg.host('edu') or _os_.path.join(_WS_PARENT, '家庭教育')
MAIN_DIR = _cfg.host('main') or _cfg.host('fin') or _WS_PARENT
MACH_TOOL = _os_.path.join(MACH, 'machine_precheck_v2.py') if MACH else None
MBASE = _os_.path.join(TOOLS, '_machine_baseline.json')
SANDBOX = _os_.path.join(TOOLS, '_selftest')
FIN = FIN_DIR
EDU = EDU_DIR
MAIN = MAIN_DIR
NODE = NODE_EXE
JSDIR = JS_YAML_DIR
MIN_CLAUSES = 12
MIN_STAGES = 6
# 官方提取器模板的格式行特征（自造格式必缺其一）
TEMPLATE_MARKERS = ["### ", "- 锚：", "- 原文（逐字）：", "- 转述：", "[类型]", "[技能="]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""):
            h.update(b)
    return h.hexdigest()


def norm(s):
    return re.sub(r"\s+", "", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="任务 slug，如 <task>")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    work = os.path.join(ROOT, ".work", a.task)
    receipt_p = os.path.join(work, "read_receipt.json")
    manual = open(MANUAL, encoding="utf-8").read()
    nmanual = norm(manual)
    manual_hash = sha256(MANUAL)

    rows = []

    # ---- 闸1 + 闸2：手册读取自证 ----
    if not os.path.exists(receipt_p):
        rows.append(("🔴", "闸1 手册哈希", "read_receipt.json 不存在 ⇒ 未自证读过权威手册"))
        rows.append(("🔴", "闸2 条款抄录", "同上"))
    else:
        try:
            rc = json.load(open(receipt_p, encoding="utf-8"))
        except Exception as e:
            rc = None
            rows.append(("🔴", "闸1 手册哈希", "read_receipt.json 解析失败：%s" % e))
        if rc:
            got = rc.get("manual_sha256", "")
            if got == manual_hash:
                rows.append(("✔", "闸1 手册哈希", "收据哈希 == 当前手册哈希（%s…）" % manual_hash[:12]))
            else:
                rows.append(("🔴", "闸1 手册哈希",
                             "收据=%s… 当前=%s… ⇒ 手册已改版，须重读重抄" % (got[:12], manual_hash[:12])))
            clauses = rc.get("clauses", [])
            bad = [c for c in clauses if norm(c) not in nmanual]
            if len(clauses) >= MIN_CLAUSES and not bad:
                rows.append(("✔", "闸2 条款抄录", "%d 条逐字命中手册（要求 ≥%d）" % (len(clauses), MIN_CLAUSES)))
            else:
                msg = "%d 条（要求 ≥%d）" % (len(clauses), MIN_CLAUSES)
                if bad:
                    msg += "；%d 条在手册中找不到：%s" % (len(bad), " ｜ ".join(x[:28] for x in bad[:3]))
                rows.append(("🔴", "闸2 条款抄录", msg))

    # ---- 闸3：执行单（判据对齐官方模板：36 项表格 + 例外登记节）----
    exe = os.path.join(work, "执行单.md")
    if os.path.exists(exe):
        t = open(exe, encoding="utf-8").read()
        rows_cnt = len([l for l in t.splitlines() if re.match(r"^\|\s*\d+\s*\|", l)])
        has_exc = "例外登记" in t
        if rows_cnt >= 30 and has_exc:
            rows.append(("✔", "闸3 执行单", "官方模板形态：%d 个编号执行项 ＋ 例外登记节" % rows_cnt))
        else:
            rows.append(("🔴", "闸3 执行单",
                         "形态不符：编号执行项 %d（要求 ≥30）、例外登记节 %s" % (rows_cnt, "有" if has_exc else "缺")))
    else:
        rows.append(("🔴", "闸3 执行单", "执行单.md 不存在 ⇒ 违反 V3.1 纪律1"))

    # ---- 闸4：机器层已跑 ----
    ml = os.path.join(work, "machine-layer-run.json")
    if os.path.exists(ml):
        try:
            d = json.load(open(ml, encoding="utf-8"))
            runs = d.get("runs", [])
            if runs:
                rows.append(("✔", "闸4 机器层", "%d 个脚本已跑（最近：%s）" % (len(runs), runs[-1].get("script", "?"))))
            else:
                rows.append(("🔴", "闸4 机器层", "记录存在但 runs 为空"))
        except Exception as e:
            rows.append(("🔴", "闸4 机器层", "解析失败：%s" % e))
    else:
        rows.append(("🔴", "闸4 机器层", "machine-layer-run.json 不存在 ⇒ ¥0 机器层未跑"))

    # ---- 闸5：提取器提示词是否来自官方模板（条件触发）----
    pd = os.path.join(work, "extractor-prompts")
    if os.path.isdir(pd):
        files = [f for f in os.listdir(pd) if f.endswith(".txt") or f.endswith(".md")]
        badf = []
        for f in files:
            t = open(os.path.join(pd, f), encoding="utf-8").read()
            if not all(m in t for m in TEMPLATE_MARKERS):
                badf.append(f)
        if files and not badf:
            rows.append(("✔", "闸5 提取器模板", "%d 个 prompt 全部含官方模板格式行" % len(files)))
        else:
            rows.append(("🔴", "闸5 提取器模板",
                         "未用官方模板（缺格式行）：%s" % (" ｜ ".join(badf[:4]) if badf else "目录为空")))
    else:
        rows.append(("▲", "闸5 提取器模板", "无 extractor-prompts/ 目录（若本任务含提取阶段，则此项应为 🔴）"))

    nred = sum(1 for s, _, _ in rows if s == "🔴")
    if not a.quiet:
        print("=" * 78)
        print("gate_start —— 开工强制自检闸（任务：%s）" % a.task)
        print("=" * 78)
        for s, name, msg in rows:
            print("  %s %-14s %s" % (s, name, msg))
        print("-" * 78)
        print("结论：%s（🔴 %d 项）" % ("✔ 可开工" if nred == 0 else "🔴 不得开工——先补齐上述红项", nred))
    return 1 if nred else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
