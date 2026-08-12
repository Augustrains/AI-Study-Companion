# I03：RAG 资料导入

## 人工输入

```text
资料文件
+ 书籍 ID
+ 版本
+ 目录/章节
+ 允许的使用范围
+ 能力与知识点标签
```

## 技术处理

```text
文件解析
→ 按章节与语义切分
→ 每个片段写入 source_id、book_id、chapter_id、ability_id、knowledge_point_id、版本和位置
→ 建立检索索引
→ 抽样验证检索与引用
```

## 输出契约

每个片段至少包含：

```text
chunk_id、content、source_id、book_id、chapter_id、ability_id、knowledge_point_id、source_location、version
```

## 人工审核接口（后续后台）

- 上传/下架资料。
- 编辑章节、能力、知识点标签。
- 查看切分片段与来源位置。
- 标记可引用/不可引用片段。
- 查看检索失败和用户反馈。
