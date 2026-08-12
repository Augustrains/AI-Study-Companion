# 资料问答 API

当前实现：会话和消息只保存在 `MaterialQaWorkflow` 的运行时内存中，服务重启后清空；PDF 检索由 LlamaIndex + Qdrant + embedding 模型完成，检索结果再传给 Agent。

## 0. 创建会话

- 操作：项目启动时创建资料问答会话
- URL：`POST /api/rag/conversations`

### 输入字段

| 英文字段 | 中文含义 | 类型 | 必填 |
|---|---|---|---:|
| `bookId` | 书籍 ID | string | 是 |
| `userId` | 用户 ID | string | 否 |

### 输出字段

| 英文字段 | 中文含义 | 类型 |
|---|---|---|
| `conversationId` | 会话 ID | string |
| `bookId` | 书籍 ID | string |
| `userId` | 用户 ID | string |
| `createdAt` | 创建时间 | string |
| `status` | 会话状态 | string |

## 1. 在会话中提问

- 操作：提交一轮用户问题，并返回 Agent 回答
- URL：`POST /api/rag/conversations/{conversationId}/messages`

### 输入字段

| 英文字段 | 中文含义 | 类型 | 必填 |
|---|---|---|---:|
| `conversationId` | URL 中的会话 ID | string | 是 |
| `bookId` | 书籍 ID | string | 是 |
| `question` | 用户问题 | string | 是 |
| `userId` | 用户 ID | string | 否 |
| `sourceIds` | 指定资料来源 ID | string[] | 否 |

### 输出字段

| 英文字段 | 中文含义 | 类型 |
|---|---|---|
| `answer` | Agent 回答内容 | string |
| `citations` | 资料引用列表 | object[] |
| `relatedKnowledgePoints` | 关联知识点 | string[] |
| `recommendedAction` | 推荐下一步操作 | string |
| `conversationId` | 会话 ID | string |
| `requestId` | 请求追踪 ID | string |

本接口每次会将当前会话中已有的历史消息和本轮问题一起传给 Agent，并保存 user、assistant 两条消息。

## 2. 兼容接口：提交问题

- 操作：发送资料问答
- URL：`POST /api/rag/ask`

说明：未传 `conversationId` 时会临时创建会话；新前端应优先使用“创建会话”和“在会话中提问”两个接口。

### 输入字段

| 英文字段 | 中文含义 | 类型 | 必填 |
|---|---|---|---:|
| `bookId` | 书籍 ID | string | 是 |
| `question` | 用户问题 | string | 是 |
| `userId` | 用户 ID | string | 否 |
| `conversationId` | 对话 ID，用于连续追问 | string | 否 |
| `sourceIds` | 指定资料来源 ID | string[] | 否 |

### 输入示例

```json
{
  "bookId": "ml",
  "question": "如何判断模型出现了过拟合？",
  "userId": "user_001",
  "conversationId": "qa-existing-001",
  "sourceIds": ["ml-s1", "ml-s2"]
}
```

### 输出字段

| 英文字段 | 中文含义 | 类型 |
|---|---|---|
| `answer` | AI 回答内容 | string |
| `citations` | 资料引用列表 | object[] |
| `citations[].id` | 引用 ID | string |
| `citations[].type` | 资料类型，如教材、讲义 | string |
| `citations[].title` | 资料标题 | string |
| `citations[].location` | 资料位置，如页码、章节 | string |
| `citations[].excerpt` | 资料摘要 | string |
| `relatedKnowledgePoints` | 关联知识点 | string[] |
| `recommendedAction` | 推荐下一步操作 | string |
| `conversationId` | 对话 ID | string |
| `requestId` | 请求追踪 ID | string |

### 输出示例

```json
{
  "answer": "如果训练误差持续降低，而验证误差开始升高，通常说明模型出现了过拟合。",
  "citations": [
    {
      "id": "ml-s1",
      "type": "教材",
      "title": "第 4 章 · 模型评估",
      "location": "P.118",
      "excerpt": "验证集用于模型选择和超参数调整。"
    }
  ],
  "relatedKnowledgePoints": ["偏差与方差", "模型评估"],
  "recommendedAction": "建议查看验证集误差曲线。",
  "conversationId": "qa-001",
  "requestId": "req-001"
}
```

## 2. 错误输出

| 英文字段 | 中文含义 | 类型 |
|---|---|---|
| `code` | 错误码 | string |
| `message` | 错误信息 | string |
| `requestId` | 请求追踪 ID | string |
| `retryable` | 是否允许重试 | boolean |
| `details` | 错误详情 | object |

```json
{
  "code": "QA_TEMPORARY_ERROR",
  "message": "资料问答暂时不可用，请稍后重试。",
  "requestId": "req-001",
  "retryable": true,
  "details": {}
}
```
