# -*- coding: utf-8 -*-
r"""trigger_card.py —— **触发判定卡**（回答「什么时候做／什么时候不做，谁说了算」）

## 用户的问题（2026-09-21）

> 「如果这三点不是一定要做，那你怎么判定什么时候做、什么时候不做？
>  如果你能判，那就不需要每次都做——具体就需要你的判断或其他的要求。」

## 为什么"我自由裁量"不可接受（本件的立论）

"我能判断"与"我的判断可信"是**两件事**。自由裁量的失效形态正好是两条基线的**镜像**：
  · **漏判前置**（该触发而判不触发）⇒ 该做的没做（用户最初担心的形态）
  · **误判前置**（不该触发而硬触发）⇒ 做假动作（我上一轮已实证的三类损害）
⇒ 所以**判据不能是我"觉得"**，必须落成**可起草、可声明、可复核**的三件：
  ① **机器起草触发卡**（按问句形态给"疑似触发"清单，**不判终态**）
  ② **必填证据**：每个"触发/豁免"都必须带**问句里的原句片段**（机器回查该片段是否真在问句里）
  ③ **答案与卡一致**：答案若不按卡做（该探询却给了结论、该标外推却没有），由 `assertion_gate` 拦

## 卡的字段（固定五栏，一题一卡）

| 字段 | 取值 | 机器可判什么 |
|---|---|---|
| ① 问句类型 | `细节回源` / `跨章节论证` / `可迁移` / `诉求型` / `格式类` | 起草：按关键词与句形给疑似类型 |
| ② 点回原文 | `必须` / `豁免` ＋ 证据片段 | 机器核：证据片段是否真在问句内 |
| ③ 标注推测 | `必须` / `豁免` ＋ 证据片段 | 同上 |
| ④ 先追问 | `必须` / `豁免` ＋ 证据片段 | 同上；**豁免且问句含诉求词 ⇒ 必须写理由** |
| ⑤ 需补字段 | 逐条列（探询型必须非空） | 非空＝置 `assertion_gate` 的"缺信息槽"义务 |

## 用法

    python tools\trigger_card.py --question <问句.txt> [--out <卡.md>]        # 起草（人不改不许交付）
    python tools\trigger_card.py --card <卡.md> --question <问句.txt>          # 复核：证据片段是否真在问句里
    python tools\trigger_card.py --selftest

退出码：0 ＝ 卡合规（证据齐全且可查）；1 ＝ 卡不合规；2 ＝ 前置不满足。
"""
import argparse
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── 触发形态（**有界词表；射程已在报告里声明，不冒充完备**）──
PAT = {
    '细节回源': r'(书里|书中|原文|原话|哪一页|哪个锚|怎么说的|依据)',
    '跨章节论证': r'(跨章节|是否自洽|自洽性|论证.*完整|漏.*反例|反例.*齐)',
    '可迁移': r'(迁移|套用到|用在.*场景|如果.*今天|能不能用来|外推|推测)',
    '诉求型': r'(要不要|该不该|能不能|可不可以|帮我(?:看|判|分析)|我手里|我的持仓|'
            r'现在(?:买|卖|加|减|补|割)|亏了|赚了|该买|该卖|值得(?:买|卖))',
    '格式类': r'(压缩到|改写成|翻译|摘要|润色|换个格式|排版|转成 ?(?:pdf|docx|md))',
}
# 每条基线的触发源（哪些问句类型会触发它）
TRIGGER_MAP = {
    '点回原文': ('细节回源', '跨章节论证'),
    '标注推测': ('可迁移', '跨章节论证'),
    '先追问': ('诉求型',),
}
WEAK_ONLY = {'标注推测', '先追问'}      # 这两条在"非触发型"问句下**默认豁免但须声明**


