// yaml_check_generic.cjs —— 用 js-yaml 解析任意技能根下活动技能的 frontmatter
// 用法：node yaml_check_generic.cjs <技能根> [js-yaml 目录] [期望件数]
// 可移植性（2026-09-17）：**不得含作者机器路径**。js-yaml 目录按"解析链"取：
//   ① argv[3]（门禁解析好后传入） ② 环境变量 DSH_JS_YAML_DIR
//   ③ <DSH_HOME>/../engine/node_modules/{.pnpm/js-yaml@*,js-yaml} ④ DSH_ENGINE_NODE 同级 engine
//   ⑤ 本脚本所在 tools 的兄弟 engine/ —— 全不命中 ⇒ **打印可执行指引并退出 2**（不给裸栈）。
const fs = require('fs');
const path = require('path');

const ROOT = process.argv[2];
if (!ROOT) {
  console.log('用法：node yaml_check_generic.cjs <技能根> [js-yaml 目录] [期望件数]');
  process.exit(2);
}
const want = process.argv[4] ? Number(process.argv[4]) : null;
if (!fs.existsSync(ROOT) || !fs.statSync(ROOT).isDirectory()) {
  console.log('🔴 技能根不存在（%s）—— 本检查判"不适用"：新用户机器上没有作者的宿主工作区。', ROOT);
  console.log('   处置：传入你自己的技能根：node yaml_check_generic.cjs <技能根> [js-yaml 目录] [期望件数]');
  process.exit(2);
}

function okJs(p) {
  try {
    if (!p || !fs.statSync(p).isDirectory()) return false;
    if (fs.existsSync(path.join(p, 'package.json'))) return true;                    // 直接是包目录
    return fs.existsSync(path.join(p, 'node_modules', 'js-yaml', 'package.json'));  // pnpm 外层
  } catch (e) { return false; }
}

function findYamlDir() {
  const cands = [process.argv[3] || '', process.env.DSH_JS_YAML_DIR || ''];
  const engines = [];
  if (process.env.DSH_HOME) engines.push(path.join(path.dirname(process.env.DSH_HOME), 'engine'));
  if (process.env.DSH_ENGINE_NODE) engines.push(path.dirname(process.env.DSH_ENGINE_NODE));
  engines.push(path.join(path.dirname(path.dirname(path.resolve(__dirname))), 'engine'));
  for (const e of engines) {
    cands.push(path.join(e, 'node_modules', 'js-yaml'));
    try {
      for (const d of fs.readdirSync(path.join(e, 'node_modules', '.pnpm'))) {
        if (d.startsWith('js-yaml@')) cands.push(path.join(e, 'node_modules', '.pnpm', d));
      }
    } catch (e) { /* 该 engine 下无 .pnpm：跳过 */ }
  }
  for (const c of cands) if (okJs(c)) return c;
  return null;
}

const yamlDir = findYamlDir();
if (!yamlDir) {
  console.log('🔴 找不到 js-yaml（本检查无法执行，**不给裸栈，给指引**）。');
  console.log('   已尝试：argv[3] ／ DSH_JS_YAML_DIR ／ <DSH_HOME>/../engine/… ／ 兄弟 engine/');
  console.log('   处置：设 DSH_JS_YAML_DIR=<...>\\js-yaml@x 后重跑。');
  process.exit(2);
}
let yaml;
try {
  const pkg = fs.existsSync(path.join(yamlDir, 'package.json'))
    ? yamlDir : path.join(yamlDir, 'node_modules', 'js-yaml');
  yaml = require(pkg);
} catch (e) {
  console.log('🔴 js-yaml 载入失败（%s）：%s', yamlDir, e.message.split('\n')[0]);
  process.exit(2);
}

const dirs = fs.readdirSync(ROOT).filter((d) => d !== 'archived' && fs.statSync(path.join(ROOT, d)).isDirectory());
let ok = 0; const bad = [];
const rows = [];
for (const d of dirs) {
  const p = path.join(ROOT, d, 'SKILL.md');
  if (!fs.existsSync(p)) continue;
  const t = fs.readFileSync(p, 'utf8');
  const m = t.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) { bad.push([d, '无 frontmatter']); continue; }
  try {
    const o = yaml.load(m[1]);
    if (!o || typeof o.name !== 'string' || typeof o.description !== 'string' || !o.description.trim()) {
      bad.push([d, 'name/description 缺失或非字符串']);
    } else {
      ok++;
      rows.push([d, o.description.length, o.description.length > 1024 ? '>1024' : '']);
    }
  } catch (e) {
    bad.push([d, 'YAML 解析失败: ' + e.message.split('\n')[0]]);
  }
}
console.log('技能根：' + ROOT);
console.log('js-yaml：' + yamlDir);
console.log('YAML 解析通过：' + ok + ' / ' + (ok + bad.length));
if (bad.length) console.log('异常：', JSON.stringify(bad, null, 1));
else console.log('全部 ' + ok + ' 个活动技能 frontmatter 合法、name/description 均为非空字符串 ✔');
rows.sort((a, b) => b[1] - a[1]);
console.log('最长 5：' + JSON.stringify(rows.slice(0, 5)));
// 余量告警（C-8／待-08）：上限 1024，余量 <100 字即列出（**信息性，不影响退出码**）。
const near = rows.filter((r) => 1024 - r[1] < 100).map((r) => [r[0], r[1], 1024 - r[1]]);
console.log('余量<100 件数：' + near.length + (near.length ? '：' + JSON.stringify(near) : ''));
console.log('>1024 件数：' + rows.filter((r) => r[2]).length);
if (want !== null) console.log(ok === want ? '件数符合期望 ' + want + ' ✔' : '✗ 件数 ' + ok + ' ≠ 期望 ' + want);
