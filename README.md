# AssistantBot

AssistantBot 是一个面向本地部署的全栈 RAG 对话系统，目标是把实验型 Notebook 代码演进为工程化产品。项目针对 Apple Silicon（Mac M3）做了推理与向量化加速优化，支持私有知识库问答、流式对话、会话管理、多模态图片输入、Gemma4 本地音频/视频理解和对话附件文件直读。

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

- 连接链路重构（替代“图片大包走 SSH 隧道”）：
  - 新增 `POST /api/chat/images/upload`：图片先二进制上传，返回 `image_id`
  - 新增 `GET /api/chat/images/{image_id}`：会话历史按 `image_id` 回放图片
  - 聊天请求支持 `image_id`（优先）与 `image`（兼容旧请求）
  - 后端新增图片缓存与压缩参数（尺寸/质量/TTL/容量），默认显著减小跨网络图片载荷
  - 会话存储默认记录 `image_id`，避免 `sessions.json` 持续膨胀
- Gemma4 图像理解第一阶段接入优化（对齐官方 OpenAI-compatible 消息结构）：
  - 后端聊天请求新增多图字段：`image_ids` / `images` / `image_formats`
  - vLLM 请求构造改为 `content=[image_url..., text]`（多图在前、文本在后）
  - `/api/chat/` 与 `/api/chat/stream` metadata 新增 `image_count` 与 `image_ids`
  - 会话消息新增 `image_ids` 持久化，历史回放可展示多张图片
  - 前端图片上传支持多选（最多 4 张）与批量发送
- Gemma4 音频理解第一阶段接入优化（对齐官方 OpenAI-compatible 消息结构）：
  - 新增 `POST /api/chat/audios/upload` 与 `GET /api/chat/audios/{audio_id}`
  - 后端聊天请求支持：`audio_url` / `audio_urls`（默认仅允许本地上传音频 URL）
  - vLLM 请求构造支持 `content=[audio_url..., text]`（与官方示例一致）
  - `/api/chat/` 与 `/api/chat/stream` metadata 新增 `has_audio`、`audio_count`、`audio_urls`
  - 会话消息新增 `has_audio/audio_url/audio_urls` 持久化
  - 前端支持“麦克风录音”后直接发给 Gemma4
- Gemma4 视频理解第一阶段接入优化（对齐官方 OpenAI-compatible 消息结构）：
  - 新增 `POST /api/chat/videos/upload` 与 `GET /api/chat/videos/{video_id}`
  - 后端聊天请求支持：`video_url` / `video_urls`（默认仅允许本地上传视频 URL）
  - vLLM 请求构造支持 `content=[video_url..., text]`（与官方示例一致）
  - `/api/chat/` 与 `/api/chat/stream` metadata 新增 `has_video`、`video_count`、`video_urls`
  - 会话消息新增 `has_video/video_url/video_urls` 持久化
  - 前端将“上传音频文件”入口替换为“上传视频文件”，用于 Gemma4 视频理解
- Gemma4 部署能力增强（对齐 vLLM 官方 Gemma4 recipe 配置建议）：
  - `deploy/vllm/start_vllm.sh` 新增 `DEPLOY_PROFILE` 档位（`rag_text/vision/full/full_featured/benchmark/extreme`）
  - 新增 thinking/tool calling 开关：`ENABLE_REASONING`、`ENABLE_TOOL_CALLING`
  - 新增压测一致性开关：`DISABLE_PREFIX_CACHING`（`benchmark` 档位自动启用）
- 新增 Gemma4 能力探测脚本：
  - `vllm_test/probe_gemma4_capabilities.py`
  - 可验证 `models/text/multimodal/structured/thinking/tool_calling`
- 新增项目内性能适配（后端 API + 前端页面）：
  - 后端新增 `GET /api/performance/overview`
  - 前端新增“性能”Tab，直接展示 Gemma4 关键指标
- 模式能力由服务端启动档位固定（取消前端运行时切换）：
  - 聊天请求支持 `enable_thinking`、`enable_tool_calling`
  - 聊天输入框保留 Thinking / Tool Calling 开关按钮（仅在服务端支持时生效）
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
# 需与服务器 DEPLOY_PROFILE 对齐: rag_text | vision | full | full_featured | benchmark | extreme
VLLM_DEPLOY_PROFILE=full_featured
VLLM_TIMEOUT_SECONDS=600
VLLM_PROBE_TIMEOUT_SECONDS=8
VLLM_HEALTH_CACHE_SECONDS=5

