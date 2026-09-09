# -*- coding: utf-8 -*-
"""试点 B · 防线3〔操作层〕冒充扫描 v1（零 LLM 本地 py）

判定对象：SKILL.md 正文中 R 段之外（I/A1/A2/E/B/数据指引）把压缩转述或整句原文
用全角/ASCII 引号包起来并紧邻〔页锚〕的行——这类行会冒充作者原话（fidelity 报告的
O1/O3 判据）。启发式（仿 judge 报告口径）：
- 规则1 引号数数：逐行统计全角引号字符数与引号内运行段；
- 规则2 整句嫌疑：引号内运行段 长度>=20 字；或 长度>=12 且含句读（，,、。；;）
      且引号后 ≤32 字窗口内出现〔…（p页）〕页锚（v2 从 22 放宽，覆盖 judge ▲旁注样本）；
- 规则3 转述豁免（v2 口径=judge ▲旁注口径）：仅 引号前窗口(14 字)或引号内容 出现 原文意/转述/压缩/非逐字/词级/短语级 等标记才豁免；后置标签（如 洁食句后挂“ca15 压缩转述”）不再豁免，按 judge 记“未标注”处理为候选；
- 范围排除：R 段（作者原话合法引文）、E-示例/最小交付、块引用（>）与 frontmatter。

验收（试点 B 召回率）：
- rse 历史修复清单 3 处（fidelity-check-rse-v2.md 修复清单①-③）应全部命中；
- trv 独立报告 O3 明示 25+ 字长引号紧邻页锚 0 命中 → 现场文件应 0 候选（无假阳）；
- rse v2-verify 后现场应 0 候选（▲旁注洁食句按带 压缩转述 标签计，边界见报告）。

用法：
  python defense3_impersonation_scan.py <SKILL.md> [更多 SKILL.md ...]
  python defense3_impersonation_scan.py --selftest
输出：stdout JSON 摘要；文件落盘用 runner（pilotB_def3_runner.py）
"""
import os
import re
import sys
import json

MARKERS = ["原文意", "转述", "压缩", "非逐字", "非原话", "省略改写", "词级", "短语级",
           "术语", "同构", "自述", "见原文", "非作者", "非实时判断"]
PUNCT = "，,、。；;？?！!：:"
OPENERS = [("“", "”"), ("「", "」"), ("\"", "\"")]


def quote_char_count(line):
    return sum(1 for ch in line if ch in "“”「」")


def has_page_anchor(line):
    i = line.find("（p")
    if i < 0:
        return False
    j = i + 2
    while j < len(line) and (line[j].isdigit() or line[j] in "-–~，"):
        j += 1
    return any(c.isdigit() for c in line[i:j])


def quoted_runs(line):
    """抽取引号对内的运行段（支持嵌套一层：外层 「」 或 “”，ASCII 双引号）。"""
    runs = []
    i = 0
    while i < len(line):
        hit = None
        for o, c in OPENERS:
            k = line.find(o, i)
            if k >= 0 and (hit is None or k < hit[0]):
                hit = (k, o, c)
        if hit is None:
            break
        k, o, c = hit
        # 跳过成对单引号里的撇号干扰：ASCII 双引号内部不再当开引号
        e = line.find(c, k + 1)
        if e < 0:
            break
        content = line[k + 1:e]
        runs.append({"text": content, "start": k, "end": e, "open": o})
        i = e + 1
    return runs


def marked(seg):
    return any(m in seg for m in MARKERS)


