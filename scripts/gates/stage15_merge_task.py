# -*- coding: utf-8 -*-
r"""stage15_merge_task.py —— 阶段1.5「去重合并 + 页锚三态 + 归属裁断」（**任务通用版**）

为什么另写一份（而不是改 `stage15_merge.py`）：后者对 <task> **写死了三处**
（`notes_T*.md` 的波段名、`--- [bark PDF p84] ---` 的页标记、`bark p84` 形态的锚、
`BAND_LAYER` 波段→专业层映射）——**换书即报废**（避坑手册 A-01 同族）。
本脚本把这三处外置为**任务配置**：`.work/<task>/bookspec-<task>.json`。

**复用**（不复制）`tools\verify_candidates.py` 的口径函数：`ENTRY/QUOTE/ANCHOR/SPLIT_ENTRY`、
`norm/clean_src/split_pages/set_pagemark` —— 保证阶段1.5 与机器校验**同一把尺子**。

权威依据（逐条抄自手册 `distillation-director` V4.6）：
  · §3 阶段1.5：「去重合并→verified.md；盲测机器词表初判→needs_llm 子集交 judge 结构化复核
     （判态：误路由/无锚/邻族抢单=🔴）」
  · §7 合并/矩阵脚本机器校验自检单（V4.1）三项：① 锚归一化 ② 格式多容错 ③ 引文命中三态
  · 避坑手册 A-35：重复页标记必须**合并而非覆盖**并登记

用法（输出路径显式传参 —— 手册 §17 V-11 写盘禁令）：
  python tools\stage15_merge_task.py --task <task>
  python tools\stage15_merge_task.py --task <task> --out-dir <目录>
退出码：0 = verified.md 已生成且零🔴；1 = 有🔴（逐条列明）
"""
import argparse
import difflib
import glob
import io
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os as _dsp_os, sys as _dsp_sys          # 可移植根目录：单一来源 tools\_paths.py
_dsp_sys.path.insert(0, _dsp_os.path.dirname(_dsp_os.path.abspath(__file__)))
from _paths import ROOT  # noqa: E402
import _bandid as BID  # noqa: E402  ← 波段 id 语法唯一来源（A-132）
# 锚形态：本册写作 `s137` / `s137-138` / `s137、s140`（**无书代号** —— 单册任务）
ANCHOR_S = re.compile(r's\s*(\d{1,4})\s*(?:[-–—~至]\s*s?\s*(\d{1,4}))?', re.I)
TRANSCRIPT_RE = re.compile(r'^-\s*转述：(.+)$', re.M)


def load_spec(task):
    p = os.path.join(ROOT, '.work', task, 'bookspec-%s.json' % task)
    if not os.path.exists(p):
        raise SystemExit('🔴 缺任务配置：%s（BAND_LAYER／页标记形态／技能族应从配置读，不得写死）' % p)
    return json.load(io.open(p, encoding='utf-8')), p


def load_entries(cand_dir, bands):
    """② 格式多容错：`[技能=S1]`／`[技能=待定]`／带尾部说明 —— 一律归一化为结构字段。"""
    rows, fatal = [], []
    for band in bands:
        npath = os.path.join(cand_dir, 'notes_%s.md' % band)
        if not os.path.exists(npath):
            fatal.append('缺波段笔记：notes_%s.md' % band)
            continue
        txt = io.open(npath, encoding='utf-8').read()
        blocks = BID.split_blocks(txt)      # ← 与 ENTRY/SPLIT 同源（A-132：语法只有一份）
        if not blocks:
            fatal.append('%s 切块为空（工装缺陷，不得视为通过）' % os.path.basename(npath))
            continue
        for b in blocks:
            head = b.split('\n')[0]
            m = VC.ENTRY.match(head)
            if not m:
                fatal.append('格式行无法解析：%s' % head)
                continue
            a = VC.ANCHOR.search(b)
            q = VC.QUOTE.search(b)
            tr = TRANSCRIPT_RE.search(b)
            rows.append(dict(
                eid='%s-%s' % (m.group(1), m.group(2)),
                band=band, typ=m.group(3), skill_local=m.group(4).strip(),
                tail=(m.group(5) or '').strip(),
                anchor_raw=(a.group(1).strip() if a else ''),
                quote=(q.group(1) if q else ''),
                trans=(tr.group(1).strip() if tr else ''),
            ))
    return rows, fatal


