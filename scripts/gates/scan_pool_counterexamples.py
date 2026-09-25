# -*- coding: utf-8 -*-
r"""scan_pool_counterexamples.py —— **反例覆盖的机械扫描器**（任务通用 · 零模型调用）

## 为什么必须存在这件工装（2026-09-21 · 盲判官实测抓到的活体缺陷）

「反例覆盖」原先是**靠作答者的自觉**：作答者自己报一句"我已反向扫池、额外命中 20 条"，
机器无法核。盲判官用**比作答者更机械**的扫法（波段 E 全 237 条 × 39 词标记 → 命中 102 →
剔除已引用/已说明 52 → 余 50 条逐条人工判）**仍找到 4 条真反例**没被列出。

⇒ 结论：**"我扫过了"这句话必须能被第三方用同一件工具复算**。本件就是把那句自报
变成**可复算的读数**（`T`／`N1`／`N2`）＋**可逐条对数的候选项清单**。

判官的关键判据（写进 `crisis-transmission-mapper\SKILL.md` 的等式第 3 条）：
> **"下界"声明只免责"未穷尽"，不免责"自报扫过的范围内仍漏"**——
> 凡声称"已逐条通读"的范围，必须给出该范围的工具读数，否则**不得声称通读**。

## 通用性纪律（避坑手册 A-74 ／ AGENTS.md 高频坑第 6 条）

**本件不得含任何一本书的数据**：册名（`--task`）、波段（`--band`）、词表（`--words`）、
源文件名与页标记形态（`.work/<task>/bookspec-<task>.json` 的 `src`／`pagemark`）
**一律来自参数或配置**。默认词表是**反例导向**的语义类目（不是某一册的引文），
且可用 `--words` 整体覆盖。换册／换波段／换词表都能跑。

## 分层口径（N1／N2 的定义，可当场复算）

对池内每条候选（`### <id>  [类型] [技能=…]`）：

| 层 | 判据 | 计入 |
|---|---|---|
| **原文（逐字）层 `N1`** | 命中词出现在该条的「**原文（逐字）**」字段内 | `N1` |
| **仅转述层 `N2`** | 原文层未命中，但命中词出现在该条的「**转述**」字段内 | `N2` |
| **合计 `T`** | 两条通道去重后的**条目数**（同一条同时命中多词只算 1 条） | `T = N1 + N2` |

⚠ 为什么必须分层：**原文层是"书中真的这么写了"的硬证据**（可直接引用）；
**仅转述层只说明提取器的概括里出现了该词**——召回不丢，但它**不等于逐字原文**，
引用前必须回池取原句。两层混报＝把"可能被转述放大"的项当硬证据（A-34 放松尺子）。

## 候选项清单的字段

| 字段 | 含义 |
|---|---|
| `id` | 池内候选 id（波段＝id 前缀） |
| `sNNN` | 池内 `- 锚：` 原值 |
| 命中词 | 该条命中的全部词（去重、按词表序） |
| 原句首 30 字 | 命中词**所在句**的句首 30 字（**直接从页文本取，不是手抄**） |
| 层 | `原文`（逐字层）／`仅转述` |
| 波段 | id 前缀所对应的波段 |

「原句」的抽取口径（零启发式）：把**页文本**按页序拼接（`norm_match` 口径，页标记剔除），
在拼接串里找到该命中的**首次出现偏移**，再按**页序前缀长度表**把偏移映射回页号；
句界＝句末标点（。！？；）与页边界。句首 30 字＝该句归一化文本的前 30 字。

## 用法

```
python tools\scan_pool_counterexamples.py --task <slug> --band E
python tools\scan_pool_counterexamples.py --task <slug> --band ALL --layer both \
       --exclude <你已引用的 id 清单.md> --out <报告.md> --json <候选.json>
```

- `--band`：`A|B|C|D|E|F|G|ALL`（**任意波段前缀**都收，不写死 A..G）
- `--layer`：`both`（默认）／`verbatim`（只报原文层）／`paraphrase`（只报仅转述层）
- `--exclude`：**已被该答案引用/已说明的 id 清单**（一行一个 id，或任意含 id 的文本，
  文件名任意）；给了它，报告追加输出「**剔除已引用后剩余 M 条**」清单
- 退出码：**恒 0**（本件是**读数器**，不是闸；读数不好看不是"跑失败"）

## 自证

本件末段 `--selftest` 做语法级正／负样本自证（页映射、句界、分层计数、幂等）。
另：跑 `--band E` 的实跑读数写进 `--out` 报告尾部（"自证：本件对该册该波段的读数"）。

## ⚠ 页文本来源的一处**已实测口径差**（2026-09-21 · 本件自证时抓到，登记备查）

`.work/<task>/deepseek_text/pNNNN.txt`（**逐页镜像**）与 `<册配置的 src>` 的**页号相差 1**：
本册实测 —— `deepseek_text/p0250.txt` 的内容 ＝ `ocr_ds.txt` 的 **`[PAGE 251]`** 段。

⇒ 本件默认**优先**用镜像目录（快、免切页），但**由"整条引文 → 句段 → 句首 12 字"逐级回落定位**，
  所以**页号列只作参考**；口径与 `tools\rquote_page_check.py` 一致的**权威页号**一律以
  `<册配置的 src>`（`bookspec-<task>.json` 的 `src`）为准 —— 这也是 `SKILL.md` 引文页锚的口径。
  **读数（N1／N2／T）不受此差影响**（读数只看池内字段，不看页号）。

若某次需要"页号与页锚严格对齐"，把镜像目录改名（如 `deepseek_text_mirror`）即可让本件
自动回落到 `src` 切页通道（两条通道产出的**页序拼接串逐字节相同**，读数不变）。
"""
import argparse
import glob
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from _paths import ROOT                      # noqa: E402  可移植根目录（单一来源）
import _bandid as BID                        # noqa: E402  波段 id 语法唯一来源（A-132）
import verify_candidates as VC               # noqa: E402  池解析／归一化口径唯一来源
import stage15_merge_task as M               # noqa: E402  load_spec／build_page_index 唯一来源

# ── 反例导向默认词表 ──────────────────────────────────────────────────────────
# 分组只为可读；匹配是**整体词表**（不分组的子串匹配）。--words 可整体覆盖。
DEFAULT_WORDS = [
    # ① 例外／反例类目（"并非所有""唯一"）
    '例外', '反例', '并非所有', '并不是所有', '唯一', '巧合', '不对称', '相反',
    # ② 转折／让步标记（书中自报张力的标准句法）
    '然而', '却', '也',
    # ③ 幸免／未被卷入类目（阻断条件的来源）
    '幸免', '逃过', '未被卷入', '没有卷入', '并未引爆',
    # ④ 无定论／悬置类目（结论强度上界）
    '无定论', '莫衷一是', '罕见',
    # ⑤ 🔴 方向性反证类目（**2026-09-21 判官实测补入**）
    #    4 条漏项里有 2 条（`E-085`「回」升／`E-173`「然而」＋方向）正是这一类；
    #    只扫①②③④ 会**系统性漏掉"因果次序相反／方向相反／回升"**这类反证。
    '回升', '逆', '反向',
    # ⑥ 🔴 比较方向类目（**2026-09-21 本件自证再补**）
    #    实测活体：`E-201`（s250）「美国与英国受危机影响远较欧元区国家严重，
    #    但在危机过后，英美两国的经济增速**明显高于**欧元区国家」——**不含①②③④⑤ 任何一词**，
    #    单靠单字词表**必然漏掉**。这类反证靠「比较算子」说话，故本轮补入比较算子本身。
    '高于', '低于', '快于', '慢于', '大于', '小于', '多于', '少于',
    '反而', '与之相反', '恰恰相反', '反过来',
]
# 🔴 **成对规则**（两项**同现于同一字段**才算命中）——覆盖「比较方向」的另一种句法：
#    单字「较」／「比」／「至」／「更」在中文里极常见（**单独用＝噪声爆炸**），
#    但与方向词**同现**时几乎只出现在"比较性反证"里（`E-201` 的「远**较**…严重」）。
PAIR_RULES = [
    ('较', ('严重', '高', '低', '强', '弱', '快', '慢', '大', '小')),
    ('比', ('更', '严重', '高', '低', '强', '弱', '快', '慢')),
    ('更', ('高', '低', '强', '弱', '快', '慢', '严重', '大', '小')),
]
# 词表分组的**可读注解**（报告里照登，供判官核对"默认词表覆盖了哪些类目"）
WORD_GROUPS = [
    ('例外／反例', ['例外', '反例', '并非所有', '并不是所有', '唯一', '巧合', '不对称', '相反']),
    ('转折让步', ['然而', '却', '也']),
    ('幸免／未卷入', ['幸免', '逃过', '未被卷入', '没有卷入', '并未引爆']),
    ('无定论／悬置', ['无定论', '莫衷一是', '罕见']),
    ('🔴 方向性反证', ['回升', '逆', '反向']),
    ('🔴 比较方向', ['高于', '低于', '快于', '慢于', '大于', '小于', '多于', '少于',
                     '反而', '与之相反', '恰恰相反', '反过来']),
]

QUOTE_LABEL = VC.QUOTE                    # 原文（逐字）字段（标签容错沿用唯一真源）
TRANSCRIPT_LABEL = re.compile(
    r"^-\s*(?:转述|概述|简述)\s*[：:]\s*(.+?)\s*$", re.M)
SENT_END = '。！？；!?;'
# 页标记形态：**从本册配置读**（不得写死 —— A-69／A-74）

# 幂等标记：本件产出的一切文件都带这一行（重复跑＝覆盖，不重复插入）
IDEMPOTENT_MARK = '<!-- scan_pool_counterexamples:generated (idempotent; 重复跑覆盖本文件) -->'


# ── 池解析 ───────────────────────────────────────────────────────────────────
def parse_pool(pool_path):
    """读 verified.md → [dict(id, band, anchor, quote, transcript), ...]（顺序＝池序）。"""
    txt = io.open(pool_path, encoding='utf-8').read()
    rows = []
    for blk in BID.split_blocks(txt):
        head = blk.split('\n')[0]
        m = VC.ENTRY.match(head)
        if not m:
            continue
        q = QUOTE_LABEL.search(blk)
        tr = TRANSCRIPT_LABEL.search(blk)
        an = VC.ANCHOR.search(blk)
        rows.append(dict(
            id='%s-%s' % (m.group(1), m.group(2)),
            band=m.group(1),
            anchor=(an.group(1).strip() if an else ''),
            quote=(q.group(1) if q else ''),
            transcript=(tr.group(1) if tr else ''),
        ))
    return rows


def anchor_pages(anchor_raw):
    """池内 `- 锚：` 值 → 页号列表（区间展开；无法归一化＝[]）。"""
    pages = []
    for m in re.finditer(r's\s*(\d{1,4})(?:\s*[-–—~至]\s*s?\s*(\d{1,4}))?', anchor_raw or ''):
        p0 = int(m.group(1))
        p1 = int(m.group(2)) if m.group(2) else p0
        pages += list(range(min(p0, p1), max(p0, p1) + 1))
    return pages


# ── 页文本层（原句抽取的唯一来源）────────────────────────────────────────────
class PageText(object):
    """按页序拼接的页文本（`norm_match` 口径）＋页码↔偏移映射。

    `--pages-dir`（每页一个 `pNNNN.txt`）优先；缺省回落到本册配置的 `src`
    （页标记切页）——**两条通道产出的页序拼接串逐字节相同**（本册实测 `p0223.txt`
    与 `ocr_ds.txt` 第 223 页段归一化后相等），故读数一致。
    """

    def __init__(self, task, work, spec):
        self.mode = ''
        self.pages = []          # [(页号, norm_match(页文本)), ...] 按页序
        pages_dir = os.path.join(work, 'deepseek_text')
        if os.path.isdir(pages_dir):
            files = sorted(glob.glob(os.path.join(pages_dir, 'p[0-9]*.txt')))
            if files:
                for f in files:
                    base = os.path.basename(f)
                    mm = re.match(r'p(\d+)\.txt$', base)
                    if not mm:
                        continue
                    self.pages.append((int(mm.group(1)),
                                       VC.norm_match(io.open(f, encoding='utf-8').read())))
                self.mode = 'per-page 文件（%s，%d 页）' % (
                    os.path.relpath(pages_dir, ROOT), len(self.pages))
        if not self.pages:
            src_name = spec.get('src')
            src = os.path.join(work, src_name) if src_name else ''
            if not src or not os.path.exists(src):
                raise SystemExit('🔴 既无逐页文本目录（%s），配置的 src 也不可用：%s'
                                 % (pages_dir, src or '（配置缺 src）'))
            pm = spec.get('pagemark') or spec.get('pagemark_form') or 'auto'
            if pm == 'auto':
                pm = VC.detect_pagemark(src)
            VC.set_pagemark(pm)
            _sm, idx, order, _dup = M.build_page_index(src)
            self.pages = [(k, t) for k, t in order]
            self.mode = '本册配置 src（%s，页标记形态 %s，%d 页）' % (src_name, pm, len(self.pages))
        # 拼接串 ＋ 页序前缀长度表（精确映射，零启发式）
        self.concat = ''
        self.bounds = []
        for pno, txt in self.pages:
            self.bounds.append((len(self.concat), len(self.concat) + len(txt), pno))
            self.concat += txt

    def page_at(self, off):
        for lo, hi, pno in self.bounds:
            if lo <= off < hi:
                return pno
        return self.bounds[-1][2] if self.bounds else 0

    def sentence_at(self, off, word):
        """命中词所在句（归一化文本口径）：句界＝句末标点或页边界。"""
        lo = 0
        i = off - 1
        while i >= 0:
            if self.concat[i] in SENT_END:
                lo = i + 1
                break
            i -= 1
        hi = len(self.concat)
        j = off + max(1, len(word))
        while j < len(self.concat):
            if self.concat[j] in SENT_END:
                hi = j + 1
                break
            j += 1
        # 页边界也算句界（跨页引文不清句）
        sp, ep = self.page_at(off), self.page_at(max(0, hi - 1))
        if sp != ep:
            for lo2, hi2, pno in self.bounds:
                if pno == sp and lo2 <= off < hi2:
                    hi = min(hi, hi2)
                    break
        seg = self.concat[lo:hi]
        return seg, lo, hi

    def first_hit(self, needle):
        """在页序拼接串里找 needle（`norm_match` 口径）；返回偏移或 -1。

        ⚠ 引文可能**跨页**（页与页之间在池内是两段），首版逐页找会漏跨页引文
        ⇒ 一律在拼接串里找（口径同 `tools\rquote_page_check.py` 的跨页分支）。
        """
        qn = VC.norm_match(needle)
        if not qn:
            return -1
        return self.concat.find(qn)

    def hit_any(self, candidates):
        """按候选长度**从长到短**在拼接串里找，返回首个命中的 (偏移, 命中串)。

        ⚠ 为什么要多候选：池内引文是**摘录**，其内部句界未必与页文本逐字相同
        （本册实测：`E-047` 的池内引文开头在页文本里就是「1825年危机主要涉及英国和南美洲」，
        而页文本该句前面还有上文的编号标记）⇒ 只搜"整句"会失败、只搜"整条引文"也会失败。
        故：整条引文 → 句段 → 句首 12 字，**逐级回落**，且**不回落到 1 字**
        （1 字命中＝噪声，会把"原句"指向无关位置 —— 宁可标注回落）。
        """
        for cand in candidates:
            if not cand:
                continue
            off = self.first_hit(cand)
            if off >= 0:
                return off, cand
        return -1, ''


