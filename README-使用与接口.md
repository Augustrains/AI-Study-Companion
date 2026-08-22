# 使用与接口说明

这份文档回答三个问题：**改动在哪、怎么用、有哪些接口**。

项目里另外两份文档的分工：

| 文件 | 内容 |
|---|---|
| `README.md` | 原有的安装、分层说明 |
| `README-demo.md` | 体验账号、演示数据、行为变更记录、后端待办 |
| `README-使用与接口.md`（本文） | 文件地图、日常操作命令、完整接口清单 |

---

## 一、改动都在哪

**没有单独的文件夹——所有改动都直接落在项目原有目录里**，按模块归位。下面是这一轮新增和改过的全部文件。

### 新增模块

| 路径 | 作用 |
|---|---|
| `modules/auth/` | 认证：注册、密码/验证码登录、令牌、账号资料。7 个文件 |
| `modules/learner_goals/` | 学习目标：目标水平 + 每周投入时长，排课的输入之一。5 个文件 |
| `modules/learning_resources/` | 知识点延伸学习资源（视频/公开课链接） |

### 新增脚本与测试

| 路径 | 作用 |
|---|---|
| `scripts/demo_reset.py` | 把体验账号恢复到演示基线（只影响 `demo_user`） |
| `scripts/seed_demo_data.py` | 演示数据基线的唯一定义 |
| `tests/test_diagnosis_smoke.py` | 诊断端到端冒烟（真跑 LangGraph） |
| `tests/test_business_rules.py` | 目标 / 排课 / 出题兜底 / 画像语义 |
| `tests/test_profile_contract.py` | 前端选项 ↔ 后端校验规则 契约测试 |
| `tests/test_demo_reset.py` | 重置脚本，重点验「其他账号数据一条不少」 |
| `tests/test_auth_api.py` | 认证 + 学习资源接口 |

### 改动过的后端文件

| 路径 | 改了什么 |
|---|---|
| `modules/diagnosis/workflow.py` | 补上漏传的 `answered_question_ids` / `diagnosis_round`（诊断起不来的根因） |
| `modules/diagnosis/services.py` | 出题改「轮转发牌」保证覆盖面；提示词加入复测上下文；复测优先出新题 |
| `modules/diagnosis/agent.py` | 模型不可用时回退规则出题计划，不再让诊断整体 502 |
| `modules/diagnosis/schemas.py` | `user_id` 改必填 |
| `modules/learning_plan/module.py` | 计划按用户归属；每周时长约束排课；实际用时校准节奏；任务时长跟随单次时长偏好 |
| `modules/learning_plan/api.py` `schemas.py` | 接口补 `userId` |
| `modules/learner_profile/field_rules.py` | 单次时长档位扩到 6 档；不再把未勾选的知识点写成「未掌握」 |
| `modules/memory/module.py` | 画像不再删除/覆盖诊断得到的掌握度 |
| `modules/material_qa/*` | 通用模型降级（`allowGeneralFallback`） |
| `modules/learning_record/*` | 学习事件带上时长；完成任务后重排剩余任务 |
| `api/server.py` `bootstrap/application.py` | 注册新模块与依赖 |
| `main.py` | 新增 `--reset-demo` |

### 改动过的前端文件

全部在 `front/frontend/src/`：

| 路径 | 改了什么 |
|---|---|
| `App.tsx` | 登录门禁、侧边栏退出、帮助中心、实际用时上限、计划时间预算、真实数据绑定 |
| `services/api.ts` | 全部接口补 `userId`；写操作不再静默降级；学习目标读写 |
| `services/session.ts` | 会话与认证层，后端缺失时降级为本地会话 |
| `components/AuthView.tsx` | 登录注册页 |
| `components/GoalsSetupView.tsx` | 选书与目标，支持回填 |
| `components/LearnerProfileView.tsx` | 学习画像改为学习前自述 |
| `components/HelpCenter.tsx` | 帮助中心「怎么用」 |
| `components/LearningResources.tsx` | 学习资源 |
| `components/SettingsView.tsx` | 设置 |
| `theme-skyglass.css` | 天蓝玻璃质感主题，22 个小节 |

---

## 二、怎么用

### 启动

```bash
cd "<项目根目录>"
python3.11 main.py
```

前端 `http://127.0.0.1:5173`，后端 `http://127.0.0.1:8000`。停止按 `Ctrl + C`。

**演示前想回到干净状态**：

```bash
python3.11 main.py --reset-demo
```

