# 自适应伴学 Agent 数据库交付包

这是一个可交给后端、算法和教研团队共同接入的 PostgreSQL 数据库包。它只包含以下两个 Microsoft GitHub 项目的内容：

- `microsoft/ML-For-Beginners`
- `microsoft/AI-For-Beginners`

不包含本地 `question_bank.csv`、旧题库、演示题或其他来源记录。

## 0. 技术交接结论

可以把整个 `database` 文件夹直接交给技术同事。

技术同事拿到后可以立即完成：

- 在空 PostgreSQL 14+ 数据库执行迁移和种子数据；
- 验证 423 条学习内容、423 条知识点映射候选、50 个知识点和中文候选数据；
- 按 OpenAPI 契约实现题目、提交、评分、掌握度、审核和发布 HTTP 接口；
- 通过五个无答案算法视图接入选题或掌握度算法；
- 直接使用规则版掌握度更新器，或在保持写入协议不变的情况下替换模型；
- 在测试环境验证答案隔离、RLS、幂等、原子发布、掌握度历史和前置关系环路回滚。

但“直接交付”不等于“可以不审核就上线”：

- 当前没有可运行的 HTTP 服务代码，`interfaces/openapi-question-bank.yaml` 是接口契约；
- 当前 301 道 Quiz 均未人工发布，因此学生安全视图初始为空；
- 301 道 Quiz 和 122 条实践素材均有知识点候选映射，正式映射为 0；
- 48 条前置关系是课程顺序候选，不能直接作为真实前置知识；
- 掌握度数据库闭环、参考更新器和接口契约已经实现，但尚需用真实学习数据校准参数；
- 122 条实践素材尚未补齐可生产使用的测试用例或 Rubric。

因此，本文件夹的准确定位是：

> 可直接部署和联调的题库与学习状态数据库交付包；正式生产上线仍需要内容审核、现有 HTTP 服务接线、实践评测配置和真实数据校准。

### 接收方只需要这个文件夹吗

首次部署需要，且只需要这个文件夹。所有迁移、种子、审核表、测试和接口文档均已包含。只有在需要从 GitHub 重新抓取或重新生成原始题库时，才需要另外准备两个上游仓库的本地副本。

### 接收方环境要求

| 依赖 | 用途 | 是否必需 |
|---|---|---|
| PostgreSQL 14+ | 正式数据库 | 必需 |
| `psql` | 执行迁移和发布 SQL | 必需 |
| Python 3.9+ | 审计、生成和静态测试；脚本只使用标准库 | 建议 |
| Docker | 运行一次性 PostgreSQL 16 集成测试 | 建议 |
| 具备 `CREATEROLE` 的 DBA 账号 | 安装最小权限角色和 RLS 授权 | 生产必需 |

接收方应先阅读本 README，再阅读 `backend/README.md`、`interfaces/02-题库审核与评测接口.md` 和 `interfaces/03-算法接入与掌握度协议.md`。

## 1. 当前结论

数据库结构、种子数据、答案隔离、知识点候选映射、审核发布工具和接口契约均已准备好，可以进入技术接入和教研审核阶段。

它还不能在无人审核的情况下直接对学生发布：301 道 Quiz 当前全部保持 `needs_review`，映射候选保持 `pending`，发布决定保持 `hold`。这是安全设计，不是导入失败。

| 项目 | 数量 | 当前状态 |
|---|---:|---|
| Quiz | 301 | 选项、参考答案、唯一正确项完整；待人工审核发布 |
| 实践素材 | 122 | 已入库；测试用例或 Rubric 仍需逐项完善 |
| 课程知识点候选 | 50 | 已按上游 Quiz 分组生成；待产品/教研确认 |
| Quiz—知识点候选映射 | 301 | 每道 Quiz 一条；待人工确认 |
| 实践素材—知识点候选映射 | 122 | 每条素材一条；待人工确认 |
| 知识点前置关系候选 | 48 | 按两个课程原生顺序生成；待教研确认 |
| 中文题干与选项候选 | 301 套 | 已生成；机器翻译，待人工审核 |
| 中文答案解析候选 | 301 套 | 已生成结构化草稿；待教研补充具体辨析并审核 |
| 可立即发布 Quiz | 0 | 未经人工审核时发布工具会拒绝生成发布包 |

