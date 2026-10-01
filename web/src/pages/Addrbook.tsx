import { useState, useEffect } from 'react';
import { api, type AddrbookEntry } from '../api/client';

export default function Addrbook() {
  const [entries, setEntries] = useState<AddrbookEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const data = await api.addrbook();
        setEntries(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = entries.filter((e) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      e.address.toLowerCase().includes(q) ||
      e.display_name.toLowerCase().includes(q) ||
      e.summary.toLowerCase().includes(q) ||
      e.capabilities.some((c) => c.toLowerCase().includes(q))
    );
  });

  const statusLabel = (status: string) => {
    const map: Record<string, { text: string; color: string }> = {
      active: { text: '活跃', color: 'bg-green-100 text-green-700' },
      paused: { text: '已暂停', color: 'bg-yellow-100 text-yellow-700' },
      revoked: { text: '已吊销', color: 'bg-red-100 text-red-700' },
    };
    const info = map[status] || { text: status, color: 'bg-gray-100 text-gray-700' };
    return <span className={`px-2 py-0.5 text-xs rounded ${info.color}`}>{info.text}</span>;
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
      <h1 className="text-2xl font-bold text-gray-900">公共地址簿</h1>

      {/* Search */}
      <div className="bg-white rounded-lg shadow p-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="搜索地址、名称、能力..."
          className="w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* Entry list */}
      {filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <p className="text-4xl mb-2">📒</p>
          <p>{search ? '没有匹配的结果' : '地址簿为空'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((entry) => (
            <div
              key={entry.address}
              className="bg-white rounded-lg shadow p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h3 className="font-semibold text-gray-900">
                    {entry.display_name || entry.address}
                  </h3>
                  <p className="text-sm font-mono text-brand-600">{entry.address}</p>
                </div>
                {statusLabel(entry.status)}
              </div>

              {entry.summary && (
                <p className="text-sm text-gray-600 mb-3">{entry.summary}</p>
              )}

              {entry.capabilities.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {entry.capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-400 text-center">
        共 {filtered.length} 个地址
        {search && ` (总共 ${entries.length} 个)`}
      </p>
    </div>
  );
}
