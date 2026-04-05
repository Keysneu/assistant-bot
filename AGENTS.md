# AGENTS.md

本文件是本仓库的长期协作规则与“项目记忆锚点”。
每次开始任务前都应先阅读本文件，并以本文件作为实现和文档更新的默认依据。

## 1. 必读原则（长期记忆）

- 本文件是 AI 代理在本仓库中的常驻规则，默认每次任务都要先读。
- 若代码现状与文档冲突：
  - 先以“当前可运行代码 + 配置”为准执行。
  - 再同步更新 README/ToD0/本文件，消除冲突。
- 每次交付至少检查三件事：
  - 是否引入与现有目录规范冲突的文件位置。
  - 是否更新了进度文档（`ToD0.md`）。
  - 是否产生新的环境变量/运行命令并同步到 `README.md`。

## 2. 项目目标

将实验型 Notebook 代码演进为工业级全栈 RAG 系统，重点关注：
- 本地化部署（隐私可控）
- Mac M3/Apple Silicon 性能优化
- 前后端解耦与可维护性
- 支持流式、多轮、知识库检索与持续扩展

## 3. 技术基线（以当前代码为准）

- 后端：FastAPI + Python
- LLM 推理：llama-cpp-python（Metal）
- 当前默认模型配置：Qwen2.5 GGUF（见 `backend/app/core/config.py`）
- Embedding：`thenlper/gte-large`（`device=mps`）
- 向量库：ChromaDB（本地持久化）
- 前端：React + Vite + Tailwind
- 协议：REST + SSE 流式

说明：历史文档提及 Mistral 方案，属于兼容目标，不应覆盖当前默认配置。

## 4. 目录与分层约定

目标结构：

```text
assistant-bot/
├── backend/
│   ├── app/
│   │   ├── api/        # 路由层：只做参数校验/编排
│   │   ├── services/   # 业务层：LLM/RAG/Session/Vision
│   │   ├── models/     # 数据模型
│   │   └── core/       # 配置和基础设施
│   ├── models/         # GGUF 模型文件
│   └── data/           # Chroma 与会话持久化
└── frontend/
    └── src/
        ├── components/
        ├── hooks/
        ├── lib/
        └── types/
```

分层规则：
- 不在 `api` 层写复杂业务逻辑。
- 公共能力沉淀到 `services`，避免重复实现。
- 前端请求统一收敛到 `src/lib/api.ts`（若缺失，优先补齐）。

## 5. 编码规范

- Python：PEP8，函数/文件 `snake_case`，类 `PascalCase`。
- TypeScript：组件 `PascalCase`，变量/函数 `camelCase`，hooks 以 `use` 开头。
- 新增配置必须写默认值并可被 `.env` 覆盖。
- 新增接口必须补充 schema，避免裸字典协议漂移。

## 6. RAG 与推理关键约束

- 保留 SSE 流式体验；变更流式链路时优先保证前端可消费。
- 文档摄入需考虑非阻塞化方向（后台任务化）。
- Prompt 模板可以多模型兼容，但默认模板必须与默认模型一致。
- 与 Apple Silicon 相关参数（如 `n_gpu_layers=-1`、`mps`）不可随意移除。

## 7. 任务执行清单（每次改动后）

- 校验导入路径与真实文件一致（避免“引用存在、文件缺失”）。
- 运行最小可用检查：后端可启动、前端可启动、核心接口可访问。
- 更新文档：
  - 功能状态更新到 `ToD0.md`
  - 运行变更更新到 `README.md`
  - 协作规则沉淀到 `AGENTS.md`

## 8. Roadmap（滚动）

1. 完善模型与模板配置统一策略（Qwen/Mistral 可切换）。
2. 文档上传与 URL 导入后台异步化。
3. 补齐 `frontend/src/lib` API 抽象层并完善错误处理。
4. 建立自动化测试与基础可观测性。
5. 接入联网搜索 Agent 与时间过滤检索。
