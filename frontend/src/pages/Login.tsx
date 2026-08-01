import { LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Form, Input, Tabs, message } from "antd";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import "./Login.css";

interface LoginFormData {
  email: string;
  password: string;
}

interface RegisterFormData {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
}

export default function LoginPage() {
  const [activeTab, setActiveTab] = useState("login");
  const { login, register, isLoading, token } = useAuthStore();
  const navigate = useNavigate();
  const [messageApi, contextHolder] = message.useMessage();

  if (token) {
    return <Navigate to="/projects/new" replace />;
  }

  const handleLogin = async (values: LoginFormData) => {
    try {
      await login(values);
      messageApi.success("已登录");
      navigate("/projects/new");
    } catch {
      messageApi.error("邮箱或密码不正确。");
    }
  };

  const handleRegister = async (values: RegisterFormData) => {
    if (values.password !== values.confirmPassword) {
      messageApi.error("两次输入的密码不一致。");
      return;
    }
    try {
      await register({
        name: values.name,
        email: values.email,
        password: values.password,
      });
      messageApi.success("账号已创建");
      navigate("/projects/new");
    } catch {
      messageApi.error("账号未创建，请检查邮箱后重试。");
    }
  };

  const items = [
    {
      key: "login",
      label: "登录",
      children: (
        <Form onFinish={handleLogin} layout="vertical" size="large">
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: "请输入邮箱。" },
              { type: "email", message: "邮箱格式不正确。" },
            ]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="researcher@example.com"
            />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "请输入密码。" }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={isLoading} block>
            登录并继续
          </Button>
        </Form>
      ),
    },
    {
      key: "register",
      label: "创建账号",
      children: (
        <Form onFinish={handleRegister} layout="vertical" size="large">
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: "请输入姓名。" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="研究者姓名" />
          </Form.Item>
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: "请输入邮箱。" },
              { type: "email", message: "邮箱格式不正确。" },
            ]}
          >
            <Input
              prefix={<MailOutlined />}
              placeholder="researcher@example.com"
            />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: "请输入密码。" },
              { min: 6, message: "密码至少需要 6 位。" },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="至少 6 位" />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            label="确认密码"
            dependencies={["password"]}
            rules={[
              { required: true, message: "请再次输入密码。" },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue("password") === value
                    ? Promise.resolve()
                    : Promise.reject(new Error("两次输入的密码不一致。"));
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="再次输入密码"
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={isLoading} block>
            创建账号并继续
          </Button>
        </Form>
      ),
    },
  ];

  return (
    <main className="login-page">
      {contextHolder}
      <section className="login-context">
        <span>ACCESS / RESEARCH WORKSPACE</span>
        <h1>实验需要可追溯，账号只负责确认“是谁”。</h1>
        <p>论文、代码、分支与运行结果都会归入你的研究项目。</p>
      </section>
      <section className="login-panel">
        <div className="login-panel-heading">
          <small>科研分身</small>
          <h2>进入实验工作区</h2>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={items}
          animated={false}
        />
      </section>
    </main>
  );
}
