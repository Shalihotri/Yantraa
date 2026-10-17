import { useState } from "react";
import { judgements } from "../data";
import { humanize, labelColor, pct, sourceName } from "../format";
import type { DomainData, LiveRun } from "../types";

interface Props {
  domain: DomainData;
  run: LiveRun;
  position: number;
}

const INSIDE = 0.13; // print a % inside a segment only when it has room

export function Thinking({ domain, run, position }: Props) {
  const [table, setTable] = useState(false);
  const [tip, setTip] = useState<{ row: number; label: string; v: number } | null>(null);
  const rows = judgements(run, position);
  const latest = run.timeline[position - 1];
  const plan = latest?.type === "plan" && latest.options ? latest : null;
  const conds = rows.at(-1)?.event.conditions;

  return (
    <div className="thinking">
      <div className="panel-head">
        <h4>How sure it was, after each check</h4>
        <button className="text-button" onClick={() => setTable((t) => !t)}>{table ? "Chart" : "Table"}</button>
      </div>
      <ul className="legend">
        {domain.actions.map((a) => (
          <li key={a.id}><span className="swatch" style={{ background: labelColor(domain, a.id) }} />{humanize(a.id)}</li>
        ))}
      </ul>
      {rows.length === 0 && <p className="empty">No judgement yet. Step forward to see the model's first call.</p>}
      {table && rows.length > 0 ? (
        <table className="mini-table">
          <thead><tr><th>Stage</th>{domain.actions.map((a) => <th key={a.id} className="num">{humanize(a.id)}</th>)}</tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.index}><td>{r.after}</td>{domain.actions.map((a) => <td key={a.id} className="num">{pct(r.event.probabilities[a.id] ?? 0)}</td>)}</tr>
          ))}</tbody>
        </table>
      ) : (
        <div className="prob-rows">
          {rows.map((r, i) => (
            <div key={r.index} className={`prob-row appear ${i === rows.length - 1 ? "current" : ""}`}
                 aria-label={`${r.after}: ${domain.actions.map((a) => `${a.id} ${pct(r.event.probabilities[a.id] ?? 0)}`).join(", ")}`}>
              <span className="prob-label">{r.after}</span>
              <span className="prob-bar">
                {domain.actions.map((a) => {
                  const v = r.event.probabilities[a.id] ?? 0;
                  if (v < 0.005) return null;
                  return (
                    <span key={a.id} className="seg" style={{ flexGrow: v, background: labelColor(domain, a.id) }}
                          onPointerEnter={() => setTip({ row: i, label: a.id, v })} onPointerLeave={() => setTip(null)}>
                      {v >= INSIDE && <span className="seg-text">{pct(v)}</span>}
                    </span>
                  );
                })}
              </span>
              {tip?.row === i && <span className="tip"><strong>{pct(tip.v)}</strong> {humanize(tip.label)}</span>}
            </div>
          ))}
        </div>
      )}

      {plan && (
        <div className="plan appear">
          <h4>What it considered checking next</h4>
          {Object.entries(plan.options!).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div key={k} className={`option ${k === plan.chosen ? "chosen" : ""}`}>
              <span className="option-label">{k === "stop" ? "Stop and decide" : sourceName(k)}</span>
              <span className="option-track"><span className="option-fill" style={{ width: `${Math.max(1, v * 100)}%` }} /></span>
              <span className="option-value">{pct(v)}</span>
            </div>
          ))}
        </div>
      )}

      {conds && (
        <div className="conds">
          <h4>Its own reading of the evidence</h4>
          {domain.conditions.map((c) => {
            const v = conds[c.id];
            return (
              <div key={c.id} className="cond">
                <span className="cond-label">{humanize(c.id)}</span>
                <span className="option-track"><span className="cond-fill" style={{ width: `${(v ?? 0) * 100}%` }} /></span>
                <span className="option-value">{v === undefined ? "n/a" : pct(v)}</span>
              </div>
            );
          })}
          <p className="note">Probability that each return condition holds, as the model reported it.</p>
        </div>
      )}
    </div>
  );
}
