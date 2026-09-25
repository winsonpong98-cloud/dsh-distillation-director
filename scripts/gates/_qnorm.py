# -*- coding: utf-8 -*-
"""引文比对归一化的**单一来源**（`G-57①` · 2026-09-24）。

两把尺子在此并排定义、各自是唯一权威实现（`A-72`：同一事实多处实现 ＝ 漂移温床）：
  ``norm_strip`` ——「层位引文」尺（`verify_layer_quotes`）：空白＋标点族**整删**；
  ``norm_ws``／``norm_match`` ——「候选/池形态」尺（`verify_candidates`）：标点变体**折叠到 ASCII 基形**后仅去空白。

两尺语义本就不同（**删** vs **折**），不互相冒充；本模块保证「归一化的任何改动只发生在这里」。
分歧探针：`tools\\check_quote_norm.py`（已挂 `postflight` ⑳）——三组样本上两尺结论必须一致；
不一致 ⇒ 引文核验读数不得采信（`G-57`：两把尺子会制造"一手绿一手红"）。
"""
import re

# 「层位引文」尺的整删字符类（原 `verify_layer_quotes.STRIP`，逐字迁入）：
# 空白（含全角空格 \u3000、零宽 \u200b）＋ 引号变体 ＋ 中西标点族 ＋ 强调记号。
# ⚠ G-65b 补遗（2026-09-25）：波浪号变体（〜 U+301C ／ ～ U+FF5E）属标点族，
#   原字符类漏收 ⇒ 技能引文「5〜6倍」对源文「5~6倍」两尺结论相反（G-57 复现，
#   实证 jingji/cn-external-asset-poise L25 等 3 条假 MISS）。补入即与姊妹尺
#   norm_match 的 QUOTE_MAP（301C/FF5E→'-'）语义对齐——是补全标点族，不是放宽。
STRIP = re.compile(r'[\s\u3000\u200b“”「」『』‘’〝〞〟"\'、。，；：！？…—－\-·．.,;:!?'
                   r'()（）《》〈〉\[\]【】*_`~|«»‹›\u301c\uff5e]')


def norm_strip(t):
    """层位引文尺：去空白（含全角/零宽）＋去标点族（原 `verify_layer_quotes.norm`，逐字迁入）。"""
    return STRIP.sub('', t)


def norm_ws(s):
    """候选/池尺第一段：仅去空白，**不动标点**（原 `verify_candidates.norm`，逐字迁入）。"""
    return re.sub(r"\s+", "", s)


# 「候选/池」尺的标点变体折叠表（原 `verify_candidates._QUOTE_MAP`，逐字迁入）：
# 引号变体 → ASCII 基形；破折/波浪变体 → '-'；省略变体 → '...'。
QUOTE_MAP = {
    '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u201f': '"',
    '\u300c': '"', '\u300d': '"', '\u300e': '"', '\u300f': '"',
    '\u2033': '"', '\uff02': '"', '\u00ab': '"', '\u00bb': '"',
    '\u2018': "'", '\u2019': "'", '\u201a': "'", '\u201b': "'",
    '\u3008': "'", '\u3009': "'", '\u2032': "'", '\uff07': "'",
    '\u2014': '-', '\u2013': '-', '\u2012': '-', '\u2015': '-',
    '\uff0d': '-', '\u2212': '-', '\u301c': '-', '\uff5e': '-', '\u007e': '-',
    '\u2026': '...', '\u22ef': '...',
}
PUNCT_TABLE = {ord(k): v for k, v in QUOTE_MAP.items()}


def norm_match(s):
    """候选/池尺：标点变体折叠到 ASCII 基形 ＋ 去空白（原 `verify_candidates.norm_match`，逐字迁入）。"""
    return norm_ws(s.translate(PUNCT_TABLE))
