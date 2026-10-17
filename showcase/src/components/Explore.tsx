import { useEffect, useMemo, useState } from "react";
import { STOP_REASONS, humanize, labelColor, money, sourceName, strategyName } from "../format";
import type { DomainData, Run, ShowCase } from "../types";
import { DecisionGraph } from "./DecisionGraph";
import { OutcomeChart } from "./OutcomeChart";

interface Props {
  domain: DomainData;
  strategies: { id: string; description: string }[];
}

function positionLabel(run: Run, p: number) {
  const E = run.evolution.length;
  if (p >= E) return "Decision";
  return p === 0 ? "Before any check" : `After checking ${sourceName(run.evolution[p].after ?? "").toLowerCase()}`;
}

function Conditions({ domain, run, position }: { domain: DomainData; run: Run; position: number }) {
  const stage = run.evolution[Math.min(position, run.evolution.length - 1)];
  if (!domain.conditions.length) return null;
  return (
    <ul className="conditions" aria-label="What the evidence shows so far">
      {domain.conditions.map((c) => {
        const v = stage.conditions?.[c.id];
        const state = v === null || v === undefined ? "unknown" : v >= 0.5 ? "holds" : "fails";
        return (
          <li key={c.id} className={state}>
            <span className="cond-icon" aria-hidden>{state === "holds" ? "✓" : state === "fails" ? "✗" : "?"}</span>
            <span><strong>{humanize(c.id)}</strong> <span className="muted">{state === "unknown" ? "not known yet" : state}</span></span>
          </li>
        );
      })}
    </ul>
  );
}

function ResultCard({ domain, caseData, run, strategy }: { domain: DomainData; caseData: ShowCase; run: Run; strategy: string }) {
  const all = caseData.runs.fetch_all;
  const diff = (run.costs.total ?? 0) - (all.costs.total ?? 0);
  return (
    <section className="card result">
      <h3>Result</h3>
      <div className="result-row">
        <span className="swatch lg" style={{ background: labelColor(domain, run.decision) }} />
        <div>
          <div className="result-decision">{humanize(run.decision)}</div>
          <div className={`verdict ${run.correct ? "ok" : "bad"}`}>
            {run.correct ? "✓ Matches the answer key" : `✗ The answer key says ${humanize(caseData.answer)}`}
          </div>
        </div>
      </div>
      <dl className="costs">
        <div><dt>Checks ({run.fetch_count})</dt><dd>{money(run.costs.retrieval)}</dd></div>
        <div><dt>AI calls</dt><dd>{money(run.costs.model, 4)}</dd></div>
        <div><dt>Mistake penalty</dt><dd>{money(run.costs.decision_loss)}</dd></div>
        <div className="total"><dt>Total</dt><dd>{money(run.costs.total)}</dd></div>
      </dl>
      {strategy !== "fetch_all" && (
        <p className={`compare-line ${Math.abs(diff) < 0.005 ? "" : diff < 0 ? "ok" : "bad"}`}>
          {Math.abs(diff) < 0.005 ? "About the same cost as" : diff < 0 ? `${money(-diff)} cheaper than` :
            `${money(diff)} more expensive than`} checking everything on this request.
        </p>
      )}
      <p className="muted small">Stopped: {STOP_REASONS[run.stop_reason] ?? humanize(run.stop_reason)}</p>
    </section>
  );
}

