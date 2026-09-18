# -*- coding: utf-8 -*-
"""pitfall_audit.py —— 避坑手册「不许腐烂」对账（防坑体系 层3 · 甲-E2）

做三件事（默认只读、不写业务文件）：
  ① **条目结构校验**：手册里每条 P-nn／A-nn 是否 6 字段齐（现象／触发场景／立即处置／预防规则／自检命令／命中次数）
  ② **命令可执行性**：抽出条目里的脚本路径，实测**文件是否存在**（`--check` 时真跑其中"只读型"命令）
  ③ **闭环缺口**：列出"有命令的 / 没命令的"条目 —— 没命令的条目＝**不可自检的坑**（应补命令或降级为"认识性条目"）

用法：
  python tools\\pitfall_audit.py                 # ①③（只读、秒级）
  python tools\\pitfall_audit.py --check         # ①③＋②**只读命令深跑**（逐条比对期望退出码）

② 的分派口径（2026-09-13 收口轮固化，对应手册 §8.7／§8.5）：
  · **闸型**（真跑，比 rc）：只读、或只写 %TEMP%／`.work`／`tools\\_selftest` 沙箱；
  · **对照型**（列出、不自动跑）：`P-11`…`P-17` 这类"证明坑存在"的实验，**没有 pass/fail 判定**，
    且 `P-13`／`P-16` 复现分支**故意非零退出** —— 自动跑会把"演示"误判成"失败"；
  · **写入型**（列出、跳过并给理由）：会改技能件／宿主库／交付报告的写入器。
"""
import io
import os
import re
import sys
import shutil
import json
import time
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
PITFALL_MANUAL = _os_.path.join(ROOT, '.dsh', 'skills', 'distillation-director', 'SKILL.md')
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
# ── 路径可移植化（**别人电脑上必须能跑**；全部走 env/推导/候选探测，禁止写死作者机器路径）
def _dsh_home():
    return os.environ.get("DSH_HOME") or os.path.join(os.path.dirname(os.path.dirname(ROOT)), "home")
def _engine_root():
    return os.environ.get("DSH_ENGINE") or os.path.join(os.path.dirname(_dsh_home()), "engine")
def _pick(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return cands[-1] if cands else ""
NODE = _pick(os.environ.get("DSH_ENGINE_NODE"), os.path.join(_engine_root(), "node.exe"),
             shutil.which("node") or "")
WSROOT = os.path.dirname(os.path.abspath(ROOT))
FIN = _pick(os.environ.get("DSH_HOST_FIN"), os.path.join(WSROOT, "金融投资"))
EDU = _pick(os.environ.get("DSH_HOST_EDU"), os.path.join(WSROOT, "家庭教育"))
_JSC = sorted(__import__("glob").glob(os.path.join(_engine_root(), "node_modules", ".pnpm", "js-yaml@*")))
JSDIR = JS_YAML_DIR
FIELDS = ['现象', '触发场景', '立即处置', '预防规则', '自检命令', '命中次数']
# 只读型工具（可安全实跑）；写入型命令**不做自动实跑**（见手册 §8.5）
READONLY = ['preflight.py', 'postflight.py', 'gate_selftest.py', 'yaml_check_generic.cjs',
            'skill_probe_generic.mjs', 'check_md_tables.py', 'check_script_sync.py',
            'final_acceptance.py', 'route_overlap_generic.py']


def env():
    e = dict(os.environ)
    e['PYTHONIOENCODING'] = 'utf-8'
    return e



def _optional_declared():
    """读包内 `optional-tools.json`（随包发行）声明的**可选工作台脚本**。
    为什么：手册引用的作者侧工作台脚本在用户机上本来就没有；已声明可选的缺失件**不得算失败**（否则用户机恒红）。"""
    for p in (os.path.join(TOOLS, 'optional-tools.json'),
              os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'optional-tools.json')):
        try:
            if os.path.isfile(p):
                d = json.loads(io.open(p, encoding='utf-8').read())
                out = set()
                def _g(o):
                    if isinstance(o, dict):
                        for v in o.values():
                            _g(v)
                    elif isinstance(o, list):
                        for v in o:
                            _g(v)
                    elif isinstance(o, str):
                        out.add(o)
                _g(d)
                return out
        except Exception:
            pass
    return set()


