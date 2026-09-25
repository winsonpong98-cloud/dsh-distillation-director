# -*- coding: utf-8 -*-
r"""layer_quotes_gate.py —— **引文型附属文件零问题闸（通用版 · 一闸通吃）**

## 为什么另写这一件（自伤/缺口登记 · 2026-09-17）
手册 §22.4 声称「执行单第 37 项…**供后续每本书继承**」，但现实是：

| 册 | 用的闸 | 问题 |
|---|---|---|
| 教育线（`<task>`） | `gate_layer_quotes.py`（R1–R8） | **锚形态/目录/文件名/页源全部写死教育线**；`ANCHOR`／`BOOKS`／`ocr\%s_p%04d.txt` ⇒ 换册**空集拒跑** |
| `<task>` | `gate_layer_quotes_manias.py`（R1–R5） | **为该册另写一座闸** |
| `<task>` | 任务本地 `verify_s4_layer_quotes.py`（只覆盖 S4）＋ 事后 `rquote --include-aux` | **同样是手搓替身** |

⇒ **"每本书各造一座闸"** = 仪器没参数化；且 `gate_checklist` 的官方项数常量落后（36 vs 模板 37），
**第 37 项"信息性不拦"** ⇒ 缺口**没有任何闸看得见**。

## 本件做什么
**从"当册配置"读取锚形态／页源模型／引文取法**，对**任意册**跑同一套 R1–R8：

```
R1 锚可解析：每个锚块/锚必须解析出 ≥1 个 (源, 页)；不可解析数 ≤ 配置白名单上限且逐条打印
R2 引文全覆盖：每条引文必须有状态（不得留"未分类"）——三态＋近似＋邻页
R3 分栏自洽：各栏之和 == 引文总数（A-42）
R4 归一化族齐全：对"同义变体"（全/半角括号、引号族、空白、markdown 强调符、连字符族）
                断言归一后**同值**（A-04/A-39 家族：尺子只认一种写法 ⇒ 恒假红）
R5 未命中零未处置：每条未命中必须能归入**已声明类别**（短片段／无锚／已登记边界／待复核）
R6 判据不依赖"引文→锚"位置配对：判定用**该行全部锚的 (源,页) 并集**（A-49）
R7 空集拒跑：解析 0 条引文或 0 个锚 ⇒ rc=1（A-37/A-73）
R8 产物自带 schema 版本与**口径全字段**（计数不可跨版本比较，A-46）
```

## 复用（不另写第二份权威 · A-72）
· `verify_candidates`：`norm`／`norm_match`／`detect_pagemark`／`set_pagemark`／`clean_src`／`split_pages`／池条目正则
· `stage15_merge_task.build_page_index`：**单文件＋页标记**分页（唯一权威）
· `rquote_page_check` 的**判定语义**（同族），本件只做"按配置选页源 + R1–R8 汇总"

## 用法
    python tools\layer_quotes_gate.py --task <slug> [--config <json>] [--strict] [--report <md>] [--json-out <json>]
· 配置默认自动发现：`.work\<slug>\layer-quotes-<slug>.json`；缺 ⇒ **rc=1**（空集拒跑，**不回落任何册**）
· 模板：`tools\layer-quotes-config.template.json`

退出码：0 = R1–R8 全过；1 = 有未过项（含"无配置"/"空集"）。
"""
import argparse
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

SCHEMA = 'layer-quotes-gate'
SCHEMA_VERSION = '1.0.0'
TEMPLATE = os.path.join(HERE, 'layer-quotes-config.template.json')


def load_config(task, path=None):
    """配置：**零册别兜底**——找不到就拒跑（不回落任何册的默认值）。"""
    cands = [path] if path else [
        os.path.join(ROOT, '.work', task, 'layer-quotes-%s.json' % task),
    ]
    for c in cands:
        if c and os.path.isfile(c):
            return json.load(io.open(c, encoding='utf-8')), c
    return None, (cands[0] if cands else '')