export function Explore({ domain, strategies }: Props) {
  const [caseId, setCaseId] = useState(domain.cases[0].id);
  const [strategy, setStrategy] = useState("selective");
  const [scenario, setScenario] = useState<string>("all");
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => { setCaseId(domain.cases[0].id); setScenario("all"); }, [domain]);
  const caseData = domain.cases.find((c) => c.id === caseId) ?? domain.cases[0];
  const run = caseData.runs[strategy];
  const E = run.evolution.length;

  useEffect(() => { setPosition(0); setPlaying(true); }, [caseData.id, strategy]);
  useEffect(() => {
    if (!playing) return;
    if (position >= E) { setPlaying(false); return; }
    const t = window.setTimeout(() => setPosition((p) => p + 1), position === 0 ? 900 : 1100);
    return () => window.clearTimeout(t);
  }, [playing, position, E]);

  const scenarios = useMemo(() => [...new Map(domain.cases.map((c) => [c.scenario, c.scenario_label])).entries()], [domain]);
  const visible = domain.cases.filter((c) => scenario === "all" || c.scenario === scenario);
  const user = (p: number) => { setPlaying(false); setPosition(Math.max(0, Math.min(E, p))); };

  return (
    <div className="explore">
      <div className="filters" role="group" aria-label="Choose a strategy">
        <span className="filter-label">Strategy</span>
        <div className="segmented">
          {strategies.map((s) => (
            <button key={s.id} aria-pressed={strategy === s.id} title={s.description}
                    onClick={() => setStrategy(s.id)}>{strategyName(s.id)}</button>
          ))}
        </div>
      </div>

      <div className="explore-grid">
        <aside className="case-list" aria-label="Requests">
          <label className="filter-label" htmlFor="scenario">Situation</label>
          <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
            <option value="all">All situations ({domain.cases.length})</option>
            {scenarios.map(([id, lbl]) => <option key={id} value={id}>{lbl}</option>)}
          </select>
          <ul>
            {visible.map((c) => (
              <li key={c.id}>
                <button className={`case-item ${c.id === caseData.id ? "active" : ""}`} onClick={() => setCaseId(c.id)}>
                  <span className="chip">{c.scenario_label}</span>
                  <span className="case-request">{c.request}</span>
                  <span className="case-answer">
                    <span className="swatch" style={{ background: labelColor(domain, c.answer) }} />Answer: {humanize(c.answer)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="explore-main">
          <section className="card">
            <div className="card-head">
              <h3>Decision graph · {strategyName(strategy)}</h3>
              <span className="muted small">{strategies.find((s) => s.id === strategy)?.description}</span>
            </div>
            <div className="scrubber">
              <button onClick={() => user(0)} aria-label="First step">⏮</button>
              <button onClick={() => user(position - 1)} aria-label="Previous step">◀</button>
              <button className="play" onClick={() => { if (position >= E) setPosition(0); setPlaying((p) => !p); }}
                      aria-label={playing ? "Pause" : "Play"}>{playing ? "❚❚" : "▶"}</button>
              <button onClick={() => user(position + 1)} aria-label="Next step">▶|</button>
              <input type="range" min={0} max={E} value={position} onChange={(e) => user(Number(e.target.value))}
                     aria-label="Step" />
              <span className="step-label">Step {position} of {E} · {positionLabel(run, position)}</span>
            </div>
            <DecisionGraph domain={domain} caseData={caseData} run={run} position={position} />
          </section>

          <div className="grid-2">
            <OutcomeChart domain={domain} run={run} position={position} onSelect={user} />
            <div className="stack">
              {position >= E ? (
                <ResultCard domain={domain} caseData={caseData} run={run} strategy={strategy} />
              ) : (
                <section className="card result pending-result">
                  <h3>Result</h3>
                  <p className="muted">Deciding… the result and its cost appear at the last step.</p>
                  <button className="link-button" onClick={() => user(E)}>Skip to the decision →</button>
                </section>
              )}
              <section className="card">
                <h3>What the evidence shows so far</h3>
                <Conditions domain={domain} run={run} position={position} />
              </section>
            </div>
          </div>

          <section className="card">
            <h3>Trace</h3>
            <ol className="trace">
              {run.steps.map((s, i) => (
                <li key={i} className={`trace-${s.kind}`}>
                  <span className="trace-kind">{s.kind === "fetch" ? "Check" : s.kind === "select" ? "Plan" : "Decide"}</span>
                  <span className="trace-action">
                    {s.kind === "classify" ? humanize(s.action) : s.action === "stop" ? "Stop" : sourceName(s.action)}
                    {s.kind === "fetch" && <span className="muted"> · {s.status === "ok" ? money(s.cost) : humanize(s.status)}</span>}
                  </span>
                  <span className="trace-summary">{s.summary}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}
