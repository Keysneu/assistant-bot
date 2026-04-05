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


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Gemma4 deployment capabilities.")
    parser.add_argument("--base-url", default=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8100/v1"))
    parser.add_argument("--api-key", default=os.getenv("VLLM_API_KEY", "EMPTY"))
    parser.add_argument("--model", default=os.getenv("VLLM_MODEL", "gemma4-e4b-it"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--require-full", action="store_true", help="Fail when any capability check fails.")
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
        "messages": [{"role": "user", "content": "返回主题和一句摘要"}],
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

    def structured_validator(body: dict[str, Any]) -> tuple[bool, str]:
        content = extract_message_content(body)
        if not content:
            return False, "empty response"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return False, f"not valid json: {content[:120]}"

        if not isinstance(parsed, dict):
            return False, f"json is not object: {type(parsed).__name__}"
        if "topic" not in parsed or "summary" not in parsed:
            return False, f"missing keys in {parsed}"
        return True, "valid json schema output"

    results.append(
        check_chat_capability(
            "structured_output",
            args.base_url,
            headers,
            structured_payload,
            args.timeout,
            structured_validator,
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
        "messages": [{"role": "user", "content": "请调用 weather_lookup 工具查询上海天气。"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "weather_lookup",
                    "description": "Query weather by city",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string"},
                        },
                        "required": ["city"],
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
