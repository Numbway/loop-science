import axios from "axios";
import api from "./api";

export interface PaperUploadResult {
  project_id: string;
  project_name: string;
  paper_title: string;
  abstract: string;
  authors: string[];
  keywords: string[];
}

export interface PaperAnalysis {
  summary: string;
  research_problem: string;
  method_steps: string[];
  datasets: string[];
  metrics: string[];
  implementation_requirements: string[];
  compute_requirements: string[];
  reproducibility_risks: string[];
  model: string;
}

export interface DataSelection {
  ready: boolean;
  source: "remote";
  kind: "file" | "folder";
  selected_name: string;
  path: string;
  file_count: number;
  total_bytes: number;
}

export interface RemoteDataEntry {
  name: string;
  path: string;
  kind: "file" | "folder";
  size: number;
}

export interface RemoteDataListing {
  current_path: string;
  parent_path: string | null;
  entries: RemoteDataEntry[];
  truncated: boolean;
}

export interface SshConnection {
  ready: boolean;
  host: string;
  port: number;
  username: string;
  auth_type: "password" | "key";
  host_key_fingerprint: string;
  capabilities: Record<string, string | boolean>;
}

export interface PreparationStatus {
  workflow: "paper_reproduction" | "existing_assets";
  api_key_ready: boolean;
  paper_analysis_ready: boolean;
  data_ready: boolean;
  execution_ready: boolean;
  code_ready: boolean;
  ready_to_generate: boolean;
  ready_to_start: boolean;
  ai_profile_id: string | null;
  ssh_profile_id: string | null;
  data: DataSelection | null;
  code: RemoteCodeImport | null;
  execution: SshConnection | null;
  missing: string[];
}

export interface ExistingAssetsProject {
  project_id: string;
  project_name: string;
  workflow: "existing_assets";
}

export interface RemoteCodeImport {
  ready: boolean;
  source: "remote";
  selected_name: string;
  path: string;
  entrypoint: string;
  arguments: string[];
  file_count: number;
  total_bytes: number;
  skipped_count: number;
}

export interface ProjectConfig {
  improvement_targets: string[];
  target_metrics: Record<string, number>;
  max_iterations: number;
  summary: string;
}

export interface DialogResult {
  session_id: string;
  complete: boolean;
  question?: string;
  options: string[];
  input_type?: "single" | "multi" | "text";
  config?: ProjectConfig;
}

export interface GeneratedFile {
  path: string;
  language: string;
  content: string;
}

export interface CodeGenerationResult {
  project_id: string;
  files: GeneratedFile[];
  summary: string;
}

export interface WizardProjectSnapshot {
  project_id: string;
  project_name: string;
  paper_title: string;
  abstract: string;
  authors: string[];
  keywords: string[];
  analysis: PaperAnalysis | null;
  dialog_complete: boolean;
  config: ProjectConfig | null;
  preparation: PreparationStatus;
  files: GeneratedFile[];
}

export interface StartExperimentResult {
  project_id: string;
  experiment_id: string;
  status: "queued";
}

export const projectWizardApi = {
  async createExistingAssetsProject(
    name: string,
  ): Promise<ExistingAssetsProject> {
    const response = await api.post<ExistingAssetsProject>(
      "/api/projects/wizard/existing-assets",
      { name },
    );
    return response.data;
  },

  async uploadPaper(
    file: File,
    projectName: string,
  ): Promise<PaperUploadResult> {
    const formData = new FormData();
    formData.append("paper", file);
    formData.append("project_name", projectName);
    const response = await api.post<PaperUploadResult>(
      "/api/projects/wizard/upload",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 60_000,
      },
    );
    return response.data;
  },

  async startDialog(projectId: string): Promise<DialogResult> {
    const response = await api.post<DialogResult>(
      `/api/projects/${projectId}/wizard/dialog/start`,
    );
    return response.data;
  },

  async selectConfigurations(
    projectId: string,
    selection: {
      ai_profile_id?: string | null;
      ssh_profile_id?: string | null;
    },
  ): Promise<PreparationStatus> {
    const response = await api.put<PreparationStatus>(
      `/api/projects/${projectId}/wizard/configurations`,
      selection,
    );
    return response.data;
  },

  async analyzePaper(projectId: string): Promise<PaperAnalysis> {
    const response = await api.post<PaperAnalysis>(
      `/api/projects/${projectId}/wizard/analyze`,
      undefined,
      { timeout: 180_000 },
    );
    return response.data;
  },

  async browseRemoteData(
    projectId: string,
    path?: string,
  ): Promise<RemoteDataListing> {
    const response = await api.get<RemoteDataListing>(
      `/api/projects/${projectId}/wizard/remote-data`,
      {
        params: path ? { path } : undefined,
        timeout: 45_000,
      },
    );
    return response.data;
  },

  async selectRemoteData(
    projectId: string,
    entry: { path: string; kind: "file" | "folder" },
  ): Promise<DataSelection> {
    const response = await api.put<DataSelection>(
      `/api/projects/${projectId}/wizard/remote-data`,
      entry,
      {
        timeout: 45_000,
      },
    );
    return response.data;
  },

  async importRemoteCode(
    projectId: string,
    input: { path: string; entrypoint: string; arguments: string },
  ): Promise<RemoteCodeImport> {
    const response = await api.post<RemoteCodeImport>(
      `/api/projects/${projectId}/wizard/remote-code`,
      input,
      { timeout: 300_000 },
    );
    return response.data;
  },

  async getPreparation(projectId: string): Promise<PreparationStatus> {
    const response = await api.get<PreparationStatus>(
      `/api/projects/${projectId}/wizard/preparation`,
    );
    return response.data;
  },

  async getSnapshot(projectId: string): Promise<WizardProjectSnapshot> {
    const response = await api.get<WizardProjectSnapshot>(
      `/api/projects/${projectId}/wizard/snapshot`,
    );
    return response.data;
  },

  async answerDialog(
    projectId: string,
    sessionId: string,
    answer: string,
  ): Promise<DialogResult> {
    const response = await api.post<DialogResult>(
      `/api/projects/${projectId}/wizard/dialog/answer`,
      { session_id: sessionId, answer },
    );
    return response.data;
  },

  async generateCode(projectId: string): Promise<CodeGenerationResult> {
    const response = await api.post<CodeGenerationResult>(
      `/api/projects/${projectId}/wizard/generate`,
      undefined,
      // Framework generation can span many model tool-use turns. The model
      // provider remains responsible for its own request-level timeouts.
      { timeout: 0 },
    );
    return response.data;
  },

  async saveCode(projectId: string, files: GeneratedFile[]): Promise<void> {
    await api.put(`/api/projects/${projectId}/wizard/code`, { files });
  },

  async startExperiment(projectId: string): Promise<StartExperimentResult> {
    const response = await api.post<StartExperimentResult>(
      `/api/projects/${projectId}/wizard/start`,
    );
    return response.data;
  },
};

export function getWizardError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (detail && typeof detail.detail === "string") {
      const missing = Array.isArray(detail.missing)
        ? `：${detail.missing.join("、")}`
        : "";
      return `${detail.detail}${missing}`;
    }
  }
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}
