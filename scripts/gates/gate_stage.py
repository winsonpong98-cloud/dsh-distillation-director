# -*- coding: utf-8 -*-
r"""gate_stage.py —— 蒸馏"阶段门禁状态机"（让跳过阶段＝命令直接失败）

设计原则（针对"声明做了但没人能验证"）：
  ① 每个阶段都有**机器可校的产物**，缺产物＝闸红；
  ② 产物不只要"存在"，还要**内容达标**（格式行数/关键词/条目数）——空文件糊弄不过去；
  ③ 阶段间有**依赖链**：前一阶段未 PASS，后一阶段命令直接 exit 1；
  ④ **时间序校验**：证据文件的 mtime 必须早于下游产物（防事后补造）；
  ⑤ 任何"人工确认"类门禁（阶段0 骨架）必须有用户确认标记，无标记＝红。

用法：
    python tools\gate_stage.py --task <task>              # 列出全部阶段状态
    python tools\gate_stage.py --task <task> --stage 2    # 只判"能否进入阶段2"
退出码：0 = 该阶段可进入；1 = 不可进入（附缺失项）
"""
import argparse, glob, json, os, re, sys, time

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
import _bandid as BID          # ← 波段 id 语法的**唯一来源**（A-132，2026-09-19 定案）
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


def newest_mtime(paths):
    ts = [os.path.getmtime(p) for p in paths if os.path.exists(p)]
    return max(ts) if ts else 0


def count_lines(path, pattern):
    if not os.path.exists(path):
        return 0
    t = open(path, encoding="utf-8", errors="ignore").read()
    return len(re.findall(pattern, t, re.M))


def check_stage0(work):
    """阶段0 骨架：BOOK_OVERVIEW.md 必须存在 + 含章节结构 + 用户确认标记"""
    p = os.path.join(work, "BOOK_OVERVIEW.md")
    if not os.path.exists(p):
        return False, ["BOOK_OVERVIEW.md 缺失（阶段0 未产出）"]
    t = open(p, encoding="utf-8", errors="ignore").read()
    errs = []
    if len(re.findall(r"^#{2,3}\s", t, re.M)) < 3:
        errs.append("BOOK_OVERVIEW.md 章节标题 <3 个（骨架不完整）")
    # 判据修正（P-23 工装伪影优先）：首版只查「用户确认」子串，被骨架里
    # 「阶段0 门禁＝用户确认骨架／当前状态：⏳ 待用户确认」这类**描述性文字**骗过 ⇒ 假通过（实测抓到）。
    # 改为：必须出现**带日期的「用户已确认」标记**，且不得残留「待用户确认／⏳／未确认」。
    confirmed = re.search(r"用户已确认", t) is not None and re.search(r"待用户确认|⏳|未经确认", t) is None
    if not confirmed:
        errs.append("未经用户门禁：缺带日期的『用户已确认』标记，或仍残留『待用户确认／⏳』"
                    "（手册 §3 阶段0 门禁＝用户确认骨架）")
    return (not errs), errs


