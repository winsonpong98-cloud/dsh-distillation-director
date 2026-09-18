// w1b_validate.mjs —— W1-b 正式版校验（全有全无；rc=0 才算过）
// ① rules-v1.yaml 用 js-yaml 实解析（A-15 权威）＋计数断言；
// ② 69 条规则（装机前 66） quote 逐一与源根 desc（js-yaml 解析值）做**子串断言**；
// ③ 精确目标的 to 必须是真实 slug；
// ④ 草案 SKILL.md：frontmatter 可解析、desc 单行、≤1024、无占位符、无裸 ASCII 双引号、反引号目标全部为真实 slug。
import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const [, , SRC, JSDIR, RULES, DRAFT] = process.argv;
if (!SRC || !JSDIR || !RULES || !DRAFT) { console.error('用法：node w1b_validate.mjs <skillsRoot> <jsYamlDir> <rules-v1.yaml> <draftSKILL.md>'); process.exit(2); }
const entry = existsSync(join(JSDIR, 'node_modules', 'js-yaml', 'index.js'))
  ? join(JSDIR, 'node_modules', 'js-yaml', 'index.js') : join(JSDIR, 'index.js');
const require = createRequire(join(entry, 'index.js'));
const jsYaml = require(entry);

let fails = 0;
const fail = (m) => { console.error('✗ ' + m); fails++; };

// ① rules yaml
const y = jsYaml.load(readFileSync(RULES, 'utf8'));
if (!y || y.schema !== 'edu-route-rules-v1') fail('schema 不符');
const c = y.counts || {};
for (const [k, v] of Object.entries({ arrow_instances: 69, trigger_lines: 24, fallbacks: 22, wildcard_instances: 3, conflicts: 7 })) {
  if (c[k] !== v) fail(`counts.${k}=${c[k]} 期望 ${v}`);
}
if ((y.rules || []).length !== 69) fail(`rules 行数 ${(y.rules || []).length} ≠ 69`);  // 2026-09-13 装机后 66→69（R8 底账同代）

// ②③ 子串与目标断言
const FRONT = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/;
const descs = {};
for (const s of y.slugs || []) {
  const t = readFileSync(join(SRC, s, 'SKILL.md'), 'utf8');
  const m = t.match(FRONT);
  const doc = jsYaml.load(m[1]);
  descs[s] = String(doc.description);
}
const slugSet = new Set(y.slugs || []);
let subOk = 0, wild = 0;
for (const r of y.rules || []) {
  if (r.wildcard) { wild++; }
  else if (!slugSet.has(r.to)) fail(`${r.id}: to=${r.to} 不是真实 slug`);
  const d = descs[r.from];
  if (typeof d !== 'string' || !d.includes(r.quote)) fail(`${r.id}: quote 不是 ${r.from} desc 的逐字子串`);
  else subOk++;
}
console.log(`① yaml 解析 ✔ ｜ 计数 ✔ ｜ quote 子串断言 ${subOk}/69 ✔ ｜ 通配 ${wild}/3 ✔ ｜ 精确目标全部存在 ✔`);
if (subOk !== 69 || wild !== 3) fails++;

// ④ 草案
const dt = readFileSync(DRAFT, 'utf8');
const dm = dt.match(FRONT);
if (!dm) fail('草案 frontmatter 不匹配');
else {
  const doc = jsYaml.load(dm[1]);
  const d = String(doc.description || '');
  if (/[\n\r]/.test(d)) fail('草案 desc 含换行');
  if (d.length > 1024) fail(`草案 desc ${d.length} > 1024`);
  if (d.includes('"')) fail('草案 desc 含裸 ASCII 双引号');
  if (/<[^>]{1,12}>/.test(d)) fail('草案 desc 含尖括号占位符');
  const targets = [...d.matchAll(/`([^`]+)`/g)].map(m => m[1]);
  const bad = targets.filter(t => !slugSet.has(t));
  if (bad.length) fail('草案 desc 反引号目标不是真实 slug：' + bad.join('、'));
  console.log(`④ 草案 ✔（desc ${d.length} 字／余 ${1024 - d.length}；目标 ${targets.length} 个全部真实 slug；单行；无占位符）`);
}
if (fails) { console.error(`结论：✗ ${fails} 项失败`); process.exit(1); }
console.log('结论：✔ W1-b 正式版校验全绿（yaml 解析／计数／69 子串／目标存在性／草案 desc 纪律）');
