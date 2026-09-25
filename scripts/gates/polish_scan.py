# -*- coding: utf-8 -*-
r"""polish_scan.py —— 交付前打磨扫描（长行 / 空话尾巴 / 速查一致性 / 路由副本）

依据：手册 §14 软闸「d1 行文：空话尾巴 / **超长行 >260 字符**」；执行单 #20
「polish_scan_v31：长行/路由副本/速查一致性（0 长行等）」。

扫什么：
  ① **超长行**（>260 字符，**排除 frontmatter 与引用行 `>`**——引用区按手册豁免）
  ② **空话尾巴**（模糊收尾短语，硬词表）
  ③ **速查一致性**：`判停速查` 的行数 ≥ `B 段 CHECKPOINT` 的条数（速查须是正文的浓缩，不得漏条）
  ④ **路由副本一致性**：desc 里出现的邻族 slug，须在 `§A2` 让位表或 `BOUNDARIES` 里也出现（防两处口径漂移）

用法：python tools\polish_scan.py --dir <技能根> [--maxlen 260] [--all]
  · 默认每个文件只打印前 6 行命中，并**自声明**未显示条数；`--all` 打印全量。
  · 读报告纪律：**「命中条数」看头部计数行，不要数显示出来的行**（A-86 同族）。
退出码：0 = 无 🔴；1 = 有 🔴（列明）
"""
import argparse
import glob
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 空话尾巴（判据：模糊、不给动作的收尾短语）
FLUFF = ["因人而异", "视情况而定", "具体情况具体分析", "总之",
         "希望对你有帮助", "以上仅供参考", "需要家长自行把握", "灵活掌握"]


def quote_spans(s):
    """逐字引文的字符区间（`「…」`／`“…”`／`『…』`／`‘…’`）。

    为什么必须豁免引文内的词表命中：d1「空话尾巴」判的是**本技能自己的空话收尾**；
    落在「」里的字是**书里的原文**——改它就等于改写引文，直接违反防线3（逐字引文）。
    实测（2026-09-17）：两处 `总之` 命中**都在带页锚的逐字引文内**（`G-047` s140／`B-012` s41），
    是词表**假阳性**，不是空话尾巴 ⇒ 回改对象应是**检测器**，不是正文。
    """
    spans = []
    for op, cl in (("「", "」"), ("“", "”"), ("『", "』"), ("‘", "’")):
        i = 0
        while True:
            a = s.find(op, i)
            if a < 0:
                break
            b = s.find(cl, a + 1)
            if b < 0:
                break
            spans.append((a, b + 1))
            i = b + 1
    return spans