固定来源版本：

| 来源 | Commit | Quiz | 实践素材 | 合计 |
|---|---|---:|---:|---:|
| ML-For-Beginners | `d0d0ea2b2d22cddca31f9c6d108df7daa87a1b46` | 156 | 47 | 203 |
| AI-For-Beginners | `33e781bf7bfb9b39fd27c4e4a3e592669b52cb4b` | 145 | 75 | 220 |
| 合计 |  | **301** | **122** | **423** |

## 2. 已经完成的工作

### 数据与来源

- 只保留两个指定 GitHub 项目的 423 条内容；
- 301 道 Quiz 全部有题干、选项、参考答案和唯一正确项；
- 每条内容保留仓库、固定 Commit、文件路径、来源 URL 和内容哈希；
- 两个固定 Commit 的 `LICENSE` 均已核对为 MIT，并写入 `source_repositories.license_name`；
- 题目版本不可变，便于复现旧作答和旧评分。

### 答案隔离

- `student_quiz_bank_safe`：学生端安全视图，不含 `answer_data` 和 `is_correct`；
- `published_quiz_bank`：兼容旧名称，但现在也是学生安全视图；
- `internal_quiz_scoring_bank`：只给可信评分服务，包含答案和正确项；
- `004_runtime_hardening.sql`：提供安全实践视图、assignment、幂等、RLS 所需表、严格发布条件和受控发布函数；
- `005/007/009`：提供学生、评分、内容审核、内容发布和学习算法五类最小权限角色。

前端和学生服务不得查询 `learning_item_versions`、`item_options`、隐藏测试或内部评分视图。

### 知识点映射

- 根据 ML 的 26 个 Quiz 主题组和 AI 的 24 个课程 Lesson，生成 50 个课程原生知识点候选；
- 为 301 道 Quiz 各生成一条高置信度候选映射；
- 为 122 条实践素材按课程文件路径各生成一条可解释候选映射；
- 候选保存在 `item_knowledge_map_candidates`，不会自动写入正式的 `item_knowledge_maps`；
- 只有人工批准后，发布工具才会把候选升级为正式映射。
- 已生成 48 条相邻课程主题的前置关系候选，但不会自动写入正式 `knowledge_edges`。
- `prerequisite_release.py` 提供人工决策校验、环路检测和受控原子发布；数据库会二次检测环路。

### 审核和发布

- `quiz_review.csv` 是可编辑审核工作表；
- 每题必须分别审核知识点映射、答案和来源；
- 三项都是 `approved`、存在 `reviewer_id`，并且 `publish_decision=publish` 时才可发布；
- `review_release.py` 可审计工作表并生成带 manifest 和内容快照保护的发布 SQL；
- 发布批次、审核人、审核说明和发布时间均可追溯；
- `publication_readiness` 视图返回具体阻塞原因。
- 重复批次 ID、重复 manifest、来源 Commit、内容哈希、题干、答案或正确选项变化都会触发事务回滚。

### 中文翻译和答案解析

- 英文题干、英文选项和参考答案保持为不可变来源基准；
- `quiz_localization_zh_review.csv` 包含 301 道题的中文题干、中文选项和结构化中文解析候选；
- `learning_item_localizations` 保存本地化题干和解析，`item_option_localizations` 保存逐选项翻译；
- 所有自动生成内容均为 `pending/needs_review/hold`，不会进入学生接口；
- `student_quiz_localized_bank_safe` 只提供已发布本地化内容，且不含答案或解析；
- `get_student_quiz_feedback(...)` 只有在当前登录用户完成该题评分后才返回已发布解析；
- `localization_release.py` 审计翻译审核表并生成带来源快照和事务保护的发布 SQL；
- 请求 `zh-CN` 但中文尚未发布时，HTTP 服务必须回退到英文并返回 `fallbackUsed=true`。

当前解析属于 `structural_draft`：已给出正确选项、知识点、简要理由、选项辨析占位、记忆提示和来源链接，但错误选项的具体辨析仍需教研逐题补充。

### 提交与幂等

