# -*- coding: utf-8 -*-
"""check_script_sync.py —— 机器脚本一致性检查（权威目录 ↔ 插件包副本）

为什么需要它：工作区里长期存在**两处同名机器脚本**（`投资蒸馏/三闸机器化/` 与
`distillation-director-plugin/scripts/`），2026-09-12 实测已发现两处漂移
（`machine_precheck_v2.py`、`machine_layer_readycheck.py`）。`distillation-director` 技能正文
指向 `投资蒸馏/三闸机器化/`，故该处为**权威**；本脚本用来"随时发现漂移"，避免两次跑出不同结论。

用法：
  python check_script_sync.py          # 只检查（有漂移 → 退出码 1）
  python check_script_sync.py --fix    # 用权威版覆盖插件副本（覆盖前备份到 `DSH_SCRIPT_SYNC_BACKUP`（默认 <工作区根>\\backup\\_script-sync））
  python check_script_sync.py --quiet  # 只输出一行结论（供批界脚本调用）
"""
import io, os, sys, shutil, hashlib
import os
import sys

# --- UTF-8 输出保护（甲-A5 严格版 · 2026-09-13 加入；坑 P-16）---
# 本块由 utf8_guard_patch.py 幂等插入，勿手删：GBK 控制台下打印 ✔ 会抛
# UnicodeEncodeError → 退出码非 0 的**假报警**（前面所有闸其实都过了）。
if os.environ.get('PYTHONIOENCODING', '').lower() != 'utf-8':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
# --- UTF-8 输出保护 结束 ---

HERE = os.path.dirname(os.path.abspath(__file__))                 # 本脚本（权威层 tools\）
# ⚠ 路径修正（2026-09-19 全面体检抓到 · A-127／A-74 家族）：原写 `WS = dirname(dirname(HERE))`
#   ⇒ 落到**工作区父目录**（`…\workspaces`），于是插件副本被找成 `…\workspaces\distillation-director-plugin\scripts`
#   —— **那儿根本没有这个目录**；同时权威件被找成"本脚本所在目录"，而这 4 件**实际住在配套脚本目录**
#   ⇒ 结果恒为 `缺失 4 个`（rc=1 **假红**，且看起来像"包缺件"⇒ 会诱导去"补件"）。
#   现改为：**根目录来自唯一来源 `_paths.ROOT`**；权威件按**解析链**找（配套脚本目录 → tools\）；
#   **两边都不存在 ⇒ 判"不适用"**（另一条工作线/未装配），**不假红**。
import sys as _s, os as _o
_s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
from _paths import ROOT as _ROOT  # noqa: E402
ROOT = _ROOT
_SCRIPTS = os.environ.get('DSH_SCRIPTS_DIR') or ''
_MACH = ''
try:
    from gate_common import cfg as _cfg
    _SCRIPTS = _SCRIPTS or (_cfg.scripts_dir or '')
    _MACH = _cfg.mach or ''
except Exception:
    pass
# 权威件按解析链找：**机器层脚本目录（cfg.mach）→ 配套脚本目录 → tools\**。
#   ⚠ 实测（2026-09-19）：这 4 件的权威副本住在 `投资蒸馏\三闸机器化\`（＝`cfg.mach`）；
#   本脚本从那儿搬到 `tools\` 之后，`HERE` 变成了 tools ⇒ **"权威目录"跟着搬错了**，恒报"缺失"。
AUTH_DIRS = [d for d in (_MACH, _SCRIPTS, HERE) if d]
PLUGIN = os.path.join(ROOT, 'distillation-director-plugin', 'scripts')
# 备份目录：**不得写死作者机器路径**（发版闸 A 判据）。
# 解析链：环境变量 DSH_SCRIPT_SYNC_BACKUP → <工作区根>\backup\_script-sync（本脚本上级目录）。
BACKUP = (os.environ.get('DSH_SCRIPT_SYNC_BACKUP') or
          os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'backup', '_script-sync'))
