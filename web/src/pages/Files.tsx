import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { api, type FileEntry } from '../api/client';

export default function Files() {
  const { boxId } = useParams<{ boxId: string }>();
  const [currentPath, setCurrentPath] = useState('');
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileName, setFileName] = useState('');
  const [showContent, setShowContent] = useState(false);

  const fetchFiles = useCallback(async () => {
    if (!boxId) return;
    setLoading(true);
    try {
      const data = await api.listFiles(boxId, currentPath);
      setFiles(data);
    } catch {
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, [boxId, currentPath]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const navigateTo = (path: string) => {
    setCurrentPath(path);
    setShowContent(false);
    setFileContent(null);
  };

  const goUp = () => {
    const parts = currentPath.split('/').filter(Boolean);
    parts.pop();
    navigateTo(parts.join('/'));
  };

  const handleFileClick = async (file: FileEntry) => {
    if (file.type === 'dir') {
      navigateTo(file.path);
    } else {
      // Read file content
      if (!boxId) return;
      try {
        const res = await fetch(
          `/api/v1/boxes/${boxId}/files/content?path=${encodeURIComponent(file.path)}`,
          {
            headers: {
              Authorization: `Bearer ${sessionStorage.getItem('agentpost_token')}`,
            },
          },
        );
        if (res.ok) {
          const text = await res.text();
          setFileContent(text);
          setFileName(file.name);
          setShowContent(true);
        }
      } catch {
        // ignore
      }
    }
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (ts?: number) => {
    if (!ts) return '-';
    return new Date(ts * 1000).toLocaleString('zh-CN');
  };

  // Quick nav shortcuts
  const shortcuts = [
    { label: '根目录', path: '' },
    { label: 'data/', path: 'data' },
    { label: 'reference/', path: 'reference' },
    { label: 'memory/', path: 'memory' },
    { label: 'skills/', path: 'skills' },
    { label: 'logs/', path: 'logs' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">文件浏览 - {boxId}</h1>
      </div>

      {/* Quick nav */}
      <div className="flex gap-2 flex-wrap">
        {shortcuts.map((s) => (
          <button
            key={s.path}
            onClick={() => navigateTo(s.path)}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              currentPath === s.path
                ? 'bg-brand-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Breadcrumb */}
      <div className="bg-white rounded-lg shadow px-4 py-2 flex items-center gap-1 text-sm">
        <button
          onClick={() => navigateTo('')}
          className="text-brand-600 hover:text-brand-800"
        >
          📦 {boxId}
        </button>
        {currentPath &&
          currentPath.split('/').map((part, i, arr) => (
            <span key={i} className="flex items-center gap-1">
              <span className="text-gray-400">/</span>
              <button
                onClick={() => navigateTo(arr.slice(0, i + 1).join('/'))}
                className={`${
                  i === arr.length - 1
                    ? 'text-gray-900 font-medium'
                    : 'text-brand-600 hover:text-brand-800'
                }`}
              >
                {part}
              </button>
            </span>
          ))}
      </div>

      {/* File list */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-5 py-3 text-left">名称</th>
                <th className="px-5 py-3 text-left">类型</th>
                <th className="px-5 py-3 text-right">大小</th>
                <th className="px-5 py-3 text-left">修改时间</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {/* Parent directory */}
              {currentPath && (
                <tr
                  onClick={goUp}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-5 py-3 text-brand-600">.. (上级目录)</td>
                  <td className="px-5 py-3 text-gray-400">-</td>
                  <td className="px-5 py-3 text-right text-gray-400">-</td>
                  <td className="px-5 py-3 text-gray-400">-</td>
                </tr>
              )}
              {files.map((file) => (
                <tr
                  key={file.path}
                  onClick={() => handleFileClick(file)}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-5 py-3">
                    <span className="flex items-center gap-2">
                      <span>{file.type === 'dir' ? '📁' : '📄'}</span>
                      <span className={file.type === 'dir' ? 'font-medium text-brand-700' : 'text-gray-900'}>
                        {file.name}
                      </span>
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-500">
                    {file.type === 'dir' ? '目录' : '文件'}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-500 font-mono text-xs">
                    {file.type === 'file' ? formatSize(file.size) : '-'}
                  </td>
                  <td className="px-5 py-3 text-gray-500 text-xs">
                    {file.type === 'file' ? formatDate(file.modified) : '-'}
                  </td>
                </tr>
              ))}
              {files.length === 0 && !currentPath && (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-gray-400">
                    目录为空
                  </td>
                </tr>
              )}
              {files.length === 0 && currentPath && (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-gray-400">
                    此目录为空
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* File content viewer */}
      {showContent && fileContent !== null && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-700">📄 {fileName}</h3>
            <button
              onClick={() => setShowContent(false)}
              className="text-gray-400 hover:text-gray-600 text-sm"
            >
              ✕ 关闭
            </button>
          </div>
          <pre className="p-5 text-sm font-mono text-gray-800 overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto bg-gray-50">
            {fileContent}
          </pre>
        </div>
      )}
    </div>
  );
}
