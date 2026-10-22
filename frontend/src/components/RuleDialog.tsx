import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { InterfaceInfo, Rule, RulePayload, ValidationIssue } from '../api/types'
import { buildFullCommand } from '../lib/commands'
import { Button, CodeBlock, Field, Input, Modal, Select, Spinner, cn } from './ui'

interface Props {
  open: boolean
  mode: 'create' | 'edit'
  initial: Rule | null
  interfaces: InterfaceInfo[]
  onClose: () => void
  onSaved: (message: string) => void
  onError: (message: string) => void
}

interface FormState {
  name: string
  note: string
  listen_address: string
  listen_port: string
  connect_address: string
  connect_port: string
  open_firewall: boolean
  firewall_rule_name: string
  profiles: string
}

const PROFILES = ['Any', 'Domain', 'Private', 'Public', 'Domain,Private', 'Private,Public']

function pickDefaultAddress(interfaces: InterfaceInfo[]): string {
  const preferred = interfaces.find((item) => !item.is_loopback)
  return preferred?.address ?? interfaces[0]?.address ?? '127.0.0.1'
}

function emptyForm(interfaces: InterfaceInfo[]): FormState {
  return {
    name: '',
    note: '',
    listen_address: pickDefaultAddress(interfaces),
    listen_port: '8889',
    connect_address: '',
    connect_port: '8889',
    open_firewall: true,
    firewall_rule_name: '',
    profiles: 'Any',
  }
}

function formFromRule(rule: Rule): FormState {
  return {
    name: rule.name ?? '',
    note: rule.note ?? '',
    listen_address: rule.listen_address,
    listen_port: String(rule.listen_port),
    connect_address: rule.connect_address,
    connect_port: String(rule.connect_port),
    open_firewall: Boolean(rule.firewall_rule_name),
    firewall_rule_name: rule.firewall_rule_name ?? '',
    profiles: rule.firewall?.profiles?.join(',') || 'Any',
  }
}

const ISSUE_STYLE: Record<ValidationIssue['level'], string> = {
  error: 'border-bad-line bg-bad-bg text-bad-ink',
  warning: 'border-warn-line bg-warn-bg text-warn-ink',
  info: 'border-line-strong bg-chip text-ink-2',
}

