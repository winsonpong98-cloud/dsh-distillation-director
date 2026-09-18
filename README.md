# distillation-director · 蒸馏主管（V4.9.7 · 发行自足 ＋ 三闸判态 ＋ §21 强制门禁 ＋ 装机态三层律 ＋ 判据单一来源 ＋ 防坑体系）

把一本书蒸馏成一组可执行的 Agent 技能——**判态制元技能**（权威执行标准）。

不是通用蒸馏框架，而是**专注书籍蒸馏的专科方案**：三闸判态制（防线3 忠实度 / 盲测路由 / 达尔文体检），只判态不打分，门禁 = 零🔴；**外加一套可运行的工程防坑体系**（避坑手册 ＋ 四件门禁 ＋ 发行纪律）。

---

## 30 秒上手

**① 安装**（四条路径任选其一）

> ⚠️ **v4.9.3 起请勿用 npm 那条（路径 A）**：npm registry 上目前仍是 **4.6.6**，而 4.6.6 **不含 §21 三道闸
> （`gate_start.py`／`gate_stage.py`／`gate_checklist.py`）与 4 个配套脚本**，装了跑不动。
> **v4.9.7** 请用 **B / C / D** 任一条；npm 待发版后本提示会撤掉。

```bash
# A. npm 一行直装（⚠️ 目前仍是 4.6.6，缺 §21 闸；4.9.x 未上架 npm 前请勿使用）
dsh plugin add dsh-distillation-director

# B. 固定链接直装（**推荐**；不需要 npm；别名资产永远指向最新版）
dsh plugin add https://github.com/winsonpong98-cloud/dsh-distillation-director/releases/latest/download/dsh-distillation-director.tgz

# B'. 指定版本直装（要固定字节时用这条）
dsh plugin add https://github.com/winsonpong98-cloud/dsh-distillation-director/releases/download/v4.9.7/dsh-distillation-director-4.9.7.tgz

# C. 从仓库直装（需要能访问 GitHub；仓库已锁定行尾字节保真；可指定 tag）
dsh plugin --profile web add github:winsonpong98-cloud/dsh-distillation-director#v4.9.7

# D. 从 Release 页面下载 tgz 后本地装（字节与作者双门校验过的发行件完全一致）
dsh plugin add <你下载到的 dsh-distillation-director-4.9.7.tgz 路径>
```

> 四条路径的关系：**B** 走 GitHub Release 的**别名资产**（`…/releases/latest/download/dsh-distillation-director.tgz`，链接永不随版本变化，本版已同时上传该别名件）；**B′** 是带版本号的固定链接；**C** 走 git 仓库（`.gitattributes` 锁定行尾字节，保证"直装字节＝发行字节"）；**D** 是最稳的离线路径；**A** 待 npm 发版后恢复为最短路径。

**② 开一个新会话，说触发词**（任一）

- 「拆书《XXX》」
- 「蒸馏这本书」
- 「把 XX 书做成 skill」
- 「按手册蒸这本书」

**③ 蒸馏任务的第一条命令必须是开工自证闸**（§21 强制门禁，未过不得调用任何子代理／不得 OCR／不得写产物）

```bash
python tools\gate_start.py --task <你的任务 slug>
```

---

## 战绩清单（实测背书）

| 维度 | 数据 |
|---|---|
| 已蒸馏书籍 | **19 本**（投资 13 本 + 教育/心理 5 本 + 技术标准 1 本） |
| 产出技能 | **约 70 个**（金融投资 43 个 + 教育/心理 22 个 + 技术 4 个） |
| 质量 | 零🔴、A 档交付（三闸判态制门禁） |
| 单本成本 | **¥20.5 实测**（L2.5 epub 文字版 ≈14 万字，35 次 flash 子代理 + 机器层 ¥0） |
| 机器层 | 零成本先行（引文逐字核验 / 盲测词表 / 防线3 冒充扫描 / 9 维预检，全部本地脚本） |

<details>
<summary><b>实测口径说明（点开）</b></summary>

