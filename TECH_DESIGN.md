# 技术选型与系统设计文档：智能办公助手

## 1. 技术栈选择 (Tech Stack)

考虑到 Mac M3 的硬件架构，我们放弃 CUDA 依赖（如 BitsAndBytes），转而使用 Apple 芯片原生支持的加速框架。

### 1.1 后端 (AI & API Layer)

- **LLM 推理引擎**: **Llama.cpp (python-binding)**。
  - *选型理由*: 替代代码中的 `transformers + bitsandbytes`。Llama.cpp 通过 Metal API 直接调用 M3 的 GPU 核心，推理速度远超 CPU。
  - **核心模型**: Mistral-7B-Instruct-v0.1 (GGUF 量化版本)。
- **应用框架**: **FastAPI**。
  - *选型理由*: 异步性能极佳，原生支持 Pydantic 模型，非常适合处理大模型的流式输出（Streaming Response）。
- **RAG 框架**: **LangChain**。
  - *保留核心*: 使用 `ConversationalRetrievalChain` 处理对话历史和检索逻辑。
- **向量库**: **ChromaDB**。
  - *保留核心*: 轻量级且支持本地持久化（`persist_directory`）。

### 1.2 前端 (UI Layer)

- **基础框架**: **React (Vite)**。
  - *选型理由*: 生态丰富，响应式速度快，优于传统的后端渲染或 Gradio。
- **样式库**: **Tailwind CSS + Shadcn/UI**。
  - *选型理由*: 快速构建专业级、类似 ChatGPT 的对话界面。
- **流式渲染**: **Markdown-it** 或 **React-Markdown**。
  - *选型理由*: 处理模型输出的 Markdown 格式，支持代码高亮和表格渲染。

### 1.3 数据库 (Storage Layer)

- **非结构化数据**: **ChromaDB**（存储文档分块及其向量特征）。
- **结构化数据**: **SQLite**。
  - *选型理由*: 本地轻量化存储用户会话历史、上传的文档元数据。

------

## 2. 项目结构 (Project Structure)

采用前后端分离的工程化目录结构：

Plaintext

```
assistant-bot/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── api/            # 路由定义 (chat, upload, search)
│   │   ├── core/           # 核心配置 (M3 Metal 配置, 环境变量)
│   │   ├── services/       # 业务逻辑
│   │   │   ├── llm_service.py     # Llama.cpp 推理封装
│   │   │   ├── rag_service.py     # LangChain 检索增强逻辑
│   │   │   └── search_service.py  # Metaphor 工具集成
│   │   └── models/         # 数据库模型定义
│   ├── data/               # 存放本地文档和 Chroma 持久化数据
│   ├── models/             # 存放 Mistral-7B GGUF 模型文件
│   └── requirements.txt
├── frontend/               # React 前端
│   ├── src/
│   │   ├── components/     # 对话框、上传组件、搜索提示
│   │   ├── hooks/          # 处理 API 请求与流式数据
│   │   └── App.tsx
│   └── package.json
└── docker-compose.yml       # (可选) 环境一键启动
```

------

## 3. 数据模型 (Data Model)

### 3.1 会话历史 (Conversation)

- `session_id`: 唯一标识。
- `messages`: 列表格式，存储 `HumanMessage` 和 `AIMessage`。
- `timestamp`: 创建时间。

### 3.2 文档元数据 (Document Metadata)

- `doc_id`: 文档唯一 ID。
- `source_name`: 文件名或 URL。
- `vector_ids`: 对应 Chroma 中的向量索引 ID。
- `status`: (Processing/Ready) 向量化进度状态。

------

## 4. 关键技术点与难点 (Key Technical Points)

### 4.1 Mac M3 性能优化 (Metal Acceleration)

- **难点**: 代码原使用的是 `device_map="auto"` (针对 NVIDIA CUDA)。
- **对策**: 在加载 Llama.cpp 时，显式指定 `n_gpu_layers=-1`。这会将所有模型层加载到 M3 的统一内存中，并由 GPU 接管计算，响应延迟可降低 80% 以上。

### 4.2 嵌入模型的本地适配

- **方案**: 继续使用 `thenlper/gte-large` 模型。
- **注意**: 确保在后端使用 `sentence-transformers` 时指定 `device="mps"`，利用 Apple 芯片的神经引擎进行向量化。

### 4.3 搜索 Agent 的日期过滤逻辑

- **难点**: 如何让模型根据当前时间自动调整搜索范围。
- **对策**: 封装一个 `get_date` 工具注入 Prompt，在调用 Metaphor API 时，动态传入 `start_published_date` 参数，实现“搜索过去一个月新闻”的逻辑。

### 4.4 前端流式响应 (Server-Sent Events)

- **对策**: 弃用 Gradio 的轮询机制，后端使用 FastAPI 的 `StreamingResponse`。前端利用 `fetch` API 的 `ReadableStream` 实时渲染模型吐出的每一个 Token，提升“直观感受”的流畅度。