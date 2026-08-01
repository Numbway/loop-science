import {
  AimOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  LoadingOutlined,
  NodeIndexOutlined,
  PlusOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  type Edge,
  type Node,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import ExperimentNodeCard, {
  type ExperimentNodeData,
} from "../components/experiment-tree/ExperimentNode";
import {
  getExperimentTree,
  type ExperimentStatus,
  type ExperimentTreeNode,
  type ProjectStatus,
} from "../services/experimentTree";
import "./ExperimentTree.css";

const nodeTypes: NodeTypes = { experiment: ExperimentNodeCard };
const HORIZONTAL_SPACING = 330;
const VERTICAL_SPACING = 215;

const statusLabels: Record<ExperimentStatus, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

const projectStatusLabels: Record<ProjectStatus, string> = {
  created: "准备中",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
};

function nodeSortKey(nodeId: string): number[] {
  return nodeId.split("-").map((part) => Number.parseInt(part, 10) || 0);
}

function compareNodeIds(left: string, right: string): number {
  const a = nodeSortKey(left);
  const b = nodeSortKey(right);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const difference = (a[index] ?? -1) - (b[index] ?? -1);
    if (difference !== 0) return difference;
  }
  return 0;
}

function buildLayout(
  experiments: ExperimentTreeNode[],
  selectedId: string,
  onSelect: (node: ExperimentTreeNode) => void,
  onBranchIntent: (node: ExperimentTreeNode) => void,
  onReportIntent: (node: ExperimentTreeNode) => void,
): { nodes: Node<ExperimentNodeData>[]; edges: Edge[] } {
  const byNodeId = new Map(experiments.map((node) => [node.node_id, node]));
  const children = new Map<string | null, ExperimentTreeNode[]>();
  experiments.forEach((node) => {
    const parentKey =
      node.parent_node_id && byNodeId.has(node.parent_node_id)
        ? node.parent_node_id
        : null;
    const siblings = children.get(parentKey) ?? [];
    siblings.push(node);
    children.set(parentKey, siblings);
  });
  children.forEach((siblings) =>
    siblings.sort((left, right) => compareNodeIds(left.node_id, right.node_id)),
  );

  const positions = new Map<string, { x: number; y: number }>();
  const visiting = new Set<string>();
  const placed = new Set<string>();
  let nextLeaf = 0;

  const placeNode = (node: ExperimentTreeNode, depth: number): number => {
    if (visiting.has(node.node_id)) {
      const fallbackX = nextLeaf * HORIZONTAL_SPACING;
      nextLeaf += 1;
      return fallbackX;
    }
    visiting.add(node.node_id);
    const descendants = children.get(node.node_id) ?? [];
    const childPositions = descendants.map((child) =>
      placeNode(child, depth + 1),
    );
    const x =
      childPositions.length > 0
        ? childPositions.reduce((sum, value) => sum + value, 0) /
          childPositions.length
        : nextLeaf++ * HORIZONTAL_SPACING;
    positions.set(node.id, { x, y: depth * VERTICAL_SPACING });
    visiting.delete(node.node_id);
    placed.add(node.id);
    return x;
  };

  (children.get(null) ?? []).forEach((root) => placeNode(root, 0));
  experiments
    .filter((node) => !placed.has(node.id))
    .forEach((node) => placeNode(node, 0));

  const xValues = [...positions.values()].map((position) => position.x);
  const center =
    xValues.length > 0 ? (Math.min(...xValues) + Math.max(...xValues)) / 2 : 0;

  return {
    nodes: experiments.map((experiment) => {
      const position = positions.get(experiment.id) ?? { x: 0, y: 0 };
      return {
        id: experiment.id,
        type: "experiment",
        position: { x: position.x - center, y: position.y },
        selected: experiment.id === selectedId,
        data: {
          experiment,
          onSelect,
          onBranchIntent,
          onReportIntent,
        },
      };
    }),
    edges: experiments
      .filter(
        (experiment) =>
          experiment.parent_node_id && byNodeId.has(experiment.parent_node_id),
      )
      .map((experiment) => {
        const parent = byNodeId.get(experiment.parent_node_id!);
        return {
          id: `${parent!.id}-${experiment.id}`,
          source: parent!.id,
          target: experiment.id,
          type: "smoothstep",
          animated: experiment.status === "running",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: experiment.status === "running" ? "#168f82" : "#8fa0b5",
            width: 14,
            height: 14,
          },
          style: {
            stroke: experiment.status === "running" ? "#168f82" : "#8fa0b5",
            strokeWidth: experiment.status === "running" ? 2 : 1.25,
          },
        };
      }),
  };
}

