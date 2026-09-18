# -*- coding: utf-8 -*-
"""gate_checklist.py —— 执行单产物存在性闸（§21.3 候选工装 → 已建成 · 2026-09-13 晚 · 包 4.6.2）

背景：§21.6 第 2 条（执行单制）此前只有两道半闸——gate_start 闸③查"执行单文件存在＋形态"、
gate_stage 查"六阶段产物"；**执行单 36 项逐项的"证据登记＋产物存在"无人机查**，而「某书」# generic-ok: PROVENANCE
事故跳过的五项（自查表／独立 I/O／防线4／d8／账本）恰全在这个盲区。本闸把 V3.1 纪律 1 的
"每完成一项记证据与日期"变成 rc 检查；用户指令（2026-09-13 晚）：「现在做，我有时候不值守」。

判据（两查，均已在此登记＝非悬空口径）：
  A 证据闸：36 项每行"完成日期"列非空；空 ⇒ 🔴。豁免仅一种：该条目在执行单 §4 例外登记表
    中且"用户确认"列非空（例外必须用户确认——本闸只认登记，不替用户追认）。
  B 产物闸：登记于 ARTIFACT_MAP 的条目（27 项），其"证据文件"产物在任务目录（＋可选
    checklist-roots.json 声明的附加根）内能 glob 到 ≥1 个非空文件；找不到 ⇒ 🔴。
    证据类条目（EVIDENCE_ONLY，9 项：过程纪律／全局文件／日志类，产物无法逐任务定位）只查 A。
    产物名含 <slug> 的用任务名替换。产物形态宽紧的校准用 --report-only 在真实任务上跑。

用法：
  python tools\\gate_checklist.py --task <slug>              # 闸模式（rc=1 ⇒ 不得宣称执行单已完成）
  python tools\\gate_checklist.py --task <slug> --report-only # 校准模式（只报不拦，rc=0）
  python tools\\gate_checklist.py --work <dir>               # 自证用：显式指定任务目录
退出码：0 全绿 ｜ 1 有缺项 ｜ 2 执行单缺失/形态不符
"""
import os
import io
import re
import sys
import glob as _glob

if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ── 工作区常量：由 `gate_common` 从 .dsh\gate-kit\workspace.json 读取（A-81 通用化）──
#   一次性配置：`python gate_bootstrap.py --workspace "<工作区>" [--host name=路径]`
#   之后本脚本**零参数**可用；缺项由 `cfg` 返回 None ⇒ 调用方判"不适用"（**不假红**）。
import os as _os_, sys as _sys_
_HERE = _os_.path.dirname(_os_.path.abspath(__file__))
for _c in (_HERE,
           _os_.path.join(_os_.path.dirname(_HERE), 'distillation-director-plugin', 'scripts', 'gates')):
    if _c not in _sys_.path:
        _sys_.path.insert(0, _c)
