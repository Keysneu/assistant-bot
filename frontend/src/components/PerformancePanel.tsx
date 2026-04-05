import { useEffect, useState } from "react";
import { Activity, CheckCircle2, Loader2, RefreshCw, XCircle } from "lucide-react";

import { getPerformanceOverview } from "../lib/api";
import type { PerformanceOverviewResponse } from "../types";
import { Button } from "./ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/Card";
import { cn } from "../lib/utils";

function formatNumber(value: number, digits = 3): string {
  return Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function renderStatus(ok: boolean, text: string) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        ok ? "bg-green-500/10 text-green-600" : "bg-destructive/10 text-destructive"
      )}
    >
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {text}
    </span>
  );
}

export function PerformancePanel() {
  const [data, setData] = useState<PerformanceOverviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getPerformanceOverview();
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载性能数据失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">Gemma4 性能展示</h2>
            <p className="text-sm text-muted-foreground mt-1">
              基于项目内最近一次 benchmark / strict suite / capability probe 结果
            </p>
          </div>
          <Button onClick={load} variant="outline" size="sm" disabled={isLoading}>
            <RefreshCw className={cn("h-4 w-4 mr-2", isLoading && "animate-spin")} />
            刷新
          </Button>
        </div>

        {error && (
          <Card className="border-destructive/30">
            <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
          </Card>
        )}

        {isLoading && !data ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            <Loader2 className="h-6 w-6 mr-2 animate-spin" />
            正在加载性能数据...
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>当前 Provider</CardDescription>
                  <CardTitle className="text-base">{data?.provider || "-"}</CardTitle>
                </CardHeader>
                <CardContent className="pt-0 text-sm text-muted-foreground">
                  active model: {data?.active_model || "-"}
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>vLLM 连通状态</CardDescription>
                  <CardTitle className="text-base">
                    {data ? renderStatus(data.vllm_connected, data.vllm_connected ? "已连接" : "不可用") : "-"}
                  </CardTitle>
                </CardHeader>
                {!data?.vllm_connected && data?.vllm_reason && (
                  <CardContent className="pt-0 text-xs text-destructive">{data.vllm_reason}</CardContent>
                )}
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>更新时间</CardDescription>
                  <CardTitle className="text-base">
                    {data?.generated_at ? new Date(data.generated_at).toLocaleString() : "-"}
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">直连 Benchmark（最新）</CardTitle>
                  <CardDescription>{data?.latest_benchmark?.run_id || "暂无结果"}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {data?.latest_benchmark ? (
                    <>
                      <div>success_rate: {formatNumber(data.latest_benchmark.success_rate_percent, 2)}%</div>
                      <div>p95_latency: {formatNumber(data.latest_benchmark.p95_latency_s)}s</div>
                      <div>p95_ttft: {formatNumber(data.latest_benchmark.p95_ttft_s)}s</div>
                      <div>req_throughput: {formatNumber(data.latest_benchmark.request_throughput_rps)} req/s</div>
                      <div>
                        token_throughput: {formatNumber(data.latest_benchmark.completion_token_throughput_tps)} tok/s
                      </div>
                    </>
                  ) : (
                    <div className="text-muted-foreground">未找到 `gemma4_direct_*` 结果目录</div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">严格套件（最新）</CardTitle>
                  <CardDescription>{data?.latest_strict_suite?.run_id || "暂无结果"}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {data?.latest_strict_suite ? (
                    <>
                      <div className="flex items-center gap-2">
                        overall:
                        {renderStatus(
                          data.latest_strict_suite.overall.toUpperCase() === "PASS",
                          data.latest_strict_suite.overall
                        )}
                      </div>
                      <div>
                        pass/fail/total: {data.latest_strict_suite.pass_count}/{data.latest_strict_suite.fail_count}/
                        {data.latest_strict_suite.total}
                      </div>
                    </>
                  ) : (
                    <div className="text-muted-foreground">未找到 `strict_suite_*` 结果目录</div>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Activity className="h-5 w-5" />
                  Gemma4 能力探测（最新）
                </CardTitle>
                <CardDescription>{data?.latest_capability_probe?.run_id || "暂无结果"}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {data?.latest_capability_probe ? (
                  <>
                    <div className="text-sm">
                      通过项: {data.latest_capability_probe.passed}/{data.latest_capability_probe.total}
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {data.latest_capability_probe.checks.map((item) => (
                        <div key={item.name} className="rounded-lg border p-3 text-sm">
                          <div className="font-medium">{item.name}</div>
                          <div className="mt-1">{renderStatus(item.passed, item.passed ? "PASS" : "FAIL")}</div>
                          <div className="mt-1 text-xs text-muted-foreground">{item.detail || "-"}</div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    未找到 `cap_probe_*` 结果目录。可先运行 `python3 vllm_test/probe_gemma4_capabilities.py --require-full`。
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
