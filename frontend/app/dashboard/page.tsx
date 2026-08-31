"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StudioShell, useStudioAuth } from "@/components/StudioShell";
import { api, ApiError, type BillingStatus, type ProjectSummary } from "@/lib/api";

export default function DashboardPage() {
  return (
    <StudioShell>
      <Dashboard />
    </StudioShell>
  );
}

function Dashboard() {
  const { user, logout } = useStudioAuth();
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const load = async () => {
    try {
      const [{ projects }, billing] = await Promise.all([api.projects(), api.billingStatus()]);
      setProjects(projects);
      setBilling(billing);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    setError(null);
    try {
      const { project } = await api.createProject(name.trim());
      router.push(`/app/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this project? The canvas will be lost.")) return;
    await api.deleteProject(id);
    void load();
  };

  const usagePct = billing ? Math.min(100, Math.round((billing.usage_today / billing.usage_limit) * 100)) : 0;

  return (
    <div className="min-h-screen bg-[#0a0f1a] text-slate-100">
      <header className="flex items-center justify-between border-b border-[#1c2740] bg-[#0e1526] px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-500 text-sm font-black text-slate-950">FK</div>
          <span className="text-sm font-semibold">FK AI Builder</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-400">{user?.email}</span>
          <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-xs capitalize text-emerald-300">
            {user?.plan} plan
          </span>
          <button onClick={() => void logout()} className="text-slate-400 hover:text-rose-300">Logout</button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-bold">Your projects</h1>
            <p className="mt-1 text-sm text-slate-400">Real-time canvases with a built-in design agent.</p>
          </div>
          <Link href="/pricing" className="text-sm text-emerald-300 hover:underline">View plans & pricing →</Link>
        </div>

        {billing && (
          <div className="mb-8 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
              <p className="text-xs uppercase tracking-wider text-slate-500">Agent messages today</p>
              <p className="mt-1 text-2xl font-bold">
                {billing.usage_today}<span className="text-sm font-normal text-slate-500"> / {billing.usage_limit}</span>
              </p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#1c2740]">
                <div className="h-full rounded-full bg-emerald-400" style={{ width: `${usagePct}%` }} />
              </div>
            </div>
            <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
              <p className="text-xs uppercase tracking-wider text-slate-500">Projects</p>
              <p className="mt-1 text-2xl font-bold">{billing.projects}</p>
              <Link href="/billing" className="mt-2 inline-block text-xs text-emerald-300 hover:underline">Manage plan →</Link>
            </div>
            <div className="rounded-xl border border-[#1c2740] bg-[#0e1526] p-4">
              <p className="text-xs uppercase tracking-wider text-slate-500">Plan</p>
              <p className="mt-1 text-2xl font-bold capitalize">{billing.plan}</p>
              {billing.period_end && <p className="mt-1 text-xs text-slate-500">renews {new Date(billing.period_end).toLocaleDateString()}</p>}
            </div>
          </div>
        )}

        <form onSubmit={create} className="mb-6 flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New project name…"
            className="min-w-0 flex-1 rounded-lg border border-[#1c2740] bg-[#0e1526] px-4 py-2 text-sm outline-none focus:border-emerald-400"
          />
          <button
            disabled={!name.trim() || creating}
            className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
          >
            + Create
          </button>
        </form>

        {error && <p className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">{error}</p>}

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <div key={p.id} className="group rounded-xl border border-[#1c2740] bg-[#0e1526] p-4 transition hover:border-emerald-500/50">
              <Link href={`/app/${p.id}`} className="block">
                <h3 className="font-semibold group-hover:text-emerald-300">{p.name}</h3>
                <p className="mt-1 text-xs text-slate-500">v{p.version} · updated {new Date(p.updated_at).toLocaleString()}</p>
                <p className="mt-3 text-sm font-medium text-emerald-400">Open workspace →</p>
              </Link>
              <button
                onClick={() => void remove(p.id)}
                className="mt-3 text-xs text-slate-600 hover:text-rose-400"
              >
                Delete
              </button>
            </div>
          ))}
          {projects.length === 0 && (
            <div className="col-span-full rounded-xl border border-dashed border-[#1c2740] p-10 text-center text-sm text-slate-500">
              No projects yet — create your first canvas above.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
