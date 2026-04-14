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

## 20. 2026-04-06 新增进展（KV Cache 高压力测试）

- 已新增高 KV cache 压力测试脚本：
  - `vllm_test/kv_cache_stress_gemma4_vllm.py`
- 已增强直连压测脚本能力：
  - `vllm_test/benchmark_gemma4_vllm.py` 新增 `--prompt-file`
  - `vllm_test/benchmark_gemma4_vllm.py` 新增 `--unique-prompt-per-request`
- 目标：
  - 通过“长上下文 + 高并发 + 大输出 + 请求级唯一前缀”场景，主动拉高 KV cache 占用，便于观察服务器端 KV cache 利用率上限与瓶颈。
- 文档同步：
  - `README.md`
  - `vllm_test/README.md`

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

## 30. 2026-04-06 连接方式重构：图片改为 `image_id` 两段式链路（稳态替代 SSH 隧道大包）

- 背景：
  - 当前“本地 SSH 隧道 + 聊天请求内嵌 base64 图片”在大图场景下抖动明显，影响稳定性与响应速度。
- 已完成：
  - `backend/app/api/chat.py`
    - 新增 `POST /api/chat/images/upload`（二进制上传，返回 `image_id`）。
    - 新增 `GET /api/chat/images/{image_id}`（历史图片按引用读取）。
    - `chat`/`chat_stream` 支持 `image_id`（优先）和 `image`（兼容）双输入。
    - 用户消息落库优先存 `image_id`，默认不再持久化大体积 base64。
  - `backend/app/services/chat_image_service.py`
    - 新增聊天图片缓存服务：图片标准化压缩（尺寸/质量/目标字节），TTL 与最大文件数清理。
  - `backend/app/models/schema.py`、`backend/app/services/session_service.py`
    - 补齐 `ChatRequest/ChatMessage` 的 `image_id` 字段和持久化链路。
  - `frontend/src/components/ImageUploader.tsx`
    - 上传前压缩策略升级：按目标大小预算进行质量/尺寸降采样，输出 JPEG 文件。
  - `frontend/src/lib/api.ts`、`frontend/src/components/ChatBox.tsx`、`frontend/src/types/index.ts`
    - 前端发送链路改为“先 `uploadChatImage` 拿 `image_id`，再发 `/chat/stream`”。
    - 历史图片展示支持 `image_id` URL 拉取与旧 `image_data` 兼容回放。
  - 文档与配置同步：
    - `README.md`、`deploy/vllm/README.md`、`backend/.env.example` 已补充新链路和参数说明。
- 验证：
  - `backend`：`python3 -m compileall backend/app` 通过。
  - `frontend`：`npm run test -- --run` 通过（8/8）。
  - `frontend`：`npm run build` 仍受历史 TS unused 报错阻断（`SessionList.tsx` / `ui/Dialog.tsx`），与本轮重构无直接关系。

## 31. 2026-04-06 极限压测通道增强（服务器侧 + 后端侧）

- 服务器部署参数增强（`deploy/vllm`）：
  - `start_vllm.sh` 新增 `DEPLOY_PROFILE=extreme` 档位（文本优先、自动关闭 prefix caching、激进并发默认值）。
  - 新增 `MAX_NUM_BATCHED_TOKENS` 环境变量并映射到 `--max-num-batched-tokens`。
  - 新增 `deploy/vllm/.env.extreme.example`，用于服务器一键加载极限压测参数。
  - `deploy/vllm/.env.example` 与 `deploy/vllm/README.md` 已同步更新上述参数与调优建议。
- 后端生成上限增强（`backend`）：
  - 新增 `MAX_TOKENS_HARD_LIMIT`，允许请求级 `max_tokens` 提升但受硬上限保护。
  - `ChatRequest` 新增可选覆盖参数：`max_tokens`、`temperature`、`top_p`。
  - `chat` / `chat_stream` 链路已支持将请求级参数传递到 `llm_service`，metadata 中回传 `effective_*` 参数便于排查。
  - `VLLM_DEPLOY_PROFILE` 支持值扩展为 `rag_text|vision|full|benchmark|extreme`。
- KV cache 压测脚本增强（`vllm_test`）：
  - `kv_cache_stress_gemma4_vllm.py` 默认提高到更激进档位（更长 prompt、更高并发/输出、超时放宽）。
  - 新增按 `/v1/models` 的 `max_model_len` 自动放大 prompt 的能力，目标默认 `92%` 上下文占用。

## 32. 2026-04-06 常规运行“高上限默认值”收口

- 目标：在日常运行配置中尽量避免因参数上限过低导致吞吐/能力受限。
- 后端（`backend`）：
  - 默认生成上限提升：`MAX_TOKENS=8192`、`MAX_TOKENS_HARD_LIMIT=16384`。
  - 上传与上下文限制提升：图片、聊天附件、文档上传、批量上传阈值全部上调到高档位。
  - 图片缓存压缩上限提升：`CHAT_IMAGE_TARGET_MAX_EDGE=4096`、`CHAT_IMAGE_TARGET_MAX_BYTES=8000000`、`CHAT_IMAGE_TARGET_QUALITY=95`。
  - `backend/.env` 已同步为高上限默认（当前为 `VLLM_DEPLOY_PROFILE=full_featured`、长超时）。
- 服务端（`deploy/vllm`）：
  - `start_vllm.sh` 默认上调为高资源占用参数：`GPU_MEMORY_UTILIZATION=0.98`、`MAX_NUM_SEQS=32`、`MAX_NUM_BATCHED_TOKENS=131072`、`DEPLOY_PROFILE=full_featured`。
  - `extreme` 档位进一步上调：`0.99 / 48 / 262144`。
  - `.env.example` 与 `.env.extreme.example`、`deploy/vllm/README.md` 已同步。
- 前端（`frontend`）：
  - 图片上传前端阈值从 10MB 提升到 64MB，并放宽压缩预算（4K 边长，8MB 目标，质量 0.95）。
  - 聊天附件前端阈值从 6MB 提升到 64MB。
  - 档位切换 UI 已包含 `extreme`。

## 33. 2026-04-06 Gemma4 官方 full-featured 启动参数适配（保持 E4B）

- 目标：
  - 按官方 full-featured 思路启用完整能力（文本/图像/音频预算 + thinking + tool calling + async scheduling），但保持模型为 `E4B`。
