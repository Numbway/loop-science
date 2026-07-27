import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from 'antd';
import LoginPage from './pages/Login';
import './App.css';

const { Header, Content, Footer } = Layout;

function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          background: '#001529',
        }}
      >
        <h1 style={{ color: '#fff', margin: 0, fontSize: 20 }}>
          🧪 科研分身
        </h1>
      </Header>
      <Content style={{ padding: '24px 50px' }}>
        <Routes>
          <Route path="/" element={<WelcomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Content>
      <Footer style={{ textAlign: 'center' }}>
        Research Companion ©2026 - AI-Powered Research Assistant
      </Footer>
    </Layout>
  );
}

function WelcomePage() {
  return (
    <div style={{ textAlign: 'center', paddingTop: 80 }}>
      <h1>欢迎使用科研分身 👋</h1>
      <p style={{ fontSize: 18, color: '#666', marginTop: 16 }}>
        你的 AI 科研助手，帮你复现论文、改进实验、自动迭代
      </p>
      <div style={{ marginTop: 40 }}>
        <a href="/login" style={{ fontSize: 16 }}>
          开始使用 →
        </a>
      </div>
    </div>
  );
}

export default App;