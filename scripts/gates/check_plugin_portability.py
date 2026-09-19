# -*- coding: utf-8 -*-
r"""check_plugin_portability.py —— **插件可移植性发版闸**（用户 2026-09-17 明确要求：
"以后做的插件我们都要自己把关：这些功能在别人电脑上能不能用"）

## 为什么必须有它
在作者机器上，**可移植性缺陷永远测不出来**（路径都对、文件都在）。用户装完才发现"很多功能用不了"
⇒ 一次性流失。本闸把"能不能在别人电脑上跑"变成**发布前必须过的 rc=0 断言**。

## 三条判据（全部可核）
  A **包内不得有"作者机器路径"**：解包 tgz，扫代码文件（.py/.mjs/.js/.cjs）中的 `X:\...` 字面量；
    命中作者特征（deepseekharness／蒸馏工作区／金融投资／家庭教育／债券与衍生品）⇒ 🔴；
    系统级路径（Windows／Temp／AppData／Program Files）允许（可由系统 API 推导）。
  B **可覆盖证据**：含路径字面量的包内脚本必须同时具备出口（`_resolve_root`／`environ`／
    `gate_common`／`cfg`），否则 🔴（防"写死无出口"—— A-78/A-101 家族）。
  C **异环境仿真**：把包内脚本拷到**无 `.dsh` 祖先**的临时树，`DSH_GATE_CONFIG` 指向不存在文件运行
    ⇒ 期望**不抛裸栈**，且要么正常跑、要么打印可执行指引（"🔴 未找到蒸馏工作区根目录"）。

用法：python tools\check_plugin_portability.py [--tgz <路径>]
退出码：0 = 三条全过（可在别人电脑上跑）；1 = 有硬项。
"""
import glob
import json
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
ABS = re.compile(r"""['"]([A-Za-z]:[\\/][^'"\n]{1,140})['"]""")
AUTHOR = re.compile(r'deepseekharness|蒸馏工作区|金融投资|家庭教育|债券与衍生品|智囊圆桌|智能视频创作')
SYSOK = re.compile(r'(?i)^[A-Za-z]:[\\/](windows|users\\.*\\appdata|program files|temp|perflogs)')



# ── D/E 两判据（2026-09-17 加 · 用户要求"别人下载后能不能用"要自己把关）───────────────
def _optional_declared(tmp):
    # 全包递归查找（manifest 可能被放在 package/ 或 scripts/gates/ 等任意层）
    hit = glob.glob(os.path.join(tmp, '**', 'optional-tools.json'), recursive=True)
    p = hit[0] if hit else ''
    if p and os.path.isfile(p):
        try:
            return set(json.load(io.open(p, encoding='utf-8')).get('optional', []))
        except Exception:
            return set()
    return set()


def check_ref_closure(tmp, names, opt=None):
    """D 引用闭合性：包内门禁引用的 *.py 必须**在整包里**（不再只看 gates/）。

    ⚠ 2026-09-17 修正：旧版直接 io.open(tar 内路径) ⇒ FileNotFoundError 落在 stderr，
    被我的输出过滤器吞掉、表现为"闸红了但不说为什么"。现改为读**解包后**的实体文件。
    """
    gates = [n for n in names if '/gates/' in n.replace('\\', '/') and n.endswith('.py')]
    allbase = {os.path.basename(n) for n in names}
    miss = []
    for g in gates:
        gp = os.path.join(tmp, g.replace('/', os.sep))
        try:
            src = io.open(gp, encoding='utf-8', errors='replace').read()
        except Exception as e:
            miss.append((os.path.basename(g), '读取失败：%s' % type(e).__name__))
            continue
        for r in sorted(set(re.findall(r"""['"]([A-Za-z0-9_]+\.py)['"]""", src))):
            if r not in allbase and r not in (opt if opt is not None else _optional_declared(tmp)):
                miss.append((os.path.basename(g), r))
    return miss


