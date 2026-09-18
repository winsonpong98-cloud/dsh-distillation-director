# -*- coding: utf-8 -*-
r"""gate_bootstrap.py —— **一次性**生成门禁配置（装完插件跑一次，之后零参数）

用户要求（2026-09-17）：「一些必要的需要人工选择外，**尽量少人工选择**，都能严格按照要求蒸馏」。
⇒ 本脚本把"配置门禁套件"压缩成**一条命令**，其余能自动探测的一律不问：

自动探测（不需你回答）：
  · 工作区根：① `--workspace` 显式给 ② 当前目录（若其下有 `tools\` 或 `.work\`）③ 从本脚本位置上溯
  · 原书树目录名：扫工作区一级子目录，找出含 `skills\` ＋ `三闸机器化` 的那个（可多个）
  · 机器层脚本目录：`<工作区>\<原书树>\三闸机器化`（存在才写）
  · 避坑手册：`<工作区>\蒸馏工程避坑手册.md`（存在才写）
  · node.exe：优先 `DSH_HOME\engine\node.exe`，其次 PATH 上的 node（找到才写）
  · js-yaml：在 `DSH_HOME\engine\node_modules\.pnpm\` 下按 `js-yaml@*` 匹配（找到才写）
  · 宿主工作区：① `--host name=<路径>` 显式给（可多次）② 否则从**当前交付上下文**猜（`债券与衍生品`／
    投资类／教育类工作区若存在则登记）

**只写一处**：`<工作区>\.dsh\gate-kit\workspace.json`（`--dry-run` 只打印；已存在则默认拒绝覆盖）。

用法：
    python gate_bootstrap.py --workspace "D:\...\我的蒸馏工作区" --host main="D:\...\金融投资"
    python gate_bootstrap.py --host fin="D:\...\金融投资" --host edu="D:\...\家庭教育"   # 工作区自动探测
    python gate_bootstrap.py --dry-run            # 只看会写什么
"""
import argparse
import glob
import io
import json
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

CONFIG_REL = os.path.join('.dsh', 'gate-kit', 'workspace.json')


def _detect_scripts_dir(root):
    r"""探测**配套脚本目录**（可选）：按"必需脚本命中数"打分，取最高分。

    必需脚本（配套闸真正会调的）：`yaml_check_generic.cjs`／`check_md_tables.py`／
    `final_acceptance.py`／`skill_probe_generic.mjs`／`machine_scan_edu.py`。
    自伤登记：首版只判"目录里有没有任一 .cjs"，结果选中了 `.work/<task>`
    （那里恰好也放了 .cjs）⇒ 让全部门禁判"解析失败"。⇒ 改为**按必需文件打分**，
    得分 <2 视为"未探测到"（相关检查判"不适用"，**不假红**）。
    """
    NEEDED = ['yaml_check_generic.cjs', 'check_md_tables.py', 'final_acceptance.py',
              'skill_probe_generic.mjs', 'machine_scan_edu.py']
    best, best_score = None, 0
    cands = [os.path.join(root, '.work', 'gate-kit', 'scripts')]
    try:
        wd = os.path.join(root, '.work')
        for n in sorted(os.listdir(wd)):
            cands.append(os.path.join(wd, n))
    except Exception:
        pass
    for c in cands:
        if not os.path.isdir(c):
            continue
        score = sum(1 for f in NEEDED if os.path.exists(os.path.join(c, f)))
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 2 else None


def detect_workspace(explicit):
    if explicit:
        return os.path.abspath(explicit)
    cwd = os.getcwd()
    for c in (cwd, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))):
        if os.path.isdir(os.path.join(c, 'tools')) or os.path.isdir(os.path.join(c, '.work')):
            return c
    return cwd


def detect_book_trees(root):
    r"""一级子目录里，含 `skills` 且含 `三闸机器化`（或含 `skills` 且**不是隐藏目录**）的 ⇒ 视为"原书树"。

    排除项（自伤登记）：首版把 `.dsh`（技能安装目录）也当成原书树——因为它下面确有 `skills\`。
    ⇒ 现在**一律跳过点开头的目录**，并要求命中项含 `skills` 子目录。
    """
    out = []
    try:
        for n in sorted(os.listdir(root)):
            if n.startswith('.') or n.startswith('_'):
                continue
            d = os.path.join(root, n)
            if not os.path.isdir(d):
                continue
            if os.path.isdir(os.path.join(d, 'skills')) or os.path.isdir(os.path.join(d, '三闸机器化')):
                out.append(n)
    except Exception:
        pass
    return out


def _engine_root():
    r"""定位 DSH 引擎根（**多候选**，因为 `DSH_HOME` 未必是安装根）。

    自伤登记（2026-09-17 实测）：首版写 `os.path.join(DSH_HOME, 'engine')`，
    而本机 `DSH_HOME=D:\deepseekharness\home`、引擎实际在 `D:\deepseekharness\engine`
    ⇒ 拼成 `...\home\engine\...` **探测失败**（`js_yaml_dir` 空）。
    ⇒ 改为按候选顺序探测，并把命中的那个写进配置注释。
    """
    cands = []
    for k in ('DSH_ENGINE', 'DSH_ENGINE_ROOT', 'DSH_HARNESS_ROOT'):
        v = (os.environ.get(k) or '').strip()
        if v:
            cands += [v, os.path.join(v, 'engine')]
    h = (os.environ.get('DSH_HOME') or '').strip()
    if h:
        cands += [os.path.join(h, 'engine'),                      # DSH_HOME 是安装根时
                  os.path.join(os.path.dirname(h), 'engine'),     # DSH_HOME 是 <root>\home 时（本机实况）
                  h]                                              # DSH_HOME 直接就是引擎时
    for c in cands:
        if c and os.path.isdir(c) and (os.path.exists(os.path.join(c, 'node.exe'))
                                       or os.path.isdir(os.path.join(c, 'node_modules'))):
            return c
    return None


