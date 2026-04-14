# Gemma4 vLLM 部署说明（演示版）

本目录用于演示：如何按 vLLM 官方 Gemma4 recipe，启动一个“全能力”服务（单档位）。

官方文档：
- https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html

## 1. 演示目标

当前脚本固定为 `full_featured`，默认能力：
- 文本对话
- 图片理解
- 音频理解
- Thinking（推理内容）
- Tool Calling（函数调用）

对应官方 full-featured 关键参数：
- `--reasoning-parser gemma4`
- `--enable-auto-tool-choice --tool-call-parser gemma4`
- `--limit-mm-per-prompt '{"image":4,"audio":1}'`
- `--async-scheduling`

## 2. 安装（Linux + NVIDIA）

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

如果你要演示音频能力，请确保当前 vLLM 版本已包含音频支持（以官方文档版本说明为准）。

## 3. 启动服务

```bash
cp deploy/vllm/.env.example .env.vllm
set -a && source .env.vllm && set +a
bash deploy/vllm/start_vllm.sh
```

默认监听地址：`0.0.0.0:6008`

无公网/弱网环境建议直接走本地模型目录：

```bash
set -a && source .env.vllm && set +a
MODEL_PATH=/root/models/gemma-4-E4B-it \
FORCE_LOCAL_MODEL=1 \
bash deploy/vllm/start_vllm.sh
```

如果模型已下载到 Hugging Face 缓存（例如 `/root/autodl-tmp/hf-cache/hub`），可不填 `MODEL_PATH`，
脚本会在缓存中自动解析 `MODEL_NAME` 对应 snapshot 目录并优先使用本地文件。

## 4. 参数讲解（演示可直接说）

- `MODEL_NAME`：实际加载模型 ID
- `MODEL_PATH`：本地模型目录（填写后优先级最高）
- `SERVED_MODEL_NAME`：API 暴露模型名，后端 `VLLM_MODEL` 要和它一致
- `MAX_MODEL_LEN=32768`：上下文长度上限
- `GPU_MEMORY_UTILIZATION=0.95`：显存利用率（默认偏稳）
- `LIMIT_MM_PER_PROMPT='{"image":4,"audio":1}'`：每个请求最多 4 图 + 1 音频
- `ENABLE_REASONING=1`：开启 Thinking
- `ENABLE_TOOL_CALLING=1`：开启 Tool Calling
- `ENABLE_ASYNC_SCHEDULING=1`：提升高并发吞吐
- `AUTO_RESOLVE_LOCAL_MODEL=1`：自动从 HF 缓存解析本地 snapshot
- `FORCE_LOCAL_MODEL=1`：强制仅使用本地模型目录
- `AUTO_OFFLINE_IF_NO_NETWORK=1`：网络不可达时自动设离线模式

项目额外参数（非官方 full-featured 必选）：
- `MAX_NUM_SEQS`
- `MAX_NUM_BATCHED_TOKENS`
- `--structured-outputs-config '{"backend":"xgrammar"}'`（支持 json_schema 输出）

## 5. 健康检查

```bash
curl http://127.0.0.1:6008/v1/models \
  -H "Authorization: Bearer ${API_KEY:-EMPTY}"
```

如果返回包含 `gemma4-e4b-it`（或你自定义的 `SERVED_MODEL_NAME`），说明服务正常。

## 6. 对接 AssistantBot 后端

在 `backend/.env` 中配置：

```bash
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://<你的服务器IP>:6008/v1
VLLM_API_KEY=EMPTY
VLLM_MODEL=gemma4-e4b-it
VLLM_DEPLOY_PROFILE=full_featured
```

然后重启后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

## 7. 常见问题

- 报错 `Transformers does not recognize architecture gemma4`：按第 2 节重装依赖。
- 后端提示模型不匹配：检查 `VLLM_MODEL` 是否等于 `SERVED_MODEL_NAME`。
- Thinking / Tool 不生效：确认 `ENABLE_REASONING=1`、`ENABLE_TOOL_CALLING=1`。
- 报错 `--limit-mm-per-prompt ... cannot be converted to json.loads`：
  - 原因：你当前 vLLM 版本要求该参数是 JSON，而不是 `image=4,audio=1`。
  - 处理：使用 `LIMIT_MM_PER_PROMPT='{"image":4,"audio":1}'`。
  - 兼容：当前脚本会自动把旧写法 `image=4,audio=1` 转为 JSON。
- 报错 `libgomp: Invalid value for environment variable OMP_NUM_THREADS` 或 `set_num_threads expects a positive integer`：
  - 原因：`OMP_NUM_THREADS` 不是正整数（如空值、0、非法字符串）。
  - 处理：脚本已自动兜底为 `OMP_NUM_THREADS=8`。
  - 你也可以手动指定：`export OMP_NUM_THREADS=8` 后再启动。
- 报错 `Network is unreachable` / `Error retrieving file list`：
  - 原因：容器无法访问 Hugging Face API（无路由或代理不可达）。
  - 处理 1（推荐）：设置 `MODEL_PATH=/abs/path/to/model` + `FORCE_LOCAL_MODEL=1` 走离线本地目录。
  - 处理 2：仅设置缓存目录（`HF_HOME`/`HUGGINGFACE_HUB_CACHE`），保持 `AUTO_RESOLVE_LOCAL_MODEL=1`，脚本会自动查找 snapshot。
  - 处理 3：恢复外网或配置可用代理/镜像后再用远端仓库名启动。
