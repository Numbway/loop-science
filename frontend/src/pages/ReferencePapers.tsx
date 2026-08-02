import { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Input,
  Space,
  Tag,
  message,
  Modal,
  Upload,
  Tabs,
  Typography,
  Popconfirm,
} from 'antd';
import {
  SearchOutlined,
  PlusOutlined,
  UploadOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import api from '../services/api';
import type { ReferencePaper, PaperMetadata } from '../types';

const { Title } = Typography;

interface PaperLibraryProps {
  projectId: string;
}

export default function ReferencePapersPage({ projectId }: PaperLibraryProps) {
  const [papers, setPapers] = useState<ReferencePaper[]>([]);
  const [searchResults, setSearchResults] = useState<PaperMetadata[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadPaperId, setUploadPaperId] = useState<string>('');
  const [messageApi, contextHolder] = message.useMessage();

  // Load papers on mount
  const loadPapers = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/projects/${projectId}/papers`);
      setPapers(res.data.items);
    } catch {
      messageApi.error('加载论文列表失败');
    } finally {
      setLoading(false);
    }
  };

  // Search externally
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setLoading(true);
    try {
      const res = await api.post(`/api/projects/${projectId}/papers/search`, {
        query: searchQuery,
        max_results: 10,
      });
      setSearchResults(res.data.items);
    } catch {
      messageApi.error('搜索失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  // Add paper to library
  const handleAddPaper = async (metadata: PaperMetadata) => {
    try {
      await api.post(`/api/projects/${projectId}/papers`, {
        metadata,
        source: 'ai_recommended',
      });
      messageApi.success(`已添加: ${metadata.title}`);
      await loadPapers();
    } catch {
      messageApi.error('添加失败');
    }
  };

  // Delete paper
  const handleDelete = async (paperId: string) => {
    try {
      await api.delete(`/api/papers/${paperId}`);
      messageApi.success('已删除');
      await loadPapers();
    } catch {
      messageApi.error('删除失败');
    }
  };

  // Upload paper PDF
  const handleUpload = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    try {
      await api.post(`/api/papers/${uploadPaperId}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      messageApi.success('上传成功');
      setUploadModalOpen(false);
      await loadPapers();
    } catch {
      messageApi.error('上传失败');
    }
    return false; // Prevent default upload behavior
  };

  const paperColumns: ColumnsType<ReferencePaper> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      width: 300,
    },
    {
      title: '作者',
      dataIndex: 'authors',
      key: 'authors',
      width: 200,
      render: (authors: string[]) => authors?.slice(0, 3).join(', ') || '-',
    },
    {
      title: '年份',
      dataIndex: 'year',
      key: 'year',
      width: 70,
    },
    {
      title: '关键词',
      dataIndex: 'keywords',
      key: 'keywords',
      width: 200,
      render: (keywords: string[]) =>
        keywords?.map((kw) => <Tag key={kw}>{kw}</Tag>) || null,
    },
    {
      title: '状态',
      dataIndex: 'download_status',
      key: 'download_status',
      width: 100,
      render: (status: string) => {
        const colors: Record<string, string> = {
          success: 'green',
          failed: 'red',
          pending: 'orange',
        };
        const labels: Record<string, string> = {
          success: '已下载',
          failed: '下载失败',
          pending: '待下载',
        };
        return <Tag color={colors[status] || 'default'}>{labels[status] || status}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space>
          {record.download_status === 'failed' && (
            <Button
              size="small"
              icon={<UploadOutlined />}
              onClick={() => {
                setUploadPaperId(record.id);
                setUploadModalOpen(true);
              }}
            >
              上传
            </Button>
          )}
          <Popconfirm
            title="确定删除这篇论文？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const searchColumns: ColumnsType<PaperMetadata> = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      width: 300,
    },
    {
      title: '作者',
      dataIndex: 'authors',
      key: 'authors',
      width: 200,
      render: (authors: string[]) => authors?.slice(0, 3).join(', ') || '-',
    },
    {
      title: '年份',
      dataIndex: 'year',
      key: 'year',
      width: 70,
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={() => handleAddPaper(record)}
        >
          添加
        </Button>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'library',
      label: '论文库',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Button type="primary" onClick={loadPapers} loading={loading}>
              刷新列表
            </Button>
          </div>
          <Table
            columns={paperColumns}
            dataSource={papers}
            rowKey="id"
            loading={loading}
            size="middle"
            pagination={{ pageSize: 20 }}
          />
        </>
      ),
    },
    {
      key: 'search',
      label: '搜索 arXiv',
      children: (
        <>
          <div style={{ marginBottom: 16 }}>
            <Space>
              <Input
                placeholder="输入关键词搜索 arXiv..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onPressEnter={handleSearch}
                style={{ width: 400 }}
                prefix={<SearchOutlined />}
              />
              <Button type="primary" onClick={handleSearch} loading={loading}>
                搜索
              </Button>
            </Space>
          </div>
          <Table
            columns={searchColumns}
            dataSource={searchResults}
            rowKey="arxiv_id"
            loading={loading}
            size="middle"
            pagination={false}
          />
        </>
      ),
    },
  ];

  return (
    <Card>
      {contextHolder}
      <Title level={4}>📚 参考论文库</Title>
      <Tabs defaultActiveKey="library" items={tabItems} />
      <Modal
        title="手动上传 PDF"
        open={uploadModalOpen}
        onCancel={() => setUploadModalOpen(false)}
        footer={null}
      >
        <Upload.Dragger
          accept=".pdf"
          beforeUpload={handleUpload}
          maxCount={1}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          </p>
          <p>点击或拖拽 PDF 文件到此处上传</p>
        </Upload.Dragger>
      </Modal>
    </Card>
  );
}