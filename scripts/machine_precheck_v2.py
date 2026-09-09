# -*- coding: utf-8 -*-
"""9 维机器初评器 v2（试点 A 优化轮 · 零 LLM 本地 py）

v2 = v1 + (1) d6 池 id 实存自动核验（家族约定文件自动发现）
        (2) test-prompts.json 盘点（供 d8 judge 快速定位）
        (3) runtime 红灯扫描（darwin gate 项）
        (4) 验证面扩展：对比器 v2 跑 6 技能（rse/trv/afd/oc/lvs/rp）

对一份 SKILL.md 跑 9 维"机械层初评"：
- 只做可确定性判定的子规则（rubric 明文规则 + 枚举式关键词/行号证据）；
- 语义窄域（"步骤真可执行""描述含金量""冗余程度"等）不硬判，
  以 semantic_only_notes 显式交给 LLM judge 复核；
- 输出 machine-report-<slug>.json：逐维 {coverage, checks[{rule,status,evidence,deduct}],
  machine_deduct, machine_raw, semantic_only_notes}。

幅度基线（v1 未校准，只做"方向+候选"级初评）：
- 扣分触发项默认各 -1；rubric 明示幅度的按 rubric（d5 软化词>=3 -> -3；d9 无反例章 -> -3+）。
- 每条 machine_raw = 10 - machine_deduct（仅当该维 coverage != none 时给出），供与
  judge raw 对拍看"方向一致性与幅度漂移"，不冒充校准后分数。

用法：
  python machine_precheck_v1.py <SKILL.md 路径> [--out <json 路径>]
"""
import os
import re
import sys
import json
import glob as _g

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 蒸馏工作区

# ----------------------------- 工具 -----------------------------

