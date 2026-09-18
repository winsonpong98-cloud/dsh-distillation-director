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

HERE = os.path.dirname(os.path.abspath(__file__))                 # 投资蒸馏/三闸机器化
WS = os.path.dirname(os.path.dirname(HERE))                       # 蒸馏工作区
PLUGIN = os.path.join(WS, 'distillation-director-plugin', 'scripts')
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
drift, missing, same = [], [], 0

for name in PAIRS:
    a, b = os.path.join(HERE, name), os.path.join(PLUGIN, name)
    if not os.path.exists(a) or not os.path.exists(b):
        missing.append((name, os.path.exists(a), os.path.exists(b)))
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
    print('script_sync: 一致 %d / 漂移 %d / 缺失 %d%s'
          % (same, len(drift), len(missing), '（已 --fix）' if fix and drift else ''))
else:
    for name, ha, hb in drift:
        print('  ⚠ %-34s **漂移**：权威 %s ｜ 插件副本 %s' % (name, ha, hb))
    for name, ea, eb in missing:
        print('  ⚠ %-34s 缺失：权威存在=%s ｜ 插件存在=%s' % (name, ea, eb))
    print('\n结论：一致 %d 个，漂移 %d 个，缺失 %d 个%s'
          % (same, len(drift), len(missing), '（已用 --fix 同步）' if fix and drift else ''))
    if drift and not fix:
        print('建议：python check_script_sync.py --fix （权威版＝本目录；改完请登记）')

sys.exit(1 if (drift or missing) and not fix else 0)
