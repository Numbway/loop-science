import {
  CheckOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  LoadingOutlined,
  MessageOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  type DialogResult,
  type GeneratedFile,
  type PaperUploadResult,
  type ProjectConfig,
  getWizardError,
  projectWizardApi,
} from "../services/projectWizard";
import "./ProjectWizard.css";

const protocolSteps = [
  { label: "论文入库", note: "PDF 解析", icon: FilePdfOutlined },
  { label: "研究问答", note: "一次一问", icon: MessageOutlined },
  { label: "配置核验", note: "目标与边界", icon: SafetyCertificateOutlined },
  { label: "框架生成", note: "AI 构建", icon: LoadingOutlined },
  { label: "代码审核", note: "逐文件确认", icon: CodeOutlined },
  { label: "启动实验", note: "进入队列", icon: RocketOutlined },
];

const generationStages = [
  "读取论文方法与实验章节",
  "构建数据、模型和训练模块",
  "加入 TensorBoard 与沙箱入口",
  "执行语法检查并整理文件",
];

interface DialogTurn {
  role: "assistant" | "user";
  content: string;
}

export default function ProjectWizardPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(0);
  const [projectName, setProjectName] = useState("");
  const [paperFile, setPaperFile] = useState<File | null>(null);
  const [paper, setPaper] = useState<PaperUploadResult | null>(null);
  const [dialog, setDialog] = useState<DialogResult | null>(null);
  const [turns, setTurns] = useState<DialogTurn[]>([]);
  const [textAnswer, setTextAnswer] = useState("");
  const [selectedAnswers, setSelectedAnswers] = useState<string[]>([]);
  const [config, setConfig] = useState<ProjectConfig | null>(null);
  const [files, setFiles] = useState<GeneratedFile[]>([]);
  const [activeFile, setActiveFile] = useState("");
  const [generationLog, setGenerationLog] = useState<string[]>([]);
  const [experimentId, setExperimentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  const currentFile = useMemo(
    () => files.find((item) => item.path === activeFile),
    [activeFile, files],
  );

  const chooseFile = (file?: File) => {
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
    if (!projectName) {
      setProjectName(file.name.replace(/\.pdf$/i, ""));
    }
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
      const firstQuestion = await projectWizardApi.startDialog(
        uploaded.project_id,
      );
      setPaper(uploaded);
      setDialog(firstQuestion);
      setTurns([
        {
          role: "assistant",
          content: firstQuestion.question ?? "先说说你的研究目标。",
        },
      ]);
      setStep(1);
    } catch (uploadError) {
      setError(getWizardError(uploadError));
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
        setStep(2);
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
    setBusy(true);
    setError("");
    try {
      const firstQuestion = await projectWizardApi.startDialog(
        paper.project_id,
      );
      setDialog(firstQuestion);
      setTurns([
        {
          role: "assistant",
          content: firstQuestion.question ?? "先说说你的研究目标。",
        },
      ]);
      setConfig(null);
      setTextAnswer("");
      setSelectedAnswers([]);
      setStep(1);
    } catch (restartError) {
      setError(getWizardError(restartError));
    } finally {
      setBusy(false);
    }
  };

  const generateCode = async () => {
    if (!paper) return;
    setStep(3);
    setBusy(true);
    setError("");
    setGenerationLog([generationStages[0]]);
    let stageIndex = 1;
    const interval = window.setInterval(() => {
      if (stageIndex < generationStages.length) {
        const stage = generationStages[stageIndex];
        setGenerationLog((current) => [...current, stage]);
        stageIndex += 1;
      }
    }, 900);
    try {
      const generated = await projectWizardApi.generateCode(paper.project_id);
      setFiles(generated.files);
      setActiveFile(generated.files[0]?.path ?? "");
      setGenerationLog((current) => [
        ...current,
        `完成：${generated.files.length} 个文件已进入审核区`,
      ]);
      setStep(4);
    } catch (generationError) {
      setError(getWizardError(generationError));
    } finally {
      window.clearInterval(interval);
      setBusy(false);
    }
  };

  const updateActiveFile = (content: string) => {
    setFiles((current) =>
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
      await projectWizardApi.saveCode(paper.project_id, files);
      setStep(5);
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

  return (
    <div className="wizard-page">
      <aside className="protocol-rail" aria-label="项目创建进度">
        <div className="protocol-heading">
          <span>PROTOCOL</span>
          <strong>M14 / PROJECT SETUP</strong>
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
                  <small>0{index + 1}</small>
                  <strong>{item.label}</strong>
                  <em>{item.note}</em>
                </span>
              </li>
            );
          })}
        </ol>
        <div className="rail-note">
          <ExperimentOutlined />
          <span>每一步都会写入同一个可追溯项目。</span>
        </div>
      </aside>

      <main className="wizard-workbench">
        <header className="wizard-header">
          <div>
            <p className="eyebrow">Research onboarding · 研究项目初始化</p>
            <h1>把论文整理成一份可运行的实验协议</h1>
          </div>
          <span className="step-counter">
            <b>{String(step + 1).padStart(2, "0")}</b> / 06
          </span>
        </header>

        {error && (
          <div className="wizard-error" role="alert">
            <strong>当前步骤未完成</strong>
            <span>{error}</span>
            <button
              type="button"
              onClick={() => setError("")}
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        )}

        {step === 0 && (
          <section className="wizard-panel upload-step">
            <div className="section-intro">
              <span className="section-code">INPUT / 论文原件</span>
              <h2>先确认研究对象</h2>
              <p>
                系统会在本地解析标题、摘要与关键词，原始 PDF
                不会被训练容器修改。
              </p>
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
                chooseFile(event.dataTransfer.files[0]);
              }}
            >
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(event) => chooseFile(event.target.files?.[0])}
              />
              <span className="dropzone-icon">
                {paperFile ? <FilePdfOutlined /> : <CloudUploadOutlined />}
              </span>
              {paperFile ? (
                <>
                  <strong>{paperFile.name}</strong>
                  <span>
                    {(paperFile.size / 1024 / 1024).toFixed(2)} MB · 已就绪
                  </span>
                </>
              ) : (
                <>
                  <strong>将论文拖到实验台</strong>
                  <span>或点击选择 PDF，最大 25 MB</span>
                </>
              )}
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
                {busy ? <LoadingOutlined /> : <span>解析论文并开始问答</span>}
              </button>
            </div>
          </section>
        )}

        {step === 1 && dialog && (
          <section className="dialog-grid">
            <div className="conversation-ledger">
              <div className="panel-label">对话记录 · {turns.length} 条</div>
              <div className="turn-list">
                {turns.map((turn, index) => (
                  <article
                    key={`${turn.role}-${index}`}
                    className={`turn ${turn.role}`}
                  >
                    <span>{turn.role === "assistant" ? "AI" : "YOU"}</span>
                    <p>{turn.content}</p>
                  </article>
                ))}
              </div>
            </div>
            <div className="question-station">
              <span className="section-code">
                QUESTION / 一次只解决一个变量
              </span>
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

        {step === 2 && config && paper && (
          <section className="wizard-panel review-config-step">
            <div className="section-intro">
              <span className="section-code">CHECKPOINT / 配置冻结前</span>
              <h2>核对这次实验的边界</h2>
              <p>这些参数会进入代码生成提示和后续自动迭代判断。</p>
            </div>
            <div className="config-sheet">
              <div className="config-paper">
                <small>研究对象</small>
                <strong>{paper.paper_title}</strong>
                <p>{paper.abstract || "PDF 中未识别到摘要。"}</p>
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
                    {Object.entries(config.target_metrics).map(
                      ([name, value]) => (
                        <span key={name}>
                          {name} ≥ {value}
                        </span>
                      ),
                    )}
                  </dd>
                </div>
                <div>
                  <dt>迭代上限</dt>
                  <dd className="iteration-value">
                    {config.max_iterations} 轮
                  </dd>
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
                onClick={generateCode}
              >
                确认配置并生成框架
              </button>
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="wizard-panel generation-step">
            <div className="generation-orbit" aria-hidden="true">
              <span />
              <CodeOutlined />
            </div>
            <div>
              <span className="section-code">BUILD / AI CODE AGENT</span>
              <h2>正在搭建可审核的实验框架</h2>
              <p>生成结果会先停在审核区，不会直接进入实验队列。</p>
              <ul className="generation-log">
                {generationLog.map((entry, index) => (
                  <li key={entry}>
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

        {step === 4 && (
          <section className="code-review">
            <div className="file-index">
              <div className="panel-label">生成文件 · {files.length}</div>
              {files.map((file) => (
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
                <span>保存会创建一条独立 Git 提交，保留 AI 初稿。</span>
                <button
                  className="primary-action"
                  type="button"
                  onClick={saveReviewedCode}
                  disabled={busy || files.length === 0}
                >
                  {busy ? <LoadingOutlined /> : "保存审核结果"}
                </button>
              </div>
            </div>
          </section>
        )}

        {step === 5 && paper && (
          <section className="wizard-panel launch-step">
            {experimentId ? (
              <div className="launch-success">
                <span className="success-seal">
                  <CheckOutlined />
                </span>
                <span className="section-code">QUEUED / 实验协议已生效</span>
                <h2>第一条实验分支已进入队列</h2>
                <p>
                  容器将从 <code>exp/1</code> 分支运行，日志与指标由 M13
                  监控服务持续写回。
                </p>
                <dl>
                  <div>
                    <dt>项目</dt>
                    <dd>{paper.project_name}</dd>
                  </div>
                  <div>
                    <dt>实验 ID</dt>
                    <dd>{experimentId}</dd>
                  </div>
                </dl>
                <Link className="primary-action link-action" to="/">
                  返回项目入口
                </Link>
              </div>
            ) : (
              <>
                <div className="section-intro">
                  <span className="section-code">LAUNCH / 最后确认</span>
                  <h2>项目已具备运行条件</h2>
                  <p>启动后会创建首个实验分支并交给 Celery 队列执行。</p>
                </div>
                <div className="launch-manifest">
                  <div>
                    <small>项目</small>
                    <strong>{paper.project_name}</strong>
                  </div>
                  <div>
                    <small>代码</small>
                    <strong>{files.length} 个已审核文件</strong>
                  </div>
                  <div>
                    <small>隔离策略</small>
                    <strong>无网络 · 代码只读</strong>
                  </div>
                </div>
                <div className="panel-actions">
                  <button
                    className="quiet-action"
                    type="button"
                    onClick={() => setStep(4)}
                  >
                    返回代码审核
                  </button>
                  <button
                    className="launch-action"
                    type="button"
                    onClick={startExperiment}
                    disabled={busy}
                  >
                    {busy ? <LoadingOutlined /> : <RocketOutlined />}
                    启动第一次实验
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