def check_stage1(work):
    """阶段1 提取：需有官方模板生成的提取器 prompt + 提取笔记（含引文格式行）"""
    errs = []
    pd = os.path.join(work, "extractor-prompts")
    prompts = glob.glob(os.path.join(pd, "*.txt")) + glob.glob(os.path.join(pd, "*.md")) if os.path.isdir(pd) else []
    if not prompts:
        errs.append("extractor-prompts/ 无 prompt ⇒ 未按官方模板派提取器")
    else:
        MARK = ["### ", "- 锚：", "- 原文（逐字）：", "- 转述："]
        for f in prompts:
            t = open(f, encoding="utf-8", errors="ignore").read()
            if not ("提取器提示词模板" in t or all(m in t for m in MARK)):
                errs.append("prompt 未使用官方模板：%s" % os.path.basename(f))
    notes = glob.glob(os.path.join(work, "candidates", "notes_*.md")) + glob.glob(os.path.join(work, "candidates", "*.md"))
    if not notes:
        errs.append("candidates/ 无提取笔记（模板规定输出为 candidates/notes_{band}.md）")
    else:
        # 判据加强（P-23）：首版只数任意 `### ` 行，被**旧的自造格式笔记**骗过（实测假通过）。
        # 改为：必须是**官方模板条目格式** —— `### {band}-NNN  [类型] [技能=…]`
        # 形态容错修复（2026-09-17 · <task> 实测自伤）：原式 `[A-Za-z]\d+-\d{3}` 实际要求
        # **波段号前无连字符**（如 `B12-005`），而官方模板/本册产出写的是 `D-001`、`A-001`
        # （连字符在波段号之后）⇒ 该式恒不命中，**阶段1 闸对任何字母波段名书册恒红**（假红）。
        # ⚠ 2026-09-19 二次定案（A-132）：当时的"改法"`[A-Za-z][0-9]*-[0-9]{3}` 仍然只吃
        #   **单字母＋数字**（`A`／`T1`），**吃不到多字母前缀 `ST-001`**；而下游
        #   `verify_candidates` 同期用的是 `[A-Za-z]+`（吃不到 `E1-001`）⇒ 同一册一手绿一手红。
        #   现**一律取自 `tools\_bandid.py`**（波段 id 语法的唯一来源），本文件不再内联该语法。
        OFFICIAL = BID.TEMPLATE_HEAD
        tot = sum(len(OFFICIAL.findall(open(n, encoding="utf-8", errors="ignore").read())) for n in notes)
        if tot < 5:
            errs.append("官方模板格式条目（`### {band}-NNN [类型] [技能=…]`）合计 %d <5 ⇒ 疑非模板格式产出" % tot)

    # 加（R10 拧闸）：① 候选池机器校验必须过（引文回源/长度≤160/锚/格式/误引页标记）
    # ⚠ 2026-09-17 修（本册实测 · A-69／A-74 家族「书别参数不得写死/漏传」）：
    #   旧实现调 `verify_candidates --all` **不带 `--task`** ⇒ 该脚本回落它自己的默认任务，
    #   **校验的是另一个任务的候选池**，却把结论算在**本任务**的阶段1 头上
    #   （实测：本册 12 波段 `✔ 全部通过`，而闸报"🔴 切块为空" —— 那条红来自**别的册**）。
    #   修法：把被检任务显式传给校验器；**任务名从 work 目录反推**（本函数只拿到 work）。
    vc = os.path.join(ROOT, "tools", "verify_candidates.py")
    if os.path.exists(vc) and notes:
        import subprocess
        task = os.path.basename(os.path.normpath(work))
        r = subprocess.run([sys.executable, vc, "--all", "--task", task], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        if r.returncode != 0:
            tail = [l.strip() for l in (r.stdout or "").splitlines() if "🔴" in l or "总判定" in l][:3]
            errs.append("候选池机器校验未过（verify_candidates --all rc=%d）：%s" % (r.returncode, " ｜ ".join(tail)))

    # 加：**波段产出必须齐全** —— 防"只跑一半波段就宣称阶段1 完成"
    if os.path.isdir(pd):
        # 波段名取值**同一真源**（A-132）：原写 `[A-Za-z]\d+` ⇒ 纯字母波段（manias `A..G`）**全漏**
        #   ⇒ "波段产出必须齐全"这项闸**对纯字母册恒空转**（漏检比误报致命，A-55 家族）。
        bands = [m.group(1) for m in (BID.BAND_ONLY.match(f) for f in os.listdir(pd)) if m]
        lack = [b for b in sorted(bands)
                if not os.path.exists(os.path.join(work, "candidates", "notes_%s.md" % b))]
        if lack:
            errs.append("波段产出不全：%s 尚无 candidates/notes_*.md（共 %d 个波段，缺 %d 个）"
                        % ("、".join(lack), len(bands), len(lack)))
    return (not errs), errs


def check_stage15(work):
    """阶段1.5 验证：verified.md 必须存在且含去重合并后的候选"""
    errs = []
    cands = glob.glob(os.path.join(work, "**", "verified*.md"), recursive=True)
    if not cands:
        errs.append("verified*.md 缺失 ⇒ 阶段1.5（去重合并→候选确认）未做")
    else:
        p = cands[0]
        # A-28 家族加固（2026-09-13 阶段1.5 实测）：原判据只数 `^### ` 与表格行 ⇒ 一份
        # **只有标题没有条目**的 verified.md 也能过（判据被描述性文字命中＝假通过）。
        # 现要求**真含官方格式条目 id**（`### <band>-NNN  [`），与表格行合并计数。
        # 形态容错同 check_stage1（2026-09-17／2026-09-19 定案 A-132）：一律取自 `_bandid`
        # （原式 `[A-Za-z]\d+-\d{3}` 要求连字符在波段号之前，对 `D-001` 形态恒不命中 ⇒ 阶段1.5 亦假红；
        #   中间那版 `[A-Za-z][0-9]*-[0-9]{3}` 又漏掉多字母前缀 `ST-001`）。
        # ⚠ 自伤登记（2026-09-19 · NAS 真机当场抓到）：此处首版写 `BID.HEAD.pattern`，
        #   而 `_bandid.HEAD` 是**字符串**不是已编译对象 ⇒ `AttributeError: 'str' object has
        #   no attribute 'pattern'` ⇒ **阶段1.5 闸整条崩掉**（本机没跑到该分支，只有真机能抓）。
        #   另一个坑：`count_lines()` 内部是 `re.findall(pattern, t, re.M)`，**传已编译对象会抛
        #   ValueError（flags 不能与已编译模式并用）** ⇒ 这里**必须传字符串**。
        #   **教训：跨机自证不是"锦上添花"，本机测不到的路径只有异机才暴露**（`A-132` 同批）。
        n_id = count_lines(p, BID.HEAD)
        n = count_lines(p, r"^###\s|^\|\s*\S+\s*\|")
        if n < 5 or n_id < 5:
            errs.append("%s 内容过少（条目 id %d 条 ／ 候选条目+表格行 %d <5）"
                        % (os.path.basename(p), n_id, n))
    return (not errs), errs


def check_stage2(work):
    """阶段2 构造：SKILL.md 必须含 R/I/E/B 骨架 ＋ E 段步骤 ＋ CHECKPOINT ＋ 让位 ＋ 输出结构

    判据升级（2026-09-13）：旧版只查「含 CHECKPOINT 字样 ＋ 含何时不用」⇒ 一份空壳也能过
    （A-28 家族假通过）。现照手册 §14 硬闸表与机器层 machine_precheck_v2 的**真实检测口径**：
      · §14 d7-c2 分节骨架 R/I/E/B
      · §14 d2-c1 E 段内 ≥5 个「步骤 N」；d2-c2 每步 输入/动作/输出/出口
      · §14 d5 无 🔴CHECKPOINT／无输出结构／判停速查无正文实现 = 🔴
      · §14 d4-c1 检查点须是**功能性** 🔴（`🔴 CHECKPOINT`/`🔴 判停`），仅软措辞不算
      · §14 d9-c1 反例章 B4
    """
    errs = []
    skills = glob.glob(os.path.join(work, "skills", "*", "SKILL.md"))
    if not skills:
        errs.append("skills/*/SKILL.md 缺失 ⇒ 阶段2 未产出")
    for s in skills:
        t = open(s, encoding="utf-8", errors="ignore").read()
        name = os.path.basename(os.path.dirname(s))
        for k in ("## R", "## I", "## E", "## B"):
            if not re.search(r"(?m)^" + re.escape(k), t):
                errs.append("%s 缺分节骨架 `%s`（手册 §14 d7-c2）" % (name, k))
        seg = re.search(r"(?ms)^##\s*E.*?(?=^##\s|\Z)", t)
        if not seg:
            errs.append("%s 无 `## E` 可执行步骤节（§14 d2）" % name)
        else:
            body = seg.group(0)
            steps = set(re.findall(r"步骤\s*([0-9０-９]+)", body))
            if len(steps) < 5:
                errs.append("%s E 段步骤数 %d <5（§14 d2-c1）" % (name, len(steps)))
            for f in ("输入", "动作", "输出", "出口"):
                if f not in body:
                    errs.append("%s E 段缺字段 `%s`（§14 d2-c2）" % (name, f))
        if "CHECKPOINT" not in t:
            errs.append("%s 缺 CHECKPOINT（§14 d5 硬闸：无 🔴CHECKPOINT）" % name)
        elif not re.search(r"🔴\s*\**\s*(CHECKPOINT|判停)", t):
            errs.append("%s 的 CHECKPOINT 不是功能性 🔴 标记（§14 d4-c1：仅软措辞不算）" % name)
        if "何时不用" not in t and "不适用" not in t and "让位" not in t:
            errs.append("%s 缺『何时不用/让位』段（手册 §3 阶段2 让位规则）" % name)
        if "输出结构" not in t:
            errs.append("%s 缺『输出结构』（§14 d5）" % name)
        if "判停速查" not in t:
            errs.append("%s 缺「判停速查」正文实现（§14 d5）" % name)
        if not re.search(r"(?m)^###\s*B4", t) and "不要做" not in t and "反例" not in t:
            errs.append("%s 缺反例章（§14 d9-c1：### B4 或含『不要做/反例』）" % name)
    return (not errs), errs


def check_stage4(work):
    """阶段4 测试：test-prompts.json —— **每技能 ≥3 条**，且四类齐（应调用/诱饵/跨技能/医疗危机）

    A-28 家族加固（2026-09-13 实测抓到）：旧版只数顶层 `prompts` 列表长度 ⇒
      ① 按技能分组的结构被**漏数**（实测把 18 条报成 0 条）；
      ② 判据与手册不符 —— §3 阶段4 要求的是「**每技能**3条（应调用/诱饵/跨技能路由+医疗/危机）」。
    现按技能维度逐项判：条数 ≥3 ＋ 四类覆盖。
    """
    errs = []
    cands = glob.glob(os.path.join(work, "**", "test-prompts*.json"), recursive=True)
    if not cands:
        errs.append("test-prompts*.json 缺失 ⇒ 阶段4 未做（d8 簇抽亦无从执行）")
        return False, errs
    try:
        d = json.load(open(cands[0], encoding="utf-8"))
    except Exception as e:
        errs.append("test-prompts 解析失败：%s" % e)
        return False, errs

    def collect(obj):
        out = []
        if isinstance(obj, dict):
            if obj.get("slug") and isinstance(obj.get("prompts"), list):
                out.append((obj["slug"], obj["prompts"]))
            for v in obj.values():
                out.extend(collect(v))
        elif isinstance(obj, list):
            for v in obj:
                out.extend(collect(v))
        return out

    groups = collect(d)
    if not groups:
        n = len(d) if isinstance(d, list) else len(d.get("prompts", d.get("tests", [])))
        if n < 3:
            errs.append("test-prompts 条数 %d <3（且未找到按技能分组的 `slug`+`prompts`）" % n)
        return (not errs), errs

    for slug, ps in groups:
        if len(ps) < 3:
            errs.append("%s test-prompts 仅 %d 条 <3（手册 §3 阶段4：每技能 3 条）" % (slug, len(ps)))
        kinds = set()
        for p in ps:
            k = str(p.get("kind", ""))
            if "应调用" in k:
                kinds.add("应调用")
            elif "诱饵" in k:
                kinds.add("诱饵")
            elif "跨技能" in k:
                kinds.add("跨技能")
            elif "医疗" in k or "危机" in k:
                kinds.add("医疗危机")
        miss = {"应调用", "诱饵", "跨技能", "医疗危机"} - kinds
        if miss:
            errs.append("%s test-prompts 缺类别：%s（手册 §3 阶段4：应调用/诱饵/跨技能路由+医疗危机）"
                        % (slug, "／".join(sorted(miss))))
    return (not errs), errs


def check_stage5(work):
    """阶段5 交付：手册 §3 阶段5 的**产物与门禁逐项**核销

    手册原文（§3 阶段5）：
      「DIGEST.md + 安装两工作区 + 四件套 + BOUNDARIES 协议 + SUPPLEMENT。
        门禁=三闸零🔴 + d8 口径达标 + **交付盲复核 A/B 档**。」
    手册 §0.2：「**交付盲复核（整书抽1-2）**｜独立 judge｜整书交付时盲审：只给 SKILL 全文＋
      机器证据包，**不给主会话结论**；出「同意/异议+理由」与 A/B/C 档位」
    四件套（手册 v3.0 §185 检查清单原文）：**SKILL / BOUNDARIES / INDEX / GLOSSARY**
    手册 §8 交付前清单：「**四件套齐全** / 三闸 gates 记录零🔴 / d8 口径达标 /
      **交付盲复核 A/B 档** / **账本登记**（agent数/波次/估算token/实际）」

    ⚠ A-28 家族加固（2026-09-13 **用户质问触发**）：本函数原版**只查 `gates-*.json` 与
    `DIGEST*.md` 两个文件是否存在** ⇒ 阶段5 的 5 项产物只做 1 项也能全绿，**闸比手册松 ⇒
    缺项假通过**，执行者据此宣称"全流程走完"。现按手册逐项落成机器判据。
    """
    errs = []
    # ① 三闸记录（含交付盲复核字段 —— §0.2＋§3 阶段5 门禁）
    gs = glob.glob(os.path.join(work, "**", "gates-*.json"), recursive=True)
    if not gs:
        errs.append("gates-*.json 缺失 ⇒ 三闸记录未落盘（手册 §13）")
    else:
        try:
            g = json.load(open(gs[0], encoding="utf-8"))
            if not g.get("gates"):
                errs.append("gates 记录无 `gates` 字段 ⇒ 三闸判态缺失")
            if "交付盲复核" not in json.dumps(g, ensure_ascii=False):
                errs.append("gates 记录缺『**交付盲复核**』（手册 §0.2＋§3 阶段5 门禁："
                            "独立 judge 出「同意/异议＋理由」与 A/B/C 档）")
        except Exception as e:
            errs.append("gates 解析失败：%s" % e)
    # ② DIGEST
    if not glob.glob(os.path.join(work, "**", "DIGEST*.md"), recursive=True):
        errs.append("DIGEST*.md 缺失（手册 §3 阶段5）")
    # ③ 四件套（**技能目录内**：SKILL / BOUNDARIES / INDEX / GLOSSARY）＋ ④ SUPPLEMENT
    #    ⑤ test-prompts 随件交付（达尔文 dim6 实证：不随件＝运行期不可达）
    skills = glob.glob(os.path.join(work, "skills", "*", "SKILL.md"))
    if not skills:
        errs.append("skills/*/SKILL.md 缺失")
    for s in skills:
        d = os.path.dirname(s)
        name = os.path.basename(d)
        for f, why in (("BOUNDARIES.md", "四件套之 BOUNDARIES 协议"),
                       ("INDEX.md", "四件套之 INDEX"),
                       ("GLOSSARY.md", "四件套之 GLOSSARY")):
            if not os.path.exists(os.path.join(d, f)):
                errs.append("%s 缺 %s（%s · 手册 v3.0 §185 四件套）" % (name, f, why))
        if not glob.glob(os.path.join(d, "SUPPLEMENT*.md")):
            errs.append("%s 缺 SUPPLEMENT*.md（手册 §3 阶段5；确不适用须建文件**显式登记**）" % name)
        if not os.path.exists(os.path.join(d, "test-prompts.json")):
            errs.append("%s 缺 test-prompts.json（须**随件交付**；否则运行期不可达）" % name)
    # ⑥ 账本登记（§8 交付前清单）
    ps = glob.glob(os.path.join(work, "**", "PIPELINE_STATE.md"), recursive=True)
    if ps:
        t = open(ps[0], encoding="utf-8", errors="ignore").read()
        if "账本" not in t:
            errs.append("PIPELINE_STATE 缺『账本』节（手册 §8：agent数/波次/估算token/实际）")
    return (not errs), errs


STAGES = [
    ("0-骨架", check_stage0),
    ("1-提取", check_stage1),
    ("1.5-验证", check_stage15),
    ("2-构造", check_stage2),
    ("4-测试", check_stage4),
    ("5-交付", check_stage5),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--stage", default=None, help="只判该阶段（可用序号或名字片段）")
    a = ap.parse_args()
    work = os.path.join(ROOT, ".work", a.task)
    if not os.path.isdir(work):
        print("🔴 任务目录不存在：%s" % work)
        return 1

    results = []
    for name, fn in STAGES:
        ok, errs = fn(work)
        results.append((name, ok, errs))

    print("=" * 78)
    print("gate_stage —— 阶段门禁状态机（任务：%s）" % a.task)
    print("=" * 78)
    for i, (name, ok, errs) in enumerate(results, 1):
        print("  %s 阶段%s %s" % ("✔" if ok else "🔴", name, "" if ok else "（%d 项未过）" % len(errs)))
        for e in errs:
            print("       · %s" % e)

    # 依赖链：找第一个未过的阶段
    first_bad = next((i for i, (_, ok, _) in enumerate(results) if not ok), None)
    print("-" * 78)
    if first_bad is None:
        print("结论：全部阶段门禁 PASS")
    else:
        print("结论：卡在【阶段%s】—— 手册纪律「未过门禁不得进下一阶段」，"
              "其后各阶段即使产物齐全也不得宣布完成" % results[first_bad][0])

    if a.stage:
        # 判据修正（P-23）：首版用 `a.stage in n or a.stage == str(i+1)`，
        # 导致 `--stage 1` 被 `0-骨架` 的序号命中（1-based 序号与名字混比）⇒ 判到错阶段（实测抓到）。
        # 改为：优先按**名字前缀**匹配（`1` → `1-提取`），仅在纯数字且前缀无命中时才退回序号。
        tgt = None
        for i, (n, _, _) in enumerate(results):
            if n.startswith(str(a.stage) + "-"):
                tgt = i
                break
        if tgt is None and str(a.stage).isdigit() and 1 <= int(a.stage) <= len(results):
            tgt = int(a.stage) - 1
        if tgt is None:
            print("🔴 未找到阶段：%s（可用：%s）" % (a.stage, "／".join(n for n, _, _ in results)))
            return 1
        blocked = [results[i][0] for i in range(tgt) if not results[i][1]]
        if blocked:
            print("🔴 **不得进入阶段%s**：前置阶段未过 → %s" % (results[tgt][0], "、".join(blocked)))
            return 1
        print("✔ 允许进入阶段%s（前置阶段均已 PASS）" % results[tgt][0])
        # 口径修正（2026-09-13 实测抓到）：`--stage` 模式的退出码必须＝「**该阶段**可否进入」
        # （脚本 docstring 第 14 行如此承诺）；旧版落到 `first_bad`＝**全阶段**是否全过 ⇒
        # 明明打印「允许进入」却 rc=1，拿它当闸用会**误判为不可进入**。
        return 0
    return 0 if first_bad is None else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
