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
    if explicit and os.path.isdir(explicit):
        return os.path.abspath(explicit)
    v = (os.environ.get('DSH_PLUGIN_DIR') or '').strip()
    if v and os.path.isdir(v):
        return os.path.abspath(v)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from _paths import ROOT
        p = os.path.join(ROOT, 'distillation-director-plugin')
        if os.path.isdir(p):
            return p
    except Exception:
        pass
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        p = os.path.join(d, 'distillation-director-plugin')
        if os.path.isdir(p):
            return p
        d = os.path.dirname(d)
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
    def _row_of(v):
        m = re.search(r'^\|\s*\*{0,2}v%s\*{0,2}\s*\|(.*)$' % re.escape(v), rd, re.M)
        return m.group(1) if m else None
    cur = _row_of(ver)
    others_benban = [ln for ln in re.findall(r'^\|\s*\*{0,2}v(\d+\.\d+\.\d+)\*{0,2}\s*\|.*$', rd, re.M)
                     if ln != ver]
    benban_others = re.findall(r'^\|\s*\*{0,2}v(\d+\.\d+\.\d+)\*{0,2}\s*\|.*本版.*$', rd, re.M)
    ok3 = (cur is not None) and ('本版' in cur) and (benban_others == [ver])
    rows.append(('README 版本表含本版行', ver if cur is not None else '(无该版本行)', ver,
                 ok3, '"当前版本那一行"必须存在且标"本版"，且**只有它**标（表序新旧不限）'))
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
    return rows


def selftest():
    """坏样本必须被检出（声明数与实物不一致）。"""
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
        # 好样本：声明 4 件（含要点版）＝实际 4 件
        io.open(os.path.join(d, 'README.md'), 'w', encoding='utf-8').write(
            '# 某插件 V9.9.9\nSKILL.md 技能正文（**V9.9.9 权威**）\n门禁与工具 4 件\n| **v9.9.9** | x | **本版** |\n')
        rows = collect_claims(d)
        bad = [r for r in rows if not r[3]]
        good = not bad
        print('  %s 好样本放行（声明＝实物）' % ('✔' if good else '🔴 %s' % bad))
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
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('  %s 自证%s' % ('✔' if ok else '🔴', '通过（3 类坏样本全拦 ＋ 好样本放行）' if ok else '失败'))
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
