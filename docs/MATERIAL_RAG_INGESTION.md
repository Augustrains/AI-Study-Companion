# 教材 RAG 数据处理与入库

本文件定义资料问答的结构化入库契约。当前索引为 `v5`，检索使用
`study_companion_v5_ml` 与 `study_companion_v5_dl`；旧 collection 不会被该流程删除。

## 输入约束

一篇 Markdown 文件对应一个知识点父文档。只有同时满足以下条件的文件会进入索引：

- 位于配置的教材 `lessons/` 目录；
- front matter 中 `cleaning_status: approved`；
- front matter 中 `review_status: approved`；
- 包含 `## 原文学习材料`，其后的内容才是可检索教材正文。

必需或建议保留的字段包括 `content_unit_id`、`knowledge_points`、`chapter`、
`source_url`、`source_commit` 和许可证信息。缺少审核状态、课程正文边界的文件会被跳过，
因此仓库 README、翻译、实验文件和维护文档不会被意外写入 Qdrant。

## 处理流程

```text
已审核 Markdown
  → 读取 front matter、学习目标和阅读重点
  → 解析原文中的 Markdown 标题树
  → 文章卡（概览粒度） + 标题层级子块（精确粒度）
  → 为每个子块拼接标题路径、知识点和学习目标
  → 写入版本化 Qdrant collection
```

文章卡用于“这个知识点讲什么”类问题。子块按二级标题分区，再在分区内部以约
1,800 字符上限和 180 字符重叠切分；代码、公式和表格会优先按段落边界保留。子块
保留 `parent_id`、`heading_path` 和 `chunk_index`，可追溯回父文章和课程小节。

Contextual Retrieval 不是把长文正文写进 metadata：用于 embedding 的文本会附加
`知识点文章 / 知识点 / 学习目标 / 阅读重点 / 标题路径`，而 metadata 只保存可筛选和
审计的结构化字段，例如 `book_id`、`content_unit_id`、`knowledge_point_ids`、
`source_url`、`source_commit`、`parent_id`。

## 查询链路

活动索引上的查询不再是单一路径的 dense Top-K，而是以下稳定、可降级的链路：

```text
问题 → Dense Top-20（语义） + BM25 Top-20（术语/编号）
     → Reciprocal Rank Fusion（RRF）
     → 重排 → Top-5 命中块
     → 子块补齐父文章卡与同节相邻块（最多 8 块）
```

BM25 使用活动 collection 的 payload 快照，因此不需要额外写入一份稀疏向量；这适合当前
以课程文章为主、规模较小的资料库。语义召回和 BM25 都会尊重 `sourceIds` 过滤条件。
默认重排器是确定性的词项覆盖度重排，保证离线或模型不可用时仍可查询。如已在部署环境缓存
cross-encoder 模型，可设置 `STUDY_COMPANION_RERANKER_MODEL`（例如内部批准的重排模型路径或名称）
启用模型重排；加载或推理失败会自动回退，不影响问答服务。资料库扩展到大规模语料时，应将
本地 BM25 替换为 Qdrant sparse vector / FastEmbed 方案，避免每次查询扫描 payload 快照。

## AI-For-Beginners 课程正文筛选

深度学习教材的原仓库中，课程正文采用英文 `lessons/` 内编号课时目录的
`README.md`，例如 `5-NLP/18-Transformers/README.md`。入库与本地 Markdown
降级检索均只接受这类来源；`translations/`、`lab/`、`assignment.md`、
`sketchnotes/`、课程外 README 与教师材料都会排除。规范化后的文件可使用
`dl-unit-xxx.md` 命名，但必须以 `source_relative_path` 指回符合规则的原始 README。

使用以下脚本生成 24 个待审核单元；脚本不会把内容直接批准或写入 Qdrant：

```powershell
.venv\Scripts\python.exe scripts\prepare_ai_for_beginners_material.py
```

输出位于 `AI-For-Beginners/lessons/processed/`。审核人员确认正文、知识点映射和
版权来源后，才可将 `cleaning_status` 与 `review_status` 改为 `approved` 并重建 `dl` 索引。

在审核或构建前，可运行只读校验并生成审计报告：

```powershell
.venv\Scripts\python.exe scripts\validate_material_documents.py
```

报告保存于 `data/material-reports/`，包含已批准、待审核、被正常排除的原始资料和 schema
错误的逐文件清单。

## 重建接口

启动后调用以下接口构建新批次。该动作会先校验所有正式教材单元，再写入一个带批次后缀的
新 collection；文章数和向量点数验收通过后，才原子更新活动索引指针。因此旧索引会持续
服务，构建失败不会清空当前可查询的 collection。

```http
POST /api/rag/indexes/rebuild
Content-Type: application/json

{
  "bookIds": ["ml", "dl"],
  "confirm": true
}
```

响应会返回每本教材的 collection 名、文章数和写入的索引文档数。正常资料问答查询
会读取活动索引指针；运行报告存放于 `data/material-reports/`，其中包含候选、排除、待审核、
校验错误、写入数量和激活结果。

## 版本、增量更新与稳定引用

每次重建都会生成不可变 `index_version` 和独立 Qdrant collection。系统会为每篇已批准单元
计算 `content_hash`（正文、知识点、来源提交版本和索引 schema）；与活动版本的 manifest 比较后：

- 新增或变更单元：重新进行切分和 embedding；
- 未变单元：直接复制旧 collection 中的向量点，不重复 embedding；
- 删除单元：不复制到新版本，但仍保留在旧版本中。

活动版本保存在 `data/qdrant-bge-m3/material_index_registry.json`。发布只会原子更新该指针：
上一版本改为 `retired`，不会立即删除。查询开始时会取得该版本的短期 lease，整次向量查询固定
使用同一版本；返回的每条教材引用都带有 `indexVersion`，可用于会话回放、审计与将来的回滚。
embedding 模型名称改变时，系统自动将所有单元判定为需重新 embedding。

## 审核状态流转

生成脚本只会产生 `pending_review` 单元。不要手动编辑状态字段；请通过审核接口记录审核人和
时间。状态只允许 `pending_review → approved/rejected`，以及修订后的
`rejected → pending_review`。批准时会重新执行 schema 校验。

```http
POST /api/rag/materials/dl-unit-018/review
Content-Type: application/json

{
  "bookId": "dl",
  "status": "approved",
  "reviewer": "content-editor-01"
}
```

## 验收建议

- 文章数应等于已审核的课程 Markdown 数，而不是教材仓库的全部 `.md` 数；
- 查询结果的 `heading_path` 应能定位到正确教材小节；
- 宽泛问题应可命中文章卡，细节问题应优先命中子块；
- 每条引用必须保留原始 `content_unit_id`、来源 URL 和知识点 ID。
