# -*- coding: utf-8 -*-
r"""check_bandid_single_source.py —— **波段 id 语法单一来源闸**（防 A-132 复发）

## 这道闸存在的原因

「波段条目 id」的语法（`### {band}-NNN …` 里的 `{band}-NNN`）在 2026-09-19 之前
**被内联写在 16 个脚本里**，共 4 种互不兼容的残缺写法。后果不是"难看"，而是
**同一份合规产出在不同仪器下时红时绿**：

* NAS 册 `<task>`（波段 `E1..E6`）产出完全合规；
* `gate_stage.py` 的格式判据用 `[A-Za-z][0-9]*-[0-9]{3}` ⇒ **绿**；
* `verify_candidates.py` 用 `[A-Za-z]+` ⇒ **🔴「切块为空：条目正则未命中任何块」**（假红）。

更糟的是：**这个判据被"修"过 4 次，每次都在另一种波段形态上修坏**
（`\d+` → 丢纯字母册；`\d*` → 丢双字母前缀；`[0-9]*` → 丢双字母前缀；
`+` → 丢「字母＋数字」册）。**靠记性挡不住**，只能靠机器：语法只许有一份，
别处一律引用，**内联即判红**。

## 判据（本闸只做一件事）

扫 `tools\` 下所有 `.py` / `.mjs` / `.cjs` / `.json` 文本，凡出现
「`[A-Za-z]` 之后 ≤16 个非空白字符即接 `-\d` 或 `-[0-9]`」的**波段前缀残片**，
且该残片**不等于**唯一真源 `_bandid.BAND + "-"`（即 `[A-Za-z][A-Za-z0-9]*-`），
即判 🔴 并给出 file:line 与残片原文。

* 白名单（两档，见 `WAIVER_LINE`／`WAIVER_FILE` 注释）：
  - 行级 `BANDID-OK-LINE`（**首选**）：只豁免同一行，用于"故意写旧写法做对照"的单点；
  - 文件级 `BANDID-OK-FILE`：只给**形态普查器**（`diag_hline_blockmatch.py`）与本文件自身，
    它们的**整个文件**都在故意内联历史写法做对照实验；业务脚本一律不许用。
* 本闸**不判断语法对不对**（那是 `_bandid.selftest()` 的事），只判断**有没有第二处**。
  —— 分工理由：判据与真源分离，才不会"自己判自己"（A-27 家族）。

用法：python tools\check_bandid_single_source.py [--root <工作区根>]
退出码：0 = 全工作台只有一份语法；1 = 有内联残片（附清单）
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

# BANDID-OK-FILE: 本文件是**单源闸自己**，自证样本里必须内联历史残缺写法做正负对照 ⇒ 整文件豁免。


def _resolve_root(explicit=None):
    if explicit and os.path.isdir(explicit):
        return os.path.abspath(explicit)
    v = (os.environ.get('DSH_DISTILL_ROOT') or os.environ.get('DSH_WORKSPACE_ROOT') or '').strip()
    if v and os.path.isdir(v):
        return os.path.abspath(v)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from _paths import ROOT as _R
        if _R and os.path.isdir(_R):
            return _R
    except Exception:
        pass
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(d, '.dsh')):
            return d
        d = os.path.dirname(d)
    sys.exit('🔴 未找到蒸馏工作区根目录 —— 请设 DSH_DISTILL_ROOT=<你的工作区根>')

# 唯一真源目录（本文件与 _bandid.py 同目录）
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import _bandid as BID  # noqa: E402

CANON = BID.BAND + '-'          # `[A-Za-z][A-Za-z0-9]*-`  ← 唯一允许出现的波段前缀写法
# 豁免令牌（**两档，语义不同，不得混用**）：
#   `BANDID-OK-LINE` = **只豁免同一行**（首选）—— 用于"这一行是故意写旧写法做对照"的场合。
#   `BANDID-OK-FILE` = 豁免整文件 —— **只允许**给"形态普查器"这类**整个文件都在故意内联**的
#                      工具用（现存：本文件自身、`diag_hline_blockmatch.py`）；
#                      任何**业务脚本**都不许用文件级豁免。
#   两档必须用**不互相包含**的令牌名（首版写成 `bandid-waiver` 与 `bandid-waiver-file`，
#   前者是后者的前缀 ⇒ 行级令牌会误触发文件级豁免 —— 判据自身的形态又写错一次，已改）。
WAIVER_LINE = 'BANDID-OK-LINE'
WAIVER_FILE = 'BANDID-OK-FILE'
EXTS = ('.py', '.mjs', '.cjs', '.json')
# 跳过目录：加了 4 类**归档/旧版**目录——2026-09-19 把"随包副本"纳入射程时必须排除它们，
# 否则 `_old-releases\**` 里各旧版包的旧语料会把闸判红（那是**归档**，不是现行面）。
SKIP_DIRS = {'__pycache__', 'node_modules', '.git', '_old-releases', '.pytest_cache', '.mypy_cache'}
SKIP_DIR_PREFIX = ('_stale-', '_quarantine-', '_removed-', '.bak-')

# 残片探测：`[A-Za-z]` ＋ ≤16 个非空白字符 ＋ `-` ＋（`\d` 或 `[0-9]`）
#   **捕获组 1 = 前缀（含结尾的 `-`）** —— 与唯一真源比对的就是它；
#   整段匹配文本（含结尾的 `\d`）只用于打印，不参与判定。
#   （自证当场抓到的错：首版拿"整段"跟 `CANON` 比 ⇒ 把**规范写法**也判红了 ——
#    也就是我自己在闸里又犯了一次"判据没写对形态"。）
FRAG = re.compile(r'(\[A-Za-z\][^\s]{0,16}?-)(?:\\d|\[0-9\])')


def code_lines_py(path):
    """只取 `.py` 的**代码行**：注释行与**文档字符串**置空；**普通字符串字面量照审**。

    为什么这么切（首跑即暴露，两次修正）：
      * 首版把注释也审 ⇒ 报了 `gate_stage.py` 4 处，**全在注释里**，而那正是"记录历史错法"
        的说明文字。**判据若连写下来的教训都判红，就等于禁止记录教训**（注释会被逼成
        含糊话，而含糊注释正是 A-72 复发的温床）⇒ 注释必须豁免。
      * 但**不能连字符串一起豁免** —— 本闸要抓的正是"写在正则字符串里的内联语法"
        （`re.compile(r"^###\\s+[A-Za-z]\\d+-…")` 就是字符串）。**只有文档字符串（prose）
        才豁免，正则字符串（code）必须审。**
    区分办法：文档字符串 = 位于**语句开头**的 STRING 记号（前一个有效记号是
    NEWLINE/INDENT/DEDENT 或文件开头）；其余 STRING 一律是代码。
    实现用标准库 `tokenize`（**不自己写正则剥注释** —— 那又是一把会出错的尺子）。
    """
    src = io.open(path, encoding='utf-8', errors='replace').read()
    lines = src.splitlines()
    try:
        import tokenize
        TRIVIA = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.NL)
        blank = []
        last_sig = None
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            is_doc = (tok.type == tokenize.STRING and
                      last_sig in (None, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT))
            if tok.type == tokenize.COMMENT or is_doc:
                s_row, s_col = tok.start
                e_row, e_col = tok.end
                if s_row == e_row:
                    blank.append((s_row, s_col, e_col))
                else:
                    blank.append((s_row, s_col, None))
                    for r in range(s_row + 1, e_row):
                        blank.append((r, 0, None))
                    blank.append((e_row, 0, e_col))
            if tok.type not in TRIVIA and tok.type != tokenize.COMMENT:
                last_sig = tok.type
        for r, c0, c1 in blank:
            if 1 <= r <= len(lines):
                lines[r - 1] = (lines[r - 1][:c0] + ' ' * max(0, c1 - c0) + lines[r - 1][c1:]
                                if c1 is not None else lines[r - 1][:c0])
        return lines
    except Exception:
        # tokenize 失败（语法异常/文件不全）：**降级为整文件审**（宁严不松，且打印说明）
        print('  ▲ %s：无法分词 ⇒ 本文件按整文件审（不排除注释）' % os.path.basename(path))
        return lines


def strip_js_comments(txt):
    """`.mjs`/`.cjs`：剥 `/* */` 与 `//`（不做字符串感知 —— JS 侧无真源引用需求，够用）。"""
    txt = re.sub(r'/\*.*?\*/', '', txt, flags=re.S)
    return '\n'.join(re.sub(r'//.*$', '', ln) for ln in txt.splitlines())


def scan_lines(path, orig_lines, code_lines):
    """审 `code_lines`（注释/docstring 已置空），但**豁免令牌在 `orig_lines` 上找**。

    ⚠ 自证当场抓到的错（本闸第二次"判据形态写错"）：首版只在**置空后**的行上找豁免令牌，
      而豁免令牌**必须写在注释里**（`# BANDID-OK-LINE: 理由`）—— 注释已被置空 ⇒
      **行级豁免永远不生效**（令牌形同虚设）。**教训**：同一行做了两种处理（置空 + 判定）时，
      **判定必须用原始行**，否则"先处理"会把"后判定"的依据一起清掉。
    """
    out = []
    for i, line in enumerate(code_lines, 1):
        orig = orig_lines[i - 1] if i - 1 < len(orig_lines) else ''
        if WAIVER_LINE in orig:          # 行级豁免（须写明理由）
            continue
        for m in FRAG.finditer(line):
            if m.group(1) == CANON:      # 与真源等价 ⇒ 放行
                continue
            out.append((i, m.group(0)))
    return out


def scan_text(path):
    """返回该文件里的内联残片清单 [(行号, 残片原文)]（已排除真源与豁免文件）。"""
    base = os.path.basename(path)
    if base == '_bandid.py':            # 真源自己
        return []
    try:
        txt = io.open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return []
    if WAIVER_FILE in txt:              # 文件级豁免（仅限形态普查器）
        return []
    orig = txt.splitlines()
    if path.endswith('.py'):
        return scan_lines(path, orig, code_lines_py(path))
    if path.endswith(('.mjs', '.cjs')):
        return scan_lines(path, orig, strip_js_comments(txt).splitlines())
    return scan_lines(path, orig, orig)


def selftest():
    """闸自身有效性自证：**该拦的必须拦住、不该拦的必须放行**（六坏样本纪律）。

    为什么必须有（本项目纪律）：本闸的第一版就同时犯了两个错——**审了注释**（把历史教训判红）
    与**该审的没审**（若连字符串也豁免，正则内联就全漏）。**闸的有效性不能靠"跑起来 rc=0"
    证明**，必须用**已知正负样本**逐条实测。
    """
    import tempfile
    cases = [
        # (样本源码, 期望是否判红, 说明)
        ('import re\nX = re.compile(r"^###\\s+[A-Za-z]+-\\d{3}\\s+\\[")\n',
         True, '代码里的内联正则（`[A-Za-z]+-`）⇒ 必须判红'),
        ('import re\nX = re.compile(r"^###\\s+[A-Za-z]\\d*-\\d{3}")\n',
         True, '代码里的内联正则（`[A-Za-z]\\d*-`）⇒ 必须判红'),
        ('import re\nX = re.compile(r"^###\\s+[A-Za-z][0-9]*-[0-9]{3}")\n',
         True, '代码里的内联正则（`[A-Za-z][0-9]*-`）⇒ 必须判红'),
        ('# 历史错法记录：原式 `[A-Za-z]\\d+-\\d{3}` 对 D-001 恒不命中\nX = 1\n',
         False, '**注释**里的历史错法记录 ⇒ 必须放行（判红就是禁止记录教训）'),
        ('"""文档字符串：历史上曾写 `[A-Za-z]+-\\d{3}`，已废弃。"""\nX = 1\n',
         False, '**文档字符串**里的历史说明 ⇒ 必须放行'),
        ('from _bandid import BAND\nX = re.compile(r"^###\\s+" + BAND + r"-\\d{3}")\n',
         False, '引用唯一真源 ⇒ 必须放行'),
        ('import re\nX = re.compile(r"^###\\s+[A-Za-z][A-Za-z0-9]*-\\d{3}")\n',
         False, '**规范写法**（与真源等价）⇒ 必须放行'),
        ('import re\nX = re.compile(r"^###\\s+[A-Za-z]+-\\d{3}")  # BANDID-OK-LINE: 故意对照\n',
         False, '行级豁免令牌（**与残片同一行**，同实盘用法）⇒ 必须放行'),
        ('import re\n# BANDID-OK-LINE: 上一行写令牌\nX = re.compile(r"^###\\s+[A-Za-z]+-\\d{3}")\n',
         True, '令牌在**另一行** ⇒ 必须判红（豁免只认同行，防"令牌一贴、整片放行"）'),
        ('import re\nband = re.findall(r"notes_([A-Za-z]+(?:\\d+)?)\\.md", t)\n',
         False, '波段无关的字母正则（文件名）⇒ 必须放行（本闸只认"前缀＋`-`＋数字"）'),
    ]
    d = tempfile.mkdtemp(prefix='bandid_selftest_')
    bad = []
    for i, (src, want, desc) in enumerate(cases):
        p = os.path.join(d, 'case%d.py' % i)
        io.open(p, 'w', encoding='utf-8').write(src)
        got = bool(scan_text(p))
        mark = '✔' if got == want else '🔴'
        if got != want:
            bad.append(desc)
        print('  %s 判红=%-5s（应 %-5s） %s' % (mark, got, want, desc))
    # 清理：**用同一个格式串构造名字**（不写 `case0.py` 这类字面量）——
    #   为什么：发版闸 D 判据会把代码里被引号引起来的 `xxx.py` 当成"包内必须存在的文件"，
    #   写死一个字面量临时名会让它报 `🔴 引用了 case0.py —— 全包内均无`（**判据没错、我触发它的方式错**）。
    #   修法不是放宽发版闸，而是**别在代码里写死临时文件名**（与 A-132 同一条纪律：形态只有一种写法）。
    for i in range(len(cases)):
        fp = os.path.join(d, 'case%d.py' % i)
        if os.path.exists(fp):
            os.remove(fp)
    try:
        os.rmdir(d)
    except Exception:
        pass
    if bad:
        for b in bad:
            print('🔴 自证失败：%s' % b)
        return 1
    print('✔ 闸自证通过（%d 个正负样本全部符合预期）' % len(cases))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=None, help='工作区根（默认自动解析）')
    ap.add_argument('--tools', default=None, help='被扫目录（默认 <root>/tools）')
    ap.add_argument('--selftest', action='store_true', help='用已知正负样本自证本闸有效性')
    a = ap.parse_args()
    if a.selftest:
        print('波段 id 语法单一来源闸 · 自证')
        print('=' * 84)
        return selftest()
    if a.tools:
        roots = [os.path.abspath(a.tools)]
    else:
        root = _resolve_root(a.root)
        roots = [os.path.join(root, 'tools')]
        # ⚠ 射程扩展（2026-09-19 · NAS 真机反证）：**随包副本也是"声明位"**。
        #   定位过程：真机跑本闸判红 3 处，而本机全绿——查下去发现真机判红的是**宿主侧
        #   `tools\` 的陈旧副本**（419 行旧版），随包副本是干净的；同时暴露出**本闸默认只扫
        #   `<root>/tools`**，随包副本（`scripts/gates/`）**从来没被扫过**。
        #   这正是 `A-139`："同一事实的每个声明位都是独立失效点"。故补扫随包目录（在场才扫）。
        _pkg = os.path.join(root, 'distillation-director-plugin', 'scripts', 'gates')
        if os.path.isdir(_pkg):
            roots.append(_pkg)
    for _r in roots:
        if not os.path.isdir(_r):
            sys.exit('🔴 目录不存在：%s' % _r)

    print('波段 id 语法单一来源闸（A-132）')
    # ⚠ 修两处（2026-09-19 NAS 真机实测）：
    #   ① 原写 `'%s\\_bandid.py' % (tools, …)` —— **硬写 Windows 反斜杠** ⇒ 真机打印出
    #      `/workspace/tools\_bandid.py`（跨平台显示缺陷，F 判据家族）；
    #   ② 原把**被扫目录**当成"唯一真源目录"打印 ⇒ 当 `--tools` 指向别处时，
    #      报告"真源在哪"这一行是**错的**（同一个 `A-139`：报告与实际必须同源）。
    #   真源永远是与本文件同目录的 `_bandid.py`。
    print('唯一真源：%s ｜ 允许写法：`%s`' % (os.path.join(_HERE, '_bandid.py'), CANON))
    print('=' * 84)

    scanned, hits, waived = 0, [], []
    for tools in roots:
        _n0, _h0 = scanned, len(hits)
        for dp, dn, fn in os.walk(tools):
            dn[:] = [d for d in dn
                     if d not in SKIP_DIRS and not d.startswith(SKIP_DIR_PREFIX)]
            for f in sorted(fn):
                if not f.endswith(EXTS):
                    continue
                p = os.path.join(dp, f)
                scanned += 1
                try:
                    txt = io.open(p, encoding='utf-8', errors='replace').read()
                except Exception:
                    continue
                if WAIVER_FILE in txt and f != '_bandid.py':
                    waived.append(os.path.relpath(p, tools))
                    continue
                for ln, frag in scan_text(p):
                    hits.append((os.path.relpath(p, tools), ln, frag))
        print('扫描根：%s（扫 %d 文件 ／ 新增命中 %d）'
              % (tools, scanned - _n0, len(hits) - _h0))
    # 去重（多根扫描时同一豁免件会出现两次）+ 报告里带上是哪个根，避免"看着像两件"
    waived = sorted(set(waived))

    print('已扫 %d 个文件' % scanned)
    if waived:
        print('文件级豁免 %d 个（含 `%s`，仅限形态普查器）：%s'
              % (len(waived), WAIVER_FILE, '、'.join(waived)))
    if hits:
        print('🔴 发现 %d 处**内联**波段 id 语法（应改为 `from _bandid import ...`）：' % len(hits))
        seen = set()
        for rel, ln, frag in hits:
            print('   %s:%d   %s' % (rel, ln, frag))
            seen.add(rel)
        print('   涉及 %d 个文件；修法：`import _bandid as BID` 后用 BID.BAND / BID.ID / '
              'BID.ID_LOOSE / BID.ENTRY / BID.SPLIT / BID.split_blocks()' % len(seen))
        print('总判定：🔴 不通过（语法必须只有一份）')
        return 1
    print('✔ 未发现内联波段 id 语法 —— 全工作台引用同一真源')
    print('总判定：✔ 通过')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as _e:
        sys.stderr.write('\n\U0001F534 本步骤无法执行：%s: %s\n' % (type(_e).__name__, _e))
        sys.exit(2)
