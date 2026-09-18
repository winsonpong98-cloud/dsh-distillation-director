# -*- coding: utf-8 -*-
r"""gate_common.py —— 门禁套件的**工作区配置加载器**（一次配置、之后零参数）

═══ 为什么需要它（用户 2026-09-17 要求：「尽量少人工选择」）═══
原来的 7 个门禁脚本（`gate_start`／`gate_stage`／`gate_checklist`／`preflight`／`postflight`／
`gate_selftest`／`pitfall_audit`）每个都在顶部写死一整套本机常量
（`ROOT`／`TOOLS`／`WORK`／`MACH`／`FIN`／`EDU`／`NODE`／`JSDIR`／`BASELINE`／`MANUAL`），
共约 60 处工作区专属项（`tools\gate_genericity_scan.py` 实测）。
⇒ 换台电脑就得改 7 个文件。**本模块把这些常量收敛成一份 JSON 配置**：

    <工作区>\.dsh\gate-kit\workspace.json

查找顺序（**零参数即可用**）：
  1. 环境变量 `DSH_GATE_CONFIG` 指向的文件（显式覆盖，最高优先）
  2. 从**当前脚本位置**逐级上溯，找 `\.dsh\gate-kit\workspace.json`
  3. 从**当前工作目录**逐级上溯，同上
  4. 都没有 ⇒ **响亮退出并指向 `gate_bootstrap.py`**（不猜、不静默降级）

配置字段（缺项一律给**保守默认**；`hosts` 缺项则该线相关的检查**标记为不适用**而不是假红）：

    {
      "workspace_root": "D:\\...\\<你的蒸馏工作区>",
      "tools_dir":      "<root>\\tools",
      "work_dir":       "<root>\\.work\\gate-kit",       # 门禁临时/基线产物
      "mach_dir":       "<root>\\<原书树>\\三闸机器化",     # 机器层脚本所在（可缺）
      "manual_path":    "<root>\\蒸馏工程避坑手册.md",      # 可缺 ⇒ pitfall_audit 判"不适用"
      "hosts": {                                         # 宿主工作区（技能库所在）
        "<name>": {"path": "D:\\...\\<宿主>", "expect_skills": null}
      },
      "node_exe":  "C:\\...\\node.exe",                  # 可缺 ⇒ 需要它的检查判"不适用"
      "js_yaml_dir": "C:\\...\\js-yaml@4.3.2",           # 可缺 ⇒ 同上
      "book_trees": ["<原书树目录名>"]
    }

用法（脚本内）：
    from gate_common import cfg
    ROOT, TOOLS, WORK = cfg.root, cfg.tools, cfg.work
    FIN = cfg.host('fin')          # 返回路径或 None（缺则调用方判"不适用"）
    print(cfg.describe())          # 打印来源与关键字段（自证用）

**只读**：本模块不写任何文件（写配置是 `gate_bootstrap.py` 的事）。
"""
import io
import glob
import json
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

CONFIG_REL = os.path.join('.dsh', 'gate-kit', 'workspace.json')
ENV_KEY = 'DSH_GATE_CONFIG'


def _ancestors(path):
    p = os.path.abspath(path)
    while True:
        yield p
        parent = os.path.dirname(p)
        if parent == p:
            return
        p = parent


def _candidates():
    seen = []
    envp = os.environ.get(ENV_KEY, '').strip()
    if envp:
        seen.append(envp)
    for base in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
        for anc in _ancestors(base):
            c = os.path.join(anc, CONFIG_REL)
            if c not in seen:
                seen.append(c)
    return seen


