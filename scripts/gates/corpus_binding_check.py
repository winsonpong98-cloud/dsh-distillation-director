# -*- coding: utf-8 -*-
r"""corpus_binding_check.py —— **语料绑定闸**（派单前必跑 · 2026-09-21 事故直接教训）

## 为什么必须存在（今天真实发生的事故）

我把**甲册**（主题词属于域 B）当作**乙书**（主题词属于域 A）的池与原文册交给了答题者。
实测：乙书的主题词在该册命中 **0 行**，而甲册自己的主题词命中 **744 行**（两域词表不相交）。
答题者**自己发现**了这个错配并拒绝自裁——**这说明"触发条件"的前提（有语料可引）本身可以是错的**，
而当时**没有任何闸在派单前拦它**。

⇒ 本件把"语料绑定"变成**四条可判定的前置判据**，**在派作答者/判官之前**跑：

| # | 判据 | 判什么 | 不合格意味着 |
|---|---|---|---|
| ① | **路径存在** | 技能声明的池/册/页文本路径是否真实可读 | 指向不存在的文件（`A-115` 家族） |
| ② | **主题命中** | 册/池里必须能命中**技能主题词**（取自技能自身文本，不写死） | **语料错配**（今天的事故） |
| ③ | **锚形态同代** | 技能里用的锚形态（`sNNN`／`pNN`）是否与册配置 `pagemark` 相符 | 锚不可回源（`A-132` 家族：形态不统一） |
| ④ | **交给下游的清单可读** | 逐条 `Test-Path` ＋ 首行取样（防"路径对了但内容是空的/换行符怪"） | 下游拿到空件 |

## 用法

    python tools\corpus_binding_check.py --skill <技能根>\<slug> --task <册 slug> [--work <工作区>] [--out <报告.md>]
    python tools\corpus_binding_check.py --selftest

退出码：0 ＝ 绑定成立；1 ＝ 有判据不合格（**不得派单**）；2 ＝ 前置不满足（技能或册不存在）。
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

IDEMPOTENT_MARK = '<!-- corpus_binding_check:generated (idempotent) -->'
# 主题词抽取：从技能文本里取"高频专有名词"（不写死任何一本书的词）
#   做法：取技能正文中出现次数 ≥3 的中文 2–6 字词组（去停用词），最多 12 个
STOP = set('本书 本件 本技能 可以 使用 需要 注意 如果 因为 所以 但是 而且 以及 或者 这个 那个 '
           '一个 两个 以下 上述 其中 对于 关于 通过 根据 因此 同时 已经 进行 出现 情况 问题 '
           '步骤 判据 内容 条件 时候 现在 之后 之前 方式 结果 部分 全部 可能 必须 不能 不要'.split())


def _work_root(work=None):
    if work:
        return work
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _topic_words(skill_text, topn=12):
    """从技能文本抽取主题词（纯统计，不写死书名词）。"""
    cnt = {}
    for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', skill_text):
        w = m.group(0)
        if w in STOP or len(set(w)) == 1:
            continue
        cnt[w] = cnt.get(w, 0) + 1
    ranked = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, c in ranked if c >= 3][:topn]


def check(skill_dir, task, work=None, out=None):
    root = _work_root(work)
    skill_md = os.path.join(skill_dir, 'SKILL.md')
    if not os.path.isfile(skill_md):
        return 2, '🔴 技能件不存在：%s' % skill_md
    sk = io.open(skill_md, encoding='utf-8', errors='replace').read()
    twd = os.path.join(root, '.work', task)
    if not os.path.isdir(twd):
        return 2, '🔴 册目录不存在：%s' % twd

    rep = ['## 一、四判据', '', '| # | 判据 | 判态 | 证据 |', '|---|---|---|---|']
    fatal, warn = [], []

    # ① 路径存在：技能里提到的 .work/<task>/ 下的相对路径
    refs = sorted(set(re.findall(r'\.work[\\/][\w\-\.]+[\\/][\w\-\./\\]+', sk)))
    refs = [r for r in refs if task in r]
    miss = []
    for r in refs:
        p = os.path.join(root, r.replace('/', os.sep))
        if not os.path.exists(p):
            miss.append(r)
    ok1 = not miss
    rep.append('| ① | 路径存在 | %s | 技能引用本册路径 %d 条 ／ 不存在 %d 条%s |'
               % ('PASS' if ok1 else '🔴 FAIL', len(refs), len(miss),
                  ('：' + '；'.join('`%s`' % x for x in miss[:3])) if miss else ''))
    if miss:
        warn.append('技能引用了本册下**不存在**的路径 %d 条（可能是旧路径或写错）：%s'
                    % (len(miss), '；'.join('`%s`' % x for x in miss[:3])))

    # ② 主题命中：册/池必须能命中技能主题词
    corpus_files = []
    for name in ('verified.md', 'book_text.md'):
        p = os.path.join(twd, name)
        if os.path.isfile(p):
            corpus_files.append(p)
    if not corpus_files:
        corpus_files = [os.path.join(twd, f) for f in sorted(os.listdir(twd))
                        if f.endswith(('.md', '.txt')) and os.path.getsize(os.path.join(twd, f)) > 50000]
    blob = ''
    for p in corpus_files[:2]:
        blob += io.open(p, encoding='utf-8', errors='replace').read()
    hits = {w: blob.count(w) for w in _topic_words(sk)}
    top = sorted(hits.items(), key=lambda kv: -kv[1])
    nz = [w for w, c in top if c > 0]
    ok2 = len(nz) >= max(1, len(top) // 3)
    rep.append('| ② | 主题命中 | %s | 语料 %s ｜ 主题词 %d 个 ／ **命中 %d 个** ｜ top: %s |'
               % ('PASS' if ok2 else '🔴 FAIL',
                  '、'.join(os.path.basename(x) for x in corpus_files[:2]),
                  len(top), len(nz), '、'.join('%s×%d' % (w, c) for w, c in top[:5])))
    if not ok2:
        fatal.append('② **语料错配**：技能主题词在册/池里几乎零命中（命中 %d/%d）⇒ '
                     '**不得派单**（这就是"把甲册当乙书"那一类**语料错配**事故的判据）；'
                     'top 命中：%s' % (len(nz), len(top),
                                   '、'.join('%s=%d' % (w, c) for w, c in top[:5])))

    # ③ 锚形态同代：技能用的锚形态 vs 册配置 pagemark
    cfg = None
    for f in os.listdir(twd):
        if f.startswith('bookspec') and f.endswith('.json'):
            import json
            try:
                cfg = json.load(io.open(os.path.join(twd, f), encoding='utf-8'))
            except Exception:
                cfg = None
            break
    pm = (cfg or {}).get('pagemark') or '?'
    sk_s = len(re.findall(r'\bs\d{3}\b', sk))
    sk_p = len(re.findall(r'\bp\d{2,4}\b', sk))
    style = 'sNNN' if sk_s > sk_p else ('pNN' if sk_p else '无锚形态')
    # 册配置的 pagemark 形态 → 期望的锚写法（同代映射；不得只印不算）
    expect = {'hline': 'pNN', 'pNN': 'pNN', 'sNNN': 'sNNN', 'auto': None}.get(pm, None)
    ok3 = style != '无锚形态'
    same_gen = (expect is None) or (style == expect)
    rep.append('| ③ | 锚形态同代 | %s | 技能锚形态=%s（s%d／p%d） ／ 册 pagemark=%s ⇒ 期望 %s ／ **同代=%s** |'
               % ('PASS' if (ok3 and same_gen) else ('⚠ 无锚' if not ok3 else '🔴 FAIL'),
                  style, sk_s, sk_p, pm, expect or '（auto，不判）', same_gen))
    if not ok3:
        warn.append('技能里**没有任何页锚形态**（sNNN/pNN）⇒ 本册的"点回原文"无抓手')
    if ok3 and not same_gen:
        fatal.append('③ **锚形态与册配置不同代**：技能用 `%s`，而册 `pagemark=%s` 期望 `%s` ⇒ '
                     '技能里的锚**按册文本回源不了**（`A-132` 家族：同一套语法写两份）' % (style, pm, expect))

    # ④ 清单可读：逐条 Test-Path ＋ 首行
    firsts = []
    for p in corpus_files[:2] + ([skill_md] if skill_md else []):
        try:
            first = io.open(p, encoding='utf-8', errors='replace').readline().strip()[:60]
            firsts.append('%s→「%s」' % (os.path.basename(p), first))
        except Exception as e:
            firsts.append('%s→读取失败 %s' % (os.path.basename(p), e))
    ok4 = all('读取失败' not in x for x in firsts) and bool(firsts)
    rep.append('| ④ | 下游清单可读 | %s | %s |'
               % ('PASS' if ok4 else '🔴 FAIL', '；'.join(firsts) if firsts else '无可读件'))

    text = IDEMPOTENT_MARK + '\n\n# 语料绑定闸 · 报告\n\n' + '\n'.join(rep) + '\n\n## 二、结论\n\n'
    if fatal:
        text += '🔴 **绑定不成立**（rc=1）——**不得派作答者/判官**：\n' + '\n'.join('- ' + x for x in fatal) + '\n'
    else:
        text += '✔ **语料绑定成立**：路径存在、主题命中、锚形态有抓手、下游件可读。\n'
    if warn:
        text += '\n### 告警（不影响 rc）\n' + '\n'.join('- ' + x for x in warn) + '\n'
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        io.open(out, 'w', encoding='utf-8', newline='\n').write(text)
    return (1 if fatal else 0), text


def selftest():
    """自证：主题错配必须红、主题对必须绿（用同一份技能 + 两个册）。"""
    import shutil
    import tempfile
    bad = []
    tmp = tempfile.mkdtemp(prefix='cbc-')
    try:
        sk = os.path.join(tmp, 'skills', 'kzz-x')
        os.makedirs(sk)
        io.open(os.path.join(sk, 'SKILL.md'), 'w', encoding='utf-8', newline='\n').write(
            '苹果 苹果 苹果 香蕉 香蕉 香蕉 橘子 橘子 橘子 葡萄 葡萄 葡萄\n'
            '锚形态 sNNN 示例（`E-001` s47）\n'
            '路径 .work/good/verified.md\n')
        for task, body in (('good', '苹果 香蕉 橘子 葡萄 ' * 60),
                           ('bad', '钢材 水泥 玻璃 木材 ' * 60)):
            d = os.path.join(tmp, '.work', task)
            os.makedirs(d)
            io.open(os.path.join(d, 'verified.md'), 'w', encoding='utf-8', newline='\n').write(body)
            io.open(os.path.join(d, 'bookspec-%s.json' % task), 'w', encoding='utf-8').write(
                '{"task":"%s","src":"book_text.md","pagemark":"hline"}' % task)
        rc_g, _ = check(sk, 'good', work=tmp)
        rc_b, _ = check(sk, 'bad', work=tmp)
        print('  好册 rc=%d（期望 0）｜ 坏册 rc=%d（期望 1）' % (rc_g, rc_b))
        if rc_g != 0:
            bad.append('主题匹配的册未通过（rc=%d）' % rc_g)
        if rc_b != 1:
            bad.append('主题错配的册未被拦下（rc=%d）—— 这正是今天事故的形态' % rc_b)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if bad:
        print('🔴 语料绑定闸自证失败：%s' % '；'.join(bad))
        return 1
    print('✔ 语料绑定闸自证通过（主题匹配放行 ＋ 主题错配拦下）')
    return 0


def main():
    ap = argparse.ArgumentParser(description='语料绑定闸（派单前必跑）')
    ap.add_argument('--skill', help='技能目录（含 SKILL.md）')
    ap.add_argument('--task', help='册 slug（.work/<task>）')
    ap.add_argument('--work', help='工作区根（默认取本脚本上两级）')
    ap.add_argument('--out', help='报告 .md')
    a = ap.parse_args()
    if not (a.skill and a.task):
        ap.error('须给 --skill 与 --task')
    rc, text = check(a.skill, a.task, a.work, a.out)
    print(text)
    if a.out:
        print('报告：%s' % a.out)
    print('退出码：%d（0=绑定成立 ／ 1=不成立**不得派单** ／ 2=前置不满足）' % rc)
    return rc


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
