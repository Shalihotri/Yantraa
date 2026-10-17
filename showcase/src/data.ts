import demoRaw from "./data/demo.json";
import liveRaw from "./data/live.json";
import { sourceName } from "./format";
import type { Demo, GraphNode, Live, LiveEvent, LiveRun } from "./types";

export const demo = demoRaw as unknown as Demo;
export const live = liveRaw as unknown as Live;
export const returnsDomain = demo.domains.find((d) => d.name === "returns")!;
export const REPO = "https://github.com/Shalihotri/Yantraa";

/** Judge events up to (not including) index `upto`, each labelled by the checks that came before it. */
export function judgements(run: LiveRun, upto = run.timeline.length) {
  const out: { index: number; after: string; event: Extract<LiveEvent, { type: "judge" }> }[] = [];
  let checks: string[] = [];
  run.timeline.slice(0, upto).forEach((e, index) => {
    if (e.type === "check") checks = [...checks, e.source];
    if (e.type === "judge") {
      out.push({ index, event: e, after: checks.length ? `After ${sourceName(checks.at(-1)!).toLowerCase()}` : "Before any check" });
    }
  });
  return out;
}

export function evidenceFor(run: LiveRun, source: string): GraphNode[] {
  return run.graph.nodes.filter((n) => n.kind === "Evidence" && n.data.source_id === source);
}

export function topLabel(p: Record<string, number>): [string, number] {
  return Object.entries(p).reduce((a, b) => (b[1] > a[1] ? b : a), ["", -1]);
}

export function describeEvent(e: LiveEvent): string {
  if (e.type === "check") return `Checks the ${sourceName(e.source).toLowerCase()} record`;
  if (e.type === "plan") {
    if (e.chosen === "stop") return e.status === "forced" ? "Nothing left to check" : "Decides to stop checking";
    const p = e.options?.[e.chosen];
    return `Plans to check ${sourceName(e.chosen).toLowerCase()}${p !== undefined ? ` (${Math.round(p * 100)}% of its choice)` : ""}`;
  }
  const [lbl, p] = topLabel(e.probabilities);
  return `Leans ${lbl} (${Math.round(p * 100)}%)`;
}