def build_page_index(src_path):
    """按页标记切页 → 页索引 {页号: norm文本}。重复页标记**合并**（A-35），并登记重复键。"""
    raw = io.open(src_path, encoding='utf-8').read()
    pages = VC.split_pages(raw)                  # [(页标识, norm文本)]
    idx, order, dup = {}, [], []
    for mark, txt in pages:
        try:
            key = int(str(mark).strip())
        except Exception:
            key = str(mark).strip()
        txt_m = VC.norm_match(txt)               # ← 与 verify_candidates 同口径（标点族折叠）
        if key in idx:
            idx[key] = idx[key] + '\n' + txt_m
            dup.append(key)
        else:
            idx[key] = txt_m
        order.append((key, txt_m))
    return VC.norm_match(VC.clean_src(raw)), idx, order, dup


def quote_state(e, idx, order, src_norm):
    """③ 引文命中三态：OK / MISANCHOR（错锚）/ NOANCHOR（源文无此引文）＋ CROSS 观测。

    ⚠ 口径统一（2026-09-17 实测抓到）：首版对本函数仍用 `VC.norm`（只折空白），
      而 `verify_candidates` 已升级为 `VC.norm_match`（折空白＋**标点族**）
      ⇒ 同一批引文在**阶段1.5 判"源文找不到"、在机器校验判"命中"**（两台仪器打架，A-04 家族）。
      修法：**一切引文比对统一走 `VC.norm_match`**（含页索引文本）。
    """
    qn = VC.norm_match(e['quote'])
    pages = []
    for m in ANCHOR_S.finditer(e['anchor_raw']):
        p0 = int(m.group(1))
        p1 = int(m.group(2)) if m.group(2) else p0
        pages += list(range(min(p0, p1), max(p0, p1) + 1))
    if not pages:
        return dict(state='NOANCHOR_SPEC', declared=[], actual=[],
                    detail='锚行无法归一化：%s' % e['anchor_raw'])
    decl_text = ''.join(idx.get(p, '') for p in pages)
    if qn and qn in decl_text:
        return dict(state='OK', declared=pages, actual=pages, detail='命中声明锚页')
    hits = [k for k, txt in idx.items() if qn and qn in txt]
    if hits:
        return dict(state='MISANCHOR', declared=pages, actual=hits,
                    detail='错锚：引文实际在 s%s，声明为 s%s'
                           % ('/s'.join(str(h) for h in hits), '/s'.join(str(p) for p in pages)))
    if qn and qn in src_norm:
        # ⚠ 2026-09-17 修（本册实测 · A-41／A-47 家族「比对窗口必须穷举命中模式」）：
        #   旧实现用**固定 16 字前缀／后缀**在"单页文本"里找起始页与结束页。当跨页引文的
        #   前 16 字（或后 16 字）**本身就横跨页边界**时，两侧都落不进任何单页 ⇒ si／ei 之一为 None
        #   ⇒ 被误判成 `MISANCHOR_CROSS`（🔴 错锚）。实测本册 4 条**全部**是这种**假红**
        #   （例：B-001 起于 p38 末、续到 p39，声明 `s38` 完全正确；I-020 起于 p179 末「在相当」、
        #    续到 p180，声明 `s180` 亦合法）。
        #   ⚠ 中间版（最长前缀/最长后缀）**仍有洞**：B-059 的真实结束页后缀只命中 2 字，
        #     被 p222 上 4 字的**杂散短匹配**盖过 ⇒ 又报一条假红。**启发式一律不要。**
        #   定版修法（**精确、无启发式**）：把各页归一化文本**按页序拼接**，在拼接串里 `find` 引文，
        #     再用前缀长度和把起止偏移映射回页号。只有在**拼接串里真找得到**时才给结论。
        concat = ''.join(t for _p, t in order)
        pos = concat.find(qn)
        if pos < 0:
            return dict(state='MISANCHOR_CROSS', declared=pages, actual=[],
                        detail='跨页引文：逐页拼接后仍找不到（页内被页眉/页标记截断？）')
        bounds, acc = [], 0
        for _p, t in order:
            bounds.append((acc, acc + len(t), _p))
            acc += len(t)

        def _page_at(off):
            for lo, hi, pp in bounds:
                if lo <= off < hi:
                    return pp
            return order[-1][0]

        sp = _page_at(pos)
        ep = _page_at(pos + len(qn) - 1)
        span = [sp] if sp == ep else [sp, ep]
        idx_of = {p: i for i, (p, _t) in enumerate(order)}
        adjacent = (abs(idx_of.get(ep, 0) - idx_of.get(sp, 0)) <= 1
                    and any(x in pages for x in span))
        return dict(state='CROSS_OK' if adjacent else 'MISANCHOR_CROSS', declared=pages,
                    actual=span,
                    detail='跨页引文：实际跨 %s（精确拼接定位，偏移 %d；%s）'
                           % ('→'.join('s%s' % s for s in span), pos,
                              '与声明锚页相邻，成立' if adjacent else '与声明锚页不符'))
    return dict(state='NOANCHOR', declared=pages, actual=[], detail='源文中找不到该引文')


