import { cn } from '../utils/cn';

interface Props {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' };

export function Spinner({ size = 'md', className }: Props) {
  return (
    <div
      className={cn('rounded-full border-2 border-t-transparent animate-spin', sizes[size], className)}
      style={{ borderColor: 'var(--gm-border)', borderTopColor: 'var(--gm-accent)' }}
      role="status"
      aria-label="Loading"
    />
  );
}