- **投资方法论类 13 本**、**教育／心理类 5 本**、**技术标准 1 本**（按**类别**统计）。
- **本插件与本文档不列举具体书名**——插件是「蒸馏方法论文档」，只含流程、规则、判态标准与机器层脚本；
  具体书目属**使用者自己的蒸馏台账**，不进插件载荷（《避坑手册》A-74：通用件里不得有任何一本书的数据）。
- 上表所有数字（本数／技能数／成本／质量）均为**本机实测**，可复核口径见 `SKILL.md` 内置成本基准与
  `.work/<task>/` 下的实测产物；**它们描述的是"方法在这类书上跑过"，不含任何书的内容**。

</details>

**差异化 vs 通用蒸馏框架（如 cangjie）：**

| 维度 | 通用框架 | 本插件 |
|---|---|---|
| 定位 | 书/视频/播客/课程全科 | **专注书籍蒸馏专科** |
| 验证 | 通用模板 | **三闸判态 + 逐字核验** |
| 机器层 | 无 | **有（脚本 ¥0）** |
| 公开战绩/成本 | 无 | **19 本 → 约 70 个技能零🔴、¥20.5/本实测** |

---

## 安装细节

底层 = pnpm 安装 npm 包 + `cordis.patch.yml` 的 insert 条目挂载，DSH 启动时扫描 bundle 自动 apply。

- **路径 A（npm 包名）**：`dsh plugin add dsh-distillation-director`。底层同样走 pnpm，但从 **npm registry** 取包（本包已上架，`latest` 即最新版）。
- **路径 B（GitHub Release 固定链接）**：别名资产链接**永远指向最新版**，**不需要 npm 也能装**——这是"npm 通道不可用"时的备用通道。
- **路径 C（仓库直装）**：仓库已加 `.gitattributes`（`* -text`）**禁用 git 行尾转换**，因此克隆／直装得到的字节与发行 tgz 一致（这是被实测修过的坑，见下「发行纪律」）。
- **路径 D（本地 tgz）**：适合离线／内网／要固定字节的场景。Release 页资产即**作者本机双门校验通过的那一份**。
- 所有路径最终都产生同一条挂载配置：

```yaml
- insert:
    - id: distillation-director
      name: dsh-distillation-director
```

**验证装上了**（**2026-09-18 重写：一条命令不够，要读三层读数**）：

> **为什么重写**：2026-09-18 在一台 NAS 的 DSH 容器里实测到**"装了但不生效"**——
> `node_modules\dsh-distillation-director` 目录在、`dsh plugin list` 也列得出它，
> **但开会话时技能目录里根本没有 `distillation-director`**，而且**不报任何错**。
> 逐层读数定位：`dependencies` 里有它、**`dsh.profile.bundles` 里没有它**
> ⇒ 引擎按 `bundles` 组装 → 没组装就不会加载 → 没加载就不会 `apply()` → 技能从未注册。
> **决定性读数**：`--dump-config` 组装树 566 行里 `distillation` 命中 **0**；补进 bundles ＋ 重启后 569 行、命中 **3**。

**一条命令给三层读数**（推荐；`--self-test` 先用坏样本自证闸有效）：

```bash
python scripts/gates/check_install_state.py
python scripts/gates/check_install_state.py --self-test     # 闸自证：4 类坏样本必须被拦
python scripts/gates/check_install_state.py --json out.json  # 机器可读
```

**手工读三层读数**（没有 python 时照这个顺序查，**不要跳层**）：

```text
① 落盘层（文件在不在、声明齐不齐）
   · plugins/<pkg>/package.json 可解析、version 正确、**声明了 dsh.bundle.patch**
   · SKILL.md 在场（frontmatter 有 name/description）· index.js 能真导入且导出 apply

② 登记层（**今天断的就是这一层**）
   · <profile>/package.json 的 dependencies **且** dsh.profile.bundles 都要有 dsh-distillation-director
   · 装配实测（**看行数与命中数，别只看有没有报错**——这一层不会报错，只会静默少一行）：
     dsh web --dump-config | findstr /C:"distillation-director"        # Windows
     node <dsh>/lib/bin.js --profile web --dump-config | grep -n distillation   # Linux/容器

③ 在役层（写进去了 ≠ 跑起来了）
   · 服务可达（HTTP 状态）· 启动日志**带时间戳**确认是本次启动的记录
   · 开一个新会话，看技能目录里是否出现 distillation-director（或按 SKILL.md §17.2 用引擎加载器实测）
```

