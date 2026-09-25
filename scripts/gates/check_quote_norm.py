# -*- coding: utf-8 -*-
r"""check_quote_norm.py —— **引文比对归一化的自证器**（`G-52` 第 ③ 项 ＋ `G-57` 的分歧探针）

## 它回答两个问题
1. **跨行引文会不会被误判"不在书里"？**（`G-52`：判官两次 `NOT FOUND` 其实是断行所致）
2. **两把尺子（`verify_layer_quotes.norm` 与 `verify_candidates.norm_match`）会不会给出不同结论？**（`G-57`：同一事实两处实现 ⇒ 可能"一手绿一手红"）

## 用法
    python tools\check_quote_norm.py            # 跑三组样本并印两把尺子的结论
    python tools\check_quote_norm.py --json
退出码：0 ＝ 三组期望全部成立；1 ＝ 有期望不成立（**说明归一化层坏了，此时引文核验读数不得采信**）
"""
import io
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify_candidates as VC            # noqa: E402
import verify_layer_quotes as VLQ         # noqa: E402

# 源文（故意在"非理性繁荣"处断行，模拟 PDF 转文本的硬换行）
SRC = ('……市场心理会把价格推到一个难以维系的高度。\n'
       '非理性\n'
       '繁荣就是指这种情况。\n'
       '……（下略）')

CASES = [
    ('正1 跨行引文（应当命中）', '非理性繁荣就是指这种情况。', True),
    ('正2 含全角标点的引文（应当命中）', '市场心理会把价格推到一个难以维系的高度。', True),
    ('负1 编造的句子（应当不命中）', '市场心理会把价格推到一个理性可维系的高度。', False),
]


def main():
    rows, ok_all = [], True
    for name, q, want in CASES:
        a = VLQ.norm(q) in VLQ.norm(SRC)          # 尺子甲（去空白＋去标点族）
        b = VC.norm_match(q) in VC.norm_match(SRC)  # 尺子乙（折空白＋标点族映射）
        ok = (a == want) and (b == want)
        diverge = (a != b)
        rows.append(dict(case=name, want=want, ruler_a=a, ruler_b=b, diverge=diverge, ok=ok))
        ok_all &= ok
    print('引文比对归一化自证（源文含硬换行）：')
    print('  %-28s %-6s %-8s %-8s %s' % ('样本', '期望', '尺子甲', '尺子乙', '结论'))
    for r in rows:
        print('  %-28s %-6s %-8s %-8s %s' % (r['case'], r['want'], r['ruler_a'], r['ruler_b'],
                                             '✔' if r['ok'] else '🔴'))
    dv = [r['case'] for r in rows if r['diverge']]
    print('  两把尺子结论不同的样本：%s' % ('、'.join(dv) if dv else '无（本组样本上一致）'))
    print('  结论：%s' % ('✔ 跨行引文能被正确判为命中、编造句被正确判为不命中' if ok_all
                        else '🔴 有样本不符 ⇒ **引文核验读数暂不可采信**（先修归一化，`G-52`／`G-57`）'))
    if '--json' in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
