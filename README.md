# distillation-director · 蒸馏主管（V4.9.26 · 三闸判态 ＋ §21 强制门禁 ＋ 装机态三层律 ＋ 异机装完即用）

> 把一本书**蒸馏成可执行的 Agent 技能**：源文取数 → 候选池 → 技能件 → 逐字回源核验 → 发行。
> 本插件是**蒸馏方法论文档**：只含流程、规则、判态标准与机器层脚本，**不含任何一本书的原文或引文**。

## 1. 它解决什么

| 问题 | 本插件的答案 |
|---|---|
| 引文是不是真的、落没落在那页 | **逐字回源核验**：①层页锚 / ②层配对 / ③层技能件自证，全本地脚本、零 API 成本 |
| 选材有没有漏（池缺条目） | **G-66 池覆盖闸**：探针→池 ＋ 精选→R 层双查 ＋ 锚白名单判据 ＋ 见证制 |
| 锚与引文是否自洽 | **G-67 锚一致性闸**（日期×引文同行共现等） |
| 交付件引的 id 有没有全文可回源 | **G-68 证据闭包闸**（id→池内全文 sha256 包；闭包/漂移双检） |
| 装了但没生效 | **装机态三层读数闸**（落盘／登记／在役，逐层给读数与修法） |
| 对外数字与实物不同代 | **A-135 对外声明≡实物闸**（件数／版本／承诺随带件逐项比对） |

## 2. 安装（三条现状路径）

```powershell
# 路径 B（推荐）：固定链接，别名资产永远指向最新版
dsh plugin add https://github.com/winsonpong98-cloud/dsh-distillation-director/releases/latest/download/dsh-distillation-director.tgz

# 路径 B′：要固定字节时用带版号的链接
dsh plugin add https://github.com/winsonpong98-cloud/dsh-distillation-director/releases/download/v4.9.26/dsh-distillation-director-4.9.26.tgz

# 路径 D（最稳，离线/内网）：从 Release 页下载 tgz 后本地装
dsh plugin add <你下载到的 dsh-distillation-director-4.9.26.tgz 路径>
```

- **npm 通道现状**：registry 上的 latest 落后于本版，**请用上面 B／B′／D**；npm 同步后此处会改为一行直装。
- 装完**务必读三层读数**（落盘／登记／在役）——实测最凶的失败模式是"装上了但 `dsh.profile.bundles` 里没有它"，不报错、技能永不注册：
  ```powershell
  python scripts/gates/check_install_state.py            # 三层读数
  python scripts/gates/check_install_state.py --self-test # 闸自证：坏样本必须被拦
  ```

## 3. 运行依赖矩阵（2026-09-25 异机安装验证实测）

| 依赖 | 要求 | 缺失时的行为 |
|---|---|---|
| Python | **≥ 3.10**（3.10 与 3.12 双版本实测：87 件门禁零裸栈零超时） | 版本过低属语法错误范围，请在 3.10+ 运行 |
| PyMuPDF（`import fitz`） | 可选（仅 PDF 文本/版面提取类工具需要） | **指引式失败**：打印 `pip install pymupdf` 并以 **rc=2** 退出（不是裸栈） |
| Node.js | 可选（包内 `.mjs/.cjs` 辅助件） | 需要时自行安装；语法核 4/4 通过 |
| DSH 引擎 | ≥ 0.1.2-rc.1 | 无 DSH 数据时门禁**优雅降级**（异机仿真 0 裸栈、服从 env 根） |

## 4. 快速开始

1. 开一个新会话，说触发词（任一）：`拆书《XXX》` / `蒸馏这本书` / `把 XX 书做成 skill` / `按手册蒸这本书`。
2. **蒸馏任务的第一条命令必须是开工自证闸**（§21 强制门禁；未过不得调子代理、不得 OCR、不得写产物）：
   ```powershell
   python tools\gate_start.py --task <你的任务 slug>
   ```
