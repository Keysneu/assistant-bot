# vLLM Benchmark Tool

用于测试 Gemma4 在 vLLM 部署下的性能，当前提供两类脚本：
- 直连 vLLM OpenAI API（推荐，用于测模型服务本身性能）
- 走本地后端 `/api/chat/`（用于测端到端链路性能）

## 1. 前置条件

直连 vLLM：
- vLLM 服务已启动并可访问（如 `http://127.0.0.1:8100/v1`）
- 已知 `VLLM_MODEL`（默认 `gemma4-e4b-it`）

后端链路压测：
- 本地后端已启动：`http://127.0.0.1:8000`
- 后端 `.env` 已配置为 `LLM_PROVIDER=vllm`
- 若 vLLM 在远程服务器，需要隧道或网络连通

## 2. Gemma4 直连 vLLM 压测（推荐）

脚本：`vllm_test/benchmark_gemma4_vllm.py`

快速执行：

```bash
python3 vllm_test/benchmark_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --requests 80 \
  --concurrency 8 \
  --max-tokens 256
```

流式模式（会统计 TTFT）：

```bash
python3 vllm_test/benchmark_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --model gemma4-e4b-it \
  --requests 40 \
  --concurrency 8 \
  --stream
```

环境变量方式（可选）：

```bash
export VLLM_BASE_URL=http://127.0.0.1:8100/v1
export VLLM_API_KEY=EMPTY
export VLLM_MODEL=gemma4-e4b-it
python3 vllm_test/benchmark_gemma4_vllm.py
```

输出目录：
- `vllm_test/results/gemma4_direct_<timestamp>/requests.jsonl`
- `vllm_test/results/gemma4_direct_<timestamp>/summary.txt`
- `vllm_test/results/gemma4_direct_<timestamp>/summary.json`

核心指标：
- 成功率、avg/p50/p90/p95/max 延迟
- 请求吞吐（req/s）
- 生成吞吐（tok/s，基于 `usage.completion_tokens`）
- TTFT（仅 `--stream`）
- 支持 `--unique-prompt-per-request`（请求级唯一前缀，减少 prefix cache 复用，适合做 KV cache 压力场景）

## 3. 高 KV Cache 压力测试（长上下文 + 高并发）

脚本：`vllm_test/kv_cache_stress_gemma4_vllm.py`

用途：
- 自动构造超长上下文 prompt（默认至少 64000 字符）
- 默认按 `/v1/models` 的 `max_model_len` 自动放大 prompt（目标 `92%` 上下文占用，支持关闭）
- 默认使用高并发 + 大输出（`concurrency=32`、`max_tokens=2048`）
- 默认开启 `unique_prompt_per_request`，减少请求间前缀缓存共享，拉高 KV cache 占用

执行命令：

```bash
python3 vllm_test/kv_cache_stress_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --requests 192 \
  --concurrency 32 \
  --max-tokens 2048
```

常用对比：

```bash
# 关闭请求级唯一前缀，用于和 prefix cache 复用场景做对比
python3 vllm_test/kv_cache_stress_gemma4_vllm.py --shared-prompt

# 关闭按 model_max_len 自动放大 prompt（仅使用 --min-prompt-chars）
python3 vllm_test/kv_cache_stress_gemma4_vllm.py --no-auto-prompt-size
```

## 4. 后端链路压测（本地后端 -> vLLM）

快速执行：

```bash
bash vllm_test/run_benchmark.sh
```

自动扫并发并给推荐上限：

```bash
bash vllm_test/sweep_concurrency.sh
```

常用参数示例：

```bash
CONCURRENCY=5 \
ROUNDS=5 \
TIMEOUT=180 \
MESSAGE="请总结RAG在企业知识库中的价值" \
bash vllm_test/run_benchmark.sh
```

```bash
MIN_CONCURRENCY=1 \
MAX_CONCURRENCY=10 \
ROUNDS=2 \
TARGET_P95=8.0 \
MIN_SUCCESS_RATE=99.0 \
bash vllm_test/sweep_concurrency.sh
```

## 5. 建议联动观察

压测时同时观察 vLLM 服务日志中的：
- `Running`
- `Waiting`
- `Avg generation throughput`

判断依据：
- `Waiting` 经常大于 0：并发触发排队
- `p95` 偏高但成功率高：优先降低 `max_tokens`
- `failed` 增加：优先排查网络、超时、服务端错误日志

## 6. 严格测试套件（多阶段 + SLO 门禁）

脚本：`vllm_test/strict_suite_gemma4_vllm.py`

用途：按“严格”场景连续执行多轮压测，并按阈值给出 `PASS/FAIL`。

默认阶段：
- `s1_stream_ttft`：流式响应与 TTFT 稳定性
- `s2_high_concurrency`：高并发非流式压力
- `s3_long_generation`：长输出压力（`max_tokens=1024`）
- `s4_soak_stream`：持续流式稳定性（soak）

执行命令：

```bash
python3 vllm_test/strict_suite_gemma4_vllm.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it \
  --strict-model
```

常用参数：

```bash
# 缩短 soak 阶段请求数（默认 320）
python3 vllm_test/strict_suite_gemma4_vllm.py --soak-requests 160

# 发现失败就立即停止后续场景
python3 vllm_test/strict_suite_gemma4_vllm.py --fail-fast
```

输出目录：
- `vllm_test/results/strict_suite_<timestamp>/suite_summary.txt`
- `vllm_test/results/strict_suite_<timestamp>/suite_report.json`
- `vllm_test/results/strict_suite_<timestamp>/runs/<scenario>/...`

返回码：
- `0`：所有场景通过
- `2`：有场景失败（触发门禁）

## 7. 部署能力探测（Gemma4 功能验收）

脚本：`vllm_test/probe_gemma4_capabilities.py`

用途：
- 对运行中的 Gemma4 vLLM 服务做功能覆盖检查
- 覆盖项：`models`、`text_generation`、`multimodal`、`structured_output`、`thinking_mode`、`tool_calling`
- 适合作为“部署后验收”与“发布前回归”的快速清单

执行命令：

```bash
python3 vllm_test/probe_gemma4_capabilities.py \
  --base-url http://127.0.0.1:8100/v1 \
  --api-key EMPTY \
  --model gemma4-e4b-it
```

若要求全能力全部通过（任一失败即非零退出）：

```bash
python3 vllm_test/probe_gemma4_capabilities.py --require-full
```

输出目录：
- `vllm_test/results/cap_probe_<timestamp>/capability_report.json`
