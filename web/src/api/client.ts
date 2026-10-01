const API_BASE = '/api/v1';

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

function getToken(): string {
  return sessionStorage.getItem('agentpost_token') || '';
}

function getActAsBox(): string | null {
  return sessionStorage.getItem('agentpost_act_as');
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options?: { raw?: boolean },
): Promise<T> {
  const token = getToken();
  const actAs = getActAsBox();

  const headers: Record<string, string> = {
    'Authorization': `Bearer ${token}`,
  };

  if (actAs) {
    headers['X-Act-As-Box'] = actAs;
  }

  if (body !== undefined && !options?.raw) {
    headers['Content-Type'] = 'application/json';
  }

  const config: RequestInit = {
    method,
    headers,
  };

  if (body !== undefined) {
    if (options?.raw) {
      config.body = body as BodyInit;
    } else {
      config.body = JSON.stringify(body);
    }
  }

  const res = await fetch(`${API_BASE}${path}`, config);

  if (res.status === 401) {
    sessionStorage.removeItem('agentpost_token');
    sessionStorage.removeItem('agentpost_role');
    sessionStorage.removeItem('agentpost_act_as');
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new Error(errBody?.detail || errBody?.error?.message || `HTTP ${res.status}`);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json();
}

export const api = {
  // System
  health: () => request<HealthResponse>('GET', '/health'),
  version: () => request<VersionResponse>('GET', '/version'),
  metrics: () => request<MetricsResponse>('GET', '/metrics'),
  config: () => request<ConfigResponse>('GET', '/config'),
  doctor: (repair: boolean) => request<DoctorResponse>('POST', '/doctor', { repair }),

  // Boxes
  listBoxes: () => request<BoxListItem[]>('GET', '/boxes'),
  getBox: (id: string) => request<BoxDetail>('GET', `/boxes/${id}`),
  registerBox: (data: RegisterBoxRequest) => request<RegisterBoxResponse>('POST', '/boxes', data),
  patchBox: (id: string, data: PatchBoxRequest) => request<PatchBoxResponse>('PATCH', `/boxes/${id}`, data),
  revokeBox: (id: string) => request<{ id: string; status: string }>('POST', `/boxes/${id}/revoke`),
  rotateToken: (id: string) => request<{ id: string; token: string }>('POST', `/boxes/${id}/token/rotate`),
  addrbook: () => request<AddrbookEntry[]>('GET', '/addrbook'),

  // Inbox
  listInbox: (boxId: string, folder: string, limit = 50) =>
    request<MessageSummary[]>('GET', `/boxes/${boxId}/inbox?folder=${folder}&limit=${limit}`),
  readMessage: (boxId: string, messageId: string) =>
    request<MessageDetail>('GET', `/boxes/${boxId}/inbox/${encodeURIComponent(messageId)}`),
  ackMessage: (boxId: string, messageId: string) =>
    request<{ status: string; message_id: string }>('POST', `/boxes/${boxId}/inbox/${encodeURIComponent(messageId)}/ack`),

  // Outbox
  listOutbox: (boxId: string, folder: string, limit = 50) =>
    request<MessageSummary[]>('GET', `/boxes/${boxId}/outbox?folder=${folder}&limit=${limit}`),
  compose: (boxId: string, data: ComposeRequest) =>
    request<ComposeResponse>('POST', `/boxes/${boxId}/outbox`, data),

  // Threads
  getThread: (boxId: string, threadId: string) =>
    request<MessageSummary[]>('GET', `/boxes/${boxId}/threads/${encodeURIComponent(threadId)}`),

  // Files
  listFiles: (boxId: string, path: string) =>
    request<FileEntry[]>('GET', `/boxes/${boxId}/files?path=${encodeURIComponent(path)}`),
  readFile: (boxId: string, path: string) =>
    request<Blob>('GET', `/boxes/${boxId}/files/content?path=${encodeURIComponent(path)}`),
  writeFile: (boxId: string, path: string, content: ArrayBuffer | string) =>
    request<{ status: string; path: string; size: number }>('PUT', `/boxes/${boxId}/files/content?path=${encodeURIComponent(path)}`, content, { raw: true }),

  // Memory & Skills & Logs
  getMemory: (boxId: string) => request<MemoryResponse>('GET', `/boxes/${boxId}/memory`),
  getSkills: (boxId: string) => request<SkillsResponse>('GET', `/boxes/${boxId}/skills`),
  getLogs: (boxId: string) => request<LogEntry[]>('GET', `/boxes/${boxId}/logs`),

  // Queue
  getSpool: () => request<SpoolResponse>('GET', '/spool'),
  retryDeadLetter: (id: string) => request<{ status: string; id: string }>('POST', `/spool/dead-letter/${id}/retry`),
  dropDeadLetter: (id: string) => request<{ status: string; id: string }>('POST', `/spool/dead-letter/${id}/drop`),
};

// --- Types ---

export interface HealthResponse {
  status: string;
  version: string;
  ready: boolean;
  queue_depth: Record<string, number>;
  boxes: number;
  uptime_sec: number;
}

export interface VersionResponse {
  version: string;
  protocol: string;
}

export interface MetricsResponse {
  delivery: Record<string, number>;
  queue_depth: Record<string, number>;
  boxes: number;
}

export interface ConfigResponse {
  domain: string;
  root: string;
  watch_interval_ms: number;
  max_attachment_bytes: number;
  max_message_bytes: number;
  api: { host: string; port: number };
  scan: { default_interval_sec: number };
  security: { require_from_match: boolean; allow_broadcast: boolean; script_timeout_sec: number };
}

export interface DoctorResponse {
  issues: Array<{ path: string; issue: string; repairable: boolean }>;
  repaired: boolean;
  count: number;
}

export interface BoxListItem {
  id: string;
  address: string;
  display_name: string;
  status: string;
  summary: string;
  capabilities: string[];
  unread: number;
  sent: number;
  failed: number;
}

export interface BoxDetail extends BoxListItem {
  issues: Array<{ path: string; issue: string }>;
  queue: {
    inbox_new: number;
    inbox_cur: number;
    outbox_new: number;
    outbox_sent: number;
    outbox_failed: number;
  };
  created_at?: string;
  scan_interval_sec?: number;
  box_root?: string;
}

export interface RegisterBoxRequest {
  id: string;
  display_name: string;
  summary: string;
  capabilities: string[];
  scan_interval_sec: number;
}

export interface RegisterBoxResponse {
  id: string;
  address: string;
  box_root: string;
  token: string;
}

export interface PatchBoxRequest {
  status?: string;
  display_name?: string;
  summary?: string;
}

export interface PatchBoxResponse {
  id: string;
  status: string;
}

export interface AddrbookEntry {
  address: string;
  display_name: string;
  summary: string;
  capabilities: string[];
  status: string;
}

export interface MessageSummary {
  message_id: string;
  from: string;
  to: string[];
  subject: string;
  type: string;
  priority: string;
  date: string;
  labels: string[];
  thread_id: string;
  in_reply_to: string | null;
  _file: string;
  _folder?: string;
  has_attachments?: boolean;
}

export interface MessageDetail extends MessageSummary {
  body: string;
  attachments: Array<{
    name: string;
    path: string;
    media_type: string;
    sha256: string;
  }>;
  cc?: string[];
  protocol?: string;
  routing?: Record<string, unknown>;
}

export interface ComposeRequest {
  to: string[];
  cc?: string[];
  subject: string;
  body: string;
  type: string;
  priority: string;
  thread_id?: string;
  in_reply_to?: string | null;
  ack: boolean;
  labels: string[];
  attachments?: Array<{ filename: string; content_base64: string; media_type?: string }>;
}

export interface ComposeResponse {
  status: string;
  message_id: string;
  from: string;
  filename: string;
}

export interface FileEntry {
  name: string;
  type: 'dir' | 'file';
  path: string;
  size?: number;
  modified?: number;
}

export interface MemoryResponse {
  episodic: Array<Record<string, unknown>>;
  semantic: Record<string, unknown>;
}

export interface SkillsResponse {
  manifest: Record<string, unknown>;
  recent: Array<{
    message_id?: string;
    skill?: string;
    status?: string;
    duration_ms?: number;
    notes?: string;
    [key: string]: unknown;
  }>;
}

export interface LogEntry {
  timestamp: string;
  action: string;
  [key: string]: unknown;
}

export interface SpoolResponse {
  depths: Record<string, number>;
  dead_letter: Array<{
    id: string;
    from: string;
    to: string[];
    subject: string;
    reason: string;
    created_at: string;
    [key: string]: unknown;
  }>;
}

export interface WSEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp?: string;
}
