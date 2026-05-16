import type { LucideIcon } from 'lucide-react';
import { cn } from '../utils/cn';

interface Props {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: Props) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-16 px-4 text-center', className)}>
      <div
        className="w-12 h-12 rounded-full flex items-center justify-center mb-4"
        style={{ background: 'var(--gm-bg-hover)', color: 'var(--gm-text-muted)' }}
      >
        <Icon size={22} />
      </div>
      <h3 className="text-base font-semibold mb-1" style={{ color: 'var(--gm-text-primary)' }}>
        {title}
      </h3>
      <p className="text-sm max-w-sm mb-4" style={{ color: 'var(--gm-text-secondary)' }}>
        {description}
      </p>
      {action && (
        <button className="gm-btn gm-btn-secondary text-sm" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
