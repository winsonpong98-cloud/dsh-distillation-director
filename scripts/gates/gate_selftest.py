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
#                 ——旧常量 `WORK = <root>\.work\fei-lixing-fanrong` 指的就是它；首版被我换成 cfg.work ⇒
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
    tpl = os.path.join(ROOT, '投资蒸馏', '三闸机器化', 'V3.1全量执行单.md')
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

    json.dump({'ts': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
               'broken_yaml_detected': broken_hit, 'over_limit_detected': over_hit,
               'good_passed': good_ok, 'bad_table_detected': tbl_hit,
               'checklist_bad_detected': bad_hit, 'checklist_good_passed': good_hit,
               'stage5_missing_detected': s5_hit, 'exception_pending_rejected': s6[0],
               'exception_confirmed_honored': s6[1], 'all_ok': ok},
              io.open(os.path.join(TOOLS, '_gate_selftest.json'), 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=1)
    print('\n结论：%s' % ('✔ 门禁自证有效（六坏全拦、三好放行）' if ok
                        else '🔴 门禁未能全部检出坏样本 —— 门禁本身需要修'))
    print('样本目录（保留供复查）：%s' % SANDBOX)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    sys.exit(main())
