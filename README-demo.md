# 体验账号与本地运行说明

## 一、体验账号

登录页直接使用以下凭据，无需注册：

| 字段 | 值 |
|---|---|
| 账号 | `demo@study.local` |
| 密码 | `demo1234` |
| 内部 user_id | `demo_user` |

说明：

- 后端认证模块（`modules/auth/`）**已实现**，服务启动时会自动确保这个体验账号存在
  （见 `modules/auth/module.py` 的 `DEMO_ACCOUNT`），账号数据落在 `data/auth/users.json`。
  只在后端没起来时，前端 `src/services/session.ts` 才降级为本地会话。
- 体验账号的 `userId` 固定为 `demo_user`，与演示数据脚本写入的数据一一对应。
  修改其中任意一处时，另一处必须同步（`src/services/session.ts` 的 `DEMO_ACCOUNT.userId` ↔ `scripts/seed_demo_data.py` 的 `DEMO_USER_ID`）。
- 首次登录后会先进入「选书与目标」引导页，选完书籍和目标即可进入今日学习。

## 二、演示前一键回到初始状态

演示过程中改了目标、做了诊断、完成了任务，下次想从干净状态开始：

```bash
# 启动服务前顺带重置（推荐，时机确定，不会在演示中途清数据）
python3.11 main.py --reset-demo

# 或者单独跑
python3.11 scripts/demo_reset.py --dry-run   # 先看会动哪些数据
python3.11 scripts/demo_reset.py             # 执行
```

清理范围严格限定在 `demo_user`：掌握度与复习安排、学习记录、学习计划、学习目标、
学习画像，以及把体验账号的昵称密码恢复成默认。**其他账号的数据按条目过滤后原样写回**，
不是把文件清空。

基线不是快照文件，而是 `scripts/seed_demo_data.py`——每次重置都重新跑一遍。
这样基线只有一个定义，而且学习事件的日期按「本周一到今天」动态生成，
放几周再演示也不会变成上个月的数据。

四条护栏：

| 护栏 | 说明 |
|---|---|
| 用户 ID 写死 | 脚本不接受「重置任意用户」的参数——能传参的删数据脚本早晚会被传错 |
| 先备份 | 动手前把涉及文件整体复制到 `data/_demo_backup/<时间戳>/` |
| 按条目过滤 | 其他账号的数据原样写回，不清空文件 |
| `DEMO_RESET_ENABLED` | 设为 `false` 整体关掉，上线时应当关掉 |

没有 `userId` 字段的历史学习计划**不会被删**——那是加归属字段之前生成的，
判断不了属于谁，删掉就是破坏别人的数据。

## 三、准备演示数据

体验账号默认是空的。执行一次种子脚本即可获得掌握度分布、到期复习项和一周的学习事件：

```bash
cd "<项目根目录>"

# 先看看会写入什么（不落盘）
python3.11 scripts/seed_demo_data.py --dry-run

# 确认无误后写入
python3.11 scripts/seed_demo_data.py
```

脚本行为：

- 只写 `user_id == demo_user` 的数据，不会触碰其他用户的记录。
- 通过项目自身的模块写入（`MemoryModule` / `LearningRecordModule`），不直接拼 JSON，
  字段结构与后端校验规则保持一致。
- 可重复执行：学习事件按 `client_request_id` 幂等，掌握度按 key upsert。
- `--reset` 会先清除 `demo_user` 已有的掌握度记忆再重写。

写入的数据涵盖：

| 知识点 | 掌握等级 | 复习状态 |
|---|---|---|
| 监督学习 | 掌握 | 9 天后复习 |
| 线性回归 | 熟悉 | 3 天后复习 |
| 模型评估 | 熟悉 | **已到期** |
| 偏差与方差 | 了解 | **已到期** |
| 正则化 | 了解 | 未安排 |
| 交叉验证 | 不会 | 未安排 |

外加 6 条学习事件（含学习时长与答题正确率），用于支撑「本周进度」卡片的统计。
事件日期按「本周一 ~ 今天」动态铺开，因此无论周几运行，6 条都会计入本周统计。

已实测的写入结果（周四运行）：本周学习 2.5 小时、正确率 64.5%（20/31）、覆盖 4 天，
其中「模型评估」和「偏差与方差」两个知识点处于**已到期待复习**状态。

