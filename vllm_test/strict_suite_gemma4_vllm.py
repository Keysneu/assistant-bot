#!/usr/bin/env python3
"""Strict multi-stage benchmark suite for Gemma4 on vLLM.

This runner executes several benchmark scenarios and applies SLO gates.
It is intended for stricter pre-release / pre-change validation.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


RuleOp = Literal["<=", ">="]


@dataclass
class Rule:
    metric: str
    op: RuleOp
    threshold: float


@dataclass
class Scenario:
    name: str
    description: str
    prompt: str
    requests: int
    concurrency: int
    max_tokens: int
    stream: bool
    rules: list[Rule]


def scenario_catalog(soak_requests: int) -> list[Scenario]:
    return [
        Scenario(
            name="s1_stream_ttft",
            description="Stream responsiveness and TTFT stability.",
            prompt="请用结构化方式解释RAG系统在企业知识库中的价值，并给出3个落地指标。",
            requests=120,
            concurrency=8,
            max_tokens=256,
            stream=True,
            rules=[
                Rule("success_rate_percent", ">=", 99.0),
                Rule("p95_latency_s", "<=", 3.0),
                Rule("p95_ttft_s", "<=", 0.20),
                Rule("completion_token_throughput_tps", ">=", 600.0),
            ],
        ),
        Scenario(
            name="s2_high_concurrency",
            description="High-concurrency stress under non-stream mode.",
            prompt="请用200字总结检索增强生成在大型知识库问答中的优势与局限。",
            requests=240,
            concurrency=16,
            max_tokens=256,
            stream=False,
            rules=[
                Rule("success_rate_percent", ">=", 99.0),
                Rule("p95_latency_s", "<=", 4.5),
                Rule("completion_token_throughput_tps", ">=", 650.0),
            ],
        ),
        Scenario(
            name="s3_long_generation",
            description="Long-generation pressure with larger max tokens.",
            prompt=(
                "请写一份企业RAG系统建设指南，包含架构、分层、索引策略、缓存策略、"
                "质量评估、线上监控与灰度发布建议，要求分点输出。"
            ),
            requests=96,
            concurrency=8,
            max_tokens=1024,
            stream=False,
            rules=[
                Rule("success_rate_percent", ">=", 98.0),
                Rule("p95_latency_s", "<=", 12.0),
                Rule("completion_token_throughput_tps", ">=", 500.0),
            ],
        ),
        Scenario(
            name="s4_soak_stream",
            description="Longer stream soak to detect stability regressions.",
            prompt="请用简洁语言给出RAG在客服、法务、研发支持三个场景的实施建议。",
            requests=soak_requests,
            concurrency=8,
            max_tokens=256,
            stream=True,
            rules=[
                Rule("success_rate_percent", ">=", 99.0),
                Rule("p95_latency_s", "<=", 3.5),
                Rule("p95_ttft_s", "<=", 0.25),
            ],
        ),
    ]


def compare(actual: float, op: RuleOp, threshold: float) -> bool:
    if op == "<=":
        return actual <= threshold
    return actual >= threshold


def evaluate_rules(metrics: dict, rules: list[Rule]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for rule in rules:
        actual = float(metrics.get(rule.metric, 0.0))
        ok = compare(actual, rule.op, rule.threshold)
        if not ok:
            failures.append(f"{rule.metric} actual={actual:.3f} required {rule.op} {rule.threshold:.3f}")
    return (len(failures) == 0), failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run strict benchmark suite for Gemma4 vLLM deployment.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default="gemma4-e4b-it")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--soak-requests", type=int, default=320)
    parser.add_argument("--out-dir", default="vllm_test/results")
    parser.add_argument("--strict-model", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def run_one(
    bench_script: Path,
    suite_dir: Path,
    args: argparse.Namespace,
    scenario: Scenario,
) -> dict:
    scenario_root = suite_dir / "runs" / scenario.name
    scenario_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(bench_script),
        "--base-url",
        args.base_url,
        "--api-key",
        args.api_key,
        "--model",
        args.model,
        "--prompt",
        scenario.prompt,
        "--temperature",
        str(args.temperature),
        "--max-tokens",
        str(scenario.max_tokens),
        "--requests",
        str(scenario.requests),
        "--concurrency",
        str(scenario.concurrency),
        "--timeout",
        str(args.timeout),
        "--warmup",
        str(args.warmup),
        "--out-dir",
        str(scenario_root),
        "--name-prefix",
        scenario.name,
    ]
    if scenario.stream:
        cmd.append("--stream")
    if args.strict_model:
        cmd.append("--strict-model")

    print(f"\n[Scenario] {scenario.name} - {scenario.description}")
    print("[Command] " + " ".join(cmd))

    if args.dry_run:
        return {
            "scenario": asdict(scenario),
            "returncode": 0,
            "status": "SKIPPED",
            "reason": "dry_run",
        }

    proc = subprocess.run(cmd, text=True)

    dirs = sorted([d for d in scenario_root.glob(f"{scenario.name}_*") if d.is_dir()])
    if not dirs:
        return {
            "scenario": asdict(scenario),
            "returncode": proc.returncode,
            "status": "FAIL",
            "reason": "result_dir_missing",
        }

    run_dir = dirs[-1]
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        return {
            "scenario": asdict(scenario),
            "returncode": proc.returncode,
            "status": "FAIL",
            "reason": "summary_json_missing",
            "run_dir": str(run_dir),
        }

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = summary.get("metrics", {})

    rules_ok, failures = evaluate_rules(metrics, scenario.rules)
    process_ok = proc.returncode == 0
    status = "PASS" if (process_ok and rules_ok) else "FAIL"

    return {
        "scenario": asdict(scenario),
        "returncode": proc.returncode,
        "status": status,
        "run_dir": str(run_dir),
        "summary_json": str(summary_path),
        "metrics": metrics,
        "rule_failures": failures,
    }


def render_table_line(item: dict) -> str:
    name = item["scenario"]["name"]
    status = item["status"]
    metrics = item.get("metrics", {})
    sr = metrics.get("success_rate_percent", 0.0)
    p95 = metrics.get("p95_latency_s", 0.0)
    ttft = metrics.get("p95_ttft_s", 0.0)
    tps = metrics.get("completion_token_throughput_tps", 0.0)
    return f"{name:<20} {status:<6} sr={sr:>6.2f}% p95={p95:>6.3f}s p95_ttft={ttft:>6.3f}s tok_tps={tps:>8.2f}"


def main() -> int:
    args = build_parser().parse_args()
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    suite_dir = Path(args.out_dir) / f"strict_suite_{ts}"
    suite_dir.mkdir(parents=True, exist_ok=True)

    bench_script = Path(__file__).resolve().with_name("benchmark_gemma4_vllm.py")
    if not bench_script.exists():
        raise SystemExit(f"benchmark script not found: {bench_script}")

    scenarios = scenario_catalog(args.soak_requests)

    print("[Strict Suite Config]")
    print(f"base_url={args.base_url}")
    print(f"model={args.model}")
    print(f"suite_dir={suite_dir}")
    print(f"scenario_count={len(scenarios)}")

    results: list[dict] = []

    for scenario in scenarios:
        result = run_one(bench_script, suite_dir, args, scenario)
        results.append(result)

        if result["status"] == "PASS":
            print("[Result] " + render_table_line(result))
        else:
            print("[Result] " + render_table_line(result))
            for failure in result.get("rule_failures", []):
                print(f"  - gate_fail: {failure}")
            if args.fail_fast and result["status"] == "FAIL":
                print("[Suite] fail-fast enabled, stop remaining scenarios.")
                break

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    skip_count = sum(1 for r in results if r["status"] == "SKIPPED")
    overall_pass = fail_count == 0

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "suite_dir": str(suite_dir),
        "config": {
            "base_url": args.base_url,
            "model": args.model,
            "timeout": args.timeout,
            "temperature": args.temperature,
            "warmup": args.warmup,
            "soak_requests": args.soak_requests,
        },
        "summary": {
            "total": len(results),
            "pass": pass_count,
            "fail": fail_count,
            "skipped": skip_count,
            "overall": "PASS" if overall_pass else "FAIL",
        },
        "results": results,
    }

    report_json = suite_dir / "suite_report.json"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "[Strict Suite Summary]",
        f"overall={'PASS' if overall_pass else 'FAIL'}",
        f"total={len(results)} pass={pass_count} fail={fail_count} skipped={skip_count}",
        "",
        "[Scenario Results]",
    ]
    for item in results:
        lines.append(render_table_line(item))
        for failure in item.get("rule_failures", []):
            lines.append(f"  gate_fail: {failure}")

    lines.append("")
    lines.append(f"suite_report_json={report_json}")

    summary_txt = "\n".join(lines) + "\n"
    summary_path = suite_dir / "suite_summary.txt"
    summary_path.write_text(summary_txt, encoding="utf-8")

    print()
    print(summary_txt)

    return 0 if overall_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
