import type {
  AuditEntry,
  HealthInfo,
  InterfaceInfo,
  OrphanRule,
  Rule,
  RulePayload,
  SystemStatus,
  ValidationResult,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => (item as { msg?: string }).msg ?? JSON.stringify(item))
          .join('；')
      }
    } catch {
      /* 保持默认消息 */
    }
    throw new Error(message)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export const api = {
  status: () => request<SystemStatus>('/system/status'),
  interfaces: (refresh = false) =>
    request<InterfaceInfo[]>(`/system/interfaces?refresh=${refresh}`),
  elevate: () =>
    request<{ started: boolean; reason: string | null }>('/system/elevate', {
      method: 'POST',
    }),

  rules: () => request<Rule[]>('/rules'),
  validate: (payload: RulePayload, excludeId?: string | null) =>
    request<ValidationResult>(
      `/rules/validate${excludeId ? `?exclude_id=${encodeURIComponent(excludeId)}` : ''}`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  create: (payload: RulePayload) =>
    request<Rule>('/rules', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id: string, payload: RulePayload) =>
    request<Rule>(`/rules/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  remove: (id: string, deleteFirewall: boolean) =>
    request<void>(
      `/rules/${encodeURIComponent(id)}?delete_firewall=${deleteFirewall}`,
      { method: 'DELETE' },
    ),

  probeBatch: (ids?: string[]) =>
    request<Record<string, HealthInfo>>('/probe/batch', {
      method: 'POST',
      body: JSON.stringify({ ids: ids ?? null }),
    }),
  probeOne: (id: string) =>
    request<HealthInfo>(`/probe/${encodeURIComponent(id)}`, { method: 'POST' }),

  logs: (limit = 60) => request<AuditEntry[]>(`/logs?limit=${limit}`),
  orphans: () => request<OrphanRule[]>('/firewall/orphans'),
  exportRules: () => request<{ version: number; exported_at: string; rules: unknown[] }>('/export'),
}
