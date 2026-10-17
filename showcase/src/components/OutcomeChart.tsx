import { useState } from "react";
import { humanize, labelColor, pct, sourceName } from "../format";
import type { DomainData, Run } from "../types";

interface Props {
  domain: DomainData;
  run: Run;
  position: number;
  onSelect: (position: number) => void;
}

const LABEL_MIN_WIDTH = 0.14; // only print a % inside a segment wide enough to hold it

/** Probable outcome after each check: one 100% bar per stage, segments in the domain's label order. */
export function OutcomeChart({ domain, run, position, onSelect }: Props) {
  const [table, setTable] = useState(false);
  const [tip, setTip] = useState<{ row: number; label: string; value: number } | null>(null);
  const E = run.evolution.length;
  const current = Math.min(position, E - 1);
  const rowName = (i: number) => (i === 0 ? "Before any check" : `After ${sourceName(run.evolution[i].after ?? "")}`);

  return (
    <section className="card" aria-labelledby="outcome-title">
      <div className="card-head">
        <h3 id="outcome-title">Probable outcome after each check</h3>
        <button className="link-button" onClick={() => setTable((t) => !t)}>{table ? "Show chart" : "Show as table"}</button>
      </div>
      <ul className="legend" aria-label="Decision labels">
        {domain.actions.map((a) => (
          <li key={a.id}>
            <span className="swatch" style={{ background: labelColor(domain, a.id) }} />
            {humanize(a.id)}{a.id === domain.fallback ? " (fallback)" : ""}
          </li>
        ))}
      </ul>

      {table ? (
        <table className="data-table">
          <thead>
            <tr><th>Stage</th>{domain.actions.map((a) => <th key={a.id} className="num">{humanize(a.id)}</th>)}</tr>
          </thead>
          <tbody>
            {run.evolution.map((s, i) => (
              <tr key={i} className={i === current ? "current" : ""}>
                <td>{rowName(i)}</td>
                {domain.actions.map((a) => <td key={a.id} className="num">{pct(s.probabilities[a.id] ?? 0)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="stack-rows">
          {run.evolution.map((s, i) => (
            <button key={i} className={`stack-row ${i === current ? "current" : ""} ${i > current ? "future" : ""}`}
                    onClick={() => onSelect(i)} aria-label={`${rowName(i)}: ${domain.actions.map((a) =>
                      `${humanize(a.id)} ${pct(s.probabilities[a.id] ?? 0)}`).join(", ")}`}>
              <span className="stack-label">{rowName(i)}</span>
              <span className="stack-bar">
                {domain.actions.map((a) => {
                  const v = s.probabilities[a.id] ?? 0;
                  if (v <= 0) return null;
                  return (
                    <span key={a.id} className="seg" style={{ flexGrow: v, background: labelColor(domain, a.id) }}
                          onPointerMove={() => setTip({ row: i, label: a.id, value: v })}
                          onPointerLeave={() => setTip(null)}>
                      {v >= LABEL_MIN_WIDTH && <span className="seg-text">{pct(v)}</span>}
                    </span>
                  );
                })}
              </span>
              {tip && tip.row === i && (
                <span className="tooltip" role="status">
                  <strong>{pct(tip.value, 1)}</strong> {humanize(tip.label)}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <p className="footnote">
        Practice mode: probabilities come from the built-in rules, not an AI model. With a real model
        (<code>--provider openai</code>) they are the model's own and are not calibrated.
      </p>
    </section>
  );
}
