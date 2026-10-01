import { useState, useEffect } from 'react';
import { api, type HealthResponse, type BoxListItem, type DoctorResponse } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';

export default function Ops() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [boxes, setBoxes] = useState<BoxListItem[]>([]);
  const [doctorResult, setDoctorResult] = useState<DoctorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [doctorLoading, setDoctorLoading] = useState(false);
  const [repairMode, setRepairMode] = useState(false);

  const fetchData = async () => {
    try {
      const [h, b] = await Promise.all([api.health(), api.listBoxes()]);
      setHealth(h);
      setBoxes(b);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  useWebSocket({
    onEvent: (event) => {
      if (event.type.startsWith('box.') || event.type.startsWith('mail.')) {
        fetchData();
      }
    },
  });

  const runDoctor = async () => {
    setDoctorLoading(true);
    try {
      const result = await api.doctor(repairMode);
      setDoctorResult(result);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Doctor 运行失败');
    } finally {
      setDoctorLoading(false);
    }
  };

  const formatUptime = (sec: number): string => {
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (d > 0) return `${d}天 ${h}时 ${m}分`;
    if (h > 0) return `${h}时 ${m}分`;
    return `${m}分`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
      </div>
    );
  }

  const totalUnread = boxes.reduce((sum, b) => sum + b.unread, 0);
  const totalSent = boxes.reduce((sum, b) => sum + b.sent, 0);
  const totalFailed = boxes.reduce((sum, b) => sum + b.failed, 0);
  const activeBoxes = boxes.filter((b) => b.status === 'active').length;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">运营总览</h1>

      {/* Status cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatusCard
          title="系统状态"
          value={health?.ready ? '就绪' : '启动中'}
          icon="🟢"
          color={health?.ready ? 'green' : 'yellow'}
        />
        <StatusCard
          title="运行时间"
          value={health ? formatUptime(health.uptime_sec) : '-'}
          icon="⏱️"
          color="blue"
        />
        <StatusCard
          title="活跃盒子"
          value={`${activeBoxes} / ${boxes.length}`}
          icon="📦"
          color="purple"
        />
        <StatusCard
          title="未读消息"
          value={String(totalUnread)}
          icon="📬"
          color="orange"
        />
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-1">已发送消息</h3>
          <p className="text-2xl font-bold text-gray-900">{totalSent}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-1">投递失败</h3>
          <p className="text-2xl font-bold text-red-600">{totalFailed}</p>
        </div>
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-1">版本</h3>
          <p className="text-2xl font-bold text-gray-900">{health?.version || '-'}</p>
        </div>
      </div>

      {/* Queue depth */}
      {health?.queue_depth && Object.keys(health.queue_depth).length > 0 && (
        <div className="bg-white rounded-lg shadow p-5">
          <h3 className="text-sm font-medium text-gray-500 mb-3">队列深度</h3>
          <div className="flex gap-6 flex-wrap">
            {Object.entries(health.queue_depth).map(([key, val]) => (
              <div key={key} className="text-center">
                <p className="text-lg font-bold text-gray-900">{val}</p>
                <p className="text-xs text-gray-500">{key}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Box summary table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-700">盒子概览</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-5 py-3 text-left">状态</th>
                <th className="px-5 py-3 text-left">ID</th>
                <th className="px-5 py-3 text-left">显示名</th>
                <th className="px-5 py-3 text-right">未读</th>
                <th className="px-5 py-3 text-right">已发</th>
                <th className="px-5 py-3 text-right">失败</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {boxes.map((box) => (
                <tr key={box.id} className="hover:bg-gray-50">
                  <td className="px-5 py-3">
                    <StatusDot status={box.status} />
                  </td>
                  <td className="px-5 py-3 font-mono text-gray-900">{box.id}</td>
                  <td className="px-5 py-3 text-gray-700">{box.display_name || '-'}</td>
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
                </tr>
              ))}
              {boxes.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-gray-400">
                    暂无注册的盒子
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Doctor */}
      <div className="bg-white rounded-lg shadow p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-700">系统诊断（Doctor）</h3>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm text-gray-500">
              <input
                type="checkbox"
                checked={repairMode}
                onChange={(e) => setRepairMode(e.target.checked)}
                className="rounded border-gray-300"
              />
              自动修复
            </label>
            <button
              onClick={runDoctor}
              disabled={doctorLoading}
              className="px-4 py-1.5 bg-brand-600 text-white text-sm rounded-md hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {doctorLoading ? '运行中...' : '运行诊断'}
            </button>
          </div>
        </div>

        {doctorResult && (
          <div>
            {doctorResult.count === 0 ? (
              <p className="text-sm text-green-600">✅ 未发现问题</p>
            ) : (
              <div>
                <p className="text-sm text-gray-600 mb-2">
                  发现 {doctorResult.count} 个问题
                  {doctorResult.repaired && '（已尝试修复）'}
                </p>
                <table className="w-full text-sm border border-gray-200 rounded">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs text-gray-500">路径</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-500">问题</th>
                      <th className="px-3 py-2 text-left text-xs text-gray-500">可修复</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {doctorResult.issues.map((issue, i) => (
                      <tr key={i}>
                        <td className="px-3 py-2 font-mono text-xs">{issue.path}</td>
                        <td className="px-3 py-2 text-gray-700">{issue.issue}</td>
                        <td className="px-3 py-2">
                          {issue.repairable ? (
                            <span className="text-green-600">是</span>
                          ) : (
                            <span className="text-red-600">否</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusCard({
  title,
  value,
  icon,
  color,
}: {
  title: string;
  value: string;
  icon: string;
  color: string;
}) {
  const bgMap: Record<string, string> = {
    green: 'bg-green-50 border-green-200',
    yellow: 'bg-yellow-50 border-yellow-200',
    blue: 'bg-blue-50 border-blue-200',
    purple: 'bg-purple-50 border-purple-200',
    orange: 'bg-orange-50 border-orange-200',
  };

  return (
    <div className={`bg-white rounded-lg shadow p-5 border-l-4 ${bgMap[color] || bgMap.blue}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-xl font-bold text-gray-900 mt-1">{value}</p>
        </div>
        <span className="text-2xl">{icon}</span>
      </div>
    </div>
  );
}

export function StatusDot({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    active: 'bg-green-500',
    paused: 'bg-yellow-500',
    revoked: 'bg-red-500',
  };
  const labelMap: Record<string, string> = {
    active: '活跃',
    paused: '已暂停',
    revoked: '已吊销',
  };

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-2.5 h-2.5 rounded-full ${colorMap[status] || 'bg-gray-400'}`} />
      <span className="text-xs text-gray-600">{labelMap[status] || status}</span>
    </span>
  );
}
