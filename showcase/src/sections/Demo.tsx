import { useEffect, useRef, useState } from "react";
import { Graph } from "../components/Graph";
import { Thinking } from "../components/Thinking";
import { describeEvent, live, returnsDomain } from "../data";
import { humanize, labelColor, money, strategyName } from "../format";

const ORDER = ["selective", "fetch_all", "fixed_order", "confidence_threshold", "initial_only"];
const BLURB: Record<string, string> = {
  selective: "The model chooses which record to check next, one at a time, and when to stop.",
  fetch_all: "Check all three records, then decide. The reference baseline.",
  fixed_order: "Order, then policy, then inspection; stop as soon as the call isn't “escalate”.",
  confidence_threshold: "Same order, but stop as soon as the model is at least 85% sure.",
  initial_only: "Decide from the customer's message alone. The lower bound.",
};

export function Demo() {
  const start = live.cases.find((c) => c.runs.selective.correct && !c.runs.fetch_all.correct) ?? live.cases[0];
  const [caseId, setCaseId] = useState(start.id);
  const [strategy, setStrategy] = useState("selective");
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const seen = useRef(false);
  const c = live.cases.find((x) => x.id === caseId)!;
  const run = c.runs[strategy];
  const T = run.timeline.length;

  useEffect(() => { // start playing the first time the demo scrolls into view
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !seen.current) { seen.current = true; setPlaying(true); }
    }, { threshold: 0.35 });
    if (ref.current) io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  useEffect(() => { setPosition(0); if (seen.current) setPlaying(true); }, [caseId, strategy]);
  useEffect(() => {
    if (!playing) return;
    if (position >= T) { setPlaying(false); return; }
    const t = window.setTimeout(() => setPosition((p) => p + 1), position === 0 ? 700 : 1150);
    return () => window.clearTimeout(t);
  }, [playing, position, T]);

  const go = (p: number) => { setPlaying(false); setPosition(Math.max(0, Math.min(T, p))); };
  const status = position === 0 ? "Reading the request" : position >= T ? `Decided: ${humanize(run.decision)}` : describeEvent(run.timeline[position - 1]);

  return (
    <div className="demo" ref={ref}>
      <div className="picker" role="radiogroup" aria-label="Choose a request">
        {live.cases.map((x, i) => (
          <button key={x.id} role="radio" aria-checked={x.id === caseId} className="pick" onClick={() => setCaseId(x.id)}>
            <span className="pick-top"><span className="pick-n">{String(i + 1).padStart(2, "0")}</span>{x.scenario_label}</span>
            <span className="pick-text">“{x.request}”</span>
            <span className="pick-answer"><span className="swatch" style={{ background: labelColor(returnsDomain, x.answer) }} />Answer: {humanize(x.answer)}</span>
          </button>
        ))}
      </div>

      <div className="stage">
        <div className="stage-bar">
          <div className="tabs" role="tablist" aria-label="Strategy">
            {ORDER.map((s) => (
              <button key={s} role="tab" aria-selected={s === strategy} onClick={() => setStrategy(s)}>
                {strategyName(s)}
                <span className={`tab-mark ${c.runs[s].correct ? "ok" : "bad"}`} aria-label={c.runs[s].correct ? "right" : "wrong"}>
                  {c.runs[s].correct ? "✓" : "✗"}
                </span>
              </button>
            ))}
          </div>
          <p className="stage-blurb">{BLURB[strategy]}</p>
        </div>

        <div className="player">
          <button onClick={() => go(0)} aria-label="Restart">↺</button>
          <button onClick={() => go(position - 1)} aria-label="Back one step">‹</button>
          <button className="play" onClick={() => { if (position >= T) setPosition(0); setPlaying((p) => !p); }}
                  aria-label={playing ? "Pause" : "Play"}>{playing ? "❚❚" : "▶"}</button>
          <button onClick={() => go(position + 1)} aria-label="Forward one step">›</button>
          <div className="progress" aria-hidden>
            {Array.from({ length: T + 1 }, (_, i) => (
              <span key={i} className={i < position ? "done" : i === position ? "now" : ""} onClick={() => go(i)} />
            ))}
          </div>
          <span className="status" aria-live="polite">{status}</span>
        </div>

        <Graph domain={returnsDomain} caseData={c} run={run} position={position} />

        <div className="stage-lower">
          <Thinking domain={returnsDomain} run={run} position={position} />
          <aside className={`result ${position >= T ? "show" : ""}`}>
            {position >= T ? (
              <>
                <h4>Outcome</h4>
                <p className="result-line">
                  <span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, run.decision) }}>{humanize(run.decision)}</span>
                  <span className={run.correct ? "ok" : "bad"}>{run.correct ? "✓ matches the answer key" : `✗ answer key: ${humanize(c.answer)}`}</span>
                </p>
                <dl className="ledger">
                  <div><dt>Checks ({run.fetch_count})</dt><dd>{money(run.costs.retrieval)}</dd></div>
                  <div><dt>Model calls</dt><dd>{money(run.costs.model, 4)}</dd></div>
                  <div><dt>Mistake penalty</dt><dd>{money(run.costs.decision_loss)}</dd></div>
                  <div className="sum"><dt>Total cost</dt><dd>{money(run.costs.total)}</dd></div>
                </dl>
                <p className="note">Penalties are illustrative: a wrong approval $20, a wrong rejection $5, an unneeded escalation $1.
                  In the package you set your own.</p>
              </>
            ) : (
              <>
                <h4>Outcome</h4>
                <p className="note">The decision, whether it was right, and what it cost appear when the run finishes.</p>
                <button className="text-button" onClick={() => go(T)}>Skip to the decision →</button>
              </>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
