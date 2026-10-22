import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Rule } from '../api/types'
import { buildDeleteCommand, buildFirewallCommand } from '../lib/commands'
import { Button, CodeBlock, Modal, Spinner } from './ui'

interface Props {
  rule: Rule | null
  onClose: () => void
  onDeleted: (message: string) => void
  onError: (message: string) => void
}

export function DeleteDialog({ rule, onClose, onDeleted, onError }: Props) {
  const [deleteFirewall, setDeleteFirewall] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (rule) setDeleteFirewall(Boolean(rule.firewall_rule_name))
  }, [rule])

  if (!rule) return null

  const commands = [
    buildDeleteCommand(rule.listen_address, rule.listen_port),
    deleteFirewall && rule.firewall_rule_name
      ? buildFirewallCommand(rule.firewall_rule_name, rule.listen_port, 'Any', 'remove')
      : null,
  ]
    .filter(Boolean)
    .join('\n')

  async function submit() {
    setSubmitting(true)
    try {
      await api.remove(rule!.id, deleteFirewall && Boolean(rule!.firewall_rule_name))
      onDeleted(`已删除 ${rule!.listen_address}:${rule!.listen_port}`)
      onClose()
    } catch (error) {
      onError((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open
      title="删除转发规则"
      subtitle="操作不可撤销，请确认以下命令无误"
      onClose={onClose}
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            取消
          </Button>
          <Button variant="danger" onClick={submit} disabled={submitting}>
            {submitting ? <Spinner /> : null}
            确认删除
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="rounded-lg border border-bad-line bg-bad-bg px-3 py-2 text-sm text-bad-ink">
          {rule.name || '未命名规则'}：{rule.listen_address}:{rule.listen_port} →{' '}
          {rule.connect_address}:{rule.connect_port}
        </div>

        {rule.firewall_rule_name ? (
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="size-4 accent-rose-500"
              checked={deleteFirewall}
              onChange={(event) => setDeleteFirewall(event.target.checked)}
            />
            同时删除防火墙规则「{rule.firewall_rule_name}」
          </label>
        ) : null}

        <CodeBlock>{commands}</CodeBlock>
      </div>
    </Modal>
  )
}