PAIRS = ['machine_precheck_v2.py', 'machine_layer_readycheck.py',
         'blindtest_lexicon_mock_v1.py', 'defense3_impersonation_scan.py',
         # ── 2026-09-21 追加（用户要求"装在第三方电脑上所有功能都要能用"）──
         #   这 29 件原只住在作者工作区 `tools\`：其中 9 件是 **SKILL.md 已让用户跑、包内却没有**
         #   （`check_doc_tool_refs.py` 实测抓到）；另 20 件是这两日新建的通用能力件
         #   （表体补抽流水线／页级覆盖／成本预估／答案纪律闸／问答台账／副本新鲜度闸／取数 OCR／凭据解析）。
         #   入包位置＝`scripts/gates/`（工作区工具目录仍是**权威**，插件内是**副本** ⇒ 必须逐字节一致，
         #   否则"测过的版本"与"装上的版本"不是同一份）。配套闸：`check_doc_tool_refs.py`。
         'cost_attrib.py', 'coverage_by_chapter.py', 'fix_anchors_generic.py',
         'make_edu_root_stamp.py', 'polish_scan.py', 'rquote_page_check.py',
         'slice_verified_by_skill.py', 'split_long_lines.py', 'table_to_blocks.py',
         'check_table_inventory.py', 'coverage_by_page_sample.py', 'estimate_cost.py',
         'check_answer_discipline.py', 'log_qa_ledger.py', 'check_root_pair_freshness.py',
         'extract_table_datapack.py', 'render_pdf_pages.py', 'map_table_images.py',
         'check_table_ocr.py', 'assemble_table_bodies.py', 'ocr_deepseek_vision.py',
         'check_doc_tool_refs.py', 'pdf_to_text.py', 'ocr_pages.py', 'build_ocr_text.py',
         'ocr_quality_check.py', 'fix_quote_pagemarks.py', '_creds.py',
         # ── 2026-09-21 追加（异机装完即用批的正件 ＋ 表格三形态批：形态普查／矢量表直取）──
         'simulate_third_party_install.py', 'probe_book_form.py', 'extract_vector_tables.py',
         # ── 2026-09-21 第2条收敛批追加（`A-101` 家族：SKILL.md 让用户"先跑"它就必须随包）──
         #   依据：`crisis-transmission-mapper\SKILL.md` 的「可机核等式」第 1／5 条明写
         #         `python tools\scan_pool_counterexamples.py …` 与 `… --check <答案.md>`；
         #         异机装完没有这个文件 ⇒ 用户**拿不到核验等式的手段**（发行层缺口）。
         #   本批给它新增的能力：`--check`（等式机核，rc≠0 即把差异集逐条列出）
         #   ＋ `--write-template`（生成处置清单模板，行集合＝命中集合 T）。
         'scan_pool_counterexamples.py',
         # ── 2026-09-21 §27 批追加（7 条验收标准的机核闸）──
         'distill_acceptance_check.py',
         # ── 2026-09-21 仪器充分性闸（`A-157`／`A-158`：回答"判据修够了没有"）──
         #   依据用户提问「这个循环到底怎么回事？有没有一次彻底解决完？」：
         #   经实测，一天内 14 处缺陷**全部**出在我方判据/代码/流程/读数工具，
         #   故必须有一件"判据自己够不够"的闸，把"继续修还是停"从手感变成可判定。
         'instrument_sufficiency.py',
         # ── 2026-09-21 三基线运行时闸（用户问「有什么办法**一定**可以做到那三条」）──
         #   把「点回原文／标注推测／先追问缺信息」从"模型自觉"改成
         #   **产物三槽形态（[原文]／[外推]／[缺信息]）＋ 机器逐条判**：
         #   引文回源未命中 ⇒ 红；【外推】未写前提 ⇒ 红；缺信息型问句无判停与字段清单 ⇒ 红。
         #   首战即抓到真实事故：盲测答卷里有 2 条"原句"在原文册中逐字**不存在**。
         'assertion_gate.py',
         # ── 2026-09-21 语料绑定闸（"把甲册当乙书"这类语料错配事故的直接教训）──
         #   派单**前**跑：路径存在／主题命中／锚形态同代／下游清单可读。
         #   实测判别力：同一技能 + 错册（主题命中 2/12）⇒ 红；+ 对册（12/12）⇒ 绿。
         'corpus_binding_check.py',
         # ── 2026-09-21 孤儿闸检查（找出"造了却没挂进任何入口"的闸）──
         #   发现经过：用户问「这三条现在是一定做了还是触发时必须做？」——
         #   实测三件运行时闸**通过自证、也进了包**，但 preflight/postflight **一处都没引用**
         #   ⇒ "触发时必须做"在执行层无法保证。本件把该缺口变成可报出的数（44 件门禁里 20 件是孤儿）。
         'orphan_gate_check.py',
         # ── 2026-09-21 触发判定卡（回答「什么时候做／什么时候不做，谁说了算」）──
         #   把"要不要做那三条"从**我的自由裁量**变成：机器起草疑似触发 → 人逐条确认并**附问句原句片段**
         #   → 机器回查片段是否真在问句里（编的证据必被拦）→ 答案须与卡一致。
         'trigger_card.py']