def draft(question):
    """起草卡：逐条给"疑似触发 ＋ 命中词"，**不判终态**（终态由人/判官确认并写证据）。"""
    lines = ['# 触发判定卡（起草 · 未确认不得交付）', '',
             '> 起草＝机器按**有界词表**给的疑似清单；**终态须逐条确认并附问句原句片段**。',
             '> 射程声明：本判据只覆盖上列词表形态，**不在词表内的写法它看不见**（不冒充完备）。', '']
    kinds = {}
    for k, p in PAT.items():
        m = re.findall(p, question)
        if m:
            kinds[k] = m[:3]
    lines.append('| ① 问句类型 | 疑似 | 命中原句片段 |')
    lines.append('|---|---|---|')
    if kinds:
        for k, ms in kinds.items():
            lines.append('| %s | 疑似触发 | %s |' % (k, '、'.join('「%s」' % x for x in ms)))
    else:
        lines.append('| （未命中任何形态词） | **须人工定类型** | — |')
    lines.append('')
    lines.append('| ②③④ 三条基线 | 起草判态 | 必填：证据（问句原句片段） |')
    lines.append('|---|---|---|')
    for base, srcs in TRIGGER_MAP.items():
        hit = [k for k in srcs if k in kinds]
        guess = '必须' if hit else ('豁免（须写理由）' if base in WEAK_ONLY else '豁免')
        lines.append('| %s | **%s** | %s |' % (base, guess,
                    ('命中类型：%s' % '、'.join(hit)) if hit else '（空 ⇒ 请写豁免理由）'))
    lines.append('')
    lines.append('| ⑤ 需补字段 | 逐条列（④ 判"必须"时本栏不得为空） |')
    lines.append('|---|---|')
    lines.append('| ① | （待填：缺它影响哪一步） |')
    lines.append('| ② | （待填） |')
    lines.append('')
    lines.append('**确认栏**（人/判官必填）：`本卡已确认 ｜ 确认人=<谁> ｜ 与问句一致=是`')
    return '\n'.join(lines) + '\n'


def review(card_path, question):
    """复核卡：① 五栏齐备 ② 每条判态都有"问句原句片段"作证据 ③ 片段真在问句里 ④ 豁免须有理由。"""
    if not os.path.exists(card_path):
        return 2, '🔴 卡不存在：%s' % card_path
    c = io.open(card_path, encoding='utf-8').read()
    q = io.open(question, encoding='utf-8').read() if os.path.exists(question) else question
    fatal, warn = [], []
    rep = ['# 触发判定卡 · 复核', '', '| 判据 | 判态 | 证据 |', '|---|---|---|']

    # ① 确认栏（**须同时有"确认人"与"与问句一致"，且不得是模板占位**）
    #   ⚠ 自证连抓两轮自身缺陷：首版只查子串"本卡已确认"（草稿标题就有"确认栏"字样）；
    #     第二版查 `确认人\s*=\s*\S` —— **被草稿模板里的 `确认人=<谁>` 骗过**（`<谁>` 也算 \S）。
    #     终版：要求**独立成行**且**不含占位符**（`<>（）待?？`）。
    PH = '<>（）()待?？'
    def _ok_line(pat):
        for l in c.split('\n'):
            m = re.search(pat, l)
            if not m:
                continue
            val = m.group(1).strip()
            if val and not any(ch in PH for ch in val):
                return True
        return False
    has_who = _ok_line(r'确认人\s*[=＝:：]\s*([^\s｜|]{1,40})')
    has_agree = _ok_line(r'与问句一致\s*[=＝:：]\s*([^\s｜|]{1,10})') and \
        bool(re.search(r'与问句一致\s*[=＝:：]\s*(?:是|✔|一致)\s*$', c, re.M))
    ok1 = has_who and has_agree
    rep.append('| ① 确认栏到位（确认人 ＋ 与问句一致，且非占位） | %s | 确认人=%s ／ 与问句一致=是=%s |'
               % ('PASS' if ok1 else '🔴 FAIL', has_who, has_agree))
    if not ok1:
        fatal.append('① 卡未确认（须独立行写 `确认人=<实际的人>` 与 `与问句一致=是`；'
                     '模板占位 `<谁>`／`（待填）` 不算）——**起草稿不得当交付依据**')

    # ② 证据：每条基线的判态行必须带「」片段
    for base in TRIGGER_MAP:
        row = [l for l in c.split('\n') if l.startswith('|') and base in l and ('必须' in l or '豁免' in l)]
        if not row:
            fatal.append('② 缺「%s」判态行' % base)
            continue
        seg = row[0]
        frags = re.findall(r'「([^」]{2,60})」', seg)
        # 证据片段必须真在问句里（豁免理由除外）
        bad = [f for f in frags if f not in q]
        okb = bool(frags) and not bad
        rep.append('| ② %s 有证据且可查 | %s | 片段 %d 个 ／ 不在问句内 %d 个%s |'
                   % (base, 'PASS' if okb else '🔴 FAIL', len(frags), len(bad),
                      ('：' + '、'.join('「%s」' % x for x in bad[:2])) if bad else ''))
        if not frags:
            fatal.append('② 「%s」判态行**无证据片段**（必须是问句原句）' % base)
        if bad:
            fatal.append('② 「%s」的证据片段**不在问句里**（可能是编的）：%s'
                         % (base, '、'.join('「%s」' % x for x in bad[:2])))
        # ④ 豁免须写理由（不能只写"豁免"）
        if '豁免' in seg and not re.search(r'理由|因为|本题不涉及|不适用', seg) and not frags:
            warn.append('「%s」判"豁免"但既无证据也无理由' % base)

    text = '\n'.join(rep) + '\n\n## 结论\n\n'
    if fatal:
        text += '🔴 **卡不合规**（rc=1）：\n' + '\n'.join('- ' + x for x in fatal) + '\n'
    else:
        text += ('✔ **卡合规**：确认栏在位、三条基线各自有可查证据——'
                 '**答案必须与卡一致**（由 `assertion_gate.py` 逐条判）。\n')
    if warn:
        text += '\n### 告警\n' + '\n'.join('- ' + x for x in warn) + '\n'
    return (1 if fatal else 0), text


