# -*- coding: utf-8 -*-
"""verify_layer_quotes.py —— 「引文型附属文件」的引文回源核验（防线1/3 机器层 · ¥0）

为什么需要它（2026-09-13 · 独立判官指出后确证）：
  · `defense3_impersonation_scan.py` 的规则是「**非 R 段**内引号原话紧邻页锚 ⇒ 冒充」——它假定引文只许出现在 SKILL.md 的 R 段。
  · 但 `references/专业层-*.md` 是**引文型附属文件**：其自述的引用纪律就是"每条都带 `【来源书 章节, PDF pNNN】` 页码标注"，
    逐字引文是**法定格式**而非冒充。于是同一把尺子在这类文件上给出 0（旧口径：锚形态不匹配，恒空转）
    或 596（新口径：把法定引文全判嫌疑）——**两个数都是伪影**。
  · 对这类文件，**正确的机器层仪器是「引文回源」**：每条引号引文是否为**所指页 OCR 源文**的逐字子串。
    本脚本即该仪器。判据与 `verify_candidates.py`（候选池回源）同族，只是对象换成附属文件的引文。

用法：
  python tools\\verify_layer_quotes.py --task <slug> [--layer <相对目录>] [--pattern <glob>]
                                      [--notes-glob <glob>] [--out <json>] [--detail] [--only <glob>]
输出：三态（逐字命中／近似／未命中／无法核）＋ 分文件计数 ＋ 明细；`--detail` 打印未命中样本。

⚠ 通用化修订（2026-09-17 · A-74「通用件不得特定化」）：
  · 旧版把三处**某一册的数据**写死在代码里：附属层目录（`skills/adhd-parenting-guide/references`）、
    文件模式（`专业层-*.md`）、候选池文件名（`notes_T*.md`，那是教育线的波段命名）。
    ⇒ 换一本册子跑，轻则"未匹配到文件"、重则**静默扫错语料**。
    现全部改为**参数 + 默认值**：`--layer`／`--pattern`／`--notes-glob`，默认值＝教育线原值（行为不变）。
  · 「不适用」必须**用证据说**：若本册附属层根本没有引文面（逐字引文 0 条），
    旧版只报"空集拒跑"，读报告者会误以为**闸没过**；现改为**带计数的「不适用」退出码 0**，
    并声明引文面由哪把仪器覆盖（SKILL.md 级＝`rquote_page_check.py`／`verify_candidates.py`）。
    这是「按文档类别选仪器」（A-39）的延伸：**没有引文面的册子，本仪器不进射程，不算缺陷**。
"""
import io
import os
import re
import sys
import glob
import json
import argparse

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
ANCHOR = re.compile(r'【([^】]{0,120}?)PDF\s*(p[\d\s、,，–\-~—p]*?)】')
BOOKS = [('Barkley', 'bark'), ('巴克利', 'bark'), ('guide', 'guide'),
         ('指南', 'guide'), ('AAP', 'guide'), ('苏林雁', 'sulin'), ('sulin', 'sulin')]
STRIP = re.compile(r'[\s\u3000\u200b“”「」『』‘’〝〞〟"\'、。，；：！？…—－\-·．.,;:!?'
                   r'()（）《》〈〉\[\]【】*_`~|«»‹›]')


def norm(t):
    return STRIP.sub('', t)


def segments(q):
    """按省略号分段（引文常用 `……` 连接两个不连续片段）；返回归一化后的段（≥8 字的才参与判定）。"""
    parts = re.split(r'[…]{1,}|\.{2,}|（略）|\(略\)|【略】', q)
    return [s for s in (norm(p) for p in parts) if len(s) >= 8]


