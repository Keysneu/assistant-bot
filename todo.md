# ToD0.md

> 说明：本文件记录当前执行进度。已按“vLLM 服务器部署优先”的 MVP 路线更新（2026-03-28）。

## 1. 已完成的功能

- 已完成 vLLM MVP 接入的后端改造：
  - 新增 `LLM_PROVIDER` 配置（支持 `llama_cpp` / `vllm`）
  - 新增 `VLLM_BASE_URL`、`VLLM_API_KEY`、`VLLM_MODEL`
  - `llm_service.py` 支持通过 OpenAI-Compatible API 调用 vLLM（含流式/非流式）
- 已补充依赖：`backend/requirements.txt` 增加 `openai` SDK。
- 已新增服务器部署资产：
  - `deploy/vllm/start_vllm.sh`
  - `deploy/vllm/.env.example`
  - `deploy/vllm/README.md`
- 已完成 vLLM 服务器部署与联调：
  - 远程 vLLM 服务已可用并接入后端
  - 后端可通过 `LLM_PROVIDER=vllm` 正常进行流式/非流式对话
  - 已完成本地后端到远程 vLLM 的链路验证与压测基线

## 2. 正在开发的功能

- vLLM 生产化收口：
  - systemd 托管 vLLM 进程（开机自启、异常自动拉起）
  - Nginx/TLS 与鉴权策略固化
  - 线上可观测性（QPS、TTFT、错误率）接入

## 3. 待开发的功能

- 异步化摄入：文档上传与 URL 导入后台任务化。
- 前端 API 抽象层补齐：`frontend/src/lib/api.ts` 与统一错误处理。
- 自动化测试与基础可观测性：后端单测、前端关键链路冒烟。
- 多模型策略：按场景动态切换模型与采样参数。

## 4. 已知问题（Bug / 待优化）

- 前端 `npm run build` 仍被历史遗留 TS unused 报错阻断（`SessionList.tsx`、`ui/Dialog.tsx`）。
- 对话附件直读目前是“截断文本注入”策略，超长文件体验仍需分段/任务化优化。

## 5. MVP 下一步执行清单（当前建议）

1. 固化 vLLM 生产部署（systemd + Nginx/TLS）。
2. 将 `probe_gemma4_capabilities.py --require-full` 纳入发布前固定验收。
3. 将压测脚本接入固定流程（记录每次发布前后 p95/成功率）。
4. 清理前端历史 TS unused 报错，恢复 `npm run build` 全量通过。
5. 对话附件能力扩展（docx/xlsx + 后台任务化解析）。

## 6. 2026-03-28 新增进展

- 已新增 `vllm_test/` 压测工具目录：
  - `vllm_test/run_benchmark.sh`：一键并发压测（默认 5 路）+ 汇总统计（成功率、avg、p50/p90/p95）
  - `vllm_test/sweep_concurrency.sh`：自动扫 1~10 并发并生成推荐上限（基于 success_rate 和 p95 阈值）
  - `vllm_test/README.md`：参数说明与使用示例
- 目的：为“本地后端 -> autodl vLLM”链路提供可重复的容量基线验证。
- 已将后端默认 `MAX_TOKENS` 调整为 `512`（`backend/app/core/config.py` 与 `backend/.env`）。

## 7. 2026-04-05 新增进展

- 已完成 `deploy/vllm` 的 Gemma4 E4B 适配（面向 RTX 4090 24GB 单卡）：
  - 默认模型更新为 `google/gemma-4-E4B-it`
  - 默认服务名更新为 `gemma4-e4b-it`
  - 新增可调参数：`MAX_NUM_SEQS`、`ENABLE_ASYNC_SCHEDULING`、`GENERATION_CONFIG`
  - 默认稳态参数更新为：`GPU_MEMORY_UTILIZATION=0.88`、`MAX_MODEL_LEN=8192`