export function RuleDialog({
  open,
  mode,
  initial,
  interfaces,
  onClose,
  onSaved,
  onError,
}: Props) {
  const [form, setForm] = useState<FormState>(() => emptyForm(interfaces))
  const [issues, setIssues] = useState<ValidationIssue[]>([])
  const [validating, setValidating] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setIssues([])
    setForm(mode === 'edit' && initial ? formFromRule(initial) : emptyForm(interfaces))
  }, [open, mode, initial, interfaces])

  const payload: RulePayload = useMemo(
    () => ({
      name: form.name.trim(),
      note: form.note.trim() ? form.note.trim() : null,
      listen_address: form.listen_address,
      listen_port: Number(form.listen_port) || 0,
      connect_address: form.connect_address.trim(),
      connect_port: Number(form.connect_port) || 0,
      open_firewall: form.open_firewall,
      firewall_rule_name: form.firewall_rule_name.trim() || null,
      profiles: form.profiles,
    }),
    [form],
  )

  const canValidate =
    payload.name.length > 0 &&
    payload.listen_port > 0 &&
    payload.connect_port > 0 &&
    payload.connect_address.length > 0

  useEffect(() => {
    if (!open) return
    if (!canValidate) {
      setIssues([])
      return
    }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setValidating(true)
      try {
        // 编辑时要把"自己"排除掉，否则会与原有监听端冲突
        const selfId = mode === 'edit' ? initial?.id : null
        const result = await api.validate(payload, selfId)
        if (!cancelled) setIssues(result.issues)
      } catch (error) {
        if (!cancelled) {
          setIssues([{ level: 'error', field: null, message: (error as Error).message }])
        }
      } finally {
        if (!cancelled) setValidating(false)
      }
    }, 400)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [open, canValidate, payload, mode, initial])

  const hasError = issues.some((issue) => issue.level === 'error')

  async function submit() {
    if (hasError || !canValidate) return
    setSubmitting(true)
    try {
      if (mode === 'edit' && initial) {
        await api.update(initial.id, payload)
        onSaved(`已更新规则 ${payload.listen_address}:${payload.listen_port}`)
      } else {
        await api.create(payload)
        onSaved(`已创建规则 ${payload.listen_address}:${payload.listen_port}`)
      }
      onClose()
    } catch (error) {
      onError((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const title = mode === 'edit' ? '编辑转发规则' : '新建转发规则'

  return (
    <Modal
      open={open}
      title={title}
      subtitle={
        mode === 'edit'
          ? `原规则：${initial?.listen_address}:${initial?.listen_port} → ${initial?.connect_address}:${initial?.connect_port}`
          : '修改监听端或目标端会等价为「删除旧规则 + 新增规则」'
      }
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={submitting || hasError || !canValidate}
          >
            {submitting ? <Spinner /> : null}
            {mode === 'edit' ? '保存修改' : '创建规则'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="名称 *" hint="会同时用于派生防火墙规则名">
          <Input
            autoFocus
            value={form.name}
            placeholder="例如：ERP Forward"
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </Field>

        <Field label="备注">
          <Input
            value={form.note}
            placeholder="给三个月后的自己看的说明"
            onChange={(event) => setForm({ ...form, note: event.target.value })}
          />
        </Field>

        <Field label="监听地址 *" hint="必须是本机网卡上的 IP，否则规则永不生效">
          {interfaces.length > 0 ? (
            <Select
              value={form.listen_address}
              onChange={(event) => setForm({ ...form, listen_address: event.target.value })}
            >
              {interfaces.map((item) => (
                <option key={item.address} value={item.address}>
                  {item.address} — {item.alias}
                  {item.is_loopback ? '（环回）' : ''}
                </option>
              ))}
            </Select>
          ) : (
            <Input
              value={form.listen_address}
              onChange={(event) => setForm({ ...form, listen_address: event.target.value })}
            />
          )}
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="监听端口 *">
            <Input
              type="number"
              min={1}
              max={65535}
              value={form.listen_port}
              onChange={(event) => setForm({ ...form, listen_port: event.target.value })}
            />
          </Field>
          <Field label="协议">
            <Input value="TCP" disabled title="portproxy 不支持 UDP" />
          </Field>
        </div>

        <Field label="目标地址 *" hint="转发的实际后端服务">
          <Input
            value={form.connect_address}
            placeholder="例如：192.168.1.199"
            onChange={(event) => setForm({ ...form, connect_address: event.target.value })}
          />
        </Field>

        <Field label="目标端口 *">
          <Input
            type="number"
            min={1}
            max={65535}
            value={form.connect_port}
            onChange={(event) => setForm({ ...form, connect_port: event.target.value })}
          />
        </Field>

        <div className="sm:col-span-2 rounded-lg border border-line bg-panel-2 p-3">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="size-4 accent-sky-500"
              checked={form.open_firewall}
              onChange={(event) => setForm({ ...form, open_firewall: event.target.checked })}
            />
            同时开放 Windows 防火墙入站端口
          </label>

          {form.open_firewall ? (
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="防火墙规则名" hint="留空则使用上面的名称">
                <Input
                  value={form.firewall_rule_name}
                  placeholder={form.name || '与名称一致'}
                  onChange={(event) =>
                    setForm({ ...form, firewall_rule_name: event.target.value })
                  }
                />
              </Field>
              <Field label="作用域 profile">
                <Select
                  value={form.profiles}
                  onChange={(event) => setForm({ ...form, profiles: event.target.value })}
                >
                  {PROFILES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          ) : null}
        </div>

        <Field label="等价的 PowerShell 命令" className="sm:col-span-2">
          <CodeBlock>{buildFullCommand(payload) || '—'}</CodeBlock>
        </Field>

        <div className="sm:col-span-2">
          <div className="mb-1 flex items-center gap-2">
            <span className="text-xs font-medium text-ink-3">预检结果</span>
            {validating ? <Spinner className="text-ink-3" /> : null}
          </div>
          {issues.length === 0 ? (
            <p className="text-xs text-ink-4">
              {canValidate ? '未发现问题' : '填写完整后自动校验'}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {issues.map((issue, index) => (
                <li
                  key={`${issue.field ?? 'general'}-${index}`}
                  className={cn(
                    'rounded-md border px-2.5 py-1.5 text-xs',
                    ISSUE_STYLE[issue.level],
                  )}
                >
                  {issue.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  )
}
