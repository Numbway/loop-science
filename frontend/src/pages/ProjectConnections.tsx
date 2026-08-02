import {
  ApiOutlined,
  ArrowLeftOutlined,
  CheckOutlined,
  CloudServerOutlined,
  LoadingOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getExperimentTree } from "../services/experimentTree";
import {
  getWizardError,
  type PreparationStatus,
  projectWizardApi,
} from "../services/projectWizard";
import {
  type CredentialProfile,
  systemConfigurationsApi,
} from "../services/systemConfigurations";
import "./ProjectConnections.css";

export default function ProjectConnectionsPage() {
  const { projectId = "" } = useParams();
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [preparation, setPreparation] = useState<PreparationStatus | null>(null);
  const [projectName, setProjectName] = useState("研究项目");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<"llm" | "ssh" | "">("");
  const [error, setError] = useState("");

  const llmProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "llm"),
    [profiles],
  );
  const sshProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "ssh"),
    [profiles],
  );

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [available, status, project] = await Promise.all([
          systemConfigurationsApi.list(),
          projectWizardApi.getPreparation(projectId),
          getExperimentTree(projectId),
        ]);
        if (!active) return;
        setProfiles(available);
        setPreparation(status);
        setProjectName(project.name);
      } catch (loadError) {
        if (active) setError(getWizardError(loadError));
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [projectId]);

  const selectProfile = async (
    kind: "llm" | "ssh",
    profileId: string,
  ) => {
    const current =
      kind === "llm"
        ? preparation?.ai_profile_id
        : preparation?.ssh_profile_id;
    if (current === profileId) return;
    setSaving(kind);
    setError("");
    try {
      const status = await projectWizardApi.selectConfigurations(projectId, {
        [kind === "llm" ? "ai_profile_id" : "ssh_profile_id"]: profileId,
      });
      setPreparation(status);
    } catch (selectionError) {
      setError(getWizardError(selectionError));
    } finally {
      setSaving("");
    }
  };

  return (
    <main className="project-connections-page">
      <header className="project-connections-hero">
        <div>
          <Link to={`/projects/${projectId}/tree`}>
            <ArrowLeftOutlined /> 返回实验谱系
          </Link>
          <p>PROJECT CONNECTION ROUTING</p>
          <h1>{projectName}</h1>
          <span>这个项目只选择系统配置档案；密钥与 SSH 凭据不会复制进项目。</span>
        </div>
        <div className="connection-route">
          <span><SettingOutlined /> 系统档案</span>
          <b>→</b>
          <span><SafetyCertificateOutlined /> 当前项目</span>
          <b>→</b>
          <span><CloudServerOutlined /> 实验执行</span>
        </div>
      </header>

      {error && <div className="project-connections-error" role="alert">{error}</div>}

      {loading ? (
        <div className="project-connections-loading">
          <LoadingOutlined spin />
          <strong>正在读取项目配置引用…</strong>
        </div>
      ) : (
        <div className="connection-selector-grid">
          <ConnectionSelector
            code="MODEL PROFILE"
            title="论文分析与代码生成"
            description="选择系统中录入的大模型配置。切换模型配置后，需要重新执行论文分析。"
            icon={<ApiOutlined />}
            profiles={llmProfiles}
            selectedId={preparation?.ai_profile_id ?? null}
            saving={saving === "llm"}
            onSelect={(id) => selectProfile("llm", id)}
          />
          <ConnectionSelector
            code="REMOTE MACHINE"
            title="训练服务器"
            description="选择已经完成连接验证的 SSH 服务器；实验任务会在该服务器上执行。"
            icon={<CloudServerOutlined />}
            profiles={sshProfiles}
            selectedId={preparation?.ssh_profile_id ?? null}
            saving={saving === "ssh"}
            onSelect={(id) => selectProfile("ssh", id)}
          />
        </div>
      )}

      <footer className="project-connections-footer">
        <div>
          <strong>配置档案在系统级维护</strong>
          <span>如需新增密钥、密码或私钥，请前往系统配置中心。</span>
        </div>
        <Link to="/settings/connections">
          <SettingOutlined /> 管理系统配置
        </Link>
      </footer>
    </main>
  );
}

function ConnectionSelector({
  code,
  title,
  description,
  icon,
  profiles,
  selectedId,
  saving,
  onSelect,
}: {
  code: string;
  title: string;
  description: string;
  icon: ReactNode;
  profiles: CredentialProfile[];
  selectedId: string | null;
  saving: boolean;
  onSelect: (profileId: string) => void;
}) {
  return (
    <section className="connection-selector">
      <header>
        <span>{icon}</span>
        <div>
          <small>{code}</small>
          <h2>{title}</h2>
        </div>
        {saving && <LoadingOutlined spin />}
      </header>
      <p>{description}</p>
      {profiles.length ? (
        <div className="connection-profile-list">
          {profiles.map((profile) => {
            const selected = profile.id === selectedId;
            return (
              <button
                type="button"
                key={profile.id}
                className={selected ? "selected" : ""}
                disabled={saving}
                onClick={() => onSelect(profile.id)}
              >
                <span className="connection-radio">
                  {selected && <CheckOutlined />}
                </span>
                <span>
                  <strong>{profile.name}</strong>
                  <em>{profileSummary(profile)}</em>
                </span>
                <small>{selected ? "当前使用" : "选择此配置"}</small>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="connection-profile-empty">
          <SettingOutlined />
          <strong>系统中还没有这种配置</strong>
          <Link to="/settings/connections">前往录入</Link>
        </div>
      )}
    </section>
  );
}

function profileSummary(profile: CredentialProfile): string {
  if (profile.kind === "llm") {
    const protocol =
      profile.public_config.provider === "openai_compatible"
        ? "OpenAI-compatible"
        : "Anthropic";
    return `${protocol} · ${String(profile.public_config.model)} · ${String(
      profile.public_config.base_url ?? "https://api.anthropic.com",
    )}`;
  }
  return `${String(profile.public_config.username)}@${String(
    profile.public_config.host,
  )}:${String(profile.public_config.port)}`;
}