from gate_common import cfg as _cfg
ROOT = _cfg.root
TOOLS = _cfg.tools
# ⚠ 三个"工作目录"必须分开（本节自伤登记 · 实测抓出）：
#   `WORK`      = **配套脚本目录**（`yaml_check_generic.cjs`／`check_md_tables.py`／`machine_scan_*.py` 等所在）
#                 ——旧常量 `WORK = <root>\.work\<配套脚本目录>` 指的就是它；首版被我换成 cfg.work ⇒
#                 `subprocess ... cwd=WORK` 指向新目录 ⇒ `NotADirectoryError`（该目录下没有那些 .cjs）。
#   `GATE_WORK` = **门禁自己的产物目录**（基线／沙箱／临时 json）——来自 `cfg.work`
#   `MACH`      = **机器层权威脚本目录**——来自 `cfg.mach`
WORK = _cfg.scripts_dir or _os_.path.join(ROOT, '.work', 'gate-kit', 'scripts')
GATE_WORK = _cfg.work
MACH = _cfg.mach
# ⚠ 两个"手册"必须分开（本节自伤登记 · 实测抓出）：
#   `MANUAL`   = **技能手册 SKILL.md**（开工收据比对的哈希对象；`gate_start` 用它）
#   `PITFALL_MANUAL` = **《避坑手册》**（`pitfall_audit` 对账对象）——它来自 `cfg.manual`
#   首版把两者统一成 `cfg.manual` ⇒ `gate_start` 拿《避坑手册》去比收据哈希 ⇒
#   `🔴 闸1 收据=59d3… 当前=03a3…（手册已改版）` **假红**（同名不同物，A-04 家族）。
MANUAL = _os_.path.join(ROOT, '.dsh', 'skills', 'distillation-director', 'SKILL.md')
PITFALL_MANUAL = _cfg.manual
NODE_EXE = _cfg.node
JS_YAML_DIR = _cfg.jsdir
BASELINE = _os_.path.join(TOOLS, '_mtime_baseline.json')
_WS_PARENT = _os_.path.dirname(ROOT)
FIN_DIR = _cfg.host('fin') or _os_.path.join(_WS_PARENT, '金融投资')
EDU_DIR = _cfg.host('edu') or _os_.path.join(_WS_PARENT, '家庭教育')
MAIN_DIR = _cfg.host('main') or _cfg.host('fin') or _WS_PARENT
MACH_TOOL = _os_.path.join(MACH, 'machine_precheck_v2.py') if MACH else None
MBASE = _os_.path.join(TOOLS, '_machine_baseline.json')
SANDBOX = _os_.path.join(TOOLS, '_selftest')
FIN = FIN_DIR
EDU = EDU_DIR
MAIN = MAIN_DIR
NODE = NODE_EXE
JSDIR = JS_YAML_DIR
def _official_expected_n():
    """**官方项数从模板自动推导**（不再硬编码）。

    ⚠ 根因登记（2026-09-17 · 用户指令"把问题彻底的解决"）：本常量曾写死 36，
    而官方模板（`投资蒸馏\\三闸机器化\\V3.1全量执行单.md`）与手册 §22.4 **早已是 37 项**
    （§22.4 明文「执行单已加第 37 项…供后续每本书继承」）⇒ #37 被判
    「超出官方 36 项的附加行（**信息性，不拦**）」⇒ **手册声称的强制项没有任何闸看一眼**
    （本册 #37 的"完成日期"格至今是空的，闸也不报）。这是 `A-53` 家族（清单不同代）的活体。

    正解：**项数只有一处权威＝官方模板**；本闸**读它**，并在读不到时**报错而不是回落常量**
    （回落＝静默降级，`A-74`）。
    """
    # 模板定位解析链（**不得写死书树名**）：cfg.env → <root>/tools（随包那份）→ <root> → book_trees → 旧路径
    tpl = None
    _cands = []
    try:
        _cands.append((_cfg.checklist_template or '').strip())
    except Exception:
        pass
    _cands.append((os.environ.get('DSH_CHECKLIST_TEMPLATE') or '').strip())
    _cands.append(os.path.join(ROOT, 'tools', 'V3.1全量执行单.md'))
    _cands.append(os.path.join(ROOT, 'V3.1全量执行单.md'))
    try:
        for _bt in (_cfg.book_trees or []):
            _cands.append(os.path.join(ROOT, _bt, '三闸机器化', 'V3.1全量执行单.md'))
    except Exception:
        pass
    _cands.append(os.path.join(ROOT, '投资蒸馏', '三闸机器化', 'V3.1全量执行单.md'))
    for _c in _cands:
        if _c and os.path.isfile(_c):
            tpl = _c
            break
    if not tpl:
        print('🔴 找不到《V3.1全量执行单》模板（找过 tools/ 、根目录、book_trees、旧路径）——'
              '请跑 init_workspace 或用 DSH_CHECKLIST_TEMPLATE 指定')
        return None, None
    if not tpl:
        print('🔴 找不到《V3.1全量执行单》模板（找过：<root>/tools/、<root>/、book_trees、旧路径）——请跑 init_workspace 或用 DSH_CHECKLIST_TEMPLATE 指定')
        return 1
    if not _os_.path.isfile(tpl):
        return None, tpl
    nums = []
    for ln in io.open(tpl, encoding='utf-8', errors='ignore').read().split('\n'):
        m = re.match(r'^\|\s*(\d+)\s*\|', ln)
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) if nums else None), tpl


