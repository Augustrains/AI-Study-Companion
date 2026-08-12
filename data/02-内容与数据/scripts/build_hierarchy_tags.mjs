import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONTENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = resolve(CONTENT_ROOT, 'data');
const apply = process.argv.includes('--apply');

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') { cell += '"'; index += 1; continue; }
    if (char === '"') { quoted = !quoted; continue; }
    if (!quoted && char === ',') { row.push(cell); cell = ''; continue; }
    if (!quoted && (char === '\n' || char === '\r')) {
      if (char === '\r' && text[index + 1] === '\n') index += 1;
      row.push(cell); cell = '';
      if (row.some(value => value !== '')) rows.push(row);
      row = [];
      continue;
    }
    cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers, ...values] = rows;
  return values.map(valuesRow => Object.fromEntries(headers.map((header, index) => [header, valuesRow[index] ?? ''])));
}

function formatCell(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
function formatCsv(headers, rows) {
  return `${headers.join(',')}\n${rows.map(row => headers.map(header => formatCell(row[header])).join(',')).join('\n')}\n`;
}
async function load(name) { return parseCsv(await readFile(resolve(DATA, name), 'utf8')); }
function unique(rows, key) {
  const seen = new Set();
  return rows.filter(row => { const id = key(row); if (seen.has(id)) return false; seen.add(id); return true; });
}

const [units, unitKnowledge, questionSources, abilityKnowledge] = await Promise.all([
  load('content_unit_catalog.csv'), load('content_unit_knowledge_edges.csv'), load('question_source_edges.csv'), load('ability_knowledge_edges.csv'),
]);
const sectionCounts = new Map();
const taggedUnits = units.map(unit => {
  const sectionOrder = (sectionCounts.get(unit.chapter_id) ?? 0) + 1;
  sectionCounts.set(unit.chapter_id, sectionOrder);
  return { ...unit, section_id: `sec-${unit.content_unit_id.replace('-unit-', '-')}`, section_order: String(sectionOrder) };
});
const unitById = new Map(taggedUnits.map(unit => [unit.content_unit_id, unit]));
const sections = taggedUnits.map(unit => ({
  section_id: unit.section_id, book_id: unit.book_id, chapter_id: unit.chapter_id, content_unit_id: unit.content_unit_id,
  section_order: unit.section_order, section_title: unit.section_title, source_relative_path: unit.source_relative_path,
  source_anchor: unit.source_url, status: unit.review_status === 'approved' ? 'active' : 'planned',
}));
const chapters = [];
const seenChapters = new Set();
for (const unit of taggedUnits) {
  if (seenChapters.has(unit.chapter_id)) continue;
  seenChapters.add(unit.chapter_id);
  chapters.push({
    chapter_id: unit.chapter_id, book_id: unit.book_id,
    chapter_order: String(chapters.filter(chapter => chapter.book_id === unit.book_id).length + 1),
    chapter_name: unit.chapter_name, source_reference: unit.source_relative_path.split('/').slice(0, -1).join('/'),
    status: unit.review_status === 'approved' ? 'active' : 'planned',
  });
}
const activeUnitKnowledge = unique(unitKnowledge.filter(edge => unitById.has(edge.content_unit_id)).map(edge => ({ ...edge, status: 'active' })), edge => `${edge.content_unit_id}|${edge.knowledge_point_id}|${edge.relation_type}`);
const chapterKnowledge = unique(activeUnitKnowledge.map(edge => ({
  chapter_id: unitById.get(edge.content_unit_id).chapter_id, knowledge_point_id: edge.knowledge_point_id,
  relation_type: edge.relation_type, status: 'active',
})), edge => `${edge.chapter_id}|${edge.knowledge_point_id}|${edge.relation_type}`);
const abilitiesByKnowledge = new Map();
for (const edge of abilityKnowledge.filter(edge => edge.status === 'active')) {
  abilitiesByKnowledge.set(edge.knowledge_point_id, [...(abilitiesByKnowledge.get(edge.knowledge_point_id) ?? []), edge]);
}
const sectionAbilities = unique(activeUnitKnowledge.flatMap(edge => (abilitiesByKnowledge.get(edge.knowledge_point_id) ?? []).map(ability => ({
  section_id: unitById.get(edge.content_unit_id).section_id, ability_id: ability.ability_id,
  relation_type: edge.relation_type === 'primary' && ability.relation_type === 'core' ? 'primary' : 'supporting', weight: ability.weight, status: 'active',
}))), edge => `${edge.section_id}|${edge.ability_id}`);
const questionSections = unique(questionSources.filter(edge => edge.status === 'active' && unitById.has(edge.content_unit_id)).map(edge => {
  const unit = unitById.get(edge.content_unit_id);
  return { question_id: edge.question_id, book_id: unit.book_id, chapter_id: unit.chapter_id, section_id: unit.section_id, content_unit_id: unit.content_unit_id, source_locator: edge.source_locator, tag_role: 'direct_source', status: 'active' };
}), edge => `${edge.question_id}|${edge.section_id}|${edge.source_locator}`);
const outputs = new Map([
  ['chapter_catalog.csv', formatCsv(['chapter_id', 'book_id', 'chapter_order', 'chapter_name', 'source_reference', 'status'], chapters)],
  ['section_catalog.csv', formatCsv(['section_id', 'book_id', 'chapter_id', 'content_unit_id', 'section_order', 'section_title', 'source_relative_path', 'source_anchor', 'status'], sections)],
  ['chapter_knowledge_edges.csv', formatCsv(['chapter_id', 'knowledge_point_id', 'relation_type', 'status'], chapterKnowledge)],
  ['section_ability_edges.csv', formatCsv(['section_id', 'ability_id', 'relation_type', 'weight', 'status'], sectionAbilities)],
  ['question_section_edges.csv', formatCsv(['question_id', 'book_id', 'chapter_id', 'section_id', 'content_unit_id', 'source_locator', 'tag_role', 'status'], questionSections)],
]);
if (!apply) {
  console.log(`dry run: ${chapters.length} chapters, ${sections.length} sections, ${activeUnitKnowledge.length} unit-knowledge edges, ${sectionAbilities.length} section-ability edges, ${questionSections.length} question-section edges`);
  console.log('Run with --apply to write only the five generated hierarchy tables; existing source tables are not changed.');
} else {
  await Promise.all([...outputs].map(([name, contents]) => writeFile(resolve(DATA, name), contents, 'utf8')));
  console.log(`hierarchy tags built: ${chapters.length} chapters, ${sections.length} sections, ${activeUnitKnowledge.length} unit-knowledge edges, ${sectionAbilities.length} section-ability edges, ${questionSections.length} question-section edges`);
}