def read_lines(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return text, text.splitlines()

def frontmatter_meta(lines):
    """解析 --- ... --- frontmatter，返回 {key: value} 与 description 原文。"""
    meta = {}
    if not lines or lines[0].strip() != "---":
        return meta, ""
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return meta, ""
    key = None
    for ln in lines[1:end]:
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", ln, re.S)
        if m:
            if key:
                meta[key] = meta.get(key, "").rstrip()
            key, val = m.group(1), m.group(2)
            meta[key] = val
        elif key and ln.startswith((" ", "\t")):
            meta[key] = meta.get(key, "") + " " + ln.strip()
    if key:
        meta[key] = meta.get(key, "").rstrip()
    desc = meta.get("description", "").strip()
    if desc.startswith('"') and desc.endswith('"') and len(desc) >= 2:
        desc = desc[1:-1]
    return meta, desc

def find_section(lines, head_re):
    """返回 0-based [start,end) 行区间；找不到返回 None。"""
    start = None
    for i, ln in enumerate(lines):
        if re.match(head_re, ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^##\s+", lines[j]):
            end = j
            break
    return start, end

def hits(lines, start, end, pattern, flag=re.I):
    rx = re.compile(pattern, flag)
    out = []
    for i in range(start, end):
        ln = lines[i]
        if rx.search(ln):
            t = ln.strip()
            if len(t) > 110:
                t = t[:107] + "..."
            out.append({"line": i + 1, "text": t})
    return out

def count_in(lines, start, end, pattern, flag=re.I):
    rx = re.compile(pattern, flag)
    return sum(1 for i in range(start, end) if rx.search(lines[i]))

# ----------------------------- 词表 -----------------------------

AI_BANNED = ["说白了", "换句话说", "综上所述", "总而言之", "值得注意的是", "需要注意的是", "不难发现", "显而易见", "总的来说"]
SOFT_HARD = ["可以考虑", "根据情况", "灵活把握", "视情况而定", "灵活应用", "视条件而定"]
EMPTY_TAIL = ["灵活应用", "根据情况判断", "视情况而定", "灵活把握"]
POOL_FILE_RE = re.compile(r"candidates/[A-Za-z0-9_\-./]+\.md")
POOL_ID_RE = re.compile(r"(?<![A-Za-z0-9])(ce|pr|fw|ca|gl)(\d{2})")
ECHO_PHRASES = ["转专业帮助", "trader-discipline", "optionality-convexity", "fund-selector", "investing-mindset"]
FAM_FILE = {"ce": "counter-examples.md", "pr": "principles.md", "fw": "frameworks.md", "ca": "cases.md", "gl": "glossary.md"}
RT_TERMS = ["在 Claude Code", "Claude Code skill", "Claude Code 用户", "Cursor only", "Codex 中", r"~\\.claude/skills/", r"/plugin install\\b"]

RT_RX = re.compile("在 Claude Code|Claude Code skill|Claude Code 用户|Cursor only|Codex 中|~/" + chr(92) + ".claude/skills/|/plugin install" + chr(92) + "b")

# ----------------------------- 各维检查 -----------------------------

def check_d1(lines, meta, desc):
    checks, deduct = [], 0
    name = meta.get("name", "")
    if not name:
        checks.append({"id": "d1-c1", "rule": "name 存在且小写 kebab 规范", "status": "fail",
                       "evidence": [], "deduct": 2, "note": "frontmatter 缺 name"})
        deduct += 2
    else:
        ok = bool(re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name))
        checks.append({"id": "d1-c1", "rule": "name 小写 kebab 规范", "status": "pass" if ok else "fail",
                       "evidence": [{"line": 2, "text": "name: " + name}], "deduct": 0 if ok else 2,
                       "note": "" if ok else "name 建议小写连字符"})
        if not ok:
            deduct += 2
    n = len(desc)
    ev_len = [{"line": 3, "text": "description...(%d 字符)" % n}] if desc else []
    if n == 0:
        checks.append({"id": "d1-c2", "rule": "description 存在", "status": "fail", "evidence": ev_len,
                       "deduct": 2, "note": "缺 description"})
        deduct += 2
    elif n > 1024:
        checks.append({"id": "d1-c2", "rule": "description 字符数 <=1024（rubric 上限）", "status": "fail",
                       "evidence": [{"line": 3, "text": "desc_len=%d > 1024" % n}], "deduct": 1,
                       "note": "与 judge 扣分同源；幅度未校准（judge 示例曾按超限计 -1~-2）"})
        deduct += 1
    else:
        checks.append({"id": "d1-c2", "rule": "description 字符数 <=1024", "status": "pass",
                       "evidence": [{"line": 3, "text": "desc_len=%d <= 1024" % n}], "deduct": 0, "note": ""})
    missing = [k for k in ["何时用", "触发词"] if k not in desc]
    if missing:
        checks.append({"id": "d1-c3", "rule": "description 含标记词:何时用/触发词", "status": "warn",
                       "evidence": [{"line": 3, "text": "missing=" + ",".join(missing)}], "deduct": 0,
                       "note": "标记词缺失=语义存疑交 judge；机器不判'做什么'含金量"})
    else:
        checks.append({"id": "d1-c3", "rule": "description 含标记词:何时用/触发词", "status": "pass",
                       "evidence": [{"line": 3, "text": "含 何时用/触发词 标记"}], "deduct": 0, "note": ""})
    tail = desc[-30:] if desc else ""
    bad_tail = [w for w in EMPTY_TAIL if w in tail]
    if bad_tail:
        checks.append({"id": "d1-c4", "rule": "无'灵活应用/根据情况判断'式空话尾巴", "status": "fail",
                       "evidence": [{"line": 3, "text": "tail_hit=" + ",".join(bad_tail)}], "deduct": 2,
                       "note": "rubric d1 明示禁止"})
        deduct += 2
    else:
        checks.append({"id": "d1-c4", "rule": "无'灵活应用/根据情况判断'式空话尾巴", "status": "pass",
                       "evidence": [], "deduct": 0, "note": ""})
    semantic = ["description 是否真含'做什么'、内容与正文是否语义重复（机器不看，交 judge）"]
    return checks, min(deduct, 8), semantic

def check_d2(lines):
    seg = find_section(lines, r"^##\s*E")
    if seg is None:
        return [{"id": "d2-c1", "rule": "E 可执行步骤节存在", "status": "fail", "evidence": [],
                 "deduct": 3, "note": "找不到 ## E 节"}], 3, ["无 E 节"]
    start, end = seg
    ev_steps = hits(lines, start, end, r"步骤\s*[0-9０-９]")
    steps = set()
    tr = str.maketrans("０１２３４５６７８９", "0123456789")
    for h in ev_steps:
        m = re.search(r"步骤\s*([0-9０-９]+)", h["text"])
        if m:
            steps.add(int(m.group(1).translate(tr)))
    n_in = count_in(lines, start, end, r"输入")
    n_out = count_in(lines, start, end, r"输出")
    n_exit = count_in(lines, start, end, r"出口")
    n_act = count_in(lines, start, end, r"动作")
    checks, deduct = [], 0
    if len(steps) < 5:
        checks.append({"id": "d2-c1", "rule": "E 内有序号步骤 >=5 个", "status": "fail",
                       "evidence": ev_steps[:8], "deduct": 2, "note": "实际步骤数=%d" % len(steps)})
        deduct += 2
    else:
        checks.append({"id": "d2-c1", "rule": "E 内有序号步骤 >=5 个", "status": "pass",
                       "evidence": [{"line": ev_steps[0]["line"], "text": "found %d 个步骤" % len(steps)}],
                       "deduct": 0, "note": ""})
    io = {"输入": n_in, "动作": n_act, "输出": n_out, "出口": n_exit}
    if min(n_out, n_in, n_act) < 3 or n_exit < 2:
        checks.append({"id": "d2-c2", "rule": "每步有 输入/动作/输出/出口 字段规格", "status": "warn",
                       "evidence": [{"line": start + 1, "text": "io_counts=" + json.dumps(io, ensure_ascii=False)}],
                       "deduct": 0, "note": "字段标记不足；机器只数词频，交 judge 判颗粒度"})
    else:
        checks.append({"id": "d2-c2", "rule": "每步有 输入/动作/输出/出口 字段规格", "status": "pass",
                       "evidence": [{"line": start + 1, "text": "io_counts=" + json.dumps(io, ensure_ascii=False)}],
                       "deduct": 0, "note": ""})
    # d2-c3 逐步骤字段矩阵（v3.1 新增：只给 judge 语义证据，不扣分——捕捉步骤0 类缺输出字段的颗粒度问题）
    step_rows = []
    cur_step = None
    cur_txt = []
    def flush_step():
        nonlocal cur_step, cur_txt
        if cur_step is not None:
            txt = " ".join(cur_txt)
            step_rows.append((cur_step, txt))
        cur_step = None
        cur_txt = []
    for i in range(start, end):
        m = re.match(r"^[-*]?\s*\*\*步骤\s*([0-9０-９]+)", lines[i])
        if m:
            flush_step()
            cur_step = int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
            cur_txt = [lines[i]]
        elif cur_step is not None:
            cur_txt.append(lines[i])
    flush_step()
    miss_steps = []
    for sn, txt in step_rows:
        if ("输出" not in txt) or ("出口" not in txt):
            miss_steps.append(sn)
    if miss_steps:
        checks.append({"id": "d2-c3", "rule": "逐步骤 输入/输出/出口 字段齐全（矩阵）", "status": "warn",
                       "evidence": [{"line": start + 1, "text": "steps_missing_output_or_exit=" + ",".join(map(str, miss_steps))}],
                       "deduct": 0,
                       "note": "v3.1 机器证据：缺失输出/出口的步骤清单（judge 语义裁决是否扣分，如 rse 步骤0 先例）"})
    else:
        checks.append({"id": "d2-c3", "rule": "逐步骤 输入/输出/出口 字段齐全（矩阵）", "status": "pass",
                       "evidence": [], "deduct": 0, "note": "全部步骤含输出与出口字段"})
    semantic = ["步骤是否真可执行/输入输出字段颗粒度是否一致（rse judge 曾因步骤0 缺'输出'扣1；机器只给 d2-c3 矩阵证据，不扣分）"]
    return checks, deduct, semantic

def check_d3(lines):
    seg = find_section(lines, r"^##\s*E")
    if seg is None:
        return [{"id": "d3-c1", "rule": "失败模式编码节存在", "status": "fail", "evidence": [],
                 "deduct": 3, "note": "无 E 节"}], 3, []
    start, end = seg
    ev_fb = hits(lines, start, end, r"fallback|兜底|一旦|若|如果")
    ev_stop = hits(lines, start, end, r"判停")
    ev_ret = hits(lines, start, end, r"不辩论|回步骤|重跑")
    checks, deduct = [], 0
    fb_ok = len(ev_fb) >= 3 or (len([h for h in ev_fb if "fallback" in h["text"]]) >= 1 and len(ev_ret) >= 1)
    if not fb_ok:
        checks.append({"id": "d3-c1", "rule": "E 内有显式失败分支编码(fallback/若…则…/兜底)", "status": "fail",
                       "evidence": ev_fb[:5], "deduct": 3,
                       "note": "rubric: 只写正向缺失败分支扣 >=3；条件词命中=%d" % len(ev_fb)})
        deduct += 3
    else:
        checks.append({"id": "d3-c1", "rule": "E 内有显式失败分支编码(fallback/若…则…/兜底)", "status": "pass",
                       "evidence": ev_fb[:4], "deduct": 0, "note": ""})
    if not ev_stop:
        checks.append({"id": "d3-c2", "rule": "有 判停/命中即停 显式编码", "status": "fail",
                       "evidence": [], "deduct": 3, "note": "无判停分支"})
        deduct += 3
    else:
        checks.append({"id": "d3-c2", "rule": "有 判停/命中即停 显式编码", "status": "pass",
                       "evidence": ev_stop[:4], "deduct": 0, "note": ""})
    if not ev_ret:
        checks.append({"id": "d3-c3", "rule": "有恢复路径(回步骤/重跑/不辩论)", "status": "warn",
                       "evidence": [], "deduct": 0, "note": "机器未命中恢复词，交 judge 复核"})
    else:
        checks.append({"id": "d3-c3", "rule": "有恢复路径(回步骤/重跑/不辩论)", "status": "pass",
                       "evidence": ev_ret[:3], "deduct": 0, "note": ""})
    semantic = ["失败分支是否语义充分（rubric: 只写正向缺失败分支扣>=3，需 judge 语义裁决）"]
    return checks, deduct, semantic

def check_d4(lines):
    n_red = sum(1 for ln in lines if "\U0001F534" in ln)
    n_ck = sum(1 for ln in lines if re.search(r"CHECKPOINT|STOP", ln))
    n_confirm = count_in(lines, 0, len(lines), r"确认|呈请")
    checks, deduct = [], 0
    if n_red >= 1 and (n_ck >= 1 or n_confirm >= 1):
        ev = hits(lines, 0, len(lines), "\U0001F534" + r"\s*(CHECKPOINT|判停)")
        checks.append({"id": "d4-c1", "rule": "显性检查点标记 🔴/STOP/CHECKPOINT 存在（rubric: 仅'如果...建议'不算）",
                       "status": "pass", "evidence": ev[:4], "deduct": 0,
                       "note": "red=%d ck=%d" % (n_red, n_ck)})
    else:
        checks.append({"id": "d4-c1", "rule": "显性检查点标记 🔴/STOP/CHECKPOINT 存在",
                       "status": "fail", "evidence": [], "deduct": 4,
                       "note": "机器未命中显性标记；仅软措辞=不达标"})
        deduct += 4
    semantic = ["检查点是否在'关键决策前'、用户介入粒度是否够（rse judge 曾因唯一确认点扣1；机器不判）"]
    return checks, deduct, semantic

def check_d5(lines):
    end = len(lines)
    checks, deduct = [], 0
    soft_hits = []
    for i in range(end):
        for w in SOFT_HARD:
            if w in lines[i]:
                t = lines[i].strip()
                if len(t) > 110:
                    t = t[:107] + "..."
                soft_hits.append({"line": i + 1, "text": t, "word": w})
    seen = {}
    for h in soft_hits:
        seen.setdefault(h["word"], []).append(h["line"])
    hard_total = sum(len(v) for v in seen.values())
    if hard_total >= 3:
        checks.append({"id": "d5-c1", "rule": "软化空话词(硬词表) <3 处", "status": "fail",
                       "evidence": soft_hits[:6], "deduct": 3,
                       "note": "rubric 明示:>=3 处扣 >=3"})
        deduct += 3
    elif hard_total > 0:
        checks.append({"id": "d5-c1", "rule": "软化空话词 <3 处", "status": "warn",
                       "evidence": soft_hits[:6], "deduct": 0,
                       "note": "1-2 处 rubric 未给幅度；列出候选交 judge"})
    else:
        checks.append({"id": "d5-c1", "rule": "软化空话词(硬词表) 0 命中", "status": "pass",
                       "evidence": [], "deduct": 0, "note": ""})
    n_tbl = count_in(lines, 0, end, r"^\|.*\|")
    n_ex = count_in(lines, 0, end, r"示例|话术|模板")
    if n_tbl >= 5 and n_ex >= 2:
        checks.append({"id": "d5-c2", "rule": "可执行正证据:表格/示例/模板", "status": "pass",
                       "evidence": [{"line": 1, "text": "tables=%d examples=%d" % (n_tbl, n_ex)}],
                       "deduct": 0, "note": ""})
    else:
        checks.append({"id": "d5-c2", "rule": "可执行正证据:表格/示例/模板", "status": "warn",
                       "evidence": [], "deduct": 0, "note": "机器只见计数，参数含金量交 judge"})
    semantic = ["'建议'类词的语境豁免（审计对象语义/示例引语内不算软化）、超长单行排版对可执行性的影响（rse judge 曾扣1；机器不判）"]
    return checks, deduct, semantic

def check_d6(lines, meta, skill_path):
    checks, deduct = [], 0
    sp = os.path.abspath(skill_path)
    parts = sp.split(os.sep)
    book_base = None
    if "skills" in parts:
        idx = parts.index("skills")
        book_base = os.sep.join(parts[:idx])
    rel = meta.get("related_skills", "")
    slugs = sorted(set(re.findall(r"[a-z][a-z0-9-]+", rel)))
    slugs = [s for s in slugs if s not in ("skills", "slug") and len(s) > 2]  # v3.5: "slug" 为 YAML 注释元词，误提→d6-c1 假阳性
    found = set()
    for cand in _g.glob(os.path.join(BASE_DIR, "投资蒸馏", "**", "skills", "*", "SKILL.md"), recursive=True):
        found.add(os.path.basename(os.path.dirname(cand)))
    # v4.1 补丁(2026-09-12)：宿主技能目录并入 found，消除"投资家族占位"注释依赖（backward-compatible）
    host_skills = os.path.join(os.path.dirname(BASE_DIR), "金融投资", ".dsh", "skills")
    if os.path.isdir(host_skills):
        for _n in os.listdir(host_skills):
            if os.path.isdir(os.path.join(host_skills, _n)):
                found.add(_n)
    missing = [s for s in slugs if s not in found]
    family_hint = []
    real_missing = []
    for s in missing:
        # 粗略判断是否为"投资家族"占位：related 文本中该 slug 后面带（投资家族
        i = rel.find(s)
        after = rel[i + len(s):i + len(s) + 24] if i >= 0 else ""
        if "投资家族" in after or s in ("trader-discipline", "fund-selector", "investing-mindset"):
            family_hint.append(s)
        else:
            real_missing.append(s)
    if family_hint or real_missing:
        checks.append({"id": "d6-c1", "rule": "related_skills slug 全库实存", "status": "warn" if not real_missing else "fail",
                       "evidence": [{"line": 7, "text": "missing=" + ",".join(missing)}],
                       "deduct": len(real_missing),
                       "note": "投资家族占位(warn 不扣):" + ",".join(family_hint) + " 实缺:" + ",".join(real_missing)})
        deduct += len(real_missing)
    else:
        checks.append({"id": "d6-c1", "rule": "related_skills slug 全库实存", "status": "pass",
                       "evidence": [], "deduct": 0, "note": ""})
    refs = []
    for i, ln in enumerate(lines):
        for m in POOL_FILE_RE.finditer(ln):
            refs.append({"line": i + 1, "ref": m.group(0)})
    bad_refs = []
    if book_base:
        for r in refs:
            p = os.path.join(book_base, r["ref"].replace("/", os.sep))
            if not os.path.isfile(p):
                bad_refs.append(r)
    fam_used = set()
    fam_mapped = set()
    for ln in lines:
        for m in POOL_ID_RE.finditer(ln):
            fam_used.add(m.group(1))
        if "candidates/" in ln:
            for m in POOL_FILE_RE.finditer(ln):
                base_f = os.path.basename(m.group(0))
                fam_mapped.add({v: k for k, v in FAM_FILE.items()}.get(base_f, "ce"))  # v3.2: 按文件名反查族（旧版只认 ce 族→误 -3）
    # v3.5 fix (d6-c3 池族映射 bug)：族映射 = 内联引用 ∪ 磁盘自动发现；文件在但没内联=▲，文件不存在=🔴
    fam_on_disk = set()
    if book_base:
        for fam in fam_used:
            fn = FAM_FILE.get(fam)
            if fn and os.path.isfile(os.path.join(book_base, "candidates", fn)):
                fam_on_disk.add(fam)
    missing_file = sorted(fam_used - fam_on_disk)      # 真缺陷：用了族但池文件不存在
    inline_missing = sorted(fam_on_disk - fam_mapped)  # 文件在但文本没明文引用(▲级)
    if refs:
        checks.append({"id": "d6-c2", "rule": "文本内 candidates/*.md 引用可达", "status": "fail" if bad_refs else "pass",
                       "evidence": refs[:5], "deduct": len(bad_refs),
                       "note": "bad_refs=" + ",".join(r["ref"] for r in bad_refs)})
        deduct += len(bad_refs)
    if missing_file:
        checks.append({"id": "d6-c3", "rule": "池代号族均有对应池文件(磁盘自动发现)", "status": "fail",
                       "evidence": refs[:5], "deduct": len(missing_file),
                       "note": "missing_file=" + ",".join(missing_file) + "；池文件不存在，id 无法实存核验"})
        deduct += len(missing_file)
    else:
        checks.append({"id": "d6-c3", "rule": "池代号族均有对应池文件", "status": "pass", "evidence": [], "deduct": 0,
                       "note": ("内联映射缺但文件在: " + ",".join(inline_missing)) if inline_missing else ""})
    # c5 池 id 实存核验（v2 新增：按家族约定文件自动发现，SKILL 引用 id 是否在池文件内存在）
    id_report = []
    if book_base:
        for fam in sorted(fam_used):
            fn = FAM_FILE.get(fam)
            if not fn:
                continue
            p = os.path.join(book_base, "candidates", fn)
            if not os.path.isfile(p):
                id_report.append({"family": fam, "file": fn, "file_exists": False, "used": 0, "missing_ids": []})
                continue
            with open(p, encoding="utf-8") as fh:
                pool_text = fh.read()
            frx = re.compile("(?<![A-Za-z0-9])" + fam + r"(\d{2})")
            pool_ids = set(int(m.group(1)) for m in frx.finditer(pool_text))
            srx = re.compile("(?<![A-Za-z0-9])" + fam + r"(\d{2})")
            used_ids = set(int(m.group(1)) for m in srx.finditer("\n".join(lines)))
            miss = sorted(used_ids - pool_ids)
            id_report.append({"family": fam, "file": fn, "file_exists": True, "used": len(used_ids), "missing_ids": miss})
    if id_report:
        bad = [x for x in id_report if not x["file_exists"] or x["missing_ids"]]
        checks.append({"id": "d6-c5", "rule": "池 id 在对应池文件内实存（自动发现族文件，v2 新增）",
                       "status": "fail" if bad else "pass",
                       "evidence": [{"line": 1, "text": json.dumps(id_report, ensure_ascii=False)}],
                       "deduct": 0,
                       "note": "缺 id 或文件缺失: " + ("无" if not bad else str(bad))})
    # c4 家族路由实存核验（信息性：trv judge 卡曾称投资家族路由"全库不存在"，实存于其他册）
    fam_locs = {}
    for cand in _g.glob(os.path.join(BASE_DIR, "投资蒸馏", "**", "skills", "*", "SKILL.md"), recursive=True):
        s = os.path.basename(os.path.dirname(cand))
        if s in ("trader-discipline", "fund-selector", "investing-mindset"):
            fam_locs.setdefault(s, []).append(os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(cand)))))
    if fam_locs:
        txt = "; ".join("%s@%s" % (k, ",".join(v)) for k, v in sorted(fam_locs.items()))
        checks.append({"id": "d6-c4", "rule": "家族路由实存核验（信息性）", "status": "pass",
                       "evidence": [], "deduct": 0,
                       "note": "实存=" + txt + "；judge 若称全库不存在则与磁盘不符（口径疑为单册内）"})
    semantic = ["'代号生态真实可达但粒度不够直接可达'的行文判断（judge 语义）", "家族式简写路径约定是否可接受"]
    return checks, min(deduct, 3), semantic

