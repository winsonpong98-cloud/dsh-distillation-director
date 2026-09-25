# -*- coding: utf-8 -*-
r"""table_to_blocks.py —— 超长**表格行**回改器（表格不能拆行 ⇒ 转「逐字段标注行」）

依据：手册 §14 软闸 d1「超长行 > 260 字符」。markdown 表格的**一行**就是一行，
  无法像段落那样插换行；整表删除又会让 `d5-c2`（可执行正证据：`^\|.*\|` 计数 ≥5）掉闸。
⇒ 处置口径：**宽表 ⇒ 逐字段标注行**——表头列名原样搬成标签（**零新增词汇**，
   不写摘要、不加连接词），每个单元格内容原样下沉；只有结构符（`|`、`- ` 标记、`：` 分隔）变化。

**守恒断言（逐字段精确比对，不靠"剔除某些字符"这种松口径）**：
  ① 标签↔表头：`labels[i].strip('*') == header_cells[i].strip('*')`（**列表级相等**）
  ② 值↔单元格：`values[i] == row_cells[i]`（**逐字节相等**）
  ③ 文本级：每个字段的**实际落盘文本**去空白后 == `- **标签**：值` 去空白后
     ⇒ 证明拆分（插换行）没有吃掉/改写任何一个字符
  ④ 非表格行：**逐字节原样保留**、顺序不变
  · **不得**用「去掉 `-`／`：` 再比」这类松口径：正文里 `2017-02-06`（连字符）、
    `制度前提：…`（冒号）都有实义，一律剔除⇒守恒断言形同虚设。

用法：python tools\table_to_blocks.py --dir <技能根> [--maxlen 260] [--dry-run]
退出码：0 = 已无超长表格行；1 = 仍有（列名，须手工处置）
"""
import argparse
import glob
import io
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import split_long_lines as SL          # 复用安全断点 / 续行缩进逻辑


def norm(s):
    return re.sub(r"\s+", "", s)


def cells_of(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_sep(line):
    return bool(re.match(r"^\|[\s:|-]+\|?\s*$", line)) and "-" in line


def block_to_md(header, rows, maxlen):
    """(表头, 数据行) → (md 文本, fields)。fields = [(标签, 值, 实际落盘文本), ...]"""
    cols = cells_of(header)
    out, fields = [], []
    for r in rows:
        cs = cells_of(r)
        cs += [""] * (len(cols) - len(cs))
        for j, val in enumerate(cs):
            raw = cols[j] if j < len(cols) and cols[j] else "列%d" % j
            label = raw.strip("*")
            text = "- **%s**：%s" % (label, val)
            if len(text) > maxlen:
                new = SL.split_one("  " + text, maxlen)[0]
                if not new:
                    raise AssertionError("字段仍超长且无安全断点：%s" % label)
                new = new[2:]                       # 去掉试探用的 2 空格缩进
            else:
                new = text
            out.append(new)
            fields.append((label, val, new))
        out.append("")                              # 行间空行 = 组边界
    return "\n".join(out).rstrip("\n"), fields


def process(path, maxlen):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    fm = SL.fm_end_of(lines)
    newlines, changes, left = [], [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if i > fm and ln.lstrip().startswith("|"):
            blk_end = i                       # ⚠ 游标变量**不得与内层循环下标重名**：
            while (blk_end < len(lines)        #   同名会被遮蔽 ⇒ `i = blk_end` 把游标重置 ⇒ 死循环
                   and lines[blk_end].lstrip().startswith("|")):
                blk_end += 1
            blk = lines[i:blk_end]
            long_rows = [b for b in blk if len(b) > maxlen and not is_sep(b)]
            if long_rows and not is_sep(blk[0]):
                header = blk[0]
                rows = [b for b in blk[1:] if not is_sep(b)]
                md, fields = block_to_md(header, rows, maxlen)
                # 守恒断言 ①②③
                cols = cells_of(header)
                k = 0
                for r in rows:
                    cs = cells_of(r) + [""] * (len(cols) - len(cells_of(r)))
                    for j, val in enumerate(cs):
                        lab, v, txt = fields[k]
                        assert lab == (cols[j] if j < len(cols) and cols[j]
                                       else "列%d" % j).strip("*"), "标签↔表头 不符"
                        assert v == val, "值↔单元格 不符（%s）" % lab
                        assert norm(txt) == norm("- **%s**：%s" % (lab, v)), \
                            "文本级不符（%s）——拆分吃掉了字符" % lab
                        k += 1
                assert k == len(fields), "字段数不符"
                changes.append((i + 1, len(blk), len(fields),
                                [len(b) for b in blk if not is_sep(b)]))
                newlines.append(md)
                i = blk_end
                continue
            else:
                for k2, b in enumerate(blk):
                    if len(b) > maxlen:
                        left.append((i + k2 + 1, len(b)))
                newlines.extend(blk)
                i = blk_end
                continue
        newlines.append(ln)                          # 守恒断言 ④：非表格行原样
        i += 1
    return fm, changes, left, "\n".join(newlines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="技能根（其下 */SKILL.md）")
    ap.add_argument("--maxlen", type=int, default=260)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = sorted(glob.glob(os.path.join(a.dir, "*", "SKILL.md")))
    files = [f for f in files if not os.path.basename(os.path.dirname(f)).startswith("_")]
    if not files:
        print("🔴 未找到 %s/*/SKILL.md" % a.dir)
        return 1
    # ⚠ 备份**必须落在被扫描根之外**（2026-09-17 自伤：备份放 `skills\_backup_pre_tablefix\`，
    #   装机把它当成一件技能 ⇒ 差点把备份装进宿主）。默认＝技能根的**同级**目录。
    bk = os.path.join(os.path.dirname(os.path.normpath(a.dir)), "_backup_pre_tablefix")
    bad, nchg = [], 0
    for f in files:
        fm, changes, left, text_new = process(f, a.maxlen)
        old = io.open(f, encoding="utf-8").read()
        print("=" * 74)
        print("%s ｜ 转置表格 %d 个" % (os.path.relpath(f, a.dir), len(changes)))
        for ln, nrow, nfield, lens in changes:
            print("   L%-5d 表 %d 行 → %d 条标注行 ｜ 原行字符 %s"
                  % (ln, nrow, nfield, lens))
        nchg += len(changes)
        for ln, L in left:
            bad.append((os.path.basename(os.path.dirname(f)), ln, L))
            print("   🔴 L%-5d 仍有超长表格行（%d）——须手工处置" % (ln, L))
        if not a.dry_run and text_new != old:
            os.makedirs(bk, exist_ok=True)
            shutil.copy2(f, os.path.join(
                bk, os.path.basename(os.path.dirname(f)) + '.md'))
            io.open(f, "w", encoding="utf-8", newline="").write(text_new)
            npipe = sum(1 for x in text_new.split("\n")
                        if x.lstrip().startswith("|") and x.count("|") >= 2)
            print("   转置后管道行 %d ｜ d5-c2（≥5）%s" % (npipe, "✔" if npipe >= 5 else "🔴"))
        elif not a.dry_run:
            print("   （幂等：无改动）")
    print("=" * 74)
    print("转置合计 %d 个表 ｜ 备份 %s ｜ dry-run=%s" % (nchg, bk, a.dry_run))
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
