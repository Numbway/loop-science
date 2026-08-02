import {
  AppstoreOutlined,
  ExperimentOutlined,
  LogoutOutlined,
  PlusOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { lazy, Suspense } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import "./App.css";

const LoginPage = lazy(() => import("./pages/Login"));
const ProjectDashboardPage = lazy(() => import("./pages/ProjectDashboard"));
const ProjectStartPage = lazy(() => import("./pages/ProjectStart"));
const ProjectWizardPage = lazy(() => import("./pages/ProjectWizard"));
const ExistingAssetsWizardPage = lazy(
  () => import("./pages/ExistingAssetsWizard"),
);
const ExperimentTreePage = lazy(() => import("./pages/ExperimentTree"));
const ExperimentDetailPage = lazy(() => import("./pages/ExperimentDetail"));
const SystemConfigurationsPage = lazy(
  () => import("./pages/SystemConfigurations"),
);
const ProjectConnectionsPage = lazy(
  () => import("./pages/ProjectConnections"),
);

function App() {
  const { token, user, logout } = useAuthStore();

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="brand-lockup" to="/">
          <span className="brand-mark">
            <ExperimentOutlined />
          </span>
          <span>
            <strong>科研分身</strong>
            <small>RESEARCH COMPANION</small>
          </span>
        </Link>
        <nav aria-label="主导航">
          {token ? (
            <>
              <span className="user-chip">{user?.name ?? "研究者"}</span>
              <Link className="header-utility" to="/projects">
                <AppstoreOutlined />
                <span>实验管理</span>
              </Link>
              <Link className="header-action" to="/projects/new">
                <PlusOutlined />
                <span>新建项目</span>
              </Link>
              <Link className="header-utility" to="/settings/connections">
                <SettingOutlined />
                <span>系统配置</span>
              </Link>
              <button className="logout-action" type="button" onClick={logout}>
                <LogoutOutlined />
                <span>退出</span>
              </button>
            </>
          ) : (
            <Link className="header-action" to="/login">
              登录
            </Link>
          )}
        </nav>
      </header>
      <Suspense
        fallback={
          <div className="route-loading">
            <ExperimentOutlined />
            <span>正在打开研究工作区…</span>
          </div>
        }
      >
        <Routes>
          <Route
            path="/"
            element={
              token ? (
                <ProjectDashboardPage />
              ) : (
                <WelcomePage authenticated={false} />
              )
            }
          />
          <Route
            path="/projects"
            element={
              token ? <ProjectDashboardPage /> : <Navigate to="/login" replace />
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/projects/new"
            element={
              token ? <ProjectStartPage /> : <Navigate to="/login" replace />
            }
          />
          <Route
            path="/projects/new/from-paper"
            element={
              token ? <ProjectWizardPage /> : <Navigate to="/login" replace />
            }
          />
          <Route
            path="/projects/new/from-assets"
            element={
              token ? (
                <ExistingAssetsWizardPage />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/projects/:projectId/continue"
            element={
              token ? (
                <ExistingAssetsWizardPage />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/projects/:projectId/continue-paper"
            element={
              token ? <ProjectWizardPage /> : <Navigate to="/login" replace />
            }
          />
          <Route
            path="/projects/:projectId/tree"
            element={
              token ? <ExperimentTreePage /> : <Navigate to="/login" replace />
            }
          />
          <Route
            path="/settings/connections"
            element={
              token ? (
                <SystemConfigurationsPage />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/projects/:projectId/connections"
            element={
              token ? (
                <ProjectConnectionsPage />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route
            path="/experiments/:experimentId"
            element={
              token ? (
                <ExperimentDetailPage />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </div>
  );
}

function WelcomePage({ authenticated }: { authenticated: boolean }) {
  return (
    <main className="welcome-page">
      <div className="welcome-copy">
        <p className="welcome-kicker">PAPER → CODE → EXPERIMENT</p>
        <h1>
          把论文复现，
          <br />
          变成一条看得见的实验路径。
        </h1>
        <p>
          从论文解析到代码审核，再到隔离训练与指标监控。每一次选择、修改和结果都保留在项目分支中。
        </p>
        <Link
          className="welcome-cta"
          to={authenticated ? "/projects/new" : "/login"}
        >
          {authenticated ? "创建一个研究项目" : "登录并开始"}
          <span>→</span>
        </Link>
      </div>
      <div className="welcome-instrument" aria-label="科研流程示意">
        <span className="instrument-label">ACTIVE PROTOCOL</span>
        <div className="instrument-core">
          <ExperimentOutlined />
          <b>06</b>
          <small>可追溯步骤</small>
        </div>
        <ol>
          <li>
            <span>01</span> 解析研究对象
          </li>
          <li>
            <span>02</span> 冻结实验配置
          </li>
          <li>
            <span>03</span> 审核并启动代码
          </li>
        </ol>
      </div>
    </main>
  );
}

export default App;
