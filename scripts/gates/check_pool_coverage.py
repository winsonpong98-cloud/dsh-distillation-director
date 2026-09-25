# -*- coding: utf-8 -*-
r"""check_pool_coverage.py —— G-66 池覆盖闸（2026-09-25 建闸）

【判据】两类覆盖，逐任务检查（.work\<task>\）：
  1) 探针覆盖：probe_questions.md（可选层）每条探针的「锚：」句片段必须
     a) 已入池（verified.md 某条「原文：」归一含该片段），或
     b) 探针登记「处置：书内确无」。两者皆无 ⇒ 🔴 探针落空。
  2) 精选覆盖：池条目备注含精选关键词（默认：总纲／划范围／数值包络，
     --tags 可调）者，必须被本任务任一 skill 的 R 索引引用（（`A-NNN` ）），
     或在未选登记（probe_questions.md / invest.md 中「处置：未选」＋A-id）登记。
     两者皆无 ⇒ 🔴 精选未落 R 层。

probe_questions.md 约定格式：
  - P-01 <问题文本>
    锚：<书中句片段（逐字）>
    必选：是｜否
    处置：书内确无｜未选（A-0NN）　← 可选

【退出码】0=通过；1=有缺口；2=用法/环境错误。--selftest 自证。
"""
import argparse
import glob
import io
import os
import re
import sys

from _bandid import ID_LOOSE

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


def _qnorm(s):
    return re.sub(r'\s', '', s)


def parse_probes(path):
    probes = []
    cur = None
    for raw in io.open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^-\s*(P-\d+)\s+(.*)$', raw.strip())
        if m:
            cur = {'id': m.group(1), 'text': m.group(2), 'anchor': None, 'disp': None}
            probes.append(cur)
            continue
        if cur is not None:
            m2 = re.match(r'^锚[：:]\s*(.+)$', raw.strip())
            if m2:
                cur['anchor'] = m2.group(1).strip()
            m3 = re.match(r'^处置[：:]\s*(.+)$', raw.strip())
            if m3:
                cur['disp'] = m3.group(1).strip()
    return probes


# ── 锚白名单判据（2026-09-25 · 判官白名单规格 v2.0 落地：封闭集特征，S2 实测 100%/100%）──
_REF = re.compile(r'(?:如|见|参|下|上)?[图表]\s*\d|所示|走势图|可知|见图|见表|如下图|如上表|[图表]\d+-\d+')
_END = '。！？…」”"'
_MARKUP = re.compile(r'\||\*|http|Chart|Fig|Center|Source|Table|Data|Figure')
BAD_ANCHOR_FIXTURES = [
    '日结算价考察（如图10-2、图10-3、图10-4、图10-5、图10-6所示）。',
    '| 伦敦 | 11 | 19 | 21 | 25 | 7 | 3 |',
    '25KeizaiKohoCenter,*Japan1994*,Chart',
    '1901—1920年数据见第341页表45第14列；1921—1946年',
    '从图2-37就可以看出，次贷危机对美股的影响从2008年5月才出现',
]
GOOD_ANCHOR_FIXTURES = [
    '汇率水平从1985年的240日元兑1美元升至1988年的130日元兑1美元。',
    '1928年，纽约股票交易所总市值增长了36%，而1929年1—8月，该指标增长了53%。',
    '2003—2004年，美国次级抵押贷款仅占抵押贷款总额的6%，而2005—2006年，这一比例升至20%。',
    '2020年我国商品房销售面积为17.6亿平方米，增长2.6%，2019年则是微跌0.1%。',
]


def _anchor_ok(s):
    """白名单合取（封闭集）：返回 (ok, 理由列表)。判据条数与准确性非正相关——本函数只留实测零误杀的条。"""
    r = []
    t = s.strip()
    if len(t) < 20:
        r.append('长度<20')
    if t and t[-1] not in _END:
        r.append('非句末收尾（疑截断）')
    if _REF.search(t):
        r.append('指代装置（图/表/所示类）')
    if _MARKUP.search(t):
        r.append('markup/竖线（表格或文献串）')
    return (not r), r


