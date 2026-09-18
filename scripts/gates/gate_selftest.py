# -*- coding: utf-8 -*-
"""gate_selftest.py —— 门禁自证有效（防坑体系 层1 · 甲-A4）

原理：门禁脚本如果只在"好数据"上跑过，就只是"看起来在检查"。
本脚本构造**三份故意坏掉的样本**，要求门禁**必须检出**，否则门禁自己不合格：

  样本 1 · YAML 破损（`description: "…"` 内层含裸 ASCII 引号 → 前置元数据解析失败）→ `yaml_check_generic.cjs` 必须报异常
  样本 2 · desc 超限（>1024 字）→ 同一工具必须报 `>1024 件数：1`
  样本 3 · 表格管道数不一致（表头 3 列、某行 5 个管道）→ `check_md_tables.py` 必须报"不一致的块 1 个"

另附**正样本**（一份完全合规的技能）→ 必须全绿（防止门禁"一律报错"式的伪严格）。

用法：python tools\\gate_selftest.py
"""
import io
import os
import re
import sys
import json
import shutil
import subprocess

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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

GOOD = '---\nname: selftest-good\ndescription: "合规样本：用于验证门禁在正常数据上不会误报（≤1024 字、标记词齐：何时用／触发词）。"\n---\n\n正文。\n'
BROKEN_YAML = ('---\nname: selftest-broken-yaml\n'
               'description: "破损样本：这句里有裸 ASCII 引号 " 会让 YAML 解析失败 → 门禁必须检出。"\n'
               '---\n\n正文。\n')
OVER_LIMIT = ('---\nname: selftest-over-limit\ndescription: "' + ('超限' * 520) + ' 何时用：触发词：测试。"\n---\n\n正文。\n')
BAD_TABLE = '# 样本\n\n| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 1 | 2 | 3 | 4 | 5 |\n'


def run(cmd, cwd=None):
    # 防坑：cwd 指向不存在的目录时 Windows 抛 NotADirectoryError(267) ⇒ 裸栈。
    _cwd_ok = cwd if (cwd and os.path.isdir(cwd)) else None
    e = dict(os.environ)
    e['PYTHONIOENCODING'] = 'utf-8'
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=e, cwd=_cwd_ok)
    return r.returncode, (r.stdout or '')


