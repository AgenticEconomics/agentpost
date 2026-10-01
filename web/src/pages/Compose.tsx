import { useState, useEffect } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { api, type AddrbookEntry } from '../api/client';

export default function Compose() {
  const { boxId } = useParams<{ boxId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [to, setTo] = useState(searchParams.get('to') || '');
  const [subject, setSubject] = useState(searchParams.get('subject') || '');
  const [body, setBody] = useState('');
  const [type, setType] = useState(searchParams.get('type') || 'request');
  const [priority, setPriority] = useState('normal');
  const [ack, setAck] = useState(true);
  const [labels, setLabels] = useState('');
  const [threadId, setThreadId] = useState(searchParams.get('thread_id') || '');
  const [inReplyTo, setInReplyTo] = useState(searchParams.get('in_reply_to') || '');
  const [addrbook, setAddrbook] = useState<AddrbookEntry[]>([]);
  const [showAddrbook, setShowAddrbook] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ status: string; message_id: string } | null>(null);
  const [error, setError] = useState('');

  // File attachments
  const [attachments, setAttachments] = useState<Array<{ filename: string; content_base64: string; media_type: string }>>([]);

  useEffect(() => {
    (async () => {
      try {
        const data = await api.addrbook();
        setAddrbook(data);
      } catch {
        // ignore
      }
    })();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    Array.from(files).forEach((file) => {
      const reader = new FileReader();
      reader.onload = () => {
        const base64 = (reader.result as string).split(',')[1];
        setAttachments((prev) => [
          ...prev,
          {
            filename: file.name,
            content_base64: base64,
            media_type: file.type || 'application/octet-stream',
          },
        ]);
      };
      reader.readAsDataURL(file);
    });
  };

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const selectRecipient = (address: string) => {
    const current = to.split(',').map((s) => s.trim()).filter(Boolean);
    if (!current.includes(address)) {
      current.push(address);
      setTo(current.join(', '));
    }
    setShowAddrbook(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!boxId) return;
    if (!to.trim()) {
      setError('请填写收件人');
      return;
    }
    if (!subject.trim()) {
      setError('请填写主题');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const toList = to.split(',').map((s) => s.trim()).filter(Boolean);
      const labelList = labels.split(',').map((s) => s.trim()).filter(Boolean);

      const res = await api.compose(boxId, {
        to: toList,
        subject: subject.trim(),
        body: body,
        type,
        priority,
        thread_id: threadId || undefined,
        in_reply_to: inReplyTo || null,
        ack,
        labels: labelList,
        attachments: attachments.length > 0 ? attachments : undefined,
      });

      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '发送失败');
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="text-4xl mb-4">✅</div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">消息已受理</h2>
          <p className="text-sm text-gray-500 mb-1">消息 ID</p>
          <p className="font-mono text-sm text-brand-700 break-all mb-6">{result.message_id}</p>
          <p className="text-xs text-gray-400 mb-4">
            消息已写入 outbox，将由投递引擎处理。可在收件箱查看投递结果。
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={() => {
                setResult(null);
                setSubject('');
                setBody('');
                setTo('');
                setAttachments([]);
                setLabels('');
              }}
              className="px-4 py-2 bg-brand-600 text-white text-sm rounded-md hover:bg-brand-700 transition-colors"
            >
              继续写信
            </button>
            <button
              onClick={() => navigate(`/mail/${boxId}/inbox`)}
              className="px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-md hover:bg-gray-200 transition-colors"
            >
              查看收件箱
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate(-1)}
          className="text-gray-400 hover:text-gray-600 text-sm"
        >
          ← 返回
        </button>
        <h1 className="text-2xl font-bold text-gray-900">写信 - {boxId}</h1>
      </div>

      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-4">
        {/* To */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            收件人 <span className="text-red-500">*</span>
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="地址，多个用逗号分隔"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <button
              type="button"
              onClick={() => setShowAddrbook(!showAddrbook)}
              className="px-3 py-2 bg-gray-100 text-gray-700 text-sm rounded-md hover:bg-gray-200 transition-colors"
            >
              📒 地址簿
            </button>
          </div>
          {showAddrbook && (
            <div className="mt-2 border border-gray-200 rounded-md max-h-48 overflow-y-auto">
              {addrbook.length === 0 ? (
                <p className="p-3 text-sm text-gray-400">地址簿为空</p>
              ) : (
                addrbook.map((entry) => (
                  <button
                    key={entry.address}
                    type="button"
                    onClick={() => selectRecipient(entry.address)}
                    className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b border-gray-100 last:border-0"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-sm font-medium text-gray-900">
                          {entry.display_name || entry.address}
                        </span>
                        <span className="text-xs text-gray-400 ml-2">{entry.address}</span>
                      </div>
                      <span className="text-xs text-gray-400">
                        {entry.status === 'active' ? '🟢' : '🔴'}
                      </span>
                    </div>
                    {entry.summary && (
                      <p className="text-xs text-gray-500 mt-0.5">{entry.summary}</p>
                    )}
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Subject */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            主题 <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="消息主题"
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        {/* Type and Priority */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">类型</label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="request">请求</option>
              <option value="reply">回复</option>
              <option value="event">事件</option>
              <option value="artifact">产物</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">优先级</label>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            >
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
            </select>
          </div>
        </div>

        {/* Labels and Ack */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">标签</label>
            <input
              type="text"
              value={labels}
              onChange={(e) => setLabels(e.target.value)}
              placeholder="逗号分隔"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="flex items-end pb-2">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
                className="rounded border-gray-300"
              />
              要求回执
            </label>
          </div>
        </div>

        {/* Thread info (for replies) */}
        {(threadId || inReplyTo) && (
          <div className="bg-blue-50 rounded-md p-3 text-xs text-blue-700 space-y-1">
            {threadId && (
              <div>
                <span className="font-medium">线程 ID：</span>
                <span className="font-mono">{threadId}</span>
              </div>
            )}
            {inReplyTo && (
              <div>
                <span className="font-medium">回复消息：</span>
                <span className="font-mono">{inReplyTo}</span>
              </div>
            )}
          </div>
        )}

        {/* Body */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">正文</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="支持 Markdown 格式..."
            rows={10}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        {/* Attachments */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">附件</label>
          <input
            type="file"
            multiple
            onChange={handleFileChange}
            className="w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
          />
          {attachments.length > 0 && (
            <div className="mt-2 space-y-1">
              {attachments.map((att, i) => (
                <div key={i} className="flex items-center justify-between bg-gray-50 px-3 py-1.5 rounded text-sm">
                  <span className="text-gray-700">{att.filename}</span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(i)}
                    className="text-red-500 hover:text-red-700 text-xs"
                  >
                    移除
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-md text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2 bg-brand-600 text-white text-sm rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '发送中...' : '发送'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-6 py-2 bg-gray-100 text-gray-700 text-sm rounded-md hover:bg-gray-200 transition-colors"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}
