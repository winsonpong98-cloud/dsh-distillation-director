# -*- coding: utf-8 -*-
r"""盲测闸 词表命中模拟器 v1（零 LLM 本地 py · 初判用）

目标：description 触发词表 对 用户路由 prompt 做字面命中初判，筛掉"机械可判"路由；
无字面锚/弱命中/邻族抢单 的 prompt 显式标记 needs_llm=True，交 LLM judge 结构化表。

═══ 设计铁律：**本脚本不得含任何一本书的数据**（2026-09-17 用户拍板 · 《避坑手册》A-74）═══
历史（如实留档，两轮才做对）：
  · v1：`BOOKS`／`SKILLS` 里**硬编码了三本书的绝对路径**（形如 `<工作区>\<册目录>\…`），
    并把某册的 12 条路由题**内嵌成默认 fixture** ⇒ ① 换机即失效（路径只在本机存在）；
    ② "没给 --prompts"时**静默拿那一册的题出报告**（产出的是**别的书**的证据，A-37）。
  · v2：真实现了 `--prompts`／`--skills-root` 成对开关，**但没有删掉内嵌的书名与路径**——
    默认分支仍指向那三册。**"抽了开关却没删数据"＝没通用化**（A-74）。
  · v3（当前）：**删除全部书别数据**——没有 BOOKS／SKILLS 常量、没有内嵌书目标题、
    没有默认 fixture。语料与词表**必须由调用者给出**，否则直接退出并打印用法。

用法：
  # 正式用（成对给出，缺一即拒跑）
  python blindtest_lexicon_mock_v1.py --prompts <probes.json> --skills-root <技能根> [--out <目录>]
  # 自证（不依赖任何外部语料；用通用占位题与合成词表验证判定逻辑，含两例已知正负样本）
  python blindtest_lexicon_mock_v1.py --self-test

  `--prompts` 期望：顶级数组，或含 `probes`／`prompts`／`rows`／`items`／`cases` 键的对象；
  每条至少 `{"prompt": "…"}`，可选 `id`／`target`（别名 `expect_top1`／`owner_skill`）／`judge_class`。

产物（写到 `--out`，缺省＝当前目录，**不再写进工具目录**以免污染脚本同步/打包新鲜度闸）：
  blindtest-mock-v1.json ＋ 盲测词表模拟器v1-报告.md
"""
import os
import re
import sys
import json

# ⚠ 本文件**不得**出现：书名、某册的目录名、任何绝对路径常量、任何一册的题目。
#    （巡检：`python tools\\scan_plugin_payload.py`；期望本文件零【甲】类命中）

# 判停红线词（时点预测等）。**注**：这是**投资域**口径；换域时须另备域内词表
#（通用替代见 `tools\\blindtest_generic.py`）。用 `--lexicon-domain` 可在产物里声明域。
REDLINE = ["什么时候会", "何时发生", "何时会", "会不会崩", "会不会涨", "会崩", "会跌", "预测", "明天", "涨跌", "提前跑", "逃顶", "抄底", "会涨吗"]  # v1.1：移除裸词"什么时候/何时"（会把"什么时候能拆线"误判为时点预测）

# ── 自证样本（**通用占位，不含任何书别数据**）────────────────────────────────
# 用途：机器证明"判定逻辑没坏"（机械命中／无锚需 LLM／红线判停／并列歧义 四种形态各一）。
# 它不是"某个任务的语料"，故可长期留在脚本里；**换域词表须另配**（见上方 REDLINE 注）。
SELFTEST_LEXICON = {
    "skill-alpha": ["预算", "现金流", "应急金", "负债率"],
    "skill-beta": ["复盘", "决策记录", "检查清单"],
}
SELFTEST_PROBES = [
    {"id": "ST-1", "target": "skill-alpha", "judge_class": "clear",
     "prompt": "家里应急金该存多少，怎么按负债率和现金流算？", "expect": "mechanical-clear"},
    {"id": "ST-2", "target": "skill-beta", "judge_class": "clear",
     "prompt": "我总在同一个地方栽跟头，怎么做决策记录和复盘？", "expect": "mechanical-clear"},
    {"id": "ST-3", "target": None, "judge_class": "boundary",
     "prompt": "今天天气不错适合散步吗？", "expect": "no-lexicon-hit"},
    {"id": "ST-4", "target": None, "judge_class": "decline",
     "prompt": "预测一下明天大盘涨跌，我想提前跑。", "expect": "redline-decline"},
]


