#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Gemma4 vLLM 启动脚本（演示版 / 单一档位）
#
# 设计原则：
# 1) 对齐 vLLM 官方 Gemma4 full-featured 配置能力集合
# 2) 只保留一个固定档位：full_featured（不再做多档位分支）
# 3) 参数尽量少且可解释，便于现场演示
#
# 官方参考：
# https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html
# ============================================================

if ! command -v vllm >/dev/null 2>&1; then
  echo "[ERROR] 未找到 vllm 命令，请先安装：pip install vllm"
  exit 1
fi

# ----------------------
# 0) 线程环境变量兜底
# ----------------------
# 你日志中的报错：
# - libgomp: Invalid value for environment variable OMP_NUM_THREADS
# - RuntimeError: set_num_threads expects a positive integer
# 通常由 OMP_NUM_THREADS 被设置为非法值（空、0、非数字）导致。
if [[ -n "${OMP_NUM_THREADS:-}" && ! "${OMP_NUM_THREADS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "[WARN] 检测到非法 OMP_NUM_THREADS='${OMP_NUM_THREADS}'，自动改为 8"
  export OMP_NUM_THREADS=8
fi
# 若未设置，则给一个稳妥默认值，避免 vLLM/torch 在某些环境推导出 0
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"

# ----------------------
# 1) 模型与服务标识
# ----------------------
# 实际加载的模型 ID
MODEL_NAME=${MODEL_NAME:-google/gemma-4-E4B-it}
# 本地模型目录（优先级最高，若存在则直接使用本地）
MODEL_PATH=${MODEL_PATH:-}
# 对外暴露给 OpenAI-compatible /v1/models 的模型名
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-gemma4-e4b-it}

# ----------------------
# 1.1) 本地缓存/离线策略
# ----------------------
# 自动在 Hugging Face 缓存中解析 MODEL_NAME 对应快照目录
AUTO_RESOLVE_LOCAL_MODEL=${AUTO_RESOLVE_LOCAL_MODEL:-1}
# 强制仅使用本地模型（找不到本地目录则直接失败）
FORCE_LOCAL_MODEL=${FORCE_LOCAL_MODEL:-0}
# 检测到网络不可达时，自动开启离线环境变量
AUTO_OFFLINE_IF_NO_NETWORK=${AUTO_OFFLINE_IF_NO_NETWORK:-1}
# 网络探测超时（秒）
HF_NETWORK_CHECK_TIMEOUT=${HF_NETWORK_CHECK_TIMEOUT:-3}
# 额外本地搜索目录（逗号或冒号分隔）
HF_LOCAL_SEARCH_ROOTS=${HF_LOCAL_SEARCH_ROOTS:-}

# ----------------------
# 2) 服务监听信息
# ----------------------
# 你当前服务器使用 6008，这里保持一致
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-6008}
API_KEY=${API_KEY:-EMPTY}

# ----------------------
# 3) 官方 full-featured 关键参数
# ----------------------
# 上下文长度（官方示例常见值）
MAX_MODEL_LEN=${MAX_MODEL_LEN:-32768}
# 显存利用率，演示优先稳定默认 0.90（可按机器上调）
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.95}
# 多模态预算：当前 vLLM 版本通常要求 JSON（推荐）
LIMIT_MM_PER_PROMPT=${LIMIT_MM_PER_PROMPT:-'{"image":4,"audio":1}'}
# 官方 full-featured 包含异步调度
ENABLE_ASYNC_SCHEDULING=${ENABLE_ASYNC_SCHEDULING:-1}
# 官方 Gemma4 推理 / 工具调用解析器
ENABLE_REASONING=${ENABLE_REASONING:-1}
ENABLE_TOOL_CALLING=${ENABLE_TOOL_CALLING:-1}

# ----------------------
# 4) 项目侧吞吐参数（便于压测/演示）
# ----------------------
MAX_NUM_SEQS=${MAX_NUM_SEQS:-2}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-65536}
GENERATION_CONFIG=${GENERATION_CONFIG:-vllm}

