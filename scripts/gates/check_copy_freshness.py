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
"""check_copy_freshness.py —— 副本新鲜度闸（W0 · 2026-09-13）

对登记副本逐一比对源根版本戳（edu-root-version.json）：
  · 副本里戳内每件每文件必须存在且 sha256 一致；
  · 副本内戳外多出的技能目录 → 白名单（whitelist）外即红；
  · 任一缺失/陈旧/多余 → exit 1（红）；全部一致 → exit 0。

登记副本（2026-09-13 W0）：
  1. dsh-psychology-books 插件构建目录（蒸馏工作区\\.dsh\\plugin-build\\…\\skills）
  2. dsh-psychology-books 安装实体（home\\profiles\\web\\node_modules\\.pnpm\\…\\skills）
  3. PPT制作工作区装机副本（PPT制作\\.dsh\\skills；白名单 document-reader／ppt-production）

用法：python tools\\check_copy_freshness.py
"""
import hashlib
import io
import json
import os
import sys

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

STAMP = _p_os.path.join(_p_os.path.join(_P_WS, '家庭教育'), r'.dsh\edu-root-version.json')
COPIES = [
    ('插件构建skills', _p_os.path.join(_P_ROOT, r'.dsh\plugin-build\dsh-psychology-books\skills'), set()),
    ('安装实体skills', _p_os.path.join(_P_HOME, r'profiles\web\node_modules\.pnpm\dsh-psychology-books@file+._be913a17da0b6ff99f2b555edce27b22\node_modules\dsh-psychology-books\skills'), set()),
    ('PPT制作skills', _p_os.path.join(_p_os.path.join(_P_WS, 'PPT制作'), r'.dsh\skills'), {'document-reader', 'ppt-production'}),
]


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(65536), b''):
            h.update(c)
    return h.hexdigest()


def main():
    if not os.path.isfile(STAMP):
        print('✗ 红线：版本戳不存在（先跑 tools\\make_edu_root_stamp.py）：%s' % STAMP)
        return 1
    stamp = json.load(io.open(STAMP, encoding='utf-8'))
    print('版本戳：%s ｜ %d 件 ｜ %s' % (stamp['stamp_iso'], stamp['count'], stamp['root']))
    # ---- A-50（2026-09-14 由 ADHD 线装机后自查抓出）：**先自证"戳与活源根同代"，再比副本** ----
    # 旧实现只把副本与**戳**比；源根一变而戳未重生成 ⇒ 两边都停在旧戳 ⇒ **闸恒绿**（"在错误宇宙里自洽"，
    # 与 A-17/A-19 同族但高一层）。实测：源根已 23 件（含新装 adhd-evidence-base、adhd-parenting-guide 16 文件），
    # 戳仍写 22 件，闸却报"3 个登记副本与源根一致"。修法＝**同代自检前置**：戳内每件每文件必须与**当前源根**逐字节一致，
    # 且源根的技能目录集合必须与戳内 pieces 完全相等；任一不符即红（提示先重生成戳）。
    live_problems = []
    for slug, meta in stamp['pieces'].items():
        for rel, want in meta['files'].items():
            p = os.path.join(stamp['root'], slug, rel.replace('/', os.sep))
            if not os.path.isfile(p):
                live_problems.append('源根缺 %s/%s' % (slug, rel))
            elif sha(p) != want:
                live_problems.append('源根已变 %s/%s' % (slug, rel))
    if os.path.isdir(stamp['root']):
        live_slugs = {d for d in os.listdir(stamp['root']) if os.path.isdir(os.path.join(stamp['root'], d))}
        only_stamp = sorted(set(stamp['pieces']) - live_slugs)
        only_live = sorted(live_slugs - set(stamp['pieces']))
        if only_live:
            live_problems.append('源根新增技能未入戳：%s' % '、'.join(only_live))
        if only_stamp:
            live_problems.append('戳内有源根已无的技能：%s' % '、'.join(only_stamp))
    if live_problems:
        print('✗ [戳同代自检] %d 项 ⇒ **版本戳已陈旧**（源根已变而戳未重生成）' % len(live_problems))
        for x in live_problems[:8]:
            print('    - %s' % x)
        print('    ⇒ 先跑 `python tools\\make_edu_root_stamp.py` 重生成戳，再同步副本；**本闸结论不可采信**')
        return 1
    print('✔ [戳同代自检] 版本戳与当前源根逐字节一致（%d 件）' % stamp['count'])
    bad = 0
    for name, root, whitelist in COPIES:
        if not os.path.isdir(root):
            print('✗ [%s] 目录不存在：%s' % (name, root))
            bad += 1
            continue
        problems = []
        for slug, meta in stamp['pieces'].items():
            for rel, want in meta['files'].items():
                p = os.path.join(root, slug, rel.replace('/', os.sep))
                if not os.path.isfile(p):
                    problems.append('缺 %s/%s' % (slug, rel))
                elif sha(p) != want:
                    problems.append('陈旧 %s/%s' % (slug, rel))
        extra = [d for d in sorted(os.listdir(root))
                 if os.path.isdir(os.path.join(root, d)) and d not in stamp['pieces'] and d not in whitelist]
        if extra:
            problems.append('多余技能目录（白名单外）：%s' % '、'.join(extra))
        if problems:
            bad += 1
            print('✗ [%s] %d 项问题：%s' % (name, len(problems), '；'.join(problems[:8]) + ('…' if len(problems) > 8 else '')))
        else:
            print('✔ [%s] 与源根逐字节一致（白名单外无多余）' % name)
    if bad:
        print('\n结论：✗ 副本新鲜度闸 %d 处红 —— 有副本落后于源根，禁止宣称"已同步"' % bad)
        return 1
    print('\n结论：✔ 副本新鲜度闸全绿（%d 个登记副本与源根一致）' % len(COPIES))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
