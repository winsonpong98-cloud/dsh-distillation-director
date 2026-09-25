# -*- coding: utf-8 -*-
r"""check_evidence_closure.py —— G-68 证据闭包闸（2026-09-25 建闸）

对每个 skills\<skill>\evidence-pool.md（由 build_evidence_pack.py 生成）：
  1) 闭包：技能件（SKILL.md/invest.md/其他 .md，除 evidence-pool.md 自身）引用的每个池 id
     都必须出现在 evidence-pool.md —— 否则 🔴 引用未闭包。
  2) 无漂移：包内每条 sha256(norm(quote)) 必须等于当前 verified.md 池内该 id 全文的 sha
     —— 否则 🔴 证据漂移（池被改动而包未重建）。
  3) 无未解析：包内不得有 UNRESOLVED 行 —— 否则 🔴 引用落空。
无池任务（无 verified.md）不在本闸射程（其技能不应引用池 id；发现引用即报）。
--selftest 自证。退出码：0=通过；1=有缺口；2=环境错误。
"""
import argparse
import glob
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
RANGE_ID = re.compile(r'^[a-z]\d+-\d+$')  # p255-283 形态＝页段，非池 id


CITE = re.compile(r'（`?(' + ID_LOOSE + r')`?\s*(?:s\d{1,4}|[：:][^）]{0,60})')
ENTRY = re.compile(r'^- (' + ID_LOOSE + ') (?:sha256=([0-9a-f]{64})|UNRESOLVED)$', re.M)
QUOTE = re.compile(r'^  quote:「(.*)」$', re.M)


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
        m = re.match(r'^###\s*(' + ID_LOOSE + r')\s*\[', raw.strip())
        if m:
            if aid and quote:
                entries.setdefault(aid, quote)
            aid, quote = m.group(1), ''
            continue
        tm = re.match(r'^\|\s*(' + ID_LOOSE + r')\s*\|', raw.strip())
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
def check_task(task, tdir=None):
    tdir = tdir or os.path.join(ROOT, '.work', task)
    vm = os.path.join(tdir, 'verified.md')
    pool = parse_pool(vm) if os.path.isfile(vm) else {}
    series = set(k.split('-')[0] for k in pool)
    findings = []
    npack = 0
    for pfile in sorted(glob.glob(os.path.join(tdir, 'skills', '*', 'evidence-pool.md'))):
        npack += 1
        if not os.path.isfile(os.path.join(os.path.dirname(pfile), 'SKILL.md')):
            findings.append('%s：🔴 孤儿包（目录有 evidence-pool.md 而无 SKILL.md——生成器射程越界产物，删除或补技能件）'
                            % os.path.basename(os.path.dirname(pfile)))
            continue
        sdir = os.path.dirname(pfile)
        text = io.open(pfile, encoding='utf-8').read()
        pack = {}
        unresolved = []
        for m in ENTRY.finditer(text):
            cid, h = m.group(1), m.group(2)
            if h:
                qm = QUOTE.search(text[m.start():m.start() + 800])
                pack[cid] = (h, qm.group(1) if qm else '')
            else:
                unresolved.append(cid)
        cited = set()
        for f in glob.glob(os.path.join(sdir, '*.md')):
            if os.path.basename(f) == 'evidence-pool.md':
                continue
            t = io.open(f, encoding='utf-8').read()
            for m in CITE.finditer(t):
                cited.add(m.group(1))
        for cid in sorted(cited):
            if cid not in pack and not RANGE_ID.match(cid) and cid.split('-')[0] in series:
                findings.append('%s：%s 引用未闭包（包内无此 id）' % (os.path.basename(sdir), cid))
        for cid in unresolved:
            if cid.split('-')[0] in series:
                findings.append('%s：%s UNRESOLVED（池内无此 id）' % (os.path.basename(sdir), cid))
        for cid, (h, q) in sorted(pack.items()):
            cur = pool.get(cid)
            if cur is None:
                findings.append('%s：%s 池内已不存在（可能被删）' % (os.path.basename(sdir), cid))
            elif sha(cur) != h:
                findings.append('%s：%s 证据漂移（sha 不符，池已改，包需重建）' % (os.path.basename(sdir), cid))
            elif norm(q) != norm(cur):
                findings.append('%s：%s 包内引文与池不一致' % (os.path.basename(sdir), cid))
    return findings, npack


def discover_tasks():
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, '.work', '*', 'book_text.md')))


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='g68selftest-')
    root_bak = ROOT
    globals()['ROOT'] = tmp
    try:
        d = os.path.join(tmp, '.work', 'demo', 'skills', 's1')
        os.makedirs(d, exist_ok=True)
        io.open(os.path.join(tmp, '.work', 'demo', 'book_text.md'), 'w', encoding='utf-8').write('x')
        io.open(os.path.join(tmp, '.work', 'demo', 'verified.md'), 'w', encoding='utf-8').write(
            '### A-001 [FR] [技能=S1]\n- 锚：s001\n- 原文：「2020年市场大涨。」\n- 字数：7\n')
        io.open(os.path.join(d, 'SKILL.md'), 'w', encoding='utf-8').write('- 「2020年市场大涨。」（`A-001` s001）\n')
        io.open(os.path.join(d, 'evidence-pool.md'), 'w', encoding='utf-8').write(
            '# evidence-pool\n- A-001 sha256=%s\n  quote:「2020年市场大涨。」\n  src:verified.md\n' % sha('2020年市场大涨。'))
        f, n = check_task('demo')
        assert n == 1 and not f, '好样例误报：%r' % (f,)
        # 漂移样例：池改了，包未重建
        io.open(os.path.join(tmp, '.work', 'demo', 'verified.md'), 'w', encoding='utf-8').write(
            '### A-001 [FR] [技能=S1]\n- 锚：s001\n- 原文：「2020年市场大涨了。」\n- 字数：8\n')
        f2, _ = check_task('demo')
        assert any('漂移' in x for x in f2), '漂移漏报：%r' % (f2,)
        print('selftest ✔（闭包过／池漂移报 1）')
    finally:
        globals()['ROOT'] = root_bak
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    tasks = [a.task] if a.task else discover_tasks()
    mirror_tasks = []
    if MIRROR and os.path.isdir(MIRROR):
        for _d in sorted(os.listdir(MIRROR)):
            if os.path.isdir(os.path.join(MIRROR, _d)) and glob.glob(os.path.join(MIRROR, _d, 'evidence-pool.md')):
                mirror_tasks.append(os.path.join(MIRROR, _d))
    total = 0
    for t in tasks:
        f, np_ = check_task(t)
        if MIRROR:
            fm, npm_ = check_task(t, os.path.join(MIRROR, t))
            f = f + ['在役|' + x for x in fm]
            np_ += npm_
        if f:
            print('🔴 %s：%d 处（包 %d）' % (t, len(f), np_))
            for x in f[:10]:
                print('   · ' + x)
        else:
            print('✔ %s：0 处（包 %d）' % (t, np_))
        total += len(f)
    print('合计 findings：%d' % total)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