- 已完成：
  - `deploy/vllm/start_vllm.sh`
    - 新增 `DEPLOY_PROFILE=full_featured` 档位。
    - 自动启用：`ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`、`ENABLE_ASYNC_SCHEDULING=1`。
    - 默认多模态预算：`LIMIT_MM_PER_PROMPT={"image":4,"audio":1}`（仍可被显式 env 覆盖）。
    - 不再自动切换到 `31B`，维持 `MODEL_NAME=google/gemma-4-E4B-it` 的默认基线。
  - 新增 `deploy/vllm/.env.full_featured.example`
    - 可一键 `source` 后启动 full-featured（E4B）配置。
  - 文档/配置同步：
    - `deploy/vllm/.env.example`、`deploy/vllm/README.md` 补充 `full_featured` 档位说明与启动方式。
    - `README.md`、`backend/.env.example` 补充 `full_featured` 档位说明。
  - 本地项目联动：
    - `backend` profile 校验与 schema 扩展支持 `full_featured`。
    - `frontend` 模式切换 UI 新增 `full_featured`，能力说明与 `full` 对齐。

## 34. 2026-04-06 取消前端运行时档位切换，固定服务端启动档位

- 目标：
  - 档位只在 vLLM 启动时确定，前端不再提供“切换档位”能力，避免运行时能力认知偏差。
- 已完成：
  - 服务端默认档位切换为 `full_featured`：
    - `deploy/vllm/start_vllm.sh` 默认 `DEPLOY_PROFILE=full_featured`
    - `deploy/vllm/.env.example` 默认 `DEPLOY_PROFILE=full_featured`，并默认开启 `ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`
    - `backend/app/core/config.py` 与 `backend/.env.example` 默认 `VLLM_DEPLOY_PROFILE=full_featured`
  - 后端禁用运行时切档：
    - `GET /api/chat/mode-config` 仍返回当前能力，但 `available_profiles=[]`
    - 请求体中的 `deploy_profile` 被忽略（返回 warning）
    - `PUT /api/chat/mode-config` 路由已彻底移除
  - 前端取消档位切换入口：
    - 移除档位按钮与切换调用，仅保留 Profile 只读说明
    - Thinking / Tool Calling 继续保留请求级开关，但由服务端档位能力决定是否可用
  - 文档同步：
    - `README.md`、`deploy/vllm/README.md` 更新为“档位由启动配置固定”说明。

## 35. 2026-04-06 前端附件名遮挡输入内容修复

- 问题现象：
  - 聊天区上传文件后，附件名标签会覆盖输入框底部内容，影响继续输入与阅读。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 附件名展示从输入框内绝对定位（`absolute bottom-*`）改为输入区域上方独立行展示。
    - 输入容器由 `flex-row` 调整为 `flex-col`，确保附件标签与 `textarea` 垂直排列，不再发生层叠遮挡。
    - 移除依赖 `textarea pb-10` 的临时避让方式，改为结构性布局修复。
- 结果：
  - 长文件名只会在独立标签区域截断显示，不会覆盖用户输入内容。

## 36. 2026-04-06 vLLM 启动参数 `limit-mm-per-prompt` 格式兼容修复

- 问题现象：
  - 启动时报错：`--limit-mm-per-prompt: Value {image:4,audio:1} cannot be converted to json.loads`。
- 已完成：
  - `deploy/vllm/start_vllm.sh`
    - `LIMIT_MM_PER_PROMPT` 解析逻辑增强，统一归一化为 JSON，兼容三种输入：
      - `{"image":4,"audio":1}`
      - `{image:4,audio:1}`
      - `image=4,audio=1`
  - `deploy/vllm/.env.example`
  - `deploy/vllm/.env.full_featured.example`
  - `deploy/vllm/.env.extreme.example`
    - 默认值改为单引号包裹 JSON，避免 `source` 时被 shell 处理破坏格式。
  - `deploy/vllm/README.md`
    - 补充 `.env` 中 `LIMIT_MM_PER_PROMPT` 的推荐写法说明。

## 37. 2026-04-06 Thinking 最终态保留“可展开思考”修复（前端）

- 问题现象：
  - 流式阶段能看到思考过程，但回答结束后思考区消失，无法继续展开查看。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 在 `done` 收尾阶段新增兜底：当后端未回传 `reasoning_content` 时，使用 `full_content` 再次解析 `thought` 结构并回填 `reasoning_content/final_content`。
    - 在 `AssistantContent` 渲染阶段新增兜底：若结构化思考字段为空但文本仍是 `thought` 格式，自动解析并展示“思考过程 + 最终回答”双区块。
- 结果：
  - Thinking 模式下，回答完成后仍可展开查看思考内容，不再出现“最终态思考消失”。

## 38. 2026-04-06 Thinking 开关生效性修复（后端 vLLM reasoning 字段兼容）

- 问题现象：
  - 前端开启 Thinking 后，部分请求仍看不到思考过程，表现为“只有最终回答”。
- 根因：
  - 当前链路主要依赖模型把思考内容直接输出到 `content` 文本；
  - 当 vLLM/Gemma4 以结构化字段（如 `reasoning_content`）返回思考时，后端未消费该字段，导致前端看不到思考。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 新增 OpenAI-compatible 响应解析兼容：同时提取 `content` 与 `reasoning_content/reasoning/reasoning_text`。
    - 非流式路径：将 `reasoning + answer` 统一格式化为 `thought ... + Final answer` 输出，确保下游可解析。
    - 流式路径：支持从 `delta` 中提取 reasoning token，并与 answer token 分段输出。
- 结果：
  - 前端开启 Thinking 后，模型通过结构化 reasoning 返回时也能稳定展示思考过程。

## 39. 2026-04-06 Gemma4 图像理解第一阶段接入优化（单图/多图）

- 目标：
  - 对齐官方 Gemma4 图像输入模式，补齐多图请求能力，并保持现有单图链路兼容。
