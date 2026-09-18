// skill_probe_generic.mjs —— 通用技能加载器探针（可选技能根，用引擎自己的加载器实测）
// 用法：node skill_probe_generic.mjs <技能根目录> [cwd] [关注 slug1,slug2,...]
// 可移植性（2026-09-17）：**不得含作者机器路径**。
//   引擎库（dsh-skill-filesystem）按解析链取：① 环境变量 DSH_SKILL_FS_LIB
//   ② <DSH_HOME>/../engine/node_modules/.pnpm/node_modules/@deepseek-ai/dsh-skill-filesystem/…
//   ③ DSH_ENGINE_NODE 同级 engine 的同上路径 ④ 本脚本所在 tools 的兄弟 engine 的同上路径
//   全不命中 ⇒ **打印可执行指引并以 2 退出**（不给裸栈）。
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';

const REL = path.join('node_modules', '.pnpm', 'node_modules', '@deepseek-ai',
  'dsh-skill-filesystem', 'lib', 'index.js');

function findLib() {
  const cands = [process.env.DSH_SKILL_FS_LIB || ''];
  const engines = [];
  if (process.env.DSH_HOME) engines.push(path.join(path.dirname(process.env.DSH_HOME), 'engine'));
  if (process.env.DSH_ENGINE_NODE) engines.push(path.dirname(process.env.DSH_ENGINE_NODE));
  engines.push(path.join(path.dirname(path.dirname(path.resolve(process.argv[1] || __filename))), 'engine'));
  for (const e of engines) {
    cands.push(path.join(e, REL));
    // 兼容非 pnpm 的扁平布局与 pnpm 虚拟目录
    cands.push(path.join(e, 'node_modules', '@deepseek-ai', 'dsh-skill-filesystem', 'lib', 'index.js'));
  }
  for (const c of cands) {
    try { if (c && fs.statSync(c).isFile()) return path.resolve(c); } catch (e) { /* 不存在即继续 */ }
  }
  return null;
}

const LIB = findLib();
if (!LIB) {
  console.log('🔴 找不到引擎技能加载器 dsh-skill-filesystem（本探针无法执行，**不给裸栈，给指引**）。');
  console.log('   已尝试：DSH_SKILL_FS_LIB ／ <DSH_HOME>/../engine/… ／ DSH_ENGINE_NODE 同级 ／ 兄弟 engine/');
  console.log('   处置：设 DSH_SKILL_FS_LIB=<...>\\dsh-skill-filesystem\\lib\\index.js 后重跑。');
  process.exit(2);
}
const { FileSystemSkillProvider } = await import(pathToFileURL(LIB).href);

const root = process.argv[2] || process.cwd();
const cwd = process.argv[3] || process.cwd();
const want = (process.argv[4] || '').split(',').map((s) => s.trim()).filter(Boolean);

const ctx = { logger: { warn: () => {}, info: () => {}, debug: () => {}, error: () => {} },
  get: () => undefined, on: () => {}, effect: () => {}, skills: { registerProvider: () => {} } };
const control = { invalidate: () => {}, signal: new AbortController().signal };
const p = new FileSystemSkillProvider(ctx, control, { includeDefaultRoots: false, customSkillDirs: [root] });
const res = await p.list({ cwd });
const cands = Array.isArray(res) ? res : res.candidates;
const names = cands.map((c) => c.name);
console.log('技能根：%s', root);
console.log('引擎发现技能数: %d  (complete=%s)', cands.length, res.complete);
console.log('唯一名: %d / %d', new Set(names).size, names.length);
console.log('解析告警: %d', cands.filter((c) => c.warnings && c.warnings.length).length);
for (const w of want) {
  const c = cands.find((x) => x.name === w);
  console.log('  %s %s  %s', c ? '✔' : '✗', w,
    c ? ('desc=' + (c.description || '').length + ' 字｜正文可取=' + Boolean(c.content)) : '未被引擎发现');
}
console.log('\n全部技能名：\n  ' + names.slice().sort().join('、'));
p.dispose?.();
process.exit(0);
