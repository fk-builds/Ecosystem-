"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type PlanInfo } from "@/lib/api";

export default function LandingPage() {
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  useEffect(() => {
    void api.plans().then((p) => setPlans(p.plans)).catch(() => undefined);
  }, []);

  const starter = plans.find((p) => p.id === "starter");
  const pro = plans.find((p) => p.id === "pro");

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-slate-100">
      {/* Nav */}
      <nav className="border-b border-[#1c2740] bg-[#0e1526]/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 text-sm font-black text-slate-950">FK</div>
            <span className="font-semibold">FK AI Builder</span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/pricing" className="text-slate-400 hover:text-emerald-300">Pricing</Link>
            <Link href="/auth" className="text-slate-300 hover:text-emerald-300">Log in</Link>
            <Link href="/auth?mode=signup" className="rounded-lg bg-emerald-500 px-3.5 py-1.5 font-semibold text-slate-950 hover:bg-emerald-400">
              Start free
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-20 text-center">
        <span className="inline-block rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
          ⚡ Real-time · AI agent ↔ visual canvas
        </span>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-black leading-tight md:text-6xl">
          Tell your agent what to build.
          <span className="bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent"> It builds it live.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-400">
          FK AI Builder unifies an AI developer workspace with a drag-and-drop UI canvas.
          Stream a prompt, watch tokens type out, and see components appear on every screen — instantly.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href="/auth?mode=signup" className="rounded-xl bg-emerald-500 px-6 py-3 font-semibold text-slate-950 hover:bg-emerald-400">
            Start free — no card
          </Link>
          <Link href="/auth" className="rounded-xl border border-[#1c2740] px-6 py-3 font-semibold text-slate-300 hover:border-emerald-500/50">
            Try the demo →
          </Link>
        </div>
      </section>

      {/* Product mock */}
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="grid grid-cols-[72px_1fr] gap-3 rounded-2xl border border-[#1c2740] bg-[#0e1526] p-4 md:grid-cols-[180px_1fr_320px]">
          {/* palette */}
          <div className="hidden space-y-1 md:block">
            {["Hero", "Heading", "Text", "Button", "Card", "Grid"].map((t) => (
              <div key={t} className="rounded-md border border-[#1c2740] bg-[#0a0f1a] px-2 py-1.5 text-xs text-slate-400">{t}</div>
            ))}
          </div>
          {/* canvas */}
          <div className="rounded-xl border border-[#1c2740] bg-[#0a0f1a] p-4">
            <div className="mx-auto max-w-sm rounded-lg bg-gradient-to-b from-slate-200 to-slate-100 p-6 text-slate-900">
              <p className="text-2xl font-black">Build with AI</p>
              <p className="mt-2 text-sm text-slate-600">A real-time agent that writes to your canvas while you watch.</p>
              <span className="mt-4 inline-block rounded-lg bg-emerald-500 px-4 py-1.5 text-sm font-bold text-white">Get Started</span>
            </div>
            <p className="mt-3 text-center text-[10px] uppercase tracking-widest text-slate-600">Live canvas — synced every keystroke</p>
          </div>
          {/* chat */}
          <div className="rounded-xl border border-[#1c2740] bg-[#0a0f1a] p-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-emerald-400">Agent Dev Hub</div>
            <div className="mb-2 rounded-lg border border-blue-500/30 bg-blue-600/90 p-2 text-xs text-white">Add a modern hero section</div>
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2 text-xs text-emerald-200">
              Got it — add a hero component… <span className="animate-pulse">▋</span>
            </div>
            <div className="mt-2 rounded-lg border border-[#1c2740] bg-[#0a0f1a] p-2 text-[10px] text-slate-500">
              ✓ canvas_add · version 12
            </div>
          </div>
        </div>
      </section>

      {/* Pricing teaser */}
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <h2 className="text-center text-2xl font-bold">Pricing that respects your wallet</h2>
        <div className="mx-auto mt-6 grid max-w-3xl gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-[#1c2740] bg-[#0e1526] p-5">
            <p className="font-semibold">Starter</p>
            <p className="text-3xl font-black">${starter?.price_usd ?? 7}<span className="text-sm font-normal text-slate-500">/mo</span></p>
            <p className="mt-2 text-sm text-slate-400">5 projects · 500 agent messages/day · code export · RAG</p>
            <Link href="/auth?mode=signup" className="mt-4 block rounded-lg bg-emerald-500 py-2 text-center text-sm font-semibold text-slate-950">Get Starter</Link>
          </div>
          <div className="rounded-2xl border border-emerald-400 bg-emerald-500/5 p-5">
            <p className="font-semibold text-emerald-300">Pro · most popular</p>
            <p className="text-3xl font-black">${pro?.price_usd ?? 15}<span className="text-sm font-normal text-slate-500">/mo</span></p>
            <p className="mt-2 text-sm text-slate-400">Unlimited projects · 2,000 messages/day · everything in Starter</p>
            <Link href="/auth?mode=signup" className="mt-4 block rounded-lg bg-emerald-500 py-2 text-center text-sm font-semibold text-slate-950">Get Pro</Link>
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-slate-500">
          Free tier: 1 project · 25 agent messages/day.{" "}
          <Link href="/pricing" className="text-emerald-400 hover:underline">Compare all plans →</Link>
        </p>
      </section>

      <footer className="border-t border-[#1c2740] px-6 py-6 text-center text-xs text-slate-600">
        FK AI Builder — Agent Dev Hub × Builder Studio · FastAPI + Next.js · demo pricing may change at launch
      </footer>
    </div>
  );
}