def dedup(entries):
    """去重：D1 引文归一化后完全相同；D2 近重复（difflib ratio ≥0.90 且长度相近）。"""
    exact = {}
    for e in entries:
        if e['quote']:
            exact.setdefault(VC.norm(e['quote']), []).append(e['eid'])
    exact_dups = {k: v for k, v in exact.items() if len(v) > 1}
    keys = [e for e in entries if e['quote']]
    near = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = VC.norm(keys[i]['quote']), VC.norm(keys[j]['quote'])
            if a == b or not a or not b:
                continue
            if abs(len(a) - len(b)) > max(10, int(0.25 * min(len(a), len(b)))):
                continue
            r = difflib.SequenceMatcher(None, a, b).ratio()
            if r >= 0.90:
                near.append(dict(a=keys[i]['eid'], b=keys[j]['eid'], ratio=round(r, 3)))
    return exact_dups, near


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--out-dir', default=None)
    a = ap.parse_args()

    spec, spec_p = load_spec(a.task)
    work = os.path.join(ROOT, '.work', a.task)
    cand_dir = os.path.join(work, 'candidates')
    out_dir = a.out_dir or work
    os.makedirs(out_dir, exist_ok=True)

    # 页标记形态**探测**（格式类判据须先做形态普查 —— A-29/A-30）
    # ⚠ 2026-09-17 修（换书实测 · A-69／A-74 家族，与 `rquote_page_check.py` 同一病根）：
    #   旧版 ① 只认配置键 `pagemark_form`（另一册写的是 `pagemark`）；
    #        ② 探测分支**只有 equals／dash，没有 hline** ⇒ 用 `pdf_to_text.py` 产物的册
    #           会被判成 `dash`，页索引为空（或错位）而**判据全歪**。
    #   修法：键名两种都认；`auto` 一律交给 `verify_candidates.detect_pagemark()`（**唯一权威探测函数**），
    #         不在本件另写一份探测逻辑（A-72 变体：同一判据写两遍＝改一处等于没改）。
    form = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
    src_name = spec.get('src')
    if not src_name:
        print('🔴 本册配置缺 `src`：%s —— 源文件名必须来自配置，拒绝运行（A-69／A-74）' % spec_p)
        return 1
    src = os.path.join(work, src_name)
    if form == 'auto':
        form = VC.detect_pagemark(src)
    VC.set_pagemark(form)

    bands = spec['bands']
    BAND_SKILL = {b['band']: b for b in bands}
    print('任务 %s ｜ 配置 %s ｜ 页标记形态 %s ｜ 源 %s' % (a.task, os.path.basename(spec_p), form, src))

    entries, fatal = load_entries(cand_dir, [b['band'] for b in bands])
    if fatal:
        for f in fatal:
            print('🔴 %s' % f)
        return 1
    src_norm, idx, order, dup_keys = build_page_index(src)
    if not idx:
        print('🔴 页索引为空（页标记未命中）⇒ 判据失效，不得视为通过')
        return 1
    print('页索引：%d 页 ｜ 重复页标记 %d 个 %s' % (len(idx), len(dup_keys), dup_keys[:10]))

    for e in entries:
        e['state'] = quote_state(e, idx, order, src_norm)
        bs = BAND_SKILL.get(e['band'], {})
        e['layer'] = dict(skill_family=bs.get('family', '?'), skill_name=bs.get('name', '?'),
                          skill_slug=bs.get('slug', '?'))

    exact_dups, near = dedup(entries)
    near_ids = {d['a'] for d in near} | {d['b'] for d in near}
    for e in entries:
        reasons, adj = [], []
        st = e['state']['state']
        if st == 'NOANCHOR':
            reasons.append('无锚：源文中找不到该引文')
        if st in ('MISANCHOR', 'MISANCHOR_CROSS'):
            reasons.append('错锚：%s' % e['state']['detail'])
        if st == 'NOANCHOR_SPEC':
            reasons.append('锚行不可归一化')
        if e['skill_local'] in ('待定', '', '待定；'):
            adj.append('局部标签「待定」⇒ 按阶段0『波段→技能』映射归 %s（机器裁断）' % e['layer']['skill_name'])
        if e['eid'] in near_ids:
            reasons.append('近重复候选')
        e['needs_llm'] = reasons
        e['adjudicated'] = adj

    st_count, band_count, fam_count, local_count = {}, {}, {}, {}
    for e in entries:
        st_count[e['state']['state']] = st_count.get(e['state']['state'], 0) + 1
        band_count[e['band']] = band_count.get(e['band'], 0) + 1
        fam_count[e['layer']['skill_family']] = fam_count.get(e['layer']['skill_family'], 0) + 1
        local_count[e['skill_local']] = local_count.get(e['skill_local'], 0) + 1
    hard = [e for e in entries if e['state']['state'] in
            ('NOANCHOR', 'MISANCHOR', 'MISANCHOR_CROSS', 'NOANCHOR_SPEC')]

    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    report = dict(generated_at=ts, task=a.task, spec=os.path.basename(spec_p),
                  pagemark_form=form, src=os.path.basename(src),
                  source_pages=len(idx), dup_page_marks=dup_keys,
                  total=len(entries), state_count=st_count, band_count=band_count,
                  family_count=fam_count, local_skill_labels=local_count,
                  exact_dup_groups=len(exact_dups),
                  exact_dup_entries=sum(len(v) for v in exact_dups.values()),
                  near_dup_pairs=len(near), hard_red=len(hard),
                  needs_llm=sum(1 for e in entries if e['needs_llm']),
                  adjudicated=sum(1 for e in entries if e['adjudicated']),
                  exact_dups=exact_dups, near_dups=near,
                  hard_red_list=[dict(eid=e['eid'], state=e['state']['state'],
                                      detail=e['state']['detail']) for e in hard])
    io.open(os.path.join(out_dir, 'stage15-report.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    # ---- verified.md ----
    L = []
    A = L.append
    A('# verified.md —— 阶段1.5 候选池（去重合并 · 页锚三态 · 归属裁断）')
    A('')
    A('> 任务 slug：`%s` ｜ 手册 `distillation-director` **V4.6** ｜ 生成时刻：**%s**' % (a.task, ts))
    A('> 依据：§3 阶段1.5 ＋ §7「合并/矩阵脚本机器校验自检单」三项 ｜ 工装：`tools\\stage15_merge_task.py`（任务通用版）')
    A('> 源文本：`%s`（页标记形态 `%s`，**%d 页**）｜ 重复页标记 %d 个（A-35 已合并非覆盖）'
      % (os.path.basename(src), form, len(idx), len(dup_keys)))
    A('> **本文件是阶段2 构造层的直接输入**：每条含 id／类型／归属／锚／引文三态／逐字原文／转述。')
    A('')
    A('## 一、归属口径（阶段0 §五 技能划分）')
    A('')
    A('| 波段 | 章节范围 | → 技能族 | 技能名 |')
    A('|---|---|---|---|')
    for b in bands:
        A('| %s | %s | %s | `%s` |' % (b['band'], b.get('chapters', ''), b['family'], b['slug']))
    A('')
    A('## 二、机器校验自检单（手册 §7 · V4.1 三项）')
    A('')
    A('### ① 锚归一化')
    A('')
    A('锚行写作 `s137`（**页号**；单册任务无书代号），区间写作 `s137-138`；'
      '归一化为页号集合后逐页取文本。无法归一化的锚单列为 `NOANCHOR_SPEC`。')
    A('')
    A('### ② 格式多容错')
    A('')
    A('`[技能=S1]`／`[技能=待定]`／`[技能=S5] 带尾部说明` 三种形态**均按同一结构解析**，解析失败即 fatal、不静默跳过。')
    A('')
    A('### ③ 引文命中三态（含跨页观测）')
    A('')
    A('| 态 | 含义 | 判态 |')
    A('|---|---|---|')
    A('| `OK` | 引文完整落在声明锚页内 | ✔ |')
    A('| `CROSS_OK` | 跨页且实际页与声明锚页**相邻**（提取器已正确跳过页锚行） | ✔ 观测项 |')
    A('| `MISANCHOR` | 源文中能找到，但**不在**声明页 | 🔴 错锚 |')
    A('| `MISANCHOR_CROSS` | 跨页引文，但实际页**与声明锚页不符** | 🔴 错锚 |')
    A('| `NOANCHOR` | 源文中**根本找不到**该引文 | 🔴 无锚 |')
    A('| `NOANCHOR_SPEC` | 锚行无法归一化 | 🔴 |')
    A('')
    A('## 三、统计')
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 条目总数 | **%d** |' % len(entries))
    A('| 各波段 | %s |' % '／'.join('%s %d' % (k, band_count[k]) for k in sorted(band_count)))
    A('| 各技能族 | %s |' % '／'.join('%s %d' % (k, fam_count[k]) for k in sorted(fam_count)))
    A('| 页锚三态 | %s |' % '／'.join('%s %d' % (k, st_count[k]) for k in sorted(st_count)))
    A('| 完全相同引文组 | %d 组（涉及 %d 条） |' % (len(exact_dups), sum(len(v) for v in exact_dups.values())))
    A('| 近重复对（ratio≥0.90） | %d 对 |' % len(near))
    A('| 🔴 硬项（无锚／错锚） | **%d** |' % len(hard))
    A('| needs_llm 子集（交 judge） | **%d** 条 |' % report['needs_llm'])
    A('| 波段局部技能标签分布 | %s |' % '／'.join('%s %d' % (k, local_count[k]) for k in sorted(local_count)))
    A('')
    if hard:
        A('## 三点五、🔴 硬项清单（无锚／错锚 —— 必须先修）')
        A('')
        A('| 条目 | 态 | 明细 |')
        A('|---|---|---|')
        for e in hard:
            A('| %s | %s | %s |' % (e['eid'], e['state']['state'], e['state']['detail']))
        A('')
    A('## 四、候选条目（按波段分组）')
    A('')
    for band in sorted(band_count):
        bs = BAND_SKILL[band]
        A('### 波段 %s → `%s`（%s）' % (band, bs['slug'], bs['name']))
        A('')
        for e in [x for x in entries if x['band'] == band]:
            A('### %s  [%s] [技能=%s]' % (e['eid'], e['typ'], e['skill_local'] or '待定'))
            A('- 锚：%s' % (e['anchor_raw'] or '（缺）'))
            A('- 引文态：`%s`（%s）' % (e['state']['state'], e['state']['detail']))
            A('- 原文（逐字）：「%s」' % e['quote'])
            A('- 转述：%s' % (e['trans'] or '（缺）'))
            A('- 归属：`%s`' % e['layer']['skill_slug'])
            if e['needs_llm']:
                A('- needs_llm：%s' % '；'.join(e['needs_llm']))
            if e['adjudicated']:
                A('- 机器裁断：%s' % '；'.join(e['adjudicated']))
            A('')
    io.open(os.path.join(out_dir, 'verified.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')

    print('-' * 74)
    print('条目 %d ｜ 三态 %s' % (len(entries), st_count))
    print('🔴 硬项 %d ｜ needs_llm %d ｜ 完全重复组 %d ｜ 近重复对 %d'
          % (len(hard), report['needs_llm'], len(exact_dups), len(near)))
    print('已写 %s' % os.path.join(out_dir, 'verified.md'))
    print('已写 %s' % os.path.join(out_dir, 'stage15-report.json'))
    return 1 if hard else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
