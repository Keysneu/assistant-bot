# AssistantBot

AssistantBot 是一个面向本地部署的全栈 RAG 对话系统，目标是把实验型 Notebook 代码演进为工程化产品。项目针对 Apple Silicon（Mac M3）做了推理与向量化加速优化，支持私有知识库问答、流式对话、会话管理、多模态图片输入和对话附件文件直读。

## 项目简介

本项目解决的问题：
- 将“文档检索 + 大模型回答”落地为可运行的前后端系统。
- 在本地环境中实现数据可控、可持续迭代的知识库助手。
- 提供接近生产形态的 API 分层、服务分层与前端交互。

当前能力（基于仓库现状）：
- FastAPI 后端（健康检查、聊天、文档上传/URL 导入、会话管理）。
- ChromaDB 本地持久化检索。
- llama-cpp-python 本地模型推理（支持 Metal 参数）。
- vLLM 远程推理接入（OpenAI-Compatible，支持流式/非流式）。
- 对话附件文件直读（`txt/md/pdf/csv/json/log`，不入库，按单次会话上下文注入）。
- 项目内 Gemma4 性能展示面板（聚合 benchmark/strict/probe 最新结果）。
- SSE 流式输出与多会话管理。
- 前端 React + Vite + Tailwind 聊天与文档管理 UI。

## 最新进展（2026-04-06）

- Gemma4 部署能力增强（对齐 vLLM 官方 Gemma4 recipe 配置建议）：
  - `deploy/vllm/start_vllm.sh` 新增 `DEPLOY_PROFILE` 档位（`rag_text/vision/full/benchmark`）
  - 新增 thinking/tool calling 开关：`ENABLE_REASONING`、`ENABLE_TOOL_CALLING`
  - 新增压测一致性开关：`DISABLE_PREFIX_CACHING`（`benchmark` 档位自动启用）
- 新增 Gemma4 能力探测脚本：
  - `vllm_test/probe_gemma4_capabilities.py`
  - 可验证 `models/text/multimodal/structured/thinking/tool_calling`
- 新增项目内性能适配（后端 API + 前端页面）：
  - 后端新增 `GET /api/performance/overview`
  - 前端新增“性能”Tab，直接展示 Gemma4 关键指标
- 新增项目内模式切换（用户自主选择）：
  - 聊天请求支持 `enable_thinking`、`enable_tool_calling`
  - 聊天输入框新增 Thinking / Tool Calling 开关按钮
  - Tool Calling 当前内置工具：`get_current_time`、`math_calculator`
- 新增“对话附件上传并直读”能力（你要求的“像图片一样上传文件给 AI 读”）：
  - 聊天请求支持文件字段：`file/file_name/file_format`
  - 后端支持 `txt/md/pdf/csv/json/log` 解析并注入当次对话上下文
  - 前端聊天框新增附件按钮，支持上传文件并随消息发送

## 技术栈

后端：
- Python 3.10+
- FastAPI / Uvicorn
- llama-cpp-python
- sentence-transformers（`thenlper/gte-large`）
- ChromaDB
- pypdf / BeautifulSoup / httpx
- sse-starlette

前端：
- React 19 + TypeScript
- Vite
- Tailwind CSS
- lucide-react
- react-markdown + remark-gfm

## 目录结构

```text
assistant-bot/
├── backend/
│   ├── app/
│   │   ├── api/                  # chat / upload / health 路由
│   │   ├── core/                 # 配置与环境变量
│   │   ├── models/               # Pydantic schema
│   │   └── services/             # llm/rag/embedding/session/vision 核心服务
│   ├── data/                     # 会话与向量数据
│   ├── models/                   # GGUF 模型目录
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/           # ChatBox/SessionList/DocumentManager 等
│   │   ├── hooks/                # useSessions/use-toast
│   │   ├── types/                # TS 类型
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── package.json
├── AGENTS.md                     # 代码代理协作规则（必读）
├── ToD0.md                       # 项目进度与待办
└── README.md
```

## 开发规范

### 通用规范
- 后端采用分层：`api -> services -> models/core`，避免在路由层堆业务逻辑。
- 新接口优先补充 Pydantic schema，保持请求/响应稳定。
- 前端使用 TypeScript，组件命名用 `PascalCase`，hooks 用 `useXxx`。
- API 路径统一放在前端 `lib/api`（建议），避免散落硬编码 URL。

