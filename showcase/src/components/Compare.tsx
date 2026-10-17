import { useState } from "react";
import { money, pct, signedMoney, strategyName } from "../format";
import type { DomainData, Metric } from "../types";

const HIGHLIGHT = "selective";

/** Round ticks across [a, b], always including 0 when it is in range. */
function niceTicks(a: number, b: number, count = 4): number[] {
  const raw = (b - a) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = Math.ceil(a / step) * step; t <= b + 1e-12; t += step) out.push(Math.abs(t) < step / 1e6 ? 0 : t);
  return out;
}

/** Values more than 3x the next largest are drawn clipped, so they don't flatten everything else. */
function scaleMax(values: number[]): { max: number; clipped: (v: number) => boolean } {
  const sorted = [...values].sort((a, b) => b - a);
  const [first, second = 0] = sorted;
  const max = first > 3 * second && second > 0 ? second * 1.35 : first * 1.05;
  return { max: max || 1, clipped: (v) => v > max };
}

function CostBars({ metrics, reference }: { metrics: Metric[]; reference: string }) {
  const [tip, setTip] = useState<string | null>(null);
  const rows = metrics.filter((m) => m.mean_total_cost !== null);
  const { max, clipped } = scaleMax(rows.map((m) => m.mean_total_cost as number));
  const W = 560, LABEL = 178, BAR = 290, ROW = 34;
  return (
    <svg viewBox={`0 0 ${W} ${rows.length * ROW + 8}`} className="chart" role="img"
         aria-label="Average total cost per decision by strategy">
      {rows.map((m, i) => {
        const v = m.mean_total_cost as number;
        const w = Math.max(2, (Math.min(v, max) / max) * BAR);
        const y = i * ROW + 6;
        const cls = m.strategy === HIGHLIGHT ? "bar accent" : "bar";
        return (
          <g key={m.strategy} tabIndex={0} onPointerEnter={() => setTip(m.strategy)} onPointerLeave={() => setTip(null)}
             onFocus={() => setTip(m.strategy)} onBlur={() => setTip(null)} className="bar-row">
            <rect x={0} y={y - 4} width={W} height={ROW - 2} className="hit" />
            <text x={0} y={y + 13} className="axis-label strong">{strategyName(m.strategy)}</text>
            {m.strategy === reference && <text x={0} y={y + 26} className="axis-label">baseline</text>}
            <rect x={LABEL} y={y} width={w} height={18} rx={4} className={cls} />
            <rect x={LABEL} y={y} width={Math.min(4, w)} height={18} className={cls} />
            {clipped(v) && (
              <path d={`M ${LABEL + w - 14} ${y - 2} l 5 22 M ${LABEL + w - 8} ${y - 2} l 5 22`} className="break-mark" />
            )}
            <text x={LABEL + w + 8} y={y + 13} className="value-label">
              {money(v)}{tip === m.strategy ? `  ·  checks ${money(m.mean_retrieval_cost)} + AI ${money(m.mean_model_cost)} + mistakes ${money(m.mean_decision_loss)}` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function PairedChart({ domain }: { domain: DomainData }) {
  const rows = domain.evaluation.paired.filter((p) => p.metric === "total_cost" && p.mean_diff !== null && p.ci95);
  const mags = rows.map((r) => Math.abs(r.mean_diff as number)).sort((a, b) => a - b);
  const typical = mags[Math.floor((mags.length - 1) / 2)] || 1;
  const inScale = rows.filter((r) => Math.abs(r.mean_diff as number) <= 6 * typical);
  const lo = Math.min(0, ...inScale.map((r) => r.ci95![0]));
  const hi = Math.max(0, ...inScale.map((r) => r.ci95![1]));
  const pad = (hi - lo) * 0.12 || 0.01;
  const [a, b] = [lo - pad, hi + pad];
  const W = 560, LABEL = 178, PLOT = 300, ROW = 32;
  const x = (v: number) => LABEL + ((Math.max(a, Math.min(b, v)) - a) / (b - a)) * PLOT;
  const H = rows.length * ROW + 34;
  const ticks = niceTicks(a, b);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
         aria-label={`Paired difference in total cost per decision versus ${strategyName(domain.evaluation.reference)}`}>
      <line x1={x(0)} x2={x(0)} y1={0} y2={rows.length * ROW} className="zero-line" />
      {rows.map((r, i) => {
        const y = i * ROW + 16;
        const off = !inScale.includes(r);
        const [l, h] = r.ci95!;
        const m = r.mean_diff as number;
        return (
          <g key={r.strategy}>
            <text x={0} y={y + 4} className="axis-label strong">{strategyName(r.strategy)}</text>
            {off ? (
              <>
                <path d={`M ${x(b) - 10} ${y - 5} l 10 5 l -10 5`} className="ci-line" />
                <text x={x(b) - 14} y={y + 4} textAnchor="end" className="value-label">{signedMoney(m)} (off scale)</text>
              </>
            ) : (
              <g tabIndex={0}>
                <title>{`${strategyName(r.strategy)}: ${signedMoney(m)} per decision (95% interval ${signedMoney(l)} to ${signedMoney(h)}), ${r.n_cases} cases`}</title>
                <line x1={x(l)} x2={x(h)} y1={y} y2={y} className="ci-line" />
                <circle cx={x(m)} cy={y} r={5} className={r.strategy === HIGHLIGHT ? "dot accent" : "dot"} />
                <text x={x(h) + 8} y={y + 4} className="value-label">{signedMoney(m)}</text>
              </g>
            )}
          </g>
        );
      })}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={rows.length * ROW} y2={rows.length * ROW + 5} className="zero-line" />
          <text x={x(t)} y={H - 6} textAnchor="middle" className="axis-label">{t === 0 ? "0" : signedMoney(t)}</text>
        </g>
      ))}
    </svg>
  );
}

function Sensitivity({ domain }: { domain: DomainData }) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = domain.evaluation.reference;
  const series = [HIGHLIGHT, ref].map((s) => ({ id: s, pts: domain.evaluation.sensitivity[s] ?? [] }));
  const mults = series[0].pts.map((p) => p.penalty_multiplier);
  const maxV = Math.max(...series.flatMap((s) => s.pts.map((p) => p.mean_total_cost ?? 0))) * 1.15 || 1;
  const W = 560, L = 48, R = 130, T = 10, B = 30, H = 210;
  const x = (i: number) => L + (i / Math.max(1, mults.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / maxV) * (H - T - B);
  const ticks = niceTicks(0, maxV, 3);
  const flat = series.every((s) => s.pts.every((p) => p.mean_total_cost === s.pts[0]?.mean_total_cost));
  return (
    <div className="chart-wrap">
      <ul className="legend">
        <li><span className="line-key accent" />{strategyName(HIGHLIGHT)}</li>
        <li><span className="line-key ref" />{strategyName(ref)}</li>
      </ul>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img"
           aria-label="Average total cost as mistake penalties are scaled from 0.25x to 4x"
           onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" className="axis-label">{money(t)}</text>
          </g>
        ))}
        {mults.map((m, i) => (
          <text key={m} x={x(i)} y={H - 8} textAnchor="middle" className="axis-label">×{m}</text>
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="crosshair" />}
        {series.map((s) => (
          <g key={s.id} className={s.id === HIGHLIGHT ? "series accent" : "series ref"}>
            <polyline points={s.pts.map((p, i) => `${x(i)},${y(p.mean_total_cost ?? 0)}`).join(" ")} className="line" />
            {s.pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.mean_total_cost ?? 0)} r={4} className="marker" />)}
            <text x={x(s.pts.length - 1) + 10} y={y(s.pts.at(-1)?.mean_total_cost ?? 0) + (s.id === HIGHLIGHT ? 14 : -6)}
                  className="value-label">{strategyName(s.id)}</text>
          </g>
        ))}
        {mults.map((_, i) => (
          <rect key={i} x={x(i) - (W - L - R) / (2 * (mults.length - 1))} y={T}
                width={(W - L - R) / (mults.length - 1)} height={H - T - B} className="hit"
                onPointerMove={() => setHover(i)} />
        ))}
      </svg>
      {flat && (
        <p className="footnote">
          The lines are flat because in practice mode neither strategy makes a mistake, so the penalty never applies.
          With a real model they slope, and may cross.
        </p>
      )}
      {hover !== null && (
        <div className="tooltip static" role="status">
          <div className="muted">Mistakes cost ×{mults[hover]}</div>
          {series.map((s) => (
            <div key={s.id}><span className={`line-key ${s.id === HIGHLIGHT ? "accent" : "ref"}`} />
              <strong>{money(s.pts[hover]?.mean_total_cost)}</strong> {strategyName(s.id)}</div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Compare({ domain }: { domain: DomainData }) {
  const ev = domain.evaluation;
  const sel = ev.metrics.find((m) => m.strategy === HIGHLIGHT)!;
  const ref = ev.metrics.find((m) => m.strategy === ev.reference)!;
  const saving = 1 - (sel.mean_total_cost ?? 0) / (ref.mean_total_cost || 1);
  const wrongCols = domain.actions.map((a) => a.id);
  return (
    <div className="compare">
      <p className="banner">
        <strong>Practice mode.</strong> These numbers come from the package's offline rules on {ev.n_cases} synthetic{" "}
        {domain.title.toLowerCase()} cases. They show how the comparison works, not how good an AI model is.
      </p>
      <div className="tiles">
        <div className="tile"><div className="tile-label">Cost per decision, AI picks the checks</div>
          <div className="tile-value">{money(sel.mean_total_cost)}</div>
          <div className="tile-delta">{pct(saving)} lower than checking everything ({money(ref.mean_total_cost)})</div></div>
        <div className="tile"><div className="tile-label">Checks per decision</div>
          <div className="tile-value">{sel.mean_retrievals.toFixed(1)}</div>
          <div className="tile-delta">vs {ref.mean_retrievals.toFixed(1)} when checking everything</div></div>
        <div className="tile"><div className="tile-label">Correct decisions</div>
          <div className="tile-value">{pct(sel.accuracy)}</div>
          <div className="tile-delta">vs {pct(ref.accuracy)} when checking everything</div></div>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3>Average total cost per decision</h3>
          <p className="sub">Checks + AI calls + mistake penalties. Hover a bar for the breakdown.</p>
          <CostBars metrics={ev.metrics} reference={ev.reference} />
        </section>
        <section className="card">
          <h3>Difference vs checking everything</h3>
          <p className="sub">Paired by case, with 95% intervals. Left of zero = cheaper.</p>
          <PairedChart domain={domain} />
        </section>
      </div>

      <div className="grid-2">
        <section className="card">
          <h3>What if mistakes cost more, or less?</h3>
          <p className="sub">Average total cost as every mistake penalty is scaled. If the lines cross, the winner depends on your costs.</p>
          <Sensitivity domain={domain} />
        </section>
        <section className="card">
          <h3>How to read this</h3>
          <ul className="reading">
            <li><strong>Total cost</strong> adds what the checks cost, what the AI calls cost, and a penalty for every
              wrong decision, using the domain's mistake prices (or yours).</li>
            <li><strong>Paired intervals</strong> compare strategies on the same cases. If an interval sits entirely
              left of zero, the saving is not just noise.</li>
            <li><strong>Sensitivity</strong> shows whether the winner changes when mistakes are priced 0.25× to 4×.
              If it does, agree on the prices before deciding.</li>
            <li><strong>Fallback rate</strong> is how often the safe label (here “{domain.fallback}”) was used. A
              cheap strategy that falls back to a person all the time just moves the cost elsewhere.</li>
          </ul>
        </section>
      </div>

      <section className="card">
        <h3>The same result in the terminal</h3>
        <p className="sub">Run it yourself: <code>pip install yantraa-evidence</code>, then <code>yantraa experiment --split test</code> and <code>yantraa evaluate</code>.</p>
        <pre className="terminal" tabIndex={0}>{ev.text}</pre>
      </section>

      <section className="card">
        <h3>Scoreboard</h3>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Strategy</th><th className="num">Correct</th>
                {wrongCols.map((a) => <th key={a} className="num">Wrong “{a}”</th>)}
                <th className="num">Fallback rate</th><th className="num">Checks</th><th className="num">Total cost</th></tr>
            </thead>
            <tbody>
              {ev.metrics.map((m) => (
                <tr key={m.strategy} className={m.strategy === HIGHLIGHT ? "current" : ""}>
                  <td>{strategyName(m.strategy)}</td><td className="num">{pct(m.accuracy)}</td>
                  {wrongCols.map((a) => <td key={a} className="num">{String(m[`wrong_${a}`] ?? 0)}</td>)}
                  <td className="num">{pct(m.fallback_rate)}</td><td className="num">{m.mean_retrievals.toFixed(2)}</td>
                  <td className="num">{money(m.mean_total_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
