# 自适应伴学智能体前端

本目录包含前端源码、交互设计说明和后端接口交接文档。

## 目录结构

```text
front-end/
├── docs/                         # 前端研究、交互和后端交接说明
├── frontend/                    # React + TypeScript + TSX 前端项目
│   ├── src/                     # 页面、组件、模拟数据和接口服务
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── README.md
└── README.md
```

## 获取后运行

进入前端目录后安装依赖并启动：

```bash
cd frontend
pnpm install
pnpm run dev
```

如果本机没有 pnpm，可以先安装 pnpm，或者使用项目团队统一的 Node.js 依赖环境。

## 后端接入

前端默认使用模拟服务，页面可以直接演示完整交互。后端接口准备好后，在 `frontend/.env` 中配置：

```text
VITE_USE_REAL_API=true
VITE_API_BASE_URL=http://后端地址
```

详细接口字段、页面状态和动作映射请阅读：

- `docs/前端交互与后端交接说明.md`
- `docs/前端研究与设计决策.md`

## 当前学习内容

当前页面仅展示：

- 《机器学习》
- 《强化学习》

后续增加书籍时，在前端模拟数据和后端书籍数据中增加对应内容即可。