def main():
    if not NODE or not JSDIR:
        print('🔴 缺 node 或 js-yaml，本门禁依赖它们的检查无法执行（**不给裸栈，给指引**）：')
        print('   NODE  = %s' % (NODE or '(未解析到)'))
        print('   JSDIR = %s' % (JSDIR or '(未解析到)'))
        print('   处置（任选其一）：')
        print('     ① 设环境变量 DSH_ENGINE_NODE=<...>\\node.exe（Linux 上为 node）与 DSH_JS_YAML_DIR=<...>\\js-yaml@x')
        print('     ② 跑 python tools\\init_workspace.py "<你的工作区根>" 自动探测并写入配置')
        print('   说明：DSH 用户通常两者都随引擎自带，正常情况不会走到这里。')
        return 1
    if os.path.isdir(SANDBOX):
        shutil.rmtree(SANDBOX)
    root = os.path.join(SANDBOX, 'skills')
    for slug, body in (('good', GOOD), ('broken-yaml', BROKEN_YAML), ('over-limit', OVER_LIMIT)):
        d = os.path.join(root, slug)
        os.makedirs(d, exist_ok=True)
        io.open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8', newline='\n').write(body)
    mdp = os.path.join(SANDBOX, 'bad-table.md')
    io.open(mdp, 'w', encoding='utf-8', newline='\n').write(BAD_TABLE)

    print('=== 门禁自证（甲-A4）：三份坏样本必须被检出，一份好样本必须放行 ===\n')
    ok = True

    rc, so = run([NODE, os.path.join(WORK, 'yaml_check_generic.cjs'), root, JSDIR], cwd=WORK)
    # ⚠ 断言要按"样本的真实性质"写：三份样本里只有 broken-yaml 是 **YAML 非法**；
    #   over-limit 是 **YAML 合法但 desc 超限**（由 >1024 计数项捕获），good 是合法。
    #   故期望是"通过 2 / 3"——首版我写成 1/3 是**断言错**（自证脚本当场抓出，已修正）。
    good_ok = bool(re.search(r'YAML 解析通过：2 / 3', so))
    broken_hit = 'broken-yaml' in so and '解析失败' in so
    over_hit = bool(re.search(r'>1024\s*件数：1', so))
    print('  %s 样本1 YAML 破损被检出（期望：解析失败名单含 broken-yaml）' % ('✔' if broken_hit else '🔴'))
    print('  %s 样本2 desc 超限被检出（期望：>1024 件数：1）' % ('✔' if over_hit else '🔴'))
    print('  %s 正样本放行（期望：YAML 解析通过 2 / 3 —— 仅 broken-yaml 非法）' % ('✔' if good_ok else '🔴'))
    if not (broken_hit and over_hit and good_ok):
        print('    ── 工具原始输出 ──')
        print('    ' + so.replace('\n', '\n    ')[:1200])
    ok &= broken_hit and over_hit and good_ok

    rc, so = run([sys.executable, os.path.join(WORK, 'check_md_tables.py'), mdp])
    tbl_hit = bool(re.search(r'不一致的块\s*1\s*个', so))
    print('  %s 样本3 表格管道数不一致被检出（期望：不一致的块 1 个）' % ('✔' if tbl_hit else '🔴'))
    if not tbl_hit:
        print('    ' + so.replace('\n', '\n    ')[:500])
    ok &= tbl_hit

    # ---- 样本4 · 执行单逐项闸（gate_checklist）：坏＝日期全空（36 项未记证据）必须 rc=1；
    #      好＝36 项日期齐＋产物在位必须 rc=0。
    #      ⚠ 诚实登记：好样本的产物文件按 gate_checklist.ARTIFACT_MAP 的清单创建——它验证的是
    #      **闸的判定逻辑**（解析/映射/豁免/退出码），不验证"映射与真实产物形态相符"；
    #      后者由 --report-only 对真实任务的校准＋新书首跑承担（§21.3 已登记）。 —— 2026-09-13 晚
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location('gate_checklist', os.path.join(TOOLS, 'gate_checklist.py'))
    _gc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_gc)
    # 模板定位解析链（**不得写死书树名**）：cfg.env → <root>/tools（随包那份）→ <root> → book_trees → 旧路径
    tpl = None
    _cands = []
    try:
        _cands.append((_cfg.checklist_template or '').strip())
    except Exception:
        pass
    _cands.append((os.environ.get('DSH_CHECKLIST_TEMPLATE') or '').strip())
    _cands.append(os.path.join(ROOT, 'tools', 'V3.1全量执行单.md'))
    _cands.append(os.path.join(ROOT, 'V3.1全量执行单.md'))
    try:
        for _bt in (_cfg.book_trees or []):
            _cands.append(os.path.join(ROOT, _bt, '三闸机器化', 'V3.1全量执行单.md'))
    except Exception:
        pass
    _cands.append(os.path.join(ROOT, '投资蒸馏', '三闸机器化', 'V3.1全量执行单.md'))
    for _c in _cands:
        if _c and os.path.isfile(_c):
            tpl = _c
            break
    if not tpl:
        print('🔴 找不到《V3.1全量执行单》模板（找过 tools/ 、根目录、book_trees、旧路径）——'
              '请跑 init_workspace 或用 DSH_CHECKLIST_TEMPLATE 指定')
        return None, None
    if not tpl:
        print('🔴 找不到《V3.1全量执行单》模板（找过：<root>/tools/、<root>/、book_trees、旧路径）——请跑 init_workspace 或用 DSH_CHECKLIST_TEMPLATE 指定')
        return 1
    for name, fill in (('checklist-bad', False), ('checklist-good', True)):
        d = os.path.join(SANDBOX, name)
        os.makedirs(d, exist_ok=True)
        t = io.open(tpl, encoding='utf-8').read()
        if fill:
            # 行级填充（自伤 #9 教训：整文 re.sub 里 `\|\s*\|` 的 \s 会吞行间换行把两行并一行）
            out = []
            for ln in t.splitlines():
                if re.match(r'^\|\s*\d+\s*\|', ln) and ln.rstrip().endswith('|'):
                    cells = ln.rstrip().split('|')
                    cells[-2] = ' 2026-09-13 '
                    ln = '|'.join(cells)
                out.append(ln)
            t = '\n'.join(out) + '\n'
            files = ['BOOK_OVERVIEW.md', 'verified.md', 'selfcheck.md', 'rquote-check.md', 'defense3.md',
                     'fidelity-io.md', '防线4-目录覆盖说明.md', 'readycheck.json', 'machine-report.md',
                     'blind-machine.md', 'd8-fulltest.md', 'darwin-judge.md', 'darwin9-scorecard.md',
                     'polish-scan.md', 'gates-checklist-good.json', 'PIPELINE_STATE.md', '报告.md',
                     'engine-probe.md', 'blind-judge.md', 'route-overlap.md', '口径登记单.md',
                     'fair-regression.md', os.path.join('skills', 'x', 'SKILL.md'),
                     os.path.join('candidates', 'c1.md'), os.path.join('parts', 'ocr', 'p1.txt'),
                     os.path.join('blind-machine', 'judge-subset.md')]
            for f in files:
                fp = os.path.join(d, f)
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                io.open(fp, 'w', encoding='utf-8', newline='\n').write('自证样本\n')
        io.open(os.path.join(d, '执行单.md'), 'w', encoding='utf-8', newline='\n').write(t)
    rc_b, so_b = run([sys.executable, os.path.join(TOOLS, 'gate_checklist.py'),
                      '--work', os.path.join(SANDBOX, 'checklist-bad')])
    rc_g2, so_g2 = run([sys.executable, os.path.join(TOOLS, 'gate_checklist.py'),
                        '--work', os.path.join(SANDBOX, 'checklist-good')])
    bad_hit = (rc_b == 1 and '未记证据/日期' in so_b)
    good_hit = (rc_g2 == 0 and '执行单逐项完成' in so_g2)
    print('  %s 样本4a 执行单 36 项全未记证据被拦（期望：rc=1 ＋ 缺项计数）' % ('✔' if bad_hit else '🔴'))
    print('  %s 样本4b 证据齐＋产物在位放行（期望：rc=0）' % ('✔' if good_hit else '🔴'))
    if not (bad_hit and good_hit):
        print('    ── 坏样本输出（尾）──\n    ' + so_b.replace('\n', '\n    ')[-700:])
        print('    ── 好样本输出（尾）──\n    ' + so_g2.replace('\n', '\n    ')[-700:])
    ok &= bad_hit and good_hit

    # ── 样本 5（A-34 自证）：阶段5 **故意缺项**的任务目录，gate_stage 必须报红 ──
    #    背景（A-34 实证 · 用户质问触发）：执行者自写的阶段5 判据原只查"两个文件是否存在"
    #    ⇒ 手册要求的 5 项产物只做 1 项也全绿（"运动员兼裁判"）。升级为手册逐项口径后，
    #    **必须用坏样本证明它会红**，否则又只是"看起来在检查"。
    #    坏样本刻意**不含 PIPELINE_STATE.md**（免被 preflight ⑤ 误判为活跃任务），且用后即删。
    bad_task = '_selftest-stage5-bad'
    bdir = os.path.join(ROOT, '.work', bad_task)
    if os.path.isdir(bdir):
        shutil.rmtree(bdir)
    skd = os.path.join(bdir, 'skills', 'selftest-skill')
    os.makedirs(skd, exist_ok=True)
    io.open(os.path.join(skd, 'SKILL.md'), 'w', encoding='utf-8', newline='\n').write(
        '---\nname: selftest-skill\ndescription: "自证样本 何时用：触发词：测。"\n---\n\n'
        '## R\n## I\n## E\n**步骤 1** 输入 动作 输出 出口\n**步骤 2** 输入 动作 输出 出口\n'
        '**步骤 3** 输入 动作 输出 出口\n**步骤 4** 输入 动作 输出 出口\n'
        '**步骤 5** 输入 动作 输出 出口\n## A1\n## A2 何时不用\n🔴 **CHECKPOINT**\n'
        '## B\n### B4 不要做\n## 判停速查\n')
    rc_s5, so_s5 = run([sys.executable, os.path.join(TOOLS, 'gate_stage.py'), '--task', bad_task])
    s5_hit = (rc_s5 == 1 and '缺 BOUNDARIES.md' in so_s5 and '缺 SUPPLEMENT' in so_s5)
    print('  %s 样本5 阶段5 缺四件套/SUPPLEMENT/随件题 被拦（期望：rc=1 ＋ 逐项列缺）'
          % ('✔' if s5_hit else '🔴'))
    if not s5_hit:
        print('    ── 坏样本输出（尾）──\n    ' + so_s5.replace('\n', '\n    ')[-700:])
    ok &= s5_hit
    shutil.rmtree(bdir, ignore_errors=True)

    # ── 样本 6（A-36 自证）：例外登记表必须"先定表、再认肯定式确认" ──
    #    背景（A-36 实证 · 2026-09-13）：旧解析器取"首个含『例外登记』字样的行"＋固定 12 行窗口，
    #    而 §2 执行项表的**正文**里就写着"见第 4 节例外登记" ⇒ **把 §2 表当成例外表读**：
    #    #7 描述含"9 维表"→ 误豁免 #9；#11 描述含"0 候选"→ 误豁免 #0；
    #    且"用户确认"列的 `**待用户确认**` 非空即算"已确认"⇒ **#9 被静默豁免（且显示成"用户确认"）**。
    #    差分成对样本：同一份执行单（**唯一缺项 = #25**，且 §2 内埋"例外登记/9/19"陷阱词），
    #    只改 §4 的"用户确认"列 → 判决必须翻转（待确认⇒rc=1 且点名 #25；确认⇒rc=0）。
    _s6_files = ['BOOK_OVERVIEW.md', 'verified.md', 'selfcheck.md', 'rquote-check.md', 'defense3.md',
                 'fidelity-io.md', '防线4-目录覆盖说明.md', 'readycheck.json', 'machine-report.md',
                 'blind-machine.md', 'd8-fulltest.md', 'darwin-judge.md',
                 'polish-scan.md', 'gates-s6.json', 'PIPELINE_STATE.md', '报告.md',
                 'engine-probe.md', 'blind-judge.md', 'route-overlap.md', '口径登记单.md',
                 'fair-regression.md', os.path.join('skills', 'x', 'SKILL.md'),
                 os.path.join('candidates', 'c1.md'), os.path.join('parts', 'ocr', 'p1.txt'),
                 os.path.join('blind-machine', 'judge-subset.md')]   # 刻意**不含** darwin9-scorecard
    s6 = []
    for name, conf, want_rc in (('checklist-exc-pending', '**待用户确认**', 1),
                                ('checklist-exc-ok', '是（自证样本）', 0)):
        d = os.path.join(SANDBOX, name)
        os.makedirs(d, exist_ok=True)
        for f in _s6_files:
            fp = os.path.join(d, f)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            io.open(fp, 'w', encoding='utf-8', newline='\n').write('自证样本\n')
        out = []
        for ln in io.open(tpl, encoding='utf-8').read().splitlines():
            if re.match(r'^\|\s*\d+\s*\|', ln) and ln.rstrip().endswith('|'):
                c = ln.strip().strip('|').split('|')
                c[-1] = ' 2026-09-13 '
                if c[0].strip() == '7':     # 陷阱：正文含"例外登记"＋裸数字 9 与 19
                    c[1] = ' 构造自查（见第 4 节例外登记）9 维表 19 '
                ln = '|' + '|'.join(c) + '|'
            out.append(ln)
        t = '\n'.join(out) + '\n'
        ls = t.splitlines()
        h = next(i for i, l in enumerate(ls) if re.match(r'^#{1,6}\s', l) and '例外登记' in l)
        for j in range(h + 1, len(ls)):
            if re.match(r'^#{1,6}\s', ls[j]):
                break
            if '-' in ls[j] and re.match(r'^\|[\s|:-]+\|$', ls[j]):
                continue   # 分隔行（`|---|---|`）；注意空数据行 `|  |  |  |  |` 不是分隔行
            c = ls[j].strip().strip('|').split('|')
            if len(c) == 4 and not c[0].strip():      # 模板的空行 ⇒ 填"日期"＋"用户确认"列
                c[0] = ' 2026-09-13 '
                c[1] = ' 25 '
                c[2] = ' 自证样本：该条产物（engine-* 探针）由本脚本主动删除以制造唯一缺项 '
                c[3] = ' ' + conf + ' '
                ls[j] = '|' + '|'.join(c) + '|'
                break
        io.open(os.path.join(d, '执行单.md'), 'w', encoding='utf-8', newline='\n').write(
            '\n'.join(ls) + '\n')
        # 主动制造「唯一真缺项」= #25（engine-*）：删掉其产物
        _ep = os.path.join(d, 'engine-probe.md')
        if os.path.exists(_ep):
            os.remove(_ep)
        rc6, so6 = run([sys.executable, os.path.join(TOOLS, 'gate_checklist.py'), '--work', d])
        hit = (rc6 == want_rc) and (want_rc == 0 or '#25' in so6)
        print('  %s 样本6%s 例外列=%s ⇒ 期望 rc=%d（待确认必须**不**豁免 #25）'
              % ('✔' if hit else '🔴', 'a' if want_rc else 'b', conf, want_rc))
        if not hit:
            print('    ── 输出（尾）──\n    ' + so6.replace('\n', '\n    ')[-700:])
        s6.append(hit)
    ok &= all(s6)

    # ── 样本 7（A-132 自证 · 2026-09-19）：**波段 id 形态**的成对差分 ─────────────────
    #    背景（NAS 异机实测）：册 `<task>` 的波段名是 `E1..E6`，产出**完全合规**，
    #    却被 `verify_candidates` 判「切块为空 ⇒ 条目 0」（假红）；同册在 `gate_stage`
    #    的格式判据下却是绿的 ⇒ **一手绿一手红，判决取决于用哪把尺子**。
    #    本样本要吃住这件事，必须**成对**：
    #      7a **好**：合规的 `### E1-001  [PR] [技能=S3]` ⇒ 必须 rc=0 且"条目 1"；
    #      7b **坏**：同内容、只把 id 改成数字开头的 `2024-001` ⇒ 必须 rc=1 且报"切块为空"
    #              （证明"放宽"没有放宽到把年份/页码当条目 —— 若两样本同判，本项即失败）。
    #    另加**判别力自证**：旧尺子 ④`[A-Za-z]+` 对 `E1-001` 恒不命中 ⇒ 说明本样本
    #    确实"能区分新旧尺子"（否则样本再绿也证明不了修好了）。
    SRC_BOOK = ('[p1]\n这是用于自证的第一句原文。\n\n[p2]\n第二句原文用于第二条。\n')
    NOTE_GOOD = ('# 候选提取笔记 · 波段 E1（自证样本）\n\n'
                 '### E1-001  [PR] [技能=S3]\n'
                 '- 锚：[p1]\n'
                 '- 原文（逐字）：「这是用于自证的第一句原文。」\n'
                 '- 转述：自证样本正文。\n')
    NOTE_BAD = NOTE_GOOD.replace('### E1-001  [PR]', '### 2024-001  [PR]')
    s7 = []
    for tag, body, want_rc, want_pat in (('good', NOTE_GOOD, 0, r'条目 1'),
                                         ('bad', NOTE_BAD, 1, r'切块为空')):
        td = os.path.join(ROOT, '.work', '_selftest-bandid-%s' % tag)
        shutil.rmtree(td, ignore_errors=True)
        os.makedirs(os.path.join(td, 'candidates'), exist_ok=True)
        io.open(os.path.join(td, 'book_text.md'), 'w', encoding='utf-8', newline='\n').write(SRC_BOOK)
        io.open(os.path.join(td, 'candidates', 'notes_E1.md'), 'w', encoding='utf-8',
                newline='\n').write(body)
        rc7, so7 = run([sys.executable, os.path.join(TOOLS, 'verify_candidates.py'),
                        '--all', '--task', '_selftest-bandid-%s' % tag,
                        '--src', os.path.join(td, 'book_text.md')])
        hit = (rc7 == want_rc) and bool(re.search(want_pat, so7))
        print('  %s 样本7%s 波段 `E1-…`（%s）⇒ 期望 rc=%d ＋ 命中「%s」'
              % ('✔' if hit else '🔴', 'a' if tag == 'good' else 'b',
                 '合规' if tag == 'good' else '数字开头 id', want_rc, want_pat))
        if not hit:
            print('    ── 输出（尾）──\n    ' + so7.replace('\n', '\n    ')[-700:])
        s7.append(hit)
        shutil.rmtree(td, ignore_errors=True)
    # 判别力自证：旧尺子对 `E1-001` 必须**不**命中（否则本样本无法区分新旧）
    _old_ruler_blind = not re.match(r'^###\s+[A-Za-z]+-\d{3}\s+\[', '### E1-001  [PR] [技能=S3]')  # BANDID-OK-LINE: 故意用旧尺子做判别力自证
    print('  %s 样本7c 判别力：旧尺子 `[A-Za-z]+-` 对 `E1-001` 不命中（期望：True）'
          % ('✔' if _old_ruler_blind else '🔴'))
    if not _old_ruler_blind:
        print('    ⚠ 旧尺子也能命中本样本 ⇒ 本样本**证明不了**修好了 A-132（须换形态）')
    s7.append(_old_ruler_blind)
    ok &= all(s7)

    # ── 样本 8（A-132 自证）：单源闸**自身有效**（该拦的拦、不该拦的放行）＋全工作台单源 ──
    _gate8 = os.path.join(TOOLS, 'check_bandid_single_source.py')
    rc8a, so8a = run([sys.executable, _gate8, '--selftest'])
    rc8b, so8b = run([sys.executable, _gate8])
    s8a = (rc8a == 0 and '闸自证通过' in so8a)
    s8b = (rc8b == 0 and '通过' in so8b)
    print('  %s 样本8a 单源闸自证（正负样本各就各位，期望 rc=0）' % ('✔' if s8a else '🔴'))
    print('  %s 样本8b 全工作台无内联波段 id 语法（期望 rc=0）' % ('✔' if s8b else '🔴'))
    if not (s8a and s8b):
        print('    ── 8a（尾）──\n    ' + so8a.replace('\n', '\n    ')[-600:])
        print('    ── 8b（尾）──\n    ' + so8b.replace('\n', '\n    ')[-600:])
    ok &= s8a and s8b

    # ── 样本 9（A-133 自证）：**源文件决议陷阱** ─────────────────────────────────────
    #    背景（NAS 真机实测）：`verify_candidates --all` 的**页标记探测**用"候选名优先"（对），
    #    而**逐文件校验**用"<work> 里 mtime 最新者"（错）⇒ 源被决议到 `DIGEST.md`（任务自己的
    #    产出文档、最新修改）⇒ **6 波段 236 条引文 100% 报"回源未命中"**。症状极具误导性：
    #    既不像产出错、也不像仪器坏，只是"每条都不合格"——会诱导执行者去改**合规的产出**。
    #    本样本按**旧规则**构造陷阱：`DIGEST.md` **更新**（mtime 最大）且**不含页标记**；
    #    真源 `book_text.md` 含页标记；引文只存在于真源 ⇒
    #      旧规则（mtime 最新）⇒ 决议到 DIGEST.md ⇒ 0 命中 ⇒ rc=1（**假红**）；
    #      新规则（名字优先 ＋ 兜底必须含页标记）⇒ 决议到 book_text.md ⇒ 命中 ⇒ rc=0。
    #    断言三条：rc=0 ＋ 打印里出现 `book_text.md` ＋ 命中数 > 0；并**自证陷阱成立**
    #    （DIGEST.md 的 mtime 必须晚于 book_text.md）。
    _t9 = os.path.join(ROOT, '.work', '_selftest-srcresolve')
    shutil.rmtree(_t9, ignore_errors=True)
    os.makedirs(os.path.join(_t9, 'candidates'), exist_ok=True)
    io.open(os.path.join(_t9, 'book_text.md'), 'w', encoding='utf-8', newline='\n').write(SRC_BOOK)
    io.open(os.path.join(_t9, 'candidates', 'notes_E1.md'), 'w', encoding='utf-8',
            newline='\n').write(NOTE_GOOD)
    _digest = ('# DIGEST（任务自己的产出文档 · 故意不含页标记 · 故意更新）\n\n'
               '本文档用于复现「源决议错到产出文档」的陷阱：这里没有页标记，也没有引文。\n')
    io.open(os.path.join(_t9, 'DIGEST.md'), 'w', encoding='utf-8', newline='\n').write(_digest)
    # 让 DIGEST.md 的 mtime **明确晚于** book_text.md（陷阱成立的前提）——
    # 用 `os.utime` 显式设置，**不靠 sleep**（确定性、且不受文件系统时间粒度影响）。
    _bt = os.path.getmtime(os.path.join(_t9, 'book_text.md'))
    os.utime(os.path.join(_t9, 'DIGEST.md'), (_bt + 5, _bt + 5))
    _trap = (os.path.getmtime(os.path.join(_t9, 'DIGEST.md'))
             > os.path.getmtime(os.path.join(_t9, 'book_text.md')))
    _rc9, _so9 = run([sys.executable, os.path.join(TOOLS, 'verify_candidates.py'),
                      '--all', '--task', '_selftest-srcresolve'])
    _hit9 = bool(re.search(r'引文回源命中：\s*1\s*/\s*1', _so9))
    _src9 = 'book_text.md' in _so9
    print('  %s 样本9a 源决议陷阱：旧规则会选 DIGEST.md（陷阱成立=%s）⇒ 期望 rc=0 且命中 1/1'
          % ('✔' if (trap_ok := _trap) and _rc9 == 0 and _hit9 and _src9 else '🔴', _trap))
    print('  %s 样本9b 决议依据可自证（输出里出现真源名 book_text.md）' % ('✔' if _src9 else '🔴'))
    if not (_trap and _rc9 == 0 and _hit9 and _src9):
        print('    ── 输出（尾）──\n    ' + _so9.replace('\n', '\n    ')[-900:])
    ok &= _trap and _rc9 == 0 and _hit9 and _src9
    shutil.rmtree(_t9, ignore_errors=True)

    json.dump({'ts': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
               'broken_yaml_detected': broken_hit, 'over_limit_detected': over_hit,
               'good_passed': good_ok, 'bad_table_detected': tbl_hit,
               'checklist_bad_detected': bad_hit, 'checklist_good_passed': good_hit,
               'stage5_missing_detected': s5_hit, 'exception_pending_rejected': s6[0],
               'exception_confirmed_honored': s6[1],
               'bandid_good_passed': s7[0], 'bandid_bad_rejected': s7[1],
               'bandid_discriminating': s7[2],
               'bandid_gate_selftest_ok': s8a, 'bandid_single_source_ok': s8b,
               'src_resolve_trap_ok': _trap and _rc9 == 0 and _hit9 and _src9,
               'all_ok': ok},
              io.open(os.path.join(TOOLS, '_gate_selftest.json'), 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=1)
    print('\n结论：%s' % ('✔ 门禁自证有效（九组坏样本全拦、好样本放行）' if ok
                        else '🔴 门禁未能全部检出坏样本 —— 门禁本身需要修'))
    print('样本目录（保留供复查）：%s' % SANDBOX)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    sys.exit(main())
