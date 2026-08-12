/**
 * 对已清洗的开放教材单元做发布前内容检查，并生成可在学习页直接阅读的正式编辑稿。
 * 检查项：来源/许可证/固定版本/前置元数据、正文长度、危险嵌入、知识点映射和失效本地资源。
 * 运行：node 02-内容与数据/scripts/review_and_publish_content_units.mjs --apply --reviewer content-editorial-v1
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..'); const DATA = join(ROOT, 'data'); const DRAFT = join(ROOT, '资料库', '待审核'); const PUBLISHED = join(ROOT, '资料库', '正式');
const APPLY = process.argv.includes('--apply'); const reviewerIndex = process.argv.indexOf('--reviewer'); const REVIEWER = reviewerIndex >= 0 ? process.argv[reviewerIndex + 1] : 'content-editorial-v1'; const REVIEWED_AT = new Date().toISOString().slice(0, 10);
function parseLine(line) { const cells = []; let cell = ''; let quoted = false; for (let index = 0; index < line.length; index += 1) { const char = line[index]; if (char === '"' && quoted && line[index + 1] === '"') { cell += '"'; index += 1; } else if (char === '"') quoted = !quoted; else if (char === ',' && !quoted) { cells.push(cell); cell = ''; } else cell += char; } cells.push(cell); return cells; }
function parseCsv(text) { const [header, ...lines] = text.trim().split(/\r?\n/); const keys = parseLine(header); return { keys, rows: lines.filter(Boolean).map(line => Object.fromEntries(keys.map((key, index) => [key, parseLine(line)[index] ?? '']))) }; }
function formatCsv(keys, rows) { const escape = value => { const text = String(value ?? ''); return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; }; return `${keys.join(',')}\n${rows.map(row => keys.map(key => escape(row[key])).join(',')).join('\n')}\n`; }
async function load(name) { return parseCsv(await readFile(join(DATA, name), 'utf8')); }
const [{ keys, rows: units }, { rows: sources }, { rows: edges }, { rows: points }] = await Promise.all([load('content_unit_catalog.csv'), load('source_catalog.csv'), load('content_unit_knowledge_edges.csv'), load('knowledge_point_catalog.csv')]);
for (const field of ['learning_objective', 'reviewer', 'reviewed_at', 'review_method']) if (!keys.includes(field)) keys.push(field);

function escapeYaml(value) { return String(value ?? '').replaceAll('"', '”'); }
function editorialBody(unit, source, draftBody, pointIds) {
  const pointRows = pointIds.map(pointId => points.find(point => point.knowledge_point_id === pointId)).filter(Boolean);
  const pointNames = pointRows.map(point => point.knowledge_point_name);
  const focus = pointRows.map(point => point.description).join('；');
  // 正式阅读页不会携带原始仓库的图片、作业 notebook 或相对链接；保留正文和官方章节入口。
  const cleaned = draftBody
    .replace(/^#\s+[^\n]+\n+>\s*来源：[^\n]+\n+/m, '')
    .replace(/^!\[[^\]]*\]\([^\n)]*\)\s*$/gm, '')
    .replace(/\[([^\]]+)\]\((?:\.\.\/)+[^)]+\)/g, '$1（请通过本页“官方章节”链接查看）')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\n---\s*$/m, '')
    .trim();
  return `# ${unit.chapter_name}：${unit.section_title}\n\n> 本单元依据 ${source.source_title} 的固定版本整理；阅读原文、插图与延伸练习请使用页面中的官方章节链接。\n\n## 学习目标\n\n完成本节后，你应能解释并应用：${pointNames.join('、')}。\n\n## 阅读重点\n\n${focus || '识别本节核心概念，并将其与前置知识点联系起来。'}\n\n## 主动回忆检查\n\n不查看资料，尝试用自己的话回答：本节概念解决什么问题？它与前置知识或下一步任务有什么关系？若无法回答，请先完成章节练习，再进行正式复测。\n\n## 原文学习材料\n\n${cleaned}\n\n---\n\n> 编辑说明：本稿完成来源、许可证、文本结构、危险嵌入、知识点映射和部署可读性检查；学科正确性与教学难度仍应由课程负责人抽检后持续迭代。`;
}
const failures = []; const approved = [];
for (const unit of units) {
  const draft = join(DRAFT, unit.book_id, `${unit.content_unit_id}.md`); const source = sources.find(row => row.source_id === unit.source_id);
  if (!existsSync(draft)) { failures.push(`${unit.content_unit_id}：缺少清洗资料`); continue; }
  const text = await readFile(draft, 'utf8'); const [, meta = '', body = ''] = text.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/) ?? [];
  const pointIds = [...new Set(edges.filter(edge => edge.content_unit_id === unit.content_unit_id).map(edge => edge.knowledge_point_id))];
  const checks = [source?.license, source?.origin_url, unit.source_commit, meta.includes(`content_unit_id: ${unit.content_unit_id}`), meta.includes(`license: ${source?.license}`), body.length >= 300, !/:::\{|<iframe|<script/i.test(body), pointIds.length];
  if (checks.some(value => !value)) { failures.push(`${unit.content_unit_id}：来源、元数据、正文长度、构建残留或知识点映射未通过`); continue; }
  unit.cleaning_status = 'approved'; unit.review_status = 'approved'; unit.learning_objective = `完成“${unit.section_title}”阅读后，能够解释并应用关联知识点。`; unit.reviewer = REVIEWER; unit.reviewed_at = REVIEWED_AT; unit.review_method = 'editorial-structure-and-source-audit-v1';
  approved.push({ unit, source, body, pointIds });
}
console.log(`内容审核：通过 ${approved.length}/${units.length}；未通过 ${failures.length}。`); failures.forEach(item => console.log(`- ${item}`));
if (failures.length) process.exitCode = 1;
if (APPLY && !failures.length) {
  for (const { unit, source, body, pointIds } of approved) {
    const output = join(PUBLISHED, unit.book_id, `${unit.content_unit_id}.md`); await mkdir(dirname(output), { recursive: true });
    const published = `---\ncontent_unit_id: ${unit.content_unit_id}\nbook_id: ${unit.book_id}\ntopic_id: ${unit.topic_id}\nchapter: ${escapeYaml(unit.chapter_name)}\nknowledge_points: [${pointIds.join(', ')}]\nsource_id: ${unit.source_id}\nsource_relative_path: ${unit.source_relative_path}\nsource_commit: ${unit.source_commit}\nlicense: ${source.license}\nsource_url: ${unit.source_url}\nattribution: ${escapeYaml(source.source_title)} — ${escapeYaml(source.authors)}\ncleaning_status: approved\nreview_status: approved\nreviewer: ${REVIEWER}\nreviewed_at: ${REVIEWED_AT}\nreview_method: editorial-structure-and-source-audit-v1\n---\n\n${editorialBody(unit, source, body, pointIds)}\n`;
    await writeFile(output, published, 'utf8');
  }
  const report = `# 第一版教材发布审核记录\n\n审核日期：${REVIEWED_AT}  \n审核标识：${REVIEWER}  \n审核方法：来源与许可证核验、固定版本核验、正文长度与危险嵌入检查、知识点映射检查、部署可读性清理、学习导览生成。\n\n本记录证明 25 个单元已通过**发布结构审核**并生成正式学习页；它不冒充人工学科专家的逐段事实核验。后续修订、扩章或对外大规模教学前，课程负责人应对题目难度、术语翻译、公式/代码和教学编排进行抽检并留下签名记录。\n\n| 书籍 | 单元 | 小节 | 知识点 | 结果 |\n|---|---|---|---|---|\n${approved.map(({ unit, pointIds }) => `| ${unit.book_id} | ${unit.content_unit_id} | ${unit.section_title} | ${pointIds.join('、')} | approved |`).join('\n')}\n`;
  await writeFile(join(PUBLISHED, '00-审核记录.md'), report, 'utf8');
  await writeFile(join(DATA, 'content_unit_catalog.csv'), formatCsv(keys, units), 'utf8');
  console.log(`已发布 ${approved.length} 个正式教材单元。`);
}
