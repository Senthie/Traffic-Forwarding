import { useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { api } from '../api/client'
import type { InterfaceInfo, ScanResult } from '../api/types'
import { Button, Spinner, cn } from '../components/ui'

interface Props {
  interfaces: InterfaceInfo[]
  loading: boolean
  onError: (message: string) => void
  onRefresh: () => void
}

interface ScanCase {
  iface: InterfaceInfo
  prefix: number
}

function ipv4ToInt(address: string): number {
  return address.split('.').reduce((acc, part) => ((acc << 8) | (Number(part) & 0xff)) >>> 0, 0)
}

function intToIpv4(value: number): string {
  return [value >>> 24, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff].join('.')
}

function networkOf(address: string, prefix: number): string {
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0
  return `${intToIpv4((ipv4ToInt(address) & mask) >>> 0)}/${prefix}`
}

function hostCount(prefix: number): number {
  if (prefix >= 31) return 0
  return 2 ** (32 - prefix) - 2
}

function formatTime(value: string): string {
  return value.replace('T', ' ').slice(0, 19)
}

interface IpRange {
  start: string
  end: string
}

/** 从已扫描网段里推导出未被占用的地址段（最多处理 4096 个地址）。 */
function freeRanges(network: string, total: number, used: Set<string>): IpRange[] | null {
  const [base, prefixText] = network.split('/')
  const prefix = Number(prefixText)
  if (!Number.isFinite(prefix) || !base) return null

  const baseInt = ipv4ToInt(base)
  const size = 2 ** (32 - prefix)
  const start = prefix >= 31 ? baseInt : baseInt + 1
  const count = Math.min(prefix >= 31 ? size : size - 2, total)
  if (count <= 0 || count > 4096) return null

  const ranges: IpRange[] = []
  let rangeStart = -1
  let rangeEnd = -1
  for (let index = 0; index < count; index += 1) {
    const value = start + index
    if (used.has(intToIpv4(value))) {
      if (rangeStart >= 0) {
        ranges.push({ start: intToIpv4(rangeStart), end: intToIpv4(rangeEnd) })
        rangeStart = -1
      }
    } else {
      if (rangeStart < 0) rangeStart = value
      rangeEnd = value
    }
  }
  if (rangeStart >= 0) {
    ranges.push({ start: intToIpv4(rangeStart), end: intToIpv4(rangeEnd) })
  }
  return ranges
}

const MAX_HOSTS = 1024

export default function ScanPage({ interfaces, loading, onError, onRefresh }: Props) {
  const [results, setResults] = useState<Record<string, ScanResult>>({})
  const [running, setRunning] = useState<Record<string, boolean>>({})
  const [scanningAll, setScanningAll] = useState(false)

  const engineQuery = useQuery({
    queryKey: ['scan-engine'],
    queryFn: () => api.scanEngine(),
    staleTime: 30000,
    retry: 0,
  })

  const scannable: ScanCase[] = interfaces
    .filter((iface) => iface.prefix_length !== null && !iface.is_loopback && !iface.address.startsWith('127.'))
    .map((iface) => ({ iface, prefix: iface.prefix_length as number }))

  const runScan = useCallback(
    async ({ iface, prefix }: ScanCase, scope: 'auto' | 'full') => {
      const base = `${iface.address}/${prefix}`
      const opKey = `${base}:${scope}`
      setRunning((current) => ({ ...current, [opKey]: true }))
      try {
        const result = await api.scanArp({
          address: iface.address,
          prefix_length: prefix,
          scope,
          timeout: 2.5,
        })
        setResults((current) => ({ ...current, [base]: result }))
      } catch (error) {
        onError(`扫描 ${iface.alias} 失败：${(error as Error).message}`)
      } finally {
        setRunning((current) => {
          const next = { ...current }
          delete next[opKey]
          return next
        })
      }
    },
    [onError],
  )

  const scanAll = useCallback(async () => {
    if (scannable.length === 0) return
    setScanningAll(true)
    try {
      await Promise.all(scannable.map((item) => runScan(item, 'auto')))
    } finally {
      setScanningAll(false)
    }
  }, [runScan, scannable])

  const engine = engineQuery.data
  const busy = Object.keys(running).length > 0 || scanningAll

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">网段扫描</h2>
          <p className="mt-0.5 text-xs text-ink-3">
            按网卡逐个扫描：发送 ARP 请求，列出该网段中已被占用的 IP。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={onRefresh} disabled={loading || busy}>
            {loading ? <Spinner /> : null}
            刷新网卡
          </Button>
          <Button variant="primary" onClick={() => void scanAll()} disabled={busy || scannable.length === 0}>
            {scanningAll ? <Spinner /> : null}
            扫描全部网卡
          </Button>
        </div>
      </div>

      {engineQuery.isError ? (
        <div className="rounded-lg border border-bad-line bg-bad-bg px-4 py-3 text-sm text-bad-ink">
          无法读取扫描引擎状态：{(engineQuery.error as Error).message}
        </div>
      ) : null}

      {engine ? (
        engine.npcap_available ? (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-ok-line bg-ok-bg px-4 py-2.5 text-xs text-ok-ink">
            <span className="text-sm font-medium">真 ARP 扫描引擎已就绪</span>
            <span className="font-mono">Npcap {engine.npcap_version ?? ''}</span>
            <span className="font-mono text-ink-3">{engine.npcap_path}</span>
            {!engine.admin ? (
              <span className="text-warn-ink">当前非管理员；若安装时勾选了「仅管理员访问」，扫描会自动回退。</span>
            ) : null}
          </div>
        ) : (
          <div className="rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-ink">
            <p className="font-medium">未检测到 Npcap，当前使用邻居表回退引擎</p>
            <p className="mt-1 text-xs leading-relaxed">{engine.note ?? engine.reason}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <a
                className="text-xs font-medium underline underline-offset-2"
                href="https://npcap.com/#download"
                target="_blank"
                rel="noreferrer"
              >
                下载 Npcap（免费）
              </a>
              <Button
                variant="ghost"
                className="px-1.5 py-0.5 text-xs"
                onClick={() => {
                  void engineQuery.refetch()
                  onRefresh()
                }}
              >
                重新检测
              </Button>
            </div>
          </div>
        )
      ) : null}

      {loading && interfaces.length === 0 ? (
        <div className="flex items-center justify-center gap-2 rounded-lg border border-line bg-panel py-16 text-sm text-ink-3">
          <Spinner /> 正在读取网卡…
        </div>
      ) : null}

      {!loading && scannable.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line bg-panel py-16 text-center">
          <p className="text-sm text-ink-3">没有可扫描的网卡</p>
          <p className="mt-1 text-xs text-ink-4">回环地址已自动排除；请确认网卡已连接并获取到 IPv4 地址。</p>
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-2">
        {scannable.map((item) => {
          const { iface, prefix } = item
          const base = `${iface.address}/${prefix}`
          const quick = networkOf(iface.address, Math.max(prefix, 24))
          const full = networkOf(iface.address, prefix)
          const quickKey = `${base}:auto`
          const fullKey = `${base}:full`
          const result = results[base]
          const fullHosts = hostCount(prefix)
          return (
            <section key={base} className="flex flex-col rounded-lg border border-line bg-panel">
              <header className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">{iface.alias}</p>
                  <p className="mt-0.5 font-mono text-xs text-ink-3">
                    {iface.address}/{prefix}
                    <span className="ml-2 text-ink-4">网段 {quick}</span>
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {prefix < 24 ? (
                    <>
                      <Button
                        variant="secondary"
                        onClick={() => void runScan(item, 'auto')}
                        disabled={running[quickKey] || scanningAll}
                        title={`只扫描 ${quick} 的 254 个地址`}
                      >
                        {running[quickKey] ? <Spinner /> : null}
                        快速 /24
                      </Button>
                      <Button
                        variant="secondary"
                        onClick={() => void runScan(item, 'full')}
                        disabled={running[fullKey] || scanningAll}
                        title={
                          fullHosts > MAX_HOSTS
                            ? `${full} 共 ${fullHosts} 个地址，超过上限，只扫前 ${MAX_HOSTS} 个`
                            : `扫描 ${full} 的 ${fullHosts} 个地址`
                        }
                      >
                        {running[fullKey] ? <Spinner /> : null}
                        完整 /{prefix}
                        {fullHosts > MAX_HOSTS ? <span className="text-[10px] text-warn-ink">（限 {MAX_HOSTS}）</span> : null}
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="secondary"
                      onClick={() => void runScan(item, 'auto')}
                      disabled={running[quickKey] || scanningAll}
                    >
                      {running[quickKey] ? <Spinner /> : null}
                      扫描
                    </Button>
                  )}
                </div>
              </header>

              {result ? (
                <ScanResultView result={result} />
              ) : (
                <p className="px-4 py-8 text-center text-xs text-ink-4">
                  尚未扫描 · 点击「{prefix < 24 ? '快速 /24' : '扫描'}」开始
                </p>
              )}
            </section>
          )
        })}
      </div>

      <p className="text-center text-[11px] text-ink-4">
        真 ARP 扫描需要 Npcap；未安装时自动回退为「UDP 触发 ARP + 读取邻居表」，结果可能偏少。
        扫描只读取本机所在网段，不会修改任何系统配置。
      </p>
    </div>
  )
}

function ScanResultView({ result }: { result: ScanResult }) {
  const { summary, hosts } = result
  const npcap = summary.engine === 'npcap'
  const used = new Set(hosts.map((host) => host.ip))
  const ranges = freeRanges(summary.network, summary.total, used)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-panel-2 px-4 py-2 text-xs text-ink-3">
        <span className="font-mono text-ink-2">{summary.network}</span>
        <span>
          在线 <b className="text-ok-ink">{summary.alive}</b>
        </span>
        <span>
          空闲 <b className="text-ink-2">{summary.idle}</b>
        </span>
        <span>共扫 {summary.total}</span>
        <span>{summary.elapsed_ms.toFixed(0)} ms</span>
        <span
          className={cn(
            'rounded border px-1.5 py-0.5 text-[10px] font-medium',
            npcap
              ? 'border-ok-line bg-ok-bg text-ok-ink'
              : 'border-warn-line bg-warn-bg text-warn-ink',
          )}
          title={npcap ? '原始 ARP 报文扫描' : 'UDP 触发 ARP + 邻居表'}
        >
          {npcap ? 'Npcap ARP' : '邻居表回退'}
        </span>
        <span className="ml-auto text-ink-4">{formatTime(summary.checked_at)}</span>
      </div>

      {summary.warning ? (
        <p className="border-b border-warn-line bg-warn-bg px-4 py-2 text-xs text-warn-ink">{summary.warning}</p>
      ) : null}

      {ranges && ranges.length > 0 ? (
        <details className="group border-b border-line px-4 py-2">
          <summary className="cursor-pointer text-xs text-ink-3 select-none hover:text-ink-2">
            查看空闲（可用）IP 段 · {ranges.length} 段 / 共 {summary.idle} 个
            {summary.truncated ? '（仅已扫描部分）' : ''}
          </summary>
          <p className="mt-1.5 break-all font-mono text-[11px] leading-relaxed text-ink-2">
            {ranges
              .map((range) => (range.start === range.end ? range.start : `${range.start} - ${range.end}`))
              .join('，')}
          </p>
        </details>
      ) : null}

      {hosts.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-ink-4">该网段没有发现任何在线设备</p>
      ) : (
        <ul className="max-h-72 divide-y divide-line overflow-y-auto">
          {hosts.map((host) => (
            <li key={host.ip} className="flex items-center justify-between gap-3 px-4 py-1.5 text-sm">
              <span className="flex items-center gap-2">
                <span className="font-mono text-link">{host.ip}</span>
                {host.is_local ? (
                  <span className="rounded bg-info-bg px-1.5 py-0.5 text-[10px] font-medium text-info-ink">本机</span>
                ) : null}
              </span>
              <span className="font-mono text-xs text-ink-3">{host.mac ? host.mac.toUpperCase() : '—'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