# ── 扫描 ─────────────────────────────────────────────────────────────────────
def scan(rows, words, layer, pt):
    """→ (hits, n1, n2) ；hits ＝ [dict(id,band,anchor,words,lead,pageno,layer), ...]

    命中词 ＝ 单字词表命中 ∪ 成对规则命中（成对规则要求两项**同现于同一字段**）。
    报告里成对规则的命中写成 `较+严重`（可核：两项在该字段内均出现）。
    """
    hits = []
    n1 = n2 = 0
    for r in rows:
        in_q = match_terms(r['quote'], words)
        in_t = match_terms(r['transcript'], words)
        verbatim = bool(in_q)
        para_only = (not in_q) and bool(in_t)
        if layer == 'verbatim' and not verbatim:
            continue
        if layer == 'paraphrase' and not para_only:
            continue
        if not verbatim and not para_only:
            continue
        if verbatim:
            n1 += 1
            matched = in_q
            src_text = r['quote']
            lyr = '原文'
        else:
            n2 += 1
            matched = in_t
            src_text = r['transcript']
            lyr = '仅转述'
        # 原句 = **该条自带的逐字文本里、命中词所在句**（硬证据，非人工转写）；
        #        页号 = 在**页文本**里定位该句（整条引文 → 句段 → 句首 12 字，逐级回落）。
        field = VC.norm_match(src_text)
        needle = matched[0].split('+')[0]
        k = field.find(needle)
        if k < 0:
            k = 0
        lo = 0
        i = k - 1
        while i >= 0:
            if field[i] in SENT_END:
                lo = i + 1
                break
            i -= 1
        hi = len(field)
        j = k + max(1, len(needle))
        while j < len(field):
            if field[j] in SENT_END:
                hi = j + 1
                break
            j += 1
        sent = field[lo:hi]
        lead = sent[:30]
        off, how = pt.hit_any([src_text, sent, sent[:12]])
        if off >= 0:
            pageno = pt.page_at(off)
            loc = '页文本命中（%s）' % ('整条引文' if how == src_text else
                                       ('句段' if how == sent else '句首 12 字'))
        else:
            pageno = (anchor_pages(r['anchor']) or [0])[0]
            loc = '池内锚（页文本未命中该句，按池内 `- 锚：` 回填）'
        hits.append(dict(id=r['id'], band=r['band'], anchor=r['anchor'],
                         words=matched, lead=lead, pageno=pageno, layer=lyr, loc=loc))
    return hits, n1, n2


def match_terms(field_text, words):
    """单字词表 ∪ 成对规则（同现）→ 命中项列表（按词表序／成对规则序）。"""
    out = [w for w in words if w and w in field_text]
    for a, bs in PAIR_RULES:
        if a in field_text:
            for b in bs:
                tok = '%s+%s' % (a, b)
                if b in field_text and tok not in out:
                    out.append(tok)
    return out


def read_exclude(path):
    """已引用 id 清单：一行一个 id，或任意含 id 的文本（宽松抽取，顺序＝文件序）。"""
    if not path or not os.path.exists(path):
        return []
    t = io.open(path, encoding='utf-8').read()
    seen, out = set(), []
    for m in BID.ID_RE.finditer(t):
        i = m.group(0)
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def md_table(hits, page_col='该句归属波段／页'):
    L = ['| # | id | 命中词 | 层 | %s | 归属页取值 | 原句首 30 字 |' % page_col,
         '|---|---|---|---|---|---|---|']
    for k, h in enumerate(hits, 1):
        L.append('| %d | `%s` | %s | %s | %s ／ s%s（池内锚 %s） | %s | %s |'
                 % (k, h['id'], '／'.join(h['words']), h['layer'], h['band'], h['pageno'],
                    h['anchor'] or '—', h.get('loc', '—'), h['lead']))
    return L


# ── 等式机核（--check · 2026-09-21 第2条收敛批：把"自报"变成"机核"）──────────
# 为什么需要它（判官实测结论）：
#   ① 第 1 轮：答案自称"已反向扫池、额外命中 20 条" → 判官用更机械的扫法仍找到真反例；
#   ② 第 2 轮：答案自称等式 `14 ＋ 119 ＝ 133 ＝ T ✓ 差异集为空` → 判官复算 **`11 ＋ 114 ≠ 133`**，
#      另有 **19 条命中在答案里"既未列入、也未说明不列"**（静默丢弃）——**自报的等式不是机核的等式**。
# ⇒ 本段把"差异集为空"从**答案的一句话**变成**工具当场算出来的集合运算**：
#     声称"通读"的范围（默认＝本件实跑的命中集合 `T`）内的每一个 id，
#     必须在答案的**处置清单**里有且仅有一条处置，且处置只能取三值之一：
#     `列入`（进入反例清单）／`不列`（写清"为什么不列"）／`未处置`（🔴 不得交付）。
COVERAGE_MARK = '反例覆盖-处置清单'
STATUS_LISTED = '列入'
STATUS_UNLISTED = '不列'
STATUS_PENDING = '未处置'
STATUS_TOKENS = (STATUS_LISTED, STATUS_UNLISTED, STATUS_PENDING)
# 处置登记表要求：**第一列就是 id**（`| \`E-007\` | 列入 | … |`）——
#   因为"在别处被引用过"不等于"已处置"（第 2 轮的丙类 3 条就是被引用≠被处置）。
CHECK_TABLE_HEAD = '| id | 处置 | 为什么（不列时必须写） |'


def _norm_head(s):
    """章节标题归一：去空白与装饰符，便于 --n-head/--m-head 容错匹配。"""
    return re.sub(r'[\s`*＊#　：:（）()｜|]', '', s or '')


# ── id 语法一律取自**唯一真源** `_bandid`（A-132：同一套语法不得内联写第二份）──
#   ⚠ 自证抓到的第 4 处活体缺陷（2026-09-21）：本批首版在 5 处内联了波段 id 的**字符类写法**
#     ⇒ `check_bandid_single_source.py` 报 10 处（tools ＋ 插件副本各 5）**全部来自本件**。
#     内联的害处不是"不美观"：真源改一次、内联的那份不改 ⇒ **同一份产出在不同仪器下时红时绿**。
_ID = BID.ID_LOOSE        # 例：[A-Za-z][A-Za-z0-9]*-\d+ （**无捕获组**）
# ⚠ 自伤（本批实测，当场拦下）：首版取的是 `BID.ID_EXACT_RE.pattern`，而它**自带一个捕获组**
#   （`(?<![A-Za-z0-9])(…)(?![0-9])`）⇒ 拼进下面几个正则后**外层组才变 group(1)**、id 落进 group(2)，
#   于是 `m.group(1)` 取到的是别的东西 ⇒ 形态 C 自证当场判红。**根因：借"别人的模式"时要连"组结构"一起核。**
# 反引号包裹的 id（答案里的常规写法）：`E-007`
RE_TICK_ID = re.compile(r'`(' + _ID + r')`')
# 表格单元格里的 id（带不带反引号都认）：`E-007` ／ E-007
RE_CELL_ID = re.compile(r'^`?\s*(' + _ID + r')\s*`?$')
# 反引号 id ＋ 紧跟的括号（形态 C）
RE_TICK_ID_PAREN = re.compile(r'`(' + _ID + r')`\s*[（(]([^）)]{0,200})[）)]')


def _id_norm(s):
    """单元格文本 → 规范 id（大写）；不是 id 则返回 ''（语法唯一来源＝`_bandid`）。"""
    m = RE_CELL_ID.match(s or '')
    return m.group(1).upper() if m else ''


def _extract_sections(ans_text, n_head, m_head):
    """按 `--n-head`／`--m-head` 抽两段（缺失＝空串；**不得静默通过** —— 缺段在核验里报错）。

    🔴 段界＝**同层级或更高层级**的标题（2026-09-21 自证抓到的活体缺陷）：
    原先写成"遇到任何 `#` 开头就停"，于是 `# 四、逐条说明不列` 往下第一行
    `## 组 1｜…` 就被当成段界 ⇒ **整段只抽到 63 字**、二级分组内容全丢。
    """
    lines = ans_text.split('\n')

    def level(l):
        s = l.lstrip()
        return len(s) - len(s.lstrip('#'))

    def slice_of(head):
        if not head:
            return ''
        h = _norm_head(head)
        hit = None
        for i, l in enumerate(lines):
            if l.lstrip().startswith('#') and h and h in _norm_head(l):
                hit = i
                break
        if hit is None:
            return ''
        base = level(lines[hit])
        buf = []
        for l in lines[hit + 1:]:
            if l.lstrip().startswith('#'):
                lv = level(l)
                if lv <= base:           # 同／更高层级＝段界
                    break
                buf.append(l)            # 更深层级（如 `## 组 1`）＝段内
                continue
            buf.append(l)
        return '\n'.join(buf)
    return slice_of(n_head), slice_of(m_head)


def _status_in(s):
    """从一段文本里取出处置取值（先长后短：`未处置` 含 `处置` 二字，顺序不能反）。"""
    for tok in STATUS_TOKENS:
        if tok in s:
            return tok
    return ''