**若 ② 缺失（最常见的失败）**，按顺序修：

```bash
cp <profile>/package.json <profile>/package.json.bak-$(date +%Y%m%d)
dsh plugin --profile <profile> add <包名或插件目录或 tgz>   # 官方命令会按安装态 reconcile，自动写入 bundles
# 复核 bundles 出现了该包名 → **重启服务**（配置在启动期组装，热改不生效）→ 回到 ② 看组装树
```

> **两条硬纪律**（《避坑手册》`A-119`／`A-120`／`A-123`）：
> ① **`dependencies` 有 ≠ 已生效**——只有进了 `dsh.profile.bundles` 才会被组装、加载、注册；
> `node_modules` 有目录、`plugin list` 列得出，**都不构成"已生效"的证据**。
> ② **本插件确实声明了 `dsh.bundle.patch`**，所以用官方命令 `dsh plugin add` 安装时**应当自动进 bundles**；
> 若没进，只有三种可能：(a) 不是用官方命令装的（手改 `package.json`／直接 `pnpm add`）；
> (b) 那次命令没成功（pnpm 非零退出时引擎不做 reconcile）；(c) 装的是不声明 `dsh.bundle` 的旧版本。

---

## 目录结构

```
SKILL.md          技能正文（**V4.9.7 权威**；§0–§16 基干 ＋ §17–§25 历次增补）
index.js          插件壳（注册技能）
scripts/          机器层脚本（4 件）＋ **WORK 配套脚本（4 件）**：yaml_check_generic.cjs ／ skill_probe_generic.mjs ／ w1b_extract.mjs ／ w1b_validate.mjs
scripts/gates/    **门禁套件 27 件**：gate_start ／ gate_stage ／ gate_checklist（§21 三道强制门禁）＋ gate_common ／ gate_bootstrap ／ init_workspace ／ preflight ／ postflight ／ gate_selftest ／ pitfall_audit ／ check_* 等；并随带《蒸馏工程避坑手册》与《V3.1全量执行单》
cordis.patch.yml  挂载配置
extractors/       提取器提示词模板
scripts/          机器层脚本 4 件（machine_precheck_v2 / machine_layer_readycheck /
                  defense3_impersonation_scan / blindtest_lexicon_mock_v1；全部本地运行、零 API 成本）
manual-history/   历史版本手册存档（4 件，文件名即如此：manual-v2.0 / manual-v3.0 / manual-V4.0 / manual-V4.1）
```

---

## 版本