# 多模态安全限制（仅 base64 载荷长度，不含 data:image 前缀）
MAX_IMAGE_BASE64_CHARS=50000000
MAX_SESSION_IMAGE_BASE64_CHARS=5000000
# 图片建议走 image_id（先上传再引用）
MAX_CHAT_IMAGE_UPLOAD_MB=64
CHAT_IMAGE_CACHE_DIR=./data/chat_images
CHAT_IMAGE_CACHE_TTL_SECONDS=604800
CHAT_IMAGE_CACHE_MAX_FILES=20000
CHAT_IMAGE_TARGET_MAX_EDGE=4096
CHAT_IMAGE_TARGET_MAX_BYTES=8000000
CHAT_IMAGE_TARGET_QUALITY=95
# 音频建议走本地上传 URL（先上传再引用）
MAX_CHAT_AUDIO_UPLOAD_MB=32
CHAT_AUDIO_CACHE_DIR=./data/chat_audios
CHAT_AUDIO_CACHE_TTL_SECONDS=604800
CHAT_AUDIO_CACHE_MAX_FILES=20000
CHAT_AUDIO_ALLOWED_EXTENSIONS=.wav,.mp3,.ogg,.webm,.m4a,.mp4,.flac
# 默认禁用公网 audio_url，避免服务器外网不可达导致 500
ALLOW_PUBLIC_AUDIO_URLS=false
# 开启公网 audio_url 时的抓取限制
AUDIO_FETCH_TIMEOUT_SECONDS=20
MAX_AUDIO_FETCH_BYTES=25000000
# 视频建议走本地上传 URL（先上传再引用）
MAX_CHAT_VIDEO_UPLOAD_MB=256
CHAT_VIDEO_CACHE_DIR=./data/chat_videos
CHAT_VIDEO_CACHE_TTL_SECONDS=604800
CHAT_VIDEO_CACHE_MAX_FILES=10000
CHAT_VIDEO_ALLOWED_EXTENSIONS=.mp4,.mov,.webm,.mkv,.m4v,.avi
# 默认禁用公网 video_url，避免服务端不可达
ALLOW_PUBLIC_VIDEO_URLS=false
# vLLM 拉取本地视频时使用的后端公开地址（需保证 vLLM 可访问）
LOCAL_MEDIA_BASE_URL=http://127.0.0.1:8000
# 本地视频传输方式：data_url（默认，避免 vLLM 反向访问 backend）| url
LOCAL_VIDEO_TRANSPORT_MODE=data_url
# data_url 方式下单视频内联字节上限（超限时后端直接报 413）
MAX_VIDEO_DATA_URL_BYTES=50000000
# 仅在非 vLLM 视觉代理路径使用；建议 Gemma4 原生多模态时关闭 GLM 代理
DISABLE_GLM_VISION=true
# 对话文件附件限制（不入知识库）
MAX_CHAT_FILE_BASE64_CHARS=80000000
MAX_CHAT_FILE_CONTEXT_CHARS=500000
CHAT_FILE_ALLOWED_EXTENSIONS=.txt,.md,.markdown,.pdf,.csv,.json,.log

# 知识库文档上传限制（RAG 入库）
MAX_UPLOAD_FILE_SIZE_MB=200
MAX_BATCH_UPLOAD_FILES=100
UPLOAD_ALLOWED_EXTENSIONS=.txt,.md,.markdown,.html,.htm,.pdf

# 生成参数上限（请求可覆盖，但不超过该硬上限）
MAX_TOKENS=8192
MAX_TOKENS_HARD_LIMIT=16384

