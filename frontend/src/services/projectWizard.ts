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

export interface StartExperimentResult {
  project_id: string;
  experiment_id: string;
  status: "queued";
}

export const projectWizardApi = {
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
      { timeout: 180_000 },
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
      return detail.detail;
    }
  }
  return error instanceof Error ? error.message : "操作未完成，请重试。";
}