- 已完成：
  - `backend/app/models/schema.py`
    - `ChatRequest` 新增多图字段：`images`、`image_ids`、`image_formats`。
    - `ChatMessage` 新增 `image_ids`，用于多图历史回放。
  - `backend/app/api/chat.py`
    - 新增 `_resolve_image_inputs()` 与 `_resolve_inline_image_inputs()`，统一解析单图/多图输入。
    - `/api/chat/` 与 `/api/chat/stream` 支持多图透传；metadata 新增 `image_ids`、`image_count`。
    - 非 vLLM provider 下新增多图视觉代理聚合逻辑（逐图分析并合并上下文）。
  - `backend/app/services/llm_service.py`
    - vLLM 用户消息构造支持多图：`content=[image_url..., text]`（与官方示例顺序一致）。
    - `generate_response/stream_response/astream_response` 全链路支持 `image_data_list/image_format_list`。
  - `backend/app/services/session_service.py`
    - 会话持久化支持 `image_ids` 字段读写。
  - `frontend/src/lib/api.ts`、`frontend/src/types/index.ts`
    - 增加 `image_ids` 与 `image_count` 类型/请求兼容。
  - `frontend/src/components/ChatBox.tsx`
    - 历史消息渲染支持 `image_ids` 多图展示（网格回放）。
- 验证结果：
  - `python3 -m compileall backend/app` 通过。
  - `cd frontend && npm run test -- --run` 通过（8/8）。
  - `cd frontend && npm run build` 仍因历史遗留 TS unused 报错失败（与本次多图改造无新增关联）。

## 40. 2026-04-06 前端多图上传交互优化

- 问题：
  - 聊天框只能上传单张图片，无法直接完成多图对比场景。
- 已完成：
  - `frontend/src/components/ImageUploader.tsx`
    - 改为多图模式：支持 `multiple` 选择、拖拽多文件、最多 4 张。
    - 保留压缩逻辑（4K 边长 + 目标大小预算），并支持逐张删除与一键清空。
  - `frontend/src/components/ChatBox.tsx`
    - 图片状态改为数组，提交时批量上传并发送 `image_ids`。
    - 用户消息渲染支持本地多图预览（发送前）与历史多图回放。
  - `frontend/src/types/index.ts`、`frontend/src/lib/api.ts`
    - 补齐 `image_urls` 字段类型，适配前端多图展示。
- 验证：
  - `cd frontend && npm run test -- --run` 通过（8/8）。
  - `cd frontend && npm run build` 失败原因不变，仍是历史 TS unused 报错（`SessionList.tsx`、`ui/Dialog.tsx`）。

## 41. 2026-04-06 Gemma4 音频转录第一阶段接入优化（E2B/E4B）

- 目标：
  - 对齐官方 Gemma4 Audio Understanding 示例，打通项目内 `audio_url` 输入到 vLLM OpenAI-compatible 链路。
- 已完成：
  - `backend/app/models/schema.py`
    - `ChatRequest` 新增 `audio_url`、`audio_urls`。
    - `ChatMessage` 新增 `has_audio`、`audio_url`、`audio_urls`。
    - 校验逻辑支持 audio-only 请求（自动补默认转录提示词）。
    - `ChatModeConfigResponse` 新增 `supports_audio`。
  - `backend/app/api/chat.py`
    - 新增音频 URL 解析与校验（支持 `http(s)` 与 `data:audio/*`）。
    - `/api/chat/` 与 `/api/chat/stream` 全链路透传音频输入。
    - 新增音频能力校验：非 vLLM 或档位不支持音频时返回明确 400 提示。
    - metadata 新增 `has_audio`、`audio_url/audio_urls`、`audio_count`，并细分 `multimodal_mode`（`gemma4_native_audio` 等）。
  - `backend/app/services/llm_service.py`
    - vLLM 用户消息构造支持 `audio_url` 块，格式与官方示例一致：`content=[audio_url..., text]`（也兼容图+音+文本）。
    - `generate_response/stream_response/astream_response` 全链路新增音频参数透传。
  - `backend/app/services/session_service.py`
    - 会话持久化支持音频字段读写。
  - `frontend/src/types/index.ts`、`frontend/src/lib/api.ts`
    - 补齐音频相关请求/响应类型（不改现有 UI 行为）。
  - `README.md`
    - 补充音频能力说明、请求示例与 profile 能力映射更新。
- 验证：
  - `python3 -m compileall backend/app` 通过。
  - `cd frontend && npm run build` 失败原因不变，仍是历史 TS unused 报错（`SessionList.tsx`、`ui/Dialog.tsx`）。

## 42. 2026-04-06 音频 URL 外网拉取失败兼容修复（vLLM 503）

- 问题现象：
  - vLLM 服务器侧直接拉取公网 `audio_url` 时出现 `Cannot connect` / `503 Service Unavailable`，导致 `/v1/chat/completions` 返回 500。
- 已完成：
  - `backend/app/api/chat.py`
    - 新增音频 URL 预取逻辑：后端先下载远程音频并转为 `data:audio/*;base64` 后再发给 vLLM。
    - 若预取失败，保留原始 URL 透传，并将失败原因写入 `mode_warnings`。
    - metadata 新增 `audio_prefetched_count`，用于确认本次请求是否走了预取链路。
  - `backend/app/core/config.py`
    - 新增 `AUDIO_FETCH_TIMEOUT_SECONDS`、`MAX_AUDIO_FETCH_BYTES` 配置项与校验。
  - `README.md`
    - 补充上述新配置与链路说明。
- 结果：
  - 在“vLLM 所在机器外网不稳定/受限”场景下，音频转录链路可由后端代拉取，显著降低 500 概率。

## 43. 2026-04-06 Gemma4 图片链路误报修复（前端提示逻辑）

- 问题现象：
  - 上传图片后前端出现告警“图片请求未走 Gemma4 原生多模态链路（当前: gemma4_native_image）”。
  - 实际上后端 `multimodal_mode=gemma4_native_image` 本身就是 Gemma4 原生图片链路，属于前端误判。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 修复图片链路判定：将 `gemma4_native_image` 与 `gemma4_native_image_audio` 视为原生链路。
    - 统一使用 `multimodalMode` 变量复用图片/音频告警文案，减少枚举不一致风险。
- 验证：
  - 代码级确认：后端 `_resolve_multimodal_mode()` 返回值与前端判定条件已对齐。
  - `cd frontend && npm run build` 仍被历史 TS unused 报错阻断（与本次修复无新增关联）。

## 44. 2026-04-06 Gemma4 音频内网/本机 URL 链路与前端语音输入补齐

- 目标：
  - 禁止公网音频 URL 依赖，统一改为“本地上传 -> `/api/chat/audios/{audio_id}`”链路。
  - 前端支持直接说话（麦克风录音）后发送给 Gemma4。
