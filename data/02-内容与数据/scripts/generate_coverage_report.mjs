import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONTENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = resolve(CONTENT_ROOT, 'data');
const REPORT = resolve(CONTENT_ROOT, 'reports', '两本教材-章节题库覆盖报告.md');
function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted && char === '"' && text[index + 1] === '"') { cell += '"'; index += 1; continue; }
    if (char === '"') { quoted = !quoted; continue; }
    if (!quoted && char === ',') { row.push(cell); cell = ''; continue; }
    if (!quoted && (char === '\n' || char === '\r')) { if (char === '\r' && text[index + 1] === '\n') index += 1; row.push(cell); cell = ''; if (row.some(value => value !== '')) rows.push(row); row = []; continue; }
    cell += char;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  const [headers, ...values] = rows;
  return values.map(valueRow => Object.fromEntries(headers.map((header, index) => [header, valueRow[index] ?? ''])));
}
const csv = async name => parseCsv(await readFile(resolve(DATA, name), 'utf8'));
const [books, chapters, sections, unitKnowledge, sectionAbilities, questionSections, questions] = await Promise.all(['book_catalog.csv', 'chapter_catalog.csv', 'section_catalog.csv', 'content_unit_knowledge_edges.csv', 'section_ability_edges.csv', 'question_section_edges.csv', 'question_bank.csv'].map(csv));
const approved = new Map(questions.filter(question => question.status === 'approved').map(question => [question.question_id, question]));
const report = ['# 两本教材：章节—知识点—能力—题目覆盖报告', '', '> 本报告由 `npm run report:coverage` 自动生成。它验证结构覆盖，不替代学科专家对题干、答案和难度的审核。', '', '## 标签链', '', '`书籍 → 章节 → 小节（教材单元） → 知识点 → 能力`；每道题再通过 `question_section_edges.csv` 直接落到一个教材小节，可由此追溯章节、知识点、能力和原始资料位置。', '', '## 按章节覆盖', '', '|书籍|章节|小节数|知识点数|能力数|正式题数|题型数|结构状态|', '|---|---|---:|---:|---:|---:|---:|---|'];
for (const chapter of chapters) {
  const chapterSections = sections.filter(section => section.chapter_id === chapter.chapter_id && section.status === 'active');
  const sectionIds = new Set(chapterSections.map(section => section.section_id));
  const unitIds = new Set(chapterSections.map(section => section.content_unit_id));
  const questionsForChapter = questionSections.filter(edge => sectionIds.has(edge.section_id) && approved.has(edge.question_id));
  const questionIds = new Set(questionsForChapter.map(edge => edge.question_id));
  const kpCount = new Set(unitKnowledge.filter(edge => unitIds.has(edge.content_unit_id)).map(edge => edge.knowledge_point_id)).size;
  const abilityCount = new Set(sectionAbilities.filter(edge => sectionIds.has(edge.section_id)).map(edge => edge.ability_id)).size;
  const typeCount = new Set([...questionIds].map(id => approved.get(id)?.question_type).filter(Boolean)).size;
  const bookName = books.find(book => book.book_id === chapter.book_id)?.book_name ?? chapter.book_id;
  const status = chapterSections.length && kpCount && abilityCount && questionIds.size ? '结构已覆盖' : '缺少映射';
  report.push(`|${bookName}|${chapter.chapter_order}. ${chapter.chapter_name}|${chapterSections.length}|${kpCount}|${abilityCount}|${questionIds.size}|${typeCount}|${status}|`);
}
report.push('', '## 按教材小节覆盖', '', '|书籍|章节|小节|知识点数|能力|正式题数|题型|复测题|', '|---|---|---|---:|---|---:|---|---:|');
for (const section of sections.filter(section => section.status === 'active')) {
  const chapter = chapters.find(item => item.chapter_id === section.chapter_id);
  const ids = questionSections.filter(edge => edge.section_id === section.section_id && approved.has(edge.question_id)).map(edge => edge.question_id);
  const sectionQuestions = ids.map(id => approved.get(id));
  const abilityIds = [...new Set(sectionAbilities.filter(edge => edge.section_id === section.section_id).map(edge => edge.ability_id))];
  const bookName = books.find(book => book.book_id === section.book_id)?.book_name ?? section.book_id;
  report.push(`|${bookName}|${chapter?.chapter_name ?? section.chapter_id}|${section.section_order}. ${section.section_title}|${unitKnowledge.filter(edge => edge.content_unit_id === section.content_unit_id).length}|${abilityIds.join('、')}|${sectionQuestions.length}|${[...new Set(sectionQuestions.map(question => question.question_type))].join('、')}|${sectionQuestions.filter(question => question.question_type === '复测题').length}|`);
}
report.push('', '## 使用规则', '', '- 新增小节：先登记教材来源，再在 `content_unit_catalog.csv` 和 `content_unit_knowledge_edges.csv` 标注小节与知识点，随后运行 `npm run build:hierarchy-tags`。', '- 新增正式题：必须同步维护题目、知识点/能力边和教材出处，随后运行 `npm run build:hierarchy-tags && npm run verify:content`。', '- “结构已覆盖”只表示题目可追溯到小节且拥有知识/能力映射；上线前仍应由人工完成题目科学性、答案准确性、难度分级和版权合规审核。', '');
await mkdir(dirname(REPORT), { recursive: true });
await writeFile(REPORT, report.join('\n'), 'utf8');
console.log(`coverage report generated: ${REPORT}`);