- 已同步更新部署文档与示例环境变量：
  - `deploy/vllm/start_vllm.sh`
  - `deploy/vllm/.env.example`
  - `deploy/vllm/README.md`

## 8. 2026-04-05 追加进展（RTX 5090 32GB，历史记录）

- 已将 `deploy/vllm` 默认档位从 E4B（4090）切换为 26B-A4B（5090）：
  - 默认模型：`google/gemma-4-26B-A4B-it`
  - 默认服务名：`gemma4-26b-a4b-it`
  - 默认参数：`GPU_MEMORY_UTILIZATION=0.90`、`MAX_MODEL_LEN=8192`、`MAX_NUM_SEQS=12`
- 已在 `deploy/vllm/README.md` 补充 Gemma4 依赖安装说明（`transformers==5.5.0` + `vllm --pre`）以解决 `gemma4` 架构识别报错。

## 9. 2026-04-05 纠偏进展（按官方 Gemma4 Recipe）

- 依据官方文档 `Gemma 4 Usage Guide`：
  - 单卡 Quick Start 为 `google/gemma-4-E4B-it`
  - `google/gemma-4-26B-A4B-it` 与 `google/gemma-4-31B-it` 标注为 `1x80GB` 级别
- 已将 `deploy/vllm` 默认档位回调为 `E4B`，并以 `RTX 5090 32GB x1` 单卡配置为基线：
  - 默认模型：`google/gemma-4-E4B-it`
  - 默认服务名：`gemma4-e4b-it`
  - 默认参数：`GPU_MEMORY_UTILIZATION=0.92`、`MAX_MODEL_LEN=16384`、`MAX_NUM_SEQS=8`
  - 新增参数：`LIMIT_MM_PER_PROMPT`（用于文本/图文场景关闭不需要的多模态占用）
- 已同步更新：
  - `deploy/vllm/start_vllm.sh`
  - `deploy/vllm/.env.example`
  - `deploy/vllm/README.md`
  - `README.md`

## 10. 2026-04-05 本地接入远程 Gemma4（assistant-bot）

- 已完成本地后端接入收口，目标是让 `LLM_PROVIDER=vllm` 可直接对接远端 Gemma4：
  - `backend/app/core/config.py`：
    - vLLM 默认地址改为 `http://127.0.0.1:8100/v1`
    - 默认模型改为 `gemma4-e4b-it`
    - 新增 `VLLM_TIMEOUT_SECONDS`（默认 60 秒）
  - `backend/app/services/llm_service.py`：
    - OpenAI-compatible client 增加超时配置
    - 新增 `probe_vllm_connection()`（校验远端可达 + 模型名匹配）
    - 新增 `get_active_model_name()`（用于 API metadata）
    - 修复代理干扰：vLLM client 强制直连（`trust_env=False`），避免 SSH 隧道场景被本机代理劫持导致 502
  - `backend/app/api/health.py`：
    - `LLM_PROVIDER=vllm` 时改为主动探活远端 vLLM
  - `backend/app/api/chat.py`：
    - `metadata.model` 改为动态模型名，去除写死 Qwen
  - `backend/.env.example`：
    - 补齐 `LLM_PROVIDER/VLLM_*` 配置模板，默认 Gemma4 vLLM 接入项
- 文档同步：
  - `README.md` 已新增上述接入说明与 `VLLM_TIMEOUT_SECONDS` 配置说明。

## 11. 2026-04-05 Gemma4 深度集成（P0/P1）

- 已完成 P0（Gemma4 原生多模态接入）：
  - `backend/app/services/llm_service.py`：
    - 新增 vLLM 多模态消息构建逻辑（`image_url + text`）
    - `generate_response/stream_response/astream_response` 支持传入 `image_data/image_format`
  - `backend/app/api/chat.py`：
    - `LLM_PROVIDER=vllm` 且带图请求时，跳过 GLM 视觉中转，直接调用 Gemma4 原生多模态
