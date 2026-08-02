import {
  ArrowLeftOutlined,
  CheckOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  LoadingOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  type PreparationStatus,
  type RemoteDataEntry,
  type RemoteDataListing,
  getWizardError,
  projectWizardApi,
} from "../services/projectWizard";
import {
  type CredentialProfile,
  systemConfigurationsApi,
} from "../services/systemConfigurations";
import "./ExistingAssetsWizard.css";

type BusyArea = "create" | "ssh" | "data" | "code" | "launch" | "ai" | "";

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

interface RemotePathPickerProps {
  label: string;
  hint: string;
  listing: RemoteDataListing | null;
  selected: RemoteDataEntry | null;
  foldersOnly?: boolean;
  busy: boolean;
  onBrowse: (path?: string) => void;
  onSelect: (entry: RemoteDataEntry) => void;
}

function RemotePathPicker({
  label,
  hint,
  listing,
  selected,
  foldersOnly = false,
  busy,
  onBrowse,
  onSelect,
}: RemotePathPickerProps) {
  return (
    <section className="asset-picker">
      <header>
        <div>
          <small>{foldersOnly ? "CODE ROOT" : "DATA INPUT"}</small>
          <h3>{label}</h3>
        </div>
        {selected && <CheckOutlined />}
      </header>
      <p>{hint}</p>
      {listing ? (
        <>
          <div className="asset-browser-toolbar">
            <code title={listing.current_path}>{listing.current_path}</code>
            {listing.parent_path && (
              <button
                type="button"
                onClick={() => onBrowse(listing.parent_path ?? undefined)}
                disabled={busy}
              >
                返回上级
              </button>
            )}
          </div>
          <div className="asset-browser-list">
            <button
              type="button"
              className={
                selected?.path === listing.current_path ? "selected" : ""
              }
              onClick={() =>
                onSelect({
                  name:
                    listing.current_path.split("/").filter(Boolean).pop() ?? "/",
                  path: listing.current_path,
                  kind: "folder",
                  size: 0,
                })
              }
            >
              <FolderOpenOutlined />
              <span>
                <strong>选择当前文件夹</strong>
                <small>{listing.current_path}</small>
              </span>
            </button>
            {listing.entries.map((entry) => {
              const selectable = entry.kind === "folder" || !foldersOnly;
              return (
                <div className="asset-browser-row" key={entry.path}>
                  <button
                    type="button"
                    className={selected?.path === entry.path ? "selected" : ""}
                    onClick={() => selectable && onSelect(entry)}
                    disabled={!selectable || busy}
                  >
                    {entry.kind === "folder" ? (
                      <FolderOutlined />
                    ) : (
                      <FileOutlined />
                    )}
                    <span>
                      <strong>{entry.name}</strong>
                      <small>
                        {entry.kind === "folder"
                          ? "文件夹"
                          : formatBytes(entry.size)}
                      </small>
                    </span>
                  </button>
                  {entry.kind === "folder" && (
                    <button
                      type="button"
                      className="asset-enter-folder"
                      onClick={() => onBrowse(entry.path)}
                      disabled={busy}
                    >
                      进入
                    </button>
                  )}
                </div>
              );
            })}
            {!listing.entries.length && (
              <span className="asset-browser-empty">
                当前目录为空，可以直接选择当前文件夹。
              </span>
            )}
          </div>
          {listing.truncated && (
            <span className="asset-browser-warning">
              当前只显示前 500 项，请进入更具体的目录。
            </span>
          )}
        </>
      ) : (
        <button
          type="button"
          className="asset-load-browser"
          onClick={() => onBrowse()}
          disabled={busy}
        >
          {busy ? <LoadingOutlined /> : <FolderOpenOutlined />}
          浏览服务器目录
        </button>
      )}
      <div className="asset-selection">
        {selected ? (
          <>
            <strong>{selected.name}</strong>
            <code>{selected.path}</code>
          </>
        ) : (
          <span>尚未选择</span>
        )}
      </div>
    </section>
  );
}

