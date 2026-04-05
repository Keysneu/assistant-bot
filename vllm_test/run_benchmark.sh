#!/usr/bin/env bash
set -euo pipefail

# One-click local benchmark for assistant-bot -> vLLM path.
# Default target is local backend, which then proxies to vLLM.

URL="${URL:-http://127.0.0.1:8000/api/chat/}"
CONCURRENCY="${CONCURRENCY:-5}"
ROUNDS="${ROUNDS:-3}"
STREAM="${STREAM:-false}"
USE_SEARCH="${USE_SEARCH:-false}"
MESSAGE="${MESSAGE:-请用120字解释什么是RAG，并给一个实际应用例子。}"
TIMEOUT="${TIMEOUT:-180}"
OUT_DIR="${OUT_DIR:-./vllm_test/results}"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${OUT_DIR}/${TS}"

mkdir -p "${RUN_DIR}"

cat <<INFO
[Benchmark Config]
URL=${URL}
CONCURRENCY=${CONCURRENCY}
ROUNDS=${ROUNDS}
STREAM=${STREAM}
USE_SEARCH=${USE_SEARCH}
TIMEOUT=${TIMEOUT}s
OUT_DIR=${RUN_DIR}
INFO

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

# warmup
curl -sS --max-time "${TIMEOUT}" "${URL}" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"warmup\",\"use_search\":${USE_SEARCH},\"stream\":${STREAM}}" \
  >/dev/null || true

for round in $(seq 1 "${ROUNDS}"); do
  ROUND_FILE="${RUN_DIR}/round_${round}.log"
  : >"${ROUND_FILE}"

  echo "[Round ${round}] start"
  seq 1 "${CONCURRENCY}" | xargs -I{} -P"${CONCURRENCY}" sh -c '
    idx="$1"
    out_file="$2"
    url="$3"
    message="$4"
    use_search="$5"
    stream="$6"
    timeout="$7"

    payload=$(printf "{\"message\":\"%s\",\"use_search\":%s,\"stream\":%s}" "$message" "$use_search" "$stream")
    result=$(curl -sS --max-time "$timeout" -o /tmp/vllm_bench_${idx}.json -w "code=%{http_code} total=%{time_total} namelookup=%{time_namelookup} connect=%{time_connect} starttransfer=%{time_starttransfer} size=%{size_download}" "$url" -H "Content-Type: application/json" -d "$payload" || echo "code=000 total=${timeout} namelookup=0 connect=0 starttransfer=0 size=0")
    echo "req=${idx} ${result}" >>"$out_file"
  ' _ {} "${ROUND_FILE}" "${URL}" "${MESSAGE}" "${USE_SEARCH}" "${STREAM}" "${TIMEOUT}"

  echo "[Round ${round}] done -> ${ROUND_FILE}"
  cat "${ROUND_FILE}"
  echo

done

ALL_FILE="${RUN_DIR}/all.log"
cat "${RUN_DIR}"/round_*.log > "${ALL_FILE}"

awk '
BEGIN {
  n=0; ok=0; fail=0;
  sum=0; min=999999; max=0;
}
{
  n++;
  code=""; total=0;
  for (i=1; i<=NF; i++) {
    if ($i ~ /^code=/) { split($i,a,"="); code=a[2]; }
    if ($i ~ /^total=/) { split($i,b,"="); total=b[2]+0; }
  }
  times[n]=total;
  sum+=total;
  if (total < min) min=total;
  if (total > max) max=total;
  if (code ~ /^2/) ok++; else fail++;
}
END {
  if (n==0) {
    print "No data";
    exit 1;
  }
  # sort times (simple bubble sort, n is small)
  for (i=1; i<=n; i++) {
    for (j=i+1; j<=n; j++) {
      if (times[i] > times[j]) { t=times[i]; times[i]=times[j]; times[j]=t; }
    }
  }
  p50=times[int((n+1)*0.50)];
  p90=times[int((n+1)*0.90)];
  p95=times[int((n+1)*0.95)];

  printf("[Summary]\n");
  printf("total_requests=%d\n", n);
  printf("success=%d\n", ok);
  printf("failed=%d\n", fail);
  printf("success_rate=%.2f%%\n", ok*100.0/n);
  printf("avg_latency=%.3fs\n", sum/n);
  printf("min_latency=%.3fs\n", min);
  printf("p50_latency=%.3fs\n", p50);
  printf("p90_latency=%.3fs\n", p90);
  printf("p95_latency=%.3fs\n", p95);
  printf("max_latency=%.3fs\n", max);
}
' "${ALL_FILE}" | tee "${RUN_DIR}/summary.txt"

cat <<TIP

[Next]
1) While running this script, watch vLLM logs for: Running / Waiting / Avg generation throughput.
2) If Waiting > 0 often or p95 is too high, lower MAX_TOKENS first.
3) Results saved in: ${RUN_DIR}
TIP
