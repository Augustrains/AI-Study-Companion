# 诊断模块接口文档

## 1. 模块说明

诊断模块用于完成一次学习诊断：启动诊断、获取题目、逐题提交答案、生成诊断结果，以及让用户校准诊断结果。

本文档仅用于说明前后端交互，不参与后端运行，也不会被代码自动读取。

接口前缀：无。以下 URL 均为应用根路径下的绝对路径，例如：

```text
POST /api/diagnostics/start
```

## 2. 推荐调用流程

```text
启动诊断
  ↓
循环提交每道题的答案
  ↓
完成诊断并获取分析结果
  ↓
（可选）提交用户对诊断结果的校准
```

## 3. 接口列表

| 接口 | 方法 | 作用 |
|---|---|---|
| `/api/diagnostics/start` | POST | 启动一次诊断并返回题目 |
| `/api/diagnostics/{diagnostic_id}/answers` | POST | 提交一道题的答案 |
| `/api/diagnostics/{diagnostic_id}/finish` | POST | 完成诊断并生成诊断结果 |
| `/api/learner-calibrations` | POST | 提交用户对诊断结果的校准 |

---

## 4. 启动诊断

### 请求

```http
POST /api/diagnostics/start
Content-Type: application/json
```

请求体：

| 字段 | 类型 | 必填 | 默认值 | 含义 | 约束 |
|---|---|---:|---|---|---|
| `bookId` | string | 是 | - | 题库或课程 ID | 不能为空 |
| `learningGoal` | string | 否 | `""` | 用户的学习目标 | 最长 200 个字符 |
| `userId` | string | 否 | `"user_001"` | 用户 ID | 不能为空 |

示例：

```json
{
  "bookId": "ml",
  "learningGoal": "掌握机器学习基础",
  "userId": "user_001"
}
```

目前 `ml` 会映射到 `ml-001` 机器学习题库，`dl` 会映射到 `dl-001` 深度学习题库；其他值直接作为题库 ID 使用。

### 成功响应：200

```json
{
  "diagnosticId": "diag_a1b2c3d4e5",
  "questions": [
    {
      "id": "q_001",
      "title": "以下哪项最能描述监督学习？",
      "tag": "supervised_learning",
      "options": [
        {
          "id": "a",
          "text": "使用带标签的数据进行学习"
        },
        {
          "id": "b",
          "text": "完全不使用数据标签"
        }
      ]
    }
  ]
}
```

响应字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `diagnosticId` | string | 本次诊断会话 ID，后续提交答案和完成诊断时使用 |
| `questions` | array | 诊断题目列表 |
| `questions[].id` | string | 题目 ID |
| `questions[].title` | string | 题目标题 |
| `questions[].tag` | string | 题目所属知识点标签 |
| `questions[].options` | array | 题目选项 |
| `questions[].options[].id` | string | 选项 ID，提交答案时传这个值 |
| `questions[].options[].text` | string | 选项文本 |

注意：正确答案不会返回给前端。

---

## 5. 提交诊断答案

### 请求

```http
POST /api/diagnostics/{diagnostic_id}/answers
Content-Type: application/json
```

路径参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `diagnostic_id` | string | 启动诊断时返回的诊断 ID |

请求体：

| 字段 | 类型 | 必填 | 默认值 | 含义 | 约束 |
|---|---|---:|---|---|---|
| `questionId` | string | 是 | - | 当前题目 ID | 不能为空 |
| `answer` | string | 否 | `""` | 选择的选项 ID | 最长 200 个字符；未跳过时必须是该题的有效选项 |
| `skipped` | boolean | 否 | `false` | 是否跳过该题 | `true` 时答案按空值保存 |

示例：

```http
POST /api/diagnostics/diag_a1b2c3d4e5/answers
```

```json
{
  "questionId": "q_001",
  "answer": "a",
  "skipped": false
}
```

### 成功响应：200