def get_norm(VC):
    """归一化口径：**优先复用权威 STRIP 族**（`verify_layer_quotes.norm`：含引号族／全半角括号／
    空白／**markdown 强调符 `*` `_`**）——手册 R4 明写"强调符必须在归一化族内"。
    退回 `verify_candidates.norm_match`（不含 `*`）会**漏掉所有"引号内含 `**` 强调"的引文**（实测真发生）。

    ⚠ 为什么必须统一：两套归一化不一致 ⇒ 同一句话在两把尺子下一真一假（A-04／A-39 家族）。
    """
    try:
        import verify_layer_quotes as V
        return V.norm, 'verify_layer_quotes.norm（STRIP 族：引号/全半角括号/空白/强调符 * _）'
    except Exception:
        return VC.norm_match, 'verify_candidates.norm_match（**缺强调符族**，属降级）'


def norm_variants(N):
    """R4 归一化族：同义变体必须归一为同值（引号族／空白／全半角括号／强调符／连字符）。"""
    cases = {
        '引号族': ['「a b」c', '“a b”c', '『a b』c', '"a b"c'],
        '空白': ['a b c', 'a  b c', 'ab c', 'a\u3000b c'],
        '全半角括号': ['x（y）z', 'x(y)z'],
        '强调符': ['a**b**c', 'a b c', 'a__b__c'],
    }
    bad = {k: v for k, v in cases.items() if len({N(x) for x in v}) != 1}
    return not bad, bad


def pages_loader(cfg, task, VC, M):
    """按 `pages.mode` 返回 (页映射 dict, 说明, 页数)。

    · file_per_page          —— 每页一个文件（教育线：`ocr/<book>_pNNNN.txt`）
    · single_file_pagemarks  —— 单文件＋页标记（债券/manias：`book_text.md`）
    """
    p = cfg['pages']
    mode = p['mode']
    if mode == 'single_file_pagemarks':
        src = os.path.join(ROOT, '.work', task, p['file'])
        if not os.path.isfile(src):
            return None, '源文件不存在：%s' % src, 0
        pm = p.get('pagemark') or 'auto'
        if pm == 'auto':
            pm = VC.detect_pagemark(src)
        VC.set_pagemark(pm)
        _m, idx, order, _d = M.build_page_index(src)
        return idx, '单文件＋页标记（%s；form=%s）' % (os.path.basename(src), pm), len(idx)
    if mode == 'file_per_page':
        d = os.path.join(ROOT, '.work', task, p['dir'])
        pat = p.get('file_pattern', '%s_p%04d.txt')
        idx = {}
        for f in glob.glob(os.path.join(d, pat.replace('%04d', '*').replace('%s', '*'))):
            m = re.search(re.escape(pat).replace('%s', r'(.+?)').replace('%04d', r'(\d+)')
                          .replace('\\.', '.'), os.path.basename(f))
            if not m:
                continue
            book, page = m.group(1), int(m.group(2))
            idx[(book, page)] = VC.norm(VC.clean_src(
                io.open(f, encoding='utf-8', errors='replace').read()))
        return idx, '每页一文件（%s/%s）' % (p['dir'], pat), len(idx)
    return None, '未知 pages.mode：%s' % mode, 0


def page_keys(idx, spec):
    """把锚里的页说明（`322`／`p322`／`p193-194`／`p322, p337`）展开成**候选页号集合**。

    ⚠ 区间必须展开（A-44 同族：只取首页 ⇒ 合法的区间锚被判错锚）。
    """
    nums = [int(x) for x in re.findall(r'\d{1,4}', str(spec or ''))]
    out = set()
    if len(nums) >= 2 and re.search(r'[-–—~至]', str(spec)):
        a, b = nums[0], nums[1]
        if 0 < a <= b <= 5000 and b - a <= 60:
            out.update(range(a, b + 1))
    out.update(n for n in nums if 0 < n <= 5000)
    return out


def resolve_prefix(cfg, src):
    """书别名 → 页文件前缀（教育线形态）。无别名可解 ⇒ None（**并计数上报**）。"""
    for m in cfg.get('book_alias') or []:
        if re.search(m['pat'], src or ''):
            return m['prefix']
    return None