function formatMetric(name: string, value: number): string {
  const normalizedName = name.toLowerCase();
  if (normalizedName.includes("acc") || normalizedName.includes("precision")) {
    return `${(value <= 1 ? value * 100 : value).toFixed(2)}%`;
  }
  return value.toFixed(4);
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "尚未结束";
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export default function ExperimentTreePage() {
  const { projectId = "" } = useParams();
  const [selectedId, setSelectedId] = useState("");
  const [branchIntent, setBranchIntent] = useState<ExperimentTreeNode | null>(
    null,
  );
  const [reportNotice, setReportNotice] = useState<ExperimentTreeNode | null>(
    null,
  );

  const query = useQuery({
    queryKey: ["experiment-tree", projectId],
    queryFn: () => getExperimentTree(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 5_000,
  });

  useEffect(() => {
    const nodes = query.data?.nodes ?? [];
    if (
      nodes.length > 0 &&
      (!selectedId || !nodes.some((node) => node.id === selectedId))
    ) {
      setSelectedId(nodes[0].id);
    }
  }, [query.data, selectedId]);

  const selectNode = useCallback((node: ExperimentTreeNode) => {
    setSelectedId(node.id);
    setBranchIntent(null);
    setReportNotice(null);
  }, []);

  const showBranchIntent = useCallback((node: ExperimentTreeNode) => {
    setSelectedId(node.id);
    setReportNotice(null);
    setBranchIntent(node);
  }, []);

  const showReportIntent = useCallback((node: ExperimentTreeNode) => {
    setSelectedId(node.id);
    setBranchIntent(null);
    setReportNotice(node);
  }, []);

  const layout = useMemo(
    () =>
      buildLayout(
        query.data?.nodes ?? [],
        selectedId,
        selectNode,
        showBranchIntent,
        showReportIntent,
      ),
    [
      query.data?.nodes,
      selectedId,
      selectNode,
      showBranchIntent,
      showReportIntent,
    ],
  );

  const selectedNode = query.data?.nodes.find((node) => node.id === selectedId);
  const stats = useMemo(() => {
    const nodes = query.data?.nodes ?? [];
    return {
      completed: nodes.filter((node) => node.status === "completed").length,
      running: nodes.filter((node) => node.status === "running").length,
      failed: nodes.filter((node) => node.status === "failed").length,
    };
  }, [query.data?.nodes]);

  if (query.isLoading) {
    return (
      <main className="tree-state-page">
        <LoadingOutlined spin />
        <strong>正在读取实验谱系…</strong>
      </main>
    );
  }

  if (query.isError || !query.data) {
    return (
      <main className="tree-state-page error">
        <WarningOutlined />
        <strong>实验树未能加载</strong>
        <p>确认项目仍然存在并检查后端连接，然后重试。</p>
        <button type="button" onClick={() => query.refetch()}>
          重新加载
        </button>
      </main>
    );
  }

  return (
    <main className="tree-page">
      <header className="tree-project-header">
        <div className="project-identity">
          <span className="tree-eyebrow">LINEAGE ATLAS / 实验谱系</span>
          <h1>{query.data.name}</h1>
          <p>{query.data.paper_title}</p>
        </div>
        <div className="project-live-state">
          <span className={`project-status ${query.data.status}`}>
            <i />
            {projectStatusLabels[query.data.status]}
          </span>
          <span className="refresh-note">
            {query.isFetching ? <LoadingOutlined spin /> : <AimOutlined />}5
            秒同步
          </span>
          <button
            type="button"
            className="tree-refresh"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            <ReloadOutlined />
            刷新
          </button>
        </div>
      </header>

      <section className="tree-summary-strip" aria-label="实验统计">
        <div>
          <NodeIndexOutlined />
          <span>
            <small>节点总数</small>
            <strong>{query.data.nodes.length}</strong>
          </span>
        </div>
        <div>
          <CheckCircleOutlined />
          <span>
            <small>已完成</small>
            <strong>{stats.completed}</strong>
          </span>
        </div>
        <div className={stats.running > 0 ? "live" : ""}>
          <ExperimentOutlined />
          <span>
            <small>运行中</small>
            <strong>{stats.running}</strong>
          </span>
        </div>
        <div className={stats.failed > 0 ? "warning" : ""}>
          <WarningOutlined />
          <span>
            <small>失败</small>
            <strong>{stats.failed}</strong>
          </span>
        </div>
        <div className="target-summary">
          <AimOutlined />
          <span>
            <small>目标指标</small>
            <strong>
              {Object.entries(query.data.target_metrics)
                .map(([name, value]) => `${name} ≥ ${value}`)
                .join(" · ") || "未设置"}
            </strong>
          </span>
        </div>
      </section>

      <section className="tree-workspace">
        <div className="tree-canvas">
          {query.data.nodes.length === 0 ? (
            <div className="empty-tree">
              <ExperimentOutlined />
              <h2>还没有实验节点</h2>
              <p>完成项目创建向导并启动第一次实验后，节点会出现在这里。</p>
              <Link to="/projects/new">创建项目</Link>
            </div>
          ) : (
            <ReactFlow
              nodes={layout.nodes}
              edges={layout.edges}
              nodeTypes={nodeTypes}
              fitView
              fitViewOptions={{ padding: 0.24, maxZoom: 1 }}
              minZoom={0.25}
              maxZoom={1.5}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable
              onNodeClick={(_event, node) => {
                const experiment = query.data.nodes.find(
                  (item) => item.id === node.id,
                );
                if (experiment) selectNode(experiment);
              }}
              proOptions={{ hideAttribution: true }}
            >
              <Background
                variant={BackgroundVariant.Dots}
                gap={24}
                size={1}
                color="#aab8c9"
              />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                nodeColor={(node) => {
                  const status = (node.data.experiment as ExperimentTreeNode)
                    .status;
                  return {
                    completed: "#6457d9",
                    running: "#168f82",
                    failed: "#c55a45",
                    pending: "#c48a2b",
                  }[status];
                }}
                maskColor="rgba(233, 239, 246, 0.78)"
              />
            </ReactFlow>
          )}
          <div className="canvas-legend">
            {(["running", "completed", "pending", "failed"] as const).map(
              (status) => (
                <span key={status} className={status}>
                  <i />
                  {statusLabels[status]}
                </span>
              ),
            )}
          </div>
        </div>

        <aside className="node-inspector">
          {selectedNode ? (
            <>
              <header>
                <div>
                  <span>FIELD LOG / NODE</span>
                  <h2>{selectedNode.node_id}</h2>
                </div>
                <span className={`inspector-status ${selectedNode.status}`}>
                  {statusLabels[selectedNode.status]}
                </span>
              </header>

              <div className="inspector-branch">
                <BranchesOutlined />
                <code>{selectedNode.git_branch}</code>
              </div>

              <section className="inspector-section">
                <h3>关键指标</h3>
                {Object.keys(selectedNode.metrics).length > 0 ? (
                  <dl className="inspector-metrics">
                    {Object.entries(selectedNode.metrics).map(
                      ([name, value]) => (
                        <div key={name}>
                          <dt>{name}</dt>
                          <dd>{formatMetric(name, value)}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                ) : (
                  <p className="inspector-empty">
                    指标将在训练日志产生后出现。
                  </p>
                )}
              </section>

              <section className="inspector-section">
                <h3>本次改进</h3>
                <p>
                  {selectedNode.improvement_description || "初始复现实验基线"}
                </p>
              </section>

              <section className="inspector-section compact">
                <div>
                  <ClockCircleOutlined />
                  <span>运行耗时</span>
                  <strong>
                    {formatDuration(selectedNode.duration_seconds)}
                  </strong>
                </div>
                <div>
                  <AimOutlined />
                  <span>创建者</span>
                  <strong>
                    {selectedNode.created_by === "ai" ? "AI" : "研究者"}
                  </strong>
                </div>
              </section>

              {selectedNode.diagnosis && (
                <section className="inspector-section diagnosis">
                  <h3>AI 诊断</h3>
                  <p>{selectedNode.diagnosis}</p>
                </section>
              )}

              {branchIntent?.id === selectedNode.id && (
                <section className="intent-panel">
                  <button
                    type="button"
                    aria-label="关闭"
                    onClick={() => setBranchIntent(null)}
                  >
                    <CloseOutlined />
                  </button>
                  <PlusOutlined />
                  <strong>父节点已锁定为 {selectedNode.node_id}</strong>
                  <p>M16 将在这里接入 2–3 问的分支创建向导。</p>
                </section>
              )}

              {reportNotice?.id === selectedNode.id && (
                <section className="intent-panel report">
                  <button
                    type="button"
                    aria-label="关闭"
                    onClick={() => setReportNotice(null)}
                  >
                    <CloseOutlined />
                  </button>
                  <FileTextOutlined />
                  <strong>
                    {selectedNode.report_available
                      ? "报告文件已生成"
                      : "该节点尚无报告"}
                  </strong>
                  <p>M17/M18 将接入完整详情与独立 HTML 报告。</p>
                </section>
              )}

              <div className="inspector-actions">
                <button
                  type="button"
                  onClick={() => showReportIntent(selectedNode)}
                >
                  <FileTextOutlined />
                  报告状态
                </button>
                <button
                  type="button"
                  className="branch-action"
                  onClick={() => showBranchIntent(selectedNode)}
                >
                  <PlusOutlined />
                  规划新分支
                </button>
              </div>
            </>
          ) : (
            <div className="inspector-placeholder">
              <NodeIndexOutlined />
              <p>选择一个节点查看实验详情。</p>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