| 版本 | 日期 | 关键内容 |
|---|---|---|
| v4.1 | 2026-09-12 | 红线词分级 + LLM 终裁 / desc 让位分离 / 分段落盘 + 超时判据 / 成本基准 ¥20.5 |
| v4.2.0 | 2026-09-13 | §17 工程纪律与装机/上架 9 条；补 manual-V4.1；同步机器层脚本口径（提交信息里写作"v4.3"，**指脚本口径，非插件版本号**） |
| v4.2.1 | 2026-09-13 | §18 防坑体系与门禁（33 条避坑手册 + preflight／postflight／gate_selftest + 写入型自检禁令） |
| v4.2.2 | 2026-09-13 | 收口轮：避坑手册 37 条 ＋ §九 发行类 ＋ §十 交付与台账纪律；`postflight` 增 ②-b 余量告警与 ④-b 打包新鲜度 |
| v4.4.0 | 2026-09-13 | §19 判官工作流 v2 与副本治理（desc 路由工程铁律六条；四层副本模型） |
| v4.5.0 | 2026-09-13 | §20 底账同代、判官输入工程与闸的升格秩序 |
| v4.6.0–4.6.2 | 2026-09-13 | §21 **强制门禁**：`gate_start` 开工自证闸 ＋ `gate_stage` 阶段依赖链 ＋ `gate_checklist` 执行单逐项闸；`preflight ⑤` 自动纳入活跃蒸馏任务 |
| v4.6.3–4.6.4 | 2026-09-14 | §22 判官要求固化：「引文型附属文件」零问题检查表（R1–R8 断言） |
| v4.6.5 | 2026-09-15 | README 与发行件同步到当前版本；补齐 v4.4.0–v4.6.4 的版本表与安装路径；**发行保真两处修复**（打包器剔除 `__pycache__` 编译产物；新增 `.gitattributes` 锁定行尾字节） |
| v4.6.6 | 2026-09-15 | **上架 npm registry**（`dsh plugin add dsh-distillation-director` 一行直装）；README 安装路径更新为**四条**并标注各自适用场景；新增"GitHub Release 固定链接"作为**不依赖 npm 的备用通道** |
| v4.6.7–4.9.2 | 2026-09-17 | 逐处回改批／继承项纳管批／落地审计批／可移植性专项批：**工具随包发行**（发版闸 A–E、`layer_quotes_gate`／`check_layer_sync`／`check_instrument_coverage`＋配套脚本）、`init_workspace.py` 一键初始化；手册升到 v3.2（A-01…A-105） |
| **v4.9.7** | **2026-09-19** | **本版**：**判据语法单一来源 ＋ 源文件决议单一来源**（NAS 异机真机两轮实测固化）——① 建唯一真源 `scripts/gates/_bandid.py`（波段条目 id 语法 `[A-Za-z][A-Za-z0-9]*-\d{3}`）并**回改 17 处内联**（旧代码 4 种残缺写法 ⇒ **同一份合规产出在不同仪器下时红时绿**：`verify_candidates` 报 `🔴 切块为空`、`gate_stage` 却 ✔）；② 新增闸 **`check_bandid_single_source.py`**（内联即判红，含 10 个正负样本自证）挂 **`postflight ⑬`**（29→**31 项**）；③ `verify_candidates` 抽出**唯一决议函数 `resolve_src()`**（探测与校验共用；兜底**必须过内容闸**＝真含页标记，避免把**任务自己的产出文档**当源）＋ 空集/全数未命中报错改为**自证型**（打印期望语法／实测标题行／实际使用的源＋三步处置）＋ 新增 **▲ 一条目多引文** 可见性；④ `gate_selftest` 由六坏扩为 **九组**（新增 `E1` 成对差分／单源闸自证／**源决议陷阱**）；⑤ `tools/diag_hline_blockmatch.py` 重写为**形态普查器**（5 把尺子 × 6 形态 ＋ `--census` 真实册并排）；⑥ 发行侧修掉三处"改了却没进包"（手写清单 → **闭包推导**＋剪枝、补 **SKILL.md 同步步**、`optional-tools.json` 与事实对齐）；手册 **§25**（R33–R37）＋避坑手册 **v3.8**（`A-132`／`A-133`，155→156 条） |
| v4.9.5–4.9.6 | 2026-09-19 | 换书实测批（**未发布**）：候选校验的**源基准**判据放宽到 `.md`、候选条目标签**容错**（`锚`／`页锚`／`出处`、半角冒号、`逐字原文`）；`gate_selftest` 增执行单例外登记成对样本 |
| **v4.9.4** | **2026-09-18** | **装机态三层律**（NAS 容器真机实测固化）——把"装了但不生效"的判据做成随包仪器 **`scripts/gates/check_install_state.py`**（落盘①／登记②／在役③ 三层逐层读数 ＋ 逐层修法 ＋ `--self-test` 四类坏样本自证）、挂 **`postflight ⑧-g`**（27→29 项）；**§6 打包流程由一行散文改写为「三步带读数」**；新增 **§17.10 装机态三层律**；README「验证装上了」由一条命令扩为**三层读数**（含最常见的失败＝`bundles` 缺项及修法）；避坑手册 **v3.5**（`A-119`…`A-124` 六条） |
| v4.9.3 | 2026-09-18 | **发行自足与跨平台**——`scripts/gates/` **27 件首次随包发行**（含 §21 三道闸 `gate_start.py`／`gate_stage.py`／`gate_checklist.py`）＋ **4 个配套脚本**（`yaml_check_generic.cjs`／`skill_probe_generic.mjs`／`w1b_*.mjs`）；发版闸由 A–E 升为 **A/B/C/D/D-配套/E/F**（新增"配套脚本必须随包"与"跨平台静态判据"）；node/js-yaml 解析链跨平台；`init_workspace` 上溯找包根＋两种布局取件；缺目录不再崩栈；手册 **v3.4**（A-106…A-118 共 13 条） |

