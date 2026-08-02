import api from "./api";

export interface ManagedProject {
  id: string;
  name: string;
  workflow: "paper_reproduction" | "existing_assets";
  status: string;
  paper_title: string;
  created_at: string;
  updated_at: string;
  experiment_count: number;
  experiment_status_counts: Record<string, number>;
  latest_experiment_id: string | null;
  latest_experiment_status: string | null;
  latest_metrics: Record<string, unknown>;
  data_name: string | null;
  remote_host: string | null;
  code_entrypoint: string | null;
}

export async function listManagedProjects(): Promise<ManagedProject[]> {
  const response = await api.get<{ projects: ManagedProject[] }>("/api/projects");
  return response.data.projects;
}
