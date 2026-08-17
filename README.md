# Study Companion

Study Companion 是一个自适应伴学 Demo：React 前端负责交互，FastAPI 负责身份、业务规则和持久化，LangGraph 承载可恢复工作流，Agent 只在后端给定的上下文边界内生成内容。

> 当前定位是可运行、可测试的单机 Demo，不是已完成生产部署的 SaaS。真实登录、生产迁移演练、全量 PostgreSQL 化和多实例部署仍是后续工作。

## 环境要求

- **Python >= 3.11**（代码使用了 `StrEnum`）
- Node.js LTS
- pnpm（推荐，仓库提交了 `pnpm-lock.yaml`；npm 也可被启动器识别）
- 真实 Agent 调用需要 OpenAI-compatible LLM API key
- 真实资料问答还需要教材目录、Embedding 模型和可写的 Qdrant 本地目录

## 从 clone 到运行

### 1. 拉取代码并安装 Python 依赖

```bash
git clone --branch shy https://github.com/Augustrains/AI-Study-Companion.git
cd AI-Study-Companion

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Windows PowerShell 激活命令是：

```powershell
.\.venv\Scripts\Activate.ps1
```

`requirements-dev.txt` 已包含运行依赖、pytest 和 Ruff；只运行服务时也可仅安装 `requirements.txt`。

### 2. 复制配置

```bash
cp .env.example .env
```

PowerShell 使用 `Copy-Item .env.example .env`。至少检查下列项：

```dotenv
STUDY_COMPANION_LLM_API_KEY=your_real_key
STUDY_COMPANION_DATABASE_URL=sqlite+pysqlite:///./data/study_companion.sqlite3
STUDY_COMPANION_AUTO_CREATE_SCHEMA=true
STUDY_COMPANION_CHECKPOINT_BACKEND=sqlite
STUDY_COMPANION_CHECKPOINT_URL=./data/langgraph_checkpoints.sqlite3
STUDY_COMPANION_ALLOW_DEV_IDENTITY=true
STUDY_COMPANION_DEV_USER_ID=user_001
STUDY_COMPANION_TIMEZONE=Asia/Shanghai
```

系统环境变量优先于 `.env`。`STUDY_COMPANION_LLM_API_KEY` 的示例占位值不能用于真实请求。

### 3. 安装前端依赖

```bash
cd front/frontend
pnpm install --frozen-lockfile
cd ../..
```

### 4. 选择运行方式

只看前端 Mock（不启动 Python、LLM 和 RAG）：

```bash
cd front/frontend
VITE_USE_REAL_API=false pnpm run dev
```

启动真实前后端：

```bash
python main.py
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

`python main.py` 会同时启动后端和 Vite，并在启动阶段打开 Qdrant、加载 Embedding 模型。首次使用 `BAAI/bge-m3` 可能会下载较大模型；离线环境请通过 `STUDY_COMPANION_EMBEDDING_MODEL` 指向已有本地模型。当前仓库不包含 `data/question_new/教材/ML-For-Beginners` 和 `AI-For-Beginners` 的完整教材，未补齐时资料问答不可用。

`python main.py --mock-api` 只会让前端切换到 Mock，后端依赖仍会初始化；若要完全避免模型加载，请使用上面的“只看前端 Mock”命令。

## 本地与生产配置边界

| 项目 | 本地开发 | 生产目标配置 |
| --- | --- | --- |
| 业务数据库 | SQLite：`sqlite+pysqlite:///./data/study_companion.sqlite3` | PostgreSQL：`postgresql+psycopg://user:password@host/database` |
| LangGraph checkpoint | 独立 SQLite 文件 | `STUDY_COMPANION_CHECKPOINT_BACKEND=postgres` + PostgreSQL DSN |
| 身份 | `STUDY_COMPANION_ALLOW_DEV_IDENTITY=true`，可使用 `X-User-Id` | `STUDY_COMPANION_ALLOW_DEV_IDENTITY=false`，只接受 Bearer JWT |
| JWT 密钥 | 可留空 | 必须设置高强度 `STUDY_COMPANION_JWT_SECRET` |
| 向量库 | 进程内 Qdrant 本地持久化 | 当前未接入独立 Qdrant 服务 |

一个生产目标配置示例（只表示代码支持的连接方式，不代表已完成生产上线）：

```dotenv
STUDY_COMPANION_DATABASE_URL=postgresql+psycopg://user:password@db:5432/study_companion
STUDY_COMPANION_AUTO_CREATE_SCHEMA=false
STUDY_COMPANION_CHECKPOINT_BACKEND=postgres
STUDY_COMPANION_CHECKPOINT_URL=postgresql://user:password@db:5432/study_companion
STUDY_COMPANION_ALLOW_DEV_IDENTITY=false
STUDY_COMPANION_JWT_SECRET=paste-generated-64-character-secret-here
```

