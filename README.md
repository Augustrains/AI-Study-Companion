# Study Companion

一个最小可运行的自适应学习伴学 Demo。当前实现了基于 LangGraph 的诊断工作流，并在两个位置支持暂停和恢复：

```text
加载题目 → 等待用户答题 → 评分 → 生成解释 → 等待用户确认 → 保存 LearningSession
```

用户确认诊断时可以：

- `approve`：接受诊断结果并保存；
- `edit`：校准一个或多个知识点状态后保存；
- `reject`：拒绝本次诊断，不更新学习状态。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 分层

```text
agents/          Agent 能力，目前使用本地模板生成解释
data/materials/  学习资料 PDF
data/questions/  正式题库 JSON
domain/          领域模型和确定性评分规则
repositories/    题库、学习会话数据访问
sdk/             LLM 等基础能力接口
workflows/       LangGraph 状态、图定义和工作流门面
```

`LearningSession` 保存长期业务状态；LangGraph Checkpointer 保存某次工作流的执行状态。当前 Demo 使用 `InMemorySaver`，生产环境应替换为数据库支持的持久化 Checkpointer。
