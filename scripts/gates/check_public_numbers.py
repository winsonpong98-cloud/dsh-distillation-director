# -*- coding: utf-8 -*-
r"""check_public_numbers.py —— **对外数字/版本一致性闸**（`A-135` 的机械化）

## 为什么需要它

2026-09-19 全面体检抓到：README 写着「门禁与工具 **34 件**」，而**实物是 36 件**
（我后来加了随包清单与清单比对闸，却没回头改 README）。
这正是 `A-135`「**对外宣称的数字必须可复算**」的现场——
**靠人记得回头改，必然会漂**；所以把它做成闸：**声明数 vs 实物数**不一致即判红。

## 判据（只查"机器能算出来的"那些，避免把工作区相关数字写死）

| # | 声明 | 实物（真值来源） |
|---|---|---|
| ① | README「门禁与工具 N 件」 | 包内 `scripts/gates/` 的文件数（**以 tgz 为准**，tgz 不在则用插件目录） |
| ② | README「技能正文（**Vx.y.z 权威**）」 | `package.json` 的 `version` |
| ③ | README 版本表**首行**版本 | `package.json` 的 `version` |
| ④ | `package.json` 的 `description` 长度 | ≤ 1024（npm 上限） |
| ⑤ | README 声明的"随包要点版"是否存在 | 包内 `防坑要点-TOP20.md` 在场 |
| ⑥ | README **一级标题**里的版本号 | `package.json` 的 `version` |
| ⑦ | **SKILL.md**「门禁套件（N 件）」 | 同 ①（**同一事实的第二个声明位**） |
| ⑧ | 内部手册的**声明位与路径位**是否都注明"不随包"，且包内**确实没有**该手册 | 反向判据（`A-137` 家族：移除类改动必须在声明侧同步） |
| ⑨ | `package.json` 的 `description` 若内嵌 `V<数字>` | 必须等于 `version`（**同一文件里两个版本声明位**） |

### ⑦ 为什么必须查 SKILL.md（本项 2026-09-19 第二批加入）

上一批只查 README，**当批就漏了**：SKILL.md 第 36 行写着「门禁套件（**34 件**，随包发行）」，
而实物已是 **37 件**——**同一事实有两个声明位，我只看住了一个**。
（`A-138` 的同族现象：**同一事实的每个声明位都是独立失效点**。）

### ⑧ 的射程：为什么**不**要求 30 处证据锚都加注

SKILL.md/README 里有 30 余处 `《避坑手册》A-xx` 形式的**证据锚**。要求每处都加"不随包"
既是噪音、又会把文档改烂。**该闸抓的是"读者会误以为它随包"的那几种写法**：

1. **权威声明位**——§0.0 B 段（"哪些随包／哪些不随包"的清单）必须写明手册不随包；
2. **§18.3 标题**——该节是手册的正文介绍位，标题必须标"不随包"；
3. **给路径的位置**——凡写出 `` `蒸馏工作区\蒸馏工程避坑手册.md` `` 这类**可打开路径**的行，
   其自身或上下 3 行内必须出现"不随包"（给了路径＝暗示读者手里有）；
4. **反向判据**——包内**不得**存在该手册文件（4.9.9 起移出；`tar -xzf` 只增不删，
   所以"移出"必须在**声明侧**也有闭环，`A-137`）。

**不查**：册数／技能数／成本等**随使用者工作区变化**的数字（那些在本 README 里已写明口径与复算方式，
不适合做阈值闸——写死就成了"作者数据进通用件"，`A-74`）。

用法：
    python tools\check_public_numbers.py [--plugin-dir <目录>] [--selftest]
退出码：0 = 全部一致；1 = 有漂移；2 = 无法执行（缺文件）
"""
import argparse
import io
import json
import os
import re
import sys
import tarfile

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DEFAULT_PLUG = None


