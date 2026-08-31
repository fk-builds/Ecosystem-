"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { api, getToken } from "@/lib/api";

const AuthCtx = createContext<ReturnType<typeof useAuth> | null>(null);
export function useStudioAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useStudioAuth outside StudioShell");
  return ctx;
}

export function StudioShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "guest") router.replace("/auth");
  }, [auth.status, router]);

  useEffect(() => {
    // Periodically refresh plan/limits in case a webhook flipped the plan.
    if (auth.status !== "authed") return;
    const timer = setInterval(() => void auth.refresh(), 60_000);
    return () => clearInterval(timer);
  }, [auth.status, auth]);

  if (auth.status === "loading") {
    return (
      <div className="flex h-screen items-center justify-center bg-[#0a0f1a] text-slate-400">
        <div className="flex items-center gap-3">
          <span className="h-3 w-3 animate-ping rounded-full bg-emerald-400" />
          Loading workspace…
        </div>
      </div>
    );
  }
  if (auth.status === "guest") {
    return <div className="h-screen bg-[#0a0f1a]" />;
  }
  return <AuthCtx.Provider value={auth}>{children}</AuthCtx.Provider>;
}

export async function ensureFreshToken() {
  return getToken();
}

export { api };
