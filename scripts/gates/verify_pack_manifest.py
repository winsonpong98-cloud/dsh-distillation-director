# -*- coding: utf-8 -*-
r"""verify_pack_manifest.py —— **随包清单双向比对**（`A-137` 的根治仪器）

## 它解决什么

`tar -xzf`（以及一切"解压覆盖"式安装）**只增改、不删除**：
包里删掉的旧文件，在**装过旧版的机器上原封不动留着**。
2026-09-19 真机实测：把 434 KB 内部手册移出包后，NAS 上它照样在（还有历史手册 4 件）
—— **"不再随包" ≠ "已从用户机器上消失"**，而症状是"**我明明删了**"这种最容易被相信的假象。

**单向判据（"该有的在不在"）永远查不出这件事**，必须**双向**：
缺件（清单有、目录无）＋ **陈旧件（目录有、清单无）** ＋ 内容不符（大小/md5）。

## 用法

    python verify_pack_manifest.py --pkg-dir <插件目录>          # 安装后比对
    python verify_pack_manifest.py --pkg-dir <插件目录> --list    # 只列清单
    python verify_pack_manifest.py --self-test                    # 用四类坏样本自证本闸有效

退出码：0 = 逐项一致；1 = 有差异（附清单）；2 = 无法执行（缺清单/目录）

纪律：**忽略项要写明理由并打印**（`__pycache__`／`*.pyc`／`node_modules`／`.git`／`*.tgz`／
`_old-releases`／编辑器临时件）——"忽略"不等于"看不见"（`A-55` 家族）。
"""
import argparse
import hashlib
import io
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

MAN_DEFAULT = os.path.join('scripts', 'gates', '_pack-manifest.txt')
# 忽略规则（**必须打印**）：这些不进包，也不该因"目录里有"而报陈旧
IGNORE_DIRS = {'__pycache__', '.git', 'node_modules', '_old-releases', '.pytest_cache', '.mypy_cache'}
IGNORE_SUFFIX = ('.pyc', '.pyo', '.pyd', '.log', '.tgz', '.orig', '.rej', '.tmp', '.bak')
# 忽略规则第二轮（首跑实测补 · 三类"看着像陈旧、其实不是"）：
#  ① **清单自身**：清单按设计**不列自己**（自指无意义）⇒ 比对时必须放行，否则永远报 1 项陈旧；
#  ② **仓库元数据**：`.gitattributes`／`.gitignore` 等**不在包的 `files` 里**，但**从仓库直装（路径 C）时
#     一定存在** ⇒ 属"安装来源的固有物"，不是旧版遗留；
#  ③ **`_stale-*`／`_quarantine-*` 归档目录**：清理陈旧件时**按本闸自己的建议**建出来的 ⇒ 必须放行，
#     否则"按建议清理"反而让闸常红（**闸的建议不能把自己变成红灯**）。
IGNORE_FILES_ANY = {'.gitattributes', '.gitignore', '.gitmodules', '.gitkeep', '_pack-manifest.txt',
                    'PUBLISH-BLOCKED.txt'}
IGNORE_DIR_PREFIX = ('_stale-', '_quarantine-', '_removed-')


def md5(p):
    h = hashlib.md5()
    with io.open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def read_manifest(path):
    """读清单 ⇒ {relpath: (size, md5)}；注释行与空行跳过。"""
    man = {}
    for ln in io.open(path, encoding='utf-8', errors='replace').read().splitlines():
        if not ln.strip() or ln.lstrip().startswith('#'):
            continue
        parts = ln.split('\t')
        if len(parts) != 3:
            print('  ⚠ 清单行格式异常（跳过）：%s' % ln[:80])
            continue
        rel, size, h = parts
        man[rel.strip().replace('\\', '/')] = (int(size), h.strip())
    return man


def walk_pkg(pkg_dir):
    """列出安装目录里的实际文件（相对路径，正斜杠）。"""
    out = set()
    for dp, dn, fn in os.walk(pkg_dir):
        dn[:] = [d for d in dn if d not in IGNORE_DIRS and not d.startswith(IGNORE_DIR_PREFIX)]
        for f in fn:
            if f.endswith(IGNORE_SUFFIX) or f in IGNORE_FILES_ANY:
                continue
            out.add(os.path.relpath(os.path.join(dp, f), pkg_dir).replace('\\', '/'))
    return out


