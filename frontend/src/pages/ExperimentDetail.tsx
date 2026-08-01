import {
  AimOutlined,
  ArrowLeftOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CodeOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  ExportOutlined,
  FileAddOutlined,
  FileTextOutlined,
  LinkOutlined,
  LoadingOutlined,
  MonitorOutlined,
  NodeIndexOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useProjectRealtime } from "../hooks/useProjectRealtime";
import {
  downloadExperimentReport,
  generateExperimentReport,
  getExperimentReport,
  getExperimentDetail,
  type ExperimentDetail,
  type MetricComparison,
} from "../services/experimentDetail";
import type { ExperimentStatus } from "../services/experimentTree";
import type {
  ProjectRealtimeEvent,
  RealtimeConnectionState,
} from "../services/realtime";
import "./ExperimentDetail.css";

const statusLabels: Record<ExperimentStatus, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const realtimeLabels: Record<RealtimeConnectionState, string> = {
  connecting: "连接实时通道",
  live: "实时",
  reconnecting: "重连中",
  offline: "离线轮询",
};

function isPercentMetric(name: string): boolean {
  const normalized = name.toLowerCase();
  return normalized.includes("acc") || normalized.includes("precision");
}

function isLowerBetterMetric(name: string): boolean {
  const normalized = name.toLowerCase();
  return ["loss", "error", "perplexity", "latency"].some((token) =>
    normalized.includes(token),
  );
}

function isImprovement(metric: MetricComparison | undefined): boolean {
  if (!metric || metric.delta === null) return true;
  return isLowerBetterMetric(metric.name)
    ? metric.delta <= 0
    : metric.delta >= 0;
}

function formatMetric(name: string, value: number | null): string {
  if (value === null) return "—";
  if (isPercentMetric(name)) {
    return `${(value <= 1 ? value * 100 : value).toFixed(2)}%`;
  }
  return value.toFixed(4);
}

function formatDelta(metric: MetricComparison): string {
  if (metric.delta === null) return "基线";
  const value = isPercentMetric(metric.name)
    ? metric.delta * 100
    : metric.delta;
  return `${value >= 0 ? "+" : ""}${value.toFixed(
    isPercentMetric(metric.name) ? 2 : 4,
  )}${isPercentMetric(metric.name) ? " pp" : ""}`;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "尚未结束";
  if (seconds < 60) return `${seconds} 秒`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return [
    hours > 0 ? `${hours} 小时` : "",
    minutes > 0 ? `${minutes} 分` : "",
    `${remainder} 秒`,
  ]
    .filter(Boolean)
    .join(" ");
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function diffLineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "file";
  if (line.startsWith("+")) return "added";
  if (line.startsWith("-")) return "removed";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("diff --git")) return "header";
  return "context";
}