def read_description(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    desc = []
    active = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.startswith("description:"):
            active = True
            desc.append(ln[len("description:"):].strip())
        elif active and ln.startswith((" ", "\t")):
            desc.append(ln.strip())
    text = " ".join(desc)
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        text = text[1:-1]
    elif text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1]
    return text


def extract_lexicon(desc):
    """词源=整段 description（触发词段＋何时用/何时不用＋引号话术示例），
    去括号后按标点/引号/斜杠/空格切词；2..16 字为 token（超长整句跳过防噪声）。"""
    seg = re.sub(r"[（(][^）)]*[）)]", "", desc)
    toks = re.split(r"['\"、，,；;/|｜\s：:。！？!?—…]+", seg)
    out = []
    seen = set()
    for t in toks:
        t = t.strip(" 　“”「」‘’：:。，、！？…")
        if 2 <= len(t) <= 16 and t not in seen and not re.fullmatch(r"[0-9a-zA-Z.]+", t):
            seen.add(t)
            out.append(t)
    return out[:200]


def build_lexicons_from_root(root):
    """从**调用者给出的技能根**建词表（每件取 `<root>/<slug>/SKILL.md` 的 description）。"""
    lex = {}
    if not os.path.isdir(root):
        sys.exit('🔴 --skills-root 不是目录：%s' % root)
    for slug in sorted(os.listdir(root)):
        p = os.path.join(root, slug, 'SKILL.md')
        if os.path.isfile(p):
            lex[slug] = extract_lexicon(read_description(p))
    return lex


def load_prompts(path):
    if not os.path.isfile(path):
        sys.exit('🔴 --prompts 文件不存在：%s' % path)
    d = json.load(open(path, encoding='utf-8'))
    if isinstance(d, dict):
        for k in ('probes', 'prompts', 'rows', 'items', 'cases'):
            if isinstance(d.get(k), list):
                d = d[k]
                break
    if not isinstance(d, list) or not d:
        sys.exit('🔴 --prompts 无可用条目（%s）：期望顶级数组或含 probes/prompts/rows 的对象' % path)
    out = []
    for it in d:
        if not isinstance(it, dict) or not str(it.get('prompt', '')).strip():
            sys.exit('🔴 --prompts 条目缺 prompt 字段：%r' % (it,))
        it = dict(it)
        it.setdefault('id', '?')
        # 目标件别名：有的库用 expect_top1／owner_skill，有的用 target
        if not it.get('target'):
            it['target'] = it.get('expect_top1') or it.get('owner_skill')
        it.setdefault('judge_class', 'unknown')
        out.append(it)
    return out


def judge_prompt(prompt, lexicons):
    red = [w for w in REDLINE if w in prompt]
    scores = {}
    hits = {}
    for slug, toks in lexicons.items():
        got = [t for t in toks if t in prompt]
        hits[slug] = got
        scores[slug] = len(got)
    best = max(scores.values()) if scores else 0
    tops = [s for s, v in scores.items() if v > 0]
    if best > 0:
        rivals = [s for s in tops if s != (tops[0] if tops else None) and scores[s] >= best * 0.6] if tops else []
    else:
        rivals = []
    tie = best > 0 and any(s != (tops[0] if tops else None) and scores[s] == best for s in tops)
    if red:
        verdict = "redline-decline"
        needs_llm = False          # 判停本身机器即可给（红灯）；语义复核可选
    elif best == 0:
        verdict = "no-lexicon-hit"
        needs_llm = True
    elif tie:
        verdict = "weak-or-ambiguous"
        needs_llm = True
    else:
        verdict = "mechanical-clear"
        needs_llm = False
    return {
        "redline_hits": red,
        "scores": {k: v for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v > 0},
        "best": best, "top": tops[0] if tops else None,
        "rivals": rivals, "verdict": verdict, "needs_llm": needs_llm,
    }


