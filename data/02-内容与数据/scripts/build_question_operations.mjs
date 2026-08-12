import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DATA = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'data');
const apply = process.argv.includes('--apply');

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
const esc = value => { const text = String(value ?? ''); return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text; };
const toCsv = (headers, rows) => `${headers.join(',')}\n${rows.map(row => headers.map(header => esc(row[header])).join(',')).join('\n')}\n`;
const load = async name => parseCsv(await readFile(resolve(DATA, name), 'utf8'));
const loadIfExists = async name => existsSync(resolve(DATA, name)) ? load(name) : [];
const cognitiveLevel = type => ({ '概念题': '记忆与理解', '解释题': '理解', '分类题': '理解', '比较题': '分析', '应用题': '应用', '计算题': '应用', '代码题': '应用', '调试题': '分析', '推导题': '分析', '情境题': '分析', '评价题': '评价', '建模题': '创造', '实验题': '创造', '复测题': '迁移复现' }[type] ?? '待确认');
const codeEnvironment = type => ['代码题', '调试题'].includes(type) ? '伪代码或Notebook（按题目要求）' : '不需要';
const scoringDimensions = task => {
  const common = task.task_type === '代码实现题' || task.task_type === '调试题'
    ? [['关键逻辑正确', 2], ['步骤或代码完整', 1], ['解释或边界处理', 1]]
    : task.task_type === '建模题' || task.task_type === '实验题'
      ? [['问题与目标定义', 1], ['方法选择与理由', 1], ['方案逻辑', 1], ['局限或验证方式', 1]]
      : [['核心结论正确', 2], ['推理或计算过程', 1], ['解释、应用或边界说明', 1]];
  const total = common.reduce((sum, [, score]) => sum + score, 0);
  const max = Number(task.max_score);
  const dimensions = common.map(([dimension, score], index) => ({ dimension, max_score: index === common.length - 1 ? score + (max - total) : score }));
  return JSON.stringify(dimensions);
};

