# RAG 发布与查询压测

使用 Locust 对“高并发查询 + 低频重复发布”进行混合压测。请只在 staging 或使用独立
`STUDY_COMPANION_DATA_DIR` 的环境执行；不要对日常使用中的本地资料目录压测。

在启动 HTTP 服务前，可先运行隔离的发布基准，比较旧式重复全量 embedding 与当前增量发布：

```powershell
.venv\Scripts\python.exe scripts\benchmark_rag_publish.py --documents 12 --repeats 3
```

该基准使用内存 Qdrant 与合成教材，不读取或修改本地 Qdrant。它验证无变化发布是否跳过、
并发发布是否被拒绝，以及查询引用是否含版本号。

```powershell
.venv\Scripts\python.exe -m pip install locust
.venv\Scripts\locust.exe -f load_tests\locustfile.py --host http://127.0.0.1:8000
```

推荐先以 20 个用户、每秒新增 2 个用户运行 5 分钟，再逐步提升。读请求与发布请求比例约为
20:1。发布测试针对 `ml`：资料未变化时应返回成功且报告状态为 `skipped_no_changes`；并发
发布时，除一个任务外其余应返回 HTTP 409，而不能同时写入多个活动版本。

验收指标：

- `rag_ask` 没有 5xx，P95 延迟不应因发布而明显恶化；
- 同一时刻只有一个 `ml` 构建任务成功进入构建区；
- 重复发布不增加新 collection，不触发新的 embedding；
- 发布成功后读取的 citation 含 `indexVersion`；
- registry 中旧版本保持 `retired`，而非被删除。