### 命名与风格
- Python：`snake_case`（函数/变量/文件），类名 `PascalCase`。
- TypeScript：组件与类型 `PascalCase`，函数变量 `camelCase`。
- 路由前缀固定 `/api`，按领域划分子路由（`/chat`、`/documents`、`/health`）。

### 提交与协作建议
- 每次开发优先更新 `ToD0.md` 中对应状态。
- 大改动前先记录目标与风险，减少回归。
- 涉及配置变化时同步更新 README 的“运行方式”和“.env 说明”。

## 如何运行

### 0) 选择 LLM Provider（本地/服务器）

在 `backend/.env` 中设置：

```bash
# 本地默认
LLM_PROVIDER=llama_cpp

# 或者使用远程 vLLM
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://<SERVER_IP>:8100/v1
VLLM_API_KEY=EMPTY
# 若 deploy/vllm 使用 served model name（推荐）
VLLM_MODEL=gemma4-e4b-it
# 需与服务器 DEPLOY_PROFILE 对齐: rag_text | vision | full | benchmark
VLLM_DEPLOY_PROFILE=rag_text
VLLM_TIMEOUT_SECONDS=60
VLLM_PROBE_TIMEOUT_SECONDS=4
VLLM_HEALTH_CACHE_SECONDS=15

# 多模态安全限制（仅 base64 载荷长度，不含 data:image 前缀）
MAX_IMAGE_BASE64_CHARS=4000000
# 仅在非 vLLM 视觉代理路径使用；建议 Gemma4 原生多模态时关闭 GLM 代理
DISABLE_GLM_VISION=true
# 对话文件附件限制（不入知识库）
MAX_CHAT_FILE_BASE64_CHARS=8000000
MAX_CHAT_FILE_CONTEXT_CHARS=12000
CHAT_FILE_ALLOWED_EXTENSIONS=.txt,.md,.markdown,.pdf,.csv,.json,.log

# 知识库文档上传限制（RAG 入库）
MAX_UPLOAD_FILE_SIZE_MB=20
MAX_BATCH_UPLOAD_FILES=10
UPLOAD_ALLOWED_EXTENSIONS=.txt,.md,.markdown,.html,.htm,.pdf

# 避免 tokenizers 在 fork/reload 场景刷告警
TOKENIZERS_PARALLELISM=false
```

vLLM 服务器部署说明：`deploy/vllm/README.md`
说明：当 `LLM_PROVIDER=vllm` 时，后端启动与 `/api/health/` 会校验远端连通性和模型可见性；健康探活使用短超时与缓存，避免隧道抖动时阻塞主请求。
说明：当 `LLM_PROVIDER=vllm` 且请求中包含 `image` 字段时，后端会直接使用 Gemma4 原生多模态推理。若请求包含 `file` 字段，后端会解析文件文本并在本次对话中注入上下文（不写入向量库）。

### 1) 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Apple Silicon 推荐
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python
uvicorn app.main:app --reload
```

默认后端地址：`http://127.0.0.1:8000`

### 2) 前端

```bash
cd frontend
npm install
npm run dev
```

默认前端地址：`http://127.0.0.1:5173`

前端思考/回答分段逻辑单测：

```bash
cd frontend
npm run test
```

### 3) 运行前检查
- 将 GGUF 模型放到 `backend/models/`。
- 按需配置 `backend/.env`（模型路径、GLM API Key、CORS 等）。
- 首次启动会初始化 `backend/data/chroma_db` 与会话数据文件。

## 当前已知注意事项

- 前端 `npm run build` 目前会被历史遗留的 TS unused 报错阻断（`SessionList.tsx`、`ui/Dialog.tsx`），与本次 Gemma4/附件功能改造无直接关系。
- `AGENTS.md` 中原“推荐模型”与当前配置不完全一致（文档提到 Mistral，配置默认 Qwen2.5），已在协作规则中改为“以代码配置为准”。
- vLLM 服务器部署说明见 `deploy/vllm/README.md`。

## 对话附件上传（直接给 AI 读）