const [questions, questionKnowledge, blueprints, masteryTasks, existingWrongOptionReviews, existingScoringCards] = await Promise.all(['question_bank.csv', 'question_knowledge_edges.csv', 'question_blueprint_catalog.csv', 'mastery_task_catalog.csv'].map(load).concat(['question_wrong_option_review.csv', 'mastery_task_scoring_card.csv'].map(loadIfExists)));
const pointByQuestion = new Map(questionKnowledge.filter(edge => edge.status === 'active').map(edge => [edge.question_id, edge.knowledge_point_id]));
const profiles = questions.filter(question => question.status === 'approved').map(question => {
  const base = Number(question.version) === 1;
  const retest = question.question_type === '复测题' || Number(question.version) > 1;
  return {
    question_id: question.question_id,
    primary_stage: base ? 'diagnostic' : question.question_type === '复测题' ? 'retest' : 'practice',
    allowed_stages: base ? 'diagnostic|practice|retest' : retest ? 'practice|retest' : 'practice',
    repeat_policy: base ? '每个诊断周期最多一次；复测池不足时可作为回退题' : question.question_type === '复测题' ? '每个复测周期最多一次' : '30天内练习最多三次；复测池可回退使用',
    practice_max_exposures: base ? '2' : '3',
    suggested_minutes: ['代码题', '调试题', '推导题', '建模题', '实验题'].includes(question.question_type) ? '8' : ['应用题', '计算题', '评价题', '情境题'].includes(question.question_type) ? '5' : '3',
    cognitive_level: cognitiveLevel(question.question_type),
    requires_code_environment: codeEnvironment(question.question_type),
    selection_note: '自动按题型和版本生成；内容负责人可在人工审核后调整。',
    status: 'active'
  };
});
const backlog = blueprints.map(blueprint => {
  const current = questions.filter(question => question.status === 'approved' && pointByQuestion.get(question.question_id) === blueprint.knowledge_point_id).length;
  const target = 7;
  return { knowledge_point_id: blueprint.knowledge_point_id, current_questions: String(current), target_questions: String(target), missing_questions: String(Math.max(0, target - current)), required_new_stages: '优先新增不与诊断重复的练习题和无提示复测题', required_new_types: '按知识点补真实应用、调试、实现或案例建模题', owner_action: '内容负责人编写并人工审核；不得由换序或通用改写替代。', status: current >= target ? 'ready_for_sampling' : 'waiting_content_expansion' };
});
const existingWrongByKey = new Map(existingWrongOptionReviews.map(row => [`${row.question_id}:${row.option_index}`, row]));
const wrongOptionReview = questions.filter(question => question.status === 'approved').flatMap(question => {
  const options = JSON.parse(question.options_json);
  return options.map((option, index) => {
    const generated = { question_id: question.question_id, option_index: String(index), option_text: option, knowledge_point_id: pointByQuestion.get(question.question_id) ?? '', is_correct: String(index === Number(question.correct_option)), misconception_code: index === Number(question.correct_option) ? '' : `pending-${question.question_id}-${index}`, misconception_label: index === Number(question.correct_option) ? '正确选项' : '待内容负责人填写：该错误选项反映的具体误解', remediation_knowledge_point_id: pointByQuestion.get(question.question_id) ?? '', reviewer: '', reviewed_at: '', status: index === Number(question.correct_option) ? 'not_applicable' : 'waiting_human_confirmation' };
    const existing = existingWrongByKey.get(`${question.question_id}:${index}`);
    return existing && existing.status !== 'waiting_human_confirmation' ? { ...generated, misconception_code: existing.misconception_code, misconception_label: existing.misconception_label, remediation_knowledge_point_id: existing.remediation_knowledge_point_id, reviewer: existing.reviewer, reviewed_at: existing.reviewed_at, status: existing.status } : generated;
  });
});
const existingCardByTask = new Map(existingScoringCards.map(card => [card.mastery_task_id, card]));
const scoringCards = masteryTasks.filter(task => task.status === 'approved').map(task => {
  const generated = {
  mastery_task_id: task.mastery_task_id,
  reference_answer_outline: '待内容负责人填写：参考解答、关键步骤或参考实现。',
  scoring_dimensions_json: scoringDimensions(task),
  common_errors: '待内容负责人填写：常见错误、扣分边界与不可接受答案。',
  hint_policy: '正式掌握任务默认无提示；如使用提示，必须记录 used_hint，不能作为无提示复测证据。',
  reviewer_instruction: '审核人按维度评分，并在 review_note 中写明关键依据；总分不得超过 max_score。',
  status: 'waiting_human_confirmation'
  };
  const existing = existingCardByTask.get(task.mastery_task_id);
  return existing && existing.status !== 'waiting_human_confirmation' ? { ...generated, reference_answer_outline: existing.reference_answer_outline, scoring_dimensions_json: existing.scoring_dimensions_json, common_errors: existing.common_errors, hint_policy: existing.hint_policy, reviewer_instruction: existing.reviewer_instruction, status: existing.status } : generated;
});
const outputs = [
  ['question_delivery_profile.csv', ['question_id', 'primary_stage', 'allowed_stages', 'repeat_policy', 'practice_max_exposures', 'suggested_minutes', 'cognitive_level', 'requires_code_environment', 'selection_note', 'status'], profiles],
  ['question_pool_expansion_backlog.csv', ['knowledge_point_id', 'current_questions', 'target_questions', 'missing_questions', 'required_new_stages', 'required_new_types', 'owner_action', 'status'], backlog],
  ['question_wrong_option_review.csv', ['question_id', 'option_index', 'option_text', 'knowledge_point_id', 'is_correct', 'misconception_code', 'misconception_label', 'remediation_knowledge_point_id', 'reviewer', 'reviewed_at', 'status'], wrongOptionReview],
  ['mastery_task_scoring_card.csv', ['mastery_task_id', 'reference_answer_outline', 'scoring_dimensions_json', 'common_errors', 'hint_policy', 'reviewer_instruction', 'status'], scoringCards],
];
console.log(`预览：${profiles.length} 条题目用途标签、${backlog.length} 条扩题待办、${wrongOptionReview.length} 条选项审核行、${scoringCards.length} 张掌握任务评分卡。`);
if (apply) {
  await mkdir(DATA, { recursive: true });
  await Promise.all(outputs.map(([name, headers, rows]) => writeFile(resolve(DATA, name), toCsv(headers, rows), 'utf8')));
  console.log('已写入题库运营数据与人工审核工作包。');
}