只清 `demo_user`，其他账号一条不动。细节见 `README-demo.md` 第二节。

只看界面、不连后端：

```bash
cd front/frontend
VITE_USE_REAL_API=false npm run dev
```

### 登录

| 字段 | 值 |
|---|---|
| 账号 | `demo@study.local` |
| 密码 | `demo1234` |

也可以用验证码登录：切到「使用验证码登录」→ 点「获取验证码」。开发模式下验证码直接显示在页面提示条并自动填入，后端终端也会打印一行。

### 跑测试

```bash
python3.11 tests/test_diagnosis_smoke.py    # 16 项
python3.11 tests/test_profile_contract.py   # 18 项
python3.11 tests/test_demo_reset.py         # 23 项
python3.11 tests/test_auth_api.py           # 40 项
python3.11 tests/test_business_rules.py     # 74 项
```

五个套件都不需要 API key、不需要 qdrant、不需要 embedding 模型。缺 `httpx` 的话
`python3.11 -m pip install httpx`。

### 排查问题

```bash
# 留一份完整日志（进度输出和报错都在里面）
python3.11 main.py 2>&1 | tee backend.log

# 绕过 HTTP 直接调诊断，报错是完整未截断的 traceback
python3.11 -c "
from bootstrap.application import build_diagnosis_workflow
workflow, _ = build_diagnosis_workflow()
print('题目数：', len(workflow.start_diagnosis(user_id='demo_user', book_id='ml-001', learning_goal='能够独立完成基础练习')['questions']))
"

# 改过 Python 文件但行为没变时，清一次字节码缓存再重启
find modules scripts -name __pycache__ -exec rm -rf {} + 2>/dev/null
```

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `AUTH_TOKEN_SECRET` | 空 | 令牌签名密钥。**不设置时每次启动生成随机密钥**，重启后旧令牌全部失效。部署必须设置 |
| `AUTH_EXPOSE_CODE` | `true` | 开发模式验证码直接回给前端。上线设 `false`，改由邮件/短信送达 |
| `DEMO_RESET_ENABLED` | `true` | 设 `false` 关掉体验账号重置入口。上线应当关掉 |
| `STUDY_COMPANION_DATA_DIR` | `<项目>/data` | 数据目录 |
| `STUDY_COMPANION_LLM_API_KEY` 等 | 见 `.env.example` | 模型配置。模型不可用时诊断会退回规则出题，不会整体挂掉 |

---

## 三、接口清单

全部以 `/api` 为前缀，返回 JSON 用 camelCase。错误统一为
`{ code, message, retryable, details }`。

> **状态码约定（重要）**：前端把 **404 / 405 / 501** 当作「接口未实现」并自动降级为本地模拟。
> 因此业务失败**绝不能**返回这三个码——认证失败用 401，冲突用 409，字段错误用 400/422，
> 「查不到」用 `200 + {exists: false}`。

### 认证 `modules/auth/`

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/auth/register` | `{nickname, account, password}` | `{token, user, expiresAt}` |
| POST | `/auth/login` | `{account, password}` | 同上 |
| POST | `/auth/login-code` | `{account, code}` | 同上 |
| POST | `/auth/send-code` | `{account, scene}` | `{sent, devCode, delivery}` |
| POST | `/auth/logout` | — | 204 |
| GET | `/auth/me` | Header `Authorization: Bearer` | `{userId, nickname, account, createdAt}` |
| PATCH | `/auth/profile` | `{nickname?, avatarColor?}` | 同上 |
| PATCH | `/auth/password` | `{currentPassword, newPassword}` | 204 |

密码用 PBKDF2-HMAC-SHA256（每账号随机盐，20 万次迭代）；令牌是 HMAC-SHA256 签名的
`payload.signature`，默认 14 天。登录失败不区分「账号不存在」和「密码错误」。

### 学习目标 `modules/learner_goals/`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/learner-goals` | `{bookId, targetLevel, weeklyHours, userId}`。每周时长变了会**自动重排**在途计划，响应带 `rescheduled` / `estimatedDays` / `planRefreshSuggested` |
| GET | `/learner-goals?userId=&bookId=` | `{exists, goal}`。没设过返回 `exists:false`，不是 404 |

`weeklyHours ÷ 7` 得到每日分钟预算，供排课使用。

