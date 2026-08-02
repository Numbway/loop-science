import api from "./api";

export interface CredentialProfile {
  id: string;
  name: string;
  kind: "llm" | "ssh";
  public_config: Record<string, unknown>;
  verified: boolean;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export type ModelProtocol = "anthropic" | "openai_compatible";

export interface SshProfileInput {
  name: string;
  host: string;
  port: number;
  username: string;
  authType: "password" | "key";
  password: string;
  privateKey: File | null;
  passphrase: string;
}

function sshForm(input: SshProfileInput): FormData {
  const data = new FormData();
  data.append("name", input.name);
  data.append("host", input.host);
  data.append("port", String(input.port));
  data.append("username", input.username);
  data.append("auth_type", input.authType);
  data.append("password", input.password);
  data.append("passphrase", input.passphrase);
  if (input.privateKey) data.append("private_key", input.privateKey);
  return data;
}

export const systemConfigurationsApi = {
  async list(kind?: "llm" | "ssh"): Promise<CredentialProfile[]> {
    const response = await api.get<CredentialProfile[]>("/api/system-configs", {
      params: kind ? { kind } : undefined,
    });
    return response.data;
  },

  async createLlm(input: {
    name: string;
    apiKey: string;
    model: string;
    baseUrl: string;
    provider: ModelProtocol;
  }): Promise<CredentialProfile> {
    const response = await api.post<CredentialProfile>(
      "/api/system-configs/llm",
      {
        name: input.name,
        api_key: input.apiKey,
        provider: input.provider,
        model: input.model,
        base_url: input.baseUrl,
      },
    );
    return response.data;
  },

  async createSsh(input: SshProfileInput): Promise<CredentialProfile> {
    const response = await api.post<CredentialProfile>(
      "/api/system-configs/ssh",
      sshForm(input),
      {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 45_000,
      },
    );
    return response.data;
  },

  async remove(profileId: string): Promise<void> {
    await api.delete(`/api/system-configs/${profileId}`);
  },
};