def parse_args():
    a = sys.argv[1:]
    flags = ('--self-test',)
    out = {}
    for k in flags:
        if k in a:
            out[k[2:].replace('-', '_')] = True
    for k in ('--prompts', '--skills-root', '--out', '--lexicon-domain'):
        if k in a:
            i = a.index(k) + 1
            if i >= len(a):
                sys.exit('🔴 %s 缺少取值' % k)
            out[k[2:].replace('-', '_')] = a[i]
    return out


USAGE = """用法：
  python blindtest_lexicon_mock_v1.py --prompts <probes.json> --skills-root <技能根> [--out <目录>]
  python blindtest_lexicon_mock_v1.py --self-test        # 不依赖外部语料，验证判定逻辑

⚠ 本脚本**不含任何一本书的数据**：语料（prompts）与词表（skills-root）**必须由你给出**。
  缺任一项即退出（早先版本会用内嵌的某一册语料静默出报告 ⇒ 产出别的书的证据，A-37/A-74）。"""


def emit(rows, lexicons, psrc, lsrc, outdir, domain_note=''):
    stats = {
        "total": len(rows),
        "judge_clear": sum(1 for r in rows if r["judge_class"] == "clear"),
        "judge_boundary": sum(1 for r in rows if r["judge_class"] == "boundary"),
        "judge_decline": sum(1 for r in rows if r["judge_class"] == "decline"),
        "machine_mechanical_clear": sum(1 for r in rows if r["verdict"] == "mechanical-clear"),
        "machine_needs_llm": sum(1 for r in rows if r["needs_llm"]),
        "machine_redline": sum(1 for r in rows if r["verdict"] == "redline-decline"),
        "top_is_target": sum(1 for r in rows if r["top"] == r["target"] and r["top"] is not None),
    }
    out = {"schema": "blindtest-lexicon-mock-v1", "prompt_source": psrc, "lexicon_root": lsrc,
           "lexicon_sizes": {k: len(v) for k, v in lexicons.items()},
           "rows": rows, "stats": stats}
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "blindtest-mock-v1.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    L = []
    A = L.append
    A("# 盲测闸 词表命中模拟器 v1 —— 机器初判（%d 题）" % len(rows))
    A("")
    A("> 语料来源：prompts=`%s` ｜ 词表=`%s`" % (psrc, lsrc))
    A("> 角色：盲测 LLM judge 的机器初判层（词表命中，零 LLM）")
    if domain_note:
        A("> ⚠ 红线词表域声明：%s" % domain_note)
    A("")
    A("## 一、语料与词表")
    A("")
    A("%d 个候选 skill 的 description 词表（触发词段自动提取）；词表规模：" % len(lexicons)
      + "，".join("%s=%d" % (k, len(v)) for k, v in sorted(lexicons.items())))
    A("")
    A("## 二、%d 条初判结果" % len(rows))
    A("")
    A("| id | judge 类 | 初判 verdict | needs_llm | top1(命中数) | 邻族风险 |")
    A("|---|---|---|---|---|---|")
    for r in rows:
        top_txt = (r["top"] + "(" + str(r["scores"].get(r["top"], 0)) + ")") if r["top"] else "—"
        rival_txt = ",".join(r["rivals"]) if r["rivals"] else "—"
        A("| %s | %s | %s | %s | %s | %s |" % (r["id"], r["judge_class"], r["verdict"],
                                              r["needs_llm"], top_txt, rival_txt))
    A("")
    A("## 三、统计")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    _nd = sum(1 for r in rows if r["judge_class"] == "decline")
    A("| 机器机械可判（mechanical-clear） | %d/%d |" % (stats["machine_mechanical_clear"], len(rows)))
    A("| 机器判 需 LLM | %d/%d（无词表锚/弱命中/邻族竞合） |" % (stats["machine_needs_llm"], len(rows)))
    A("| 判停红线机器命中 | %d/%d（judge_class=decline 的题） |" % (stats["machine_redline"], _nd))
    A("| 词表 top1 = 期望目标技能 | %d/%d |" % (stats["top_is_target"], len(rows)))
    A("")
    A("## 四、已知缺口（v2 候选）")
    A("")
    A("- 词表只取 description 全文切词，未单独利用「何时用／何时不用」语义区；")
    A("- 同义改写（如口语化表述 vs 书内术语）命中不了，须交 LLM judge；")
    A("- 红线词表为**投资域（时点预测）**口径，换域须另备词表（通用替代：`tools/blindtest_generic.py`）。")
    A("")
    md = "\n".join(L)
    md_path = os.path.join(outdir, "盲测词表模拟器v1-报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(json.dumps(stats, ensure_ascii=False))
    for r in rows:
        print("%s %-7s %-20s llm=%-5s top=%s" % (r["id"], r["judge_class"], r["verdict"],
                                                 r["needs_llm"], (r["top"] or "—")[:26]))
    print("md ->", md_path)
    return stats


def self_test(outdir):
    """不依赖任何外部语料：用通用占位词表＋占位题验证四种判定形态（含正负样本）。"""
    print('# 自证模式：语料＝脚本内**通用占位**样本（不含任何书别数据）')
    rows = []
    for pr in SELFTEST_PROBES:
        r = judge_prompt(pr["prompt"], SELFTEST_LEXICON)
        r.update({"id": pr["id"], "target": pr["target"], "judge_class": pr["judge_class"],
                  "prompt": pr["prompt"]})
        rows.append((r, pr["expect"]))
    ok = 0
    for r, want in rows:
        good = (r["verdict"] == want)
        ok += good
        print('  %s %s 期望=%s 实测=%s（top=%s）' % ('✔' if good else '🔴', r["id"], want,
                                                    r["verdict"], r["top"] or '—'))
    emit([r for r, _ in rows], SELFTEST_LEXICON, '（自证：脚本内通用占位样本）',
         '（自证：脚本内通用占位词表）', outdir,
         domain_note='自证样本，非真实域；红线条目仅用于验证判定分支')
    print('自证：%d/%d 形态符合预期 ⇒ %s' % (ok, len(rows), '✔ 通过' if ok == len(rows) else '🔴 判定逻辑有变'))
    return 0 if ok == len(rows) else 1


def main():
    args = parse_args()
    if args.get('self_test'):
        return self_test(args.get('out') or os.getcwd())

    hp, hs = bool(args.get('prompts')), bool(args.get('skills_root'))
    if not hp and not hs:
        print(USAGE)
        return 2
    if hp != hs:
        sys.exit('🔴 --prompts 与 --skills-root 必须**成对**给出。\n'
                 '   （早先只给 prompts 时，词表会取自**别的书的内嵌语料**，静默产出跨书假证据；A-37）\n\n' + USAGE)

    prompts = load_prompts(args['prompts'])
    lexicons = build_lexicons_from_root(args['skills_root'])
    if not lexicons:
        sys.exit('🔴 --skills-root 下未找到任何 <slug>/SKILL.md：%s' % args['skills_root'])
    targets = {p['target'] for p in prompts if p.get('target')}
    miss = sorted(targets - set(lexicons))
    if miss:
        sys.exit('🔴 prompts 的 target 不在词表语料内：%s ⇒ **语料不匹配**（A-37），拒绝产出'
                 '（词表语料前 8 个：%s）' % (miss, sorted(lexicons)[:8]))

    outdir = args.get('out') or os.getcwd()
    if not os.path.isdir(outdir):
        sys.exit('🔴 --out 不是目录：%s' % outdir)
    print('# 语料来源：prompts=%s ｜ 词表=%s ｜ 共 %d 题'
          % (args['prompts'], args['skills_root'], len(prompts)))
    domain_note = args.get('lexicon_domain') or (
        '内嵌 REDLINE＝**投资域（时点预测）**口径；若本次语料属他域，'
        '红线条目的判停结论**不得**直接采信，须另备域内词表（通用替代：tools/blindtest_generic.py）')
    print('# ⚠ %s' % domain_note)
    rows = []
    for fx in prompts:
        r = judge_prompt(fx["prompt"], lexicons)
        r.update({"id": fx["id"], "target": fx["target"], "judge_class": fx["judge_class"],
                  "prompt": fx["prompt"]})
        rows.append(r)
    emit(rows, lexicons, args['prompts'], args['skills_root'], outdir, domain_note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
