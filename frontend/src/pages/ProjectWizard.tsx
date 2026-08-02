import {
  ApiOutlined,
  CheckOutlined,
  CloudServerOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileOutlined,
  FilePdfOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  LoadingOutlined,
  MessageOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  type DialogResult,
  type GeneratedFile,
  type PaperAnalysis,
  type PaperUploadResult,
  type PreparationStatus,
  type ProjectConfig,
  type RemoteDataEntry,
  type RemoteDataListing,
  getWizardError,
  projectWizardApi,
} from "../services/projectWizard";
import {
  type CredentialProfile,
  systemConfigurationsApi,
} from "../services/systemConfigurations";
import "./ProjectWizard.css";

const protocolSteps = [
  { label: "论文入库", note: "PDF 原件", icon: FilePdfOutlined },
  { label: "论文分析", note: "真实大模型", icon: ApiOutlined },
  { label: "研究问答", note: "一次一问", icon: MessageOutlined },
  { label: "目标核验", note: "范围与指标", icon: SafetyCertificateOutlined },
  { label: "实验准备", note: "数据与服务器", icon: CloudServerOutlined },
  { label: "框架生成", note: "AI 构建", icon: LoadingOutlined },
  { label: "代码审核", note: "逐文件确认", icon: CodeOutlined },
  { label: "启动实验", note: "远端执行", icon: RocketOutlined },
];

const generationStages = [
  "读取论文结构化分析与实验章节",
  "核对真实数据清单与远端运行能力",
  "构建数据、模型和训练模块",
  "执行语法检查并整理审核文件",
];

interface DialogTurn {
  role: "assistant" | "user";
  content: string;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}