def _resolve_node(declared=None):
    """node 可执行文件解析链（顺序即优先级；**任一步命中即返回**，全不命中返回 None）。
    1) gate-kit 配置里的 node_exe（作者/自定义显式指定）
    2) 环境变量 DSH_ENGINE_NODE（DSH 宿主注入）
    3) <DSH_HOME>/../engine/node.exe（DSH 安装布局：home 与 engine 同级）
    4) 工作站根的兄弟目录 ../engine/node.exe
    5) PATH 上的 node／node.exe（用户自装 node）
    说明：**不得静默返回 None** —— 调用方必须打印"哪一步都没命中"的可执行指引。"""
    _c = [(declared or '').strip()]
    _c.append((os.environ.get('DSH_ENGINE_NODE') or '').strip())
    # 跨平台：Windows 是 node.exe，Linux／macOS（含 NAS／Docker）是 node（无扩展名）——
    # 两种都试，别把平台写死（2026-09-17：为 NAS 的 Linux 容器收口）。
    _names = ('node.exe', 'node') if os.name == 'nt' else ('node', 'node.exe')
    _homes = []
    _home = (os.environ.get('DSH_HOME') or '').strip()
    if _home:
        _homes.append(os.path.join(os.path.dirname(_home), 'engine'))
    _homes.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               '..', 'engine'))
    for _e in _homes:
        for _n in _names:
            _c.append(os.path.join(_e, _n))
    for _p in _c:
        if _p and os.path.isfile(_p):
            return os.path.abspath(_p)
    return shutil.which('node') or shutil.which('node.exe') or None


def _resolve_jsdir(declared=None):
    """js-yaml 目录解析链（顺序即优先级；任一步命中即返回，全不命中返回 None）。
    1) gate-kit 配置里的 js_yaml_dir  2) 环境变量 DSH_JS_YAML_DIR
    3) <DSH_HOME>/../engine/node_modules/.pnpm/js-yaml@*（DSH 安装布局，随引擎自带）
    4) 兄弟 ../engine/node_modules/{.pnpm/js-yaml@*,js-yaml}
    说明：**不得静默返回 None** —— 调用方须打印"哪一步都没命中"的可执行指引。"""
    _c = [(declared or '').strip(), (os.environ.get('DSH_JS_YAML_DIR') or '').strip()]
    _eng = []
    _home = (os.environ.get('DSH_HOME') or '').strip()
    if _home:
        _eng.append(os.path.join(os.path.dirname(_home), 'engine'))
    _eng.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             '..', 'engine'))
    for _e in _eng:
        _c.append(os.path.join(_e, 'node_modules', 'js-yaml'))
        _c += sorted(glob.glob(os.path.join(
            _e, 'node_modules', '.pnpm', 'js-yaml@*')))
    def _ok_js(_x):
        # 认两种形态：直接是包目录（有 package.json），或 pnpm 外层
        # `.pnpm/js-yaml@x/`（它的 package.json 在 `node_modules/js-yaml/` 里）
        return bool(_x) and os.path.isdir(_x) and (
            os.path.isfile(os.path.join(_x, 'package.json')) or
            os.path.isfile(os.path.join(_x, 'node_modules', 'js-yaml', 'package.json')))
    for _p in _c:
        if _ok_js(_p):
            if os.path.isfile(os.path.join(_p, 'package.json')):
                return os.path.abspath(_p)
            return os.path.abspath(os.path.join(_p, 'node_modules', 'js-yaml'))
    return None