def parse_refs(block):
    """把一个 `【…】` 块解析成 **[(书, [页…]), …]**（块内可含**多引用**）。

    ⚠ A-48（2026-09-13 由独立判官 F 指出并给出可复核证据）：旧实现把整块当成**单引用**，
    取"块内**最后一个**书别名 ＋ 块内**全部**页号" ⇒ 对
    `【Barkley 第15章, PDF p322, p337, p339-340；AAP 第7章, PDF p112, p115, PDF p128】`
    会算成 (guide, [112,115,128,322,337,339,340]) ⇒ **串书**（机器目标页 OCR 在补包内 0/6；
    判官实测包内 `[bark p128]` 是"含蔗糖的饮料"页，却被当作 AAP 第 128 页）。
    正确做法：先按 `；`/`;` 切分，每段找**最近的**书别名，**无别名则继承上一段**。
    """
    inner = block.strip().strip('【】')
    out = []
    last_book = None
    for part in re.split(r'[；;]', inner):
        bk = book_of(part) or last_book
        if bk:
            last_book = bk
        # ⚠ 取**第一个** `PDF` 之后的部分（不是最后一个！）：`part.split('PDF')[-1]` 会丢掉前面的页引用
        #   （实测 `Barkley 第3章, PDF p112, PDF p116` → 只剩 116；`… PDF p112, PDF p115, PDF p128` → 只剩 128）。
        #   同时这样也把"第15章"这类章号排除在页号解析之外。
        seg = part[part.find('PDF'):] if 'PDF' in part else part
        pgs = parse_pages(seg)
        if bk and pgs:
            out.append((bk, pgs))
    return out


def parse_pages(spec):
    """解析锚块里的页说明 → 页号集合。
    ⚠ A-44（2026-09-13 由独立判官 E 指出）：旧实现的正则**只吃 `、`/`,` 分隔的多页**，
    对**区间写法** `p193–194`／`p285-286`／`p179–p180` 只取到**首页** ⇒ 已正确的区间锚
    被误判成"跨页未声明"（**解析型假阳性**，实测 8 条）。此处显式展开区间。
    """
    out = set()
    # 先展开区间：p?A [–~-] p?B
    for m in re.finditer(r'(\d{1,3})\s*[–\-~—]\s*p?\s*(\d{1,3})', spec):
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < a <= b <= 400 and b - a <= 60:
            out.update(range(a, b + 1))
    # 再收单页号（区间写法内部的数字会被重复计入，集合去重无害）
    for m in re.finditer(r'(?<![\d])(\d{1,3})(?![\d])', spec):
        out.add(int(m.group(1)))
    return sorted(x for x in out if 0 < x <= 400)


def load_pool(task, notes_glob='notes_*.md'):
    """候选池全部「原文（逐字）」→ 一个归一化大串（防线2 派生链的核对面）。

    `notes_glob` 默认 `notes_*.md`（**通用**；旧版写死 `notes_T*.md`＝教育线波段命名 ⇒ A-74）。
    排除备份件（`_backup_*`）与还原件（`*.recovered`）。
    """
    buf = []
    pat = os.path.join(ROOT, '.work', task, 'candidates', notes_glob)
    for f in sorted(glob.glob(pat)):
        b = os.path.basename(f)
        if b.startswith('_') or b.endswith('.recovered'):
            continue
        t = io.open(f, encoding='utf-8', errors='replace').read()
        for m in re.finditer(r'原文（逐字）[：:]\s*[「“"](.+?)[」”"]\s*$', t, re.M):
            buf.append(norm(m.group(1)))
        for m in re.finditer(r'^\s*-\s*原文（逐字）[：:]\s*(.+)$', t, re.M):
            buf.append(norm(m.group(1)))
    return '│'.join(buf)


def book_of(tag):
    low = tag.lower()
    for k, v in BOOKS:
        if (k.lower() in low):
            return v
    return None


def load_pages(task, book):
    cache = {}

    def get(p):
        if p not in cache:
            f = os.path.join(ROOT, '.work', task, 'ocr', '%s_p%04d.txt' % (book, p))
            if os.path.isfile(f):
                t = io.open(f, encoding='utf-8', errors='replace').read()
                cache[p] = norm(re.sub(r'^---\s*\[[^\]]*\]\s*---\s*', '', t.strip()))
            else:
                cache[p] = None
        return cache[p]
    return get


