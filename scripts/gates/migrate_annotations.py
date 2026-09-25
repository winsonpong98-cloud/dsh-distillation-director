# -*- coding: utf-8 -*-
r"""migrate_annotations.py —— G-69 标注约定迁移唤醒件（2026-09-25）

【背景】R2 mark-tier 契约：〔〕内只许逐字作者语（〔pNN〕／〔sNNN〕页/片锚）；编辑性标注
（时效／勘误／转述／非逐字／编注等）必须用【】。历史迁移批（R2 修复）只跑过一次——
旧件被唤醒／回滚／复制复活时旧约定会重新进闸视野 ⇒ 需要幂等迁移件。

【判据】扫描 .work\<task>\skills\**\*.md 与 .work\<task>\verified.md 中的
  〔(时效|勘误|转述|非逐字|编注|注：|说明：)[^〕]*〕
命中 ⇒ R2 违约形态，--apply 时转成同文【…】。幂等：转换后再跑 0 命中。
【退出码】0=无残留；1=有残留（--apply 未给时）；2=环境错。--selftest 自证。
"""
import argparse
import glob
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

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
    sys.exit('🔴 未找到蒸馏工作区根目录 —— 设 DSH_DISTILL_ROOT=<你的工作区根> 或在根下放 .dsh 标记')


ROOT = _resolve_root()
BAD = re.compile(r'〔(时效|勘误|转述|非逐字|编注|注：|说明：)[^〕]{0,80}〕')


def _is_audit(p):
    return 'dupfx-audit-tmp' in p or p.replace(chr(92), '/').split('/.work/')[-1].split('/')[0].endswith('-audit-tmp')  # 审计区＝有意保留旧版对照，不迁移


def scan_file(p, apply=False):
    t = io.open(p, encoding='utf-8').read()
    hits = BAD.findall(t)
    if not hits:
        return 0
    if apply:
        t2 = BAD.sub(lambda m: '【' + m.group(0)[1:-1] + '】', t)
        io.open(p, 'w', encoding='utf-8', newline='\n').write(t2)
    return len(hits)


def iter_files(task=None):
    pat = os.path.join(ROOT, '.work', task or '*', 'skills', '**', '*.md')
    for f in glob.glob(pat, recursive=True):
        if not _is_audit(f):
            yield f
    if task:
        v = os.path.join(ROOT, '.work', task, 'verified.md')
        if os.path.isfile(v):
            yield v
    else:
        for v in glob.glob(os.path.join(ROOT, '.work', '*', 'verified.md')):
            yield v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        import tempfile
        tmp = tempfile.mkdtemp(prefix='g69-')
        f = os.path.join(tmp, 'SKILL.md')
        io.open(f, 'w', encoding='utf-8').write('- 「书句。」——〔s024〕〔p91〕〔时效：2026-09 前〕\n')
        n0 = scan_file(f)
        assert n0 == 1, '坏样例漏报'
        scan_file(f, apply=True)
        t = io.open(f, encoding='utf-8').read()
        assert '【时效：2026-09 前】' in t and '〔时效' not in t, '转换不对'
        assert scan_file(f) == 0, '不幂等'
        assert '〔s024〕〔p91〕' in t, '合法页锚不得动'
        print('selftest ✔（检出 1／转换为【】／合法〔sNNN〕〔pNN〕不动／再跑 0）')
        return 0
    total = 0
    files = 0
    for f in iter_files(a.task):
        files += 1
        n = scan_file(f, apply=a.apply)
        if n:
            total += n
            print(('🔴 ' if not a.apply else '✔已转 ') + os.path.relpath(f, ROOT) + '：' + str(n) + ' 处')
    print('扫描 %d 文件；旧约定标注 %d 处%s' % (files, total, '（--apply 已全部转【】）' if a.apply else '（未处置）'))
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
