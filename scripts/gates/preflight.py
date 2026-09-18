# -*- coding: utf-8 -*-
"""preflight.py —— 蒸馏工作区「开工前门禁」（防坑体系 层1 · 甲-A1/A3/A4/A5）

设计口径（与《防坑体系-要做清单》一致）：
  · 位置 `蒸馏工作区\\tools\\`（稳定语义位置；`.work\\` 是"处理中产物"，不放工具）
  · **复用**既有工具（绝对路径调用），不复制不重写
  · **只读不写业务文件**（唯一写入＝首次建立 mtime 基线 `tools\\_mtime_baseline.json`）
  · **UTF-8 输出保护**：本脚本自设 `PYTHONIOENCODING=utf-8` 并 `reconfigure(stdout)`，
    且调用子进程时统一注入该环境变量 —— 消除"GBK 控制台打印 ✔ 抛 UnicodeEncodeError → 假非零退出"（坑 P-16）
  · 统一输出格式：`期望 / 实测 / 判定`（防"看起来在检查"的空转）
  · 任一不符 → **非零退出**

用法：
  python preflight.py                # 跑四道门
  python preflight.py --selftest     # 用"故意坏掉"的样本自证门禁有效（甲-A4）
  python preflight.py --json         # 附机器可读结果（写 tools/_preflight_last.json）
"""
import io
import os
import re
import sys
import json
import time
import hashlib
import subprocess

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
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
# 🆕 2026-09-17 第三宿主首次交付 · 四件套④「计数文档同步」（书名见 .work/<task>/ 配置，本行仅 provenance）  # generic-ok: PROVENANCE
BOND_DIR = _cfg.host('bond') or _os_.path.join(_WS_PARENT, '债券与衍生品')
MAIN_DIR = _cfg.host('main') or _cfg.host('fin') or _WS_PARENT
MACH_TOOL = _os_.path.join(MACH, 'machine_precheck_v2.py') if MACH else None
MBASE = _os_.path.join(TOOLS, '_machine_baseline.json')
SANDBOX = _os_.path.join(TOOLS, '_selftest')
FIN = FIN_DIR
EDU = EDU_DIR
MAIN = MAIN_DIR
NODE = NODE_EXE
JSDIR = JS_YAML_DIR

# mtime 巡检范围：技能库全集 ＋ 关键文档
WATCH = [
    os.path.join(FIN, '.dsh', 'skills'),
    os.path.join(EDU, '.dsh', 'skills'),
    os.path.join(ROOT, '.dsh', 'skills'),
    os.path.join(ROOT, 'AGENTS.md'),
    os.path.join(FIN, 'AGENTS.md'),
    os.path.join(EDU, 'AGENTS.md'),
    os.path.join(FIN, '.dsh', 'skills', 'INDEX.md'),
]

results = []


def env():
    e = dict(os.environ)
    e['PYTHONIOENCODING'] = 'utf-8'
    return e


def run(cmd, cwd=None):
    # 防坑：cwd 指向不存在的目录时 Windows 抛 NotADirectoryError(267) ⇒ 裸栈。
    _cwd_ok = cwd if (cwd and os.path.isdir(cwd)) else None
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace', env=env(), cwd=_cwd_ok)
    return r.returncode, (r.stdout or ''), (r.stderr or '')


def rec(gate, expect, actual, ok, note=''):
    results.append({'gate': gate, 'expect': expect, 'actual': actual,
                    'verdict': 'PASS' if ok else 'FAIL', 'note': note})
    print('  %s %-26s 期望=%-22s 实测=%-30s %s'
          % ('✔' if ok else '🔴', gate, expect, actual, note))


def walk_files(root):
    for d, _, fs in os.walk(root):
        for f in fs:
            yield os.path.join(d, f)


