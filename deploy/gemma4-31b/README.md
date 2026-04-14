# vLLM Server Deployment (Gemma-4-31B-IT-AWQ on NVIDIA GPU)

本目录提供 AssistantBot 的 Gemma-4-31B-IT-AWQ vLLM 部署方案（Linux + NVIDIA GPU）。

官方参考：
- https://huggingface.co/QuantTrio/gemma-4-31B-it-AWQ
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#quick-start-single-gpu
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html#configuration-tips

## 1. 服务器准备

- OS: Ubuntu 22.04+
- Python: 3.10+
- GPU: NVIDIA（推荐 80GB+ 显存，如 H100/A100 或多卡组合）
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
pip install -U "transformers>=4.42"
```

## 2. 启动服务（默认单卡 AWQ）

```bash
cp deploy/gemma4-31b/.env.example .env.gemma4-31b
set -a && source .env.gemma4-31b && set +a
bash deploy/gemma4-31b/start_vllm.sh
```

默认监听：`0.0.0.0:6006`

默认关键参数：
- `MODEL_NAME=QuantTrio/gemma-4-31B-it-AWQ`
- `SERVED_MODEL_NAME=gemma4-31b-it-awq`
- `GPU_MEMORY_UTILIZATION=0.80`
- `MAX_MODEL_LEN=4096`
- `MAX_NUM_SEQS=4`
- `MAX_NUM_BATCHED_TOKENS=4096`
- `LIMIT_MM_PER_PROMPT=image=0 audio=0` (纯文本模式)
- `ENABLE_ASYNC_SCHEDULING=1`

## 3. 纯文本模式

默认使用纯文本模式，完全跳过多模态分析：

- `LIMIT_MM_PER_PROMPT=image=0 audio=0` - 禁用图片和音频处理
- `ENABLE_REASONING=0` - 关闭推理模式
- `ENABLE_TOOL_CALLING=0` - 关闭工具调用

支持的 `LIMIT_MM_PER_PROMPT` 格式：
- JSON: `{"image":0,"audio":0}`
- 空格分隔: `image=0 audio=0` (推荐)

## 4. 显存需求参考

Gemma-4-31B-IT-AWQ (AWQ 量化)：
- 理论显存约 18-20GB（AWQ 量化）
- 推荐单卡 40GB+（如 A100 40GB / 3090 24GB 较紧张）
- 多卡可设置 `TENSOR_PARALLEL_SIZE`

若显存不足（CUDA OOM）：
- 先降 `GPU_MEMORY_UTILIZATION`（0.95 -> 0.85 -> 0.80）
- 再降 `MAX_MODEL_LEN`（32768 -> 8192 -> 4096）
- 设置 `LIMIT_MM_PER_PROMPT='image=0 audio=0'` 确保纯文本模式

## 5. 健康检查

```bash
curl http://127.0.0.1:6006/v1/models \
  -H "Authorization: Bearer ${API_KEY:-EMPTY}"
```

## 6. 接入 AssistantBot 后端

在 `backend/.env` 中设置：

```bash
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://<YOUR_SERVER_IP>:6006/v1
VLLM_API_KEY=EMPTY
VLLM_MODEL=gemma4-31b-it-awq
```

连接方式建议：
- 首选：`WireGuard/Tailscale` 组网
- 备选：Nginx/Caddy 反向代理 + TLS

然后重启后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

## 7. 多卡部署

若单卡显存不足，可使用多卡：

```bash
set -a && source .env.gemma4-31b && set +a
TENSOR_PARALLEL_SIZE=2 bash deploy/gemma4-31b/start_vllm.sh
```

## 8. 生产化下一步

- 用 systemd 托管 `start_vllm.sh`
- 反向代理（Nginx）+ TLS
- 接入监控（QPS、TTFT、错误率、GPU 显存/利用率）
