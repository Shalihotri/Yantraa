export type Probs = Record<string, number>;

export interface GraphNode {
  id: string;
  kind: string;
  data: Record<string, unknown>;
}

export interface GraphLink {
  src: string;
  dst: string;
  rel: string;
}

export interface Metric {
  strategy: string;
  n: number;
  accuracy: number;
  fallback_rate: number;
  mean_retrievals: number;
  mean_retrieval_cost: number;
  mean_model_cost: number | null;
  mean_decision_loss: number;
  mean_total_cost: number | null;
  [key: string]: unknown;
}

export interface Paired {
  strategy: string;
  reference: string;
  metric: "total_cost" | "error";
  n_cases: number;
  mean_diff: number | null;
  ci95: [number, number] | null;
}

export interface SourceInfo {
  id: string;
  kind: string;
  description: string;
  cost: number;
}

export interface DomainData {
  title: string;
  industry: string;
  name: string;
  task: string;
  fallback: string;
  subject_kind: string;
  sources: SourceInfo[];
  actions: { id: string; meaning: string }[];
  conditions: { id: string; meaning: string }[];
  loss: Record<string, number>;
  evaluation: {
    text: string;
    n_cases: number;
    reference: string;
    metrics: Metric[];
    paired: Paired[];
    sensitivity: Record<string, { penalty_multiplier: number; mean_total_cost: number | null }[]>;
  };
}

export interface Demo {
  strategies: { id: string; description: string }[];
  domains: DomainData[];
}

// ---------------------------------------------------------------- live model runs (export_live.py)
export type LiveEvent =
  | { type: "plan"; chosen: string; status: string; options: Probs | null }
  | { type: "check"; source: string; status: string; cost: number }
  | { type: "judge"; action: string; probabilities: Probs; conditions: Record<string, number> | null };

export interface LiveRun {
  decision: string;
  correct: boolean;
  stop_reason: string;
  fetch_count: number;
  costs: { retrieval: number; model: number | null; decision_loss: number; total: number | null };
  timeline: LiveEvent[];
  graph: { nodes: GraphNode[]; links: GraphLink[] };
}

export interface LiveCase {
  id: string;
  scenario: string;
  scenario_label: string;
  request: string;
  facts: Record<string, unknown>;
  answer: string;
  runs: Record<string, LiveRun>;
}

export interface Live {
  model: string;
  api: string;
  date: string;
  n_cases: number;
  cases: LiveCase[];
  metrics: Metric[];
  paired: Paired[];
  rerun_selective: { accuracy: number; mean_retrievals: number; n: number };
}