- 已完成 P1（图文+RAG 融合）：
  - `backend/app/api/chat.py`：
    - 统一抽取 RAG 上下文后，与图片在同一条 vLLM 请求中发送
    - 非 vLLM provider 继续保留原视觉中转路径（兼容）
- 验证结果：
  - `/api/health/` 正常 `healthy`
  - `/api/chat/` 文本请求正常
  - `/api/chat/` 与 `/api/chat/stream` 图片请求正常，metadata 显示 `multimodal_mode=gemma4_native`

## 12. 2026-04-05 P2 参数格式兼容修复（vLLM limit-mm）

- 发现问题：
  - 部分 vLLM 版本要求 `--limit-mm-per-prompt` 使用 JSON 格式，旧写法 `image=2,audio=0` 会报 `cannot be converted to json.loads`。
- 已修复：
  - `deploy/vllm/start_vllm.sh` 增加兼容逻辑：若检测到旧写法，会自动转换为 JSON 后再传给 vLLM。
  - `deploy/vllm/.env.example` 与 `deploy/vllm/README.md` 已改为 JSON 推荐写法，并保留旧格式兼容说明。

## 13. 2026-04-05 前端流式响应截断修复

- 问题现象：
  - 前端在流式渲染时，长回答偶发被“截断/缺字”。
- 根因：
  - `frontend/src/components/ChatBox.tsx` 对每个 token 执行 `JSON.parse`，当 token 本身是合法 JSON（例如数字字面量）时被误判并吞掉。
- 修复：
  - `frontend/src/components/ChatBox.tsx` 改为 token 纯文本无损拼接，不再对 token 做 JSON 解析。
  - `frontend/src/lib/api.ts` 增加 `onMetadata` 回调，metadata（`session_id` 等）与 token 流分离处理。
- 结果：
  - 流式文本渲染不再因 token 误判而丢失内容，长回答完整性显著提升。

## 14. 2026-04-06 图片对话卡死修复（流式与空文本兼容）

- 问题现象：
  - 上传图片对话时，前端长时间等待，后端未及时返回 token，页面表现为“卡住”。
  - 图片-only 提交（不输入文本）会触发后端请求校验失败风险。
- 根因：
  - `backend/app/services/llm_service.py` 的 `astream_response` 先 `list()` 收集全量 token，再一次性返回，导致“伪流式”，图片场景首 token 慢时表现为长时间无输出。
  - `frontend/src/lib/api.ts` 在图片-only 场景会把 `message` 发送为空字符串，和后端 `message` 校验约束冲突。
  - 前端调试日志会打印完整请求体（含大体积 base64 图片），加重卡顿感知。
- 已修复：
  - 后端 `astream_response` 改为线程生产 + 异步队列转发，按 token 实时输出。
  - `backend/app/models/schema.py` 放宽为“文本或图片至少一个”，并在图片-only 时自动补全默认问题（`请描述这张图片`）。
  - 前端 `streamMessage` 在图片-only 时补默认消息，并将日志改为摘要信息（不再打印 base64 全量数据）。
  - 前端 `ImageUploader` 新增上传前标准化：缩放到最长边 1536、统一转 `jpeg`，降低大图传输与格式兼容风险。
  - 后端新增图文链路关键日志：记录 `has_image/image_chars/native_vllm_mm`，便于确认是否真正进入 vLLM 多模态分支。
  - 隧道稳定性加固：
    - `health` 探活改为异步线程执行 + 超时保护，避免 vLLM 探活阻塞主事件循环。
    - vLLM 探活增加短超时与缓存（减少 `/v1/models` 高频请求）。
    - 前端健康检查轮询降频为 15 秒并防重入。
    - 新增 `MAX_IMAGE_BASE64_CHARS`，超大图片直接返回 413，避免大包拖死隧道。

## 15. 2026-04-06 tokenizers fork 告警消除