**学习计划不在脚本内预置** —— 计划应当由「能力诊断 → 提交校准」的真实流程生成。
体验账号登录后走一次诊断，就能得到一份真实的计划，也顺带验证了闭环。

## 四、启动项目

```bash
cd "<项目根目录>"
python3.11 main.py
```

启动后浏览器打开 `http://127.0.0.1:5173`。停止按 `Ctrl + C`。

只想看界面、不连后端时：

```bash
cd front/frontend
VITE_USE_REAL_API=false npm run dev
```

## 五、行为变更记录（升级后请注意）

### 1. 学习画像不再决定掌握度

改动前：画像页是「勾选已掌握的知识点，未勾选的自动记为未掌握」，保存时
`MemoryModule.sync_learner_profile()` 会

- 把**所有没勾选的知识点记忆直接删除**（包括诊断测出来的），
- 给勾选的知识点写 `掌握 / score=1.0 / confidence=1.0 / 稳定保持 / 60 天`。

也就是说保存一次画像，就把诊断结论整个洗掉了。

改动后：

- 画像页改成粗粒度自评（完全没接触过 / 看过概念 / 跟着做过练习 / 能独立解决），不再逐知识点定性；
- `sync_learner_profile()` 不删任何知识点，也不覆盖已有记忆；
  只有**还没有任何记忆**的知识点才会落一条「了解 / 0.5 / 置信 0.3 / 未验证」的冷启动先验；
- 掌握度的唯一权威来源是 `ingest_diagnosis()`（诊断 + 用户校准）。

**如果你之前保存过画像**，被删掉的知识点记忆无法恢复，重跑一次诊断即可。

### 2. 后端不再接受缺 userId 的请求

`modules/diagnosis`、`modules/material_qa`、`modules/learning_record` 的请求 schema
里 `user_id` 原本默认 `"user_001"`。前端有一半接口没传 userId，于是诊断写进
`user_001`、今日学习读登录用户，**诊断完等于没发生**。

现在这些字段改成必填，前端也补齐了。副作用：早先在 `user_001` 名下产生的诊断、
计划、记录，登录体验账号后不再可见——那些数据本来就不属于这个账号。
学习计划另外加了 `userId` 归属字段，没有该字段的历史计划一律不匹配，需要重新生成。

## 六、后端待实现接口清单

前端已按契约预留调用，后端实现后无需改动前端代码。

### 认证 —— 已实现（`modules/auth/`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册，返回 `{ token, user }` |
| POST | `/api/auth/login` | 密码登录 |
| POST | `/api/auth/login-code` | 验证码登录 |
| POST | `/api/auth/send-code` | 发送验证码 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户 |
| PATCH | `/api/auth/profile` | 修改昵称等 |
| PATCH | `/api/auth/password` | 修改密码 |

实现要点：

- 密码用 PBKDF2-HMAC-SHA256 存储，每个账号一个随机盐，迭代次数随账号存储（默认 20 万次），
  `data/auth/users.json` 里不会出现任何明文密码。
- 令牌是 HMAC-SHA256 签名的 `payload.signature`，内含 user_id 与过期时间（默认 14 天），
  通过 `Authorization: Bearer <token>` 传递。篡改 payload 会被签名挡下。
- 登录失败不区分「账号不存在」和「密码错误」，统一返回 `INVALID_CREDENTIALS`，避免账号枚举；
  账号不存在时同样跑一次散列，让两种失败耗时接近。
- **状态码刻意避开 404/405/501** —— 前端把这三个码当作「接口未实现」并降级为本地会话，
  认证失败若返回 404，用户会在后端明确拒绝的情况下拿到一个本地伪造的登录态。
  因此用 401（凭据错误 / 未登录）、409（账号已存在）、400（验证码或密码强度）。

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `AUTH_TOKEN_SECRET` | 空 | 令牌签名密钥。**不设置时每次启动生成随机密钥**，重启后旧令牌全部失效。部署必须设置。 |
| `AUTH_EXPOSE_CODE` | `true` | 开发模式：验证码直接返回给前端并显示在登录页。上线设为 `false`，改由邮件/短信通道送达。 |

验证码的真实发送通道预留在 `services.py` 的 `VerificationCodeService._deliver()`，
接邮件/短信服务时只改这一个方法，`issue()` / `verify()` 的调用方不用动。

上线前仍需补的（代码注释里也标了）：用户表换数据库（当前单文件 JSON，无跨进程并发保护）、
验证码换共享存储（当前进程内存，重启即失效）、令牌加服务端撤销、加登录失败与发码频率限制。

