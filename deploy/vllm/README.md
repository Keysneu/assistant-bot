# vLLM Server Deployment (Gemma 4 E4B on RTX 5090 32GB)

本目录提供 AssistantBot 的 Gemma4 vLLM 部署方案（Linux + NVIDIA GPU）。

官方参考（建议先读）：
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#quick-start-single-gpu
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#configuration-tips
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#full-featured-server-launch
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#benchmarking

## 1. 服务器准备

- OS: Ubuntu 22.04+
- Python: 3.10+
- GPU: NVIDIA（本目录默认单卡 5090 32GB）
- CUDA: 推荐 12.9/13.0 兼容栈

按官方 Gemma4 recipe 安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip uninstall -y vllm transformers tokenizers
pip install -U --pre vllm \
  --extra-index-url https://wheels.vllm.ai/nightly/cu129 \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --index-strategy unsafe-best-match
pip install -U "transformers==5.5.0"
```

## 2. 启动服务（默认单卡 E4B）

```bash
cp deploy/vllm/.env.example .env.vllm
set -a && source .env.vllm && set +a
bash deploy/vllm/start_vllm.sh
```

默认监听：`0.0.0.0:8100`

默认关键参数：
- `MODEL_NAME=google/gemma-4-E4B-it`
- `SERVED_MODEL_NAME=gemma4-e4b-it`
- `GPU_MEMORY_UTILIZATION=0.92`
- `MAX_MODEL_LEN=16384`
- `MAX_NUM_SEQS=8`
- `ENABLE_ASYNC_SCHEDULING=1`

## 3. 部署档位（完整展示模型能力）

`start_vllm.sh` 新增 `DEPLOY_PROFILE`：

- `rag_text`：文本/RAG 优先
- `vision`：图文问答优先
- `full`：全能力（文本+图像+音频预算，支持 thinking/tool 组合）
- `benchmark`：压测档位（自动关闭 prefix caching，便于一致性测试）

默认映射（可被 `LIMIT_MM_PER_PROMPT` 覆盖）：
- `rag_text` -> `{"image":0,"audio":0}`
- `vision` -> `{"image":2,"audio":0}`
- `full` -> `{"image":4,"audio":1}`
- `benchmark` -> `{"image":0,"audio":0}` + `--no-enable-prefix-caching`

## 4. 与官方 Configuration Tips 的对应关系

- `--max-model-len`：按实际业务设置，不盲目拉满，节省 KV Cache 显存。
- `--gpu-memory-utilization 0.90~0.95`：提高显存利用率，提升有效并发。
- `--limit-mm-per-prompt`：
  - 文本场景：`{"image":0,"audio":0}`
  - 图像场景：`{"image":2,"audio":0}`
- `--async-scheduling`：开启以提升吞吐。
- 压测场景建议 `--no-enable-prefix-caching`（脚本用 `DEPLOY_PROFILE=benchmark` 自动处理）。

## 5. 全能力开关（thinking / tool calling / 动态视觉）

在 `.env.vllm` 中按需开启：

```bash
DEPLOY_PROFILE=full
ENABLE_REASONING=1
ENABLE_TOOL_CALLING=1
# 例如动态视觉相关 kwargs（按实际 vLLM 版本支持项填写）
MM_PROCESSOR_KWARGS=
```

脚本会自动追加：
- `--reasoning-parser gemma4`
- `--enable-auto-tool-choice --tool-call-parser gemma4`

多卡场景可设置：

```bash
TENSOR_PARALLEL_SIZE=2
```

## 6. 健康检查

```bash
curl http://127.0.0.1:8100/v1/models \
  -H "Authorization: Bearer ${API_KEY:-EMPTY}"
```

## 7. 接入 AssistantBot 后端

在 `backend/.env` 中设置：

```bash
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://<YOUR_SERVER_IP>:8100/v1
VLLM_API_KEY=EMPTY
VLLM_MODEL=gemma4-e4b-it
```

然后重启后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

## 8. 调参建议（5090 单卡）

- 显存紧张：先降 `MAX_NUM_SEQS`（8 -> 4），再降 `MAX_MODEL_LEN`（16384 -> 8192）。
- 时延优先：降低并发和 `MAX_TOKENS`，并保持 `DEPLOY_PROFILE=rag_text`。
- 多模态优先：使用 `DEPLOY_PROFILE=vision`，避免音频预算占用。
- 若报 `Transformers does not recognize architecture gemma4`：按第 1 节重装依赖。

## 9. 生产化下一步

- 用 systemd 托管 `start_vllm.sh`。
- 反向代理（Nginx）+ TLS。
- 接入监控（QPS、TTFT、错误率、GPU 显存/利用率）。