export default function ExperimentDetailPage() {
  const { experimentId = "" } = useParams();
  const queryClient = useQueryClient();
  const [reportAction, setReportAction] = useState<
    "generate" | "open" | "download" | null
  >(null);
  const [reportNotice, setReportNotice] = useState("");
  const [reportError, setReportError] = useState("");
  const query = useQuery({
    queryKey: ["experiment-detail", experimentId],
    queryFn: () => getExperimentDetail(experimentId),
    enabled: Boolean(experimentId),
  });
  const handleRealtimeEvent = useCallback(
    (event: ProjectRealtimeEvent) => {
      if (event.type === "heartbeat") return;
      if (event.type === "connected") {
        void queryClient.invalidateQueries({
          queryKey: ["experiment-detail", experimentId],
        });
        return;
      }
      if (event.experiment_id !== experimentId) return;
      queryClient.setQueryData<ExperimentDetail>(
        ["experiment-detail", experimentId],
        (current) => {
          if (!current) return current;
          const eventMetrics = event.metrics ?? {};
          return {
            ...current,
            status: event.status ?? current.status,
            metrics: { ...current.metrics, ...eventMetrics },
            metric_comparisons: current.metric_comparisons.map((metric) => {
              const value = eventMetrics[metric.name];
              return value === undefined
                ? metric
                : {
                    ...metric,
                    current: value,
                    delta:
                      metric.parent === null ? null : value - metric.parent,
                  };
            }),
            diagnosis: event.diagnosis ?? current.diagnosis,
            started_at: event.started_at ?? current.started_at,
            completed_at: event.completed_at ?? current.completed_at,
          };
        },
      );
      if (
        event.type === "experiment_completed" ||
        event.type === "experiment_failed" ||
        event.type === "diagnosis_ready"
      ) {
        void queryClient.invalidateQueries({
          queryKey: ["experiment-detail", experimentId],
        });
      }
    },
    [experimentId, queryClient],
  );
  const realtimeState = useProjectRealtime(
    query.data?.project_id ?? "",
    handleRealtimeEvent,
  );
  const refetchDetail = query.refetch;

  useEffect(() => {
    if (realtimeState === "live" || query.data?.status !== "running") return;
    const fallbackTimer = window.setInterval(() => {
      void refetchDetail();
    }, 15_000);
    return () => window.clearInterval(fallbackTimer);
  }, [query.data?.status, realtimeState, refetchDetail]);

  const generateReport = async () => {
    setReportAction("generate");
    setReportError("");
    setReportNotice("");
    try {
      await generateExperimentReport(experimentId);
      await query.refetch();
      setReportNotice("独立 HTML 报告已生成，可打开或下载归档。");
    } catch {
      setReportError("报告生成失败。检查实验文件和 Git 分支后重试。");
    } finally {
      setReportAction(null);
    }
  };

  const openReport = async () => {
    const reportWindow = window.open("", "_blank");
    if (!reportWindow) {
      setReportError("浏览器阻止了新窗口。允许弹出窗口后重试。");
      return;
    }
    reportWindow.opener = null;
    setReportAction("open");
    setReportError("");
    setReportNotice("");
    try {
      const report = await getExperimentReport(experimentId);
      const reportUrl = URL.createObjectURL(report);
      reportWindow.location.href = reportUrl;
      window.setTimeout(() => URL.revokeObjectURL(reportUrl), 60_000);
    } catch {
      reportWindow.close();
      setReportError("报告未能打开。重新生成后再试。");
    } finally {
      setReportAction(null);
    }
  };

  const downloadReport = async () => {
    setReportAction("download");
    setReportError("");
    setReportNotice("");
    try {
      const report = await downloadExperimentReport(experimentId);
      const reportUrl = URL.createObjectURL(report);
      const anchor = document.createElement("a");
      anchor.href = reportUrl;
      anchor.download = `experiment-${query.data?.node_id ?? experimentId}-report.html`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(reportUrl), 0);
      setReportNotice("报告已下载，可脱离系统独立打开。");
    } catch {
      setReportError("报告下载失败。重新生成后再试。");
    } finally {
      setReportAction(null);
    }
  };

  if (query.isLoading) {
    return (
      <main className="detail-state-page">
        <LoadingOutlined spin />
        <strong>正在整理实验档案…</strong>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="detail-state-page error">
        <WarningOutlined />
        <strong>实验档案未能加载</strong>
        <p>确认实验仍然存在并检查后端连接，然后重试。</p>
        <button type="button" onClick={() => query.refetch()}>
          重新加载
        </button>
      </main>
    );
  }

  const detail = query.data;
  const diffLines = detail.code_diff.patch.split("\n").slice(0, 2_000);
  const primaryMetric =
    detail.metric_comparisons.find((metric) =>
      metric.name.toLowerCase().includes("acc"),
    ) ?? detail.metric_comparisons[0];

  return (
    <main className="experiment-detail-page">
      <nav className="detail-breadcrumb" aria-label="实验导航">
        <Link to={`/projects/${detail.project_id}/tree`}>
          <ArrowLeftOutlined />
          返回实验树
        </Link>
        <span>/</span>
        <span>{detail.project_name}</span>
        <span>/</span>
        <strong>节点 {detail.node_id}</strong>
        <span className={`detail-realtime realtime-${realtimeState}`}>
          <i />
          {realtimeLabels[realtimeState]}
        </span>
      </nav>

      <header className="detail-hero">
        <div className="detail-node-stamp">
          <small>EXPERIMENT RECORD</small>
          <strong>{detail.node_id}</strong>
          <span className={`detail-status ${detail.status}`}>
            <i />
            {statusLabels[detail.status]}
          </span>
        </div>
        <div className="detail-hero-copy">
          <span>RESULT ABSTRACT / 结果摘要</span>
          <h1>{detail.summary}</h1>
          <p>{detail.improvement_description || "初始复现实验基线"}</p>
          <div>
            <code>
              <BranchesOutlined />
              {detail.git_branch}
            </code>
            <span>{detail.paper_title}</span>
          </div>
        </div>
        <div className="detail-primary-result">
          <small>{primaryMetric?.name ?? "METRIC"}</small>
          <strong>
            {primaryMetric
              ? formatMetric(primaryMetric.name, primaryMetric.current)
              : "—"}
          </strong>
          <span className={isImprovement(primaryMetric) ? "positive" : ""}>
            {primaryMetric ? formatDelta(primaryMetric) : "等待指标"}
          </span>
        </div>
      </header>

      <section className="evidence-ruler" aria-label="实验材料完整度">
        <div className={detail.metric_comparisons.length ? "ready" : ""}>
          <span>01</span>
          <strong>指标</strong>
          <small>
            {detail.metric_comparisons.length
              ? `${detail.metric_comparisons.length} 项`
              : "等待中"}
          </small>
        </div>
        <div className={detail.tensorboard.available ? "ready" : ""}>
          <span>02</span>
          <strong>训练监控</strong>
          <small>
            {detail.tensorboard.available
              ? `${detail.tensorboard.event_file_count} 个事件文件`
              : "尚无事件"}
          </small>
        </div>
        <div className={detail.diagnosis ? "ready" : ""}>
          <span>03</span>
          <strong>AI 诊断</strong>
          <small>{detail.diagnosis ? "已记录" : "等待分析"}</small>
        </div>
        <div className={detail.code_diff.available ? "ready" : ""}>
          <span>04</span>
          <strong>代码证据</strong>
          <small>
            {detail.code_diff.available
              ? `${detail.code_diff.files.length} 个文件`
              : "不可用"}
          </small>
        </div>
      </section>

      <div className="detail-layout">
        <div className="detail-main-column">
          <section className="detail-panel metrics-panel">
            <header>
              <span>
                <AimOutlined />
                METRIC COMPARISON
              </span>
              <h2>指标对照</h2>
            </header>
            {detail.metric_comparisons.length ? (
              <div className="metric-comparison-grid">
                {detail.metric_comparisons.map((metric) => (
                  <article key={metric.name}>
                    <span>{metric.name}</span>
                    <strong>{formatMetric(metric.name, metric.current)}</strong>
                    <dl>
                      <div>
                        <dt>父节点</dt>
                        <dd>{formatMetric(metric.name, metric.parent)}</dd>
                      </div>
                      <div>
                        <dt>变化</dt>
                        <dd className={isImprovement(metric) ? "up" : "down"}>
                          {formatDelta(metric)}
                        </dd>
                      </div>
                      <div>
                        <dt>目标</dt>
                        <dd>{formatMetric(metric.name, metric.target)}</dd>
                      </div>
                    </dl>
                  </article>
                ))}
              </div>
            ) : (
              <div className="detail-empty">
                <AimOutlined />
                <p>训练产生指标后，这里会显示与父节点和目标值的对照。</p>
              </div>
            )}
          </section>

          <section className="detail-panel tensorboard-panel">
            <header>
              <span>
                <MonitorOutlined />
                TRAINING MONITOR
              </span>
              <h2>TensorBoard</h2>
            </header>
            {detail.tensorboard.embed_url ? (
              <iframe
                src={detail.tensorboard.embed_url}
                title={`实验 ${detail.node_id} TensorBoard`}
                sandbox="allow-same-origin allow-scripts allow-forms"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="tensorboard-placeholder">
                <MonitorOutlined />
                <div>
                  <strong>
                    {detail.tensorboard.available
                      ? "训练事件已采集，嵌入服务尚未配置"
                      : "尚未检测到 TensorBoard 事件"}
                  </strong>
                  <p>
                    {detail.tensorboard.available
                      ? `已发现 ${detail.tensorboard.event_file_count} 个事件文件。配置 TENSORBOARD_PUBLIC_URL 后即可在此嵌入。`
                      : "实验开始写入 scalar 后，训练曲线会出现在这里。"}
                  </p>
                </div>
              </div>
            )}
          </section>

          <section className="detail-panel diff-panel">
            <header>
              <span>
                <CodeOutlined />
                REPRODUCIBLE CHANGESET
              </span>
              <h2>代码变更</h2>
              <div className="diff-summary">
                <b>+{detail.code_diff.insertions}</b>
                <b>-{detail.code_diff.deletions}</b>
              </div>
            </header>
            <div className="diff-branches">
              <code>{detail.code_diff.base_branch ?? "无父分支"}</code>
              <span>→</span>
              <code>{detail.code_diff.target_branch}</code>
            </div>
            {detail.code_diff.available && detail.code_diff.patch ? (
              <pre className="unified-diff" aria-label="统一格式代码差异">
                {diffLines.map((line, index) => (
                  <code
                    key={`${index}-${line}`}
                    className={diffLineClass(line)}
                  >
                    <span>{String(index + 1).padStart(4, "0")}</span>
                    {line || " "}
                  </code>
                ))}
              </pre>
            ) : (
              <div className="detail-empty">
                <CodeOutlined />
                <p>
                  {detail.code_diff.unavailable_reason ??
                    "该分支与父节点之间没有可显示的代码差异。"}
                </p>
              </div>
            )}
            {(detail.code_diff.truncated ||
              detail.code_diff.patch.split("\n").length > diffLines.length) && (
              <p className="diff-truncated">
                差异过长，页面仅显示前 2,000 行。
              </p>
            )}
          </section>
        </div>

        <aside className="detail-side-column">
          <section className="detail-panel diagnosis-panel">
            <header>
              <span>
                <ExperimentOutlined />
                AI DIAGNOSIS
              </span>
              <h2>实验诊断</h2>
            </header>
            {detail.diagnosis ? (
              <p>{detail.diagnosis}</p>
            ) : (
              <div className="detail-empty compact">
                <ExperimentOutlined />
                <p>实验结束并完成分析后，诊断会记录在这里。</p>
              </div>
            )}
          </section>

          <section className="detail-panel runtime-panel">
            <header>
              <span>
                <ClockCircleOutlined />
                RUN PROFILE
              </span>
              <h2>运行档案</h2>
            </header>
            <dl>
              <div>
                <dt>耗时</dt>
                <dd>{formatDuration(detail.duration_seconds)}</dd>
              </div>
              <div>
                <dt>开始</dt>
                <dd>{formatTimestamp(detail.started_at)}</dd>
              </div>
              <div>
                <dt>结束</dt>
                <dd>{formatTimestamp(detail.completed_at)}</dd>
              </div>
              <div>
                <dt>创建者</dt>
                <dd>{detail.created_by === "ai" ? "AI" : "研究者"}</dd>
              </div>
            </dl>
          </section>

          <section className="detail-panel log-panel">
            <header>
              <span>
                <NodeIndexOutlined />
                RECENT LOG
              </span>
              <h2>训练日志</h2>
            </header>
            {detail.recent_logs.length ? (
              <ol>
                {detail.recent_logs.slice(-8).map((log, index) => (
                  <li key={`${log.timestamp}-${index}`} className={log.level}>
                    <span>{formatTimestamp(log.timestamp)}</span>
                    <code>{log.message}</code>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="detail-empty compact">
                <NodeIndexOutlined />
                <p>暂无持久化训练日志。</p>
              </div>
            )}
          </section>

          <section className="detail-panel evidence-panel">
            <header>
              <span>
                <FileTextOutlined />
                REFERENCE EVIDENCE
              </span>
              <h2>参考依据</h2>
            </header>
            {detail.references.length ? (
              <ol>
                {detail.references.map((reference) => (
                  <li key={reference.id}>
                    <span>
                      {reference.year ?? "—"} /{" "}
                      {reference.authors.slice(0, 2).join(", ") || "未知作者"}
                    </span>
                    <strong>{reference.title}</strong>
                    {reference.key_contributions[0] && (
                      <p>{reference.key_contributions[0]}</p>
                    )}
                    {reference.url && (
                      <a href={reference.url} target="_blank" rel="noreferrer">
                        查看论文
                        <LinkOutlined />
                      </a>
                    )}
                  </li>
                ))}
              </ol>
            ) : (
              <div className="detail-empty compact">
                <FileTextOutlined />
                <p>项目尚未关联参考论文。</p>
              </div>
            )}
          </section>

          <details className="detail-config">
            <summary>查看实验配置</summary>
            <pre>{JSON.stringify(detail.config, null, 2)}</pre>
          </details>

          <section className="report-control" aria-label="独立 HTML 报告">
            <header>
              <span>
                {detail.report_available ? (
                  <CheckCircleOutlined />
                ) : (
                  <FileAddOutlined />
                )}
              </span>
              <div>
                <strong>
                  {detail.report_available ? "HTML 报告已归档" : "生成独立报告"}
                </strong>
                <p>
                  {detail.report_available
                    ? "报告包含七类证据，可独立打开、下载和打印。"
                    : "将当前节点的指标、曲线、诊断和代码差异固化为单个 HTML 文件。"}
                </p>
              </div>
            </header>

            {detail.report_available ? (
              <div className="report-actions">
                <button
                  type="button"
                  onClick={openReport}
                  disabled={reportAction !== null}
                >
                  {reportAction === "open" ? (
                    <LoadingOutlined spin />
                  ) : (
                    <ExportOutlined />
                  )}
                  打开报告
                </button>
                <button
                  type="button"
                  onClick={downloadReport}
                  disabled={reportAction !== null}
                >
                  {reportAction === "download" ? (
                    <LoadingOutlined spin />
                  ) : (
                    <DownloadOutlined />
                  )}
                  下载
                </button>
                <button
                  className="secondary"
                  type="button"
                  onClick={generateReport}
                  disabled={reportAction !== null}
                >
                  {reportAction === "generate" ? (
                    <LoadingOutlined spin />
                  ) : (
                    <FileTextOutlined />
                  )}
                  重新生成
                </button>
              </div>
            ) : (
              <button
                className="report-generate"
                type="button"
                onClick={generateReport}
                disabled={reportAction !== null}
              >
                {reportAction === "generate" ? (
                  <LoadingOutlined spin />
                ) : (
                  <FileAddOutlined />
                )}
                {reportAction === "generate"
                  ? "正在固化证据…"
                  : "生成 HTML 报告"}
              </button>
            )}
            {reportNotice && <p className="report-notice">{reportNotice}</p>}
            {reportError && (
              <p className="report-error" role="alert">
                {reportError}
              </p>
            )}
          </section>
        </aside>
      </div>
    </main>
  );
}
