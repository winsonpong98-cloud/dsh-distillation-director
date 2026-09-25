# -*- coding: utf-8 -*-
r"""_creds.py —— **凭据解析唯一来源**（作者机／异机／容器 三态可用）

为什么要单独一件（2026-09-21 · 用户要求"插件装在第三方电脑上也要能用"）：
  实测**三处各写了一份作者机绝对路径**（`D:\deepseekharness\home\.credentials.yaml`）——
  `ocr_pages.py`／`ocr_deepseek_vision.py`／（同类）⇒ **异机 100% 跑不动**，
  而发版闸 A 判据（包内不得有作者机路径）当场判红。⇒ 收成一件，谁用谁 import（A-04：同一事实只有一个来源）。

解析优先级（**先环境变量、后文件；文件位置也按可移植规则推导**）：
  ① 环境变量 `<NAME>`（如 `DEEPSEEK_API_KEY`）——**异机最省事：设了就能用**；
  ② 环境变量 `DSH_CREDENTIALS` 指向的 yaml；
  ③ `$DSH_HOME/.credentials.yaml`（`_paths.HOME` 已按 DSH_HOME → 兄弟目录 `home` 推导）；
  ④ `<工作区根>/.credentials.yaml`（把密钥放在自己的蒸馏工作区里，最直观）；
  ⑤ `~/.credentials.yaml`。
全都拿不到 ⇒ **明确报错并打印可执行指引**（不静默、不猜、不打印密钥本身）。

用法：
  from _creds import get_key
  KEY = get_key('DEEPSEEK_API_KEY')            # 缺则 SystemExit ＋ 指引
  KEY = get_key('SILICONFLOW_API_KEY', required=False)   # 缺则返回 None（调用方自行降级）
"""
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from _paths import ROOT, HOME
except Exception:                                  # `_paths` 不在场：退化为"只认环境变量"
    ROOT, HOME = None, None


def candidate_files():
    """按优先级给出所有"可能存放凭据的文件"（存在与否都列出，便于报错时打印）。"""
    out = []
    v = (os.environ.get('DSH_CREDENTIALS') or '').strip()
    if v:
        out.append(v)
    if HOME:
        out.append(os.path.join(HOME, '.credentials.yaml'))
    if ROOT:
        out.append(os.path.join(ROOT, '.credentials.yaml'))
    out.append(os.path.join(os.path.expanduser('~'), '.credentials.yaml'))
    return out


def get_key(name, required=True, cred_files=None):
    """取一个 API key：先环境变量，再按优先级扫文件。"""
    v = (os.environ.get(name) or '').strip()
    if v:
        return v
    for fp in (cred_files or candidate_files()):
        if not fp or not os.path.isfile(fp):
            continue
        try:
            txt = io.open(fp, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        m = re.search(re.escape(name) + r'\s*:\s*[\'"]?(\S+?)[\'"]?\s*$', txt, re.M)
        if m:
            return m.group(1)
    if not required:
        return None
    sys.exit('\U0001F534 取不到 %s。三种可用的给法（任选一种）：\n'
             '   ① 设环境变量：%s=<你的密钥>            ← 异机／容器最省事\n'
             '   ② 设 DSH_CREDENTIALS=<yaml 路径>，文件里写一行  %s: <密钥>\n'
             '   ③ 把 .credentials.yaml 放到工作区根 或 $DSH_HOME（现查过：%s）\n'
             '   （本工具只读取密钥，不回显、不落盘、不外传。）'
             % (name, name, name, ' ｜ '.join(candidate_files())))


if __name__ == '__main__':
    n = sys.argv[1] if len(sys.argv) > 1 else 'DEEPSEEK_API_KEY'
    k = get_key(n, required=False)
    print('%s = %s' % (n, (k[:4] + '***（已找到，长度 %d）' % len(k)) if k else '（未找到）'))
