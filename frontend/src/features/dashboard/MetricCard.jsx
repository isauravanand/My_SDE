import React from 'react';
import { cn } from '../../lib/utils';

export function MetricCard({ title, value, subtitle, icon: Icon, className }) {
  return (
    <div
      className={cn(
        'p-5 rounded-lg bg-background-card border border-border-subtle hover:border-border-strong transition-colors',
        className
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-wider text-content-secondary">
          {title}
        </span>
        {Icon && (
          <div className="p-2 rounded-md bg-background-subtle border border-border-subtle text-accent/80">
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold tracking-tight text-content-primary font-mono">
          {value}
        </span>
      </div>
      {subtitle && (
        <p className="mt-1 text-xs text-content-muted leading-normal">
          {subtitle}
        </p>
      )}
    </div>
  );
}
