#!/usr/bin/env bash
set -euo pipefail

if ! command -v vllm >/dev/null 2>&1; then
  echo "[ERROR] vllm command not found. Install first: pip install vllm"
  exit 1
fi

MODEL_NAME=${MODEL_NAME:-QuantTrio/gemma-4-31B-it-AWQ}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-gemma4-31b-it-awq}
PORT=${PORT:-6006}
HOST=${HOST:-0.0.0.0}
API_KEY=${API_KEY:-EMPTY}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.80}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-4096}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-4}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-4096}
ENABLE_ASYNC_SCHEDULING=${ENABLE_ASYNC_SCHEDULING:-1}
GENERATION_CONFIG=${GENERATION_CONFIG:-vllm}

# 纯文本模式配置 - 使用空格分隔格式可完全跳过多模态分析
LIMIT_MM_PER_PROMPT=${LIMIT_MM_PER_PROMPT:-'image=0 audio=0'}
ENABLE_REASONING=${ENABLE_REASONING:-0}
ENABLE_TOOL_CALLING=${ENABLE_TOOL_CALLING:-0}
DISABLE_PREFIX_CACHING=${DISABLE_PREFIX_CACHING:-0}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-}

# Ignore backend-side env vars if user sourced a shared .env file.
unset VLLM_BASE_URL VLLM_MODEL LLM_PROVIDER VLLM_API_KEY

trim_spaces() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

CMD=(
  vllm serve "$MODEL_NAME"
  --host "$HOST"
  --port "$PORT"
  --api-key "$API_KEY"
  --served-model-name "$SERVED_MODEL_NAME"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-seqs "$MAX_NUM_SEQS"
  --generation-config "$GENERATION_CONFIG"
  --structured-outputs-config '{"backend":"xgrammar"}'
  --dtype auto
)

if [[ -n "$TENSOR_PARALLEL_SIZE" ]]; then
  CMD+=(--tensor-parallel-size "$TENSOR_PARALLEL_SIZE")
fi

if [[ -n "$MAX_NUM_BATCHED_TOKENS" ]]; then
  CMD+=(--max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS")
fi

if [[ "$ENABLE_ASYNC_SCHEDULING" == "1" ]]; then
  CMD+=(--async-scheduling)
fi

if [[ "$DISABLE_PREFIX_CACHING" == "1" ]]; then
  CMD+=(--no-enable-prefix-caching)
fi

if [[ "$ENABLE_REASONING" == "1" ]]; then
  CMD+=(--reasoning-parser gemma4)
fi

if [[ "$ENABLE_TOOL_CALLING" == "1" ]]; then
  CMD+=(--enable-auto-tool-choice --tool-call-parser gemma4)
fi

if [[ -n "$MM_PROCESSOR_KWARGS" ]]; then
  CMD+=(--mm-processor-kwargs "$MM_PROCESSOR_KWARGS")
fi

if [[ -n "$LIMIT_MM_PER_PROMPT" ]]; then
  LIMIT_MM_RAW="$(trim_spaces "$LIMIT_MM_PER_PROMPT")"
  LIMIT_MM_WORK="$LIMIT_MM_RAW"

  # Accept:
  # 1) JSON: {"image":4,"audio":1}
  # 2) relaxed braces: {image:4,audio:1}
  # 3) legacy kv: image=4,audio=1
  # 4) space-separated kv: image=0 audio=0 (preferred for pure text)
  if [[ "$LIMIT_MM_WORK" == \{* && "$LIMIT_MM_WORK" == *\} ]]; then
    LIMIT_MM_WORK="${LIMIT_MM_WORK#\{}"
    LIMIT_MM_WORK="${LIMIT_MM_WORK%\}}"
    IFS=',' read -ra KV_PAIRS <<< "$LIMIT_MM_WORK"
  else
    IFS=' ' read -ra KV_PAIRS <<< "$LIMIT_MM_WORK"
  fi

  JSON_ITEMS=()
  for PAIR in "${KV_PAIRS[@]}"; do
    PAIR="$(trim_spaces "$PAIR")"
    if [[ -z "$PAIR" ]]; then
      continue
    fi

    if [[ "$PAIR" == *"="* ]]; then
      KEY="${PAIR%%=*}"
      VALUE="${PAIR#*=}"
    elif [[ "$PAIR" == *":"* ]]; then
      KEY="${PAIR%%:*}"
      VALUE="${PAIR#*:}"
    else
      echo "[ERROR] Invalid LIMIT_MM_PER_PROMPT entry: '$PAIR'"
      echo "[ERROR] Use one of: '{\"image\":2,\"audio\":0}' / '{image:2,audio:0}' / 'image=2,audio=0'"
      exit 1
    fi

    KEY="$(trim_spaces "$KEY")"
    VALUE="$(trim_spaces "$VALUE")"

    if [[ ${#KEY} -ge 2 && "$KEY" == \"*\" ]]; then
      KEY="${KEY:1:${#KEY}-2}"
    fi
    if [[ ${#KEY} -ge 2 && "$KEY" == \'*\' ]]; then
      KEY="${KEY:1:${#KEY}-2}"
    fi
    if [[ ${#VALUE} -ge 2 && "$VALUE" == \"*\" ]]; then
      VALUE="${VALUE:1:${#VALUE}-2}"
    fi
    if [[ ${#VALUE} -ge 2 && "$VALUE" == \'*\' ]]; then
      VALUE="${VALUE:1:${#VALUE}-2}"
    fi

    if [[ -z "$KEY" || -z "$VALUE" ]]; then
      echo "[ERROR] Invalid LIMIT_MM_PER_PROMPT entry: '$PAIR'"
      exit 1
    fi

    if [[ ! "$KEY" =~ ^[a-zA-Z0-9_]+$ ]]; then
      echo "[ERROR] LIMIT_MM_PER_PROMPT key must match [a-zA-Z0-9_], got '$KEY'"
      exit 1
    fi

    if [[ ! "$VALUE" =~ ^[0-9]+$ ]]; then
      echo "[ERROR] LIMIT_MM_PER_PROMPT value must be integer, got '$VALUE' for key '$KEY'"
      exit 1
    fi

    JSON_ITEMS+=("\"$KEY\":$VALUE")
  done

  if [[ ${#JSON_ITEMS[@]} -eq 0 ]]; then
    echo "[ERROR] LIMIT_MM_PER_PROMPT is empty after parsing: '$LIMIT_MM_PER_PROMPT'"
    exit 1
  fi

  LIMIT_MM_ARG="{${JSON_ITEMS[*]}}"
  LIMIT_MM_ARG="${LIMIT_MM_ARG// /,}"
  if [[ "$LIMIT_MM_RAW" != "$LIMIT_MM_ARG" ]]; then
    echo "[INFO] Normalized LIMIT_MM_PER_PROMPT='$LIMIT_MM_PER_PROMPT' -> '$LIMIT_MM_ARG'"
  fi

  CMD+=(--limit-mm-per-prompt "$LIMIT_MM_ARG")
fi

echo "[INFO] Mode: Pure Text Analysis (multimodal disabled)"
echo "[INFO] Model: $MODEL_NAME (served as $SERVED_MODEL_NAME)"
echo "[INFO] max_model_len=$MAX_MODEL_LEN max_num_seqs=$MAX_NUM_SEQS max_num_batched_tokens=${MAX_NUM_BATCHED_TOKENS:-auto} gpu_memory_utilization=$GPU_MEMORY_UTILIZATION"

exec "${CMD[@]}" \
  "$@"
