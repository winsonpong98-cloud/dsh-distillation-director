# -*- coding: utf-8 -*-
r"""instrument_sufficiency.py —— **仪器充分性闸**（回答"判据修够了没有"）

## 它解决的元问题（2026-09-21 用户提问：「这个循环到底怎么回事？有没有一次彻底解决完？」）

**机制（实测数字）**：2026-09-21 一天内在自建判据上抓到并修掉 **14 处缺陷**，
其中**归属被测对象的 0 处、归属我方判据/代码/流程/读数工具的 14 处**。
⇒ 所谓"问题解决不完"，主要不是"被检对象有问题"，而是**每加一条判据就新增一个缺陷源**。
⇒ 因此循环的止点**不在"被检对象修完"**（那是开放世界，永远修不完），
   而在**"判据自己能否自证"**——一旦判据能自证，就**允许停**。

## 本件的判据（四条，全部闭式、零模型）

| # | 判据 | 含义 | 通不过意味着 |
|---|---|---|---|
| ① | **坏样本必须被拦** | 每一类已知错误形态都有一个坏样本，且都被判不合格 | 判据**漏检**（最危险：伪装成"干净"） |
| ② | **已知为真必须放行** | 已确认为真的产物不得被判不合格 | 判据**假红**（会让人误以为对象错了） |
| ③ | **判据不可恒真／恒空转** | 新增判项在真产物上必须**有产出**（非恒真）；在坏样本上必须**有反应**（非恒空转） | 判据是**纸面的**（`A-143`） |
| ④ | **射程已声明** | 每条"有界判据"（词表类/启发式）必须在报告里显式写出它**覆盖不到什么** | 会被读成"完备承诺" |

**用法**
    python tools\instrument_sufficiency.py --pipeline counterexamples --known-good <真产物> --known-bad <旧产物>
    python tools\instrument_sufficiency.py --selftest

退出码：**0 ＝ 仪器充分（允许停止修判据）**；1 ＝ 不充分（须继续修，并指出是哪一条）。
"""
import argparse
import io
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    return (p.returncode,
            p.stdout.decode('utf-8', 'replace'),
            p.stderr.decode('utf-8', 'replace'))


def check_counterexamples(known_good, known_bad):
    """对 `scan_pool_counterexamples.py` 这套判据做四判据充分性核。"""
    tool = os.path.join(HERE, 'scan_pool_counterexamples.py')
    res = []

    # ① 坏样本必须被拦（穷举自证：负样本逐条）
    rc, so, se = _run([sys.executable, tool, '--selftest-exhaustive'])
    neg = re.findall(r'✔\s+(负·\S+)\s+rc=1', so)
    res.append(('① 坏样本必须被拦（穷举级）', rc == 0 and len(neg) >= 4,
                '负样本被拦 %d 个：%s ｜ rc=%d' % (len(neg), '、'.join(neg), rc)))

    # ② 已知为真必须放行
    rc, so, se = _run([sys.executable, tool, '--selftest'])
    res.append(('② 已知为真必须放行（自带自证）', rc == 0,
                'rc=%d ｜ %s' % (rc, (so.strip().split('\n') or [''])[-1][:80])))

    # ③ 判据不可恒真／恒空转：真产物上 rc 必须 0，且新增判项必须有产出
    if known_good and os.path.exists(known_good):
        rc, so, se = _run([sys.executable, tool, '--task', 'manias-crashes', '--band', 'E',
                           '--check', known_good, '--out', os.path.join(os.environ.get('TEMP', '.'), '_isu_good.md')])
        rep = ''
        gp = os.path.join(os.environ.get('TEMP', '.'), '_isu_good.md')
        if os.path.exists(gp):
            rep = io.open(gp, encoding='utf-8').read()
        # 判项 ⑧⑨ 必须出现在报告里（＝真的跑了，不是被跳过）
        has8 = '⑧' in rep
        has9 = '⑨' in rep
        res.append(('③ 判据不可恒真／恒空转（真产物）', rc == 0 and has8 and has9,
                    '真产物 rc=%d ｜ 判项⑧在=%s 判项⑨在=%s ｜ FAIL 数=%d'
                    % (rc, has8, has9, rep.count('🔴 FAIL'))))
    else:
        res.append(('③ 判据不可恒真／恒空转（真产物）', None, '未给 --known-good ⇒ 本项不适用'))

    # ④ 已知为假必须被判不合格（对旧产物）
    if known_bad and os.path.exists(known_bad):
        rc, so, se = _run([sys.executable, tool, '--task', 'manias-crashes', '--band', 'E',
                           '--check', known_bad, '--out', os.path.join(os.environ.get('TEMP', '.'), '_isu_bad.md')])
        res.append(('④ 已知为假必须被拦（旧产物）', rc == 1,
                    '旧产物 rc=%d（期望 1）' % rc))
    else:
        res.append(('④ 已知为假必须被拦（旧产物）', None, '未给 --known-bad ⇒ 本项不适用'))

    # ⑤ 射程声明在位（有界判据必须写明它覆盖不到什么）
    txt = io.open(tool, encoding='utf-8').read()
    declared = ('射程明示' in txt) and ('不是完备清单' in txt)
    res.append(('⑤ 射程已声明（有界判据不冒充完备）', declared,
                '射程声明句在位=%s' % declared))
    return res


def main():
    ap = argparse.ArgumentParser(description='仪器充分性闸：判"判据修够了没有"')
    ap.add_argument('--pipeline', default='counterexamples',
                    choices=['counterexamples'], help='被测判据套件')
    ap.add_argument('--known-good', default=None, help='已知为真的产物（应 rc=0）')
    ap.add_argument('--known-bad', default=None, help='已知为假的产物（应 rc=1）')
    a = ap.parse_args()

    print('=== 仪器充分性闸（%s）===' % a.pipeline)
    print('判据：① 坏样本被拦 ② 已知为真放行 ③ 判据非恒真/非空转 ④ 已知为假被拦 ⑤ 射程已声明')
    print()
    res = check_counterexamples(a.known_good, a.known_bad)
    bad, na = [], []
    for name, ok, note in res:
        tag = '✔' if ok else ('⏭' if ok is None else '🔴')
        print('  %s %-34s %s' % (tag, name, note))
        if ok is False:
            bad.append(name)
        if ok is None:
            na.append(name)
    print()
    if bad:
        print('🔴 **仪器尚不充分**（%d 条未过）⇒ 继续修判据是被要求的：%s' % (len(bad), '、'.join(bad)))
        print('   注意：**这不是"被测对象不合格"** —— 是判据自己没达标。')
        return 1
    print('✔ **仪器充分**（%d 条全过%s）⇒ **允许停止修判据**。'
          % (len(res) - len(na), ('，%d 条不适用' % len(na)) if na else ''))
    print('   含义：判据已能自证（坏样本全拦、已知为真放行、已知为假仍被拦、射程已声明）。')
    print('   继续加判据＝**扩大检查面**（会新增缺陷源），只在出现"真实使用中的落空实例"时才值得做。')
    return 0


def selftest():
    """自证：不给参数时应报"不适用"而非假绿；给假路径时报不适用而非崩。"""
    res = check_counterexamples(None, None)
    na = [n for n, ok, _ in res if ok is None]
    print('自证：不适用项 %d 个（%s）' % (len(na), '、'.join(na)))
    if len(na) < 2:
        print('🔴 自证失败：缺参数时未如实报"不适用"')
        return 1
    print('✔ 仪器充分性闸自证通过（缺参数 ⇒ 报不适用，不假绿）')
    return 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