def plug_path(name):
    """插件内副本位置：`scripts\\<名>` 或 `scripts\\gates\\<名>`（两种布局都认，不猜）。"""
    for cand in (os.path.join(PLUGIN, name), os.path.join(PLUGIN, 'gates', name)):
        if os.path.exists(cand):
            return cand
    return os.path.join(PLUGIN, name)

md5 = lambda p: hashlib.md5(io.open(p, 'rb').read()).hexdigest()
only = lambda p: hashlib.md5(io.open(p, 'rb').read()).hexdigest()[:12]

fix = '--fix' in sys.argv
quiet = '--quiet' in sys.argv
drift, missing, same, na = [], [], 0, []

for name in PAIRS:
    a = next((os.path.join(d, name) for d in AUTH_DIRS if os.path.exists(os.path.join(d, name))), None)
    b = plug_path(name)
    if a is None and not os.path.exists(b):
        # 两边都没有 ⇒ **不适用**（例：本工作区未装该插件，或该册未产出这 4 件），不是"缺件"
        na.append(name)
        continue
    if a is None or not os.path.exists(b):
        missing.append((name, bool(a), os.path.exists(b)))
        continue
    if md5(a) == md5(b):
        same += 1
        if not quiet:
            print('  ✔ %-34s 一致（md5 %s）' % (name, only(a)))
        continue
    drift.append((name, only(a), only(b)))
    if fix:
        os.makedirs(BACKUP, exist_ok=True)
        shutil.copy2(b, os.path.join(BACKUP, name + '.pre-sync.bak'))
        shutil.copy2(a, b)
        if not quiet:
            print('  ⚙ %-34s 已同步 %s → %s（旧副本备份）' % (name, only(b), only(a)))

if quiet:
    print('script_sync: 一致 %d / 漂移 %d / 缺失 %d / 不适用 %d%s'
          % (same, len(drift), len(missing), len(na), '（已 --fix）' if fix and drift else ''))
else:
    for name, ha, hb in drift:
        print('  ⚠ %-34s **漂移**：权威 %s ｜ 插件副本 %s' % (name, ha, hb))
    for name, ea, eb in missing:
        print('  ⚠ %-34s 缺失：权威存在=%s ｜ 插件存在=%s' % (name, ea, eb))
    if na:
        print('  ⏭ 不适用 %d 个（两边都不存在，非缺件）：%s' % (len(na), '、'.join(na)))
    print('\n结论：一致 %d 个，漂移 %d 个，缺失 %d 个，不适用 %d 个%s'
          % (same, len(drift), len(missing), len(na), '（已用 --fix 同步）' if fix and drift else ''))
    if drift and not fix:
        print('建议：python check_script_sync.py --fix （权威版＝配套脚本目录／tools\\；改完请登记）')

sys.exit(1 if (drift or missing) and not fix else 0)
