import {
  BranchesOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  LoadingOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Handle, Position, type NodeProps } from "reactflow";
import type {
  ExperimentStatus,
  ExperimentTreeNode,
} from "../../services/experimentTree";
import "./ExperimentNode.css";

export interface ExperimentNodeData {
  experiment: ExperimentTreeNode;
  onSelect: (experiment: ExperimentTreeNode) => void;
  onBranchIntent: (experiment: ExperimentTreeNode) => void;
  onDetailIntent: (experiment: ExperimentTreeNode) => void;
}

const statusLabels: Record<ExperimentStatus, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
};

function findMetric(
  metrics: Record<string, number>,
  candidates: string[],
): number | undefined {
  const entry = Object.entries(metrics).find(([name]) =>
    candidates.includes(name.toLowerCase().replace(/\//g, "_")),
  );
  return entry?.[1];
}

function formatAccuracy(value: number | undefined): string {
  if (value === undefined) return "—";
  return `${(value <= 1 ? value * 100 : value).toFixed(1)}%`;
}

function formatLoss(value: number | undefined): string {
  return value === undefined ? "—" : value.toFixed(3);
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "计时中";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export default function ExperimentNodeCard({
  data,
  selected,
}: NodeProps<ExperimentNodeData>) {
  const { experiment } = data;
  const accuracy = findMetric(experiment.metrics, [
    "accuracy",
    "acc",
    "validation_accuracy",
    "val_accuracy",
  ]);
  const loss = findMetric(experiment.metrics, [
    "loss",
    "validation_loss",
    "val_loss",
    "train_loss",
  ]);

  return (
    <article
      className={`lineage-node status-${experiment.status} ${
        selected ? "selected" : ""
      }`}
      role="group"
      tabIndex={0}
      aria-label={`实验节点 ${experiment.node_id}，${statusLabels[experiment.status]}`}
      onClick={() => data.onSelect(experiment)}
      onFocus={() => data.onSelect(experiment)}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="lineage-handle"
      />
      <header>
        <span className="node-sequence">{experiment.node_id}</span>
        <span className="node-status">
          {experiment.status === "running" && <LoadingOutlined spin />}
          {statusLabels[experiment.status]}
        </span>
      </header>
      <div className="node-metrics">
        <div>
          <small>ACC</small>
          <strong>{formatAccuracy(accuracy)}</strong>
        </div>
        <div>
          <small>LOSS</small>
          <strong>{formatLoss(loss)}</strong>
        </div>
      </div>
      <p>{experiment.improvement_description || "初始复现实验"}</p>
      <footer>
        <span>
          <ClockCircleOutlined />
          {formatDuration(experiment.duration_seconds)}
        </span>
        <div>
          <button
            type="button"
            title="查看实验详情"
            onClick={(event) => {
              event.stopPropagation();
              data.onDetailIntent(experiment);
            }}
          >
            <FileTextOutlined />
          </button>
          <button
            type="button"
            title="从此节点规划新分支"
            onClick={(event) => {
              event.stopPropagation();
              data.onBranchIntent(experiment);
            }}
          >
            <PlusOutlined />
          </button>
        </div>
      </footer>
      <span className="branch-label">
        <BranchesOutlined />
        {experiment.git_branch}
      </span>
      <Handle
        type="source"
        position={Position.Bottom}
        className="lineage-handle"
      />
    </article>
  );
}
