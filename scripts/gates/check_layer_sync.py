# -*- coding: utf-8 -*-
r"""check_layer_sync.py —— **原稿层 ↔ 在役层 逐字节同步闸**（通用 · 只读 · 毫秒级）

## 为什么需要它（缺口登记 · 2026-09-17）
现有门禁里，"副本漂移"只被覆盖了一部分：
  · 教育线 3 个登记副本 → `check_copy_freshness.py`（postflight ⑧⒜）
  · 插件/脚本/打包产物 → `check_script_sync.py`（4/0/0）＋ 打包新鲜度（解包级）
  · **原稿层（`.work\<task>\skills\`）↔ 在役层（`<宿主>\.dsh\skills\`）之间没有任何闸**
    ⇒ 交付之后若有人**只改一层**，没有任何闸会红（只靠交付时"记得 `--apply` ＋ MD5"）。

**唯一要抓的失败模式**：`只改一层`（`A-17` 多层副本漂移）。它有真实先例：
教育线某次的插件副本停在旧包（18 件/缺 4 件/16 件 desc 显示成 `|`），**污染每个会话的 GUI 目录**。

**射程与判据**：
  · 对每个"原稿技能"（`.work\<task>\skills\<slug>\SKILL.md`，跳过 `_` 开头目录），
    在**所有宿主**里找**同名技能** `<ws>\<宿主>\.dsh\skills\<slug>\SKILL.md`，逐对比 **MD5**。
  · **只比同名对**（不要求两个宿主的件集相同——不同宿主有各自的自有件，那不是漂移）。
  · 临时/审计工作区（名字含 `tmp`）**默认排除**并打印理由（它们是**有意保留的旧版对照样本**，
    例如 `<审计副本目录>` 的 28 件全漂移是**快照性质**，不是缺陷）。

用法：python tools\check_layer_sync.py [--all]（`--all` 也列临时区）
退出码：0 = 无漂移；1 = 有漂移（逐条列出：任务/技能/宿主/两侧 mtime）。
"""
import glob
import hashlib
import io
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── 可移植根目录解析（**插件在别人电脑上必须能跑**）─────────────────────────────
# 优先级：① 环境变量 DSH_DISTILL_ROOT ／ DSH_WORKSPACE_ROOT
#         ② `gate_common.cfg`（它自己按 DSH_GATE_CONFIG → 从脚本位置上溯找
#            `<root>\.dsh\gate-kit\workspace.json` → 由配置位置反推）
#         ③ 从本文件位置逐级上溯找 `.dsh`
#         ④ **明确失败并打印可执行指引**（不静默用错路径 —— A-78/A-101 家族）
def _resolve_root():
    for k in ('DSH_DISTILL_ROOT', 'DSH_WORKSPACE_ROOT'):
        v = (os.environ.get(k) or '').strip()
        if v and os.path.isdir(v):
            return v
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
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
    sys.exit('🔴 未找到蒸馏工作区根目录 —— 请任选其一：\n'
             '   ① 设环境变量 DSH_DISTILL_ROOT=<你的工作区根>\n'
             '   ② 写 <工作区>/.dsh/gate-kit/workspace.json 的 workspace_root\n'
             '   ③ 用 DSH_GATE_CONFIG 指向该配置文件')
ROOT = _resolve_root()
WS = os.path.dirname(ROOT)


def md5(p):
    return hashlib.md5(io.open(p, 'rb').read()).hexdigest()


def main():
    show_all = '--all' in sys.argv
    hosts = {}
    for h in sorted(glob.glob(os.path.join(WS, '*'))):
        sd = os.path.join(h, '.dsh', 'skills')
        if os.path.isdir(sd):
            hosts[os.path.basename(h)] = sd
    pairs, drift, skipped = 0, [], []
    for sk in sorted(glob.glob(os.path.join(ROOT, '.work', '*', 'skills', '*', 'SKILL.md'))):
        task = sk.split(os.sep)[-4]
        slug = os.path.basename(os.path.dirname(sk))
        if slug.startswith('_'):
            continue
        if 'tmp' in task.lower() and not show_all:
            skipped.append((task, slug))
            continue
        for hn, sd in hosts.items():
            live = os.path.join(sd, slug, 'SKILL.md')
            if not os.path.isfile(live):
                continue
            pairs += 1
            a, b = md5(sk), md5(live)
            if a != b:
                drift.append((task, slug, hn,
                              os.path.getmtime(sk), os.path.getmtime(live)))
    print('=' * 96)
    print('原稿层 ↔ 在役层 同步闸 ｜ 宿主 %d 个 ｜ 同名对 %d ｜ 漂移 %d'
          % (len(hosts), pairs, len(drift)))
    if skipped:
        print('  已排除临时/审计区（有意保留的旧版对照样本，非缺陷）：%d 件——%s'
              % (len(skipped), '、'.join(sorted({t for t, _ in skipped}))))
    for task, slug, hn, mt, ml in drift:
        print('  🔴 %-28s %-34s 宿主 %-12s 原稿 mtime=%d ／ 在役 mtime=%d（%s 更新）'
              % (task, slug, hn, mt, ml, '在役' if ml > mt else '原稿'))
    print('结论：%s' % ('✔ 原稿层与在役层逐字节一致（无漂移）' if not drift
                     else '🔴 有 %d 对漂移 —— 先同步再谈"改完"' % len(drift)))
    return 1 if drift else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
