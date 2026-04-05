#!/usr/bin/env bash
set -euo pipefail

if ! command -v vllm >/dev/null 2>&1; then
  echo "[ERROR] vllm command not found. Install first: pip install vllm"
  exit 1
fi

MODEL_NAME=${MODEL_NAME:-google/gemma-4-E4B-it}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-gemma4-e4b-it}
PORT=${PORT:-8100}
HOST=${HOST:-0.0.0.0}
API_KEY=${API_KEY:-EMPTY}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.92}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-16384}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-8}
ENABLE_ASYNC_SCHEDULING=${ENABLE_ASYNC_SCHEDULING:-1}
GENERATION_CONFIG=${GENERATION_CONFIG:-vllm}
LIMIT_MM_PER_PROMPT=${LIMIT_MM_PER_PROMPT:-}
DEPLOY_PROFILE=${DEPLOY_PROFILE:-rag_text}
DISABLE_PREFIX_CACHING=${DISABLE_PREFIX_CACHING:-0}
ENABLE_REASONING=${ENABLE_REASONING:-0}
ENABLE_TOOL_CALLING=${ENABLE_TOOL_CALLING:-0}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-}
MM_PROCESSOR_KWARGS=${MM_PROCESSOR_KWARGS:-}

# Ignore backend-side env vars if user sourced a shared .env file.
unset VLLM_BASE_URL VLLM_MODEL LLM_PROVIDER VLLM_API_KEY

case "$DEPLOY_PROFILE" in
  rag_text)
    PROFILE_MM_DEFAULT='{"image":0,"audio":0}'
    ;;
  vision)
    PROFILE_MM_DEFAULT='{"image":2,"audio":0}'
    ;;
  full)
    PROFILE_MM_DEFAULT='{"image":4,"audio":1}'
    ;;
  benchmark)
    PROFILE_MM_DEFAULT='{"image":0,"audio":0}'
    DISABLE_PREFIX_CACHING=1
    ;;
  *)
    echo "[WARN] Unknown DEPLOY_PROFILE='$DEPLOY_PROFILE', using custom LIMIT_MM_PER_PROMPT only."
    PROFILE_MM_DEFAULT=""
    ;;
esac

if [[ -z "$LIMIT_MM_PER_PROMPT" && -n "${PROFILE_MM_DEFAULT:-}" ]]; then
  LIMIT_MM_PER_PROMPT="$PROFILE_MM_DEFAULT"
fi

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
  --dtype auto
)

if [[ -n "$TENSOR_PARALLEL_SIZE" ]]; then
  CMD+=(--tensor-parallel-size "$TENSOR_PARALLEL_SIZE")
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
  LIMIT_MM_ARG="$LIMIT_MM_PER_PROMPT"

  # vLLM expects JSON for --limit-mm-per-prompt on recent versions.
  # Accept legacy "image=2,audio=0" format and convert it automatically.
  if [[ "$LIMIT_MM_ARG" != \{* ]]; then
    JSON_ITEMS=()
    IFS=',' read -ra KV_PAIRS <<< "$LIMIT_MM_ARG"
    for PAIR in "${KV_PAIRS[@]}"; do
      KEY="${PAIR%%=*}"
      VALUE="${PAIR#*=}"
      KEY="${KEY//[[:space:]]/}"
      VALUE="${VALUE//[[:space:]]/}"

      if [[ -z "$KEY" || -z "$VALUE" ]]; then
        echo "[ERROR] Invalid LIMIT_MM_PER_PROMPT entry: '$PAIR'"
        echo "[ERROR] Use JSON (e.g. '{\"image\":2,\"audio\":0}') or legacy 'image=2,audio=0'"
        exit 1
      fi

      if [[ ! "$VALUE" =~ ^[0-9]+$ ]]; then
        echo "[ERROR] LIMIT_MM_PER_PROMPT value must be integer, got '$VALUE' for key '$KEY'"
        exit 1
      fi

      JSON_ITEMS+=("\"$KEY\":$VALUE")
    done

    LIMIT_MM_ARG="{${JSON_ITEMS[*]}}"
    LIMIT_MM_ARG="${LIMIT_MM_ARG// /,}"
    echo "[INFO] Converted legacy LIMIT_MM_PER_PROMPT='$LIMIT_MM_PER_PROMPT' -> '$LIMIT_MM_ARG'"
  fi

  CMD+=(--limit-mm-per-prompt "$LIMIT_MM_ARG")
fi

echo "[INFO] Launch profile: $DEPLOY_PROFILE"
echo "[INFO] Model: $MODEL_NAME (served as $SERVED_MODEL_NAME)"
echo "[INFO] max_model_len=$MAX_MODEL_LEN max_num_seqs=$MAX_NUM_SEQS gpu_memory_utilization=$GPU_MEMORY_UTILIZATION"

exec "${CMD[@]}" \
  "$@"
