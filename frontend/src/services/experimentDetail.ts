import api from "./api";
import type { ExperimentStatus } from "./experimentTree";

export interface MetricComparison {
  name: string;
  current: number;
  parent: number | null;
  delta: number | null;
  target: number | null;
}

export interface TrainingLogEntry {
  level: "info" | "warning" | "error";
  message: string;
  timestamp: string;
}

export interface ReferenceEvidence {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  url: string | null;
  key_contributions: string[];
}

export interface TensorBoardEmbed {
  available: boolean;
  event_file_count: number;
  embed_url: string | null;
}

export interface CodeDiff {
  available: boolean;
  base_branch: string | null;
  target_branch: string;
  files: string[];
  patch: string;
  insertions: number;
  deletions: number;
  truncated: boolean;
  unavailable_reason: string | null;
}

export interface ExperimentDetail {
  id: string;
  project_id: string;
  project_name: string;
  paper_title: string;
  node_id: string;
  parent_node_id: string | null;
  parent_experiment_id: string | null;
  git_branch: string;
  status: ExperimentStatus;
  summary: string;
  improvement_description: string;
  metrics: Record<string, number>;
  metric_comparisons: MetricComparison[];
  target_metrics: Record<string, number>;
  config: Record<string, unknown>;
  diagnosis: string | null;
  code_changes: Record<string, unknown>;
  code_diff: CodeDiff;
  tensorboard: TensorBoardEmbed;
  recent_logs: TrainingLogEntry[];
  references: ReferenceEvidence[];
  duration_seconds: number | null;
  created_by: "ai" | "user";
  started_at: string | null;
  completed_at: string | null;
  report_available: boolean;
}

export async function getExperimentDetail(
  experimentId: string,
): Promise<ExperimentDetail> {
  const response = await api.get<ExperimentDetail>(
    `/api/experiments/${experimentId}`,
  );
  return response.data;
}