# ----------------------
# 5) 可选参数（默认关闭/留空）
# ----------------------
# 多卡时再设置，例如 2 / 4
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-}
# 动态视觉参数（JSON 字符串），例如 {"max_soft_tokens":560}
MM_PROCESSOR_KWARGS=${MM_PROCESSOR_KWARGS:-}
# 压测一致性场景可手动关闭 prefix cache
DISABLE_PREFIX_CACHING=${DISABLE_PREFIX_CACHING:-0}

# 兼容旧环境变量：保留但不参与分支
DEPLOY_PROFILE=${DEPLOY_PROFILE:-full_featured}

# 避免 source 共享 env 时，误带 backend 变量影响当前脚本
unset VLLM_BASE_URL VLLM_MODEL LLM_PROVIDER VLLM_API_KEY

trim_spaces() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

append_unique_dir() {
  local dir="$1"
  local existed
  dir="$(trim_spaces "$dir")"
  [[ -z "$dir" ]] && return 0
  if [[ "$dir" == "~"* ]]; then
    dir="${dir/#\~/$HOME}"
  fi
  for existed in "${HF_SEARCH_DIRS[@]:-}"; do
    if [[ "$existed" == "$dir" ]]; then
      return 0
    fi
  done
  HF_SEARCH_DIRS+=("$dir")
}