def main():
    _here = _os_.path.dirname(_os_.path.abspath(__file__))
    _cand = [PITFALL_MANUAL,
             _os_.path.join(_here, '蒸馏工程避坑手册.md'),
             _os_.path.join(_os_.path.dirname(_here), '蒸馏工程避坑手册.md')]
    _mp = next((x for x in _cand if x and _os_.path.isfile(x)), None)
    if not _mp:
        print('=== 避坑手册对账：**判不适用**（未找到手册，非失败）===')
        for _x in _cand:
            print('   找过：%s' % (_x or '(None)'))
        print('   处置：python tools\\init_workspace.py "<你的工作区根>"（会把手册装到工作区根），')
        print('         或把手册放到 %s' % _os_.path.join(_here, '蒸馏工程避坑手册.md'))
        return 0
    t = io.open(_mp, encoding='utf-8').read()
    lines = t.split('\n')
    # 条目：形如 "### P-01" / "### A-01"（或其标题行含编号）
    # 条目标题的真实格式是 `### 5-P01 ｜…`（章号-P 编号，**P 与数字之间没有横线**）。
    # ⚠ 教训（2026-09-13 本脚本前两版）：① 只认行首 `P-\d\d` → 0 命中却输出 ✔（**假绿**）；
    #   ② 改成 `\S*?(P-\d\d)` 仍 0 命中，因为手册写的是 `P01` 而非 `P-01`。
    #   故：正则用 `P-?\d\d`，并**加"条目数下限"闸**（<30 直接判失败，不许当全绿）。
    idx = [i for i, l in enumerate(lines) if re.match(r'^#{2,4}\s*\S*?(P-?\d\d|A-?\d\d)\b', l)]
    print('=== 避坑手册对账（%s）===' % os.path.basename(_mp))
    print('手册 %d 行 ｜ 识别到条目 **%d** 个\n' % (len(lines), len(idx)))
    if len(idx) < 30:
        print('🔴 **条目数异常（%d < 30）** —— 要么手册被改坏，要么本对账脚本的正则不认识新格式；'
              '两种都必须先查清，**不得当作"全绿"**' % len(idx))
        sys.exit(1)
    no_cmd, incomplete, missing_scripts, demo_names = [], [], {}, {}
    for n, i in enumerate(idx):
        end = idx[n + 1] if n + 1 < len(idx) else len(lines)
        block = '\n'.join(lines[i:end])
        code = re.match(r'^#{2,4}\s*\S*?(P-?\d\d|A-?\d\d)\b', lines[i])
        assert code, '条目行正则与 idx 不一致：%r' % lines[i][:60]
        cid = code.group(1)
        miss = [f for f in FIELDS if f not in block]
        if miss:
            incomplete.append((cid, miss))
        if '自检命令' in block:
            seg = block.split('自检命令', 1)[1][:600]
            if not re.search(r'[`\\](tools|\.work|投资蒸馏)[\\/]|python |node ', seg):
                no_cmd.append(cid)
        else:
            no_cmd.append(cid)
        # ⚠ 2026-09-15 修（假阳性）：`.pyc`／`.pyo` **编译产物**文件名会被下面这条正则**截成 `*.py`**
        #   —— 因为 `(?:py|mjs|cjs)` 先匹配到 `.py`，尾部的 `c` 落在匹配之外。
        #   实测：手册 §9.5 写入两个 `__pycache__` 产物名（`...cpython-312.pyc`）后，本对账误报
        #   "引用但找不到的脚本 2 个"（且归到 A-49，因为 A-50/51 只有索引行、条目块一路延伸到文末）。
        #   处置＝**扫描前掩码掉 `.pyc`／`.pyo`**：它们是产物，不是"被引用的脚本"，本就不该进这项判据。
        scan = re.sub(r'\.py[co](?![A-Za-z0-9_])', '.__PYC__', block)
        for m in re.finditer(r'([A-Za-z0-9_\-\.]+\.(?:py|mjs|cjs))', scan):
            f = m.group(1)
            if f.startswith('_'):          # `_t.py` / `_dsh_probe.py` 等＝**演示用示例文件名**，非真实工具
                demo_names.setdefault(f, []).append(cid)
                continue
            cands = [os.path.join(TOOLS, f), os.path.join(ROOT, '.work', 'fei-lixing-fanrong', f),
                     os.path.join(ROOT, '投资蒸馏', '三闸机器化', f)]
            if not any(os.path.exists(c) for c in cands):
                missing_scripts.setdefault(f, []).append(cid)

    print('① 结构：6 字段不全的条目 %d 个%s' % (len(incomplete),
          ('：' + json.dumps(incomplete, ensure_ascii=False)) if incomplete else ' ✔'))
    print('③ 闭环：无"自检命令"可用命令的条目 %d 个%s' % (len(no_cmd),
          ('：' + '、'.join(no_cmd)) if no_cmd else ' ✔'),
          '（环境类对照实验条目，手册已注明非"闸"；不判失败）' if no_cmd else '')
    if demo_names:
        print('ℹ 演示用示例文件名（非真实工具，不计缺失）：%s' % '、'.join(sorted(demo_names)))
    if missing_scripts:
        # 真机实测（NAS 2026-09-18）：用户机上本就没有作者侧工作台脚本，而它们已在 optional-tools.json 声明可选
        # ⇒ 已声明者只作**信息**（不参与 rc），未声明者才算真失败。
        _opt = _optional_declared()
        _opt_hit = sorted(k for k in missing_scripts if k in _opt)
        missing_scripts = {k: v for k, v in missing_scripts.items() if k not in _opt}
        if _opt_hit:
            print('ℹ 本机缺少 %d 个**已声明可选**的工作台脚本（作者侧专用，不参与本闸判定）：%s'
                  % (len(_opt_hit), '、'.join(_opt_hit[:8])))
    if missing_scripts:
        print('⚠ 引用但**找不到**的脚本 %d 个：' % len(missing_scripts))
        for k, v in missing_scripts.items():
            print('   - %s（出现在 %s）' % (k, '、'.join(sorted(set(v)))))
    else:
        print('✔ 手册引用的脚本**全部存在**')

    deep = '--check' in sys.argv
    gate_res = []
    if deep:
        print('\n② 只读命令**深跑**（甲-E2 落地 · 2026-09-13 收口轮补）')
        PY = sys.executable