EXPECTED_N, TPL_PATH = _official_expected_n()
if not EXPECTED_N:
    sys.exit('🔴 读不到官方执行单模板的项数（%s）——**不回落硬编码常量**（A-74 静默降级）。' % TPL_PATH)
# 【2026-09-17 · 9 维旧口径剔除】原 #19「B 档权威评分（darwin9-scorecard）」已从官方模板**剔除**
#   （依据：现行手册 §5.3「达尔文体检（判态，替换 9 维打分）」／§14「权重表已废除」／§15 替换对照表；
#     §0.2 现行原文为「B 档数字分（按需）…默认不跑」，与该行引用的 §15.2（已不在手册内）相矛盾）。
#   处置：**行号 19 保留但标记为"已剔除"**（不重编号，避免打断既有引用与历史留痕）。
#   本闸对 #19 的判据：**只要求该行存在且写明"已剔除"，不要求任何产物**（产物类不再纳入 ARTIFACT_MAP）。
#   历史留存：剔除前的旧口径与判据见《蒸馏工程避坑手册》A-54（备查，不复活）。
DROPPED_ITEMS = {19}
DROPPED_MARK = '已剔除'


# —— 产物映射（登记口径）：条目# → glob 模式列表（相对任务目录；** 递归；<slug>→任务名）
ARTIFACT_MAP = {
    1: ['**/parts/**', '**/ocr*/**', '**/*ocr*', '**/*文本提取*'],
    2: ['BOOK_OVERVIEW.md', '**/BOOK_OVERVIEW*.md'],
    3: ['**/candidates/**', '**/notes/**', '**/extractor-prompts/**'],
    4: ['**/verified*.md', '**/verified*/**'],
    5: ['**/blind-*', '**/blind*/**'],
    6: ['**/skills/*/SKILL.md', '**/SKILL.md'],
    7: ['**/*selfcheck*', '**/*self-check*', '**/*自查*'],
    8: ['**/candidates/**', '**/*candidates*'],
    9: ['**/skills/*/SKILL.md', '**/SKILL.md'],
    10: ['**/*rquote*'],
    11: ['**/*defense3*'],
    12: ['**/*fidelity*', '**/*io*judge*', '**/*io*verify*'],
    13: ['**/*防线4*', '**/*目录覆盖*'],
    14: ['**/readycheck*.json', '**/*readycheck*'],
    15: ['**/*machine*report*', '**/*machine_static*', '**/*machine*precheck*'],
    16: ['**/*blind-machine*', '**/*judge-subset*', '**/blind*/**'],
    17: ['**/*d8*', '**/*full*test*'],
    18: ['**/*darwin*judge*', '**/*darwin*/**'],
    20: ['**/*polish*'],
    21: ['**/gates-*.json'],
    22: ['PIPELINE_STATE.md', '**/PIPELINE_STATE.md', '**/*账本*', '**/*ledger*'],
    23: ['**/*交付报告*.md', '**/DIGEST*', '**/*DIGEST*', '**/*报告*.md'],
    25: ['**/*engine*'],
    26: ['**/*blind*judge*', '**/*盲测*'],
    27: ['**/*route*overlap*', '**/*重叠*'],
    29: ['**/*口径*登记*'],
    30: ['**/*fair*regression*', '**/*公平回归*'],
    33: ['**/*装机*'],  # 条件项：本册要装才需要；无产物时须"不适用"豁免路径
}
# —— 证据类（只查 A）：24 全工作区行为／28 过程纪律／31·34·35·36 收尾与门禁日志／32 无产物（—）
EVIDENCE_ONLY = {24, 28, 31, 32, 34, 35, 36}


def _is_confirmed(cell):
    """『用户确认』列必须是肯定式才认（A-36：『待用户确认』不是确认）。"""
    s = (cell or '').strip().strip('*`_ ').strip()
    if not s:
        return False
    low = s.lower()
    for k in ('待', '未', '否', 'no', 'todo', 'pending', 'n/a'):
        if k in low:
            return False
    if s.strip('-—–') == '':  # 纯占位符（--- / — / –）
        return False
    return True