- 问题现象：
  - 后端在 `fork/reload` 场景反复出现 `huggingface/tokenizers ... just got forked` 告警。
- 已修复：
  - 在 `backend/app/__init__.py` 启动早期设置 `TOKENIZERS_PARALLELISM=false`。
  - 在 `backend/app/services/embedding_service.py` 导入 `sentence_transformers` 前再次兜底设置同一环境变量。
  - 已同步 `backend/.env.example` 与 `README.md` 的运行配置说明。

## 16. 2026-04-06 Gemma4 vLLM 性能测试脚本新增

- 新增脚本：
  - `vllm_test/benchmark_gemma4_vllm.py`
- 能力范围：
  - 直连 vLLM OpenAI-compatible API（`/v1/chat/completions`）测试 Gemma4 部署性能。
  - 支持并发压测与 warmup。
  - 输出成功率、avg/p50/p90/p95/max 延迟、请求吞吐（req/s）、生成吞吐（tok/s）。
  - 支持 `--stream` 模式，统计 TTFT（首 token 时延）。
  - 结果落盘到 `vllm_test/results/gemma4_direct_<timestamp>/`（`requests.jsonl`、`summary.txt`、`summary.json`）。
- 文档同步：
  - `vllm_test/README.md`
  - `README.md`

## 17. 2026-04-06 Gemma4 压测脚本 warmup 400 修复

- 问题现象：
  - 当使用 `--stream` 运行 `vllm_test/benchmark_gemma4_vllm.py` 时，warmup 请求可能返回 `400`，但正式压测请求正常。
- 根因：
  - warmup 走非流式请求，但复用了流式模式下的 `stream_options` 字段；部分 vLLM 版本会对该组合返回 400。
- 已修复：
  - `vllm_test/benchmark_gemma4_vllm.py` warmup 请求中显式移除 `stream_options`，并强制 `stream=false`。

## 18. 2026-04-06 Gemma4 严格压测套件新增

- 新增脚本：
  - `vllm_test/strict_suite_gemma4_vllm.py`
- 目标：
  - 提供发布前更严格的多阶段性能验证，并基于门禁阈值自动输出 `PASS/FAIL`。
- 默认场景：
  - `s1_stream_ttft`（流式首 token 与延迟稳定性）
  - `s2_high_concurrency`（高并发压力）
  - `s3_long_generation`（长输出压力）
  - `s4_soak_stream`（持续稳定性）
- 产物：
  - `vllm_test/results/strict_suite_<timestamp>/suite_summary.txt`
  - `vllm_test/results/strict_suite_<timestamp>/suite_report.json`
- 同步增强：
  - `vllm_test/benchmark_gemma4_vllm.py` 增加 `--name-prefix`，并将结果目录时间戳提升到微秒级，避免多场景连续执行时目录冲突。

## 19. 2026-04-06 需求澄清：新增“对话附件上传直读”能力（非 RAG 入库）

> 用户明确要求：“像图片一样上传文件，让 AI 直接读取内容”，不是知识库文档上传。

### 19.1 本轮已完成

- Gemma4 部署能力增强（对齐官方 Configuration Tips）：
  - `deploy/vllm/start_vllm.sh` 新增部署档位：`DEPLOY_PROFILE=rag_text|vision|full|benchmark`
  - 新增能力开关：`ENABLE_REASONING`、`ENABLE_TOOL_CALLING`、`DISABLE_PREFIX_CACHING`
  - 新增可选参数：`TENSOR_PARALLEL_SIZE`、`MM_PROCESSOR_KWARGS`
- 新增部署能力验收脚本：
  - `vllm_test/probe_gemma4_capabilities.py`
  - 覆盖 `models/text/multimodal/structured/thinking/tool_calling`
