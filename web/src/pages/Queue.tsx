import { useState, useEffect, useCallback } from 'react';
import { api, type SpoolResponse } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';

export default function Queue() {
  const [spool, setSpool] = useState<SpoolResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const data = await api.getSpool();
      setSpool(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useWebSocket({
    onEvent: (event) => {
      if (event.type.startsWith('mail.') || event.type === 'queue.depth') {
        fetchData();
      }
    },
  });

  const handleRetry = async (id: string) => {
    setActionLoading(`retry-${id}`);
    try {
      await api.retryDeadLetter(id);
      await fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : '重试失败');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDrop = async (id: string) => {
    if (!confirm(`确定要丢弃此死信吗？此操作不可逆！`)) return;
    setActionLoading(`drop-${id}`);
    try {
      await api.dropDeadLetter(id);
      await fetchData();
    } catch (err) {
      alert(err instanceof Error ? err.message : '丢弃失败');
    } finally {
      setActionLoading(null);
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
      <h1 className="text-2xl font-bold text-gray-900">队列管理</h1>

      {/* Spool depths */}
      <div className="bg-white rounded-lg shadow p-5">
        <h3 className="text-sm font-medium text-gray-700 mb-4">队列深度</h3>
        {spool?.depths && Object.keys(spool.depths).length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(spool.depths).map(([key, val]) => (
              <div key={key} className="bg-gray-50 rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-gray-900">{val}</p>
                <p className="text-xs text-gray-500 mt-1">{key}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-400">队列为空</p>
        )}
      </div>

      {/* Dead letter list */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-700">死信队列</h3>
          <span className="text-xs text-gray-400">
            {spool?.dead_letter?.length || 0} 条
          </span>
        </div>

        {!spool?.dead_letter || spool.dead_letter.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <p className="text-4xl mb-2">🎉</p>
            <p>没有死信</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-5 py-3 text-left">ID</th>
                  <th className="px-5 py-3 text-left">发件人</th>
                  <th className="px-5 py-3 text-left">收件人</th>
                  <th className="px-5 py-3 text-left">主题</th>
                  <th className="px-5 py-3 text-left">原因</th>
                  <th className="px-5 py-3 text-left">时间</th>
                  <th className="px-5 py-3 text-center">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {spool.dead_letter.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-5 py-3 font-mono text-xs text-gray-600 truncate max-w-[120px]">
                      {item.id}
                    </td>
                    <td className="px-5 py-3 text-gray-700">{item.from}</td>
                    <td className="px-5 py-3 text-gray-700">
                      {Array.isArray(item.to) ? item.to.join(', ') : item.to}
                    </td>
                    <td className="px-5 py-3 text-gray-700 max-w-[200px] truncate">
                      {item.subject}
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-red-600 text-xs">{item.reason}</span>
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-500">
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString('zh-CN')
                        : '-'}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex gap-2 justify-center">
                        <button
                          onClick={() => handleRetry(item.id)}
                          disabled={actionLoading === `retry-${item.id}`}
                          className="px-2.5 py-1 bg-blue-50 text-blue-700 text-xs rounded hover:bg-blue-100 disabled:opacity-50 transition-colors"
                        >
                          重试
                        </button>
                        <button
                          onClick={() => handleDrop(item.id)}
                          disabled={actionLoading === `drop-${item.id}`}
                          className="px-2.5 py-1 bg-red-50 text-red-700 text-xs rounded hover:bg-red-100 disabled:opacity-50 transition-colors"
                        >
                          丢弃
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
