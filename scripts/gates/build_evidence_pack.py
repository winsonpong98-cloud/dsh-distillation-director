# -*- coding: utf-8 -*-
r"""build_evidence_pack.py —— G-68 证据闭包·构建件（2026-09-25 建闸）

对每个有 verified.md 的任务：解析池（### <系列>-<序号>，- 原文：「…」）→ id→(全文, sha256)；
对每个引用了池 id 的技能件（.work\<task>\skills\<skill>\），生成 skills\<skill>\evidence-pool.md：
  - <id> sha256=<64hex>
    quote:「<池内全文>」
    src:verified.md
未解析 id 记 UNRESOLVED 行（供闭包闸报缺口）。
【A-74】证据包只落在工作区 skills 层，绝不进 cangjie 插件 npm 包（打包排除，见台账）。
用法：python tools\build_evidence_pack.py [--task X]
"""
import argparse
import glob
import shutil
import hashlib
import io
import os
import re
from _bandid import ID_LOOSE  # 波段 id 语法的唯一真源（A-132：不得内联 [A-Za-z]...-\d）
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── 可移植根目录解析（**插件在别人电脑上必须能跑**，与 check_layer_sync.py 同款）──
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
             '   ② 在工作区根下放 .dsh 目录标记\n'
             '   ③ 与 gate_common.cfg 兼容的 DSH_GATE_CONFIG')


ROOT = _resolve_root()

MIRROR = (os.environ.get('DSH_FIN_INVEST_SKILLS') or '').strip()  # 部署侧技能根（可选；双层闭包用）
CITE = re.compile(r'（`?(' + ID_LOOSE + ')`?\s*(?:s\d{1,4}|[：:][^）]{0,60})')


def norm(s):
    return re.sub(r'\s', '', s)


def sha(s):
    return hashlib.sha256(norm(s).encode('utf-8')).hexdigest()


def parse_pool(path):
    """v2：### 标题块 ＋ 表行（| ID | ... |「…」... |）两种格式。"""
    entries = {}
    aid = None
    quote = ''
    for raw in io.open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^###\s*(' + ID_LOOSE + ')\s*\[', raw.strip())
        if m:
            if aid and quote:
                entries.setdefault(aid, quote)
            aid, quote = m.group(1), ''
            continue
        tm = re.match(r'^\|\s*(' + ID_LOOSE + ')\s*\|', raw.strip())
        if tm and '「' in raw:
            qm = re.search(r'「([^」]*)」', raw)
            if qm:
                entries.setdefault(tm.group(1), qm.group(1))
            if aid:
                if quote:
                    entries.setdefault(aid, quote)
                aid = None
            continue
        if aid:
            m2 = re.match(r'^- 原文(?:（[^）]*）)?[：:]「(.*)」\s*$', raw.strip())
            if m2:
                quote = m2.group(1)
                entries.setdefault(aid, quote)
                aid = None
            elif raw.strip() == '':
                if quote:
                    entries.setdefault(aid, quote)
                aid = None
                quote = ''
    if aid and quote:
        entries.setdefault(aid, quote)
    return entries
def build_task(task):
    tdir = os.path.join(ROOT, '.work', task)
    vm = os.path.join(tdir, 'verified.md')
    if not os.path.isfile(vm):
        return None
    pool = parse_pool(vm)
    made = 0
    for sdir in sorted(glob.glob(os.path.join(tdir, 'skills', '*'))):
        if not os.path.isdir(sdir):
            continue
        cited = set()
        for f in glob.glob(os.path.join(sdir, '*.md')):
            t = io.open(f, encoding='utf-8').read()
            for m in CITE.finditer(t):
                cited.add(m.group(1))
        if not cited:
            continue
        lines = ['# evidence-pool · %s · %s' % (task, os.path.basename(sdir)),
                 '> G-68 证据闭包包（2026-09-25）。id→池内全文＋sha256(norm)。构建件：tools\\build_evidence_pack.py', '']
        n_unres = 0
        for cid in sorted(cited):
            if cid in pool:
                q = pool[cid]
                lines += ['- %s sha256=%s' % (cid, sha(q)), '  quote:「%s」' % q, '  src:verified.md']
            else:
                lines += ['- %s UNRESOLVED' % cid]
                n_unres += 1
        out = os.path.join(sdir, 'evidence-pool.md')
        io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        made += 1
        if MIRROR and os.path.isdir(MIRROR):
            _msd = os.path.join(MIRROR, os.path.basename(sdir))
            if not os.path.isfile(os.path.join(_msd, 'SKILL.md')):
                print('   ⚠ 镜像跳过 %s：部署侧无此技能件（不越界造孤儿目录）' % os.path.basename(sdir))
            else:
                _ms = os.path.join(_msd, 'evidence-pool.md')
                shutil.copy2(out, _ms)
        print('✔ %s/%s：引用 %d 个 id（未解析 %d）' % (task, os.path.basename(sdir), len(cited), n_unres))
    return made


def discover_tasks():
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(ROOT, '.work', '*', 'verified.md')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task')
    a = ap.parse_args()
    tasks = [a.task] if a.task else discover_tasks()
    total = 0
    for t in tasks:
        n = build_task(t)
        total += (n or 0)
    print('生成 evidence-pool.md 件数：%d' % total)


if __name__ == '__main__':
    main()
