# -*- coding: utf-8 -*-
r"""ocr_quality_check.py —— OCR 质检（手册 §2「乱码检测 → 问题页 32B 精修 → 复查 → 抽查」的机器层）

判据（每条都写明口径，避免"看起来像缺陷"当缺陷 —— 避坑手册 P-06）：

  G1 位置标记残留   `<|LOC_数字|>` 出现次数（手册 §2 明令清洗 `<|LOC_数字|>`）→ 计数 + 页清单
  G2 空/极短页       正文字符 < 40 且非图像页声明 → 疑漏检
  G3 图像页幻觉     同一页出现 ≥3 种**非中文非英文**字母（西里尔/日文假名/阿拉伯等），或
                     连续同一短语重复 ≥3 次 ⇒ 判"幻觉页"（实测 p1/p10 有此形态）
  G4 重复行          归一化后同一行出现 ≥3 次 ⇒ 疑似退化循环
  G5 乱码替换符      `�` 或连续 ≥4 个非字母数字符号
  G6 页覆盖          已处理页数 / 应为页数；缺页清单

输出：md 报告 ＋ json（页级明细），**必须显式传 --out**（V-11：写入型自检禁止覆盖交付文档）。

用法：
  python tools\ocr_quality_check.py --txt .work\manias-crashes\ocr.txt `
      --out .work\manias-crashes\ocr_quality.md --json-out .work\manias-crashes\ocr_quality.json
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

PAGE_RE = re.compile(r'^=====\s*\[PAGE (\d+)\]\s*=====\s*$', re.M)
# 非中文、非拉丁、非常见标点的字母区（西里尔／假名／阿拉伯／希伯来／希腊／谚文）
WEIRD = re.compile(r'[\u0400-\u04FF\u3040-\u30FF\u0600-\u06FF\u0590-\u05FF\u0370-\u03FF\uAC00-\uD7AF]')


def cjk_latin_len(s):
    return len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--txt', required=True)
    ap.add_argument('--out', required=True, help='md 报告输出路径（必填 · V-11）')
    ap.add_argument('--json-out', default='', help='页级明细 json（可选）')
    ap.add_argument('--expect-pages', type=int, default=0, help='应为页数（如 425）')
    a = ap.parse_args()

    raw = io.open(a.txt, encoding='utf-8', errors='replace').read()
    parts = PAGE_RE.split(raw)
    # parts = [前言, page1, text1, page2, text2, ...]
    pages = {}
    dup_keys = []
    for i in range(1, len(parts), 2):
        k = int(parts[i])
        if k in pages:
            dup_keys.append(k)          # A-35：页标记重复必须登记、不得静默覆盖
        pages[k] = (pages.get(k, '') + '\n' + parts[i + 1]).strip()

    rows = []
    for p in sorted(pages):
        t = pages[p]
        loc = len(re.findall(r'<\|LOC_\d+\|>', t))
        weird = len(set(WEIRD.findall(t)))
        body = cjk_latin_len(t)
        # 归一化行重复
        lines = [re.sub(r'\s+', '', l) for l in t.splitlines() if len(re.sub(r'\s+', '', l)) >= 8]
        rep = max(Counter(lines).values()) if lines else 0
        bad_char = t.count('\ufffd')
        image_page = '[本页为图像页' in t
        flags = []
        if loc:
            flags.append('G1_LOC残留x%d' % loc)
        if body < 40 and not image_page:
            flags.append('G2_极短(%d字)' % body)
        if weird >= 3:
            flags.append('G3_幻觉字符(%d种异域字母)' % weird)
        if rep >= 3:
            flags.append('G4_重复行x%d' % rep)
        if bad_char or re.search(r'[^\w\s]{4,}', t):
            # ⚠ 判据修正（2026-09-17 实测抓到**假警报** · 避坑手册 P-06「把看起来像缺陷的当缺陷」）：
            #   首版用"连续 ≥4 个非文字符号"⇒ 把**目录点线**（`………`）与**省略号**判成乱码，
            #   实测 p11–16（整页目录）＋p27/p217/p331（正文含《》与省略号）**全部误报**（9/9 假）。
            #   现排除两类**合法排版字符**后重判：①点线/省略号族（`.` `·` `…` `．` `。`）；
            #   ②成对书名号/引号/括号/破折号（`《》〈〉（）【】〔〕“”‘’——` 等）。
            cleaned = re.sub(r'[.．·…。\u2026]+', ' ', t)
            cleaned = re.sub(r'[《》〈〉「」『』（）()【】〔〕“”‘’"\'—－\-–_~、,，;；:：!！?？/\\|*#>+=%&@$^]+',
                             ' ', cleaned)
            if bad_char or re.search(r'[^\w\s]{4,}', cleaned):
                flags.append('G5_乱码符号')
        rows.append(dict(page=p, body_chars=body, loc_tokens=loc, weird_scripts=weird,
                         max_repeat_lines=rep, image_page=image_page, flags=flags))

    n_page = len(rows)
    g = Counter()
    for r in rows:
        for f in r['flags']:
            g[f.split('(')[0]] += 1
    missing = sorted(set(range(1, a.expect_pages + 1)) - set(pages)) if a.expect_pages else []
    total_loc = sum(r['loc_tokens'] for r in rows)
    total_body = sum(r['body_chars'] for r in rows)

    L = []
    A = L.append
    A('# OCR 质检报告（机器层）')
    A('')
    A('> 输入：`%s` ｜ 生成：机器判据（口径见脚本 docstring，六类判据全部写出）' % a.txt)
    A('> **本报告不含语义判断**：它只标"疑点页"，语义/精修决定权在主会话与 32B 精修环节。')
    A('')
    A('## 一、总览')
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 已处理页（有页标记） | %d |' % n_page)
    A('| 应为页数（--expect-pages） | %s |' % (a.expect_pages if a.expect_pages else '未指定'))
    A('| 缺页 | %d %s |' % (len(missing), (('（前 20：%s）' % missing[:20]) if missing else '')))
    A('| 重复页标记（A-35） | %d %s |' % (len(dup_keys), dup_keys[:20] if dup_keys else ''))
    A('| 正文可见字符总数（中日韩＋英数） | %d |' % total_body)
    A('| `<\\|LOC_n\\|>` 残留总数 | **%d** |' % total_loc)
    A('')
    A('## 二、判据命中分栏（各栏之和可当场核）')
    A('')
    A('| 判据 | 命中页数 | 含义 |')
    A('|---|---|---|')
    names = {'G1': '位置标记 `<\\|LOC_n\\|>` 残留（手册 §2 明令清洗）',
             'G2': '正文字符 <40 且未声明图像页 ⇒ 疑漏检',
             'G3': '≥3 种异域字母（西里尔/假名等）⇒ 疑幻觉',
             'G4': '归一化后同一行重复 ≥3 次 ⇒ 疑退化循环',
             'G5': '替换符或连续 ≥4 个非文字符号 ⇒ 乱码'}
    for k in ('G1', 'G2', 'G3', 'G4', 'G5'):
        A('| %s | %d | %s |' % (k, g.get(k, 0), names[k]))
    A('')
    A('## 三、疑点页清单（逐页可核）')
    A('')
    A('| 页 | 正文字符 | LOC | 异域字母 | 最大行重复 | 图像页声明 | 判据 |')
    A('|---|---|---|---|---|---|---|')
    for r in rows:
        if r['flags']:
            A('| %d | %d | %d | %d | %d | %s | %s |'
              % (r['page'], r['body_chars'], r['loc_tokens'], r['weird_scripts'],
                 r['max_repeat_lines'], '是' if r['image_page'] else '否', '；'.join(r['flags'])))
    if not any(r['flags'] for r in rows):
        A('| — | — | — | — | — | — | （无命中） |')
    A('')
    A('## 四、处置指引（手册 §2）')
    A('')
    A('- **G1**：清洗 `<\\|LOC_n\\|>`（可用 `tools\\ocr_clean.py`），清洗后复跑本报告，G1 必须归零；')
    A('- **G3/G4/G5**：问题页交 **32B 精修**（只修问题页，不重扫全书——省成本是 §0.3 的明写口径）；')
    A('- **G2**：先人工看图确认是否真为空白/插图页，再决定是否重扫该页。')

    p = os.path.abspath(a.out)
    # V-11：禁止把交付文档当自检输出（要求显式传参已由 argparse 保证；此处再拒一次 输出\ 目录）
    if os.sep + '输出' + os.sep in p:
        print('🔴 拒写：--out 指向交付目录 `输出/`（V-11 写入型自检禁令）')
        return 2
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    if a.json_out:
        io.open(a.json_out, 'w', encoding='utf-8', newline='\n').write(
            json.dumps({'txt': a.txt, 'pages': rows, 'summary': dict(g),
                        'missing_pages': missing, 'dup_page_markers': dup_keys,
                        'total_loc_tokens': total_loc, 'total_body_chars': total_body},
                       ensure_ascii=False, indent=1) + '\n')
    print('已写 %s' % p)
    print('页数=%d  LOC残留=%d  疑点页=%d  缺页=%d'
          % (n_page, total_loc, sum(1 for r in rows if r['flags']), len(missing)))
    print('判据分栏：%s' % dict(g))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n   多半是工作区脚手架/数据文件未就绪。\n'
                         '   请先运行：python tools/init_workspace.py <你的工作区根>\n' % (type(_e).__name__, _e))
        sys.exit(2)