- `assessment_assignments` 固化选题版本、知识点、评测规格和算法信息；
- `task_submissions` 支持 assignment 提交和原有学习任务提交，但必须且只能关联其中一种；
- `api_idempotency_records` 保存用户、接口、幂等键、请求哈希和原结果；
- 同一个 assignment 只能产生一条提交；
- 同一个评分结果只能转换成一条掌握度证据；
- RLS 对 assignment、提交、结果和幂等记录执行用户隔离。

### 掌握度与算法安全层

- `learner_mastery_current` 同时保存五级知识掌握状态和独立的四级记忆状态；
- `learner_mastery_history` 追加保存每次状态变化，`mastery_evidence_processing` 防止重复消费证据；
- `apply_mastery_update(...)` 校验证据归属、幂等 ID 和 `expectedStateVersion`，并在单一事务中写历史与当前状态；
- `mastery_rules.py` 提供可解释规则版参考算法，提示、重试和引导练习会降权；“掌握”要求重复独立成功和延迟复测成功；
- 五个 `algorithm_*` 视图提供知识点、已发布题目、正式前置图、证据和学习者状态，均不包含参考答案；
- `app_learning_algorithm` 无权直接读取答案表或更新掌握度基表。

### 题库质量审计

- `question_quality_report.json` 覆盖 301 道 Quiz 的答案一致性、选项、重复题干、中文完整度和解析状态；
- 当前结构阻断项为 0；301 道题仍因解析是 `structural_draft` 而保持人工复核状态；
- 正确选项位置分布为 A=127、B=100、C=74，仅作为后续教研和数据分析参考。

### 接口文档

- `interfaces/01-接口契约.md`：全系统接口与算法边界；
- `interfaces/02-题库审核与评测接口.md`：学生、评分、审核、发布接口细节；
- `interfaces/03-算法接入与掌握度协议.md`：算法视图、证据、五级掌握度、记忆状态和更新协议；
- `interfaces/openapi-question-bank.yaml`：17 条路径、可导入 API 工具的 OpenAPI 3.1 契约。

## 3. 仍需要团队配合的工作

### 产品/教研团队

- 确认 50 个知识点是否与产品现有知识体系合并、重命名或拆分；
- 审核 48 条课程顺序产生的前置关系候选；
- 在 `quiz_review.csv` 中逐题确认映射、参考答案和来源；
- 在 `quiz_localization_zh_review.csv` 中逐题校对术语、题意、选项等价性和答案解析；
- 填写审核人和说明，决定发布或拒绝；
- 为实践任务批准 Rubric，或定义 Notebook/代码任务的测试标准。

这些判断涉及教学口径和产品知识体系，不能由脚本代替人工签字。

### 后端团队

- 在测试 PostgreSQL 执行迁移和种子 SQL；
- 将 OpenAPI 契约接到现有 HTTP 服务；
- 接入用户鉴权，`user_id` 必须来自服务端会话；
- 使用已经准备的 `api_idempotency_records` 和 assignment 事务实现接口；
- 分配数据库运行角色，确保学生服务无法读取答案；
- 在生产发布前完成 PostgreSQL 集成测试和 API 端到端测试。

### 算法团队

- 只从五个 `algorithm_*` 安全视图和正式知识关系中读取；
- 通过 `apply_mastery_update(...)` 写状态，不直接修改题库或掌握度表；
- 将评分结果写入 `evaluation_results`，再转换为 `assessment_evidence`；
- 保存算法/评分器版本、置信度、原因码和输入证据 ID。
- 使用 `item_quality_statistics` 逐步计算曝光量、正确率、响应时间、经验难度和区分度；样本不足时不得把统计值标记为 `stable`。
- 用真实学生数据校准规则阈值、证据权重和复习间隔，或替换为经过评估的新模型。

### 基础设施/安全团队

- 准备代码和 Notebook 的禁网、限时、限内存沙箱；
- 配置备份、恢复、审计日志、密钥和监控；
- 在连接池中确保每个学生事务都设置并在事务结束时清除 `app.current_user_id`；

## 4. 目录结构