def detect_node():
    e = _engine_root()
    if e:
        for n in ('node.exe', 'node'):
            p = os.path.join(e, n)
            if os.path.exists(p):
                return p
    return shutil.which('node')


def detect_jsdir():
    e = _engine_root()
    if not e:
        return None
    pat = os.path.join(e, 'node_modules', '.pnpm', 'js-yaml@*')
    hits = sorted(glob.glob(pat))
    return hits[-1] if hits else None


def detect_hosts(explicit):
    """显式 `name=path` 优先；否则在工作区同级目录里找可能的宿主（**只登记存在的**）。"""
    hosts = {}
    for item in explicit or []:
        if '=' not in item:
            sys.stderr.write('🔴 --host 需要 `name=路径` 形式，实测：%s\n' % item)
            raise SystemExit(2)
        n, p = item.split('=', 1)
        hosts[n.strip()] = {'path': os.path.abspath(p.strip()), 'expect_skills': None}
    if hosts:
        return hosts
    root = detect_workspace(None)
    parent = os.path.dirname(root)
    for n in sorted(os.listdir(parent)) if os.path.isdir(parent) else []:
        p = os.path.join(parent, n)
        if os.path.isdir(os.path.join(p, '.dsh', 'skills')):
            hosts[n] = {'path': p, 'expect_skills': None}
    return hosts


def build(args):
    root = detect_workspace(args.workspace)
    trees = detect_book_trees(root)
    mach = None
    for t in trees:
        c = os.path.join(root, t, '三闸机器化')
        if os.path.isdir(c):
            mach = c
            break
    if mach is None:
        c = os.path.join(root, '三闸机器化')
        mach = c if os.path.isdir(c) else None
    manual = os.path.join(root, '蒸馏工程避坑手册.md')
    return {
        'workspace_root': root,
        'tools_dir': os.path.join(root, 'tools'),
        'work_dir': os.path.join(root, '.work', 'gate-kit'),
        'scripts_dir': _detect_scripts_dir(root),
        'mach_dir': mach,
        'manual_path': manual if os.path.exists(manual) else None,
        'hosts': detect_hosts(args.host),
        'node_exe': detect_node(),
        'js_yaml_dir': detect_jsdir(),
        'book_trees': trees or ['投资蒸馏'],
        '_comment': ('门禁套件工作区配置。由 gate_bootstrap.py 生成；'
                     '字段含义见 scripts/gates/gate_common.py 的 docstring。'
                     '缺项会被判"不适用"而不是假红；改完请跑 gate_selftest.py 自证。'),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', default=None, help='蒸馏工作区根（缺省自动探测）')
    ap.add_argument('--host', action='append', default=[],
                    help='宿主工作区，`name=路径`，可多次（如 fin="D:\\...\\金融投资"）')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='已存在时覆盖（先备份）')
    a = ap.parse_args()

    data = build(a)
    dest = os.path.join(data['workspace_root'], CONFIG_REL)
    print('=' * 88)
    print('将写入：%s' % dest)
    print('=' * 88)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print('=' * 88)
    # 自证：逐项说明"探测到了什么/没探测到什么"
    def st(k):
        v = data.get(k)
        return ('✔ ' + str(v)) if v else '✗ 未探测到（相关检查将判"不适用"，不会假红）'
    for k in ('tools_dir', 'mach_dir', 'manual_path', 'node_exe', 'js_yaml_dir'):
        print('  %-12s %s' % (k, st(k)))
    print('  hosts        %s' % (', '.join('%s=%s' % (n, h['path']) for n, h in data['hosts'].items())
                                 or '✗ 未探测到（可用 --host name=路径 指定）'))
    print('  book_trees   %s' % data['book_trees'])

    if a.dry_run:
        print('\n[dry-run] 未落盘。去掉 --dry-run 执行。')
        return 0
    if os.path.exists(dest) and not a.force:
        print('\n🔴 已存在：%s' % dest)
        print('   **默认拒绝覆盖**（防手改的配置被冲掉）。要覆盖请加 --force（会先备份）。')
        return 1
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        b = dest + '.bak-before-force'
        shutil.copy2(dest, b)
        print('\n已备份 → %s' % os.path.basename(b))
    io.open(dest, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    # 落盘后回读自证
    back = json.loads(io.open(dest, encoding='utf-8').read())
    ok = back['workspace_root'] == data['workspace_root']
    print('\n✔ 已写 %s（%d B）｜ 回读自证：%s'
          % (dest, os.path.getsize(dest), '通过' if ok else '🔴 失败'))
    print('   下一步：python gate_selftest.py   （自证门禁有效）')
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
