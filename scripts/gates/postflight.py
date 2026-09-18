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

# 表格门禁覆盖的关键 md（我方交付文档；判官/证据文件按纪律不纳入）
MD_WATCH = [
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
    for tag, host, want in (('金融投资', FIN, 49), ('教育线', EDU, 23)):  # 教育线 22→23（2026-09-13 深夜 ADHD 专业线装机 · R8 计数同步）
        rc, so, se = run([NODE, os.path.join(WORK, 'yaml_check_generic.cjs'),
                          os.path.join(host, '.dsh', 'skills'), JSDIR, str(want)], cwd=WORK)
        m = re.search(r'YAML 解析通过：(\d+) / (\d+)', so)
        rec('yaml:' + tag, '%d/%d' % (want, want),
            (m.group(0).replace('YAML 解析通过：', '') if m else '解析失败'),
            bool(m) and int(m.group(1)) == want and rc == 0)

    print('\n② desc 长度（官方解析器口径 ≤1024）')
    for tag, host, want in (('金融投资', FIN, 49), ('教育线', EDU, 23)):  # 教育线 22→23（2026-09-13 深夜 ADHD 专业线装机 · R8 计数同步）
        rc, so, se = run([NODE, os.path.join(WORK, 'yaml_check_generic.cjs'),
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
        rc, so, se = run([NODE, os.path.join(WORK, 'yaml_check_generic.cjs'),
                          os.path.join(host, '.dsh', 'skills'), JSDIR], cwd=WORK)
        for mm in re.finditer(r'\[\s*"([a-z0-9-]+)",\s*(\d+),\s*(\d+)\s*\]', so):
            near.append((tag, mm.group(1), int(mm.group(2)), int(mm.group(3))))
    near.sort(key=lambda x: x[3])
    rec('余量告警（信息性）', '列出余量 <100 字的件（不阻断）',
        '余量紧张 %d 件' % len(near), True,
        '；'.join('%s %s(%d,余%d)' % (t, s, l, r) for t, s, l, r in near[:6]) if near else '无')

    print('\n③ 表格完整性（关键 md 管道数一致）')
    files = [p for p in MD_WATCH if os.path.exists(p)]
    rc, so, se = run([sys.executable, os.path.join(WORK, 'check_md_tables.py')] + files)
    bad = re.findall(r'不一致的块\s*(\d+)', so)
    nbad = sum(int(x) for x in bad)
    rec('表格', '0 个不一致块', '检查 %d 份 md ｜ 不一致 %d 块' % (len(files), nbad), nbad == 0,
        '' if nbad == 0 else '（明细见 stdout）')
    if nbad:
        print(so if len(so) < 4000 else so[-4000:])

    print('\n④ 脚本一致（插件副本 ↔ 权威）')
    rc, so, se = run([sys.executable, os.path.join(MACH, 'check_script_sync.py')])
    m = re.search(r'一致\s*(\d+)\s*个，漂移\s*(\d+)\s*个，缺失\s*(\d+)\s*个', so)
    rec('脚本同步', '一致 4 / 漂移 0 / 缺失 0',
        (m.group(0) if m else '解析失败'), bool(m) and rc == 0)

    # ④-b 打包产物新鲜度（待-01 → 闸）：解包级校验两个 tgz 与权威一致。
    # 依据：`待-01`「插件 tgz 过期会带回旧脚本」—— 2026-09-13 已**实际发生一次**
    # （修 K-18 后两个 tgz 双双失效）。把它从"要靠人记得"改成"每次收尾都红一次"。
    print('\n④-b 打包产物新鲜度（发行类闸 · 待-01）')
    rc, so, se = run([sys.executable, os.path.join(WORK, 'verify_plugin_pack.py')])
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

    rc, so, se = run([NODE, os.path.join(WORK, 'skill_probe_generic.mjs'),
                      os.path.join(EDU, '.dsh', 'skills'), EDU], cwd=WORK)
    m = re.search(r'唯一名[：:]\s*(\d+)\s*/\s*(\d+)', so)
    rec('edu:引擎探针(坑5)', '23 件加载 0 告警（rc=0）',
        (('%s/%s 唯一名' % (m.group(1), m.group(2))) if m else '🔴 见输出'),
        rc == 0 and bool(m) and m.group(1) == '23', '')

    rc, so, se = run([NODE, os.path.join(WORK, 'w1b_validate.mjs'),
                      os.path.join(EDU, '.dsh', 'skills'), JSDIR,
                      os.path.join(ROOT, 'routing', 'rules-v1.yaml'),
                      os.path.join(ROOT, 'routing', 'edu-route-authority-draft', 'SKILL.md')], cwd=WORK)
    m = re.search(r'quote 子串断言 (\d+)/(\d+)', so)
    rec('edu:rules-v1底账同代', '69/69 quote 子串（rc=0）',
        (('%s/%s 子串' % (m.group(1), m.group(2))) if m else '🔴 见输出'),
        rc == 0 and bool(m) and m.group(1) == m.group(2) == '69',
        '防"规则清单落后于源根"漂移（批15 实证）')

    # ⑧-b 引文型附属文件零问题闸（§22 · ADHD 线收口批挂入；先平账后拧闸：建闸时已 8/8 过）
    _task = 'adhd-pro'
    _glq = os.path.join(ROOT, '.work', _task, 'skills', 'adhd-parenting-guide', 'references')
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
    #   依据（NAS 异机实测 · 活体标本）：册 `cn-pop-2100` 的波段名是 `E1..E6`，产出**完全合规**，
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

    bad = [r for r in results if r['verdict'] == 'FAIL']
    print('\n结论：%s' % ('✔ 改后门禁全绿（%d 项检查 · 含⑧教育线四闸＋⑨子模式自检＋⑩格式判据活性＋⑪Windows .cmd/退出码判空＋⑫写死版号巡检＋⑬波段 id 单源）' % len(results) if not bad
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
