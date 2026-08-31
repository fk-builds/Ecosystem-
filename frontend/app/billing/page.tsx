"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StudioShell, useStudioAuth } from "@/components/StudioShell";
import { api, ApiError, type BillingStatus, type PlanInfo } from "@/lib/api";

export default function BillingPage() {
  return (
    <StudioShell>
      <Billing />
    </StudioShell>
  );
}

function Billing() {
  const { user, refresh } = useStudioAuth();
  const router = useRouter();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void Promise.all([api.billingStatus(), api.plans()]).then(([s, p]) => {
      setStatus(s);
      setPlans(p.plans);
    }).catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load"));
  }, []);

  const upgrade = async (planId: string, interval: "month" | "year") => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.checkout(planId, interval);
      setMessage(
        result.demo
          ? `Sandbox mode: ${planId} activated instantly (no card charged). Add Stripe keys for real payments.`
          : "Redirecting to Stripe Checkout…"
      );
      if (result.url) {
        window.location.href = result.url;
        return;
      }
      await refresh();
      const s = await api.billingStatus();
      setStatus(s);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Checkout failed");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!window.confirm("Downgrade to Free? Your projects stay, but daily agent limits drop.")) return;
    setBusy(true);
    try {
      await api.cancel();
      await refresh();
      setStatus(await api.billingStatus());
      setMessage("Subscription cancelled — you're on the Free plan.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to cancel");
    } finally {
      setBusy(false);
    }
  };

  const downgraded = status && status.plan === "free";

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-slate-100">
      <header className="flex items-center justify-between border-b border-[#1c2740] bg-[#0e1526] px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 text-sm font-black text-slate-950">FK</div>
          <span className="text-sm font-semibold">Billing & plans</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link href="/dashboard" className="text-slate-400 hover:text-emerald-300">← Dashboard</Link>
          <span className="text-slate-500">{user?.email}</span>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        {status && (
          <div className="mb-8 flex flex-wrap items-center gap-4 rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Current plan</p>
              <p className="text-xl font-bold capitalize">{status.plan}</p>
            </div>
            <div className="text-sm text-slate-400">
              {status.usage_today}/{status.usage_limit} agent messages used today
              {status.period_end && <> · renews {new Date(status.period_end).toLocaleDateString()}</>}
            </div>
            <div className="ml-auto">
              {!downgraded && (
                <button
                  onClick={() => void cancel()}
                  disabled={busy}
                  className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-500/10 disabled:opacity-40"
                >
                  Cancel subscription
                </button>
              )}
              <span
                className={`ml-2 rounded-full px-2.5 py-1 text-xs ${
                  status.billing_mode === "stripe" ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"
                }`}
                title={status.billing_mode === "stripe" ? "Real payments via Stripe" : "Add STRIPE_SECRET_KEY to enable real payments"}
              >
                {status.billing_mode === "stripe" ? "live payments" : "sandbox (no real charge)"}
              </span>
            </div>
          </div>
        )}

        {message && <p className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">{message}</p>}
        {error && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">{error}</p>}

        <div className="grid gap-4 md:grid-cols-3">
          {plans.map((plan) => {
            const current = status?.plan === plan.id;
            return (
              <div key={plan.id} className={`flex flex-col rounded-2xl border p-5 ${current ? "border-emerald-400 bg-emerald-500/5" : "border-[#1c2740] bg-[#0e1526]"}`}>
                <p className="text-sm font-semibold text-slate-300">{plan.name}</p>
                <p className="text-xs text-slate-500">{plan.tagline}</p>
                <p className="mt-3 text-3xl font-bold">
                  ${plan.price_usd}
                  <span className="text-sm font-normal text-slate-500">/mo</span>
                </p>
                {plan.price_yearly_usd > 0 && <p className="text-xs text-slate-500">or ${plan.price_yearly_usd}/yr (save ~20%)</p>}
                <ul className="mt-4 flex-1 space-y-1.5 text-sm text-slate-300">
                  {plan.features.map((f) => (
                    <li key={f} className="flex gap-2"><span className="text-emerald-400">✓</span>{f}</li>
                  ))}
                </ul>
                {current ? (
                  <p className="mt-4 rounded-lg border border-emerald-500/30 py-2 text-center text-sm text-emerald-300">Current plan</p>
                ) : plan.id === "free" ? (
                  <p className="mt-4 rounded-lg border border-[#1c2740] py-2 text-center text-sm text-slate-500">Always free</p>
                ) : (
                  <div className="mt-4 space-y-2">
                    <button
                      onClick={() => void upgrade(plan.id, "month")}
                      disabled={busy}
                      className="w-full rounded-lg bg-emerald-500 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
                    >
                      Subscribe monthly
                    </button>
                    <button
                      onClick={() => void upgrade(plan.id, "year")}
                      disabled={busy}
                      className="w-full rounded-lg border border-emerald-500/40 py-2 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-40"
                    >
                      Subscribe yearly
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <p className="mt-6 text-center text-xs text-slate-500">
          Prices deliberately below market so anyone can afford an AI design agent. Cancel anytime — your projects stay on Free.
        </p>
      </main>
    </div>
  );
}
