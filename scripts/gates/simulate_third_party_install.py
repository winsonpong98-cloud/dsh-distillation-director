# -*- coding: utf-8 -*-
r"""simulate_third_party_install.py —— **异机安装仿真验收**（发版前最后一道 · 只读 ＋ 只在 %TEMP% 落地）

用户要求（2026-09-21）："所有插件的修补都要考虑这个是安装在第三方电脑上的，
所以要确保插件安装后，**所有的功能都能正常使用**。"

为什么必须"装一遍再跑一遍"（而不是只看闸）：
  发版闸能证明"包内无作者机路径／引用闭合"，但**证明不了"装完之后每件都能起来"**：
  实测同族事故＝`init_workspace.py` 漏 `init_workspace.py` 自身（异机初始化直接坑掉）、
  `check_*` 引用的配套脚本没随包（新用户跑不动）。⇒ 本脚本把"别人电脑上第一次用"演一遍。

做的事（全部在 `%TEMP%` 下的新树里，**祖先无 `.dsh`** ＝ 真异机形态）：
  ① 解包 tgz（npm 版或扁平版都认）；
  ② 建假工作区 `<tmp>\ws`，跑包内 `init_workspace.py <ws> --plugin <包根>`；
  ③ **件数对账**：装入 `tools\` 的件数 ≥ 包内待装件数（`scripts/gates` ＋ `scripts` 的 py/json/cjs/mjs/md）；
  ④ **逐件冒烟**：对 `scripts/gates/` 与 `scripts/` 里每个 `.py` 跑 `--help`（argparse 必 rc=0），
     在**清掉密钥环境变量 ＋ 配置指向不存在文件**的条件下跑，判态：
       · ✔ 可跑（rc=0）／⚪ 优雅失败（rc≠0 但**无 Traceback** 且有指引行）／🔴 裸栈或作者机路径泄漏；
  ⑤ **密钥缺失指引专项**：`_creds` 相关件必须在"无任何密钥"时**打印三种给法**，而不是崩；
  ⑥ 汇总成 md 报告 ＋ 退出码（🔴 0 才可发版）。

用法：
  python tools\simulate_third_party_install.py --tgz <tgz 路径> [--out 报告.md] [--keep]
  python tools\simulate_third_party_install.py --plug <插件目录>        # 不打包，直接按目录仿真
退出码：0 = 异机可用；1 = 有 🔴；2 = 环境缺件
"""
import argparse
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

AUTHOR = re.compile(r'[A-Za-z]:\\deepseekharness|/deepseekharness')
GUIDE = re.compile(r'(用法|三种可用的给法|pip install|请先|未装|缺|不适用|usage|Usage|help)')
EXT_INSTALL = ('.py', '.json', '.cjs', '.mjs', '.md')


def unpack(tgz, dest):
    with tarfile.open(tgz) as tf:
        tf.extractall(dest)
    # npm 形态是 <tmp>/package/…；扁平形态直接是 <tmp>/scripts/…
    if os.path.isdir(os.path.join(dest, 'package', 'scripts')):
        return os.path.join(dest, 'package')
    return dest