def parse_pool(path):
    """返回 [(aid, 整条目文本, 原文)]——标签匹配用整条目（含备注行）。
    v2（2026-09-25 复核整改）：全系列 ID（B1/C1 等，v1 只认 A-\\d{3} 曾漏读 ⇒ 探针误红）＋
    「原文（逐字）：」变体＋md 表行格式。注：与 check_evidence_closure 的 {aid: quote} 口径
    各取所需——本闸需要整条目文本做精选层标签匹配（A-72 注记：两解析器判据同源规范）。"""
    entries = []
    aid = None
    buf = []
    quote = ''
    for raw in io.open(path, encoding='utf-8').read().split('\n'):
        st = raw.strip()
        m = re.match(r'^###\s*(' + ID_LOOSE + r')\b', st)
        # 回退 A（第八轮实测：gongshou 池为 YAML units 格式 `- id: fw01`）：整单元为一条目，无条件可见
        if not m:
            m = re.match(r'^-\s*id:\s*([A-Za-z][A-Za-z0-9_-]*)\s*$', st)
        # 回退 B（yuanze 池为 `### [p6] 〔…〕` 方括号 id 格式）
        if not m:
            m = re.match(r'^###\s*\[([A-Za-z]?\d+)\]\s*(.*)$', st)
        tm = re.match(r'^\|\s*(' + ID_LOOSE + r')\s*\|', st) if not m else None
        if m:
            if aid:
                entries.append((aid, '\n'.join(buf), quote))
            aid, buf, quote = m.group(1), [st], ''
            continue
        if tm:
            if aid:
                entries.append((aid, '\n'.join(buf), quote))
            qm = re.search(r'「([^」]*)」', st)
            aid, buf, quote = tm.group(1), [st], (qm.group(1) if qm else '')
            entries.append((aid, '\n'.join(buf), quote))
            aid = None
            continue
        if aid is not None:
            if st == '':
                entries.append((aid, '\n'.join(buf), quote))
                aid = None
                buf = []
                quote = ''
                continue
            buf.append(st)
            m2 = re.match(r'^- 原文(?:（[^）]*）)?[：:]「(.*)」\s*$', st)
            if m2:
                quote = m2.group(1)
            # YAML 型引文字段（原文／quote／引文；gongshou 无此字段则留空——可见性不受影响）
            m3 = re.match(r'^(?:原文|quote|引文|excerpt)\s*[:：]\s*["「]?([^"」]{6,})["」]?\s*$', st)
            if m3 and not quote:
                quote = m3.group(1).strip()
    if aid:
        entries.append((aid, '\n'.join(buf), quote))
    return entries


def task_findings(task, tags):
    tdir = os.path.join(ROOT, '.work', task)
    bt = os.path.join(tdir, 'book_text.md')
    vm = os.path.join(tdir, 'verified.md')
    findings = []
    if not (os.path.isfile(bt) and os.path.isfile(vm)):
        return findings, 0, 0
    srcn = _qnorm(io.open(bt, encoding='utf-8').read())
    entries = parse_pool(vm)
    pool_norm = {aid: _qnorm(q) for aid, _l, q in entries}
    labels = {aid: l for aid, l, _q in entries}
    # 技能 R 索引引用的池 id（v2：全词边界包含，任意系列——v1 只认（A-\d{3}）曾漏 F/D 系落 R 行）
    cited = set()
    notsel = set()
    files = glob.glob(os.path.join(tdir, 'skills', '**', '*.md'), recursive=True)
    inv = os.path.join(tdir, 'invest.md')
    if os.path.isfile(inv):
        files.append(inv)
    skill_text = '\n'.join(io.open(f, encoding='utf-8').read() for f in files)
    for aid in labels:
        if re.search(r'(?<![A-Za-z0-9-])' + re.escape(aid) + r'(?![0-9])', skill_text):
            cited.add(aid)
    for m in re.finditer(r'处置[：:]\s*未选（?\s*(' + ID_LOOSE + r')\s*）?', skill_text):
        notsel.add(m.group(1))
    pfile = os.path.join(tdir, 'probe_questions.md')
    nprobe = 0
    if os.path.isfile(pfile):
        for p in parse_probes(pfile):
            nprobe += 1
            if p['disp'] and ('书内确无' in p['disp'] or '未选' in p['disp']):
                continue
            anc = p.get('anchor')
            if not anc:
                continue
            an = _qnorm(anc)
            in_src = an in srcn
            hit = [aid for aid, qn in pool_norm.items() if an and an in qn]
            if not hit:
                findings.append('探针 %s 锚片段未入池（书内%s）：%s' % (p['id'], '有' if in_src else '无', anc[:36]))
    # 池可见性前置闸（第五轮复核 Q6/Q2）：probe 件在而池解析 0 条 ⇒ 发现轮无效（yuanze 型空泛红）
    if nprobe and not entries:
        findings.append('池对闸不可见（verified.md 解析 0 条）——本册发现轮/棘轮无效，须池件考古后再铺')
    # 精选覆盖
    nsel = 0
    for aid, label, _q in entries:
        if not any(k in label for k in tags):
            continue
        nsel += 1
        if aid in cited or aid in notsel or '未选' in label:  # 备注含「未选」＝登记未选（v2）
            continue
        findings.append('精选条目 %s 未落 R 层且未登记未选：%s' % (aid, label[:44]))
    # 发现→交付闭环判据（第四轮复核★1）：「发现轮补选」条目必须进 R 或登记「仅入池」——否则发现只到池、交付永不改善
    for aid, label, _q in entries:
        if '发现轮补选' not in label:
            continue
        # 见证判据（判官办法3 的可追溯实现）：机选来源条目必须有 pool-audit.jsonl 的 ADMIT 记录
        try:
            import pool_writer as _W
            if aid not in _W.witnessed(os.path.dirname(vm)):
                findings.append('机选条目 %s 无写入见证（未经受控入口）——绕过通道：%s' % (aid, label[:36]))
        except Exception:
            pass
        # 白名单闸（判官规格 v2.0 · G2 写池前）：机选入池条目的原文必须过封闭集判据
        if _q:
            _ok, _why = _anchor_ok(_q)
            if not _ok:
                findings.append('机选条目 %s 原文未过白名单（%s）——不得入池：%s' % (aid, '/'.join(_why), _q[:32]))
        _jrc = re.search(r'仅入池[：:]\s*(表格图表数据|数值包络|总纲|阈值)', label)
        if aid in cited or _jrc or '未选' in label:  # 「未选」＝显式弃权登记（判官签章前不进 R 同属此列）
            continue
        findings.append('发现轮补选 %s 未进 R 且未登记仅入池 ⇒ 发现未影响交付：%s' % (aid, label[:44]))
    return findings, nprobe, nsel


