"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiGet, type Health } from "@/lib/api";
import type { User } from "@/lib/types";

type Ctx = {
  users: User[];
  user: User | null;
  setUserId: (id: string) => void;
  health: Health | null;
  backendError: string | null;
};

const UserContext = createContext<Ctx>({ users: [], user: null, setUserId: () => {}, health: null, backendError: null });

const KEY = "briefing.user";

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserIdState] = useState<string>("U-ANA");
  const [health, setHealth] = useState<Health | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved) setUserIdState(saved);
    } catch {
      /* storage unavailable: keep the default */
    }
    Promise.all([apiGet<User[]>("/api/users"), apiGet<Health>("/api/health")])
      .then(([u, h]) => {
        setUsers(u);
        setHealth(h);
      })
      .catch((e) => setBackendError(String(e)));
  }, []);

  const setUserId = useCallback((id: string) => {
    setUserIdState(id);
    try {
      localStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const user = users.find((u) => u.user_id === userId) ?? null;
  return (
    <UserContext.Provider value={{ users, user, setUserId, health, backendError }}>{children}</UserContext.Provider>
  );
}

export const useUser = () => useContext(UserContext);