def _resolve_plug(explicit=None):
    r"""插件目录解析 —— **改用唯一来源** `_plugdir.resolve_plugin_dir`（`A-133`）。

    旧版本这里自己写了一套（DSH_PLUGIN_DIR → `_paths.ROOT/distillation-director-plugin` → 逐级上溯），
    与 `verify_pack_manifest.py` 里的另一套**互不一致**（后者把 `tools\` 当成了包）。
    **同一个问题两套规则 ⇒ 两个闸对同一台机器给出不同结论**，这正是 `A-133`。
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from _plugdir import resolve_plugin_dir
        return resolve_plugin_dir(explicit, need_manifest=False, here=__file__)
    except ImportError:
        pass
    # 兜底（`_plugdir.py` 不在场时）：只保留"工作台布局"这一条，**不再猜别的**
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from _paths import ROOT
        p = os.path.join(ROOT, 'distillation-director-plugin')
        if os.path.isdir(p):
            return p
    except BaseException:
        pass
    return None


def gates_count_in_tgz(tgz):
    with tarfile.open(tgz) as tf:
        return len([m for m in tf.getmembers()
                    if m.isfile() and '/gates/' in m.name.replace('\\', '/')
                    and m.name.rsplit('/', 1)[-1] != ''])


def collect_claims(plug):
    """返回 [(项, 声明值, 实物值, 是否一致, 备注)]。"""
    rd = io.open(os.path.join(plug, 'README.md'), encoding='utf-8').read()
    pkg = json.loads(io.open(os.path.join(plug, 'package.json'), encoding='utf-8').read())
    ver = pkg.get('version', '?')
    rows = []
    # 真值：优先以 tgz 为准（**发行件才是"对外"的那份**）
    tgz = None
    for f in sorted(os.listdir(plug)):
        if f.endswith('-%s.tgz' % ver):
            tgz = os.path.join(plug, f)
            break
    if tgz:
        src = 'tgz %s' % os.path.basename(tgz)
        n_real = gates_count_in_tgz(tgz)
        with tarfile.open(tgz) as tf:
            names = [m.name for m in tf.getmembers() if m.isfile()]
        has_top = any('防坑要点-TOP20' in n for n in names)
    else:
        src = '插件目录（无 tgz）'
        gd = os.path.join(plug, 'scripts', 'gates')
        n_real = len([f for f in os.listdir(gd) if os.path.isfile(os.path.join(gd, f))])
        has_top = os.path.isfile(os.path.join(gd, '防坑要点-TOP20.md'))
    # ① 件数
    m = re.search(r'门禁与工具\s*\*{0,2}(\d+)\s*件', rd)
    rows.append(('README「门禁与工具 N 件」', m.group(1) if m else '(未声明)',
                 '%d 件（%s）' % (n_real, src), (m is not None and int(m.group(1)) == n_real),
                 'A-135：对外件数必须等于发行件里的实物数'))
    # ② SKILL 版本行
    m2 = re.search(r'技能正文（\*{0,2}V(\d+\.\d+\.\d+)\s*权威', rd)
    rows.append(('README「SKILL 权威版本」', m2.group(1) if m2 else '(未声明)', ver,
                 (m2 is not None and m2.group(1) == ver), '文档声明的权威版本应＝package.json 版本'))
    # ③ 版本表里**当前版本这一行必须存在且标"本版"**，且**只有它**标"本版"
    #    ⚠ 自伤（首跑实测抓到）：原判据写"版本表**首行**＝当前版本"，而本 README 的版本表是
    #    **从旧到新**排列（首行是 v4.1）⇒ 该判据**恒红**（拿"表的排列顺序"当"版本新旧的判据"）。
    #    正确判据：**当前版本那一行存在 ＋ 它带"本版"标记 ＋ 别的行不带**（这才是"文档已更新到本版"）。
    def _marks_benban(line):
        """只有"某个单元格**以**本版开头"才算标记。

        ⚠ 自伤（2026-09-19 第二批实测）：旧判据用 `.*本版.*` 扫整行，
        而 v4.9.11 那一行的**正文里恰好引用了这个词**（"版本表\"本版\"行"）
        ⇒ 把"上一版"的历史行判成了并存的"本版"行，**闸自己报假红**。
        这正是 `A-136`/`A-36` 家族：**判据必须锚定结构位（单元格开头），不能扫自由文本**。
        """
        return any(re.match(r'^\*{0,2}本版', c.strip()) for c in line.split('|'))

    cur_line = None
    for ln in rd.split('\n'):
        if re.match(r'^\|\s*\*{0,2}v%s\*{0,2}\s*\|' % re.escape(ver), ln):
            cur_line = ln
            break
    marked = [re.search(r'^\|\s*\*{0,2}v(\d+\.\d+\.\d+)', ln).group(1)
              for ln in rd.split('\n')
              if re.match(r'^\|\s*\*{0,2}v\d+\.\d+\.\d+\*{0,2}\s*\|', ln) and _marks_benban(ln)]
    ok3 = (cur_line is not None) and _marks_benban(cur_line) and (marked == [ver])
    rows.append(('README 版本表含本版行', ver if cur_line is not None else '(无该版本行)', ver,
                 ok3, '"当前版本那一行"必须存在且标"本版"，且**只有它**标（判据锚定单元格开头）'))
    # ③-b 目录结构里的"SKILL 权威版本"（上一项②）
    m4 = re.search(r'SKILL\.md\s+技能正文（\*{0,2}V(\d+\.\d+\.\d+)\s*权威', rd)
    rows.insert(2, ('README 目录结构里的版本', m4.group(1) if m4 else '(未声明)', ver,
                    (m4 is not None and m4.group(1) == ver),
                    '目录结构段落里的版本号也要跟着升（最容易漏的一处）'))
    # ④ 描述长度
    dl = len(pkg.get('description', ''))
    rows.append(('package.json 描述长度', '%d' % dl, '≤1024', dl <= 1024, 'npm 上限 1024'))
    # ⑤ 通用要点版在场
    rows.append(('README 声明"随包通用要点版"', '有声明' if '防坑要点-TOP20' in rd else '(未声明)',
                 '在场' if has_top else '🔴 缺', has_top, 'A-136：对外承诺随带的文件必须在包里'))
    # ⑥ **一级标题里的版本号**（最显眼的一处，恰恰最容易漏）
    #    ⚠ 体检实测：H1 停在 `V4.9.8`，而版本表已推进到 4.9.10 —— **静默漂了两个版本**。
    #    "最显眼的地方"与"最常被改的地方"不在一处；判据必须把两处都覆盖住。
    m5 = re.search(r'^#\s+.*?V(\d+\.\d+\.\d+)', rd, re.M)
    rows.append(('README 一级标题里的版本', m5.group(1) if m5 else '(未声明)', ver,
                 (m5 is not None and m5.group(1) == ver),
                 '一级标题是页面上最显眼的版本号，最容易漏升'))
    # ⑦ SKILL.md 里的**同一个声明**（实测：上一批只看住 README，SKILL.md 件数静默停在 34）
    skp = os.path.join(plug, 'SKILL.md')
    sk = io.open(skp, encoding='utf-8').read() if os.path.isfile(skp) else ''
    # ⚠ `R38` 的落实：**不是"找到第一个声明就对"，而是"所有声明位都必须对"**。
    #   首版用 `re.search`（只看第一处）——那等于把"每个声明位都是独立失效点"这条规矩**又违反一次**。
    m6all = re.findall(r'门禁套件（\*{0,2}(\d+)\s*件', sk)
    if not sk:
        rows.append(('SKILL.md「门禁套件 N 件」', '(无 SKILL.md)', '%d 件' % n_real, True,
                     'SKILL.md 不在场 ⇒ 本项不适用（在场性由 verify_plugin_pack 管）'))
    else:
        _ok6 = bool(m6all) and all(int(x) == n_real for x in m6all)
        rows.append(('SKILL.md「门禁套件 N 件」',
                     '／'.join(m6all) if m6all else '(未声明)',
                     '%d 件（%s；声明位 %d 处，须**全部**一致）' % (n_real, src, max(len(m6all), 1)),
                     _ok6,
                     'R38：同一事实的每个声明位都是独立失效点（上一批只查 README，SKILL.md 静默漂 3 版）'))
    # ⑧ 内部手册：声明位 ＋ 路径位 ＋ 反向判据（详见模块 docstring 的「⑧ 的射程」）
    MAN = '蒸馏工程避坑手册'
    in_pack = []
    for dirpath, _dirs, files in os.walk(plug):
        for f in files:
            if MAN in f:
                in_pack.append(os.path.relpath(os.path.join(dirpath, f), plug))
    if tgz:
        with tarfile.open(tgz) as tf:
            in_pack += [m.name for m in tf.getmembers() if m.isfile() and MAN in m.name]
    notship = ('不随包发行', '不随包', '不随插件发行')
    probs = []
    # ⑧-1 §0.0 B 段（"哪些随包／哪些不随包"的清单）
    mb = re.search(r'^###\s*B\.[^\n]*\n(.*?)(?=^###\s|\Z)', sk, re.S | re.M)
    if mb and MAN in mb.group(1) and not any(k in mb.group(1) for k in notship):
        probs.append('§0.0 B 段（随包清单）提到内部手册却未注明不随包')
    # ⑧-2 §18.3 标题
    mh = re.search(r'^###\s*18\.3[^\n]*$', sk, re.M)
    if mh and not any(k in mh.group(0) for k in notship):
        probs.append('§18.3 标题未注明内部手册不随包')
    # ⑧-3 路径位（给了可打开路径 ⇒ 暗示读者手里有）
    lines = sk.split('\n')
    for i, ln in enumerate(lines):
        if re.search(r'`[^`]*%s\.md`' % MAN, ln):
            win = '\n'.join(lines[max(0, i - 3):i + 4])
            if not any(k in win for k in notship):
                probs.append('SKILL.md 第 %d 行给出内部手册路径但邻近 3 行未注明不随包' % (i + 1))
    if sk and MAN not in sk:
        probs.append('SKILL.md 全文未提内部手册（应至少说明它不随包）')
    # ⑧-4 反向判据：包内不得真的躺着手册
    if in_pack:
        probs.append('包内出现了内部手册：%s' % ', '.join(sorted(set(in_pack))[:3]))
    # ⑨ description 内嵌的版本号必须与 version 同代（2026-09-19 发 npm 前的元数据自检抓到）
    #   实测形态：version=4.9.14，而 desc 里写着「（V4.9.12：…）」——**同一份文件里两个声明位不同代**，
    #   而且漂的位置是 **npm 页面最显眼的那一行**。同族 `A-139`。
    _dv = re.findall(r'V(\d+\.\d+\.\d+)', pkg.get('description', ''))
    rows.append(('desc 内嵌的版本号', '／'.join(_dv) if _dv else '(未内嵌)',
                 ver + '（内嵌时必须同代）',
                 (not _dv) or all(x == ver for x in _dv),
                 'A-139：description 也是版本声明位；内嵌就必须同代（最好**不内嵌**）'))
    rows.append(('内部手册：不随包声明 ＋ 包内不存在',
                 '不随包（声明位＋路径位）' if not probs else '；'.join(probs[:2]),
                 '包内 %d 处' % len(in_pack), not probs,
                 'A-137：移除类改动必须在**声明侧**闭环（tar 只增不删）'))
    return rows


def _good_skill(n=4, mark=True):
    """好样本的 SKILL.md：三个声明位都齐（件数／B 段／18.3 标题／路径位）。"""
    ym = '、**不随包发行**（作者本地）' if mark else ''
    return ('### B. **只在原工作区存在**（别人电脑上没有）\n'
            '《蒸馏工程避坑手册》`蒸馏工程避坑手册.md`%s。\n'
            '门禁套件（%d 件，随包发行）\n'
            '### 18.3 《蒸馏工程避坑手册》（作者本地资料%s）\n' % (ym, n, ym))


def selftest():
    """坏样本必须被检出（声明数与实物不一致 ＋ 手册声明位缺失）。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp(prefix='pubnum_')
    ok = True
    try:
        gd = os.path.join(d, 'scripts', 'gates')
        os.makedirs(gd)
        for i in range(3):
            io.open(os.path.join(gd, 'f%d.txt' % i), 'w', encoding='utf-8').write('x')
        io.open(os.path.join(gd, '防坑要点-TOP20.md'), 'w', encoding='utf-8').write('x')
        io.open(os.path.join(d, 'package.json'), 'w', encoding='utf-8').write(
            json.dumps({'version': '9.9.9', 'description': 'x'}, ensure_ascii=False))
        io.open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8').write(_good_skill(4))
        # 好样本：声明 4 件（含要点版）＝实际 4 件
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 4 件\n| **v9.9.9** | x | **本版** |\n')
        rows = collect_claims(d)
        bad = [r for r in rows if not r[3]]
        good = not bad
        print('  %s 好样本放行（声明＝实物，%d 项）' % ('✔' if good else '🔴 %s' % bad, len(rows)))
        ok &= good
        # 坏样本：改成 34（实物 4）
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 34 件\n| **v9.9.9** | x | **本版** |\n')
        rows = collect_claims(d)
        hit = any((not r[3]) and '门禁与工具' in r[0] for r in rows)
        print('  %s 坏样本①件数不一致被检出（声明 34 vs 实物 4）' % ('✔' if hit else '🔴'))
        ok &= hit
        # 坏样本：版本不一致
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            'SKILL.md 技能正文（**V0.0.1 权威**）\n门禁与工具 4 件\n| **v9.9.9** | x | **本版** |\n')
        rows = collect_claims(d)
        hit = any((not r[3]) and 'SKILL' in r[0] for r in rows)
        print('  %s 坏样本②版本声明不一致被检出' % ('✔' if hit else '🔴'))
        ok &= hit
        # 坏样本（第 ⑥ 类）：desc 内嵌的版本号与 version 不同代
        io.open(os.path.join(d, 'package.json'), 'w', encoding='utf-8').write(
            json.dumps({'version': '9.9.9', 'description': 'x（V1.2.3：旧批次）'}, ensure_ascii=False))
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 4 件\n| **v9.9.9** | x | **本版** |\n')
        rows = collect_claims(d)
        hit = any((not r[3]) and 'desc 内嵌' in r[0] for r in rows)
        print('  %s 坏样本⑥ desc 内嵌版本不同代被检出' % ('✔' if hit else '🔴'))
        ok &= hit
        io.open(os.path.join(d, 'package.json'), 'w', encoding='utf-8').write(
            json.dumps({'version': '9.9.9', 'description': 'x'}, ensure_ascii=False))

        # 坏样本：承诺随带的要点版缺失
        os.remove(os.path.join(gd, '防坑要点-TOP20.md'))
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 3 件\n| **v9.9.9** | x | **本版** |\n'
            # ⚠ 自证样本里**不写书名号**（首跑被通用件巡检判为"通用工具里混入书目引用"）——
            #   判据没错（通用件不得出现《…》），是我**造样本的方式**第三次踩同类坑。
            '随带通用要点版 防坑要点-TOP20\n')
        rows = collect_claims(d)
        hit = any((not r[3]) and '要点版' in r[0] for r in rows)
        print('  %s 坏样本③承诺随带的文件缺失被检出' % ('✔' if hit else '🔴'))
        ok &= hit
        # 坏样本④：**SKILL.md 里的同一件数声明**漂了（实物 3 件；这是上一批的真实漏检形态）
        io.open(os.path.join(gd, '防坑要点-TOP20.md'), 'w', encoding='utf-8').write('x')
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 4 件\n| **v9.9.9** | x | **本版** |\n')
        io.open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8').write(_good_skill(34))
        rows = collect_claims(d)
        hit = any((not r[3]) and r[0].startswith('SKILL.md「门禁套件') for r in rows)
        print('  %s 坏样本④SKILL.md 里的件数漂移被检出（声明 34 vs 实物 4）' % ('✔' if hit else '🔴'))
        ok &= hit
        # 坏样本⑤：手册声明位缺失 ＋ 包内**真的**躺着手册（tar 只增不删的典型残留）
        io.open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8').write(_good_skill(4, mark=False))
        io.open(os.path.join(d, '蒸馏工程避坑手册.md'), 'w', encoding='utf-8').write('x')
        rows = collect_claims(d)
        hit = any((not r[3]) and r[0].startswith('内部手册') for r in rows)
        print('  %s 坏样本⑤手册声明位缺失＋包内残留被检出' % ('✔' if hit else '🔴'))
        ok &= hit
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('  %s 自证%s' % ('✔' if ok else '🔴', '通过（6 类坏样本全拦 ＋ 好样本放行）' if ok else '失败'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plugin-dir', default=None)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        print('对外数字一致性闸 · 自证')
        print('=' * 78)
        return 0 if selftest() else 1
    plug = _resolve_plug(a.plugin_dir)
    if not plug:
        print('🔴 找不到插件目录 —— 用 --plugin-dir 指定，或设 DSH_PLUGIN_DIR')
        return 2
    print('对外数字/版本一致性闸（A-135）｜ 插件目录：%s' % plug)
    print('=' * 92)
    rows = collect_claims(plug)
    bad = 0
    for name, claimed, real, okk, note in rows:
        if not okk:
            bad += 1
        print('  %s %-28s 声明=%-12s 实物=%-28s %s'
              % ('✔' if okk else '🔴', name, claimed, real, '' if okk else '← ' + note))
    print('-' * 92)
    if bad:
        print('结论：🔴 %d 项与实物不符 —— **不得对外宣称**（先改文档或先改实物，二者必须同代）' % bad)
    else:
        print('结论：✔ 对外声明与实物逐项一致（%d 项）' % len(rows))
    return 1 if bad else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(e).__name__, e))
        sys.exit(2)
