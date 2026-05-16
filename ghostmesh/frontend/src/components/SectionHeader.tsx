import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

interface Props {
  icon?: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function SectionHeader({ icon: Icon, title, subtitle, actions }: Props) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div className="flex items-center gap-3">
        {Icon && (
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'rgba(47,129,247,0.15)', color: 'var(--gm-accent)' }}
          >
            <Icon size={16} />
          </div>
        )}
        <div>
          <h1
            className="text-lg font-semibold leading-tight"
            style={{ color: 'var(--gm-text-primary)' }}
          >
            {title}
          </h1>
          {subtitle && (
            <p className="text-sm mt-0.5" style={{ color: 'var(--gm-text-secondary)' }}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex items-center gap-2 shrink-0">{actions}</div>
      )}
    </div>
  );
}
