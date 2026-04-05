#!/usr/bin/env bash
set -euo pipefail

# Sweep benchmark: test concurrency from MIN_CONCURRENCY to MAX_CONCURRENCY,
# then produce a summary table and recommended max concurrency.

URL="${URL:-http://127.0.0.1:8000/api/chat/}"
MIN_CONCURRENCY="${MIN_CONCURRENCY:-1}"
MAX_CONCURRENCY="${MAX_CONCURRENCY:-10}"
ROUNDS="${ROUNDS:-2}"
STREAM="${STREAM:-false}"
USE_SEARCH="${USE_SEARCH:-false}"
MESSAGE="${MESSAGE:-请用120字解释什么是RAG，并给一个实际应用例子。}"
TIMEOUT="${TIMEOUT:-180}"
OUT_DIR="${OUT_DIR:-./vllm_test/results}"
TARGET_P95="${TARGET_P95:-8.0}"
MIN_SUCCESS_RATE="${MIN_SUCCESS_RATE:-99.0}"

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${OUT_DIR}/sweep_${TS}"
mkdir -p "${RUN_DIR}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

if [[ "${MIN_CONCURRENCY}" -gt "${MAX_CONCURRENCY}" ]]; then
  echo "MIN_CONCURRENCY must be <= MAX_CONCURRENCY" >&2
  exit 1
fi

cat <<INFO
[Sweep Config]
URL=${URL}
MIN_CONCURRENCY=${MIN_CONCURRENCY}
MAX_CONCURRENCY=${MAX_CONCURRENCY}
ROUNDS=${ROUNDS}
STREAM=${STREAM}
USE_SEARCH=${USE_SEARCH}
TIMEOUT=${TIMEOUT}s
TARGET_P95=${TARGET_P95}s
MIN_SUCCESS_RATE=${MIN_SUCCESS_RATE}%
OUT_DIR=${RUN_DIR}
INFO

# warmup
curl -sS --max-time "${TIMEOUT}" "${URL}" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"warmup\",\"use_search\":${USE_SEARCH},\"stream\":${STREAM}}" \
  >/dev/null || true

TABLE_FILE="${RUN_DIR}/table.tsv"
printf "concurrency\ttotal\tsuccess\tfailed\tsuccess_rate\tavg\tp50\tp90\tp95\tmax\n" > "${TABLE_FILE}"

for conc in $(seq "${MIN_CONCURRENCY}" "${MAX_CONCURRENCY}"); do
  CASE_DIR="${RUN_DIR}/c${conc}"
  mkdir -p "${CASE_DIR}"
  ALL_FILE="${CASE_DIR}/all.log"
  : > "${ALL_FILE}"

  echo "[Case c=${conc}] start"

  for round in $(seq 1 "${ROUNDS}"); do
    ROUND_FILE="${CASE_DIR}/round_${round}.log"
    : > "${ROUND_FILE}"

    seq 1 "${conc}" | xargs -I{} -P"${conc}" sh -c '
      idx="$1"
      out_file="$2"
      url="$3"
      message="$4"
      use_search="$5"
      stream="$6"
      timeout="$7"

      payload=$(printf "{\"message\":\"%s\",\"use_search\":%s,\"stream\":%s}" "$message" "$use_search" "$stream")
      result=$(curl -sS --max-time "$timeout" -o /tmp/vllm_sweep_${idx}.json -w "code=%{http_code} total=%{time_total}" "$url" -H "Content-Type: application/json" -d "$payload" || echo "code=000 total=${timeout}")
      echo "req=${idx} ${result}" >>"$out_file"
    ' _ {} "${ROUND_FILE}" "${URL}" "${MESSAGE}" "${USE_SEARCH}" "${STREAM}" "${TIMEOUT}"

    cat "${ROUND_FILE}" >> "${ALL_FILE}"
  done

  stats=$(awk '
  BEGIN { n=0; ok=0; fail=0; sum=0; min=999999; max=0; }
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
    if (n==0) { print "0\t0\t0\t0\t0\t0\t0\t0\t0"; exit; }
    for (i=1; i<=n; i++) {
      for (j=i+1; j<=n; j++) {
        if (times[i] > times[j]) { t=times[i]; times[i]=times[j]; times[j]=t; }
      }
    }
    p50=times[int((n+1)*0.50)];
    p90=times[int((n+1)*0.90)];
    p95=times[int((n+1)*0.95)];
    sr=ok*100.0/n;
    printf("%d\t%d\t%d\t%.2f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f", n, ok, fail, sr, sum/n, p50, p90, p95, max);
  }
  ' "${ALL_FILE}")

  printf "%s\t%s\n" "${conc}" "${stats}" >> "${TABLE_FILE}"
  echo "[Case c=${conc}] done"
done

# Pretty print table
REPORT_TXT="${RUN_DIR}/report.txt"
{
  echo "[Sweep Summary]"
  column -t -s $'\t' "${TABLE_FILE}"
  echo
} | tee "${REPORT_TXT}"

# Recommend max concurrency under target constraints.
REC=$(awk -F'\t' -v target_p95="${TARGET_P95}" -v min_sr="${MIN_SUCCESS_RATE}" '
BEGIN { best=0; }
NR==1 { next; }
{
  c=$1+0; sr=$5+0; p95=$9+0;
  if (sr >= min_sr && p95 <= target_p95 && c > best) {
    best=c;
  }
}
END { print best; }
' "${TABLE_FILE}")

{
  echo "[Recommendation]"
  if [[ "${REC}" -gt 0 ]]; then
    echo "recommended_max_concurrency=${REC}"
    echo "rule=success_rate>=${MIN_SUCCESS_RATE}% and p95<=${TARGET_P95}s"
  else
    echo "recommended_max_concurrency=none"
    echo "reason=no concurrency level satisfies success_rate>=${MIN_SUCCESS_RATE}% and p95<=${TARGET_P95}s"
  fi
  echo "raw_table=${TABLE_FILE}"
  echo "report=${REPORT_TXT}"
} | tee "${RUN_DIR}/recommendation.txt"

cat <<TIP

[Next]
1) During sweep, watch vLLM logs for Running/Waiting/throughput to confirm queue behavior.
2) If recommended concurrency is low, reduce MAX_TOKENS or shorten prompts.
3) Output directory: ${RUN_DIR}
TIP