### 书籍目录与学习目标

| 方法 | 路径 | 状态 | 说明 |
|---|---|---|---|
| GET | `/api/books` | 待实现 | 返回 `{ books: [{ id, title, shortTitle, subtitle, knowledgePointCount, available }] }` |
| POST | `/api/learner-goals` | **已实现** | 保存目标 `{ bookId, targetLevel, weeklyHours, userId }`，按 `user_id:book_id` 覆盖 |
| GET | `/api/learner-goals?userId=&bookId=` | **已实现** | 读回目标，供「选书与目标」页回填；没设过返回 `exists:false`（不是 404） |

学习目标模块在 `modules/learner_goals/`，数据落在 `data/learner_goals/goals.json`。
`weeklyHours` 会折算成每日分钟预算（按 7 天摊平），传给 `modules/learning_plan`
用于把任务顺序装箱到具体日期（见下面的「每周时长约束排课」）。

`/books` 未实现时，前端回退到本地目录，并调用已有的
`/api/learner-profile/knowledge-points?learning_domain=...` 补齐真实的知识点数量；
取不到就显示「知识点数待接口返回」，不会编造数字。

### 资料问答的通用模型降级 —— 已实现

`POST /api/rag/conversations/{id}/messages` 接收字段：

```json
{ "allowGeneralFallback": false }
```

- 默认 `false`：资料不足时照常返回 `refused: true`。
- 用户在界面上点击「用通用模型回答（无教材引用）」后，前端才会传 `true`。
- 降级作答时后端应返回 `answeredByGeneralModel: true` 且 `citations: []`。
- 该类回答不写入学习记录、不影响掌握度，延续「资料问答不修改掌握状态」的既有原则。

实现方式（`modules/material_qa/agent.py`）：

- 先按原来的「只依据教材」提示词生成。答得出来就正常返回，带引用，**不走降级**。
- 只有在教材内答不出（`refused=true`）**且**本次请求带了 `allowGeneralFallback=true` 时，
  才发第二次请求，换成一套明确说「教材里没有依据，请用通用知识回答、不要编造章节引用」的提示词。
  正常有出处的问答仍然只有一次模型调用。
- 降级回答强制 `citations: []`、`relatedKnowledgePoints: []`：这条回答没有教材出处，给引用就是造假；
  掌握度只由诊断和练习产生，通用回答不应影响任何知识点的判断。
- 回答正文会带上「以下内容来自通用模型，未在当前教材中找到依据」的前缀，
  这样即使内容被复制出去、脱离了前端标注，也仍然能看出未经核对。

后端未实现该字段时（例如回退到旧版本），前端会再次收到 `refused: true`，并如实提示
「后端暂不支持通用模型回答」，不会静默失败。

### 待办 1：`/learning-events` 无法携带时长与正确率（会导致本周进度恒为 0）

`modules/learning_record/module.py` 的 `record_learning_event()` 把 `result` 写死成：

```python
result={"task_status": status, "task_status_label": display_status}
```

但 `today_learning._weekly_progress()` 统计时读的是另外三个字段：

```python
activity.result.get("duration_seconds")
activity.result.get("correct_count")
activity.result.get("total_count")
```

两边对不上，所以**真实使用中「本周进度」的学习时长和正确率会永远是 0**
（前端已经改成读后端真值，这个后端缺口就直接暴露出来了）。

修法：`record_learning_event()` 增加 `duration_seconds` / `correct_count` / `total_count`
入参并写进 `result`，前端 `writeLearningEvent` 同步带上这几个字段。
在此之前，种子脚本绕开该方法、直接用官方 `LearningActivity` 模型 + 校验器落库，
所以体验账号的统计是有数的。

### 待办 2：能力图谱读的是诊断快照，不是实时掌握度

`today_learning._knowledge_graph()` 只从「该书最近一次诊断活动的结果快照」取节点，
因此：完成任务后掌握度变了图谱不动；没做过诊断的书籍图谱整个为空。
建议改为读实时 `LearnerMemory`，并把该书全部知识点都渲染出来
（没测过的显示为「未评估」灰色节点），前端的图例和空态已经准备好了。

### 每周学习时长约束排课 —— 已实现

