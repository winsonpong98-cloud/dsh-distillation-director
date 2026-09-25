# -*- coding: utf-8 -*-
"""postflight.py —— 蒸馏工作区「改后门禁」（防坑体系 层1 · 甲-A2/A3/A4/A5）

口径（与《防坑体系-要做清单》一致；⑧ 教育线四闸＝W4 批挂入 · 2026-09-13）：**全绿才算改完**。
  ① YAML 全库（两线，js-yaml 实解析）
  ② desc 长度（官方解析器口径 ≤1024）
  ③ 表格完整性（复用 `check_md_tables.py`：关键 md 管道数一致性）
  ④ 脚本一致（`check_script_sync.py` ＝ 4/0/0）
  ⑤ **机器层零新增 fail**（对基线 diff：金融线 44 ＋ 教育线 22）
  ⑥ `py_compile` 全脚本（三闸机器化 ＋ tools ＋ .work 工装）
  ⑦ 技能体积 vs spill 阈值（信息性不阻断 · K-20）
  ⑧ **教育线四闸**（W4 · 只读）：⒜ 副本新鲜度（A-17/A-19 比对版本戳）⒝ desc 占位符（A-21）
     ⒞ 引擎探针（坑 5：加载器实测 23 件）⒟ rules-v1 底账同代（66/66 quote 子串断言——
     防止"规则清单落后于源根"的漂移，批15 实证它抓得住）。

纪律：只读不写业务文件；唯一写入＝首次建立 `tools/_machine_baseline.json`；
      UTF-8 输出保护同 preflight；统一 `期望/实测/判定`；任一不符非零退出。

用法：
  python postflight.py                 # 六项门禁
  python postflight.py --update-baseline   # 明确地"接受当前状态为新基线"（改动有意时用）
  python postflight.py --json
"""
import io
import os
import re
import sys
import glob
import json
import time
import py_compile
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
TOOLS = _cfg.tools or _os_.path.join(ROOT, 'tools')
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