> **从哪装最省事（v4.9.7 现状）**：用固定链接那条 `dsh plugin add https://github.com/winsonpong98-cloud/dsh-distillation-director/releases/latest/download/dsh-distillation-director.tgz`（路径 B）。**npm 通道目前仍是 4.6.6（缺 §21 闸），4.9.x 上架 npm 后本段会改回"一行直装"。** 装完**务必按「安装细节 → 验证装上了」读三层读数**（2026-09-18 实测最凶的失败模式就是"装上了但 `bundles` 里没有它"）。

> **版本编号说明（v4.3 未独立发布）**：**`v4.3` 是跳过的编号，未独立发版**。v4.2.0 提交信息里的"v4.3"指**机器层脚本口径**、v4.6.4 提交信息里的"V4.3"指**防坑体系批次**，二者均非插件版本号；「防坑体系 37 条 ＋ 三件门禁」实际随 **v4.2.2** 收口轮交付。故编号自 v4.2.2 直接进入 v4.4.0。

完整手册演进见 `manual-history/` 与技能正文 `SKILL.md` §16–§22。

---

## 发行纪律（本插件自己的纪律，也是可复用的参考）

本插件的每次发行都要过以下闸，且**这些闸自身被坏样本验证过"确实会红"**：

| 闸 | 作用 |
|---|---|
| `preflight` / `postflight` | 开工前／改后各一组门禁（YAML、desc 长度、表格、脚本同步、打包产物新鲜度、机器层零新增 fail、可编译……） |
| `gate_selftest` | 用已知坏样本证明门禁有效（**"不可能失败的门"不算门**） |
| `pitfall_audit --check` | 避坑手册与工具对账 ＋ 只读命令深跑（防手册腐烂） |
| 解包级校验 | 两个 tgz 与权威源逐字节一致 ＋ **包内无多余产物**（双向判据） |
| 端到端可加载 | 对打包产物真 `import` ＋ 模拟注册，确认真能装上（不是"文件都在"） |
| 三层字节一致 | 工作区 / git 索引 / tgz 三层逐字节相同（防 `core.autocrlf` 静默改写） |

**v4.6.5 修掉的两个发行缺陷**（都出自真实事故，已进避坑手册 `§9.5`）：

1. **脏包**：打包器曾把 `scripts/__pycache__/*.pyc` 打进 tgz（4.6.2／4.6.3／4.6.4 内测件受影响）。修法＝打包器目录级＋后缀级双排除，并给校验器补「包内无多余产物」的黑名单 ＋ 逐件反查**双向**判据。
2. **字节保真**：`core.autocrlf=true` 曾把脚本在 git 索引里 LF 化，导致**仓库直装的字节 ≠ 发行 tgz 的字节**。修法＝`.gitattributes`（`* -text`）＋ `git add --renormalize .`。

> 纪律两条：**① 所有"该有的在不在"型判据都拦不住"多带了什么"；② 发布完成后必须从公网回读资产、比对 sha256 三方一致，才算发行完成。**

---

## 版权边界（重要）

**本插件是「蒸馏方法论文档」，只含流程、规则、判态标准、机器层脚本——不含任何书籍原文或逐字引文。**

- 手册中出现的书名（如《周期、估值与人性》《原则》）仅作实测对象的**书名引用**，不构成内容复制。
- 你用本插件蒸馏任何书时，**蒸馏产物（技能 SKILL.md）里的原文引文版权归原书作者**，请自行遵守版权法规；本插件与作者不对你的蒸馏产物承担版权责任。

## 许可证

AGPL-3.0-or-later（因 index.js 结构参考了同许可证的 dsh-cangjie-skill）。完整文本见 `LICENSE` 或 <https://www.gnu.org/licenses/agpl-3.0.html>。

## 运行环境要求（2026-09-17 补 · 来自外部机器实测）