def check_d7(lines):
    checks, deduct = [], 0
    rseg = find_section(lines, r"^##\s*R")
    def is_quote_line(i, ln):
        if rseg is not None and rseg[0] <= i < rseg[1]:
            return True
        if ln.lstrip().startswith(">"):
            return True
        if "「" in ln and "」" in ln:
            return True
        return False
    hits_all = []
    for i, ln in enumerate(lines):
        if is_quote_line(i, ln):
            continue
        for w in AI_BANNED:
            if w in ln:
                hits_all.append({"line": i + 1, "text": ln.strip()[:110], "word": w})
    if hits_all:
        checks.append({"id": "d7-c1", "rule": "AI 腔禁词 0 命中（rubric: 一处扣1）", "status": "fail",
                       "evidence": hits_all[:6], "deduct": min(3, len(hits_all)),
                       "note": "禁词命中 %d 处" % len(hits_all)})
        deduct += min(3, len(hits_all))
    else:
        checks.append({"id": "d7-c1", "rule": "AI 腔禁词 0 命中", "status": "pass", "evidence": [], "deduct": 0, "note": ""})
    need = {"## R": False, "## I": False, "## E": False, "## B": False}
    for ln in lines:
        for k in need:
            if ln.startswith(k):
                need[k] = True
    has_update = any("数据更新指引" in ln for ln in lines)
    if all(need.values()) and has_update:
        checks.append({"id": "d7-c2", "rule": "分节骨架齐全(R/I/E/B/数据更新指引)", "status": "pass",
                       "evidence": [], "deduct": 0, "note": ""})
    else:
        checks.append({"id": "d7-c2", "rule": "分节骨架齐全(R/I/E/B/数据更新指引)", "status": "warn",
                       "evidence": [], "deduct": 0,
                       "note": "missing=" + ",".join(k for k, v in need.items() if not v)})
    echo = {}
    for i, ln in enumerate(lines):
        for ph in ECHO_PHRASES:
            if ph in ln:
                echo.setdefault(ph, []).append(i + 1)
    echo_warn = {k: v for k, v in echo.items() if len(v) >= 4}
    if echo_warn:
        checks.append({"id": "d7-c3", "rule": "回声计数（信息性）", "status": "warn",
                       "evidence": [{"line": v[0], "text": "%s 出现 %d 行: %s" % (k, len(v), ",".join(map(str, v)))} for k, v in list(echo_warn.items())[:3]],
                       "deduct": 0, "note": "交 judge 判断是否构成冗余扣分"})
    semantic = ["AI 腔词在原文引文/用户引句内的豁免（机器已跳过 R 段/「」引句/>块引用）",
                "层次紧凑性/冗余回声（trv judge 曾因 4 处路由回声扣1；机器只报回声计数不扣）",
                "文件体积/超长行对维护与注入的代价（rse judge 曾扣1；机器不判）"]
    return checks, deduct, semantic