# 避免 tokenizers 在 fork/reload 场景刷告警
TOKENIZERS_PARALLELISM=false
```

vLLM 服务器部署说明：`deploy/vllm/README.md`
说明：当 `LLM_PROVIDER=vllm` 时，后端启动与 `/api/health/` 会校验远端连通性和模型可见性；健康探活使用短超时与缓存，避免隧道抖动时阻塞主请求。
说明：当 `LLM_PROVIDER=vllm` 且请求中包含 `image_id/image_ids`（或兼容字段 `image/images`）时，后端会直接使用 Gemma4 原生多模态推理。若请求包含 `audio_url/audio_urls`，默认仅接受本地上传音频 URL（`/api/chat/audios/{audio_id}` 或同路径完整 URL），后端会读取本地缓存并转为 `data:audio/*` 后发送给 vLLM。若请求包含 `video_url/video_urls`，默认仅接受本地上传视频 URL（`/api/chat/videos/{video_id}` 或同路径完整 URL）：默认 `LOCAL_VIDEO_TRANSPORT_MODE=data_url`，后端会将本地视频转为 `data:video/*` 后发送给 vLLM（无需 vLLM 反向访问 backend）；若超出 `MAX_VIDEO_DATA_URL_BYTES` 会回退 URL 传输模式。若请求包含 `file` 字段，后端会解析文件文本并在本次对话中注入上下文（不写入向量库）。
说明：音频/视频能力依赖服务端 vLLM 多模态能力，并在启动参数中允许预算（例如 `--limit-mm-per-prompt '{"image":4,"audio":1,"video":1}'`）。

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
# 可选：显式指定后端地址（建议）
# export VITE_API_URL=http://127.0.0.1:8000
npm run dev
```

默认前端地址：`http://127.0.0.1:5173`
说明：本地调试建议优先使用 `127.0.0.1` 而非 `localhost`，可避免部分环境下 IPv6 (`::1`) 解析导致的“前端误判后端未启动”问题。

前端思考/回答分段逻辑单测：

```bash
cd frontend
npm run test
```

### 3) 运行前检查
- 将 GGUF 模型放到 `backend/models/`。
- 按需配置 `backend/.env`（模型路径、GLM API Key、CORS 等）。
- 首次启动会初始化 `backend/data/chroma_db` 与会话数据文件。

## 连接方式优化（替代 SSH 隧道）

推荐从“本地 SSH 端口转发”切换到以下任一方式：
- `WireGuard/Tailscale` 内网直连（首选，稳定且吞吐更高）
- 服务器侧 `Nginx/Caddy + TLS` 暴露受控 API 域名（配合 IP 白名单/鉴权）

本项目已支持图片两段式链路，降低长请求抖动风险：
1. 客户端先调用 `POST /api/chat/images/upload` 上传图片二进制，获得 `image_id`
2. 再调用 `/api/chat/stream`，请求体携带 `image_id`（单图）或 `image_ids`（多图）+ 文本
3. 会话历史通过 `GET /api/chat/images/{image_id}` 拉取图片展示

这样可避免将大体积 base64 图片直接塞进流式聊天请求，弱网下稳定性更高。

单图请求体示例（推荐 `image_id`）：

```json
{
  "message": "请详细描述这张图片",
  "session_id": "optional-session-id",
  "image_id": "a1b2c3...",
  "enable_thinking": true
}
```

多图请求体示例（`image_ids`）：

```json
{
  "message": "对比这两张图的相同点与差异",
  "session_id": "optional-session-id",
  "image_ids": ["img_id_1", "img_id_2"],
  "enable_thinking": true
}
```

音频转录请求体示例（`audio_url`）：

```json
{
  "message": "Provide a verbatim, word-for-word transcription of the audio.",
  "session_id": "optional-session-id",
  "audio_url": "/api/chat/audios/<audio_id>",
  "enable_thinking": false
}
```

视频理解请求体示例（`video_url`）：

```json
{
  "message": "Summarize what happens in this video.",
  "session_id": "optional-session-id",
  "video_url": "/api/chat/videos/<video_id>",
  "enable_thinking": false
}
```

推荐两段式调用（完全不依赖公网）：

```bash
# 1) 上传本地音频，获取 audio_id
curl -X POST http://127.0.0.1:8000/api/chat/audios/upload \
  -F "file=@./sample.wav"

# 2) 聊天请求中引用本机 URL
curl -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Transcribe this audio.",
    "audio_url": "/api/chat/audios/<audio_id>"
  }'
```

```bash
# 1) 上传本地视频，获取 video_id
curl -X POST http://127.0.0.1:8000/api/chat/videos/upload \
  -F "file=@./sample.mp4"

# 2) 聊天请求中引用本机 URL
curl -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Summarize what happens in this video.",
    "video_url": "/api/chat/videos/<video_id>"
  }'
```

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

## 模式能力（Thinking / Tool Calling）

你现在可以在聊天框中按请求开关：
- `Thinking`：对应请求参数 `enable_thinking=true`
- `Tool Calling`：对应请求参数 `enable_tool_calling=true`

说明：
- Thinking / Tool Calling 是请求级别开关。
- 需要服务端 vLLM 启动时允许相关能力（例如 `ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`）。
- 当前 Tool Calling 内置了两个演示工具：时间查询与数学计算。
- 当 `LLM_PROVIDER=vllm` 且传图时，后端走 Gemma4 原生多模态；可通过 `DISABLE_GLM_VISION=true` 禁用 GLM 视觉代理，避免链路混淆。
- 项目通过 `GET /api/chat/mode-config` 感知当前 `VLLM_DEPLOY_PROFILE`，自动禁用不支持的开关：
  - `rag_text`: 文本优先（不支持图像/音频/视频、Tool Calling）
  - `vision`: 图文优先（支持图像，不支持音频/视频、Tool Calling）
  - `full`: 全能力（支持图像/音频/视频、Thinking、Tool Calling）
  - `full_featured`: 全功能官方档位（支持图像/音频/视频、Thinking、Tool Calling）
  - `benchmark`: 压测模式（禁用图像/音频/视频/Thinking/Tool Calling）
- `extreme`: 极限压测模式（文本优先，禁用图像/音频/视频/Thinking/Tool Calling）
- 运行中不支持前端切换档位；如需改档位，请修改服务端 `VLLM_DEPLOY_PROFILE` 并重启 vLLM。
- `Profile: xxx` 标签可点击查看六档能力说明（Image/Audio/Video/Thinking/Tool Calling）。
- `backend/.env` 中的 `VLLM_DEPLOY_PROFILE` 需与服务端启动档位一致。

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

高 KV cache 压力建议增加参数：

```bash
python3 vllm_test/benchmark_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --model gemma4-e4b-it \
  --prompt-file ./long_prompt.txt \
  --requests 192 \
  --concurrency 32 \
  --max-tokens 2048 \
  --unique-prompt-per-request
```

## Gemma4 高 KV Cache 压测（推荐）

新增脚本（自动构造长上下文 + 高并发配置）：

```bash
python3 vllm_test/kv_cache_stress_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --requests 192 \
  --concurrency 32 \
  --max-tokens 2048
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