### 能力诊断 `modules/diagnosis/`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/diagnostics/start` | `{bookId, learningGoal, userId}` → `{diagnosticId, questions}`。**只有这一步认人**，后续按 diagnosticId 找回同一用户 |
| POST | `/diagnostics/{id}/answers` | `{questionId, answer, skipped}`，一题一存 |
| POST | `/diagnostics/{id}/finish` | 返回 AI 评估摘要 |
| POST | `/learner-calibrations` | `{diagnosticId, level, reason}`，用户校准与 AI 判断分开保存 |

出题：题量在多个知识点间**轮转发牌**保证覆盖面；复测优先出没做过的题，题池用尽才回收；
模型不可用时退回规则计划，诊断照常能跑。

### 学习计划 `modules/learning_plan/`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/learning-plans?bookId=&userId=&diagnosticId=` | `{exists, plan}`，按用户过滤 |
| POST | `/learning-plans/generate` | `{diagnosticId, bookId, goal, userId}`。计划归属跟随诊断 |
| POST | `/learning-plans/material` | 把资料问答的来源变成一个正式任务 |

计划里的 `timeBudget`：

```json
{ "dailyMinutes": 43, "totalMinutes": 240, "estimatedDays": 6,
  "paceFactor": 1.8, "adjustedTotalMinutes": 432 }
```

`paceFactor` 是最近 10 条完成记录里「实际 ÷ 计划」的中位数。**任务自己的 minutes 始终是
AI 的原始估计，不会被校准值改写**——改写会让下一轮比值自动趋近 1，校准把自己的输入抹掉。

### 学习记录 `modules/learning_record/`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/learning-events` | `{taskId, eventType, status, durationSeconds, plannedMinutes, userId}`。完成任务后用新样本重排剩余任务，响应带 `planRescheduled` |
| GET | `/learning-records?userId=&category=&page=&pageSize=` | 分页流水 |
| GET | `/learning-records/{activityId}` | 单条详情 |

### 学习画像 `modules/learner_profile/`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/learner-profile?user_id=&learning_domain=` | 读画像 |
| GET | `/learner-profile/knowledge-points?learning_domain=` | 知识点目录 |
| POST | `/learner-profile/workflows` | 保存画像 |
| POST | `/learner-profile/workflows/{id}/review` | 校正后确认 |

**画像 = 学习前的自述**：只收粗粒度自评和偏好，不逐个知识点定性。
掌握度只由「诊断 + 用户校准」产生。单次学习时长档位定义在
`field_rules.py` 的 `SESSION_DURATION_CHOICES = {15,30,45,60,90,120}`，
前端渲染同一份列表，`tests/test_profile_contract.py` 强制两边不许漂移。

### 今日学习 `modules/today_learning/`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/today-learning?userId=&bookId=` | 今日任务、推荐、本周进度、能力图谱 |

### 资料问答 `modules/material_qa/`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/rag/conversations` | `{bookId, userId}` → 新会话 |
| POST | `/rag/conversations/{id}/messages` | `{bookId, question, userId, allowGeneralFallback}` |
| POST | `/rag/ask` | 同上，没有会话时自动建一个 |

教材里找不到依据时返回 `refused: true`。用户显式点「用通用模型回答」后才带
`allowGeneralFallback: true`，此时后端换一套提示词重答，返回
`answeredByGeneralModel: true` 且 `citations: []`——没出处就不给引用，也不影响掌握度。

### 学习资源 `modules/learning_resources/`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/learning-resources?knowledgePointIds=a,b` | 不传则返回全部已收录知识点 |

数据在 `data/learning_resources/resources.json`，14 个知识点 / 40 条链接，全部核实过可访问。
未收录的知识点返回空列表，由前端展示空态，不编造链接。

---

## 四、还没做的

按优先级：

1. **能力图谱读的是诊断快照，不是实时掌握度**。完成任务后掌握度变了图谱不动；没做过诊断的书籍图谱整个为空。应改为读实时 `LearnerMemory`。
2. **排课没考虑学习频率**。现在按天顺序摊平，没用上画像里选的「每天 / 每周三四次 / 偶尔」，也不跳休息日。
3. **资料问答只有单会话**。「清空对话」就是清空——会话只存在后端进程内存里，没有列表接口，也没有回到旧对话的入口。要做多会话需要：会话持久化 + 列表接口 + 侧栏切换。
4. **改目标水平不自动重排任务内容**。只重排日期，任务内容要重做一次诊断才会变——重新生成会清掉当前进度，所以留给用户决定。
5. **认证是演示级**。用户表是单文件 JSON（无并发保护）、验证码在进程内存（重启失效）、令牌无法撤销、没有登录失败与发码频率限制。上线前必须补。
