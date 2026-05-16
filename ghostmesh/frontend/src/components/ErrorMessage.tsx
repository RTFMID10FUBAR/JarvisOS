import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  title?: string;
  message: string;
  onRetry?: () => void;
  onDiagnostics?: () => void;
}

export function ErrorMessage({
  title = 'Service unavailable',
  message,
  onRetry,
  onDiagnostics,
}: Props) {
  return (
    <div className="gm-card border-[var(--gm-red)]/30 p-4">
      <div className="flex items-start gap-3">
        <AlertCircle size={18} className="mt-0.5 shrink-0" style={{ color: 'var(--gm-red)' }} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold mb-0.5" style={{ color: 'var(--gm-text-primary)' }}>
            {title}
          </p>
          <p className="text-sm" style={{ color: 'var(--gm-text-secondary)' }}>
            {message}
          </p>
          {(onRetry || onDiagnostics) && (
            <div className="flex gap-2 mt-3">
              {onRetry && (
                <button className="gm-btn gm-btn-secondary text-xs gap-1.5" onClick={onRetry}>
                  <RefreshCw size={12} /> Retry
                </button>
              )}
              {onDiagnostics && (
                <button className="gm-btn gm-btn-secondary text-xs" onClick={onDiagnostics}>
                  View diagnostics
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