export default function ProjectWizardPage() {
  const { projectId: resumeProjectId = "" } = useParams();
  const paperInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(resumeProjectId ? 1 : 0);
  const [projectName, setProjectName] = useState("");
  const [paperFile, setPaperFile] = useState<File | null>(null);
  const [paper, setPaper] = useState<PaperUploadResult | null>(null);
  const [profiles, setProfiles] = useState<CredentialProfile[]>([]);
  const [selectedAiProfileId, setSelectedAiProfileId] = useState("");
  const [selectedSshProfileId, setSelectedSshProfileId] = useState("");
  const [analysis, setAnalysis] = useState<PaperAnalysis | null>(null);
  const [dialog, setDialog] = useState<DialogResult | null>(null);
  const [turns, setTurns] = useState<DialogTurn[]>([]);
  const [textAnswer, setTextAnswer] = useState("");
  const [selectedAnswers, setSelectedAnswers] = useState<string[]>([]);
  const [config, setConfig] = useState<ProjectConfig | null>(null);
  const [generatedFiles, setGeneratedFiles] = useState<GeneratedFile[]>([]);
  const [activeFile, setActiveFile] = useState("");
  const [generationLog, setGenerationLog] = useState<string[]>([]);
  const [generationSeconds, setGenerationSeconds] = useState(0);
  const [preparation, setPreparation] = useState<PreparationStatus | null>(null);
  const [remoteData, setRemoteData] = useState<RemoteDataListing | null>(null);
  const [selectedRemoteData, setSelectedRemoteData] =
    useState<RemoteDataEntry | null>(null);
  const [experimentId, setExperimentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyArea, setBusyArea] = useState<"data" | "ssh" | "">("");
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  const currentFile = useMemo(
    () => generatedFiles.find((item) => item.path === activeFile),
    [activeFile, generatedFiles],
  );
  const llmProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "llm"),
    [profiles],
  );
  const sshProfiles = useMemo(
    () => profiles.filter((profile) => profile.kind === "ssh"),
    [profiles],
  );

  const loadProfiles = async () => {
    const available = await systemConfigurationsApi.list();
    setProfiles(available);
    return available;
  };

  useEffect(() => {
    if (!resumeProjectId) return;
    let active = true;
    const resume = async () => {
      setBusy(true);
      setError("");
      try {
        const [snapshot, available] = await Promise.all([
          projectWizardApi.getSnapshot(resumeProjectId),
          systemConfigurationsApi.list(),
        ]);
        if (!active) return;
        setProfiles(available);
        setPaper({
          project_id: snapshot.project_id,
          project_name: snapshot.project_name,
          paper_title: snapshot.paper_title,
          abstract: snapshot.abstract,
          authors: snapshot.authors,
          keywords: snapshot.keywords,
        });
        setProjectName(snapshot.project_name);
        setAnalysis(snapshot.analysis);
        setPreparation(snapshot.preparation);
        setSelectedAiProfileId(snapshot.preparation.ai_profile_id ?? "");
        setSelectedSshProfileId(snapshot.preparation.ssh_profile_id ?? "");
        setConfig(snapshot.config);
        setGeneratedFiles(snapshot.files);
        setActiveFile(snapshot.files[0]?.path ?? "");
        if (snapshot.files.length) {
          setStep(6);
        } else if (snapshot.dialog_complete) {
          setStep(4);
        } else {
          setStep(1);
        }
        if (snapshot.preparation.ssh_profile_id) {
          try {
            setRemoteData(
              await projectWizardApi.browseRemoteData(resumeProjectId),
            );
          } catch {
            // The saved project remains resumable even if SSH is temporarily
            // unavailable; the preparation screen can retry the browser.
          }
        }
      } catch (resumeError) {
        if (active) setError(getWizardError(resumeError));
      } finally {
        if (active) setBusy(false);
      }
    };
    void resume();
    return () => {
      active = false;
    };
  }, [resumeProjectId]);

  const choosePaper = (file?: File) => {
    if (!file) return;
    setError("");
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件。");
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setError("PDF 不能超过 25 MB。");
      return;
    }
    setPaperFile(file);
    if (!projectName) setProjectName(file.name.replace(/\.pdf$/i, ""));
  };

  const uploadPaper = async () => {
    if (!paperFile) {
      setError("先选择需要复现的论文 PDF。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const uploaded = await projectWizardApi.uploadPaper(
        paperFile,
        projectName,
      );
      const available = await loadProfiles();
      setPaper(uploaded);
      const firstLlm = available.find((profile) => profile.kind === "llm");
      setSelectedAiProfileId(firstLlm?.id ?? "");
      setStep(1);
    } catch (uploadError) {
      setError(getWizardError(uploadError));
    } finally {
      setBusy(false);
    }
  };

  const analyzePaper = async () => {
    if (!paper) return;
    if (!selectedAiProfileId) {
      setError("请先在系统配置中录入并选择一个大模型配置。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setPreparation(
        await projectWizardApi.selectConfigurations(paper.project_id, {
          ai_profile_id: selectedAiProfileId,
        }),
      );
      const result = await projectWizardApi.analyzePaper(paper.project_id);
      setAnalysis(result);
      setPreparation(await projectWizardApi.getPreparation(paper.project_id));
    } catch (analysisError) {
      setError(getWizardError(analysisError));
    } finally {
      setBusy(false);
    }
  };

  const beginDialog = async () => {
    if (!paper || !analysis) return;
    setBusy(true);
    setError("");
    try {
      const firstQuestion = await projectWizardApi.startDialog(paper.project_id);
      setDialog(firstQuestion);
      setTurns([
        {
          role: "assistant",
          content: firstQuestion.question ?? "先说说你的研究目标。",
        },
      ]);
      setStep(2);
    } catch (dialogError) {
      setError(getWizardError(dialogError));
    } finally {
      setBusy(false);
    }
  };

  const toggleAnswer = (option: string) => {
    if (dialog?.input_type === "single") {
      setSelectedAnswers([option]);
      return;
    }
    setSelectedAnswers((current) =>
      current.includes(option)
        ? current.filter((item) => item !== option)
        : [...current, option],
    );
  };

  const answerQuestion = async () => {
    if (!paper || !dialog) return;
    const answer =
      dialog.input_type === "text"
        ? textAnswer.trim()
        : selectedAnswers.join("、");
    if (!answer) {
      setError("回答当前问题后再继续。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const next = await projectWizardApi.answerDialog(
        paper.project_id,
        dialog.session_id,
        answer,
      );
      setDialog(next);
      setTextAnswer("");
      setSelectedAnswers([]);
      if (next.complete && next.config) {
        setTurns((current) => [...current, { role: "user", content: answer }]);
        setConfig(next.config);
        setStep(3);
      } else {
        setTurns((current) => [
          ...current,
          { role: "user", content: answer },
          {
            role: "assistant",
            content: next.question ?? "请继续补充。",
          },
        ]);
      }
    } catch (answerError) {
      setError(getWizardError(answerError));
    } finally {
      setBusy(false);
    }
  };

  const restartDialog = async () => {
    if (!paper) return;
    setConfig(null);
    await beginDialog();
  };

  const enterPreparation = async () => {
    if (!paper) return;
    setBusy(true);
    setError("");
    try {
      const available = await loadProfiles();
      const firstSsh = available.find((profile) => profile.kind === "ssh");
      const status = await projectWizardApi.getPreparation(paper.project_id);
      const sshProfileId = status.ssh_profile_id ?? firstSsh?.id ?? "";
      setSelectedSshProfileId(sshProfileId);
      setPreparation(status);
      if (status.ssh_profile_id) {
        setRemoteData(
          await projectWizardApi.browseRemoteData(paper.project_id),
        );
      }
      setStep(4);
    } catch (statusError) {
      setError(getWizardError(statusError));
    } finally {
      setBusy(false);
    }
  };

  const browseRemoteData = async (path?: string) => {
    if (!paper || !selectedSshProfileId) {
      setError("请先选择 SSH 训练服务器。");
      return;
    }
    setBusyArea("data");
    setError("");
    try {
      setRemoteData(
        await projectWizardApi.browseRemoteData(
          paper.project_id,
          path,
        ),
      );
      setSelectedRemoteData(null);
    } catch (dataError) {
      setError(getWizardError(dataError));
    } finally {
      setBusyArea("");
    }
  };

  const confirmRemoteData = async (entry: RemoteDataEntry) => {
    if (!paper) return;
    setBusyArea("data");
    setError("");
    try {
      await projectWizardApi.selectRemoteData(paper.project_id, {
        path: entry.path,
        kind: entry.kind,
      });
      setSelectedRemoteData(entry);
      setPreparation(await projectWizardApi.getPreparation(paper.project_id));
    } catch (dataError) {
      setError(getWizardError(dataError));
    } finally {
      setBusyArea("");
    }
  };

  const selectSshProfile = async (profileId: string) => {
    if (!paper) return;
    setBusyArea("ssh");
    setError("");
    try {
      setSelectedSshProfileId(profileId);
      const status = await projectWizardApi.selectConfigurations(
        paper.project_id,
        {
          ssh_profile_id: profileId,
        },
      );
      setPreparation(status);
      setSelectedRemoteData(null);
      setRemoteData(
        await projectWizardApi.browseRemoteData(paper.project_id),
      );
    } catch (sshError) {
      setError(getWizardError(sshError));
    } finally {
      setBusyArea("");
    }
  };

  const generateCode = async () => {
    if (!paper || !preparation?.ready_to_generate) return;
    setStep(5);
    setBusy(true);
    setError("");
    setGenerationLog([generationStages[0]]);
    setGenerationSeconds(0);
    let stageIndex = 1;
    const stageInterval = window.setInterval(() => {
      if (stageIndex < generationStages.length) {
        setGenerationLog((current) => [
          ...current,
          generationStages[stageIndex],
        ]);
        stageIndex += 1;
      }
    }, 20_000);
    const clockInterval = window.setInterval(() => {
      setGenerationSeconds((current) => current + 1);
    }, 1_000);
    try {
      const generated = await projectWizardApi.generateCode(paper.project_id);
      setGeneratedFiles(generated.files);
      setActiveFile(generated.files[0]?.path ?? "");
      setGenerationLog((current) => [
        ...current,
        `完成：${generated.files.length} 个文件已进入审核区`,
      ]);
      setStep(6);
    } catch (generationError) {
      setError(getWizardError(generationError));
    } finally {
      window.clearInterval(stageInterval);
      window.clearInterval(clockInterval);
      setBusy(false);
    }
  };

  const updateActiveFile = (content: string) => {
    setGeneratedFiles((current) =>
      current.map((item) =>
        item.path === activeFile ? { ...item, content } : item,
      ),
    );
  };

  const saveReviewedCode = async () => {
    if (!paper) return;
    setBusy(true);
    setError("");
    try {
      await projectWizardApi.saveCode(paper.project_id, generatedFiles);
      setPreparation(await projectWizardApi.getPreparation(paper.project_id));
      setStep(7);
    } catch (saveError) {
      setError(getWizardError(saveError));
    } finally {
      setBusy(false);
    }
  };

  const startExperiment = async () => {
    if (!paper) return;
    setBusy(true);
    setError("");
    try {
      const started = await projectWizardApi.startExperiment(paper.project_id);
      setExperimentId(started.experiment_id);
    } catch (startError) {
      setError(getWizardError(startError));
    } finally {
      setBusy(false);
    }
  };

  if (resumeProjectId && !paper) {
    return (
      <div className="route-loading">
        {busy ? <LoadingOutlined /> : <ExperimentOutlined />}
        <strong>{busy ? "正在恢复项目进度…" : "项目暂时无法恢复"}</strong>
        {error && <span>{error}</span>}
        {!busy && <Link to="/projects">返回实验管理</Link>}
      </div>
    );
  }

  return (
    <div className="wizard-page">
      <aside className="protocol-rail" aria-label="项目创建进度">
        <div className="protocol-heading">
          <span>REPRODUCTION PROTOCOL</span>
          <strong>PROJECT READINESS / 8 GATES</strong>
        </div>
        <ol>
          {protocolSteps.map((item, index) => {
            const Icon = item.icon;
            const state =
              index < step ? "complete" : index === step ? "active" : "pending";
            return (
              <li key={item.label} className={`protocol-step ${state}`}>
                <span className="protocol-node">
                  {state === "complete" ? <CheckOutlined /> : <Icon />}
                </span>
                <span>
                  <small>{String(index + 1).padStart(2, "0")}</small>
                  <strong>{item.label}</strong>
                  <em>{item.note}</em>
                </span>
              </li>
            );
          })}
        </ol>
        <div className="rail-note">
          <ExperimentOutlined />
          <span>论文、数据、机器和代码全部就绪后，实验才允许启动。</span>
        </div>
      </aside>

      <main className="wizard-workbench">
        <header className="wizard-header">
          <div>
            <p className="eyebrow">Research onboarding · 实验准备工作台</p>
            <h1>把论文变成一份有数据、有机器的实验协议</h1>
          </div>
          <span className="step-counter">
            <b>{String(step + 1).padStart(2, "0")}</b> / 08
          </span>
        </header>

        {error && (
          <div className="wizard-error" role="alert">
            <strong>当前步骤未完成</strong>
            <span>{error}</span>
            <button type="button" onClick={() => setError("")} aria-label="关闭">
              ×
            </button>
          </div>
        )}

        {step === 0 && (
          <section className="wizard-panel upload-step">
            <div className="section-intro">
              <span className="section-code">INPUT / 论文原件</span>
              <h2>先确认研究对象</h2>
              <p>上传后先进行文本解析，下一步必须调用真实大模型完成方法分析。</p>
            </div>
            <label
              className={`paper-dropzone ${dragging ? "dragging" : ""} ${
                paperFile ? "has-file" : ""
              }`}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                choosePaper(event.dataTransfer.files[0]);
              }}
            >
              <input
                ref={paperInputRef}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => choosePaper(event.target.files?.[0])}
              />
              <span className="dropzone-icon">
                {paperFile ? <FilePdfOutlined /> : <CloudUploadOutlined />}
              </span>
              <strong>{paperFile?.name ?? "将论文拖到实验台"}</strong>
              <span>
                {paperFile
                  ? `${(paperFile.size / 1024 / 1024).toFixed(2)} MB · 已就绪`
                  : "或点击选择 PDF，最大 25 MB"}
              </span>
            </label>
            <div className="project-name-field">
              <label htmlFor="project-name">项目名称</label>
              <input
                id="project-name"
                value={projectName}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="例如：Adaptive Vision 复现实验"
                maxLength={200}
              />
              <small>用于区分实验项目，稍后仍可修改。</small>
            </div>
            <div className="panel-actions">
              <span>支持文本型学术 PDF；扫描件需要先完成 OCR。</span>
              <button
                className="primary-action"
                type="button"
                onClick={uploadPaper}
                disabled={busy || !paperFile}
              >
                {busy ? <LoadingOutlined /> : "上传并解析论文"}
              </button>
            </div>
          </section>
        )}

        {step === 1 && paper && (
          <section className="wizard-panel analysis-step">
            <div className="section-intro">
              <span className="section-code">ANALYZE / 大模型精读</span>
              <h2>先读懂论文，再讨论实验</h2>
              <p>
                从系统配置选择大模型连接；项目只记录配置引用，不复制 API Key。
              </p>
            </div>
            {!analysis ? (
              <div className="analysis-console">
                <div className="profile-picker">
                  <small>选择大模型配置</small>
                  {llmProfiles.length ? (
                    <div className="profile-options">
                      {llmProfiles.map((profile) => (
                        <button
                          type="button"
                          key={profile.id}
                          className={
                            selectedAiProfileId === profile.id ? "selected" : ""
                          }
                          onClick={() => setSelectedAiProfileId(profile.id)}
                        >
                          <ApiOutlined />
                          <span>
                            <strong>{profile.name}</strong>
                            <em>
                              {profile.public_config.provider ===
                              "openai_compatible"
                                ? "OpenAI-compatible"
                                : "Anthropic"}{" "}
                              · {String(profile.public_config.model)} ·{" "}
                              {String(
                                profile.public_config.base_url ??
                                  "https://api.anthropic.com",
                              )}
                            </em>
                          </span>
                          {selectedAiProfileId === profile.id && <CheckOutlined />}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="configuration-empty">
                      <span>系统中还没有大模型配置。</span>
                      <Link to="/settings/connections">前往系统配置录入</Link>
                    </div>
                  )}
                </div>
                <button
                  className="primary-action analysis-action"
                  type="button"
                  onClick={analyzePaper}
                  disabled={busy || !selectedAiProfileId}
                >
                  {busy ? <LoadingOutlined /> : <ApiOutlined />}
                  {busy ? "正在调用大模型分析…" : "使用所选配置分析论文"}
                </button>
              </div>
            ) : (
              <>
                <div className="paper-analysis-board">
                  <article className="analysis-lead">
                    <small>研究问题</small>
                    <h3>{analysis.research_problem}</h3>
                    <p>{analysis.summary}</p>
                    <em>分析模型 · {analysis.model}</em>
                  </article>
                  <AnalysisList title="方法步骤" items={analysis.method_steps} />
                  <AnalysisList title="论文数据" items={analysis.datasets} />
                  <AnalysisList title="评估指标" items={analysis.metrics} />
                  <AnalysisList
                    title="计算需求"
                    items={analysis.compute_requirements}
                  />
                  <AnalysisList
                    title="复现风险"
                    items={analysis.reproducibility_risks}
                    warning
                  />
                </div>
                <div className="panel-actions">
                  <span>确认分析内容后，再让模型询问你的改进目标。</span>
                  <button
                    className="primary-action"
                    type="button"
                    onClick={beginDialog}
                    disabled={busy}
                  >
                    进入研究问答
                  </button>
                </div>
              </>
            )}
          </section>
        )}

        {step === 2 && dialog && (
          <section className="dialog-grid">
            <div className="conversation-ledger">
              <div className="panel-label">对话记录 · {turns.length} 条</div>
              <div className="turn-list">
                {turns.map((turn, index) => (
                  <article key={`${turn.role}-${index}`} className={`turn ${turn.role}`}>
                    <span>{turn.role === "assistant" ? "AI" : "YOU"}</span>
                    <p>{turn.content}</p>
                  </article>
                ))}
              </div>
            </div>
            <div className="question-station">
              <span className="section-code">QUESTION / 一次只解决一个变量</span>
              <h2>{dialog.question}</h2>
              {dialog.input_type === "text" ? (
                <textarea
                  value={textAnswer}
                  onChange={(event) => setTextAnswer(event.target.value)}
                  placeholder="写下你的判断、限制或预期……"
                  rows={6}
                  autoFocus
                />
              ) : (
                <div className="answer-options">
                  {dialog.options.map((option) => (
                    <button
                      type="button"
                      key={option}
                      className={
                        selectedAnswers.includes(option) ? "selected" : ""
                      }
                      onClick={() => toggleAnswer(option)}
                    >
                      <span className="option-marker" />
                      {option}
                    </button>
                  ))}
                </div>
              )}
              <div className="panel-actions">
                <span>回答会用于生成训练配置与代码说明。</span>
                <button
                  className="primary-action"
                  type="button"
                  onClick={answerQuestion}
                  disabled={busy}
                >
                  {busy ? <LoadingOutlined /> : "记录回答并继续"}
                </button>
              </div>
            </div>
          </section>
        )}

        {step === 3 && config && paper && (
          <section className="wizard-panel review-config-step">
            <div className="section-intro">
              <span className="section-code">CHECKPOINT / 目标冻结前</span>
              <h2>核对这次实验的边界</h2>
              <p>这些参数会进入代码生成提示和后续自动迭代判断。</p>
            </div>
            <div className="config-sheet">
              <div className="config-paper">
                <small>研究对象</small>
                <strong>{paper.paper_title}</strong>
                <p>{analysis?.summary || paper.abstract}</p>
              </div>
              <dl>
                <div>
                  <dt>改进方向</dt>
                  <dd>
                    {config.improvement_targets.map((target) => (
                      <span key={target}>{target}</span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt>目标指标</dt>
                  <dd className="metric-value">
                    {Object.entries(config.target_metrics).map(([name, value]) => (
                      <span key={name}>
                        {name} ≥ {value}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt>迭代上限</dt>
                  <dd className="iteration-value">{config.max_iterations} 轮</dd>
                </div>
                <div>
                  <dt>研究约束摘要</dt>
                  <dd>{config.summary || "采用默认复现约束。"}</dd>
                </div>
              </dl>
            </div>
            <div className="panel-actions">
              <button
                className="quiet-action"
                type="button"
                onClick={restartDialog}
                disabled={busy}
              >
                重新进行问答
              </button>
              <button
                className="primary-action"
                type="button"
                onClick={enterPreparation}
                disabled={busy}
              >
                确认目标，准备数据和机器
              </button>
            </div>
          </section>
        )}

        {step === 4 && paper && (
          <section className="preparation-grid">
            <div className={`readiness-card ${preparation?.execution_ready ? "ready" : ""}`}>
              <div className="readiness-heading">
                <span className="readiness-icon"><CloudServerOutlined /></span>
                <div>
                  <small>REMOTE MACHINE</small>
                  <h2>验证 SSH 实验服务器</h2>
                </div>
                {preparation?.execution_ready && <CheckOutlined />}
              </div>
              <p>选择系统中已验证的服务器配置；凭据不会复制到当前项目。</p>
              <div className="profile-options server-profile-options">
                {sshProfiles.map((profile) => (
                  <button
                    type="button"
                    key={profile.id}
                    className={
                      selectedSshProfileId === profile.id ? "selected" : ""
                    }
                    onClick={() => selectSshProfile(profile.id)}
                    disabled={busyArea !== ""}
                  >
                    {busyArea === "ssh" &&
                    selectedSshProfileId === profile.id ? (
                      <LoadingOutlined />
                    ) : (
                      <CloudServerOutlined />
                    )}
                    <span>
                      <strong>{profile.name}</strong>
                      <em>
                        {String(profile.public_config.username)}@
                        {String(profile.public_config.host)}:
                        {String(profile.public_config.port)}
                      </em>
                    </span>
                    {preparation?.ssh_profile_id === profile.id && (
                      <CheckOutlined />
                    )}
                  </button>
                ))}
                {!sshProfiles.length && (
                  <div className="configuration-empty">
                    <span>系统中还没有已验证的 SSH 配置。</span>
                    <Link to="/settings/connections">前往系统配置录入</Link>
                  </div>
                )}
              </div>
              {preparation?.execution && (
                <div className="server-proof">
                  <strong>
                    {preparation.execution.username}@{preparation.execution.host}
                  </strong>
                  <span>{String(preparation.execution.capabilities.python)}</span>
                  <span>{String(preparation.execution.capabilities.gpu)}</span>
                  <code>{preparation.execution.host_key_fingerprint}</code>
                </div>
              )}
              <Link className="quiet-action config-center-link" to="/settings/connections">
                管理系统连接配置
              </Link>
            </div>

            <div className={`readiness-card remote-data-card ${preparation?.data_ready ? "ready" : ""}`}>
              <div className="readiness-heading">
                <span className="readiness-icon"><DatabaseOutlined /></span>
                <div>
                  <small>REMOTE DATA INPUT</small>
                  <h2>从服务器选择数据</h2>
                </div>
                {preparation?.data_ready && <CheckOutlined />}
              </div>
              <p>浏览所选 SSH 账号可访问的目录，只能点击选择一个已有文件或文件夹。</p>
              {!preparation?.execution_ready ? (
                <div className="remote-browser-locked">
                  <CloudServerOutlined />
                  <span>先在左侧选择训练服务器，随后才能读取远端目录。</span>
                </div>
              ) : remoteData ? (
                <>
                  <div className="remote-browser-toolbar">
                    <code title={remoteData.current_path}>
                      {remoteData.current_path}
                    </code>
                    {remoteData.parent_path && (
                      <button
                        type="button"
                        onClick={() =>
                          browseRemoteData(remoteData.parent_path ?? undefined)
                        }
                        disabled={busyArea !== ""}
                      >
                        返回上级
                      </button>
                    )}
                  </div>
                  <div className="remote-data-list">
                    <div
                      className={`remote-data-row ${
                        selectedRemoteData?.path === remoteData.current_path
                          ? "selected"
                          : ""
                      }`}
                    >
                      <button
                        type="button"
                        className="remote-data-entry"
                        onClick={() =>
                          setSelectedRemoteData({
                            name:
                              remoteData.current_path
                                .split("/")
                                .filter(Boolean)
                                .pop() ?? "/",
                            path: remoteData.current_path,
                            kind: "folder",
                            size: 0,
                          })
                        }
                      >
                        <FolderOpenOutlined />
                        <span>
                          <strong>选择当前文件夹</strong>
                          <small>{remoteData.current_path}</small>
                        </span>
                      </button>
                    </div>
                    {remoteData.entries.map((entry) => (
                      <div
                        key={entry.path}
                        className={`remote-data-row ${
                          selectedRemoteData?.path === entry.path
                            ? "selected"
                            : ""
                        }`}
                      >
                        <button
                          type="button"
                          className="remote-data-entry"
                          onClick={() => setSelectedRemoteData(entry)}
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
                            className="remote-open-folder"
                            onClick={() => browseRemoteData(entry.path)}
                            disabled={busyArea !== ""}
                          >
                            进入
                          </button>
                        )}
                      </div>
                    ))}
                    {!remoteData.entries.length && (
                      <div className="remote-data-empty">
                        当前目录为空，可以选择当前文件夹。
                      </div>
                    )}
                  </div>
                  {remoteData.truncated && (
                    <span className="remote-data-warning">
                      当前目录仅显示前 500 项，请进入更具体的子目录。
                    </span>
                  )}
                </>
              ) : (
                <button
                  type="button"
                  className="quiet-action remote-load-action"
                  onClick={() => browseRemoteData()}
                  disabled={busyArea !== ""}
                >
                  {busyArea === "data" ? <LoadingOutlined /> : <FolderOpenOutlined />}
                  浏览服务器数据
                </button>
              )}
              <div className="selection-manifest remote-selection-manifest">
                {selectedRemoteData ? (
                  <>
                    <strong>{selectedRemoteData.name}</strong>
                    <span>{selectedRemoteData.path}</span>
                  </>
                ) : preparation?.data ? (
                  <>
                    <strong>{preparation.data.selected_name}</strong>
                    <span>{preparation.data.path} · 已锁定远端引用</span>
                  </>
                ) : (
                  <span>尚未选择远端数据</span>
                )}
              </div>
              <button
                className="primary-action card-action"
                type="button"
                onClick={() =>
                  selectedRemoteData &&
                  void confirmRemoteData(selectedRemoteData)
                }
                disabled={busyArea !== "" || !selectedRemoteData}
              >
                {busyArea === "data" ? <LoadingOutlined /> : <CheckOutlined />}
                {busyArea === "data" ? "正在验证远端数据…" : "确认使用所选数据"}
              </button>
            </div>

            <div className="readiness-gate">
              <div>
                <small>START GATE</small>
                <strong>
                  {preparation?.ready_to_generate
                    ? "数据与服务器均已就绪"
                    : "还不能生成实验代码"}
                </strong>
                <span>
                  {preparation?.ready_to_generate
                    ? "代码生成将使用论文分析、数据清单和服务器能力。"
                    : preparation?.missing
                        .filter((item) => !item.includes("代码"))
                        .join(" · ")}
                </span>
              </div>
              <button
                className="launch-action"
                type="button"
                onClick={generateCode}
                disabled={!preparation?.ready_to_generate}
              >
                生成适配该环境的代码
              </button>
            </div>
          </section>
        )}

        {step === 5 && (
          <section className="wizard-panel generation-step">
            <div className="generation-orbit" aria-hidden="true">
              <span />
              <CodeOutlined />
            </div>
            <div>
              <span className="section-code">BUILD / AI CODE AGENT</span>
              <h2>正在搭建可审核的真实实验框架</h2>
              <p>
                生成结果会先停在审核区，不会直接进入远端服务器。多轮模型调用可能超过
                3 分钟，页面会保持等待，不再在 180 秒时中断。
              </p>
              {busy && (
                <div className="generation-duration" aria-live="polite">
                  <strong>
                    {String(Math.floor(generationSeconds / 60)).padStart(2, "0")}:
                    {String(generationSeconds % 60).padStart(2, "0")}
                  </strong>
                  <span>连接保持中 · 可以继续等待</span>
                </div>
              )}
              <ul className="generation-log">
                {generationLog.map((entry, index) => (
                  <li key={`${entry}-${index}`}>
                    {index === generationLog.length - 1 && busy ? (
                      <LoadingOutlined />
                    ) : (
                      <CheckOutlined />
                    )}
                    {entry}
                  </li>
                ))}
              </ul>
              {!busy && error && (
                <button
                  className="quiet-action generation-retry"
                  type="button"
                  onClick={generateCode}
                >
                  重新生成
                </button>
              )}
            </div>
          </section>
        )}

        {step === 6 && (
          <section className="code-review">
            <div className="file-index">
              <div className="panel-label">生成文件 · {generatedFiles.length}</div>
              {generatedFiles.map((file) => (
                <button
                  type="button"
                  key={file.path}
                  className={file.path === activeFile ? "active" : ""}
                  onClick={() => setActiveFile(file.path)}
                >
                  <CodeOutlined />
                  <span>{file.path}</span>
                  <small>{file.language}</small>
                </button>
              ))}
            </div>
            <div className="editor-station">
              <div className="editor-toolbar">
                <span>{currentFile?.path}</span>
                <em>可编辑 · UTF-8</em>
              </div>
              <textarea
                aria-label={`编辑 ${currentFile?.path ?? "代码文件"}`}
                className="code-editor"
                value={currentFile?.content ?? ""}
                onChange={(event) => updateActiveFile(event.target.value)}
                spellCheck={false}
              />
              <div className="panel-actions">
                <span>保存会创建独立 Git 提交；数据和凭据不会写入代码仓库。</span>
                <button
                  className="primary-action"
                  type="button"
                  onClick={saveReviewedCode}
                  disabled={busy || generatedFiles.length === 0}
                >
                  {busy ? <LoadingOutlined /> : "保存审核结果"}
                </button>
              </div>
            </div>
          </section>
        )}

        {step === 7 && paper && (
          <section className="wizard-panel launch-step">
            {experimentId ? (
              <div className="launch-success">
                <span className="success-seal"><CheckOutlined /></span>
                <span className="section-code">QUEUED / 远端实验已排队</span>
                <h2>第一条实验分支已进入执行队列</h2>
                <p>工作节点会通过已验证的 SSH 连接上传代码，直接读取服务器上的所选数据，并持续回传日志。</p>
                <dl>
                  <div><dt>项目</dt><dd>{paper.project_name}</dd></div>
                  <div><dt>实验 ID</dt><dd>{experimentId}</dd></div>
                </dl>
                <Link className="primary-action link-action" to={`/projects/${paper.project_id}/tree`}>
                  查看实验树
                </Link>
              </div>
            ) : (
              <>
                <div className="section-intro">
                  <span className="section-code">LAUNCH / 最后确认</span>
                  <h2>所有启动条件都已有证据</h2>
                  <p>启动后才会创建实验分支、连接服务器并上传代码；所选数据保留在原路径，不会重复传输。</p>
                </div>
                <div className="launch-manifest">
                  <div>
                    <small>真实数据</small>
                    <strong>{preparation?.data?.selected_name}</strong>
                  </div>
                  <div>
                    <small>远端机器</small>
                    <strong>
                      {preparation?.execution?.username}@
                      {preparation?.execution?.host}
                    </strong>
                  </div>
                  <div>
                    <small>审核代码</small>
                    <strong>{generatedFiles.length} 个文件</strong>
                  </div>
                </div>
                <div className="panel-actions">
                  <button className="quiet-action" type="button" onClick={() => setStep(6)}>
                    返回代码审核
                  </button>
                  <button
                    className="launch-action"
                    type="button"
                    onClick={startExperiment}
                    disabled={busy || !preparation?.ready_to_start}
                  >
                    {busy ? <LoadingOutlined /> : <RocketOutlined />}
                    通过 SSH 启动第一次实验
                  </button>
                </div>
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

function AnalysisList({
  title,
  items,
  warning = false,
}: {
  title: string;
  items: string[];
  warning?: boolean;
}) {
  return (
    <article className={`analysis-list ${warning ? "warning" : ""}`}>
      <small>{title}</small>
      <ul>
        {(items.length ? items : ["论文未明确说明"]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </article>
  );
}
