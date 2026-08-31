"use client";

import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken, ApiError, type UserInfo } from "@/lib/api";

type AuthStatus = "loading" | "authed" | "guest";

export function useAuth() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setStatus("guest");
      return;
    }
    api
      .me()
      .then(({ user }) => {
        setUser(user);
        setStatus("authed");
      })
      .catch(() => {
        setToken(null);
        setStatus("guest");
      });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { token, user } = await api.login(email, password);
    setToken(token);
    setUser(user);
    setStatus("authed");
    return user;
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const { token, user } = await api.signup(email, password);
    setToken(token);
    setUser(user);
    setStatus("authed");
    return user;
  }, []);

  const demo = useCallback(async () => {
    const { token, user } = await api.demo();
    setToken(token);
    setUser(user);
    setStatus("authed");
    return user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* token already dead */
    }
    setToken(null);
    setUser(null);
    setStatus("guest");
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { user } = await api.me();
      setUser(user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null);
        setStatus("guest");
        setUser(null);
      }
    }
  }, []);

  return { user, status, login, signup, demo, logout, refresh };
}