- **Node**：DSH 自带（插件本体只需 DSH 引擎的 Node）。随包的 4 个机器层脚本 +
  4 个配套脚本（`yaml_check_generic.cjs`／`skill_probe_generic.mjs`／`w1b_*.mjs`）在包内 `scripts/` 下。
- **Python 3.10+**：门禁套件（`scripts/gates/*.py`）需要 Python。**若你的环境（如裸 Debian 容器）没有 Python**，
  装一个免 root 的便携版即可（实测可行）：解压到 `/data/tools/python` 并在 PATH 目录建 `python3`／`python` 软链 ⇒
  `python tools/gate_start.py --task <slug>` 可原样执行；不想要时删目录 + 两条软链，零副作用。
- **安装后第一步**：在**你的工作区**跑
  `python "<插件目录>/scripts/gates/init_workspace.py" "<你的工作区根>"`
  —— 它会把整套门禁（含 `gate_start.py`／`gate_stage.py`／`gate_checklist.py`）与配套脚本装到 `<工作区>\tools\`，
  之后手册里的 `python tools\gate_start.py …` 等命令才能按原样执行。
- **读全文再抄录**：`skill` 工具返回的正文可能被裁剪（实测省略 13,491 字节）。
  §21 的哈希核对与"逐字抄录 ≥12 条"**必须先读全文**（插件里的 `SKILL.md`），否则中部条款缺失、逐字对不上。

---

## v4.9.3 修掉的发行缺陷（发行自足，全部来自异机实测）

本节与"v4.6.5 修掉的两个发行缺陷"同性质：**都不是功能问题，而是"在我这台机器上永远测不出来"的发行问题**。

1. **§21 三道闸与整套门禁不随包发行**：`scripts/gates/` 此前 4.1.0–4.9.2 **一律缺失** ⇒ 手册 §21 写的
   `python tools\gate_start.py --task <slug>` 在别人的机器上跑不起来（"未过不许调子代理"只能靠自觉）。
   本版把 **27 件**随包发行，并在包内提供 `init_workspace.py` 一键装到你的工作区。
2. **4 个配套脚本不随包**：`yaml_check_generic.cjs`（YAML 实解析）／`skill_probe_generic.mjs`（引擎加载器实测）／
   `w1b_*.mjs` 原先只住在作者工作目录 ⇒ 新机器的 YAML 闸与引擎探针直接失效。本版入包（`scripts/`）。
3. **发版闸判据只覆盖"最常见的一类依赖"**：原 D 判据只验"引用的 `.py` 在不在包里"，
   对配套脚本／运行时目录／外部库（node／js-yaml）**全无覆盖** ⇒ 判据升级为
   **A/B/C/D/D-配套/E/F**：新增**D-配套**（包内门禁引用的 WORK 文件必须在包内）与
   **F 跨平台静态判据**（Windows 专有 API／硬写 `node.exe` 且无平台兜底）。
4. **同步清单手写必然漏**：包内与权威源实测**漂移 7 个文件**（改了 `tools\` 却从没进包）。
   修法＝同步清单**改为按包内实际发行文件自动生成**，并给数据文件（手册／执行单）单独加同步步。
5. **初始化在发行包布局下算错包根**：原实现按固定跳数求插件根 ⇒ 发行包里算错两级、**一个文件都装不上**。
   修法＝**上溯找包根**＋两种布局取件源；同时补齐 `.dsh\gate-kit` 配置目录。
6. **平台写死与缺目录崩栈**：node 只认 `node.exe`（Linux／NAS 上引擎二进制叫 `node`）；
   `os.listdir`／`cwd=` 在目录不存在时直接抛异常（新用户机器上必现）。两者均已修（解析链＋`_safe_listdir`）。

**本版复验**：`repack` rc=0 ｜ 发版闸 rc=0（六判据全过）｜ `postflight` rc=0（连跑两次）｜
`pitfall_audit --check` rc=0 ｜ `gate_selftest` rc=0 ｜ **异机安装实测 rc=0**（46 文件解到 `<DSH_HOME>/packages/`，
引擎 `node` 加载 `index.js` → 注册技能 `distillation-director`）｜ **异机门禁模拟 11 项致命 0**。
