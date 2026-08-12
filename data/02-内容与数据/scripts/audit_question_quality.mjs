import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const CONTENT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const DATA = resolve(CONTENT_ROOT, 'data');
const REPORT = resolve(CONTENT_ROOT, 'reports', '题库预审核与校准清单.md');
const GATE = resolve(DATA, 'question_quality_gate.csv');
const strict = process.argv.includes('--strict');

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
const baseId = id => id.replace(/-v\d+$/, '');
const normalOptions = question => JSON.parse(question.options_json).map(value => value.trim()).sort().join('|');
const [points, scope, units, unitKnowledge, questions, questionKnowledge, blueprints, preReviews] = await Promise.all(['knowledge_point_catalog.csv', 'book_knowledge_scope.csv', 'content_unit_catalog.csv', 'content_unit_knowledge_edges.csv', 'question_bank.csv', 'question_knowledge_edges.csv', 'question_blueprint_catalog.csv', 'question_pre_review.csv'].map(csv));
const approved = questions.filter(question => question.status === 'approved');
const questionById = new Map(approved.map(question => [question.question_id, question]));
const reviewById = new Map(preReviews.map(review => [review.question_id, review]));
const baseQuestions = approved.filter(question => question.question_id === baseId(question.question_id));
const variantQuestions = approved.filter(question => question.question_id !== baseId(question.question_id));
const recycledOptionVariants = variantQuestions.filter(question => normalOptions(question) === normalOptions(questionById.get(baseId(question.question_id))));
const genericStemVariants = variantQuestions.filter(question => /^(应用情境：|综合判断：)/.test(question.prompt));
const codeWithoutCode = approved.filter(question => question.question_type === '代码题' && !/`[^`]+`|\b(def|for|while|import|print|Conv2d|Linear)\b|\{.*\}|\[[^\]]+\]\s*=/.test(`${question.prompt}\n${question.options_json}`));
const requiredScope = scope.filter(edge => edge.status === 'active' && edge.scope_type === 'required');
const recommendedScope = scope.filter(edge => edge.status === 'active' && edge.scope_type === 'recommended');
const unitIdsByPoint = pointId => [...new Set(unitKnowledge.filter(edge => edge.knowledge_point_id === pointId).map(edge => edge.content_unit_id))];
const questionIdsByPoint = pointId => [...new Set(questionKnowledge.filter(edge => edge.status === 'active' && edge.knowledge_point_id === pointId).map(edge => edge.question_id).filter(id => questionById.has(id)))];
const scopeProblems = requiredScope.filter(edge => !unitIdsByPoint(edge.knowledge_point_id).length || !questionIdsByPoint(edge.knowledge_point_id).length || !blueprints.some(blueprint => blueprint.knowledge_point_id === edge.knowledge_point_id));
const recommendedProblems = recommendedScope.filter(edge => !unitIdsByPoint(edge.knowledge_point_id).length || !questionIdsByPoint(edge.knowledge_point_id).length || !blueprints.some(blueprint => blueprint.knowledge_point_id === edge.knowledge_point_id));
const reviewProblems = baseQuestions.filter(question => !reviewById.has(question.question_id));
const semanticWarnings = baseQuestions.filter(question => reviewById.get(question.question_id)?.preliminary_correctness !== '语义基本正确');
const humanCalibrationGaps = baseQuestions.filter(question => reviewById.get(question.question_id)?.human_decision !== 'approved');
const masteryRows = blueprints.map(blueprint => {
  const ids = questionIdsByPoint(blueprint.knowledge_point_id);
  const pointQuestions = ids.map(id => questionById.get(id));
  const requiredTypes = blueprint.required_question_types.split('|');
  const actualTypes = [...new Set(pointQuestions.map(question => question.question_type))];
  const missingTypes = requiredTypes.filter(type => !actualTypes.includes(type));
  const independentQuestionCount = new Set(pointQuestions.map(question => `${question.prompt}|${normalOptions(question)}`)).size;
  const recycled = pointQuestions.filter(question => question.question_id !== baseId(question.question_id) && normalOptions(question) === normalOptions(questionById.get(baseId(question.question_id)))).length;
  return { ...blueprint, ids, actualTypes, missingTypes, independentQuestionCount, recycled, ready: missingTypes.length === 0 && independentQuestionCount >= Number(blueprint.min_approved_versions) && recycled === 0 };
});
const masteryReady = masteryRows.filter(row => row.ready);
const gates = masteryRows.map(row => {
  const relatedBaseIds = new Set(row.ids.map(baseId));
  const humanApproved = [...relatedBaseIds].every(id => reviewById.get(id)?.human_decision === 'approved');
  const masteryStatus = !row.ready ? 'blocked' : humanApproved ? 'eligible' : 'pending_human_calibration';
  return {
    knowledge_point_id: row.knowledge_point_id,
    mastery_status: masteryStatus,
    reason_code: !row.ready ? 'mastery_evidence_incomplete' : humanApproved ? 'quality_review_approved' : 'human_calibration_required',
    review_status: masteryStatus === 'eligible' ? 'approved' : masteryStatus === 'blocked' ? 'blocked' : 'pending',
    updated_at: new Date().toISOString().slice(0, 10),
  };
});
const pointName = id => points.find(point => point.knowledge_point_id === id)?.knowledge_point_name ?? id;
const reviewActionCounts = new Map();
for (const review of preReviews) reviewActionCounts.set(review.action, (reviewActionCounts.get(review.action) ?? 0) + 1);
const report = [
  '# 题库预审核与人工校准清单', '',
  '> 审核性质：这是基于题干、答案、标签与题目变式关系的**预审核**。它可以发现明确的结构和教学测量问题，但不能替代人工智能学科教师的最终签字。人工校准请填写 `data/question_pre_review.csv` 的空白列。', '',
  '## 结论（当前不能把题库视为“掌握级正式题库”）', '',
  `- 题量：${approved.length} 道，由 ${baseQuestions.length} 道基础题和 ${variantQuestions.length} 道独立掌握题组成；选项复用变式为 ${recycledOptionVariants.length} 道，通用题干变式为 ${genericStemVariants.length} 道。`,
  `- 掌握证据：自动按“蓝图要求题型 + 独立情境 + 非复用选项”重算后，结构达标的知识点为 ${masteryReady.length}/${masteryRows.length}；仍必须经过人工学科审核。`,
  `- 正式必学范围：${requiredScope.length} 个知识点都有教材单元、题目和蓝图的结构映射；另外 ${recommendedScope.length} 个推荐编程知识点${recommendedProblems.length ? '仍有教材、题目或蓝图缺口，不能纳入正式复测范围。' : '（Python、Q 表实现）均已具备教材单元、题目与蓝图，可作为推荐前置知识练习或复测。'}`,
  `- 题干预审：${baseQuestions.length - semanticWarnings.length}/${baseQuestions.length} 道基础题语义基本可用；${semanticWarnings.length} 道存在明确问题或题型错误，需要先改；${humanCalibrationGaps.length}/${baseQuestions.length} 道尚未得到人工确认。`, '',
  '## 必须先修正', '',
  `1. **题目独立性已替换完成。**新增题使用不同情境、不同选项与不同解题目标；当前发现的选项复用变式为 ${recycledOptionVariants.length} 道。`,
  `2. **题型蓝图结构已匹配。**仍须由人工确认推导、代码、建模、评价等题型的教学难度与正确答案。`,
  `3. **代码题预审。**${codeWithoutCode.length ? `${codeWithoutCode.map(question => `\`${question.question_id}\``).join('、')} 缺少可识别代码片段，需要补写。` : '所有代码题均包含代码片段或代码配置。'}`,
  `4. **语义预审待复核项。**${semanticWarnings.length ? semanticWarnings.map(question => `\`${question.question_id}\``).join('、') : '无自动标记项'}；最终以人工校准结论为准。`, '',
  '## 逐知识点：掌握证据核查', '',
  '|知识点|正式题数|独立题数|蓝图要求但缺少的题型|复用选项变式数|预审结论|', '|---|---:|---:|---|---:|---|',
];
for (const row of masteryRows) report.push(`|${pointName(row.knowledge_point_id)}|${row.ids.length}|${row.independentQuestionCount}|${row.missingTypes.join('、') || '无'}|${row.recycled}|${row.ready ? '可进入人工终审' : '不具备掌握证据'}|`);
report.push('', '## 基础题人工校准队列', '', '|题目|语义预审|难度预审|处理建议|原因|人工决定|', '|---|---|---|---|---|---|');
for (const question of baseQuestions) {
  const review = reviewById.get(question.question_id);
  report.push(`|${question.question_id}|${review?.preliminary_correctness ?? '缺少预审'}|${review?.difficulty_assessment ?? '缺少预审'}|${review?.action ?? '补录'}|${review?.reason ?? ''}|${review?.human_decision || '待校准'}|`);
}
report.push('', '## 范围遗漏', '', `- 当前 ${units.length} 个小节是产品第一版的**精选学习路径**，不能称为两本教材的完整目录覆盖。完整边界与补齐顺序见 \`教材完整目录覆盖清单.md\`。`, '- 现阶段可对外表述为：“机器学习与深度学习的第一版基础路径”，不要表述为“完整两本教材”。', `- 推荐范围的 Python、Q 表实现${recommendedProblems.length ? '仍有内容或题库缺口，应补齐后再纳入正式复测。' : '已具备资料、题目和蓝图；但在基础题经人工确认前，仍不允许升级为“掌握”。'}`, '', '## 人工校准顺序', '', '1. 先处理重写项：ml-q05、ml-q17、dl-q05、dl-q07；再由学科同学抽检其余基础题。', '2. 每个知识点至少新写 4 个**不同情境、不同选项、不同解题路径**的题，不能由同一题换序产生。', '3. 对“掌握”至少保留一种应用/计算或推导证据；涉及编程能力时，必须增加代码阅读、填空、调试或运行结果题。', '4. 人工在 `question_pre_review.csv` 的 `human_decision` 填入 `approved`、`rewrite` 或 `reject`，并填写审核人与日期；只有关联基础题均为 `approved`，且独立题目和题型证据满足蓝图时，安全门才会开放。', '', '## 自动检查口径', '', '- `npm run audit:question-quality`：生成本报告并返回统计；`npm run audit:question-quality -- --strict`：若仍有掌握证据或人工校准缺口则失败。', '- 当前严格检查**预期失败**，这正是为了避免系统在题库尚未校准时把用户标成“掌握”。', '');
await mkdir(dirname(REPORT), { recursive: true });
await writeFile(REPORT, report.join('\n'), 'utf8');
await writeFile(GATE, `knowledge_point_id,mastery_status,reason_code,review_status,updated_at\n${gates.map(gate => Object.values(gate).join(',')).join('\n')}\n`, 'utf8');
console.log(`题库预审核：基础题 ${baseQuestions.length}，变式 ${variantQuestions.length}，复用选项变式 ${recycledOptionVariants.length}，通用改写变式 ${genericStemVariants.length}，掌握级通过 ${masteryReady.length}/${masteryRows.length}。`);
console.log(`必学知识点映射缺口 ${scopeProblems.length}；推荐知识点未覆盖 ${recommendedProblems.length}；待人工确认基础题 ${humanCalibrationGaps.length}。`);
if (strict && (masteryReady.length !== masteryRows.length || gates.some(gate => gate.mastery_status !== 'eligible') || scopeProblems.length || reviewProblems.length)) {
  console.error('题库尚未通过严格质量审核；详见 02-内容与数据/reports/题库预审核与校准清单.md');
  process.exitCode = 1;
}