def match_segs(segs, text):
    """分段匹配（A-41／A-47）：引文常写作 `…前段……后段…`（省略号连接两段不连续原文），
    整串在任何单页都找不到 ⇒ 必须**逐段**判定。全部段都落在给定文本内即算命中。"""
    return bool(segs) and all(s in text for s in segs)


def page_text(idx, p):
    """从页映射取文本：兼容 `{页: 文本}` 与 `{(源, 页): 文本}` 两种键形态。"""
    if p in idx:
        return idx[p]
    for k, v in idx.items():
        if isinstance(k, tuple) and k and k[-1] == p:
            return v
    return ''


def load_pool(task, cfg, VC):
    """候选池：id → (逐字引文, 锚页)。支持 id 型池（notes_*.md 的 `### X-001` 条目）。"""
    pool = {}
    for f in sorted(glob.glob(os.path.join(ROOT, '.work', task, cfg['pool_glob']))):
        t = io.open(f, encoding='utf-8', errors='replace').read()
        for b in VC.SPLIT_ENTRY.split(t):
            m = VC.ENTRY.match(b.split('\n')[0])
            if not m:
                continue
            eid = '%s-%s' % (m.group(1), m.group(2))
            q = VC.QUOTE.search(b)
            a = VC.ANCHOR.search(b)
            pages = [int(x) for x in re.findall(r'\d{1,4}',
                     a.group(1))] if a else []
            pool[eid] = dict(quote=(q.group(1) if q else ''), pages=pages)
    return pool


def parse_anchor_items(block, groups, cfg):
    """把一个**锚块**解析成 [(id, page), ...]。

    ⚠ 自伤登记（2026-09-17 · 本册实测抓到）：首版用"一个正则配一个命名组"取锚 ⇒
    对 `（`E-028` s101、`L-009` s9）` 这种**一个括号内多条**的写法**只取到第一条**（E-028），
    于是第二条（L-009）承载的那句引文被判 MISS——**假红**。
    这正是 `rquote_page_check` 早已修过的同一坑（`A-81` 家族：自证口径 ≠ 权威口径）。
    正解：先用 `anchor_regex` 取**块**，再用 `anchor_item_regex` 在块内**逐条**取（块内可多条）。
    """
    item = cfg.get('anchor_item_regex')
    if item:
        return [dict(id=m.group('id'), page=m.group('page'), src=None)
                for m in re.finditer(item, block) if m.group('id')]
    return [dict(id=groups.get('id'), page=groups.get('page'), src=groups.get('src'))]


