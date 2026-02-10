# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 1. 项目愿景

将原有的 `.ipynb` 实验代码演进为一个工业级的全栈 RAG（检索增强生成）系统。目标是利用 **Mac M3** 的 Metal 加速能力，构建一个高性能、前后端解耦的私有知识库与实时搜索助手。

## 2. 技术栈 (Mac M3 优化)

| **组件**      | **选型**                                | **说明**                                 |
| ------------- | --------------------------------------- | ---------------------------------------- |
| **LLM 推理**  | **Llama.cpp (python-binding)**          | 关键：必须使用 Metal API 调度 M3 GPU     |
| **模型版本**  | Mistral-7B-Instruct-v0.1                | 使用 GGUF 量化格式 (推荐 Q5_K_M 或 Q6_K) |
| **后端框架**  | **FastAPI**                             | 支持异步处理与 SSE 流式响应              |
| **前端框架**  | **React (Vite)** + Tailwind + Shadcn/UI | 替代 Gradio，提供 ChatGPT 级的交互体验   |
| **RAG 编排**  | LangChain + Llama-Index                 | 延续原代码逻辑，处理多轮对话与检索       |
| **向量库**    | ChromaDB                                | 本地持久化存储                           |
| **Embedding** | thenlper/gte-large                      | 使用 `device="mps"` 在 M3 神经引擎上运行 |

## 3. 项目结构规范

AI 在生成代码时应严格遵守以下目录结构：

Plaintext

```
assistant-bot/
├── backend/                # FastAPI 逻辑
│   ├── app/
│   │   ├── api/            # 路由 (chat.py, upload.py, search.py)
│   │   ├── services/       # 核心逻辑 (llm_service, rag_service)
│   │   └── models/         # Pydantic 模式与数据库定义
│   ├── models/             # 存放 .gguf 模型文件
│   └── data/               # ChromaDB 持久化目录
├── frontend/               # React 源码
│   └── src/
│       ├── components/     # UI 组件 (ChatBox, DataSourceManager)
│       └── hooks/          # API 交互 (useStreamingChat)
```

## 4. 关键开发约定

### 4.1 LLM 加载 (M3 专用)

在实现 `llm_service.py` 时，确保模型配置利用 Apple Silicon：

Python

```
# 示例配置
llm = LlamaCpp(
    model_path="./models/mistral-7b-v0.1.Q5_K_M.gguf",
    n_gpu_layers=-1,  # 关键：将所有层卸载到 GPU (Metal)
    n_ctx=4096,
    f16_kv=True,      # 开启半精度
    streaming=True
)
```

### 4.2 提示词模板

必须保留原始 Mistral 指令格式：

```
[INST] <<SYS>> {system_prompt} <<SYS>> {context} {question} [/INST]
```

### 4.3 核心 API 行为

- **SSE 流式传输**：`/api/chat` 接口必须支持 `StreamingResponse`，以便前端实时显示回复。
- **异步向量化**：上传文档后需异步触发向量化流程，不阻塞主线程。

## 5. 常用命令

- **后端启动**：`uvicorn app.main:app --reload`
- **前端开发**：`npm run dev`
- **依赖安装 (M3)**：`CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python`
- **向量库清理**：`rm -rf backend/data/chroma_db`

## 6. 开发优先级 (Roadmap)

1. **Phase 1**: 在 FastAPI 中封装 Llama.cpp，验证 M3 Metal 加速推理。
2. **Phase 2**: 实现基于 ChromaDB 的本地文档上传与 RAG 检索链。
3. **Phase 3**: 开发 React 对话界面，实现 SSE 流式交互。
4. **Phase 4**: 集成 Metaphor API 实现带日期过滤的 Agent 联网搜索。