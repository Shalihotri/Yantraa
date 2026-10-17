import { useState } from "react";
import { demo } from "../data";
import { money, signedMoney, strategyName } from "../format";

export function Scale() {
  const [i, setI] = useState(0);
  const d = demo.domains[i];
  const ev = d.evaluation;
  const ms = ev.metrics;
  const sorted = [...ms].map((m) => m.mean_total_cost ?? 0).sort((a, b) => b - a);
  const cap = sorted[0] > 3 * sorted[1] ? sorted[1] * 1.3 : sorted[0];
  const paired = ev.paired.filter((p) => p.metric === "total_cost" && p.ci95);

  return (
    <div className="scale">
      <div className="scale-controls">
        <div className="seg-control" role="radiogroup" aria-label="Use case">
          {demo.domains.map((x, k) => (
            <button key={x.name} role="radio" aria-checked={k === i} onClick={() => setI(k)}>{x.title}</button>
          ))}
        </div>
        <span className="muted">{ev.n_cases} synthetic requests · offline practice rules · free</span>
      </div>
      <div className="scale-grid">
        <figure className="panel">
          <h4>Average total cost per decision</h4>
          <div className="cost-rows">
            {ms.map((m) => {
              const v = m.mean_total_cost ?? 0;
              return (
                <div key={m.strategy} className={`cost-row ${m.strategy === "selective" ? "hl" : ""}`}>
                  <span className="cost-name">{strategyName(m.strategy)}</span>
                  <span className="bar-cell"><span className="track"><span className={`hbar ${v > cap ? "broken" : ""}`} style={{ width: `${Math.min(1, v / cap) * 100}%` }} /></span>
                    <span className="bar-val">{money(v)}{v > cap ? " ⟶ off scale" : ""}</span></span>
                </div>
              );
            })}
          </div>
          <figcaption><span className="fig-n">Figure 7.</span> {d.title}: every strategy on the same {ev.n_cases} requests.</figcaption>
        </figure>
        <figure className="panel">
          <h4>Saving vs checking everything, per decision</h4>
          <table className="mini-table">
            <thead><tr><th>Strategy</th><th className="num">Difference</th><th className="num">95% interval</th></tr></thead>
            <tbody>
              {paired.map((p) => (
                <tr key={p.strategy}>
                  <td>{strategyName(p.strategy)}</td>
                  <td className="num">{signedMoney(p.mean_diff ?? 0)}</td>
                  <td className="num">{signedMoney(p.ci95![0])} to {signedMoney(p.ci95![1])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <figcaption>Paired by request. Negative means cheaper. An interval that doesn't cross zero is a real difference.</figcaption>
        </figure>
      </div>
      <figure className="terminal-figure">
        <div className="term-bar"><span /><span /><span /> <em>yantraa evaluate</em></div>
        <pre tabIndex={0}>{ev.text}</pre>
      </figure>
      <p className="note center">Practice rules use the same logic as the answer key, so they score 100%: they test the
        mechanics and your cost model for free. Switch to a real model with <code>--provider openai</code>.</p>
    </div>
  );
}