使用方式：
- 在聊天输入框左侧点击回形针按钮上传文件（`txt/md/pdf/csv/json/log`）。
- 可只发文件不输入文本，后端会自动补全默认提问。
- 文件内容仅用于当前请求上下文，不会自动写入 RAG 知识库。

适用场景：
- 快速让模型总结一份临时文档
- 对单个 PDF/文本做即时问答，不污染长期知识库

## 项目内性能展示（Gemma4 E4）

访问方式：
- 启动前后端后，在左侧导航进入 `性能` Tab
- 页面会调用 `GET /api/performance/overview`，聚合展示：
  - 最新 `gemma4_direct_*` benchmark 指标（成功率、P95、吞吐、TTFT）
  - 最新 `strict_suite_*` 总体状态（PASS/FAIL）
  - 最新 `cap_probe_*` 能力检查通过情况

前提：
- 需先运行至少一轮测试脚本，结果写入 `vllm_test/results/`
- 推荐顺序：`benchmark_gemma4_vllm.py` -> `strict_suite_gemma4_vllm.py` -> `probe_gemma4_capabilities.py`

## 模式切换（Thinking / Tool Calling）

你现在可以在聊天框中自主切换：
- `Thinking`：对应请求参数 `enable_thinking=true`
- `Tool Calling`：对应请求参数 `enable_tool_calling=true`

说明：
- 该切换是“请求级别”开关，用户可按会话即时选择。
- 需要服务端 vLLM 启动时允许相关能力（例如 `ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`）。
- 当前 Tool Calling 内置了两个演示工具：时间查询与数学计算。
- 当 `LLM_PROVIDER=vllm` 且传图时，后端走 Gemma4 原生多模态；可通过 `DISABLE_GLM_VISION=true` 禁用 GLM 视觉代理，避免链路混淆。
- 项目会通过 `GET /api/chat/mode-config` 感知当前 `VLLM_DEPLOY_PROFILE`，自动禁用不支持的开关：
  - `rag_text`: 文本优先（不支持图像、Tool Calling）
  - `vision`: 图文优先（支持图像，不支持 Tool Calling）
  - `full`: 全能力（支持图像、Thinking、Tool Calling）
  - `benchmark`: 压测模式（禁用图像/Thinking/Tool Calling）
- 聊天框上方提供 `rag_text / vision / full / benchmark` 一键切换按钮（调用 `PUT /api/chat/mode-config`），切换后新请求自动按所选模式执行。
- `Profile: xxx` 标签可点击查看四档能力说明（Image/Thinking/Tool Calling）。
- `backend/.env` 中的 `VLLM_DEPLOY_PROFILE` 仅作为启动默认值；运行中可在前端直接切换模式。

## vLLM 压测（本地后端 -> 远程 vLLM）

项目内置一键压测脚本：

```bash
bash vllm_test/run_benchmark.sh
```

默认执行 5 路并发压测并输出统计汇总。详细参数说明见 `vllm_test/README.md`。

自动扫描并发上限（1~10 并发）：

```bash
bash vllm_test/sweep_concurrency.sh
```

## Gemma4 直连 vLLM 压测（推荐）

用于评估 vLLM 模型服务本身性能（绕过本地后端），可直接测 Gemma4 的延迟与吞吐：

```bash
python3 vllm_test/benchmark_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --requests 80 \
  --concurrency 8 \
  --max-tokens 256
```

流式压测（统计 TTFT）：

```bash
python3 vllm_test/benchmark_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --model gemma4-e4b-it \
  --requests 40 \
  --concurrency 8 \
  --stream
```

详细参数见：`vllm_test/README.md`。

## Gemma4 严格压测（多阶段门禁）

如果你需要更严格的发布前验证，可执行多阶段严格套件（流式TTFT、高并发、长输出、soak）：

```bash
python3 vllm_test/strict_suite_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --strict-model
```

结果会输出 `PASS/FAIL`，并生成 `suite_summary.txt` 与 `suite_report.json`。详细见 `vllm_test/README.md`。

## Gemma4 部署能力验收（推荐）

执行能力探测脚本（模型可见性、文本、多模态、结构化、thinking、tool calling）：

```bash
python3 vllm_test/probe_gemma4_capabilities.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --require-full
```

输出目录：`vllm_test/results/cap_probe_<timestamp>/capability_report.json`