# 表格门禁覆盖的关键 md（我方交付文档；判官/证据文件按纪律不纳入）
# ⚠ 2026-09-23（自伤登记 · 见本工作区输出的闸缺陷台账 `G-37`）：这份表是**手写**的 ⇒
#   台账（缺陷的**唯一索引**）**不在内**，于是"台账自己表破了一整轮"没有任何闸发现。
#   本轮把**当日两件索引**加进来；**未做**「改成全量 glob」——实测 `输出\*.md` 149 份里
#   有 **4 份**块内不一致，改全量会当场红 4 处 ⇒ 登记为待办（先清那 4 份，再改全量）。
MD_WATCH = [
    os.path.join(ROOT, '输出', '2026-09-23-闸缺陷台账.md'),
    os.path.join(ROOT, '输出', '蒸馏台账-2026-09-23.md'),
    os.path.join(ROOT, '输出', '接续清单-总表-2026-09-12.md'),
    os.path.join(ROOT, '输出', '口径登记单-2026-09-12.md'),
    os.path.join(ROOT, '输出', '未完成清单-逐条-2026-09-12.md'),
    os.path.join(ROOT, '输出', '彻底解决-收口报告-2026-09-12.md'),
    os.path.join(ROOT, '输出', '机器工具遗留对账-2026-09-12.md'),
    os.path.join(ROOT, '输出', '路由基线-2026-09-12.md'),
    os.path.join(ROOT, '输出', '第8轮-收官小结-2026-09-13.md'),
    os.path.join(ROOT, '输出', '第8轮-复盘与后续计划-2026-09-13.md'),
    os.path.join(ROOT, '输出', '机器层-教育线-全量-2026-09-13.md'),
    os.path.join(ROOT, '输出', '路由互斥候选清单-教育线-2026-09-13.md'),
    os.path.join(ROOT, 'AGENTS.md'),
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
    print('  %s %-26s 期望=%-20s 实测=%-34s %s'
          % ('✔' if ok else '🔴', gate, expect, actual, note))


def _safe_listdir(d, why=''):
    """列目录，但**缺目录不算异常**：打印理由并返回空表（A-74：缺件判"不适用"，不出裸栈）。
    为什么统一走这里：异机（新用户）没有作者的宿主工作区，任何直接 os.listdir 都会崩。"""
    if not os.path.isdir(d):
        print('   ⚠ 目录不存在，跳过（判"不适用"）：%s %s' % (d, why))
        return []
    return sorted(os.listdir(d))


def machine_failset(path):
    out = os.path.join(TOOLS, '_tmp_mach.json')
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([sys.executable, MACH_TOOL, path, '--out', out],
                   capture_output=True, text=True, encoding='utf-8', env=env())
    if not os.path.exists(out):
        return None
    j = json.loads(io.open(out, encoding='utf-8').read())
    fails = set()
    for dim, dv in j['dims'].items():
        for c in dv.get('checks', []):
            if c['status'] == 'fail' and c.get('deduct', 0) > 0:
                fails.add(c['id'])
    os.remove(out)
    return {'static': j['summary'].get('machine_static_score'), 'fails': sorted(fails)}


def machine_all():
    res = {}
    for tag, host in (('fin', FIN), ('edu', EDU)):
        root = os.path.join(host, '.dsh', 'skills')
        if not os.path.isdir(root):
            # 异机（新用户）不会有作者的宿主工作区 ⇒ **跳过并说明**，不崩栈（A-74）
            print('   ⚠ 跳过机器层扫描：%s 的宿主技能根不存在（%s）—— 判"不适用"' % (tag, root))
            continue
        for slug in _safe_listdir(root):
            p = os.path.join(root, slug, 'SKILL.md')
            if not os.path.isfile(p):
                continue
            m = machine_failset(p)
            if m:
                res['%s/%s' % (tag, slug)] = m
    return res


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
    update = '--update-baseline' in sys.argv
    print('=== 蒸馏工作区 · 改后门禁（postflight）=== \n')

    print('① YAML 全库')
    for tag, host, want in (('金融投资', FIN, 54), ('教育线', EDU, 23)):  # 金融投资 51→53→54（2026-09-25 G-68 双层证据包装机扩容 · R8 计数同步）
        rc, so, se = run([NODE, os.path.join(TOOLS, 'yaml_check_generic.cjs'),
                          os.path.join(host, '.dsh', 'skills'), JSDIR, str(want)], cwd=WORK)
        m = re.search(r'YAML 解析通过：(\d+) / (\d+)', so)
        rec('yaml:' + tag, '%d/%d' % (want, want),
            (m.group(0).replace('YAML 解析通过：', '') if m else '解析失败'),
            bool(m) and int(m.group(1)) == want and rc == 0)

    print('\n② desc 长度（官方解析器口径 ≤1024）')
    for tag, host, want in (('金融投资', FIN, 54), ('教育线', EDU, 23)):  # 金融投资 51→53→54（2026-09-25 G-68 双层证据包装机扩容 · R8 计数同步）
        rc, so, se = run([NODE, os.path.join(TOOLS, 'yaml_check_generic.cjs'),
                          os.path.join(host, '.dsh', 'skills'), JSDIR, str(want)], cwd=WORK)
        m = re.search(r'>1024 件数：(\d+)', so)
        mx = re.search(r'"([a-z0-9-]+)",\s*(\d+),\s*""', so)
        rec('desc≤1024:' + tag, '超限 0 件',
            '超限 %s ｜ 最长 %s' % (m.group(1) if m else '?',
                                  (mx.group(1) + ' ' + mx.group(2)) if mx else '?'),
            bool(m) and m.group(1) == '0')

    # ②-b 余量告警（C-8 · 信息性，**不阻断**）：余量 <100 字的件全部列出。
    # 依据：`待-08`「带长度上限的字段要"先量后写"」+ 未完成总表 C-8（dev-primary-school 954 等）。
    # 它不做判定 —— 它的价值是"让'快满了'变成每次都会看到的一行"，而不是等下次加句时才发现超限。
    print('\n②-b 余量告警（<100 字 · 信息性不阻断）')
    near = []
    for tag, host in (('金融投资', FIN), ('教育线', EDU)):
        rc, so, se = run([NODE, os.path.join(TOOLS, 'yaml_check_generic.cjs'),
                          os.path.join(host, '.dsh', 'skills'), JSDIR], cwd=WORK)
        for mm in re.finditer(r'\[\s*"([a-z0-9-]+)",\s*(\d+),\s*(\d+)\s*\]', so):
            near.append((tag, mm.group(1), int(mm.group(2)), int(mm.group(3))))
    near.sort(key=lambda x: x[3])
    rec('余量告警（信息性）', '列出余量 <100 字的件（不阻断）',
        '余量紧张 %d 件' % len(near), True,
        '；'.join('%s %s(%d,余%d)' % (t, s, l, r) for t, s, l, r in near[:6]) if near else '无')

    print('\n③ 表格完整性（关键 md 管道数一致）')
    files = [p for p in MD_WATCH if os.path.exists(p)]
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_md_tables.py')] + files)
    bad = re.findall(r'不一致的块\s*(\d+)', so)
    nbad = sum(int(x) for x in bad)
    rec('表格', '0 个不一致块', '检查 %d 份 md ｜ 不一致 %d 块' % (len(files), nbad), nbad == 0,
        '' if nbad == 0 else '（明细见 stdout）')
    if nbad:
        print(so if len(so) < 4000 else so[-4000:])

    # ③-b 缺陷台账**结构自检**（2026-09-23 新增 · 依据闸缺陷台账 `G-37`／`G-38`）
    #   为什么单列一项：`check_md_tables.py` 的口径是「**块内**管道数一致」——
    #   表被空行切成 N 段时每段自洽 ⇒ 它报 0 不一致（台账 2026-09-23 实测：正是这样漏掉的）。
    #   本项补的是**通用件看不见**的不变量：连续性／编号连续／计数句＝行数／汇总算术／标题唯一。
    #   ⚠ `check_gate_ledger.py` **不随包**（它守的是本工作区的台账）⇒ 存在性守卫 + 缺件记 N/A。
    print('\n③-b 缺陷台账结构自检（台账＝缺陷的唯一索引 · 工作区专用闸）')
    _led_tool = os.path.join(TOOLS, 'check_gate_ledger.py')
    _led = glob.glob(os.path.join(ROOT, '输出', '*闸缺陷台账*.md'))
    if not os.path.exists(_led_tool):
        rec('台账:结构自检', '本机台账结构自检全过', 'N/A（本机无该闸件 `tools\\check_gate_ledger.py`）',
            True, '该件**不随包**（工作区专用）：异机无台账文件，故缺件不判红')
    elif not _led:
        rec('台账:结构自检', '本机台账结构自检全过', 'N/A（本机未发现台账）', True,
            '发现规则：%s' % os.path.join('输出', '*闸缺陷台账*.md'))
    else:
        rcl, sol, sel = run([sys.executable, _led_tool])
        _m = re.search(r'台账结构自检全过（(\d+) 项）', sol)
        rec('台账:结构自检', '发现 %d 份台账 ⇒ 逐份结构自检全过' % len(_led),
            (_m.group(0) if _m else '🔴 见输出｜rc=%d' % rcl), rcl == 0 and bool(_m),
            '；'.join(os.path.basename(x) for x in _led))
        if rcl != 0:
            print(sol if len(sol) < 4000 else sol[-4000:])

    print('\n④ 脚本一致（插件副本 ↔ 权威）')
    rc, so, se = run([sys.executable, os.path.join(MACH, 'check_script_sync.py')])
    m = re.search(r'一致\s*(\d+)\s*个，漂移\s*(\d+)\s*个，缺失\s*(\d+)\s*个', so)
    rec('脚本同步', '一致 4 / 漂移 0 / 缺失 0',
        (m.group(0) if m else '解析失败'), bool(m) and rc == 0)

    # ④-b 打包产物新鲜度（待-01 → 闸）：解包级校验两个 tgz 与权威一致。
    # 依据：`待-01`「插件 tgz 过期会带回旧脚本」—— 2026-09-13 已**实际发生一次**
    # （修 K-18 后两个 tgz 双双失效）。把它从"要靠人记得"改成"每次收尾都红一次"。
    print('\n④-b 打包产物新鲜度（发行类闸 · 待-01）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'verify_plugin_pack.py')])
    ver = re.search(r'package\.json 版本 ([0-9.]+)', so)
    bad_tgz = len(re.findall(r'🔴', so))
    last = [l for l in (so or '').strip().split('\n') if l.strip()]
    rec('打包新鲜度(解包级)', '两个 tgz 与权威一致（rc=0）',
        'version=%s ｜ rc=%d ｜ 🔴 行 %d' % (ver.group(1) if ver else '?', rc, bad_tgz),
        rc == 0, (last[-1][:60] if last else ''))

    print('\n⑤ 机器层零新增 fail（对基线 diff）')
    cur = machine_all()
    if not os.path.exists(MBASE) or update:
        io.open(MBASE, 'w', encoding='utf-8', newline='\n').write(
            json.dumps({'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'skills': cur},
                       ensure_ascii=False, indent=1))
        rec('机器层基线', '已存在基线', '已建立/更新（%d 件）' % len(cur), True,
            '下次运行起做 diff' + ('（本次为显式 --update-baseline）' if update else ''))
    else:
        base = json.loads(io.open(MBASE, encoding='utf-8').read())['skills']
        new_fail = {k: sorted(set(v['fails']) - set(base.get(k, {}).get('fails', [])))
                    for k, v in cur.items()
                    if set(v['fails']) - set(base.get(k, {}).get('fails', []))}
        rec('机器层零新增 fail', '0 件新增扣分 fail',
            '新增 %d 件%s' % (len(new_fail), ('：' + json.dumps(new_fail, ensure_ascii=False)) if new_fail else ''),
            not new_fail)

    print('\n⑥ py_compile 全脚本')
    scripts, failed = [], []
    for d in (MACH, TOOLS, WORK):
        if not os.path.isdir(d):
            continue
        for f in _safe_listdir(d):
            if f.endswith('.py') and not f.startswith('_tmp'):
                p = os.path.join(d, f)
                scripts.append(p)
                try:
                    py_compile.compile(p, cfile=p + 'c', doraise=True)
                except Exception as e:
                    failed.append('%s: %s' % (f, str(e)[:80]))
    rec('py_compile', '%d 个脚本全部可编译' % len(scripts),
        '编译失败 %d 个' % len(failed), not failed,
        ('；'.join(failed[:3]) if failed else ''))

    # ⑦ 技能体积 vs spill 阈值（信息性，不阻断）—— 口径 K-20／坑 A-13
    # 依据：`skill` 工具返回受 `@deepseek-ai/dsh-spill-policy` 的 `maxInlineBytes` 约束，
    #   超限时以「首尾预览 ＋ spill 文件」返回，**被省略的是中段**（而中段恰是 A2 触发表／
    #   让位条款／E 段步骤／红线速查）。2026-09-13 全量实测：旧阈值 50000 下有 **16/69 件**超限；
    #   调至 120000 后只剩 1 件（social-psychology 219KB，已在其头部加大件兜底句）。
    #   本项不阻断：超阈值是**运行期降级**，不是数据损坏；修法是判断题（抬阈值／索引迁移／头部兜底）。
    print('\n⑦ 技能体积 vs spill 阈值（信息性不阻断 · K-20）')
    th = 50000          # dsh-base 默认值（未在 profile 覆盖时按此）
    pj = os.path.join(os.environ.get('DSH_HOME', (os.environ.get('DSH_HOME') or os.path.join(os.path.dirname(os.path.dirname(ROOT)), 'home'))),
                      'profiles', 'web', 'cordis.patch.yml')
    if os.path.exists(pj):
        m = re.search(r'maxInlineBytes:\s*(\d+)', io.open(pj, encoding='utf-8').read())
        if m:
            th = int(m.group(1))
    over, near = [], []
    for tag, host in (('金融投资', FIN), ('教育线', EDU)):
        root = os.path.join(host, '.dsh', 'skills')
        for slug in _safe_listdir(root):
            p = os.path.join(root, slug, 'SKILL.md')
            if not os.path.isfile(p):
                continue
            n = os.path.getsize(p)
            if n > th:
                over.append('%s %s(%.0fKB)' % (tag, slug, n / 1024))
            elif n > th * 0.85:
                near.append('%s %s(%.0fKB)' % (tag, slug, n / 1024))
    rec('技能体积 vs spill 阈值', '超阈值件列出（不阻断）｜阈值 %d' % th,
        '超阈值 %d 件 ｜ 接近(>85%%) %d 件' % (len(over), len(near)), True,
        ('超：' + '；'.join(over[:5])) if over else '无（全部件均小于阈值）')

    # ⑨-b 孤儿闸检查（信息性不阻断 · 2026-09-21）
    #   发现经过：用户问「这三条现在是一定做了还是触发时必须做？」
    #   实测：三件运行时闸通过自证、也进了包，但 preflight/postflight **一处都没引用**
    #   ⇒ "触发时必须做"在执行层无法保证（要靠"我记得跑"）。
    #   本项把「造了却没挂的闸」变成**每次都报出来的数**，保证"你不可能不知道"。
    print('\n⑨-b 孤儿闸检查（信息性不阻断）')
    _og = os.path.join(TOOLS, 'orphan_gate_check.py')
    if os.path.isfile(_og):
        _rc, _so, _se = run([sys.executable, _og, '--quiet'])
        _m = re.search(r'孤儿闸计数：(\d+)', _so or '')
        rec('孤儿闸检查', '列出"造了却没挂"的闸（不阻断）',
            '孤儿 %s 个' % (_m.group(1) if _m else '?'), True,
            '（逐条分流建议见 输出 下孤儿闸报告；本项不阻断）')
    else:
        rec('孤儿闸检查', '列出"造了却没挂"的闸（不阻断）', '🔴 检查器不存在', False, '')

    # ⑨ 同窗写检测（A-152 机械化 · 2026-09-21 第2条收敛批挂入 · **信息性不阻断**）
    #   依据：修A 与修CD 两批**并发**改同一批文件，各自带回滚器 ⇒ 同命中即互相抹掉，
    #         而两次都报成功（A-19 同族）。事后唯一可查的痕迹＝**同一窗内的成串 mtime**。
    #   为什么不阻断：mtime 同窗**也可能是一次批处理脚本的正常产物**（本闸无法区分意图），
    #     故只报警、让人去核"这两批的写集是否相交"，避免变成恒红的纸面闸（A-80 纪律）。
    print('\n⑨ 同窗写检测（A-152 · 信息性不阻断）')
    _WIN = 300            # 5 分钟窗：同窗 ≥3 件＝疑似并批写入
    _hits = []
    _wroot = os.path.join(ROOT, '.work')
    for _task in _safe_listdir(_wroot):
        _td = os.path.join(_wroot, _task)
        if not os.path.isdir(_td):
            continue
        _fs = []
        for _f in _safe_listdir(_td):
            _p = os.path.join(_td, _f)
            if os.path.isfile(_p) and _f.endswith('.md'):
                _fs.append((os.path.getmtime(_p), _f))
        if len(_fs) < 3:
            continue
        _fs.sort(reverse=True)
        _base, _grp = _fs[0][0], [_fs[0][1]]
        for _t, _n in _fs[1:]:
            if _base - _t <= _WIN:
                _grp.append(_n)
            else:
                break
        if len(_grp) >= 3:
            _hits.append('%s(%d 件)' % (_task, len(_grp)))
    rec('同窗写检测(A-152)', '同窗（%ds）≥3 件的任务目录列出（不阻断）' % _WIN,
        '疑似并批写入 %d 个任务目录' % len(_hits), True,
        ('；'.join(_hits[:4]) if _hits else '无（各任务目录最近写不同窗）'))

    # ⑧ 教育线四闸（W4 批挂入 · 2026-09-13 · 全部只读）：
    #   依据：A-17（副本漂移实测发生过 3 副本停 11 天）/ 坑 5（加载器实测）/
    #         A-21（占位符债）/ 批15 实证（validator 首跑 44/66 抓住底账漂移）。
    print('\n⑧ 教育线四闸（W4 挂入 · 只读）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_copy_freshness.py')])
    ok1 = re.search(r'✔ 副本新鲜度闸全绿', so)
    rec('edu:副本新鲜度(A-17)', '3 登记副本与源根一致（rc=0）', ('全绿' if ok1 else '🔴 见输出') + '｜rc=%d' % rc,
        rc == 0 and bool(ok1), '')

    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_desc_placeholders.py'),
                      os.path.join(EDU, '.dsh', 'skills')])
    m = re.search(r'✔ A-21 占位符扫描：(\d+) 件 desc 全部干净', so)
    rec('edu:desc占位符(A-21)', '23 件 0 处占位符（rc=0）',
        ('%s 件干净' % m.group(1)) if m else '🔴 见输出',
        rc == 0 and bool(m) and m.group(1) == '23', '')

    rc, so, se = run([NODE, os.path.join(TOOLS, 'skill_probe_generic.mjs'),
                      os.path.join(EDU, '.dsh', 'skills'), EDU], cwd=WORK)
    m = re.search(r'唯一名[：:]\s*(\d+)\s*/\s*(\d+)', so)
    rec('edu:引擎探针(坑5)', '23 件加载 0 告警（rc=0）',
        (('%s/%s 唯一名' % (m.group(1), m.group(2))) if m else '🔴 见输出'),
        rc == 0 and bool(m) and m.group(1) == '23', '')

    rc, so, se = run([NODE, os.path.join(TOOLS, 'w1b_validate.mjs'),
                      os.path.join(EDU, '.dsh', 'skills'), JSDIR,
                      os.path.join(ROOT, 'routing', 'rules-v1.yaml'),
                      os.path.join(ROOT, 'routing', 'edu-route-authority-draft', 'SKILL.md')], cwd=WORK)
    m = re.search(r'quote 子串断言 (\d+)/(\d+)', so)
    rec('edu:rules-v1底账同代', '69/69 quote 子串（rc=0）',
        (('%s/%s 子串' % (m.group(1), m.group(2))) if m else '🔴 见输出'),
        rc == 0 and bool(m) and m.group(1) == m.group(2) == '69',
        '防"规则清单落后于源根"漂移（批15 实证）')

    # ⑧-b 引文型附属文件零问题闸（§22 · ADHD 线收口批挂入；先平账后拧闸：建闸时已 8/8 过）
    # 通用化（A-74 · 2026-09-19 脱敏批）：不再写死被检任务名 —— 改为**自动发现**
    #   「声明了 incumbent gate 的任务」（其配置在**任务自己的目录**里，数据不出册）。
    _task = ''
    for _lp in sorted(glob.glob(os.path.join(ROOT, '.work', '*', 'layer-quotes-*.json'))):
        try:
            _lj = json.load(io.open(_lp, encoding='utf-8'))
        except Exception:
            continue
        if _lj.get('incumbent_gate') or _lj.get('gate_ready') is False:
            _task = _lj.get('task') or os.path.basename(os.path.dirname(_lp))
            break
    _glq = os.path.join(ROOT, '.work', _task, 'skills') if _task else ''
    if os.path.isdir(_glq):
        rc, so, se = run([sys.executable, os.path.join(TOOLS, 'gate_layer_quotes.py'),
                          '--task', _task])
        m = re.search(r'(\d+)/(\d+) 断言过', so)
        rec('edu:layer-quotes 零问题闸(§22)', '8/8 断言过（rc=0）',
            (('%s/%s 断言过' % (m.group(1), m.group(2))) if m else ('🔴 见输出｜rc=%d' % rc)),
            rc == 0, 'R1-R8：锚可解析／引文全覆盖／分栏自洽／归一化族／未命中零未处置／并集判定／空集拒跑／schema+口径')

    # ⑧-c 引文型附属文件零问题闸 · **通用版**（§22 · 2026-09-17 用户指令"把问题彻底的解决"挂入 · 只读）
    #   为什么必须挂：手册 §22.4 声称"执行单第 37 项…供后续每本书继承"，但 ⑧-b 那座闸
    #   **锚形态写死教育线** ⇒ 换册空集拒跑 ⇒ 每本书各自手搓替身（债券线 8 个脚本/29KB、
    #   manias 另写一座闸），而 `gate_checklist` 的项数常量又落后（36 vs 模板 37）⇒
    #   **第 37 项"信息性不拦"、没有任何闸看一眼**。通用闸（配置驱动）＋ 本检查＝把它纳管。
    print('\n⑧-c 引文型附属文件零问题闸（**通用版** · 配置驱动 · 只读）')
    _tasks = []
    for d in sorted(glob.glob(os.path.join(ROOT, '.work', '*'))):
        t = os.path.basename(d)
        if os.path.isfile(os.path.join(d, 'layer-quotes-%s.json' % t)):
            _tasks.append(t)
    if not _tasks:
        rec('layer-quotes 通用闸', '至少一个任务声明了当册配置', '无（不适用）', True,
            '不适用不计红；新册请在 .work/<task>/layer-quotes-<task>.json 声明锚形态/页源/引文取法')
    for t in _tasks:
        rc, so, se = run([sys.executable, os.path.join(TOOLS, 'layer_quotes_gate.py'),
                          '--task', t])
        m = re.search(r'射程内引文 (\d+).*?MISS (\d+)', so)
        na = '不适用（N/A · 自声明）' in so
        ok = (rc == 0) and (na or bool(re.search(r'R1–R8 全过', so)))
        rec('layer-quotes:%s(§22 通用)' % t,
            'R1–R8 全过（rc=0）｜或自声明不适用',
            (('N/A（gate_ready=false，由 %s 把关）' % (re.search(r'在役仪器：(.+)', so).group(1)
                                                  if re.search(r'在役仪器：(.+)', so) else '既有专用闸'))
             if na else
             ((('%s 条引文 ｜ MISS %s' % (m.group(1), m.group(2))) if m else '🔴 见输出')
              + ('' if ok else '（rc=%d）' % rc))),
            ok, 'R1 锚可解析／R2 全覆盖／R2b 射程排除带上限／R3 分栏自洽／R4 归一化族／R5 未命中零未处置／R6 并集判定／R7 空集拒跑／R8 schema+口径')

    # ⑧-d 原稿层 ↔ 在役层 **逐字节同步闸**（2026-09-17 挂入 · 只读 · 毫秒级）
    #   缺口登记：交付后的只改一层此前无闸（教育线副本有 ⑧⒜，插件/脚本/打包有各自的闸，
    #   但 .work 原稿 ↔ 宿主在役 这一对没有）⇒ 本闸补上；临时/审计区（含 tmp）默认排除并打印理由。
    print('\n⑧-d 原稿层 ↔ 在役层同步闸（只读 · 毫秒级）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_layer_sync.py')])
    m = re.search(r'同名对 (\d+).*?漂移 (\d+)', so)
    rec('layer-sync:原稿↔在役(只读)', '0 对漂移（rc=0）',
        (('同名对 %s ｜ 漂移 %s' % (m.group(1), m.group(2))) if m else '🔴 见输出'), rc == 0,
        'A-17 多层副本漂移；临时/审计区默认排除（快照性质，非缺陷）')

    # ⑧-e 引文面**仪器覆盖对账闸**（2026-09-17 挂入 · 只读 · 毫秒级）
    #   为什么需要：通用闸与教育线专用闸的**射程/切分根本不同**（A/B 可对齐键交集仅 145/1460）
    #   ⇒ 正解不是合并，而是**把并存变成受管结构**：每册要么通用闸过，要么有一座
    #   **在门禁里有座位**的专用闸（座位字符串必须真在 postflight.py 里，否则＝纸面覆盖）。
    print('\\n⑧-e 引文面仪器覆盖对账（只读）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_instrument_coverage.py')])
    m = re.search(r'有引文面的任务 (\d+) ｜ 缺口 (\d+)', so)
    rec('instrument-coverage(§22)', '0 缺口（每册都有受管仪器）',
        (('有引文面任务 %s ｜ 缺口 %s' % (m.group(1), m.group(2))) if m else '🔴 见输出'), rc == 0,
        '⒜ 通用闸（gate_ready=true → ⑧-c）｜⒝ 专用闸（gate_ready=false + incumbent_gate + seat 真存在于 postflight）')

    # ⑧-f 插件**可移植性发版闸**（2026-09-17 · 用户要求"以后做的插件都要自己把关"）
    #   判据是"**服从 env 指定的根**"而不是"能不能跑"——作者机器上写死路径照样跑得通（`A-104`）。
    print('\n⑧-f 插件可移植性（只读 · 发行前置）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_plugin_portability.py')])
    m = re.search(r'结论：(✔|🔴)', so)
    rec('plugin-portability(发行前置)', 'A/B/C 三判据全过（rc=0）',
        ('✔ 可在别人电脑上跑' if m and m.group(1) == '✔' else '🔴 见输出（**不得发布**）'), rc == 0,
        'A 包内无作者路径／B 有可覆盖出口／C 服从 env 根（A-104）')

    # ⑧-g 插件**装机态三层闸**（2026-09-18 挂入 · 只读 · NAS 装机缺陷复盘固化）
    #   由来（真机实测）：在一台 NAS 的容器里装本插件，**装了但不生效**——`dependencies` 有它、
    #   `dsh.profile.bundles` 没有它 ⇒ 引擎根本不加载（症状与会话里看不到插件一模一样，但修法完全不同）。
    #   为什么单列三层：①落盘（文件/声明）②登记（deps＋bundles＋组装树）③在役（服务＋技能根同代），
    #   三层的失败**症状同、修法不同**；只报"没生效"等于让使用者从零猜。
    #   口径：本闸带 `--self-test`（坏样本必须被拦）自证有效；作者侧"本机未装插件是常态"时判**不适用**
    #   （不假绿也不假红，原判照印）。
    print('\n⑧-g 插件装机态三层闸（只读 · 装机/换机后必跑）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'check_install_state.py'),
                      '--not-applicable-ok'])
    if '判"不适用"' in so:
        rec('install-state:三层装机态', '三层全过 或 明确不适用（rc=0）',
            'ℹ 不适用（本机 profile 未装该插件；原判已打印）', True,
            '①落盘／②登记（deps＋bundles＋组装树）／③在役（服务＋技能根同代）——A-119…A-124')
    else:
        m_g = re.search(r'结论：(✔ 三层装机态闸全绿|✗ 三层装机态闸 \d+ 层有真缺陷)', so)
        rec('install-state:三层装机态', '三层全过（rc=0）',
            (m_g.group(1) if m_g else '🔴 见输出'), rc == 0,
            '①落盘／②登记（deps＋bundles＋组装树）／③在役（服务＋技能根同代）——A-119…A-124')
    # 仪器自证：闸本身必须拦得住坏样本（A-34／A-55：新仪器交付前先过已知坏样本）
    rc2, so2, _ = run([sys.executable, os.path.join(TOOLS, 'check_install_state.py'), '--self-test'])
    rec('install-state:自证(A-55)', '坏样本全拦＋好样本全放行（rc=0）',
        ('✔ 自证通过' if re.search(r'自证通过', so2) else '🔴 见输出'), rc2 == 0,
        '4 类坏样本（无 dsh.bundle／deps 有 bundles 无／技能根不同代／语法坏）＋2 类好样本')

    # ⑨ 门禁工具子模式自检（A-32 脚本化落地 · 2026-09-13 ADHD 线阶段1.5 挂入 · 只读）
    #   依据：A-32 实证——`gate_stage --stage X` 的 docstring 承诺「0 = 该阶段可进入」，
    #   实现却取**全阶段**是否全过 ⇒ 打印「✔ 允许进入」却 rc=1，**拿它当闸用会误判**。
    #   这类缺陷（工具自述语义 ≠ 实际返回）不被任何"结果对不对"的检查抓到，
    #   只能靠「打印 ↔ 退出码一致性」的独立断言。
    print('\n⑨ 门禁工具子模式自检（A-32 · 只读）')
    rc, so, se = run([sys.executable, os.path.join(TOOLS, 'gate_selfmode_check.py')])
    if ('未找到活跃任务' in so) or ('gate_stage.py 不在' in so):
        rec('gate:子模式rc(A-32)', '无活跃任务 ⇒ 不适用', '跳过（不适用）', True, '不适用不计红')
    else:
        m = re.search(r'结论：✔ 全部阶段子模式', so)
        rec('gate:子模式rc(A-32)', '各阶段「打印 ↔ 退出码」一致（rc=0）',
            ('一致' if m else '🔴 见输出'), rc == 0 and bool(m),
            '防 A-32：工具自述语义≠实际返回')

    # ⑩ 格式判据活性（A-30 脚本化落地 · 2026-09-13 ADHD 线阶段1.5 挂入 · 只读）
    #   依据：A-30 实证——页标记正则 `[a-z]+\s*p\d+` 与源文实际格式 `--- [bark PDF p84] ---`
    #   不符 ⇒ **零命中** ⇒ 「误引页标记」检查与「剔页标记」逻辑**双双静默失效**（假通过）。
    #   判据：**命中 0 ＝ 判据失效**，不是"数据干净"。（源文格式一变就要立刻发现）
    print('\n⑩ 格式判据活性（A-30 · 只读）')
    _srcs = []
    _wd = os.path.join(ROOT, '.work')
    if os.path.isdir(_wd):
        for _t in _safe_listdir(_wd):
            _sd = os.path.join(_wd, _t, 'notes', 'source')
            if os.path.isdir(_sd):
                _srcs += [os.path.join(_sd, f) for f in _safe_listdir(_sd)
                          if f.endswith('.txt')]
    if not _srcs:
        rec('fmt:页标记正则活性(A-30)', '无分段源文 ⇒ 不适用', '跳过（不适用）', True, '')
    else:
        _pat = re.compile(r"---\s*\[[^\]]*\]\s*---")
        _n = 0
        for _p in _srcs[:20]:
            _n += len(_pat.findall(io.open(_p, encoding='utf-8', errors='ignore').read()))
        rec('fmt:页标记正则活性(A-30)', '活跃任务源文页标记命中 > 0',
            '命中 %d 处（扫 %d 份源文）' % (_n, min(len(_srcs), 20)), _n > 0,
            'A-30：命中 0 ＝ 判据失效，不是数据干净')

    # ⑪ Windows「.cmd/.bat 经 spawn 直调」静态巡检（A-52 脚本化落地 · 2026-09-15 挂入 · 只读）
    #   依据：2026-09-15 实测**双陷阱**——Node `spawnSync('<x>.cmd', …)` 在 Windows 上**不带 `shell: true`**
    #   会直接 **EINVAL、status = null**；而 `console.log('%d', null)` 会把 null **打印成 `0`**
    #   ⇒ 工具**报 rc=0 却什么都没做**（本次真实发生：npm 发布辅助脚本"假装发布成功"）。
    #   这是 A-32（工具自述语义 ≠ 实际返回）的**同族新形态**：不是"退出码写错"，而是"退出码是 null 却被印成 0"。
    #   判据（只扫用了 spawn 的脚本，避免误伤）：出现 `.cmd/.bat` 字符串字面量 ⇒ 同文件必须有
    #   `shell: true` 或 `cmd.exe` 包装；出现 `['"]%d['"] … .status` ⇒ 必须有 `status === null` 这类显式判空。
    print('\n⑪ Windows .cmd 调用需 shell（A-52 · 只读）')
    #   A-52 判据两轮修正（**两轮都是被坏样本逼出来的**）：
    #     首版只认"字符串恰好是 `%d`" ⇒ 坏样本 `console.log("rc = %d", r.status)` **漏检**（A-30 家族：判据写死单一书写形态）；
    #     放宽后再跑 ⇒ 又**误报** 3 个文件——它们印的是 `fetch` 响应的 `.status`（HTTP 状态码恒为数字，永远安全）。
    #     ⇒ 精准化：只认**由 `spawnSync(...)` 赋值出来的变量**的 `.status`（只有 spawnSync 的结果可能 status=null）。
    #       这样既接住真陷阱，又不冤枉 HTTP 状态码 —— **判据必须区分"谁的状态码"**。
    _cmd_lit = re.compile(r"""["'][^"']*\.(?:cmd|bat)["']""")
    _pctd = re.compile(r"""%d[^"'\n]*["'][^)\n]*?([A-Za-z_$][\w$]*)\.status""")
    _spawn_assign = re.compile(r"""(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*spawnSync\(""")
    _NULL_GUARD = ('status === null', 'status == null', 'status !== null', 'status ?? ')
    _scan = _cmd_hits = 0
    _bad_shell, _bad_null = [], []
    for _d in (os.path.join(ROOT, '.work'), TOOLS):
        if not os.path.isdir(_d):
            continue
        for _r, _ds, _fs in os.walk(_d):
            for _f in _fs:
                if not _f.endswith(('.mjs', '.js', '.py')):
                    continue
                _p = os.path.join(_r, _f)
                _t = io.open(_p, encoding='utf-8', errors='ignore').read()
                if not (('spawnSync(' in _t) or ('execFile(' in _t) or ('spawn(' in _t)):
                    continue
                _scan += 1
                if (_cmd_lit.search(_t) or 'pnpm.cmd' in _t or 'npm.cmd' in _t):
                    _cmd_hits += 1
                    if not (('shell: true' in _t) or ('shell:true' in _t) or ('cmd.exe' in _t)):
                        _bad_shell.append(os.path.relpath(_p, ROOT))
                _spawn_vars = set(_spawn_assign.findall(_t))
                if _spawn_vars and any(m in _spawn_vars for m in _pctd.findall(_t)) \
                        and not any(g in _t for g in _NULL_GUARD):
                    _bad_null.append(os.path.relpath(_p, ROOT))
    rec('win:cmd需shell(A-52)', '0 个 .cmd 直调（扫 %d 个 spawn 脚本）' % _scan,
        ('🔴 ' + '、'.join(_bad_shell[:3])) if _bad_shell
        else '✔ 0 个（其中 %d 个调 .cmd，均有 shell 守卫）' % _cmd_hits,
        not _bad_shell, 'A-52：不带 shell 的 .cmd 直调 = EINVAL + status=null = 假绿退出码')
    rec('win:退出码判空(A-52)', '0 处 `%d` 直印 .status（未判 null）',
        ('🔴 ' + '、'.join(_bad_null[:3])) if _bad_null else '✔ 0 处',
        not _bad_null, 'A-52：`%d` 把 null 印成 0 ⇒ 假绿；须显式判 null')

    # ⑫ 工具里"写死最新版号"静态巡检（A-53 脚本化落地 · 2026-09-15 挂入 · 只读）
    #   依据：同日晚**真实事故**——`patch_releases.mjs` 把 `LATEST = 'v4.6.5'` 写死 ⇒ 发 v4.6.6 时
    #   它给**最新的 v4.6.6 自己**盖上了"⚠️ 本版已被 v4.6.5 取代"的**反向标注**，而该标的 v4.6.5 没标。
    #   判据：`LATEST|LATEST_TAG|CURRENT_TAG|CURRENT_VERSION|TARGET_TAG` 被赋**字面版本号** ⇒ 红；
    #   确需写死的行加 `allow-hardcoded-version` 注释**显式豁免**（豁免要留痕，不许静默）。
    print('\n⑫ 工具里不得写死最新版号（A-53 · 只读）')
    _vervar = re.compile(r"""(LATEST|LATEST_TAG|CURRENT_TAG|CURRENT_VERSION|TARGET_TAG)\s*=\s*['"]v?\d""")
    _verhits, _vscan = [], 0
    for _d in (os.path.join(ROOT, '.work'), TOOLS):
        if not os.path.isdir(_d):
            continue
        for _r, _ds, _fs in os.walk(_d):
            for _f in _fs:
                if not _f.endswith(('.mjs', '.js', '.py')):
                    continue
                _p = os.path.join(_r, _f)
                _vscan += 1
                for _i, _line in enumerate(io.open(_p, encoding='utf-8', errors='ignore'), 1):
                    if 'allow-hardcoded-version' in _line:
                        continue
                    _m = _vervar.search(_line)
                    if not _m:
                        continue
                    # ⚠ 首轮实测**误报 2 处**：命中的都是**注释里引用的"旧的错误写法"**（证据文字！）
                    #   ⇒ 判据必须**跳过注释**：① 整行是注释；② 命中位置前面已有 `//` 或 `#`。
                    _head = _line.lstrip()
                    if _head.startswith(('//', '#', '*', '/*')):
                        continue
                    _before = _line[:_m.start()]
                    if ('//' in _before) or ('#' in _before):
                        continue
                    _verhits.append('%s:%d' % (os.path.relpath(_p, ROOT), _i))
    rec('ver:不得写死最新版号(A-53)', '0 处（扫 %d 个脚本）' % _vscan,
        ('🔴 ' + '、'.join(_verhits[:3])) if _verhits else '✔ 0 处',
        not _verhits, 'A-53：写死"最新版号" ⇒ 发新版时给最新版自己盖反向标注（注释内引用不算）')

    # ⑬ 波段 id 语法单一来源（A-132 · 2026-09-19 挂入 · 只读）
    #   依据（NAS 异机实测 · 活体标本）：册 `<task>` 的波段名是 `E1..E6`，产出**完全合规**，
    #   却被 `verify_candidates` 判「切块为空 ⇒ 条目 0」（假红），而**同一册**在 `gate_stage`
    #   的格式判据下是绿的 ⇒ **一手绿一手红，判决取决于用哪把尺子**。
    #   根因：这套语法在工作台里**被内联写了 17 处、共 4 种残缺写法**，而每次"修"都在另一形态上修坏
    #   （`\d+` 丢纯字母册 → `\d*`/`[0-9]*` 丢双字母前缀 → `+` **丢「字母＋数字」册**）。
    #   判据：全工作台只许有一份语法（`tools\_bandid.py`）；内联残片 ⇒ 判红。
    #   同时跑该闸的**自证**（正负样本），防"闸自己失效却报绿"（A-32/A-36 家族）。
    print('\n⑬ 波段 id 语法单一来源（A-132 · 只读）')
    _bs = os.path.join(TOOLS, 'check_bandid_single_source.py')
    if not os.path.exists(_bs):
        rec('bandid:单一来源(A-132)', '闸在位', '🔴 缺 tools\\check_bandid_single_source.py',
            False, 'A-132：语法唯一来源闸缺失 ⇒ 内联复发无法拦')
    else:
        _rcs, _sos, _ = run([sys.executable, _bs, '--selftest'])
        _sts = (r'闸自证通过' in _sos)
        rec('bandid:闸自证(A-132)', '正负样本各就各位（rc=0＋闸自证通过）',
            ('✔ 自证通过' if _sts and _rcs == 0 else '🔴 见输出'), _sts and _rcs == 0,
            'A-132：闸必须先证明自己拦得住（含"令牌贴错行不算豁免"这类自身形态）')
        _rcb, _sob, _ = run([sys.executable, _bs])
        _bsr = re.search(r'已扫\s*(\d+)\s*个文件', _sob)
        if re.search(r'未发现内联波段 id 语法', _sob) and _rcb == 0:
            rec('bandid:零内联(A-132)', '0 处内联（引用唯一真源 tools\\_bandid.py）',
                '✔ 0 处（扫 %s 个文件）' % (_bsr.group(1) if _bsr else '?'), True,
                'A-132：语法写两处＝改一处等于没改（本项曾 17 处）')
        else:
            _tail = [l.strip() for l in _sob.splitlines() if '🔴' in l][:3]
            rec('bandid:零内联(A-132)', '0 处内联（引用唯一真源 tools\\_bandid.py）',
                '🔴 ' + (' ｜ '.join(_tail) or 'rc=%s' % _rcb), False,
                'A-132：内联波段 id 语法 ⇒ 换册即假红/假绿')

    # ⑭ 随包清单双向比对（A-137 根治 · 2026-09-19 挂入 · 只读）
    #   依据（真机实测）：`tar -xzf` 覆盖解包**只增改、不删除** ⇒ 把文件移出包后，
    #   **装过旧版的机器上它照样留着**（实测：434 KB 内部手册与历史手册 4 件仍在）
    #   ⇒ "不再随包" ≠ "已从用户机器上消失"，而症状是"**我明明删了**"这种最容易被相信的假象。
    #   单向判据（"该有的在不在"）永远查不出它 ⇒ 本项是**双向**：缺件／**陈旧件**／内容不符。
    print('\n⑭ 随包清单双向比对（A-137 · 只读）')
    _pm = os.path.join(TOOLS, 'verify_pack_manifest.py')
    _plug = os.path.join(ROOT, 'distillation-director-plugin')
    if not os.path.exists(_pm):
        rec('manifest:比对闸在位(A-137)', '闸在位', '🔴 缺 tools\\verify_pack_manifest.py',
            False, 'A-137：没有清单比对闸 ⇒ 陈旧件无人发现')
    else:
        _rc1, _so1, _ = run([sys.executable, _pm, '--self-test'])
        _ok1 = ('自证通过' in _so1) and _rc1 == 0
        rec('manifest:闸自证(A-137)', '四类坏样本全拦（rc=0）',
            ('✔ 自证通过' if _ok1 else '🔴 见输出'), _ok1,
            'A-137：闸必须先证明能拦"缺件/陈旧件/内容不符/忽略项不误报"')
        if os.path.isdir(_plug):
            _rc2, _so2, _ = run([sys.executable, _pm, '--pkg-dir', _plug])
            _m = re.search(r'陈旧件（目录有、清单无）\*\* (\d+) 项', _so2)
            _ok2 = _rc2 == 0
            rec('manifest:插件目录≡清单(A-137)', '缺 0 ／ 陈旧 0 ／ 内容不符 0',
                ('✔ 逐项一致' if _ok2 else '🔴 陈旧 %s 项（见输出）' % (_m.group(1) if _m else '?')),
                _ok2, 'A-137：插件目录里不该有"清单之外"的残留（旧版遗留／编译产物／一次性脚本）')
        else:
            rec('manifest:插件目录≡清单(A-137)', '插件目录不存在 ⇒ 不适用', '跳过（不适用）', True, '')

    # ⑮ 对外数字/版本一致性（A-135 机械化 · 2026-09-19 全面体检批挂入 · 只读）
    #   依据：体检抓到 README 写着「门禁与工具 34 件」而**实物 36 件**（我加了随包清单与清单闸却没回头改 README），
    #   另有"目录结构里的版本号没跟着升""版本表里**两行都标本版**"——三条同族：
    #   **对外声明与实物不同代**。靠人记得回头改必然会漂 ⇒ 落闸（声明数 vs 实物数／版本／承诺随带件）。
    print('\n⑮ 对外数字一致性（A-135 · 只读）')
    _pn = os.path.join(TOOLS, 'check_public_numbers.py')
    if not os.path.exists(_pn):
        rec('public:数字一致性闸在位(A-135)', '闸在位', '🔴 缺 tools\\check_public_numbers.py',
            False, 'A-135：没有这个闸 ⇒ 对外数字会随实物漂移而无人发现')
    else:
        _rc1, _so1, _ = run([sys.executable, _pn, '--selftest'])
        _ok1 = ('自证通过' in _so1) and _rc1 == 0
        # ⚠ 读数必须**从闸的输出派生**，不得在这里写死（2026-09-19 第二批：闸已由 3 类坏样本
        #   扩到 5 类、由 6 项扩到 9 项，而本处文案仍写旧数 ⇒ **门禁自己的报告成了"对外数字"的漂移点**，
        #   与 A-135 同族。凡"某一处声明某个数"的地方都是独立失效点（A-138）。
        _m1 = re.search(r'自证通过（(\d+)\s*类坏样本', _so1)
        _n1 = (_m1.group(1) + ' 类坏样本全拦') if _m1 else '自证通过'
        rec('public:闸自证(A-135)', '%s（rc=0）' % _n1,
            ('✔ 自证通过' if _ok1 else '🔴 见输出'), _ok1,
            'A-135：闸必须先证明能拦"件数不一致／版本不一致／承诺随带件缺失／SKILL.md 声明数漂移／手册声明位缺失"')
        _rc2, _so2, _ = run([sys.executable, _pn])
        _ok2 = _rc2 == 0
        _bad = [l.strip() for l in _so2.splitlines() if '🔴' in l][:3]
        _m2 = re.search(r'逐项一致（(\d+)\s*项）', _so2)
        _n2 = (_m2.group(1) + ' 项逐项一致') if _m2 else '逐项一致'
        rec('public:声明≡实物(A-135)', '%s（rc=0）' % _n2,
            ('✔ 一致' if _ok2 else '🔴 ' + '｜'.join(_bad)), _ok2,
            'A-135：README/SKILL 的件数·版本·承诺随带件·内部手册声明位必须等于发行件里的实物')

    # ⑯ 插件目录解析唯一来源（A-133 第二现场 · 2026-09-19 第二批挂入 · 只读）
    #   依据：同一问题"插件目录在哪"被两个闸各写一套 ⇒ `verify_pack_manifest.py` 从 `tools\` 运行时
    #   把 `tools\` 自己当成了包，去 `tools\scripts\gates\` 找清单，**报"找不到清单 ⇒ 重装 4.9.10+"**
    #   —— 路径解析错却说成"你的包太旧"（**误导性错误比崩溃更坏**）。
    #   本项自证 `_plugdir.py`（唯一来源）能扛：包内上溯／包根／显式参数命中，空上下文与缺清单的包**不猜**。
    print('\n⑯ 插件目录解析唯一来源（A-133 · 只读）')
    _pd = os.path.join(TOOLS, '_plugdir.py')
    if not os.path.exists(_pd):
        _pd = os.path.join(TOOLS, 'scripts', 'gates', '_plugdir.py')
    if not os.path.exists(_pd):
        rec('plugdir:解析器在位(A-133)', '`tools\\_plugdir.py` 在位', '🔴 缺', False,
            'A-133：解析规则必须只有一份')
    else:
        _rc3, _so3, _ = run([sys.executable, _pd, '--selftest'])
        _ok3 = ('自证通过' in _so3) and _rc3 == 0
        # 同一台机器上必须真能解析出插件目录（"单一来源"要落到现场，不是纸面主张）
        _rc4, _so4, _ = run([sys.executable, _pd])
        _m3 = re.search(r'解析结果：(.+)', _so4)
        _resolved = _m3.group(1).strip() if _m3 else ''
        _same = bool(_resolved) and os.path.isdir(_resolved)
        rec('plugdir:解析器自证(A-133)', '3 正 3 负全过（rc=0）＋ 现场可解析出真实目录',
            ('✔ 自证通过' if _ok3 else '🔴 见输出')
            + (' ｜ 现场＝%s' % os.path.basename(_resolved) if _same else ' ｜ 🔴 现场解析失败'),
            _ok3 and _same,
            'A-133：解析器必须先证明"该中的中、不该猜的不猜"，且在本机真能解析出目录')

    # ⑰ 文档↔随包对账（2026-09-21「异机装完即用」批挂入 · 只读）
    #   依据（用户要求）："插件装在第三方电脑上，所有功能都要能正常使用"。
    #   `init_workspace.py` 只把**包内**件拷到用户 `tools\` ⇒ 文书里让用户跑的脚本若不在包内，
    #   异机用户照做即缺件，而**此前所有闸都照不到这一面**（实测首跑抓到 9 件）。
    #   判据：只认"指令型引用"（`python …X.py` 或 `tools\X.py`／`scripts\X.py`），裸名提及不算承诺。
    print('\n⑰ 文档↔随包对账（A-135 家族 · 只读）')
    _cd = os.path.join(TOOLS, 'check_doc_tool_refs.py')
    if not os.path.exists(_cd):
        rec('docrefs:闸在位', '`tools\\check_doc_tool_refs.py` 在位', '🔴 缺', False,
            '本闸用于拦住"文档让用户跑、包里却没有"这类缺件')
    else:
        _rc5, _so5, _se5 = run([sys.executable, _cd, '--quiet'])
        _m5 = re.search(r'指令型悬空 (\d+)', _so5)
        _miss5 = int(_m5.group(1)) if _m5 else 0
        _na5 = ('找不到插件根' in (_so5 + _se5)) or _rc5 == 2
        rec('docrefs:文档≡随包', '文书里让用户跑的脚本 100% 在包内（悬空 0）',
            ('不适用（本机无插件根）' if _na5 else '悬空 %d 件' % _miss5),
            _na5 or (_rc5 == 0 and _miss5 == 0),
            'A-135 家族：文档承诺的脚本必须在发行件里真实存在，否则异机装完即缺件')

    # ⑱ 页级覆盖闸在岗（防线4 从"章节级"升格为"章节级＋页级" · 2026-09-21 · 只读）
    #   依据：能力审计指出"不丢章节"只到章节级（那册自己的边界声明就写着"未逐页核对 425 页"）；
    #   实测页级锚定率 78.6%、91 页零取料（其中 90 页有实质正文）。
    #   本项判两件事（都是确定性的）：① 页级闸工具在岗；② **已出过页级覆盖报告的任务，
    #   其零覆盖页判态表必须在位**（做了什么就要做完）。
    #   ⚠ 口径（2026-09-21 首跑即修）：**只按"已开始"的任务要求**——某任务若连页级报告都没出过，
    #   属"尚未开始"（ℹ️ 计数、不阻断），不属"做漏了"。首版把所有带池任务一律要求判态表
    #   ⇒ 立刻把一个从未做过页级核验的任务判红（闸在要求"没开始的工作"，那是**假红**。
    #   同族：A-55「假红比漏检更伤」）。
    print('\n⑱ 页级覆盖闸在岗（防线4 页级 · 只读）')
    _cp = os.path.join(TOOLS, 'coverage_by_page_sample.py')
    if not os.path.exists(_cp):
        rec('pagecov:闸在位', '`tools\\coverage_by_page_sample.py` 在位', '🔴 缺', False,
            '防线4 的页级版；缺它则"零覆盖页"只能靠人肉找')
    else:
        _work_root = os.path.join(ROOT, '.work')
        _out = os.path.join(ROOT, '输出')
        _tasks, _started, _have, _notstarted = [], [], [], []
        if os.path.isdir(_work_root):
            for _d in sorted(os.listdir(_work_root)):
                _p = os.path.join(_work_root, _d)
                if not os.path.isdir(_p) or not os.path.exists(os.path.join(_p, 'verified.md')):
                    continue
                _tasks.append(_d)
                _rep = ([f for f in (os.listdir(_out) if os.path.isdir(_out) else [])
                         if ('页级覆盖' in f and _d in f)]
                        + [f for f in os.listdir(_p) if '页级覆盖' in f])
                _cands = [os.path.join(_p, '页级覆盖判态表.md'),
                          os.path.join(_p, '_页级判态'),
                          os.path.join(ROOT, '输出', '页级覆盖判态表-%s.md' % _d)]
                _has = any(os.path.exists(c) for c in _cands)
                if _rep:
                    _started.append(_d)
                    if _has:
                        _have.append(_d)
                elif _has:
                    _have.append(_d)
                else:
                    _notstarted.append(_d)
        _miss_tasks = [t for t in _started if t not in _have]
        rec('pagecov:判态表在位', '已出页级报告的任务 100% 有《页级覆盖判态表》',
            ('不适用（本机无已开始页级核验的任务）' if not _started
             else '已开始 %d 个 ／ 判态表在位 %d 个%s%s'
             % (len(_started), len(_have),
                ('｜🔴 缺：' + '、'.join(_miss_tasks[:3])) if _miss_tasks else '',
                ('｜ℹ️ 未开始（不阻断）：' + '、'.join(_notstarted[:3])) if _notstarted else '')),
            (not _started) or (not _miss_tasks),
            '防线4 页级：**做了的必须做完**（零覆盖页逐页有理由）；未开始的不算漏做')

    # ⑲ G-61④ 产物↔生成脚本可追溯（只读 · 棘轮式 · 2026-09-24 08:00 落地）
    #   G-61 本案：答卷改不出来源（生成脚本不在同目录）⇒ 判官只能核结果、核不了产出过程。
    #   棘轮口径：只对**本项落地时刻（2026-09-24 08:00）之后新写/改写的答卷**强制合规；
    #   首跑实测落地前的当日早件 8 件与其余历史件一样**只报告不拦**——规则不能追溯约束
    #   它存在之前的动作（硬拦＝假红，同 A-55）；老件一旦被改写（mtime 过线）即自动入射程。
    #   合规双通道（同 G-61① 的两个分支）：① 同目录留有生成脚本(.py)；或 ② 答卷自带
    #   「生成方式」声明（手写答卷诚实自报"模型手写、无脚本"，不逼人伪造脚本）。
    #   ⚠ 简化声明（如实）：本项只机检存在性/自报声明；「哪个脚本生成了哪个答卷」的
    #   精确归属靠 G-61①纪律＋G-62②归属登记（_writer.json），不在此闸射程。
    print('\n⑲ G-61④ 产物↔生成脚本可追溯（只读 · 棘轮式）')
    try:
        _rule_date = time.mktime(time.strptime('2026-09-24 08:00:00', '%Y-%m-%d %H:%M:%S'))
    except ValueError:
        _rule_date = 0.0
    _g61_selfdoc = re.compile(r'(生成方式|如何生成|生成脚本)')
    _ans_dirs = []
    if os.path.isdir(os.path.join(ROOT, '.work')):
        for _d in sorted(os.listdir(os.path.join(ROOT, '.work'))):
            _ad = os.path.join(ROOT, '.work', _d, 'answers')
            if os.path.isdir(_ad):
                _ans_dirs.append((_d, _ad))
    _g61_new_ok, _g61_new_bad, _g61_old_nodir, _g61_hist_n = 0, [], set(), 0
    for _tname, _ad in _ans_dirs:
        _names = _safe_listdir(_ad, 'G-61④')
        _pys = [f for f in _names if f.lower().endswith('.py')]
        for _f in _names:
            if not _f.lower().endswith('.md'):
                continue
            _fp = os.path.join(_ad, _f)
            try:
                _is_new = os.path.getmtime(_fp) >= _rule_date
            except OSError:
                continue
            if _is_new:
                try:
                    _has_selfdoc = bool(_g61_selfdoc.search(
                        io.open(_fp, encoding='utf-8', errors='replace').read()))
                except OSError:
                    _has_selfdoc = False
                if _pys or _has_selfdoc:
                    _g61_new_ok += 1
                else:
                    _g61_new_bad.append('%s/%s' % (_tname, _f))
            else:
                if not _pys:
                    _g61_old_nodir.add(_tname)
                _g61_hist_n += 1
    rec('g61:产物↔生成脚本',
        '落地时刻(2026-09-24 08:00)后新写/改写的答卷 100% 合规（同目录 .py ∥ 自带生成方式声明）；历史只报不拦',
        (('新规射程 %d 件全过%s%s' % (
            _g61_new_ok,
            ('｜🔴 新写缺来源：' + '、'.join(_g61_new_bad[:3])) if _g61_new_bad else '',
            ('｜ℹ️ 历史（含落地前当日早件）：%d 个目录无 .py ／ %d 件，不阻断' % (len(_g61_old_nodir), _g61_hist_n)) if _g61_old_nodir else ''))
         if (_g61_new_ok or _g61_new_bad or _g61_old_nodir) else '不适用（无 answers 目录）'),
        not _g61_new_bad,
        'G-61④：判官核产出过程的前提是来源找得到；棘轮＝老件被改写即入射程（只读巡检）')

    # ⑳ 引文归一化分歧探针（G-57② · 2026-09-24 · 只读）
    #   G-57 本案：引文比对曾有"两把尺子"（verify_layer_quotes.norm 删标点族 vs
    #   verify_candidates.norm_match 折叠标点）⇒ 可能"一手绿一手红"（A-04 家族）。
    #   2026-09-24 两把尺子已并成单一来源 `tools\_qnorm.py`（G-57①）；本项挂其**分歧探针**
    #   （`check_quote_norm.py`：三组样本上两尺结论必须一致；不一致 ⇒ 引文核验读数不得采信）。
    print('\n⑳ 引文归一化分歧探针（G-57② · 只读）')
    _qn = os.path.join(TOOLS, 'check_quote_norm.py')
    if not os.path.exists(_qn):
        rec('qnorm:两尺一致', '`tools\\check_quote_norm.py` 在位', '🔴 缺', False,
            'G-57②：两把尺子的分歧探针；缺它则"一手绿一手红"无法机检')
    else:
        _rc20, _so20, _se20 = run([sys.executable, _qn])
        rec('qnorm:两尺一致', '两把尺子在三组样本上结论一致（探针 rc=0）',
            ('一致（探针 rc=0）' if _rc20 == 0 else '🔴 分歧或探针错（rc=%d）' % _rc20),
            _rc20 == 0,
            'G-57②：归一化单一来源 `tools\\_qnorm.py`；本项盯两尺不再分叉')

    # ㉑ 写手归属登记巡检（G-62②③④ · 2026-09-24 · 只读）
    #   G-62 本案：同一产物被两个写手并发改写 ⇒ 后写者胜、判官所裁版本 ≠ 盘上版本。
    #   机制：每个 answers 目录一份 `_writer.json`（`tools\writer_claim.py` 登记/接管/校验）。
    #   本项只读巡检：①已登记件盘上 sha == 登记 sha（改后不重登＝漂移）；②声明了生成器的
    #   登记件，答卷 mtime ≥ 生成器 mtime（G-61 原始症状）；③棘轮＝落地时刻后新写/改写的
    #   答卷必须已登记（历史只报不拦）。
    print('\n㉑ 写手归属登记巡检（G-62②③④ · 只读）')
    _g62_land = time.mktime(time.strptime('2026-09-24 13:00:00', '%Y-%m-%d %H:%M:%S'))
    _g62_dirs, _g62_drift, _g62_genbad, _g62_ok, _g62_hist, _g62_unclaimed = 0, [], [], 0, 0, []

    def _g62_sha(_p):
        import hashlib
        _h = hashlib.sha256()
        with open(_p, 'rb') as _f:
            for _c in iter(lambda: _f.read(65536), b''):
                _h.update(_c)
        return _h.hexdigest()[:16].upper()

    for _tname, _ad in _ans_dirs:
        _wjf = os.path.join(_ad, '_writer.json')
        _mds62 = sorted(_f for _f in os.listdir(_ad) if _f.lower().endswith('.md'))
        if os.path.exists(_wjf):
            _g62_dirs += 1
            try:
                _wdata = json.load(io.open(_wjf, encoding='utf-8'))
            except Exception as _e62:
                _g62_drift.append('%s：_writer.json 不可读（%s）' % (_tname, _e62))
                continue
            for _c in _wdata.get('claims', []):
                _fp62 = os.path.join(_ad, _c.get('file', ''))
                if not os.path.exists(_fp62):
                    _g62_drift.append('%s/%s：登记件不在盘上' % (_tname, _c.get('file')))
                    continue
                if _g62_sha(_fp62) != _c.get('sha16'):
                    _g62_drift.append('%s/%s：盘上 sha ≠ 登记 sha（改后未重登）' % (_tname, _c.get('file')))
                    continue
                if _c.get('generator'):
                    _gp62 = os.path.join(_ad, _c['generator'])
                    if not os.path.exists(_gp62):
                        _g62_genbad.append('%s/%s：声明生成器 %s 不在同目录' % (_tname, _c.get('file'), _c['generator']))
                    elif os.path.getmtime(_fp62) < os.path.getmtime(_gp62):
                        _g62_genbad.append('%s/%s：答卷 mtime 早于生成器（G-61 原始症状）' % (_tname, _c.get('file')))
                _g62_ok += 1
        else:
            for _f in _mds62:
                try:
                    _new62 = os.path.getmtime(os.path.join(_ad, _f)) >= _g62_land
                except OSError:
                    continue
                if _new62:
                    _g62_unclaimed.append('%s/%s' % (_tname, _f))
                else:
                    _g62_hist += 1
    rec('g62:写手归属登记',
        '落地时刻(2026-09-24 13:00)后新写/改写的答卷 100% 有 `_writer.json` 归属登记；已登记件 sha／生成器症状零异常（历史只报不拦）',
        (('登记目录 %d ｜ 已验证登记 %d 件%s%s%s' % (
            _g62_dirs, _g62_ok,
            ('｜🔴 漂移/缺件：' + '；'.join(_g62_drift[:3])) if _g62_drift else '',
            ('｜🔴 生成器症状：' + '；'.join(_g62_genbad[:3])) if _g62_genbad else '',
            ('｜🔴 新写未登记：' + '、'.join(_g62_unclaimed[:3])) if _g62_unclaimed
            else ('｜ℹ️ 历史未登记 %d 件，不阻断' % _g62_hist if _g62_hist else '')))
         if _ans_dirs else '不适用（无 answers 目录）'),
        not (_g62_drift or _g62_genbad or _g62_unclaimed),
        'G-62②③④：登记＝writer_claim.py claim（他人接管须 --takeover 留痕）；落表前 verify --expect；'
        '漂移／生成器症状＝巡检拦截。G-62① 派发纪律（一产物一写手、先停后派）见台账')

    # ㉒ 三新闸自检（G-66/G-67/G-68 · 2026-09-25 · 只读）
    #   G-67 锚一致性（日期×引文同行共现）；G-66 池覆盖（探针→池＋精选→R 层）；
    #   G-68 证据闭包（id→全文 sha256 包；闭包/漂移双检）。三闸均带 --selftest。
    print('\n㉒ 三新闸自检（G-66/G-67/G-68 · 只读）')
    _gnew_bad = []
    for _gn in ('check_anchor_consistency.py', 'check_pool_coverage.py', 'check_evidence_closure.py'):
        _gp = os.path.join(TOOLS, _gn)
        if not os.path.exists(_gp):
            _gnew_bad.append(_gn + ' 缺')
            continue
        _rc22, _so22, _se22 = run([sys.executable, _gp, '--selftest'])
        if _rc22 != 0:
            _gnew_bad.append('%s selftest rc=%d' % (_gn, _rc22))
        if _gn == 'check_pool_coverage.py':
            # 第五轮复核 R2：常驻门禁跑池覆盖闸【全量】（防"判据只在手动全跑时生效"的假绿通道）
            _rf22, _fo22, _fe22 = run([sys.executable, _gp])
            if _rf22 != 0:
                _tail22 = [l for l in (_fo22 + _fe22).splitlines() if '🔴' in l][:3]
                _gnew_bad.append('%s 全量 rc=%d %s' % (_gn, _rf22, '；'.join(x.strip()[:90] for x in _tail22)))
    rec('g68:三新闸自检',
        'G-66/G-67/G-68 三闸 --selftest 全过（rc=0）',
        (('🔴 %s' % '；'.join(_gnew_bad)) if _gnew_bad else '自检过'),
        not _gnew_bad,
        'G-66/67/68：锚一致性／池覆盖／证据闭包三闸活性；缺件或自检红＝不得改完')

    bad = [r for r in results if r['verdict'] == 'FAIL']
    print('\n结论：%s' % ('✔ 改后门禁全绿（%d 项检查 · 含⑧教育线四闸＋⑨子模式自检＋⑩格式判据活性＋⑪Windows .cmd/退出码判空＋⑫写死版号巡检＋⑬波段 id 单源＋⑭随包清单双向＋⑮对外数字一致＋⑯插件目录解析单源＋⑰文档↔随包对账＋⑱页级覆盖闸＋⑲产物↔生成脚本＋⑳引文归一化分歧＋㉑写手归属登记＋㉒三新闸自检）' % len(results) if not bad
                        else '🔴 %d 项不符，不得宣布"改完"' % len(bad)))
    for r in bad:
        print('   - %s：期望 %s ／ 实测 %s' % (r['gate'], r['expect'], r['actual']))
    if '--json' in sys.argv:
        io.open(os.path.join(TOOLS, '_postflight_last.json'), 'w', encoding='utf-8', newline='\n').write(
            json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'results': results},
                       ensure_ascii=False, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    sys.exit(main())