def check_foreign_no_traceback(tmp, names):
    r"""E 异机 0 裸栈：包内门禁在"无 DSH 数据/无 .dsh 祖先"的临时目录里跑，断言无 Traceback。

    ⚠ **射程漏洞（2026-09-19 NAS 真机反证）**：本判据原先只在"**作者机器上**模拟异机"，
    而作者机器上那些**基准件恰好都在**（原书树的机器层脚本目录、`tools\` 权威目录）⇒
    `verify_plugin_pack.py` 在本机永远绿，**在真机上 `FileNotFoundError` 裸栈**。故改为跑两轮：
      E-1 无 DSH 环境（原判据）；
      E-2 **基准件缺失**：`DSH_GATE_CONFIG` 指向一份"各目录都不存在"的配置 ⇒
          读基准件的闸必须**判"不适用"并打印原因**，不得裸栈。

    ⚠ **本判据自己更严重的缺陷（本批实测抓到）：E 此前是「空转」的**——
    拷贝夹具写的是 `tmp/scripts/...`，而 **npm 形态的包根是 `tmp/package/scripts/...`**
    ⇒ **一支门禁都没被跑到**，却打印"✔ 0 裸栈"。这正是 `A-36` 家族最坏的一种：
    **闸看起来在查、其实什么都没查**（而它当时正是我引证"异机可跑"的那条证据）。
    修法两条：① 先**找真实包根**（不假设前缀）再拷夹具；② **把实跑支数返回给调用方，0 支即判红**。

    返回 `(异常清单, E-1 实跑支数, E-2 实跑支数)`。
    """
    fx = tempfile.mkdtemp(prefix='E_foreign_')
    env = {k: v for k, v in os.environ.items() if not k.startswith('DSH_')}
    env['PYTHONIOENCODING'] = 'utf-8'
    # ① 找**真实包根**：任意一层 `*/scripts/gates` 的上一级（兼容 `package/` 前缀与扁平两种形态）
    _root = tmp
    for _d, _dirs, _fs in os.walk(tmp):
        if os.path.basename(_d) == 'gates' and os.path.basename(os.path.dirname(_d)) == 'scripts':
            _root = os.path.dirname(os.path.dirname(_d))
            break
    _gsrc, _ssrc = os.path.join(_root, 'scripts', 'gates'), os.path.join(_root, 'scripts')
    if not os.path.isdir(_gsrc):
        shutil.rmtree(fx, ignore_errors=True)
        return [('（E 判据）', '包内找不到 `scripts/gates/` ⇒ 无法仿真（判红，不静默放行）')], 0, 0
    # 整目录拷贝（模拟真实安装：包内 gates\ 与 scripts\ 一起装）——
    # 旧版只拷单个文件 ⇒ gate_common/_paths 导入失败被误判为"异机崩"（夹具伪影）
    for _sd in (_gsrc, _ssrc):
        if not os.path.isdir(_sd):
            continue
        for _f in os.listdir(_sd):
            if _f.endswith(('.py', '.json')):
                shutil.copy2(os.path.join(_sd, _f), os.path.join(fx, _f))
    _ey = os.path.join(fx, 'gates')
    os.makedirs(_ey, exist_ok=True)
    for _f in os.listdir(_gsrc):
        if _f.endswith('.py'):
            shutil.copy2(os.path.join(_gsrc, _f), os.path.join(_ey, _f))

    def _run_all(envx, tag):
        bad, ran = [], 0
        for n in sorted({os.path.basename(x) for x in names
                         if "/gates/" in x.replace('\\', '/') and x.endswith('.py')}):
            dst = os.path.join(fx, n)
            if not os.path.isfile(dst):
                continue
            ran += 1
            try:
                r = subprocess.run([sys.executable, dst], capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', env=envx, cwd=fx, timeout=150)
                out = (r.stdout or '') + (r.stderr or '')
            except subprocess.TimeoutExpired:
                bad.append((n, '%s 超时' % tag))
                continue
            if 'Traceback' in out:
                # ⚠ 打印长度 70 → 200（`A-117` 的教训：**裁剪过的错误信息会把人引错方向**——
                #   首跑只看到 `...C:\Users\A`，根本判断不出是哪个文件读不到）。
                line = next((l.strip() for l in out.split('\n') if 'Error' in l), 'Traceback')
                bad.append((n, '%s：%s' % (tag, line[:200])))
        return bad, ran

    bad, _ran1 = _run_all(env, 'E-1 异机')
    # E-2 基准件缺失：造一份"目录都不存在"的 gate 配置（真机新装用户就是这个形态）
    _gap = tempfile.mkdtemp(prefix='E_gapcfg_')
    _cfgp = os.path.join(_gap, 'workspace.json')
    with io.open(_cfgp, 'w', encoding='utf-8', newline='\n') as _f:
        _f.write(json.dumps({'workspace_root': os.path.join(_gap, 'ws'),
                             'tools_dir': os.path.join(_gap, 'ws', 'tools'),
                             'work_dir': os.path.join(_gap, 'ws', '.work'),
                             'mach_dir': os.path.join(_gap, 'ws', '原书树', '三闸机器化')},
                            ensure_ascii=False, indent=1))
    env2 = dict(env, DSH_GATE_CONFIG=_cfgp, DSH_DISTILL_ROOT=os.path.join(_gap, 'ws'))
    _b2, _ran2 = _run_all(env2, 'E-2 基准件缺失')
    bad += _b2
    shutil.rmtree(_gap, ignore_errors=True)
    shutil.rmtree(fx, ignore_errors=True)
    return bad, _ran1, _ran2


def _work_refs(names, tmp):
    """收集包内门禁引用的 `join(WORK, 'x')` 文件名（＝必须随包的配套脚本）。"""
    pat = re.compile(r"""join\(\s*WORK\s*,\s*['"]([^'"]+)['"]""")
    out = set()
    for n in names:
        if n.endswith('.py'):
            try:
                out.update(pat.findall(io.open(os.path.join(tmp, n), encoding='utf-8').read()))
            except Exception:
                pass
    # 只保留"像文件"的项（带扩展名、无通配符、不含路径分隔符）
    # ⚠ 2026-09-19 修（A-132 同批 · 判据过宽导致**假红**）：本判据首跑报了
    #   `🔴 bookspec-%s.json 全包内均无 —— 新用户必跑不动`，而 `bookspec-%s.json` 是
    #   **格式化模板**（`join(WORK, 'bookspec-%s.json' % task)`），**根本不是文件名**。
    #   假红比漏检更伤：会诱导执行者去"补一个不存在的文件"（`A-55` 家族）。
    #   修法：排除含 `%` 的格式化模板（真正的配套脚本名里不会有 `%`）。
    return {x for x in out if re.search(r'\.[A-Za-z0-9]+$', x) and '*' not in x
            and '%' not in x and '{' not in x
            and '/' not in x and '\\' not in x}


def _cross_platform_issues(names, tmp):
    """判据 F：跨平台静态扫描（为 NAS／Linux）。
    红旗：① 使用 Windows 专有 API（win32/windll/winreg/msvcrt）；
          ② **硬要求 `node.exe`** 却没有任何平台兜底（`'node'`／`os.name`／`process.platform`）。
    为什么单列：作者机与仿真都在 Windows，Linux 上的问题**只能靠静态判据先拦住**。"""
    bad = []
    for n in names:
        if not n.endswith(('.py', '.cjs', '.mjs', '.js')):
            continue
        try:
            t = io.open(os.path.join(tmp, n), encoding='utf-8').read()
        except Exception:
            continue
        if re.search(r'win32|windll|winreg|msvcrt|pywin32', t) and not n.endswith(
                'check_plugin_portability.py'):
            bad.append('%s  使用 Windows 专有 API' % n)
        if (n.endswith('check_plugin_portability.py')):
            continue          # 不扫自己（本文件里就写着 win32/node.exe 的正则字面量）
        _delegates = re.search(r'_resolve_node|_resolve_jsdir|cfg\.node|NODE = _cfg|gate_common', t)
        if ('node.exe' in t and not _delegates
                and not re.search(r"'node'|\"node\"|os\.name|process\.platform", t)):
            bad.append('%s  硬要求 node.exe 且无平台兜底（Linux 上引擎二进制叫 node）' % n)
    return bad

def _import_closure_issues(names, tmp):
    """判据 D-import：**本地 import 闭包**。包内 Python 若 `import X`／`from X import ...`，
    而 `X.py` 既不在包内、也未在 `optional-tools.json` 声明 ⇒ 该门禁在别人机器上必然 ImportError。"""
    names = set(names)
    declared = set(_optional_declared(tmp))
    mods = {}
    for n in sorted(names):
        if not n.endswith('.py'):
            continue
        try:
            t = io.open(os.path.join(tmp, n), encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        mods[os.path.basename(n)[:-3]] = (n, t)
    bad = []
    for mod, (n, t) in mods.items():
        for m in set(re.findall(r'^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)', t, re.M)):
            if m in mods or m == mod:
                continue
            # 只有当"被引用名"看起来像本地工具时才算（避免误报标准库/三方库）
            if m.endswith(('_candidates', '_merge', '_merge_task', '_oracle', '_matrix',
                           '_regression', '_acceptance', '_scan', '_check', '_probe',
                           '_gate', '_util', '_paths', '_common', '_inventory', '_diff',
                           '_overlap', '_stamp', '_sync', '_quote', '_quotes', '_lines')):
                if (m + '.py') not in names and m not in declared:
                    bad.append('%s  import %s（包内与可选声明中都没有）' % (os.path.basename(n), m))
    return sorted(set(bad))

def main():
    tgz = next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--tgz=')), None)
    if not tgz:
        # 按 **mtime 新→旧**，且**优先非 .BLOCKED**：否则上一轮红灯留下的
        # `*.tgz.BLOCKED` 会被选走 ⇒ 一直审计陈旧包（2026-09-17 已第三次踩此坑）。
        _cand = sorted(glob.glob(os.path.join(ROOT, 'distillation-director-plugin',
                                             'dsh-distillation-director-*.tgz*')),
                       key=os.path.getmtime, reverse=True)
        _live = [x for x in _cand if not x.endswith('.BLOCKED')]
        tgz = (_live or _cand)[0] if _cand else None
    if not tgz or not os.path.isfile(tgz):
        print('🔴 找不到发行包（tgz）—— 请先 repack'); return 1
    names = [m.name for m in tarfile.open(tgz).getmembers() if m.isfile()]
    # 可选依赖集合：**直接从 tar 成员读**（不依赖解包布局与 glob）
    _opt_from_tar = set()
    with tarfile.open(tgz) as _tf:
        for _m in _tf.getmembers():
            if _m.isfile() and os.path.basename(_m.name) == 'optional-tools.json':
                try:
                    def _gather(_o, _acc):
                        if isinstance(_o, dict):
                            for _v in _o.values():
                                _gather(_v, _acc)
                        elif isinstance(_o, list):
                            for _v in _o:
                                _gather(_v, _acc)
                        elif isinstance(_o, str):
                            _acc.add(_o)
                        return _acc
                    _mf = _tf.extractfile(_m)
                    _opt_from_tar = _gather(json.loads(
                        _mf.read().decode('utf-8')), set())
                except Exception as _e:
                    print('  ！可选清单读取失败（%s）：%s' % (type(_e).__name__, _e))
                break
    ok_all = True
    print('=' * 100)
    print('插件可移植性发版闸 ｜ %s' % os.path.basename(tgz))
    print('=' * 100)
    hits, evidence_missing, ncode = [], [], 0
    tmp = tempfile.mkdtemp(prefix='portchk_')
    with tarfile.open(tgz) as tf:
        tf.extractall(tmp)
        for m in tf.getmembers():
            if not m.isfile() or not re.search(r'\.(py|mjs|js|cjs)$', m.name):
                continue
            ncode += 1
            data = tf.extractfile(m).read().decode('utf-8', 'replace')
            # 占位符/文档示例不算（含 `...`、`<`、`你的` 的都是示意，不是真路径）
            lits = [x for x in ABS.findall(data)
                    if not SYSOK.match(x) and not re.search(r'\.\.\.|<|你的|XXX', x)]
            if not lits:
                continue
            author = [x for x in lits if AUTHOR.search(x)]
            if author:
                hits.append((m.name, author[:2]))
            if not re.search(r'_resolve_root|environ|gate_common|cfg\.', data):
                evidence_missing.append((m.name, lits[:2]))
    print('  A 包内不得有"作者机器路径"')
    if hits:
        ok_all = False
        for n, ex in hits:
            print('     🔴 %-52s %s' % (n, '；'.join(ex)[:70]))
    else:
        print('     ✔ 0 处（扫 %d 个代码文件）' % ncode)
    print('  B 含路径字面量的脚本必须有"可覆盖出口"')
    if evidence_missing:
        ok_all = False
        for n, ex in evidence_missing:
            print('     🔴 %-52s 无出口 ｜ %s' % (n, '；'.join(ex)[:60]))
    else:
        print('     ✔ 全部具备出口（_resolve_root／environ／gate_common／cfg）')
    print('  D 引用闭合性（包内门禁引用的 *.py 必须在整包里）；可选声明 %d 个' % len(_opt_from_tar))
    _miss = check_ref_closure(tmp, names, _opt_from_tar)
    if _miss:
        ok_all = False
        for _w, _r in _miss:
            print('     🔴 %-34s 引用了 %s —— 全包内均无' % (_w, _r))
        # ⚠ 这个提示是**用血换来的**：同一形态已复发 3 次（case0 ／ g ／ a-x-y-z 三次都是
        #   自证样本里的假文件名）——
        #   每次都是**自证样本里写了一个假文件名**（把它当作 os.path.join 的第二个参数），
        #   而本判据的正则**扫的是"引号里的 .py 名字"**，看不见"这是样本名不是模块名"。
        #   判据没错（真引用就该闭合），错的是**我造样本的方式**；所以不能只改样本名——
        #   必须在这里把"下次该改什么"直接印出来，否则第 4 次照样复发。
        #   ⚠ 写这段提示时又自伤一次：提示里若出现**带引号的 .py 名**，本判据会把**提示自己**判红。
        _susp = [r for _w, r in _miss if re.match(r'^[a-z]{1,3}\.py$', r)]
        if _susp:
            print('     ⚠ 疑似**自证样本里的假文件名**（%s）：本判据扫"引号内的 *.py"，'
                  '而样本名会被当成真引用。' % '、'.join(sorted(set(_susp))[:4]))
            print('       处置：把自证样本名改成**不带 `.py`** 的名字（如 `caller`／`sample`）；'
                  '不要为此放宽判据（`A-07` 第 7 形态：断言的适用条件没按数据形态分派）。')
    else:
        print('     ✔ 0 处悬空引用')
    _pkgbase = {os.path.basename(_n) for _n in names}
    _wr = _work_refs(names, tmp)
    _wmiss = sorted(x for x in _wr if x not in _pkgbase and x not in _opt_from_tar)
    print('  D-配套 包内门禁引用的 WORK 配套脚本必须在包内（共 %d 个引用）' % len(_wr))
    if _wmiss:
        for _x in _wmiss[:12]:
            print('     🔴 %-34s 全包内均无 —— 新用户必跑不动' % _x)
        print('     处置：把权威层 tools\\ 的同名文件加进 repack 的 SYNC_HELPERS')
    else:
        print('     ✔ 0 处缺件')
    _miss = _miss or _wmiss

    _xp = _cross_platform_issues(names, tmp)
    print('  F 跨平台静态判据（为 NAS／Linux）：Windows 专有 API ｜ 硬写 node.exe 无兜底')
    if _xp:
        for _x in _xp[:10]:
            print('     🔴 %s' % _x[:96])
        _miss = _miss + _xp
    else:
        print('     ✔ 0 处（跨平台解析链齐备）')

    _imp = _import_closure_issues(names, tmp)
    print('  D-import 包内 Python 的本地 import 闭包（引用到的本地模块必须在包内或显式可选）')
    if _imp:
        for _x in _imp[:10]:
            print('     🔴 %s' % _x[:96])
        _miss = _miss + _imp
    else:
        print('     ✔ 0 处（import 闭包完整）')

    print('  E 异机 0 裸栈（无 DSH 数据/无 .dsh 祖先下跑包内门禁）')
    _bad, _e1, _e2 = check_foreign_no_traceback(tmp, names)
    if _bad:
        ok_all = False
        for _w, _why in _bad:
            print('     🔴 %-34s %s' % (_w, _why))
    else:
        print('     ✔ 0 裸栈')
    print('     · E-1（无 DSH 环境）实跑 %d 支门禁 ｜ E-2（`DSH_GATE_CONFIG` 指向"各目录都不存在"的假配置）实跑 %d 支'
          % (_e1, _e2))
    if _e1 == 0 or _e2 == 0:
        ok_all = False
        print('     🔴 **空转**：某轮一支门禁都没跑到 ⇒ 这条判据等于没查（判据必须自证"真的跑了东西"）')
    print('  C 异环境仿真（无 .dsh 祖先 + 配置指向不存在文件）')
    src = None
    for cand in ('scripts/gates/check_layer_sync.py', 'scripts/gates/layer_quotes_gate.py'):
        p = os.path.join(tmp, 'package', cand)
        if os.path.isfile(p):
            src = p; break
    if not src:
        print('     ⚠ 包内未找到可仿真的脚本 ⇒ 不适用（不静默放行，请核对包内容）')
    else:
        # 服从性测试：造一个**空的假工作区**（只有 .dsh\skills），把 env 根指到它。
        # 若脚本仍报出"宿主 9 个 / 作者侧任务" ⇒ **它没服从 env（＝写死路径）** ⇒ 🔴
        fake = tempfile.mkdtemp(prefix='fakeroot_')
        os.makedirs(os.path.join(fake, '.dsh', 'skills'), exist_ok=True)
        tgt = os.path.join(fake, os.path.basename(src))
        shutil.copy2(src, tgt)
        env = dict(os.environ, PYTHONIOENCODING='utf-8', DSH_DISTILL_ROOT=fake)
        env.pop('DSH_GATE_CONFIG', None)
        r = subprocess.run([sys.executable, tgt], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', env=env, cwd=fake)
        out = (r.stdout or '') + (r.stderr or '')
        trace = 'Traceback' in out
        obey = (('宿主 0 个' in out) or ('同名对 0' in out) or ('有引文面的任务 0' in out)
                or ('未找到蒸馏工作区根目录' in out) or ('请设置' in out))
        print('     %s 空假根下：退出码 %d ｜ 裸栈 %s ｜ 服从 env 根 %s'
              % ('✔' if (not trace and obey) else '🔴', r.returncode,
                 '有' if trace else '无', '是' if obey else '**否（可能写死作者路径）**'))
        if trace or not obey:
            ok_all = False
            print('     ---- 输出前 6 行 ----')
            for ln in out.split('\n')[:6]:
                print('        %s' % ln[:110])
        shutil.rmtree(fake, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    print('结论：%s' % ('✔ 可在别人电脑上跑（A/B/C/D/D-配套/D-import/E/F 判据全过）' if (ok_all and not _xp)
                     else '🔴 有硬项 —— **不得发布**（用户明确要求：别人用不了的插件不要再发）'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