- 已完成：
  - `backend/app/services/chat_audio_service.py`
    - 新增本地音频 URL 解析（`/api/chat/audios/{audio_id}`）与 `audio_id -> data:audio/*` 转换能力。
  - `backend/app/api/chat.py`
    - `audio_url` 校验默认仅允许本地上传 URL（或 `data:audio/*`）。
    - 本地 URL 不再走网络请求，直接读取缓存音频转 data URL 后发送给 vLLM。
  - `backend/app/core/config.py`、`backend/.env.example`
    - 新增 `ALLOW_PUBLIC_AUDIO_URLS`（默认 `false`），保留可选外部 URL 抓取开关。
    - 补齐音频上传缓存参数示例（大小/TTL/容量/扩展名）。
  - `frontend/src/components/ChatBox.tsx`
    - 新增音频文件选择、麦克风录音开始/停止、已选音频预览与清除。
    - 发送时先上传音频，再在请求中使用本地 URL：`/api/chat/audios/{audio_id}`。
    - 消息历史新增音频播放器渲染，支持会话回放。
    - Profile 能力展示新增 `Audio`，并在档位不支持时给出前端提示。
  - `frontend/src/lib/api.ts`
    - 新增 `resolveApiUrl`，支持将会话中的相对音频路径解析为可播放地址。
  - `README.md`
    - 音频示例改为本地上传 URL；补充两段式 cURL 示例；明确默认禁用公网音频 URL。
- 验证：
  - `python3 -m compileall backend/app` 通过。
  - `cd frontend && npm run build` 仍可能受历史 TS unused 报错影响（与本次音频改造无直接关系）。

## 45. 2026-04-06 前端麦克风“停止即发送”交互优化

- 目标：
  - 用户点击麦克风即可直接录音，停止后自动发给 Gemma4，不需要手动选文件上传或再点发送。
- 已完成：
  - `frontend/src/components/ChatBox.tsx`
    - 录音新增实时计时显示（`mm:ss`）。
    - 麦克风录音停止后自动触发表单提交，直接进入后端音频上传与对话链路。
    - 保留音频文件选择入口作为补充方式（录音权限受限时可回退）。
- 验证：
  - `cd frontend && npm run build` 无新增报错；仍是历史 TS6133（`SessionList.tsx`、`ui/Dialog.tsx`）。

## 46. 2026-04-06 音频默认行为由“逐字转写”改为“理解后回答”

- 问题：
  - 纯音频请求在无文本提示词时，默认 prompt 是 verbatim transcription，导致模型只复述音频内容。
- 已完成：
  - `backend/app/models/schema.py`
    - `has_audio && !has_message` 的默认消息改为“理解音频并回答问题；无明确问题则总结并给建议”。
  - `frontend/src/lib/api.ts`
    - `streamMessage` 的 `hasAudio && !message` 默认提示词同步改为上述回答导向版本。
- 验证：
  - `python3 -m compileall backend/app` 通过。
  - `cd frontend && npm run build` 仍是历史 TS6133（与本次改动无新增关联）。

## 47. 2026-04-06 Gemma4 视频理解第一阶段接入优化（前后端链路）

- 目标：
  - 对齐官方 Gemma4 Video Understanding 示例，打通项目内 `video_url` 输入与本地视频上传链路。
  - 前端将“上传音频文件”入口替换为“上传视频文件”，用于视频理解请求。
- 已完成：
  - `backend/app/models/schema.py`
    - `ChatRequest` 新增 `video_url`、`video_urls`。
    - `ChatMessage` 新增 `has_video`、`video_url`、`video_urls`。
    - 新增 `ChatVideoUploadResponse` 与 `supports_video` 能力字段。
    - 校验逻辑支持 video-only 请求（自动补视频总结默认提示词）。
  - `backend/app/services/chat_video_service.py`
    - 新增本地视频缓存服务（上传校验、缓存 TTL/容量控制、`video_id` 解析、文件读取）。
  - `backend/app/api/chat.py`
    - 新增 `POST /api/chat/videos/upload` 与 `GET /api/chat/videos/{video_id}`。
    - `/api/chat/` 与 `/api/chat/stream` 全链路透传视频输入，并在 metadata 返回 `has_video/video_url/video_urls/video_count`。
    - 本地相对视频 URL 会自动转换为 `LOCAL_MEDIA_BASE_URL + /api/chat/videos/{video_id}` 后发送给 vLLM。
    - `multimodal_mode` 细分新增 `gemma4_native_video`、`gemma4_native_image_video` 等视频相关标签。
  - `backend/app/services/llm_service.py`
    - vLLM 用户消息构造支持 `video_url` block，格式对齐官方：`content=[video_url..., text]`（也兼容图/音/视频混合）。
    - `generate_response/stream_response/astream_response` 全链路新增视频参数透传。
  - `backend/app/services/session_service.py`
    - 会话持久化支持视频字段读写。
  - `frontend/src/lib/api.ts`、`frontend/src/types/index.ts`
    - 新增 `uploadChatVideo`、`chatVideoUpload/chatVideo` API。
    - 请求与响应类型补齐 `video_url/video_urls/has_video/video_count` 与 `supports_video`。
  - `frontend/src/components/ChatBox.tsx`
    - 将音频文件上传按钮替换为视频文件上传按钮。
    - 发送前先上传视频，再在聊天请求中引用 `/api/chat/videos/{video_id}`。
    - 消息历史新增视频播放器渲染，Profile 能力展示新增 `Video`。
  - 配置与部署文档同步：
    - `backend/app/core/config.py`、`backend/.env.example` 新增视频缓存配置与 `LOCAL_MEDIA_BASE_URL`。
    - `deploy/vllm/start_vllm.sh` 与 `deploy/vllm/*.env.example` 默认多模态预算更新为含 `video`（如 `{"image":4,"audio":1,"video":1}`）。
    - `README.md`、`deploy/vllm/README.md` 补充视频链路说明与示例。
- 验证：
  - `python3 -m compileall backend/app` 通过。
  - `cd frontend && npm run build` 失败原因不变，仍是历史 TS6133（`SessionList.tsx`、`ui/Dialog.tsx`），无本次新增报错。

## 48. 2026-04-06 视频链路改为本地 data_url 优先（避免 vLLM 反向访问 backend）

- 问题：
  - 远端 vLLM 无法访问本地 backend 的 `/api/chat/videos/{video_id}`，导致 `video_url` 拉取失败（Connection refused）。
