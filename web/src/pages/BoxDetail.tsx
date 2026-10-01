import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, type BoxDetail as BoxDetailType } from '../api/client';
import { StatusDot } from './Ops';

export default function BoxDetail() {
  const { boxId } = useParams<{ boxId: string }>();
  const [box, setBox] = useState<BoxDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [rotatedToken, setRotatedToken] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState('');

  const fetchBox = useCallback(async () => {
    if (!boxId) return;
    try {
      const data = await api.getBox(boxId);
      setBox(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [boxId]);

  useEffect(() => {
    fetchBox();
  }, [fetchBox]);

  const handleAction = async (action: string) => {
    if (!boxId) return;
    setActionLoading(action);
    try {
      switch (action) {
        case 'pause':
          await api.patchBox(boxId, { status: 'paused' });
          break;
        case 'resume':
          await api.patchBox(boxId, { status: 'active' });
          break;
        case 'revoke':
          if (!confirm(`确定要吊销盒子 ${boxId} 吗？此操作不可逆！`)) {
            setActionLoading('');
            return;
          }
          await api.revokeBox(boxId);
          break;
        case 'rotate':
          if (!confirm(`轮换令牌后，旧令牌将立即失效。确定要继续吗？`)) {
            setActionLoading('');
            return;
          }
          const result = await api.rotateToken(boxId);
          setRotatedToken(result.token);
          break;
      }
      await fetchBox();
    } catch (err) {
      alert(err instanceof Error ? err.message : '操作失败');
    } finally {
      setActionLoading('');
    }
  };

  const copyToken = () => {
    if (rotatedToken) {
      navigator.clipboard.writeText(rotatedToken);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    );
  }

  if (!box) {
    return (
      <div className="text-center py-12 text-gray-500">
        <p>盒子不存在或无权访问</p>
        <Link to="/boxes" className="text-brand-600 hover:underline text-sm mt-2 inline-block">
          ← 返回盒子列表
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/boxes" className="text-gray-400 hover:text-gray-600">
          ← 返回
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">
          {box.display_name || box.id}
        </h1>
        <StatusDot status={box.status} />
      </div>

      {/* Rotated token modal */}
      {rotatedToken && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-lg w-full p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">🔑 新令牌已生成</h2>
            <div className="flex gap-2 mb-4">
              <code className="flex-1 bg-gray-100 px-3 py-2 rounded text-sm font-mono break-all select-all">
                {rotatedToken}
              </code>
              <button
                onClick={copyToken}
                className="px-3 py-2 bg-brand-600 text-white text-sm rounded hover:bg-brand-700 shrink-0"
              >
                复制
              </button>
            </div>
            <p className="text-xs text-red-500 mb-4">⚠️ 请立即保存，关闭后无法再次查看！</p>
            <button
              onClick={() => setRotatedToken(null)}
              className="w-full py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200"
            >
              我已保存，关闭
            </button>
          </div>
        </div>
      )}

      {/* Info cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-2">基本信息</h3>
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500">ID</dt>
              <dd className="font-mono text-gray-900">{box.id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">地址</dt>
              <dd className="font-mono text-brand-700 text-xs">{box.address}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">显示名</dt>
              <dd className="text-gray-900">{box.display_name || '-'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">扫描间隔</dt>
              <dd className="text-gray-900">{box.scan_interval_sec || 15} 秒</dd>
            </div>
          </dl>
        </div>

        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-2">队列状态</h3>
          {box.queue && (
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">收件 new</dt>
                <dd className="font-mono">{box.queue.inbox_new}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">收件 cur</dt>
                <dd className="font-mono">{box.queue.inbox_cur}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">发件 new</dt>
                <dd className="font-mono">{box.queue.outbox_new}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">已发送</dt>
                <dd className="font-mono">{box.queue.outbox_sent}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-500">发送失败</dt>
                <dd className="font-mono text-red-600">{box.queue.outbox_failed}</dd>
              </div>
            </dl>
          )}
        </div>

        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-2">能力标签</h3>
          <div className="flex flex-wrap gap-1.5">
            {box.capabilities.length > 0 ? (
              box.capabilities.map((cap) => (
                <span
                  key={cap}
                  className="px-2 py-1 bg-brand-50 text-brand-700 text-xs rounded-md"
                >
                  {cap}
                </span>
              ))
            ) : (
              <span className="text-sm text-gray-400">暂无</span>
            )}
          </div>
          {box.summary && (
            <p className="text-sm text-gray-600 mt-3">{box.summary}</p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="bg-white rounded-lg shadow p-5">
        <h3 className="text-sm font-medium text-gray-700 mb-4">操作</h3>
        <div className="flex flex-wrap gap-3">
          {box.status === 'active' && (
            <button
              onClick={() => handleAction('pause')}
              disabled={actionLoading === 'pause'}
              className="px-4 py-2 bg-yellow-500 text-white text-sm rounded-md hover:bg-yellow-600 disabled:opacity-50 transition-colors"
            >
              ⏸ 暂停
            </button>
          )}
          {box.status === 'paused' && (
            <button
              onClick={() => handleAction('resume')}
              disabled={actionLoading === 'resume'}
              className="px-4 py-2 bg-green-500 text-white text-sm rounded-md hover:bg-green-600 disabled:opacity-50 transition-colors"
            >
              ▶️ 恢复
            </button>
          )}
          {box.status !== 'revoked' && (
            <button
              onClick={() => handleAction('revoke')}
              disabled={actionLoading === 'revoke'}
              className="px-4 py-2 bg-red-500 text-white text-sm rounded-md hover:bg-red-600 disabled:opacity-50 transition-colors"
            >
              🚫 吊销
            </button>
          )}
          <button
            onClick={() => handleAction('rotate')}
            disabled={actionLoading === 'rotate'}
            className="px-4 py-2 bg-gray-600 text-white text-sm rounded-md hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            🔑 轮换令牌
          </button>

          <div className="ml-auto flex gap-2">
            <Link
              to={`/mail/${boxId}/inbox`}
              className="px-4 py-2 bg-brand-50 text-brand-700 text-sm rounded-md hover:bg-brand-100 transition-colors"
            >
              📥 查看收件箱
            </Link>
            <Link
              to={`/mail/${boxId}/compose`}
              className="px-4 py-2 bg-brand-50 text-brand-700 text-sm rounded-md hover:bg-brand-100 transition-colors"
            >
              ✏️ 写信
            </Link>
            <Link
              to={`/files/${boxId}`}
              className="px-4 py-2 bg-brand-50 text-brand-700 text-sm rounded-md hover:bg-brand-100 transition-colors"
            >
              📁 文件
            </Link>
          </div>
        </div>
      </div>

      {/* Issues */}
      {box.issues && box.issues.length > 0 && (
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-700 mb-3">目录问题</h3>
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs text-gray-500">路径</th>
                <th className="px-3 py-2 text-left text-xs text-gray-500">问题</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {box.issues.map((issue, i) => (
                <tr key={i}>
                  <td className="px-3 py-2 font-mono text-xs">{issue.path}</td>
                  <td className="px-3 py-2 text-gray-700">{issue.issue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
