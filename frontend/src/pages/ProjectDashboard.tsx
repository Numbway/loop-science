import {
  ArrowRightOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  LoadingOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  type ManagedProject,
  listManagedProjects,
} from "../services/projects";
import { getWizardError } from "../services/projectWizard";
import "./ProjectDashboard.css";

type ProjectFilter = "all" | "active" | "preparing" | "completed" | "attention";

const projectStatusLabels: Record<string, string> = {
  created: "准备中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
};

const experimentStatusLabels: Record<string, string> = {
  pending: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

function projectTarget(project: ManagedProject): string {
  if (project.status !== "created") return `/projects/${project.id}/tree`;
  return project.workflow === "existing_assets"
    ? `/projects/${project.id}/continue`
    : `/projects/${project.id}/continue-paper`;
}

function projectAction(project: ManagedProject): string {
  return project.status === "created" ? "继续准备" : "打开实验谱系";
}

function formatUpdated(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function metricValue(value: unknown): string {
  if (typeof value === "number") {
    return Math.abs(value) < 0.01 && value !== 0
      ? value.toExponential(2)
      : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  return String(value);
}

export default function ProjectDashboardPage() {
  const [projects, setProjects] = useState<ManagedProject[]>([]);
  const [filter, setFilter] = useState<ProjectFilter>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setProjects(await listManagedProjects());
    } catch (loadError) {
      setError(getWizardError(loadError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const counts = useMemo(
    () => ({
      active: projects.filter(
        (project) =>
          project.status === "running" ||
          project.latest_experiment_status === "pending" ||
          project.latest_experiment_status === "running",
      ).length,
      preparing: projects.filter((project) => project.status === "created").length,
      completed: projects.filter((project) => project.status === "completed").length,
      attention: projects.filter(
        (project) =>
          project.latest_experiment_status === "failed" ||
          project.status === "paused",
      ).length,
    }),
    [projects],
  );

  const visibleProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return projects.filter((project) => {
      const matchesQuery =
        !normalizedQuery ||
        project.name.toLocaleLowerCase().includes(normalizedQuery) ||
        project.paper_title.toLocaleLowerCase().includes(normalizedQuery) ||
        project.remote_host?.toLocaleLowerCase().includes(normalizedQuery);
      const matchesFilter =
        filter === "all" ||
        (filter === "active" &&
          (project.status === "running" ||
            ["pending", "running"].includes(
              project.latest_experiment_status ?? "",
            ))) ||
        (filter === "preparing" && project.status === "created") ||
        (filter === "completed" && project.status === "completed") ||
        (filter === "attention" &&
          (project.status === "paused" ||
            project.latest_experiment_status === "failed"));
      return matchesQuery && matchesFilter;
    });
  }, [filter, projects, query]);

  return (
    <main className="project-dashboard">
      <header className="project-dashboard-hero">
        <div>
          <span>RESEARCH RUN LEDGER</span>
          <h1>实验管理</h1>
          <p>所有项目、实验分支和运行状态都从这里重新进入。</p>
        </div>
        <Link to="/projects/new">
          <PlusOutlined />
          新建项目
        </Link>
      </header>

      <section className="project-instrument-strip" aria-label="项目状态汇总">
        <button
          type="button"
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          <small>ALL PROJECTS</small>
          <strong>{projects.length}</strong>
          <span>全部项目</span>
        </button>
        <button
          type="button"
          className={filter === "active" ? "active" : ""}
          onClick={() => setFilter("active")}
        >
          <small>LIVE RUNS</small>
          <strong>{counts.active}</strong>
          <span>正在运行</span>
        </button>
        <button
          type="button"
          className={filter === "preparing" ? "active" : ""}
          onClick={() => setFilter("preparing")}
        >
          <small>PREPARATION</small>
          <strong>{counts.preparing}</strong>
          <span>等待准备</span>
        </button>
        <button
          type="button"
          className={filter === "completed" ? "active" : ""}
          onClick={() => setFilter("completed")}
        >
          <small>ARCHIVED</small>
          <strong>{counts.completed}</strong>
          <span>已经完成</span>
        </button>
        <button
          type="button"
          className={filter === "attention" ? "active" : ""}
          onClick={() => setFilter("attention")}
        >
          <small>ATTENTION</small>
          <strong>{counts.attention}</strong>
          <span>需要处理</span>
        </button>
      </section>

      <section className="project-ledger">
        <header>
          <div>
            <strong>项目运行台账</strong>
            <span>{visibleProjects.length} 个匹配项目</span>
          </div>
          <div className="project-ledger-tools">
            <label>
              <SearchOutlined />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索项目、论文或服务器"
              />
            </label>
            <button type="button" onClick={() => void load()} disabled={loading}>
              {loading ? <LoadingOutlined /> : <ReloadOutlined />}
              刷新
            </button>
          </div>
        </header>

        {error && <div className="project-dashboard-error">{error}</div>}

        {loading && !projects.length ? (
          <div className="project-dashboard-loading">
            <LoadingOutlined />
            <span>正在读取项目与实验状态…</span>
          </div>
        ) : visibleProjects.length ? (
          <div className="project-ledger-list">
            {visibleProjects.map((project) => {
              const metrics = Object.entries(project.latest_metrics).slice(0, 3);
              const needsAttention =
                project.latest_experiment_status === "failed" ||
                project.status === "paused";
              return (
                <article
                  className={`project-ledger-row status-${project.status} ${
                    needsAttention ? "needs-attention" : ""
                  }`}
                  key={project.id}
                >
                  <div className="project-status-spine" aria-hidden="true">
                    {needsAttention ? (
                      <WarningOutlined />
                    ) : project.status === "completed" ? (
                      <CheckCircleOutlined />
                    ) : project.status === "created" ? (
                      <ClockCircleOutlined />
                    ) : (
                      <ExperimentOutlined />
                    )}
                  </div>

                  <div className="project-ledger-identity">
                    <div>
                      {project.workflow === "existing_assets" ? (
                        <CodeOutlined />
                      ) : (
                        <FilePdfOutlined />
                      )}
                      <span>
                        {project.workflow === "existing_assets"
                          ? "已有资产直跑"
                          : "论文复现"}
                      </span>
                    </div>
                    <h2>{project.name}</h2>
                    <p>
                      {project.workflow === "existing_assets"
                        ? project.code_entrypoint || "训练代码待导入"
                        : project.paper_title}
                    </p>
                  </div>

                  <div className="project-ledger-run">
                    <small>PROJECT / LATEST RUN</small>
                    <strong>
                      {projectStatusLabels[project.status] ?? project.status}
                      <span>·</span>
                      {project.latest_experiment_status
                        ? experimentStatusLabels[
                            project.latest_experiment_status
                          ] ?? project.latest_experiment_status
                        : "尚未启动"}
                    </strong>
                    <p>
                      <BranchesOutlined />
                      {project.experiment_count} 个实验节点
                      {project.remote_host && (
                        <>
                          <CloudServerOutlined />
                          {project.remote_host}
                        </>
                      )}
                    </p>
                  </div>

                  <div className="project-ledger-metrics">
                    <small>LATEST METRICS</small>
                    {metrics.length ? (
                      <div>
                        {metrics.map(([name, value]) => (
                          <span key={name}>
                            <em>{name}</em>
                            <strong>{metricValue(value)}</strong>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p>
                        {project.data_name
                          ? `数据：${project.data_name}`
                          : "等待实验指标"}
                      </p>
                    )}
                  </div>

                  <div className="project-ledger-action">
                    <small>更新于 {formatUpdated(project.updated_at)}</small>
                    <Link to={projectTarget(project)}>
                      {projectAction(project)}
                      <ArrowRightOutlined />
                    </Link>
                    {project.latest_experiment_id && (
                      <Link
                        className="project-detail-link"
                        to={`/experiments/${project.latest_experiment_id}`}
                      >
                        最近一次实验
                      </Link>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="project-dashboard-empty">
            <ExperimentOutlined />
            <h2>{projects.length ? "没有匹配的项目" : "还没有实验项目"}</h2>
            <p>
              {projects.length
                ? "调整筛选条件或搜索词。"
                : "创建第一个项目后，它会固定出现在这个管理台。"}
            </p>
            {!projects.length && (
              <Link to="/projects/new">
                <PlusOutlined />
                新建项目
              </Link>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
