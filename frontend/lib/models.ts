"use client";

import type { Health } from "@/lib/api";
import { useUser } from "@/lib/user";

/** Model display names come from the backend (/api/health), so the app always names the models actually used. */
export type Models = { opus: string; haiku: string };

/** 'claude-haiku-5-5' -> 'Haiku 5.5' (for ids stored in older results). Names already in display form pass through. */
export function modelLabel(id?: string | null): string {
  const m = (id ?? "").match(/^claude-([a-z]+)-(\d+)(?:-(\d+))?/);
  if (!m) return id ?? "";
  return `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}${m[3] ? `.${m[3]}` : ""}`;
}

export function modelsFrom(health: Health | null): Models {
  return health?.models ?? { opus: "Opus", haiku: "Haiku" };
}

/** The models in use, for components. */
export function useModels(): Models {
  return modelsFrom(useUser().health);
}

/** How a briefing or evaluation was produced: 'Opus 5.5 + Haiku 5.5', or 'offline'. */
export function engineLabel(mode: string | null | undefined, m: Models): string {
  return mode === "anthropic" ? `${m.opus} + ${m.haiku}` : "offline";
}
