#!/usr/bin/env python3
"""Direct benchmark for Gemma4 on vLLM OpenAI-compatible API.

Usage example:
  python3 vllm_test/benchmark_gemma4_vllm.py \
    --base-url http://127.0.0.1:8100/v1 \
    --model gemma4-e4b-it \
    --concurrency 8 \
    --requests 64
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import math
import os
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional
from urllib import error, request


DEFAULT_PROMPT = "请用150字解释RAG在企业知识库问答中的价值，并给出一个落地场景。"


@dataclass
class RequestResult:
    request_id: int
    ok: bool
    status_code: int
    latency_s: float
    ttft_s: Optional[float]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    output_chars: int
    error: str


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    idx = max(1, math.ceil(len(values) * q)) - 1
    idx = min(max(idx, 0), len(values) - 1)
    return values[idx]


def build_headers(api_key: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def http_json_request(
    url: str,
    method: str,
    headers: dict[str, str],
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 120.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, method=method, headers=headers, data=data)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
        status = int(resp.status)
    parsed = json.loads(body) if body else {}
    return status, parsed


def parse_completion_content(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                total += len(item.get("text", ""))
            elif isinstance(item, str):
                total += len(item)
        return total
    return 0


def run_non_stream_request(
    request_id: int,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: float,
) -> RequestResult:
    start = time.perf_counter()
    status_code = 0

    try:
        status_code, data = http_json_request(
            url=url,
            method="POST",
            headers=headers,
            payload=payload,
            timeout=timeout_s,
        )
        latency_s = time.perf_counter() - start

        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))

        choices = data.get("choices") or []
        output_chars = 0
        if choices:
            message = choices[0].get("message") or {}
            output_chars = parse_completion_content(message.get("content"))

        return RequestResult(
            request_id=request_id,
            ok=200 <= status_code < 300,
            status_code=status_code,
            latency_s=latency_s,
            ttft_s=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            output_chars=output_chars,
            error="",
        )
    except error.HTTPError as exc:
        latency_s = time.perf_counter() - start
        err_body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        return RequestResult(
            request_id=request_id,
            ok=False,
            status_code=int(exc.code),
            latency_s=latency_s,
            ttft_s=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            output_chars=0,
            error=f"HTTPError: {err_body[:500]}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        latency_s = time.perf_counter() - start
        return RequestResult(
            request_id=request_id,
            ok=False,
            status_code=status_code,
            latency_s=latency_s,
            ttft_s=None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            output_chars=0,
            error=f"Exception: {exc}",
        )


def extract_delta_text(delta_content: Any) -> str:
    if isinstance(delta_content, str):
        return delta_content
    if isinstance(delta_content, list):
        parts: list[str] = []
        for item in delta_content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return ""


def run_stream_request(
    request_id: int,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: float,
) -> RequestResult:
    start = time.perf_counter()
    status_code = 0
    ttft_s: Optional[float] = None
    output_chars = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url=url, method="POST", headers=headers, data=data)
        with request.urlopen(req, timeout=timeout_s) as resp:
            status_code = int(resp.status)
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                body = line[len("data:") :].strip()
                if body == "[DONE]":
                    break
                try:
                    event = json.loads(body)
                except json.JSONDecodeError:
                    continue

                usage = event.get("usage") or {}
                if usage:
                    prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens)
                    completion_tokens = int(usage.get("completion_tokens") or completion_tokens)
                    total_tokens = int(usage.get("total_tokens") or total_tokens)

                choices = event.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                token_piece = extract_delta_text(delta.get("content"))
                if token_piece:
                    if ttft_s is None:
                        ttft_s = time.perf_counter() - start
                    output_chars += len(token_piece)

        latency_s = time.perf_counter() - start
        return RequestResult(
            request_id=request_id,
            ok=200 <= status_code < 300,
            status_code=status_code,
            latency_s=latency_s,
            ttft_s=ttft_s,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            output_chars=output_chars,
            error="",
        )
    except error.HTTPError as exc:
        latency_s = time.perf_counter() - start
        err_body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        return RequestResult(
            request_id=request_id,
            ok=False,
            status_code=int(exc.code),
            latency_s=latency_s,
            ttft_s=ttft_s,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            output_chars=output_chars,
            error=f"HTTPError: {err_body[:500]}",
        )
    except Exception as exc:  # pylint: disable=broad-except
        latency_s = time.perf_counter() - start
        return RequestResult(
            request_id=request_id,
            ok=False,
            status_code=status_code,
            latency_s=latency_s,
            ttft_s=ttft_s,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            output_chars=output_chars,
            error=f"Exception: {exc}",
        )


def list_models(base_url: str, headers: dict[str, str], timeout_s: float) -> list[str]:
    status, payload = http_json_request(
        url=f"{base_url}/models",
        method="GET",
        headers=headers,
        payload=None,
        timeout=timeout_s,
    )
    if not (200 <= status < 300):
        return []
    models = payload.get("data") or []
    ids: list[str] = []
    for item in models:
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Gemma4 deployment on vLLM.")
    parser.add_argument("--base-url", default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8100/v1"))
    parser.add_argument("--api-key", default=os.getenv("VLLM_API_KEY", "EMPTY"))
    parser.add_argument("--model", default=os.getenv("VLLM_MODEL", "gemma4-e4b-it"))
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--stream", action="store_true", help="Use stream mode and collect TTFT.")
    parser.add_argument("--strict-model", action="store_true", help="Fail if model not found in /models.")
    parser.add_argument("--out-dir", default="vllm_test/results")
    parser.add_argument("--name-prefix", default="gemma4_direct", help="Prefix for result folder name.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.requests <= 0:
        raise SystemExit("--requests must be > 0")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = Path(args.out_dir) / f"{args.name_prefix}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    headers = build_headers(args.api_key)
    completion_url = f"{args.base_url}/chat/completions"

    print("[Config]")
    print(f"base_url={args.base_url}")
    print(f"model={args.model}")
    print(f"requests={args.requests}")
    print(f"concurrency={args.concurrency}")
    print(f"stream={args.stream}")
    print(f"max_tokens={args.max_tokens}")
    print(f"timeout={args.timeout}s")
    print(f"out_dir={run_dir}")

    try:
        models = list_models(args.base_url, headers, args.timeout)
        if models:
            print(f"available_models={','.join(models)}")
        if args.model not in models:
            msg = f"target model '{args.model}' not found in /models"
            if args.strict_model:
                raise SystemExit(msg)
            print(f"warning={msg}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"warning=models check failed: {exc}")

    base_payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "stream": bool(args.stream),
    }
    if args.stream:
        base_payload["stream_options"] = {"include_usage": True}

    if args.warmup > 0:
        print(f"\n[Warmup] count={args.warmup}")
        for i in range(1, args.warmup + 1):
            # stream_options is only valid when stream=true.
            warmup_payload = {k: v for k, v in base_payload.items() if k != "stream_options"}
            warmup_payload["stream"] = False
            warmup_result = run_non_stream_request(
                request_id=i,
                url=completion_url,
                headers=headers,
                payload=warmup_payload,
                timeout_s=args.timeout,
            )
            print(
                f"warmup_{i}: ok={warmup_result.ok} status={warmup_result.status_code} latency={warmup_result.latency_s:.3f}s"
            )

    print("\n[Benchmark] start")

    lock = threading.Lock()
    results: list[RequestResult] = []

    def worker(rid: int) -> None:
        payload = dict(base_payload)
        if args.stream:
            result = run_stream_request(rid, completion_url, headers, payload, args.timeout)
        else:
            result = run_non_stream_request(rid, completion_url, headers, payload, args.timeout)
        with lock:
            results.append(result)

    benchmark_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(worker, rid) for rid in range(1, args.requests + 1)]
        for fut in concurrent.futures.as_completed(futures):
            fut.result()
    benchmark_elapsed = time.perf_counter() - benchmark_start

    results.sort(key=lambda x: x.request_id)

    ok_results = [r for r in results if r.ok]
    fail_results = [r for r in results if not r.ok]

    latencies = sorted(r.latency_s for r in ok_results)
    ttfts = sorted(r.ttft_s for r in ok_results if r.ttft_s is not None)

    success_count = len(ok_results)
    fail_count = len(fail_results)
    total_count = len(results)
    success_rate = (success_count * 100.0 / total_count) if total_count else 0.0

    avg_latency = statistics.fmean(latencies) if latencies else 0.0
    p50 = percentile(latencies, 0.50)
    p90 = percentile(latencies, 0.90)
    p95 = percentile(latencies, 0.95)
    max_latency = max(latencies) if latencies else 0.0

    avg_ttft = statistics.fmean(ttfts) if ttfts else 0.0
    p95_ttft = percentile(ttfts, 0.95) if ttfts else 0.0

    sum_prompt_tokens = sum(r.prompt_tokens for r in ok_results)
    sum_completion_tokens = sum(r.completion_tokens for r in ok_results)
    sum_total_tokens = sum(r.total_tokens for r in ok_results)

    req_throughput = (total_count / benchmark_elapsed) if benchmark_elapsed > 0 else 0.0
    success_req_throughput = (success_count / benchmark_elapsed) if benchmark_elapsed > 0 else 0.0
    output_tps = (sum_completion_tokens / benchmark_elapsed) if benchmark_elapsed > 0 else 0.0

    summary = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "config": {
            "base_url": args.base_url,
            "model": args.model,
            "requests": args.requests,
            "concurrency": args.concurrency,
            "stream": args.stream,
            "max_tokens": args.max_tokens,
            "timeout": args.timeout,
            "warmup": args.warmup,
        },
        "metrics": {
            "total_requests": total_count,
            "success": success_count,
            "failed": fail_count,
            "success_rate_percent": round(success_rate, 2),
            "benchmark_elapsed_s": round(benchmark_elapsed, 3),
            "avg_latency_s": round(avg_latency, 3),
            "p50_latency_s": round(p50, 3),
            "p90_latency_s": round(p90, 3),
            "p95_latency_s": round(p95, 3),
            "max_latency_s": round(max_latency, 3),
            "avg_ttft_s": round(avg_ttft, 3),
            "p95_ttft_s": round(p95_ttft, 3),
            "request_throughput_rps": round(req_throughput, 3),
            "success_throughput_rps": round(success_req_throughput, 3),
            "completion_token_throughput_tps": round(output_tps, 3),
            "sum_prompt_tokens": sum_prompt_tokens,
            "sum_completion_tokens": sum_completion_tokens,
            "sum_total_tokens": sum_total_tokens,
        },
    }

    requests_path = run_dir / "requests.jsonl"
    with requests_path.open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

    summary_json_path = run_dir / "summary.json"
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_txt_lines = [
        "[Summary]",
        f"total_requests={total_count}",
        f"success={success_count}",
        f"failed={fail_count}",
        f"success_rate={success_rate:.2f}%",
        f"benchmark_elapsed={benchmark_elapsed:.3f}s",
        f"avg_latency={avg_latency:.3f}s",
        f"p50_latency={p50:.3f}s",
        f"p90_latency={p90:.3f}s",
        f"p95_latency={p95:.3f}s",
        f"max_latency={max_latency:.3f}s",
        f"avg_ttft={avg_ttft:.3f}s",
        f"p95_ttft={p95_ttft:.3f}s",
        f"request_throughput={req_throughput:.3f} req/s",
        f"success_throughput={success_req_throughput:.3f} req/s",
        f"completion_token_throughput={output_tps:.3f} tok/s",
        f"sum_prompt_tokens={sum_prompt_tokens}",
        f"sum_completion_tokens={sum_completion_tokens}",
        f"sum_total_tokens={sum_total_tokens}",
        f"requests_log={requests_path}",
        f"summary_json={summary_json_path}",
    ]

    if fail_results:
        summary_txt_lines.append("\n[Errors]")
        for item in fail_results[:20]:
            summary_txt_lines.append(
                f"request_id={item.request_id} status={item.status_code} error={item.error}"
            )

    summary_txt = "\n".join(summary_txt_lines) + "\n"
    summary_txt_path = run_dir / "summary.txt"
    summary_txt_path.write_text(summary_txt, encoding="utf-8")

    print()
    print(summary_txt)
    print(f"[Done] artifacts={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