- 已完成：
  - `backend/app/core/config.py`
    - 新增 `LOCAL_VIDEO_TRANSPORT_MODE`（`data_url|url`，默认 `data_url`）。
    - 新增 `MAX_VIDEO_DATA_URL_BYTES`（默认 50MB）。
  - `backend/app/services/chat_video_service.py`
    - 新增 `resolve_chat_video_data_url(video_id)`，将缓存视频转换为 `data:video/*;base64`。
  - `backend/app/api/chat.py`
    - 本地上传视频默认走 `data_url` 方式发给 vLLM，不再依赖 vLLM 回连 backend。
    - 当视频超出 `MAX_VIDEO_DATA_URL_BYTES` 时后端直接返回 413，避免隐式回退到 URL 传输导致远端连接失败。
  - `backend/.env.example`、`README.md`
    - 新增上述配置说明与行为说明。
- 验证：
  - 待执行：重启 backend 后做视频请求联调（关注 metadata `mode_warnings` 是否出现超限回退提示）。

## 49. 2026-04-06 前端“请先启动后端”误判修复（localhost/127.0.0.1）

- 问题：
  - 后端实际可用，但前端仍提示“请先启动后端服务”。
  - 常见触发条件：前端从 `127.0.0.1:5173` 访问，后端 CORS 默认仅放行 `localhost:5173`。
- 已完成：
  - `backend/app/core/config.py`
    - 默认 `CORS_ORIGINS` 增加 `http://127.0.0.1:5173` 与 `http://127.0.0.1:3000`。
  - `frontend/src/lib/api.ts`
    - 当未设置 `VITE_API_URL` 时，默认 API 地址由浏览器当前 host 自动推导为 `http(s)://<current-host>:8000`，避免固定 `localhost` 导致跨主机误连。
- 验证：
  - 需要重启 backend + frontend dev server 后生效。

## 50. 2026-04-06 本地 IPv6 localhost 歧义修复（前端默认后端地址）

- 问题：
  - 在部分本机环境中，`localhost:8000` 会优先解析到 IPv6 `::1`，请求可能命中非后端进程或空响应；前端因此误判“后端未启动”。
  - 现象是后端日志没有对应请求 `INFO` 行，或仅偶发成功。
- 已完成：
  - `frontend/src/lib/api.ts`
    - `VITE_API_URL` 未设置时：若前端 host 为 `localhost/127.0.0.1/::1`，默认固定使用 `http://127.0.0.1:8000`。
    - 其他 host 仍保持 `http(s)://<current-host>:8000` 推导策略。
  - `README.md`
    - 前端启动说明新增 `VITE_API_URL=http://127.0.0.1:8000` 建议，并补充“本地优先 127.0.0.1”的说明。
- 验证：
  - 本机验证 `curl --ipv4 http://localhost:8000/api/health/` 返回 200。
  - 本机验证 `curl --ipv6 http://localhost:8000/api/health/` 为空响应（复现歧义场景）。

## 51. 2026-04-06 Gemma4 Thinking 官方结构化接入（reasoning_content / SSE reasoning）

- 目标：
  - 对齐官方 Gemma4 thinking 模式：`extra_body.chat_template_kwargs.enable_thinking=true` 下，优先消费 `reasoning_content` 字段，不再依赖拼接文本解析。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 新增 `generate_response_structured()`：返回 `reasoning_content` 与 `final_content`。
    - vLLM 调用链改为结构化提取 `reasoning_content/content`，工具调用路径同样返回结构化结果。
    - 新增 `stream_response_events()/astream_response_events()`：流式按事件区分 `reasoning` 与 `answer` token。
    - 保留原 `generate_response/stream_response/astream_response` 兼容层（旧调用仍可工作）。
  - `backend/app/api/chat.py`
    - 非流式 `POST /api/chat/` 改为使用结构化返回并落库 `reasoning_content/final_content`。
    - 流式 `POST /api/chat/stream` 新增 SSE `reasoning` 事件；`token` 事件专用于最终回答 token。
    - `done` 事件稳定返回：`full_content`、`reasoning_content`、`final_content`、`display_content`。
    - 保留旧 `thought ... Final answer` 文本的兼容分割兜底。
  - `frontend/src/lib/api.ts`
    - `streamMessage()` 新增 `onReasoningToken` 回调，消费 `reasoning` SSE 事件。
  - `frontend/src/components/ChatBox.tsx`
    - 新增实时 `streamingAssistantReasoning` 状态，流式阶段思考内容进入“思考过程”面板实时渲染。
    - 最终态优先使用后端结构化字段，保留旧格式兼容解析兜底。
  - 文档同步：
    - `README.md` “最新进展”新增本项接入说明。
- 验证：
  - `python3 -m py_compile backend/app/services/llm_service.py backend/app/api/chat.py backend/app/models/schema.py` 通过。
  - `cd frontend && npm run test -- thinkingParser` 通过（8/8）。
  - `cd frontend && npm run build` 失败原因不变：历史 TS6133（`SessionList.tsx`、`ui/Dialog.tsx`），与本次改动无直接关系。

## 52. 2026-04-06 Gemma4 Tool Calling 官方链路增强（多轮工具 + thinking/tool 组合）

- 目标：
  - 对齐官方 Gemma4 工具调用流程：支持模型多轮 `tool_calls`、支持与 thinking 同时开启、并可与多模态输入共用同一对话链路。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 扩展内置工具集合：
      - `get_weather(location, unit)`（Open-Meteo 实时天气）
      - `calculate_wind_chill(temperature, wind_speed_kmh, unit)`
      - 保留 `get_current_time`、`math_calculator`
    - 重构 `_generate_vllm_with_modes()` 的工具执行逻辑：
      - 从“固定两步”改为“最多 `MAX_TOOL_CALL_ROUNDS` 轮”循环
      - 每轮支持多个 `tool_calls`
      - thinking 开启时累计保留各轮 `reasoning_content`
      - 最终返回结构化 `reasoning_content/final_content`
    - 保持 `thinking + tool calling + multimodal` 共存调用路径一致（都走同一 `messages/tools/extra_body` 请求构造）。
  - `backend/app/core/config.py`
    - 新增 `MAX_TOOL_CALL_ROUNDS`（默认 4）
    - 新增 `WEATHER_TOOL_ENABLED`（默认 true）
    - 新增 `WEATHER_TOOL_TIMEOUT_SECONDS`（默认 12）
    - 新增对应校验
  - `backend/.env.example`
    - 补齐上述三项配置模板
  - `README.md`
    - 更新 Tool Calling 内置工具说明与配置说明
