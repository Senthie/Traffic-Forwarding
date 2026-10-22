import type { HealthInfo } from '../api/types'
import { formatLatency, formatTime } from '../lib/commands'
import { cn } from './ui'

const STATE_STYLE: Record<
  HealthInfo['state'],
  { label: string; dot: string; text: string; ring: string }
> = {
  healthy: {
    label: '正常',
    dot: 'bg-emerald-500',
    text: 'text-ok-ink',
    ring: 'bg-ok-bg border-ok-line',
  },
  'half-open': {
    label: '仅监听',
    dot: 'bg-amber-500',
    text: 'text-warn-ink',
    ring: 'bg-warn-bg border-warn-line',
  },
  down: {
    label: '不通',
    dot: 'bg-rose-500',
    text: 'text-bad-ink',
    ring: 'bg-bad-bg border-bad-line',
  },
  unknown: {
    label: '未探测',
    dot: 'bg-ink-4',
    text: 'text-ink-3',
    ring: 'bg-chip border-line',
  },
}

export function HealthBadge({ health }: { health: HealthInfo | null | undefined }) {
  const state = health?.state ?? 'unknown'
  const style = STATE_STYLE[state]

  const tooltip = health
    ? [
        `监听端：${health.listen_ok ? '通' : '不通'} ${formatLatency(health.listen_latency_ms)}`,
        `目标端：${health.target_ok ? '通' : '不通'} ${formatLatency(health.target_latency_ms)}`,
        health.checked_at ? `检测时间：${formatTime(health.checked_at)}` : '',
        health.error ?? '',
      ]
        .filter(Boolean)
        .join('\n')
    : '尚未探测'

  return (
    <span
      title={tooltip}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium',
        style.ring,
        style.text,
      )}
    >
      <span className={cn('size-1.5 rounded-full', style.dot)} />
      {style.label}
      {health?.state === 'healthy' && health.target_latency_ms != null ? (
        <span className="font-mono text-[11px] opacity-80">
          {formatLatency(health.target_latency_ms)}
        </span>
      ) : null}
    </span>
  )
}

export function FirewallBadge({
  firewall,
}: {
  firewall: import('../api/types').FirewallStatus | null | undefined
}) {
  if (!firewall) return <span className="text-xs text-ink-4">—</span>
  if (!firewall.available) {
    return (
      <span
        title={firewall.error ?? '需要管理员权限'}
        className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-line-strong bg-chip px-2 py-0.5 text-xs text-ink-3"
      >
        需管理员
      </span>
    )
  }
  if (firewall.exists) {
    const label = firewall.enabled ? '已开放' : '已禁用'
    return (
      <span
        title={[firewall.rule_name, firewall.profiles.join(', ')].filter(Boolean).join(' · ')}
        className={cn(
          'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs',
          firewall.enabled
            ? 'border-ok-line bg-ok-bg text-ok-ink'
            : 'border-warn-line bg-warn-bg text-warn-ink',
        )}
      >
        {label}
      </span>
    )
  }
  if (firewall.reused_by) {
    return (
      <span
        title={`端口已被其它规则覆盖：${firewall.reused_by}`}
        className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-info-line bg-info-bg px-2 py-0.5 text-xs text-info-ink"
      >
        复用
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-bad-line bg-bad-bg px-2 py-0.5 text-xs text-bad-ink">
      未开放
    </span>
  )
}