is_hf_repo_id() {
  local value="$1"
  [[ "$value" == */* && "$value" != */./* && "$value" != /* ]]
}

resolve_snapshot_from_hf_cache() {
  local repo_id="$1"
  local hub_cache_dir="$2"
  local repo_key repo_dir ref_file ref_hash candidate

  repo_key="${repo_id//\//--}"
  repo_dir="${hub_cache_dir%/}/models--${repo_key}"
  [[ -d "$repo_dir" ]] || return 1

  ref_file="$repo_dir/refs/main"
  if [[ -f "$ref_file" ]]; then
    ref_hash="$(tr -d '[:space:]' < "$ref_file")"
    if [[ -n "$ref_hash" && -d "$repo_dir/snapshots/$ref_hash" ]]; then
      if [[ -f "$repo_dir/snapshots/$ref_hash/config.json" ]]; then
        printf '%s\n' "$repo_dir/snapshots/$ref_hash"
        return 0
      fi
    fi
  fi

  candidate=""
  for candidate_dir in "$repo_dir"/snapshots/*; do
    if [[ -d "$candidate_dir" && -f "$candidate_dir/config.json" ]]; then
      candidate="$candidate_dir"
    fi
  done

  if [[ -n "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  return 1
}

probe_hf_network() {
  local timeout="$1"
  local endpoint
  if ! command -v curl >/dev/null 2>&1; then
    return 2
  fi
  if curl -sS -I --max-time "$timeout" https://huggingface.co >/dev/null 2>&1; then
    return 0
  fi
  endpoint="$(trim_spaces "${HF_ENDPOINT:-}")"
  if [[ -n "$endpoint" ]]; then
    if curl -sS -I --max-time "$timeout" "${endpoint%/}" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

# 兼容两种 LIMIT_MM_PER_PROMPT 输入：
# 1) JSON: {"image":4,"audio":1}
# 2) 旧写法: image=4,audio=1
normalize_limit_mm_per_prompt() {
  local raw work key value pair
  local items=()
  raw="$(trim_spaces "$1")"

  if [[ -z "$raw" ]]; then
    echo ""
    return 0
  fi

  if [[ "$raw" == \{* && "$raw" == *\} ]]; then
    echo "$raw"
    return 0
  fi

  IFS=',' read -ra pairs <<< "$raw"
  for pair in "${pairs[@]}"; do
    pair="$(trim_spaces "$pair")"
    [[ -z "$pair" ]] && continue
    if [[ "$pair" != *"="* ]]; then
      echo "[ERROR] LIMIT_MM_PER_PROMPT 非法：$raw" >&2
      echo "[ERROR] 请使用 JSON（推荐）或旧写法 image=4,audio=1" >&2
      exit 1
    fi
    key="$(trim_spaces "${pair%%=*}")"
    value="$(trim_spaces "${pair#*=}")"
    if [[ ! "$key" =~ ^[a-zA-Z0-9_]+$ || ! "$value" =~ ^[0-9]+$ ]]; then
      echo "[ERROR] LIMIT_MM_PER_PROMPT 非法项：$pair" >&2
      exit 1
    fi
    items+=("\"$key\":$value")
  done

  if [[ ${#items[@]} -eq 0 ]]; then
    echo "[ERROR] LIMIT_MM_PER_PROMPT 为空：$raw" >&2
    exit 1
  fi

  work="{${items[*]}}"
  work="${work// /,}"
  echo "$work"
}

LIMIT_MM_PER_PROMPT="$(normalize_limit_mm_per_prompt "$LIMIT_MM_PER_PROMPT")"

# ----------------------
# 6) 模型路径解析（本地优先）
# ----------------------
MODEL_RESOLVED="$MODEL_NAME"
MODEL_SOURCE="remote_repo"
LOCAL_MODEL_FOUND=0
NETWORK_STATUS="unknown"
HF_SEARCH_DIRS=()

if [[ -n "$MODEL_PATH" ]]; then
  MODEL_PATH="$(trim_spaces "$MODEL_PATH")"
  if [[ ! -d "$MODEL_PATH" ]]; then
    echo "[ERROR] MODEL_PATH 不存在或不是目录：$MODEL_PATH" >&2
    exit 1
  fi
  MODEL_RESOLVED="$MODEL_PATH"
  MODEL_SOURCE="model_path"
  LOCAL_MODEL_FOUND=1
elif [[ -d "$MODEL_NAME" ]]; then
  MODEL_RESOLVED="$MODEL_NAME"
  MODEL_SOURCE="model_name_local_dir"
  LOCAL_MODEL_FOUND=1
fi

if [[ "$LOCAL_MODEL_FOUND" == "0" && "$AUTO_RESOLVE_LOCAL_MODEL" == "1" ]]; then
  if is_hf_repo_id "$MODEL_NAME"; then
    if [[ -n "$HF_LOCAL_SEARCH_ROOTS" ]]; then
      IFS=',:' read -ra EXTRA_HF_DIRS <<< "$HF_LOCAL_SEARCH_ROOTS"
      for one_dir in "${EXTRA_HF_DIRS[@]}"; do
        append_unique_dir "$one_dir"
      done
    fi
    append_unique_dir "${HUGGINGFACE_HUB_CACHE:-}"
    append_unique_dir "${HF_HUB_CACHE:-}"
    if [[ -n "${HF_HOME:-}" ]]; then
      append_unique_dir "${HF_HOME%/}/hub"
    fi
    append_unique_dir "$HOME/.cache/huggingface/hub"

    for one_cache_dir in "${HF_SEARCH_DIRS[@]:-}"; do
      if [[ ! -d "$one_cache_dir" ]]; then
        continue
      fi
      if MODEL_CACHED_PATH="$(resolve_snapshot_from_hf_cache "$MODEL_NAME" "$one_cache_dir")"; then
        MODEL_RESOLVED="$MODEL_CACHED_PATH"
        MODEL_SOURCE="hf_cache_snapshot"
        LOCAL_MODEL_FOUND=1
        break
      fi
    done
  fi
fi

if probe_hf_network "$HF_NETWORK_CHECK_TIMEOUT"; then
  NETWORK_STATUS="ok"
else
  case $? in
    1) NETWORK_STATUS="unreachable" ;;
    2) NETWORK_STATUS="skip(no_curl)" ;;
    *) NETWORK_STATUS="unknown" ;;
  esac
fi

if [[ "$FORCE_LOCAL_MODEL" == "1" && "$LOCAL_MODEL_FOUND" == "0" ]]; then
  echo "[ERROR] FORCE_LOCAL_MODEL=1，但未找到可用本地模型目录。" >&2
  echo "[ERROR] 请设置 MODEL_PATH=/abs/path/to/model 或确保 HF 缓存已存在 $MODEL_NAME。" >&2
  exit 1
fi

if [[ "$AUTO_OFFLINE_IF_NO_NETWORK" == "1" && "$NETWORK_STATUS" == "unreachable" ]]; then
  export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
  export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
fi

if [[ "$NETWORK_STATUS" == "unreachable" && "$LOCAL_MODEL_FOUND" == "0" && "$MODEL_SOURCE" == "remote_repo" ]]; then
  echo "[ERROR] 当前网络不可达，且 MODEL_NAME=$MODEL_NAME 未解析到本地缓存目录。" >&2
  echo "[ERROR] 建议设置 MODEL_PATH 指向已下载模型目录，或先联网执行 huggingface-cli download。" >&2
  exit 1
fi

CMD=(
  vllm serve "$MODEL_RESOLVED"
  --host "$HOST"
  --port "$PORT"
  --api-key "$API_KEY"
  --served-model-name "$SERVED_MODEL_NAME"
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --limit-mm-per-prompt "$LIMIT_MM_PER_PROMPT"
  --max-num-seqs "$MAX_NUM_SEQS"
  --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS"
  --generation-config "$GENERATION_CONFIG"
  # 项目需要结构化输出能力（response_format=json_schema）
  --structured-outputs-config '{"backend":"xgrammar"}'
  --dtype auto
)

# 官方 full-featured 推荐开启
if [[ "$ENABLE_ASYNC_SCHEDULING" == "1" ]]; then
  CMD+=(--async-scheduling)
fi

# 压测场景可选
if [[ "$DISABLE_PREFIX_CACHING" == "1" ]]; then
  CMD+=(--no-enable-prefix-caching)
fi

# Gemma4 thinking
if [[ "$ENABLE_REASONING" == "1" ]]; then
  CMD+=(--reasoning-parser gemma4)
fi

# Gemma4 tool calling
if [[ "$ENABLE_TOOL_CALLING" == "1" ]]; then
  CMD+=(--enable-auto-tool-choice --tool-call-parser gemma4)
fi

# 多卡可选
if [[ -n "$TENSOR_PARALLEL_SIZE" ]]; then
  CMD+=(--tensor-parallel-size "$TENSOR_PARALLEL_SIZE")
fi

# 动态视觉可选
if [[ -n "$MM_PROCESSOR_KWARGS" ]]; then
  CMD+=(--mm-processor-kwargs "$MM_PROCESSOR_KWARGS")
fi

echo "[INFO] 启动模式: full_featured (官方能力集合)"
echo "[INFO] MODEL_NAME=$MODEL_NAME"
echo "[INFO] MODEL_RESOLVED=$MODEL_RESOLVED"
echo "[INFO] MODEL_SOURCE=$MODEL_SOURCE"
echo "[INFO] SERVED_MODEL_NAME=$SERVED_MODEL_NAME"
echo "[INFO] ENDPOINT=$HOST:$PORT"
echo "[INFO] MAX_MODEL_LEN=$MAX_MODEL_LEN GPU_MEMORY_UTILIZATION=$GPU_MEMORY_UTILIZATION"
echo "[INFO] LIMIT_MM_PER_PROMPT=$LIMIT_MM_PER_PROMPT"
echo "[INFO] ASYNC=$ENABLE_ASYNC_SCHEDULING REASONING=$ENABLE_REASONING TOOL_CALLING=$ENABLE_TOOL_CALLING"
echo "[INFO] MAX_NUM_SEQS=$MAX_NUM_SEQS MAX_NUM_BATCHED_TOKENS=$MAX_NUM_BATCHED_TOKENS"
echo "[INFO] NETWORK_STATUS=$NETWORK_STATUS HF_HUB_OFFLINE=${HF_HUB_OFFLINE:-0} TRANSFORMERS_OFFLINE=${TRANSFORMERS_OFFLINE:-0}"

exec "${CMD[@]}" "$@"
