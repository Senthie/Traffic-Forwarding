import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { HealthInfo, Rule } from '../api/types'
import { AuditPanel } from '../components/AuditPanel'
import { DeleteDialog } from '../components/DeleteDialog'
import { RuleDialog } from '../components/RuleDialog'
import { RuleTable } from '../components/RuleTable'
import { ThemeToggle } from '../components/ThemeToggle'
import { Button, Spinner, cn } from '../components/ui'
import { useTheme } from '../lib/theme'

type Toast = { id: number; kind: 'success' | 'error' | 'info'; message: string }

const ADMIN_HINT = '当前未以管理员身份运行：可以查看与探测，但无法新建 / 修改 / 删除规则。'

export default function Dashboard() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [health, setHealth] = useState<Record<string, HealthInfo>>({})
  const [probingAll, setProbingAll] = useState(false)
  const [probingId, setProbingId] = useState<string | null>(null)
  const [autoProbe, setAutoProbe] = useState(true)
  const [auditToken, setAuditToken] = useState(0)
  const [dialog, setDialog] = useState<{ mode: 'create' | 'edit'; rule: Rule | null } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Rule | null>(null)
  const [elevating, setElevating] = useState(false)
  const { mode, setTheme } = useTheme()

  const pushToast = useCallback((kind: Toast['kind'], message: string) => {
    const id = Date.now() + Math.random()
    setToasts((current) => [...current, { id, kind, message }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== id))
    }, 6000)
  }, [])

  const statusQuery = useQuery({
    queryKey: ['status'],
    queryFn: api.status,
    refetchInterval: 30000,
    retry: 0,
  })

  const rulesQuery = useQuery({
    queryKey: ['rules'],
    queryFn: api.rules,
    refetchInterval: 20000,
    retry: 0,
  })

  const interfacesQuery = useQuery({
    queryKey: ['interfaces'],
    queryFn: () => api.interfaces(),
    staleTime: 60000,
    retry: 0,
  })

  const rules = rulesQuery.data ?? []
  const admin = statusQuery.data?.admin ?? false
  const hasRules = rules.length > 0

  const runProbeAll = useCallback(async () => {
    if (!hasRules) return
    setProbingAll(true)
    try {
      const data = await api.probeBatch()
      setHealth((current) => ({ ...current, ...data }))
    } catch (error) {
      pushToast('error', `批量探测失败：${(error as Error).message}`)
    } finally {
      setProbingAll(false)
    }
  }, [hasRules, pushToast])

  useEffect(() => {
    if (!autoProbe || !hasRules) return
    void runProbeAll()
    const timer = window.setInterval(() => void runProbeAll(), 30000)
    return () => window.clearInterval(timer)
  }, [autoProbe, hasRules, runProbeAll])

  const probeOne = useCallback(
    async (rule: Rule) => {
      setProbingId(rule.id)
      try {
        const result = await api.probeOne(rule.id)
        setHealth((current) => ({ ...current, [rule.id]: result }))
      } catch (error) {
        pushToast('error', `探测失败：${(error as Error).message}`)
      } finally {
        setProbingId(null)
      }
    },
    [pushToast],
  )

  const elevate = useCallback(async () => {
    setElevating(true)
    try {
      const result = await api.elevate()
      if (!result.started) {
        pushToast('info', result.reason ?? '提权请求未发起')
      } else {
        pushToast('info', '已发起提权启动，请在 UAC 弹窗中确认')
      }
    } catch (error) {
      pushToast('error', `提权失败：${(error as Error).message}`)
    } finally {
      setElevating(false)
    }
  }, [pushToast])

  const afterMutation = useCallback(
    (message: string) => {
      pushToast('success', message)
      setAuditToken((value) => value + 1)
      void rulesQuery.refetch()
      void statusQuery.refetch()
      window.setTimeout(() => void runProbeAll(), 300)
    },
    [pushToast, rulesQuery, statusQuery, runProbeAll],
  )

  const mergedHealth = rules.map((rule) => health[rule.id] ?? rule.health ?? null)
  const stats = {
    total: rules.length,
    healthy: mergedHealth.filter((item) => item?.state === 'healthy').length,
    halfOpen: mergedHealth.filter((item) => item?.state === 'half-open').length,
    down: mergedHealth.filter((item) => item?.state === 'down').length,
  }

  const backendDown = rulesQuery.isError || statusQuery.isError

  return (
    <div className="min-h-full bg-app">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-5 py-3">
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold text-ink">
              转发管理器
              <span
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[11px] font-medium',
                  admin
                    ? 'border-ok-line bg-ok-bg text-ok-ink'
                    : 'border-warn-line bg-warn-bg text-warn-ink',
                )}
              >
                {admin ? '管理员' : '只读'}
              </span>
            </h1>
            <p className="mt-0.5 text-xs text-ink-3">
              端口转发 · 防火墙 · 健康探测
              {statusQuery.data ? ` · v${statusQuery.data.version}` : ''}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <ThemeToggle mode={mode} onChange={setTheme} />
            <label className="mr-1 flex cursor-pointer items-center gap-1.5 text-xs text-ink-3">
              <input
                type="checkbox"
                className="size-3.5 accent-sky-500"
                checked={autoProbe}
                onChange={(event) => setAutoProbe(event.target.checked)}
              />
              自动探测 30s
            </label>

            <Button variant="secondary" onClick={() => void rulesQuery.refetch()}>
              刷新
            </Button>
            <Button variant="secondary" onClick={() => void runProbeAll()} disabled={probingAll}>
              {probingAll ? <Spinner /> : null}
              探测全部
            </Button>
            <Button
              variant="primary"
              onClick={() => setDialog({ mode: 'create', rule: null })}
              disabled={!admin}
              title={admin ? undefined : '需要管理员权限'}
            >
              + 新建规则
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-5 py-5">
        {backendDown ? (
          <div className="rounded-lg border border-bad-line bg-bad-bg px-4 py-3 text-sm text-bad-ink">
            无法连接本地后端（{(rulesQuery.error ?? statusQuery.error)?.message}）。
            请确认后端已启动，且由 <code className="font-mono">run_as_admin.ps1</code> 启动时具备管理员权限。
          </div>
        ) : null}

        {!backendDown && !admin ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-warn-line bg-warn-bg px-4 py-3">
            <p className="text-sm text-warn-ink">{ADMIN_HINT}</p>
            <Button variant="secondary" onClick={() => void elevate()} disabled={elevating}>
              {elevating ? <Spinner /> : null}
              以管理员身份重启
            </Button>
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="规则总数" value={stats.total} tone="slate" />
          <StatCard label="正常" value={stats.healthy} tone="emerald" />
          <StatCard label="仅监听" value={stats.halfOpen} tone="amber" />
          <StatCard label="不通" value={stats.down} tone="rose" />
        </div>

        <RuleTable
          rules={rules}
          health={health}
          admin={admin}
          loading={rulesQuery.isLoading}
          probingId={probingId}
          onProbe={(rule) => void probeOne(rule)}
          onEdit={(rule) => setDialog({ mode: 'edit', rule })}
          onDelete={(rule) => setDeleteTarget(rule)}
        />

        <AuditPanel refreshToken={auditToken} />

        <p className="text-center text-[11px] text-ink-4">
          规则读取自注册表 <span className="font-mono">PortProxy\v4tov4\tcp</span>；
          写操作通过 netsh 执行，全部记入审计日志。
        </p>
      </main>

      <RuleDialog
        open={dialog !== null}
        mode={dialog?.mode ?? 'create'}
        initial={dialog?.rule ?? null}
        interfaces={interfacesQuery.data ?? []}
        onClose={() => setDialog(null)}
        onSaved={afterMutation}
        onError={(message) => pushToast('error', message)}
      />

      <DeleteDialog
        rule={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onDeleted={afterMutation}
        onError={(message) => pushToast('error', message)}
      />

      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg',
              toast.kind === 'success' &&
                'border-ok-line bg-ok-bg text-ok-ink',
              toast.kind === 'error' && 'border-bad-line bg-bad-bg text-bad-ink',
              toast.kind === 'info' && 'border-line-strong bg-panel text-ink',
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  )
}

const TONES: Record<string, string> = {
  slate: 'text-ink',
  emerald: 'text-ok-ink',
  amber: 'text-warn-ink',
  rose: 'text-bad-ink',
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone: keyof typeof TONES
}) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <p className="text-xs text-ink-3">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold tabular-nums', TONES[tone])}>{value}</p>
    </div>
  )
}