def check_d9(lines):
    checks, deduct = [], 0
    seg_b4 = find_section(lines, r"^###\s*B4")
    ev_b4 = []
    if seg_b4:
        ev_b4 = hits(lines, seg_b4[0], seg_b4[1], r"^-")
    has_speed = any("判停速查" in ln for ln in lines)
    has_b3 = find_section(lines, r"^###\s*B3") is not None
    has_nodo = any(("不要做" in ln or "反例" in ln) for ln in lines)
    if seg_b4 and has_nodo:
        checks.append({"id": "d9-c1", "rule": "独立'不要做'反例章(B4/反例池)存在", "status": "pass",
                       "evidence": ev_b4[:5], "deduct": 0, "note": "B4 反例条数=%d" % len(ev_b4)})
    else:
        checks.append({"id": "d9-c1", "rule": "独立'不要做'反例章存在（rubric: 只写正向扣>=3）", "status": "fail",
                       "evidence": [], "deduct": 3, "note": "未命中 B4/反例"})
        deduct += 3
    if has_speed:
        checks.append({"id": "d9-c2", "rule": "红灯动作速查(判停速查)单独成节", "status": "pass",
                       "evidence": hits(lines, 0, len(lines), r"判停速查")[:2], "deduct": 0, "note": ""})
    else:
        checks.append({"id": "d9-c2", "rule": "红灯动作速查单独成节", "status": "warn", "evidence": [], "deduct": 0,
                       "note": "未命中'判停速查'专节，交 judge 复核"})
    if has_b3:
        checks.append({"id": "d9-c3", "rule": "限定语纪律(B3)存在", "status": "pass", "evidence": [], "deduct": 0, "note": ""})
    semantic = ["反例条目语义质量/与正文咬合（机器只查存在性与条数）"]
    return checks, deduct, semantic

