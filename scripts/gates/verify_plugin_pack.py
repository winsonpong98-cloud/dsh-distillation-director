# ── 可移植化（别人电脑上必须能跑）：把所有作者机器字面量换成 env/推导 ──
import os as _p_os, sys as _p_sys
_p_sys.path.insert(0, _p_os.path.dirname(_p_os.path.abspath(__file__)))
try:
    from _paths import ROOT as _P_ROOT, WS as _P_WS, HOME as _P_HOME, ENGINE as _P_ENG
except Exception:
    _P_ROOT = _p_os.environ.get('DSH_DISTILL_ROOT') or _p_os.getcwd()
    _P_WS = _p_os.path.dirname(_P_ROOT)
    _P_HOME = _p_os.environ.get('DSH_HOME') or ''
    _P_ENG = _p_os.environ.get('DSH_ENGINE') or ''
# -*- coding: utf-8 -*-
"""verify_plugin_pack.py —— 插件重打包的**解包级校验**（未-01 验收 · C-9 参数化版）

校验四件事（对应"下次装插件不再带回旧脚本"）：
  ① 两个 tgz **解包后** 4 个脚本 MD5 == 权威副本 `投资蒸馏/三闸机器化/`；SKILL.md MD5 == 权威技能
     （历史事故：tgz 内 `machine_precheck_v2.py` 32,562 B vs 现版 43,935 B）
  ② `package.json` 含 5 个元数据字段（author/repository/homepage/bugs/keywords）且 **version == package.json 里的版本**
  ③ **退出码语义**（2026-09-13 收口轮补）：**不一致 ⇒ 非零退出**。
  ④ **包内无多余产物**（2026-09-15 新增 · 修判据盲区）：④-a 黑名单拦 `__pycache__`/`.pyc`/`.log`/`.tgz` 等；
     ④-b 反向逐件核对包内每个文件都能在插件目录找到且 md5 一致。
     （事故：4.6.4 两个 tgz 混入 `scripts/__pycache__/*.pyc` 76,966 B，本脚本与 postflight 全绿放过。）

⚠ 2026-09-13 收口轮的两处修正（C-9 写死路径巡检发现）：
  · **版本号不再写死**：v1 把 version == '4.2.0' 与两个 tgz 文件名都钉死在代码里 —— 一发新版就报废；
    现改为**从 `distillation-director-plugin/package.json` 读版本**，tgz 名单按该版本自动拼。
    另支持 `--all`：把工作区里**所有**扁平版 tgz 都校验一遍（历史发行件也能抽查）。
  · **补 `sys.exit`**：v1 打印"🔴 存在不一致，需处置"**却退 0** —— 那是"**一个不可能失败的门**"，
    放进 `postflight` 之前必须修掉（否则闸永远是绿的）。
"""
import io, os, re, json, tarfile, hashlib, tempfile, shutil
import os
import sys

# --- UTF-8 输出保护（甲-A5 严格版 · 2026-09-13 加入；坑 P-16）---
# 本块由 utf8_guard_patch.py 幂等插入，勿手删：GBK 控制台下打印 ✔ 会抛
# UnicodeEncodeError → 退出码非 0 的**假报警**（前面所有闸其实都过了）。
if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
# --- UTF-8 输出保护 结束 ---

ROOT = _P_ROOT
PLUG = os.path.join(ROOT, 'distillation-director-plugin')
MACH = os.path.join(ROOT, '投资蒸馏', '三闸机器化')
SKILL = os.path.join(ROOT, '.dsh', 'skills', 'distillation-director', 'SKILL.md')

# --- C-9：把"写死版本"换成"从 package.json 推导"（v1 曾把版本与两个 tgz 文件名钉死在这里） ---
import glob as _glob
_pjf = os.path.join(PLUG, 'package.json')
VER = json.loads(io.open(_pjf, encoding='utf-8').read())['version']
FLAT = os.path.join(ROOT, 'dsh-distillation-director-v%s.tgz' % VER)
NPMV = os.path.join(PLUG, 'dsh-distillation-director-%s.tgz' % VER)
if '--all' in sys.argv:
    TGZ = sorted(_glob.glob(os.path.join(ROOT, 'dsh-distillation-director-v*.tgz'))) + \
          sorted(_glob.glob(os.path.join(PLUG, 'dsh-distillation-director-*.tgz')))
