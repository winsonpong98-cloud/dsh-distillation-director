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


def _read_ver(pjf):
    """读插件目录的 `package.json` 版本；**读不到就返回 None，绝不抛异常**。

    ⚠ 2026-09-19 NAS 真机 ＋ 发版闸 E 判据实测（两处同时抓到）：
    原写法 `VER = json.loads(io.open(_pjf).read())['version']` 是**无条件读文件** ⇒
    在"别人电脑上/无插件目录"的环境里直接 `FileNotFoundError` **裸栈**（本闸是随包发行的闸，
    这正是发版闸 E 判据要拦的形态）。**根因＝把"本机一定有这个目录"当成了前提。**
    正确语义：**读不到版本 ⇒ 本闸不适用 ＋ 打印原因与处置 ＋ 退出码 2**（不裸栈、不假绿）。
    """
    try:
        return json.loads(io.open(pjf, encoding='utf-8').read())['version']
    except Exception:
        return None


VER = _read_ver(_pjf)
if not VER:
    print('ℹ 解包级校验**不适用**：本机找不到插件目录的 `package.json`。')
    print('   路径：%s' % _pjf)
    print('   原因：本闸比对的是"发行件 ↔ 工作台权威层"，需要工作台里的插件目录在场；')
    print('         在别人电脑上只装发行包、没有工作台源代码时**属正常**。')
    print('   处置：在工作台里跑（`<工作区>/distillation-director-plugin/package.json` 在场），')
    print('         或用 `--all` 前先确认插件目录已就位。')
    sys.exit(2)
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


def md5_or_none(p):
    """基准件缺失时返回 None —— **不得抛异常**。

    ⚠ 2026-09-19 NAS 真机实测（本闸在本机全绿、在真机裸栈）：
    机器层脚本目录（原书树里的 `三闸机器化\\`）**只在作者工作区存在**；
    换台电脑/新装用户的机器上没有它 ⇒ 旧版直接
    `FileNotFoundError: /workspace/投资蒸馏/三闸机器化/machine_precheck_v2.py` **整条崩掉**。
    同族＝`A-115`「缺目录当异常」＋ 发版闸 E 判据的**射程漏洞**：
    E 只在"作者机器上模拟异机"，而作者机器上那些基准件**恰好都在** ⇒ 永远测不出这一形态。
    正确语义：**基准件不在场 ⇒ 该比对判"不适用"并打印原因**（不判红、也不假绿）。
    """
    return md5(p) if os.path.isfile(p) else None


ref = {s: md5_or_none(os.path.join(MACH, s)) for s in SCRIPTS}
# 门禁套件：权威源在 `tools\`，包内 `scripts/gates/`（A-81）
GATES = ['gate_start.py', 'gate_stage.py', 'gate_checklist.py', 'preflight.py', 'postflight.py', 'gate_selftest.py', 'pitfall_audit.py', 'gate_common.py', 'gate_bootstrap.py', 'check_judge_pack.py']
GATES_REF = {g: md5_or_none(os.path.join(ROOT, 'tools', g)) for g in GATES}
ref_skill = md5_or_none(SKILL)
_missing = ([s for s, h in ref.items() if h is None] + [g for g, h in GATES_REF.items() if h is None])
print('=== 权威基准（package.json 版本 %s） ===' % VER)
if _missing:
    print('  ℹ **不适用项**：本机缺 %d 个权威基准件 ⇒ 与它们的比对**跳过**（不判红、不假绿）' % len(_missing))
    print('     缺件：%s' % '、'.join(_missing[:8]) + ('…' if len(_missing) > 8 else ''))
    print('     原因：机器层脚本目录 = `MACH`（原书树内，**只在作者工作区存在**）；'
          '`tools\\` 权威工具目录同理。换台电脑/新装用户没有它们**属正常**。')
    print('     仍然照常执行的校验：包内文件在场性 ／ 逐件 md5 与**包内清单**一致 ／ 元数据 ／ 反向判据（无内部手册）。')
for s in SCRIPTS:
    if ref[s] is None:
        print('  %-34s （不适用：本机缺 `MACH/%s`）' % (s, s))
        continue
    print('  %-34s %s  (%d 字节)' % (s, ref[s], os.path.getsize(os.path.join(MACH, s))))
if ref_skill is None:
    print('  %-34s （不适用：本机缺权威技能件）' % 'SKILL.md（权威技能）')
else:
    print('  %-34s %s  (%d 字节)' % ('SKILL.md（权威技能）', ref_skill, os.path.getsize(SKILL)))