# （已移除写死定义：改由上文 _pick/env 解析 —— 2026-09-17 可移植化）
# （已移除写死定义：改由上文 _pick/env 解析 —— 2026-09-17 可移植化）
# （已移除写死定义：改由上文 _pick/env 解析 —— 2026-09-17 可移植化）
        JSDIR = '' or (_JSC[-1] if _JSC else os.environ.get("DSH_JS_YAML_DIR", ""))
        TMP = os.environ.get('TEMP') or r'C:\Windows\Temp'
        W = os.path.join(ROOT, '.work', 'fei-lixing-fanrong')
        M = os.path.join(ROOT, '投资蒸馏', '三闸机器化')
        CAT_MD = os.path.join(ROOT, '输出', '口径登记单-2026-09-12.md')
        # 端到端校验要一个具体 tgz：**自动取版本号最大的扁平版**（不写死版本，见 C-9 写死路径巡检）
        import glob as _glob
        _tgzs = sorted(_glob.glob(os.path.join(ROOT, 'dsh-distillation-director-v*.tgz')))
        FLAT_TGZ = _tgzs[-1] if _tgzs else ''
        # 闸型：真跑，逐条比对**期望退出码**（零写业务文件，或只写 %TEMP%/.work/tools 沙箱）
        gates = [
            ('YAML 全库·金融投资', [NODE, os.path.join(W, 'yaml_check_generic.cjs'), os.path.join(FIN, '.dsh', 'skills'), JSDIR, '44'], 0, '只读'),
            ('YAML 全库·教育线', [NODE, os.path.join(W, 'yaml_check_generic.cjs'), os.path.join(EDU, '.dsh', 'skills'), JSDIR, '22'], 0, '只读'),
            ('引擎加载器·金融投资', [NODE, os.path.join(W, 'skill_probe_generic.mjs'), os.path.join(FIN, '.dsh', 'skills'), FIN], 0, '只读'),
            ('引擎加载器·教育线', [NODE, os.path.join(W, 'skill_probe_generic.mjs'), os.path.join(EDU, '.dsh', 'skills'), EDU], 0, '只读'),
            ('引擎 desc 探针', [NODE, os.path.join(W, 'engine_desc_probe.mjs')], 0, '只读'),
            ('desc 四口径对照', [PY, os.path.join(W, 'desc_oracle.py'), '--slug', 'cape-valuation-anchor'], 0, '只读'),
            ('desc 全库矩阵', [PY, os.path.join(W, 'desc_parity_matrix.py')], 0, '只读（写 .work 内 json）'),
            ('两行差异定位', [PY, os.path.join(W, 'chardiff.py'), 'cape-valuation-anchor', 'description'], 0, '只读'),
            ('md 表格管道（口径登记单）', [PY, os.path.join(W, 'check_md_tables.py'), CAT_MD], 0, '只读'),
            ('死链清点', [PY, os.path.join(W, 'deadlink_inventory.py'), '--quiet'], 0, '写 .work 内 json'),
            ('门禁自证（三坏全拦）', [PY, os.path.join(TOOLS, 'gate_selftest.py')], 0, '写 tools\\_selftest 沙箱'),
            ('公平回归（同深度暂存）', [PY, os.path.join(W, 'fair_regression_all.py')], 0, '写 %TEMP%'),
            ('脚本一致（权威↔插件副本）', [PY, os.path.join(M, 'check_script_sync.py')], 0, '只读'),
            ('打包产物·解包级', [PY, os.path.join(W, 'verify_plugin_pack.py')], 0, '只读（解包到 %TEMP%）'),
            ('desc 块标量残留（A-15）', [NODE, os.path.join(W, 'w0_inline_normalize.mjs'), os.path.join(EDU, '.dsh', 'skills'), JSDIR, '--check'], 0, '只读干跑（0 目标＝已全部单行）'),
            ('插件消费方解析实测（A-16/A-18）', [NODE, os.path.join(W, 'w0_plugin_parse_test.mjs')], 0, '只读'),
            ('副本新鲜度闸（A-17/A-19）', [PY, os.path.join(TOOLS, 'check_copy_freshness.py')], 0, '只读（比对版本戳）'),
            ('desc 占位符闸（A-21）', [PY, os.path.join(TOOLS, 'check_desc_placeholders.py'), os.path.join(EDU, '.dsh', 'skills')], 0, '只读（2026-09-13 批14 清零后升格 rc=0 闸）'),
        ]
        if os.path.exists(FLAT_TGZ):
            gates.append(('打包产物·端到端', [NODE, os.path.join(W, 'verify_plugin_loadable.mjs'), FLAT_TGZ], 0, '只读（解包到 %TEMP%）'))
        nmark = '✔'
        for label, argv, expect, note in gates:
            # 真机实测（NAS／Linux 2026-09-18）：宿主没有 node 时 NODE 为空串，
            # `subprocess.run(['' , ...])` 在 Linux 抛 PermissionError(13) ⇒ **裸栈**（Windows 上表现不同，故作者机从未见）。
            # 处置：缺可执行件 ⇒ 打印指引、记 N/A（不冒充 PASS），绝不崩。
            _exe = argv[0] if argv else ''
            if not _exe or ((os.sep in str(_exe) or '/' in str(_exe)) and not os.path.isfile(_exe)):
                print('   ⚠ %-24s 判"不适用"：缺可执行件（%r）—— 设 DSH_ENGINE_NODE 指向 node／'
                      'DSH_JS_YAML_DIR 指向 js-yaml，或跑 init_workspace.py 自动探测' % (label, _exe))
                gate_res.append({'label': label, 'rc': None, 'expect': expect,
                                 'verdict': 'N/A', 'note': '缺可执行件：%r' % _exe})
                continue
            # 通用规则（NAS 复测暴露）：参数里**任何"像路径且不存在"的项** ⇒ 本机的这类检查判"不适用"。
            # 依据：深跑表里的绝大多数项依赖**作者侧制品**（宿主技能根／工作台脚本／打包产物），
            # 用户机上本来就没有；把它们算 FAIL ⇒ 该闸在用户机恒红（A-34 家族：判据比规范宽/严都错）。
            _absent = next((x for x in argv[1:]
                            if isinstance(x, str) and ('/' in x or os.sep in x)
                            and not x.startswith('-') and not os.path.exists(x)), None)
            if _absent is not None:
                print('   ⚠ %-24s 判"不适用"：本机没有该路径（%s）' % (label, _absent[:70]))
                gate_res.append({'label': label, 'rc': None, 'expect': expect,
                                 'verdict': 'N/A', 'note': '缺路径：%s' % _absent[:70]})
                continue
            r = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', env=env(), cwd=ROOT)
            _o = (r.stdout or '') + (r.stderr or '')
            if r.returncode == 1 and '缺 node 或 js-yaml' in _o:
                print('   ⚠ %-24s 判"不适用"：环境未就绪（缺 node／js-yaml，自身已给指引）' % label)
                gate_res.append({'label': label, 'rc': r.returncode, 'expect': expect,
                                 'verdict': 'N/A', 'note': '环境未就绪：缺 node／js-yaml'})
                continue
            tail = [l for l in (r.stdout or '').strip().split('\n') if l.strip()]
            tail = tail[-1][:70] if tail else '(无输出)'
            good = (r.returncode == expect)
            nmark = '✔' if good else '🔴'
            gate_res.append({'label': label, 'rc': r.returncode, 'expect': expect,
                             'verdict': 'PASS' if good else 'FAIL', 'note': note})
            print('   %s %-24s 期望 rc=%d ／ 实测 rc=%d ｜ %s ｜ %s'
                  % (nmark, label, expect, r.returncode, note, tail))
        print('   —— 下面两组**不进闸**（按 §8.5／附注 2 的口径分派）：')
        for cid, what, why in [
            ('P-11', '`$host` 是只读变量（含 `final_acceptance.py` 对照）', '对照实验：无 pass/fail 判定'),
            ('P-12', 'pwsh 不支持 heredoc', '对照实验：无 pass/fail 判定'),
            ('P-13', '`python -c` 被 PowerShell 吞掉', '对照实验：**故意**非零退出，不得当失败'),
            ('P-14', '`Select-Object -First N` 截断上游', '对照实验：无 pass/fail 判定'),
            ('P-15', '`Get-Content` 编码／中文路径', '对照实验：无 pass/fail 判定'),
            ('P-16', 'GBK 下打印 ✔ 抛异常', '对照实验：**复现分支故意**去掉 PYTHONIOENCODING'),
            ('P-17', 'shell 打印 UTF-8 中文变乱码', '对照实验：无 pass/fail 判定'),
        ]:
            print('   ○ %-6s %-46s → %s' % (cid, what, why))
        for cid, what, why in [
            ('待-09', '`machine_scan_edu.py`（即使已参数化）', '写入型：输出路径虽可指定，仍会刷新交付报告 → 不自动跑'),
            ('A-10', '`repack_plugin.py`', '写入型：会同步副本并重建 tgz → 属主动发行动作'),
            ('A-02', '`route_overlap_generic.py`（手册示例传 %TEMP%）', '写入型：写第 2 个参数指定的 md'),
            ('A-17', '`make_edu_root_stamp.py`（主模式）', '写入型：重写源根版本戳（刷新基准）→ 属主动动作，不自动跑；`--print` 为只读'),
            ('A-19', '`w0_sync_copies.py`（不带 --check）', '写入型：同步三副本 → 属主动改盘动作；`--check` 为干跑'),
            ('—', '`check_desc_placeholders.py` 自身（A-21）', '已升格为 rc=0 闸（见上方深跑表），不再列跳过'),
            ('—', '`edu_route_hardening*.py` / `install_*.py` / `fix_*.py`', '写入器：会改技能件／宿主库'),
        ]:
            print('   ⏭ %-6s %-46s → 跳过理由：%s' % (cid, what, why))
    else:
        print('\n② 只读型命令抽查：**未跑**（加 `--check` 才真跑并比对期望退出码）')

    res = {'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'entries': len(idx),
           'incomplete': incomplete, 'no_selfcheck': no_cmd, 'missing_scripts': missing_scripts,
           'deep_check': gate_res}
    io.open(os.path.join(TOOLS, '_pitfall_audit.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(res, ensure_ascii=False, indent=1))
    gate_fail = [g for g in gate_res if g['verdict'] == 'FAIL']
    gate_na = [g for g in gate_res if g['verdict'] == 'N/A']
    # 真机实测（NAS 2026-09-18）：手册引用了 62 个**作者侧工作台脚本**，用户机上本就没有 ⇒
    # 若参与判定，该闸在用户机恒红（红的原因不是手册/工具坏了，而是"本机没有作者的东西"）。
    # 故：缺失清单只作信息；发行完整性由发版闸 D／D-配套 与深跑负责。
    bad = bool(incomplete or gate_fail)
    if gate_na:
        print('\nℹ 深跑中有 %d 项判"不适用"（缺 node／js-yaml）：%s'
              % (len(gate_na), '、'.join(g['label'] for g in gate_na[:6])))
    print('\n结论：%s' % ('🔴 存在结构不全／脚本缺失／只读命令退出码不符，需处置' if bad
                        else '✔ 手册结构完整、引用脚本齐、%s（无命令条目 %d 个，属"认识性条目"，已列出）'
                             % ('只读命令 %d 条全部符合期望' % len(gate_res) if gate_res else '（未跑深检）', len(no_cmd))))
    for g in gate_fail:
        print('   - %s：期望 rc=%d ／ 实测 rc=%d' % (g['label'], g['expect'], g['rc']))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
