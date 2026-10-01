import { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api, type BoxListItem, type RegisterBoxResponse } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';
import { StatusDot } from './Ops';

export default function Boxes() {
  const [boxes, setBoxes] = useState<BoxListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newToken, setNewToken] = useState<RegisterBoxResponse | null>(null);

  const fetchBoxes = useCallback(async () => {
    try {
      const data = await api.listBoxes();
      setBoxes(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBoxes();
  }, [fetchBoxes]);

  useWebSocket({
    onEvent: (event) => {
      if (event.type.startsWith('box.') || event.type.startsWith('mail.')) {
        fetchBoxes();
      }
    },
  });

  const handleRegistered = (result: RegisterBoxResponse) => {
    setNewToken(result);
    setShowForm(false);
    fetchBoxes();
  };

  const copyToken = () => {
    if (newToken) {
      navigator.clipboard.writeText(newToken.token);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">盒子管理</h1>
        <button
          onClick={() => { setShowForm(true); setNewToken(null); }}
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          + 注册新盒子
        </button>
      </div>

      {/* New token modal */}
      {newToken && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">🎉 盒子注册成功</h2>

            <div className="space-y-3 mb-6">
              <div>
                <label className="text-sm text-gray-500">地址</label>
                <p className="font-mono text-brand-700">{newToken.address}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500">盒子根目录</label>
                <p className="font-mono text-sm text-gray-700">{newToken.box_root}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500">
                  访问令牌 <span className="text-red-600 font-medium">（仅显示一次！）</span>
                </label>
                <div className="flex gap-2">
                  <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono break-all select-all">
                    {newToken.token}
                  </code>
                  <button
                    onClick={copyToken}
                    className="px-3 py-2 bg-brand-600 text-white text-sm rounded hover:bg-brand-700 transition-colors shrink-0"
                  >
                    复制
                  </button>
                </div>
                <p className="text-xs text-red-500 mt-1">
                  ⚠️ 请立即保存此令牌，关闭后将无法再次查看！
                </p>
              </div>
            </div>

            <button
              onClick={() => setNewToken(null)}
              className="w-full py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition-colors"
            >
              我已保存，关闭
            </button>
          </div>
        </div>
      )}

      {/* Register form */}
      {showForm && !newToken && (
        <RegisterForm
          onSuccess={handleRegistered}
          onCancel={() => setShowForm(false)}
        />
      )}

      {/* Box list */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-5 py-3 text-left">状态</th>
                <th className="px-5 py-3 text-left">ID</th>
                <th className="px-5 py-3 text-left">地址</th>
                <th className="px-5 py-3 text-left">显示名</th>
                <th className="px-5 py-3 text-left">能力</th>
                <th className="px-5 py-3 text-right">未读</th>
                <th className="px-5 py-3 text-right">已发</th>
                <th className="px-5 py-3 text-right">失败</th>
                <th className="px-5 py-3 text-center">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {boxes.map((box) => (
                <tr key={box.id} className="hover:bg-gray-50">
                  <td className="px-5 py-3">
                    <StatusDot status={box.status} />
                  </td>
                  <td className="px-5 py-3 font-mono text-gray-900">{box.id}</td>
                  <td className="px-5 py-3 text-gray-600 text-xs font-mono">{box.address}</td>
                  <td className="px-5 py-3 text-gray-700">{box.display_name || '-'}</td>
                  <td className="px-5 py-3">
                    <div className="flex gap-1 flex-wrap">
                      {box.capabilities.slice(0, 3).map((cap) => (
                        <span
                          key={cap}
                          className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                        >
                          {cap}
                        </span>
                      ))}
                      {box.capabilities.length > 3 && (
                        <span className="text-xs text-gray-400">+{box.capabilities.length - 3}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right font-mono">
                    {box.unread > 0 ? (
                      <span className="text-orange-600 font-medium">{box.unread}</span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-gray-500">{box.sent}</td>
                  <td className="px-5 py-3 text-right font-mono">
                    {box.failed > 0 ? (
                      <span className="text-red-600">{box.failed}</span>
                    ) : (
                      '0'
                    )}
                  </td>
                  <td className="px-5 py-3 text-center">
                    <Link
                      to={`/boxes/${box.id}`}
                      className="text-brand-600 hover:text-brand-800 text-xs"
                    >
                      详情 →
                    </Link>
                  </td>
                </tr>
              ))}
              {boxes.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-gray-400">
                    暂无注册的盒子，点击「注册新盒子」开始
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RegisterForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: (result: RegisterBoxResponse) => void;
  onCancel: () => void;
}) {
  const [id, setId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [summary, setSummary] = useState('');
  const [capabilities, setCapabilities] = useState('');
  const [scanInterval, setScanInterval] = useState(15);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id.trim()) {
      setError('ID 不能为空');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await api.registerBox({
        id: id.trim(),
        display_name: displayName.trim(),
        summary: summary.trim(),
        capabilities: capabilities
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        scan_interval_sec: scanInterval,
      });
      onSuccess(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">注册新盒子</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              盒子 ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="例如: researcher-01"
              pattern="[a-z0-9][a-z0-9._-]{1,62}"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
              required
            />
            <p className="mt-0.5 text-xs text-gray-400">
              小写字母、数字、点、下划线、横线
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">显示名</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="例如: 资料研究员"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">简介</label>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="描述这个盒子的用途..."
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">能力标签</label>
            <input
              type="text"
              value={capabilities}
              onChange={(e) => setCapabilities(e.target.value)}
              placeholder="逗号分隔，例如: research, summarize"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">扫描间隔（秒）</label>
            <input
              type="number"
              value={scanInterval}
              onChange={(e) => setScanInterval(Number(e.target.value))}
              min={5}
              max={3600}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-md text-sm">
            {error}
          </div>
        )}

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 bg-brand-600 text-white text-sm rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '注册中...' : '注册'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-5 py-2 bg-gray-100 text-gray-700 text-sm rounded-md hover:bg-gray-200 transition-colors"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}
