import React from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, ArrowLeft } from 'lucide-react';

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
      <div className="w-12 h-12 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center mb-4">
        <AlertCircle className="w-6 h-6 text-accent" />
      </div>
      <h1 className="text-2xl font-bold text-content-primary mb-2">404 — Page Not Found</h1>
      <p className="text-sm text-content-secondary max-w-sm mb-6 leading-relaxed">
        The route you are navigating to does not exist in the MySDE application.
      </p>
      <Link
        to="/"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-accent text-background text-sm font-semibold hover:bg-accent-hover transition-colors shadow-subtle"
      >
        <ArrowLeft className="w-4 h-4" />
        Return to Dashboard
      </Link>
    </div>
  );
}
