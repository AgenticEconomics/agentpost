import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Sidebar() {
  const { role, actAsBox, setActAsBox, boxId, logout } = useAuth();
  const navigate = useNavigate();

  const currentBoxId = actAsBox || boxId;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItemClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
      isActive
        ? 'bg-brand-600 text-white'
        : 'text-gray-300 hover:bg-gray-700 hover:text-white'
    }`;

  return (
    <aside className="w-56 bg-gray-900 text-white flex flex-col min-h-screen shrink-0">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-gray-700">
        <h1 className="text-lg font-bold tracking-tight">📦 AgentPost</h1>
        <p className="text-xs text-gray-400 mt-0.5">多智能体协作运行时</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {/* Operator sections */}
        {role === 'operator' && (
          <>
            <div className="px-2 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              运维管理
            </div>
            <NavLink to="/ops" className={navItemClass} end>
              <span>📊</span> 运营总览
            </NavLink>
            <NavLink to="/boxes" className={navItemClass}>
              <span>📦</span> 盒子管理
            </NavLink>
            <NavLink to="/queue" className={navItemClass}>
              <span>📮</span> 队列管理
            </NavLink>
            <div className="px-2 mt-4 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              公共
            </div>
            <NavLink to="/addrbook" className={navItemClass}>
              <span>📒</span> 地址簿
            </NavLink>
          </>
        )}

        {/* Box user sections */}
        {role === 'box' && (
          <>
            <div className="px-2 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              邮箱
            </div>
            {boxId && (
              <>
                <NavLink to={`/mail/${boxId}/inbox`} className={navItemClass}>
                  <span>📥</span> 收件箱
                </NavLink>
                <NavLink to={`/mail/${boxId}/compose`} className={navItemClass}>
                  <span>✏️</span> 写信
                </NavLink>
                <NavLink to={`/files/${boxId}`} className={navItemClass}>
                  <span>📁</span> 文件浏览
                </NavLink>
              </>
            )}
            <div className="px-2 mt-4 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              公共
            </div>
            <NavLink to="/addrbook" className={navItemClass}>
              <span>📒</span> 地址簿
            </NavLink>
          </>
        )}

        {/* Operator acting as box - show mail links */}
        {role === 'operator' && currentBoxId && (
          <>
            <div className="px-2 mt-4 mb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">
              邮箱（代操作）
            </div>
            <NavLink to={`/mail/${currentBoxId}/inbox`} className={navItemClass}>
              <span>📥</span> 收件箱
            </NavLink>
            <NavLink to={`/mail/${currentBoxId}/compose`} className={navItemClass}>
              <span>✏️</span> 写信
            </NavLink>
            <NavLink to={`/files/${currentBoxId}`} className={navItemClass}>
              <span>📁</span> 文件浏览
            </NavLink>
          </>
        )}
      </nav>

      {/* Act-as selector for operator */}
      {role === 'operator' && <ActAsSelector />}

      {/* Logout */}
      <div className="px-3 py-3 border-t border-gray-700">
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded-md transition-colors"
        >
          <span>🚪</span> 退出登录
        </button>
      </div>
    </aside>
  );
}

function ActAsSelector() {
  const { setActAsBox, actAsBox } = useAuth();
  const [boxes, setBoxes] = useState<Array<{ id: string; display_name: string }>>([]);

  useEffect(() => {
    fetchBoxes();
  }, []);

  const fetchBoxes = async () => {
    try {
      const token = sessionStorage.getItem('agentpost_token');
      const res = await fetch('/api/v1/boxes', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setBoxes(data);
      }
    } catch {
      // ignore
    }
  };

  return (
    <div className="px-3 py-3 border-t border-gray-700">
      <label className="block text-xs text-gray-500 mb-1">代操作盒子</label>
      <select
        value={actAsBox || ''}
        onChange={(e) => setActAsBox(e.target.value || null)}
        className="w-full bg-gray-800 text-sm text-gray-200 border border-gray-600 rounded px-2 py-1.5 focus:outline-none focus:border-brand-500"
      >
        <option value="">-- 不选择 --</option>
        {boxes.map((b) => (
          <option key={b.id} value={b.id}>
            {b.display_name || b.id}
          </option>
        ))}
      </select>
    </div>
  );
}