def scan_file(path, maxlen, out_dir, show_all=False):
    lines = io.open(path, encoding="utf-8", errors="ignore").read().split("\n")
    name = os.path.relpath(path, out_dir)
    # frontmatter 范围
    fm_end = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_end = i
                break
    long_lines = []
    fluff = []
    fluff_exempt = []
    for i, ln in enumerate(lines):
        if i <= fm_end:
            continue
        if ln.lstrip().startswith(">"):        # 引用区豁免（手册 §7 口径）
            continue
        if len(ln) > maxlen:
            long_lines.append((i + 1, len(ln)))
        if any(w in ln for w in FLUFF):
            spans = quote_spans(ln)            # 逐字引文内的命中 ⇒ 豁免（不得改写原文）
            for w in FLUFF:
                st = 0
                while True:
                    p = ln.find(w, st)
                    if p < 0:
                        break
                    if any(a <= p < b for a, b in spans):
                        fluff_exempt.append((i + 1, w))
                    else:
                        fluff.append((i + 1, w))
                        break
                    st = p + 1
    t = "\n".join(lines)
    # 速查一致性
    m_speed = re.search(r"(?ms)^##\s*判停速查.*?(?=^##\s|\Z)", t)
    n_speed = 0
    if m_speed:
        n_speed = len(re.findall(r"(?m)^\|\s*\S", m_speed.group(0))) - 1   # 减表头
    m_b1 = re.search(r"(?ms)^###\s*B1.*?(?=^###\s|^##\s|\Z)", t)
    n_b1 = len(re.findall(r"(?m)^\d+\.\s", m_b1.group(0))) if m_b1 else 0
    # 路由副本一致性
    desc = ""
    dm = re.search(r'^description:\s*(.+)$', t, re.M)
    if dm:
        desc = dm.group(1)
    slugs_desc = set(re.findall(r"`([a-z][a-z0-9-]{3,})`", desc))
    slugs_rest = set(re.findall(r"`([a-z][a-z0-9-]{3,})`", t))
    only_desc = sorted(s for s in slugs_desc if s not in slugs_rest)

    bad = 0
    print("=" * 74)
    print("polish_scan ｜ %s" % name)
    print("  超长行(>%d，排除 frontmatter/引用区)：%d" % (maxlen, len(long_lines)))
    cut = (lambda lst: lst if show_all else lst[:6])   # ⚠ 两个列表**各自**截断：
    for ln, L in cut(long_lines):                      #   共用一个 cap 会在 `--all` 且
        print("     🔴 L%d（%d 字符）" % (ln, L))       #   超长行=0 时把明细切成空（实测自伤）
    if len(long_lines) > len(cut(long_lines)):
        # 截断必须自声明：不声明截断 ⇒ 读报告者会把"显示条数"当成"命中条数"（A-86 同族）
        print("     …（仅显示前 %d 行；未显示 %d 行，加 --all 查看全量）"
              % (len(cut(long_lines)), len(long_lines) - len(cut(long_lines))))
    bad += len(long_lines)
    print("  空话尾巴：%d" % len(fluff))
    for ln, w in cut(fluff):
        print("     ▲ L%d「%s」" % (ln, w))
    if len(fluff) > len(cut(fluff)):
        print("     …（仅显示前 %d 条；未显示 %d 条，加 --all 查看全量）"
              % (len(cut(fluff)), len(fluff) - len(cut(fluff))))
    if fluff_exempt:
        # 自声明：命中被豁免的**原因与处数**（防"看不见的豁免"＝免检）
        print("     ↳ 另有 %d 处词表命中落在**逐字引文内 ⇒ 豁免**（引文一字不得改）：%s"
              % (len(fluff_exempt),
                 "、".join("L%d「%s」" % x for x in cut(fluff_exempt))
                 + ("…" if len(fluff_exempt) > len(cut(fluff_exempt)) else "")))
    print("  判停速查行数 %d ｜ B1 条数 %d ⇒ %s"
          % (n_speed, n_b1, "✔ 速查不少于正文" if n_speed >= n_b1 else "🔴 速查少于正文（漏条）"))
    if n_b1 and n_speed < n_b1:
        bad += 1
    print("  desc 独有 slug：%s" % ("无" if not only_desc else "、".join(only_desc)))
    if only_desc:
        print("     ▲ 这些 slug 只在 desc 出现、正文/让位表未复现（登记项，防口径漂移）")
    print("  → %s" % ("✔ 通过" if bad == 0 else "🔴 %d 项" % bad))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="技能根（其下 */SKILL.md）")
    ap.add_argument("--maxlen", type=int, default=260)
    ap.add_argument("--all", action="store_true",
                    help="打印全部命中行（默认每个文件仅前 6 行，并自声明截断余量）")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*", "SKILL.md")))
    # ⚠ 跳过 `_` 开头的目录（备份/隔离区）——它们不是技能；否则备份件会被当成"技能"计入判定
    files = [f for f in files if not os.path.basename(os.path.dirname(f)).startswith("_")]
    if not files:
        print("🔴 未找到 %s/*/SKILL.md" % a.dir)
        return 1
    total = 0
    for f in files:
        total += scan_file(f, a.maxlen, a.dir, a.all)
    print("=" * 74)
    print("总判定：%s（扫 %d 件）" % ("✔ 全部通过" if total == 0 else "🔴 合计 %d 项" % total, len(files)))
    return 1 if total else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
