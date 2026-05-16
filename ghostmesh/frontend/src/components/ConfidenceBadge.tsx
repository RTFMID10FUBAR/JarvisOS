import { cn } from '../utils/cn';

interface Props {
  score: number; // 0-100
  size?: 'sm' | 'md';
}

function getColor(score: number): { bg: string; text: string } {
  if (score >= 75) return { bg: 'rgba(57,211,83,0.15)',  text: 'var(--gm-teal)'   };
  if (score >= 45) return { bg: 'rgba(240,167,50,0.15)', text: 'var(--gm-yellow)' };
  return           { bg: 'rgba(248,81,73,0.15)',  text: 'var(--gm-red)'    };
}

export function ConfidenceBadge({ score, size = 'md' }: Props) {
  const { bg, text } = getColor(score);
  return (
    <span
      className={cn(
        'inline-flex items-center font-mono font-semibold rounded px-1.5',
        size === 'sm' ? 'text-xs py-0.5' : 'text-sm py-0.5',
      )}
      style={{ background: bg, color: text }}
      title={`Confidence: ${score}%`}
    >
      {score}%
    </span>
  );
}