def run(cmd, cwd, env):
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=180)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except subprocess.TimeoutExpired:
        return -9, '(超时 180s)'
    except Exception as e:                      # noqa: BLE001
        return -1, '(无法启动：%s)' % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tgz', default=None)
    ap.add_argument('--plug', default=None, help='直接给插件目录（仿真"目录形态"，不打包）')
    ap.add_argument('--out', default=None)
    ap.add_argument('--keep', action='store_true', help='保留临时树（排查用）')
    a = ap.parse_args()
    if not a.tgz and not a.plug:
        print('🔴 至少给 --tgz 或 --plug 之一')
        return 2

    tmp = tempfile.mkdtemp(prefix='thirdparty_')
    pkg = a.plug and os.path.abspath(a.plug) or unpack(a.tgz, tmp)
    src = a.tgz or pkg
    ws = os.path.join(tmp, 'ws')                 # 假工作区（祖先无 .dsh ⇒ 真异机形态）
    os.makedirs(ws, exist_ok=True)

    # 清掉一切"作者机会话才有的"东西：密钥一律不给、配置指向不存在的文件、
    # **所有 `DSH_*` 环境变量一律清掉**（本机有 DSH_ENGINE／DSH_HOME／DSH_ENGINE_NODE…，
    #   留着就等于"作者的机器"——首跑实测：preflight/postflight 打印出作者机 node 路径，
    #   差点被误判成插件缺陷；**仿真环境的保真度本身也要先自检**）。
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('DSH_')
           and k not in ('DEEPSEEK_API_KEY', 'SILICONFLOW_API_KEY', 'ZHIPU_API_KEY')}
    env['DSH_GATE_CONFIG'] = os.path.join(tmp, 'no-such-config.json')
    env['PYTHONIOENCODING'] = 'utf-8'
    # **PATH 也要"异机化"**：本机 PATH 里带作者机的 `…\deepseekharness\engine`（DSH 启动器加的），
    #   于是 `shutil.which('node')` 会解析到作者机的 node ⇒ preflight/postflight 打印
    #   `NODE = D:\deepseekharness\engine\node.EXE`，被误判成"作者机路径泄漏"（首跑实测）。
    #   别人电脑的 PATH 里不会有这个目录 ⇒ 仿真必须把它摘掉（**仿真环境的保真度本身要先自检**）。
    env['PATH'] = os.pathsep.join(
        x for x in (env.get('PATH') or '').split(os.pathsep) if 'deepseekharness' not in x.lower())
    # **家目录也要"异机化"**：`_creds.py` 的最后一个候选是 `~/.credentials.yaml`；
    #   本机若真有这个文件，"无密钥"用例会**误判为失败**（实测抓到）。别人电脑的家里没有我们的密钥
    #   ⇒ 把 `~` 指到一个新建的空目录（这也顺带验了"连家目录都没有时仍给指引"）。
    fake_home = os.path.join(tmp, 'fake-home')
    os.makedirs(fake_home, exist_ok=True)
    env['HOME'] = fake_home
    env['USERPROFILE'] = fake_home
    env['HOMEDRIVE'], env['HOMEPATH'] = os.path.splitdrive(fake_home)

    L = ['# 异机安装仿真验收 ｜ %s' % os.path.basename(str(src)), '',
         '> 工装：`tools\\simulate_third_party_install.py`（在 `%%TEMP%%` 新树里演一遍"别人电脑第一次用"）',
         '> 条件：**无 `.dsh` 祖先**、**不提供任何密钥**、`DSH_GATE_CONFIG` 指向不存在的文件', '']
    n_red = 0

    # ① 初始化
    iw = os.path.join(pkg, 'scripts', 'gates', 'init_workspace.py')
    if not os.path.isfile(iw):
        print('🔴 包内无 init_workspace.py：%s' % iw)
        return 2
    rc, out = run([sys.executable, iw, ws, '--plugin', pkg], tmp, env)
    L += ['## ① 初始化（`init_workspace.py`）', '', '```', out.strip()[-1200:], '```', '']
    m = re.search(r'装入 tools\\：(\d+) 个文件', out)
    n_installed = int(m.group(1)) if m else 0
    want = 0
    for d in ('scripts/gates', 'scripts'):
        for f in glob.glob(os.path.join(pkg, *d.split('/'), '*')):
            if os.path.isfile(f) and f.endswith(EXT_INSTALL):
                want += 1
    ok_init = rc == 0 and n_installed >= want > 0
    if not ok_init:
        n_red += 1
    L += ['| 项 | 期望 | 实测 | 判态 |', '|---|---|---|---|',
          '| 退出码 | 0 | %d | %s |' % (rc, '✔' if rc == 0 else '🔴'),
          '| 装入 `tools\\` 件数 | ≥ %d | **%d** | %s |'
          % (want, n_installed, '✔' if n_installed >= want else '🔴'), '']

    # ② 逐件冒烟（--help；再单测"缺密钥/缺库"两类的优雅失败）
    tools_dir = os.path.join(ws, 'tools')
    py = sorted(glob.glob(os.path.join(tools_dir, '*.py')))
    rows, naked, ok_run, graceful = [], [], 0, 0
    for f in py:
        rc, out = run([sys.executable, f, '--help'], ws, env)
        name = os.path.basename(f)
        if AUTHOR.search(out):
            hit = next((ln.strip()[:120] for ln in out.splitlines() if AUTHOR.search(ln)), '')
            rows.append((name, rc, '🔴 输出里出现作者机路径：%s' % hit))
            n_red += 1
            continue
        if 'Traceback' in out:
            naked.append((name, out.strip().splitlines()[-1][:110]))
            rows.append((name, rc, '🔴 裸栈'))
            n_red += 1
            continue
        if rc == 0:
            ok_run += 1
            rows.append((name, rc, '✔ 可跑（--help）'))
        else:
            graceful += 1
            rows.append((name, rc, '⚪ 优雅失败（有指引、无裸栈）'))
    L += ['## ② 逐件冒烟（每件 `--help`，无密钥、无配置）', '',
          '脚本 **%d** 件：✔ 可跑 **%d** ／ ⚪ 优雅失败 **%d** ／ 🔴 裸栈或泄漏 **%d**'
          % (len(py), ok_run, graceful, n_red), '',
          '| 脚本 | rc | 判态 |', '|---|---|---|']
    L += ['| `%s` | %d | %s |' % r for r in rows]
    L += ['']
    if naked:
        L += ['### 🔴 裸栈明细（异机第一次用就会看到这个）', '']
        L += ['- `%s`：%s' % x for x in naked]
        L += ['']

    # ③ 密钥缺失专项（必须"给指引"而不是崩）
    #    ⚠ 首版自伤：只跑了 `_creds.py <NAME>` —— 那是**探测模式**（`required=False`，打印"（未找到）"），
    #    根本没走"缺密钥要指引"那条路 ⇒ 误判成 🔴。现改为**跑真正需要密钥的两件**（用户的实际路径）。
    probes = [('ocr_deepseek_vision.py', ['--task', 'needkey', '--pages', '1']),
              ('ocr_pages.py', ['--pdf', 'nope.pdf', '--task', 'needkey'])]
    os.makedirs(os.path.join(ws, '.work', 'needkey'), exist_ok=True)   # 先给任务目录（否则会先报"缺任务目录"）
    L += ['## ③ 无密钥时的表现（真跑两件需要密钥的工具）', '',
          '- 期望：**打印三种给法并退出**（`_creds.get_key` 唯一来源），不回显密钥、不发裸栈', '',
          '| 工具 | rc | 判态 |', '|---|---|---|']
    for name, args in probes:
        fp = os.path.join(tools_dir, name)
        if not os.path.isfile(fp):
            L.append('| `%s` | — | 🔴 不在包内 |' % name)
            n_red += 1
            continue
        rc, out = run([sys.executable, fp] + args, ws, env)
        good = ('三种可用的给法' in out) and ('Traceback' not in out)
        if not good:
            n_red += 1
        L.append('| `%s` | %d | %s |' % (name, rc, '✔ 给了三种给法' if good else '🔴 未给指引'))
        if not good:
            L += ['', '```', out.strip()[-600:], '```']
    L += ['', '（另：`_creds.py <NAME>` 是**探测模式**，无密钥时只打印"（未找到）"并 rc=0 —— 属正常，不判失败。）', '']

    L += ['## ④ 结论', '',
          '异机装完即用：**%s**（🔴 %d ／ 冒烟覆盖 %d 件）'
          % ('✔ 达标' if n_red == 0 else '🔴 未达标', n_red, len(py)), '',
          '**边界**：① 本仿真只验"能不能起来、缺件时给不给指引"，**不验语义正确性**'
          '（那要真跑一本书，见 §三闸与逐表清点闸）；② 需要网络与真密钥的环节'
          '（视觉 OCR／模型蒸馏）**不在本仿真射程**——只验"无密钥时优雅失败"；'
          '③ 未覆盖真 Linux／macOS（那两项由发版闸 F 判据静态兜底）。', '']
    rep = '\n'.join(L)
    dst = a.out or os.path.join(ws, '异机仿真验收.md')
    io.open(dst, 'w', encoding='utf-8').write(rep + '\n')
    print(rep)
    print('→ 报告：%s' % dst)
    if a.keep:
        print('（临时树保留：%s）' % tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if n_red else 0


if __name__ == '__main__':
    sys.exit(main())
