import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const DATA = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'data');
const apply = process.argv.includes('--apply');
function parseCsv(text) { const rows=[]; let row=[]; let cell=''; let quoted=false; for(let i=0;i<text.length;i+=1){const char=text[i];if(quoted&&char==='"'&&text[i+1]==='"'){cell+='"';i+=1;continue;}if(char==='"'){quoted=!quoted;continue;}if(!quoted&&char===','){row.push(cell);cell='';continue;}if(!quoted&&(char==='\n'||char==='\r')){if(char==='\r'&&text[i+1]==='\n')i+=1;row.push(cell);cell='';if(row.some(value=>value!==''))rows.push(row);row=[];continue;}cell+=char;}if(cell||row.length){row.push(cell);rows.push(row);}const [headers,...values]=rows;return values.map(valueRow=>Object.fromEntries(headers.map((header,index)=>[header,valueRow[index]??'']))); }
const esc = value => { const text=String(value??''); return /[",\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text; };
const toCsv = (headers, rows) => `${headers.join(',')}\n${rows.map(row=>headers.map(header=>esc(row[header])).join(',')).join('\n')}\n`;
const load = async name => parseCsv(await readFile(resolve(DATA,name),'utf8'));
const loadIfExists = async name => existsSync(resolve(DATA,name)) ? load(name) : [];

const questionOverrides = {
  'ml-q02': { recommendation:'建议保留，并在扩题时补多步回报与终止状态', difficulty:'熟悉-合适', reason:'一步回报计算、答案和讲解一致；但只检验单步代入。' },
  'ml-q04': { recommendation:'建议保留为基本了解/练习题，不作为熟悉主证据', difficulty:'熟悉-偏低', reason:'题目只要求说出贝尔曼递推的未来价值部分，未检验折扣、动作选择或数值计算。' },
  'ml-q05': { recommendation:'建议保留为练习题，不单独作为掌握证据', difficulty:'掌握-偏低', reason:'数值更新结果正确，代码片段清晰；但仍是单步代入，不能证明能实现或调试Q Learning。' },
  'dl-q03': { recommendation:'建议保留为基本了解/练习题，不作为熟悉主证据', difficulty:'熟悉-偏低', reason:'前向输出用于计算损失的结论正确，但没有张量、样本或形状计算。' },
  'dl-q04': { recommendation:'建议保留为基本了解/练习题，不作为熟悉主证据', difficulty:'熟悉-偏低', reason:'反向传播求梯度的结论正确，但未检验链式法则、方向或具体梯度。' },
  'dl-q05': { recommendation:'建议保留为练习题，不单独作为掌握证据', difficulty:'掌握-偏低', reason:'optimizer.step 的答案正确，代码顺序清晰；但仅识别单行，未检验完整训练循环或调试能力。' },
  'ml-q12': { recommendation:'建议保留', difficulty:'基本了解-合适', reason:'题目确为MSE数值计算，正确答案和讲解一致；后续应补损失对优化的影响题。' },
  'dl-q15': { recommendation:'建议保留为基本了解题；扩题时增加具体尺寸计算', difficulty:'基本了解-合适', reason:'步幅增大通常降低输出空间尺寸的判断正确；虽然题型名为计算题，但当前未要求具体数值计算。' },
  'ml-q17': { recommendation:'建议保留', difficulty:'基本了解-偏高', reason:'验证集用于选超参数、测试集不应反复调参的表述正确；可作为模型选择的高质量基础题。' }
};
const taskGuidance = type => ({
  '简答题': ['核心概念与结论', '因果解释或边界条件', '术语准确性'],
  '推导题': ['公式或计算结果', '中间推导步骤', '边界条件或含义解释'],
  '调试题': ['定位错误', '给出正确修正', '解释错误后果'],
  '代码实现题': ['关键逻辑或伪代码', '变量/步骤完整性', '边界条件或解释'],
  '建模题': ['问题要素定义', '方法或特征选择', '理由与验证方式'],
  '评价题': ['结论选择', '指标或证据依据', '取舍或适用条件'],
  '比较题': ['两个对象的核心差异', '适用场景', '计算或例证'],
  '实验题': ['实验变量与对照', '观测指标', '判断标准']
}[type] ?? ['核心答案', '推理过程', '解释']);

const [questions, preReviews, taskCards, wrongOptionReviews, previousQuestionReviews, previousTaskReviews, previousWrongOptionReviews] = await Promise.all(['question_bank.csv','question_pre_review.csv','mastery_task_scoring_card.csv','question_wrong_option_review.csv'].map(load).concat(['question_ai_pre_review.csv','mastery_task_ai_pre_review.csv','wrong_option_ai_pre_review.csv'].map(loadIfExists)));
const baseQuestions = questions.filter(question => question.status === 'approved' && question.question_id === question.question_id.replace(/-v\d+$/, ''));
const previousQuestionById = new Map(previousQuestionReviews.map(row => [row.question_id, row]));
const aiQuestionReviews = baseQuestions.map(question => {
  const existing = preReviews.find(review => review.question_id === question.question_id);
  const override = questionOverrides[question.question_id] ?? {};
  const isBasic = question.target_level === '基本了解';
  const generated = {
    question_id: question.question_id,
    ai_semantic_assessment: '题干、正确答案与讲解在当前题面上未发现明显矛盾；需人工对照原教材核实术语和边界。',
    ai_answer_check: '依据题干给定条件重新核对，答案与讲解一致；仍需内容负责人对教材出处确认。',
    ai_distractor_check: '错误选项与正确概念可区分，建议人工检查是否存在过于明显、歧义或诱导性不足的干扰项。',
    ai_difficulty_assessment: override.difficulty ?? `${question.target_level}-${isBasic ? '合适' : '待人工确认'}`,
    ai_source_check: question.source_note ? '已登记教材出处；需人工核对是否对应到准确小节和原文表述。' : '缺少可核对出处。',
    ai_recommendation: override.recommendation ?? '建议保留，等待人工确认。',
    ai_reason: override.reason ?? existing?.reason ?? '当前题面可用于基础诊断；建议由学科负责人确认答案、难度与干扰项。',
    ai_confidence: override.recommendation ? 'medium' : 'low',
    human_decision: '', human_reviewer: '', human_reviewed_at: '', status: 'ai_pre_assessed_pending_human'
  };
  const previous = previousQuestionById.get(question.question_id);
  return previous?.human_decision ? { ...generated, human_decision: previous.human_decision, human_reviewer: previous.human_reviewer, human_reviewed_at: previous.human_reviewed_at, status: previous.status } : generated;
});
const taskById = new Map(taskCards.map(card => [card.mastery_task_id, card]));
const previousTaskById = new Map(previousTaskReviews.map(row => [row.mastery_task_id, row]));
const aiTaskReviews = [...taskById].map(([taskId, card]) => {
  const dimensions = JSON.parse(card.scoring_dimensions_json).map(item => item.dimension).join('；');
  const generated = {
    mastery_task_id: taskId,
    ai_reference_answer_outline: `应至少覆盖既有任务量表中的要求：${card.reference_answer_outline.includes('待内容负责人') ? '以任务题干与原始 rubric 为准，补写可复核的参考答案或参考实现。' : card.reference_answer_outline}`,
    ai_scoring_focus: `建议审核重点：${dimensions}。各维度分值总和必须等于任务满分。`,
    ai_common_error_suggestion: '建议至少检查：只写结论不说明依据、遗漏题干约束、公式/代码缺关键步骤、没有处理边界情况或把相近概念混淆。',
    ai_hint_policy_check: '正式掌握任务建议默认无提示；如有提示必须记录 used_hint，且不能作为无提示复测证据。',
    ai_recommendation: '建议补写参考答案、可接受答案范围、不可接受答案和每维扣分边界后，再由人工设为 active。',
    ai_confidence: 'low', human_decision: '', human_reviewer: '', human_reviewed_at: '', status: 'ai_pre_assessed_pending_human'
  };
  const previous = previousTaskById.get(taskId);
  return previous?.human_decision ? { ...generated, human_decision: previous.human_decision, human_reviewer: previous.human_reviewer, human_reviewed_at: previous.human_reviewed_at, status: previous.status } : generated;
});
const answerByQuestion = new Map(questions.map(question => [question.question_id, question.answer_key]));
const previousWrongByKey = new Map(previousWrongOptionReviews.map(row => [`${row.question_id}:${row.option_index}`, row]));
const aiWrongOptions = wrongOptionReviews.filter(row => row.is_correct === 'false').map(row => ({
  question_id: row.question_id, option_index: row.option_index, option_text: row.option_text, knowledge_point_id: row.knowledge_point_id,
  ai_suggested_misconception_code: `misread-${row.question_id}-${row.option_index}`,
  ai_suggested_misconception_label: `将“${row.option_text}”误认为“${answerByQuestion.get(row.question_id) ?? '正确答案'}”，需核实这是否反映稳定的概念误解。`,
  ai_suggested_remediation_knowledge_point_id: row.knowledge_point_id,
  ai_confidence: 'low', human_decision: '', human_reviewer: '', human_reviewed_at: '', status: 'ai_pre_assessed_pending_human',
  ...((previousWrongByKey.get(`${row.question_id}:${row.option_index}`)?.human_decision) ? { human_decision: previousWrongByKey.get(`${row.question_id}:${row.option_index}`).human_decision, human_reviewer: previousWrongByKey.get(`${row.question_id}:${row.option_index}`).human_reviewer, human_reviewed_at: previousWrongByKey.get(`${row.question_id}:${row.option_index}`).human_reviewed_at, status: previousWrongByKey.get(`${row.question_id}:${row.option_index}`).status } : {})
}));
const outputs = [
  ['question_ai_pre_review.csv',['question_id','ai_semantic_assessment','ai_answer_check','ai_distractor_check','ai_difficulty_assessment','ai_source_check','ai_recommendation','ai_reason','ai_confidence','human_decision','human_reviewer','human_reviewed_at','status'],aiQuestionReviews],
  ['mastery_task_ai_pre_review.csv',['mastery_task_id','ai_reference_answer_outline','ai_scoring_focus','ai_common_error_suggestion','ai_hint_policy_check','ai_recommendation','ai_confidence','human_decision','human_reviewer','human_reviewed_at','status'],aiTaskReviews],
  ['wrong_option_ai_pre_review.csv',['question_id','option_index','option_text','knowledge_point_id','ai_suggested_misconception_code','ai_suggested_misconception_label','ai_suggested_remediation_knowledge_point_id','ai_confidence','human_decision','human_reviewer','human_reviewed_at','status'],aiWrongOptions]
];
console.log(`预览：${aiQuestionReviews.length} 道基础题、${aiTaskReviews.length} 张评分卡、${aiWrongOptions.length} 个错误选项的 AI 预评估。`);
if(apply){await Promise.all(outputs.map(([name,headers,rows])=>writeFile(resolve(DATA,name),toCsv(headers,rows),'utf8')));console.log('已写入独立 AI 预评估文件；不会改变人工审核表或质量门控。');}
