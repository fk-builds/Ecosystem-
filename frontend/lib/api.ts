"use client";

/** Typed REST client for the SaaS API. Token is stored in localStorage. */

export const TOKEN_KEY = "fk_token";

export interface PlanInfo {
  id: string;
  name: string;
  tagline: string;
  price_usd: number;
  price_yearly_usd: number;
  projects: number | null;
  agent_messages_per_day: number;
  features: string[];
}

export interface UserInfo {
  id: string;
  email: string;
  plan: string;
  plan_status: string;
  period_end: string | null;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  name: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface BillingStatus {
  plan: string;
  plan_status: string;
  period_end: string | null;
  usage_today: number;
  usage_limit: number;
  projects: number;
  billing_mode: "demo" | "stripe";
}

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}, auth = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(options.headers as Record<string, string>) };
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  const res = await fetch(`/api${path}`, { ...options, headers });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* empty */
  }
  if (!res.ok) {
    const detail = (body as { detail?: string })?.detail ?? (body as { detail?: unknown })?.detail;
    const message = typeof detail === "string" ? detail : `Request failed (${res.status})`;
    const limitCode = (body as { detail?: string })?.detail?.includes("plan") ? "plan_limit" : undefined;
    throw new ApiError(res.status, message, limitCode);
  }
  return body as T;
}

export const api = {
  me: () => request<{ user: UserInfo }>("/auth/me"),
  signup: (email: string, password: string) =>
    request<{ token: string; user: UserInfo }>("/auth/signup", { method: "POST", body: JSON.stringify({ email, password }) }, false),
  login: (email: string, password: string) =>
    request<{ token: string; user: UserInfo }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false),
  demo: () => request<{ token: string; user: UserInfo }>("/auth/demo", { method: "POST" }, false),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  plans: () => request<{ plans: PlanInfo[] }>("/plans", {}, false),
  projects: () => request<{ projects: ProjectSummary[] }>("/projects"),
  project: (id: string) => request<{ project: { id: string; name: string; canvas: unknown; created_at: string; updated_at: string } }>(`/projects/${id}`),
  createProject: (name: string) => request<{ project: { id: string; name: string; version: number } }>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  renameProject: (id: string, name: string) => request<{ ok: boolean }>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteProject: (id: string) => request<{ ok: boolean }>(`/projects/${id}`, { method: "DELETE" }),
  code: (id: string, format: "html" | "react") => request<{ format: string; html: string; react: string; version: number }>(`/projects/${id}/code?format=${format}`),

  billingStatus: () => request<BillingStatus>("/billing/status"),
  checkout: (plan: string, interval: "month" | "year") =>
    request<{ url: string | null; demo: boolean; plan: string }>("/billing/checkout", { method: "POST", body: JSON.stringify({ plan, interval }) }),
  cancel: () => request<{ ok: boolean; plan: string }>("/billing/cancel", { method: "POST" }),
};