def parse_checklist(path):
    """返回 (rows{no:(desc,artifact,cell_last)}, rows_cnt, exceptions{no}, err)"""
    if not os.path.exists(path):
        return {}, 0, set(), '执行单.md 不存在 ⇒ 违反 V3.1 纪律1'
    t = io.open(path, encoding='utf-8').read()
    lines = t.splitlines()
    rows, dup = {}, []
    for ln in lines:
        if re.match(r'^\|\s*\d+\s*\|', ln):
            cells = [c.strip() for c in ln.strip().strip('|').split('|')]
            if len(cells) < 5:
                continue
            no = int(cells[0])
            rec = (cells[1], cells[3] if len(cells) > 3 else '', cells[-1])
            if no in rows and rows[no][-1] and not rec[-1]:
                continue  # 保留已填日期的那行
            if no in rows:
                dup.append(no)
            rows[no] = rec
    # 例外登记（§4）：| 日期 | 不执行项# | 原因 | 用户确认 |
    # ⚠ 自伤 A-36（2026-09-13）：旧实现取"首个含『例外登记』字样的行"＋固定 12 行窗口——
    #   而 §2 执行项表第 3 行的**正文**里就写着"见第 4 节例外登记"，于是**把 §2 表当例外表读**：
    #   #7 描述含"9 维表"→ 误登记 #9；#11 描述含"0 候选"→ 误登记 #0；
    #   且 cells[4] 的"**待用户确认**"非空即被当成"用户已确认"⇒ **#9 被静默豁免**。
    #   正确口径：只认**标题行**（`## 4. 例外登记`）之后的表，读到下一个标题为止；
    #   且"用户确认"列必须是**肯定式**（含 待/未/否/TODO/pending 一律不算）。
    exc = set()
    hdr = None
    for i, l in enumerate(lines):
        if re.match(r'^#{1,6}\s', l) and '例外登记' in l:
            hdr = i
            break
    if hdr is not None:
        for ln in lines[hdr + 1:]:
            if re.match(r'^#{1,6}\s', ln):
                break  # 表随本节结束而结束，禁越界读下文
            m = re.match(r'^\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]*)\|', ln)
            if not (m and m.group(1).strip() and m.group(2).strip()):
                continue
            if not _is_confirmed(m.group(4)):
                continue
            for part in re.split(r'[、,，/ ]+', m.group(2).strip()):
                part = part.lstrip('#').strip()
                if part.isdigit():
                    exc.add(int(part))
    err = None
    if len(rows) < 30 or '例外登记' not in t:
        err = '形态不符：编号执行项 %d（要求 ≥30）、例外登记节 %s' % (
            len(rows), '有' if '例外登记' in t else '缺')
    return rows, len(rows), exc, (err, dup) if dup else err


def find_artifact(no, artifact, work, extra_roots):
    pats = ARTIFACT_MAP.get(no)
    if not pats:
        return None  # 证据类
    roots = [work] + [r for r in extra_roots.get(str(no), []) + extra_roots.get(no, [])]
    slug = os.path.basename(os.path.normpath(work))
    for root in roots:
        root = root if os.path.isabs(root) else os.path.join(ROOT, root)
        if not os.path.isdir(root):
            continue
        for p in pats:
            p = p.replace('<slug>', slug)
            for hit in _glob.glob(os.path.join(root, p), recursive=True):
                if os.path.isfile(hit) and os.path.getsize(hit) > 0:
                    return hit
    return None