def selftest():
    """好 1 放行 ＋ 坏 4 全拦（卡缺确认栏／缺证据／证据不在问句里／证据是编的）。"""
    import tempfile
    bad = []
    tmp = tempfile.mkdtemp(prefix='tc-')
    q = os.path.join(tmp, 'q.txt')
    io.open(q, 'w', encoding='utf-8', newline='\n').write('这只转债亏了 8%，要不要割掉？书里怎么说的？')
    base = draft(io.open(q, encoding='utf-8').read())
    good = base.replace('（待填：缺它影响哪一步）', '成本价与持有期限（缺它无法判风险预算）') \
               .replace('（待填）', '资金用途') \
               .replace('| 点回原文 | **必须** | 命中类型：细节回源 |',
                        '| 点回原文 | **必须** | 「书里怎么说的」 |') \
               .replace('| 标注推测 | **豁免（须写理由）** | （空 ⇒ 请写豁免理由） |',
                        '| 标注推测 | **豁免** | 「要不要割掉」理由：本题不要求迁移 |') \
               .replace('| 先追问 | **必须** | 命中类型：诉求型 |',
                        '| 先追问 | **必须** | 「要不要割掉」 |') \
               + '\n本卡已确认 ｜ 确认人=主会话 ｜ 与问句一致=是\n'
    cases = {
        '好卡': (good, 0),
        '坏1 缺确认栏': (good.replace('本卡已确认 ｜ 确认人=主会话 ｜ 与问句一致=是', ''), 1),
        '坏1b 确认栏只有标题': (good.replace('本卡已确认 ｜ 确认人=主会话 ｜ 与问句一致=是',
                                      '（待确认）'), 1),
        '坏2 缺证据片段': (good.replace('| 先追问 | **必须** | 「要不要割掉」 |',
                                  '| 先追问 | **必须** |  |'), 1),
        '坏3 证据不在问句里': (good.replace('「书里怎么说的」', '「书里写着不能割」'), 1),
    }
    for name, (txt, want) in cases.items():
        p = os.path.join(tmp, name + '.md')
        io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
        rc, _ = review(p, q)
        good_rc = (rc == want)
        print('  %-4s %-20s rc=%d（期望 %d）' % ('✔' if good_rc else '🔴', name, rc, want))
        if not good_rc:
            bad.append('%s：期望 rc=%d 实得 rc=%d' % (name, want, rc))
    print()
    if bad:
        print('🔴 触发判定卡自证失败：%s' % '；'.join(bad))
        return 1
    print('✔ 触发判定卡自证通过（好 1 放行 ＋ 坏 3 全拦）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='触发判定卡（什么时候做／什么时候不做）')
    ap.add_argument('--question', help='问句文本文件')
    ap.add_argument('--card', help='已有卡（复核模式）')
    ap.add_argument('--out', help='输出卡 .md')
    a = ap.parse_args()
    if a.card and a.question:
        rc, text = review(a.card, a.question)
        print(text)
        print('退出码：%d（0=卡合规 ／ 1=不合规 ／ 2=前置不满足）' % rc)
        return rc
    if not a.question:
        ap.error('须给 --question（或 --card + --question）')
    q = io.open(a.question, encoding='utf-8').read() if os.path.exists(a.question) else a.question
    text = draft(q)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        io.open(a.out, 'w', encoding='utf-8', newline='\n').write(text)
        print('卡已起草：%s（**未确认不得交付**；确认后跑 `--card <该文件> --question <问句>` 复核）' % a.out)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
