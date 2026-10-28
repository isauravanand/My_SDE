import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CreditCard,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Sparkles,
  Zap,
  Users,
  ShieldCheck,
  ArrowRight,
  RefreshCw,
  X,
  FileText,
  HelpCircle,
} from 'lucide-react';
import { useAuth } from '../features/auth/AuthContext';
import { api } from '../lib/api';
import { LoadingSpinner } from '../components/common/LoadingSpinner';

const PLAN_ICONS = {
  free: Sparkles,
  pro: Zap,
  team: Users,
};

export function BillingPage() {
  const queryClient = useQueryClient();
  const { activeWorkspace } = useAuth();
  const workspaceId = activeWorkspace?.id;

  const [currency, setCurrency] = useState('INR');
  const [selectedPlan, setSelectedPlan] = useState(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);
  const [isCancelConfirmOpen, setIsCancelConfirmOpen] = useState(false);
  const [feedback, setFeedback] = useState(null);

  // 1. Fetch Subscription & Quotas
  const {
    data: subscription,
    isLoading: isSubLoading,
    refetch: refetchSub,
  } = useQuery({
    queryKey: ['billing', 'subscription', workspaceId],
    queryFn: () => api.getSubscription(workspaceId),
    enabled: !!workspaceId,
    staleTime: 10000,
  });

  // 2. Fetch Available Plans
  const {
    data: plans = [],
    isLoading: isPlansLoading,
  } = useQuery({
    queryKey: ['billing', 'plans'],
    queryFn: () => api.getBillingPlans(),
    staleTime: 60000,
  });

  // 3. Fetch Usage History
  const {
    data: usageHistory = [],
    isLoading: isHistoryLoading,
  } = useQuery({
    queryKey: ['billing', 'usage', workspaceId],
    queryFn: () => api.getUsageHistory(workspaceId, 25),
    enabled: !!workspaceId,
    staleTime: 15000,
  });

  // 4. Cancellation Mutation
  const cancelMutation = useMutation({
    mutationFn: () => api.cancelSubscription(workspaceId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['billing'] });
      setIsCancelConfirmOpen(false);
      setFeedback(data.message || 'Subscription will cancel at the end of the billing period.');
      setTimeout(() => setFeedback(null), 6000);
    },
    onError: (err) => {
      setFeedback(`Cancellation failed: ${err.message}`);
      setTimeout(() => setFeedback(null), 6000);
    },
  });

  // 5. Simulated / Sandbox Checkout Completion
  const handleSimulatePaymentSuccess = async (planCode) => {
    try {
      // Simulate verified server webhook payload
      const mockPayload = {
        event: 'order.paid',
        event_id: `sim_evt_${Date.now()}`,
        notes: {
          workspace_id: workspaceId,
          plan_code: planCode,
        },
      };
      // In mock provider mode, any signature or mock signature activates the verified server transition
      await api.simulateMockWebhook('mock', mockPayload, 'mock_signature_bypass');
      queryClient.invalidateQueries({ queryKey: ['billing'] });
      setIsCheckoutOpen(false);
      setSelectedPlan(null);
      setFeedback(`Successfully upgraded to ${planCode.toUpperCase()} plan.`);
      setTimeout(() => setFeedback(null), 6000);
    } catch (err) {
      setFeedback(`Checkout activation error: ${err.message}`);
      setTimeout(() => setFeedback(null), 6000);
    }
  };

  const handleOpenCheckout = (plan) => {
    setSelectedPlan(plan);
    setIsCheckoutOpen(true);
  };

  if (isSubLoading || isPlansLoading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center gap-3">
        <LoadingSpinner size="lg" />
        <p className="text-sm text-content-muted">Loading workspace subscription and quotas...</p>
      </div>
    );
  }

  const usage = subscription?.usage;
  const currentPlan = subscription?.plan;

  const agentRunPercent = usage ? Math.min(Math.round((usage.agent_runs_used / usage.agent_runs_limit) * 100), 100) : 0;
  const repairRunPercent = usage ? Math.min(Math.round((usage.repair_runs_used / usage.repair_runs_limit) * 100), 100) : 0;

  return (
    <div className="space-y-8 max-w-6xl pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-content-primary flex items-center gap-2">
            <CreditCard className="w-5 h-5 text-accent" />
            Subscription & Usage Metering
          </h1>
          <p className="text-sm text-content-secondary mt-1">
            Server-enforced quotas, auditable usage ledger, and billing plans for{' '}
            <span className="text-content-primary font-medium">{activeWorkspace?.name || 'Workspace'}</span>.
          </p>
        </div>

        <button
          onClick={() => refetchSub()}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md bg-background-subtle border border-border-subtle text-xs font-semibold text-content-secondary hover:text-content-primary hover:bg-background-hover transition-colors shrink-0"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh Quotas
        </button>
      </div>

      {/* Feedback Alert */}
      {feedback && (
        <div className="p-3.5 rounded-lg bg-background-subtle border border-accent/40 flex items-center justify-between text-xs text-content-primary animate-fade-in">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-accent shrink-0" />
            <span>{feedback}</span>
          </div>
          <button onClick={() => setFeedback(null)} className="text-content-muted hover:text-content-primary">
            &times;
          </button>
        </div>
      )}

      {/* Quota Exceeded Banner */}
      {(usage?.is_agent_runs_exceeded || usage?.is_repair_runs_exceeded) && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-rose-200">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-semibold text-rose-100">Monthly Usage Quota Reached</h3>
              <p className="text-xs text-rose-300/90 mt-0.5">
                {usage?.is_agent_runs_exceeded
                  ? 'Your workspace has consumed all allocated agent runs for this cycle.'
                  : 'Your automated repair budget has been exhausted.'}{' '}
                Upgrade your subscription to immediately unlock additional run capacity.
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              const upgradeTarget = plans.find((p) => p.plan_code === (currentPlan?.plan_code === 'free' ? 'pro' : 'team'));
              if (upgradeTarget) handleOpenCheckout(upgradeTarget);
            }}
            className="px-4 py-2 rounded-md bg-accent text-background font-semibold text-xs hover:bg-accent-hover transition-colors shrink-0 self-start sm:self-auto"
          >
            Upgrade Plan
          </button>
        </div>
      )}

      {/* Current Subscription Card */}
      <div className="p-6 rounded-xl bg-background-card border border-border-subtle shadow-subtle space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wider text-content-muted">
              Current Plan
            </span>
            <div className="flex items-center gap-3 mt-1">
              <h2 className="text-2xl font-bold tracking-tight text-content-primary">
                {currentPlan?.name || 'Free Starter'}
              </h2>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase border ${
                  subscription?.status === 'active'
                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                    : subscription?.status === 'past_due'
                    ? 'bg-rose-950/60 text-rose-300 border-rose-800/60'
                    : 'bg-zinc-800 text-zinc-400 border-zinc-700'
                }`}
              >
                {subscription?.status || 'active'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {currentPlan?.plan_code !== 'free' && !subscription?.cancel_at_period_end && (
              <button
                onClick={() => setIsCancelConfirmOpen(true)}
                className="px-3 py-1.5 rounded-md bg-background-subtle border border-border-subtle text-xs text-rose-400 hover:bg-rose-950/30 hover:border-rose-800/60 transition-colors font-medium"
              >
                Cancel Subscription
              </button>
            )}
            {subscription?.cancel_at_period_end && (
              <span className="text-xs text-amber-400 font-medium bg-amber-950/40 border border-amber-800/60 px-3 py-1.5 rounded-md">
                Cancels on cycle end
              </span>
            )}
          </div>
        </div>

        {/* Subscription Cycle Details */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div className="p-3.5 rounded-lg bg-background-subtle border border-border-subtle">
            <span className="text-content-muted block mb-1">Billing Period</span>
            <span className="font-mono text-content-primary font-medium">
              {new Date(subscription?.current_period_start).toLocaleDateString()} —{' '}
              {new Date(subscription?.current_period_end).toLocaleDateString()}
            </span>
          </div>

          <div className="p-3.5 rounded-lg bg-background-subtle border border-border-subtle">
            <span className="text-content-muted block mb-1">Payment Provider</span>
            <span className="font-mono text-content-primary capitalize font-medium">
              {subscription?.provider || 'Mock (Sandbox)'}
            </span>
          </div>

          <div className="p-3.5 rounded-lg bg-background-subtle border border-border-subtle">
            <span className="text-content-muted block mb-1">Standing & Entitlements</span>
            <span
              className={`font-semibold ${
                subscription?.is_in_good_standing ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {subscription?.is_in_good_standing ? 'In Good Standing' : 'Payment Required'}
            </span>
          </div>
        </div>
      </div>

      {/* Quota Usage Meters */}
      <div className="space-y-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-2">
          <Clock className="w-4 h-4 text-accent" />
          Billing Cycle Quotas & Concurrency
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Agent Runs Meter */}
          <div className="p-5 rounded-xl bg-background-card border border-border-subtle space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-content-secondary">Agent Executions</span>
              <span className="font-mono font-bold text-content-primary">
                {usage?.agent_runs_used} / {usage?.agent_runs_limit}
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-background-subtle overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  agentRunPercent >= 100
                    ? 'bg-rose-500'
                    : agentRunPercent >= 80
                    ? 'bg-amber-500'
                    : 'bg-accent'
                }`}
                style={{ width: `${agentRunPercent}%` }}
              />
            </div>
            <p className="text-[11px] text-content-muted">
              {usage?.agent_runs_limit - usage?.agent_runs_used} runs remaining this cycle
            </p>
          </div>

          {/* Repairs Meter */}
          <div className="p-5 rounded-xl bg-background-card border border-border-subtle space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-content-secondary">Self-Healing Repairs</span>
              <span className="font-mono font-bold text-content-primary">
                {usage?.repair_runs_used} / {usage?.repair_runs_limit}
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-background-subtle overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  repairRunPercent >= 100
                    ? 'bg-rose-500'
                    : repairRunPercent >= 80
                    ? 'bg-amber-500'
                    : 'bg-accent'
                }`}
                style={{ width: `${repairRunPercent}%` }}
              />
            </div>
            <p className="text-[11px] text-content-muted">
              {usage?.repair_runs_limit - usage?.repair_runs_used} automated repair runs remaining
            </p>
          </div>

          {/* Tokens Meter */}
          <div className="p-5 rounded-xl bg-background-card border border-border-subtle space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-content-secondary">Model Provider Tokens</span>
              <span className="font-mono font-bold text-content-primary">
                {Math.round((usage?.tokens_used || 0) / 1000)}k / {Math.round((usage?.tokens_limit || 0) / 1000)}k
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-background-subtle overflow-hidden">
              <div
                className="h-full bg-accent transition-all duration-300"
                style={{
                  width: `${Math.min(
                    Math.round(((usage?.tokens_used || 0) / (usage?.tokens_limit || 1)) * 100),
                    100
                  )}%`,
                }}
              />
            </div>
            <p className="text-[11px] text-content-muted">Token usage tracked from upstream provider</p>
          </div>

          {/* Concurrency Slots */}
          <div className="p-5 rounded-xl bg-background-card border border-border-subtle space-y-3">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-content-secondary">Parallel Execution</span>
              <span className="font-mono font-bold text-content-primary">
                {usage?.parallel_runs_active} / {usage?.max_parallel_runs} active
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-background-subtle overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-300"
                style={{
                  width: `${Math.min(
                    Math.round(((usage?.parallel_runs_active || 0) / (usage?.max_parallel_runs || 1)) * 100),
                    100
                  )}%`,
                }}
              />
            </div>
            <p className="text-[11px] text-content-muted">Concurrency ceiling for simultaneous sandboxes</p>
          </div>
        </div>
      </div>

      {/* Plan Selection Grid */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-accent" />
              Available Subscription Tiers
            </h3>
            <p className="text-xs text-content-muted mt-0.5">
              Choose the capacity tier that fits your engineering team size and throughput.
            </p>
          </div>

          {/* Currency Toggle */}
          <div className="inline-flex rounded-lg bg-background-card border border-border-subtle p-0.5 text-xs font-semibold">
            <button
              onClick={() => setCurrency('INR')}
              className={`px-3 py-1 rounded-md transition-colors ${
                currency === 'INR' ? 'bg-accent text-background' : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              INR (₹)
            </button>
            <button
              onClick={() => setCurrency('USD')}
              className={`px-3 py-1 rounded-md transition-colors ${
                currency === 'USD' ? 'bg-accent text-background' : 'text-content-secondary hover:text-content-primary'
              }`}
            >
              USD ($)
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
          {plans.map((plan) => {
            const isCurrent = currentPlan?.plan_code === plan.plan_code;
            const PlanIcon = PLAN_ICONS[plan.plan_code] || Sparkles;
            const price =
              currency === 'INR'
                ? plan.price_inr_cents === 0
                  ? '₹0'
                  : `₹${(plan.price_inr_cents / 100).toLocaleString()}`
                : plan.price_usd_cents === 0
                ? '$0'
                : `$${plan.price_usd_cents / 100}`;

            return (
              <div
                key={plan.id}
                className={`rounded-xl border p-6 flex flex-col justify-between transition-all ${
                  isCurrent
                    ? 'bg-background-card border-accent shadow-subtle'
                    : 'bg-background-card/60 border-border-subtle hover:border-border-strong'
                }`}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2 rounded-lg bg-accent/10 text-accent border border-accent/20">
                        <PlanIcon className="w-5 h-5" />
                      </div>
                      <div>
                        <h4 className="text-base font-bold text-content-primary">{plan.name}</h4>
                        <span className="text-[11px] text-content-muted capitalize">{plan.billing_interval}</span>
                      </div>
                    </div>
                    {isCurrent && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-accent/20 text-accent border border-accent/30">
                        Active
                      </span>
                    )}
                  </div>

                  <div className="pt-2">
                    <span className="text-3xl font-extrabold text-content-primary font-mono">{price}</span>
                    <span className="text-xs text-content-muted ml-1.5">/ month</span>
                  </div>

                  <p className="text-xs text-content-secondary leading-relaxed min-h-[36px]">
                    {plan.description}
                  </p>

                  <div className="pt-4 border-t border-border-subtle/80 space-y-2.5 text-xs text-content-secondary">
                    <div className="font-semibold text-content-primary text-[11px] uppercase tracking-wider mb-2">
                      Plan Inclusions
                    </div>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
                      <span><strong>{plan.monthly_agent_runs}</strong> agent execution runs / month</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
                      <span><strong>{plan.monthly_repair_runs}</strong> self-healing repair runs</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 text-accent shrink-0" />
                      <span><strong>{plan.max_parallel_runs}</strong> concurrent execution sandbox</span>
                    </div>
                    {plan.features?.map((feat, idx) => (
                      <div key={idx} className="flex items-center gap-2 capitalize">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                        <span>{feat.replace(/_/g, ' ')}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-6 mt-6 border-t border-border-subtle/60">
                  {isCurrent ? (
                    <button
                      disabled
                      className="w-full py-2.5 rounded-lg bg-background-subtle border border-border-subtle text-xs font-semibold text-content-muted cursor-default"
                    >
                      Current Plan
                    </button>
                  ) : (
                    <button
                      onClick={() => handleOpenCheckout(plan)}
                      className="w-full py-2.5 rounded-lg bg-accent text-background hover:bg-accent-hover font-semibold text-xs transition-colors flex items-center justify-center gap-1.5 shadow-subtle"
                    >
                      {plan.price_inr_cents > (currentPlan?.price_inr_cents || 0)
                        ? `Upgrade to ${plan.name}`
                        : `Switch to ${plan.name}`}
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Usage Ledger History */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-content-secondary flex items-center gap-2">
          <FileText className="w-4 h-4 text-accent" />
          Auditable Usage Ledger
        </h3>

        <div className="rounded-xl bg-background-card border border-border-subtle overflow-hidden">
          {isHistoryLoading ? (
            <div className="py-12 flex justify-center">
              <LoadingSpinner size="md" />
            </div>
          ) : usageHistory.length === 0 ? (
            <div className="p-8 text-center text-xs text-content-muted">
              No usage events recorded in this workspace ledger yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-background-subtle/80 border-b border-border-subtle text-[11px] font-semibold uppercase tracking-wider text-content-muted">
                  <tr>
                    <th className="py-3 px-4">Event Type</th>
                    <th className="py-3 px-4">Quantity</th>
                    <th className="py-3 px-4">Operation ID</th>
                    <th className="py-3 px-4">Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle/60 font-mono text-[11px]">
                  {usageHistory.map((item) => (
                    <tr key={item.id} className="hover:bg-background-hover/50">
                      <td className="py-3 px-4 text-content-primary font-sans font-medium">
                        {item.event_type.replace(/_/g, ' ')}
                      </td>
                      <td className="py-3 px-4 text-content-secondary">
                        +{item.quantity}
                      </td>
                      <td className="py-3 px-4 text-content-muted truncate max-w-xs" title={item.operation_id}>
                        {item.operation_id}
                      </td>
                      <td className="py-3 px-4 text-content-muted font-sans text-xs">
                        {new Date(item.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Checkout Modal */}
      {isCheckoutOpen && selectedPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="relative w-full max-w-md bg-background-card border border-border-subtle rounded-xl p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-md bg-accent/10 text-accent">
                  <CreditCard className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-content-primary">Plan Checkout</h3>
                  <span className="text-[11px] text-content-muted">Sandbox Payment Simulation</span>
                </div>
              </div>
              <button
                onClick={() => setIsCheckoutOpen(false)}
                className="text-content-muted hover:text-content-primary p-1 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 rounded-lg bg-background-subtle border border-border-subtle space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-content-muted">Upgrading to:</span>
                <span className="font-bold text-content-primary">{selectedPlan.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-content-muted">Billing Cycle:</span>
                <span className="font-mono text-content-secondary">Monthly Renewal</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-border-subtle">
                <span className="font-semibold text-content-primary">Amount Payable:</span>
                <span className="font-mono font-bold text-base text-accent">
                  {currency === 'INR'
                    ? `₹${(selectedPlan.price_inr_cents / 100).toLocaleString()}`
                    : `$${selectedPlan.price_usd_cents / 100}`}
                </span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-blue-950/30 border border-blue-800/40 text-[11px] text-blue-300 flex items-start gap-2">
              <HelpCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Running in safe sandbox/test mode. Activating this plan simulates verified payment webhook delivery.
                No credit card credentials are stored or charged.
              </span>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setIsCheckoutOpen(false)}
                className="px-4 py-2 rounded-md bg-background-subtle border border-border-subtle text-xs font-semibold text-content-secondary hover:text-content-primary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleSimulatePaymentSuccess(selectedPlan.plan_code)}
                className="px-4 py-2 rounded-md bg-accent text-background font-semibold text-xs hover:bg-accent-hover transition-colors shadow-subtle"
              >
                Confirm Upgrade
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cancellation Confirmation Modal */}
      {isCancelConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="relative w-full max-w-md bg-background-card border border-border-subtle rounded-xl p-6 shadow-2xl space-y-4">
            <h3 className="text-base font-bold text-content-primary">Cancel Subscription?</h3>
            <p className="text-xs text-content-secondary leading-relaxed">
              Your subscription will remain active until the end of the current billing cycle (
              {new Date(subscription?.current_period_end).toLocaleDateString()}). After this date, your workspace
              will automatically revert to the Free Starter tier quotas.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsCancelConfirmOpen(false)}
                className="px-4 py-2 rounded-md bg-background-subtle border border-border-subtle text-xs font-semibold text-content-secondary hover:text-content-primary"
              >
                Keep Subscription
              </button>
              <button
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                className="px-4 py-2 rounded-md bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs"
              >
                {cancelMutation.isPending ? 'Processing...' : 'Confirm Cancellation'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
