# Study Companion｜自适应 AI 学习伴侣

> 面向机器学习与深度学习学习者的全栈学习平台。项目将学习目标、能力诊断、个性化周计划、每日任务、练习复盘与 RAG 资料问答串联为可持续迭代的学习闭环。

## 项目概览

Study Companion 以工作台形式承载学习流程，后端通过 FastAPI 提供领域 API，并使用 LLM、知识点图谱和学习记录生成学习建议。系统以 MySQL 持久化用户与学习数据，以本地 Qdrant 向量库支撑资料问答；当模型或向量检索不可用时，核心流程可回退到规则规划或 Markdown 检索。

| 维度 | 技术选型 |
| --- | --- |
| 前端 | React、TypeScript、Vite、pnpm |
| 后端 | Python 3.14、FastAPI、Uvicorn、Pydantic |
| 智能能力 | LangGraph、OpenAI-compatible LLM、sentence-transformers（BGE-M3） |
| 数据与检索 | MySQL、SQLAlchemy、Qdrant、Markdown/PDF 文档 |
| 工程化 | pytest、SQL 迁移、环境变量配置、演示数据重置 |

## 核心功能

1. **账号与学习档案**：注册/登录、学习偏好、基础能力、目标知识点与每周可投入时长管理。
2. **自适应能力诊断**：按知识点生成诊断题并记录结果；LLM 不可用时回退到规则化题目规划。
3. **个性化学习计划**：综合学习目标、诊断掌握度、可用时长及历史完成情况，生成并动态调整周计划和每日任务。
4. **练习与学习记录**：记录练习、学习事件、任务完成与实际用时，为节奏校准和计划重排提供反馈。
5. **资料问答（RAG）**：对机器学习/深度学习教材进行向量检索和回答，支持会话、附件上传、OSS 存储及 Markdown 降级检索。
6. **演示与交互**：前端提供学习资源、社区、激励、帮助中心等页面；`--reset-demo` 支持将体验账号恢复到可重复演示的基线。

## 架构设计

```text
React + Vite（5173）
        │ /api（Vite 代理）
        ▼
FastAPI + Uvicorn（8001）
        │
        ├── auth / learner_profile / learner_goals
        ├── diagnosis / learning_plan / today_learning / practice
        ├── learning_record / learning_resources / material_qa
        │
        ├── MySQL：账号、画像、目标、计划、学习记录、问答消息
        ├── Qdrant + BGE-M3：教材向量检索
        ├── OSS：问答附件
        └── OpenAI-compatible LLM：诊断、计划和问答智能体
```

领域模块采用 `API → Module/Workflow → Service/Agent → Repository` 分层。`bootstrap/application.py` 是组合根，统一装配基础设施；`bootstrap/web_runtime.py` 负责前后端联合启动、后端就绪探测和资源释放。

## 项目路径与文件说明

```text
./                                  # 项目根目录（克隆仓库后所在目录）
├── main.py                         # 启动入口：Web 服务、诊断 Demo、演示数据重置
├── requirements.txt                # 从 .venv 导出的精确 Python 依赖
├── .env.example                    # LLM、MySQL、OSS、Tavily 环境变量模板
├── api/server.py                   # FastAPI、CORS、统一异常处理、路由注册
├── bootstrap/
│   ├── application.py              # 构建 MySQL、LLM、RAG 与业务依赖图
│   ├── web_runtime.py              # 前后端启动、健康探测和资源关闭
│   └── demo_runtime.py             # 轻量诊断工作流演示
├── modules/                        # 后端领域模块
│   ├── auth/                       # 注册、登录、令牌与账号仓储
│   ├── learner_profile/            # 学习者画像与能力评估
│   ├── learner_goals/              # 学习目标与每周投入配置
│   ├── diagnosis/                  # 自适应诊断、题目规划、结果记录
│   ├── learning_plan/              # 周计划、掌握度融合、BKT 与节奏调整
│   ├── today_learning/             # 每日学习任务编排
│   ├── practice/                   # 练习题查询与答题数据
│   ├── learning_record/            # 学习事件、时长与完成记录
│   ├── material_qa/                # RAG 问答、对话、附件和检索降级
│   ├── learning_resources/         # 学习资源接口
│   └── common/                     # 配置、数据库、错误模型和通用工具
├── sdk/llm_client.py               # OpenAI-compatible LLM 客户端封装
├── data/                           # 题库、知识点、教材、资源与本地数据
├── models/                         # 可选本地 Embedding 模型目录（bge-m3）
├── migrations/                     # MySQL 结构与数据迁移 SQL
├── scripts/                        # 演示数据、教材处理、迁移和压测脚本
├── tests/                          # pytest 单元、契约、仓储与 API 测试
├── load_tests/locustfile.py        # RAG 发布场景的 Locust 压测脚本
├── docs/                           # RAG 导入、压测及设计说明
└── front/frontend/                 # React 前端（src/components、services、data）
```

更多接口字段和演示账号说明见 [README-使用与接口.md](README-使用与接口.md) 与 [README-demo.md](README-demo.md)。

## 本地运行

### 前置条件

- Windows PowerShell、Python **3.14.5**（项目当前 `.venv` 的版本）
- Node.js 与 pnpm
- MySQL（真实后端模式必需）
- 可选：LLM API Key、阿里云 OSS、Tavily Key

### 配置与安装

```powershell
# 在克隆后的项目根目录执行
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 填入真实的 MySQL、LLM 等配置；不要提交 .env
Copy-Item .env.example .env

Set-Location .\front\frontend
pnpm install --frozen-lockfile
Set-Location ..\..
```

将 `.env` 中的 `STUDY_COMPANION_DB_*` 配置为可访问的 MySQL 实例。资料问答附件还需要 `STUDY_COMPANION_OSS_*` 与 OSS Access Key。首次运行若没有本地 `models/bge-m3`，会按 `BAAI/bge-m3` 加载或下载模型。

### 启动

```powershell
# 同时启动 FastAPI（8001）与 Vite（5173）
python main.py

# 重置 demo_user 后启动，适合重复的现场演示
python main.py --reset-demo

# 仅运行后端诊断工作流 Demo
python main.py --demo

# 前端使用 Mock API
python main.py --mock-api
```

启动后访问 `http://127.0.0.1:5173`。

## 测试与质量验证

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q

# 关键流程
.\.venv\Scripts\python.exe -m pytest tests\test_diagnosis_smoke.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_material_qa_attachment_api.py -q

# 前端构建
Set-Location .\front\frontend
pnpm run build
```

测试覆盖学习目标、画像规则、诊断工作流、计划生成、资料问答检索/附件、认证 API、仓储层与演示数据重置等核心场景。

## 安全说明

`.env`、数据库密码、LLM API Key、OSS Access Key 均不得提交到版本库。生产环境应关闭开发态验证码回显、设置稳定的令牌签名密钥，并按部署地址收紧 CORS 白名单。