def _parse_manifest_rows(ans_text, n3='', m4=''):
    """解析答案的**处置登记** → ({id: (处置, 原行, 行号)}, 重复清单, 形态名)。

    三形态**都是严格可机核**的（2026-09-21 收敛批：把"严格"做成彼此等价的三种登记法，
    而不是"严格一种＋宽松一种"——**宽松口径不得单独达标**）：

    | 形态 | 长什么样 | 处置取值来源 |
    |---|---|---|
    | `A 显式处置列` | `\\| \\`E-007\\` \\| 列入 \\| … \\|` | 第 2 列（**推荐**，也是 `--write-template` 生成的形态） |
    | `B 处置列名` | `\\| id \\| … \\| 处置 \\|`（列名就叫「处置」） | 「处置」那一列 |
    | `C 段内登记` | `\\`E-007\\`（列入）` ／ `\\`E-007\\`（不列，同词不同义）` | 紧跟的括号内文字 |

    🔴 形态 C 的**取词范围只限两段处置区**（`--n-head`／`--m-head`）：引用 ≠ 处置
    —— 第 2 轮实测的 `E-163` 就是"在别处被引用过"而被误算成已处置的。
    """
    lines = ans_text.split('\n')
    rows, dup = {}, []
    form_a = form_b = form_c = False
    # 表头逐表跟踪：遇表头行（某列列名就叫 `id`）就记住 id 列／处置列下标
    #   ⚠ 实测形态：表头可能是 `| # | id | 页锚 | … | 处置 | 与主结论的关系 |`
    #     —— **`id` 不一定在第一列**，只认第一列＝整表漏读（自证抓到的第 2 处真缺陷）
    id_idx, disp_idx = None, None
    for ln, l in enumerate(lines, 1):
        s = l.strip()
        if s.startswith('|'):
            cells = [c.strip() for c in s.strip('|').split('|')]
            if len(cells) < 2:
                continue
            norm = [re.sub(r'[`*＊\s]', '', c) for c in cells]
            if 'id' in norm or '处置' in norm:
                # 表头行：登记本表 id 列／「处置」列下标
                id_idx = norm.index('id') if 'id' in norm else 0
                disp_idx = norm.index('处置') if '处置' in norm else None
                continue
            k = id_idx if id_idx is not None else 0
            if k >= len(cells):
                continue
            i = _id_norm(cells[k])                                   # id 语法唯一来源＝_bandid
            if not i:
                continue
            st = ''
            if disp_idx is not None and disp_idx < len(cells):
                st = _status_in(cells[disp_idx])
                if st:
                    form_b = True
            if not st:                                   # 形态 A：紧跟 id 的那一列就是处置
                nxt = k + 1
                if nxt < len(cells) and disp_idx != nxt:
                    st = _status_in(cells[nxt])
                    if st:
                        form_a = True
            if not st:
                continue
            if i in rows:
                dup.append(i)
            # 理由：处置列右边第一个非空单元格（跳过序号/锚/命中等结构化列）
            reason = ''
            start = (disp_idx + 1) if disp_idx is not None else 1
            for c in cells[start:]:
                cc = re.sub(r'[`*＊\s]', '', c)
                if cc and not _id_norm(cc) and cc not in STATUS_TOKENS:
                    reason = c.strip()
                    break
            rows[i] = dict(status=st, raw=s, line=ln, reason=reason)
    if not rows and (n3 or m4):
        # 形态 C：段内 `id`（处置…）——只在两段处置区内取词；
        # 条目分隔符**全角 `｜` 与半角 `|` 都认**（批2 实测用的就是全角，只认半角＝取词盲区）
        for ln, l in enumerate((n3 + '\n' + m4).split('\n'), 1):
            for piece in re.split(r'[｜|]', l):
                _add_seg_entry(rows, dup, piece, ln, in_m4=(l in m4.split('\n')))
                # 形态 C 的"为什么"就写在括号里（去掉开头的处置词本身）
    form_c = any(v.get('form') == 'C' for v in rows.values())
    # 🔴 补齐规则（**单向更强**：只会让差异集更小、不会把真实漏项盖住）——
    #   当答案把某段**显式限定为"逐条说明不列"**（`--m-head`）时，
    #   该段内每个 `id`（……） 的括号内容若**非空**，即构成"为什么不列"的理由 ⇒ 计为「不列」。
    #   依据：段标题本身就是处置语义的限定（件内既有形态：`# 四、…逐条说明不列 M ＝ …`）。
    #   ⚠ 段外引用**一律不适用**该规则（引用 ≠ 处置，第 2 轮的 E-163 就是段外引用）。
    if m4:
        for ln, l in enumerate(m4.split('\n'), 1):
            for piece in re.split(r'[｜|]', l):
                # 实测形态（第 3 处活体缺陷）：命中词写在**第一个括号**里，处置理由在破折号之后 ——
                #   `- `E-004`（却）— 弗里德曼…**已入既有条目（作者已并列的张力）**`
                # 只吃第一个括号 ⇒ 把这类**已逐条说明**的条目误判成"静默丢弃"（假阳）。
                # 但也不能"只要出现 id 就算处置"——否则 `（**仅转述层 `N2`**）` 这类
                # **裸登记**（没有理由）会被算成已处置（假通过，正是第 2 轮的 `E-163` 形态）。
                # ⇒ 判据：**必须有实质理由**（括号内容 或 破折号后文字 ≥4 字且非纯标记）。
                m = RE_TICK_ID_PAREN.search(piece)
                if not m:
                    continue
                i = m.group(1).upper()
                if i in rows:
                    continue
                head = m.group(2).strip()
                tail = re.sub(r'^\s*[—–\-:：，,]*\s*', '', piece[m.end():].strip())
                if _status_in(tail) == STATUS_LISTED:
                    rows[i] = dict(status=STATUS_LISTED, raw=piece.strip(), line=ln,
                                   reason=tail[:200], form='C2')
                    continue
                _why = tail if len(tail) >= 4 else head
                if len(_why) < 4 or _why in STATUS_TOKENS:
                    continue                                  # 裸登记＝无理由 ⇒ 不算处置
                rows[i] = dict(status=STATUS_UNLISTED, raw=piece.strip(), line=ln,
                               reason=_why[:200], form='C2')
    form = ('清单·A 显式处置列' if form_a else
            '清单·B 处置列名' if form_b else
            '清单·C 段内登记' if (form_c or any(v.get('form') == 'C2' for v in rows.values())) else '')
    return rows, dup, form


def _add_seg_entry(rows, dup, piece, ln, in_m4=False):
    """段内形态 C 的单条登记：`\\`E-007\\`（列入）` / `\\`E-007\\`（不列，同词不同义）`。"""
    m = RE_TICK_ID_PAREN.search(piece)
    if not m:
        return
    st = _status_in(m.group(2))
    if not st:
        return
    i = m.group(1).upper()
    if i in rows:
        dup.append(i)
        return
    _why = re.sub(r'^\s*(?:' + '|'.join(STATUS_TOKENS) + r')\s*[，,、:：]\s*', '', m.group(2))
    rows[i] = dict(status=st, raw=piece.strip(), line=ln,
                   reason=('' if _why.strip() in STATUS_TOKENS else _why.strip()), form='C')


_CN_DIGIT = {'〇': 0, '零': 0, '一': 1, '壹': 1, '二': 2, '两': 2, '贰': 2, '三': 3, '叁': 3,
             '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6, '七': 7, '柒': 7,
             '八': 8, '捌': 8, '九': 9, '玖': 9}
