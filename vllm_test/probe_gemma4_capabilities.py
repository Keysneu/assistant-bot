#!/usr/bin/env python3
"""Probe Gemma4 vLLM deployment capabilities via OpenAI-compatible API.

This script validates a running Gemma4 deployment and reports capability
coverage (text, multimodal, structured output, thinking, tool calling).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


MINI_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+f6kAAAAASUVORK5CYII="
)


@dataclass
class CapabilityResult:
    name: str
    passed: bool
    latency_s: float
    detail: str


def http_json_request(
    url: str,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None,
    timeout_s: float,
) -> tuple[int, dict[str, Any]]:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = request.Request(url=url, method=method, headers=headers, data=data)
    with request.urlopen(req, timeout=timeout_s) as resp:
        status = int(resp.status)
        body = resp.read().decode("utf-8", errors="ignore")

    parsed = json.loads(body) if body else {}
    return status, parsed


def check_models(base_url: str, headers: dict[str, str], timeout_s: float, model: str) -> CapabilityResult:
    start = time.perf_counter()
    try:
        status, payload = http_json_request(
            url=f"{base_url}/models",
            method="GET",
            headers=headers,
            payload=None,
            timeout_s=timeout_s,
        )
        if not (200 <= status < 300):
            return CapabilityResult("models", False, time.perf_counter() - start, f"status={status}")

        items = payload.get("data") or []
        model_ids = [item.get("id") for item in items if isinstance(item, dict) and item.get("id")]
        if model not in model_ids:
            return CapabilityResult(
                "models",
                False,
                time.perf_counter() - start,
                f"configured model '{model}' not in /models: {model_ids}",
            )

        return CapabilityResult("models", True, time.perf_counter() - start, f"available={','.join(model_ids)}")
    except Exception as exc:  # pylint: disable=broad-except
        return CapabilityResult("models", False, time.perf_counter() - start, str(exc))


def check_chat_capability(
    name: str,
    base_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_s: float,
    validator,
) -> CapabilityResult:
    start = time.perf_counter()
    try:
        status, body = http_json_request(
            url=f"{base_url}/chat/completions",
            method="POST",
            headers=headers,
            payload=payload,
            timeout_s=timeout_s,
        )
        if not (200 <= status < 300):
            return CapabilityResult(name, False, time.perf_counter() - start, f"status={status}")

        passed, detail = validator(body)
        return CapabilityResult(name, passed, time.perf_counter() - start, detail)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        return CapabilityResult(name, False, time.perf_counter() - start, f"HTTPError {exc.code}: {detail[:300]}")
    except Exception as exc:  # pylint: disable=broad-except
        return CapabilityResult(name, False, time.perf_counter() - start, str(exc))


def extract_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return ""


def _strip_markdown_json_fence(content: str) -> str:
    """Strip optional markdown json code fence for diagnostics."""
    text = (content or "").strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def validate_topic_summary_json(content: str) -> tuple[bool, str]:
    """Strict validator for structured output stability checks."""
    raw = (content or "").strip()
    if not raw:
        return False, "empty response"

    # We intentionally require pure JSON text here to catch markdown fence leaks.
    if raw.startswith("```"):
        cleaned = _strip_markdown_json_fence(raw)
        try:
            json.loads(cleaned)
            return False, "json wrapped by markdown fence (not strict pure json)"
        except Exception:
            return False, "markdown fenced and invalid json"

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return False, f"not valid json: {raw[:120]}"

    if not isinstance(parsed, dict):
        return False, f"json is not object: {type(parsed).__name__}"

    keys = set(parsed.keys())
    expected = {"topic", "summary"}
    if keys != expected:
        return False, f"schema mismatch keys={sorted(list(keys))}, expected={sorted(list(expected))}"

    topic = parsed.get("topic")
    summary = parsed.get("summary")
    if not isinstance(topic, str) or not topic.strip():
        return False, "field 'topic' must be non-empty string"
    if not isinstance(summary, str) or not summary.strip():
        return False, "field 'summary' must be non-empty string"

    return True, "strict schema-compliant json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Gemma4 deployment capabilities.")
    parser.add_argument("--base-url", default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8100/v1"))
    parser.add_argument("--api-key", default=os.getenv("VLLM_API_KEY", "EMPTY"))
    parser.add_argument("--model", default=os.getenv("VLLM_MODEL", "gemma4-e4b-it"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--require-full", action="store_true", help="Fail when any capability check fails.")
    parser.add_argument(
        "--structured-runs",
        type=int,
        default=5,
        help="Number of repeated runs for structured_output stability check (default: 5).",
    )
    parser.add_argument(
        "--structured-min-pass-rate",
        type=float,
        default=1.0,
        help="Minimum pass rate required for structured_output to pass (default: 1.0).",
    )
    parser.add_argument("--out-dir", default="vllm_test/results")
    args = parser.parse_args()

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / f"cap_probe_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {args.api_key}",
    }

    results: list[CapabilityResult] = []

    results.append(check_models(args.base_url, headers, args.timeout, args.model))

    text_payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "请用一句话说明你是 Gemma4 部署实例。"}],
        "temperature": 0.1,
        "max_tokens": 64,
    }
    results.append(
        check_chat_capability(
            "text_generation",
            args.base_url,
            headers,
            text_payload,
            args.timeout,
            lambda body: (
                bool(extract_message_content(body)),
                "non-empty text" if extract_message_content(body) else "empty response",
            ),
        )
    )

    multimodal_payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请简要描述图片颜色"},
                    {"type": "image_url", "image_url": {"url": MINI_PNG_DATA_URL}},
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 64,
    }
    results.append(
        check_chat_capability(
            "multimodal",
            args.base_url,
            headers,
            multimodal_payload,
            args.timeout,
            lambda body: (
                bool(extract_message_content(body)),
                "non-empty multimodal response" if extract_message_content(body) else "empty response",
            ),
        )
    )

    structured_payload = {
        "model": args.model,
        "messages": [
            {
                "role": "system",
                "content": "Output ONLY valid JSON. No markdown/code fence and no extra text.",
            },
            {
                "role": "user",
                "content": (
                    "Text: Apple released a new chip for laptops. "
                    "Return topic and one-sentence summary."
                ),
            },
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 128,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "topic_summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["topic", "summary"],
                    "additionalProperties": False,
                },
            },
        },
    }

    structured_runs = max(1, int(args.structured_runs))
    structured_start = time.perf_counter()
    structured_pass = 0
    structured_fail_reasons: list[str] = []
    structured_samples: list[dict[str, Any]] = []

    for idx in range(structured_runs):
        try:
            status, body = http_json_request(
                url=f"{args.base_url}/chat/completions",
                method="POST",
                headers=headers,
                payload=structured_payload,
                timeout_s=args.timeout,
            )
            if not (200 <= status < 300):
                reason = f"status={status}"
                structured_fail_reasons.append(reason)
                structured_samples.append({"run": idx + 1, "ok": False, "detail": reason, "content": ""})
                continue

            content = extract_message_content(body)
            ok, detail = validate_topic_summary_json(content)
            if ok:
                structured_pass += 1
            else:
                structured_fail_reasons.append(detail)
            structured_samples.append(
                {
                    "run": idx + 1,
                    "ok": ok,
                    "detail": detail,
                    "content_preview": content[:180],
                }
            )
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            reason = f"HTTPError {exc.code}: {detail[:200]}"
            structured_fail_reasons.append(reason)
            structured_samples.append({"run": idx + 1, "ok": False, "detail": reason, "content_preview": ""})
        except Exception as exc:  # pylint: disable=broad-except
            reason = str(exc)
            structured_fail_reasons.append(reason)
            structured_samples.append({"run": idx + 1, "ok": False, "detail": reason, "content_preview": ""})

    structured_latency = time.perf_counter() - structured_start
    structured_pass_rate = structured_pass / structured_runs
    structured_ok = structured_pass_rate >= float(args.structured_min_pass_rate)
    structured_detail = (
        f"pass_rate={structured_pass_rate:.2%} ({structured_pass}/{structured_runs}), "
        f"threshold={float(args.structured_min_pass_rate):.2%}"
    )
    if structured_fail_reasons:
        structured_detail += f", first_fail={structured_fail_reasons[0]}"

    results.append(
        CapabilityResult(
            "structured_output",
            structured_ok,
            structured_latency,
            structured_detail,
        )
    )

    thinking_payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "请给出 2 条关于企业 RAG 迭代的建议。"}],
        "max_tokens": 256,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
            }
        },
    }
    results.append(
        check_chat_capability(
            "thinking_mode",
            args.base_url,
            headers,
            thinking_payload,
            args.timeout,
            lambda body: (
                bool(extract_message_content(body)),
                "thinking request completed" if extract_message_content(body) else "empty response",
            ),
        )
    )

    tool_payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": "请调用 search_web_realtime 工具查询 OpenAI 最近一天新闻。"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_web_realtime",
                    "description": "Search real-time web news and latest headlines.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "freshness": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                },
            }
        ],
        "max_tokens": 256,
    }

    def tool_validator(body: dict[str, Any]) -> tuple[bool, str]:
        choices = body.get("choices") or []
        if not choices:
            return False, "no choices"
        message = choices[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return False, "no tool_calls returned (check --enable-auto-tool-choice and parser flags)"
        first = tool_calls[0]
        fn = ((first or {}).get("function") or {}).get("name")
        return True, f"tool_call={fn}"

    results.append(
        check_chat_capability(
            "tool_calling",
            args.base_url,
            headers,
            tool_payload,
            args.timeout,
            tool_validator,
        )
    )

    report = {
        "timestamp": timestamp,
        "base_url": args.base_url,
        "model": args.model,
        "require_full": args.require_full,
        "results": [asdict(item) for item in results],
        "structured_output_stats": {
            "runs": structured_runs,
            "passed": structured_pass,
            "pass_rate": structured_pass_rate,
            "required_min_pass_rate": float(args.structured_min_pass_rate),
            "samples": structured_samples,
        },
        "summary": {
            "passed": sum(1 for item in results if item.passed),
            "total": len(results),
        },
    }

    report_path = out_dir / "capability_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[Gemma4 Capability Probe]")
    print(f"base_url={args.base_url}")
    print(f"model={args.model}")
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        print(f"- {item.name}: {status} ({item.latency_s:.2f}s) {item.detail}")

    print(f"report={report_path}")

    baseline_required = {"models", "text_generation"}
    baseline_ok = all(item.passed for item in results if item.name in baseline_required)

    if not baseline_ok:
        return 2
    if args.require_full and any(not item.passed for item in results):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
