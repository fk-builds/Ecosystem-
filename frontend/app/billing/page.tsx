"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { StudioShell, useStudioAuth } from "@/components/StudioShell";
import {
  api,
  ApiError,
  type BillingStatus,
  type CheckoutResult,
  type PaymentRecord,
  type PlanInfo,
} from "@/lib/api";

export default function BillingPage() {
  return (
    <StudioShell>
      <Billing />
    </StudioShell>
  );
}

function Billing() {
  const { user, refresh } = useStudioAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [checkout, setCheckout] = useState<CheckoutResult | null>(null);
  const [txnRef, setTxnRef] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const [s, p, pays] = await Promise.all([api.billingStatus(), api.plans(), api.payments()]);
      setStatus(s);
      setPlans(p.plans);
      setPayments(pays.payments);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const upgrade = async (planId: string, interval: "month" | "year") => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.checkout(planId, interval);
      if (result.mode === "sandbox") {
        setMessage(`Sandbox: ${planId} activated instantly (no real charge).`);
        await refresh();
        await load();
      } else if (result.mode === "manual") {
        setCheckout(result);
        setMessage(null);
      } else if (result.mode === "jazzcash" && result.url) {
        submitForm(result.url, result.redirect_params);
      } else if (result.url) {
        window.location.href = result.url;
      } else {
        setMessage(result.instructions ?? "Checkout started — complete payment to activate.");
        if (result.order_id) setCheckout(result);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Checkout failed");
    } finally {
      setBusy(false);
    }
  };

  const submitConfirm = async (e: FormEvent) => {
    e.preventDefault();
    if (!checkout?.order_id || !txnRef.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.confirmPayment(checkout.order_id, txnRef.trim());
      setMessage("Transaction reference submitted — the owner will verify it and activate your plan.");
      setCheckout(null);
      setTxnRef("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit");
    } finally {
      setBusy(false);
    }
  };

  const adminAction = async (id: string, action: "approve" | "reject") => {
    setBusy(true);
    try {
      if (action === "approve") await api.approvePayment(id);
      else await api.rejectPayment(id, "Rejected by owner");
      await refresh();
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed");
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
      await load();
      setMessage("Subscription cancelled — you're on the Free plan.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to cancel");
    } finally {
      setBusy(false);
    }
  };

  const downgraded = status && status.plan === "free";
  const providerLabel: Record<string, string> = {
    auto: "auto",
    sandbox: "sandbox (no charge)",
    manual: "JazzCash / bank transfer + review",
    paddle: "Paddle cards (USD)",
    jazzcash: "JazzCash gateway (PKR)",
    stripe: "Stripe",
  };

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

      <main className="mx-auto max-w-5xl px-6 py-8">
        {status && (
          <div className="mb-6 flex flex-wrap items-center gap-4 rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">Current plan</p>
              <p className="text-xl font-bold capitalize">{status.plan}</p>
            </div>
            <div className="text-sm text-slate-400">
              {status.usage_today}/{status.usage_limit} agent messages used today
              {status.period_end && <> · renews {new Date(status.period_end).toLocaleDateString()}</>}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-300">
                {providerLabel[status.billing_mode] ?? status.billing_mode}
              </span>
              {status.is_admin && <span className="rounded-full bg-amber-500/10 px-2.5 py-1 text-xs text-amber-300">owner/admin</span>}
              {!downgraded && (
                <button onClick={() => void cancel()} disabled={busy} className="rounded-lg border border-rose-500/40 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-500/10 disabled:opacity-40">
                  Cancel
                </button>
              )}
            </div>
          </div>
        )}

        {message && <p className="mb-4 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">{message}</p>}
        {error && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">{error}</p>}

        {/* Manual / JazzCash payment instructions */}
        {checkout && checkout.mode === "manual" && (
          <div className="mb-6 rounded-2xl border border-emerald-500/40 bg-emerald-500/5 p-5">
            <h3 className="font-semibold text-emerald-300">Pay via JazzCash / EasyPaisa / bank — then confirm</h3>
            <p className="mt-1 text-sm text-slate-300">
              Order <code className="text-emerald-300">{checkout.order_id}</code> ·{" "}
              <span className="font-bold text-white">Rs. {(checkout.amount_pkr ?? 0).toLocaleString()}</span> ({checkout.plan}, {checkout.interval})
            </p>
            <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
              {checkout.account.jazzcash && <p><span className="text-slate-500">JazzCash:</span> <b>{checkout.account.jazzcash}</b></p>}
              {checkout.account.easypaisa && <p><span className="text-slate-500">EasyPaisa:</span> <b>{checkout.account.easypaisa}</b></p>}
              {checkout.account.iban && <p><span className="text-slate-500">Bank ({checkout.account.bank_name}):</span> <b>{checkout.account.iban}</b></p>}
              {checkout.account.account_title && <p><span className="text-slate-500">Account title:</span> <b>{checkout.account.account_title}</b></p>}
            </div>
            <p className="mt-3 text-xs text-slate-500">{checkout.instructions}</p>
            <form onSubmit={submitConfirm} className="mt-4 flex flex-wrap gap-2">
              <input
                value={txnRef}
                onChange={(e) => setTxnRef(e.target.value)}
                placeholder="Transaction reference / TRX id (e.g. 7728419021)"
                className="min-w-0 flex-1 rounded-lg border border-[#1c2740] bg-[#0a0f1a] px-3 py-2 text-sm outline-none focus:border-emerald-400"
              />
              <button disabled={busy || !txnRef.trim()} className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40">
                I've paid — confirm
              </button>
            </form>
          </div>
        )}

        {/* Plan cards */}
        <div className="grid gap-4 md:grid-cols-3">
          {plans.map((plan) => {
            const current = status?.plan === plan.id;
            return (
              <div key={plan.id} className={`flex flex-col rounded-2xl border p-5 ${current ? "border-emerald-400 bg-emerald-500/5" : "border-[#1c2740] bg-[#0e1526]"}`}>
                <p className="text-sm font-semibold text-slate-300">{plan.name}</p>
                <p className="text-xs text-slate-500">{plan.tagline}</p>
                <div className="mt-3">
                  <p className="text-3xl font-bold">
                    ${plan.price_usd}
                    <span className="text-sm font-normal text-slate-500">/mo</span>
                  </p>
                  {plan.price_pkr_month > 0 && (
                    <p className="text-sm text-emerald-300">Rs. {plan.price_pkr_month.toLocaleString()}/mo</p>
                  )}
                  {plan.price_yearly_usd > 0 && <p className="text-xs text-slate-500">${plan.price_yearly_usd}/yr or Rs. {plan.price_pkr_year.toLocaleString()}/yr</p>}
                </div>
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
                    <button onClick={() => void upgrade(plan.id, "month")} disabled={busy} className="w-full rounded-lg bg-emerald-500 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40">
                      Subscribe monthly
                    </button>
                    <button onClick={() => void upgrade(plan.id, "year")} disabled={busy} className="w-full rounded-lg border border-emerald-500/40 py-2 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-40">
                      Subscribe yearly
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Payments history / admin review */}
        <section className="mt-10">
          <h2 className="mb-3 text-lg font-semibold">Payments</h2>
          {payments.length === 0 ? (
            <p className="rounded-xl border border-dashed border-[#1c2740] p-6 text-center text-sm text-slate-500">
              No payments yet.
            </p>
          ) : (
            <div className="overflow-hidden rounded-xl border border-[#1c2740]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#0e1526] text-xs uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Order</th>
                    <th className="px-4 py-2">Plan</th>
                    <th className="px-4 py-2">Amount</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="px-4 py-2">Txn ref</th>
                    {status?.is_admin && <th className="px-4 py-2">Owner</th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1c2740]">
                  {payments.map((p) => (
                    <tr key={p.id} className="bg-[#0a0f1a]">
                      <td className="px-4 py-2 font-mono text-xs">{p.order_id}</td>
                      <td className="px-4 py-2 capitalize">{p.plan_id}</td>
                      <td className="px-4 py-2">Rs. {p.amount_pkr.toLocaleString()}</td>
                      <td className="px-4 py-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            p.status === "approved"
                              ? "bg-emerald-500/10 text-emerald-300"
                              : p.status === "rejected"
                                ? "bg-rose-500/10 text-rose-300"
                                : p.status === "pending_review"
                                  ? "bg-amber-500/10 text-amber-300"
                                  : "bg-slate-500/10 text-slate-400"
                          }`}
                        >
                          {p.status.replace("_", " ")}
                        </span>
                      </td>
                      <td className="px-4 py-2 font-mono text-xs text-slate-400">{p.txn_ref || "—"}</td>
                      {status?.is_admin && (
                        <td className="px-4 py-2">
                          {p.status === "pending_review" && (
                            <span className="flex gap-2">
                              <button onClick={() => void adminAction(p.id, "approve")} disabled={busy} className="rounded bg-emerald-500 px-2 py-1 text-xs font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40">
                                Approve
                              </button>
                              <button onClick={() => void adminAction(p.id, "reject")} disabled={busy} className="rounded border border-rose-500/40 px-2 py-1 text-xs text-rose-300 disabled:opacity-40">
                                Reject
                              </button>
                            </span>
                          )}
                          {p.status === "approved" && <span className="text-xs text-emerald-400">paid ✓</span>}
                          {p.status === "rejected" && <span className="text-xs text-rose-400">rejected</span>}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <p className="mt-6 text-center text-xs text-slate-500">
          Pakistan payments: JazzCash / EasyPaisa wallet, bank transfer, or Paddle (international cards). Owner approves manual payments.
        </p>
      </main>
    </div>
  );
}

function submitForm(url: string, params: Record<string, string>) {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = url;
  form.style.display = "none";
  for (const [k, v] of Object.entries(params)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = k;
    input.value = v;
    form.appendChild(input);
  }
  document.body.appendChild(form);
  form.submit();
}