```text
database/
├── README.md
├── backend/
│   ├── README.md
│   ├── migrations/
│   │   ├── 001_content_learning.sql
│   │   ├── 002_assessment_and_practice.sql
│   │   ├── 003_content_governance.sql
│   │   ├── 004_runtime_hardening.sql
│   │   ├── 005_runtime_roles.sql
│   │   ├── 006_localization_and_explanations.sql
│   │   ├── 007_localization_roles.sql
│   │   ├── 008_algorithm_and_mastery.sql
│   │   └── 009_algorithm_roles.sql
│   ├── algorithms/
│   │   └── mastery_rules.py
│   ├── generated/
│   │   ├── curriculum_items.jsonl
│   │   ├── curriculum_report.json
│   │   ├── curriculum_seed.sql
│   │   ├── knowledge_taxonomy.json
│   │   ├── knowledge_edge_candidates.csv
│   │   ├── quiz_knowledge_mapping_candidates.csv
│   │   ├── practice_knowledge_mapping_candidates.csv
│   │   ├── quiz_review.csv
│   │   ├── knowledge_mapping_seed.sql
│   │   ├── practice_mapping_seed.sql
│   │   ├── practice_mapping_report.json
│   │   ├── publication_readiness_report.json
│   │   ├── quiz_localization_zh_review.csv
│   │   ├── localization_seed.sql
│   │   ├── localization_report.json
│   │   ├── localization_readiness_report.json
│   │   ├── question_quality_review.csv
│   │   ├── question_quality_report.json
│   │   └── prerequisite_readiness_report.json
│   ├── scripts/
│   │   ├── import_curriculum.py
│   │   ├── emit_catalog_sql.py
│   │   ├── build_knowledge_mapping.py
│   │   ├── review_release.py
│   │   ├── build_zh_localizations.py
│   │   ├── localization_release.py
│   │   ├── build_practice_mapping.py
│   │   ├── audit_question_quality.py
│   │   └── prerequisite_release.py
│   └── tests/
└── interfaces/
    ├── 01-接口契约.md
    ├── 02-题库审核与评测接口.md
    ├── 03-算法接入与掌握度协议.md
    ├── examples/
    └── openapi-question-bank.yaml
```

## 5. 安装顺序

要求 PostgreSQL 14+。先在空测试库执行：

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_content_learning.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/002_assessment_and_practice.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/003_content_governance.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/004_runtime_hardening.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/curriculum_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/knowledge_mapping_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/practice_mapping_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/005_runtime_roles.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/006_localization_and_explanations.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/localization_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/007_localization_roles.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/008_algorithm_and_mastery.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/009_algorithm_roles.sql
```

`005_runtime_roles.sql`、`007_localization_roles.sql` 和 `009_algorithm_roles.sql` 需要 `CREATEROLE`，应由 DBA 执行；生产环境必须安装。

角色是 `NOLOGIN` 权限组，需要 DBA 把它们授予实际服务账号：

```sql
GRANT app_student_api TO your_student_service_login;
GRANT app_scoring_service TO your_scoring_service_login;
GRANT app_content_reviewer TO your_reviewer_service_login;
GRANT app_content_publisher TO your_publisher_service_login;
GRANT app_learning_algorithm TO your_algorithm_service_login;
```

不要把 `app_scoring_service` 或数据库 owner 权限授予学生端服务。

## 6. 导入后检查

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

python3 backend/scripts/review_release.py audit \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_review.csv \
  --report backend/generated/publication_readiness_report.json
```

初次导入预期：

```text
source_repositories                 2
learning_items                    423
quiz_question                     301
practice items                    122
knowledge_nodes                    50
item_knowledge_map_candidates     423
knowledge_edge_candidates          48
item_knowledge_maps                 0
ready_to_publish                    0
student_quiz_bank_safe              0
learning_item_localizations zh-CN 301
item_option_localizations zh-CN    856
published zh-CN Quiz                 0
learner mastery states               0
```

可执行以下数据库检查：

```sql
SELECT source_id, count(*)
FROM source_documents
GROUP BY source_id;

SELECT item_type, status, count(*)
FROM learning_items
GROUP BY item_type, status
ORDER BY item_type, status;

SELECT status, count(*)
FROM item_knowledge_map_candidates
GROUP BY status;

SELECT readiness_status, count(*)
FROM publication_readiness
WHERE item_type = 'quiz_question'
GROUP BY readiness_status;
```

## 7. 人工审核工作流

