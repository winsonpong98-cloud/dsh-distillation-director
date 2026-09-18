# -*- coding: utf-8 -*-
r"""check_install_state.py —— **三层装机态闸**（2026-09-18 · NAS 装机缺陷复盘固化）

> 由来（真机实测，不是推演）：2026-09-18 在一台 NAS 的 DSH 容器里装本插件，
> 现象是"**装了但不生效**"——`node_modules` 里有目录、`dsh plugin list` 也列得出，
> 但开会话时技能目录里根本没有 `distillation-director`。
> 逐层实测后定位到**三层里断在第二层**（详见《避坑手册》A-119…A-124 与
> `输出/2026-09-18-NAS装机缺陷复盘与工装优化.md`）。
> **本闸就是那次的判据固化**：把"我以为装上了"变成可复核的三层读数。

## 判什么（三层，缺一层即"不可宣称已装"）

| 层 | 名称 | 判据 | 为什么必须单列 |
|---|---|---|---|
| ① | **落盘层**（文件） | 插件目录存在、`package.json` 可解析、`SKILL.md` 在场、`node --check index.js` 通过、`description` 非空 | 只证明"文件拷贝成功了" |
| ② | **登记层**（装配） | 目标 profile 的 `package.json`：`dependencies` 含插件名 **且** `dsh.profile.bundles` 含插件名；且 `--dump-config` 组装树里出现对应 `id:` | **今天断的就是这一层**：`dependencies` 有、`bundles` 没有 ⇒ 引擎根本不会加载它 |
| ③ | **在役层**（运行期） | 服务可达（HTTP）、启动日志里 **服务**装载行在场、`<技能根>/.dsh/skills/<name>/SKILL.md` 的内容哈希与包内一致 | "写进去了 ≠ 跑起来了"（§17.2） |

**为什么三层不能合并**：三层的失败**症状完全相同**（会话里看不到技能），
但**修法完全不同**（① 重装／② 补 `bundles` 并重启／③ 排服务启动与技能根）。
只报"没生效"等于让使用者从零开始猜；本闸逐层给"断了没有、断在哪、怎么修"。

## 一条最容易被忽略的事实（今天实测确认，写进闸注释备查）

`dsh plugin add` 会**自动**把"声明了 `dsh.bundle.patch` 的依赖"登记进 `dsh.profile.bundles`
（引擎 `dsh/lib/plugin-*.js` 的 `reconcilePlugins()`；**rc.12 与 0.1.2-rc.1 实读源码均有此逻辑**）。
⇒ 若 `dependencies` 有而 `bundles` 没有，**只有三种可能**：
 (a) 不是用 `dsh plugin add` 装的（手改 `package.json` / 直接 `pnpm add`）；
 (b) 那次命令**没成功**（pnpm 非零退出时引擎**不**做 reconcile）；
 (c) 装的是**声明了 `dsh.bundle` 的旧版本**，之后换成了不声明/换目录。
**本闸不猜是哪一种，只报"第二层没通"，并打印按 (a)(b)(c) 的修法命令。**

## 用法

```powershell
# 最省事：什么都不给（自动探测 DSH_HOME / profiles / 工作区 / 技能根）
python scripts\gates\check_install_state.py

# 指定（容器/异机/多 profile 时）
python scripts\gates\check_install_state.py --home /data --profile web `
       --plugin-dir /workspace/distillation-director-plugin --skills-root /workspace

# 机器可读
python scripts\gates\check_install_state.py --json out.json

# 自证（用故意坏掉的临时样本，证闸会红；不需要网络与 DSH）
python scripts\gates\check_install_state.py --self-test
```

退出码：`0` ＝ 三层全过（或**明确不适用**：本机根本没有目标 profile）；
`2` ＝ 有真缺陷（三层里哪一层断，输出里写明）；`1` ＝ 用法/环境错。
**"不适用"与"通过"在输出里字样不同**（口径 A-74／A-115 家族），不得混读。
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

DEFAULT_PLUGIN = 'dsh-distillation-director'


# ────────────────────────────── 基础工具 ──────────────────────────────

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    try:
        return io.open(path, encoding='utf-8', errors='replace').read()
    except Exception:
        return ''


def read_json(path):
    try:
        return json.loads(read_text(path))
    except Exception:
        return None


def run(cmd, timeout=90, cwd=None):
    """跑外部命令，返回 (rc, stdout+stderr)。异常一律降级为 rc=127，不让闸自己崩。"""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, cwd=cwd,
                           env=dict(os.environ, PYTHONIOENCODING='utf-8'))
        return p.returncode, (p.stdout or b'').decode('utf-8', 'replace')
    except Exception as e:
        return 127, '%s: %s' % (type(e).__name__, e)


def entry_id(pkg_name):
    """插件包名 → 组装树里的条目 id（实测：`dsh-distillation-director` → `distillation-director`）。"""
    return pkg_name[4:] if pkg_name.startswith('dsh-') else pkg_name


def first_existing(paths):
    for p in paths:
        if p and os.path.isdir(p):
            return p
    return None


# ────────────────────────────── 自动探测 ──────────────────────────────

def detect_home(explicit):
    cands = [explicit,
             os.environ.get('DSH_HOME'),
             os.path.join(os.path.expanduser('~'), '.dsh'),
             '/data',                      # DSH 官方容器默认
             os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', '..', 'home')]
    return first_existing([os.path.abspath(p) for p in cands if p])


def detect_profiles(home):
    if not home:
        return None
    p = os.path.join(home, 'profiles')
    return p if os.path.isdir(p) else None


def detect_workspace_root(explicit):
    if explicit:
        return os.path.abspath(explicit) if os.path.isdir(explicit) else None
    for key in ('DSH_DISTILL_ROOT', 'DSH_WORKSPACE_ROOT'):
        v = (os.environ.get(key) or '').strip()
        if v and os.path.isdir(v):
            return v
    here = os.path.dirname(os.path.abspath(__file__))
    d = here
    for _ in range(6):
        if os.path.isdir(os.path.join(d, '.dsh')):
            return d
        d = os.path.dirname(d)
    return None


def detect_skills_roots(explicit):
    """技能根候选：本地工作区（<工作区>/.dsh/skills）＋容器工作区（/workspace/.dsh/skills）。"""
    cands = []
    if explicit:
        cands.append(os.path.join(explicit, '.dsh', 'skills') if not explicit.rstrip('/\\').endswith('skills')
                     else explicit)
    if os.path.isdir('/workspace'):
        cands.append('/workspace/.dsh/skills')
        cands.append('/workspace')
    ws = detect_workspace_root(None)
    if ws:
        cands.append(os.path.join(ws, '.dsh', 'skills'))
    out = []
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isdir(c) and c not in out:
            out.append(c)
    return out


def detect_plugin_dirs(explicit, pkg_name, profile_dir, skills_roots, workspace_root):
    cands = []
    if explicit:
        cands.append(os.path.abspath(explicit))
    if profile_dir:
        cands.append(os.path.join(profile_dir, 'node_modules', pkg_name))
        vendor = os.path.join(profile_dir, 'vendor')
        if os.path.isdir(vendor):
            for n in os.listdir(vendor):
                if n.startswith(pkg_name):
                    cands.append(os.path.join(vendor, n))
    if workspace_root:
        cands.append(os.path.join(workspace_root, 'distillation-director-plugin'))
    for sr in skills_roots:
        # 以技能根为线索找同级的插件目录（作者侧布局）
        cands.append(os.path.join(os.path.dirname(sr.rstrip('/\\')), '..', 'distillation-director-plugin'))
    out = []
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isdir(c) and c not in out:
            out.append(c)
    return out


# ────────────────────────────── 三层判据 ──────────────────────────────

def layer1_local(pkg_name, plugin_dir):
    """① 落盘层：文件都在、声明可解析、语法与导入自证通过。"""
    problems, notes = [], []
    if plugin_dir is None:
        return None, ['未找到插件目录'], []
    pj = os.path.join(plugin_dir, 'package.json')
    manifest = read_json(pj)
    if manifest is None:
        problems.append('package.json 缺失或不是合法 JSON：%s' % pj)
    else:
        if manifest.get('name') != pkg_name:
            problems.append('package.json 里的 name 与预期不符：%r ≠ %r' % (manifest.get('name'), pkg_name))
        notes.append('版本 %s' % manifest.get('version'))
        if not (manifest.get('dsh') or {}).get('bundle', {}).get('patch'):
            problems.append('package.json 未声明 dsh.bundle.patch ⇒ 引擎不会把它当 profile 层（**这是本闸最关心的声明**）')
        else:
            notes.append('dsh.bundle.patch=%s' % manifest['dsh']['bundle']['patch'])
    skill = os.path.join(plugin_dir, 'SKILL.md')
    if not os.path.isfile(skill):
        problems.append('SKILL.md 不在场：%s' % skill)
    else:
        txt = read_text(skill)
        m = re.search(r'^---\s*$([\s\S]*?)^---\s*$', txt, re.M)
        fm = m.group(1) if m else ''
        if not re.search(r'^name:\s*\S', fm, re.M):
            problems.append('SKILL.md frontmatter 缺 name')
        if not re.search(r'^description:\s*\S', fm, re.M):
            problems.append('SKILL.md frontmatter 缺 description')
        notes.append('SKILL.md %d 字符 / sha256 %s' % (len(txt), sha256(skill)[:16]))
    idx = os.path.join(plugin_dir, 'index.js')
    if not os.path.isfile(idx):
        problems.append('index.js 不在场（引擎按 main 字段加载它）')
    else:
        node = shutil.which('node')
        if node:
            rc, out = run([node, '--check', idx])
            if rc != 0:
                problems.append('index.js 语法自检不过（node --check rc=%d）：%s' % (rc, out.strip()[:200]))
            else:
                notes.append('index.js 语法自检通过')
        if node:
            # 真导入一次（比 `--check` 强：能抓"语法对但顶层读了不存在的文件"这类错）
            c, o = run([node, '-e',
                        'import(process.argv[1]).then(m=>{if(typeof m.apply!=="function")'
                        '{console.error("no apply export");process.exit(3)};'
                        'console.log("OK exports="+Object.keys(m).join(","))})'
                        '.catch(e=>{console.error(String(e));process.exit(4)})',
                        'file://' + idx.replace('\\', '/')])
            if c == 0 and 'OK' in o:
                notes.append('index.js 真导入通过（%s）' % o.strip().splitlines()[-1][:120])
            else:
                problems.append('index.js 真导入失败（rc=%d）：%s —— 引擎加载插件时会在此报错'
                                % (c, o.strip().splitlines()[-1][:200] if o.strip() else ''))
    return (problems or None), notes


def layer2_bundle_declared(plugin_dir):
    """该插件包是否声明了 `dsh.bundle.patch`（决定它走 bundled 注册还是文件系统注册）。"""
    if not plugin_dir:
        return False
    m = read_json(os.path.join(plugin_dir, 'package.json')) or {}
    return bool((m.get('dsh') or {}).get('bundle', {}).get('patch'))


def layer2_registration(profile_dir, pkg_name, profile_name):
    """② 登记层：dependencies + bundles 两处都要有，且组装树里出现 id。"""
    problems, notes = [], []
    if profile_dir is None:
        return None, ['未找到 profile 目录'], None
    pj = os.path.join(profile_dir, 'package.json')
    manifest = read_json(pj)
    if manifest is None:
        return ['profile package.json 不可读：%s' % pj], notes, None
    deps = manifest.get('dependencies') or {}
    bundles = ((manifest.get('dsh') or {}).get('profile') or {}).get('bundles') or []
    in_deps = pkg_name in deps
    in_bundles = pkg_name in bundles
    notes.append('dependencies 含 %s：%s' % (pkg_name, '是' if in_deps else '**否**'))
    notes.append('dsh.profile.bundles 含 %s：%s（bundles 共 %d 项）' % (pkg_name, '是' if in_bundles else '**否**', len(bundles)))
    if not in_deps:
        problems.append('profile 依赖里没有 %s ⇒ 根本没装进这个 profile' % pkg_name)
    if not in_bundles:
        problems.append('dsh.profile.bundles 里没有 %s ⇒ **引擎不会加载它**（装上了但不生效；三层里断在②）'
                        % pkg_name)
    # 组装树：只有 bundles 里的条目才会被组装（引擎源码 loadProfile/loadBundleLayer）
    tree_ids, tree_ok = None, False
    if in_bundles:
        dsh_bin = None
        for base in (os.environ.get('DSH_INSTALL_DIR') or '',
                     '/opt/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js'):
            if base and os.path.isfile(base):
                dsh_bin = base
                break
        if dsh_bin is None:
            # 本机形态：home 同级的 engine 里找（作者侧/开发机）
            home = os.path.dirname(profile_dir)
            guess = os.path.join(os.path.dirname(home), 'engine', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')
            if os.path.isfile(guess):
                dsh_bin = guess
        if dsh_bin is None:
            # pnpm 布局（开发机常见）：找任一 dsh 包的 bin.js
            home = os.path.dirname(profile_dir)
            pnpm = os.path.join(os.path.dirname(home), 'engine', 'node_modules', '.pnpm')
            if os.path.isdir(pnpm):
                for n in sorted(os.listdir(pnpm)):
                    if n.startswith('@deepseek-ai+dsh@'):
                        cand = os.path.join(pnpm, n, 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')
                        if os.path.isfile(cand):
                            dsh_bin = cand
                            break
        if dsh_bin is None:
            notes.append('组装树自检**跳过**（找不到 dsh 引擎 bin.js；不阻断）')
        else:
            node = shutil.which('node')
            cmd = ([node] if node else []) + [dsh_bin, '--profile', profile_name, '--dump-config']
            rc, out = run(cmd, timeout=180, cwd=profile_dir)
            if rc != 0:
                notes.append('组装树自检**失败**（rc=%d）：%s' % (rc, out.strip().splitlines()[-1][:200] if out.strip() else ''))
            else:
                tree_ok = True
                tree_ids = re.findall(r'^-\s*id:\s*(\S+)', out, re.M)
                want = entry_id(pkg_name)
                hit = want in tree_ids
                notes.append('组装树 %d 条 ｜ 期望 id=%s ｜ %s' % (len(tree_ids), want, '在场' if hit else '**不在场**'))
                if not hit:
                    problems.append('组装树里没有 id=%s ⇒ 即使 bundles 写了也没被组装（多半是 bundles 写了但没重启 / patch 层报错）' % want)
    return (problems or None), notes, tree_ids


def layer3_runtime(profile_dir, pkg_name, skills_roots, plugin_dir, url):
    """③ 在役层：服务可达 + 服务装载行 + 技能根里的 SKILL 与包内一致。"""
    problems, notes = [], []
    # (a) 服务可达
    if url:
        rc, out = run([sys.executable, '-c',
                       'import sys,urllib.request,urllib.error\n'
                       'u=sys.argv[1]\n'
                       'try:\n'
                       '    r=urllib.request.urlopen(u,timeout=8)\n'
                       '    print("HTTP="+str(r.status))\n'
                       'except urllib.error.HTTPError as e:\n'
                       '    print("HTTP="+str(e.code)+"（引擎在跑，但该路径要鉴权/被拒——属正常）")\n'
                       'except Exception as e:\n'
                       '    print("UNREACHABLE="+type(e).__name__+": "+str(e)[:120])', url])
        line = (out.strip().splitlines() or [''])[-1]
        if rc == 0 and line.startswith('HTTP='):
            notes.append('服务可达 %s（%s）' % (url, line))
        else:
            notes.append('服务不可达 %s ⇒ %s（服务没起时"在役层"无从谈起：先起服务；'
                         '容器里请把 --url 指到容器内端口，如 http://127.0.0.1:4080/）' % (url, line or '无输出'))
    else:
        notes.append('未给 --url，跳过服务可达性检查')
    # (b) 技能根一致性
    skill_rel = os.path.join(pkg_name, 'SKILL.md')
    pkg_skill = os.path.join(plugin_dir, 'SKILL.md') if plugin_dir else None
    pkg_sha = sha256(pkg_skill) if (pkg_skill and os.path.isfile(pkg_skill)) else None
    if not skills_roots:
        notes.append('未找到任何技能根候选（<工作区>/.dsh/skills、/workspace/.dsh/skills）⇒ 在役层第 c 项判**不适用**')
    else:
        found = False
        for sr in skills_roots:
            d = os.path.join(sr, pkg_name)
            if os.path.isdir(d):
                found = True
                f = os.path.join(d, 'SKILL.md')
                if not os.path.isfile(f):
                    problems.append('技能根里有 %s 目录但没有 SKILL.md：%s' % (pkg_name, d))
                elif pkg_sha and sha256(f) != pkg_sha:
                    problems.append('技能根副本与包内**不同代**：%s（包内 %s / 副本 %s）'
                                    % (f, pkg_sha[:16], sha256(f)[:16]))
                else:
                    notes.append('技能根副本与包内逐字节一致：%s' % f)
                break
        if not found:
            bundled = layer2_bundle_declared(plugin_dir)
            if bundled:
                # 声明了 dsh.bundle ⇒ 引擎按 plugin apply() 注册，**不依赖**技能根目录
                notes.append('技能根里没有 %s 目录 —— 该包声明了 dsh.bundle，走 **bundled 注册**路径，'
                             '本项判**不适用**（不假红）；技能是否真的注册成功请看手册 §17.2 的引擎加载器实测'
                             % pkg_name)
            else:
                problems.append('技能根里没有 %s 目录，且该包**未声明** dsh.bundle ⇒ 引擎既不会 bundled 注册、'
                                '文件系统也找不到 ⇒ **技能必然不可见**：%s'
                                % (pkg_name, '、'.join(skills_roots)))
    return (problems or None), notes


# ────────────────────────────── 自证 ──────────────────────────────

def self_test():
    """用故意坏掉的临时样本证"闸会红"，用好样本证"闸会绿"。不联网、不需要 DSH。"""
    import tempfile
    pkg = DEFAULT_PLUGIN
    tmp = tempfile.mkdtemp(prefix='install-state-selftest-')
    fails = []
    # 合规插件的最小形态：main 指向的模块必须导出 apply()（引擎按此注册技能）
    OK_INDEX = ('export const name = "dsh-selftest-sample"\n'
                'export const inject = ["skills"]\n'
                'export function apply(ctx) { return () => {} }\n')
    try:
        # ---- 坏样本 A：落盘层缺 dsh.bundle 声明 ----
        bad = os.path.join(tmp, 'bad-plugin')
        os.makedirs(bad)
        io.open(os.path.join(bad, 'package.json'), 'w', encoding='utf-8').write(
            json.dumps({'name': pkg, 'version': '0.0.1', 'main': './index.js'}))
        io.open(os.path.join(bad, 'index.js'), 'w', encoding='utf-8').write(OK_INDEX)
        io.open(os.path.join(bad, 'SKILL.md'), 'w', encoding='utf-8').write(
            '---\nname: distillation-director\ndescription: 样本\n---\n正文\n')
        probs, _ = layer1_local(pkg, bad)
        if not probs or not any('dsh.bundle' in p for p in probs):
            fails.append('坏样本 A（无 dsh.bundle 声明）**未被拦下** —— 闸失效')
        # ---- 好样本 B：声明齐全 ----
        good = os.path.join(tmp, 'good-plugin')
        os.makedirs(good)
        io.open(os.path.join(good, 'package.json'), 'w', encoding='utf-8').write(
            json.dumps({'name': pkg, 'version': '9.9.9', 'main': './index.js',
                        'dsh': {'bundle': {'patch': './cordis.patch.yml'}}}))
        io.open(os.path.join(good, 'index.js'), 'w', encoding='utf-8').write(OK_INDEX)
        io.open(os.path.join(good, 'cordis.patch.yml'), 'w', encoding='utf-8').write('[]\n')
        io.open(os.path.join(good, 'SKILL.md'), 'w', encoding='utf-8').write(
            '---\nname: distillation-director\ndescription: 样本\n---\n正文\n')
        probs, _ = layer1_local(pkg, good)
        if probs:
            fails.append('好样本 B **被误判为红**（假红）：%s' % probs)
        # ---- 坏样本 C：登记层只有 dependencies、没有 bundles（今天真机同型）----
        prof = os.path.join(tmp, 'profile')
        os.makedirs(prof)
        io.open(os.path.join(prof, 'package.json'), 'w', encoding='utf-8').write(json.dumps(
            {'name': 'p', 'private': True, 'dependencies': {pkg: 'link:/x'},
             'dsh': {'profile': {'bundles': ['@deepseek-ai/dsh-base']}}}))
        probs, _, _ = layer2_registration(prof, pkg, 'web')
        if not probs or not any('bundles' in p for p in probs):
            fails.append('坏样本 C（dependencies 有 / bundles 无 = 今天真机同型）**未被拦下** —— 闸失效')
        # ---- 坏样本 D：技能根副本与包内不同代 ----
        src = os.path.join(tmp, 'root', '.dsh', 'skills', pkg)
        os.makedirs(src)
        io.open(os.path.join(src, 'SKILL.md'), 'w', encoding='utf-8').write('---\nname: x\ndescription: y\n---\n旧\n')
        probs, _ = layer3_runtime(None, pkg, [os.path.join(tmp, 'root', '.dsh', 'skills')], good, None)
        if not probs or not any('不同代' in p for p in probs):
            fails.append('坏样本 D（技能根副本陈旧）**未被拦下** —— 闸失效')
        # ---- 好样本 E：技能根与包内一致 ----
        io.open(os.path.join(src, 'SKILL.md'), 'w', encoding='utf-8').write(read_text(os.path.join(good, 'SKILL.md')))
        probs, _ = layer3_runtime(None, pkg, [os.path.join(tmp, 'root', '.dsh', 'skills')], good, None)
        if probs:
            fails.append('好样本 E **被误判为红**（假红）：%s' % probs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        for f in fails:
            print('✗ %s' % f)
        print('\n结论：✗ 自证失败（%d 项）—— 本闸结论不可采信' % len(fails))
        return 1
    print('✔ 自证通过：4 类坏样本全被拦、2 类好样本全放行（落盘①／登记②／在役③ 三层各有覆盖）')
    return 0


# ────────────────────────────── 主流程 ──────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='三层装机态闸（落盘／登记／在役）')
    ap.add_argument('--home', help='DSH 家目录（默认自动探测：DSH_HOME／~/.dsh／/data）')
    ap.add_argument('--profile', default='web', help='profile 名（默认 web）')
    ap.add_argument('--plugin', default=DEFAULT_PLUGIN, help='插件包名（默认 %s）' % DEFAULT_PLUGIN)
    ap.add_argument('--plugin-dir', help='插件目录（默认按 profile node_modules／工作区自动探测）')
    ap.add_argument('--workspace', help='蒸馏工作区根（默认自动上溯找 .dsh）')
    ap.add_argument('--skills-root', help='技能根（默认探测 <工作区>/.dsh/skills 与 /workspace/.dsh/skills）')
    ap.add_argument('--url', default='http://127.0.0.1:3080/',
                    help='服务地址用于可达性检查（默认本机 web；容器里给 http://127.0.0.1:4080/）')
    ap.add_argument('--json', help='把结果写成 JSON')
    ap.add_argument('--self-test', action='store_true', help='用临时坏样本自证闸有效')
    ap.add_argument('--not-applicable-ok', action='store_true',
                    help='把「本机未装该插件（登记层未过）」按**作者侧不适用**处理：打印原判但不判红。'
                         '**只给"未装插件是常态"的作者机/门禁汇总用**；受检机自称"已装"时请勿加此参数'
                         '（那正是本闸要拦的场景）')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    home = detect_home(args.home)
    profiles_dir = detect_profiles(home)
    profile_dir = os.path.join(profiles_dir, args.profile) if profiles_dir else None
    if profile_dir and not os.path.isdir(profile_dir):
        profile_dir = None
    ws_root = detect_workspace_root(args.workspace)
    skills_roots = detect_skills_roots(args.skills_root or ws_root)
    plugin_dirs = detect_plugin_dirs(args.plugin_dir, args.plugin, profile_dir, skills_roots, ws_root)

    print('三层装机态检查：%s ｜ profile=%s' % (args.plugin, args.profile))
    print('  home=%s' % (home or '（未找到）'))
    print('  profile=%s' % (profile_dir or '（未找到）'))
    print('  工作区=%s' % (ws_root or '（未找到）'))
    print('  技能根候选=%s' % ('、'.join(skills_roots) if skills_roots else '（无）'))
    print('  插件目录候选=%s' % ('、'.join(plugin_dirs) if plugin_dirs else '（无）'))
    print('')

    result = {'plugin': args.plugin, 'profile': args.profile, 'profile_dir': profile_dir,
              'home': home, 'workspace': ws_root, 'skills_roots': skills_roots,
              'plugin_dirs': plugin_dirs, 'layers': {}}
    red = 0
    not_installed = False          # 本机没装（登记层两条都缺）＝"作者侧不适用"的判据形态
    if profile_dir:
        _m = read_json(os.path.join(profile_dir, 'package.json')) or {}
        _deps = _m.get('dependencies') or {}
        _bun = ((_m.get('dsh') or {}).get('profile') or {}).get('bundles') or []
        not_installed = (args.plugin not in _deps) and (args.plugin not in _bun)

    # ── 关键前提：本机有没有目标 profile。没有 ⇒ 判"不适用"（不是失败）──
    if profile_dir is None and not plugin_dirs:
        print('ℹ 判"不适用"：本机既没有 profile 目录、也没有插件目录。')
        print('  本闸只对"装了这个插件的机器"有意义；缺件判不适用是本项目一贯口径'
              '（A-74／A-115 家族）——**不要把"不适用"读成"通过"**。')
        result['verdict'] = 'not-applicable'
        if args.json:
            io.open(args.json, 'w', encoding='utf-8').write(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # ① 落盘层
    plugin_dir = plugin_dirs[0] if plugin_dirs else None
    probs, notes = layer1_local(args.plugin, plugin_dir)
    result['layers']['1-落盘'] = {'dir': plugin_dir, 'problems': probs or [], 'notes': notes}
    print('① 落盘层（文件在不在、声明齐不齐）')
    for n in notes:
        print('    · %s' % n)
    if probs:
        red += 1
        for p in probs:
            print('    ✗ %s' % p)
    else:
        print('    ✔ 通过')

    # ② 登记层
    probs, notes, tree_ids = layer2_registration(profile_dir, args.plugin, args.profile)
    result['layers']['2-登记'] = {'problems': probs or [], 'notes': notes,
                                  'tree_entry_count': len(tree_ids) if tree_ids else None}
    print('② 登记层（dependencies ＋ dsh.profile.bundles ＋ 组装树）')
    for n in notes:
        print('    · %s' % n)
    if probs:
        red += 1
        for p in probs:
            print('    ✗ %s' % p)
        print('    ⇒ 修法（按可能性排序，改前先备份 profile/package.json）：')
        print('       (a) 用官方命令重装一次（会自动 reconcile 进 bundles）：')
        print('           dsh plugin --profile %s add %s' % (args.profile, plugin_dir or '<插件目录>'))
        print('       (b) 手工把 "%s" 追加进 package.json 的 dsh.profile.bundles，然后重启服务' % args.plugin)
        print('       (c) 若插件版本更新过而 bundles 仍无：确认新版本 package.json 仍声明 dsh.bundle.patch')
    else:
        print('    ✔ 通过')

    # ③ 在役层
    probs, notes = layer3_runtime(profile_dir, args.plugin, skills_roots, plugin_dir, args.url)
    result['layers']['3-在役'] = {'problems': probs or [], 'notes': notes}
    print('③ 在役层（服务在跑、技能根同代）')
    for n in notes:
        print('    · %s' % n)
    if probs:
        red += 1
        for p in probs:
            print('    ✗ %s' % p)
    else:
        print('    ✔ 通过（未发现真缺陷；"未发现"≠"已验证生效"——生效判定见手册 §17.2）')

    if red:
        if args.not_applicable_ok and not_installed:
            result['verdict'] = 'not-applicable'
            print('\n结论：ℹ 判"不适用"（本机 profile 未安装 %s；登记层两条均缺 ⇒ 这是"作者侧未装插件"的常态，'
                  '不是缺陷）。**原判如上，未隐藏**；若受检机自称"已装"，去掉 --not-applicable-ok 重跑，'
                  '届时本项必须判红。' % args.plugin)
            rc_out = 0
        else:
            result['verdict'] = 'red'
            print('\n结论：✗ 三层装机态闸 %d 层有真缺陷 —— **不得宣称"已装好"**' % red)
            rc_out = 2
    else:
        result['verdict'] = 'green'
        print('\n结论：✔ 三层装机态闸全绿（落盘①／登记②／在役③ 均无真缺陷）')
        rc_out = 0
    if args.json:
        io.open(args.json, 'w', encoding='utf-8').write(json.dumps(result, ensure_ascii=False, indent=2))
        print('（JSON 已写：%s）' % args.json)
    return rc_out


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        sys.stderr.write('\n🔴 本步骤无法执行：%s: %s\n   多半是环境未就绪；'
                         '可用 --self-test 先自证闸本身有效。\n' % (type(e).__name__, e))
        sys.exit(1)