def main():
    args = sys.argv[1:]
    report_only = '--report-only' in args
    task, work_override = None, None
    for i, a in enumerate(args):
        if a == '--task':
            task = args[i + 1]
        if a == '--work':
            work_override = args[i + 1]
    work = work_override or os.path.join(ROOT, '.work', task or '')
    if not work_override and not task:
        print('用法：--task <slug> ／ --work <dir>（另可 --report-only）')
        sys.exit(2)
    rows, cnt, exc, err = parse_checklist(os.path.join(work, '执行单.md'))
    if err is not None:
        msg = err if isinstance(err, str) else '形态不符（含重复条目行 %s）' % err[1]
        print('🔴 %s ｜ 任务目录：%s' % (msg, work))
        sys.exit(2)
    extra_roots = {}
    rj = os.path.join(work, 'checklist-roots.json')
    if os.path.exists(rj):
        try:
            import json
            extra_roots = json.loads(io.open(rj, encoding='utf-8').read())
        except Exception as e:
            print('⚠ checklist-roots.json 解析失败（忽略附加根）：%s' % e)

    print('=== 执行单逐项闸（gate_checklist）｜ 任务：%s ＋ %s' % (
        os.path.basename(os.path.normpath(work)), '校准模式（只报不拦）' if report_only else '闸模式'))
    miss_ev, miss_art, exd, ok_n = [], [], [], 0
    for no in range(1, EXPECTED_N + 1):
        if no not in rows:
            miss_ev.append((no, '缺行'))
            print('  🔴 #%-2d 缺行（执行单须含全部 %d 项）' % (no, EXPECTED_N))
            continue
        desc, artifact, cell = rows[no]
        if no in DROPPED_ITEMS:
            # 已剔除项：只要求该行写明剔除以留痕，**不要求任何产物、不计入例外**
            if DROPPED_MARK in desc or DROPPED_MARK in str(cell):
                ok_n += 1
                print('  ⚫ #%-2d 已剔除（9 维旧口径，无需产物）｜ %s' % (no, desc[:40]))
            else:
                miss_ev.append((no, '已剔除项未写明剔除'))
                print('  🔴 #%-2d 已剔除项未写明「已剔除」｜ %s' % (no, desc[:40]))
            continue
        if no in exc:
            exd.append(no)
            print('  ⚪ #%-2d 例外登记（用户确认）｜ %s' % (no, desc[:30]))
            continue
        if not cell:
            miss_ev.append((no, '未记证据/日期'))
            print('  🔴 #%-2d 未记证据/日期 ｜ %s' % (no, desc[:36]))
            continue
        if no in ARTIFACT_MAP:
            hit = find_artifact(no, artifact, work, extra_roots)
            if hit and no != 33:
                ok_n += 1
                print('  ✔ #%-2d 产物：%s' % (no, os.path.relpath(hit, work)))
                continue
            if no == 33:  # 条件项：无装机产物 ⇒ 视为"未装机"，日期已记即可
                ok_n += 1
                print('  ✔ #%-2d 装机类：无装机产物（未装即不适用，日期已记）' % no)
                continue
            miss_art.append((no, artifact))
            print('  🔴 #%-2d 产物未找到（期望 %s）｜ %s' % (no, artifact, desc[:24]))
            continue
        ok_n += 1
        print('  ✔ #%-2d 证据已记（证据类条目）｜ %s' % (no, desc[:30]))
    if rows:
        extra = [n for n in rows if n > EXPECTED_N]
        if extra:
            print('  ℹ 超出官方 %d 项的附加行：%s（信息性，不拦）' % (EXPECTED_N, sorted(extra)))
    bad = miss_ev + miss_art
    print('---')
    print('小结：✔ %d ／ ⚪ 例外 %d ／ 🔴 缺 %d%s' % (
        ok_n, len(exd), len(bad),
        ('：' + '、'.join('#%d(%s)' % (n, w) for n, w in bad[:8]) + ('…' if len(bad) > 8 else '')) if bad else ''))
    if bad and not report_only:
        print('结论：🔴 执行单未逐项完成 —— 未过前不得宣称"闸已过"（证据闸 V3.1 纪律1 ＋ 产物闸 §21.3）')
        sys.exit(1)
    print('结论：%s' % ('✔ 执行单逐项完成（%d 项证据＋产物在位，例外 %d）' % (ok_n, len(exd))
                      if not bad else '（校准模式：%d 项缺，仅供参考，不拦）' % len(bad)))
    sys.exit(0)


if __name__ == '__main__':
    main()