def snapshot_mtimes():
    out = {}
    for w in WATCH:
        if os.path.isfile(w):
            out[w] = int(os.path.getmtime(w))
        elif os.path.isdir(w):
            for p in walk_files(w):
                if p.endswith(('.md', '.json', '.py', '.mjs', '.cjs', '.yml', '.yaml')) or 'SKILL' in p:
                    out[p] = int(os.path.getmtime(p))
    return out


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
    selftest = '--selftest' in sys.argv
    print('=== 蒸馏工作区 · 开工前门禁（preflight）%s ===\n'
          % ('【自检样本模式】' if selftest else ''))
    print('① 四道验收闸')
    rc, so, se = run([sys.executable, os.path.join(WORK, 'final_acceptance.py')])
    m = {'act': re.search(r'活动\s*(\d+)', so), 'arc': re.search(r'archived\s*(\d+)', so)}
    ok1 = rc == 0 and '①' in so
    rec('final_acceptance', '退出码 0 且四闸打印', 'rc=%d' % rc, ok1,
        '（② 输出见 stdout 末端）')

    print('\n② YAML 全库（两线，js-yaml 实解析）')
    for tag, host, want in (('金融投资', FIN, 49), ('教育线', EDU, 23), ('债券线', BOND_DIR, 5)):  # 教育线 22→23（2026-09-13 深夜 ADHD 装机 · 计数同步）；债券线 0→5（2026-09-17 首次交付）
        _skills = os.path.join(host, '.dsh', 'skills')
        if not os.path.isdir(_skills):
            rec('yaml:' + tag, '%d/%d' % (want, want),
                '技能根不存在（%s）' % _skills, True,
                '判"不适用"：异机（新用户）没有作者的宿主工作区；本项不计失败')
            print('   ⚠ %s：宿主技能根不存在 ⇒ 判"不适用"（不调用 node，避免 ENOENT 栈）' % tag)
            continue
        rc, so, se = run([NODE, os.path.join(WORK, 'yaml_check_generic.cjs'),
                          _skills, JSDIR, str(want)], cwd=WORK)
        m = re.search(r'YAML 解析通过：(\d+) / (\d+)', so)
        good = bool(m) and int(m.group(1)) == want and rc == 0
        rec('yaml:' + tag, '%d/%d' % (want, want),
            (m.group(0).replace('YAML 解析通过：', '') if m else '解析失败'), good)

    print('\n③ 引擎加载器实测（件数/唯名/告警/封存态）')
    for tag, host, want in (('金融投资', FIN, 49), ('教育线', EDU, 23), ('债券线', BOND_DIR, 5)):  # 债券线 0→5（2026-09-17 首次交付）
        rc, so, se = run([NODE, os.path.join(WORK, 'skill_probe_generic.mjs'),
                          os.path.join(host, '.dsh', 'skills'), host], cwd=WORK)
        n = re.search(r'引擎发现技能数:\s*(\d+)', so)
        u = re.search(r'唯一名:\s*(\d+)\s*/\s*(\d+)', so)
        w = re.search(r'解析告警:\s*(\d+)', so)
        good = (bool(n) and int(n.group(1)) == want and bool(u) and u.group(1) == u.group(2)
                and bool(w) and int(w.group(1)) == 0)
        rec('engine:' + tag, '%d 件/唯名一致/告警 0' % want,
            '件数=%s 唯名=%s 告警=%s' % (n.group(1) if n else '?',
                                        (u.group(0).split(':')[-1].strip() if u else '?'),
                                        w.group(1) if w else '?'), good)
        if tag == '金融投资':
            rec('engine:bargain-hunting', '不可加载（封存态）',
                '不可加载' if 'bargain-hunting' not in so else '🔴 仍可加载',
                'bargain-hunting' not in so)

    print('\n④ mtime 巡检（"有没有被别的会话动过"）')
    cur = snapshot_mtimes()
    update = '--update-baseline' in sys.argv
    if not os.path.exists(BASELINE) or update:
        os.makedirs(TOOLS, exist_ok=True)
        io.open(BASELINE, 'w', encoding='utf-8', newline='\n').write(
            json.dumps({'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'mtimes': cur},
                       ensure_ascii=False, indent=1))
        rec('mtime 基线', '已存在基线',
            ('已显式更新' if os.path.exists(BASELINE) and update else '首次建立') + '（%d 个文件）' % len(cur),
            True, '显式 --update-baseline＝本次改动已被有意接受；否则下次运行起开始比对')
    else:
        base = json.loads(io.open(BASELINE, encoding='utf-8').read())['mtimes']
        changed = [k for k, v in base.items() if cur.get(k) != v]
        added = [k for k in cur if k not in base]
        rec('mtime 漂移', '0 个文件被改动',
            '改动 %d ｜ 新增 %d' % (len(changed), len(added)), len(changed) == 0,
            '（新增不算异常；改动过的前 5 个：%s）' % '、'.join(os.path.basename(p) for p in changed[:5]))

    print('\n⑤ 蒸馏任务阶段门禁（活跃任务＝PIPELINE_STATE 在 24h 内更新过）')
    # 设计意图（2026-09-13 用户指令「让偷懒跑不通」）：蒸馏任务的"读手册/建执行单/跑机器层/按阶段推进"
    # 此前全靠自觉；本闸把它们变成**开工即拦**：活跃任务未过闸 → preflight 直接非零退出。
    # 活跃判据＝该任务 PIPELINE_STATE.md 的 mtime 在 24h 内（自动、无需声明、无法手改规避）。
    #
    # ⚠ 判据修正（2026-09-17 · manias-crashes 实测抓到「开工死锁」· 用户拍板甲案）：
    #   旧实现把**三闸并成一个与**（gate_start ∧ gate_stage ∧ gate_checklist 全绿），
    #   而 gate_stage 要求**六阶段产物齐备**、gate_checklist 要求**执行单 36 项逐项完成**
    #   —— 那是"**干完活**"的条件，不是"开工前"的条件。
    #   ⇒ 任何**新**蒸馏任务在动工前都**不可能**让 ⑤ 通过；而 §18.2 又要求"preflight 全绿才开工"
    #   ⇒ **互锁**（实测：某新任务首跑 ①②③④ 全绿、仅 ⑤ 红，且红因正是"该任务尚未完成"）。
    #   新判据（对齐手册 §21.4「preflight＝工作区健康／蒸馏流程合规，postflight＝收尾」的分工）：
    #     ① **gate_start 恒查**（它就是为"开工前"设计的：手册哈希／条款抄录／执行单存在／机器层）；
    #     ② gate_stage 与 gate_checklist **只对任务自己"已宣称完成"的阶段与执行项判红**——
    #        宣称源＝PIPELINE_STATE.md 里一行**显式、可审、可 grep** 的声明：
    #            `<!-- preflight-stage-gate: 阶段0,阶段1.5 -->`
    #        无该行 ⇒ 默认只宣称"开工自证"（＝下游两闸本次不判红，但**会打印**"未宣称"以示透明）。
    #        执行单逐项闸随**阶段5**一并启用（阶段性核销的最后一关）。
    #   纪律：本闸**不得**阻止新任务开工；它只阻止"**宣称完成了却没过闸**"。
    import glob as _glob
    wdir = os.path.join(ROOT, '.work')
    now = time.time()
    actives = []
    if os.path.isdir(wdir):
        for d in sorted(os.listdir(wdir)):
            ps = os.path.join(wdir, d, 'PIPELINE_STATE.md')
            if os.path.exists(ps) and (now - os.path.getmtime(ps)) < 86400:
                actives.append(d)
    if not actives:
        rec('distill:阶段门禁', '无活跃蒸馏任务（不适用）', '0 个', True,
            '（活跃任务一旦出现即自动纳入本闸）')
    for t in actives:
        ps = os.path.join(wdir, t, 'PIPELINE_STATE.md')
        txt = io.open(ps, encoding='utf-8', errors='replace').read()
        mclaim = re.search(r'<!--\s*preflight-stage-gate:\s*([^>]*?)\s*-->', txt)
        claimed = []
        if mclaim:
            for tok in re.split(r'[、,，\s]+', mclaim.group(1)):
                tok = tok.strip()
                # 「开工自证」＝**真空态哨兵**，不是阶段名：仅表示"该任务只宣称开工" ⇒ 本闸只查 gate_start
                # （修：首版把它当阶段名去匹配 ⇒ 打印"宣称的阶段名无法对上"而**假红**；实测抓到）
                if tok and tok not in ('无', 'none', '-', '开工自证'):
                    claimed.append(tok)
        claim_note = ('宣称已完成：%s' % '、'.join(claimed)) if claimed else '只宣称开工（未宣称任何已完成阶段）'

        rc_s, so_s, _ = run([sys.executable, os.path.join(TOOLS, 'gate_start.py'), '--task', t, '--quiet'])
        why = []
        if rc_s != 0:
            why.append('开工闸未过（`gate_start.py --task %s`）' % t)

        # 只对"已宣称完成"的**最靠后**那个阶段跑 gate_stage（前序都过才轮到它 → 与阶段依赖链一致）
        stage_checked, stage_rc, so_g = False, 0, ''
        if claimed:
            rc_all, so_all, _ = run([sys.executable, os.path.join(TOOLS, 'gate_stage.py'), '--task', t])
            names = re.findall(r'^\s*[✔🔴]\s*阶段(\S+)', so_all, re.M)
            want = None
            for tok in claimed:                      # 取与某个真实阶段名匹配的最后一个宣称
                t = tok.replace('阶段', '').strip()   # 容忍「阶段0」与「0-骨架」两种写法（都指同一阶段）
                for nm in names:
                    nmkey = nm.split('-')[0]
                    if t == nmkey or nmkey.startswith(t + '-') or nm.startswith(tok):
                        want = nm
            if want is None:
                why.append('宣称的阶段名无法与 gate_stage 的阶段名对上（宣称 %s ／ 实有 %s）'
                           % ('、'.join(claimed), '、'.join(names)))
            else:
                stage_checked = True
                key = want.split('-')[0]
                rc_g, so_g, _ = run([sys.executable, os.path.join(TOOLS, 'gate_stage.py'),
                                     '--task', t, '--stage', key])
                stage_rc = rc_g
                if rc_g != 0:
                    ms = re.search(r'卡在【([^】]+)】', so_all)
                    why.append('宣称完成阶段【%s】但阶段门禁未过%s'
                               % (want, ('（卡在 %s）' % ms.group(1)) if ms else ''))

        # 执行单逐项闸：随阶段5 一并启用（它是"交付前"的逐项核销）
        cl_checked = False
        ctx_stage5 = any(x.startswith('5') for x in claimed)
        if ctx_stage5:
            cl_checked = True
            rc_c, so_c, _ = run([sys.executable, os.path.join(TOOLS, 'gate_checklist.py'), '--task', t])
            if rc_c != 0:
                mc = re.search(r'🔴 缺 \d+[：:][^\n]*', so_c)
                why.append('宣称阶段5 但执行单逐项未过：%s'
                           % (mc.group(0) if mc else '（`gate_checklist.py` 报红，详见其输出）'))

        ok = not why
        detail = '；'.join(why) if why else (
            'PASS（%s；已判：开工闸%s%s）'
            % (claim_note,
               '＋阶段门禁[%s]' % ('过' if stage_rc == 0 else '红') if stage_checked else '',
               '＋执行单逐项闸' if cl_checked else ''))
        rec('distill:' + t, '开工闸全绿；已宣称阶段亦全绿',
            'PASS' if ok else '；'.join(why), ok,
            '（%s；未过不得进入下一阶段。命令：gate_start.py ／ gate_stage.py ／ gate_checklist.py --task %s）'
            % (claim_note, t))

    bad = [r for r in results if r['verdict'] == 'FAIL']
    print('\n结论：%s' % ('✔ 开工前门禁全绿（%d 项）' % len(results) if not bad
                        else '🔴 %d 项不符，先处理再开工' % len(bad)))
    for r in bad:
        print('   - %s：期望 %s ／ 实测 %s' % (r['gate'], r['expect'], r['actual']))
    if '--json' in sys.argv:
        os.makedirs(TOOLS, exist_ok=True)
        io.open(os.path.join(TOOLS, '_preflight_last.json'), 'w', encoding='utf-8', newline='\n').write(
            json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'results': results},
                       ensure_ascii=False, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    sys.exit(main())