else:
    TGZ = [FLAT, NPMV]

SCRIPTS = ['machine_precheck_v2.py', 'machine_layer_readycheck.py',
           'defense3_impersonation_scan.py', 'blindtest_lexicon_mock_v1.py']


def md5(p):
    return hashlib.md5(io.open(p, 'rb').read()).hexdigest()


ref = {s: md5(os.path.join(MACH, s)) for s in SCRIPTS}
# 门禁套件：权威源在 `tools\`，包内 `scripts/gates/`（A-81）
GATES = ['gate_start.py', 'gate_stage.py', 'gate_checklist.py', 'preflight.py', 'postflight.py', 'gate_selftest.py', 'pitfall_audit.py', 'gate_common.py', 'gate_bootstrap.py', 'check_judge_pack.py']
GATES_REF = {g: md5(os.path.join(ROOT, 'tools', g)) for g in GATES}
ref_skill = md5(SKILL)
print('=== 权威基准（package.json 版本 %s） ===' % VER)
for s in SCRIPTS:
    print('  %-34s %s  (%d 字节)' % (s, ref[s], os.path.getsize(os.path.join(MACH, s))))
print('  %-34s %s  (%d 字节)' % ('SKILL.md（权威技能）', ref_skill, os.path.getsize(SKILL)))

