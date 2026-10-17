export type Probs = Record<string, number>;

export interface Stage {
  after: string | null;
  status: string | null;
  probabilities: Probs;
  conditions: Record<string, number | null> | null;
  leading: string;
}

export interface Step {
  kind: "fetch" | "select" | "classify";
  action: string;
  status: string;
  summary: string;
  cost: number;
}

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

export interface Run {
  decision: string;
  correct: boolean;
  stop_reason: string;
  fetch_count: number;
  costs: { retrieval: number; model: number | null; decision_loss: number; total: number | null };
  steps: Step[];
  graph: { nodes: GraphNode[]; links: GraphLink[] };
  evolution: Stage[];
}

export interface ShowCase {
  id: string;
  scenario: string;
  scenario_label: string;
  request: string;
  facts: Record<string, unknown>;
  answer: string;
  runs: Record<string, Run>;
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
  cases: ShowCase[];
  evaluation: {
    text: string;
    n_cases: number;
    reference: string;
    metrics: Metric[];
    paired: Paired[];
    sensitivity: Record<string, { penalty_multiplier: number; mean_total_cost: number | null }[]>;
    by_scenario: Record<string, Record<string, number>>;
  };
}

export interface Demo {
  strategies: { id: string; description: string }[];
  domains: DomainData[];
}
