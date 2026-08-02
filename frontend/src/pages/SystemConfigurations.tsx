import {
  ApiOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  KeyOutlined,
  LoadingOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { getWizardError } from "../services/projectWizard";
import {
  type CredentialProfile,
  type ModelProtocol,
  systemConfigurationsApi,
} from "../services/systemConfigurations";
import "./SystemConfigurations.css";

export default function SystemConfigurationsPage() {
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [activeForm, setActiveForm] = useState<"llm" | "ssh" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [llmName, setLlmName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [provider, setProvider] =
    useState<ModelProtocol>("openai_compatible");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [sshName, setSshName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState(22);
  const [username, setUsername] = useState("");
  const [authType, setAuthType] = useState<"password" | "key">("password");
  const [password, setPassword] = useState("");
  const [privateKey, setPrivateKey] = useState<File | null>(null);
  const [passphrase, setPassphrase] = useState("");

  const llmProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "llm"),
    [profiles],
  );
  const sshProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "ssh"),
    [profiles],
  );

  const load = async () => {
    setError("");
    try {
      setProfiles(await systemConfigurationsApi.list());
    } catch (loadError) {
      setError(getWizardError(loadError));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const createLlm = async () => {
    if (
      !llmName.trim() ||
      !apiKey.trim() ||
      !model.trim() ||
      !baseUrl.trim()
    ) {
      setError("请填写配置名称、协议、Base URL、模型名和 API Key。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await systemConfigurationsApi.createLlm({
        name: llmName.trim(),
        apiKey: apiKey.trim(),
        model: model.trim(),
        baseUrl: baseUrl.trim(),
        provider,
      });
      setLlmName("");
      setApiKey("");
      setActiveForm(null);
      await load();
    } catch (createError) {
      setError(getWizardError(createError));
    } finally {
      setBusy(false);
    }
  };

  const createSsh = async () => {
    if (!sshName.trim() || !host.trim() || !username.trim()) {
      setError("请填写配置名称、服务器地址和用户名。");
      return;
    }
    if (authType === "password" && !password) {
      setError("请输入 SSH 登录密码。");
      return;
    }
    if (authType === "key" && !privateKey) {
      setError("请选择 SSH 私钥文件。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await systemConfigurationsApi.createSsh({
        name: sshName.trim(),
        host: host.trim(),
        port,
        username: username.trim(),
        authType,
        password,
        privateKey,
        passphrase,
      });
      setSshName("");
      setHost("");
      setUsername("");
      setPassword("");
      setPrivateKey(null);
      setPassphrase("");
      setActiveForm(null);
      await load();
    } catch (createError) {
      setError(getWizardError(createError));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (profile: CredentialProfile) => {
    if (!window.confirm(`删除配置“${profile.name}”？`)) return;
    setBusy(true);
    setError("");
    try {
      await systemConfigurationsApi.remove(profile.id);
      await load();
    } catch (removeError) {
      setError(getWizardError(removeError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="config-registry-page">
      <header className="registry-hero">
        <div>
          <p>SYSTEM CONNECTION REGISTRY</p>
          <h1>先登记连接，再交给项目选择</h1>
          <span>
            模型协议、访问地址、密钥与服务器凭据只维护一次。项目只保存配置引用。
          </span>
        </div>
        <div className="registry-route" aria-label="配置复用关系">
          <span><ApiOutlined /> 模型配置</span>
          <b>→</b>
          <span><SafetyCertificateOutlined /> 研究项目</span>
          <b>→</b>
          <span><CloudServerOutlined /> 训练服务器</span>
        </div>
      </header>

      {error && <div className="registry-error" role="alert">{error}</div>}

      <section className="registry-columns">
        <RegistrySection
          title="大模型配置"
          code="LLM CREDENTIALS"
          icon={<ApiOutlined />}
          count={llmProfiles.length}
          onAdd={() => setActiveForm(activeForm === "llm" ? null : "llm")}
        >
          {activeForm === "llm" && (
            <div className="registry-form">
              <label>
                <span>配置名称</span>
                <input
                  value={llmName}
                  onChange={(event) => setLlmName(event.target.value)}
                  placeholder="例如：实验室 Claude"
                />
              </label>
              <label>
                <span>模型</span>
                <input
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  placeholder={
                    provider === "anthropic"
                      ? "例如：claude-sonnet-4-6"
                      : "填写服务商提供的模型 ID"
                  }
                />
              </label>
              <div className="registry-auth protocol-switch wide-field">
                <button
                  type="button"
                  className={provider === "openai_compatible" ? "active" : ""}
                  onClick={() => {
                    setProvider("openai_compatible");
                    setBaseUrl("https://api.openai.com/v1");
                    setModel("");
                  }}
                >
                  OpenAI-compatible
                </button>
                <button
                  type="button"
                  className={provider === "anthropic" ? "active" : ""}
                  onClick={() => {
                    setProvider("anthropic");
                    setBaseUrl("https://api.anthropic.com");
                    setModel("claude-sonnet-4-6");
                  }}
                >
                  Anthropic Messages
                </button>
              </div>
              <label className="wide-field">
                <span>Base URL</span>
                <input
                  type="url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://provider.example/v1"
                />
                <small className="field-hint">
                  {provider === "openai_compatible"
                    ? "填写兼容接口的 API 根地址，通常以 /v1 结尾。"
                    : "填写 Messages API 根地址；客户端会自动追加 /v1/messages。"}
                </small>
              </label>
              <label className="wide-field">
                <span>API Key</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="输入服务商提供的密钥"
                />
              </label>
              <button type="button" onClick={createLlm} disabled={busy}>
                {busy ? <LoadingOutlined /> : <KeyOutlined />} 保存模型配置
              </button>
            </div>
          )}
          <ProfileList profiles={llmProfiles} busy={busy} onRemove={remove} />
        </RegistrySection>

        <RegistrySection
          title="SSH 服务器"
          code="REMOTE MACHINES"
          icon={<CloudServerOutlined />}
          count={sshProfiles.length}
          onAdd={() => setActiveForm(activeForm === "ssh" ? null : "ssh")}
        >
          {activeForm === "ssh" && (
            <div className="registry-form ssh-registry-form">
              <label>
                <span>配置名称</span>
                <input
                  value={sshName}
                  onChange={(event) => setSshName(event.target.value)}
                  placeholder="例如：A100 训练节点"
                />
              </label>
              <label>
                <span>服务器地址</span>
                <input value={host} onChange={(event) => setHost(event.target.value)} />
              </label>
              <label>
                <span>端口</span>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  value={port}
                  onChange={(event) => setPort(Number(event.target.value))}
                />
              </label>
              <label>
                <span>用户名</span>
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
              </label>
              <div className="registry-auth wide-field">
                <button
                  type="button"
                  className={authType === "password" ? "active" : ""}
                  onClick={() => setAuthType("password")}
                >
                  账号密码
                </button>
                <button
                  type="button"
                  className={authType === "key" ? "active" : ""}
                  onClick={() => setAuthType("key")}
                >
                  公私钥
                </button>
              </div>
              {authType === "password" ? (
                <label className="wide-field">
                  <span>登录密码</span>
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </label>
              ) : (
                <>
                  <label>
                    <span>私钥文件</span>
                    <input
                      className="native-file"
                      type="file"
                      accept=".pem,.key,text/plain"
                      onChange={(event) =>
                        setPrivateKey(event.target.files?.[0] ?? null)
                      }
                    />
                  </label>
                  <label>
                    <span>私钥口令（可选）</span>
                    <input
                      type="password"
                      value={passphrase}
                      onChange={(event) => setPassphrase(event.target.value)}
                    />
                  </label>
                </>
              )}
              <button type="button" onClick={createSsh} disabled={busy}>
                {busy ? <LoadingOutlined /> : <CloudServerOutlined />}
                连接验证并保存
              </button>
            </div>
          )}
          <ProfileList profiles={sshProfiles} busy={busy} onRemove={remove} />
        </RegistrySection>
      </section>
    </main>
  );
}

function RegistrySection({
  title,
  code,
  icon,
  count,
  onAdd,
  children,
}: {
  title: string;
  code: string;
  icon: ReactNode;
  count: number;
  onAdd: () => void;
  children: ReactNode;
}) {
  return (
    <section className="registry-section">
      <header>
        <span className="registry-section-icon">{icon}</span>
        <div><small>{code}</small><h2>{title}</h2></div>
        <em>{count} 项</em>
        <button type="button" onClick={onAdd}><PlusOutlined /> 新增</button>
      </header>
      {children}
    </section>
  );
}

function ProfileList({
  profiles,
  busy,
  onRemove,
}: {
  profiles: CredentialProfile[];
  busy: boolean;
  onRemove: (profile: CredentialProfile) => void;
}) {
  if (!profiles.length) {
    return (
      <div className="registry-empty">
        <PlusOutlined />
        <strong>还没有可选择的配置</strong>
        <span>点击右上角“新增”录入第一项。</span>
      </div>
    );
  }
  return (
    <div className="profile-ledger">
      {profiles.map((profile) => (
        <article key={profile.id}>
          <span className="profile-status"><CheckCircleOutlined /></span>
          <div>
            <strong>{profile.name}</strong>
            {profile.kind === "llm" ? (
              <span>
                {profile.public_config.provider === "openai_compatible"
                  ? "OpenAI-compatible"
                  : "Anthropic"}{" "}
                · {String(profile.public_config.model)} ·{" "}
                {String(profile.public_config.masked_key)}
              </span>
            ) : (
              <span>
                {String(profile.public_config.username)}@
                {String(profile.public_config.host)}:
                {String(profile.public_config.port)}
              </span>
            )}
            <small>
              {profile.kind === "ssh"
                ? String(profile.public_config.host_key_fingerprint)
                : String(
                    profile.public_config.base_url ??
                      "https://api.anthropic.com",
                  )}
            </small>
          </div>
          <button
            type="button"
            aria-label={`删除 ${profile.name}`}
            disabled={busy}
            onClick={() => onRemove(profile)}
          >
            <DeleteOutlined />
          </button>
        </article>
      ))}
    </div>
  );
}