ok_all = True
for tgz in TGZ:
    if not os.path.exists(tgz):
        print('\n=== 缺文件（本版本应有）：%s ===' % tgz)
        ok_all = False
        continue
    print('\n=== 解包校验：%s（%d 字节）===' % (os.path.basename(tgz), os.path.getsize(tgz)))
    tmp = tempfile.mkdtemp(prefix='ddpack_')
    with tarfile.open(tgz) as tf:
        mobjs = tf.getmembers()
        members = [m.name for m in mobjs]
        # ⚠ 2026-09-15 修：本包的目录项由 TarInfo(name) 直接构造，**名字不带尾部 `/`**
        #   ⇒ 不能用 m.endswith('/') 判目录（会把目录当文件去算 md5 → PermissionError 假红）。
        #   一律以 tarfile 成员的 isfile() 为准。
        is_file = {m.name: m.isfile() for m in mobjs}
        try:
            tf.extractall(tmp, filter='data')   # Python 3.12+ 显式 filter，消除 DeprecationWarning
        except TypeError:
            tf.extractall(tmp)
    # 找 scripts 目录（两种前缀：./ 或 package/）
    sp = None
    for d, _, fs in os.walk(tmp):
        if os.path.basename(d) == 'scripts':
            sp = d
            break
    sk = None
    for d, _, fs in os.walk(tmp):
        if 'SKILL.md' in fs:
            sk = os.path.join(d, 'SKILL.md')
            break
    pj = None
    for d, _, fs in os.walk(tmp):
        if 'package.json' in fs:
            pj = os.path.join(d, 'package.json')
            break

    ok = True
    if not sp:
        print('  ✗ 包内无 scripts/ 目录'); ok = False
    else:
        for s in SCRIPTS:
            p = os.path.join(sp, s)
            if not os.path.exists(p):
                print('  ✗ 缺 %s' % s); ok = False; continue
            h = md5(p)
            good = (h == ref[s])
            ok &= good
            print('  %s %-34s %s  (%d 字节)' % ('✔' if good else '🔴', s, h, os.path.getsize(p)))
    if sk:
        h = md5(sk)
        good = (h == ref_skill)
        ok &= good
        print('  %s %-34s %s  (%d 字节)' % ('✔' if good else '🔴', 'SKILL.md', h, os.path.getsize(sk)))
    else:
        print('  ✗ 包内无 SKILL.md'); ok = False
    if pj:
        j = json.loads(io.open(pj, encoding='utf-8').read())
        need = ['author', 'repository', 'homepage', 'bugs', 'keywords']
        miss = [k for k in need if k not in j]
        vok = (j.get('version') == VER)
        ok &= (not miss) and vok
        print('  %s package.json：version=%s（期望 %s）｜ 缺字段=%s'
              % ('✔' if (not miss and vok) else '🔴', j.get('version'), VER, miss if miss else '无'))
    else:
        print('  ✗ 包内无 package.json'); ok = False
    # 附加：确认 manual-history 里有 V4.1
    mh = [m for m in members if 'manual-V4.1' in m]
    print('  %s manual-history 含 V4.1：%s' % ('✔' if mh else '⚠', mh if mh else '无'))
    # --- ④ 包内"多余产物"双向判据（2026-09-15 新增 · 修判据盲区） ---
    # 事故：4.6.4 两个 tgz 内混入 scripts/__pycache__/*.pyc（76,966 B），而本脚本与前序所有门禁
    #      都**只查"该有的在不在、内容对不对"，无人查"有没有多余东西"** ⇒ 脏包一路绿灯发到发行口。
    # 判据分两向（任一不通过 ⇒ 🔴 ⇒ rc=1）：
    #   ④-a 黑名单：包内路径不得含 __pycache__ 目录，也不得以 .pyc/.pyo/.log/.tgz 等产物后缀结尾；
    #   ④-b 反向核对：包内**每一个文件**都必须能在插件目录里找到且 md5 一致（外来文件一律不许）。
    #       （④-b 单独不足以拦 pyc —— 源目录若仍有 __pycache__，脏产物也能"对上"；故必须与 ④-a 并用。）
    BAD_DIRS = {'__pycache__', '.git', 'node_modules', '.pytest_cache', '.mypy_cache'}
    BAD_SUFFIX = ('.pyc', '.pyo', '.pyd', '.log', '.tgz', '.orig', '.rej', '.tmp')
    BAD_NAMES = {'.DS_Store', 'Thumbs.db'}
    pfx = 'package/' if any(m.startswith('package/') for m in members) else ''
    file_members = [m for m in members if is_file.get(m, False)]
    bad_hits, foreign = [], []
    for m in file_members:
        rel = m[len(pfx):] if pfx and m.startswith(pfx) else m
        parts = rel.split('/')
        base = parts[-1]
        if (set(parts[:-1]) & BAD_DIRS) or rel.endswith(BAD_SUFFIX) or base in BAD_NAMES:
            bad_hits.append(rel)
            continue
        local = os.path.join(PLUG, rel.replace('/', os.sep))
        if not os.path.isfile(local):
            foreign.append('%s（插件目录无此文件）' % rel)
        elif md5(local) != md5(os.path.join(tmp, m)):
            foreign.append('%s（与插件目录同名文件内容不同）' % rel)
    print('  %s ④-a 包内无编译/临时产物：%s' % ('✔' if not bad_hits else '🔴',
                                              '干净' if not bad_hits else bad_hits))
    print('  %s ④-b 包内无外来文件（逐件反查插件目录+md5）：%s' % ('✔' if not foreign else '🔴',
                                                              '干净' if not foreign else foreign))
    ok &= (not bad_hits) and (not foreign)
    print('  包内文件数：%d' % len(file_members))
    ok_all &= ok
    shutil.rmtree(tmp, ignore_errors=True)

print('\n结论：%s' % ('✔ 全部 tgz 通过解包级校验（脚本与权威一致、SKILL 与技能一致、元数据齐、包内无多余产物、版本 %s）' % VER
                   if ok_all else '🔴 存在不一致，需处置'))
# ⚠ 2026-09-13 修：v1 到这里就结束了（**🔴 也退 0**）；作为闸必须给退出码。
sys.exit(0 if ok_all else 1)
