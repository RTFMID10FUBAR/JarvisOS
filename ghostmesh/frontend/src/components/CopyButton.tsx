import { Check, Copy } from 'lucide-react';
import { useState } from 'react';

interface Props {
  value: string;
  size?: number;
}

export function CopyButton({ value, size = 14 }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <button
      onClick={handleCopy}
      className="p-1 rounded transition-colors hover:bg-[var(--gm-bg-hover)]"
      style={{ color: copied ? 'var(--gm-teal)' : 'var(--gm-text-muted)' }}
      title="Copy to clipboard"
      aria-label="Copy"
    >
      {copied ? <Check size={size} /> : <Copy size={size} />}
    </button>
  );
}
