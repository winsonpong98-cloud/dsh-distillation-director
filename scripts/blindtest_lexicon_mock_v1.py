# -*- coding: utf-8 -*-
"""盲测闸 词表命中模拟器 v1（零 LLM 本地 py · 初判用）

目标：description 触发词表 对 用户路由 prompt 做字面命中初判，筛掉“机械可判”路由；
无字面锚/弱命中/邻族抢单 的 prompt 显式标记 needs_llm=True，交 LLM judge 结构化表
（13x{命中/目标/邻族风险}，单发小批）——对应三闸方案里盲测的机器初判层。

验收基准：反脆弱册 blind-test-report.md 的 12 条路由盲测（AD-1..6 / OC-1..6），
judge 结论=9 干脆 + 3 边界存疑（AD-3/OC-4/OC-5）+ 2 判停（AD-6/OC-6）。

用法：
  python blindtest_lexicon_mock_v1.py
  python blindtest_lexicon_mock_v1.py --prompts <json>   （覆盖内嵌 fixture）
产物：blindtest-mock-v1.json + 盲测词表模拟器v1-试点报告.md（同目录）
"""
import os
import re
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TT = os.path.join(ROOT, "投资蒸馏", "塔勒布五部曲")
BOOKS = {
    "反脆弱": os.path.join(TT, "反脆弱"),
    "股票大作手回忆录": os.path.join(ROOT, "投资蒸馏", "股票大作手回忆录"),
    "寻找鱼多的池塘": os.path.join(ROOT, "投资蒸馏", "寻找鱼多的池塘"),
}
SKILLS = {
    "antifragile-designer": os.path.join(BOOKS["反脆弱"], "skills", "antifragile-designer", "SKILL.md"),
    "optionality-convexity": os.path.join(BOOKS["反脆弱"], "skills", "optionality-convexity", "SKILL.md"),
    "trader-discipline": os.path.join(BOOKS["股票大作手回忆录"], "skills", "trader-discipline", "SKILL.md"),
    "market-structure-and-manipulation": os.path.join(BOOKS["股票大作手回忆录"], "skills", "market-structure-and-manipulation", "SKILL.md"),
    "multi-asset-rotation": os.path.join(BOOKS["寻找鱼多的池塘"], "skills", "multi-asset-rotation", "SKILL.md"),
    "convertible-pool-rotation": os.path.join(BOOKS["寻找鱼多的池塘"], "skills", "convertible-pool-rotation", "SKILL.md"),
    "fund-selector": os.path.join(BOOKS["寻找鱼多的池塘"], "skills", "fund-selector", "SKILL.md"),
    "investing-mindset": os.path.join(BOOKS["寻找鱼多的池塘"], "skills", "investing-mindset", "SKILL.md"),
}

# 判停红线词（时点预测等；盲测 AD-6/OC-6）
REDLINE = ["什么时候会", "何时发生", "何时会", "会不会崩", "会不会涨", "会崩", "会跌", "预测", "明天", "涨跌", "提前跑", "逃顶", "抄底", "会涨吗"]  # v1.1：移除裸词“什么时候/何时”（会把“什么时候能拆线”误判为时点预测），见规范对比实验 sge-3 案例

