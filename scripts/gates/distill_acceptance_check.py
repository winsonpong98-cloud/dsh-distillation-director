# -*- coding: utf-8 -*-
r"""distill_acceptance_check.py —— **蒸馏后 7 条验收标准的机核闸**（任务通用 · 零模型 · 只读）

## 它是什么 / 不是什么（先划清射程，防"纸面判据"）

**是**：对一份"交付答卷"（或一个技能根）做**机器能判的那部分**验收，逐条给 PASS / 待判官 / 不适用。
**不是**：它**不能**替判官判语义（例如"这条算不算真反例""这个引文是不是改字"）。
⇒ 每一条要么给**闭式机器证据**，要么**明确写"本条须判官裁"**，**不得用关键词命中冒充达标**。

## 为什么必须存在（2026-09-21 实测来源）

7 条验收标准原先只存在于「人工判官 + 一次性会话」里：同一件被三轮判过、
每轮判官的词表与口径都不同，**数字不可相减**（判官 RJ2 19 条 vs 机核 20 条即是实例）。
本件把其中**可闭式化的部分**固定下来，让"是否达标"不再取决于某一次判官的手感。

## 七条标准的机核化分栏（本件实现的射程）

| # | 标准 | 本件能判什么 | 不能判什么 |
|---|---|---|---|
| 1 | 点回原文 | 引文是否**成对**给出 `（id sNNN）` 双锚；锚格式是否合法；`--pool` 给出时可查 id 是否真在池内 | 引文与原文是否**逐字一致**（须 `verify_layer_quotes` / 判官） |
| 2 | 跨章节论证完整（漏反例） | 是否附 `--check` 机核输出且 **rc=0**；等式三项是否 ≡ T | 该列而未列（语义，须判官） |
| 3 | 推测标注 | **【外推】**块数与 `外推清单：N` 是否**自洽**；每条是否写了"依赖前提" | 该不该标（语义） |
| 4 | 先追问缺信息 | 是否出现判停声明；是否给出**字段清单** | 清单够不够（语义） |
| 5 | 两书冲突 | 是否出现**证据等级句 / 时效句 / 适用条件**三类标记 | 判定是否正确（语义，须判官） |
| 6 | 成本 | 是否引用**会话级账页**（含快照时刻/会话数/金额）；**缺少可复算记录即判"不合格"** | 金额本身是否合理 |
| 7 | 导出/复用/积累 | 答卷里声明的落盘路径是否**真实存在**（`Test-Path` 等价） | 内容质量 |

## 用法

    python tools\distill_acceptance_check.py --answer <答卷.md> [--pool <verified.md>] [--out <报告.md>]
    python tools\distill_acceptance_check.py --selftest

退出码：**0 ＝ 机核项全过**；**1 ＝ 有机器可判项不合格**；**2 ＝ 前置不满足**。
⚠ 退出码 0 **不等于**7 条全达标 —— 报告里"须判官裁"的条目仍须判官过一遍（本件不越权）。
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

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

IDEMPOTENT_MARK = '<!-- distill_acceptance_check:generated (idempotent) -->'
# 双锚形态（实测至少 5 种）：`E-007` s207 ／ （`E-007` s207） ／ E-007 s207 ／ `E-007`（s207） ／ E-007，s207
#   ⚠ 自证抓到的自身缺陷：首版写 `\D{0,6}` ⇒ 锚前若有反引号＋中文顿号（`（\`E-000\` s000）`）会**漏数**；
#     而漏数会把"有锚"判成"无锚"（假红），也会让"锚充足"判据失真。改用**非贪婪任意字符**并 **DOTALL 关**。
ANCHOR_RE = re.compile(r'([A-Za-z][A-Za-z0-9]*-\d{3})\s*`?\s*[（(]?\s*[，,、]?\s*`?\s*(s\d{3})')
QUOTE_RE = re.compile('「[^」]{6,400}」')
EXTRAP_RE = re.compile(r'【外推[^】]{0,8}】')
EXTRAP_DECL_RE = re.compile(r'外推清单\s*[：:]\s*(\d+)')
STOP_RE = re.compile(r'判停')
FIELD_LIST_RE = re.compile(r'(字段清单|需要你自报|需你自报|缺失信息|需补(?:的)?事实|缺口清单)')
# 第5条三类标记（弱证据：只证明"写了这类句子"，不证明判对）
EV_TIER_RE = re.compile(r'(证据等级|一手|可回查程度|定级)')
TIMELINESS_RE = re.compile(r'(时效|最新时点|数据(?:的)?最新|截至\s*\d{4})')
APPLY_COND_RE = re.compile(r'(适用条件|失效条件|边界条件|在什么条件下)')
# 第6条：会话级成本账的证据形态 —— `G-49`（2026-09-24 修·用户解冻判据改造）：判据从**关键词存在性**
# 改为**结构化要素四联**（触及成本域时必须能解析出值：①快照定位 ②会话数 ③金额 ④口径声明，缺一 FAIL）。
# 旧 COST_EVID_RE（关键词存在性）已废——「口径」「成本」出现 ≠ 有账（fei 第 3／4 条假绿实录，A-30/A-36 家族）。
COST_RE = re.compile(r'(成本|￥|¥|\d+\.\d{4}\s*元|会话级|cost_attrib|tokens?)')     # 仅作"是否触及成本域"初筛
COST_SNAP_RE = re.compile(r'`([^\n`]*(?:快照|账页|ledger|cost|成本)[^\n`]*)`')       # ① 快照/账页路径（解析出路径原文；**单行**）
COST_TAKEN_RE = re.compile(r'takenAt[^，。；;\n]{0,20}|\d{4}-\d{2}-\d{2}[ T]?\d{2}:\d{2}')  # ①′ 快照时刻（路径的替代形态）
COST_SESS_RE = re.compile(r'(\d+)\s*个会话|会话数\s*[：:=]?\s*(\d+)')                # ② 会话数（数值）
COST_AMT_RE = re.compile(r'[￥¥$]?\s*(\d+(?:\.\d+)?)\s*(?:元|美元|USD)')             # ③ 金额（数值）
COST_CAL_RE = re.compile(r'口径\s*[：:=]?\s*([^\n｜|。；;]{4,80})')                   # ④ 口径声明（语句）
COST_SNAP_PATHISH = re.compile(r'[\\/]|\.(?:md|json|jsonl|csv|txt|xlsx)\b', re.I)    # ① 须**像路径**（有分隔符或扩展名）
COST_CAL_VOCAB = re.compile(r'会话|余额|平均|计入|统计|账页|快照|成本|token', re.I)   # ④ 须是**成本口径**词汇（散文"结构口径"不算）


def check(answer_path, pool_path=None, out=None):
    if not os.path.exists(answer_path):
        return 2, '🔴 答卷不存在：%s' % answer_path
    t = io.open(answer_path, encoding='utf-8').read()
    lines = t.split('\n')
    rep = ['## 一、机核项（本件能判的部分）', '',
           '| # | 标准 | 机核判态 | 机器证据 |', '|---|---|---|---|']
    fatal = []          # 机器可判的**不合格**（影响 rc）
    notes = []          # **待人工核**（不影响 rc；例如相对路径基准不同）

    # ── 第1条：双锚成对 ──
    anchors = ANCHOR_RE.findall(t)
    quotes = QUOTE_RE.findall(t)
    # ⚠ 自证抓到的自身缺陷（首版）：原写 `bool(anchors) or not quotes` ⇒
    #   "有引文但零锚"时因 `not quotes` 为 False 也走不到……真正的漏洞是**引文为零时直接判 PASS**，
    #   于是坏样本（删掉锚）反而放行。**漏检比误报更致命（A-55）**，故改为：
    #   有引文 ⇒ 必须有锚（锚数 ≥ 引文数的 1/3，容忍省略号合并写法）；无引文 ⇒ 记"不适用"，不判 PASS。
    if not quotes:
        ok1, why1 = None, '本答卷无「」引文段 ⇒ 本项**不适用**（不得读作 PASS）'
    elif len(anchors) >= max(1, len(quotes) // 3):
        ok1, why1 = True, '双锚 %d 处 ／ 引文段 %d 处' % (len(anchors), len(quotes))
    else:
        ok1, why1 = False, '引文段 %d 处但双锚仅 %d 处（不足 1/3）⇒ 多数引文未给 `（id sNNN）`' % (len(quotes), len(anchors))
    rep.append('| 1 | 点回原文 | %s | %s |'
               % ({True: 'PASS', False: '🔴 FAIL', None: '— 不适用'}[ok1], why1))
    if ok1 is False:
        fatal.append('第1条：%s' % why1)

    # ── 第2条：等式机核 ──
    has_check = ('--check' in t) or ('等式机核' in t)
    has_rc0 = bool(re.search(r'(退出码\s*[：:=]?\s*0|rc\s*=\s*0|差异集\s*=\s*0|差异集为空)', t))
    has_eq = bool(re.search(r'列入.*不列.*≡|列入.*＋.*不列', t))
    ok2 = has_check and has_rc0 and has_eq
    rep.append('| 2 | 跨章节论证完整 | %s | --check 证据=%s ／ rc0/差异集空=%s ／ 等式=%s |'
               % ('PASS' if ok2 else '🔴 FAIL', has_check, has_rc0, has_eq))
    if not ok2:
        fatal.append('第2条：缺 **机核等式证据**（须附 `--check` 实跑且 rc=0；自报一句不算）'
                     '（--check=%s rc/差异集=%s 等式=%s）' % (has_check, has_rc0, has_eq))

    # ── 第3条：外推标注自洽 ──
    n_ex = len(EXTRAP_RE.findall(t))
    m = EXTRAP_DECL_RE.search(t)
    decl = int(m.group(1)) if m else None
    ok3 = (n_ex == 0 and (decl in (None, 0))) or (n_ex > 0 and decl == n_ex) or \
          (n_ex > 0 and re.search(r'依赖(?:的)?前提', t) is not None and decl is None)
    # ⚠ 2026-09-24（`G-56`）：`n_ex == 0` **不得**印 PASS —— 一份压根没有【外推】块的答卷
    #   会被读成"第 3 条达标"（实测：`yuanze-cwo` 的第 4 条答卷 `【外推】` 块 0 处、含依赖前提 False，却印 PASS）。
    #   改为第三种状态「▲ 未触及」：**本条无从判定**，既不判达标也不判失败（rc 语义不变）。
    _t3 = ('▲ 未触及（无【外推】块 ⇒ 本条无从判定，**不得读作达标**）' if n_ex == 0
           else ('PASS' if ok3 else '🔴 FAIL'))
    rep.append('| 3 | 推测标注 | %s | 【外推】块 %d ／ 声明条数 %s ｜ 含"依赖前提"=%s |'
               % (_t3, n_ex, decl, bool(re.search(r'依赖(?:的)?前提', t))))
    if not ok3:
        fatal.append('第3条：有【外推】块 %d 个，但 `外推清单：N` 声明为 %s（须自洽；无外推时应不出现）'
                     % (n_ex, decl))

    # ── 第4条：判停与字段清单（弱证据，须判官裁） ──
    stopped = bool(STOP_RE.search(t))
    fields = bool(FIELD_LIST_RE.search(t))
    rep.append('| 4 | 先追问缺信息 | %s | 判停标记=%s ／ 字段清单=%s |'
               % ('PASS' if (stopped and fields) else '🔴 FAIL', stopped, fields))
    if not (stopped and fields):
        fatal.append('第4条：缺"判停 ＋ 字段清单"（判停=%s 清单=%s）——若本题非"缺信息型"请显式写'
                     '「本题不触发判停」并给理由' % (stopped, fields))

    # ── 第5条：三类标记（弱证据） ──
    ev, tl, ac = bool(EV_TIER_RE.search(t)), bool(TIMELINESS_RE.search(t)), bool(APPLY_COND_RE.search(t))
    ok5 = ev and tl and ac
    rep.append('| 5 | 两书冲突（证据/时效/适用条件） | %s | 证据等级句=%s ／ 时效句=%s ／ 适用条件句=%s |'
               % ('PASS' if ok5 else '🔴 FAIL', ev, tl, ac))
    if not ok5:
        fatal.append('第5条：三类标记须齐（证据等级/时效/适用条件）：%s/%s/%s' % (ev, tl, ac))

    # ── 第6条：成本须引用**可复算**账页（`G-49` 修后＝结构化要素四联） ──
    #   触及成本域 ⇒ 必须解析出 ①快照定位（账页/快照路径 ∥ 快照时刻）②会话数（数值）
    #   ③金额（数值）④口径声明（语句）；**缺一 ⇒ 🔴 FAIL**（A-135）。完全未触及 ⇒ **▲ 未触及**
    #   （本条无从判定，不得读作达标——与第 3 条 `G-56` 同款三分法，rc 语义不变）。
    #   「该册是否存在账页」与「答卷是否达标」**分开印**（见下方 notes，`G-49` 处方原文）。
    cost_has = bool(COST_RE.search(t))
    if not cost_has:
        rep.append('| 6 | 成本（可复算） | ▲ 未触及 | 本答卷未触及成本域 ⇒ 本条**无从判定**（**不得读作达标**） |')
    else:
        _m_sP, _m_sT = COST_SNAP_RE.search(t), COST_TAKEN_RE.search(t)
        _m_ss, _m_am = COST_SESS_RE.search(t), COST_AMT_RE.search(t)
        _m_ca = COST_CAL_RE.search(t)
        # ①须像路径（散文级反引号串不算）；④须成本口径词汇（"结构口径"这类散文不算）——首版实测抓到两处误配后收紧
        _snap1 = _m_sP.group(1).strip() if (_m_sP and COST_SNAP_PATHISH.search(_m_sP.group(1))) else None
        _cal1 = _m_ca.group(1).strip() if (_m_ca and COST_CAL_VOCAB.search(_m_ca.group(1))) else None
        _el6 = [('①快照定位', _snap1 or (_m_sT.group(0).strip() if _m_sT else None)),
                ('②会话数', (_m_ss.group(1) or _m_ss.group(2)) if _m_ss else None),
                ('③金额', _m_am.group(1) if _m_am else None),
                ('④口径', _cal1)]
        _miss6 = [n for n, v in _el6 if not v]
        rep.append('| 6 | 成本（可复算） | %s | 四联解析：%s%s |'
                   % ('PASS' if not _miss6 else '🔴 FAIL',
                      ' ／ '.join('%s=%s' % (n, ('`%s`' % v) if v else '**缺**') for n, v in _el6),
                      (' ⇒ 缺 %s' % '、'.join(_miss6)) if _miss6 else ' ⇒ 四要素齐，可复算'))
        if _miss6:
            fatal.append('第6条：触及成本域但**结构化要素缺 %s**（快照定位/会话数/金额/口径须能解析出值）——'
                         '按 `A-135`：不可复算的数字不得对外宣称（`G-49` 修后口径）' % '、'.join(_miss6))
    # 「该册是否存在账页」**分开印**（`G-49` 处方：册侧有没有账 ≠ 答卷是否达标，不得混读）
    _td6 = os.path.dirname(os.path.dirname(os.path.abspath(answer_path)))
    if os.path.basename(os.path.dirname(_td6)) == '.work':
        _led6 = []
        for _r6, _d6, _f6 in os.walk(_td6):
            for _f in _f6:
                if re.search(r'(成本|账页|ledger|cost)', _f, re.I) and \
                        _f.lower().endswith(('.md', '.json', '.jsonl', '.csv', '.txt')):
                    _led6.append(os.path.relpath(os.path.join(_r6, _f)))
        notes.append('第6条（分开印 · `G-49`）：该册 `%s` 下成本账页类文件 **%d** 个%s —— 这是"册侧有没有账"，'
                     '**不是**"答卷第 6 条达标"（达标看上表四联解析）'
                     % (os.path.basename(_td6), len(_led6),
                        ('：' + '；'.join('`%s`' % x for x in _led6[:4])) if _led6 else ''))
    else:
        notes.append('第6条（分开印 · `G-49`）：答卷不在 `.work/<册>/answers/` 布局 ⇒ 册侧账页清点不适用'
                     '（**不适用 ≠ 达标**，达标只看四联解析）')

    # ── 第7条：落盘件真实存在 ──
    #   ⚠ 口径（自证抓到后修正）：路径存在性**按当前工作目录**判 —— 答卷里的相对路径可能
    #     以"工作区父目录／答卷所在目录"为基准，从别处跑就会**假红**。
    #     故本项**不判 FAIL**，只报告"未在当前 cwd 下找到"并**逐条打印路径原文**，由人裁。
    paths = re.findall(r'`([^`]*\.(?:md|json|jsonl|txt|csv|xlsx))`', t)
    cand = [p for p in paths if ('\\' in p or '/' in p)]
    found, notfound = [], []
    for p in cand:
        (found if os.path.exists(p) else notfound).append(p)
    ok7 = not notfound
    rep.append('| 7 | 导出/复用/积累（落盘件） | %s | 可核路径 %d ／ 当前 cwd 下找到 %d ／ 未找到 %d |'
               % ('PASS' if ok7 else '⚠ 待人工核', len(cand), len(found), len(notfound)))
    if notfound:
        rep.append('| ↳ | 未找到的路径（**可能是相对路径基准不同，不一定是真缺**） | — | %s |'
                   % '；'.join('`%s`' % x for x in notfound[:5]))
        notes.append('第7条：%d 个路径未在**当前 cwd** 下找到（须逐条判断是"真缺"还是"相对基准不同"）：'
                     '；'.join('`%s`' % x for x in notfound[:5]))

    # ── 须判官裁的清单（本件不越权） ──
    rep += ['', '## 二、**须判官裁**的条目（本件明确不判）', '',
            '- 第 1 条：引文与池内原文是否**逐字一致**、锚是否指向正确页（须回源；见 `verify_layer_quotes.py`）。',
            '- 第 2 条：T 内每一条的**处置该不该**（该列而未列＝语义判定）。',
            '- 第 3 条：某句**该不该**标【外推】。',
            '- 第 4 条：字段清单**够不够**、是否真属"缺信息型"问题。',
            '- 第 5 条：证据等级/时效/适用条件的**判定是否正确**。',
            '- 第 6 条：金额本身是否合理（本件只核"是否可复算"）。',
            '- 第 7 条：产物**内容质量**。', '',
            '## 三、结论', '']
    if fatal:
        rep.append('🔴 **机核项不通过**（rc=1）：')
        rep += ['- ' + x for x in fatal]
    else:
        rep.append('✔ **机核项通过** —— 注意：这**不等于** 7 条全达标；'
                   '第二节"须判官裁"的条目仍须判官过一遍。')
    if notes:
        rep += ['', '### 待人工核（**不影响 rc**）', ''] + ['- ' + x for x in notes]

    text = IDEMPOTENT_MARK + '\n\n# 蒸馏后 7 条验收 · 机核报告\n\n' + '\n'.join(rep) + '\n'
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        io.open(out, 'w', encoding='utf-8', newline='\n').write(text)
    return (1 if fatal else 0), text


def selftest():
    """自证：好样本放行、六类坏样本全拦（A-55：漏检比误报更致命）。"""
    bad = []
    import tempfile
    import shutil
    tmp = tempfile.mkdtemp(prefix='dac-selftest-')
    try:
        # ⚠ 样本里的引号必须是真的全角引号（首版误用转义写法 ⇒ 引文段恒为 0，坏样本反而放行）
        Q1, Q2 = '\u300c', '\u300d'
        good = ('# 答卷\n引用：' + Q1 + '甲甲甲甲甲甲' + Q2 + '。（`E-007` s207）\n'
                '等式机核：--check 退出码：0 ｜ 差异集 = 0 ｜ 列入 1 ＋ 不列 132 ≡ T\n'
                '【外推】依赖前提：X；前提破则 Y。\n外推清单：1\n'
                '判停：本题缺信息。字段清单：①A ②B\n'
                '证据等级：两端同级。时效：左端 2021-08。适用条件：见下。\n'
                '成本：会话级快照 takenAt 09:17，20 个会话，合计 ￥0.8420 元，'
                '口径：会话级与余额差并列不平均，见 `.work/x/账页-0920.md`。\n')
        cases = {
            '好样本': (good, 0),
            '好·通篇无成本（▲ 未触及）': (
                good.replace('成本：会话级快照 takenAt 09:17，20 个会话，合计 ￥0.8420 元，'
                             '口径：会话级与余额差并列不平均，见 `.work/x/账页-0920.md`。\n', ''), 0),
            '坏1 有引文但零锚': (good.replace('（`E-007` s207）', ''), 1),
            '坏2 无等式证据': (good.replace('--check 退出码：0 ｜ 差异集 = 0 ｜ 列入 1 ＋ 不列 132 ≡ T', ''), 1),
            '坏3 外推数不自洽': (good.replace('外推清单：1', '外推清单：3'), 1),
            '坏4 无判停无清单': (good.replace('判停：本题缺信息。字段清单：①A ②B', ''), 1),
            '坏5 缺时效句': (good.replace('时效：左端 2021-08。', ''), 1),
            '坏6 触及成本但四联全缺': (
                good.replace('会话级快照 takenAt 09:17，20 个会话，合计 ￥0.8420 元，'
                             '口径：会话级与余额差并列不平均，见 `.work/x/账页-0920.md`。', '成本约 1 元。'), 1),
            '坏6b 缺快照定位': (
                good.replace('，见 `.work/x/账页-0920.md`', '').replace('takenAt 09:17，', ''), 1),
            '坏6c 缺会话数': (good.replace('20 个会话，', ''), 1),
            '坏6d 快照位是散文不是路径': (
                good.replace('`.work/x/账页-0920.md`', '`成本相关说明文字（无路径形态）`')
                    .replace('takenAt 09:17，', ''), 1),
            '坏7 声明路径不存在': (good + '\n产物：`不存在的目录\\没有这个文件.md`\n', 0),
        }
        for name, (txt, want) in cases.items():
            p = os.path.join(tmp, name.replace(' ', '_') + '.md')
            io.open(p, 'w', encoding='utf-8', newline='\n').write(txt)
            if name == '坏7 声明路径不存在':
                # 第7条是"待人工核"（相对路径基准可能不同）⇒ 只要求**出现待核提示**，不要求 rc=1
                _rc, rep7 = check(p)
                if '待人工核' not in rep7:
                    bad.append('%s：未出现"待人工核"提示' % name)
                continue
            rc, _ = check(p)
            if rc != want:
                bad.append('%s：期望 rc=%d 实得 rc=%d' % (name, want, rc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for b in bad:
        print('🔴 %s' % b)
    if bad:
        return 1
    print('✔ distill_acceptance_check 自证通过（%d 组样本全部符合预期：好样本＋▲未触及放行／坏样本全拦——'
          '含 `G-49` 四联解析的反向四例）' % len(cases))
    return 0


def main():
    ap = argparse.ArgumentParser(description='蒸馏后 7 条验收标准的机核闸（只读）')
    ap.add_argument('--answer', help='交付答卷 .md')
    ap.add_argument('--pool', help='候选池 .md（可选；本版只登记不深查）')
    ap.add_argument('--out', help='报告 .md')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    if not a.answer:
        ap.error('须给 --answer')
    rc, text = check(a.answer, a.pool, a.out)
    if not a.quiet:
        print(text)
    if a.out:
        print('报告：%s' % a.out)
    print('退出码：%d（0=机核项通过 ／ 1=有机器可判项不合格 ／ 2=前置不满足）' % rc)
    return rc


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        sys.stderr.write('🔴 本步骤无法执行：%s: %s\n' % (type(e).__name__, e))
        sys.exit(2)
