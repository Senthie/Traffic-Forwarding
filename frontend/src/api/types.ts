export type HealthState = 'healthy' | 'half-open' | 'down' | 'unknown'

export interface HealthInfo {
  state: HealthState
  listen_ok: boolean
  target_ok: boolean
  listen_latency_ms: number | null
  target_latency_ms: number | null
  checked_at: string | null
  error: string | null
}

export interface FirewallStatus {
  rule_name: string | null
  exists: boolean
  enabled: boolean
  action: string | null
  profiles: string[]
  reused_by: string | null
  available: boolean
  error: string | null
}

export interface Rule {
  id: string
  name: string | null
  note: string | null
  listen_address: string
  listen_port: number
  connect_address: string
  connect_port: number
  proto: string
  firewall_rule_name: string | null
  firewall: FirewallStatus | null
  health: HealthInfo | null
  is_named: boolean
  created_at: string | null
}

export interface RulePayload {
  name: string
  note: string | null
  listen_address: string
  listen_port: number
  connect_address: string
  connect_port: number
  open_firewall: boolean
  firewall_rule_name: string | null
  profiles: string
}

export interface ValidationIssue {
  level: 'error' | 'warning' | 'info'
  field: string | null
  message: string
}

export interface ValidationResult {
  ok: boolean
  issues: ValidationIssue[]
  normalized: RulePayload | null
  target_reachable: boolean | null
  listen_latency_ms: number | null
}

export interface InterfaceInfo {
  alias: string
  address: string
  prefix_length: number | null
  is_loopback: boolean
}

export interface FirewallProfile {
  Name?: string
  Enabled?: number | boolean
  name?: string
  enabled?: number | boolean
}

export interface SystemStatus {
  version: string
  admin: boolean
  host: string
  port: number
  data_dir: string
  probe_timeout: number
  firewall_available: boolean
  firewall_profiles: FirewallProfile[]
  interfaces_count: number
}

export interface AuditEntry {
  id: number
  ts: string
  action: string
  rule_id: string | null
  detail: string | null
  command: string | null
  returncode: number | null
  output: string | null
  ok: boolean
}

export interface OrphanRule {
  name: string
  port: string | number
  rule_id: string
  detail: string
}

export type ScanEngine = 'npcap' | 'fallback'

export interface ScanEngineInfo {
  engine: ScanEngine
  npcap_available: boolean
  npcap_version: string | null
  npcap_path: string | null
  admin: boolean
  reason: string | null
  note: string | null
}

export interface ScanRequest {
  address: string
  prefix_length: number
  scope: 'auto' | 'full'
  timeout?: number
}

export interface ScanHost {
  ip: string
  mac: string | null
  is_local: boolean
}

export interface ScanSummary {
  network: string
  prefix_length: number
  interface_alias: string | null
  interface_address: string
  engine: ScanEngine
  total: number
  alive: number
  idle: number
  elapsed_ms: number
  truncated: boolean
  warning: string | null
  checked_at: string
}

export interface ScanResult {
  summary: ScanSummary
  hosts: ScanHost[]
}
