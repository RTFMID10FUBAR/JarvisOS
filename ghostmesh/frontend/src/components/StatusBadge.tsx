import { cn } from '../utils/cn';
import type { ServiceStatus } from '../types';

interface Props {
  status: ServiceStatus;
  label?: string;
  size?: 'sm' | 'md';
}

const config: Record<ServiceStatus, { dot: string; text: string; label: string }> = {
  online:  { dot: 'bg-[var(--gm-teal)]',        text: 'text-[var(--gm-teal)]',        label: 'Online'   },
  offline: { dot: 'bg-[var(--gm-red)]',          text: 'text-[var(--gm-red)]',          label: 'Offline'  },
  degraded:{ dot: 'bg-[var(--gm-yellow)]',       text: 'text-[var(--gm-yellow)]',       label: 'Degraded' },
  unknown: { dot: 'bg-[var(--gm-text-muted)]',   text: 'text-[var(--gm-text-muted)]',   label: 'Unknown'  },
};

export function StatusBadge({ status, label, size = 'md' }: Props) {
  const c = config[status];
  return (
    <span className={cn('inline-flex items-center gap-1.5', size === 'sm' ? 'text-xs' : 'text-sm')}>
      <span
        className={cn('rounded-full', c.dot, size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2')}
        style={{ animation: status === 'online' ? 'pulse-dot 2s infinite' : undefined }}
      />
      <span className={c.text}>{label ?? c.label}</span>
    </span>
  );
}