class Config(object):
    def __init__(self, data, src):
        self.src = src
        self.data = data or {}
        root = (self.data.get('workspace_root') or '').strip()
        if not root:
            # 兜底：若配置文件本身就在 <root>\.dsh\gate-kit\ 下，可反推 root
            if src and src.endswith(CONFIG_REL.replace('/', os.sep)):
                root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(src))))
        self.root = root or os.getcwd()
        self.tools = (self.data.get('tools_dir') or '').strip() or os.path.join(self.root, 'tools')
        self.work = (self.data.get('work_dir') or '').strip() or os.path.join(self.root, '.work', 'gate-kit')
        self.mach = (self.data.get('mach_dir') or '').strip() or None
        self.manual = (self.data.get('manual_path') or '').strip() or None
        self.node = _resolve_node(self.data.get('node_exe'))
        self.jsdir = _resolve_jsdir(self.data.get('js_yaml_dir'))
        self.book_trees = [x for x in (self.data.get('book_trees') or []) if x] or ['投资蒸馏']
        self.hosts = self.data.get('hosts') or {}

    # ── 访问器（缺项返回 None，调用方据此判"不适用"，**不假红**）────────────────
    @property
    def scripts_dir(self):
        r"""配套脚本目录（yaml_check_generic.cjs／check_md_tables.py／machine_scan_*.py 等所在）。

        **可缺**：缺则依赖它的检查判不适用（**不假红**）——不是每个使用者都需要作者的全套配套脚本。
        """
        return (self.data.get('scripts_dir') or '').strip() or None

    @property
    def pitfall_manual(self):
        return self.manual

    def host(self, name):
        h = self.hosts.get(name) or {}
        return (h.get('path') or '').strip() or None

    def host_expect(self, name):
        h = self.hosts.get(name) or {}
        return h.get('expect_skills')

    def host_names(self):
        return sorted(self.hosts)

    def has_mach(self):
        return bool(self.mach and os.path.isdir(self.mach))

    def has_manual(self):
        return bool(self.manual and os.path.exists(self.manual))

    def has_node(self):
        return bool(self.node and os.path.exists(self.node))

    def has_jsdir(self):
        return bool(self.jsdir and os.path.isdir(self.jsdir))

    def describe(self):
        def ok(p):
            return ('✔' if p and os.path.exists(p) else '✗') + (p or '(未配置)')
        L = ['门禁配置来源：%s' % (self.src or '(未找到)'),
             '  root      %s' % self.root,
             '  tools     %s' % ok(self.tools),
             '  work      %s' % self.work,
             '  mach      %s' % ok(self.mach),
             '  manual    %s' % ok(self.manual),
             '  node      %s' % ok(self.node),
             '  js-yaml   %s' % ok(self.jsdir),
             '  book_trees %s' % self.book_trees]
        for n in self.host_names():
            L.append('  host[%-8s] %s' % (n, ok(self.host(n))))
        return '\n'.join(L)


def load(required=True):
    """加载配置。找不到且 `required=True` ⇒ 打印指引并 `SystemExit(2)`（**响亮拒跑**）。"""
    for c in _candidates():
        if c and os.path.isfile(c):
            try:
                d = json.loads(io.open(c, encoding='utf-8').read())
            except Exception as e:
                sys.stderr.write('🔴 门禁配置解析失败：%s（%s: %s）\n'
                                 '   常见原因：中文引号写成裸 ASCII 双引号（见《避坑手册》A-70）\n'
                                 % (c, type(e).__name__, e))
                raise SystemExit(2)
            return Config(d, c)
    if not required:
        return Config({}, None)
    sys.stderr.write(
        '🔴 未找到门禁配置（%s）。\n'
        '   查找顺序：① 环境变量 %s ② 从脚本所在目录上溯 ③ 从当前目录上溯，找 `%s`\n'
        '   一次性生成（约 10 秒，之后**无需再给任何参数**）：\n'
        '       python gate_bootstrap.py --workspace "<你的蒸馏工作区>" '
        '--host fin="<金融类宿主>" --host edu="<教育类宿主>"\n'
        '   只用一个宿主时：`--host main="<宿主工作区>"` 即可。\n'
        % (CONFIG_REL, ENV_KEY, CONFIG_REL))
    raise SystemExit(2)


class _LazyCfg(object):
    """惰性代理：**首次访问属性时才加载配置**。

    为什么必须惰性（设计自伤登记）：最初写成模块级 `cfg = load(required=True)`，
    结果是**连生成配置的引导脚本一 import 也会被卡死**（引导脚本要先用本模块探测→写配置，
    却又因为"配置不存在"而在 import 阶段退出）——**循环依赖**。
    惰性化后：`import gate_common` 永远安全；只有在**真的要用配置**时才要求它存在。
    """

    _real = None

    def _get(self):
        if _LazyCfg._real is None:
            _LazyCfg._real = load(required=True)
        return _LazyCfg._real

    def __getattr__(self, item):
        return getattr(self._get(), item)


# 模块级入口：`from gate_common import cfg`（惰性，import 无副作用）
cfg = _LazyCfg()


# ── None 安全网（2026-09-17）：取不到的 host/机器目录一律返回 ''，避免 os.path.join(None,…) 崩溃
def _none_safe():
    try:
        for _a in ("mach", "manual", "manual_path", "work", "tools", "root"):
            if getattr(cfg, _a, None) is None:
                setattr(cfg, _a, "")
        _orig = cfg.host
        cfg.host = lambda *a, **k: (_orig(*a, **k) or "")
    except Exception:
        pass


_none_safe()