def discover_tasks():
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(ROOT, '.work', '*', 'book_text.md')))


def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix='g66selftest-')
    t = os.path.join(tmp, 'demo', '.keep')
    os.makedirs(os.path.dirname(t), exist_ok=True)
    io.open(os.path.join(tmp, 'demo', 'book_text.md'), 'w', encoding='utf-8').write(
        '_alpha_\n2020年A股市场全年大涨，沪深300指数涨幅超过百分之二十。2021年市场风格发生切换，成长股相对价值股明显走弱。')
    io.open(os.path.join(tmp, 'demo', 'verified.md'), 'w', encoding='utf-8').write(
        '### A-001 [FR] [技能=S1]\n- 锚：s001\n- 原文：「2020年A股市场全年大涨，沪深300指数涨幅超过百分之二十。」\n- 字数：28\n- 备注：总纲\n'
        '### A-002 [PR] [技能=S1]\n- 锚：s001\n- 原文：「2021年市场风格发生切换，成长股相对价值股明显走弱。」\n- 字数：27\n- 备注：普通条目\n')
    sk = os.path.join(tmp, 'demo', 'skills', 's1')
    os.makedirs(sk, exist_ok=True)
    io.open(os.path.join(sk, 'SKILL.md'), 'w', encoding='utf-8').write('- 「2020年A股市场全年大涨，沪深300指数涨幅超过百分之二十。」（`A-001` s001）\n')
    io.open(os.path.join(tmp, 'demo', 'probe_questions.md'), 'w', encoding='utf-8').write(
        '- P-01 2020 年如何？\n  锚：2020年A股市场全年大涨，沪深300指数涨幅超过百分之二十。\n  必选：是\n'
        '- P-02 书里讲了量子纠缠吗？\n  处置：书内确无\n')
    f, np_, ns_ = task_findings(os.path.join(tmp, 'demo'), ['总纲'])
    assert np_ == 2 and ns_ == 1, '解析数不对：%r %r' % (np_, ns_)
    assert not f, '好样例误报：%r' % (f,)
    # 坏样例：总纲条目未被引用
    io.open(os.path.join(sk, 'SKILL.md'), 'w', encoding='utf-8').write('- 无引用\n')
    f2, _np, _ns = task_findings(os.path.join(tmp, 'demo'), ['总纲'])
    assert any('A-001' in x for x in f2), '坏样例漏报：%r' % (f2,)
    # 坏样例（白名单判据归位后）：机选条目原文不合白名单必红——G2 写池前检查点自证
    io.open(os.path.join(tmp, 'demo', 'probe_questions.md'), 'w', encoding='utf-8').write(
        '- P-01 2020 年如何？\n  锚：2020年A股市场全年大涨，沪深300指数涨幅超过百分之二十。\n  必选：是\n')
    io.open(os.path.join(tmp, 'demo', 'verified.md'), 'a', encoding='utf-8').write(
        '### A-003 [PR] [技能=S1]\n- 锚：s001\n- 原文：「日结算价考察（如图10-2、图10-3所示）。」\n- 备注：真探针发现轮补选（2026-09-25）。\n')
    f3, _np2, _ns2 = task_findings(os.path.join(tmp, 'demo'), ['总纲'])
    assert any('原文未过白名单' in x for x in f3), '坏锚样例漏报：%r' % (f3,)
    # 坏样例（第五轮复核 R3）：probe 在而池解析 0 ⇒ 池对闸不可见必红
    d2 = os.path.join(tmp, 'demo2')
    os.makedirs(os.path.join(d2, 'skills'), exist_ok=True)
    io.open(os.path.join(d2, 'book_text.md'), 'w', encoding='utf-8').write('内容。')
    io.open(os.path.join(d2, 'probe_questions.md'), 'w', encoding='utf-8').write('- P-01 池不可见测？\n  锚：池外句子样本一\n  必选：是\n')
    io.open(os.path.join(d2, 'verified.md'), 'w', encoding='utf-8').write('## 池不可见：无标准条目结构。')
    f4, _np3, _ns3 = task_findings(d2, ['总纲'])
    assert any('池对闸不可见' in x for x in f4), '池不可见样例漏报：%r' % (f4,)
    # 第八轮实测：两解析回退的自证（方括号 id 池 / YAML units 池都必须可见）
    d3 = os.path.join(tmp, 'demo3')
    os.makedirs(os.path.join(d3, 'skills'), exist_ok=True)
    io.open(os.path.join(d3, 'book_text.md'), 'w', encoding='utf-8').write('正文。')
    io.open(os.path.join(d3, 'probe_questions.md'), 'w', encoding='utf-8').write('- P-01 池可见测？\n  锚：池外样本句甲\n  必选：是\n')
    io.open(os.path.join(d3, 'verified.md'), 'w', encoding='utf-8').write('### [p6] 〔示例〕\n- 原文：「示例句。」\n')
    f5, _a5, _b5 = task_findings(d3, ['总纲'])
    assert not any('池对闸不可见' in x for x in f5), '方括号池被误判不可见：%r' % (f5,)
    d4 = os.path.join(tmp, 'demo4')
    os.makedirs(os.path.join(d4, 'skills'), exist_ok=True)
    io.open(os.path.join(d4, 'book_text.md'), 'w', encoding='utf-8').write('正文。')
    io.open(os.path.join(d4, 'probe_questions.md'), 'w', encoding='utf-8').write('- P-01 池可见测？\n  锚：池外样本句乙\n  必选：是\n')
    io.open(os.path.join(d4, 'verified.md'), 'w', encoding='utf-8').write('units:\n  - id: fw01\n    title: "示例单元"\n')
    f6, _a6, _b6 = task_findings(d4, ['总纲'])
    assert not any('池对闸不可见' in x for x in f6), 'YAML 池被误判不可见：%r' % (f6,)
    # 白名单判据双向回归（真实样本子集：坏锚必拒、好锚必过——办法6 的机器实现）
    for _b in BAD_ANCHOR_FIXTURES:
        _o, _w = _anchor_ok(_b)
        assert not _o, '坏锚被判过：%r %r' % (_b, _w)
    for _g in GOOD_ANCHOR_FIXTURES:
        _o2, _w2 = _anchor_ok(_g)
        assert _o2, '好锚被误杀：%r %r' % (_g, _w2)
    print('selftest ✔（探针命中／书内确无跳过／精选未落 R 层报 1／坏锚必红／池不可见必红／方括号池可见／YAML 池可见／白名单双向回归 %d+%d）'
          % (len(BAD_ANCHOR_FIXTURES), len(GOOD_ANCHOR_FIXTURES)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task')
    ap.add_argument('--tags', default='总纲,划范围,数值包络')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    tasks = [a.task] if a.task else discover_tasks()
    total = 0
    for t in tasks:
        f, np_, ns_ = task_findings(t, a.tags.split(','))
        if f:
            print('🔴 %s：%d 处（探针 %d／精选 %d）' % (t, len(f), np_, ns_))
            for x in f[:12]:
                print('   · ' + x)
        else:
            print('✔ %s：0 处（探针 %d／精选 %d）' % (t, np_, ns_))
        total += len(f)
    print('合计 findings：%d' % total)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
