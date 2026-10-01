import { useEffect, useRef, useCallback, useState } from 'react';
import type { WSEvent } from '../api/client';

interface UseWebSocketOptions {
  onEvent?: (event: WSEvent) => void;
  enabled?: boolean;
}

interface UseWebSocketReturn {
  connected: boolean;
  lastEvent: WSEvent | null;
  reconnect: () => void;
}

export function useWebSocket({ onEvent, enabled = true }: UseWebSocketOptions): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const onEventRef = useRef(onEvent);

  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    const token = sessionStorage.getItem('agentpost_token');
    if (!token || !enabled) return;

    const actAs = sessionStorage.getItem('agentpost_act_as');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsUrl = `${wsProtocol}//${window.location.host}/api/v1/stream?token=${encodeURIComponent(token)}`;
    if (actAs) {
      wsUrl += `&box=${encodeURIComponent(actAs)}`;
    }

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data: WSEvent = JSON.parse(event.data);
        if (data.type === 'keepalive') return;
        setLastEvent(data);
        onEventRef.current?.(data);
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Auto-reconnect after 3 seconds
      reconnectTimer.current = setTimeout(() => {
        connect();
      }, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [enabled]);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = undefined;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    connect();
  }, [disconnect, connect]);

  useEffect(() => {
    if (enabled) {
      connect();
    }
    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);

  return { connected, lastEvent, reconnect };
}
