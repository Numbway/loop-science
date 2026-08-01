import api from "./api";

export type ExperimentStatus = "pending" | "running" | "completed" | "failed";
export type ProjectStatus = "created" | "running" | "paused" | "completed";

export interface ExperimentTreeNode {
  id: string;
  node_id: string;
  parent_node_id: string | null;
  git_branch: string;
  improvement_description: string;
  status: ExperimentStatus;
  metrics: Record<string, number>;
  config: Record<string, unknown>;
  diagnosis: string | null;
  duration_seconds: number | null;
  created_by: "ai" | "user";
  started_at: string | null;
  completed_at: string | null;
  report_available: boolean;
}

export interface ProjectTree {
  project_id: string;
  name: string;
  paper_title: string;
  status: ProjectStatus;
  target_metrics: Record<string, number>;
  max_iterations: number;
  nodes: ExperimentTreeNode[];
  updated_at: string;
}

export type BranchFocus = "model" | "data" | "training" | "regularization";
export type BranchBudget = "quick" | "balanced" | "thorough";

export interface BranchPlan {
  focus: BranchFocus;
  approach: string;
  budget: BranchBudget;
}

export interface CreatedExperimentBranch {
  node: ExperimentTreeNode;
  branch: {
    name: string;
    head_sha: string;
    parent_head_sha: string;
  };
}

export async function getExperimentTree(
  projectId: string,
): Promise<ProjectTree> {
  const response = await api.get<ProjectTree>(
    `/api/projects/${projectId}/tree`,
  );
  return response.data;
}

export async function createExperimentBranch(
  projectId: string,
  parentExperimentId: string,
  plan: BranchPlan,
): Promise<CreatedExperimentBranch> {
  const response = await api.post<CreatedExperimentBranch>(
    `/api/projects/${projectId}/tree/nodes/${parentExperimentId}/branches`,
    plan,
  );
  return response.data;
}
