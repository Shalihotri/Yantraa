import { live, returnsDomain, topLabel } from "../data";
import { humanize, labelColor, money, pct, strategyName } from "../format";

const ORDER = ["fetch_all", "selective", "fixed_order", "confidence_threshold", "initial_only"];

/** F1: every conflicting-message case, checked fully: the model's own reading vs its decision. */
function OverTrust() {
  const rows = live.cases.filter((c) => c.scenario === "conflicting_messages").map((c) => {
    const run = c.runs.fetch_all;
    const j = [...run.timeline].reverse().find((e) => e.type === "judge");
    return { c, run, conds: j?.type === "judge" ? j.conditions ?? {} : {}, p: j?.type === "judge" ? topLabel(j.probabilities)[1] : 0 };
  });
  return (
    <table className="finding-table">
      <thead>
        <tr><th>Customer said</th>{returnsDomain.conditions.map((k) => <th key={k.id} className="num">{humanize(k.id)}</th>)}<th>Decided</th><th>Answer</th></tr>
      </thead>
      <tbody>
        {rows.map(({ c, run, conds, p }) => (
          <tr key={c.id}>
            <td className="said">“{c.request.replace(/^(Hi|Hello|Hey there|Good morning)[,.]\s*/i, "")}”</td>
            {returnsDomain.conditions.map((k) => (
              <td key={k.id} className="num"><span className="meter"><span style={{ width: `${(conds[k.id] ?? 0) * 100}%` }} /></span>{pct(conds[k.id] ?? 0)}</td>
            ))}
            <td><span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, run.decision) }}>{humanize(run.decision)}</span> <span className="muted">{pct(p)}</span></td>
            <td><span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, c.answer) }}>{humanize(c.answer)}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** F2: how sure the model was before seeing any evidence, against the 85% stopping threshold. */
function SureEarly() {
  const pts = live.cases.map((c) => {
    const j = c.runs.confidence_threshold.timeline.find((e) => e.type === "judge");
    return j?.type === "judge" ? topLabel(j.probabilities) : ["", 0] as [string, number];
  });
  const W = 520, H = 150, L = 20, R = 20, lo = 0.75, hi = 1;
  const x = (v: number) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mini-chart" role="img"
         aria-label={`Top probability before any evidence, all ${pts.length} requests between ${pct(Math.min(...pts.map((p) => p[1])))} and ${pct(Math.max(...pts.map((p) => p[1])))}, above the 85% threshold`}>
      <rect x={x(0.85)} y={16} width={x(1) - x(0.85)} height={86} className="zone" />
      <line x1={x(0.85)} x2={x(0.85)} y1={10} y2={102} className="threshold" />
      <text x={x(0.85) - 8} y={24} textAnchor="end" className="axis">stops here: 85%</text>
      <text x={x(0.85) + 8} y={24} className="axis">every request</text>
      <line x1={L} x2={W - R} y1={102} y2={102} className="baseline" />
      {[0.75, 0.8, 0.85, 0.9, 0.95, 1].map((t) => <text key={t} x={x(t)} y={120} textAnchor="middle" className="axis">{pct(t)}</text>)}
      {pts.map(([lbl, p], i) => (
        <circle key={i} cx={x(p)} cy={44 + (i % 4) * 16} r={6.5} fill={labelColor(returnsDomain, lbl)} className="dot">
          <title>{`Request ${i + 1}: ${humanize(lbl)} ${pct(p)} before any check`}</title>
        </circle>
      ))}
      <text x={L} y={H - 6} className="axis">Highest probability before checking anything. Every dot is “escalate”.</text>
    </svg>
  );
}