FIXTURES = [
    {"id": "AD-1", "target": "antifragile-designer", "judge_class": "clear", "prompt": "家庭财务就怕是裁员这种打击，怎么让我的职业收入不怕黑天鹅？"},
    {"id": "AD-2", "target": "antifragile-designer", "judge_class": "clear", "prompt": "我现在零冗余、满负荷、效率极高，但总觉得哪里不对，是不是越优化越脆？"},
    {"id": "AD-3", "target": "antifragile-designer", "judge_class": "boundary", "prompt": "我吃一堆保健品、每年全套体检来防病，这种过度保护是不是反而有害？"},
    {"id": "AD-4", "target": "antifragile-designer", "judge_class": "clear", "prompt": "这本书刚出版就火了，值不值得买来学？新公司值不值得追？"},
    {"id": "AD-5", "target": "antifragile-designer", "judge_class": "clear", "prompt": "我严格按计划、全面求稳，反而越来越脆，为什么越优化越脆？"},
    {"id": "AD-6", "target": "antifragile-designer", "judge_class": "decline", "prompt": "股市房价什么时候会崩，我想提前跑。"},
    {"id": "OC-1", "target": "optionality-convexity", "judge_class": "clear", "prompt": "10 个创业公司死 9 个，成了赚 50 倍，要不要拿全部积蓄投？"},
    {"id": "OC-2", "target": "optionality-convexity", "judge_class": "clear", "prompt": "我胜率不到 40%，是不是方法不行该放弃？"},
    {"id": "OC-3", "target": "optionality-convexity", "judge_class": "clear", "prompt": "小仓位试错和赌博有什么区别？"},
    {"id": "OC-4", "target": "optionality-convexity", "judge_class": "boundary", "prompt": "这只基金十年年年正收益，历史数据这么好，能不能重仓？"},
    {"id": "OC-5", "target": "optionality-convexity", "judge_class": "boundary", "prompt": "波动太大我睡不着，要不要降仓位、降波动？"},
    {"id": "OC-6", "target": "optionality-convexity", "judge_class": "decline", "prompt": "预测比特币明天涨跌，涨了我就全仓跟。"},
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
    if text.startswith("") and text.endswith("") and len(text) >= 2:
        text = text[1:-1]
    return text


def extract_lexicon(desc):
    """v1.2（对比实验 v3.1 优化）：词源=整段 description（触发词段+何时用/何时不用+引号话术示例），
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


def build_lexicons():
    lex = {}
    for slug, path in SKILLS.items():
        desc = read_description(path)
        lex[slug] = extract_lexicon(desc)
    return lex


# ---- 通用化（A-37 修复 · 2026-09-13）------------------------------------------------
# 病根：docstring 写着 `--prompts <json>`，**代码里从未实现**（`prompts = FIXTURES` 无条件），
# 于是「换一本书跑盲测」会**静默地**拿内嵌的反脆弱册 fixture 出报告 —— 产出的是**另一本书的证据**。
# 修法：① 真实现 --prompts；② 词表语料必须由 --skills-root 显式给出并与 prompts 同批（否则拒跑）；
#       ③ 输出目录 --out（不再写死在工具目录，避免污染脚本同步/打包新鲜度闸）；④ 语料来源写进产物。
def parse_args():
    a = sys.argv[1:]
    out = {}
    for k in ('--prompts', '--skills-root', '--out'):
        if k in a:
            i = a.index(k) + 1
            if i >= len(a):
                sys.exit('🔴 %s 缺少取值' % k)
            out[k[2:].replace('-', '_')] = a[i]
    return out


def build_lexicons_from_root(root):
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
        # 目标件别名（A-37）：本库 test-prompts 用 expect_top1／owner_skill，投资册用 target
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
        second = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
        rivals = [s for s in tops if s != (tops[0] if tops else None) and scores[s] >= best * 0.6] if tops else []
    else:
        rivals = []
    tie = best > 0 and any(s != (tops[0] if tops else None) and scores[s] == best for s in tops)
    if red:
        verdict = "redline-decline"
        needs_llm = False  # 判停本身机器即可给（红灯），语义复核可选
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


def main():
    args = parse_args()
    if bool(args.get('prompts')) != bool(args.get('skills_root')):
        sys.exit('🔴 --prompts 与 --skills-root 必须成对给出（A-37：只给 prompts ⇒ 词表仍取自**内嵌的另'
                 '一本书**语料，会静默产出跨书假证据）')
    if args.get('prompts'):
        prompts = load_prompts(args['prompts'])
        psrc = args['prompts']
        lexicons = build_lexicons_from_root(args['skills_root'])
        lsrc = args['skills_root']
        if not lexicons:
            sys.exit('🔴 --skills-root 下未找到任何 <slug>/SKILL.md：%s' % lsrc)
        targets = {p['target'] for p in prompts if p.get('target')}
        miss = sorted(targets - set(lexicons))
        if miss:
            sys.exit('🔴 prompts 的 target 不在词表语料内：%s ⇒ **语料不匹配**（A-37），拒绝产出'
                     '（词表语料：%s）' % (miss, sorted(lexicons)[:8]))
    else:
        prompts, psrc = FIXTURES, '内嵌 fixture（反脆弱册 AD/OC 12 题）'
        lexicons, lsrc = build_lexicons(), '内嵌 BOOKS（投资蒸馏三册）'
    outdir = args.get('out') or HERE
    if not os.path.isdir(outdir):
        sys.exit('🔴 --out 不是目录：%s' % outdir)
    print('# 语料来源：prompts=%s ｜ 词表=%s ｜ 共 %d 题' % (psrc, lsrc, len(prompts)))
    print('# ⚠ 红线词表口径：内嵌 REDLINE＝**投资域（时点预测）**专用；'
          + ('本次为**外域语料**，判停红线须另备域内词表（本域用 tools/blindtest_generic.py），'
             '本行的 redline 计数**不得**当作判停结论。' if args.get('prompts') else '内嵌 fixture 同域，可用。'))
    rows = []
    for fx in prompts:
        r = judge_prompt(fx["prompt"], lexicons)
        r.update({"id": fx["id"], "target": fx["target"], "judge_class": fx["judge_class"],
                  "prompt": fx["prompt"]})
        rows.append(r)
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
    with open(os.path.join(outdir, "blindtest-mock-v1.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    # ---- md ----
    L = []
    A = L.append
    A("# 盲测闸 词表命中模拟器 v1 —— 机器初判（%d 题）" % len(rows))
    A("")
    A("> 语料来源：prompts=`%s` ｜ 词表=`%s`" % (psrc, lsrc))
    A("> 角色：盲测 LLM judge 的机器初判层（词表命中，零 LLM）")
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
        A("| %s | %s | %s | %s | %s | %s |" % (r["id"], r["judge_class"], r["verdict"], r["needs_llm"], top_txt, rival_txt))
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
    A("## 四、结论（v1 数据）")
    A("")
    A("- 机器初判层的价值=先筛：机械可判的路由（verdict=mechanical-clear 且 top1=目标）可免 LLM；其余（无锚/弱锚/邻族抢单）才进 LLM 语义判定，输入从 12 条全量降到 needs_llm 子集。")
    A("- 与 judge 盲测报告的印证与差异：AD-3/OC-5 无（弱）字面锚 → needs_llm（与报告边界结论一致）；OC-4 现词表已含 重仓/回测/年年正收益/历史数据（报告改进建议 1 已落地）→ 机器机械命中；AD-4「值不值得追」与触发词「值不值得追新」差一字漏字面命中（词元化留 v2）。")
    A("- 已知缺口（v2 候选）：词表只取 description 触发词段，未用 何时用/何时不用 语义区；同义改写（保健品/体检 vs 过度保护）命中不了；判停红线目前只覆盖时点类。")
    A("")
    md = "\n".join(L)
    md_path = os.path.join(outdir, "盲测词表模拟器v1-试点报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(json.dumps(stats, ensure_ascii=False))
    for r in rows:
        print("%s %-7s %-20s llm=%-5s top=%s" % (r["id"], r["judge_class"], r["verdict"], r["needs_llm"], (r["top"] or "—")[:26]))
    print("md ->", md_path)


if __name__ == "__main__":
    main()