```json
{
  "diagnosticId": "diag_a1b2c3d4e5",
  "questionId": "q_001",
  "saved": true
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `diagnosticId` | string | 诊断 ID |
| `questionId` | string | 已提交的题目 ID |
| `saved` | boolean | 是否保存成功 |

---

## 6. 完成诊断

### 请求

```http
POST /api/diagnostics/{diagnostic_id}/finish
```

路径参数：

| 参数 | 类型 | 含义 |
|---|---|---|
| `diagnostic_id` | string | 启动诊断时返回的诊断 ID |

该接口不需要请求体。调用前，前端应先提交需要保存的题目答案。

### 成功响应：200

```json
{
  "level": "intermediate",
  "accuracy": "75%",
  "confidence": "high",
  "evidence": "用户在基础概念题上的表现较好。",
  "answerPerformance": "已回答题目中大部分正确。",
  "generatedAt": "2026-08-11T10:30:00+08:00",
  "relatedScope": "掌握机器学习基础及其前置知识点。"
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `level` | string | 诊断出的学习水平 |
| `accuracy` | string | 答题准确率，带百分号 |
| `confidence` | string | 诊断置信度 |
| `evidence` | string | 支撑诊断结论的证据 |
| `answerPerformance` | string | 对答题表现的文字总结 |
| `generatedAt` | string | 结果生成时间，ISO 8601 格式 |
| `relatedScope` | string | 本次诊断涉及的知识范围 |

完成后，诊断会话进入等待审核状态。最终结果通常还需要调用“提交用户校准”接口确认。

---

## 7. 提交用户校准

### 请求

```http
POST /api/learner-calibrations
Content-Type: application/json
```

请求体：

| 字段 | 类型 | 必填 | 默认值 | 含义 | 可选值/约束 |
|---|---|---:|---|---|---|
| `diagnosticId` | string | 是 | - | 要校准的诊断 ID | 不能为空 |
| `level` | string | 是 | - | 用户认为系统诊断水平的相对高低 | `lower`、`same`、`higher` |
| `reason` | string | 否 | `""` | 用户校准的原因 | 最长 500 个字符 |

`level` 的含义：

| 值 | 含义 |
|---|---|
| `lower` | 系统评估结果偏高，用户认为自己的水平更低 |
| `same` | 系统评估结果基本准确 |
| `higher` | 系统评估结果偏低，用户认为自己的水平更高 |

示例：

```json
{
  "diagnosticId": "diag_a1b2c3d4e5",
  "level": "same",
  "reason": "诊断结果与我的实际学习情况基本一致。"
}
```

### 成功响应：200

```json
{
  "diagnosticId": "diag_a1b2c3d4e5",
  "saved": true
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `diagnosticId` | string | 被校准的诊断 ID |
| `saved` | boolean | 是否保存成功 |

---

## 8. 通用错误响应

应用会将错误统一返回为以下结构：

```json
{
  "code": "REQUEST_VALIDATION_ERROR",
  "message": "request validation failed",
  "retryable": false,
  "details": {}
}
```

常见错误：

| HTTP 状态码 | `code` | 说明 |
|---:|---|---|
| 400 | `VALIDATION_ERROR` | 参数通过接口格式校验，但不符合业务规则，例如答案不属于当前题目选项 |
| 404 | `RESOURCE_NOT_FOUND` | 诊断会话或题目不存在 |
| 409 | `WORKFLOW_STATE_ERROR` / `CONFLICT` | 当前诊断状态不允许执行该操作 |
| 422 | `REQUEST_VALIDATION_ERROR` | 请求体未通过 Pydantic 接口字段校验 |
| 500 | `APP_ERROR` 或其他服务端错误码 | 服务端内部错误 |
| 502 | `EXTERNAL_SERVICE_ERROR` | 外部服务调用失败 |

`retryable: true` 表示客户端可以考虑稍后重试；参数错误通常不应直接重试。

## 9. 字段命名约定

接口 JSON 使用小驼峰命名，例如 `diagnosticId`、`questionId`、`answerPerformance`；后端 Python 代码内部使用蛇形命名，例如 `diagnostic_id`、`question_id`、`answer_performance`。
