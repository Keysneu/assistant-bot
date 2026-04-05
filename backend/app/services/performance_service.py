"""Performance summary service for Gemma4/vLLM benchmarking artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import BASE_DIR, settings
from app.services.llm_service import get_active_model_name, probe_vllm_connection


RESULTS_DIR = BASE_DIR.parent / "vllm_test" / "results"


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file safely and return None on parse/read failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _latest_run_dir(prefix: str) -> Path | None:
    """Get latest run directory under results by prefix."""
    if not RESULTS_DIR.exists():
        return None

    candidates = [p for p in RESULTS_DIR.iterdir() if p.is_dir() and p.name.startswith(prefix)]
    if not candidates:
        return None

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def _extract_benchmark(run_dir: Path | None) -> dict[str, Any] | None:
    """Extract summary from benchmark result directory."""
    if run_dir is None:
        return None

    payload = _safe_read_json(run_dir / "summary.json")
    if not payload:
        return None

    metrics = payload.get("metrics") or {}
    config = payload.get("config") or {}
    return {
        "run_id": run_dir.name,
        "generated_at": payload.get("generated_at"),
        "model": config.get("model"),
        "concurrency": config.get("concurrency"),
        "requests": config.get("requests"),
        "stream": config.get("stream"),
        "success_rate_percent": float(metrics.get("success_rate_percent") or 0.0),
        "p95_latency_s": float(metrics.get("p95_latency_s") or 0.0),
        "avg_latency_s": float(metrics.get("avg_latency_s") or 0.0),
        "request_throughput_rps": float(metrics.get("request_throughput_rps") or 0.0),
        "completion_token_throughput_tps": float(metrics.get("completion_token_throughput_tps") or 0.0),
        "p95_ttft_s": float(metrics.get("p95_ttft_s") or 0.0),
    }


def _extract_strict_suite(run_dir: Path | None) -> dict[str, Any] | None:
    """Extract summary from strict suite report."""
    if run_dir is None:
        return None

    payload = _safe_read_json(run_dir / "suite_report.json")
    if not payload:
        return None

    summary = payload.get("summary") or {}
    return {
        "run_id": run_dir.name,
        "generated_at": payload.get("generated_at"),
        "overall": summary.get("overall", "UNKNOWN"),
        "pass_count": int(summary.get("pass") or 0),
        "fail_count": int(summary.get("fail") or 0),
        "total": int(summary.get("total") or 0),
    }


def _extract_capability(run_dir: Path | None) -> dict[str, Any] | None:
    """Extract summary from capability probe report."""
    if run_dir is None:
        return None

    payload = _safe_read_json(run_dir / "capability_report.json")
    if not payload:
        return None

    summary = payload.get("summary") or {}
    checks = payload.get("results") or []
    return {
        "run_id": run_dir.name,
        "generated_at": payload.get("timestamp"),
        "passed": int(summary.get("passed") or 0),
        "total": int(summary.get("total") or 0),
        "checks": [
            {
                "name": item.get("name", ""),
                "passed": bool(item.get("passed", False)),
                "detail": item.get("detail", ""),
                "latency_s": float(item.get("latency_s") or 0.0),
            }
            for item in checks
            if isinstance(item, dict)
        ],
    }


def get_performance_overview() -> dict[str, Any]:
    """Build overview payload for Gemma4 deployment performance in project UI."""
    vllm_connected = True
    vllm_reason = None
    if settings.LLM_PROVIDER == "vllm":
        vllm_connected, vllm_reason = probe_vllm_connection()

    benchmark = _extract_benchmark(_latest_run_dir("gemma4_direct_"))
    strict_suite = _extract_strict_suite(_latest_run_dir("strict_suite_"))
    capability = _extract_capability(_latest_run_dir("cap_probe_"))

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "provider": settings.LLM_PROVIDER,
        "active_model": get_active_model_name(),
        "deploy_profile": settings.VLLM_DEPLOY_PROFILE if settings.LLM_PROVIDER == "vllm" else "local_default",
        "vllm_connected": vllm_connected,
        "vllm_reason": vllm_reason,
        "latest_benchmark": benchmark,
        "latest_strict_suite": strict_suite,
        "latest_capability_probe": capability,
    }