只编辑 `backend/generated/quiz_review.csv` 的以下列：

| 列 | 允许值 | 说明 |
|---|---|---|
| `mapping_review_status` | `pending/approved/changes_requested/rejected` | 知识点映射审核 |
| `answer_review_status` | 同上 | 参考答案审核 |
| `source_review_status` | 同上 | 来源和版权/出处审核 |
| `publish_decision` | `hold/publish/reject` | 最终发布决定 |
| `reviewer_id` | 团队成员 ID | 发布时必填 |
| `reviewer_note` | 文本 | 审核依据或修改说明 |

不要修改题目 ID、版本 ID、来源字段或映射候选 ID。若题干或答案有问题，应创建新的题目版本，再重新生成审核表。映射生成器默认保留现有 `quiz_review.csv`；只有明确传入 `--overwrite-review` 才会覆盖人工审核进度。

审核后先运行审计：

```bash
python3 backend/scripts/review_release.py audit \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_review.csv \
  --report backend/generated/publication_readiness_report.json
```

生成发布 SQL：

```bash
python3 backend/scripts/review_release.py build-release \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_review.csv \
  --output backend/generated/quiz_release_2026_01.sql \
  --batch-id publication-quiz-2026-01 \
  --batch-name "Quiz first reviewed release" \
  --requested-by reviewer-team
```

如果没有任何完整批准的题目，工具会拒绝生成发布 SQL。生成后应由第二位审核人查看差异，再在测试库执行：

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/quiz_release_2026_01.sql
```

发布 SQL 只调用受控的 `publish_quiz_batch(...)`，函数会：

1. 把候选映射升级为正式映射；
2. 写入答案、映射、来源审核记录；
3. 发布对应 `exact_answer` 评测规格；
4. 发布题目和任务模板；
5. 写入审核批次和发布批次记录；
6. 校验唯一 manifest、固定 Commit、内容哈希、题干、答案和正确选项；任一步失败都会整体回滚。

## 8. 答案安全边界

学生题目读取：

```text
student_quiz_bank_safe
→ questionId、versionId、题干、普通选项、知识点 ID、来源
```

服务端评分：

```text
internal_quiz_scoring_bank
→ versionId、evaluationSpecId、answer_data、正确项、评分配置
```

强制规则：

- 学生响应中不得出现 `answer_data`、`is_correct`、隐藏测试或评分配置；
- 客户端提交选项 key，服务端只与 `correct_option_key` 比较，答案文本仅供审核；
- 评分结果可以返回是否正确、得分和反馈，但不要回传整套内部评分记录；
- 生产环境用独立数据库账号，不要仅依赖应用代码删字段；
- 发布前用契约测试扫描学生响应，确认不存在答案字段。
- 中文题干和中文选项可在作答前返回；中文解析只能在该用户提交且评分状态为 `completed` 后返回。

### 中文翻译与解析审核

只编辑 `backend/generated/quiz_localization_zh_review.csv` 中的 `zh_*` 内容列和以下审核列：

| 列 | 允许值 | 说明 |
|---|---|---|
| `translation_review_status` | `pending/approved/changes_requested/rejected` | 中文题干和选项审核 |
| `explanation_review_status` | 同上 | 解析审核 |
| `publish_decision` | `hold/publish/reject` | 本地化发布决定 |
| `reviewer_id` | 团队成员 ID | 发布时必填 |
| `reviewer_note` | 文本 | 术语或教学口径说明 |

审核和生成发布包：

```bash
python3 backend/scripts/localization_release.py audit \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_localization_zh_review.csv \
  --report backend/generated/localization_readiness_report.json

python3 backend/scripts/localization_release.py build-release \
  --items backend/generated/curriculum_items.jsonl \
  --review backend/generated/quiz_localization_zh_review.csv \
  --output backend/generated/quiz_localization_zh_release.sql \
  --batch-id localization-zh-001 \
  --batch-name "Reviewed zh-CN Quiz localization" \
  --requested-by reviewer-team
