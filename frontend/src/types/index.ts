/** Core TypeScript type definitions. */

// User
export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

// Auth
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  name: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

// Project
export interface Project {
  id: string;
  user_id: string;
  name: string;
  paper_title: string;
  paper_path: string;
  paper_metadata: Record<string, unknown>;
  improvement_targets: string[];
  target_metrics: Record<string, number>;
  max_iterations: number;
  repo_path: string;
  status: 'created' | 'running' | 'paused' | 'completed';
  created_at: string;
  updated_at: string;
}

// Experiment
export interface Experiment {
  id: string;
  project_id: string;
  node_id: string;
  parent_node_id: string | null;
  git_branch: string;
  improvement_description: string;
  code_changes: Record<string, unknown>;
  config: Record<string, unknown>;
  metrics: Record<string, number> | null;
  diagnosis: string | null;
  report_html_path: string | null;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_by: 'ai' | 'user';
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
}

// Reference Paper
export interface ReferencePaper {
  id: string;
  project_id: string;
  title: string;
  authors: string[];
  year: number | null;
  arxiv_id: string | null;
  url: string | null;
  local_path: string | null;
  keywords: string[];
  abstract: string | null;
  key_contributions: string[];
  source: 'ai_recommended' | 'user_uploaded';
  download_status: 'success' | 'failed' | 'pending';
  download_error: string | null;
}

// API
export interface ApiError {
  detail: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}