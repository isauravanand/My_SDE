import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Terminal, Mail, CheckCircle2, AlertCircle, ArrowLeft, Loader2 } from 'lucide-react';
import { api } from '../../lib/api';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      await api.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Unable to submit password reset request.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-background-card border border-border-subtle text-accent shadow-card mb-4">
            <Terminal className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-content-primary">
            Reset Password
          </h1>
          <p className="text-sm text-content-secondary mt-1.5">
            Receive single-use instructions to recover your account
          </p>
        </div>

        <div className="p-6 sm:p-8 rounded-xl bg-background-card border border-border-subtle shadow-card">
          {submitted ? (
            <div className="text-center py-4 space-y-4">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h2 className="text-base font-semibold text-content-primary">Request Received</h2>
              <p className="text-xs text-content-secondary leading-relaxed">
                If an account with email <strong className="text-content-primary">{email}</strong> exists, password reset instructions have been dispatched.
              </p>
              <div className="pt-4 border-t border-border-subtle">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-xs text-accent hover:text-accent-hover font-medium"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Return to sign in
                </Link>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs flex items-start gap-2.5">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1.5" htmlFor="email">
                  Work Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-content-muted absolute left-3 top-3" />
                  <input
                    id="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="developer@company.com"
                    className="w-full pl-9 pr-3.5 py-2 rounded-lg bg-background-subtle border border-border-subtle text-sm text-content-primary placeholder:text-content-disabled focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full py-2.5 rounded-lg bg-accent text-background text-sm font-semibold hover:bg-accent-hover disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Sending link...
                  </>
                ) : (
                  'Send Reset Link'
                )}
              </button>

              <div className="mt-4 pt-4 border-t border-border-subtle text-center text-xs">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-1.5 text-content-secondary hover:text-content-primary"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to sign in
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