- 验证：
  - `python3 -m py_compile backend/app/services/llm_service.py backend/app/core/config.py` 通过。

## 53. 2026-04-06 Tool Calling 执行轨迹透传与前端可视化

- 目标：
  - 在前端可直接查看 agent 的工具执行链路（工具名、参数、输出、耗时），支持流式和历史回放。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 工具调用循环中记录 `tool_traces`：`id/name/arguments/output/elapsed_ms/ts`。
    - `generate_response_structured()` 输出新增 `tool_traces`。
    - `stream_response_events()/astream_response_events()` 新增 `tool_trace` 事件类型。
  - `backend/app/api/chat.py`
    - 非流式 `/api/chat/` metadata 新增 `tool_traces/tool_trace_count`，并持久化到会话消息。
    - 流式 `/api/chat/stream` 新增 SSE `tool_trace` 事件；`done` 事件携带 `tool_traces/tool_trace_count`。
  - `backend/app/models/schema.py` + `backend/app/services/session_service.py`
    - `ChatMessage` 与会话读写新增 `tool_traces` 字段，支持历史回放。
  - `frontend/src/lib/api.ts` + `frontend/src/components/ChatBox.tsx`
    - `streamMessage()` 新增 `onToolTrace` 回调，消费 SSE `tool_trace`。
    - 聊天气泡新增“工具执行轨迹”折叠区，展示每次工具调用的参数、输出与耗时。
  - 文档同步：
    - `README.md` 最新进展新增 Tool Calling 轨迹可视化说明。
- 验证：
  - `python3 -m py_compile backend/app/services/llm_service.py backend/app/api/chat.py backend/app/services/session_service.py backend/app/models/schema.py` 通过。
  - `cd frontend && npm run build` 失败原因不变：历史 TS6133（`SessionList.tsx`、`ui/Dialog.tsx`），无本次新增报错。

## 54. 2026-04-06 Gemma4 结构化输出接入优化（response_format json_schema）

- 目标：
  - 对齐 vLLM 官方 Gemma4 recipe 的结构化输出用法，支持 `response_format={"type":"json_schema", ...}` 并贯通到项目聊天链路。
- 已完成：
  - `backend/app/models/schema.py`
    - `ChatRequest` 新增 `response_format` 字段（OpenAI-compatible）。
    - 增加请求校验：当前仅允许 `type=json_schema`，且要求 `json_schema.name/schema` 必填。
    - `ChatModeConfigResponse` 新增 `supports_structured_output`。
  - `backend/app/api/chat.py`
    - 模式能力映射新增 `supports_structured_output`。
    - 请求级新增结构化输出开关解析：`effective_structured_output`。
    - 当 `LLM_PROVIDER!=vllm` 且请求 `response_format` 时返回 400（避免静默不生效）。
    - `/api/chat/` 与 `/api/chat/stream` 调用层透传 `response_format` 到 LLM 服务。
    - metadata 新增：
      - `enable_structured_output`
      - `requested_structured_output`
      - `response_format_type`
      - `response_schema_name`
  - `backend/app/services/llm_service.py`
    - `generate_response_structured()/stream_response_events()` 等全链路函数新增 `response_format` 参数。
    - vLLM 非流式、流式、工具调用路径均透传 `response_format` 到 `chat.completions.create`。
    - 与 `enable_thinking=true` 可同时开启。
  - `frontend/src/lib/api.ts` + `frontend/src/types/index.ts`
    - 请求/metadata 类型补齐 `response_format` 与结构化输出状态字段，便于后续 UI 接入。
  - 文档同步：
    - `README.md` 新增结构化输出能力说明与请求示例。
- 验证：
  - 待执行：`python3 -m py_compile backend/app/services/llm_service.py backend/app/api/chat.py backend/app/models/schema.py`

## 55. 2026-04-06 天气工具增强：支持中文城市名查询

- 目标：
  - 修复 `get_weather` 对中文城市（如“沈阳市”）查询失败的问题。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 新增中文城市别名映射（`CN_CITY_ALIAS_TO_EN`），优先将常见中文城市转换为英文名后再调用 Open-Meteo geocoding。
    - 新增中文地名归一化逻辑：去空格、去常见行政后缀（如“市/省/自治区/特别行政区”）并构建多候选回退查询。
    - 新增候选结果优选逻辑：中文输入时优先中国（`country_code=CN`）结果，并按 `feature_code + population` 评分选最优城市。
    - 天气工具返回增加 `location_query_resolved`，便于调试“原始输入 -> 实际地理编码查询词”。
- 验证：
  - `python3 -m py_compile backend/app/services/llm_service.py` 通过。

## 56. 2026-04-06 Tool Calling 扩展：news / FX / stock

- 目标：
  - 按需求新增可玩性更强且可直接落地的工具：`search_news`、`get_exchange_rate`、`stock_quote`。
- 已完成：
  - `backend/app/services/llm_service.py`
    - `BUILTIN_TOOLS` 新增三个函数定义：
      - `search_news(query, limit)`
      - `get_exchange_rate(base_currency, target_currency, amount?)`
      - `stock_quote(symbol)`
    - `_execute_builtin_tool()` 新增三个执行分支：
      - `search_news`：调用 HN Algolia API，返回标题/链接/作者/时间等结构化结果。
      - `get_exchange_rate`：调用 `open.er-api.com`，返回汇率与可选金额换算。
      - `stock_quote`：调用 Yahoo Finance Quote API，返回价格、涨跌幅、交易所等字段。
    - 三个工具均复用现有 `httpx` 与超时配置，异常路径统一返回 JSON error。
  - `README.md`
    - 更新内置工具清单与模式说明章节。
- 验证：
  - `python3 -m py_compile backend/app/services/llm_service.py` 通过。

## 57. 2026-04-06 时间工具优化：新增北京时间专用工具

- 目标：
  - 解决“时间查询返回不是北京时间”的体验问题，提供稳定可调用的北京时间工具。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 新增 `get_beijing_time` 工具（固定 `Asia/Shanghai`）。
    - 优化 `get_current_time`：支持按 `timezone` 参数返回目标时区本地时间，不再只返回 UTC。
    - 时间返回结构统一包含：
      - `timezone`
      - `current_time_local`
      - `current_time_utc`
      - `utc_offset`
      - `unix_timestamp`
  - `README.md`
    - 内置工具列表新增 `get_beijing_time` 说明。
- 验证：
  - 待执行：`python3 -m py_compile backend/app/services/llm_service.py`