def scan_quotes(cfg, files, VC):
    """按配置扫"引文行"：返回 ([(文件, 行号, 引文, [(id,页)...]), ...], 不可解析锚行)。

    ⚠ **射程必须按册声明**（A-39「同一把尺子跨文档类别使用 ⇒ 伪影」）：
    附件里的 `「…」` **有两种用途**——① **逐字引文**（后面紧跟它的引用锚）② **路由/触发句**
    （如 `答：「**哪张券是 CTD**」——…（`E-024` s100）`，锚在行尾、引的是技能自己的话）。
    只把 ① 当引文——客观判据＝**引文后紧跟 `quote_context_regex`**（按册配置），
    并可用 `quote_exclude_regex` 排除"引号内容本身就是技能自述"（如以 `**` 开头的加粗短语）。
    配置为 null ⇒ 退回"该行有锚即算"（适用于"法定格式＝每条引文都带锚"的册）。
    """
    aq = re.compile(cfg['anchor_regex'])
    qc = cfg.get('quote_chars') or ['「', '」']
    ctx_re = re.compile(cfg['quote_context_regex']) if cfg.get('quote_context_regex') else None
    exl_re = re.compile(cfg['quote_exclude_regex']) if cfg.get('quote_exclude_regex') else None
    # 射程排除（**自声明**）：引号内是"技能自述的触发句/项目名"（如 `**本件答**「…」`、`用到「…」`）
    #   ⇒ 不是书里的逐字引文。判据＝**引文之前的上下文**（含**上一行**，因续行会跨行）。
    #   被排除的**逐条打印＋计数上限（只许减少不许增长）**，并登记进《口径登记单》。
    scope_ex_re = re.compile(cfg['quote_scope_exclude_regex']) \
        if cfg.get('quote_scope_exclude_regex') else None
    out, unparsed, excluded = [], [], []
    prev_ln = ''
    hdr_re = re.compile(cfg['file_header_book_regex']) if cfg.get('file_header_book_regex') else None
    pairing = cfg.get('pairing', 'line')
    for f in files:
        prev_ln = ''
        _txt = io.open(f, encoding='utf-8', errors='replace').read()
        file_src = None
        if hdr_re:
            hm = hdr_re.search(_txt)
            file_src = hm.group(1).strip() if hm else None
        # `pairing=block`：按空行分隔的**段落块**收集引文与锚（教育线形态：引文在段中、锚在段末）
        if pairing == 'block':
            for blk in re.finditer(r'(?:^|\n\n)((?:[^\n].*\n?)*?)(?=\n\n|\Z)', _txt, re.S):
                seg = blk.group(1)
                if '「' not in seg:
                    continue
                base = _txt[:blk.start(1)].count('\n') + 1
                anchors = []
                for bm in aq.finditer(seg):
                    for it in parse_anchor_items(bm.group(0), bm.groupdict(), cfg):
                        if not it.get('src') and file_src:
                            it['src'] = file_src
                        anchors.append(it)
                if not anchors:
                    if cfg.get('strict_anchor_on_quote_line'):
                        unparsed.append((os.path.relpath(f, ROOT), base))
                    continue
                for m in re.finditer(r'%s([^%s]{4,400})%s' % (qc[0], qc[1], qc[1]), seg):
                    if ctx_re is not None and not ctx_re.match(seg[m.end():]):
                        continue
                    if exl_re is not None and exl_re.match(m.group(1)):
                        continue
                    out.append((os.path.relpath(f, ROOT),
                                base + seg[:m.start()].count('\n'), m.group(1), anchors))
            continue
        for i, ln in enumerate(_txt.split('\n'), 1):
            anchors = []
            for bm in aq.finditer(ln):
                for it in parse_anchor_items(bm.group(0), bm.groupdict(), cfg):
                    if not it.get('src') and file_src:
                        it['src'] = file_src          # 空来源锚 ⇒ 文件头回退（教育线既有口径）
                    anchors.append(it)
            for m in re.finditer(r'%s([^%s]{4,400})%s' % (qc[0], qc[1], qc[1]), ln):
                if ctx_re is not None and not ctx_re.match(ln[m.end():]):
                    continue                      # ② 路由/触发句 ⇒ 不进射程（不是引文）
                if exl_re is not None and exl_re.match(m.group(1)):
                    continue                      # 引号内容本身是技能自述（加粗短语等）
                if scope_ex_re is not None:
                    # ⚠ 精度要求（2026-09-17 实测自伤）：曾用"本行前 90 字 ∪ 上一行"作上下文 ⇒
                    #   把**同行别处**出现 `本件答` 的真引文也误排（manias 实测 1 条真引文被排除，
                    #   靠"排除计数带上限＋逐条打印"当场暴露）。⇒ 收紧为**标记必须紧跟引文**
                    #   （只看引文前的最后 14 字，且标记须贴着引号结尾）。
                    before = ln[:m.start()][-14:]
                    if scope_ex_re.search(before):
                        excluded.append((os.path.relpath(f, ROOT), i, m.group(1)[:40]))
                        continue
                if not anchors:
                    if cfg.get('strict_anchor_on_quote_line'):
                        unparsed.append((os.path.relpath(f, ROOT), i))
                    continue
                out.append((os.path.relpath(f, ROOT), i, m.group(1), anchors))
            prev_ln = ln
    return out, unparsed, excluded


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--task', required=True)
    ap.add_argument('--config', default=None)
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--report', default=None)
    ap.add_argument('--json-out', default=None)
    a = ap.parse_args()
    task = a.task.replace('.work/', '').replace('.work\\', '')

    cfg, cfg_path = load_config(task, a.config)
    if cfg is None:
        print('🔴 本册缺配置：%s —— **不回落任何册的默认值**（A-74：兜底＝静默降级）。' % cfg_path)
        print('   请照模板填一份：%s' % TEMPLATE)
        return 1
    if cfg.get('gate_ready') is False:
        # **自声明的"不适用"**（不是静默通过）：本册尚未迁移到通用闸，由**既有专用闸**把关。
        print('✔ 不适用（N/A · 自声明）：本册配置显式 `gate_ready=false` ⇒ 未迁移到通用闸。')
        print('   理由：%s' % cfg.get('gate_ready_note', '（未填写）'))
        print('   在役仪器：%s' % cfg.get('incumbent_gate', '（未填写）'))
        return 0
    import verify_candidates as VC
    import stage15_merge_task as M
    N, norm_note = get_norm(VC)

    layer = os.path.join(ROOT, '.work', task, cfg['layer'])
    files = sorted(p for p in glob.glob(os.path.join(layer, cfg.get('pattern', '*.md')),
                                        recursive=True)
                   if os.path.basename(p) != 'SKILL.md'
                   and not any(s.startswith('_') for s in os.path.relpath(p, layer).split(os.sep)))

    rows = []            # 每条引文一行
    unparsed_total = 0
    pool = load_pool(task, cfg, VC)
    idx, pages_note, n_pages = pages_loader(cfg, task, VC, M)
    res = {}

    def rec(rn, name, ok, detail):
        print('  %s %-28s %s' % ('✔' if ok else '🔴', name, detail))
        res[rn] = dict(name=name, ok=bool(ok), detail=detail)

    print('=' * 92)
    print('%s · 引文型附属文件零问题闸（通用版）｜ 配置 %s'
          % (task, os.path.relpath(cfg_path, ROOT)))
    print('  锚形态：%s' % cfg['anchor_regex'][:80])
    print('  页源　：%s（页数 %d）' % (pages_note, n_pages))
    print('  引文取法：%s ｜ 池条目 %d ｜ 扫 %d 个附属文件'
          % (cfg.get('quote_source', 'inline_quote'), len(pool), len(files)))
    print('=' * 92)

    quotes, unparsed, q_excluded = scan_quotes(cfg, files, VC)
    unparsed_total = len(unparsed)

    # 逐条判定（R6：用该行全部锚的并集）
    n_ok = n_pool = n_miss = n_near = n_short = 0
    n_src_unresolved = [0]          # 书别名不可解的锚数（自声明）
    for fn, ln, q, anchors in quotes:
        qn = N(q)
        if len(qn) < cfg.get('min_quote_len', 8):
            n_short += 1
            rows.append(dict(file=fn, line=ln, state='SHORT', q=q[:40]))
            continue
        ids = [x['id'] for x in anchors if x['id']]
        try:
            import verify_layer_quotes as _VL
            segs = _VL.segments(q) or [qn]          # 复用权威分段（A-72；纯函数、零配置）
        except Exception:
            segs = [qn]
        hit_pool = [i for i in ids if i in pool and qn and
                    match_segs(segs, N(pool[i]['quote']))]
        pgs, exact = [], []
        for an in anchors:                      # ⚠ 不得用 `a`：会遮蔽 argparse 的 Namespace（A-94 家族）
            if an['page']:
                ks = sorted(page_keys(idx, an['page']))
                pre = resolve_prefix(cfg, an.get('src'))
                if pre is None and an.get('src'):
                    n_src_unresolved[0] += 1
                for k in ks:
                    pgs.append(k)
                    if pre is not None:
                        exact.append((pre, k))
            if an['id'] and an['id'] in pool:
                pgs.extend(pool[an['id']]['pages'])
        if hit_pool:
            n_ok += 1
            rows.append(dict(file=fn, line=ln, state='PAGE_OK',
                             detail='池条目逐字命中（%s）' % '、'.join(hit_pool[:3]), q=q[:40]))
            continue
        if idx and exact:
            found = [p for (pre, p) in exact if qn in idx.get((pre, p), '')]
            if found:
                n_ok += 1
                rows.append(dict(file=fn, line=ln, state='PAGE_OK',
                                 detail='源页 s%s（按别名精确）'
                                        % '/s'.join(map(str, sorted(set(found)))), q=q[:40]))
                continue
        if idx and pgs:
            # ⚠ A-72 家族修正（2026-09-22 由新会话换书实测定位）：
            #   本闸引文侧用 `VL.norm`（STRIP 族：**剥标点/括号/强调符**），
            #   而页文本侧此前只用 `VC.norm`（**仅去空白、保标点**）⇒
            #   **同一化判据两侧归一化不一致** ⇒ 任何带标点的引文都合不上，**必然假 MISS**。
            #   实测（qushi-liliang 首次真跑）：GLOSSARY L55 引文 `因此，2021年…可能性。`
            #   其 `VL.segments()` 段为 `因此2021年确实存在均值回归的可能性`（无标点），
            #   而页文本为 `因此，2021年…可能性。`（带标点）⇒ `seg in pt` 永假。
            #   修法：**页文本侧改用同一归一化 VL.norm**（两侧同尺）。
            try:
                import verify_layer_quotes as _VLN
                _NT = _VLN.norm
            except Exception:
                _NT = VC.norm          # 兜底：至少不引入未定义名（QN/N 在本文件均未定义）
            found = [p for p in set(pgs) if match_segs(segs, _NT(page_text(idx, p)))]
            if found:
                n_ok += 1
                rows.append(dict(file=fn, line=ln, state='PAGE_OK',
                                 detail='源页 s%s 逐字命中' % '/s'.join(map(str, sorted(found))), q=q[:40]))
                continue
        # 邻页（±2）作为"近似/锚偏"类
        if idx and pgs:
            near = []
            for p in set(pgs):
                for d in (-2, -1, 1, 2):
                    if qn in idx.get(p + d, '') or qn in idx.get(('', p + d), ''):
                        near.append(p + d)
            if near:
                n_near += 1
                rows.append(dict(file=fn, line=ln, state='NEAR',
                                 detail='邻页命中 s%s（自称 s%s）'
                                        % ('/s'.join(map(str, sorted(set(near)))), pgs[:3]), q=q[:40]))
                continue
        n_miss += 1
        rows.append(dict(file=fn, line=ln, state='MISS',
                         detail='源页与池条目均未命中（自称 %s）' % (pgs[:3] or '无页'), q=q[:40]))

    total = len(rows)
    print()
    if q_excluded:
        print('  ℹ 射程排除（引号内是技能自述的触发句/项目名 ⇒ **不是**逐字引文）%d 条'
              '（上限 %s，**只许减少不许增长**）：'
              % (len(q_excluded), cfg.get('quote_scope_exclude_allow')))
        for fn, i, q in q_excluded:
            print('      - %s L%d ｜ %s…' % (os.path.relpath(fn, ROOT), i, q))
    rec('R1', '锚可解析', unparsed_total <= cfg.get('unparsable_allow', 0),
        '不可解析锚行 %d（白名单上限 %s）' % (unparsed_total, cfg.get('unparsable_allow', 0)))
    rec('R2', '引文全覆盖', total == n_ok + n_near + n_miss + n_short,
        '射程内引文 %d（另排除 %d）｜ OK %d ／ NEAR %d ／ MISS %d ／ SHORT %d'
        % (total, len(q_excluded), n_ok, n_near, n_miss, n_short))
    rec('R2b', '射程排除带上限', len(q_excluded) <= (cfg.get('quote_scope_exclude_allow') or 0),
        '排除 %d ／ 上限 %s（只许减少不许增长）'
        % (len(q_excluded), cfg.get('quote_scope_exclude_allow')))
    rec('R3', '分栏自洽', total == n_ok + n_near + n_miss + n_short,
        '%d == %d＋%d＋%d＋%d' % (total, n_ok, n_near, n_miss, n_short))
    ok4, bad4 = norm_variants(N)
    rec('R4', '归一化族齐全', ok4, '口径＝%s ｜ 未覆盖族：%s'
        % (norm_note, ('、'.join(bad4) if bad4 else '无')))
    # R5：未命中零未处置 —— 每条 MISS 必须落入**已声明类别**（regex），且该类计数 ≤ allow（只许减少）
    classes = cfg.get('miss_classes') or []
    cls_hit = {c['name']: 0 for c in classes}
    unclassified = []
    for r in rows:
        if r['state'] != 'MISS':
            continue
        got = False
        for c in classes:
            if re.search(c['regex'], r['q']):
                cls_hit[c['name']] += 1
                got = True
                break
        if not got:
            unclassified.append(r)
    cls_bad = [c['name'] for c in classes if cls_hit[c['name']] > c.get('allow', 0)]
    ok5 = (n_miss == 0) or (not unclassified and not cls_bad)
    if classes:
        print('  ℹ 未命中分类（每条必须落入已声明类别，**只许减少不许增长**）：')
        for c in classes:
            print('      - %s：%d ／ 上限 %s%s' % (c['name'], cls_hit[c['name']], c.get('allow', 0),
                                              '（🔴 超限）' if cls_hit[c['name']] > c.get('allow', 0) else ''))
        if unclassified:
            print('      🔴 未分类未命中 %d 条：%s' % (len(unclassified),
                                                 '、'.join(x['q'][:24] for x in unclassified[:5])))
    rec('R5', '未命中零未处置（或落入已声明类别）', ok5,'MISS %d（未分类 %d；超限类别 %s）'
        % (n_miss, len(unclassified), cls_bad or '无'))
    rec('R5b', 'MISS 零未分类', n_miss == 0, '由 R5 承担')
    rec('R6', '判据＝该行全部锚并集', True, '实现：同行为单位的锚并集（不做位置配对，A-49）')
    rec('R7', '空集拒跑', total > 0 and len(pool) > 0,
        '引文 %d ｜ 池条目 %d' % (total, len(pool)))
    rec('R8', 'schema 与口径全字段', True, '%s@%s' % (SCHEMA, SCHEMA_VERSION))

    ok_all = all(v['ok'] for v in res.values())
    out = dict(schema=SCHEMA, schema_version=SCHEMA_VERSION, task=task,
               config=os.path.relpath(cfg_path, ROOT),
               口径=dict(锚形态=cfg['anchor_regex'], 页源=pages_note, 引文取法=cfg.get('quote_source', 'inline_quote'),
                        归一化=norm_note,
                        命中窗口='自称页 ∪ 池锚页；邻页 ±2 计 NEAR',
                        书别名不可解锚数=n_src_unresolved[0],
                        未命中类别={c['name']: cls_hit[c['name']] for c in (cfg.get('miss_classes') or [])},
                        池条目=len(pool), 附属文件=len(files)),
               counts=dict(total=total, ok=n_ok, near=n_near, miss=n_miss, short=n_short),
               rows=rows, assertions=res,
               partition_check=dict(consistent=total == n_ok + n_near + n_miss + n_short))
    rp = a.report or os.path.join(ROOT, '.work', task, 'layer-quotes-gate.md')
    jp = a.json_out or os.path.join(ROOT, '.work', task, 'layer-quotes-gate.json')
    L = ['# 引文型附属文件零问题闸（通用版）· `%s`' % task, '',
         '> schema `%s@%s` ｜ 配置 `%s` ｜ 页源 %s ｜ 引文 %d 条（池 %d 条）'
         % (SCHEMA, SCHEMA_VERSION, os.path.relpath(cfg_path, ROOT), pages_note, total, len(pool)), '',
         '| 断言 | 结果 | 明细 |', '|---|---|---|']
    for k in sorted(res):
        L.append('| %s %s | %s | %s |' % (k, res[k]['name'],
                                          '✔' if res[k]['ok'] else '🔴', res[k]['detail']))
    if n_miss or n_near:
        L += ['', '## 非 OK 明细', '', '| 文件 | 行 | 态 | 明细 |', '|---|---|---|---|']
        for r in rows:
            if r['state'] not in ('PAGE_OK',):
                L.append('| %s | L%d | %s | %s |' % (r['file'], r['line'], r['state'], r.get('detail', '')))
    io.open(rp, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    io.open(jp, 'w', encoding='utf-8', newline='\n').write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    print('-' * 92)
    print('结论：%s ｜ 报告 %s' % ('✔ R1–R8 全过' if ok_all else '🔴 有未过项',
                                os.path.relpath(rp, ROOT)))
    return 0 if ok_all else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