def compare(pkg_dir, man_path, quiet=False):
    """返回 (ok, 统计 dict)。三类差异：missing / stale / mismatch。"""
    man = read_manifest(man_path)
    have = walk_pkg(pkg_dir)
    missing = sorted(set(man) - have)
    stale = sorted(have - set(man))
    mismatch = []
    for rel in sorted(set(man) & have):
        size, h = man[rel]
        p = os.path.join(pkg_dir, rel)
        if os.path.getsize(p) != size or md5(p) != h:
            mismatch.append('%s（清单 %d B/%s ｜ 实际 %d B/%s）'
                            % (rel, size, h[:8], os.path.getsize(p), md5(p)[:8]))
    ok = not (missing or stale or mismatch)
    if not quiet:
        print('清单：%s（%d 项）' % (man_path, len(man)))
        print('目录：%s（%d 个文件）' % (pkg_dir, len(have)))
        print('忽略规则（不进包、不计陈旧）：目录 %s ｜ 后缀 %s ｜ 文件名 %s ｜ 目录前缀 %s'
              % ('、'.join(sorted(IGNORE_DIRS)), '、'.join(IGNORE_SUFFIX),
                 '、'.join(sorted(IGNORE_FILES_ANY)), '、'.join(IGNORE_DIR_PREFIX)))
        for label, items in (('缺件（清单有、目录无）', missing),
                             ('**陈旧件（目录有、清单无）**', stale),
                             ('内容不符', mismatch)):
            if items:
                print('  🔴 %s %d 项：' % (label, len(items)))
                for x in items[:15]:
                    print('       · %s' % x)
                if len(items) > 15:
                    print('       …（另 %d 项）' % (len(items) - 15))
            else:
                print('  ✔ %s 0 项' % label)
    return ok, dict(missing=missing, stale=stale, mismatch=mismatch)