/** F3: accuracy and total cost per strategy, side by side (one measure per chart). */
function Scoreboard() {
  const ms = ORDER.map((s) => live.metrics.find((m) => m.strategy === s)!);
  const maxCost = Math.max(...ms.map((m) => m.mean_total_cost ?? 0));
  return (
    <div className="score">
      <div className="score-head"><span /><span>Right decisions</span><span>Average total cost</span><span className="num">Checks</span></div>
      {ms.map((m) => (
        <div key={m.strategy} className={`score-row ${m.strategy === "fetch_all" ? "ref" : ""}`}>
          <span className="score-name">{strategyName(m.strategy)}</span>
          <span className="bar-cell"><span className="track"><span className="hbar" style={{ width: `${m.accuracy * 100}%` }} /></span><span className="bar-val">{Math.round(m.accuracy * m.n)}/{m.n}</span></span>
          <span className="bar-cell"><span className="track"><span className="hbar cost" style={{ width: `${((m.mean_total_cost ?? 0) / maxCost) * 100}%` }} /></span><span className="bar-val">{money(m.mean_total_cost)}</span></span>
          <span className="num">{m.mean_retrievals.toFixed(1)}</span>
        </div>
      ))}
    </div>
  );
}

export function Findings() {
  const fa = live.metrics.find((m) => m.strategy === "fetch_all")!;
  const io = live.metrics.find((m) => m.strategy === "initial_only")!;
  return (
    <div className="findings">
      <article className="finding stacked">
        <div className="finding-text">
          <span className="finding-n">Finding 1</span>
          <h3>It checked everything, agreed with the evidence, and still sided with the customer's story.</h3>
          <p>In every request where the customer's message contradicted the records, the model rated all three return
            conditions as met (delivered, in window, damaged), then said <em>reject</em>. More evidence didn't help
            when the final step didn't follow it.</p>
          <p className="implication">What to try next: let the decision follow the model's own condition judgements, and
            measure whether that closes the gap.</p>
        </div>
        <figure className="finding-figure">
          <OverTrust />
          <figcaption><span className="fig-n">Figure 3.</span> “Check everything” on all four conflicting-message requests.
            Bars show the model's own probability that each condition holds.</figcaption>
        </figure>
      </article>

      <article className="finding">
        <div className="finding-text">
          <span className="finding-n">Finding 2</span>
          <h3>Confident before looking.</h3>
          <p>“Stop when confident” never checked a single record. Before seeing any evidence, the model was already at least
            85% sure it should escalate every request, so the rule stopped immediately. Confidence is not the same as
            correctness.</p>
          <p className="implication">What to try next: a stopping rule that ignores confidence in the fallback label.</p>
        </div>
        <figure className="finding-figure">
          <SureEarly />
          <figcaption><span className="fig-n">Figure 4.</span> One dot per request: the model's highest probability before
            any check, against the 85% threshold.</figcaption>
        </figure>
      </article>

      <article className="finding stacked">
        <div className="finding-text">
          <span className="finding-n">Finding 3</span>
          <h3>Checking more wasn't more right, and it cost more.</h3>
          <p>Checking everything got {Math.round(fa.accuracy * fa.n)} of {fa.n} right and averaged {money(fa.mean_total_cost)} per
            decision, about {Math.round((fa.mean_total_cost ?? 0) / (io.mean_total_cost ?? 1))}× the cost of not checking at all,
            because confident wrong rejections carry a penalty while escalating is cheap. Letting the model pick the checks
            did better ({money(live.metrics.find((m) => m.strategy === "selective")!.mean_total_cost)}), but it still
            checked all three records every time. The saving came from fewer mistakes, not fewer checks.</p>
          <p className="implication">Run it again and the same strategy scored {Math.round(live.rerun_selective.accuracy * live.rerun_selective.n)}/{live.rerun_selective.n}:
            live models vary, so compare with repeats and paired intervals, which the package does for you.</p>
        </div>
        <figure className="finding-figure">
          <Scoreboard />
          <figcaption><span className="fig-n">Figure 5.</span> All five strategies on the same {live.n_cases} requests,
            {" "}{live.model}. Total cost = checks + model calls + mistake penalties.</figcaption>
        </figure>
      </article>

      <aside className="caveat">
        <strong>Read with care.</strong> Ten synthetic requests, one model, one run, illustrative penalties. These are leads
        for the next experiment, not conclusions about {live.model} or about any strategy. The point of the toolkit is to
        make the next experiment cheap and the comparison honest.
      </aside>
    </div>
  );
}
