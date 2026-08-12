# 后端数据库技术说明

本目录实现两条内容轨道：

1. 301 道有参考答案的 Microsoft Quiz，经过知识点和内容审核后用于正式诊断；
2. 122 条 Assignment、Notebook/Lab、代码及概念素材，按测试、Rubric 或人工审核方式评测。

## 安装

```text
migrations/001_content_learning.sql
→ migrations/002_assessment_and_practice.sql
→ migrations/003_content_governance.sql
→ migrations/004_runtime_hardening.sql
→ generated/curriculum_seed.sql
→ generated/knowledge_mapping_seed.sql
→ generated/practice_mapping_seed.sql
→ migrations/005_runtime_roles.sql（生产必需，DBA 执行）
→ migrations/006_localization_and_explanations.sql
→ generated/localization_seed.sql
→ migrations/007_localization_roles.sql（生产必需，DBA 执行）
→ migrations/008_algorithm_and_mastery.sql
→ migrations/009_algorithm_roles.sql（生产必需，DBA 执行）
```

`005/007/009` 创建五个 `NOLOGIN` 权限组：

- `app_student_api`：只能读取不含答案的发布视图；
- `app_scoring_service`：可以读取内部答案视图并写评分结果；
- `app_content_reviewer`：可以处理候选映射和审核记录，但不能直接发布；
- `app_content_publisher`：只能调用受控发布函数，不能直接更新题库状态。
- `app_learning_algorithm`：只能读取五个无答案算法视图，并调用受控掌握度写入函数。

## 核心模型

| 模块 | 表或视图 |
|---|---|
| 来源 | `source_repositories`、`source_documents` |
| 题目 | `learning_items`、`learning_item_versions`、`item_options` |
| 知识体系 | `books`、`abilities`、`chapters`、`knowledge_nodes`、`knowledge_edges` |
| 映射 | `item_knowledge_map_candidates`、`item_knowledge_maps` |
| 前置关系候选 | `knowledge_edge_candidates` |
| 前置关系审核发布 | `knowledge_edge_review_records`、`knowledge_edge_publication_batches` |
| 评测 | `evaluation_specs`、`evaluation_test_cases`、`evaluation_rubric_criteria` |
| 提交与幂等 | `assessment_assignments`、`task_submissions`、`api_idempotency_records` |
| 结果与统计 | `evaluation_results`、`assessment_evidence`、`item_quality_statistics` |
| 审核发布 | `question_review_records`、`content_review_batches`、`publication_batches` |
| 安全读取 | `student_quiz_bank_safe`、`student_practice_task_bank_safe`、内部评分视图 |
| 发布检查 | `content_review_queue`、`publication_readiness` |
| 多语言与解析 | `learning_item_localizations`、`item_option_localizations`、本地化审核/发布批次 |
| 多语言安全读取 | `student_quiz_localized_bank_safe`、`get_student_quiz_feedback(...)` |
| 掌握度 | `learner_mastery_current`、`learner_mastery_history`、`mastery_evidence_processing` |
| 算法安全读取 | 五个 `algorithm_*` 视图 |

## 状态转换

```text
learning_items: needs_review → published
evaluation_specs: draft → published
mapping candidates: pending → approved
formal maps: 不存在 → item_knowledge_maps
```

这四项必须由同一审核发布流程协调完成。不要只修改题目状态。

`publication_readiness.readiness_status` 可能返回：

- `BLOCKED_SOURCE`
- `BLOCKED_ANSWER`
- `BLOCKED_CORRECT_OPTION_COUNT`
- `BLOCKED_TARGET_MAPPING`
- `BLOCKED_REVIEW`
- `BLOCKED_EXACT_EVALUATION`
- `READY`

## 重新生成

```bash
python3 backend/scripts/import_curriculum.py \
  --repo ml=/path/to/ML-For-Beginners \
  --repo ai=/path/to/AI-For-Beginners \
  --commit ml=<ML_COMMIT_SHA> \
  --commit ai=<AI_COMMIT_SHA> \
  --output backend/generated/curriculum_items.jsonl \
  --report backend/generated/curriculum_report.json

python3 backend/scripts/emit_catalog_sql.py \
  --input backend/generated/curriculum_items.jsonl \
  --output backend/generated/curriculum_seed.sql

python3 backend/scripts/build_knowledge_mapping.py \
  --input backend/generated/curriculum_items.jsonl \
  --output-dir backend/generated

python3 backend/scripts/build_zh_localizations.py \
  --items backend/generated/curriculum_items.jsonl \
  --mappings backend/generated/quiz_knowledge_mapping_candidates.csv \
  --output-dir backend/generated

python3 backend/scripts/build_practice_mapping.py \
  --input backend/generated/curriculum_items.jsonl \
  --taxonomy backend/generated/knowledge_taxonomy.json \
  --output-dir backend/generated

python3 backend/scripts/audit_question_quality.py \
  --items backend/generated/curriculum_items.jsonl \
  --quiz-mappings backend/generated/quiz_knowledge_mapping_candidates.csv \
  --practice-mappings backend/generated/practice_knowledge_mapping_candidates.csv \
  --localizations backend/generated/quiz_localization_zh_review.csv \
  --output-dir backend/generated
```

