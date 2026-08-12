# 内容数据：多对多关系模型

本目录中的 CSV 是人工维护、技术导入的第一版内容资产。

第一版已提供《机器学习》与《深度学习》的基础学习路径：27 个正式教材单元、35 个必学知识点与 150 道已登记客观题（37 道基础题、113 道独立掌握题）。Python 编程基础与 Q 表实现已作为推荐前置内容进入资料范围，各有 4 道正式题和题目蓝图；其基础题仍须经过内容负责人的人工预审核。`question_bank.csv` 的题干、选项、正确选项、讲解、评分规则和来源由开发者维护；服务只会选择 `status=approved` 的题。题目能否作为“掌握”升级证据，还必须通过 `question_quality_gate.csv` 的人工校准门控。

“掌握”还要求应用证据：`mastery_task_catalog.csv` 为每个必学知识点登记短答、调试、实现或建模任务，`mastery_task_auto_grading_spec.csv` 已为全部 37 道任务配置结构化提交字段、确定性答案键和分值。正式运行时只按答案键、数值容差、结构化字段规则或代码测试自动判分；人工只在上线前核对这些规则，不参与学习者提交后的实时判分。自动任务得分仍受 `question_quality_gate.csv` 门控，所有 `content_review_status=ai_pre_assessed_pending_human` 的规格不得解除“掌握”发布门控。两本书的完整目录边界见 `../reports/教材完整目录覆盖清单.md`，当前基础路径不得表述为完整教材。

题库中的 `topic_id` 只允许使用 `topic_catalog.csv` 里的当前 active 专题；旧演示专题已迁移，原值保留在 `legacy_topic_id` 供审计，不参与学习路径筛选。`target_level=掌握` 仅表示该题是掌握证据链的一个客观版本；单题正确不会升级状态，仍需多题型、无提示复测、自动判分应用任务和质量门控共同满足。

## 不再使用单表映射

`能力 → 知识点`、`书籍 → 知识点`、`知识点 → 前置知识点` 都是多对多关系，必须通过边表表达，不能再使用一张 `ability_knowledge_map.csv` 同时承载所有关系。

## 导入顺序

```text
book_catalog.csv
→ topic_catalog.csv
→ source_catalog.csv
→ content_unit_catalog.csv
→ content_unit_knowledge_edges.csv
→ chapter_catalog.csv
→ section_catalog.csv
→ chapter_knowledge_edges.csv
→ section_ability_edges.csv
→ ability_catalog.csv
→ knowledge_point_catalog.csv
→ book_knowledge_scope.csv
→ ability_knowledge_edges.csv
→ knowledge_prerequisite_edges.csv
→ question_bank.csv
→ question_knowledge_edges.csv
→ question_ability_edges.csv
→ question_source_edges.csv
→ question_section_edges.csv
→ question_blueprint_catalog.csv
→ question_delivery_profile.csv
→ question_pool_expansion_backlog.csv
→ question_wrong_option_review.csv
→ mastery_task_catalog.csv
→ mastery_task_auto_grading_spec.csv
→ mastery_task_scoring_card.csv
→ question_ai_pre_review.csv
→ mastery_task_ai_pre_review.csv
→ wrong_option_ai_pre_review.csv
→ rule_config.yaml
```

## 多对多关系

```text
一本书
→ 多个章节
→ 多个教材小节（`content_unit`）
↔ 多个知识点

一个知识点
↔ 多项能力

一道题
↔ 多个知识点与能力
→ 一个可追溯的教材小节
```

算法只读取以上新表；任何旧格式数据都必须先迁移。

## 题目字段补充

`question_bank.csv` 额外包含 `prompt`、`options_json`、`correct_option` 和 `explanation`。诊断时不逐题展示答案或讲解；题目提交后才生成 AI 判断。

题目更新后，应从项目根目录运行 `npm test`，验证选题、状态和服务闭环。

## 正式题的出处与补题计划

- `question_source_edges.csv`：每道正式题必须连接到一个已登记的教材单元和可定位的小节；这是题干、答案和讲解的可追溯依据，不代表把题目答案自动从教材中生成。
- `question_blueprint_catalog.csv`：按知识点列出“掌握”所需的题型、独立版本数与当前缺口。现有“版本数”只说明结构登记，不证明题目独立；后续补题仍必须同步更新题库和边表。
- `question_pre_review.csv`：逐基础题的预审核与人工校准入口；`question_quality_gate.csv`：每个知识点能否被用于自动升级“掌握”的安全门控。运行 `npm run audit:question-quality` 可更新报告和门控。
- `question_delivery_profile.csv`：每道正式题的诊断、练习、复测用途、曝光次数、建议用时和认知层级；服务用它避免一直重复同一道练习题。
- `question_pool_expansion_backlog.csv`：从当前最低 4 题扩充至建议 7 题的内容待办；它不自动生成或批准题目。
- `question_wrong_option_review.csv`：保存每个选项的错因审核模板。只有内容负责人确认并设为 `active` 的错因标签，才可以用于给学习者解释薄弱点。
- `mastery_task_auto_grading_spec.csv`：37 道应用任务的正式自动判分规格。服务端只向学习者下发 `response_schema_json`，在服务端保存 `answer_key_json`；每个正确/错误字段均可复现判分。`content_review_status` 用于内容人工确认，不会改变实时评分路径。
- `mastery_task_scoring_card.csv`：历史评分卡工作表，仅可用于内容设计与抽检；它不承担学习者提交后的实时评分。自动判分边界见 `../reports/非选择题自动判分规则.md`。
- `question_ai_pre_review.csv`、`mastery_task_ai_pre_review.csv`、`wrong_option_ai_pre_review.csv`：AI 对基础题、评分卡和错误选项的**独立建议表**。它们只为人工节省初审时间，状态固定为 `ai_pre_assessed_pending_human`，不改变 `question_pre_review.csv`、评分卡、错因标签或任何掌握门控。

完整协作顺序见 `../reports/题库运营与人工确认导览.md`。

## 教材来源与章节内容

- `source_catalog.csv`：每本书的原始来源、许可证、固定版本、下载日期和可用范围；没有来源记录的教材不得导入。
- `content_unit_catalog.csv`：可阅读的章节/小节单元；必须标出来源相对路径、网页链接、固定版本、预计时长、清洗状态与审核状态。
- `content_unit_knowledge_edges.csv`：章节单元与知识点的多对多关系。
- `chapter_catalog.csv`：书籍下的章节标签；它不替换来源教材的原始目录，而是当前产品可学习路径的一级标签。
- `section_catalog.csv`：章节下的二级小节标签，与 `content_unit_id` 一一对应，并保存原始资料定位链接。
- `chapter_knowledge_edges.csv`、`section_ability_edges.csv`：从已维护的“教材单元—知识点”和“能力—知识点”关系生成，供算法按章节或能力选题。
- `question_section_edges.csv`：每道正式题的章节/小节标签。它由题目的教材出处生成，因此不与 `question_source_edges.csv` 重复维护。

运行 `npm run build:hierarchy-tags` 会重新生成以上五张标签表，但**不会改写**原始教材、题库、知识点或题目出处表；运行 `npm run report:coverage` 可查看每章和每节的题目覆盖情况。

`cleaning_status` 仅说明文本抽取是否完成；只有内容负责人确认准确性、版权标注和知识点标签后，`review_status` 才能变为 `approved`。运行版只能把 `approved` 单元作为正式学习资料和 RAG 语料。
