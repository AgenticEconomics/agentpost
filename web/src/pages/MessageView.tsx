import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { api, type MessageDetail as MessageDetailType } from '../api/client';

export default function MessageView() {
  const { boxId, messageId } = useParams<{ boxId: string; messageId: string }>();
  const navigate = useNavigate();
  const [message, setMessage] = useState<MessageDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [acking, setAcking] = useState(false);
  const [acked, setAcked] = useState(false);

  useEffect(() => {
    if (!boxId || !messageId) return;
    (async () => {
      try {
        const data = await api.readMessage(boxId, messageId);
        setMessage(data);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    })();
  }, [boxId, messageId]);

  const handleAck = async () => {
    if (!boxId || !message) return;
    setAcking(true);
    try {
      await api.ackMessage(boxId, message.message_id || message._file);
      setAcked(true);
    } catch (err) {
      alert(err instanceof Error ? err.message : '确认失败');
    } finally {
      setAcking(false);
    }
  };

  const handleReply = () => {
    if (!boxId || !message) return;
    const params = new URLSearchParams({
      to: message.from,
      subject: message.subject.startsWith('Re:') ? message.subject : `Re: ${message.subject}`,
      in_reply_to: message.message_id,
      thread_id: message.thread_id,
      type: 'reply',
    });
    navigate(`/mail/${boxId}/compose?${params.toString()}`);
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '-';
    try {
      return new Date(dateStr).toLocaleString('zh-CN');
    } catch {
      return dateStr;
    }
  };

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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    );
  }

  if (!message) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>消息不存在或无权访问</p>
        <Link to={`/mail/${boxId}/inbox`} className="text-brand-600 hover:underline text-sm mt-2 inline-block">
          ← 返回收件箱
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-4xl">
      {/* Back link */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="text-gray-400 hover:text-gray-600 text-sm"
        >
          ← 返回
        </button>
      </div>

      {/* Message header */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-start justify-between mb-4">
          <h1 className="text-xl font-semibold text-gray-900">
            {message.subject || '(无主题)'}
          </h1>
          <div className="flex gap-2">
            <button
              onClick={handleReply}
              className="px-3 py-1.5 bg-brand-50 text-brand-700 text-sm rounded-md hover:bg-brand-100 transition-colors"
            >
              ↩️ 回复
            </button>
            {!acked && (
              <button
                onClick={handleAck}
                disabled={acking}
                className="px-3 py-1.5 bg-green-50 text-green-700 text-sm rounded-md hover:bg-green-100 disabled:opacity-50 transition-colors"
              >
                {acking ? '处理中...' : '✅ 标记已处理'}
              </button>
            )}
            {acked && (
              <span className="px-3 py-1.5 bg-green-100 text-green-800 text-sm rounded-md">
                ✅ 已处理
              </span>
            )}
          </div>
        </div>

        {/* Headers */}
        <div className="bg-gray-50 rounded-md p-4 mb-4 space-y-1.5 text-sm">
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">消息 ID</span>
            <span className="font-mono text-xs text-gray-700 break-all">{message.message_id}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">发件人</span>
            <span className="text-gray-900">{message.from}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">收件人</span>
            <span className="text-gray-900">{message.to?.join(', ')}</span>
          </div>
          {message.cc && message.cc.length > 0 && (
            <div className="flex gap-2">
              <span className="text-gray-500 w-20 shrink-0">抄送</span>
              <span className="text-gray-900">{message.cc.join(', ')}</span>
            </div>
          )}
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">日期</span>
            <span className="text-gray-900">{formatDate(message.date)}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">类型</span>
            <span className="text-gray-900">{typeLabel(message.type)}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-gray-500 w-20 shrink-0">优先级</span>
            <span className={message.priority === 'high' ? 'text-red-600 font-medium' : 'text-gray-900'}>
              {message.priority}
            </span>
          </div>
          {message.thread_id && (
            <div className="flex gap-2">
              <span className="text-gray-500 w-20 shrink-0">线程</span>
              <span className="font-mono text-xs text-brand-600">{message.thread_id}</span>
            </div>
          )}
          {message.in_reply_to && (
            <div className="flex gap-2">
              <span className="text-gray-500 w-20 shrink-0">回复</span>
              <span className="font-mono text-xs text-gray-500 break-all">{message.in_reply_to}</span>
            </div>
          )}
          {message.labels && message.labels.length > 0 && (
            <div className="flex gap-2">
              <span className="text-gray-500 w-20 shrink-0">标签</span>
              <div className="flex gap-1 flex-wrap">
                {message.labels.map((label) => (
                  <span
                    key={label}
                    className="px-1.5 py-0.5 bg-brand-50 text-brand-700 text-xs rounded"
                  >
                    {label}
                  </span>
                ))}
              </div>
            </div>
          )}
          {message.protocol && (
            <div className="flex gap-2">
              <span className="text-gray-500 w-20 shrink-0">协议</span>
              <span className="font-mono text-xs text-gray-500">{message.protocol}</span>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="prose prose-sm max-w-none border-t border-gray-100 pt-4">
          <ReactMarkdown>{message.body || '(空消息)'}</ReactMarkdown>
        </div>
      </div>

      {/* Attachments */}
      {message.attachments && message.attachments.length > 0 && (
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-700 mb-3">📎 附件</h3>
          <div className="space-y-2">
            {message.attachments.map((att, i) => (
              <div
                key={i}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-md"
              >
                <div>
                  <p className="text-sm font-medium text-gray-900">{att.name}</p>
                  <p className="text-xs text-gray-500">
                    {att.media_type}
                    {att.sha256 && ` · SHA256: ${att.sha256.substring(0, 12)}...`}
                  </p>
                </div>
                <a
                  href={`/api/v1/boxes/${boxId}/files/content?path=${encodeURIComponent(att.path)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1 bg-brand-50 text-brand-700 text-xs rounded hover:bg-brand-100 transition-colors"
                >
                  下载
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
