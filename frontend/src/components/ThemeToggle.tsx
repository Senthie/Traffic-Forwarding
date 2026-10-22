import { Monitor, Moon, Sun } from 'lucide-react'
import type { ThemeMode } from '../lib/theme'
import { cn } from './ui'

const OPTIONS: Array<{ value: ThemeMode; label: string; Icon: typeof Sun }> = [
  { value: 'system', label: '跟随系统', Icon: Monitor },
  { value: 'light', label: '亮色', Icon: Sun },
  { value: 'dark', label: '暗色', Icon: Moon },
]

export function ThemeToggle({
  mode,
  onChange,
}: {
  mode: ThemeMode
  onChange: (mode: ThemeMode) => void
}) {
  return (
    <div
      role="group"
      aria-label="主题"
      className="flex items-center gap-0.5 rounded-md border border-line bg-panel-2 p-0.5"
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = mode === value
        return (
          <button
            key={value}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={active}
            onClick={() => onChange(value)}
            className={cn(
              'rounded p-1 transition-colors',
              active
                ? 'bg-chip text-ink'
                : 'text-ink-4 hover:bg-hover hover:text-ink-2',
            )}
          >
            <Icon size={14} strokeWidth={2} />
          </button>
        )
      })}
    </div>
  )
}
