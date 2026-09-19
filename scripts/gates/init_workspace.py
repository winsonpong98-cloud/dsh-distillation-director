# -*- coding: utf-8 -*-
r"""init_workspace.py —— **一键初始化 DSH 蒸馏工作区**（新用户第一步）

用法：python init_workspace.py <你的工作区根> [--plugin <插件解包目录>]
做四件事：
  1. 建目录：<ws>\tools、<ws>\.work\gate-kit、<ws>\.dsh
  2. 写配置：<ws>\.dsh\gate-kit\workspace.json（workspace_root / tools_dir / work_dir / manual_path）
  3. 拷门禁：把插件包内 scripts\gates\*.py 与 scripts\*.py 装到 <ws>\tools\
  4. 拷数据：执行单模板、避坑手册、layer-quotes 配置模板（缺失不报错，只提示）
然后自检并打印下一步该跑什么。
"""
import argparse
import glob
import io
import json
import os
import shutil
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ws', help='你的工作区根（例如 D:\\dsh\\workspaces\\我的蒸馏工作区）')
    ap.add_argument('--plugin', default=None, help='插件解包目录（含 scripts/gates）')
    a = ap.parse_args()
    ws = os.path.abspath(a.ws)
    def _find_plug(start):
        """找插件包根：**上溯**认 `package.json` 或 `scripts/gates`（不能用 dirname 固定跳数——
        发行包里本脚本在 `<包>/scripts/gates/`，跳两级会算成 `<包>/scripts`，导致一个文件都装不上）。"""
        d = os.path.abspath(start)
        for _ in range(6):
            if (os.path.isfile(os.path.join(d, 'package.json'))
                    or os.path.isdir(os.path.join(d, 'scripts', 'gates'))):
                return d
            up = os.path.dirname(d)
            if up == d:
                break
            d = up
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    plug = os.path.abspath(a.plugin) if a.plugin else _find_plug(__file__)
    SRC_DIRS = []
    for _c in (os.path.join(plug, 'scripts', 'gates'), os.path.join(plug, 'scripts'),
               os.path.dirname(os.path.abspath(__file__))):
        if os.path.isdir(_c) and _c not in SRC_DIRS:
            SRC_DIRS.append(_c)
    gates = SRC_DIRS[0] if SRC_DIRS else os.path.join(plug, 'scripts', 'gates')
    scr = SRC_DIRS[1] if len(SRC_DIRS) > 1 else os.path.join(plug, 'scripts')
    print('插件根：%s' % plug)
    print('取件源：%s' % ' ｜ '.join(SRC_DIRS))
    for d in (os.path.join(ws, 'tools'), os.path.join(ws, '.work', 'gate-kit'),
              os.path.join(ws, '.work', 'gate-kit', 'scripts'),
              os.path.join(ws, '.dsh'), os.path.join(ws, '.dsh', 'skills'),
              # **配置目录本身**也必须建：作者机与仿真都因它已存在而掩盖了这个缺失，
              # 异机新工作区会在写 workspace.json 时 FileNotFoundError（2026-09-17 实测）。
              os.path.join(ws, '.dsh', 'gate-kit')):
        os.makedirs(d, exist_ok=True)
    cfg = os.path.join(ws, '.dsh', 'gate-kit', 'workspace.json')
    json.dump({'workspace_root': ws, 'tools_dir': os.path.join(ws, 'tools'),
               'work_dir': os.path.join(ws, '.work', 'gate-kit'),
               'manual_path': os.path.join(ws, '蒸馏工程避坑手册.md')},
              io.open(cfg, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False, indent=1)
    n = 0
    EXTS = ('*.py', '*.json', '*.cjs', '*.mjs', '*.md')     # 配套脚本必须成套（缺 .cjs/.mjs ⇒ YAML 闸跑不动）
    for d in tuple(SRC_DIRS):
        if os.path.isdir(d):
            for pat in EXTS:
                for f in glob.glob(os.path.join(d, pat)):
                    for dest in (os.path.join(ws, 'tools'),
                                 os.path.join(ws, '.work', 'gate-kit', 'scripts')):
                        os.makedirs(dest, exist_ok=True)
                        shutil.copy2(f, os.path.join(dest, os.path.basename(f)))
                    n += 1
    # ---- 数据文件与自动探测（本次修：**必须真拷**，否则工作区缺手册 ⇒ pitfall_audit 无处可读）
    #   2026-09-19（脱敏批 · 方案乙）：随包的是**通用要点版**（防坑要点-TOP20.md，不带书名号＝避免被通用件巡检判为书目引用），
    #   完整内部手册**不随包**（用户拍板：内部手册只留作者本地）⇒ 这里只拷随包件。
    data = {}
    for f in ('防坑要点-TOP20.md', 'V3.1全量执行单.md'):
        src = next((os.path.join(d, f) for d in (gates, scr)
                    if os.path.isfile(os.path.join(d, f))), None)
        if src:
            shutil.copy2(src, os.path.join(ws, f))
            data[f] = os.path.join(ws, f)

    def _probe_node():
        c = [(os.environ.get('DSH_ENGINE_NODE') or '').strip()]
        h = (os.environ.get('DSH_HOME') or '').strip()
        _names = ('node.exe', 'node') if os.name == 'nt' else ('node', 'node.exe')
        for _e in ([os.path.join(os.path.dirname(h), 'engine')] if h else []) + \
                  [os.path.join(os.path.dirname(plug), 'engine')]:
            for _n in _names:
                c.append(os.path.join(_e, _n))
        return next((x for x in c if x and os.path.isfile(x)),
                    shutil.which('node') or shutil.which('node.exe'))

    def _probe_jsdir():
        c = [(os.environ.get('DSH_JS_YAML_DIR') or '').strip()]
        eng = []
        h = (os.environ.get('DSH_HOME') or '').strip()
        if h:
            eng.append(os.path.join(os.path.dirname(h), 'engine'))
        eng.append(os.path.join(os.path.dirname(plug), 'engine'))
        for e in eng:
            c.append(os.path.join(e, 'node_modules', 'js-yaml'))
            c += sorted(glob.glob(os.path.join(e, 'node_modules', '.pnpm', 'js-yaml@*')))
        for x in c:
            if x and os.path.isdir(x) and os.path.isfile(os.path.join(x, 'package.json')):
                return x
        return None

    cfgd = {'workspace_root': ws, 'tools_dir': os.path.join(ws, 'tools'),
            'work_dir': os.path.join(ws, '.work', 'gate-kit'),
            'manual_path': data.get('蒸馏工程避坑手册.md',
                                    os.path.join(ws, '蒸馏工程避坑手册.md')),
            'node_exe': _probe_node() or '', 'js_yaml_dir': _probe_jsdir() or ''}
    json.dump(cfgd, io.open(cfg, 'w', encoding='utf-8', newline='\n'),
              ensure_ascii=False, indent=1)
    print('   自动探测：node=%s ｜ js-yaml=%s'
          % (cfgd['node_exe'] or '(未找到，门禁会给指引)', cfgd['js_yaml_dir'] or '(未找到，门禁会给指引)'))
    print('   数据文件：%s' % ('、'.join(data) if data else '(包内未带，门禁判不适用)'))

    print('✔ 已初始化：%s' % ws)
    print('   配置：%s' % cfg)
    print('   装入 tools\\：%d 个文件' % n)
    missing = [f for f in ('V3.1全量执行单.md', '防坑要点-TOP20.md')
               if not os.path.isfile(os.path.join(ws, 'tools', f))
               and not os.path.isfile(os.path.join(ws, f))]
    if missing:
        print('   ⚠ 仍缺数据文件（部分门禁会判"不适用"而不是崩）：%s' % '、'.join(missing))
    print('\n下一步：\n  1) 写一本书的任务目录：%s\\.work\\<task>\\（含 skills\\、candidates\\）' % ws)
    print('  2) 开工门禁：python "%s"\n  3) 收尾门禁：python "%s"' % (
        os.path.join(ws, 'tools', 'preflight.py'), os.path.join(ws, 'tools', 'postflight.py')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