## 58. 2026-04-06 Tool Calling 扩展：更常用的通用工具集

- 目标：
  - 增加高频通用工具，覆盖日常问答中的单位换算、日期信息、文本统计、唯一 ID 生成场景。
- 已完成：
  - `backend/app/services/llm_service.py`
    - `BUILTIN_TOOLS` 新增：
      - `convert_unit(value, from_unit, to_unit)`：支持温度/长度/重量换算。
      - `get_calendar_info(date?, timezone?)`：返回星期、ISO 周、是否周末。
      - `text_stats(text)`：返回字符数/去空白字符数/词数/行数/中文字符数。
      - `generate_uuid(version?)`：当前支持 UUID v4。
    - 新增单位别名归一化与换算逻辑（`UNIT_ALIASES`、`LENGTH_TO_METER`、`WEIGHT_TO_GRAM`）。
    - `_execute_builtin_tool()` 增加以上四个工具执行分支与统一 JSON 错误返回。
  - `README.md`
    - 更新 Tool Calling 内置工具清单与说明。
- 验证：
  - 待执行：`python3 -m py_compile backend/app/services/llm_service.py`

## 59. 2026-04-06 Tool Calling 扩展：无外部 API 的趣味工具集

- 目标：
  - 增加一批本地可执行、无需外部网络 API 的“好玩 + 实用”工具。
- 已完成：
  - `backend/app/services/llm_service.py`
    - `BUILTIN_TOOLS` 新增：
      - `random_number(min?, max?)`
      - `coin_flip(count?)`
      - `roll_dice(sides?, count?)`
      - `generate_password(length?, include_symbols?)`
      - `hash_text(text, algorithm?)`
      - `base64_codec(mode, text)`
    - `_execute_builtin_tool()` 新增以上 6 个工具执行分支，全部本地运行，不依赖外部 API。
  - `README.md`
    - 更新 Tool Calling 内置工具清单。
- 验证：
  - 待执行：`python3 -m py_compile backend/app/services/llm_service.py`

## 35. 2026-04-08 deploy/vllm 单档位收敛

- 已按“仅全能档位”收敛 `deploy/vllm` 三个文件：
  - `deploy/vllm/start_vllm.sh`：
    - 删除多档位分支逻辑（`rag_text/vision/full/benchmark/extreme`）
    - 固定为单一 `full_featured` 运行模式
    - 默认开启 `ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`、`ENABLE_ASYNC_SCHEDULING=1`
    - 默认多模态预算改为 `LIMIT_MM_PER_PROMPT={"image":4,"audio":1}`（对齐官方 Gemma4 full-featured 示例）
  - `deploy/vllm/.env.example`：
    - 同步为单档位配置模板，仅保留兼容字段 `DEPLOY_PROFILE=full_featured`
  - `deploy/vllm/README.md`：
    - 删除多档位说明与不存在示例文件引用，改为单一路径启动说明
- 后端配置结论：
  - 当前 `backend/.env` 已是 `VLLM_DEPLOY_PROFILE=full_featured`，无需额外修改。

## 36. 2026-04-08 deploy/vllm 按官方 Gemma4 recipe 演示化整理

- 目标：按 vLLM 官方 Gemma4 文档收敛 `deploy/vllm` 三文件，并补充详细注释用于演示。
- 已完成：
  - `deploy/vllm/start_vllm.sh`
    - 按官方 full-featured 能力集合组织参数：
      - `--reasoning-parser gemma4`
      - `--enable-auto-tool-choice --tool-call-parser gemma4`
      - `--limit-mm-per-prompt image=4,audio=1`
      - `--async-scheduling`
    - 补齐分段注释（模型标识、网络、官方核心参数、项目吞吐参数、可选高级参数）。
  - `deploy/vllm/.env.example`
    - 改为演示版环境模板，逐项中文注释。
    - 默认 `LIMIT_MM_PER_PROMPT=image=4,audio=1`（去除 `video` 预算写法）。
  - `deploy/vllm/README.md`
    - 改为演示导向文档：目标能力、参数讲解、演示话术、常见问题。
- 校验：
  - `bash -n deploy/vllm/start_vllm.sh` 通过。

## 37. 2026-04-08 deploy/vllm（按实际服务器口径）再次优化

- 背景：用户已替换为“服务器实际在用版本”，需继续按官方 Gemma4 配置收敛并适配现网口径。
- 已完成：
  - `deploy/vllm/start_vllm.sh`
    - 移除多档位分支，固定单档位 `full_featured`。
    - 保留并强化官方关键参数：
      - `--limit-mm-per-prompt image=4,audio=1`
      - `--reasoning-parser gemma4`
      - `--enable-auto-tool-choice --tool-call-parser gemma4`
      - `--async-scheduling`
    - 全量中文注释，按“模型/网络/官方核心/项目吞吐/可选参数”分段。
    - 保持用户现网端口默认值 `PORT=6008`。
  - `deploy/vllm/.env.example`
    - 改为中文注释演示模板，默认值与脚本一致（含 `PORT=6008`）。
  - `deploy/vllm/README.md`
    - 改为中文演示文档，统一端口与参数口径，补充讲解与 FAQ。
- 校验：
  - `bash -n deploy/vllm/start_vllm.sh` 通过。

## 38. 2026-04-08 vLLM 启动报错修复（OMP_NUM_THREADS）

- 问题：服务器启动 Gemma4 vLLM 时出现：
  - `libgomp: Invalid value for environment variable OMP_NUM_THREADS`
  - `RuntimeError: set_num_threads expects a positive integer`
- 原因：`OMP_NUM_THREADS` 被设置为非法值（空/0/非数字），导致 torch 线程数设置失败。
- 已修复：
  - `deploy/vllm/start_vllm.sh`
    - 新增线程环境变量兜底逻辑：
      - 若 `OMP_NUM_THREADS` 非法，自动改为 `8`
      - 若未设置，默认导出 `OMP_NUM_THREADS=8`
  - `deploy/vllm/.env.example`
    - 增加 `OMP_NUM_THREADS` 注释说明（必须为正整数）。
  - `deploy/vllm/README.md`
    - 增加该报错的原因与处理说明。
- 校验：
  - `bash -n deploy/vllm/start_vllm.sh` 通过。

## 39. 2026-04-09 vLLM 无网场景修复（HF 本地缓存优先）

