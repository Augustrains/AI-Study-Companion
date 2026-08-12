# Study Companion

基于 LangGraph 和 FastAPI 的自适应学习伴学 Demo。

## 安装与运行

```powershell
python -m pip install -r requirements.txt
python main.py
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 项目分层

```text
api/                         FastAPI 应用组装和全局错误处理
bootstrap/                   启动运行时和业务依赖组装
modules/                     按业务模块组织 API、模型、服务、仓储和工作流
  learner_profile/           学习者画像模块
  diagnosis/                 诊断模块
data/                        题库、学习材料和画像数据
sdk/                         LLM 等基础能力接口
```

每个业务模块内部独立维护自己的模型、Service、Workflow、Repository 和 API，
应用启动时由 `bootstrap` 组装，再由 `api/server.py` 注册到 FastAPI。
