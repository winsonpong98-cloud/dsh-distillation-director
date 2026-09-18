# -*- coding: utf-8 -*-
"""machine_layer_readycheck v1（v3.1 · 负样本校准版）

作用：§13 机器层适用性前置检查的落地脚本。
设计修正（负样本启发）：不再用“固定四项(candidates 五池/quote-precheck)”一刀切，
改为 按闸最小输入 判定——机器层各闸只需其自身所需的最小机器输入，
塔勒布式家族资产(candidates 池/quote-precheck)视为可选强化而非适用前提。

每闸适用条件：
  blind-lexicon : SKILL description 含 何时用/触发词 任一标记
  defense3     : SKILL 含 R 段且正文存在「」或引号引用形态（冒充扫描输入）
  darwin       : SKILL 含 R/I/E/B 分节 + description（机器初评输入）
  fidelity-R   : 册根存在可核对原文(parts/*.md 或 ocr 等)且 SKILL R 段非空
用法: python machine_layer_readycheck.py <SKILL.md> <bookbase> [--json out.json]
"""
import os, re, sys, json

def check(skill_path, bookbase):
    text = open(skill_path, encoding="utf-8").read()
    meta_ok = ("何时用" in text[:2000]) or ("触发词" in text[:2000])
    has_R = re.search(r"^##\s*R", text, re.M) is not None
    has_I = re.search(r"^##\s*I", text, re.M) is not None
    has_E = re.search(r"^##\s*E", text, re.M) is not None
    has_B = re.search(r"^##\s*B", text, re.M) is not None
    quotes = "「" in text or "“" in text
    # fidelity 源：册根 parts/ocr 等
    srcs = []
    # v0.2b：优先只取 <bookbase>/parts/ 下的正文源；并排除 *check* 等副本目录（原版把 parts-check 也计入 → 页数翻倍）
    pref = os.path.join(bookbase, "parts") if bookbase else ""
    if pref and os.path.isdir(pref):
        for fn in sorted(os.listdir(pref)):
            if fn.endswith((".md", ".txt")):
                srcs.append(os.path.join(pref, fn))
    elif os.path.isdir(bookbase):
        for root, dirs, files in os.walk(bookbase):
            if any(k in os.path.basename(root).lower() for k in ("check", "backup", "backups")):
                continue
            for fn in files:
                if fn.endswith((".md", ".txt")) and ("part" in fn.lower() or "ocr" in fn.lower() or "ch" in fn.lower()):
                    srcs.append(os.path.join(root, fn))
    r_quotes = len(re.findall(r"「[^」]+」", text.split("## I")[0] if "## I" in text else text))
    # v0.2（M7）：原版本闸只给 True/False 与 missing=[]，属**自证式清单**、无可核计数。
    # 现为每闸输出**可核计数**（desc 长度/触发词数、R 段条数、引号与页锚计数、原文页数、步骤与 CHECKPOINT 数），
    # 并在结论中明确“本检查只判最小输入齐备度，不替代任何真实闸”。
    _desc = re.search(r'^description:\s*[|"\'](.*?)(?:"\s*$|\n\S)', text, re.M | re.S)
    _desc_txt = _desc.group(1) if _desc else ""
    n_pages = 0
    for _sp in srcs:
        try:
            n_pages += len(re.findall(r"=====\s*\[PAGE \d+\]\s*=====", open(_sp, encoding="utf-8").read()))
        except Exception:
            pass
    counts = {
        "desc_chars": len(_desc_txt),
        "trigger_keywords": len(re.findall(r"[、，/／]", _desc_txt[_desc_txt.find("触发词"):])) if "触发词" in _desc_txt else 0,
        "R_quote_lines": len(re.findall(r"^\s*-\s*(?:R\d+|「)", text, re.M)),
        "quote_pairs": len(re.findall(r"「[^」]{4,}」", text)),
        "page_anchors": len(re.findall(r"〔p\d+", text)),
        "source_md_files": len(srcs), "source_pages": n_pages,
        "E_steps": len(set(re.findall(r"步骤\s*(\d)", text))),
        "checkpoints": len(re.findall(r"CHECKPOINT", text)),
    }

    def _g(applicable, missing, note):
        return {"applicable": bool(applicable), "missing": [] if applicable else missing,
                "input_note": note, "counts": counts}

    gates = {
        "blind-lexicon": _g(meta_ok, ["description 缺 何时用/触发词 标记"], "词表取自 description（desc 长度与触发词数见 counts）"),
        "defense3": _g(has_R and quotes, ["无 R 段或无引号引用形态"], "冒充扫描需 R 段边界与引号/页锚形态（R 行数与引号对见 counts）"),
        "darwin": _g(has_R and has_I and has_E and has_B, ["缺 R/I/E/B 分节之一"], "9 维初评需 RIA 分节与 description"),
        "fidelity-R": _g(bool(srcs) and has_R and r_quotes > 0,
                         ([] if srcs else ["册根无可核对原文(parts/ocr)"]) + ([] if r_quotes > 0 else ["R 段无引文"]),
                         "R 引文逐字需册根原文（源文件数与页标记数见 counts）"),
    }
    return {"skill": os.path.abspath(skill_path), "bookbase": os.path.abspath(bookbase) if bookbase else None,
            "gates": gates, "counts": counts,
            "recommendation": ("machine-ok（四闸最小输入齐备；**本检查只判最小输入齐备度，不替代任何真实闸**）"
                               if all(g["applicable"] for g in gates.values())
                               else "partial-degrade（不适用闸按 v2.3 全 LLM 并标 pending；其余闸照跑机器层）"),
            "method_note": "v0.2（M7 修正）：由‘清单式自证’升级为**可核计数**（desc/R/引号/页锚/原文源与页数/步骤/检查点），计数随本文件落盘可复核。"}