- 背景：
  - 服务器日志出现 `Network is unreachable` / `Error retrieving file list`，vLLM 启动阶段访问 Hugging Face API 失败。
- 已修复：
  - `deploy/vllm/start_vllm.sh`
    - 新增 `MODEL_PATH`（本地模型目录优先）。
    - 新增缓存自动解析：`AUTO_RESOLVE_LOCAL_MODEL=1` 时，自动从 `HUGGINGFACE_HUB_CACHE/HF_HUB_CACHE/HF_HOME/hub` 查找 `MODEL_NAME` 对应 snapshot。
    - 新增 `FORCE_LOCAL_MODEL=1`：强制仅使用本地模型，未找到本地目录时快速失败。
    - 新增网络探测 + 离线降级：`AUTO_OFFLINE_IF_NO_NETWORK=1` 时自动设置 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`。
    - 启动日志新增 `MODEL_RESOLVED/MODEL_SOURCE/NETWORK_STATUS`，便于排查到底走的是远端还是本地。
  - `deploy/vllm/.env.example`
    - 新增离线相关模板变量（`MODEL_PATH/AUTO_RESOLVE_LOCAL_MODEL/FORCE_LOCAL_MODEL/AUTO_OFFLINE_IF_NO_NETWORK/HF_NETWORK_CHECK_TIMEOUT/HF_LOCAL_SEARCH_ROOTS`）。
  - `deploy/vllm/README.md`
    - 新增无公网环境的本地启动示例与参数说明。
    - FAQ 新增 `Network is unreachable` 处理路径。
  - `README.md`
    - 增加离线本地模型优先启动说明（`MODEL_PATH + FORCE_LOCAL_MODEL`）。
- 校验：
  - `bash -n deploy/vllm/start_vllm.sh` 通过。

## 40. 2026-04-09 对话附件支持 mp3 并自动走 Gemma4 音频分析

- 背景：
  - 新需求：在“上传文件”入口支持 `mp3`，并在上传的是音频时使用 Gemma4 音频能力分析，而不是按文本文件解析。
- 已完成：
  - `backend/app/api/chat.py`
    - 新增“文件附件音频识别”逻辑：当 `file/file_name/file_format` 为音频（含 `mp3`）时，自动转换为 `data:audio/*` 并并入音频多模态输入。
    - 文件为音频时跳过文本文件解析（不再走 `txt/md/pdf/csv/json/log` 的文件上下文注入路径）。
    - 模式能力校验改为基于实际解析后的输入（含文件转音频场景），确保会触发 `supports_audio` 约束。
    - 会话落库中，音频文件不再标记为文本附件，统一按 `has_audio/audio_url` 记录。
  - `backend/app/models/schema.py`
    - `ChatRequest` 新增“音频文件附件”判定；当仅上传音频文件且无文本时，默认消息改为音频模式（空白占位），避免误用“请阅读文件”提示词。
  - `frontend/src/components/ChatBox.tsx`
    - 回形针文件选择新增 `.mp3`。
    - 通过回形针选择 `mp3` 时，自动切换到音频附件状态并复用已有音频上传链路（`uploadChatAudio -> /api/chat/audios/{audio_id}`）。
    - 文件选择错误提示与按钮标题同步更新，明确 `mp3` 会自动音频分析。
  - `README.md`
    - 更新“对话附件上传”说明，补充 `mp3` 自动进入 Gemma4 音频理解链路。

## 41. 2026-04-09 mp3 音频兼容性修复（发送前自动转 wav）

- 背景：
  - 用户反馈：上传 `mp3` 并输入提示词后，模型仍提示“音频缺失”。
  - 研判：部分 vLLM/Gemma4 组合对 `audio/mpeg` 解码不稳定，需要统一转 `wav` 提升兼容性。
- 已完成：
  - `backend/app/api/chat.py`
    - 新增 `_normalize_audio_for_vllm()`：在发送到 vLLM 前，按配置使用 `ffmpeg` 将音频转为 `wav`（单声道 16kHz）。
    - 覆盖三条音频入模路径：
      - `file` 附件转音频路径（含 mp3 文件）
      - 本地 `/api/chat/audios/{audio_id}` 路径
      - 远端 `audio_url` 预取路径
    - 当 `ffmpeg` 不可用或转码失败时自动回退原始音频并写日志，不阻断请求。
  - `backend/app/core/config.py` + `backend/.env.example`
    - 新增配置：
      - `CHAT_AUDIO_TRANSCODE_TO_WAV`（默认 true）
      - `FFMPEG_BINARY`（默认 `ffmpeg`）
      - `AUDIO_TRANSCODE_TIMEOUT_SECONDS`（默认 30）
  - `README.md`
    - 补充上述音频转码配置说明。

## 42. 2026-04-09 Gemma4 Tool Calling 新增实时联网搜索工具

- 背景：
  - 用户反馈 `search_news` 返回结果不够“实时”，希望能直接查到最新资讯，且按 Gemma4 的 function tool 标注方式接入。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 新增 `search_web_realtime` 内置工具（OpenAI-compatible function schema）。
    - 实现 Bing News RSS 实时检索链路，按时间倒序拉取并支持 `freshness` 时间窗口过滤（`hour/day/week/month/any`）。
    - 解析并返回结构化字段：`title/url/source/published_at_utc/snippet`，附带 `searched_at_utc`。
    - `search_news` 升级为兼容别名：优先走实时检索，失败时回退到 HN Algolia 并返回 `provider_error`。
    - 在 `enable_tool_calling=true` 时追加工具策略提示：遇到“最新/实时/当前资讯”优先调用实时搜索工具。
  - `README.md`
    - 更新工具清单，新增 `search_web_realtime` 说明与参数建议。

## 43. 2026-04-09 实时搜索容错增强（Google/Baidu 回退 + 验证页识别）

- 背景：
  - 实测部分环境在实时搜索时会出现 RSS 解析异常（如空响应/非 XML），且不同网络环境对 Google/Baidu 的可达性差异较大。
- 已完成：
  - `backend/app/services/llm_service.py`
    - 实时检索 provider 调整为 `Bing -> Google -> Baidu`，按顺序自动回退。
    - 新增 RSS 解析容错：空响应、非 XML 时返回可读错误并继续下一个 provider。
    - 新增 Baidu HTML 解析与安全验证识别：命中“百度安全验证/captcha”时返回明确错误原因。
    - 新增 `market/language` 解析逻辑：当只传 `language` 时自动推断 `market`，减少区域参数错配。
