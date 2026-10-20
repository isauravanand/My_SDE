import React, { useState, useEffect } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { Terminal, CheckCircle2, AlertCircle, Loader2, ArrowRight } from 'lucide-react';
import { api } from '../../lib/api';

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const tokenFromUrl = searchParams.get('token') || '';

  const [token, setToken] = useState(tokenFromUrl);
  const [status, setStatus] = useState('idle'); // 'idle' | 'verifying' | 'success' | 'error'
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (tokenFromUrl) {
      handleVerify(tokenFromUrl);
    }
  }, [tokenFromUrl]);

  const handleVerify = async (tokenToVerify) => {
    if (!tokenToVerify) return;
    setStatus('verifying');
    setMessage('');

    try {
      const res = await api.verifyEmail(tokenToVerify);
      setStatus('success');
      setMessage(res.message || 'Your email has been verified successfully!');
    } catch (err) {
      setStatus('error');
      setMessage(err.message || 'Verification token is invalid or has expired.');
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
            Email Verification
          </h1>
          <p className="text-sm text-content-secondary mt-1.5">
            Confirm your identity to unlock automated repository interactions
          </p>
        </div>

        <div className="p-6 sm:p-8 rounded-xl bg-background-card border border-border-subtle shadow-card text-center">
          {status === 'verifying' && (
            <div className="py-6 flex flex-col items-center gap-3">
              <Loader2 className="w-8 h-8 text-accent animate-spin" />
              <p className="text-sm text-content-secondary">Verifying your token...</p>
            </div>
          )}

          {status === 'success' && (
            <div className="py-4 space-y-4">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 mx-auto flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h2 className="text-base font-semibold text-content-primary">Email Verified</h2>
              <p className="text-xs text-content-secondary">{message}</p>
              <Link
                to="/"
                className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-background text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                Go to Dashboard
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          )}

          {status === 'error' && (
            <div className="py-4 space-y-4">
              <div className="w-12 h-12 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 mx-auto flex items-center justify-center">
                <AlertCircle className="w-6 h-6" />
              </div>
              <h2 className="text-base font-semibold text-content-primary">Verification Failed</h2>
              <p className="text-xs text-rose-400">{message}</p>
              <div className="pt-2">
                <Link
                  to="/login"
                  className="text-xs text-accent hover:text-accent-hover font-medium"
                >
                  Return to sign in
                </Link>
              </div>
            </div>
          )}

          {status === 'idle' && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleVerify(token);
              }}
              className="space-y-4 text-left"
            >
              <div>
                <label className="block text-xs font-medium text-content-secondary mb-1.5" htmlFor="token">
                  Verification Token
                </label>
                <input
                  id="token"
                  type="text"
                  required
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste single-use token"
                  className="w-full px-3.5 py-2 rounded-lg bg-background-subtle border border-border-subtle text-sm text-content-primary placeholder:text-content-disabled font-mono focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
                />
              </div>
              <button
                type="submit"
                className="w-full py-2.5 rounded-lg bg-accent text-background text-sm font-semibold hover:bg-accent-hover transition-colors"
              >
                Verify Token
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
