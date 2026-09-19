# -*- coding: utf-8 -*-
"""check_script_sync.py —— 机器脚本一致性检查（权威目录 ↔ 插件包副本）

为什么需要它：工作区里长期存在**两处同名机器脚本**（`投资蒸馏/三闸机器化/` 与
`distillation-director-plugin/scripts/`），2026-09-12 实测已发现两处漂移
（`machine_precheck_v2.py`、`machine_layer_readycheck.py`）。`distillation-director` 技能正文
指向 `投资蒸馏/三闸机器化/`，故该处为**权威**；本脚本用来"随时发现漂移"，避免两次跑出不同结论。

用法：
  python check_script_sync.py          # 只检查（有漂移 → 退出码 1）
  python check_script_sync.py --fix    # 用权威版覆盖插件副本（覆盖前备份到 `DSH_SCRIPT_SYNC_BACKUP`（默认 <工作区根>\\backup\\_script-sync））
  python check_script_sync.py --quiet  # 只输出一行结论（供批界脚本调用）
"""
import io, os, sys, shutil, hashlib
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

HERE = os.path.dirname(os.path.abspath(__file__))                 # 本脚本（权威层 tools\）
# ⚠ 路径修正（2026-09-19 全面体检抓到 · A-127／A-74 家族）：原写 `WS = dirname(dirname(HERE))`
#   ⇒ 落到**工作区父目录**（`…\workspaces`），于是插件副本被找成 `…\workspaces\distillation-director-plugin\scripts`
#   —— **那儿根本没有这个目录**；同时权威件被找成"本脚本所在目录"，而这 4 件**实际住在配套脚本目录**
#   ⇒ 结果恒为 `缺失 4 个`（rc=1 **假红**，且看起来像"包缺件"⇒ 会诱导去"补件"）。
#   现改为：**根目录来自唯一来源 `_paths.ROOT`**；权威件按**解析链**找（配套脚本目录 → tools\）；
#   **两边都不存在 ⇒ 判"不适用"**（另一条工作线/未装配），**不假红**。
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
from _paths import ROOT as _ROOT  # noqa: E402
ROOT = _ROOT
_SCRIPTS = os.environ.get('DSH_SCRIPTS_DIR') or ''
_MACH = ''
try:
    from gate_common import cfg as _cfg
    _SCRIPTS = _SCRIPTS or (_cfg.scripts_dir or '')
    _MACH = _cfg.mach or ''
except Exception:
    pass
# 权威件按解析链找：**机器层脚本目录（cfg.mach）→ 配套脚本目录 → tools\**。
#   ⚠ 实测（2026-09-19）：这 4 件的权威副本住在 `投资蒸馏\三闸机器化\`（＝`cfg.mach`）；
#   本脚本从那儿搬到 `tools\` 之后，`HERE` 变成了 tools ⇒ **"权威目录"跟着搬错了**，恒报"缺失"。
AUTH_DIRS = [d for d in (_MACH, _SCRIPTS, HERE) if d]
PLUGIN = os.path.join(ROOT, 'distillation-director-plugin', 'scripts')
# 备份目录：**不得写死作者机器路径**（发版闸 A 判据）。
# 解析链：环境变量 DSH_SCRIPT_SYNC_BACKUP → <工作区根>\backup\_script-sync（本脚本上级目录）。
BACKUP = (os.environ.get('DSH_SCRIPT_SYNC_BACKUP') or
          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'backup', '_script-sync'))
PAIRS = ['machine_precheck_v2.py', 'machine_layer_readycheck.py',
         'blindtest_lexicon_mock_v1.py', 'defense3_impersonation_scan.py']

md5 = lambda p: hashlib.md5(io.open(p, 'rb').read()).hexdigest()
only = lambda p: hashlib.md5(io.open(p, 'rb').read()).hexdigest()[:12]

fix = '--fix' in sys.argv
quiet = '--quiet' in sys.argv
drift, missing, same, na = [], [], 0, []

for name in PAIRS:
    a = next((os.path.join(d, name) for d in AUTH_DIRS if os.path.exists(os.path.join(d, name))), None)
    b = os.path.join(PLUGIN, name)
    if a is None and not os.path.exists(b):
        # 两边都没有 ⇒ **不适用**（例：本工作区未装该插件，或该册未产出这 4 件），不是"缺件"
        na.append(name)
        continue
    if a is None or not os.path.exists(b):
        missing.append((name, bool(a), os.path.exists(b)))
        continue
    if md5(a) == md5(b):
        same += 1
        if not quiet:
            print('  ✔ %-34s 一致（md5 %s）' % (name, only(a)))
        continue
    drift.append((name, only(a), only(b)))
    if fix:
        os.makedirs(BACKUP, exist_ok=True)
        shutil.copy2(b, os.path.join(BACKUP, name + '.pre-sync.bak'))
        shutil.copy2(a, b)
        if not quiet:
            print('  ⚙ %-34s 已同步 %s → %s（旧副本备份）' % (name, only(b), only(a)))

if quiet:
    print('script_sync: 一致 %d / 漂移 %d / 缺失 %d / 不适用 %d%s'
          % (same, len(drift), len(missing), len(na), '（已 --fix）' if fix and drift else ''))
else:
    for name, ha, hb in drift:
        print('  ⚠ %-34s **漂移**：权威 %s ｜ 插件副本 %s' % (name, ha, hb))
    for name, ea, eb in missing:
        print('  ⚠ %-34s 缺失：权威存在=%s ｜ 插件存在=%s' % (name, ea, eb))
    if na:
        print('  ⏭ 不适用 %d 个（两边都不存在，非缺件）：%s' % (len(na), '、'.join(na)))
    print('\n结论：一致 %d 个，漂移 %d 个，缺失 %d 个，不适用 %d 个%s'
          % (same, len(drift), len(missing), len(na), '（已用 --fix 同步）' if fix and drift else ''))
    if drift and not fix:
        print('建议：python check_script_sync.py --fix （权威版＝配套脚本目录／tools\\；改完请登记）')

sys.exit(1 if (drift or missing) and not fix else 0)
