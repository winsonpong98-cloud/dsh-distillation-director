# -*- coding: utf-8 -*-
r"""split_long_lines.py —— 超长行回改器（**只插换行＋对齐缩进，一个字都不改**）

依据：手册 §14 软闸 d1「超长行 > 260 字符」（`tools\polish_scan.py` 的 ① ）。

做法：在**安全断点**处插入换行，续行按列表项标记宽度缩进（markdown lazy continuation，
      仍属同一列表项 / 同一段落）。

原子不拆（拆了会让下游检查器看不见）：
  · `` `inline code` ``、`（\`ID\` sNN）` **含引文 id 的括号组**、`「…」`/`“…”`/`『…』` 逐字引文
  · 表格行 `|…|`、frontmatter、引用行 `>`、逐字引文载体行 `- 「…」` —— 一律 SKIP（另案处置）

**核心安全断言（逐处自证，不靠自觉）**：
      re.sub(r'\s+', '', 新文本) == re.sub(r'\s+', '', 旧文本)
  ⇒ 改动是**空白字符级**的 ⇒ 逐字引文、页锚 id、检索键（候选池 id／slug／数字）
    全部逐字节不变。

依据（为何插换行安全）：逐字引文回源器 `verify_candidates.py` / `rquote_page_check.py`
  比对一律走 `norm()`＝`re.sub(r"\s+","",s)`（`verify_candidates.py` L98、L126）
  ⇒ 换行对二者**不可见**（本工具落地后仍须跑真闸复核，见 §回改后必跑）。

用法：
  python tools\split_long_lines.py --dir <技能根> [--maxlen 260] [--dry-run] [--report <out>]
退出码：0 = 全部行已 ≤ maxlen；1 = 仍有超长行（列名）
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os as _b_os, sys as _b_sys          # 单一来源：tools\_bandid.py（A-132）
_b_sys.path.insert(0, _b_os.path.dirname(_b_os.path.abspath(__file__)))
import _bandid as BID  # noqa: E402

# 允许作为断点的标点（由粗到细，前者优先）
BREAKS = "；。、，;"

# 续行缩进用的列表标记
MARKER = re.compile(r"^(\s*)((?:[-*+]|\d+[.)]|◈|·)\s+)")


def protected_spans(s):
    """返回不可拆的字符区间列表 [(start, end_exclusive), ...]。"""
    spans = []
    # 逐字引文 / 引号族
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
    # inline code
    i = 0
    while True:
        a = s.find("`", i)
        if a < 0:
            break
        b = s.find("`", a + 1)
        if b < 0:
            break
        spans.append((a, b + 1))
        i = b + 1
    # 含引文 id 的括号组（`D-001` s76）—— 拆开会让回源器看不见
    for m in re.finditer(r"[（(][^（）()]{0,600}[）)]", s):
        if re.search(r"`" + BID.ID_LOOSE + r"`", m.group(0)):
            spans.append((m.start(), m.end()))
    spans.sort()
    return spans


def in_protected(i, spans):
    for a, b in spans:
        if a <= i < b:
            return (a, b)
    return None


def split_one(line, maxlen):
    """返回 (新文本, 信息dict)。新文本为 None ⇒ 不拆（类型豁免）。"""
    s = line.rstrip("\n")
    st = s.strip()
    if not st:
        return None, {"skip": "空行"}
    if st.startswith("|"):
        return None, {"skip": "表格行（另案：短单元格＋表下展开）"}
    if st.startswith("#"):
        return None, {"skip": "标题"}
    if st.startswith(">"):
        return None, {"skip": "引用行（手册 §7 豁免）"}
    if re.match(r"^[-*+]\s*「", st) or re.match(r"^\d+[.)]\s*「", st):
        return None, {"skip": "逐字引文载体行（不得拆断）"}
    if len(s) <= maxlen:
        return None, {"skip": "未超长"}

    m = MARKER.match(s)
    if m:
        indent = len(m.group(1)) + len(m.group(2))
    else:
        indent = len(s) - len(s.lstrip(" "))
    budget = maxlen - indent
    spans = protected_spans(s)

    # 候选断点：标点，且在保护区间外
    cand = [i for i, ch in enumerate(s)
            if ch in BREAKS and i < len(s) - 1 and not in_protected(i, spans)]

    out, start, hard = [], 0, []
    while start < len(s):
        if len(s) - start <= budget:
            out.append(s[start:])
            break
        limit = start + budget
        pick = None
        for p in cand:
            if start < p < limit:
                pick = p
            elif p >= limit:
                break
        if pick is None:
            # 回退 ①：退到保护区间之前
            back = limit
            sp = in_protected(back, spans)
            if sp:
                back = sp[0]
            # 回退 ②：在 [start+1, back] 内找最靠右的空格
            sp2 = s.rfind(" ", start + 1, back + 1)
            cut = sp2 if sp2 > start else back
            hard.append(cut - start)
            pick = cut - 1 if cut > start else start
        out.append(s[start:pick + 1])
        start = pick + 1

    cont = " " * indent
    # 续行去掉原缩进后按标记宽度重排（首行保持原样 ⇒ 编号/项目符号位置不变）
    new = out[0] + "".join("\n" + cont + seg.lstrip(" ") for seg in out[1:])
    info = {"n": len(out), "lens": [len(x) for x in out],
            "indent": indent, "hard": hard}
    return new, info


def norm(s):
    return re.sub(r"\s+", "", s)


def fm_end_of(lines):
    """frontmatter 结束行号（含）。**description 行绝不能拆**（desc ≤1024 硬闸）。"""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i
    return -1


def process(path, maxlen, apply):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    fm = fm_end_of(lines)
    plan, newlines = [], []
    for i, ln in enumerate(lines):
        if i <= fm:
            newlines.append(ln)
            continue
        new, info = split_one(ln, maxlen)
        if new is None:
            if len(ln) > maxlen:                      # 只报超长且未处置的
                plan.append((i + 1, len(ln), info["skip"]))
            newlines.append(ln)
            continue
        assert norm(new) == norm(ln), "🔴 非空白改动！L%d" % (i + 1)
        plan.append((i + 1, len(ln), "→ %d 行 %s%s"
                     % (info["n"], info["lens"],
                        "  ⚠硬切%d处" % len(info["hard"]) if info["hard"] else "")))
        newlines.append(new)
    text_new = "\n".join(newlines)
    assert norm(text_new) == norm("\n".join(lines)), "🔴 全文非空白改动！"
    return fm, plan, text_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="技能根（其下 */SKILL.md）")
    ap.add_argument("--maxlen", type=int, default=260)
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不落盘")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*", "SKILL.md")))
    files = [f for f in files if not os.path.basename(os.path.dirname(f)).startswith("_")]
    if not files:
        print("🔴 未找到 %s/*/SKILL.md" % a.dir)
        return 1
    # ⚠ 备份**必须落在被扫描根之外**（2026-09-17 自伤：备份放 `skills\_backup_pre_split\`，
    #   装机/机器层把它当成一件技能 ⇒ 差点把备份装进宿主）。默认＝技能根的**同级**目录。
    bk = os.path.join(os.path.dirname(os.path.normpath(a.dir)), "_backup_pre_split")
    total_plan, bad = 0, []
    for f in files:
        fm, plan, text_new = process(f, a.maxlen, not a.dry_run)
        old = io.open(f, encoding="utf-8").read()
        print("=" * 74)
        print("%s ｜ 超长行 %d（frontmatter 至 L%d，不动）"
              % (os.path.relpath(f, a.dir), len(plan), fm + 1))
        for ln, L, d in plan:
            print("   L%-5d %4d 字符  %s" % (ln, L, d))
        total_plan += len(plan)
        if not a.dry_run and text_new != old:
            os.makedirs(bk, exist_ok=True)          # 备份在技能根之外（见上）
            shutil.copy2(f, os.path.join(bk, os.path.basename(os.path.dirname(f)) + '.md'))
            io.open(f, "w", encoding="utf-8", newline="").write(text_new)
        # 复核：拆后是否仍有超长行（与 polish_scan 同口径：排除 frontmatter / 引用行）
        nl = text_new.split("\n")
        for i, ln in enumerate(nl):
            if i <= fm or ln.lstrip().startswith(">"):
                continue
            if len(ln) > a.maxlen:
                bad.append((os.path.basename(os.path.dirname(f)), i + 1, len(ln)))
    print("=" * 74)
    print("超长行合计 %d ｜ 备份目录 %s ｜ dry-run=%s"
          % (total_plan, bk, a.dry_run))
    if bad:
        print("🔴 仍超长 %d 行（须另案处置）：" % len(bad))
        for s, i, L in bad:
            print("   %s L%d（%d）" % (s, i, L))
    return 1 if bad else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