def scan_line(ln, body, heading):
    """body=False 表示该行处于排除范围。返回记录列表。"""
    recs = []
    qcount = quote_char_count(ln)
    anchor = has_page_anchor(ln)
    for run in quoted_runs(ln):
        txt = run["text"]
        if len(txt) < 4:
            continue
        n = len(txt)
        punct = any(ch in txt for ch in PUNCT)
        before = ln[max(0, run["start"] - 14):run["start"]]
        labeled = marked(before) or marked(txt[:40])   # v2：后置标签不计（judge ▲旁注口径）
        window = ln[run["end"] + 1:run["end"] + 32]
        tight_trail = ("〔" in window) and ("（p" in window)
        suspect = body and tight_trail and not labeled and ((n >= 20) or (n >= 12 and punct))
        recs.append({
            "quote": txt[:80], "quote_len": n, "punct": punct, "labeled": labeled,
            "anchor": anchor, "tight_trail": tight_trail, "suspect": suspect, "qcount": qcount,
            "near": "标注豁免" if labeled else ("引号后无紧邻页锚" if not tight_trail else "命中"),
        })
    return recs


def is_excluded_line(ln, heading):
    s = ln.lstrip()
    if s.startswith(">"):
        return True
    if s.startswith("|") or s.startswith("-") and "反例" in heading and len(s) < 60:
        return False
    if heading.startswith("## R"):
        return True
    if heading.startswith("### E-示例") or heading.startswith("### 最小交付"):
        return True
    if ln.startswith("description:") or ln.startswith("---"):
        return True
    return False


def scan_file(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    heading = ""
    body_lines = 0
    suspects = []
    stats = {"quote_lines": 0, "labeled_runs": 0}
    for idx, ln in enumerate(lines):
        if ln.startswith("#"):
            heading = ln
        if is_excluded_line(ln, heading):
            continue
        body_lines += 1
        recs = scan_line(ln, True, heading)
        if recs:
            stats["quote_lines"] += 1
        for r in recs:
            if r["labeled"]:
                stats["labeled_runs"] += 1
            if r["suspect"]:
                suspects.append({"line": idx + 1, "text": ln.strip()[:160], **r})
    return {"file": os.path.abspath(path), "body_lines": body_lines, "stats": stats,
            "suspects": suspects, "total_lines": len(lines)}


def selftest():
    """召回样本：通用无版权示例（原样本含书籍原文片段，已替换为通用示例以规避版权；测试结构不变，如需原语料请自取原书）。"""
    cases = [
        ("示例-修复清单①（应命中）", "他分文未掏，反称这事儿要怪“机构没事儿大把赚钱、出事儿他说怪运气”（见 ca04〔示例·某案例（p1）〕）", True),
        ("示例-修复清单②（应命中）", "「只做短期动作，等周期快结束就离场、每 5 年换一个策略」〔示例·同节（p2）〕", True),
        ("示例-修复清单③（应命中）", "“不是提供好产品，而是没被某群体否决”〔第2章·否决（p3）〕", True),
        ("示例-原文意标注（应豁免）", "某公司的成功不在提供优质产品，而在没有被某群体否决（原文意：成功靠“没有被某群体否决”，见 ca16〔示例·否决（p3）〕）", False),
        ("示例-词级短引（应豁免）", "若某方案“98% 置信度安全”适用于个体重复暴露（〔示例·重复风险（p4-5）〕）", False),
        ("示例-带引号后置标签（应命中）", "“某群体绝不吃某种食物、非某群体吃得下”（ca15 压缩转述，〔示例·某案例（p6）〕）", True),
        ("示例-短术语引+页锚（应豁免）", "“平均值掩盖了深度差异”＝均值安全掩盖路径上的深坑（R·〔p7〕）", False),
    ]
    results = []
    for name, text, expect in cases:
        recs = scan_line(text, True, "## 测试")
        got = any(r["suspect"] for r in recs)
        results.append({"case": name, "expect_hit": expect, "got_hit": got,
                        "pass": got == expect, "recs": recs})
    return results


def main():
    if "--selftest" in sys.argv:
        out = {"mode": "selftest", "results": selftest()}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    paths = [p for p in sys.argv[1:] if os.path.isfile(p)]
    if not paths:
        print(__doc__)
        sys.exit(2)
    res = [scan_file(p) for p in paths]
    print(json.dumps({"mode": "scan", "files": res}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
