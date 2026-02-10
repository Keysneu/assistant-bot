# 产品需求文档 (PRD)：智能办公助手系统 (AssistentBot)

## 1. 项目概述

### 1.1 产品定义

AssistentBot 是一款基于大语言模型（LLM）和检索增强生成（RAG）技术的智能办公助手。它能够通过对网页、本地文档的深度理解，结合实时互联网搜索，为用户提供精准的问题解答、内容摘要和信息整合服务。

### 1.2 核心目标

- **私有化知识库**：通过上传文档或输入 URL，构建个性化的向量数据库。
- **实时情报获取**：集成 Agent 搜索功能，支持带日期过滤的互联网深度搜索。
- **高性能对话**：使用 Mistral-7B 结合 4-bit 量化技术，保证低资源下的高性能响应。
- **解耦架构**：摒弃 Gradio，采用独立的 React/Vue 前端与 FastAPI 后端架构。

------

## 2. 技术架构需求 (Tech Stack)

为了尽可能保留代码中的技术灵魂，系统架构如下：

- **大模型层**：Mistral-7B-Instruct-v0.1（量化加载：BitsAndBytes 4-bit）。
- **向量化层**：thenlper/gte-large 嵌入模型。
- **向量数据库**：ChromaDB（用于持久化存储文档分块）。
- **编排层**：LangChain (ConversationalRetrievalChain) 与 Llama-Index。
- **Agent 搜索**：Metaphor (Exa.ai) API。
- **后端框架**：Python FastAPI (替代 Gradio 的交互逻辑)。
- **前端框架**：React + Tailwind CSS (提供更极致的交互体验)。

------

## 3. 功能需求

### 3.1 增强检索问答 (RAG)

- **数据注入**：
  - 支持解析指定 URL 列表并抓取内容。
  - 支持本地文件夹文档加载（SimpleDirectoryReader）。
- **处理逻辑**：
  - 采用 `RecursiveCharacterTextSplitter` 进行文本分块（1024 chunks, 64 overlap）。
  - 生成的向量存储在 Chroma 向量库中。
- **问答体验**：支持输出生成答案所引用的源文档（Source Documents）。

### 3.2 智能 Agent 搜索

- **动态搜索**：当用户提问超出本地知识库或需要时效性信息时，触发 Agent 搜索。
- **日期感知**：利用 `get_date` 工具，根据当前时间应用 Metaphor 过滤器（例如“过去一个月的新闻”）。

### 3.3 对话管理

- **上下文关联**：使用 `ConversationBufferMemory` 存储多轮对话历史。
- **Standalone 问题重写**：系统需自动将用户的追加问题（Follow-up）改写为独立的问题，以提高检索精度。

------

## 4. 接口设计 (API Endpoints)

后端需提供以下核心 RESTful API 接口：

| **接口名**   | **路径**          | **方法** | **功能描述**                           |
| ------------ | ----------------- | -------- | -------------------------------------- |
| **发起对话** | `/api/chat`       | POST     | 接收用户输入，返回流式或全文回复       |
| **上传文档** | `/api/upload`     | POST     | 接收本地文件并触发数据切片与向量化入库 |
| **注入 URL** | `/api/ingest_url` | POST     | 接收 URL，爬取内容并更新知识库         |
| **会话历史** | `/api/history`    | GET      | 获取当前用户的历史聊天列表             |

------

## 5. UI/UX 交互设计需求

### 5.1 前端核心组件

- **对话窗口**：支持 Markdown 渲染（包含代码高亮、表格、公式）。
- **引用溯源卡片**：在模型回答下方悬浮显示引用的文档分块或 URL 来源。
- **知识库面板**：可视化显示当前已加载的文档列表、URL 及其处理状态。
- **Agent 状态提示**：当 Agent 正在调用外部搜索时，UI 应显示“正在搜索互联网...”的加载动画。

------

## 6. 非功能需求

- **并发处理**：后端需支持多会话并发，确保不同用户的 `chat_history` 互不干扰。
- **响应速度**：集成流式输出（Streaming），减少用户等待首字出现的焦虑。
- **安全性**：API 密钥（如 Metaphor API Key）需在后端环境变量中管理，严禁暴露给前端。

------

### Master's Vibe Hint 🧙‍♂️

在实现过程中，请注意 `Mistral-7B` 的 `Prompt Template` 必须保持原始代码中的 `[INST]` 格式，这是该模型理解指令的关键：

Markdown

```
[INST] <<SYS>>
Act as a Marketing Manager expert...
<<SYS>>
{context}
{question} [/INST]
```