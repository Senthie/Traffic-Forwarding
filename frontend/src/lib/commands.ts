import type { RulePayload } from '../api/types'

const TABLE = 'v4tov4'

export function buildAddCommand(payload: RulePayload): string {
  return `netsh interface portproxy add ${TABLE} listenport=${payload.listen_port} listenaddress=${payload.listen_address} connectport=${payload.connect_port} connectaddress=${payload.connect_address}`
}

export function buildDeleteCommand(listenAddress: string, listenPort: number): string {
  return `netsh interface portproxy delete ${TABLE} listenaddress=${listenAddress} listenport=${listenPort}`
}

export function buildFirewallCommand(
  name: string,
  port: number,
  profiles: string,
  action: 'add' | 'remove' = 'add',
): string {
  if (action === 'remove') {
    return `Remove-NetFirewallRule -DisplayName "${name}"`
  }
  return `New-NetFirewallRule -DisplayName "${name}" -Direction Inbound -Protocol TCP -LocalPort ${port} -Action Allow -Profile ${profiles}`
}

export function buildFullCommand(payload: RulePayload): string {
  const lines: string[] = []
  if (payload.open_firewall) {
    lines.push(
      buildFirewallCommand(
        payload.firewall_rule_name || payload.name,
        payload.listen_port,
        payload.profiles,
      ),
    )
  }
  lines.push(buildAddCommand(payload))
  return lines.join('\n')
}

export function defaultFirewallName(name: string): string {
  return name.trim()
}

export function formatLatency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 1) return '<1 ms'
  return `${value.toFixed(0)} ms`
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}
