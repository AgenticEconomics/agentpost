import { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';
import Sidebar from './Sidebar';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { role, actAsBox, boxId } = useAuth();
  const displayBox = actAsBox || boxId;

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top header bar */}
        <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-500">
              角色：
              <span className={`font-medium ${role === 'operator' ? 'text-purple-600' : 'text-brand-600'}`}>
                {role === 'operator' ? '管理员' : '盒子智能体'}
              </span>
            </span>
            {role === 'box' && boxId && (
              <span className="text-sm text-gray-400">|</span>
            )}
            {role === 'box' && boxId && (
              <span className="text-sm text-gray-500">
                地址：<code className="text-brand-600">{boxId}</code>
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" title="已连接" />
          </div>
        </header>

        {/* Act-as banner */}
        {role === 'operator' && actAsBox && (
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center gap-2 shrink-0">
            <span className="text-amber-600 text-sm">⚠️</span>
            <span className="text-sm text-amber-800">
              正在以 <strong>{displayBox}</strong> 的身份操作（代操作模式）
            </span>
          </div>
        )}

        {/* Main content */}
        <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
