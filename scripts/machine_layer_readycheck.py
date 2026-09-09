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
    if os.path.isdir(bookbase):
        for root, dirs, files in os.walk(bookbase):
            for fn in files:
                if fn.endswith((".md", ".txt")) and ("part" in fn.lower() or "ocr" in fn.lower() or "ch" in fn.lower()):
                    srcs.append(os.path.join(root, fn))
    r_quotes = len(re.findall(r"「[^」]+」", text.split("## I")[0] if "## I" in text else text))
    gates = {
        "blind-lexicon": {"applicable": meta_ok, "missing": [] if meta_ok else ["description 缺 何时用/触发词 标记"], "input_note": "词表取自 description，构造即产出"},
        "defense3": {"applicable": has_R and quotes, "missing": [] if (has_R and quotes) else ["无 R 段或无引号引用形态"], "input_note": "冒充扫描需 R 段边界与引号/条款锚形态"},
        "darwin": {"applicable": has_R and has_I and has_E and has_B, "missing": [] if (has_R and has_I and has_E and has_B) else ["缺 R/I/E/B 分节之一"], "input_note": "9 维初评需 RIA 分节与 description"},
        "fidelity-R": {"applicable": bool(srcs) and has_R and r_quotes > 0, "missing": ([] if srcs else ["册根无可核对原文(parts/ocr)"]) + ([] if r_quotes > 0 else ["R 段无引文"]), "input_note": "R 引文逐字需册根原文；池式资产可选强化"},
    }
    return {"skill": os.path.abspath(skill_path), "bookbase": os.path.abspath(bookbase) if bookbase else None,
            "gates": gates,
            "recommendation": "machine-ok（四闸最小输入齐备）" if all(g["applicable"] for g in gates.values())
            else "partial-degrade（不适用闸按 v2.3 全 LLM 并标 pending；其余闸照跑机器层）"}

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(2)
    res = check(sys.argv[1], sys.argv[2])
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
