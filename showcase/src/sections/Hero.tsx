import { useEffect, useState } from "react";
import { evidenceFor, live, returnsDomain, topLabel } from "../data";
import { humanize, labelColor, money, pct, sourceName } from "../format";

const PREFERRED: Record<string, string> = {
  get_order: "order_status", get_policy: "return_window_days", get_inspection: "damage_status",
};

/** Figure 1: a real decision, replayed on a loop. */
function HeroFigure() {
  const c = live.cases.find((x) => x.scenario === "conflicting_messages" && x.runs.fixed_order?.decision === "reject")!;
  const run = c.runs.fixed_order;
  const events = run.timeline;
  const [step, setStep] = useState(0);
  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    if (reduced) { setStep(events.length + 1); return; }
    const t = window.setTimeout(() => setStep((s) => (s > events.length + 2 ? 0 : s + 1)), step === 0 ? 900 : step > events.length ? 3600 : 1300);
    return () => window.clearTimeout(t);
  }, [step, events.length, reduced]);

  const lastJudge = [...events].reverse().find((e) => e.type === "judge");
  const conds = lastJudge?.type === "judge" ? lastJudge.conditions : null;

  return (
    <figure className="hero-figure" aria-label="A real decision by the model, replayed">
      <div className="hf-card">
        <div className="hf-eyebrow"><span className="live-dot" aria-hidden /> A real decision · {live.model}</div>
        <blockquote className="hf-quote">“{c.request}”</blockquote>
        <ol className="hf-steps">
          {events.map((e, i) => {
            if (i >= step) return null;
            if (e.type === "check") {
              const p = evidenceFor(run, e.source)[0]?.data.payload as Record<string, unknown> | undefined;
              const key = PREFERRED[e.source];
              const val = p && key ? String(p[key]).replace(/_/g, " ") : "";
              return (
                <li key={i} className="hf-check appear">
                  <span className="hf-n">{events.slice(0, i + 1).filter((x) => x.type === "check").length}</span>
                  <span className="hf-src">{sourceName(e.source)}</span>
                  <span className="hf-val">{humanize(key ?? "")}: <strong>{val}</strong> <span className="hf-ok">✓</span></span>
                  <span className="hf-cost">{money(e.cost)}</span>
                </li>
              );
            }
            if (e.type === "judge") {
              const [lbl, p] = topLabel(e.probabilities);
              return (
                <li key={i} className="hf-judge appear">
                  <span className="hf-lean">model leans</span>
                  <span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, lbl) }}>{humanize(lbl)}</span>
                  <span className="hf-p">{pct(p)}</span>
                </li>
              );
            }
            return null;
          })}
        </ol>
        <div className={`hf-verdict ${step > events.length ? "show" : ""}`} aria-hidden={step <= events.length}>
          <div className="hf-row">
            <span>Decided</span><span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, run.decision) }}>{humanize(run.decision)}</span>
            <span className="hf-arrow">·</span>
            <span>Answer key</span><span className="chip-label" style={{ ["--c" as string]: labelColor(returnsDomain, c.answer) }}>{humanize(c.answer)}</span>
          </div>
          {conds && (
            <p className="hf-note">
              Its own reading: delivered {pct(conds.delivered ?? 0)}, within window {pct(conds.within_window ?? 0)},
              damaged {pct(conds.damaged ?? 0)}. It still said no, which cost a {money(run.costs.decision_loss)} penalty.
            </p>
          )}
        </div>
      </div>
      <figcaption><span className="fig-n">Figure 1.</span> A customer's message contradicts the records. The model
        checked every record, rated every return condition as met, and rejected the return anyway.</figcaption>
    </figure>
  );
}

export function Hero() {
  return (
    <header className="hero" id="top">
      <div className="hero-text">
        <p className="eyebrow">Open-source research toolkit · Interactive demo</p>
        <h1>How much evidence does an AI need before it decides?</h1>
        <p className="lede">
          Before an AI approves a refund, pays a claim or clears an alert, it checks records. Every check costs money.
          Every wrong call costs more. <em>Yantraa Evidence</em> is a Python package for finding out which way of
          gathering evidence gives the best decisions for the money, in your domain and at your prices.
        </p>
        <div className="cta-row">
          <a className="btn primary" href="#demo">Watch a real model decide</a>
          <a className="btn" href="#start"><code>pip install yantraa-evidence</code></a>
        </div>
        <p className="byline">v0.3 · Apache-2.0 · Runs offline, or with OpenAI models</p>
      </div>
      <HeroFigure />
    </header>
  );
}
