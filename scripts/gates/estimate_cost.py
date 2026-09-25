# -*- coding: utf-8 -*-
r"""estimate_cost.py —— **事前**单册成本预估器（任务通用 · 费率外置）

为什么要它（2026-09-20）：用户要的是"**成本可预期**"——现有的是**事后**实测账本（`cost_meter`／`cost_attrib`），
  但"预期"必须在**开工前**给出。本工具补这一层，并可对历史册回测（`--actual` 校核区间是否覆盖实际）。

判据（费率取自 `tools\cost_rates.json`，本脚本**不含任何一册的数据**）：
  ① 书况 → 走哪条 OCR 路径：文本层均值 ≥ `low_density_chars_per_page` ⇒ **文字版（免 OCR，¥0）**；否则扫描版；
  ② OCR 段 = 页数 × 原生视觉费率（或免费档 ¥0，附带污染风险 → 追加清污估算区间）；
  ③ 蒸馏段 = `distill_base` ×（乐观 0.85 ／ 基准 1.0 ／ 悲观 1.15）；
  ④ 返工预留 = `rework_base` ×（0.5 ／ 1.0 ／ 1.5）；
  ⑤ 风险加价：页数 > `long_book_pages`、首跑新书族、扫描版且走免费档（污染）；
  ⑥ 输出**三档区间 ＋ 逐项依据 ＋ 免责**；`--actual` 时给"区间是否覆盖实际／基准偏差%"。

用法：
  python tools\estimate_cost.py --pdf <PDF路径> --out <报告.md>            # 自动探测书况
  python tools\estimate_cost.py --pages 260 --chars-per-page 527 --out <报告.md>
  python tools\estimate_cost.py --pages 425 --chars-per-page 0.15 --actual 18.14 --out <报告.md>   # 回测
退出码：0 = 跑通；1 = 参数不足／费率表缺失
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
RATES = os.path.join(HERE, 'cost_rates.json')


def probe_pdf(pdf):
    """调既有的唯一权威探测（pdf_to_text.py --probe），解析页数与文本层均值。"""
    exe = sys.executable
    r = subprocess.run([exe, os.path.join(HERE, 'pdf_to_text.py'), '--pdf', pdf, '--probe'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (r.stdout or '') + (r.stderr or '')
    m_pages = re.search(r'页数\s*(\d+)', out)
    m_per = re.search(r'均值\s*([\d.]+)\s*字符/页', out)
    if not m_pages or not m_per:
        raise RuntimeError('探测输出无法解析：\n' + out[:600])
    return int(m_pages.group(1)), float(m_per.group(1)), out.strip()


def band(v, lo, hi):
    return round(v * lo, 2), round(v, 2), round(v * hi, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf', default=None)
    ap.add_argument('--pages', type=int, default=None)
    ap.add_argument('--chars-per-page', type=float, default=None, dest='cpp')
    ap.add_argument('--ocr-mode', choices=['vision', 'free'], default='vision', dest='ocr_mode')
    ap.add_argument('--first-in-family', action='store_true', dest='first')
    ap.add_argument('--actual', type=float, default=None, help='事后实测金额（回测用，单册全程）')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    if not os.path.exists(RATES):
        print('🔴 缺费率表：%s' % RATES); return 1
    R = json.load(io.open(RATES, encoding='utf-8'))

    probe_txt = ''
    if a.pdf:
        pages, cpp, probe_txt = probe_pdf(a.pdf)
    elif a.pages is not None and a.cpp is not None:
        pages, cpp = a.pages, a.cpp
    else:
        print('🔴 需给 --pdf，或同时给 --pages 与 --chars-per-page'); return 1

    is_text = cpp >= R['low_density_chars_per_page']
    risk = []
    if is_text:
        ocr_l = ocr_b = ocr_h = 0.0
        risk.append('文本层均值 %.0f 字符/页 ≥ %d ⇒ **文字版**，直抽免 OCR（¥0）' % (cpp, R['low_density_chars_per_page']))
    else:
        if a.ocr_mode == 'free':
            ocr_l, ocr_b = 0.0, 0.0
            ocr_h = round(pages * R['ocr_scrub_per_page_high'], 2)
            risk.append('扫描版＋免费档 OCR：OCR 段本身 ¥0，但**免费档实测疑点页 46%%** ⇒ 悲观档含清污估算 %.2f–%.2f 元/页（**该单价未实测，属估算**）'
                        % (R['ocr_scrub_per_page_low'], R['ocr_scrub_per_page_high']))
        else:
            ocr_l = ocr_b = round(pages * R['ocr_per_page_vision'], 2)
            ocr_h = ocr_b
            risk.append('扫描版＋原生视觉引擎：%.4f 元/页 × %d 页（该费率为实测反推）' % (R['ocr_per_page_vision'], pages))
    if pages > R['long_book_pages']:
        risk.append('页数 %d > %d ⇒ 蒸馏段与返工预留各上浮（长书更易分期返工）' % (pages, R['long_book_pages']))

    d_l, d_b, d_h = band(R['distill_base'], R['distill_spread_low'], R['distill_spread_high'])
    r_l, r_b, r_h = band(R['rework_base'], R['rework_spread_low'], R['rework_spread_high'])
    if a.first:
        f = R['first_in_family_surcharge']
        d_l, d_b, d_h = round(d_l * f, 2), round(d_b * f, 2), round(d_h * f, 2)
        risk.append('首跑新书族（无既有同族件可让位/复用）⇒ 蒸馏段 ×%.2f（路由与让位回改风险）' % f)
    if pages > R['long_book_pages']:
        s = R['long_book_surcharge']
        d_l, d_b, d_h = round(d_l * s, 2), round(d_b * s, 2), round(d_h * s, 2)
        r_l, r_b, r_h = round(r_l * s, 2), round(r_b * s, 2), round(r_h * s, 2)

    tot_l = round(ocr_l + d_l + r_l, 2)
    tot_b = round(ocr_b + d_b + r_b, 2)
    tot_h = round(ocr_h + d_h + r_h, 2)

    L = ['# 单册蒸馏成本预估（事前）', '',
         '> 工装：`tools\\estimate_cost.py` ｜ 费率表：`tools\\cost_rates.json`（**改费率＝改模型**）',
         '> 输入：页数 %d ｜ 文本层均值 %.0f 字符/页 ｜ OCR 路径：%s%s' % (
             pages, cpp, '文字版（免 OCR）' if is_text else ('原生视觉' if a.ocr_mode == 'vision' else '免费档'),
             ' ｜ 首跑新书族' if a.first else ''),
         '']
    if probe_txt:
        L += ['## 书况探测（唯一权威：`pdf_to_text.py --probe`）', '', '```', probe_txt, '```', '']
    L += ['## 一、三档预估', '',
          '| 档 | OCR 段 | 蒸馏段 | 返工预留 | **合计** |', '|---|---|---|---|---|',
          '| 乐观 | %.2f | %.2f | %.2f | **%.2f** |' % (ocr_l, d_l, r_l, tot_l),
          '| **基准** | %.2f | %.2f | %.2f | **%.2f** |' % (ocr_b, d_b, r_b, tot_b),
          '| 悲观 | %.2f | %.2f | %.2f | **%.2f** |' % (ocr_h, d_h, r_h, tot_h), '',
          '## 二、逐项依据（风险因子）', '']
    for i, t in enumerate(risk, 1):
        L.append('%d. %s' % (i, t))
    L += ['', '## 三、免责与口径（必须与数字一起读）', '',
          '1. 预估依赖**当期费率与优惠**（空闲档半价、OCR 免费档）；费率一变即失效 ⇒ 本工具**报区间、不报单点**。',
          '2. 返工预留是**方法成本**（回改/补做/工装优化），两册实测均标"非纯量、含空闲期"，**无法剥离**。',
          '3. 蒸馏段与页数**弱相关**（两实测点：425 页 ¥13.26 ／ 260 页 ¥13.45）⇒ 决定成本的是"返工"与"OCR 是否污染"，不是页数。',
          '4. 清污单价**未实测**（现役路径工序归零）；本表用的是旧引擎路径的**估算**，已在表内标注。', '']

    if a.actual is not None:
        cov = '**覆盖 ✔**' if tot_l <= a.actual <= tot_h else '**未覆盖 🔴**'
        dev = 100.0 * (tot_b - a.actual) / a.actual
        L += ['## 四、回测校核（--actual %.2f）' % a.actual, '',
              '| 项 | 值 |', '|---|---|',
              '| 实测（单册全程） | **%.2f** |' % a.actual,
              '| 预估区间 | %.2f – %.2f |' % (tot_l, tot_h),
              '| 区间是否覆盖实测 | %s |' % cov,
              '| 基准档偏差 | **%+.1f%%** |' % dev, '',
              '（验收判据：区间覆盖实测 ∧ 基准偏差绝对值 ≤30%）', '']

    out = '\n'.join(L)
    io.open(a.out, 'w', encoding='utf-8').write(out + '\n')
    print(out)
    print('→ 已写入 %s' % a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
