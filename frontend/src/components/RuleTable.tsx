import type { HealthInfo, Rule } from '../api/types'
import { FirewallBadge, HealthBadge } from './Badges'
import { Button, Spinner, cn } from './ui'

interface Props {
  rules: Rule[]
  health: Record<string, HealthInfo>
  admin: boolean
  loading: boolean
  probingId: string | null
  onProbe: (rule: Rule) => void
  onEdit: (rule: Rule) => void
  onDelete: (rule: Rule) => void
}

const TH =
  'whitespace-nowrap px-2.5 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-3'
const TD = 'px-2.5 py-2.5 align-middle'

export function RuleTable({
  rules,
  health,
  admin,
  loading,
  probingId,
  onProbe,
  onEdit,
  onDelete,
}: Props) {
  if (loading && rules.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-lg border border-line bg-panel py-16 text-sm text-ink-3">
        <Spinner /> 正在读取注册表…
      </div>
    )
  }

  if (rules.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-line bg-panel py-16 text-center">
        <p className="text-sm text-ink-3">系统中还没有任何端口转发规则</p>
        <p className="mt-1 text-xs text-ink-4">
          点击右上角「新建规则」，或先在命令行执行 netsh interface portproxy add
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-panel">
      <table className="w-full border-collapse text-sm">
        <thead className="border-b border-line bg-panel-2">
          <tr>
            <th className={TH}>名称 / 备注</th>
            <th className={TH}>监听端</th>
            <th className={TH}>目标端</th>
            <th className={TH}>防火墙</th>
            <th className={TH}>健康</th>
            <th className={cn(TH, 'text-right')}>操作</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => {
            const current = health[rule.id] ?? rule.health ?? null
            const probing = probingId === rule.id
            return (
              <tr
                key={rule.id}
                className="border-b border-line transition-colors last:border-0 hover:bg-hover"
              >
                <td className={TD}>
                  <div className="flex flex-col">
                    <span
                      className={cn(
                        'whitespace-nowrap font-medium',
                        rule.name ? 'text-ink' : 'italic text-ink-3',
                      )}
                    >
                      {rule.name || '未命名'}
                    </span>
                    {rule.note ? (
                      <span className="mt-0.5 max-w-[22ch] truncate text-xs text-ink-3" title={rule.note}>
                        {rule.note}
                      </span>
                    ) : null}
                  </div>
                </td>
                <td className={cn(TD, 'font-mono text-[13px] text-link')}>
                  {rule.listen_address}:{rule.listen_port}
                  <span className="ml-2 hidden rounded bg-chip px-1 py-0.5 text-[10px] uppercase text-ink-3 lg:inline-block">
                    {rule.proto}
                  </span>
                </td>
                <td className={cn(TD, 'font-mono text-[13px] text-ink-2')}>
                  {rule.connect_address}:{rule.connect_port}
                </td>
                <td className={TD}>
                  <FirewallBadge firewall={rule.firewall} />
                </td>
                <td className={TD}>
                  <HealthBadge health={current} />
                </td>
                <td className={cn(TD, 'text-right whitespace-nowrap')}>
                  <Button
                    variant="ghost"
                    className="px-1.5"
                    onClick={() => onProbe(rule)}
                    disabled={probing}
                    title="单条探测"
                  >
                    {probing ? <Spinner /> : '探测'}
                  </Button>
                  <Button
                    variant="ghost"
                    className="px-1.5"
                    onClick={() => onEdit(rule)}
                    disabled={!admin}
                    title={admin ? '编辑' : '需要管理员权限'}
                  >
                    编辑
                  </Button>
                  <Button
                    variant="ghost"
                    className="px-1.5 text-bad-ink hover:bg-bad-bg"
                    onClick={() => onDelete(rule)}
                    disabled={!admin}
                    title={admin ? '删除' : '需要管理员权限'}
                  >
                    删除
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