def main():
    # A-78（2026-09-17 可移植性审计）：**显式参数解析 + 可读错误**。
    #   旧版只判 `len(sys.argv) < 3`，随后直接 `open(sys.argv[1])`——
    #   于是把选项名当文件名：`--task no-such-task` ⇒ `FileNotFoundError: '--task'` **裸 traceback**
    #   （使用者看不出"该脚本不接受 --task，它要的是两个位置参数"）。换台机器时这种误用极常见。
    argv = sys.argv[1:]
    # 兼容 `--json <path>`（原设计），其余 `--x` 一律报错并打印用法
    json_out = None
    if '--json' in argv:
        i = argv.index('--json')
        if i + 1 >= len(argv):
            sys.stderr.write('🔴 --json 缺少取值\n')
            return 2
        json_out = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if '-h' in argv or '--help' in argv:
        print(__doc__)
        return 0
    bad = [x for x in argv if x.startswith('-')]
    if bad:
        sys.stderr.write('🔴 不认识选项：%s\n'
                         '   本脚本**只接受两个位置参数**：`<SKILL.md> <bookbase>`'
                         '（可选 `--json <out.json>`）。\n'
                         '   例：python machine_layer_readycheck.py "<技能件>/SKILL.md" "<原书册根>" --json out.json\n'
                         % ' '.join(bad))
        return 2
    if len(argv) < 2:
        print(__doc__)
        return 2
    skill_path, bookbase = argv[0], argv[1]
    if not os.path.isfile(skill_path):
        sys.stderr.write('🔴 第 1 个位置参数应为**存在的 SKILL.md 路径**，实测不存在：%s\n' % skill_path)
        return 2
    if not os.path.isdir(bookbase):
        sys.stderr.write('🔴 第 2 个位置参数应为**存在的原书册根目录**，实测不存在：%s\n'
                         '   （本脚本用它找 `parts/` 等可核对原文；无册根时该闸会判"不适用"，'
                         '但路径本身必须先存在）\n' % bookbase)
        return 2
    res = check(skill_path, bookbase)
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0

if __name__ == "__main__":
    sys.exit(main())
