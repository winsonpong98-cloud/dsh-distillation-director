# -*- coding: utf-8 -*-
r"""check_doc_tool_refs.py —— **文档声明的脚本 vs 随包实物** 对账（只读 · 零模型调用 · 发版闸）

用户要求（2026-09-21）："所有插件的修补都要考虑这个是安装在第三方电脑上的，
所以要确保插件安装后，所有的功能都能正常使用。"

为什么必须单独成闸（实测缺口）：
  `init_workspace.py` 只把**包内** `scripts/gates/*` 与 `scripts/*` 拷到用户 `<ws>\tools\`。
  ⇒ 文书里让用户跑的脚本若**不在包内**，异机用户照做就是"缺件"，但**发版闸此前照不到这一面**：
  实测抓到 **9 件**（`rquote_page_check.py`／`polish_scan.py`／`split_long_lines.py`／`table_to_blocks.py`／
  `cost_attrib.py`／`coverage_by_chapter.py`／`fix_anchors_generic.py`／`slice_verified_by_skill.py`／
  `make_edu_root_stamp.py`）——**文档承诺 ≠ 实物交付**（A-135 家族）。

判据（确定性；**"指令型引用"才算承诺**）：
  ① 抽脚本名 `<名>.(py|cjs|mjs|js)`，**且后面不得紧跟词字符**
     （否则 `package.json` 会被误当 `package.js` —— 首版即踩此坑：33 个"悬空"里大半是 `.json` 尾巴）；
  ② 判定"指令型引用"＝ **出现 `python <路径含该名>`／`node <路径含该名>`**
     或 **出现 `tools\<名>`／`scripts\<名>`**（＝"你的工具目录里该有这一个"）；
     仅裸名出现（历史叙述、示例、被替换掉的旧名）**不算承诺**；
  ③ 与包内实物 ＋ `optional-tools.json` 比对 ⇒ **指令型悬空 = 🔴**；
  ④ 白名单：DSH 自身路径（`<dsh>/lib/bin.js` 之类）不属于本插件承诺，自动排除并打印。

用法：
  python tools\check_doc_tool_refs.py --plug <插件根>            # 插件根目录（含 SKILL.md）
  python tools\check_doc_tool_refs.py --tgz <tgz 路径>           # 或直接给发行包
  python tools\check_doc_tool_refs.py                            # 不加参数：从本脚本位置上溯找插件根
退出码：0 = 指令型悬空 0；1 = 有悬空（**异机照文档做会缺件 ⇒ 不得发版**）；2 = 环境缺件
"""
import argparse
import io
import json
import os
import re
import sys
import tarfile

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

NAME = re.compile(r'([A-Za-z0-9_\-]+\.(?:py|cjs|mjs|js))(?![\w])')
# 白名单：DSH 引擎自身／第三方运行时的路径（不是本插件的承诺）
WHITELIST = re.compile(r'(?:lib[\\/]bin\.js|node_modules|js-yaml)')


def is_placeholder(name):
    """**占位名**不是承诺（2026-09-21 自伤登记）：本闸自己的使用说明里写了
    「`python tools\\X.py`／`tools\\X.py`」这种**示例占位**，首跑即被自己判成"悬空 1 件"。
    本项目真实工具名的**主名**一律 ≥3 字符且为 `[a-z][a-z0-9_]*`（如 `check_table_inventory`）
    ⇒ 主名短于 3 字符者（`X.py`／`Y.py`／`N.py`）按占位处理。
    （同族先例：可移植性闸 D-配套曾把格式化模板 `bookspec-%s.json` 判成缺件 —— 假红比漏检更伤。）"""
    stem = name.rsplit('.', 1)[0]
    return len(stem) < 3
DOCS = ('SKILL.md', 'README.md')


def is_command_ref(line, name):
    if WHITELIST.search(line) and name == 'bin.js':
        return False
    if re.search(r'(?:python|py|node)\s+[^\s`|]*' + re.escape(name), line):
        return True
    return bool(re.search(r'(?:tools|scripts)[\\/]' + re.escape(name), line))


def packed_names(plug=None, tgz=None):
    if tgz:
        with tarfile.open(tgz) as tf:
            return {os.path.basename(n) for n in tf.getnames() if not n.endswith('/')}
    out = set()
    for d in (os.path.join(plug, 'scripts', 'gates'), os.path.join(plug, 'scripts')):
        if os.path.isdir(d):
            out |= {f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}
    return out


def find_plug():
    d = os.path.abspath(_HERE)
    for _ in range(6):
        for c in (os.path.join(d, 'distillation-director-plugin'), d):
            if os.path.isfile(os.path.join(c, 'SKILL.md')) and os.path.isdir(os.path.join(c, 'scripts', 'gates')):
                return c
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--plug', default=None, help='插件根（含 SKILL.md 与 scripts/gates）')
    ap.add_argument('--tgz', default=None, help='发行包；给则按包内清单比对（更接近用户装上后的事实）')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args()

    plug = os.path.abspath(a.plug) if a.plug else find_plug()
    if not plug or not os.path.isdir(plug):
        print('🔴 找不到插件根：请用 --plug <插件根> 指定（或 --tgz <包>）')
        return 2
    optional = set()
    optf = os.path.join(plug, 'scripts', 'gates', 'optional-tools.json')
    if os.path.isfile(optf):
        optional = set(json.load(io.open(optf, encoding='utf-8')).get('optional', []))
    packed = packed_names(plug, a.tgz)
    src = a.tgz or plug

    print('=' * 92)
    print('文档↔随包 对账 ｜ 来源：%s' % os.path.basename(src))
    print('  包内实物 %d 件 ｜ 可选声明 %d 件 ｜ 判据："指令型引用"必须能在包内找到'
          % (len(packed), len(optional)))
    total = 0
    for doc in DOCS:
        fp = os.path.join(plug, doc)
        if not os.path.isfile(fp):
            continue
        t = io.open(fp, encoding='utf-8', errors='replace').read()
        refs = {}
        for i, line in enumerate(t.splitlines(), 1):
            for m in NAME.finditer(line):
                n = m.group(1)
                if is_placeholder(n):
                    continue
                e = refs.setdefault(n, {'n': 0, 'cmd': []})
                e['n'] += 1
                if is_command_ref(line, n):
                    e['cmd'].append((i, line.strip()[:118]))
        dangling = sorted(n for n in refs
                          if n not in packed and n not in optional and refs[n]['cmd'])
        mention = sorted(n for n in refs
                         if n not in packed and n not in optional and not refs[n]['cmd'])
        print('-' * 92)
        print('【%s】引用脚本 %d 个 ｜ 🔴 指令型悬空 %d ｜ ○ 仅提及 %d'
              % (doc, len(refs), len(dangling), len(mention)))
        for n in dangling:
            print('   🔴 %s（引用 %d 次）' % (n, refs[n]['n']))
            for i, ln in refs[n]['cmd'][:2]:
                print('        L%d: %s' % (i, ln))
        if mention and not a.quiet:
            print('   ○ 仅提及（非承诺，不判失败）：%s' % '、'.join(mention))
        total += len(dangling)
    print('=' * 92)
    print('结论：%s'
          % ('✔ 文书里让用户跑的脚本全部在包内（异机装完即用）' if total == 0 else
             '🔴 指令型悬空 %d 件 ⇒ 异机用户照文档做会缺件：**补包**，或改文档并登记为可选依赖（缺则降级）'
             % total))
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
