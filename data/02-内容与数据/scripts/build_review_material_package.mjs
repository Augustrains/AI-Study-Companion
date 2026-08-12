#!/usr/bin/env node
/**
 * Build a compact, human-facing review package from the authoritative content
 * module. The package is a read/review copy, never an input for the runtime.
 */
import { cp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const contentRoot = join(scriptDir, '..');
const projectRoot = join(contentRoot, '..');
const outputRoot = join(projectRoot, '08-资料与题库审核包');

const copy = async (sourceRelative, targetRelative = sourceRelative) => {
  const source = join(contentRoot, sourceRelative);
  const target = join(outputRoot, targetRelative);
  await mkdir(dirname(target), { recursive: true });
  await cp(source, target, { recursive: true, force: true });
};

const copyTextbook = async (sourceRelative, targetRelative) => {
  const source = join(contentRoot, sourceRelative);
  const target = join(outputRoot, targetRelative);
  await mkdir(dirname(target), { recursive: true });
  await cp(source, target, {
    recursive: true,
    force: true,
    // The source repository's Git history is not learning material and would
    // make this local review package hundreds of MB larger.
    filter: (path) => !path.split('/').includes('.git'),
  });
};

const csvGroups = {
  '01-书籍与正式学习资料/目录与来源': [
    'book_catalog.csv', 'source_catalog.csv', 'content_unit_catalog.csv',
    'chapter_catalog.csv', 'section_catalog.csv', 'content_unit_knowledge_edges.csv',
    'book_knowledge_scope.csv',
  ],
  '02-知识地图': [
    'ability_catalog.csv', 'knowledge_point_catalog.csv', 'topic_catalog.csv',
    'ability_knowledge_edges.csv', 'knowledge_prerequisite_edges.csv',
    'chapter_knowledge_edges.csv', 'section_ability_edges.csv',
  ],
  '03-正式题库': [
    'question_bank.csv', 'question_blueprint_catalog.csv', 'question_delivery_profile.csv',
    'question_knowledge_edges.csv', 'question_ability_edges.csv', 'question_section_edges.csv',
    'question_source_edges.csv', 'mastery_task_catalog.csv', 'mastery_task_knowledge_edges.csv', 'mastery_task_auto_grading_spec.csv',
  ],
  '04-人工审核与AI预评估': [
    'question_pre_review.csv', 'question_quality_gate.csv', 'mastery_task_scoring_card.csv',
    'question_wrong_option_review.csv', 'question_ai_pre_review.csv',
    'mastery_task_ai_pre_review.csv', 'wrong_option_ai_pre_review.csv',
  ],
  '05-覆盖报告与待补齐': [
    'question_pool_expansion_backlog.csv', 'rule_config.yaml',
  ],
};

for (const [folder, files] of Object.entries(csvGroups)) {
  for (const file of files) await copy(`data/${file}`, `${folder}/${file}`);
}

await copy('data/README.md', '00-阅读前请看/数据结构说明.md');
await copy('README.md', '00-阅读前请看/内容模块说明.md');
await copy('原始资料/README.md', '01-书籍与正式学习资料/原始教材获取说明.md');
await copy('资料库/正式', '01-书籍与正式学习资料/正式阅读资料');
await copy('资料库/正式/00-审核记录.md', '04-人工审核与AI预评估/教材审核记录.md');
await copyTextbook(
  '原始资料/ocademy-machine-learning',
  '01-书籍与正式学习资料/原始教材/机器学习-Open-Machine-Learning-Book',
);
await copyTextbook(
  '原始资料/d2l-zh',
  '01-书籍与正式学习资料/原始教材/深度学习-动手学深度学习中文版',
);

for (const report of [
  '教材完整目录覆盖清单.md', '两本教材-章节题库覆盖报告.md',
  '题库运营与人工确认导览.md', '题库预审核与校准清单.md',
  '非选择题自动判分规则.md',
]) {
  await copy(`reports/${report}`, `05-覆盖报告与待补齐/${report}`);
}

await copy('../06-质量验证/题库试用与校正指标.md', '05-覆盖报告与待补齐/题库试用与校正指标.md');

const summary = `# 自适应学习系统：资料与题库审核包

> 生成时间：${new Date().toISOString().slice(0, 10)}  
> 用途：给内容负责人、题库审核人和项目成员集中查看、审核与补充资料。  
> 重要：本目录是从 \`02-内容与数据\` 同步出的**查看/审核副本**；唯一正式来源仍是 \`02-内容与数据\`，审核结论和新增题目须回写正式来源。

## 当前已有内容

- **两本开放教材来源**：机器学习（Open Machine Learning Book，CC BY 4.0）与深度学习（《动手学深度学习》中文版，Apache-2.0）。
- **27 个正式阅读单元**：机器学习 14 个、深度学习 13 个；每个单元均带来源、章节与知识点标签。
- **学习地图**：35 个必学知识点，另有 Python 编程和 Q 表实现两个推荐前置点；能力、书籍、章节、知识点和前置关系均以多对多表保存。
- **正式题库**：150 道客观题（37 道基础题、113 道独立版本），37 个知识点对应的结构化自动判分应用任务，以及诊断/练习/复测投放规则。
- **审核工作表**：基础题预审核、自动答案键的离线确认、错误选项错因、质量门控和 AI 预评估建议。

## 从哪里开始看

1. **先看书籍与资料**：\`01-书籍与正式学习资料/\`。\`正式阅读资料/\` 是可给学习者使用的 27 个单元；\`原始教材/\` 保留了两本开放教材的正文、图片、代码和许可证（不含 Git 历史）。
2. **再看学习地图**：\`02-知识地图/\`。先看 \`knowledge_point_catalog.csv\`、\`ability_catalog.csv\`、\`knowledge_prerequisite_edges.csv\`。
3. **审核/补充题目**：\`03-正式题库/\` 是正式题与任务；\`04-人工审核与AI预评估/\` 是待人工确认表。
4. **看缺口与覆盖**：\`05-覆盖报告与待补齐/\` 说明题库覆盖边界和接下来需要补的题。

## 资料状态与边界

| 类别 | 当前可用 | 仍需人工完成 |
|---|---:|---|
| 正式阅读资料 | 27 个单元 | 确认内容准确性、资料质量与标签 |
| 客观题 | 150 道 | 审核 37 道基础题的学科正确性 |
| 应用任务 | 37 个 | 已有结构化字段、答案键与自动评分规则；仍待离线学科核对 |
| 错误选项解释 | 300 个错误选项 | 逐项确认真实错因标签 |
| 题池覆盖 | 35 个必学知识点 | 扩充独立题目，建议每个知识点至少 7 道 |

AI 预评估只用于帮助人工初审，所有 \`ai_pre_assessed_pending_human\` 状态均不是正式审核结论，也不能触发“掌握”自动升级。

## 文件夹说明

| 文件夹 | 放什么 | 谁主要使用 |
|---|---|---|
| \`00-阅读前请看\` | 内容结构与正式来源说明 | 全体成员 |
| \`01-书籍与正式学习资料\` | 书籍来源、目录、正式 Markdown 阅读单元、两本原始开放教材 | 内容/资料负责人 |
| \`02-知识地图\` | 能力、知识点、前置关系、章节关联 | 内容负责人、算法负责人 |
| \`03-正式题库\` | 客观题、题目蓝图、投放规则、自动判分应用任务 | 题库负责人、研发 |
| \`04-人工审核与AI预评估\` | 题目/答案键的离线审核入口与 AI 初审建议 | 学科审核人 |
| \`05-覆盖报告与待补齐\` | 覆盖报告、补题待办、试用指标 | 项目统筹、题库负责人 |

## 正确的协作方式

请在这里阅读和提出意见；确认后，将修改同步回 \`02-内容与数据\` 的对应文件。不要把本资料包当作运行服务的数据来源；\`原始教材/\` 仅供本机查看，已被 Git 忽略，不应提交到项目仓库。

可重新生成本资料包：在项目根目录执行 \`npm run build:review-material-package\`。
`;

await mkdir(outputRoot, { recursive: true });
await writeFile(join(outputRoot, 'README.md'), summary, 'utf8');

const manifest = {
  generated_at: new Date().toISOString(),
  authoritative_source: relative(outputRoot, contentRoot),
  purpose: 'human_review_copy_only',
  included: Object.values(csvGroups).flat().length + 8,
  excluded: ['历史快照', '脚本', '原始教材的 Git 历史目录'],
};
await writeFile(join(outputRoot, '资料包清单.json'), `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
console.log(`资料与题库审核包已同步：${outputRoot}`);
