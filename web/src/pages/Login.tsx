import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { api } from '../api/client';

export default function Login() {
  const [token, setToken] = useState('');
  const [role, setRole] = useState<'operator' | 'box'>('operator');
  const [boxId, setBoxId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [domain, setDomain] = useState('agentpost.local');
  const { login } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    fetch('/api/v1/config')
      .then(res => res.ok ? res.json() : null)
      .then(data => { if (data?.domain) setDomain(data.domain); })
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) {
      setError('请输入令牌');
      return;
    }
    setLoading(true);
    setError('');

    try {
      // Temporarily store the token to test it
      sessionStorage.setItem('agentpost_token', token.trim());
      sessionStorage.setItem('agentpost_role', role);

      // Verify token by hitting health endpoint
      const res = await fetch('/api/v1/health', {
        headers: { Authorization: `Bearer ${token.trim()}` },
      });

      if (!res.ok) {
        throw new Error('令牌无效或无法连接服务器');
      }

      // For box role, verify the box exists
      if (role === 'box') {
        if (!boxId.trim()) {
          // Try to figure out the box id from addrbook
          setError('请输入盒子 ID');
          sessionStorage.removeItem('agentpost_token');
          sessionStorage.removeItem('agentpost_role');
          setLoading(false);
          return;
        }
        const boxRes = await fetch(`/api/v1/boxes/${encodeURIComponent(boxId.trim())}`, {
          headers: { Authorization: `Bearer ${token.trim()}` },
        });
        if (!boxRes.ok) {
          throw new Error(`无法访问盒子 ${boxId}，请检查令牌和 ID`);
        }
      }

      login(token.trim(), role, role === 'box' ? boxId.trim() : undefined);
      navigate(role === 'operator' ? '/ops' : `/mail/${boxId.trim()}/inbox`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
      sessionStorage.removeItem('agentpost_token');
      sessionStorage.removeItem('agentpost_role');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white">📦 AgentPost</h1>
          <p className="text-gray-400 mt-2">多智能体协作运行时</p>
        </div>

        {/* Login card */}
        <div className="bg-white rounded-xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-800 mb-6">登录</h2>

          {/* Role selector */}
          <div className="flex gap-3 mb-6">
            <button
              onClick={() => setRole('operator')}
              className={`flex-1 py-3 px-4 rounded-lg border-2 text-sm font-medium transition-all ${
                role === 'operator'
                  ? 'border-brand-500 bg-brand-50 text-brand-700'
                  : 'border-gray-200 text-gray-500 hover:border-gray-300'
              }`}
            >
              🔑 管理员令牌
            </button>
            <button
              onClick={() => setRole('box')}
              className={`flex-1 py-3 px-4 rounded-lg border-2 text-sm font-medium transition-all ${
                role === 'box'
                  ? 'border-brand-500 bg-brand-50 text-brand-700'
                  : 'border-gray-200 text-gray-500 hover:border-gray-300'
              }`}
            >
              📦 盒子令牌
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Token input */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                访问令牌
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="粘贴令牌..."
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                autoFocus
              />
            </div>

            {/* Box ID (only for box role) */}
            {role === 'box' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  盒子 ID
                </label>
                <input
                  type="text"
                  value={boxId}
                  onChange={(e) => setBoxId(e.target.value)}
                  placeholder="例如: alice"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                />
                <p className="mt-1 text-xs text-gray-400">
                  地址格式：ID@{domain}
                </p>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2.5 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium text-sm hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? '验证中...' : '登录'}
            </button>
          </form>

          <p className="text-xs text-gray-400 mt-6 text-center">
            令牌仅存储在会话内存中，关闭页面后需重新输入
          </p>
        </div>
      </div>
    </div>
  );
}
