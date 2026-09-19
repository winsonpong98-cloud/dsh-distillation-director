import os as _p_os, sys as _p_sys
_p_sys.path.insert(0, _p_os.path.dirname(_p_os.path.abspath(__file__)))
# ⚠ 清理（2026-09-19 第二批）：此处原有 `from _paths import ROOT as _P_ROOT, ...` —— 
#   **本文件就是 `_paths.py`**，那是一次**自导入**：模块尚未执行完 ⇒ 必然 ImportError ⇒
#   被 except 吞掉、改用 DSH_DISTILL_ROOT 或 cwd，**然后在第 50 行又被真值覆盖**。
#   即：那 6 行**永远是死代码**，且它给出的 ROOT（cwd）曾与真 ROOT 并存 ⇒ 谁读到哪一份看时机。
#   保留 `sys.path.insert`（下游有用），删掉自导入块（`A-138`：同一事实只能有一个来源）。
# -*- coding: utf-8 -*-
r"""_paths.py —— **工作台唯一路径来源**（工作区/宿主/引擎/DSH 家目录）

为什么：工作台里曾有 121 个脚本各自写死 `D:\deepseekharness\...` ⇒ 换机器、换工作区路径
就大面积跑不动（**不随包，不影响插件用户**，但影响"换机/换人接手"）。
纪律：**新脚本一律 `from _paths import ROOT`（或 WS/HOME/ENGINE/HOST），不得再写死绝对路径。**

解析优先级（与门禁套件一致）：
  ① 环境变量 `DSH_DISTILL_ROOT`／`DSH_WORKSPACE_ROOT`
  ② `gate_common.cfg`（`DSH_GATE_CONFIG` → 上溯找 `<root>\.dsh\gate-kit\workspace.json`）
  ③ 从本文件位置逐级上溯找 `.dsh`
  ④ **明确失败并打印可执行指引**（不静默用错路径）
"""
import os
import sys


def _resolve_root():
    for k in ('DSH_DISTILL_ROOT', 'DSH_WORKSPACE_ROOT'):
        v = (os.environ.get(k) or '').strip()
        if v and os.path.isdir(v):
            return v
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from gate_common import cfg as _gc
        if _gc.root and os.path.isdir(_gc.root):
            return _gc.root
    except Exception:
        pass
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, '.dsh')):
            return d
        d = os.path.dirname(d)
    sys.exit('🔴 未找到蒸馏工作区根目录 —— 请设 DSH_DISTILL_ROOT=<你的工作区根>，'
             '或写 <工作区>/.dsh/gate-kit/workspace.json 的 workspace_root')


ROOT = _resolve_root()                      # 蒸馏工作区
WS = os.environ.get('DSH_WORKSPACES') or os.path.dirname(os.path.abspath(ROOT))   # 工作区父目录
HOME = os.environ.get('DSH_HOME') or os.path.join(os.path.dirname(WS), 'home')    # DSH 家目录
ENGINE = os.environ.get('DSH_ENGINE') or os.path.join(os.path.dirname(HOME), 'engine')


def HOST(name, default=None):
    """宿主技能根：<WS>\\<name>（不存在则返回 None，交给调用方判"不适用"）"""
    p = os.environ.get('DSH_HOST_%s' % name.upper()) or os.path.join(WS, name)
    return p if os.path.isdir(p) else (default if default is not None else None)


PLUGIN_NAME = 'distillation-director-plugin'

# 插件目录解析：**唯一来源在 `_plugdir.py`**（`A-133`）。
# 为什么单独立一个模块而不住在本文件里：本文件的 `_resolve_root()` **找不到根就 `sys.exit`**，
# 那是工作台内正确、**异机（随包运行）致命**的行为；而 `_plugdir.py` 只用标准库、永不退出、永不打印。
# 这里只做**再导出**（工作台内的脚本照旧写 `from _paths import resolve_plugin_dir`）。
try:
    from _plugdir import PLUGIN_NAME as _PLUGIN_NAME, resolve_plugin_dir, resolve_plugin_dir_report
    PLUGIN_NAME = _PLUGIN_NAME
except ImportError:  # `_plugdir.py` 不在场时的最小兜底（只认工作台布局，不猜别的）
    def resolve_plugin_dir(explicit=None, need_manifest=False, here=None):
        p = os.path.join(ROOT, PLUGIN_NAME)
        return p if os.path.isdir(p) else None

    def resolve_plugin_dir_report(explicit=None, need_manifest=False, here=None):
        p = os.path.join(ROOT, PLUGIN_NAME)
        return resolve_plugin_dir(explicit, need_manifest, here), [('<工作区根>/%s' % PLUGIN_NAME, p)]


if __name__ == '__main__':
    for k in ('ROOT', 'WS', 'HOME', 'ENGINE'):
        print('%-8s %s' % (k, globals()[k]))