def lcs_len(a, b):
    """最长公共子串长度（滚动数组；两侧长度已截断控制代价）。"""
    if not a or not b:
        return 0
    if len(a) > 400:
        a = a[:400]
    if len(b) > 4000:
        b = b[:4000]
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


QUOTE_PAIRS = [('“', '”'), ('「', '」'), ('"', '"')]
POOL = ''


def runs_on_line(ln):
    out = []
    i = 0
    while i < len(ln):
        best = None
        for o, c in QUOTE_PAIRS:
            k = ln.find(o, i)
            if k >= 0 and (best is None or k < best[0]):
                best = (k, o, c)
        if best is None:
            break
        k, o, c = best
        if o == '"':      # ASCII：成对出现才算
            e = ln.find(c, k + 1)
        else:
            e = ln.find(c, k + 1)
        if e < 0:
            break
        out.append((k, e, ln[k + 1:e]))
        i = e + 1
    return out


def quote_surface(task):
    """本册附属层（`skills/*/*.md`，不含 SKILL.md 及其副本）的**引文面计数**（「不适用」的证据）。

    ⚠ 自伤登记（2026-09-17 当场抓到）：首版只排除 `basename == 'SKILL.md'`，
    于是 `skills/_backup_pre_split/<slug>-SKILL.md`（本册回改快照）被当成"附属文件"，
    把 SKILL.md 里的 2000+ 处引号计进"附属层引文面" ⇒ 本册明明**零引文面**却报 2102 处。
    正解：① 跳过任何以 `_` 开头的路径段（备份/隔离区）② 跳过文件名含 `SKILL` 者。
    """
    n_file, n_quote = 0, 0
    for f in sorted(glob.glob(os.path.join(ROOT, '.work', task, 'skills', '*', '*.md'))):
        rel = os.path.relpath(f, os.path.join(ROOT, '.work', task))
        if any(seg.startswith('_') for seg in rel.split(os.sep)):
            continue
        if 'SKILL' in os.path.basename(f):
            continue
        t = io.open(f, encoding='utf-8', errors='replace').read()
        n_file += 1
        n_quote += len(re.findall(r'原文（逐字）', t)) + len(re.findall(r'「', t))
    return n_file, n_quote


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    # ⚠ 三处**某一册的数据**改为参数（默认＝教育线原值，行为不变）——A-74
    ap.add_argument('--layer', default='skills/adhd-parenting-guide/references',
                    help='附属层相对 .work/<task>/ 的目录（默认＝教育线专业层）')
    ap.add_argument('--pattern', default='专业层-*.md', help='附属文件 glob')
    ap.add_argument('--notes-glob', default='notes_*.md', help='候选池文件名 glob')
    ap.add_argument('--out', default=None)
    ap.add_argument('--detail', action='store_true')
    ap.add_argument('--only', default=None)
    a = ap.parse_args()
    task = a.task.replace('.work/', '').replace('.work\\', '')
    # `--layer` 支持通配（如 `skills/*` ⇒ 扫全部技能目录的附属文件）
    layer_pat = os.path.join(ROOT, '.work', task, a.layer)
    layer = (layer_pat if not any(c in a.layer for c in '*?[')
             else (sorted(glob.glob(layer_pat)) or [layer_pat])[0])
    pat = a.only or a.pattern
    files = []
    if any(c in a.layer for c in '*?['):
        for d in sorted(glob.glob(layer_pat)):
            files.extend(sorted(glob.glob(os.path.join(d, pat))))
    else:
        files = sorted(glob.glob(os.path.join(layer, pat)))
    n_file, n_quote = quote_surface(task)
    if not files:
        if n_quote == 0:
            # **不适用**（不是"闸没过"）：本册附属层没有引文面 ⇒ 本仪器不进射程。
            # 证据＝实扫计数；引文面在 SKILL.md 级，由 rquote_page_check／verify_candidates 覆盖。
            print('✔ 不适用（N/A）：本册附属层**无引文面**——够格被扫的附属文件 %d 个，'
                  '其中逐字引文/引号命中合计 **%d** 处。' % (n_file, n_quote))
            print('   本仪器射程＝「引文型附属文件」（法定格式＝逐字引文＋页锚）；'
                  '本册引文面在 SKILL.md 级，请以 `python tools\\rquote_page_check.py --task %s`'
                  ' 与 `python tools\\verify_candidates.py --all --task %s` 为准。' % (task, task))
            print('   （按文档类别选仪器 · A-39：**没有引文面的册子不算缺陷**）')
            return 0
        sys.exit('🔴 未匹配到任何引文型附属文件（%s/%s）——**空集不得当零问题放行**；'
                 '若本册附属层另有目录/命名，请用 `--layer`／`--pattern` 指定'
                 '（本册附属层实扫：文件 %d 个、引文面 %d 处）' % (layer, pat, n_file, n_quote))
    global POOL
    POOL = load_pool(task, a.notes_glob)
    if not POOL:
        sys.exit('🔴 候选池「原文（逐字）」加载为空（%s/candidates/%s）——'
                 '**空集不得当零问题放行**（否则派生链核对面缺失，全部引文会被误判未命中）；'
                 '若本册池文件另有命名，请用 `--notes-glob` 指定' % (task, a.notes_glob))

    rows = []
    for f in files:
        get = {}
        for idx, ln in enumerate(io.open(f, encoding='utf-8', errors='replace').read().splitlines(), 1):
            anchors = []
            for m in ANCHOR.finditer(ln):
                for bk, pg in parse_refs(m.group(0)):    # A-48：块内多引用逐个成对
                    anchors.append((m.start(), bk, pg))
            if not anchors:
                continue
            for (s, e, txt) in runs_on_line(ln):
                if len(norm(txt)) < 8:
                    continue
                after = [(p, bk, pg) for (p, bk, pg) in anchors if p >= e]
                cands = after if after else []
                near = [x for x in cands if x[0] - e <= 120] or cands[:1]
                if not near:
                    continue
                _, bk, pages = near[0]
                if not get.get(bk):
                    get[bk] = load_pages(task, bk)
                # ---- A-49（2026-09-13 由三名独立判官 F／G2／G3 同型指出）----
                #   旧实现把"引文↔锚"按**位置启发式**配对（取引文后第一个锚），铁证＝**同一段引文两次被配到不同锚**
                #   （判官 G3：15-2 配 sulin p187 盖度 0.06；17-1 配 bark p318 最佳窗口 bark p308–310 盖度 0.69），
                #   而它的正确锚 `【Barkley 第14章, PDF p309-310】` **本来就写在同一行内**。
                #   正解＝**判定用该行全部锚的 (书,页) 并集**（本仪器问的是"这条引文在这行声明的来源里有没有原文"，
                #   不是"它属于哪一个锚"——后者是判官的定位工作）。定位线索另存 `near_anchor`。
                line_bys = {}
                for (_pos, _bk, _pg) in anchors:
                    line_bys.setdefault(_bk, set()).update(_pg)
                srcs = {p: get[bk](p) for p in sorted(line_bys.get(bk, set()))}
                q = norm(txt)
                segs = segments(txt) or ([q] if len(q) >= 8 else [])
                # ---- 判态（v2 · 依 2026-09-13 独立判官 C 必修 #1：**加跨页拼接＋输出 match_mode**）----
                # 归一化已含全半角括号/引号族/空白/markdown 强调符（judge C 举例 "（piracetam）vs (piracetam)" 属此）；
                # 关键修正是**跨页**：引文常跨 pN／pN+1，单页子串匹配必然假未命中（实测 21/134 由此解释）。
                state, hitp, ratio, where, mode = '未命中', None, 0.0, None, None
                hit_span = None
                pool_hit = bool(segs) and all(s in POOL for s in segs)
                p0 = min(pages)

                def allin(ps, bk_=None):
                    """窗口内判定（三种模式，任一成立即算命中）：
                    ① 拼接连续命中；② **分段归页命中**（每段落在窗口内某一页即可）——
                       A-47（判官 G2 报出）：引文常**在页界处被页眉/页脚截断**，此时"整串连续"必假；
                    ③ 页界重叠命中（前页尾 N 字 ＋ 后页首 N 字，容忍页眉插入）。
                    `bk_` 省略时用定位锚所属书（**兼容旧调用**）。
                    """
                    b_ = bk_ or bk
                    txts = [get[b_](x) or '' for x in ps]
                    txt = ''.join(txts)
                    if txt and segs and all(s in txt for s in segs):
                        return True
                    if segs and all(any(s in t for t in txts if t) for s in segs):
                        return True
                    if len(txts) >= 2 and segs:
                        for a in txts:
                            for b in txts:
                                if a is b or not a or not b:
                                    continue
                                for n in (40, 80, 160):
                                    if all(s in (a[-n:] + b[:n]) for s in segs):
                                        return True
                    return False

                # 逐书确保已装载页加载器（`get` 以书为键；A-49 后判定要遍历该行**所有**书）
                for _b2 in line_bys:
                    if _b2 not in get:
                        get[_b2] = load_pages(task, _b2)
                # A-49：**判定用该行全部锚的 (书,页) 并集**（逐书分别试）
                hit_by = None
                for _b2, _ps in sorted(line_bys.items()):
                    if allin(sorted(_ps), _b2):
                        hit_by = (_b2, sorted(_ps))
                        break

                if not segs:
                    state, mode = '片段过短', 'n/a'
                elif hit_by:
                    state, hitp, ratio, where = '逐字命中(源页)', (min(hit_by[1]) if hit_by[1] else None), 1.0, 'OCR'
                    # ⚠ match_mode 必须是**有界类别**（A-42：分栏要可用）；页区间另存入 hit_span 字段，
                    #   否则分栏会炸成数百类（本批实测：把区间拼进 mode 后出现 >300 种取值）。
                    mode = '行内锚并集'
                    hit_span = '%s p%d–p%d' % (hit_by[0], min(hit_by[1]), max(hit_by[1])) if len(hit_by[1]) > 1 \
                        else '%s p%d' % (hit_by[0], min(hit_by[1]))
                elif pool_hit:
                    state, hitp, ratio, where, mode = '逐字命中(池条目)', None, 1.0, 'POOL', '池条目'
                else:
                    # 全库（同书）单页唯一命中且在邻域内 ⇒ **锚偏**（页号错 N）
                    nbr = None
                    for d in range(1, 9):
                        for pp in (p0 + d, p0 - d):
                            if allin([pp]):
                                nbr = (pp, pp - p0)
                                break
                        if nbr:
                            break
                    if nbr:
                        state, hitp, ratio, where = '邻页命中(锚偏)', nbr[0], 1.0, 'OCR'
                        mode = '单页 p{}（差 {:+d}）'.format(nbr[0], nbr[1])
                    elif all(v is None for v in srcs.values()) and not pool_hit:
                        state, mode = '无法核', None
                    else:
                        for pp, sv in srcs.items():
                            if not sv:
                                continue
                            r = sum(lcs_len(s, sv) for s in segs) / max(1, sum(len(s) for s in segs))
                            if r > ratio:
                                ratio, hitp = r, pp
                        state = '近似' if ratio >= 0.85 else '未命中'
                marked = ('逐字' in ln[max(0, s - 20):s])
                rows.append(dict(file=os.path.basename(f), line=idx, book=bk, pages=pages,
                                 quote=txt[:120], state=state, matched_page=hitp,
                                 via=where, ratio=round(ratio, 3), marked_verbatim=marked,
                                 match_mode=mode, hit_span=hit_span, text=ln.strip()[:160]))

    cnt = {}
    for r in rows:
        cnt[r['state']] = cnt.get(r['state'], 0) + 1
    per_file = {}
    for r in rows:
        d = per_file.setdefault(r['file'], {})
        d[r['state']] = d.get(r['state'], 0) + 1
    marked_bad = [r for r in rows if r['marked_verbatim'] and r['state'] == '未命中']
    via = {}
    for r in rows:
        k = r.get('via') or '—'
        via[k] = via.get(k, 0) + 1
    mmc = {}
    for r in rows:
        k = r.get('match_mode') or '—'
        mmc[k] = mmc.get(k, 0) + 1
    out = {'schema': 'layer-quote-resource-check-v2', 'task': task,
           '_口径': {
               '对象': '引文型附属文件（%s）——其法定格式即"逐字引文＋页锚"，故不适用 defense3 的"非 R 段引号＝冒充"规则',
               '判据': '引号内文本按省略号分段、归一化后，**逐段**是否为（a）所指页 OCR 源文 或（b）**相邻页拼接**'
                       ' 或（c）候选池「原文（逐字）」的子串；三类皆记为"逐字命中"，用 `match_mode` 区分',
               '归一化': '去空白、去中英标点（**含全/半角括号与引号族**）、去 markdown 强调符（`*`/`_`/`` ` ``）',
               '分段': '按省略号 `…`／`……`／（略）切分；每段归一化后 ≥8 字才参与判定；无段可判＝「片段过短」（单列）',
               '跨页窗口': 'p／p+1（`跨页 p+p+1`）与 p−1／p（`跨页 p-1+p`）——引文常跨页，**单页匹配必然假未命中**',
               '锚偏判定': '若整句在**单个邻页** p±1…p±8 内成立而所指页不成立 ⇒ `邻页命中(锚偏)`（性质＝页号记错，非无源）',
               '锚单位': '锚中的 PDF 页号＝扫描件页号＝`ocr/<book>_pNNNN.txt` 的文件号（与附属文件自述口径一致）',
               '双源理由': '附属文件由候选池装配而来（防线2 派生链）；只对 OCR 直测会**假未命中**（引文经省略号重组／'
                           '带作者补注），故必须以池条目为并列核对面',
               '全量分栏纪律': '**报告任何一类计数时必须同时给出完整分栏**（旧版只报"610 命中／134 未命中"，'
                               '漏列"近似 15／无法核 12／片段过短"⇒ 被独立判官判为"计数不自洽"，属呈现缺陷）'},
           'pool_chars': len(POOL), 'files': per_file, 'counts': cnt, 'via': via,
           'total_quotes': len(rows),
           'partition_check': {'sum_of_counts': sum(cnt.values()), 'total': len(rows),
                               'consistent': sum(cnt.values()) == len(rows)},
           'marked_verbatim_but_missed': len(marked_bad),
           'match_mode_counts': mmc,
           'rows': rows}
    outp = a.out or os.path.join(ROOT, '.work', task, 'layer-quote-check.json')
    io.open(outp, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')

    print('=== 引文型附属文件 · 引文回源核验 v2（%s）===' % task)
    print('  文件 %d 个 ｜ 引文 %d 条' % (len(files), len(rows)))
    print('  **完整分栏（合计必须 = %d）**：%s ⇒ 合计 %d（%s）'
          % (len(rows), '／'.join('%s=%d' % kv for kv in sorted(cnt.items())), sum(cnt.values()),
             '自洽' if sum(cnt.values()) == len(rows) else '**不自洽**'))
    print('  match_mode：%s' % '／'.join('%s=%d' % kv for kv in sorted(mmc.items())))
    print('  核对面来源：%s ｜ 池语料 %d 字' % ('／'.join('%s=%d' % kv for kv in sorted(via.items())), len(POOL)))
    print('  标「逐字」但未命中：**%d** 条（最高优先）' % len(marked_bad))
    for fn, d in per_file.items():
        print('   %-26s %s' % (fn, '／'.join('%s=%d' % kv for kv in sorted(d.items()))))
    if a.detail and (cnt.get('未命中') or cnt.get('近似')):
        print('  -- 未命中/近似样本 --')
        for r in rows:
            if r['state'] in ('未命中', '近似'):
                print('   %s L%s [%s] %s ｜ 引文：%s' % (r['state'], r['line'], r['book'],
                                                       r['pages'], r['quote'][:80]))
    print('  落盘：%s' % outp)
    print('  ⚠ 判据边界：未命中一律按"🔴 候选"交语义判官终裁，不直接判缺陷。')


if __name__ == '__main__':
    main()
