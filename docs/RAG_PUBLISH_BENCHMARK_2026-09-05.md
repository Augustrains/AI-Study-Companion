# RAG 发布与查询基准记录（2026-09-05）

## 目的

验证版本化增量发布是否能减少重复 embedding，并确认活动版本、查询租约与稳定引用不会造成
不可接受的查询延迟。

## 环境与方法

- 执行脚本：`scripts/benchmark_rag_publish.py`
- Qdrant：内存模式（隔离，不读取或修改本地运行数据）
- 合成资料：12 篇已批准的规范化教材单元
- 连续发布次数：3 次，内容完全相同
- 文档 embedding 延迟模拟：8ms / 文本
- 查询 embedding 延迟模拟：2ms / 请求
- 每种查询路径各执行 30 次；记录 P50 与 P95。

执行命令：

```powershell
.venv\Scripts\python.exe scripts\benchmark_rag_publish.py `
  --documents 12 --repeats 3 --embedding-delay-ms 8 --query-delay-ms 2
```

## 最终结果

| 指标 | 旧式固定 collection / 全量发布模拟 | 当前版本化增量发布 |
|---|---:|---:|
| 发布阶段 embedding 文本数 | 75 | 25 |
| 三次发布总耗时 | 9.354s | 0.278s |
| 查询 P50 | 2.76ms | 3.08ms |
| 查询 P95 | 3.43ms | 3.33ms |
| 无变化发布 | 每次全量重建 | 后两次跳过 |
| 并发发布 | 无保护 | 返回冲突，阻止并发构建 |
| 教材引用 | 无版本字段 | 返回 `indexVersion` |

## 发现与修正

首次版本化实现的查询 P95 约为 33ms，明显高于旧式基线。原因是每次查询都为 lease 读写
`material_index_registry.json`，产生同步磁盘 I/O。

已修正为：

- 活动版本与 manifest 仍持久化到注册表；
- 查询 lease 改为进程内短生命周期计数；
- `QdrantVectorStore` 按 collection 缓存复用。

修正后新版 P95 为 3.33ms，与旧式 3.43ms 基线持平，同时保留安全发布能力。

## 结论与边界

该结果证明发布链路的去重、发布锁和查询路径优化在受控环境中生效，但不代表生产 HTTP
延迟：测试未覆盖真实 BGE 模型加载、FastAPI、MySQL、磁盘 Qdrant 或多进程部署。

下一次评测应使用 [RAG_LOAD_TESTING.md](RAG_LOAD_TESTING.md) 的 Locust 场景，在独立 staging
数据目录执行，并记录 QPS、HTTP P50/P95/P99、5xx、409、CPU/内存和 Qdrant 磁盘占用。
