import {
  ArrowRightOutlined,
  CodeOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
} from "@ant-design/icons";
import { Link } from "react-router-dom";
import "./ProjectStart.css";

export default function ProjectStartPage() {
  return (
    <main className="project-start-page">
      <header className="project-start-intro">
        <span>CHOOSE A STARTING PROTOCOL</span>
        <h1>你的实验从哪里开始？</h1>
        <p>
          论文复现会完成分析、问答和代码生成；已有资产可以直接接入服务器上的训练代码与数据。
        </p>
      </header>

      <section className="protocol-choice-grid" aria-label="项目启动方式">
        <Link className="protocol-choice paper-protocol" to="/projects/new/from-paper">
          <div className="protocol-choice-index">
            <FilePdfOutlined />
            <span>8 GATES</span>
          </div>
          <div>
            <small>SOP / PAPER REPRODUCTION</small>
            <h2>从论文开始</h2>
            <p>上传论文，调用大模型分析方法，定义目标并生成可审核的训练框架。</p>
          </div>
          <ol>
            <li>论文分析与研究问答</li>
            <li>远端数据和服务器准备</li>
            <li>AI 生成、审核并启动代码</li>
          </ol>
          <strong>
            进入论文复现流程
            <ArrowRightOutlined />
          </strong>
        </Link>

        <Link
          className="protocol-choice assets-protocol"
          to="/projects/new/from-assets"
        >
          <div className="protocol-choice-index">
            <CodeOutlined />
            <span>3 GATES</span>
          </div>
          <div>
            <small>SOP / EXISTING ASSETS</small>
            <h2>已有代码与数据</h2>
            <p>跳过论文分析和框架生成，把服务器上的现有训练目录导入为实验基线。</p>
          </div>
          <ol>
            <li>选择已验证的 SSH 服务器</li>
            <li>锁定数据并导入训练代码</li>
            <li>核对入口参数后直接启动</li>
          </ol>
          <strong>
            进入快捷启动流程
            <ArrowRightOutlined />
          </strong>
        </Link>
      </section>

      <footer className="project-start-footnote">
        <ExperimentOutlined />
        <span>
          两种流程都会建立 Git 基线并保留实验分支、日志、指标和后续迭代记录。
        </span>
      </footer>
    </main>
  );
}
