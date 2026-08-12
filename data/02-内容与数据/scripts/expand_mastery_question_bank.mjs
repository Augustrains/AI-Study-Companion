/**
 * 为内容负责人已审核的基础题生成固定、可追溯的三种待审核变式草稿：应用、综合、无提示复测。
 * 题干、选项、答案、出处都保存在 CSV；脚本不调用模型，也不会在运行时临时出题。
 * 变式草稿不能因为换序或改写题干自动成为“掌握”证据，必须由人工补写和审核后再批准。
 * 运行：node 02-内容与数据/scripts/expand_mastery_question_bank.mjs --apply
 */
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = resolve(HERE, '../data');
const APPLY = process.argv.includes('--apply');

if (process.argv.includes('--reset-corrupted-variants')) {
  const file = join(DATA, 'question_bank.csv'); const raw = await readFile(file, 'utf8'); const marker = raw.search(/\n[a-z]+-q\d+-v[234],/);
  if (marker < 0) throw new Error('未找到可清理的题目变式标记');
  await writeFile(file, `${raw.slice(0, marker)}\n`, 'utf8');
  console.log('已恢复基础题数据；请重新运行 --apply 生成无换行的正式变式。');
  process.exit(0);
}

function parseLine(line) {
  const cells = []; let cell = ''; let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"' && quoted && line[index + 1] === '"') { cell += '"'; index += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === ',' && !quoted) { cells.push(cell); cell = ''; }
    else cell += char;
  }
  cells.push(cell); return cells;
}
function parseCsv(text) { const [header, ...lines] = text.trim().split(/\r?\n/); const keys = parseLine(header); return lines.filter(Boolean).map(line => Object.fromEntries(keys.map((key, index) => [key, parseLine(line)[index] ?? '']))); }
function csv(rows) { const keys = Object.keys(rows[0]); const escape = value => { const text = String(value ?? ''); return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; }; return `${keys.join(',')}\n${rows.map(row => keys.map(key => escape(row[key])).join(',')).join('\n')}\n`; }
async function load(name) { return parseCsv(await readFile(join(DATA, name), 'utf8')); }
async function save(name, rows) { await writeFile(join(DATA, name), csv(rows), 'utf8'); }
function rotate(values, amount) { return [...values.slice(amount), ...values.slice(0, amount)]; }
function independentStem(base, number) {
  const subject = base.question_summary;
  if (number === 2) return `应用情境：某项目需要根据“${subject}”做出实际决策。下列做法或判断中，哪一项最符合该知识点？`;
  if (number === 3) return `综合判断：团队正在复盘一个模型方案。围绕“${subject}”，哪一项解释同时符合其定义与实际用途？`;
  return `无提示复测：不查看资料。请独立判断关于“${subject}”的下列说法，哪一项最准确？`;
}
function buildVariant(base, number) {
  const options = JSON.parse(base.options_json); const rotated = number === 2 ? rotate(options, 1) : number === 3 ? rotate(options, 2) : [...options].reverse();
  const correctText = options[Number(base.correct_option)]; const correct = rotated.indexOf(correctText);
  const labels = {
    2: { type: '应用题', difficulty: 2, prefix: `应用情境：请把“${base.question_summary}”用于一个具体学习或工程判断。` },
    3: { type: '综合题', difficulty: 3, prefix: `综合判断：比较几个可能方案后，选择最符合“${base.question_summary}”原理的一项。` },
    4: { type: '复测题', difficulty: 2, prefix: `无提示复测：不查看资料，重新判断“${base.question_summary}”。` }
  }[number];
  return { ...base, question_id: `${base.question_id}-v${number}`, target_level: '掌握', question_type: labels.type, difficulty: labels.difficulty,
    question_summary: `${base.question_summary}·${labels.type}`, prompt: independentStem(base, number), options_json: JSON.stringify(rotated), correct_option: correct,
    answer_key: correctText, explanation: `${base.explanation}（待审核${labels.type}草稿 v${number}）`, source_note: `${base.source_note}；开发者维护待审核${labels.type}草稿 v${number}`, version: number, status: 'pending_review' };
}

const [questions, knowledgeEdges, abilityEdges, sourceEdges, blueprints] = await Promise.all([
  load('question_bank.csv'), load('question_knowledge_edges.csv'), load('question_ability_edges.csv'), load('question_source_edges.csv'), load('question_blueprint_catalog.csv')
]);
const isVariant = row => /-v[234]$/.test(row.question_id);
const canonicalQuestions = questions.filter(question => !isVariant(question));
const canonicalKnowledgeEdges = knowledgeEdges.filter(edge => !isVariant(edge));
const canonicalAbilityEdges = abilityEdges.filter(edge => !isVariant(edge));
const canonicalSourceEdges = sourceEdges.filter(edge => !isVariant(edge));
const baseQuestions = canonicalQuestions.filter(question => question.status === 'approved');
const existingIds = new Set(canonicalQuestions.map(question => question.question_id));
const generated = [];
for (const base of baseQuestions) for (const number of [2, 3, 4]) {
  const variant = buildVariant(base, number);
  if (!existingIds.has(variant.question_id)) generated.push(variant);
}
const allQuestions = [...canonicalQuestions, ...generated];
const copyEdges = (rows, idKey) => [...rows, ...generated.flatMap(variant => {
  const baseId = variant.question_id.replace(/-v[234]$/, '');
  return rows.filter(row => row.question_id === baseId).map(row => ({ ...row, question_id: variant.question_id }));
})];
const nextKnowledgeEdges = copyEdges(canonicalKnowledgeEdges, 'question_id');
const nextAbilityEdges = copyEdges(canonicalAbilityEdges, 'question_id');
const nextSourceEdges = copyEdges(canonicalSourceEdges, 'question_id');
const nextBlueprints = blueprints.map(blueprint => {
  const count = allQuestions.filter(question => question.status === 'approved' && nextKnowledgeEdges.some(edge => edge.question_id === question.question_id && edge.knowledge_point_id === blueprint.knowledge_point_id)).length;
  return { ...blueprint, current_approved_versions: String(count), gap_status: 'review_required', owner_action: '变式草稿必须补成不同情境、不同选项和不同解题路径的题目，并经内容负责人审核后才能作为掌握级证据。' };
});
console.log(`基础题 ${baseQuestions.length} 道；新增正式变式 ${generated.length} 道；合计 ${allQuestions.length} 道。`);
if (APPLY) {
  await Promise.all([
    save('question_bank.csv', allQuestions), save('question_knowledge_edges.csv', nextKnowledgeEdges), save('question_ability_edges.csv', nextAbilityEdges), save('question_source_edges.csv', nextSourceEdges), save('question_blueprint_catalog.csv', nextBlueprints)
  ]);
  console.log('已更新题库、知识点/能力/出处边表和掌握题目蓝图。');
} else console.log('仅预览；使用 --apply 写入文件。');
