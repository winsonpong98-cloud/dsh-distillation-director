# -*- coding: utf-8 -*-
r"""check_anchor_consistency.py —— G-67 锚一致性闸（2026-09-25 建闸）

【判据】同一行内同时出现「日期」与「引文」时，这对（日期×引文）必须能在源文
（.work\<task>\book_text.md）的窗口范围内共现；否则判 D2 类「日期×引文错配」。

- 日期形态：2018.6.19／2018.6／2018年6月19日／2018年6月／2018年（归一为数字元组后比对）。
- 引文形态：「…」与“…”（内容 ≥4 字）。引文不在源文 → 跳过（那是 R2 的辖域）。
- 单一标尺 _qnorm：去空白比对（与 G-45 收敛的 verify_layer_quotes 同口径）。
- 窗口 --window（默认 400 字，指归一源文中的字符距离）。
- v2（数值陈述与数字包络核对）为未来版本，本版只做日期×引文共现。

【退出码】0=通过；1=有错配；2=用法/环境错误。
用法：
  python tools\check_anchor_consistency.py                     # 自动发现全部 10 册
  python tools\check_anchor_consistency.py --task zhouqi-guzhi-renxing
  python tools\check_anchor_consistency.py --selftest
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
# MIRROR 已移除（A-74/A-135：随包工具零部署特定路径；部署侧用 DSH_FIN_INVEST_SKILLS 或调用方参数）
DATE_RE = re.compile(r'\d{4}(?:[.．]\d{1,2}){1,2}|\d{4}年(?:\d{1,2}月)?(?:\d{1,2}日)?|\d{1,2}月\d{1,2}日')
QUOTE_RE = re.compile(r'[「“]([^「”」]{4,4000})[」”]')


def _qnorm(s):
    """单一标尺：仅去空白（与 verify_layer_quotes._qnorm 同口径）。"""
    return re.sub(r'\s', '', s)


def date_key(s):
    """把日期串归一为 (Y,M,D) 元组（缺省位补 None）。"""
    s = s.replace('．', '.')
    m = re.match(r'(\d{4})(?:\.(\d{1,2}))?(?:\.(\d{1,2}))?$', s)
    if m:
        return tuple(int(x) if x else None for x in m.groups())
    m = re.match(r'(\d{4})年(?:(\d{1,2})月)?(?:(\d{1,2})日)?$', s)
    if m:
        return tuple(int(x) if x else None for x in m.groups())
    m = re.match(r'(\d{1,2})月(\d{1,2})日$', s)
    if m:
        return (None, int(m.group(1)), int(m.group(2)))
    return None


def date_variants(s):
    """同一 (Y,M,D) 的全部书写形态（含前缀：年、年月）。"""
    k = date_key(s)
    if not k:
        return []
    y, m, d = k
    out = []
    if y:
        out.append('%d年' % y)
        if m:
            out += ['%d.%d' % (y, m), '%d年%d月' % (y, m)]
            if d:
                out += ['%d.%d.%d' % (y, m, d), '%d年%d月%d日' % (y, m, d), '%d.%02d.%02d' % (y, m, d), '%d年%02d月%02d日' % (y, m, d)]
    if m and d:
        out += ['%d月%d日' % (m, d), '%d月%02d日' % (m, d)]
    return out


def build_date_index(srcn):
    """归一源文里每个日期形态出现位置表。"""
    idx = {}
    for m in DATE_RE.finditer(srcn):
        for v in date_variants(m.group(0)):
            idx.setdefault(v, []).append(m.start())
    return idx


LABEL_SEG = re.compile(r'（[^（）]*）')  # 行尾/行内注释段：其内日期是数据标签，不与引文配对


def check_file(path, srcn, didx, window, line_prox=60):
    """返回 findings：[(line_no, date, quote, hint)]。
    行内邻近 ≤ line_prox；（…）注释段内的日期不参与配对；引文自身含日期→平凡共现。"""
    out = []
    seen = set()
    try:
        text = io.open(path, encoding='utf-8').read()
    except OSError:
        return out
    for ln_no, ln in enumerate(text.split('\n'), 1):
        quotes = [(m.start(), m.end(), q) for m in QUOTE_RE.finditer(ln) for q in [m.group(1)] if len(_qnorm(q)) >= 4]
        if not quotes:
            continue
        label_spans = [(-1, -1)] + [(m.start(), m.end()) for m in LABEL_SEG.finditer(ln)]
        dates = [(m.start(), m.group(0)) for m in DATE_RE.finditer(ln) if date_key(m.group(0))
                 and not any(a <= m.start() < b for a, b in label_spans)
                 and not any(qs <= m.start() < qe for qs, qe, _q in quotes)]
        if not dates:
            continue
        for qs, qe, q in quotes:
            qn = _qnorm(q)
            positions = [m.start() for m in re.finditer(re.escape(qn), srcn)]
            if not positions:
                continue  # 引文不在源文 → R2 辖域
            for ds, d in dates:
                if min(abs(ds - qs), abs(ds - qe)) > line_prox:
                    continue  # 行内不相邻 → 非同一语境
                seg = ln[min(ds, qs):max(ds, qe)]
                if re.search(r'[〔【（]', seg):
                    continue  # 日期与引文之间夹锚标/注释 → 跨源段交叉引用，不构成同语境配对
                key = (ln_no, date_key(d), qn[:60])
                if key in seen:
                    continue
                seen.add(key)
                ok = False
                ky, km, kd = date_key(d)
                for v in date_variants(d):
                    for dp in didx.get(v, []):
                        if any(abs(dp - qp) <= window for qp in positions):
                            ok = True
                            break
                    if ok:
                        break
                if not ok and ky and km and kd:
                    # 月日回退：源文同月日（任意年）在窗内，且该年出现在 3×window 内
                    for v in ['%d月%d日' % (km, kd), '%d月%02d日' % (km, kd)]:
                        for dp in didx.get(v, []):
                            if any(abs(dp - qp) <= window for qp in positions) and \
                               any(abs(dp - yp) <= window * 3 for yp in didx.get('%d年' % ky, [])):
                                ok = True
                                break
                        if ok:
                            break
                if not ok:
                    qp = positions[0]
                    hint = srcn[max(0, qp - 30):qp + len(qn) + 30]
                    out.append((ln_no, d, q[:40], hint))
    return out


def discover_tasks():
    tasks = []
    for bt in glob.glob(os.path.join(ROOT, '.work', '*', 'book_text.md')):
        tasks.append(os.path.basename(os.path.dirname(bt)))
    return sorted(tasks)


def run(tasks, window):
    total = 0
    for t in tasks:
        bt = os.path.join(ROOT, '.work', t, 'book_text.md')
        if not os.path.isfile(bt):
            print('跳过（无源文）：%s' % t)
            continue
        srcn = _qnorm(io.open(bt, encoding='utf-8').read())
        didx = build_date_index(srcn)
        # 只扫本册原稿层（在役层由 sync 闸保证逐字节一致，不重复扫）
        files = sorted(glob.glob(os.path.join(ROOT, '.work', t, 'skills', '**', '*.md'), recursive=True))
        seen = set()
        findings = []
        for f in files:
            if f in seen:
                continue
            seen.add(f)
            for r in check_file(f, srcn, didx, window):
                findings.append((f, t) + r)
        if findings:
            print('🔴 %s：%d 处日期×引文窗口外' % (t, len(findings)))
            for f, _t, ln_no, d, q, hint in findings[:12]:
                print('   · %s L%s 日期[%s] × 「%s…」' % (os.path.relpath(f, ROOT), ln_no, d, q))
                print('     源文窗口：…%s…' % hint[:80])
            total += len(findings)
        else:
            print('✔ %s：0 处' % t)
    print('合计 findings：%d' % total)
    return 1 if total else 0


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='g67selftest-')
    src = ('2020年3月5日，证监会发布再融资新规。\n'
           '2018年6月19日，上证指数大跌4.98%。\n'
           '2021年2月18日，贵州茅台见顶2627元。')
    srcn = _qnorm(src)
    didx = build_date_index(srcn)
    good = io.open(os.path.join(tmp, 'good.md'), 'w', encoding='utf-8')
    good.write('- 「2018年6月19日，上证指数大跌4.98%。」——大书 p1\n')
    good.close()
    bad = io.open(os.path.join(tmp, 'bad.md'), 'w', encoding='utf-8')
    bad.write('- 「2018年6月19日，上证指数大跌4.98%。」——2019.3.1 复盘\n')
    bad.close()
    nog = check_file(os.path.join(tmp, 'good.md'), srcn, didx, 400)
    nb = check_file(os.path.join(tmp, 'bad.md'), srcn, didx, 400)
    assert not nog, '好样例误报：%r' % (nog,)
    assert len(nb) == 1 and nb[0][1] in ('2019.3.1', '2019年3月1日'), '坏样例漏报：%r' % (nb,)
    # 引文不在源文 → 跳过
    skip = io.open(os.path.join(tmp, 'skip.md'), 'w', encoding='utf-8')
    skip.write('- 「这句根本不在书里出现啊」——2018年6月19日\n')
    skip.close()
    ns = check_file(os.path.join(tmp, 'skip.md'), srcn, didx, 400)
    assert not ns, '不在源文的引文应跳过：%r' % (ns,)
    print('selftest ✔（好样例过／错配报 1／源外引文跳过）')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', help='限定任务（默认自动发现全部）')
    ap.add_argument('--window', type=int, default=400)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    tasks = [a.task] if a.task else discover_tasks()
    if not tasks:
        print('未发现任何 .work\\*\\book_text.md')
        sys.exit(2)
    sys.exit(run(tasks, a.window))


if __name__ == '__main__':
    main()