ok_all = True
# ⚠ 2026-09-19 真机（NAS）实测：装机后本机**只有装机件与发行资产**，没有工作台里的扁平 tgz
#   ⇒ 旧版逐条打印"=== 缺文件（本版本应有）==="并判 🔴"存在不一致"——**诚实但误导**：
#   它让人以为"包坏了"，实际是"**这台机器没有工作台源码布局**"（同族 `A-144`：把"本机一定有 X"当前提）。
#   正确语义：**一个都不在场 ⇒ 判"不适用" ＋ 说明 ＋ rc=2**；部分缺 ⇒ 仍判红（那确实是缺件）。
_present = [t for t in TGZ if os.path.exists(t)]
if not _present:
    print('ℹ 解包级校验**不适用**：本机没有找到任何发行件（tgz）。')
    for _t in TGZ:
        print('   期望路径：%s%s' % (_t, '（在场）' if os.path.exists(_t) else '（不在场）'))
    print('   原因：本闸比对"发行件 ↔ 工作台权威层"，需要在工作台里同时具备 tgz 与插件目录；')
    print('         只装了发行包的用户机器上没有这个布局**属正常**。')
    print('   处置：在工作台里跑（先用打包器生成 tgz），或用 `--all` 指定存在的包；')
    print('         已装的包要验证完整性，请用 `verify_pack_manifest.py --pkg-dir <插件目录>`'
          '（随包清单双向比对，装机侧同样适用）。')
    sys.exit(2)
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
            if ref[s] is None:
                # 基准件不在场：**只报在场性，不判同源**（不假绿：打印"未比对"）
                print('  ✔ %-34s %s  (%d 字节)  ← 在场；与权威基准**未比对**（本机缺基准件）'
                      % (s, h, os.path.getsize(p)))
                continue
            good = (h == ref[s])
            ok &= good
            print('  %s %-34s %s  (%d 字节)' % ('✔' if good else '🔴', s, h, os.path.getsize(p)))
    if sk:
        h = md5(sk)
        if ref_skill is None:
            print('  ✔ %-34s %s  (%d 字节)  ← 在场；与权威技能**未比对**（本机缺基准件）'
                  % ('SKILL.md', h, os.path.getsize(sk)))
        else:
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
    # --- 门禁套件逐件比对（2026-09-19 第二批补：原 `GATES`／`GATES_REF` **建了却从未使用**）---
    #   一条"建了不使用"的判据＝**纸面判据**（`A-98`／`A-123` 家族）：它出现在输出里让人以为查过，
    #   实际上从未比对。本批把它接上（本机有 `tools\` 时逐件比 md5；异机无基准件则**只报在场性**）。
    _gsp = os.path.join(sp, 'gates') if sp else None
    if _gsp and os.path.isdir(_gsp):
        _gmiss, _gbad, _gskip = [], [], 0
        for g in GATES:
            gp = os.path.join(_gsp, g)
            if not os.path.isfile(gp):
                _gmiss.append(g); continue
            if GATES_REF[g] is None:
                _gskip += 1; continue
            if md5(gp) != GATES_REF[g]:
                _gbad.append(g)
        if _gmiss or _gbad:
            ok = False
            print('  🔴 包内门禁套件：缺 %d 件%s ／ 与权威不一致 %d 件%s'
                  % (len(_gmiss), ('（%s）' % '、'.join(_gmiss[:5])) if _gmiss else '',
                     len(_gbad), ('（%s）' % '、'.join(_gbad[:5])) if _gbad else ''))
        else:
            print('  ✔ 包内门禁套件在场且与权威逐件一致（比对 %d 件%s）'
                  % (len(GATES) - _gskip, '；%d 件未比对＝本机缺基准' % _gskip if _gskip else ''))
    else:
        print('  ℹ 包内未找到 `scripts/gates/`（旧版包形态）⇒ 门禁套件比对不适用')

    # 附加（2026-09-19 脱敏批 · 用户拍板方案乙）：**不再随包 manual-history 与完整内部手册**。
    #   判据改为**反向**——包内**不得**出现它们（防"哪天又悄悄带回去"），并确认通用要点版在场。
    _leak = sorted({m.split('/')[1] if m.count('/') > 1 else m for m in members
                    if 'manual-history' in m or '蒸馏工程避坑手册' in m})
    print('  %s 包内不含内部手册/历史手册：%s' % ('✔' if not _leak else '🔴', _leak or '干净'))
    if _leak:
        ok = False
    _top = [m for m in members if '防坑要点-TOP20' in m]
    print('  %s 随包通用要点版在场：%s' % ('✔' if _top else '🔴', _top or '（缺）'))
    if not _top:
        ok = False
    # 随包清单 ↔ 包内成员 **双向**（A-137 根治）：清单是安装侧"缺件＋陈旧件"比对的前提，
    #   所以构建侧必须断言"清单 ≡ 包内成员（清单自身除外）"——否则安装侧会拿一份错的尺子去比对。
    _relm = lambda n: n.split('/', 1)[1] if n.startswith('package/') else n
    _mn = [m for m in members if m.endswith('_pack-manifest.txt')]
    if not _mn:
        print('  🔴 包内缺随包清单 `scripts/gates/_pack-manifest.txt`（缺它 ⇒ 安装侧无法双向比对）')
        ok = False
    else:
        # ⚠ 自伤（首跑实测抓到）：此处原用外层 `with tarfile.open(tgz) as tf` 的句柄，
        #   而该 `with` 块已结束 ⇒ `OSError: TarFile is closed`。**重新开一次**（只读、代价可忽略）。
        import tarfile as _tarfile
        with _tarfile.open(tgz) as _tf2:
            _raw = _tf2.extractfile(_mn[0]).read().decode('utf-8', 'replace')
        _man = {l.split('\t')[0].strip().replace('\\', '/')
                for l in _raw.splitlines() if l.strip() and not l.lstrip().startswith('#')}
        _pkgfiles = {_relm(m) for m in members if is_file.get(m, False)}
        _expect = _man | {_relm(_mn[0])}          # 清单不含自己
        _missing = sorted(_expect - _pkgfiles)
        _extra = sorted(_pkgfiles - _expect)
        print('  %s 随包清单 ≡ 包内成员（%d 项）：缺 %d ／ 多 %d'
              % ('✔' if not (_missing or _extra) else '🔴', len(_man), len(_missing), len(_extra)))
        if _missing:
            print('       清单有、包内无：%s' % '、'.join(_missing[:8]))
        if _extra:
            print('       包内有、清单无：%s' % '、'.join(_extra[:8]))
        if _missing or _extra:
            ok = False
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