可用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成密钥并粘贴到 `.env`。当开发身份被关闭时，后端验证 HS256 JWT 的签名、`sub`、`exp` 和可选 `nbf`，并以 `sub` 作为唯一用户身份。请求 body/query 中的 `userId` 不能覆盖它。公开占位值或少于 32 字符的 JWT 密钥会让启动失败。但项目目前**不负责注册、登录、刷新 token、密钥轮换或注销**；生产环境需要接入真实身份服务。

部署配置若同时关闭开发身份、却仍开启自动建表，系统也会拒绝启动，避免绕过版本化迁移。

## 前后端与 Agent 的边界

```text
React 页面 -> HTTP JSON -> FastAPI Schema/身份 -> Workflow/业务规则
                                             |-> ContextBuilder -> Agent
                                             |-> Retriever(RAG) -> Agent
                                             |-> Database/checkpoint
```

- 前端只提交用户动作，不能直接写掌握度、服务端任务状态、正确答案或其他用户的资源。
- FastAPI 负责 Schema 校验、JWT 身份和资源归属；Workflow 负责状态转移、幂等和持久化顺序。
- Agent 只能根据后端组装的 DTO 生成诊断建议、计划文案或资料问答；ID、所有权、掌握度、任务完成状态和引用来源仍由后端校验。
- `ContextBuilder` 只组装“本轮可用上下文”，不是业务数据库，也**不会调用 RAG**。RAG 由 `MaterialQaWorkflow` 单独调用 Retriever，排名后的 chunks 再作为不可信数据交给 Agent。

上下文和长期记忆的详细数据流、三种主要 policy 及裁剪策略见 [docs/context-memory.md](docs/context-memory.md)。

## 测试、构建和迁移

后端测试与静态检查：

```bash
python -m pytest -q
python -m ruff check .
```

前端生产构建：

```bash
cd front/frontend
pnpm run build
```

新建数据库的标准执行链：

```bash
python -m alembic upgrade head
python -m alembic current
```

本地 Demo 可保留 `STUDY_COMPANION_AUTO_CREATE_SCHEMA=true`。部署时必须设为 `false`，先执行 Alembic，再启动服务。

如果数据库曾由旧版本的 `create_all()` 建表、已有业务表但没有 `alembic_version`，先备份数据库，然后执行受控接管；不要直接 `upgrade head`：

```bash
python -m modules.persistence.schema_migration
python -m alembic upgrade head
```

接管命令会先比较现有应用表与当前 ORM 元数据；缺表或结构不一致时拒绝写入版本号。它只接管结构版本，不替代正式备份和生产回滚演练。后续修改表结构时再生成并审查新 revision：

```bash
python -m alembic revision --autogenerate -m "describe schema change"
```

启动时还会按版本账本自动回填旧数据：先将 `data/memory/learner_memories.json` 的完整正式记忆迁入 SQL，再同步 `data/profiles/learner_profiles.json` 的自报画像。全部成功后才写入 `migration_ledger`；解析或写入失败会中止启动，避免静默丢数据。

## 当前实现与后续工作

已有实现：

- 学习者画像、诊断、计划、资料问答、学习记录和 Today 页的 FastAPI 边界。
- 按 `user_id + learning_domain` 持久化的 SQL 记忆状态、幂等记忆事件、历史版本和上下文 trace。
- 诊断、计划和 Tutor 三条主要上下文 policy，会话摘要/最近消息和最终 Prompt 预算。
- 开发身份和 HS256 Bearer JWT 验证边界。

尚未完成或仅适用于单机：

- 真实登录/发 token/刷新/撤销、权限管理后台和密钥轮换。
- 当前已有首个 Alembic baseline；尚未完成真实生产数据升级/回滚演练。
- 学习计划、学习记录和原始画像仍有 JSON/本地文件路径；未完成全量 PostgreSQL 化。
- Qdrant 是进程内本地存储，不适合直接水平扩容。
- 部分并发协调仍依赖进程内锁和本地文件；多实例前需迁移到共享存储、补齐分布式 lease/锁和压测。
- 当前上下文“token”计数是 UTF-8 字节上界，不是模型原生 tokenizer 的精确计数。

## 主要目录

```text
api/                         FastAPI 应用组装和全局错误处理
bootstrap/                   启动、依赖注入和资源关闭
modules/context/             上下文策略、预算、渲染和 trace
modules/memory/              长期记忆、事件投影和 SQL 仓储
modules/conversation/        会话、消息、摘要和幂等 turn
modules/diagnosis/           诊断工作流
modules/learning_plan/       学习计划与 Agent
modules/material_qa/         RAG Retriever、资料问答 Workflow 与 Agent
modules/persistence/         SQLAlchemy 表、数据库和 checkpoint 资源
front/frontend/              React + Vite 前端
tests/                       后端单测和集成测试
```
