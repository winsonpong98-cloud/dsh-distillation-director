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


if __name__ == '__main__':
    for k in ('ROOT', 'WS', 'HOME', 'ENGINE'):
        print('%-8s %s' % (k, globals()[k]))