_CN_UNIT = {'十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000}
_CN_BIG = {'万': 10000, '萬': 10000, '亿': 100000000, '億': 100000000}
# 全角数字 → 半角（`１２３` 也是合法写法）
_FW_DIGIT = {chr(0xFF10 + d): str(d) for d in range(10)}


def _cn2int(s):
    """数字字符串 → int。支持：`123`／`１２３`（全角）／`一百三十二`／`壹佰叁拾贰`／
    `十二`／`三十`／`五`／**混写 `1百32`、`3万2千`**。

    ⚠ 为什么必须支持到这一层：第 ⑧ 判项（自报数 = 机核数）若解析不了，
    该处自报数就**取不到** ⇒ 判项静默空转（`A-155` 家族：漏检伪装成通过）。
    自证连抓两轮：先是只认阿拉伯数字（中文数字漏），再是只认纯中文（混写漏）。
    """
    if s is None:
        return None
    s = ''.join(_FW_DIGIT.get(ch, ch) for ch in s)          # 全角 → 半角
    s = s.strip().replace(',', '').replace('，', '')
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total, section, cur = 0, 0, 0
    seen = False
    for ch in s:
        if ch.isdigit():
            cur = cur * 10 + int(ch)                        # 支持 `1百32` 里的 1 与 32
            seen = True
        elif ch in _CN_DIGIT:
            cur = _CN_DIGIT[ch]
            seen = True
        elif ch in _CN_UNIT:
            u = _CN_UNIT[ch]
            section += (cur if cur else 1) * u
            cur = 0
            seen = True
        elif ch in _CN_BIG:
            b = _CN_BIG[ch]
            section = (section + (cur if cur else 1)) * b
            total += section
            section, cur = 0, 0
            seen = True
        else:
            return None
    return (total + section + cur) if seen else None



def _selfreport_crosscheck(ans_text, listed, unlisted, pending, Tset):
    """**自报数 vs 机核数**闭式对账（2026-09-21 §27 批新增；同日再扩中文数字与形态）。

    为什么必须加：`--check` 原先只核"T 内每条**有**处置"，**不核答案自报的数字对不对**。
    实测活体：`R2c` 自称「列入 5 ／ 不列 128」，而机核实为 **1 ／ 132**（5／128 是把 4 条 T 外条目
    错算进 T 内所得）—— **闸当时看不见这个矛盾**（因为表的行集合是对的）。
    ⇒ 本函数把"答案自己写的数"逐处抓出来与机核数比，**不一致即失败**（`A-139`／R38 家族）。

    识别的书写形态（覆盖实测出现的全部形态；**中文数字也认**）：
      A `列入 N ／ 不列 M`（`／` 或 `/`；可带 `条`）
      B `列入 N 行 … 不列 M 行`
      C `T ＝ N` / `T=N`
      D `N 条列入 … M 条不列`
    返回 (findings, values, unparsed)：findings＝不一致项；values＝抓到的自报值；
      unparsed＝**看起来像自报数但解析不了**的片段（登记备查，不判失败——防"取不到却以为查过"）。
    """
    findings, values, unparsed = [], [], []
    n_l, n_u = len(listed & Tset), len(unlisted & Tset)
    n_p, n_t = len(pending & Tset), len(Tset)

    # ⚠ 射程收敛（自证连抓三轮假红后定稿）：
    #   ① 只扫"答案自报"的正文区：跳过内嵌的**工具输出块**（那是机核读数，不是自报）；
    #   ② 数字必须**紧邻关键词**，不允许跨行；③ 排除机核行残留与枚举尾随。
    scan = ans_text
    cut = scan.find('反例覆盖 · **等式机核**')
    if cut > 0:
        scan = scan[:cut]
    scan = re.sub(r'```[\s\S]{0,4000}?```', '\n', scan)

    SEP = r'[`\'"“”*\s]{0,6}'
    # 数字写法：阿拉伯（含全角）／中文（含大写、万/亿）／**混写（1百32、3万2千）**
    NUM = (r'((?:[0-9０-９]{1,9}|[〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾百佰千仟万萬亿億]{1,10})'
           r'(?:[0-9０-９〇零一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾百佰千仟万萬亿億]{1,9})?)')

    def num(x):
        return _cn2int(x)

    # ── A：同一行内「列入 N ／ 不列 M」（可带「条」）──
    for m in re.finditer(r'列入' + SEP + NUM + r'\s*条?[^\n]{0,6}?[／/][ \t]{0,4}?不列' + SEP + NUM + r'(?![、,，])', scan):
        a, b = num(m.group(1)), num(m.group(2))
        if a is None or b is None:
            unparsed.append('A 形态解析失败：%s' % m.group(0)[:40])
            continue
        values.append(('A 列入/不列', a, b))
        if (a, b) != (n_l, n_u):
            findings.append('自报「列入 %s ／ 不列 %s」≠ 机核「列入 %d ／ 不列 %d」'
                            '（原文：%s…）' % (a, b, n_l, n_u, m.group(0)[:40]))
    # ── B：同一行内「列入 N 行 … 不列 M 行」──
    for m in re.finditer(r'列入' + SEP + NUM + r'\s*行[^\n]{0,60}?不列' + SEP + NUM + r'\s*行', scan):
        a, b = num(m.group(1)), num(m.group(2))
        if a is None or b is None:
            unparsed.append('B 形态解析失败：%s' % m.group(0)[:40])
            continue
        values.append(('B 列入/不列 行', a, b))
        if (a, b) != (n_l, n_u):
            findings.append('自报「列入 %s 行 … 不列 %s 行」≠ 机核「%d ／ %d」'
                            '（原文：%s…）' % (a, b, n_l, n_u, m.group(0)[:40]))
    # ── C：自报工具命中总数 `T = N`（排除机核行残留：`且属 T = 1`／`不属 T = 0`）──
    for m in re.finditer(r'(?<![A-Za-z])(?<!且属 )(?<!不属 )(?<!属 )T\s*[＝=]\s*' + NUM + r'(?![、,，0-9])', scan):
        v = num(m.group(1))
        if v is None:
            unparsed.append('C 形态解析失败：%s' % m.group(0)[:40])
            continue
        values.append(('C 自报 T', v))
        if v != n_t:
            findings.append('自报 `T ＝ %s` ≠ 工具机核 `T ＝ %d`' % (m.group(1), n_t))
    # ── D：「N 条列入 … M 条不列」──
    for m in re.finditer(NUM + r'\s*条\s*列入[^\n]{0,30}?' + NUM + r'\s*条\s*不列', scan):
        a, b = num(m.group(1)), num(m.group(2))
        if a is None or b is None:
            unparsed.append('D 形态解析失败：%s' % m.group(0)[:40])
            continue
        values.append(('D N 条列入/M 条不列', a, b))
        if (a, b) != (n_l, n_u):
            findings.append('自报「%s 条列入 … %s 条不列」≠ 机核「%d ／ %d」'
                            '（原文：%s…）' % (a, b, n_l, n_u, m.group(0)[:40]))
    return findings, values, unparsed


def _crosstable_consistency(ans_text, Tset, pool_ids, rows, n3='', m4=''):
    """**跨表一致**（2026-09-21 §27 批 · 回应判官 RJ3 第 9 项 ▲ 的另一半）。

    原闸的两个"看不见"：
      ① 只核"表内每行有处置"，**不核答案里提到的其他 id 有没有去向**——
        于是"把该列的条目挪到表外、只在正文里引一句"可以绕过等式；
      ② 完全不知道答案提到的 id **是否真的存在于池内**（编造 id 也发现不了）。

    🔴 判据射程（首版**过宽**、被真答案当场证伪后收紧）：
      首版把"答案提到的每个 id 都必须在处置**表内**"当判据 ⇒ 在真答卷上误报 **31 条**，
      而这 31 条**全部有正当去向**（判官宽表差集 19 条 ＋ 件内必列 6 条 ＋ 同族条目），
      它们本就"不进表、由边界声明承载"。
      ⇒ 正确判据是：**表外提及的 id 必须在"处置区"里有承载**——
        即它出现在 `--n-head`／`--m-head` 两段内，或出现在答案的**反例/边界章节**里
        （`## 2.3`／`§2.3.2`／`§三.3`／`§三.4` 一类标题下），**否则**才算
        "既不在表内、也无任何处置区承载"＝可疑的"挪到表外规避等式"。
    返回 (findings, unregistered, not_in_pool, unprotected)
    """
    findings = []
    if pool_ids is None:
        pool_ids = set()
    mentioned = {m.upper() for m in RE_TICK_ID.findall(ans_text)}
    registered = set(rows)

    # "处置区"＝**给出实质承载**的章节。判据（两轮收紧后定稿）：
    #   ① 章节标题含"实质承载"语义：证据／支持／主张／反例／例外／边界／差集／必列／宽表／处置／口径；
    #   ② **纯名录型章节不算**（如"工具读数"里的 id 名单 = 登记，不是处置）。
    #   ⚠ 首版只认"反例/边界"关键词 ⇒ 把真答卷 §2.2「支持章节/证据」里的 8 条**误报为无承载**。
    ZONE_HEAD = r'(证据|支持|主张|反例|例外|边界|差集|必列|宽表|处置|口径)'
    lines = ans_text.split('\n')
    in_zone, zone_text = False, []
    for l in lines:
        if l.lstrip().startswith('#'):
            in_zone = bool(re.search(ZONE_HEAD, l.strip()))
        if in_zone:
            zone_text.append(l)
    zone = '\n'.join(zone_text)

    # "承载"判据（2026-09-21 第三版 · **去掉标题依赖**）：
    #   前两版都靠"章节标题关键词"判处置区，两次都在真答案上报假红
    #   （第一次漏"证据/支持"标题 ⇒ 8 条误报；根因是**标题写法不可穷举**）。
    #   本版改为**结构判据**：该 id 只要在任一行里**与实质内容同现**即算有承载——
    #     ① 该行含「」引文（＝真在引池内原文/给理由）；**或**
    #     ② 该行去掉 id 与装饰符后仍有 ≥12 个非空白字符（＝真有说明，不是名录）。
    #   ⚠ 自证抓到的自身缺陷：首版把"body ≥12 字符"单独当判据 ⇒ **几乎恒真**
    #     （名录行 `另见 \`Z-001\`。` 也能凑够字符）⇒ 负样本 G 没被拦下。
    def _carried_struct(i):
        for l in ans_text.split('\n'):
            if i not in l:
                continue
            if '「' in l and '」' in l:
                return True                                   # 带引文 ⇒ 硬信号
            body = re.sub(r'[`*＊\s|—\-–:：]', '', l.replace(i, ''))
            if len(body) >= 12:
                return True
        return False

    def _carried(i):
        return (i in rows) or (i in n3) or (i in m4) or (i in zone) or _carried_struct(i)

    unprotected = sorted(i for i in mentioned if i not in Tset and not _carried(i))
    if unprotected:
        findings.append('答案提到、但**既不在命中集合 T 内、也不在处置区（反例/边界章节）里**的 id '
                        '%d 个 —— 须核这些是否"该列而未列"或"挪到表外规避等式"：%s'
                        % (len(unprotected), '、'.join('`%s`' % x for x in unprotected[:12])))
    # ⚠ 池内核的射程（第三处自身缺陷·自证抓到）：**只对"同波段"的 id 查池**。
    #   实测活体：`A-104`（波段 A）在"波段 E"的机核里被报成"池内不存在＝可能编造"，
    #   而件内明写必列清单**含 A／B／F 段条目**（`SKILL.md` L273）。
    #   ⇒ 跨波段 id 合法，不查池；只查"与本轮 T 同波段"的 id 是否真在池内。
    t_bands = {x.split('-')[0] for x in Tset}
    not_in_pool = sorted(i for i in mentioned
                         if pool_ids and i not in pool_ids
                         and i.split('-')[0] in t_bands)
    if not_in_pool:
        findings.append('答案提到**池内不存在**的 id %d 个（可能是编造或写错）：%s'
                        % (len(not_in_pool), '、'.join('`%s`' % x for x in not_in_pool[:12])))
    return findings, sorted(mentioned - registered), not_in_pool, unprotected


def _severity_rank(ans_text, hits_by_id, unlisted, pool_entries=None):
    """**候选强度排序**（机器给判官的三角定位名单，**不代替判官裁、也不主张穷尽**）。

    三轮定稿（前两版都被真答案证伪）：
      · 首版只扫 **lead（命中词所在句的前 30 字）** ⇒ 池内条目里**别的句子**的反例导向词看不到；
      · 本版扫**池内该条的全文**（`原文（逐字）` ＋ `转述` 两字段），命中词按强度加权；
      · 🔴 **射程明示**：本表只覆盖**固定标记族**（下叙 STRONG／MEDIUM 两个词表）。
        任何**不在词表内**的反例写法它都看不见 ⇒ **本表不是完备清单**，
        判官仍须自己扫一遍（`SKILL.md` 第 3 条：下界声明只免责"未穷尽"）。
    """
    STRONG = ('并非所有', '并不是所有', '没有出现', '甚至没有', '尚不明确', '莫衷一是',
              '无定论', '唯一', '例外', '相反', '恰恰相反', '与之相反', '反过来', '很少',
              '罕见', '幸免', '逃过', '未被卷入', '没有卷入', '并未引爆',
              # 本版按"反例导向"语义补入（仍属**有界词表**，不是穷尽）
              '并不能', '不足以', '未必', '不必然', '未必如此', '另一说', '反驳', '反证',
              '不成立', '恰恰', '正相反', '相反地')
    MEDIUM = ('然而', '却', '逆', '反向', '回升', '高于', '低于', '快于', '慢于', '大于', '小于',
              '反而', '超过', '不如', '多于', '少于')
    out = []
    for i in sorted(unlisted):
        h = hits_by_id.get(i) or {}
        e = (pool_entries or {}).get(i) or {}
        blob = ((h.get('lead') or '') + '\n' + (e.get('quote') or '') + '\n'
                + (e.get('transcript') or ''))
        words = h.get('words') or []
        s = 3 * sum(1 for w in STRONG if w in blob) + 1 * sum(1 for w in MEDIUM if w in blob)
        # 命中词本身若属强标记，再加权（词表命中 + 强标记 = 更该看一眼）
        s += 3 * sum(1 for w in words if w in STRONG)
        if s > 0:
            out.append((s, i, h.get('anchor') or '', '／'.join(words),
                        (h.get('lead') or '')[:60]))
    out.sort(key=lambda r: (-r[0], r[1]))
    return out


def _markers_outside_wordlist(hits_by_id, words, pool_entries=None):
    """**词表外强标记核**（可自证的闭式判据 · 第三版定稿）。

    闭式判据：**池内该条文本里出现了「反例导向参照词表」中的词，而工具词表里没有这个词** ⇒
    说明该条**是靠"参照词表"才被认出来的**（而不是靠工具词表）——它的「不列」理由**必须比
    "同词不同义"更强**才站得住。机器只**列出**这些条（附标记与出处），判官据此逐条看理由。

    🔴 自证抓到的两轮自身缺陷（本条判据连改三版）：
      · 第 1 版：`outside` 只保留"与命中词不同族"的词，**且要求命中词为空** ⇒
        实测 **11 条含强标记、入选 0 条**——**判据恒空转**（`A-143`：一支都没扫到却像查过）。
        根因：工具词表 34 词几乎总能命中，`命中词为空` 的洞根本不成立。
      · 第 2 版起：判据改为**与命中路径无关**——直接问"池内文本含参照词、而该词不在工具词表"。
      这条与"排序表是否完备"的区别：**参照词表是固定的**，所以本判据**逐条可复算**。
    """
    REF = ('并非所有', '并不是所有', '没有出现', '甚至没有', '尚不明确', '莫衷一是',
           '无定论', '唯一', '恰恰相反', '与之相反', '反过来', '很少', '罕见',
           '幸免', '逃过', '未被卷入', '没有卷入', '并未引爆', '不成立', '未必',
           '不足以', '另一说', '反证', '反驳')
    tool_words = set(words or [])
    out = []
    for i, h in sorted(hits_by_id.items()):
        e = (pool_entries or {}).get(i) or {}
        blob = ((h.get('lead') or '') + '\n' + (e.get('quote') or '') + '\n'
                + (e.get('transcript') or ''))
        outside = [w for w in REF if w in blob and w not in tool_words]
        if outside:
            out.append((i, h.get('anchor') or '', '／'.join(outside), (h.get('lead') or '')[:50]))
    return out



def _parse_lenient(ans_text, scope=None):
    """宽松兜底：正文任意形态里 `\\`id\\`` 附近（同段/同行）出现处置词即计入。

    ⚠ 本路径**本就比机核弱**：它只能证明"这两个字在附近出现过"，
    不能证明"该 id 被逐条处置"（第 2 轮的 `E-163` 就是这样被误算成已处置的）。
    故 `--format lenient` 的报告里**必须**显著标注它不可单独作为达标依据。

    🔴 2026-09-21 自证时抓到的活体缺陷（当场修）：**本函数原先扫全文**，
    于是"N2 名册里列了一次""正文引用过一次"都被算成已处置 ⇒ 差异集被算小（假通过方向）。
    处置区（`--n-head`／`--m-head` 两段）之外的命中**一律不算处置** —— 引用 ≠ 处置。
    """
    text = ans_text if scope is None else scope
    rows = {}
    for m in RE_TICK_ID.finditer(text):
        i = m.group(1).upper()
        seg = text[max(0, m.start() - 60):m.end() + 120]
        st = ''
        for tok in STATUS_TOKENS:
            if tok in seg:
                st = tok
                break
        if i in rows and rows[i]['status'] != STATUS_PENDING:
            continue
        if st:
            rows[i] = dict(status=st, raw=seg.replace('\n', ' '), line=0, reason=seg.strip())
    return rows, []


def _required_list_ids(sec_text):
    """从「必列清单」段里抽**行首**的 id（只认行首，不认叙述里被提到的 id）。

    §27.1 第 2 条的**机核③「必列清单全覆盖」**＝`必列清单 ⊆ 列入`。
    🔴 射程：本项只检**覆盖性**（声明的必列清单是否都进了「列入」），
      **不检完整性**（清单本身是否穷尽反例）——完整性是语义，属 §27.1 **右栏判官**。
      故本项 PASS **不得**读成"该列而未列已无"。
    """
    out = []
    # id 语法取自**唯一真源** `_bandid`（A-132：同一套语法不得内联写第二份）
    row = re.compile(r'^\s*(?:[-*+]|\|)\s*`(' + BID.ID_LOOSE_STRICT + r')`')
    for l in (sec_text or '').split('\n'):
        m = row.match(l)
        if m:
            out.append(m.group(1))
    return out


def check_answer(task, band, ans_path, n_head, m_head, fmt, out, limit_unhandled,
                 json_path=None, must_head='必列清单'):
    """等式机核：解析答案的处置清单 → 与工具命中集合 T 做集合运算 → 差异集非空则 rc=1。

    返回 (rc, 报告文本)。**只读答案文件**，不改动任何产物。

    §27.1 第 2 条的四个机核项落地：①四环齐备＝判项⑥ ②等式 rc=0＝判项①②③④⑤⑦⑧⑨
    ③**必列清单全覆盖**＝判项⑩（`必列清单 ⊆ 列入`）④边界声明在位＝答案自带 §射程 段（判官核）。
    """
    jp = json_path or os.path.join(ROOT, '.work', task, 'pool-counterexamples-%s.json' % band)
    if not os.path.exists(jp):
        return 2, ('🔴 找不到工具读数 JSON：`%s`\n'
                   '⇒ 先跑：`python tools\\scan_pool_counterexamples.py --task %s --band %s`'
                   % (jp, task, band))
    payload = json.loads(io.open(jp, encoding='utf-8').read())
    T = [h['id'] for h in payload.get('hits', [])]
    Tset = set(T)
    if payload.get('T') != len(T) or len(Tset) != len(T):
        return 2, ('🔴 工具读数自相矛盾：`T`=%s 而 `hits` 去重后=%d —— 先修工具读数，不得据此核答案'
                   % (payload.get('T'), len(Tset)))
    if not os.path.exists(ans_path):
        return 2, '🔴 答案文件不存在：`%s`' % ans_path
    ans = io.open(ans_path, encoding='utf-8').read()

    # 两段处置区**先抽**（宽松路径要用它当取词范围 —— 引用 ≠ 处置）
    n3, m4 = _extract_sections(ans, n_head, m_head)
    sec_present = {'N': bool(n3.strip()), 'M': bool(m4.strip())}

    rows, dup, form = _parse_manifest_rows(ans, n3, m4)
    if fmt == 'lenient' or (fmt == 'auto' and not rows):
        rows2, _ = _parse_lenient(n3 + '\n' + m4)
        rows = rows2
        form = '宽松扫描（⚠ 弱口径：仅证明"处置词出现在两段处置区内"，不可单独作为达标依据）'

    listed = {i for i, v in rows.items() if v['status'] == STATUS_LISTED}
    unlisted = {i for i, v in rows.items() if v['status'] == STATUS_UNLISTED}
    pending = {i for i, v in rows.items() if v['status'] == STATUS_PENDING}

    noted = (listed | unlisted) & Tset
    pending_in_t = pending & Tset
    outside = sorted(set(rows) - Tset)
    missing = sorted(Tset - noted - pending_in_t)

    # 「不列」必须**事实上**写了"为什么不列"（表格第三栏 ／ 形态 C 的括号内说明）
    no_reason = [i for i in sorted(unlisted & Tset) if not rows[i]['reason'].strip()]

    bad, warn = [], []
    if not sec_present['N']:
        bad.append('缺 `%s` 段（两段处置区是件内既有的作答形态，缺段即无法复算）' % n_head)
    if not sec_present['M']:
        bad.append('缺 `%s` 段' % m_head)
    if form.startswith('宽松'):
        bad.append('处置登记形态不可机核（未按 A 显式处置列 ／ B「处置」列名 ／ C 段内 `id`（处置）登记）')
    if missing:
        bad.append('🔴 **静默丢弃 %d 条** —— 工具命中集合 `T` 内既未「列入」也未「不列」也非「未处置」'
                   % len(missing))
    if pending_in_t:
        bad.append('🔴 **未处置 %d 条**（登记为「%s」＝不得交付）' % (len(pending_in_t), STATUS_PENDING))
    if no_reason:
        bad.append('🔴 标了「不列」但第三栏为空（没有"为什么不列"）%d 条' % len(no_reason))
    if dup:
        bad.append('🔴 同一条 id 被登记两次（重复＝计数不可信）%d 条' % len(set(dup)))
    # ── §27 批新增：**自报数 vs 机核数** 闭式对账（现含中文数字与 4 种书写形态） ──
    sr_find, sr_vals, sr_unparsed = _selfreport_crosscheck(ans, listed, unlisted, pending, Tset)
    for _x in sr_find:
        bad.append('🔴 自报数与机核数不一致：' + _x)
    # ── §27 批新增：**跨表一致**（答案提到的 id 必须合规；不核"该不该列"，核"有没有去向"） ──
    pool_ids = set()
    if os.path.exists(payload.get('pool', '') or ''):
        try:
            pool_ids = {r['id'] for r in parse_pool(payload['pool'])}
        except Exception:
            pool_ids = set()
    ct_find, ct_unreg, ct_notpool, ct_unprot = _crosstable_consistency(
        ans, Tset, pool_ids, rows, n3, m4)
    for _x in ct_find:
        bad.append('🔴 跨表一致：' + _x)
    # ── §27 批新增：候选强度排序（**给判官的三角定位名单，不代替判官裁**） ──
    hits_by_id = {h['id']: h for h in payload.get('hits', [])}
    pool_entries = {}
    try:
        if os.path.exists(payload.get('pool', '') or ''):
            pool_entries = {r['id']: r for r in parse_pool(payload['pool'])}
    except Exception:
        pool_entries = {}
    ranked = _severity_rank(ans, hits_by_id, unlisted & Tset, pool_entries)
    # ── §27.1 机核③：**必列清单全覆盖**（`必列清单 ⊆ 列入`）──────────────
    must_sec = _extract_sections(ans, must_head, '__none__')[0] if must_head else ''
    must_ids = _required_list_ids(must_sec)
    must_set = set(must_ids)
    must_dup = sorted({i for i in must_ids if must_ids.count(i) > 1})
    must_not_t = sorted(must_set - Tset)
    must_not_listed = sorted(must_set - listed)
    must_bad = (not must_sec.strip()) or must_not_listed or must_dup
    # ── §27 批新增：**词表外强标记核**（把"排序表是否完备"换成可自证的闭式判据） ──
    wl_outside = _markers_outside_wordlist(hits_by_id, payload.get('words') or [], pool_entries)
    # ⚠ 越界 id 是**告警**，不是失败 —— 判据第 ⑦ 项写的是"仅告警，不判失败"。
    #   🔴 自证抓到的假红（2026-09-21）：上一版把它也 `bad.append` ⇒ 第 ⑦ 项显示 PASS 而 rc 仍为 1
    #      （**判据与实现不一致**＝`A-107` 家族：打印绿灯却返回红灯／打印红灯却返回绿灯）。
    if outside:
        warn.append('⚠ 登记了**不属 T** 的 id %d 条（可能来自其他波段／其他册的「必列清单」条目）：%s'
                    % (len(outside), '、'.join('`%s`' % x for x in outside[:20])))
    if not outside:
        pass
    if limit_unhandled is not None and len(missing) + len(pending_in_t) > limit_unhandled:
        bad.append('🔴 未处置合计 %d 条，超过 `--limit-unhandled %d`'
                   % (len(missing) + len(pending_in_t), limit_unhandled))

    L = [IDEMPOTENT_MARK, '',
         '# 反例覆盖 · **等式机核**（任务 `%s` ｜ 波段 `%s`）' % (task, band), '',
         '> 工装：`tools\\scan_pool_counterexamples.py --check`（任务通用 · 零模型调用 · **只读答案**）',
         '> 被判答案：`%s`（%d 字节）' % (ans_path, len(ans.encode('utf-8'))),
         '> 工具读数：`%s`' % os.path.relpath(jp, ROOT).replace('\\', '/'), '',
         '## 一、等式（本页所有数字都是**工具当场算的集合运算**，不是答案自报）', '',
         '```',
         '工具命中集合        T        = %d' % len(Tset),
         '登记「列入」且属 T  = %d' % len(listed & Tset),
         '登记「不列」且属 T  = %d' % len(unlisted & Tset),
         '登记「未处置」属 T  = %d' % len(pending_in_t),
         '⇒ 已处置合计        = %d' % len(noted | pending_in_t),
         '⇒ **差异集（无任何处置）** = %d' % len(missing),
         '⇒ 判据：`列入 ＋ 不列 ＋ 未处置 ≡ T` 且 **未处置 ＝ 0 且差异集为空**',
         '```', '',
         '## 二、逐项判定', '',
         '| 判项 | 判态 | 数值 |', '|---|---|---|']
    def rec(name, ok, val):
        L.append('| %s | %s | %s |' % (name, 'PASS' if ok else '🔴 FAIL', val))
    rec('① 差异集为空（无静默丢弃）', not missing, '差异集 = %d' % len(missing))
    rec('② 未处置为 0', not pending_in_t, '「%s」= %d' % (STATUS_PENDING, len(pending_in_t)))
    rec('③ 「不列」逐条写了理由', not no_reason, '无理由 = %d' % len(no_reason))
    rec('④ 无重复登记', not dup, '重复 = %d' % len(set(dup)))
    rec('⑤ 处置清单形态可机核', form.startswith('清单'), form)
    rec('⑥ 两段处置区齐备', sec_present['N'] and sec_present['M'],
        '列入段 %s ／ 不列段 %s' % ('在' if sec_present['N'] else '缺',
                                    '在' if sec_present['M'] else '缺'))
    # ⚠ G-15①（2026-09-24 改名＋分列读数）：旧名「无越界 id」与读数「不属 T = N」互相打架——
    #   本判据**从来不是**在断言"没有 T 外登记"（T 只是下界，T 外登记合法且常见），
    #   它真正断言的是「T 外登记**只走告警、不判失败**」（判据第 ⑦ 项原文＝"仅告警，不判失败"）。
    #   ⇒ 名字改成与真实语义一致，读数分列两半（登记数 ／ 告警栏去向），不再共用一个数。
    rec('⑦ T 外登记仅告警（不判失败；T 只是下界）', True,
        'T 外登记 = %d ｜ 去向 = %s' % (len(outside),
          ('全部进「告警（不判失败）」栏' if outside else '—（无 T 外登记）')))
    rec('⑧ 自报数 = 机核数（§27 新增）', not sr_find,
        '抓到自报数 %d 处 ／ 不一致 %d 处 ／ 解析不了 %d 处%s'
        % (len(sr_vals), len(sr_find), len(sr_unparsed),
           ('：' + '；'.join('%s=%s' % (v[0], v[1:]) for v in sr_vals[:4])) if sr_vals else ''))
    rec('⑨ 跨表一致：提及的 id 都有处置区承载（§27 新增）', not ct_find,
        '登记 %d 个 ／ 表外提及 %d 个 ／ **无任何承载 %d 个** ／ 池内无此 id %d 个'
        % (len(rows), len(ct_unreg), len(ct_unprot), len(ct_notpool)))
    rec('⑩ 必列清单全覆盖（`%s ⊆ 列入`）（§27.1 机核③ 新增）' % must_head, not must_bad,
        ('缺 `%s` 段' % must_head) if not must_sec.strip() else
        '必列 %d 条 ／ 未进「列入」%d 条 ／ 不在 T %d 条 ／ 重复 %d 条'
        % (len(must_set), len(must_not_listed), len(must_not_t), len(must_dup)))
    if not must_sec.strip():
        bad.append('🔴 缺「%s」段 —— §27.1 第 2 条把「必列清单全覆盖」列为**机核③**，'
                   '缺段即该机核项**无法判定**（不得静默算过）' % must_head)
    if must_not_listed:
        bad.append('🔴 **必列清单未全覆盖**：%d 条被声明为必列却只登记「不列」或未登记 —— %s'
                   % (len(must_not_listed), '、'.join('`%s`' % x for x in must_not_listed)))
    if must_not_t:
        # ⚠ 与判项⑤（越界 id 仅告警）口径必须一致：**必列清单允许含 T 外 id**
        #   （＝「T 只是下界，已列小节内的池内条目也要处置」这条口径的必然产物）。
        #   若此处判失败，就会出现"⑤ 说告警、⑩ 说失败"的**自相矛盾判据**（A-107 家族）。
        warn.append('⚠ 必列清单含**不在命中集合 T** 的 id %d 条（T 外补列，须另立口径说明，'
                    '不得混进等式）：%s'
                    % (len(must_not_t), '、'.join('`%s`' % x for x in must_not_t)))
    if must_dup:
        bad.append('🔴 必列清单有重复登记：%s' % '、'.join('`%s`' % x for x in must_dup))
    L += ['', '## 三、差异集明细（每一条都必须给出去向）', '']
    if missing:
        L.append('以下 %d 条属工具命中集合 `T`，但答案里**既未列入、也未说明不列、也未登记未处置**'
                 '——即"自报扫过的范围内仍漏"（件内判据第 3 条正是红线）：' % len(missing))
        L.append('')
        L.append('| # | id | 池内锚 | 命中词 |')
        L.append('|---|---|---|---|')
        amap = {h['id']: h for h in payload.get('hits', [])}
        for k, i in enumerate(missing, 1):
            h = amap.get(i, {})
            L.append('| %d | `%s` | %s | %s |'
                     % (k, i, h.get('anchor') or '—', '／'.join(h.get('words') or [])))
    else:
        L.append('**差异集为空** —— 工具命中集合内每一条都有明确去向（这条是本页唯一能替代"我扫过了"的东西）。')
    if pending_in_t:
        L += ['', '## 四、登记为「未处置」的条目（不得交付）', '',
              '、'.join('`%s`' % x for x in sorted(pending_in_t))]
    # ── §27 批新增：候选强度排序（给判官的名单；机器不判"该不该列"） ──
    # ── §27.1 机核③：必列清单（`必列清单 ⊆ 列入`）────────────────────
    L += ['', '## 三之二、**必列清单全覆盖**（§27.1 第 2 条 · 机核③）', '',
          '读作：答案在 `%s` 段里**行首**声明的 id，必须**全部**登记为「列入」。' % must_head,
          '> 🔴 **射程**：本栏只检**覆盖性**（清单内的都进了列入），**不检完整性**'
          '（清单本身是否穷尽反例）——完整性＝语义裁，属 §27.1 **右栏判官**。'
          '故本栏 PASS **不得**读成「该列而未列已无」。', '']
    if not must_sec.strip():
        L.append('- 🔴 **缺 `%s` 段** ⇒ 该机核项无法判定。' % must_head)
    else:
        L.append('| 读数 | 值 |')
        L.append('|---|---|')
        L.append('| 必列清单条数 | %d |' % len(must_set))
        L.append('| 未进「列入」 | %d |' % len(must_not_listed))
        L.append('| 不在命中集合 T | %d |' % len(must_not_t))
        L.append('| 重复登记 | %d |' % len(must_dup))
        if must_not_listed:
            L += ['', '未进「列入」的必列条目（**每一条都必须给出去向**）：',
                  '', '、'.join('`%s`' % x for x in must_not_listed)]
    if ranked:
        L += ['', '## 四之二、**候选强度排序**（给判官的三角定位名单 · 机器不代替判官裁）', '',
              '判据：答案把该条标了「不列」，但其**池内该条全文**（`原文（逐字）`＋`转述`）含'
              '**反例导向强标记**（并非所有／没有出现／尚不明确／例外／相反／很少／幸免…）或**比较/方向算子**。',
              '⇒ **分数越高越该被判官看一眼**；本表**不主张**其中任何一条"该列"。',
              '',
              '🔴 **射程明示**：本表只覆盖**固定标记族**（上列词表）——**不在词表内的反例写法它看不见**，'
              '故**本表不是完备清单**；判官仍须自己扫一遍（件内第 3 条：下界只免责"未穷尽"）。', '',
              '| 强度 | id | 池内锚 | 命中词 | 原句首 60 字 |', '|---|---|---|---|---|']
        for s, i, anc, w, lead in ranked[:30]:
            L.append('| %d | `%s` | %s | %s | %s |' % (s, i, anc or '—', w or '—', lead))
        if len(ranked) > 30:
            L.append('')
            L.append('（共 %d 条，此处只列前 30）' % len(ranked))
    # ── §27 批新增：词表外强标记核（可自证的闭式判据） ──
    if wl_outside:
        L += ['', '## 四之二之二、**词表外强标记核**（可自证 · 判官须逐条看理由）', '',
              '以下条目**池内文本含反例导向强标记，但工具的默认词表里没有它**'
              '⇒ 它们是靠"非词表路径"被扫到的，其「不列」理由**必须比"同词不同义"更强**才站得住。',
              '',
              '> 本栏的意义：把"排序表是否完备"（**不可自证**）换成"**词表外强标记是否都列出来了**"'
              '（**可自证**——因为参照词表是固定的、逐条可复算）。', '',
              '| id | 池内锚 | 词表外标记 | 原句首 50 字 |', '|---|---|---|---|']
        for i, anc, mk, lead in wl_outside[:40]:
            L.append('| `%s` | %s | %s | %s |' % (i, anc or '—', mk, lead))
        if len(wl_outside) > 40:
            L.append('')
            L.append('（共 %d 条，此处只列前 40）' % len(wl_outside))
    if sr_unparsed:
        L += ['', '## 四之三、看起来像自报数但**解析不了**的片段（登记备查，不判失败）', '']
        for x in sr_unparsed[:10]:
            L.append('- %s' % x)
        L.append('')
        L.append('> 本栏存在时，说明第 ⑧ 项的射程**未覆盖**这些写法 ⇒ 请人工核它们是否与机核数一致。')
    if outside:
        L += ['', '## 五、不属 T 的登记（仅告警）', '',
              '这些 id 不在本波段本次词表的命中集合内；若来自件内「必列清单」的其他波段，'
              '**必须另立口径说明**（不得混进本等式）：',
              '', '、'.join('`%s`' % x for x in outside)]
    L += ['', '## 六、复算方式（第三方照抄即可）', '',
          '```',
          'python tools\\scan_pool_counterexamples.py --task %s --band %s' % (task, band),
          'python tools\\scan_pool_counterexamples.py --task %s --band %s --check <答案.md>' % (task, band),
          '```',
          '> 本报告与工具读数 JSON 均带幂等标记：**重复跑＝覆盖同一文件**，不追加、不漂移。', '']

    rc = 0 if not bad else 1
    L += ['## 七、结论', '', ('✔ **等式机核通过**：差异集为空、未处置为 0。'
                              '（注意：这只证明"自报扫过的范围内无静默丢弃"，'
                              '**不免责词表覆盖之外的未穷尽** —— 件内判据第 3 条）')
          if rc == 0 else '🔴 **等式机核不通过**（rc=1）：', '']
    for b in bad:
        L.append('- ' + b)
    if not bad:
        L.append('- （无失败项）')
    if warn:
        L += ['', '### 告警（**不判失败**，但判官须核它是否构成"该列而未列"）', '']
        for w in warn:
            L.append('- ' + w)
        L.append('')
        L.append('> 本项**不影响退出码**（判据第 ⑦ 项：仅告警）。'
                 '判官要核的是：这些 id 里有没有**本该进反例清单却只登记为「不列」**的'
                 '（例如更宽词表扫出的真反例）——那是**语义判定**，机器闸不越权。')
    return rc, '\n'.join(L) + '\n'


def _exhaustive_selftest():
    """**穷举级自证**：逐样本单独跑，证明"每个样本都真的被执行、且判态与期望一致"。

    为什么需要它（与 `--selftest` 的分工）：
      `--selftest` 是**一组断言连着跑**——中间若因故提前跳过某段，**打印仍会说"通过"**；
      本模式把每个样本**独立跑一遍并逐条打印 rc 与期望**，于是"哪一段没跑到"一眼可见。
      依据 `A-55`（漏检比误报更致命）＋ `A-143`（判据空转：一支都没跑到却打印全绿）。
    """
    import shutil
    import tempfile
    TICK = '`'
    tmp = tempfile.mkdtemp(prefix='spe-exhaustive-')
    old_root = ROOT
    bad = []
    try:
        task, band = 'selftest-task', 'E'
        jp = os.path.join(tmp, '.work', task, 'pool-counterexamples-%s.json' % band)
        os.makedirs(os.path.dirname(jp), exist_ok=True)
        io.open(jp, 'w', encoding='utf-8').write(json.dumps(dict(
            T=5, hits=[dict(id='E-%03d' % k, anchor='s1', words=['例外'], layer='原文', lead='例句')
                       for k in (1, 2, 3, 4, 5)]), ensure_ascii=False))
        globals()['ROOT'] = tmp

        def idc(i):
            return TICK + i + TICK

        tbl = ('| id | 处置 | 为什么 |\n|---|---|---|\n'
               + ''.join('| %s | %s | %s |\n' % (idc('E-%03d' % k),
                                                 STATUS_LISTED if k <= 3 else STATUS_UNLISTED,
                                                 '—' if k <= 3 else '同词不同义')
                         for k in (1, 2, 3, 4, 5)))
        cases = [
            ('正·自报一致', '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n', 0),
            ('正·中文数字', '## 三、列入\n\n本表：列入 三 ／ 不列 二\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n', 0),
            ('正·内嵌机核', '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n\n```\n工具命中集合        T        = 5\n'
               '登记「列入」且属 T  = 3\n登记「不列」且属 T  = 2\n不属 T = 0\n```\n', 0),
            ('正·越界只告警', '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n%s（不列，波段 A，属件内必列清单）\n' % idc('A-104'), 0),
            ('负·自报不符', '## 三、列入\n\n本表：列入 5 ／ 不列 128\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n', 1),
            ('负·表外无承载', '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n\n## 附：随手一提\n\n另见 %s（无承载）。\n' % idc('Z-001'), 1),
            ('负·中文数字不符', '## 三、列入\n\n本表：列入 五 ／ 不列 一百二十八\n\n' + tbl
             + '\n## 四、逐条说明不列\n\n（在）\n', 1),
            ('负·静默丢弃', '## 三、列入\n\n本表：列入 3 ／ 不列 1\n\n'
             + ''.join('| %s | %s | %s |\n' % (idc('E-%03d' % k),
                                               STATUS_LISTED if k <= 3 else STATUS_UNLISTED, '—')
                       for k in (1, 2, 3, 4))
             + '\n## 四、逐条说明不列\n\n（在）\n', 1),
        ]
        for name, txt, want in cases:
            p = os.path.join(tmp, name + '.md')
            io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
            rc, _rep = check_answer(task, band, p, '列入', '不列', 'auto', None, None, json_path=jp)
            good = (rc == want)
            print('  %-4s %-16s rc=%d（期望 %d）' % ('✔' if good else '🔴', name, rc, want))
            if not good:
                bad.append('%s：期望 rc=%d 实得 rc=%d' % (name, want, rc))
    finally:
        globals()['ROOT'] = old_root
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if bad:
        print('🔴 穷举自证失败 %d 项' % len(bad))
        return 1
    print('✔ 穷举自证通过（%d 个样本**逐个独立跑**，判态全部与期望一致）' % len(cases))
    return 0


def write_template(task, band, json_path, out):
    """生成**处置清单模板**（每个 id 一行，处置取值待填）——作答前置，防"散在正文里"。"""
    jp = json_path or os.path.join(ROOT, '.work', task, 'pool-counterexamples-%s.json' % band)
    payload = json.loads(io.open(jp, encoding='utf-8').read())
    L = [IDEMPOTENT_MARK, '',
         '## %s（模板 · 逐行填第 2、3 栏）' % COVERAGE_MARK, '',
         '> 填法：第 2 栏只填 `%s`／`%s`／`%s` 三者之一（填「%s」＝不得交付）；'
         '填「%s」时**第 3 栏必须写清为什么不列**。' % (
             STATUS_LISTED, STATUS_UNLISTED, STATUS_PENDING, STATUS_PENDING, STATUS_UNLISTED),
         '> 本模板由 `--write-template` 生成：**行集合＝工具命中集合 `T`**，一行不许删、不许并。',
         '> ⚠ 生成器留存（G-61③ · 2026-09-24）：本模板以及**基于它写就的答卷**，其**生成脚本必须与答卷同目录留存**'
         '（或答卷自带一段可跑的「如何生成」命令）——判官/机核要核产出过程时以此为准；'
         '`postflight` ⑲ 项对规则日之后的答卷强制抽查此项。', '',
         CHECK_TABLE_HEAD, '|---|---|---|']
    for h in payload.get('hits', []):
        L.append('| `%s` |  | （命中词：%s｜锚 %s｜层 %s） |'
                 % (h['id'], '／'.join(h.get('words') or []), h.get('anchor') or '—',
                    h.get('layer') or '—'))
    L.append('')
    io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    return len(payload.get('hits', []))


def main():
    ap = argparse.ArgumentParser(description='反例覆盖的机械扫描器（任务通用 · 零模型调用）')
    ap.add_argument('--task', required=True, help='任务 slug（册名一律来自参数，不得写死）')
    ap.add_argument('--allow-empty-pool', dest='allow_empty_pool', action='store_true', default=False,
                    help='允许「池文件在但解析 0 条」时继续跑（**默认禁止**：池 0 条即「无对簿对象」，rc=1；见 G-41）。'
                         '只用于脚手架自测，**不得**用于对外报告。')
    ap.add_argument('--band', default='ALL',
                    help='波段＝池内 id 前缀（A|B|C|…|ALL）；ALL＝全池不筛')
    ap.add_argument('--words', default=None,
                    help='逗号分隔词表（整体覆盖默认词表；空＝用默认反例导向词表）')
    ap.add_argument('--layer', default='both', choices=['both', 'verbatim', 'paraphrase'],
                    help='both＝两层都报（默认）／verbatim＝只报原文（逐字）层／paraphrase＝只报仅转述层')
    ap.add_argument('--out', default=None, help='报告 .md（默认 .work/<task>/pool-counterexamples-<band>.md）')
    ap.add_argument('--json', dest='json_out', default=None,
                    help='候选 .json（默认 .work/<task>/pool-counterexamples-<band>.json）')
    ap.add_argument('--exclude', default=None,
                    help='已被该答案引用的 id 清单文件（用于算"剔除已引用后剩余 M 条"）')
    ap.add_argument('--pool', default=None, help='池路径（默认为 .work/<task>/verified.md）')
    # ── 等式机核（--check · 2026-09-21 第2条收敛批）──────────────────────────
    ap.add_argument('--check', dest='check_ans', default=None, metavar='答案.md',
                    help='🔴 等式机核：解析答案的处置清单，与工具命中集合 T 做集合运算；'
                         '差异集非空／有「未处置」/ 「不列」无理由 ⇒ rc=1。**只读答案**')
    ap.add_argument('--n-head', default='列入', help='答案里"列入"段的标题关键词（默认 `列入`）')
    ap.add_argument('--m-head', default='逐条说明不列', help='答案里"不列"段的标题关键词（默认 `逐条说明不列`）')
    ap.add_argument('--must-head', default='必列清单',
                    help='答案里"必列清单"段的标题关键词（§27.1 机核③ 用；默认 `必列清单`）。'
                         '只认段内**行首**的 id。')
    ap.add_argument('--format', dest='fmt', default='auto', choices=['auto', 'manifest', 'lenient'],
                    help='auto（默认，先按清单形态、失败回落到宽松并照实报弱）／manifest（只认清单）'
                         '／lenient（只做宽松扫描）')
    ap.add_argument('--limit-unhandled', type=int, default=None, metavar='N',
                    help='允许的"未处置＋差异集"上限（默认不设限：非空即 rc=1）')
    ap.add_argument('--write-template', default=None, metavar='输出.md',
                    help='按工具命中集合 T 生成**处置清单模板**（作答前置：一 id 一行，不许删并）')
    a = ap.parse_args()

    # 机核模式：不重扫池，只读工具读数 JSON ＋ 答案文件
    if a.write_template:
        n = write_template(a.task, (a.band or 'ALL').strip(), a.json_out, a.write_template)
        print('处置清单模板：%s（%d 行 ＝ 工具命中集合 T）' % (a.write_template, n))
        print('⇒ 作答时逐行填「处置」；再用 --check 机核。')
        return 0
    if a.check_ans:
        rc, rep = check_answer(a.task, (a.band or 'ALL').strip(), a.check_ans,
                               a.n_head, a.m_head, a.fmt, a.out, a.limit_unhandled,
                               json_path=a.json_out, must_head=a.must_head)
        out = a.out or os.path.join(ROOT, '.work', a.task,
                                    'counterexample-equation-check-%s.md' % (a.band or 'ALL').strip())
        if rc != 2:
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            io.open(out, 'w', encoding='utf-8', newline='\n').write(rep)
        print(rep)
        print('报告：%s' % (out if rc != 2 else '（未生成：前置条件不满足）'))
        print('退出码：%d（0=等式机核通过 ／ 1=不通过 ／ 2=前置条件不满足）' % rc)
        return rc

    work = os.path.join(ROOT, '.work', a.task)
    pool_path = a.pool or os.path.join(work, 'verified.md')
    if not os.path.exists(pool_path):
        raise SystemExit('🔴 池不存在：%s' % pool_path)
    spec, spec_path = M.load_spec(a.task)

    words = ([w.strip() for w in a.words.split(',') if w.strip()]
             if a.words is not None else list(DEFAULT_WORDS))
    band = (a.band or 'ALL').strip()
    rows = parse_pool(pool_path)
    # ⚠ 2026-09-24 新增（闸缺陷台账 `G-41`）：**「池文件在、但解析出 0 条」过去会静默算过（rc=0）** ——
    #   报告里那句"等式机核 rc=0"会被读成"第 2 条达标"，而它其实**没有对簿对象**（`A-143` 家族：空转不像空转）。
    #   判据（由两位独立判官在 `yuanze-cwo`／`fei-lixing-fanrong` 上各复现一次）：`池 0 条`／`T=0` ⇒
    #   **不是通过，是"本册无对簿对象"**。现在：默认 **rc=1＋首行声明**；确需空池跑脚手架时用 `--allow-empty-pool`。
    if not rows and not getattr(a, 'allow_empty_pool', False):
        print('🔴 本册**无对簿对象**：池文件在（`%s`）但**解析出 0 条** ⇒ 等式与判项**不可执行**。'
              % os.path.relpath(pool_path, ROOT))
        print('   ⇒ 这一格**不得记为通过**（闸缺陷台账 `G-41`）。若池确实还没建，请先补池；'
              '若只是脚手架自测，可显式加 `--allow-empty-pool`。')
        return 1
    if band.upper() != 'ALL':
        rows_b = [r for r in rows if r['band'].upper() == band.upper()]
    else:
        rows_b = list(rows)
    pt = PageText(a.task, work, spec)
    hits, n1, n2 = scan(rows_b, words, a.layer, pt)
    T = len(hits)

    ex = read_exclude(a.exclude)
    ex_set = set(ex)
    left = [h for h in hits if h['id'] not in ex_set]
    M_left = len(left)

    out = a.out or os.path.join(work, 'pool-counterexamples-%s.md' % band)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    L = [IDEMPOTENT_MARK, '',
         '# 反例覆盖 · 机械扫描读数（任务 `%s` ｜ 波段 `%s`）' % (a.task, band), '',
         '> 工装：`tools\\scan_pool_counterexamples.py`（任务通用 · 零模型调用 · 只读）',
         '> 池：`%s`（%d 条）｜ 本波段：**%d 条** ｜ 页文本层：%s'
         % (os.path.relpath(pool_path, ROOT).replace('\\', '/'), len(rows), len(rows_b), pt.mode),
         '> 分层口径：`N1`＝命中词落在该条**「原文（逐字）」**字段内；'
         '`N2`＝原文层未命中但落在**「转述」**字段内；`T = N1 + N2`（同条只算一次）。', '',
         '## 一、参数（可复算）', '',
         '| 参数 | 值 |', '|---|---|',
         '| `--task` | `%s` |' % a.task,
         '| `--band` | `%s`（池内 id 前缀；ALL＝不筛） |' % band,
         '| `--layer` | `%s` |' % a.layer,
         '| `--words` | %s（**%d 词**） |'
         % ('默认反例导向词表' if a.words is None else '**调用侧传入**', len(words)),
         '| `--exclude` | %s |' % (('`%s`（%d 个 id）'
                                    % (os.path.basename(a.exclude), len(ex))) if a.exclude else '未给'),
         '| 本册配置 | `%s` |' % os.path.relpath(spec_path, ROOT).replace('\\', '/'),
         '',
         '### 词表（逐词照登）', '',
         '`' + '`／`'.join(words) + '`', '']
    if a.words is None:
        L += ['> 默认词表的分组覆盖（判官可据此核对"类目有没有漏"）：', '']
        for gname, gwords in WORD_GROUPS:
            L.append('- **%s**：%s' % (gname, '／'.join(gwords)))
        L.append('')
        L += ['> **成对规则**（两项同现于同一字段才算命中；报告里写成 `较+严重`）：', '']
        for a1, bs in PAIR_RULES:
            L.append('- `%s` ＋ 任一（%s）' % (a1, '／'.join(bs)))
        L.append('')
        L += ['> 🔴 **第 ⑤ 组「方向性反证」与第 ⑥ 组「比较方向」均为 2026-09-21 实测补入**：'
              '只扫前四组会系统性漏掉「因果次序相反／方向相反／回升」与「比较算子性反证」'
              '（成因见 `tools\\scan_pool_counterexamples.py` 的默认词表注记：'
              '实测 4 条漏项里 2 条属第⑤类；另一类只靠比较算子说话、不含①②③④⑤ 任何一词，'
              '**本件自证时又抓到一次**）。', '']

    L += ['## 二、分层计数（读数）', '',
          '| 层 | 条数 | 含义 |', '|---|---|---|',
          '| **原文（逐字）层 `N1`** | **%d** | 命中词在被引条目**原文**里逐字出现 ⇒ 硬证据 |' % n1,
          '| **仅转述层 `N2`** | **%d** | 只有**转述**字段命中 ⇒ 引用前须回池取原句 |' % n2,
          '| **合计 `T`** | **%d** | `T = N1 ＋ N2`（同条多词只计一次，当场可核） |' % T, '']
    for k, h in enumerate(hits, 1):
        pass
    L += ['> ⚠ 两层**不得混报**：把 `N2` 当 `N1` 报＝把"提取器的概括"当"书里这么写"（放松尺子）。', '',
          '## 三、候选项清单（每一行＝一条可逐条处置的候选）', '']
    if hits:
        L += md_table(hits)
    else:
        L.append('（本波段本词表：命中 0 条）')
    L.append('')

    L += ['## 四、剔除已引用后剩余', '']
    if a.exclude:
        L += ['- 已引用/已说明 id：**%d 个**（来自 `%s`）' % (len(ex), os.path.basename(a.exclude)),
              '- **剔除已引用后剩余 `M` ＝ %d 条**（`T %d － 列入/已说明 %d`）'
              % (M_left, T, T - M_left), '']
        if left:
            L += md_table(left)
        else:
            L.append('（本波段本词表：剔除已引用后剩余 0 条）')
    else:
        L.append('（未给 `--exclude`：本栏不计算。作答时必须传入**你自己已引用的 id 清单**，'
                 '否则"剔除已引用后剩余多少条"无法被第三方复算）')
    L.append('')

    L += ['## 五、自证', '',
          '- 本件与 `tools\\rquote_page_check.py` 共用**同一套**口径来源：'
          '池解析 `_bandid`／`verify_candidates`、页索引 `stage15_merge_task.build_page_index`'
          '（不得另写一份 —— A-72 同一判据写两遍＝改一处等于没改）。',
          '- 页文本层：%s；页序拼接串长度 ＝ **%d** 字（归一化口径）。'
          % (pt.mode, len(pt.concat)),
          '- 原句抽取＝**从页文本按偏移取句**（不是人工转写）：句界＝句末标点'
          '（。！？；）与页边界；句首 30 字＝该句归一化文本前 30 字。',
          '- 本报告与同名 `.json` 均带幂等标记 `%s`：**重复跑＝覆盖同一文件，不重复插入**。'
          % IDEMPOTENT_MARK,
          '- 退出码恒 0（读数器，不是闸）。', '']

    io.open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')

    json_out = a.json_out or os.path.join(work, 'pool-counterexamples-%s.json' % band)
    payload = dict(_mark=IDEMPOTENT_MARK, tool='scan_pool_counterexamples.py',
                   task=a.task, band=band, layer=a.layer, words=words,
                   pool=pool_path, pool_total=len(rows), band_total=len(rows_b),
                   pages_mode=pt.mode, concat_len=len(pt.concat),
                   N1=n1, N2=n2, T=T,
                   exclude_count=len(ex), M_left=M_left,
                   exclude=ex, hits=hits, left=left)
    io.open(json_out, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(payload, ensure_ascii=False, indent=1) + '\n')

    print('任务 %s ｜ 波段 %s ｜ 池 %d 条 ｜ 本波段 %d 条' % (a.task, band, len(rows), len(rows_b)))
    print('词表 %d 词 ｜ 层 %s' % (len(words), a.layer))
    print('读数：原文（逐字）层 N1=%d ｜ 仅转述层 N2=%d ｜ 合计 T=%d' % (n1, n2, T))
    if a.exclude:
        print('剔除已引用 %d 个 id 后剩余 M=%d' % (len(ex), M_left))
    print('报告：%s' % out)
    print('候选：%s' % json_out)
    return 0


# ── 自证（语法级正／负样本）─────────────────────────────────────────────────
def selftest():
    bad = []
    # ① 默认词表必须含判官点名的全部词（缺一个＝漏一类反证）
    must = ['例外', '反例', '并非所有', '并不是所有', '唯一', '巧合', '不对称', '相反',
            '然而', '却', '也', '幸免', '逃过', '未被卷入', '没有卷入', '并未引爆',
            '无定论', '莫衷一是', '罕见', '回升', '逆', '反向', '高于']
    miss = [w for w in must if w not in DEFAULT_WORDS]
    if miss:
        bad.append('默认词表缺词：%s' % '／'.join(miss))
    flat = [w for _g, ws in WORD_GROUPS for w in ws]
    if sorted(flat) != sorted(DEFAULT_WORDS):
        bad.append('WORD_GROUPS 与 DEFAULT_WORDS 不对齐（分组表必须覆盖全词表）')
    if not PAIR_RULES:
        bad.append('PAIR_RULES 为空（比较方向类目会漏）')
    # ①-b 成对规则：比较算子反证（E-201 型）必须被吃到
    if not match_terms('美国受影响远较欧元区国家严重', []):
        bad.append('成对规则未命中「较+严重」型比较反证')
    if '高于' not in match_terms('英美两国的经济增速明显高于欧元区国家', DEFAULT_WORDS):
        bad.append('比较方向词「高于」未命中（E-201 型反证会漏）')
    # ② 锚归一化：单页／区间／多段
    if anchor_pages('s223') != [223]:
        bad.append('anchor_pages 单页错')
    if anchor_pages('s137-139') != [137, 138, 139]:
        bad.append('anchor_pages 区间错')
    if anchor_pages('s10, s12') != [10, 12]:
        bad.append('anchor_pages 多段错')
    if anchor_pages('NOANCHOR') != []:
        bad.append('anchor_pages 无锚应为空')
    # ③ 池解析标签容错（逐字原文／原文；转述／概述）
    fake_pool = ('### E-999  [CA] [技能=S3]\n- 锚：s10\n'
                 '- 原文（逐字）：「甲却乙」\n- 转述：甲丙乙\n\n'
                 '### E-998  [PR] [技能=S3]\n- 锚：s11\n'
                 '- 原文：「无关键词」\n- 概述：这里出现了例外\n\n')
    rows = parse_pool_text(fake_pool)
    if len(rows) != 2 or rows[0]['quote'] != '甲却乙' or rows[1]['transcript'] != '这里出现了例外':
        bad.append('池解析／标签容错错：%s' % rows)
    # ④ 分层口径：只命中转述 ⇒ N2；两层都命中 ⇒ 只算 N1
    pt = PageText.__new__(PageText)
    pt.concat = '甲却乙。甲丙乙。'
    pt.bounds = [(0, len(pt.concat), 10)]
    pt.mode = 'selftest'
    hits, n1, n2 = scan(rows, ['却', '例外'], 'both', pt)
    if (n1, n2, len(hits)) != (1, 1, 2):
        bad.append('分层计数错：期望 (N1,N2,T)=(1,1,2)，实得 %s' % ((n1, n2, len(hits)),))
    # ⑤ 句界：句首 30 字必须止于句末标点
    seg, _lo, _hi = pt.sentence_at(0, '却')
    if seg != '甲却乙。':
        bad.append('句界抽取错：%r' % seg)
    # ⑥ 页映射：偏移落到第二页时必须报第二页
    pt2 = PageText.__new__(PageText)
    pt2.concat = 'AAAABBBB'
    pt2.bounds = [(0, 4, 21), (4, 8, 22)]
    pt2.mode = 'selftest'
    if pt2.page_at(5) != 22 or pt2.page_at(3) != 21:
        bad.append('页映射错')
    # ⑦ 等式机核（--check）：正样本 1 组 ＋ 负样本 3 组（**都必须是合成的，不许读真答案**）
    _b, _stat = _selftest_check()
    bad += _b
    for b in bad:
        print('🔴 %s' % b)
    if bad:
        return 1
    print('✔ scan_pool_counterexamples 自证通过（默认词表 %d 词）\n'
          '  ／等式机核自证：正 %d ＋ 负 %d 组全中（计数由 mark() 当场累加，不写死）'
          % (len(DEFAULT_WORDS), _stat['pos'], _stat['neg']))
    return 0


def _selftest_check():
    """等式机核的正／负样本自证。

    ⚠ 为什么必须自证这一段：**闸自己假通过比没有闸更危险**（避坑手册 A-36…A-39）。
    本段用**合成文件**在临时目录里跑，读的是自己造的 JSON 与答案，
    不碰任何真实任务数据（避免"自证依赖被测对象"）。
    """
    import shutil
    import tempfile
    import builtins
    global ROOT
    bad = []
    # §27 批修订：正／负样本计数由**计数**得出，不再写死在汇总行里
    #   （旧版汇总行硬写「正 7 ＋ 负 6」，加样本后即与事实不符 ＝ A-107 家族：自报≠实况）
    stat = {'pos': 0, 'neg': 0}

    def mark(kind):
        stat[kind] += 1
    tmp = tempfile.mkdtemp(prefix='spe-check-selftest-')
    old_root = ROOT
    try:
        task, band = 'selftest-task', 'E'
        work = os.path.join(tmp, '.work', task)
        os.makedirs(work, exist_ok=True)
        ids = ['E-%03d' % k for k in (1, 2, 3, 4, 5)]
        jp = os.path.join(work, 'pool-counterexamples-%s.json' % band)
        io.open(jp, 'w', encoding='utf-8', newline='\n').write(json.dumps(dict(
            _mark=IDEMPOTENT_MARK, task=task, band=band, T=len(ids),
            hits=[dict(id=i, anchor='s1', words=['例外'], layer='原文') for i in ids]),
            ensure_ascii=False, indent=1))
        ROOT = tmp

        def answer(rows, n_head='## 三、工具读数 133 条的处置（一）：列入', m_head='## 四、逐条说明不列',
                   must='auto'):
            """合成答案。`must='auto'`＝必列清单默认取全部「列入」条目（§27.1 机核③ 段）。
            `must=False`＝**故意不写**该段（用于负样本 I）；`must=[...]`＝指定必列 id。"""
            L = [n_head, '', '| id | 处置 | 为什么 |', '|---|---|---|']
            L += ['| `%s` | %s | %s |' % r for r in rows]
            L += ['', m_head, '', '（段存在即可）', '']
            if must == 'auto':
                must = [r[0] for r in rows if r[1] == STATUS_LISTED]
            if must is not False:
                L += ['', '## 五、必列清单', '']
                L += ['- `%s`｜依据：合成样本' % i for i in must]
                L += ['']
            p = os.path.join(tmp, 'ans-%d.md' % len(os.listdir(tmp)))
            io.open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(L))
            return p

        # §27.1 机核③ 段（合成样本必须自带「必列清单」，否则⑩ 判缺段 ⇒ rc=1）
        MUST_SEC = '## 五、必列清单\n\n- `E-001`｜样本\n- `E-002`｜样本\n- `E-003`｜样本\n'

        # 正样本：5 条全部有处置（3 列入 ＋ 2 不列且给了理由）⇒ 差异集空
        p_ok = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                       ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                       ('E-005', STATUS_UNLISTED, '边界条件')])
        mark('pos')
        rc, rep = check_answer(task, band, p_ok, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('等式机核正样本未通过（rc=%d）' % rc)
        if not re.search(r'差异集（无任何处置）\*\*\s*=\s*0', rep):
            bad.append('正样本报告未出现"差异集 = 0"')

        # 负样本 A：静默丢弃（少一条）
        p_miss = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                         ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义')])
        mark('neg')
        rc, rep = check_answer(task, band, p_miss, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '`E-005`' not in rep or '静默丢弃' not in rep:
            bad.append('等式机核负样本A（静默丢弃）未被拦下（rc=%d）' % rc)

        # 负样本 B：「未处置」不得交付
        p_pend = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                         ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                         ('E-005', STATUS_PENDING, '')])
        mark('neg')
        rc, rep = check_answer(task, band, p_pend, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or STATUS_PENDING not in rep:
            bad.append('等式机核负样本B（未处置）未被拦下（rc=%d）' % rc)

        # 负样本 C：“不列”却没写理由（第 2 轮的活体缺陷形态）
        p_noreason = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                             ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, ''),
                             ('E-005', STATUS_UNLISTED, '')])
        mark('neg')
        rc, rep = check_answer(task, band, p_noreason, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '没有' not in rep:
            bad.append('等式机核负样本C（不列无理由）未被拦下（rc=%d）' % rc)

        # 负样本 D：散在正文、不成清单 ⇒ 必须报"形态不可机核"（宽松口径不得单独达标）
        p_loose = os.path.join(tmp, 'ans-loose.md')
        io.open(p_loose, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n（本段对 `E-001` `E-002` `E-003` `E-004` `E-005` '
            '一律不作登记，只在这里提一次 id）\n\n## 四、逐条说明不列\n\n（段存在）\n')
        mark('neg')
        rc, rep = check_answer(task, band, p_loose, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '形态不可机核' not in rep:
            bad.append('等式机核负样本D（只提 id、不登记处置）未被拦下（rc=%d）' % rc)

        # 正样本 4（§27 批新增）：自报数与机核数**一致** ⇒ rc=0；**不一致 ⇒ rc=1**
        p_sr_ok = os.path.join(tmp, 'ans-srok.md')
        io.open(p_sr_ok, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n本表：列入 3 ／ 不列 2（与机核一致）\n\n'
            '| id | 处置 | 为什么 |\n|---|---|---|\n'
            '| `E-001` | 列入 | — |\n| `E-002` | 列入 | — |\n| `E-003` | 列入 | — |\n'
            '| `E-004` | 不列 | 同词不同义 |\n| `E-005` | 不列 | 边界条件 |\n\n'
            '## 四、逐条说明不列\n\n（段存在）\n\n' + MUST_SEC)
        mark('pos')
        rc, rep = check_answer(task, band, p_sr_ok, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('正样本4（自报数＝机核数）被误拦（rc=%d）' % rc)

        p_sr_bad = os.path.join(tmp, 'ans-srbad.md')
        io.open(p_sr_bad, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n本表：列入 5 ／ 不列 128（**与机核不符**）\n\n'
            '| id | 处置 | 为什么 |\n|---|---|---|\n'
            '| `E-001` | 列入 | — |\n| `E-002` | 列入 | — |\n| `E-003` | 列入 | — |\n'
            '| `E-004` | 不列 | 同词不同义 |\n| `E-005` | 不列 | 边界条件 |\n\n'
            '## 四、逐条说明不列\n\n（段存在）\n\n' + MUST_SEC)
        mark('neg')
        rc, rep = check_answer(task, band, p_sr_bad, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '自报数与机核数不一致' not in rep:
            bad.append('负样本F（自报 5／128 ≠ 机核 3／2）未被拦下（rc=%d）' % rc)

        # ── §27.1 机核③（必列清单全覆盖）的负样本：正样本走了新路径，还必须证明它**真会拦** ──
        #   ⚠ 若只加正样本，本项就成"只被自证过一半的闸"（A-38 家族：闸恒空转而不自知）。
        mark('neg')
        p_must_short = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                               ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                               ('E-005', STATUS_UNLISTED, '边界条件')],
                              must=['E-001', 'E-002', 'E-003', 'E-004'])   # E-004 只登记「不列」
        rc, rep = check_answer(task, band, p_must_short, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '必列清单未全覆盖' not in rep or '`E-004`' not in rep:
            bad.append('负样本H（必列清单含只登记「不列」的条目）未被拦下（rc=%d）' % rc)

        mark('neg')
        p_must_none = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                              ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                              ('E-005', STATUS_UNLISTED, '边界条件')], must=False)
        rc, rep = check_answer(task, band, p_must_none, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '无法判定' not in rep:
            bad.append('负样本I（缺「必列清单」段）未被拦下（rc=%d）' % rc)

        # 正样本 5（§27 批回归）：答案里**内嵌机核输出**（`且属 T  = 1` 这类行）不得被当成自报
        p_embed = os.path.join(tmp, 'ans-embed.md')
        io.open(p_embed, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n'
            '| id | 处置 | 为什么 |\n|---|---|---|\n'
            '| `E-001` | 列入 | — |\n| `E-002` | 列入 | — |\n| `E-003` | 列入 | — |\n'
            '| `E-004` | 不列 | 同词不同义 |\n| `E-005` | 不列 | 边界条件 |\n\n'
            '## 四、逐条说明不列\n\n（段存在）\n\n' + MUST_SEC +
            '```\n工具命中集合        T        = 5\n'
            '登记「列入」且属 T  = 3\n登记「不列」且属 T  = 2\n'
            '登记「未处置」属 T  = 0\n不属 T = 0\n```\n')
        mark('pos')
        rc, rep = check_answer(task, band, p_embed, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('正样本5（内嵌机核输出行被误当自报）产生假红（rc=%d）' % rc)

        # 正样本 6（§27 批）：**中文数字**自报数必须能解析且与机核一致
        p_cn = os.path.join(tmp, 'ans-cn.md')
        io.open(p_cn, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n本表：列入 三 ／ 不列 二\n\n'
            '| id | 处置 | 为什么 |\n|---|---|---|\n'
            '| `E-001` | 列入 | — |\n| `E-002` | 列入 | — |\n| `E-003` | 列入 | — |\n'
            '| `E-004` | 不列 | 同词不同义 |\n| `E-005` | 不列 | 边界条件 |\n\n'
            '## 四、逐条说明不列\n\n（段存在）\n\n' + MUST_SEC)
        mark('pos')
        rc, rep = check_answer(task, band, p_cn, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('正样本6（中文数字「列入 三 ／ 不列 二」）未通过（rc=%d）' % rc)
        if '解析不了' in rep and '／ 解析不了 0 处' not in rep:
            bad.append('正样本6：中文数字被判为"解析不了"（射程未覆盖）')

        # 负样本 G（§27 批）：答案提到 T 外 id 却**无任何处置区承载** ⇒ 必须拦（"挪到表外规避等式"形态）
        #   ⚠ 自证抓到的自身缺陷：首跑该样本**未被拦下**，根因有二——
        #     ① 该自证的 JSON 载荷**没写 `pool` 键** ⇒ `pool_ids` 为空、跨表判项的池内核被跳过；
        #     ② 结构判据首版几乎恒真（名录行也凑够字符）。两处都修后本样本才真被拦。
        pool_p = os.path.join(work, 'verified.md')
        io.open(pool_p, 'w', encoding='utf-8', newline='\n').write(
            '### E-001  [CA] [技能=S3]\n- 锚：s1\n- 原文（逐字）：「例外甲」\n\n'
            '### E-002  [CA] [技能=S3]\n- 锚：s1\n- 原文（逐字）：「例外乙」\n\n'
            '### E-003  [CA] [技能=S3]\n- 锚：s1\n- 原文（逐字）：「例外丙」\n\n'
            '### E-004  [CA] [技能=S3]\n- 锚：s1\n- 原文（逐字）：「例外丁」\n\n'
            '### E-005  [CA] [技能=S3]\n- 锚：s1\n- 原文（逐字）：「例外戊」\n\n'
            '### A-104  [CA] [技能=S3]\n- 锚：s57\n- 原文（逐字）：「波段 A 的必列条目」\n\n'
            '### Z-001  [CA] [技能=S3]\n- 锚：s9\n- 原文（逐字）：「波段 Z 的同节补列」\n')
        io.open(jp, 'w', encoding='utf-8', newline='\n').write(json.dumps(dict(
            _mark=IDEMPOTENT_MARK, task=task, band=band, T=len(ids), pool=pool_p,
            words=['例外'],
            hits=[dict(id=i, anchor='s1', words=['例外'], layer='原文', lead='例句') for i in ids]),
            ensure_ascii=False, indent=1))

        p_unprot = os.path.join(tmp, 'ans-unprot.md')
        io.open(p_unprot, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n本表：列入 3 ／ 不列 2\n\n'
            '| id | 处置 | 为什么 |\n|---|---|---|\n'
            '| `E-001` | 列入 | — |\n| `E-002` | 列入 | — |\n| `E-003` | 列入 | — |\n'
            '| `E-004` | 不列 | 同词不同义 |\n| `E-005` | 不列 | 边界条件 |\n\n'
            '## 四、逐条说明不列\n\n（段存在）\n\n' + MUST_SEC +
            '## 附：随手一提\n\n另见 `Z-001`。\n')
        mark('neg')
        rc, rep = check_answer(task, band, p_unprot, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '无任何承载' not in rep and '无任何处置区' not in rep:
            bad.append('负样本G（表外无承载）未被拦下（rc=%d）' % rc)


        p_formc = os.path.join(tmp, 'ans-formc.md')
        io.open(p_formc, 'w', encoding='utf-8', newline='\n').write(
            '## 三、列入\n\n`E-001`（列入）｜`E-002`（列入）｜`E-003`（列入）\n\n'
            '## 四、逐条说明不列\n\n`E-004`（不列，同词不同义）｜`E-005`（不列，边界条件）\n\n' + MUST_SEC)
        mark('pos')
        rc, rep = check_answer(task, band, p_formc, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0 or '清单·C' not in rep:
            bad.append('等式机核正样本2（形态 C 段内登记）未通过或未走严格路径（rc=%d）' % rc)

        # 正样本 J（§27.1 机核③ 新增）：**必列清单允许含 T 外 id**（T 只是下界），
        #   但必须已登记「列入」；T 外一律**仅告警**，与判项⑤ 口径一致（不得自相矛盾）。
        #   ⚠ 本样本必须放在 `pool_p` 建好之后：否则 Z-001 会被判"池内无此 id"而假红。
        mark('pos')
        p_must_out = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                             ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                             ('E-005', STATUS_UNLISTED, '边界条件'),
                             ('Z-001', STATUS_LISTED, '「波段 Z 的同节补列」')],
                            must=['E-001', 'E-002', 'E-003', 'Z-001'])
        rc, rep = check_answer(task, band, p_must_out, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('正样本J（必列清单含 T 外 id 且已列入）被误拦（rc=%d）' % rc)
        if '不在命中集合 T' not in rep:
            bad.append('正样本J：T 外必列未按「仅告警」登记（与判项⑤口径不一致）')

        # 正样本 3：**越界 id 只告警、不得影响 rc**（2026-09-21 抓到的假红回归）
        #   活体：上一版把 outside 也 bad.append ⇒ 第 ⑦ 项打印 PASS 而 rc=1（A-107 家族）。
        p_outside = answer([('E-001', STATUS_LISTED, ''), ('E-002', STATUS_LISTED, ''),
                            ('E-003', STATUS_LISTED, ''), ('E-004', STATUS_UNLISTED, '同词不同义'),
                            ('E-005', STATUS_UNLISTED, '边界条件'),
                            ('A-104', STATUS_UNLISTED, '波段 A，属件内必列清单')])
        mark('pos')
        rc, rep = check_answer(task, band, p_outside, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 0:
            bad.append('越界 id（不属 T）把机核判成不通过（rc=%d）—— 告警不得影响 rc' % rc)
        if '告警' not in rep:
            bad.append('越界 id 未出现在"告警（不判失败）"栏')

        # 负样本 E：引用 ≠ 处置（段外引用同一 id，不得被算成已处置）
        p_refonly = os.path.join(tmp, 'ans-refonly.md')
        io.open(p_refonly, 'w', encoding='utf-8', newline='\n').write(
            '## 一、主张\n\n本答案引用了 `E-005`（见 §2.1）。\n\n'
            '## 三、列入\n\n`E-001`（列入）｜`E-002`（列入）｜`E-003`（列入）\n\n'
            '## 四、逐条说明不列\n\n`E-004`（不列，同词不同义）\n')
        mark('neg')
        rc, rep = check_answer(task, band, p_refonly, '列入', '不列', 'auto', None, None, json_path=jp)
        if rc != 1 or '`E-005`' not in rep:
            bad.append('等式机核负样本E（段外引用被误算成处置）未被拦下（rc=%d）' % rc)

        # 正样本 2：--write-template 生成的行数必须 ＝ T
        tp = os.path.join(tmp, 'tpl.md')
        n = write_template(task, band, jp, tp)
        if n != len(ids):
            bad.append('模板行数 ≠ T（%d vs %d）' % (n, len(ids)))
        # 幂等：同一模板重复写＝逐字节相同
        h1 = hashlib.sha256(io.open(tp, 'rb').read()).hexdigest()
        write_template(task, band, jp, tp)
        if hashlib.sha256(io.open(tp, 'rb').read()).hexdigest() != h1:
            bad.append('模板写入不幂等（两次 sha256 不同）')
    finally:
        ROOT = old_root
        shutil.rmtree(tmp, ignore_errors=True)
    return bad, stat


def parse_pool_text(txt):
    """自证用的纯文本入口（与 parse_pool 同口径，不碰文件）。"""
    rows = []
    for blk in BID.split_blocks(txt):
        m = VC.ENTRY.match(blk.split('\n')[0])
        if not m:
            continue
        q = QUOTE_LABEL.search(blk)
        tr = TRANSCRIPT_LABEL.search(blk)
        an = VC.ANCHOR.search(blk)
        rows.append(dict(id='%s-%s' % (m.group(1), m.group(2)), band=m.group(1),
                         anchor=(an.group(1).strip() if an else ''),
                         quote=(q.group(1) if q else ''),
                         transcript=(tr.group(1) if tr else '')))
    return rows


if __name__ == '__main__':
    if '--selftest-exhaustive' in sys.argv:
        sys.exit(_exhaustive_selftest())
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n🔴 本步骤无法执行：%s: %s\n'
                         '   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n'
                         % (type(_e).__name__, _e))
        sys.exit(2)

