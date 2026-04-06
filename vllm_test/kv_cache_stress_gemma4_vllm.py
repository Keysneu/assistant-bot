#!/usr/bin/env python3
"""KV-cache pressure benchmark wrapper for Gemma4 on vLLM.

This script builds a long-context prompt and invokes benchmark_gemma4_vllm.py
with high-concurrency defaults to push KV-cache utilization higher.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib import request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run KV-cache pressure benchmark for Gemma4 vLLM.")
    parser.add_argument("--base-url", default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8100/v1"))
    parser.add_argument("--api-key", default=os.getenv("VLLM_API_KEY", "EMPTY"))
    parser.add_argument("--model", default=os.getenv("VLLM_MODEL", "gemma4-e4b-it"))
    parser.add_argument("--requests", type=int, default=192)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--min-prompt-chars",
        type=int,
        default=64000,
        help="Build prompt text until this char length is reached.",
    )
    parser.add_argument(
        "--target-context-ratio",
        type=float,
        default=0.92,
        help="Target ratio of model context length to fill when auto sizing prompt.",
    )
    parser.add_argument(
        "--chars-per-token",
        type=float,
        default=3.6,
        help="Estimated characters per token for auto prompt sizing.",
    )
    parser.add_argument(
        "--no-auto-prompt-size",
        action="store_true",
        help="Disable model-aware prompt auto sizing.",
    )
    parser.add_argument(
        "--shared-prompt",
        action="store_true",
        help="Do not add per-request unique prefix (useful for prefix-cache comparison).",
    )
    parser.add_argument("--stream", action="store_true", help="Use stream mode and collect TTFT.")
    parser.add_argument("--strict-model", action="store_true")
    parser.add_argument("--out-dir", default="vllm_test/results")
    parser.add_argument("--name-prefix", default="kv_cache_pressure")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def build_long_context_prompt(min_prompt_chars: int) -> str:
    header = (
        "You are evaluating a long-context enterprise RAG workload.\n"
        "Read the full context and then produce:\n"
        "1) architecture risks, 2) retrieval strategy, 3) cache strategy, "
        "4) observability strategy, 5) phased rollout plan.\n"
        "Answer in structured bullet sections.\n\n"
        "[Long Context Start]\n"
    )
    footer = "\n[Long Context End]\nPlease provide a detailed implementation report."

    chunks: list[str] = []
    idx = 1
    while len(header) + len("".join(chunks)) + len(footer) < min_prompt_chars:
        part = (
            f"[KB-{idx:04d}] Service=assistant-bot; tenant=t{idx % 37:02d}; "
            f"region=ap-sg-{idx % 3}; release=2026.{(idx % 12) + 1:02d}; "
            f"incident_rate={(idx % 11) / 10:.1f}; p95_target_ms={1200 + (idx % 9) * 80}; "
            f"rag_topk={6 + (idx % 5)}; rerank=enabled; "
            f"notes=Document chunking, metadata filters, hybrid retrieval, and canary policy.\n"
        )
        chunks.append(part)
        idx += 1

    return header + "".join(chunks) + footer


def get_model_max_len(base_url: str, api_key: str, model: str, timeout_s: float) -> int | None:
    models_url = f"{base_url.rstrip('/')}/models"
    req = request.Request(
        url=models_url,
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    payload = json.loads(body) if body else {}
    for item in payload.get("data", []):
        if isinstance(item, dict) and item.get("id") == model:
            raw = item.get("max_model_len")
            if isinstance(raw, int) and raw > 0:
                return raw
            try:
                as_int = int(raw)
                if as_int > 0:
                    return as_int
            except Exception:
                return None
    return None


def main() -> int:
    args = build_parser().parse_args()

    if args.requests <= 0:
        raise SystemExit("--requests must be > 0")
    if args.concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")
    if args.max_tokens <= 0:
        raise SystemExit("--max-tokens must be > 0")
    if args.min_prompt_chars < 1000:
        raise SystemExit("--min-prompt-chars should be >= 1000 for KV pressure test")
    if args.target_context_ratio <= 0 or args.target_context_ratio > 1:
        raise SystemExit("--target-context-ratio must be in (0, 1]")
    if args.chars_per_token <= 0:
        raise SystemExit("--chars-per-token must be > 0")

    bench_script = Path(__file__).resolve().with_name("benchmark_gemma4_vllm.py")
    if not bench_script.exists():
        raise SystemExit(f"benchmark script not found: {bench_script}")

    target_prompt_chars = args.min_prompt_chars
    model_max_len: int | None = None
    auto_prompt_size = not args.no_auto_prompt_size
    if auto_prompt_size:
        try:
            model_max_len = get_model_max_len(
                base_url=args.base_url,
                api_key=args.api_key,
                model=args.model,
                timeout_s=min(30.0, args.timeout),
            )
            if model_max_len:
                auto_chars = int(model_max_len * args.target_context_ratio * args.chars_per_token)
                target_prompt_chars = max(target_prompt_chars, auto_chars)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"warning=auto prompt sizing skipped due to model query failure: {exc}")

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    prompt_text = build_long_context_prompt(target_prompt_chars)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = out_dir / f"{args.name_prefix}_prompt_{ts}.txt"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    cmd = [
        sys.executable,
        str(bench_script),
        "--base-url",
        args.base_url,
        "--api-key",
        args.api_key,
        "--model",
        args.model,
        "--prompt-file",
        str(prompt_file),
        "--temperature",
        str(args.temperature),
        "--max-tokens",
        str(args.max_tokens),
        "--requests",
        str(args.requests),
        "--concurrency",
        str(args.concurrency),
        "--timeout",
        str(args.timeout),
        "--warmup",
        str(args.warmup),
        "--out-dir",
        str(args.out_dir),
        "--name-prefix",
        args.name_prefix,
    ]
    if args.stream:
        cmd.append("--stream")
    if args.strict_model:
        cmd.append("--strict-model")
    if not args.shared_prompt:
        cmd.append("--unique-prompt-per-request")

    print("[KV Cache Stress Config]")
    print(f"base_url={args.base_url}")
    print(f"model={args.model}")
    print(f"requests={args.requests}")
    print(f"concurrency={args.concurrency}")
    print(f"max_tokens={args.max_tokens}")
    print(f"stream={args.stream}")
    print(f"unique_prompt_per_request={not args.shared_prompt}")
    print(f"auto_prompt_size={auto_prompt_size}")
    print(f"target_context_ratio={args.target_context_ratio}")
    print(f"chars_per_token={args.chars_per_token}")
    if model_max_len:
        print(f"model_max_len={model_max_len}")
    print(f"prompt_chars={len(prompt_text)}")
    print(f"prompt_file={prompt_file}")
    print("[Benchmark Command]")
    print(" ".join(cmd))

    if args.dry_run:
        return 0

    proc = subprocess.run(cmd, text=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
