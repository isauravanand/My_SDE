import React from 'react';
import { cn } from '../../lib/utils';

export function StatusBadge({ status, label, className }) {
  const statusStyles = {
    connected: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    disconnected: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    pending: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
    neutral: 'bg-content-muted/10 text-content-secondary border-border-subtle',
  };

  const dotStyles = {
    connected: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]',
    disconnected: 'bg-rose-400',
    pending: 'bg-amber-400 animate-pulse',
    neutral: 'bg-content-muted',
  };

  const currentStatus = statusStyles[status] || statusStyles.neutral;
  const currentDot = dotStyles[status] || dotStyles.neutral;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border',
        currentStatus,
        className
      )}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full', currentDot)} />
      {label || status}
    </span>
  );
}