- 新增聊天附件直读（P0）：
  - 后端 `ChatRequest` 增加 `file/file_name/file_format`
  - 后端支持 `txt/md/pdf/csv/json/log` 解析并注入本次 prompt 上下文（不入向量库）
  - 前端 `ChatBox` 新增附件上传按钮，支持随消息发送并在会话中显示附件名
  - 新增配置：`MAX_CHAT_FILE_BASE64_CHARS`、`MAX_CHAT_FILE_CONTEXT_CHARS`、`CHAT_FILE_ALLOWED_EXTENSIONS`

### 19.2 详细执行顺序（建议）

1. P0（已完成）: 部署脚本档位化 + 对话附件直读可用
2. P1（下一步）: 完整联调验收
   - 验证文本/图片/附件三类输入都可流式输出
   - 执行 `probe_gemma4_capabilities.py --require-full` 形成基线报告
3. P1（下一步）: 前端构建稳定性清理
   - 修复 `SessionList.tsx`、`ui/Dialog.tsx` 的 TS unused 报错
   - 恢复 `npm run build` 全量通过
4. P2（后续）: 附件能力增强
   - 支持 docx/xlsx（解析器扩展）
   - 增加附件解析后台任务化与超时取消
5. P2（后续）: 生产化收口
   - systemd + Nginx/TLS
   - 指标采集（TTFT、吞吐、错误率）接入告警

### 19.3 当前风险/待跟进

- 前端全量构建仍被历史 TS unused 问题阻断（与本轮核心功能无直接冲突）。
- 附件直读当前按“截断文本注入”策略运行，超长文档需要后续做分段/任务化优化。

## 20. 2026-04-06 项目内模式切换适配（Thinking / Tool Calling）

- 已完成“用户可自主切换模式”的项目接入：
  - 前端 `ChatBox` 增加 `Thinking` 与 `Tool Calling` 开关按钮
  - 请求参数新增：`enable_thinking`、`enable_tool_calling`
  - 后端聊天链路已贯通上述参数到 vLLM 调用层
- Tool Calling 已实现最小可用执行闭环：
  - 内置工具：`get_current_time`、`math_calculator`
  - 支持模型发起工具调用后，后端执行工具并回填结果，再生成最终回答
- 当前约束：
  - Tool Calling 流式路径当前采用“后端先完成工具调用，再分块回传文本”的兼容策略，不是原生 token 级工具流。

## 21. 2026-04-06 DEPLOY_PROFILE 项目侧适配补齐

- 已补齐“部署档位到项目能力”的映射链路：
  - 后端新增 `VLLM_DEPLOY_PROFILE`（需与服务器 `DEPLOY_PROFILE` 对齐）
  - 新增 `GET /api/chat/mode-config` 返回当前档位可用能力
  - 前端 `ChatBox` 启动时拉取模式配置并自动禁用不支持的开关
- 档位生效策略（项目内）：
  - `rag_text`：禁用图片与 Tool Calling
  - `vision`：允许图片，禁用 Tool Calling
  - `full`：允许图片 + Thinking + Tool Calling
  - `benchmark`：禁用图片 + Thinking + Tool Calling
- 用户体验增强：
  - UI 显示当前 `Profile`
  - 若用户请求被档位降级，前端显示 `mode_warnings` 提示

## 22. 2026-04-06 Chat 档位可见性与图片上传提示优化

- 问题背景：
  - 用户在 `VLLM_DEPLOY_PROFILE=rag_text` 下看到前端图片上传不可用，但界面缺少明确原因提示。
  - `Profile: rag_text` 仅为静态文本，无法点击查看用途与档位差异。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 将 `Profile: xxx` 改为可点击说明入口，弹窗展示 `rag_text/vision/full/benchmark` 四档能力矩阵。
    - 新增当前档位能力行（Image/Thinking/Tool Calling ON/OFF）。
    - 当 `supports_image=false` 时，新增明确告警文案，引导切换到 `vision/full`。
  - `frontend/src/components/ImageUploader.tsx`
    - 新增 `disabledReason`，在禁用状态下通过按钮提示说明原因（例如当前档位不支持图片）。
  - `README.md`
    - 补充 Profile 可点击说明与“图片不可用时如何切档位”的操作指引。