```

发布中文前，英文基础题必须已经通过正式题库发布流程。没有完整批准行时，工具会拒绝生成发布 SQL。

## 9. 算法接入方式

| 能力 | 读取 | 写入 |
|---|---|---|
| 诊断选题 | `student_quiz_bank_safe`、正式映射、历史证据 | 题单和选题理由 |
| Quiz 评分 | `internal_quiz_scoring_bank`、用户提交 | `evaluation_results` |
| 掌握度估计 | `algorithm_evidence_feed`、`algorithm_learner_state` | `apply_mastery_update(...)` |
| 学习计划 | 学习目标、知识图、掌握度、用户校准 | `learning_plans`、`learning_tasks` |
| 实践评分 | 评测规格、测试/Rubric、提交 | `evaluation_results`、人工复核状态 |

算法不得直接更新题目、答案、正式映射、历史评分结果或掌握度基表。每次算法输出都应保存算法名称、版本、置信度、原因码和输入证据。

算法增强所需承载结构已经预留：

- `knowledge_edge_candidates`：课程前置关系候选；
- `learning_item_enrichment_candidates`：难度、预计用时和答案解析候选；
- `learning_item_localizations`：中文等多语言版本及审核状态；
- `item_quality_statistics`：运行期题目质量和样本稳定性。

当前 301 道 Quiz 的英文原文完整，并已有 301 套中文题干、选项和解析候选；中文仍全部待审核。题目尚无正式难度和预计用时。自动翻译和结构化解析不能直接变成可信教学数据，必须经过教研审核。

五个算法安全视图、受控掌握度更新函数和可解释规则版参考实现已经完成。详细数据契约、并发规则和调用示例见 `interfaces/03-算法接入与掌握度协议.md`。

## 10. API 接入最小闭环

第一阶段建议只实现已审核 Quiz：

```text
POST /v1/assessment/assignments/next
POST /v1/assessment/submissions
GET  /v1/assessment/submissions/{submissionId}/result
```

管理端实现：

```text
GET  /v1/admin/content/review-queue
POST /v1/admin/content/mappings/{candidateId}/decision
POST /v1/admin/content/items/{versionId}/review
POST /v1/admin/content/publication-batches/{batchId}/publish
POST /v1/admin/content/localizations/{versionId}/review
POST /v1/admin/content/localization-publication-batches/{batchId}/publish
POST /v1/admin/content/knowledge-edges/{candidateId}/decision
POST /v1/admin/content/knowledge-edge-publication-batches/{batchId}/publish
GET  /v1/learners/me/knowledge-status
GET  /v1/learners/me/mastery-history
GET  /v1/internal/mastery/evidence-events
POST /v1/internal/mastery/updates
```

精确字段、状态码、DTO、幂等规则和权限矩阵见 `interfaces/02-题库审核与评测接口.md` 与 `interfaces/openapi-question-bank.yaml`。

## 11. 上线验收

### 数据与教研

- [ ] 两个来源和 Commit 均已确认；
- [ ] 待上线 Quiz 的答案、映射、来源均已审核；
- [ ] 正式映射和发布批次可追溯；
- [ ] 未审核题目不会出现在学生安全视图。
- [ ] 中文题干、选项和解析均已分别审核，机器生成内容未被直接发布；

### 接口与安全

- [ ] 学生服务账号无法查询答案表和内部评分视图；
- [ ] 用户身份来自登录上下文，不信任请求体的 `userId`；
- [ ] 每个学生事务执行 `SET LOCAL app.current_user_id`，RLS 测试通过；
- [ ] 写接口支持 `Idempotency-Key` 和事务；
- [ ] 管理端和发布端有单独权限与审计；
- [ ] 接口契约测试确认学生响应无答案字段。
- [ ] 作答前响应不含解析；只有已完成且属于当前用户的提交才能取得解析；

### 算法与运维

- [ ] 选题算法只使用已发布并已映射题目；
- [ ] 评分器和掌握度算法均保存版本；
- [ ] 掌握度变化可追溯到评测证据；
- [ ] 算法只调用 `apply_mastery_update(...)`，重复证据和过期版本会被拒绝；
- [ ] 正式前置关系通过发布函数写入且环路检查通过；
- [ ] 测试库迁移、接口测试和端到端测试通过；
- [ ] 已配置备份、恢复、监控和日志脱敏。

## 12. 实践任务说明

122 条实践素材继续保留，但不伪造唯一答案：

- 82 个 Notebook/Lab：使用固定镜像从头运行并执行隐藏检查；
- 35 个 Project：使用人工批准 Rubric，LLM 只作评分辅助；
- 2 个代码任务：使用沙箱公开/隐藏测试；
- 3 个概念任务：默认人工审核，不直接更新掌握度。

实践任务评测尚未达到生产可用状态。建议先上线 Quiz 闭环，再逐批补充并验证测试用例和 Rubric。

## 13. 技术同事 30 分钟接入步骤

以下命令均从 `database` 目录执行。

### 第一步：准备空测试数据库

```bash
export DATABASE_URL='postgresql://user:password@host:5432/adaptive_learning_test'
```

不要先导入其他题库，也不要复用已有业务库测试首次迁移。

### 第二步：执行数据库安装

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_content_learning.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/002_assessment_and_practice.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/003_content_governance.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/004_runtime_hardening.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/curriculum_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/knowledge_mapping_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/practice_mapping_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/005_runtime_roles.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/006_localization_and_explanations.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/generated/localization_seed.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/007_localization_roles.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/008_algorithm_and_mastery.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/009_algorithm_roles.sql
```

