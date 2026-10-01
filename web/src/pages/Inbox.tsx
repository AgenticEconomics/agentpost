import { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api, type MessageSummary } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';

type Folder = 'new' | 'cur' | 'seen';

export default function Inbox() {
  const { boxId } = useParams<{ boxId: string }>();
  const navigate = useNavigate();
  const [folder, setFolder] = useState<Folder>('cur');
  const [messages, setMessages] = useState<MessageSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchMessages = useCallback(async () => {
    if (!boxId) return;
    try {
      const data = await api.listInbox(boxId, folder);
      setMessages(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [boxId, folder]);

  useEffect(() => {
    setLoading(true);
    fetchMessages();
  }, [fetchMessages]);

  useWebSocket({
    onEvent: (event) => {
      if (
        event.type === 'mail.inbox_new' ||
        event.type === 'mail.delivered' ||
        event.type === 'skills.finished'
      ) {
        fetchMessages();
      }
    },
  });

  const tabs: { key: Folder; label: string }[] = [
    { key: 'new', label: '新消息' },
    { key: 'cur', label: '待处理' },
    { key: 'seen', label: '已读' },
  ];

  const typeLabel = (type: string) => {
    const map: Record<string, string> = {
      request: '请求',
      reply: '回复',
      event: '事件',
      receipt: '回执',
      artifact: '产物',
      system: '系统',
    };
    return map[type] || type;
  };

  const priorityColor = (p: string) => {
    switch (p) {
      case 'high':
        return 'text-red-600 font-medium';
      case 'low':
        return 'text-gray-400';
      default:
        return 'text-gray-600';
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    try {
      const d = new Date(dateStr);
      return d.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">收件箱 - {boxId}</h1>
        <Link
          to={`/mail/${boxId}/compose`}
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          ✏️ 写信
        </Link>
      </div>

      {/* Folder tabs */}
      <div className="flex gap-1 bg-white rounded-lg shadow p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setFolder(tab.key)}
            className={`flex-1 py-2 px-4 text-sm rounded-md transition-colors ${
              folder === tab.key
                ? 'bg-brand-600 text-white'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Message list */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
          </div>
        ) : messages.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <p className="text-4xl mb-2">📭</p>
            <p>暂无消息</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {messages.map((msg) => (
              <div
                key={msg._file || msg.message_id}
                onClick={() =>
                  navigate(
                    `/mail/${boxId}/inbox/${encodeURIComponent(msg.message_id || msg._file)}`,
                  )
                }
                className="px-5 py-4 hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-gray-900 truncate">
                        {msg.subject || '(无主题)'}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        msg.type === 'receipt'
                          ? 'bg-green-50 text-green-700'
                          : msg.type === 'system'
                          ? 'bg-purple-50 text-purple-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}>
                        {typeLabel(msg.type)}
                      </span>
                      {msg.priority === 'high' && (
                        <span className="text-xs text-red-600">🔴 高优先</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      <span>来自: {msg.from}</span>
                      <span>→</span>
                      <span className="truncate">{msg.to?.join(', ')}</span>
                    </div>
                    {msg.labels && msg.labels.length > 0 && (
                      <div className="flex gap-1 mt-1.5">
                        {msg.labels.map((label) => (
                          <span
                            key={label}
                            className="px-1.5 py-0.5 bg-brand-50 text-brand-700 text-xs rounded"
                          >
                            {label}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <p className={`text-xs ${priorityColor(msg.priority)}`}>
                      {formatDate(msg.date)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