## 23. 2026-04-06 前端一键模式切换（运行时自动配置）

- 目标：
  - 用户无需手改 `backend/.env`，可在前端直接切换 `rag_text/vision/full/benchmark`。
- 已完成：
  - 后端新增运行时模式更新接口：
    - `PUT /api/chat/mode-config`（请求体：`deploy_profile`）
  - 后端聊天请求新增可选字段：
    - `deploy_profile`（请求级模式覆盖）
  - 后端 `GET /api/chat/mode-config` 响应增强：
    - 返回 `available_profiles`、`configured_profile`、`runtime_profile_override`、`profile_source`
  - 前端聊天框新增档位按钮：
    - 点击后调用模式更新接口并立即生效
    - 后续请求自动携带当前档位，不再依赖手动改 `.env`
- 当前说明：
  - `backend/.env` 的 `VLLM_DEPLOY_PROFILE` 变为“启动默认档位”。
  - 若服务端实际部署能力不足，请求会返回明确提示。

## 24. 2026-04-06 禁用 GLM 视觉代理，强制 Gemma4 原生多模态

- 背景：
  - 用户反馈回答出现“看不了图片”文案，需要排除 GLM 代理链路干扰，确保只走 Gemma4 原生多模态。
- 已完成：
  - 新增配置：`DISABLE_GLM_VISION`（`backend/app/core/config.py`）。
  - `vision_service.py` 增加 GLM 路径总开关逻辑，`DISABLE_GLM_VISION=true` 时不会初始化/使用 GLM。
  - `main.py` 启动日志优化：`LLM_PROVIDER=vllm` 时明确提示“Gemma4 native multimodal”路径。
  - `.env.example` 与 `README.md` 已补充 `DISABLE_GLM_VISION` 说明。
  - 当前本地 `backend/.env` 已设置 `DISABLE_GLM_VISION=true`。

## 25. 2026-04-06 Thinking 前端展示优化（对齐主流产品交互）

- 背景：
  - 用户已开启 Thinking，但回答中出现 `thought ...` 原始推理文本，影响主回答可读性。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 新增 `thought` 内容解析逻辑：识别“推理轨迹 + 最终回答”。
    - Assistant 消息改为双区块展示：
      - 可折叠“思考过程”区（默认在流式思考阶段自动展开）。
      - 主回答区仅展示最终答案；若答案尚未生成，显示“正在整理最终回答...”。
    - 保留原有 Markdown 渲染能力，思考区与主回答区均支持格式化文本。
- 当前效果：
  - 交互形态更接近 Gemini/GPT：先展示“思考中”，再展示最终回答，推理细节可按需展开查看。
  - 已完成二次修正：增强 `thought` 分割策略（关键词 + 步骤块结构 + 答案引导词兜底），降低“最终回答被误判为思考内容”的概率。
  - 已完成三次修正：新增“语言切换边界”识别（例如英文推理后直接切中文正文）和自检句式移交分割，进一步降低误判率。

## 26. 2026-04-06 Thinking 展示重构（抗抖动 + 主流交互对齐）

- 目标：
  - 解决流式生成过程中页面抖动严重、思考与最终回答混排的问题。
  - 对齐 GPT/Gemini/Claude 常见交互：流式阶段轻渲染，完成后展示折叠思考与主回答。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 重构 token 更新策略：不再每 token 写回 `messages`，改为独立流式缓冲 + 50ms 节流刷新。
    - 新增 `streamingAssistantIndex/streamingAssistantContent`，只更新当前流式消息，降低整页重渲染。
    - 移除独立“加载小气泡”以减少布局跳变。
    - 抽离 `AssistantContent`（`memo`）组件，历史消息不随每次 token 刷新重复 Markdown 渲染。
    - 流式阶段使用轻量文本渲染；完成后再切换 Markdown 富渲染。
  - `frontend/src/utils/thinkingParser.ts`
    - 新增独立思考分段解析器（关键词/步骤结构/答案引导词/交接句/语言切换边界）。
  - `frontend/tests/thinkingParser.test.ts`
    - 新增 8 条单测覆盖核心分段场景（含英文 thought -> 中文最终回答、长样例、无显式终结标记场景）。
  - `frontend/vitest.config.ts`、`frontend/package.json`
    - 新增 `vitest` 与 `npm run test` 命令。
  - `README.md`
    - 新增前端思考分段单测运行说明。

