import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  BranchesOutlined,
  CheckOutlined,
  CloseOutlined,
  ExperimentOutlined,
  LoadingOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import type {
  BranchBudget,
  BranchFocus,
  BranchPlan,
  ExperimentTreeNode,
} from "../../services/experimentTree";
import "./BranchDialog.css";

interface BranchDialogProps {
  parent: ExperimentTreeNode;
  creating: boolean;
  error: string;
  onClose: () => void;
  onCreate: (plan: BranchPlan) => void;
}

const focusOptions: Array<{
  value: BranchFocus;
  code: string;
  label: string;
  detail: string;
}> = [
  {
    value: "model",
    code: "ARCH",
    label: "模型结构",
    detail: "调整层、模块、连接或容量",
  },
  {
    value: "data",
    code: "DATA",
    label: "数据与增强",
    detail: "改变预处理、采样或增强方案",
  },
  {
    value: "training",
    code: "OPT",
    label: "训练策略",
    detail: "调整优化器、学习率或调度",
  },
  {
    value: "regularization",
    code: "REG",
    label: "正则化",
    detail: "抑制过拟合并改善泛化",
  },
];

const budgetOptions: Array<{
  value: BranchBudget;
  code: string;
  label: string;
  detail: string;
}> = [
  {
    value: "quick",
    code: "S",
    label: "快速验证",
    detail: "先用较短训练确认方向",
  },
  {
    value: "balanced",
    code: "M",
    label: "平衡",
    detail: "在速度与可信度之间取中值",
  },
  {
    value: "thorough",
    code: "L",
    label: "充分训练",
    detail: "使用完整预算评估最终效果",
  },
];

const stepLabels = ["改进对象", "具体方案", "验证预算"];

export default function BranchDialog({
  parent,
  creating,
  error,
  onClose,
  onCreate,
}: BranchDialogProps) {
  const [step, setStep] = useState(0);
  const [focus, setFocus] = useState<BranchFocus | null>(null);
  const [approach, setApproach] = useState("");
  const [budget, setBudget] = useState<BranchBudget | null>(null);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !creating) onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [creating, onClose]);

  const canContinue = useMemo(() => {
    if (step === 0) return focus !== null;
    if (step === 1) return approach.trim().length >= 8;
    return budget !== null;
  }, [approach, budget, focus, step]);

  const createBranch = () => {
    if (!focus || !budget || approach.trim().length < 8) return;
    onCreate({ focus, approach: approach.trim(), budget });
  };

  return (
    <div className="branch-dialog-backdrop" onMouseDown={onClose}>
      <section
        className="branch-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="branch-dialog-header">
          <div>
            <span>BRANCH PROPOSAL / 分支提案</span>
            <h2 id="branch-dialog-title">从节点 {parent.node_id} 延伸实验</h2>
          </div>
          <button
            type="button"
            aria-label="关闭分支对话框"
            onClick={onClose}
            disabled={creating}
          >
            <CloseOutlined />
          </button>
        </header>

        <div className="branch-graft-line" aria-hidden="true">
          <span>{parent.git_branch}</span>
          <i />
          <strong>NEW EXPERIMENT</strong>
        </div>

        <div className="branch-dialog-body">
          <ol className="branch-step-rail" aria-label="分支规划进度">
            {stepLabels.map((label, index) => (
              <li
                key={label}
                className={
                  index < step ? "done" : index === step ? "active" : ""
                }
              >
                <span>{index < step ? <CheckOutlined /> : index + 1}</span>
                <div>
                  <small>DECISION {index + 1}</small>
                  <strong>{label}</strong>
                </div>
              </li>
            ))}
          </ol>

          <div className="branch-question">
            <span className="question-index">0{step + 1} / 03</span>

            {step === 0 && (
              <>
                <h3>这次实验主要改变什么？</h3>
                <p>只选择一个主要变量，让结果更容易归因。</p>
                <div className="branch-choice-grid">
                  {focusOptions.map((option, index) => (
                    <button
                      key={option.value}
                      type="button"
                      className={focus === option.value ? "selected" : ""}
                      onClick={() => setFocus(option.value)}
                      autoFocus={index === 0}
                    >
                      <span>{option.code}</span>
                      <strong>{option.label}</strong>
                      <small>{option.detail}</small>
                      <i>{focus === option.value && <CheckOutlined />}</i>
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <h3>描述你准备验证的具体方案</h3>
                <p>写清修改动作；它会成为新节点的实验说明。</p>
                <label className="branch-approach-field">
                  <span>实验假设</span>
                  <textarea
                    value={approach}
                    onChange={(event) => setApproach(event.target.value)}
                    placeholder="例如：使用余弦退火学习率，并加入 5 个 epoch 的 warmup"
                    maxLength={600}
                    rows={6}
                    autoFocus
                  />
                  <small>{approach.trim().length} / 600 · 至少 8 个字符</small>
                </label>
              </>
            )}

            {step === 2 && (
              <>
                <h3>为这条分支选择验证预算</h3>
                <p>预算作为实验计划保存，不会在此阶段立即启动训练。</p>
                <div className="budget-choice-list">
                  {budgetOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={budget === option.value ? "selected" : ""}
                      onClick={() => setBudget(option.value)}
                    >
                      <span>{option.code}</span>
                      <div>
                        <strong>{option.label}</strong>
                        <small>{option.detail}</small>
                      </div>
                      <i>{budget === option.value && <CheckOutlined />}</i>
                    </button>
                  ))}
                </div>
                <div className="branch-plan-summary">
                  <ExperimentOutlined />
                  <span>
                    <small>待创建分支</small>
                    <strong>
                      {focusOptions.find((option) => option.value === focus)
                        ?.label ?? "未选择"}{" "}
                      · {approach || "未填写方案"}
                    </strong>
                  </span>
                </div>
              </>
            )}

            {error && (
              <div className="branch-dialog-error" role="alert">
                <BranchesOutlined />
                <span>
                  <strong>分支未创建</strong>
                  {error}
                </span>
              </div>
            )}
          </div>
        </div>

        <footer className="branch-dialog-footer">
          <button
            type="button"
            className="branch-back"
            onClick={() => setStep((current) => current - 1)}
            disabled={step === 0 || creating}
          >
            <ArrowLeftOutlined />
            上一步
          </button>
          <span>
            父节点 <code>{parent.node_id}</code> 保持不变
          </span>
          {step < 2 ? (
            <button
              type="button"
              className="branch-next"
              onClick={() => setStep((current) => current + 1)}
              disabled={!canContinue}
            >
              下一问
              <ArrowRightOutlined />
            </button>
          ) : (
            <button
              type="button"
              className="branch-create"
              onClick={createBranch}
              disabled={!canContinue || creating}
            >
              {creating ? <LoadingOutlined spin /> : <BranchesOutlined />}
              {creating ? "正在创建" : "创建 Git 分支"}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}