3. 装好插件后先在工作区根跑一次初始化（把门禁与配套脚本装到 `<工作区>\tools\`）：
   ```powershell
   python "<插件目录>\scripts\gates\init_workspace.py" "<你的工作区根>"
   ```

## 5. 战绩清单（口径写死，可复算）

> 口径：**册**＝`.work/<task>/skills/<slug>/SKILL.md` 存在记 1 册，排除 `*-audit-tmp` 审计目录；**产出技能**＝同口径下 slug 去重；**在役技能**＝各宿主 `.dsh/skills/<slug>/SKILL.md` 实测。数字随你的产出变化，不必与本表相同。

| 维度 | 数据（2026-09-25 本机实测） |
|---|---|
| 本机蒸馏册数 | **14 册**（另有 1 个审计临时目录已按口径排除） |
| 产出技能 | **37 个**（slug 去重） |
| 在役技能 | **80 个**（跨宿主 slug 去重；各宿主读数：金融投资 54／债券与衍生品 5／家庭教育 23） |
| 三闸判态 | **全绿**：G-66 池覆盖 / G-67 锚一致性 / G-68 证据闭包 —— 三条命令 + postflight 全 rc=0（见 §6） |
| 机器层成本 | **¥0**（引文核验、锚一致性、闭包、白名单、见证、装机态全部本地脚本，不花 API） |
| 单本成本 | 本版**未重测**；历史口径（2026-09-19、账户余额差法）：蒸馏主体 + 后改 ≈ ¥17.52/册 —— 如需最新请重跑 `estimate_cost` / `cost_attrib` |
| 异机可用性 | 干净安装验证：解包到临时目录 + 假 HOME + 清空 `DSH_*` + **双 Python** → 87 件门禁 **CRASH 0／TIMEOUT 0**；无工作区场景指引式失败 |

**门禁真的会抓东西吗？**（不是"我声称它有用"，而是它抓过）

| 抓到 | 症状 | 结局 |
|---|---|---|
| 门禁在缺依赖时裸崩 | 别人机器没装 PyMuPDF ⇒ Traceback 直出，像"插件坏了" | 改为**指引式失败**（打印 pip 安装命令 + rc=2） |
| 仪器静默缩射程 | 缺 `source_book` 的技能被当"不是本书"，射程 31→1 却只打印一行、不改 rc（读数系统性偏绿） | 改为**列名并置 rc 0→1** |
| 判据挂错位置 | 白名单判据挂在"全部探针"上 ⇒ 一次误红 56 处（连池内校准题都被判不合格） | 归位到"机选入池条目"，并加**坏样本自证** |
| 同名不同内容 | 两份 `4.9.22` 而 sha 不同 ⇒ "最新版是不是修正版"无法回答 | 规则＝**内容变更必升版**，旧份归档 |
| 台账"已登记"是假的 | 追加按 `| G-66 ` 匹配而行格式为 `| **G-66** |` ⇒ 静默未落，脚本照打 ✔ | 改为**写后读回核验**（打印与实际写入解耦） |

## 6. 门禁体系（随包 **门禁与工具 93 件**）

```powershell
# 三闸（本版实测全绿）
python scripts/gates/check_pool_coverage.py --selftest
python scripts/gates/check_anchor_consistency.py --selftest
python scripts/gates/check_evidence_closure.py --selftest
# 改后门禁（46 项）：打包新鲜度／对外数字／文档↔随包／装机态三层……
python scripts/gates/postflight.py
# 发版审核（A/B/C/D/D-配套/D-import/E/F）＋异机安装仿真
python scripts/gates/verify_plugin_pack.py --pkg-dir <插件目录>
python scripts/gates/simulate_third_party_install.py
```

分层：**§21 强制门禁**（`gate_start` 开工自证／`gate_stage` 阶段依赖链／`gate_checklist` 执行单逐项闸，未过跑不动）→ **发行审核**（可移植性／import 闭包／无裸栈）→ **质量闸**（引文／锚／闭包／池覆盖／装机态／对外数字）→ **自证**（每闸 `--selftest` 用坏样本证明"该红会红"，无坏样本的闸不算闸）。

## 7. 目录结构

```
SKILL.md          技能正文（**V4.9.26 权威**；§0–§16 基干 ＋ §17–§27 增补）
index.js          插件壳（注册技能）
cordis.patch.yml  挂载配置（dsh.bundle.patch ⇒ 走 bundles 组装）
extractors/       提取器提示词模板（含随带**通用要点版**《防坑要点-TOP20》）
scripts/          机器层脚本 4 件（本地运行、零 API 成本）
scripts/gates/    **门禁与工具 93 件**：§21 三道强制门禁、gate_common／preflight／postflight／
                  gate_selftest／pitfall_audit、check_*（判据单源、装机三层、可移植性、
                  台账结构、文档↔随包、对外数字）、三闸（池覆盖／锚一致性／证据闭包）、
                  一致性仪器（_bandid／_plugdir／_creds／_qnorm 四个单源模块）、
                  取数与 OCR、表体补抽、成本账本、质量与覆盖、两道发版审核，
                  以及 **_pack-manifest.txt**（随包成员清单，供安装侧做缺件／陈旧件／内容不符双向比对）
```

## 8. 发行纪律

1. 改内容**必须升版**（同号不得对应两份不同内容）；旧份移入 `_old-releases/`。
2. 发行前必须过：**发版审核**（含异机仿真：解包→初始化→件数对账→逐件冒烟→缺密钥给指引）＋ **随包清单双向比对**（缺件／陈旧件／内容不符）＋ **对外声明≡实物**（件数／版本）。
3. `dsh plugin add` 走 bundles 登记；装完读**三层读数**，只看到"目录在"不算生效。
4. 覆盖安装只增不删 ⇒ 升级后用 `verify_pack_manifest.py --pkg-dir <插件目录>` 查**陈旧件**，陈旧件先移入归档再复核。

## 9. 版本

| 版本 | 日期 | 关键内容 |
|---|---|---|
| v4.9.26 | 2026-09-25 | **本版**：README 重写（删过期的多版本历史与旧通道细节，战绩清单改为可复算口径）；仪器与判据同代：门禁件数／版本／承诺随带件与实物逐项一致 |
| v4.9.25 | 2026-09-25 | 站点内容刷新（清陈旧版本串、删过期历史节、内部执行单移出仓库）；件数声明与实物同代 |

更早版本请见 [Releases](https://github.com/winsonpong98-cloud/dsh-distillation-director/releases)（本仓库不再维护长篇逐版历史）。

## 10. 版权边界与许可证

- 本插件**不含任何书籍原文或逐字引文**；蒸馏产物里的引文版权归原书作者，请自行遵守版权法规。
- 许可证：**AGPL-3.0-or-later**（完整文本见 `LICENSE`）。