export default function ExistingAssetsWizardPage() {
  const { projectId: routeProjectId = "" } = useParams();
  const [phase, setPhase] = useState(routeProjectId ? 1 : 0);
  const [projectName, setProjectName] = useState("");
  const [projectId, setProjectId] = useState(routeProjectId);
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [selectedSshProfileId, setSelectedSshProfileId] = useState("");
  const [selectedAiProfileId, setSelectedAiProfileId] = useState("");
  const [preparation, setPreparation] = useState<PreparationStatus | null>(null);
  const [dataListing, setDataListing] = useState<RemoteDataListing | null>(null);
  const [codeListing, setCodeListing] = useState<RemoteDataListing | null>(null);
  const [selectedData, setSelectedData] = useState<RemoteDataEntry | null>(null);
  const [selectedCode, setSelectedCode] = useState<RemoteDataEntry | null>(null);
  const [entrypoint, setEntrypoint] = useState("train.py");
  const [argumentsText, setArgumentsText] = useState("");
  const [experimentId, setExperimentId] = useState("");
  const [busyArea, setBusyArea] = useState<BusyArea>("");
  const [error, setError] = useState("");

  const sshProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "ssh"),
    [profiles],
  );
  const llmProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "llm"),
    [profiles],
  );

  useEffect(() => {
    systemConfigurationsApi
      .list()
      .then(setProfiles)
      .catch((loadError: unknown) => setError(getWizardError(loadError)));
  }, []);

  useEffect(() => {
    if (!routeProjectId) return;
    let active = true;
    const resume = async () => {
      setBusyArea("create");
      setError("");
      try {
        const status = await projectWizardApi.getPreparation(routeProjectId);
        if (!active) return;
        setProjectId(routeProjectId);
        setPreparation(status);
        setSelectedSshProfileId(status.ssh_profile_id ?? "");
        setSelectedAiProfileId(status.ai_profile_id ?? "");
        if (status.data) {
          setSelectedData({
            name: status.data.selected_name,
            path: status.data.path,
            kind: status.data.kind,
            size: status.data.total_bytes,
          });
        }
        if (status.code) {
          setSelectedCode({
            name: status.code.selected_name,
            path: status.code.path,
            kind: "folder",
            size: status.code.total_bytes,
          });
          setEntrypoint(status.code.entrypoint);
          setArgumentsText(status.code.arguments.join(" "));
        }
        if (status.ssh_profile_id) {
          const [dataHome, codeHome] = await Promise.all([
            projectWizardApi.browseRemoteData(routeProjectId),
            projectWizardApi.browseRemoteData(routeProjectId),
          ]);
          if (!active) return;
          setDataListing(dataHome);
          setCodeListing(codeHome);
        }
      } catch (resumeError) {
        if (active) setError(getWizardError(resumeError));
      } finally {
        if (active) setBusyArea("");
      }
    };
    void resume();
    return () => {
      active = false;
    };
  }, [routeProjectId]);

  const createProject = async () => {
    if (!projectName.trim()) {
      setError("请填写项目名称。");
      return;
    }
    setBusyArea("create");
    setError("");
    try {
      const created = await projectWizardApi.createExistingAssetsProject(
        projectName.trim(),
      );
      setProjectId(created.project_id);
      setPreparation(
        await projectWizardApi.getPreparation(created.project_id),
      );
      setPhase(1);
    } catch (createError) {
      setError(getWizardError(createError));
    } finally {
      setBusyArea("");
    }
  };

  const selectServer = async (profileId: string) => {
    if (!projectId) return;
    setBusyArea("ssh");
    setError("");
    try {
      setSelectedSshProfileId(profileId);
      setPreparation(
        await projectWizardApi.selectConfigurations(projectId, {
          ssh_profile_id: profileId,
        }),
      );
      setSelectedData(null);
      setSelectedCode(null);
      const [dataHome, codeHome] = await Promise.all([
        projectWizardApi.browseRemoteData(projectId),
        projectWizardApi.browseRemoteData(projectId),
      ]);
      setDataListing(dataHome);
      setCodeListing(codeHome);
    } catch (serverError) {
      setError(getWizardError(serverError));
    } finally {
      setBusyArea("");
    }
  };

  const selectOptionalModel = async (profileId: string) => {
    if (!projectId) return;
    setBusyArea("ai");
    setError("");
    try {
      setSelectedAiProfileId(profileId);
      setPreparation(
        await projectWizardApi.selectConfigurations(projectId, {
          ai_profile_id: profileId || null,
        }),
      );
    } catch (modelError) {
      setError(getWizardError(modelError));
    } finally {
      setBusyArea("");
    }
  };

  const browse = async (purpose: "data" | "code", path?: string) => {
    if (!projectId || !selectedSshProfileId) return;
    setBusyArea(purpose);
    setError("");
    try {
      const listing = await projectWizardApi.browseRemoteData(projectId, path);
      if (purpose === "data") {
        setDataListing(listing);
        setSelectedData(null);
      } else {
        setCodeListing(listing);
        setSelectedCode(null);
      }
    } catch (browseError) {
      setError(getWizardError(browseError));
    } finally {
      setBusyArea("");
    }
  };

  const confirmData = async () => {
    if (!projectId || !selectedData) return;
    setBusyArea("data");
    setError("");
    try {
      await projectWizardApi.selectRemoteData(projectId, {
        path: selectedData.path,
        kind: selectedData.kind,
      });
      setPreparation(await projectWizardApi.getPreparation(projectId));
    } catch (dataError) {
      setError(getWizardError(dataError));
    } finally {
      setBusyArea("");
    }
  };

  const importCode = async () => {
    if (!projectId || !selectedCode || !entrypoint.trim()) {
      setError("请选择代码文件夹并填写入口脚本。");
      return;
    }
    setBusyArea("code");
    setError("");
    try {
      await projectWizardApi.importRemoteCode(projectId, {
        path: selectedCode.path,
        entrypoint: entrypoint.trim(),
        arguments: argumentsText.trim(),
      });
      setPreparation(await projectWizardApi.getPreparation(projectId));
    } catch (codeError) {
      setError(getWizardError(codeError));
    } finally {
      setBusyArea("");
    }
  };

  const startExperiment = async () => {
    if (!projectId) return;
    setBusyArea("launch");
    setError("");
    try {
      const current = await projectWizardApi.getPreparation(projectId);
      setPreparation(current);
      if (!current.ready_to_start) {
        setError(`还缺少：${current.missing.join("、")}`);
        return;
      }
      const started = await projectWizardApi.startExperiment(projectId);
      setExperimentId(started.experiment_id);
      setPhase(2);
    } catch (launchError) {
      setError(getWizardError(launchError));
    } finally {
      setBusyArea("");
    }
  };

  return (
    <main className="assets-wizard">
      <aside className="assets-rail">
        <Link to="/projects/new">
          <ArrowLeftOutlined />
          更换启动方式
        </Link>
        <div>
          <span>EXISTING ASSETS SOP</span>
          <strong>DIRECT RUN / 3 GATES</strong>
        </div>
        <ol>
          {[
            ["创建运行项目", "只需要一个项目名称"],
            ["锁定实验资产", "服务器、数据与代码"],
            ["启动远端实验", "建立分支并进入监控"],
          ].map(([label, note], index) => (
            <li
              className={
                index < phase
                  ? "complete"
                  : index === phase
                    ? "active"
                    : ""
              }
              key={label}
            >
              <span>{index < phase ? <CheckOutlined /> : index + 1}</span>
              <div>
                <strong>{label}</strong>
                <small>{note}</small>
              </div>
            </li>
          ))}
        </ol>
      </aside>

      <section className="assets-workspace">
        <header className="assets-workspace-header">
          <span>SKIP PAPER ANALYSIS / KEEP EXPERIMENT TRACE</span>
          <h1>使用已经准备好的训练资产</h1>
          <p>
            代码会从服务器导入为 Git 基线，数据只保存远端引用。启动时系统上传代码快照，并直接读取原数据路径。
          </p>
        </header>

        {error && <div className="assets-error">{error}</div>}

        {phase === 0 && (
          <section className="assets-create-panel">
            <div className="assets-panel-heading">
              <span>01 / PROJECT ENVELOPE</span>
              <h2>先给这次运行一个名字</h2>
              <p>不会要求上传论文，也不会调用大模型生成框架。</p>
            </div>
            <label>
              项目名称
              <input
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="例如：ResNet50 现有基线复跑"
                maxLength={200}
                autoFocus
              />
            </label>
            <button
              type="button"
              className="assets-primary-action"
              onClick={createProject}
              disabled={busyArea !== ""}
            >
              {busyArea === "create" ? (
                <LoadingOutlined />
              ) : (
                <ExperimentOutlined />
              )}
              创建运行项目
            </button>
          </section>
        )}

        {phase === 1 && (
          <>
            <section className="assets-server-panel">
              <div className="assets-panel-heading">
                <span>02A / EXECUTION TARGET</span>
                <h2>选择代码和数据所在的服务器</h2>
                <p>只有系统中已验证并记录主机指纹的 SSH 配置可以使用。</p>
              </div>
              <div className="assets-profile-grid">
                {sshProfiles.map((profile) => (
                  <button
                    type="button"
                    key={profile.id}
                    className={
                      selectedSshProfileId === profile.id ? "selected" : ""
                    }
                    onClick={() => selectServer(profile.id)}
                    disabled={busyArea !== "" || preparation?.code_ready}
                  >
                    {busyArea === "ssh" &&
                    selectedSshProfileId === profile.id ? (
                      <LoadingOutlined />
                    ) : (
                      <CloudServerOutlined />
                    )}
                    <span>
                      <strong>{profile.name}</strong>
                      <small>
                        {String(profile.public_config.username)}@
                        {String(profile.public_config.host)}
                      </small>
                    </span>
                    {preparation?.ssh_profile_id === profile.id && (
                      <CheckOutlined />
                    )}
                  </button>
                ))}
                {!sshProfiles.length && (
                  <div className="assets-empty-config">
                    <span>尚未录入已验证的 SSH 服务器。</span>
                    <Link to="/settings/connections">前往系统配置</Link>
                  </div>
                )}
              </div>
            </section>

            <div className="assets-picker-grid">
              <div>
                <RemotePathPicker
                  label="选择准备好的数据"
                  hint="可以选择一个文件或整个文件夹；数据不会下载或复制。"
                  listing={dataListing}
                  selected={selectedData}
                  busy={busyArea !== ""}
                  onBrowse={(path) => void browse("data", path)}
                  onSelect={setSelectedData}
                />
                <button
                  type="button"
                  className="assets-confirm-action"
                  onClick={confirmData}
                  disabled={
                    busyArea !== "" ||
                    !selectedData ||
                    !selectedSshProfileId
                  }
                >
                  {busyArea === "data" ? (
                    <LoadingOutlined />
                  ) : (
                    <DatabaseOutlined />
                  )}
                  {preparation?.data_ready ? "远端数据已锁定" : "确认使用这份数据"}
                </button>
              </div>

              <div>
                <RemotePathPicker
                  label="选择现有训练代码目录"
                  hint="目录会通过 SFTP 导入并提交为 Git 基线；密钥、.env 和虚拟环境会自动跳过。"
                  listing={codeListing}
                  selected={selectedCode}
                  foldersOnly
                  busy={busyArea !== ""}
                  onBrowse={(path) => void browse("code", path)}
                  onSelect={setSelectedCode}
                />
                <div className="assets-launch-fields">
                  <label>
                    入口脚本
                    <input
                      value={entrypoint}
                      onChange={(event) => setEntrypoint(event.target.value)}
                      placeholder="train.py"
                      disabled={Boolean(preparation?.code_ready)}
                    />
                  </label>
                  <label>
                    启动参数
                    <input
                      value={argumentsText}
                      onChange={(event) => setArgumentsText(event.target.value)}
                      placeholder="--data-path {data_path} --epochs 20"
                      disabled={Boolean(preparation?.code_ready)}
                    />
                  </label>
                  <small>
                    <code>{"{data_path}"}</code> 会替换为所选远端数据路径；系统也会设置
                    <code> DATA_PATH</code> 环境变量。
                  </small>
                </div>
                <button
                  type="button"
                  className="assets-confirm-action code-import-action"
                  onClick={importCode}
                  disabled={
                    busyArea !== "" ||
                    !selectedCode ||
                    !selectedSshProfileId ||
                    Boolean(preparation?.code_ready)
                  }
                >
                  {busyArea === "code" ? (
                    <LoadingOutlined />
                  ) : (
                    <CodeOutlined />
                  )}
                  {busyArea === "code"
                    ? "正在导入并建立 Git 基线…"
                    : preparation?.code_ready
                      ? "训练代码已导入"
                      : "导入这份训练代码"}
                </button>
              </div>
            </div>

            <section className="assets-optional-model">
              <div>
                <small>OPTIONAL / LATER ITERATIONS</small>
                <strong>后续需要 AI 诊断时，可选一个模型配置</strong>
              </div>
              <select
                value={selectedAiProfileId}
                onChange={(event) => void selectOptionalModel(event.target.value)}
                disabled={busyArea !== ""}
              >
                <option value="">暂不选择</option>
                {llmProfiles.map((profile) => (
                  <option value={profile.id} key={profile.id}>
                    {profile.name} · {String(profile.public_config.model)}
                  </option>
                ))}
              </select>
            </section>

            <section className="assets-start-gate">
              <div>
                <small>DIRECT RUN GATE</small>
                <h2>
                  {preparation?.ready_to_start
                    ? "服务器、数据与代码均已就绪"
                    : "完成三项资产确认后即可启动"}
                </h2>
                <p>
                  {preparation?.ready_to_start
                    ? `${preparation.code?.entrypoint ?? entrypoint} 将作为训练入口。`
                    : preparation?.missing.join(" · ")}
                </p>
              </div>
              <button
                type="button"
                className="assets-primary-action"
                onClick={startExperiment}
                disabled={busyArea !== "" || !preparation?.ready_to_start}
              >
                {busyArea === "launch" ? (
                  <LoadingOutlined />
                ) : (
                  <RocketOutlined />
                )}
                直接启动实验
              </button>
            </section>
          </>
        )}

        {phase === 2 && (
          <section className="assets-launched">
            <RocketOutlined />
            <small>EXPERIMENT QUEUED</small>
            <h2>现有训练基线已经进入远端执行队列</h2>
            <p>
              实验分支已建立。接下来可以查看实时日志、指标、代码版本和后续迭代。
            </p>
            <div>
              <Link
                className="assets-primary-action"
                to={`/projects/${projectId}/tree`}
              >
                打开实验谱系
              </Link>
              <Link
                className="assets-secondary-action"
                to={`/experiments/${experimentId}`}
              >
                查看本次实验
              </Link>
            </div>
          </section>
        )}
      </section>
    </main>
  );
}
