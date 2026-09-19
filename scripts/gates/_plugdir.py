# -*- coding: utf-8 -*-
r"""_plugdir.py —— **插件目录解析唯一来源**（`A-133` 的第二个现场：解析规则只准有一份）

## 为什么要有这个文件（真事故）

"插件目录在哪"这个问题，曾被**各闸各写一遍**，于是各错各的。2026-09-19 实测两种真实错法：

| 闸 | 从 `tools\` 单独运行时的行为 | 后果 |
|---|---|---|
| `check_public_numbers.py` | 先按工作台布局找，找不到才兜底 | 凑巧对（但**判据里有侥幸**） |
| `verify_pack_manifest.py` | 把 **`tools\` 自己**当成插件目录 | 去 `tools\scripts\gates\_pack-manifest.txt` 找清单 ⇒ 报 **"找不到随包清单 ⇒ 重装 4.9.10+"** |

第二种最危险：**路径解析错，却把结论说成"你的包太旧"** ——
**误导性错误比崩溃更坏**（人会照着错误结论去"重装"，永远修不好）。
同族判据：`A-133`（源文件决议单一来源）、`A-138`（同一事实只能有一个来源）。

## 为什么**不**放进 `_paths.py` / `gate_common.py`

那两个模块在找到工作台/配置之前会 **`sys.exit`（响亮退出）**——那是它们在**工作台内**的正确行为，
但本模块要被**随包运行的闸**使用（别的电脑上没有 `.dsh`、没有 `workspace.json`，
`verify_plugin_pack` 的 **E 判据**就是专门跑这种场景的）。
⇒ 本模块纪律：**只用标准库、只读不写、永不退出、永不打印**；
找不到就返回 `None`，由调用方打印"试过哪些位置"。

## 解析优先级

① `explicit`（命令行 `--plugin-dir` / `--pkg-dir`）
② 环境变量 `DSH_PLUGIN_DIR`
③ 从**本文件位置逐级上溯**：脚本在 `<pkg>/scripts/gates/` ⇒ 包根＝上两级；脚本在 `<pkg>/` ⇒ 包根＝本目录
④ `DSH_DISTILL_ROOT`／`DSH_WORKSPACE_ROOT`（或上溯 `.dsh` 得到的根）下的 `distillation-director-plugin`
⑤ 工作区根的父目录布局兜底
⑥ 返回 `None`（**不猜、不静默降级**）

判定"这是不是包"：默认要求 `package.json` 在场；`need_manifest=True` 时要求
`scripts/gates/_pack-manifest.txt` 在场（4.9.10+ 的包才有）。

用法：
    from _plugdir import resolve_plugin_dir, resolve_plugin_dir_report
    pkg, tried = resolve_plugin_dir_report(a.pkg_dir, need_manifest=True)
    if not pkg: 打印 tried 后返回 2

自证：`python _plugdir.py --selftest`（3 个正样本 ＋ 2 个负样本）
"""
import os
import shutil
import sys
import tempfile

PLUGIN_NAME = 'distillation-director-plugin'
MANIFEST_REL = os.path.join('scripts', 'gates', '_pack-manifest.txt')


def _looks_like_pkg(p, need_manifest=False):
    if not p or not os.path.isdir(p):
        return False
    if need_manifest:
        return os.path.isfile(os.path.join(p, MANIFEST_REL))
    return os.path.isfile(os.path.join(p, 'package.json'))


