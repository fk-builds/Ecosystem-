"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type PlanInfo } from "@/lib/api";

export default function PricingPage() {
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  useEffect(() => {
    void api.plans().then((p) => setPlans(p.plans)).catch(() => undefined);
  }, []);

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-slate-100">
      <header className="flex items-center justify-between border-b border-[#1c2740] bg-[#0e1526] px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 text-sm font-black text-slate-950">FK</div>
          <span className="text-sm font-semibold">FK AI Builder</span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Link href="/" className="text-slate-400 hover:text-emerald-300">Home</Link>
          <Link href="/auth" className="rounded-lg bg-emerald-500 px-3 py-1.5 text-slate-950 font-semibold">Start free</Link>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12">
        <div className="text-center">
          <h1 className="text-3xl font-bold">Simple, below-market pricing</h1>
          <p className="mx-auto mt-2 max-w-xl text-slate-400">
            A real-time AI design agent + visual canvas. Start free, upgrade only when you need more.
            Most comparable tools charge $20–30/mo — we don't.
          </p>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {plans.map((plan) => (
            <div key={plan.id} className={`flex flex-col rounded-2xl border p-6 ${plan.id === "pro" ? "border-emerald-400 bg-emerald-500/5" : "border-[#1c2740] bg-[#0e1526]"}`}>
              {plan.id === "pro" && (
                <span className="mb-2 w-fit rounded-full bg-emerald-500 px-2 py-0.5 text-[11px] font-bold text-slate-950">Most popular</span>
              )}
              <p className="font-semibold">{plan.name}</p>
              <p className="text-xs text-slate-500">{plan.tagline}</p>
              <p className="mt-3 text-4xl font-black">
                ${plan.price_usd}
                <span className="text-sm font-normal text-slate-500">/mo</span>
              </p>
              {plan.price_yearly_usd > 0 && <p className="text-xs text-slate-500">${plan.price_yearly_usd}/year · save 20%</p>}
              <ul className="mt-5 flex-1 space-y-2 text-sm text-slate-300">
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2"><span className="text-emerald-400">✓</span>{f}</li>
                ))}
              </ul>
              <Link
                href="/auth"
                className={`mt-6 rounded-lg py-2.5 text-center text-sm font-semibold ${plan.id === "free" ? "border border-[#1c2740] text-slate-300" : "bg-emerald-500 text-slate-950 hover:bg-emerald-400"}`}
              >
                {plan.id === "free" ? "Start free" : `Get ${plan.name}`}
              </Link>
            </div>
          ))}
        </div>

        <div className="mt-12 grid gap-6 text-sm text-slate-400 md:grid-cols-3">
          <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
            <p className="font-semibold text-slate-200">Real-time, not screenshots</p>
            <p className="mt-1">Your agent edits the live canvas; every client syncs instantly over WebSocket or long-poll.</p>
          </div>
          <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
            <p className="font-semibold text-slate-200">You own the code</p>
            <p className="mt-1">Export clean Tailwind HTML or React/TSX from any canvas — no lock-in.</p>
          </div>
          <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
            <p className="font-semibold text-slate-200">Cancel anytime</p>
            <p className="mt-1">Projects stay on the free tier. Upgrade only when you hit the daily limits.</p>
          </div>
        </div>
      </main>
    </div>
  );
}