def selftest():
    """四类坏样本必须被检出、一份好样本必须放行（闸自身有效性自证）。"""
    d = tempfile.mkdtemp(prefix='man_selftest_')
    ok = True
    try:
        pkg = os.path.join(d, 'pkg')
        os.makedirs(os.path.join(pkg, 'scripts', 'gates'))
        io.open(os.path.join(pkg, 'a.txt'), 'w', encoding='utf-8').write('AAA')
        # ⚠ 自证样本**不用 `.py` 名字**（首版用 `g.py` ⇒ 发版闸 D 判据把它当成"包内必须存在的文件"
        #   报 `🔴 引用了 g.py —— 全包内均无`）。**判据没错，是我触发它的方式错**：
        #   自证样本的临时名不该长得像真模块（与上一批 `case0.py` 同一坑，第二次）。
        io.open(os.path.join(pkg, 'scripts', 'gates', 'g.md'), 'w', encoding='utf-8').write('sample')
        rels = ['a.txt', 'scripts/gates/g.md']
        man = os.path.join(d, 'MAN.txt')
        io.open(man, 'w', encoding='utf-8', newline='\n').write(
            '# hdr\n' + '\n'.join('%s\t%d\t%s' % (r, os.path.getsize(os.path.join(pkg, r)),
                                                md5(os.path.join(pkg, r))) for r in rels) + '\n')
        good, st = compare(pkg, man, quiet=True)
        print('  %s 好样本放行（期望 True）' % ('✔' if good else '🔴'))
        ok &= good

        # ① 缺件
        os.remove(os.path.join(pkg, 'a.txt'))
        bad, st = compare(pkg, man, quiet=True)
        hit = (not bad) and False or (st['missing'] == ['a.txt'])
        print('  %s 坏样本①缺件被检出（期望 missing=[a.txt]）' % ('✔' if hit else '🔴'))
        ok &= hit
        io.open(os.path.join(pkg, 'a.txt'), 'w', encoding='utf-8').write('AAA')

        # ② 陈旧件（**本条是 A-137 的核心**）
        io.open(os.path.join(pkg, 'stale-internal.md'), 'w', encoding='utf-8').write('旧版遗留')
        bad, st = compare(pkg, man, quiet=True)
        hit = (st['stale'] == ['stale-internal.md'])
        print('  %s 坏样本②**陈旧件**被检出（期望 stale=[stale-internal.md]）' % ('✔' if hit else '🔴'))
        ok &= hit
        os.remove(os.path.join(pkg, 'stale-internal.md'))

        # ③ 内容不符
        io.open(os.path.join(pkg, 'a.txt'), 'w', encoding='utf-8').write('BBB')
        bad, st = compare(pkg, man, quiet=True)
        hit = len(st['mismatch']) == 1
        print('  %s 坏样本③内容不符被检出（期望 mismatch=1）' % ('✔' if hit else '🔴'))
        ok &= hit
        io.open(os.path.join(pkg, 'a.txt'), 'w', encoding='utf-8').write('AAA')

        # ④ 忽略项不得报陈旧（__pycache__ 不该被当陈旧件）
        os.makedirs(os.path.join(pkg, '__pycache__'), exist_ok=True)
        io.open(os.path.join(pkg, '__pycache__', 'x.pyc'), 'w', encoding='utf-8').write('x')
        good, st = compare(pkg, man, quiet=True)
        hit = good and not st['stale']
        print('  %s 坏样本④忽略项不误报（期望 True，且 stale 为空）' % ('✔' if hit else '🔴'))
        ok &= hit
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('  %s 自证%s' % ('✔' if ok else '🔴', '通过（4 类坏样本全拦 ＋ 好样本放行）' if ok else '失败'))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pkg-dir', default=None, help='插件安装目录（默认＝本脚本所在包的上一级）')
    ap.add_argument('--manifest', default=None, help='清单路径（默认 <pkg-dir>/%s）' % MAN_DEFAULT)
    ap.add_argument('--list', action='store_true', help='只列出清单内容')
    ap.add_argument('--self-test', action='store_true', help='用四类坏样本自证本闸有效')
    a = ap.parse_args()
    if a.self_test:
        print('随包清单比对闸 · 自证')
        print('=' * 78)
        return 0 if selftest() else 1
    here = os.path.dirname(os.path.abspath(__file__))
    # 插件目录解析改用**唯一来源** `_plugdir.resolve_plugin_dir`（A-133）。
    # ⚠ 旧写法 `pkg = a.pkg_dir or (上两级 if basename=='gates' else here)` 有个真实事故：
    #   从 `tools\` 单独运行时它把 **`tools\` 自己**当插件目录 ⇒ 去 `tools\scripts\gates\` 找清单 ⇒
    #   打印"找不到随包清单 ⇒ 重装 4.9.10+"——**把"我路径解析错了"说成"你的包太旧"**。
    #   随包运行时（`_plugdir.py` 与本文件同目录）正常工作；异机/无上下文时返回 None 并**列出试过的位置**。
    pkg, tried = None, []
    try:
        sys.path.insert(0, here)
        from _plugdir import resolve_plugin_dir_report
        pkg, tried = resolve_plugin_dir_report(a.pkg_dir, need_manifest=True, here=__file__)
    except ImportError:
        pkg = a.pkg_dir or (os.path.dirname(os.path.dirname(here))
                            if os.path.basename(here) == 'gates' else None)
        tried = [('（`_plugdir.py` 不在场，用本文件内联兜底）', here)]
    man = a.manifest or os.path.join(pkg or '', MAN_DEFAULT)
    if not pkg or not os.path.isdir(pkg):
        print('🔴 找不到插件目录（试过以下位置，均无 `scripts/gates/%s`）：'
              % os.path.basename(MAN_DEFAULT))
        for k, v in tried:
            print('     %-26s %s' % (k, v))
        print('   处置：`--pkg-dir <插件目录>` 或设 `DSH_PLUGIN_DIR`。')
        return 2
    if not os.path.isfile(man):
        print('🔴 在该插件目录里找不到随包清单：%s' % man)
        print('   说明：清单由打包器（repack_plugin.py）在 4.9.10 起生成；该目录里的包可能更早。')
        print('   处置：升级到 4.9.10+ 的包（含清单），或用 `--manifest <路径>` 显式指定。')
        return 2
    if a.list:
        for rel, (size, h) in sorted(read_manifest(man).items()):
            print('  %-56s %8d B  %s' % (rel, size, h[:8]))
        return 0
    print('随包清单双向比对（缺件 ／ **陈旧件** ／ 内容不符）')
    print('=' * 78)
    ok, st = compare(pkg, man)
    print('-' * 78)
    if ok:
        print('结论：✔ 安装目录与随包清单逐项一致（%d 项）' % len(read_manifest(man)))
    else:
        print('结论：🔴 有差异 —— 缺 %d ／ 陈旧 %d ／ 内容不符 %d'
              % (len(st['missing']), len(st['stale']), len(st['mismatch'])))
        if st['stale']:
            print('   陈旧件处置（**这就是 A-137 的现场**）：它们不在本版包里 ⇒ 属旧版遗留。')
            print('   先移到归档目录留痕（不要直接删），例如：')
            print('     mkdir -p <插件目录>/_stale-<版本> && mv <陈旧件…> <插件目录>/_stale-<版本>/')
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(e).__name__, e))
        sys.exit(2)