映射生成器使用固定、可解释的课程结构：ML 的 Quiz 每 6 题对应一个主题组，AI 按 `lesson-N.json` 对应课程 Lesson。自动结果只进入候选表，不直接发布；相邻课程主题会生成 48 条待审核前置关系候选。
为避免丢失人工进度，生成器默认不覆盖已经存在的 `generated/quiz_review.csv`；只有显式使用 `--overwrite-review` 才会重置审核表。

## 审核和发布

审核人员只编辑 `generated/quiz_review.csv` 的审核列。先审计：

```bash
python3 backend/scripts/review_release.py audit \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_review.csv \
  --report backend/generated/publication_readiness_report.json
```

满足以下条件的行才进入发布包：

```text
mapping_review_status = approved
answer_review_status  = approved
source_review_status  = approved
publish_decision      = publish
reviewer_id           非空
```

生成 SQL：

```bash
python3 backend/scripts/review_release.py build-release \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_review.csv \
  --output backend/generated/quiz_release.sql \
  --batch-id publication-quiz-001 \
  --batch-name "Reviewed Quiz release" \
  --requested-by reviewer-team
```

工具不会自动批准任何题目；没有完整批准行时会失败退出。

中文审核人员编辑 `generated/quiz_localization_zh_review.csv`。题干/选项翻译和解析必须分别批准，再通过 `localization_release.py audit/build-release` 生成事务化发布 SQL。自动生成的解析为结构草稿，错误选项的具体辨析必须由教研补充。

前置关系审核人员编辑 `generated/knowledge_edge_candidates.csv`，批准行必须填写 `reviewer_id`。`prerequisite_release.py` 会先做环路检查，再生成只调用 `publish_knowledge_edge_batch(...)` 的事务 SQL；数据库会再次检查环路，失败时整批回滚。

## 答案隔离

学生 API 只读 `student_quiz_bank_safe`。该视图提供普通选项，但 SQL 定义中不包含 `answer_data` 或 `is_correct`。

学生事务必须先执行 `SET LOCAL app.current_user_id='<服务端验证的用户 ID>'`。RLS 会对 assignment、提交、结果和幂等记录再次执行用户隔离。

评分服务只通过 `internal_quiz_scoring_bank` 读取答案，并使用 `correct_option_key` 评分。应用层仍需使用独立数据库账号，并禁止把内部查询对象序列化给前端。

## 评分模式

| 类型 | `evaluation_mode` | 证据策略 |
|---|---|---|
| Quiz | `exact_answer` | `direct` |
| 代码 | `code_tests` | `strong` |
| Notebook | `notebook_tests` | `strong` |
| Project | `rubric` | `auxiliary` |
| 概念/反思 | `manual_review` | `none` |

算法输出必须追加写入 `evaluation_results`，记录 `evaluator_name`、`evaluator_version`、`confidence` 和 `reason_codes`。不要覆盖旧结果。

掌握度算法读取 `algorithm_evidence_feed` 和 `algorithm_learner_state`，只通过 `apply_mastery_update(...)` 写入。数据库会执行证据归属校验、防重复消费、`expectedStateVersion` 乐观锁、历史追加和当前状态更新。参考规则实现位于 `algorithms/mastery_rules.py`，完整协议见 `../interfaces/03-算法接入与掌握度协议.md`。

## 验证

```bash
python3 backend/tests/test_backend_contract.py
python3 backend/tests/test_generated_catalog.py
python3 backend/tests/test_content_governance.py
python3 backend/tests/test_localization.py
python3 backend/tests/test_practice_mapping.py
python3 backend/tests/test_question_quality.py
python3 backend/tests/test_prerequisite_release.py
python3 backend/tests/test_algorithm_security.py
python3 -m unittest backend.tests.test_mastery_rules -v
./backend/tests/run_postgres_integration.sh
```

静态测试还验证 301 套中文题干/选项/解析候选、122 条实践映射、质量审计、前置环路检测、算法答案隔离和规则掌握度更新。Docker 集成测试会在真实 PostgreSQL 16 中验证全部迁移、角色权限、RLS、未审核内容隔离、掌握度幂等/版本锁和循环前置关系整批回滚。HTTP 服务仍需由现有后端执行 API 端到端测试。