如果测试账号没有 `CREATEROLE`，可暂时跳过 `005_runtime_roles.sql`、`007_localization_roles.sql` 和 `009_algorithm_roles.sql`；但生产环境必须由 DBA 执行，否则答案隔离和运行角色验收不完整。

### 第三步：运行交付包校验

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

预期最后输出：

```text
backend contract passed: 48 tables
generated catalog passed: 301 quizzes, 122 practice items
content governance passed: 301 review rows, 50 knowledge points, answers isolated
localization passed: 301 zh-CN stems/options/explanations, all pending review
practice mapping passed: 122 pending mappings
question quality audit passed: 301 Quiz rows, zero structural blockers
prerequisite release passed: current graph pending, cycle detection active
algorithm security passed: safe views and controlled mastery writes
PostgreSQL integration passed
```

### 第四步：确认初始空发布状态

```sql
SELECT count(*) FROM learning_items;
SELECT count(*) FROM item_knowledge_map_candidates;
SELECT count(*) FROM item_knowledge_maps;
SELECT count(*) FROM knowledge_edge_candidates;
SELECT count(*) FROM knowledge_edges;
SELECT count(*) FROM student_quiz_bank_safe;
```

首次导入应分别返回：

```text
learning_items                  423
item_knowledge_map_candidates  423
item_knowledge_maps              0
knowledge_edge_candidates       48
knowledge_edges                  0
student_quiz_bank_safe            0
```

后三个正式数据为 0 是预期安全状态，不是安装失败。

### 第五步：实现 HTTP 服务

将 `interfaces/openapi-question-bank.yaml` 导入 Swagger、Postman 或后端代码生成工具。第一批只需实现：

```text
POST /v1/assessment/assignments/next
POST /v1/assessment/submissions
GET  /v1/assessment/submissions/{submissionId}/result
GET  /v1/admin/content/review-queue
POST /v1/admin/content/mappings/{candidateId}/decision
POST /v1/admin/content/items/{versionId}/review
POST /v1/admin/content/publication-batches/{batchId}/publish
```

应用层必须使用独立数据库账号，并在每个学生事务执行：

```sql
SET LOCAL app.current_user_id = '<服务端鉴权确认的用户ID>';
```

不能信任请求体传入的 `userId`。

## 14. 知识点和算法标签使用说明

### 题目知识点标签

| 数据 | 当前数量 | 状态 | 算法是否可用 |
|---|---:|---|---|
| `knowledge_nodes` | 50 | 课程级候选知识点 | 可用于离线开发 |
| `item_knowledge_map_candidates` | 423 | 301 道 Quiz + 122 条实践素材，全部 `pending` | 不能作为生产真值 |
| `item_knowledge_maps` | 0 | 正式映射 | 发布后供生产算法使用 |
| `knowledge_edge_candidates` | 48 | 课程顺序候选 | 只能做实验参考 |
| `knowledge_edges` | 0 | 正式知识关系 | 审核后供路径算法使用 |

