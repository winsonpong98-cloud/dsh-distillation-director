// w1b_extract.mjs —— W1-b 权威抽取：教育线 desc 路由条款 → rules-v1-extract.json
// 修 W1-a 草稿三个机械盲区：
//   ① desc 取值改 js-yaml 实解析（A-15 权威；不再用逐行正则近似）；
//   ② 箭头按"实例"全量捕获（一句多箭头分别成条 → 解决 61句 vs 63箭头 分段差）；
//   ③ 通配目标（`dev-*`／`makestick-*`）单独成类（正则 [a-z0-9-]+ 漏收的两族）。
// 触发词行三分类：real（"触发词："枚举）／qualification（准入条件，如 adhd 收紧口径）／meta（引用"触发词行"概念本身，如 SP 两条）。
// 用法：node w1b_extract.mjs <skillsRoot> <jsYamlDir>
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync, mkdirSync } from 'node:fs';
import { join, basename } from 'node:path';

const [, , SRC, JSDIR] = process.argv;
if (!SRC || !JSDIR) { console.error('用法：node w1b_extract.mjs <skillsRoot> <jsYamlDir>'); process.exit(2); }
const entry = existsSync(join(JSDIR, 'node_modules', 'js-yaml', 'index.js'))
  ? join(JSDIR, 'node_modules', 'js-yaml', 'index.js') : join(JSDIR, 'index.js');
const require = createRequire(join(entry, 'index.js'));
const jsYaml = require(entry.endsWith('index.js') ? entry : entry);

const ARROW = /→\s*`([^`]+)`/g;
const TRIGGER = /触发词/;
const SPLIT = /[。；]/;
const FRONT = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/;

const slugs = readdirSync(SRC).filter(s => statSync(join(SRC, s)).isDirectory() && existsSync(join(SRC, s, 'SKILL.md'))).sort();
const slugSet = new Set(slugs);
const descs = {};   // slug -> js-yaml 解析后的 desc（权威值）
const meta = {};
for (const slug of slugs) {
  const t = readFileSync(join(SRC, slug, 'SKILL.md'), 'utf8');
  const m = t.match(FRONT);
  if (!m) { console.error(`✗ ${slug}: frontmatter 不匹配`); process.exit(1); }
  let doc;
  try { doc = jsYaml.load(m[1]); } catch (e) { console.error(`✗ ${slug}: js-yaml 解析失败 ${e.message}`); process.exit(1); }
  const d = doc && doc.description;
  if (typeof d !== 'string' || !d) { console.error(`✗ ${slug}: desc 非字符串/为空`); process.exit(1); }
  if (/[\n\r]/.test(d)) { console.error(`✗ ${slug}: desc 含换行（非单行，违反 W0 归一口径）`); process.exit(1); }
  descs[slug] = d;
  meta[slug] = { desc_len: d.length, budget_left: 1024 - d.length };
}

function sentences(desc) {
  const out = []; let s = 0;
  for (const m of desc.matchAll(new RegExp(SPLIT, 'g'))) { const seg = desc.slice(s, m.index + 1); if (seg.trim()) out.push(seg); s = m.index + 1; }
  const tail = desc.slice(s); if (tail.trim()) out.push(tail);
  return out;
}

const rules = [];        // 每箭头实例一条
let sentNo = 0; const sentenceIndex = [];
const triggerLines = []; const fallbacks = [];
for (const slug of slugs) {
  const ss = sentences(descs[slug]);
  ss.forEach((sent, i) => {
    const sid = `S-${slug}-${String(i + 1).padStart(2, '0')}`;
    sentNo++;
    const hits = [...sent.matchAll(ARROW)];
    for (const h of hits) {
      const to = h[1];
      const wildcard = to.includes('*');
      rules.push({
        from: slug, to, wildcard, sid,
        exact: !wildcard && slugSet.has(to),
        quote: sent,
      });
    }
    if (TRIGGER.test(sent)) {
      const cls = /触发词行/.test(sent) ? 'meta' : (/触发词[:：]/.test(sent) ? 'real' : 'qualification');
      triggerLines.push({ slug, sid, class: cls, quote: sent });
    }
    if (/缺省优先|默认归|兜底|不再循环|主答归|一律先归|一律归本技能|一律归/.test(sent)) {
      fallbacks.push({ slug, sid, quote: sent });
    }
    sentenceIndex.push({ sid, slug, i: i + 1 });
  });
}
// id 编号
rules.forEach((r, i) => { r.id = 'C-' + String(i + 1).padStart(3, '0'); });
fallbacks.forEach((f, i) => { f.id = 'F-' + String(i + 1).padStart(3, '0'); });
triggerLines.forEach((t, i) => { t.id = 'T-' + String(i + 1).padStart(2, '0'); });

// 重复模板统计（同 quote 多件）
const dupMap = new Map();
for (const r of rules) { if (!dupMap.has(r.quote)) dupMap.set(r.quote, new Set()); dupMap.get(r.quote).add(r.from); }
const dupTemplates = [...dupMap.entries()].filter(([, v]) => v.size >= 2)
  .map(([q, v]) => ({ quote: q, froms: [...v], covering: rules.filter(r => r.quote === q).map(r => r.id) }));

// 目标存在性
const missingTargets = rules.filter(r => !r.wildcard && !r.exact).map(r => ({ id: r.id, to: r.to, from: r.from }));
const wildcards = [...new Set(rules.filter(r => r.wildcard).map(r => r.to))];

const out = {
  schema: 'edu-route-extract-v1', generated: new Date().toISOString(),
  source_root: SRC, desc_parse: 'js-yaml（引擎同款 · A-15 权威）',
  sentence_split: '[。；] 近似（引号内句号会误切；每条带 sid+quote 供逐条核对）',
  counts: {
    slugs: slugs.length, sentences: sentNo,
    arrow_instances: rules.length, arrow_sentences: new Set(rules.map(r => r.sid)).size,
    wildcard_targets: wildcards, trigger_lines: triggerLines.length,
    trigger_by_class: triggerLines.reduce((a, t) => (a[t.class] = (a[t.class] || 0) + 1, a), {}),
    fallbacks: fallbacks.length, dup_templates: dupTemplates.length,
    dup_covering: dupTemplates.reduce((a, d) => a + d.covering.length, 0),
  },
  slugs, meta, rules, trigger_lines: triggerLines, fallbacks, dup_templates: dupTemplates,
  missing_targets: missingTargets,
};
const OUT = process.argv[4] || join(process.cwd(), 'routing', 'rules-v1-extract.json');
writeFileSync(OUT, JSON.stringify(out, null, 1), 'utf8');
console.log(`✔ 抽取完成 → ${OUT}`);
console.log(`  件数 ${slugs.length} ｜ 句 ${sentNo} ｜ 箭头实例 ${rules.length}（分布 ${out.counts.arrow_sentences} 句）｜ 通配目标 ${JSON.stringify(wildcards)}`);
console.log(`  触发词行 ${triggerLines.length}（${JSON.stringify(out.counts.trigger_by_class)}）｜ 兜底/主答 ${fallbacks.length} ｜ 重复模板 ${dupTemplates.length} 条覆盖 ${out.counts.dup_covering} 实例`);
if (missingTargets.length) console.log(`  ⚠ 目标不存在的精确箭头：${missingTargets.map(m => `${m.id}→${m.to}`).join('、')}`);
const w = rules.filter(r => r.wildcard);
console.log(`  通配实例 ${w.length} 条：${w.map(r => `${r.id} ${r.from}→${r.to}`).join('、')}`);