# ----------------------------- 主流程 -----------------------------

DIM_W = {"d1": 7, "d2": 12, "d3": 12, "d4": 6, "d5": 18, "d6": 4, "d7": 12, "d8": 23, "d9": 6}
DIM_NAME = {"d1": "Frontmatter 质量", "d2": "工作流清晰度", "d3": "失败模式编码", "d4": "检查点设计",
            "d5": "可执行具体性", "d6": "资源整合度", "d7": "整体架构", "d8": "实测表现", "d9": "反例与黑名单"}
COVER = {"d1": "partial", "d2": "partial", "d3": "partial", "d4": "partial", "d5": "partial",
         "d6": "partial", "d7": "partial", "d8": "none", "d9": "full"}

def run(skill_path):
    text, lines = read_lines(skill_path)
    meta, desc = frontmatter_meta(lines)
    slug = os.path.basename(os.path.dirname(os.path.abspath(skill_path)))
    fns = {
        "d1": lambda: check_d1(lines, meta, desc),
        "d2": lambda: check_d2(lines),
        "d3": lambda: check_d3(lines),
        "d4": lambda: check_d4(lines),
        "d5": lambda: check_d5(lines),
        "d6": lambda: check_d6(lines, meta, skill_path),
        "d7": lambda: check_d7(lines),
        "d8": lambda: ([], 0, ["d8=运行期实测(full_test/dry_run)，机器初评不参与；judge 保留此维"]),
        "d9": lambda: check_d9(lines),
    }
    dims = {}
    for d in ["d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9"]:
        checks, deduct, sem = fns[d]()
        cov = COVER[d]
        dims[d] = {
            "dim": d, "name": DIM_NAME[d], "weight": DIM_W[d], "coverage": cov,
            "checks": checks, "machine_deduct": deduct,
            "machine_raw": None if cov == "none" else max(1, 10 - deduct),
            "semantic_only_notes": sem,
        }
    machine_static = sum(dims[d]["machine_raw"] * DIM_W[d] for d in dims if dims[d]["machine_raw"] is not None) / 10.0
    # v2: test-prompts 盘点 + runtime 红灯扫描（信息性，进 machine-report）
    skill_dir = os.path.dirname(os.path.abspath(skill_path))
    tp = {"exists": False}
    tp_path = os.path.join(skill_dir, "test-prompts.json")
    if os.path.isfile(tp_path):
        try:
            with open(tp_path, encoding="utf-8") as fh:
                _d = json.load(fh)
            ids = [str(x.get("id")) for x in _d if isinstance(x, dict) and "id" in x]
            tp = {"exists": True, "count": len(_d) if isinstance(_d, list) else None, "ids": ids[:16]}
        except Exception as exc:
            tp = {"exists": True, "parse_error": str(exc)}
    rt = [{"line": i + 1, "text": ln.strip()[:100]} for i, ln in enumerate(lines) if RT_RX.search(ln)]
    report = {
        "schema": "machine-precheck-v2",
        "skill": slug,
        "file": os.path.abspath(skill_path),
        "lines": len(lines),
        "bytes": len(text.encode("utf-8")),
        "test_prompts": tp,
        "runtime_red_scan": {"hits": len(rt), "evidence": rt[:6]},
        "dims": dims,
        "summary": {
            "machine_covered_weight": 77,
            "static_weight_excl_d8": 77,
            "machine_static_score": round(machine_static, 2),
        },
    }
    return report

def main():
    if len(sys.argv) < 2:
        print("usage: python machine_precheck_v1.py <SKILL.md> [--out out.json]")
        sys.exit(2)
    skill_path = sys.argv[1]
    report = run(skill_path)
    out = None
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    if out is None:
        slug = report["skill"]
        out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(skill_path)), "..", "..", "machine-report-" + slug + ".json"))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("OK", report["skill"], "machine_static=%.2f" % report["summary"]["machine_static_score"], "->", out)

if __name__ == "__main__":
    main()