每道 Quiz 当前有一个 `target` 候选知识点。数据库支持一题多知识点及 `target/prerequisite/application/misconception/related` 关系，但当前导入数据尚未细化到这些多重关系。

算法生产读取原则：

```text
选题和掌握度归因 → 只读 item_knowledge_maps
前置路径规划     → 只读 knowledge_edges
内容审核界面     → 可读 candidates 表
```

不要让生产算法把 `pending` 候选直接当作已审核标签。

### 掌握度标签

现有结构可以保存：

- `assessment_evidence`：题目、知识点、得分、正确性、用时、提示和重试；
- `ai_assessments`：`不会/了解/熟悉/掌握`、置信度、证据 ID、原因码和算法版本；
- `user_calibrations`：用户自我校准，不覆盖 AI 判断；
- `learner_mastery_current`：掌握分、记忆稳定天数、置信度、最近证据和下次复习时间；
- `adaptive_decisions`：选题或计划算法的输入快照、输出快照、原因码和版本。

这些表是算法接入位置，不是已经运行的掌握度算法。技术团队仍需实现：

```text
evaluation_results
→ assessment_evidence
→ 掌握度更新器
→ ai_assessments + learner_mastery_current
→ adaptive_decisions / learning_tasks
```

第一版掌握度更新器应遵守：

- 一次答对不能直接升级为稳定掌握；
- 提示、重试和非独立作答降低证据权重；
- 即时正确主要更新当前理解，延迟无提示复测主要更新记忆稳定度；
- 视频观看、聊天和任务完成只能作为学习过程，不能直接升级掌握度；
- 每次状态变化必须保存算法版本、原因码和证据 ID。

当前 OpenAPI 已提供以下掌握度读取和更新端点：

```text
GET  /v1/learners/me/knowledge-status
GET  /v1/learners/me/knowledge-status/{knowledgePointId}
GET  /v1/learners/me/mastery-history
GET  /v1/knowledge-points/{knowledgePointId}/prerequisites
GET  /v1/internal/mastery/evidence-events
POST /v1/internal/mastery/updates
```

规则版更新器已位于 `backend/algorithms/mastery_rules.py`。它是可运行参考实现；团队可替换计算模型，但仍应使用相同受控数据库写入协议。

## 15. 哪些文件可以修改

技术和教研团队可以修改：

- `backend/generated/quiz_review.csv` 的审核状态、审核人和审核说明列；
- `backend/generated/quiz_localization_zh_review.csv` 的中文内容列、审核列和审核说明；
- `backend/generated/practice_knowledge_mapping_candidates.csv` 的审核列；
- `backend/generated/knowledge_edge_candidates.csv` 的审核状态、审核人和说明；
- 新增迁移文件、HTTP 服务实现和算法服务实现；
- 接口文档，但修改后必须同步 OpenAPI。

不要直接修改：

- `curriculum_items.jsonl` 中的来源题目；
- 已发布的题目版本、答案或历史评分；
- 题目 ID、版本 ID、来源 Commit、内容哈希；
- 生产数据库里的正式映射或发布状态。

题干、答案或选项需要修正时，应创建新的题目版本并重新审核，不能覆盖已经产生学生作答的旧版本。

## 16. 交接验收清单

技术负责人收到文件夹后应确认：

- [ ] 能在空 PostgreSQL 测试库顺序执行全部迁移和种子；
- [ ] 全部静态测试、规则算法测试和 PostgreSQL 集成测试通过；
- [ ] 能解释为什么初始学生题库为 0；
- [ ] 学生服务账号不能读取 `answer_data`、`is_correct` 或内部评分视图；
- [ ] 评分服务与学生服务使用不同数据库角色；
- [ ] HTTP 用户身份来自鉴权上下文，并在事务设置 `app.current_user_id`；
- [ ] 重复提交使用 `Idempotency-Key`，不会产生重复作答和证据；
- [ ] 生产算法只读取正式题目映射和正式前置关系；
- [ ] 内容团队知道需要审核 `quiz_review.csv` 和中文审核表；
- [ ] 团队明确前置关系/内容审核、实践任务评测和真实数据参数校准仍需配合。

满足以上接入项后，本文件夹即可作为后端题库数据层进入团队联调；完成内容审核和正式发布后，才能作为学生生产题库使用。
