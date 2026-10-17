import type { DomainData } from "./types";

export const STRATEGY_NAMES: Record<string, string> = {
  selective: "AI picks the checks",
  fetch_all: "Check everything",
  fixed_order: "Checklist, stop early",
  confidence_threshold: "Stop when confident",
  initial_only: "No checks",
};

export const strategyName = (id: string) => STRATEGY_NAMES[id] ?? humanize(id);

export function humanize(id: string): string {
  const s = id.replace(/^get_/, "").replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const sourceName = humanize;

export function money(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "unknown";
  const abs = Math.abs(v);
  const d = abs > 0 && abs < 0.01 ? 4 : digits;
  return `${v < 0 ? "−" : ""}$${abs.toFixed(d)}`;
}

export function signedMoney(v: number): string {
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}$${Math.abs(v).toFixed(Math.abs(v) < 0.01 && v !== 0 ? 4 : 2)}`;
}

export const pct = (v: number, digits = 0) => `${(v * 100).toFixed(digits)}%`;

/** CSS variable for a decision label: categorical slots 1-3 in the domain's fixed label order. */
export function labelColor(domain: DomainData, action: string): string {
  const i = domain.actions.findIndex((a) => a.id === action);
  return `var(--label-${(i < 0 ? 0 : i) + 1})`;
}

/** A few short, readable fields from a record payload. */
export function payloadLines(payload: Record<string, unknown>, max = 3): [string, string][] {
  return Object.entries(payload)
    .filter(([, v]) => v !== null && typeof v !== "object" && String(v).length <= 26)
    .slice(0, max)
    .map(([k, v]) => [humanize(k), typeof v === "boolean" ? (v ? "yes" : "no") : String(v)]);
}

export const STOP_REASONS: Record<string, string> = {
  classifier_decided: "Finished normally",
  budget_spend: "Hit the spending cap",
  budget_time: "Ran out of time",
  budget_fetches: "Hit the check limit",
  invalid_output: "Unusable answer",
  provider_error: "Decision-maker unreachable",
  probabilities_unavailable: "No confidence scores",
};
