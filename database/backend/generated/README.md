# 生成的题库文件

本目录由导入脚本生成，不要手工编辑。

- `curriculum_items.jsonl`：来自两个 Microsoft GitHub 仓库的 423 条标准化内容。
- `curriculum_report.json`：数量、类型、仓库 Commit 与错误统计。
- `curriculum_seed.sql`：PostgreSQL 内容、草稿评测规格和任务模板种子数据。
- `knowledge_taxonomy.json`：从两套课程原生 Quiz 分组生成的 50 个候选知识点。
- `knowledge_edge_candidates.csv`：按课程顺序生成的 48 条前置关系候选，必须经教研审核。
- `quiz_knowledge_mapping_candidates.csv`：301 道 Quiz 的候选知识点映射，不代表已审核。
- `practice_knowledge_mapping_candidates.csv`：122 条实践素材的候选知识点映射，不代表已审核。
- `quiz_review.csv`：教研审核工作表；只有三项审核均通过并选择发布，发布工具才接受。
- `knowledge_mapping_seed.sql`：知识结构、301 条题目映射候选和 48 条前置关系候选的种子 SQL。
- `practice_mapping_seed.sql`：122 条实践素材映射候选的种子 SQL。
- `practice_mapping_report.json`：实践素材映射覆盖率和低置信度数量。
- `publication_readiness_report.json`：当前审核数量、可发布数量和错误报告。
- `quiz_localization_zh_review.csv`：301 道 Quiz 的中文题干、选项、结构化解析候选及审核列。
- `localization_seed.sql`：中文候选种子数据，初始全部为 `needs_review`。
- `localization_report.json`：中文内容完整度、审核状态和可发布数量。
- `localization_readiness_report.json`：中文审核表审计结果、阻塞状态和可发布数量。
- `question_quality_review.csv`：301 道 Quiz 的结构质量复核清单。
- `question_quality_report.json`：答案一致性、重复项、中文完整度和警告汇总。
- `prerequisite_readiness_report.json`：48 条前置关系的决策数量和环路审计。

其中 301 道带参考答案的 Quiz 是正式题库候选；其余 122 条 Assignment、Notebook/Lab、代码和概念素材属于实践任务。423 条内容现在都各有一条知识点映射候选，但正式映射仍需人工批准。全部内容初始为 `needs_review`，评测规格初始为 `draft`，映射候选初始为 `pending`。只编辑明确标为审核工作表的 CSV；重新生成脚本默认保留已有 Quiz 审核表。审核发布规则见 `../README.md`。
