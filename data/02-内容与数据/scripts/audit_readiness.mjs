/**
 * 面向内容负责人和集成负责人的发布就绪审计。
 * 默认只输出事实与阻塞项；传入 --strict 时，存在阻塞项即返回非零状态。
 */
import { readFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = resolve(HERE, '../data');

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const parseLine = line => {
    const cells = []; let cell = ''; let quoted = false;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      if (char === '"' && quoted && line[index + 1] === '"') { cell += '"'; index += 1; }
      else if (char === '"') quoted = !quoted;
      else if (char === ',' && !quoted) { cells.push(cell); cell = ''; }
      else cell += char;
    }
    cells.push(cell); return cells;
  };
  const header = parseLine(lines.shift());
  return lines.filter(Boolean).map(line => Object.fromEntries(header.map((key, index) => [key, parseLine(line)[index] ?? ''])));
}
async function csv(name) { return parseCsv(await readFile(join(DATA_DIR, name), 'utf8')); }
const [sources, units, topics, scope, questions, questionKnowledgeEdges, preReviews, deliveryProfiles, wrongOptionReviews, scoringCards, poolBacklog] = await Promise.all([
  csv('source_catalog.csv'), csv('content_unit_catalog.csv'), csv('topic_catalog.csv'), csv('book_knowledge_scope.csv'), csv('question_bank.csv'), csv('question_knowledge_edges.csv'), csv('question_pre_review.csv'), csv('question_delivery_profile.csv'), csv('question_wrong_option_review.csv'), csv('mastery_task_scoring_card.csv'), csv('question_pool_expansion_backlog.csv')
]);

const blockers = [];
const activeTopics = topics.filter(row => row.status === 'active');
console.log('内容发布就绪审计');
console.log(`资料源：${sources.length} 本；章节单元：${units.length} 个；当前可运行专题：${activeTopics.length} 个。`);

for (const source of sources) {
  const sourceUnits = units.filter(unit => unit.source_id === source.source_id);
  const approved = sourceUnits.filter(unit => unit.review_status === 'approved').length;
  const pending = sourceUnits.filter(unit => unit.review_status !== 'approved').length;
  console.log(`- ${source.book_id}：${source.source_title}，${sourceUnits.length} 个章节单元（正式 ${approved}，待审核 ${pending}）。`);
  if (!source.license || !source.origin_url || !source.source_commit) blockers.push(`${source.book_id} 缺少许可证、原始链接或固定版本`);
  if (!approved) blockers.push(`${source.book_id} 没有审核通过的正式教材单元`);
}

for (const topic of activeTopics) {
  const required = scope.filter(edge => edge.book_id === topic.book_id && edge.topic_id === topic.topic_id && edge.scope_type === 'required' && edge.status === 'active').map(edge => edge.knowledge_point_id);
  const topicQuestions = questions.filter(question => question.book_id === topic.book_id && question.topic_id === topic.topic_id && question.status === 'approved');
  const missing = [];
  const masteryGaps = [];
  for (const pointId of required) {
    const pointQuestions = topicQuestions.filter(question => questionKnowledgeEdges.some(edge => edge.status === 'active' && edge.question_id === question.question_id && edge.knowledge_point_id === pointId));
    if (!pointQuestions.length) missing.push(pointId);
    const types = new Set(pointQuestions.map(question => question.question_type));
    if (pointQuestions.length < 4 || types.size < 3) masteryGaps.push(`${pointId}（${pointQuestions.length} 题 / ${types.size} 类题型）`);
  }
  console.log(`- ${topic.topic_name}：${required.length} 个必学知识点，${topicQuestions.length} 道 approved 题。`);
  if (missing.length) blockers.push(`${topic.topic_name} 缺少正式题：${missing.join('、')}`);
  if (masteryGaps.length) blockers.push(`${topic.topic_name} 不能支撑“掌握”目标：${masteryGaps.join('；')}`);
  const linkedApprovedUnits = units.filter(unit => unit.book_id === topic.book_id && unit.review_status === 'approved').length;
  if (!linkedApprovedUnits) blockers.push(`${topic.topic_name} 没有审核通过的正式教材单元`);
}

const approvedQuestions = questions.filter(question => question.status === 'approved');
const missingProfiles = approvedQuestions.filter(question => !deliveryProfiles.some(profile => profile.question_id === question.question_id && profile.status === 'active'));
const pendingBaseReviews = preReviews.filter(review => review.human_decision !== 'approved');
const pendingScoringCards = scoringCards.filter(card => card.status !== 'active');
const pendingWrongOptionReviews = wrongOptionReviews.filter(row => row.is_correct === 'false' && row.status !== 'active').length;
const expansionGaps = poolBacklog.filter(row => Number(row.missing_questions) > 0).length;
if (missingProfiles.length) blockers.push(`正式题缺少用途与曝光规则：${missingProfiles.map(question => question.question_id).join('、')}`);
if (pendingBaseReviews.length) blockers.push(`仍有 ${pendingBaseReviews.length} 道基础题未完成内容负责人确认`);
if (pendingScoringCards.length) blockers.push(`仍有 ${pendingScoringCards.length} 张开放掌握任务评分卡未完成内容负责人确认`);

console.log(`- 题目用途标签：${deliveryProfiles.length}/${approvedQuestions.length}；基础题人工确认待办：${pendingBaseReviews.length}；评分卡待确认：${pendingScoringCards.length}。`);
console.log(`- 错误选项标签待确认：${pendingWrongOptionReviews}；建议扩题待办：${expansionGaps} 个知识点（不阻塞第一版基础路径，但会限制独立复测）。`);

console.log(`\n结论：${blockers.length ? '尚不可对外发布' : '内容数据达到第一版发布线'}。`);
if (blockers.length) {
  console.log('阻塞项：');
  blockers.forEach((blocker, index) => console.log(`${index + 1}. ${blocker}`));
}
if (process.argv.includes('--strict') && blockers.length) process.exitCode = 1;
