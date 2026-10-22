import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import { formatTime } from '../lib/commands'
import { Button, Spinner, cn } from './ui'

export function AuditPanel({ refreshToken }: { refreshToken: number }) {
  const [open, setOpen] = useState(false)

  const logsQuery = useQuery({
    queryKey: ['logs', refreshToken],
    queryFn: () => api.logs(60),
    enabled: open,
    staleTime: 2000,
  })

  return (
    <section className="rounded-lg border border-line bg-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-ink-2">
          <span className="text-ink-3">{open ? '▾' : '▸'}</span>
          审计日志
          {logsQuery.isFetching ? <Spinner className="text-ink-3" /> : null}
        </span>
        <span className="text-xs text-ink-4">记录每次实际执行的命令</span>
      </button>

      {open ? (
        <div className="border-t border-line px-4 py-3">
          {logsQuery.isLoading ? (
            <p className="py-4 text-center text-xs text-ink-3">加载中…</p>
          ) : !logsQuery.data?.length ? (
            <p className="py-4 text-center text-xs text-ink-3">暂无记录</p>
          ) : (
            <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {logsQuery.data.map((entry) => (
                <li
                  key={entry.id}
                  className="rounded-md border border-line bg-panel-2 px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span
                      className={cn(
                        'rounded px-1.5 py-0.5 font-mono text-[10px]',
                        entry.ok
                          ? 'bg-ok-bg text-ok-ink'
                          : 'bg-bad-bg text-bad-ink',
                      )}
                    >
                      {entry.action}
                    </span>
                    <span className="text-ink-3">{formatTime(entry.ts)}</span>
                    {entry.rule_id ? (
                      <span className="font-mono text-ink-3">{entry.rule_id}</span>
                    ) : null}
                  </div>
                  {entry.detail ? (
                    <p className="mt-1 text-xs text-ink-3">{entry.detail}</p>
                  ) : null}
                  {entry.command ? (
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-ink-3">
                      {entry.command}
                    </pre>
                  ) : null}
                  {entry.output ? (
                    <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-ink-4">
                      {entry.output}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 flex justify-end">
            <Button variant="ghost" onClick={() => void logsQuery.refetch()}>
              刷新
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
