import React from 'react';
import { cn } from '../../lib/utils';

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-8 sm:p-12 text-center rounded-lg border border-border-subtle bg-background-card/50',
        className
      )}
    >
      {Icon && (
        <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-background-subtle border border-border-subtle mb-4 text-content-secondary">
          <Icon className="w-6 h-6 text-accent/80" />
        </div>
      )}
      <h3 className="text-base font-medium text-content-primary mb-1.5">{title}</h3>
      {description && (
        <p className="text-sm text-content-secondary max-w-sm mb-6 leading-relaxed">
          {description}
        </p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
