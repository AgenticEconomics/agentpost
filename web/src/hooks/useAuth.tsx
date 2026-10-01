import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

interface AuthState {
  token: string;
  role: 'operator' | 'box' | null;
  boxId: string | null;
  actAsBox: string | null;
}

interface AuthContextValue extends AuthState {
  login: (token: string, role: 'operator' | 'box', boxId?: string) => void;
  logout: () => void;
  setActAsBox: (boxId: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(() => ({
    token: sessionStorage.getItem('agentpost_token') || '',
    role: (sessionStorage.getItem('agentpost_role') as 'operator' | 'box') || null,
    boxId: sessionStorage.getItem('agentpost_box_id') || null,
    actAsBox: sessionStorage.getItem('agentpost_act_as') || null,
  }));

  const login = useCallback((token: string, role: 'operator' | 'box', boxId?: string) => {
    sessionStorage.setItem('agentpost_token', token);
    sessionStorage.setItem('agentpost_role', role);
    if (boxId) {
      sessionStorage.setItem('agentpost_box_id', boxId);
    } else {
      sessionStorage.removeItem('agentpost_box_id');
    }
    sessionStorage.removeItem('agentpost_act_as');
    setState({
      token,
      role,
      boxId: boxId || null,
      actAsBox: null,
    });
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem('agentpost_token');
    sessionStorage.removeItem('agentpost_role');
    sessionStorage.removeItem('agentpost_box_id');
    sessionStorage.removeItem('agentpost_act_as');
    setState({ token: '', role: null, boxId: null, actAsBox: null });
  }, []);

  const setActAsBox = useCallback((boxId: string | null) => {
    if (boxId) {
      sessionStorage.setItem('agentpost_act_as', boxId);
    } else {
      sessionStorage.removeItem('agentpost_act_as');
    }
    setState((prev) => ({ ...prev, actAsBox: boxId }));
  }, []);

  // Listen for storage changes (e.g., logout from another tab)
  useEffect(() => {
    const handler = (e: StorageEvent) => {
      if (e.key === 'agentpost_token' && !e.newValue) {
        setState({ token: '', role: null, boxId: null, actAsBox: null });
      }
    };
    window.addEventListener('storage', handler);
    return () => window.removeEventListener('storage', handler);
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout, setActAsBox }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
