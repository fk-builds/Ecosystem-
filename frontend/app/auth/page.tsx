"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

export default function AuthPage() {
  const auth = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await auth.login(email, password);
      else await auth.signup(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const tryDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      await auth.demo();
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Demo login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0f1a] px-4 text-slate-100">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-6 flex items-center justify-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-cyan-500 text-lg font-black text-slate-950">FK</div>
          <div>
            <p className="font-bold">FK AI Builder</p>
            <p className="text-xs text-slate-500">Real-time AI agent + visual canvas</p>
          </div>
        </Link>

        <div className="rounded-2xl border border-[#1c2740] bg-[#0e1526] p-6">
          <div className="mb-6 flex rounded-lg border border-[#1c2740] p-1">
            {(["login", "signup"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-md py-1.5 text-sm ${mode === m ? "bg-emerald-500/10 text-emerald-300" : "text-slate-500"}`}
              >
                {m === "login" ? "Log in" : "Create account"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-slate-500">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-lg border border-[#1c2740] bg-[#0a0f1a] px-3 py-2 text-sm outline-none focus:border-emerald-400"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs uppercase tracking-wide text-slate-500">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
                className="w-full rounded-lg border border-[#1c2740] bg-[#0a0f1a] px-3 py-2 text-sm outline-none focus:border-emerald-400"
              />
            </label>
            {error && <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{error}</p>}
            <button
              disabled={busy}
              className="w-full rounded-lg bg-emerald-500 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
            >
              {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create free account"}
            </button>
          </form>

          <div className="my-4 flex items-center gap-3 text-xs text-slate-600">
            <div className="h-px flex-1 bg-[#1c2740]" /> or <div className="h-px flex-1 bg-[#1c2740]" />
          </div>
          <button
            onClick={() => void tryDemo()}
            disabled={busy}
            className="w-full rounded-lg border border-emerald-500/40 py-2.5 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-40"
          >
            ✨ Guest demo — full Pro features, no account
          </button>

          <p className="mt-4 text-center text-xs text-slate-500">
            New accounts start on the <span className="text-slate-300">Free plan</span> — upgrade anytime.{" "}
            <Link href="/pricing" className="text-emerald-400 hover:underline">See pricing</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