def _roots_from_env(here=None):
    """能拿到的工作区根候选（**不退出**）：环境变量 → 从 **here**（调用者位置）上溯 `.dsh` → 无。

    ⚠ 自证抓到的错法（本文件首跑）：这里原写"从 `__file__` 上溯"——那是**本模块自己的位置**，
    于是在工作台内跑自证时，**负样本（模拟异机）永远会命中真工作区**，自证必然失败。
    正确语义：**按调用者的位置**上溯（与 `_paths._resolve_root()` 同理）——
    随包运行时 `here` 在别的电脑上，上溯不到 `.dsh`，第 ③ 步之后就该返回 None。
    """
    out = []
    for k in ('DSH_DISTILL_ROOT', 'DSH_WORKSPACE_ROOT'):
        v = (os.environ.get(k) or '').strip()
        if v:
            out.append(v)
    d = os.path.abspath(here or os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(d):
        d = os.path.dirname(d)
    for _ in range(6):
        if os.path.isdir(os.path.join(d, '.dsh')):
            out.append(d)
            break
        d = os.path.dirname(d)
    return out


def resolve_plugin_dir(explicit=None, need_manifest=False, here=None):
    """返回插件目录绝对路径，或 None。**永不退出、永不打印。**"""
    if explicit and _looks_like_pkg(explicit, need_manifest):
        return os.path.abspath(explicit)
    v = (os.environ.get('DSH_PLUGIN_DIR') or '').strip()
    if v and _looks_like_pkg(v, need_manifest):
        return os.path.abspath(v)
    d = os.path.abspath(here or os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(d):
        d = os.path.dirname(d)
    for _ in range(7):
        cand = os.path.dirname(os.path.dirname(d)) if os.path.basename(d) == 'gates' else d
        if _looks_like_pkg(cand, need_manifest):
            return os.path.abspath(cand)
        d = os.path.dirname(d)
    for r in _roots_from_env(here):
        for cand in (os.path.join(r, PLUGIN_NAME), r):
            if _looks_like_pkg(cand, need_manifest):
                return os.path.abspath(cand)
        # 工作区根的**父目录**布局（本工作台的实际形态：<父>\<工作区>\<插件>）
        par = os.path.dirname(r)
        for cand in (os.path.join(par, PLUGIN_NAME), os.path.join(par, os.path.basename(r), PLUGIN_NAME)):
            if _looks_like_pkg(cand, need_manifest):
                return os.path.abspath(cand)
    return None


def resolve_plugin_dir_report(explicit=None, need_manifest=False, here=None):
    """同 `resolve_plugin_dir`，额外返回"试过哪些位置"（错误信息必须自证，`A-55`）。"""
    tried = [('命令行参数', explicit or '(未给)'),
             ('环境变量 DSH_PLUGIN_DIR', os.environ.get('DSH_PLUGIN_DIR') or '(未设)'),
             ('脚本位置上溯', os.path.dirname(os.path.abspath(here or __file__)))]
    for r in _roots_from_env(here):
        tried.append(('工作区根候选', r))
    return resolve_plugin_dir(explicit, need_manifest, here), tried


def selftest():
    r"""自证：3 个命中样本 ＋ 3 个"不该猜"的负样本。

    ⚠ **样本名一律不带 `.py`**：发版闸 D 判据扫的是"引号里的 `*.py` 名字"，
    样本名叫 `x.py` 会被当成**真引用**而判红（本形态已复发 3 次：
    `case0.py`／`g.py`／本文件首版的 `a.py x.py y.py z.py`）。
    判据没错，是造样本的方式错 ⇒ 样本名用 `caller`／`empty` 这类中性名。"""
    # 3 正 2 负：上溯／显式／环境变量能命中；空目录与"缺清单的包"不能命中。"""
    ok = True
    d = tempfile.mkdtemp(prefix='plugdir_')
    try:
        pkg = os.path.join(d, 'ws', PLUGIN_NAME)
        gd = os.path.join(pkg, 'scripts', 'gates')
        os.makedirs(gd)
        with open(os.path.join(pkg, 'package.json'), 'w', encoding='utf-8') as f:
            f.write('{}')
        # ① 从包内 gates 目录上溯（最多见：随包运行）
        r = resolve_plugin_dir(here=os.path.join(gd, 'caller'))
        print('  %s ①包内 gates 上溯命中' % ('✔' if r == os.path.abspath(pkg) else '🔴 %s' % r))
        ok &= (r == os.path.abspath(pkg))
        # ② 从包根上溯（脚本就在包根）
        r = resolve_plugin_dir(here=os.path.join(pkg, 'caller'))
        print('  %s ②包根上溯命中' % ('✔' if r == os.path.abspath(pkg) else '🔴 %s' % r))
        ok &= (r == os.path.abspath(pkg))
        # ③ 显式参数最高优先
        r = resolve_plugin_dir(explicit=pkg, here=os.path.join(d, 'elsewhere', 'caller'))
        print('  %s ③显式参数优先命中' % ('✔' if r == os.path.abspath(pkg) else '🔴 %s' % r))
        ok &= (r == os.path.abspath(pkg))
        # ④ 负样本：空目录不得猜中（**这一条是关键**：旧版正是把"自己"当成了包）
        empty = os.path.join(d, 'empty')
        os.makedirs(empty)
        old = os.environ.pop('DSH_DISTILL_ROOT', None)
        old2 = os.environ.pop('DSH_WORKSPACE_ROOT', None)
        old3 = os.environ.pop('DSH_PLUGIN_DIR', None)
        try:
            r = resolve_plugin_dir(here=os.path.join(empty, 'caller'))
            print('  %s ④负样本：无包上下文 ⇒ 返回 None（不猜）' % ('✔' if r is None else '🔴 %s' % r))
            ok &= (r is None)
            # ⑤ 负样本：4.9.10 之前的包（无清单）在 need_manifest 下不得命中
            with open(os.path.join(gd, 'x.txt'), 'w', encoding='utf-8') as f:
                f.write('x')
            r = resolve_plugin_dir(here=os.path.join(gd, 'caller'), need_manifest=True)
            print('  %s ⑤负样本：缺清单的包在 need_manifest 下不命中' % ('✔' if r is None else '🔴 %s' % r))
            ok &= (r is None)
        finally:
            if old is not None:
                os.environ['DSH_DISTILL_ROOT'] = old
            if old2 is not None:
                os.environ['DSH_WORKSPACE_ROOT'] = old2
            if old3 is not None:
                os.environ['DSH_PLUGIN_DIR'] = old3
        # ⑥ 正样本补：清单在场时 need_manifest 命中
        with open(os.path.join(gd, '_pack-manifest.txt'), 'w', encoding='utf-8') as f:
            f.write('x\n')
        r = resolve_plugin_dir(here=os.path.join(gd, 'caller'), need_manifest=True)
        print('  %s ⑥清单在场 ⇒ need_manifest 命中' % ('✔' if r == os.path.abspath(pkg) else '🔴 %s' % r))
        ok &= (r == os.path.abspath(pkg))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print('  %s 自证%s' % ('✔' if ok else '🔴', '通过（3 正 3 负）' if ok else '失败'))
    return ok


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        print('插件目录解析（唯一来源）· 自证')
        print('=' * 78)
        sys.exit(0 if selftest() else 1)
    p, t = resolve_plugin_dir_report()
    print('解析结果：%s' % (p or '🔴 未找到'))
    for k, v in t:
        print('  试过 %-24s %s' % (k, v))
    sys.exit(0 if p else 2)