`LearningPlanModule._apply_time_budget()` 按每日分钟预算把任务顺序装箱到具体日期，
写进每个任务的 `expectedCompletionDate`，并在 `plan.timeBudget` 里给出
`{dailyMinutes, totalMinutes, estimatedDays}`。

三条刻意的边界：

- **不删任务、不压缩时长**。计划内容由诊断结果决定，时间预算只决定它摊多少天完成。
- 单个任务本身就超过一天预算时独占一天，不切碎。
- 单任务时长上限取「学习画像里的单次时长偏好」和「每日预算」的较小值。

### 实际用时校准排课节奏 —— 已实现

`LearningPlanModule.pace_factor(user_id, book_id)` 从学习记录里取最近 10 条完成事件的
「实际用时 / 计划用时」**中位数**，作为排课的速度校准倍数。

| 决定 | 理由 |
|---|---|
| 用中位数，不用总和之比 | 总和之比会被一两个特别长的任务主导；中位数对误填的 24 小时和偶发的通宵更稳 |
| 少于 3 条样本不校准 | 两条记录不构成规律，那是噪声 |
| 倍数夹在 [0.5, 3.0] | 一次误填不该把后面所有排课毁掉 |
| 只看最近 10 条 | 速度会随熟练度变化，半年前的记录不代表现在 |
| **不把校准值写回任务的 minutes** | 写回去以后下一轮算「计划 vs 实际」比值会自动趋近 1，校准把自己的输入抹掉，越校越准是假象。任务显示的分钟数始终是 AI 的原始估计，校准只作用于装箱时的占用计算 |

结果放在 `plan.timeBudget.paceFactor` 和 `adjustedTotalMinutes`，前端在计划页显示
「你最近的实际用时约为计划的 X 倍，排课已按这个速度放慢」。倍数落在 0.9–1.1 之间视为估得准，不提示。

### 自动重排 —— 已实现

`LearningPlanModule.reschedule(user_id, book_id)` 按最新的每周时长和速度校准，
重排在途计划里**还没完成**的任务日期。两个触发点：

| 触发 | 行为 |
|---|---|
| `POST /api/learner-goals` 且**每周时长变了** | 立刻重排，响应带回 `rescheduled` / `estimatedDays` |
| `POST /api/learning-events` 完成一个任务 | 用新的用时样本重算速度并重排剩余任务，响应带回 `planRescheduled` |

边界（都是刻意的）：

- **只改日期，不动任务内容、不调模型、不碰已完成的任务**，所以自动做是安全的。
- **目标水平变了不自动重生成任务**。任务内容确实该跟着目标水平变，但重新生成会丢掉
  当前计划的完成进度，属于有损操作，所以只返回 `planRefreshSuggested: true`，
  由前端提示用户「重做一次诊断能得到更贴合的任务」，让用户自己决定。
- 排课说明用固定前缀标识并每次重写，重排 N 次也只会有一条，不会越积越多。

### 任务时长跟随「单次学习时长」偏好 —— 已实现

以前 `_minutes_for()` 写死 25/20/15 分钟，跟用户选的单次时长完全无关，
所以不管选 30 分钟还是 2 小时，排出来的任务都是二十几分钟。

现在以画像里的单次时长偏好为基准，按掌握程度缩放：

| 掌握状态 | 占单次时长的比例 | 偏好 30 分钟 | 偏好 2 小时 |
|---|---|---|---|
| 不会 / 了解 | 100% | 30 分钟 | 120 分钟 |
| 熟悉 | 75% | 25 分钟 | 90 分钟 |
| 掌握 | 50% | 15 分钟 | 60 分钟 |

单次时长档位是 **15 / 30 / 45 / 60 / 90 / 120**，定义在
`modules/learner_profile/field_rules.py` 的 `SESSION_DURATION_CHOICES`，
前端渲染同一份列表，`tests/test_profile_contract.py` 强制两边不许漂移。

另外 `_max_task_minutes()` **不再用每日预算给单个任务封顶**：
每日预算决定任务摊几天做完，不决定一次坐下来学多久。
一个 120 分钟的任务遇上 40 分钟的日预算，会由排课独占一天，而不是被砍成 40 分钟。
单任务硬顶 2 小时——再长应该拆成两个任务。

### 待办：更细的排课

现在是「按天顺序摊平」，没有考虑用户在画像里选的学习频率（每天 / 每周三四次 / 偶尔），
也没有跳过休息日。要做得更准，需要把 `preferences.learning_frequency` 一并纳入装箱。