## 27. 2026-04-06 Thinking/Final 结构化字段落地 + 流式 Markdown 实时渲染

- 目标：
  - 前端不再依赖文本启发式拆分，改为后端结构化字段驱动思考区/回答区展示。
  - 修复“先全部输出再渲染 Markdown”的体验，改为流式增量渲染。
- 已完成：
  - `backend/app/api/chat.py`
    - `chat` 与 `chat/stream` 完成 `reasoning_content` / `final_content` / `display_content` 输出与落库。
    - 拆分失败兜底改为“全部归入 final_content，不返回可疑 reasoning”，避免误分导致混淆。
  - `backend/app/models/schema.py`、`backend/app/services/session_service.py`
    - 会话消息模型和持久化字段补齐 `reasoning_content`、`final_content`。
  - `frontend/src/lib/api.ts`
    - 流式接口新增 `onDone` 回调，接收 `done` 事件结构化字段。
  - `frontend/src/components/ChatBox.tsx`
    - 历史消息映射补齐结构化字段。
    - 流式阶段改为实时 Markdown 渲染（50ms 节流刷新）。
    - 助手消息展示优先使用 `reasoning_content/final_content`，移除运行时启发式分割依赖。
- 验证：
  - `frontend`：`npm run test` 通过（8/8）。
  - `frontend`：`npx eslint src/components/ChatBox.tsx src/lib/api.ts src/types/index.ts` 通过。
  - `backend`：`python3 -m py_compile backend/app/api/chat.py backend/app/services/session_service.py backend/app/models/schema.py` 通过。
  - `frontend`：`npm run build` 仍受历史未使用变量告警阻断（`SessionList.tsx` / `ui/Dialog.tsx`），与本轮改动无关。

## 28. 2026-04-06 思考框实时流式展示修正

- 背景：
  - 用户反馈：思考内容仍然在结束后才进入思考框，而不是流式阶段实时显示。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 恢复并用于流式阶段的 `parseThinkingContent`。
    - 当流式内容命中 `thought` 结构时，实时将推理文本渲染在思考框中。
    - 若已检测到答案段，思考框显示“思考完成”，并在下方开始渲染答案；未检测到时显示“正在整理最终回答...”。
    - 保持最终态以后端 `reasoning_content/final_content` 结构化字段为准，避免落地内容混淆。
- 验证：
  - `frontend`：`npx eslint src/components/ChatBox.tsx` 通过。
  - `frontend`：`npm run test` 通过（8/8）。

## 29. 2026-04-06 思考框“跳出再跳回”抖动修复

- 背景：
  - 用户反馈流式生成时，思考内容会短暂跳出思考框，再回到思考框。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 新增 `streamingThinkingPanelLocked`（思考面板锁定状态）。
    - 流式请求开始时按请求设置预锁定，收到 `metadata.enable_thinking` 后用服务端有效值同步。
    - `AssistantContent` 新增 `preferThinkingPanel`，流式期间锁定后即使解析未命中也保持在思考框内渲染，避免分支抖动。
    - 收尾阶段不再把 `streamingAssistantContent` 临时切换为 `display_content`，避免尾帧闪跳。
- 验证：
  - `frontend`：`npx eslint src/components/ChatBox.tsx` 通过。
  - `frontend`：`npm run test` 通过（8/8）。
